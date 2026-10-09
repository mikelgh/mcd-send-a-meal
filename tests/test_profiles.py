"""profiles 模块：关系 → 默认约束 / 覆盖合并 / 不现实的钠上限已修正。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcd_send.profiles import RecipientProfile, known_relations, profile_for  # noqa: E402


class TestProfiles(unittest.TestCase):
    def test_known_relations_present(self):
        rels = known_relations()
        for expected in ("parent", "partner", "friend", "colleague", "client"):
            self.assertIn(expected, rels)

    def test_parent_default_sodium_is_realistic(self):
        # 关键修正：真实菜单单品钠普遍 900-1200mg，670 会直接无解
        p = profile_for("parent")
        self.assertEqual(p.sodium_max_mg, 1500)
        self.assertTrue(p.no_ice)
        self.assertIn("辣", p.avoid_keywords)

    def test_profile_for_unknown_falls_back_to_friend(self):
        # 未知关系：对象保留原 relation 字段，但约束套用 friend 默认
        p = profile_for("不存在的关系")
        self.assertEqual(p.relation, "不存在的关系")
        self.assertEqual(p.energy_max_kcal, 1000)  # friend 默认

    def test_override_merges_only_given_fields(self):
        base = profile_for("parent")
        self.assertEqual(base.energy_max_kcal, 800)
        merged = profile_for("parent", {"energy_max_kcal": 600})
        self.assertEqual(merged.energy_max_kcal, 600)
        self.assertEqual(merged.sodium_max_mg, 1500)  # 未覆盖项保持默认
        self.assertTrue(merged.no_ice)

    def test_colleague_wants_protein(self):
        p = profile_for("colleague")
        self.assertEqual(p.protein_min_g, 30)
        self.assertEqual(p.energy_min_kcal, 500)

    def test_partner_controls_calories_and_fat(self):
        p = profile_for("partner")
        self.assertEqual(p.energy_max_kcal, 700)
        self.assertEqual(p.fat_max_g, 30)

    def test_to_dict_roundtrip(self):
        p = profile_for("client")
        d = p.to_dict()
        self.assertIsInstance(d, dict)
        self.assertEqual(d["relation"], "client")


if __name__ == "__main__":
    unittest.main(verbosity=2)
