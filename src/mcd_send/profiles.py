"""收件人画像。

代送和自点的根本区别在于约束来自**收件人**而不是下单人：
给爸妈点要控钠、给恋人点要控卡、给加班的同事点要高蛋白扛饿。
这里把「关系」翻译成一组可执行的营养约束，供本地求解器使用。
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class RecipientProfile:
    """收件人的点餐约束。所有阈值都是硬约束，求解器不做静默放宽。"""

    relation: str = "friend"
    energy_max_kcal: float | None = None
    energy_min_kcal: float | None = None
    sodium_max_mg: float | None = None
    protein_min_g: float | None = None
    fat_max_g: float | None = None
    no_ice: bool = False
    avoid_keywords: list[str] = field(default_factory=list)
    prefer_keywords: list[str] = field(default_factory=list)
    note: str = ""

    def merge(self, override: dict[str, Any] | None) -> RecipientProfile:
        """联系人自带画像覆盖默认画像；只覆盖显式给出的字段。"""
        if not override:
            return self
        data = asdict(self)
        for key, value in override.items():
            if value is None:
                continue
            if key in data:
                data[key] = value
        return RecipientProfile(**data)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# 关系 → 默认约束。
#
# 钠上限取 1500mg 是权衡后的结果，不是随手写的数：
# 麦当劳单品的钠普遍落在 900–1200mg 区间，若按「每日 2000mg 的三分之一」
# 取 670mg，真实菜单上会直接无解（连一个巨无霸单独吃都超）。所以按
# 「一天最多两餐快餐」的假设把单餐上限定在 1500mg，既能筛掉真正的
# 高钠组合，又留得出可执行的方案空间。
#
# 蛋白下限 30g 对应一顿正餐能给到中老年人和健身人群一个像样的量。
_BASE: dict[str, dict[str, Any]] = {
    "parent": {
        "sodium_max_mg": 1500,
        "energy_max_kcal": 800,
        "protein_min_g": 20,
        "no_ice": True,
        "avoid_keywords": ["辣", "冰"],
        "prefer_keywords": ["粥", "玉米", "豆浆", "鸡"],
        "note": "长辈：控钠、去冰、避开难嚼和过辣的",
    },
    "partner": {
        "energy_max_kcal": 700,
        "fat_max_g": 30,
        "prefer_keywords": ["沙拉", "鸡", "玉米"],
        "avoid_keywords": [],
        "note": "伴侣：一般在控卡，警惕大份薯条和含糖饮料",
    },
    "friend": {
        "energy_max_kcal": 1000,
        "note": "朋友：不设太硬的约束，以好吃和限定新品优先",
    },
    "colleague": {
        "protein_min_g": 30,
        "energy_min_kcal": 500,
        "prefer_keywords": ["鸡", "牛", "堡"],
        "note": "同事：加班场景要扛饿，优先高蛋白和主食",
    },
    "client": {
        "energy_max_kcal": 900,
        "prefer_keywords": ["牛", "堡", "咖啡"],
        "avoid_keywords": [],
        "note": "客户：偏正式的口味，避开太随意的单品",
    },
}


def profile_for(relation: str, override: dict[str, Any] | None = None) -> RecipientProfile:
    """按关系取出默认画像，再用联系人自己的覆盖项合并。"""
    base = _BASE.get(relation or "friend", _BASE["friend"])
    profile = RecipientProfile(relation=relation or "friend", **base)
    return profile.merge(override)


def known_relations() -> list[str]:
    return sorted(_BASE)
