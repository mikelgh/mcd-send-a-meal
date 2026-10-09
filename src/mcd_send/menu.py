"""菜单理解与配餐求解。

做三件事：
1. 把门店返回的餐品按名称分类（主餐 / 小食 / 饮品 / 甜点 / 早餐）；
2. 用官方营养表给每件餐品挂上能量、钠、蛋白、脂肪；
3. 在收件人画像的硬约束下，组合出若干「可直接下单」的候选套餐。

两条刻意的设计原则：

* **数值不进 LLM。** 热量、钠、蛋白的加总与阈值判定全部在本地用纯 Python 算，
  模型只负责把结果讲成人话，不参与任何算术。
* **查不到营养就如实说查不到。** 官方营养表没收录的新品（比如季节限定），
  返回 `nutrition_missing=True`，绝不按 0 处理——否则「钠 0mg」会被误判成健康。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from typing import Any, Iterable

from .profiles import RecipientProfile
from .util import norm_text, pick, to_float

CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("breakfast", ("早餐", "粥", "油条", "煎饼", "松饼", "麦满分", "蛋堡", "薯饼")),
    ("dessert", ("冰淇淋", "圣代", "麦旋风", "甜筒", "蛋筒", "派", "蛋糕", "布丁")),
    ("drink", ("可乐", "雪碧", "芬达", "咖啡", "拿铁", "美式", "豆浆", "牛奶",
               "茶", "橙汁", "矿泉水", "纯净水", "奶昔", "可可")),
    ("side", ("薯条", "玉米", "沙拉", "麦乐鸡", "鸡块", "鸡翅", "洋葱圈", "水果")),
    ("main", ("堡", "卷", "饭", "鸡腿", "鸡排", "牛肉", "猪肉", "鱼", "培根", "猪柳")),
]

COMBO_SHAPES: list[tuple[str, tuple[str, ...]]] = [
    ("简餐", ("main",)),
    ("主餐 + 小食", ("main", "side")),
    ("主餐 + 饮品", ("main", "drink")),
    ("全套", ("main", "side", "drink")),
]


@dataclass
class Combo:
    label: str
    items: list[dict[str, Any]]
    energy_kcal: float | None = None
    sodium_mg: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    nutrition_missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    preference_hits: list[str] = field(default_factory=list)
    price: dict[str, Any] | None = None
    gm_service_code: str = ""  # 该方案试算时命中并应在下单时使用的券（gmServiceCode）

    @property
    def names(self) -> list[str]:
        return [str(pick(i, "name", "mealName", "title", "cnName") or "?") for i in self.items]

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "items": self.names,
            "energy_kcal": self.energy_kcal,
            "sodium_mg": self.sodium_mg,
            "protein_g": self.protein_g,
            "fat_g": self.fat_g,
            "nutrition_missing": self.nutrition_missing,
            "notes": self.notes,
            "preference_hits": self.preference_hits,
            "price": self.price,
        }


def classify(meal: dict[str, Any]) -> str:
    name = str(pick(meal, "name", "mealName", "title", "cnName", "productName") or "")
    category = str(pick(meal, "categoryName", "category", "typeName", "classify") or "")
    haystack = name + category
    for label, keywords in CATEGORY_RULES:
        if any(k in haystack for k in keywords):
            return label
    return "other"


def build_nutrition_index(nutrition_rows: Iterable[dict]) -> dict[str, dict]:
    """按归一化后的餐品名建索引，方便菜单项与营养表对齐。"""
    index: dict[str, dict] = {}
    for row in nutrition_rows:
        if not isinstance(row, dict):
            continue
        name = pick(row, "name", "foodName", "mealName", "cnName", "title")
        key = norm_text(name)
        if key:
            index[key] = row
    return index


def lookup_nutrition(meal: dict, index: dict[str, dict]) -> dict | None:
    name = pick(meal, "name", "mealName", "title", "cnName", "productName")
    key = norm_text(name)
    if not key:
        return None
    if key in index:
        return index[key]
    # 退一步做包含匹配：「巨无霸汉堡」对上「巨无霸」
    for candidate_key, row in index.items():
        if candidate_key and (candidate_key in key or key in candidate_key):
            return row
    return None


def _nutrient(nutrition: dict | None, *keys: str) -> float | None:
    if not nutrition:
        return None
    raw = pick(nutrition, *keys)
    return to_float(raw)


def _constraints_ok(
    combo: Combo, profile: RecipientProfile
) -> bool:
    """逐条硬约束判定。查不到营养的维度跳过判定，但调用方能看到缺哪些。"""
    if profile.energy_max_kcal is not None and combo.energy_kcal is not None:
        if combo.energy_kcal > profile.energy_max_kcal:
            return False
    if profile.energy_min_kcal is not None and combo.energy_kcal is not None:
        if combo.energy_kcal < profile.energy_min_kcal:
            return False
    if profile.sodium_max_mg is not None and combo.sodium_mg is not None:
        if combo.sodium_mg > profile.sodium_max_mg:
            return False
    if profile.protein_min_g is not None and combo.protein_g is not None:
        if combo.protein_g < profile.protein_min_g:
            return False
    if profile.fat_max_g is not None and combo.fat_g is not None:
        if combo.fat_g > profile.fat_max_g:
            return False
    return True


def _preference_hits(combo: Combo, profile: RecipientProfile) -> list[str]:
    text = "".join(combo.names)
    return [word for word in profile.prefer_keywords if word and word in text]


def _blocked(combo: Combo, profile: RecipientProfile) -> bool:
    text = "".join(combo.names) + "".join(
        str(pick(i, "description", "desc", "remark") or "") for i in combo.items
    )
    return any(word and word in text for word in profile.avoid_keywords)


def build_combos(
    meals: list[dict],
    profile: RecipientProfile,
    nutrition_index: dict[str, dict],
    *,
    max_per_category: int = 6,
    max_combos: int = 40,
) -> tuple[list[Combo], list[str]]:
    """在收件人约束下生成候选套餐。

    返回 (候选列表, 无解时的放宽建议)。
    无解时不静默放宽标准，而是明确告诉用户哪条约束卡住了。
    """
    buckets: dict[str, list[dict]] = {"main": [], "side": [], "drink": [], "dessert": [], "breakfast": [], "other": []}
    for meal in meals:
        if isinstance(meal, dict):
            buckets[classify(meal)].append(meal)

    mains = buckets["main"] or buckets["breakfast"] or buckets["other"]
    sides = buckets["side"]
    drinks = buckets["drink"]

    if not mains:
        return [], ["门店菜单里没有识别到主餐，可能是菜单结构超出预期，建议人工看一眼原始菜单。"]

    combos: list[Combo] = []

    for label, shape in COMBO_SHAPES:
        pools: list[list[dict]] = []
        skip = False
        for category in shape:
            pool = {
                "main": mains,
                "side": sides,
                "drink": drinks,
            }.get(category, [])
            if not pool:
                skip = True
                break
            pools.append(pool[:max_per_category])
        if skip:
            continue

        for picked_items in product(*pools):
            items = list(picked_items)
            combo = Combo(label=label, items=items)

            total_energy = total_sodium = total_protein = total_fat = 0.0
            counted = {"energy": False, "sodium": False, "protein": False, "fat": False}

            for item in items:
                nutrition = lookup_nutrition(item, nutrition_index)
                name = str(pick(item, "name", "mealName", "title", "cnName") or "?")
                if nutrition is None:
                    combo.nutrition_missing.append(name)
                    continue

                energy = _nutrient(nutrition, "energy", "calorie", "kcal", "energyKcal", "heat")
                sodium = _nutrient(nutrition, "sodium", "na", "sodiumMg")
                protein = _nutrient(nutrition, "protein", "proteinG", "pro")
                fat = _nutrient(nutrition, "fat", "fatG", "lipid")

                if energy is not None:
                    total_energy += energy
                    counted["energy"] = True
                if sodium is not None:
                    total_sodium += sodium
                    counted["sodium"] = True
                if protein is not None:
                    total_protein += protein
                    counted["protein"] = True
                if fat is not None:
                    total_fat += fat
                    counted["fat"] = True

            combo.energy_kcal = round(total_energy, 1) if counted["energy"] else None
            combo.sodium_mg = round(total_sodium, 1) if counted["sodium"] else None
            combo.protein_g = round(total_protein, 1) if counted["protein"] else None
            combo.fat_g = round(total_fat, 1) if counted["fat"] else None

            if combo.nutrition_missing:
                combo.notes.append(
                    f"官方营养表未收录：{'、'.join(combo.nutrition_missing)}，相关维度未计入判定"
                )
            if profile.no_ice and any(classify(i) == "drink" for i in items):
                combo.notes.append("饮品去冰")

            if _blocked(combo, profile):
                continue
            if not _constraints_ok(combo, profile):
                continue

            combo.preference_hits = _preference_hits(combo, profile)
            combos.append(combo)

    combos.sort(
        key=lambda c: (
            -len(c.preference_hits),
            c.nutrition_missing != [],
            c.sodium_mg if c.sodium_mg is not None else 1e9,
            -(c.protein_g or 0),
        )
    )

    if combos:
        return combos[:max_combos], []

    return [], _relaxation_hints(profile)


def _relaxation_hints(profile: RecipientProfile) -> list[str]:
    """全部候选都被约束挡掉时，明确列出是哪几条约束在卡。"""
    hints: list[str] = []
    if profile.energy_max_kcal is not None:
        hints.append(f"能量上限 {profile.energy_max_kcal:g} kcal")
    if profile.energy_min_kcal is not None:
        hints.append(f"能量下限 {profile.energy_min_kcal:g} kcal")
    if profile.sodium_max_mg is not None:
        hints.append(f"钠上限 {profile.sodium_max_mg:g} mg")
    if profile.protein_min_g is not None:
        hints.append(f"蛋白下限 {profile.protein_min_g:g} g")
    if profile.fat_max_g is not None:
        hints.append(f"脂肪上限 {profile.fat_max_g:g} g")
    if profile.avoid_keywords:
        hints.append(f"忌口：{'、'.join(profile.avoid_keywords)}")
    return hints or ["未设置任何约束，但仍无候选，请检查门店菜单是否正常返回。"]
