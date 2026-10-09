"""代送流程编排。

把「一句话给某人点一份」拆成两段，中间必须由人确认：

    只读阶段 plan_send()
        收件人 → 收件人地址下的可配送门店 → 该门店真实菜单
        → 收件人画像约束求解 → 按目标门店重查券 → 官方核价 → 候选方案

    写入阶段 execute_send()   ← 必须显式 confirm
        创建订单 → 返回支付链接 → 可查配送进度 / 可取消

这样切分的理由很直接：代送是**替别人花钱**，比自点更容易出问题
（地址错、忌口漏、对方不在家）。任何写操作都不允许静默执行。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .contacts import Contact, find_contact
from .menu import Combo, build_combos, build_nutrition_index
from .pricing import (
    PriceBreakdown,
    build_order_args,
    parse_price_result,
    rank_by_price,
    top_coupons,
)
from .store_match import StoreScore, pick_store
from .util import pick

ProgressFn = Callable[[str], None]


def _noop(_: str) -> None:
    pass


@dataclass
class SendPlan:
    contact: Contact
    store: StoreScore
    combos: list[Combo]
    coupons: list[dict]
    warnings: list[str] = field(default_factory=list)
    menu_size: int = 0
    candidates_considered: int = 0

    @property
    def recommended(self) -> Combo | None:
        ranked = rank_by_price(self.combos)
        return ranked[0] if ranked else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "contact": self.contact.to_dict(),
            "store": self.store.to_dict(),
            "menu_size": self.menu_size,
            "candidates_considered": self.candidates_considered,
            "warnings": self.warnings,
            "combos": [c.to_dict() for c in rank_by_price(self.combos)],
        }


def _diversify(combos: list[Combo], limit: int) -> list[Combo]:
    """挑候选时保证主餐不重样。

    求解器排出来的前几名经常是同一个主餐的不同搭配（比如「板烧 + 玉米杯」
    「板烧 + 豆浆」「板烧 + 玉米杯 + 可乐」），全拿去核价等于只给了用户
    一个主餐选择。这里先按主餐去重各取一个，再按原序补齐剩下的名额。
    """
    if len(combos) <= limit:
        return combos

    picked: list[Combo] = []
    seen_mains: set[str] = set()
    for combo in combos:
        main = combo.names[0] if combo.names else ""
        if main in seen_mains:
            continue
        seen_mains.add(main)
        picked.append(combo)
        if len(picked) >= limit:
            return picked

    for combo in combos:
        if combo in picked:
            continue
        picked.append(combo)
        if len(picked) >= limit:
            break
    return picked


def plan_send(
    tools: Any,
    alias: str,
    *,
    contacts_path: str | None = None,
    progress: ProgressFn = _noop,
    max_combos_to_price: int = 6,
    coupon_probe: int = 3,
) -> SendPlan:
    """只读地算出一份代送方案。这一步不会产生任何订单。"""
    warnings: list[str] = []

    progress(f"读取收件人「{alias}」")
    contact = find_contact(alias, contacts_path)
    profile = contact.recipient_profile
    if not contact.address_id:
        raise ValueError(
            f"联系人「{contact.alias}」还没有地址 ID。\n"
            "先用 create-address 建一条收件人地址，把返回的 ID 填进地址簿的 address_id 字段。"
        )

    progress(f"按收件人地址找可配送门店（{contact.city or '未知城市'}）")
    stores = tools.stores_for_address(contact.address_id)
    if not stores:
        raise ValueError(
            f"收件人地址「{contact.alias}」没有匹配到可配送门店。\n"
            "可能是地址超出麦当劳外送范围。可以改用「到店取餐」模式，"
            "或换成收件人公司/家附近的另一个地址。"
        )
    store = pick_store(stores)
    progress(
        f"选中门店 {store.name}（{store.code}）"
        + (f" · {store.distance_km:g}km" if store.distance_km is not None else "")
    )

    progress("拉取该门店真实在售菜单")
    meals = tools.meals(store.code)
    if not meals:
        raise ValueError(f"门店 {store.name} 没有返回菜单，无法继续。")

    progress("拉取官方营养表并做约束求解")
    nutrition_rows = tools.nutrition()
    index = build_nutrition_index(nutrition_rows)
    combos, hints = build_combos(meals, profile, index)
    if not combos:
        raise ValueError(
            "在收件人约束下没有可行套餐。卡住的约束是：\n  - "
            + "\n  - ".join(hints)
            + "\n可以放宽其中一条，或把联系人的 profile 覆盖项改松一点。"
        )
    if not index:
        warnings.append("官方营养表返回为空，营养约束本次未生效（价格仍然有效）。")
    elif any(c.nutrition_missing for c in combos):
        warnings.append(
            "部分餐品官方营养表未收录，相关维度的判定已跳过，报告里会逐条标出。"
        )

    progress(f"按收件人所在门店重查可用券（门店 {store.code}）")
    coupons = tools.store_coupons(store.code)
    if not coupons:
        coupons = tools.my_coupons()
        if coupons:
            warnings.append(
                "该门店没有返回门店券，已回退使用账户券包。"
                "注意异地门店的券适用范围可能不同，请以核价结果为准。"
            )
    probe = top_coupons(coupons, coupon_probe)

    progress("调官方核价接口逐组试算真实应付")
    priced: list[Combo] = []
    shortlist = _diversify(combos, max_combos_to_price)
    for combo in shortlist:
        best: PriceBreakdown | None = None
        for coupon in [None, *probe]:
            args = build_order_args(
                store_code=store.code,
                combo=combo,
                address_id=contact.address_id,
                coupon_id=pick(coupon or {}, "couponId", "id", "code") if coupon else None,
            )
            try:
                result = tools.calculate_price(args)
            except Exception as exc:  # noqa: BLE001 - 单组试算失败不该拖垮整个方案
                warnings.append(f"核价失败（{combo.label}）：{exc}")
                continue
            breakdown = parse_price_result(result, coupon)
            if breakdown.payable_yuan is None:
                continue
            if best is None or (breakdown.payable_yuan or 1e9) < (best.payable_yuan or 1e9):
                best = breakdown
        if best is not None:
            combo.price = best.to_dict()
            priced.append(combo)

    if not priced:
        warnings.append(
            "所有候选都没能核到价。请先跑一次 --inspect 看下 calculate-price 的参数是否被平台调整过。"
        )

    return SendPlan(
        contact=contact,
        store=store,
        combos=priced or combos,
        coupons=coupons,
        warnings=warnings,
        menu_size=len(meals),
        candidates_considered=len(shortlist),
    )


@dataclass
class SendResult:
    order_id: str = ""
    pay_url: str = ""
    status: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    eta_min: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "pay_url": self.pay_url,
            "status": self.status,
            "eta_min": self.eta_min,
        }


_ORDER_ID_KEYS = ("orderId", "orderNo", "id", "orderCode")
_PAY_URL_KEYS = ("payUrl", "paymentUrl", "payLink", "url", "jumpUrl", "cashierUrl")
_ETA_KEYS = ("estimateTime", "eta", "deliveryTime", "arriveTime", "expectTime")


def execute_send(
    tools: Any,
    plan: SendPlan,
    *,
    combo: Combo | None = None,
    confirm: bool = False,
    progress: ProgressFn = _noop,
) -> SendResult:
    """真正下单。没有 confirm=True 就绝不发请求。"""
    if not confirm:
        raise PermissionError(
            "代送订单涉及真实扣款，必须显式确认。请在命令后加 --confirm 再执行一次。"
        )

    target = combo or plan.recommended
    if target is None:
        raise ValueError("没有可下单的套餐。")

    coupon_id = (target.price or {}).get("coupon_id") or None
    args = build_order_args(
        store_code=plan.store.code,
        combo=target,
        address_id=plan.contact.address_id,
        coupon_id=coupon_id,
    )

    progress(f"创建订单：{'、'.join(target.names)} → {plan.contact.alias}")
    result = tools.create_order(args)

    order_id = str(pick(result, *_ORDER_ID_KEYS) or "")
    pay_url = str(pick(result, *_PAY_URL_KEYS) or "")
    if not order_id:
        raise ValueError(
            "下单接口没有返回订单号，请检查返回结构："
            f"{sorted(result) if isinstance(result, dict) else type(result)}"
        )

    return SendResult(
        order_id=order_id,
        pay_url=pay_url,
        status=str(pick(result, "status", "orderStatus", "statusDesc") or "已创建"),
        eta_min=None,
        raw=result if isinstance(result, dict) else {},
    )


def track_order(tools: Any, order_id: str) -> dict[str, Any]:
    """查配送进度。代送场景下这一步比自点重要得多——收件人不在场，只能靠它。"""
    detail = tools.query_order(order_id)
    return {
        "order_id": order_id,
        "status": pick(detail, "status", "orderStatus", "statusDesc", "orderStatusName"),
        "eta_min": pick(detail, *_ETA_KEYS),
        "items": pick(detail, "items", "mealList", "orderItems", "products"),
        "address": pick(detail, "address", "addressDetail", "receiverAddress"),
        "receiver": pick(detail, "receiverName", "contactName", "receiver"),
        "raw": detail,
    }
