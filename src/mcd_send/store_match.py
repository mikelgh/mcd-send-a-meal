"""门店匹配：把「查店原点」从下单人切换到收件人。

这是整个项目里最容易被忽略、但决定成败的一步。

自点场景下所有人都在用 `query-nearby-stores`（查我附近的店），
但代送场景下这毫无意义——给杭州的爸妈点餐，我附近的店送不到他们那儿。
正确做法是先用收件人地址调 `delivery-query-stores` 拿到**可配送门店**，
再在这些门店里按距离和预计送达时间排序。

排序权重刻意做成可解释的：
    距离 0.45 / 预计送达 0.40 / 营业状态 0.15（不满足营业直接淘汰）
不用任何黑箱模型，每一项都能对着原始数据复算。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .util import clamp, pick, to_float

WEIGHT_DISTANCE = 0.45
WEIGHT_ETA = 0.40
WEIGHT_OPEN = 0.15


@dataclass
class StoreScore:
    store: dict[str, Any]
    code: str
    name: str
    distance_km: float | None
    eta_min: float | None
    is_open: bool
    score: float
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "distance_km": self.distance_km,
            "eta_min": self.eta_min,
            "is_open": self.is_open,
            "score": round(self.score, 4),
            "reasons": self.reasons,
        }


def _store_code(store: dict) -> str:
    return str(pick(store, "storeCode", "store_code", "code", "id", "storeId", "beCode") or "")


def _store_name(store: dict) -> str:
    return str(pick(store, "storeName", "name", "store_name", "shopName", "title") or "")


def _is_open(store: dict) -> bool:
    raw = pick(
        store, "businessStatus", "openStatus", "status", "isOpen", "bizStatus", "canOrder"
    )
    if raw is None:
        # 平台没给状态字段时，默认视为可用，不让整条链路卡住
        return True
    if isinstance(raw, bool):
        return raw
    text = str(raw)
    if any(word in text for word in ("营业", "可配送", "可下单", "正常", "开")):
        return True
    if any(word in text for word in ("休息", "打烊", "停业", "关闭", "不可配")):
        return False
    number = to_float(raw)
    if number is not None:
        return number not in (0, -1)
    return True


def score_stores(
    stores: list[dict],
    *,
    need_delivery: bool = True,
) -> list[StoreScore]:
    """给候选门店打分排序。输入必须已经是「收件人地址可配送」的门店。"""
    scored: list[StoreScore] = []

    distances = [
        to_float(pick(s, "distance", "distanceKm", "distanceText", "range"))
        for s in stores
    ]
    etas = [
        to_float(pick(s, "eta", "deliveryTime", "estimateTime", "arriveTime", "duration"))
        for s in stores
    ]
    d_vals = [d for d in distances if d is not None]
    e_vals = [e for e in etas if e is not None]
    d_max = max(d_vals) if d_vals else None
    e_max = max(e_vals) if e_vals else None

    for store, distance, eta in zip(stores, distances, etas):
        open_now = _is_open(store)
        reasons: list[str] = []

        if need_delivery and not open_now:
            reasons.append("当前不可配送，已排除")
            scored.append(
                StoreScore(store, _store_code(store), _store_name(store),
                           distance, eta, False, 0.0, reasons)
            )
            continue

        def ratio(value: float | None, top: float | None, lower_better: bool) -> float:
            if value is None or not top:
                return 0.5
            normalized = clamp(value / top, 0.0, 1.0)
            return normalized if lower_better else 1.0 - normalized

        d_score = 1.0 - ratio(distance, d_max, lower_better=True) if distance is not None else 0.5
        e_score = 1.0 - ratio(eta, e_max, lower_better=True) if eta is not None else 0.5
        o_score = 1.0 if open_now else 0.0

        score = WEIGHT_DISTANCE * d_score + WEIGHT_ETA * e_score + WEIGHT_OPEN * o_score

        if distance is not None:
            reasons.append(f"距收件人约 {distance:g}km")
        if eta is not None:
            reasons.append(f"预计送达约 {eta:g} 分钟")
        if open_now:
            reasons.append("当前可配送")
        else:
            reasons.append("状态未知，按可用处理")

        scored.append(
            StoreScore(store, _store_code(store), _store_name(store),
                       distance, eta, open_now, score, reasons)
        )

    scored.sort(key=lambda s: (-s.score, s.code))
    return scored


def pick_store(stores: list[dict], *, need_delivery: bool = True) -> StoreScore:
    ranked = score_stores(stores, need_delivery=need_delivery)
    if not ranked:
        raise ValueError(
            "收件人地址没有匹配到任何可配送门店。"
            "请确认地址是否在麦当劳外送范围内，或换用到店取餐。"
        )
    # 代送场景下，绝不能把「休息中」的店当成交付店。
    # score_stores 会把不可配送的店排到最后（score=0），这里显式跳过它们；
    # 如果剩下全是休息中的店，直接报错，而不是硬选一家送不到的。
    if need_delivery:
        open_ones = [s for s in ranked if s.is_open]
        if not open_ones:
            raise ValueError(
                "收件人地址附近的门店当前都不可配送（休息中）。"
                "请稍后重试，或换用收件人公司/家附近的另一个地址。"
            )
        best = open_ones[0]
    else:
        best = ranked[0]
    if not best.code:
        raise ValueError(
            "门店数据里没有可用的门店编码（storeCode），无法继续查询菜单。"
            f"原始字段：{sorted(best.store)}"
        )
    return best
