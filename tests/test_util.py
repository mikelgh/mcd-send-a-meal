"""util 模块：容错取值 / 数值解析 / 文本归一化 / 区间夹紧。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcd_send.util import clamp, norm_text, pick, to_float  # noqa: E402


class TestUtil(unittest.TestCase):
    def test_pick_returns_first_present(self):
        d = {"a": 1, "b": 2}
        self.assertEqual(pick(d, "x", "a", "b"), 1)

    def test_pick_case_and_underscore_insensitive(self):
        d = {"store_code": 99}
        self.assertEqual(pick(d, "storeCode"), 99)
        self.assertEqual(pick(d, "Store-Code"), 99)

    def test_pick_skips_empty_values(self):
        d = {"a": "", "b": None, "c": [], "d": "ok"}
        self.assertEqual(pick(d, "a", "b", "c", "d"), "ok")

    def test_pick_treats_zero_as_valid(self):
        # 0 是真实数值，不应被当成「空」跳过
        d = {"count": 0, "name": "x"}
        self.assertEqual(pick(d, "count"), 0)

    def test_pick_default_when_missing(self):
        self.assertEqual(pick({}, "nope", default="fallback"), "fallback")

    def test_to_float_from_number_and_string(self):
        self.assertEqual(to_float(12), 12.0)
        self.assertEqual(to_float("约 1.8km"), 1.8)
        self.assertEqual(to_float("约 25 分钟"), 25.0)
        self.assertEqual(to_float("1234.5"), 1234.5)

    def test_to_float_returns_default_on_garbage(self):
        self.assertEqual(to_float("不是数字", default=-1), -1)
        self.assertIsNone(to_float(None))

    def test_norm_text_strips_noise(self):
        self.assertEqual(norm_text("巨无霸 汉堡 (套餐)"), "巨无霸汉堡套餐")
        self.assertEqual(norm_text("板烧·鸡腿堡"), "板烧鸡腿堡")

    def test_clamp_bounds(self):
        self.assertEqual(clamp(5, 0, 10), 5)
        self.assertEqual(clamp(-3, 0, 10), 0)
        self.assertEqual(clamp(99, 0, 10), 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
