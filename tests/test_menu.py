"""menu 模块：分类 / 营养对齐 / 约束求解 / 营养缺失如实标注。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcd_send.fixtures import MEALS, NUTRITION  # noqa: E402
from mcd_send.menu import build_combos, build_nutrition_index, classify, lookup_nutrition  # noqa: E402
from mcd_send.profiles import profile_for  # noqa: E402


class TestMenu(unittest.TestCase):
    def test_classify_categories(self):
        self.assertEqual(classify({"name": "巨无霸汉堡"}), "main")
        self.assertEqual(classify({"name": "中薯条"}), "side")
        self.assertEqual(classify({"name": "中杯可乐"}), "drink")
        self.assertEqual(classify({"name": "麦旋风"}), "dessert")
        self.assertEqual(classify({"name": "猪柳蛋堡"}), "breakfast")  # 蛋堡属早餐
        self.assertEqual(classify({"name": "鲜煮咖啡"}), "drink")
        self.assertEqual(classify({"name": "一个不知道是什么的"}), "other")

    def test_build_nutrition_index_normalizes_names(self):
        index = build_nutrition_index(NUTRITION)
        # key 是归一化后的全名（去空格/标点），lookup 时再做包含匹配
        self.assertIn("巨无霸汉堡", index)
        self.assertIn("麦乐鸡5块", index)  # 「麦乐鸡 5 块」归一化丢了空格

    def test_lookup_nutrition_fuzzy(self):
        index = build_nutrition_index(NUTRITION)
        meal = {"name": "巨无霸汉堡（套餐）"}
        row = lookup_nutrition(meal, index)
        self.assertIsNotNone(row)
        self.assertEqual(row["sodium"], 950)

    def test_build_combos_respects_parent_constraints(self):
        profile = profile_for("parent")  # 忌「辣」「冰」，控钠 1500，蛋白>=20
        index = build_nutrition_index(NUTRITION)
        combos, hints = build_combos(MEALS, profile, index)
        self.assertTrue(combos, f"长辈约束下应仍有可行套餐，但返回无解：{hints}")

        for c in combos:
            joined = "".join(c.names)
            self.assertNotIn("辣", joined)
            if c.sodium_mg is not None:
                self.assertLessEqual(c.sodium_mg, 1500)
            if c.protein_g is not None:
                self.assertGreaterEqual(c.protein_g, 20)

    def test_build_combos_marks_nutrition_missing(self):
        # 把营养表换成只含一项，制造大量缺录，验证不按 0 处理
        sparse_index = build_nutrition_index([{"name": "巨无霸汉堡", "energy": 550}])
        profile = profile_for("friend")
        combos, _ = build_combos(MEALS, profile, sparse_index)
        self.assertTrue(combos)
        # 至少有一组标了 nutrition_missing（因为多数餐品不在稀疏表里）
        self.assertTrue(any(c.nutrition_missing for c in combos))

    def test_build_combos_no_main_returns_hints(self):
        drinks_only = [m for m in MEALS if classify(m) == "drink"]
        combos, hints = build_combos(drinks_only, profile_for("friend"), build_nutrition_index(NUTRITION))
        self.assertEqual(combos, [])
        self.assertTrue(hints)


if __name__ == "__main__":
    unittest.main(verbosity=2)
