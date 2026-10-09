"""核价与优惠券核算。

三条硬规矩：

1. **金额一律以官方 `calculate-price` 为准。** 本地不做任何价格加总，
   菜单上标的「随单购价」经常和真实应付不一致，只有官方接口说了算。
2. **单位坑必须显式处理。** 麦当劳 MCP 返回的金额单位是**分**，
   直接当元用会差 100 倍。这里统一走 `to_yuan()`，并允许用环境变量
   `MCD_PRICE_UNIT=yuan` 覆盖（万一平台改了单位）。
3. **券必须按目标门店重查。** 异地场景下，同一个账户在收件人所在门店
   的可用券和本地并不相同，不能拿本地下单时的券包直接套用。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from .menu import Combo
from .util import pick, to_float

UNIT_ENV = "MCD_PRICE_UNIT"

TOTAL_KEYS = ("totalAmount", "originalAmount", "totalPrice", "amount", "orderAmount")
PAYABLE_KEYS = (
    "payableAmount", "payAmount", "actualAmount", "needPayAmount",
    "finalAmount", "totalFee", "payable",
)
DELIVERY_KEYS = ("deliveryFee", "deliveryPrice", "shippingFee", "deliverFee", "freight")
DISCOUNT_KEYS = ("discountAmount", "couponAmount", "reduceAmount", "discount", "preferentialAmount")


def price_unit() -> str:
    return (os.environ.get(UNIT_ENV, "cent") or "cent").strip().lower()


def to_yuan(value: Any) -> float | None:
    """把官方返回的金额换算成元。默认按「分」处理。"""
    number = to_float(value)
    if number is None:
        return None
    return number if price_unit() == "yuan" else number / 100.0


def fmt_yuan(value: Any) -> str:
    yuan = to_yuan(value)
    return "—" if yuan is None else f"¥{yuan:.2f}"


@dataclass
class PriceBreakdown:
    total_yuan: float | None = None
    payable_yuan: float | None = None
    delivery_yuan: float | None = None
    discount_yuan: float | None = None
    coupon_id: str = ""
    coupon_name: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def goods_payable_yuan(self) -> float | None:
        """商品实付 = 商品原价 - 优惠。不含配送费。"""
        if self.total_yuan is None:
            return None
        return round(self.total_yuan - (self.discount_yuan or 0.0), 2)

    @property
    def net_saved_yuan(self) -> float | None:
        """净省 = 商品原价 - 最终应付（含配送费）。

        注意这个值可能小于券面额甚至为负——外送配送费会吃掉一部分优惠。
        所以展示时必须把配送费单独列出来，只说一个「省了多少」是误导。
        """
        if self.total_yuan is None or self.payable_yuan is None:
            return None
        return round(self.total_yuan - self.payable_yuan, 2)

    # 兼容旧字段名
    @property
    def saved_yuan(self) -> float | None:
        return self.net_saved_yuan

    def lines(self) -> list[tuple[str, float | None]]:
        """给展示层用的明细行，顺序固定，缺项保留为 None。"""
        return [
            ("商品原价", self.total_yuan),
            (f"券优惠（{self.coupon_name}）" if self.coupon_name else "券优惠",
             None if self.discount_yuan is None else -self.discount_yuan),
            ("配送费", self.delivery_yuan),
            ("应付", self.payable_yuan),
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_yuan": self.total_yuan,
            "payable_yuan": self.payable_yuan,
            "delivery_yuan": self.delivery_yuan,
            "discount_yuan": self.discount_yuan,
            "goods_payable_yuan": self.goods_payable_yuan,
            "net_saved_yuan": self.net_saved_yuan,
            "coupon_id": self.coupon_id,
            "coupon_name": self.coupon_name,
        }


def parse_price_result(result: dict, coupon: dict | None = None) -> PriceBreakdown:
    total = pick(result, *TOTAL_KEYS)
    payable = pick(result, *PAYABLE_KEYS)
    delivery = pick(result, *DELIVERY_KEYS)
    discount = pick(result, *DISCOUNT_KEYS)

    # 有些返回把金额藏在 items/settle 之类的子对象里
    if payable is None:
        for nested_key in ("settle", "summary", "priceInfo", "orderAmountInfo", "data"):
            nested = result.get(nested_key)
            if isinstance(nested, dict):
                payable = pick(nested, *PAYABLE_KEYS)
                total = total or pick(nested, *TOTAL_KEYS)
                delivery = delivery or pick(nested, *DELIVERY_KEYS)
                discount = discount or pick(nested, *DISCOUNT_KEYS)
                if payable is not None:
                    break

    # 支付金额缺失时，用「总价 - 优惠 + 配送费」兜一个可见的估算值，
    # 但会在报告里标明这是推算值，不当成官方结论。
    if payable is None:
        t, d, fee = to_float(total), to_float(discount), to_float(delivery)
        if t is not None:
            payable = t - (d or 0) + (fee or 0)

    return PriceBreakdown(
        total_yuan=to_yuan(total),
        payable_yuan=to_yuan(payable),
        delivery_yuan=to_yuan(delivery),
        discount_yuan=to_yuan(discount),
        coupon_id=str(pick(coupon or {}, "couponId", "id", "code") or ""),
        coupon_name=str(pick(coupon or {}, "name", "couponName", "title", "desc") or ""),
        raw=result if isinstance(result, dict) else {},
    )


def coupon_sort_key(coupon: dict) -> tuple:
    """挑券时的启发式排序：先看能否叠加配送优惠，再看到期时间，最后看面额。"""
    amount = to_float(
        pick(coupon, "discountAmount", "amount", "faceValue", "value", "couponAmount")
    ) or 0.0
    expires = str(pick(coupon, "expireTime", "endTime", "validEndTime", "expireDate") or "9999")
    return (-amount, expires)


def top_coupons(coupons: list[dict], limit: int = 3) -> list[dict]:
    usable = [
        c for c in coupons
        if isinstance(c, dict) and pick(c, "couponId", "id", "code")
    ]
    usable.sort(key=coupon_sort_key)
    return usable[:limit]


def build_order_args(
    *,
    store_code: str,
    combo: Combo,
    address_id: str | None,
    order_type: int = 1,
    coupon_id: str | None = None,
) -> dict[str, Any]:
    """构造下单/核价参数。

    参数名这块**故意不猜死**：`ToolSchemas.resolve()` 会拿平台真实的
    inputSchema 做一次归一化匹配，匹配不上就带着合法参数名报错，
    所以第一次真实调用就能拿到准确反馈，不会静默失败。
    """
    items: list[dict[str, Any]] = []
    for item in combo.items:
        code = pick(item, "code", "mealCode", "spuId", "productCode", "id")
        if not code:
            continue
        items.append({"mealCode": str(code), "count": 1})

    args: dict[str, Any] = {
        "storeCode": store_code,
        "orderType": order_type,
        "items": items,
    }
    if address_id:
        args["addressId"] = address_id
    if coupon_id:
        args["couponId"] = coupon_id
    return args


def rank_by_price(combos: list[Combo]) -> list[Combo]:
    """按实付升序排；没核到价的排最后，不参与「最便宜」的结论。"""
    priced = [c for c in combos if c.price]
    unpriced = [c for c in combos if not c.price]

    def payable(combo: Combo) -> float:
        return (combo.price or {}).get("payable_yuan") or 1e9

    priced.sort(key=payable)
    return priced + unpriced
