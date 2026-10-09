"""解析器单测：营养表字符串 + 账户券 markdown。

样本来自真实 MCP 返回（2026-10-09 实测），确保格式变动能被测出来。
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mcd_send.tools import parse_nutrition_text, parse_coupon_markdown

import unittest


class TestParseNutrition(unittest.TestCase):
    SAMPLE = (
        "[160]{productName,nutritionDescription,energyKj,energyKcal,protein,"
        "fat,carbohydrate,sodium,calcium}:\n"
        "  猪柳麦满分,null,1288,308,16,16,24,781,213\n"
        "  火腿扒麦满分,null,1092,261,14,12,24,608,131\n"
        "  中薯条,null,1210,289,4,12,38,165,18"
    )

    def test_parses_rows(self):
        rows = parse_nutrition_text(self.SAMPLE)
        self.assertEqual(len(rows), 3)

    def test_name_and_numeric(self):
        rows = parse_nutrition_text(self.SAMPLE)
        pork = rows[0]
        self.assertEqual(pork["name"], "猪柳麦满分")
        self.assertEqual(pork["energyKcal"], 308.0)
        self.assertEqual(pork["protein"], 16.0)
        self.assertEqual(pork["sodium"], 781.0)
        self.assertEqual(pork["calcium"], 213.0)

    def test_null_becomes_none(self):
        rows = parse_nutrition_text(self.SAMPLE)
        # nutritionDescription 为 null -> 不应出现该键
        self.assertNotIn("nutritionDescription", rows[0])

    def test_empty_input(self):
        self.assertEqual(parse_nutrition_text(""), [])
        self.assertEqual(parse_nutrition_text(None), [])


class TestParseCouponMarkdown(unittest.TestCase):
    SAMPLE = (
        "# 您的优惠券列表\n\n"
        "共 14 张可用优惠券 | 第 1/1 页 | 每页 200 条\n\n"
        "## 麦旋风任选\n"
        "- **优惠**: ¥9.9 (用券价格)\n"
        "- **有效期**: 2026-10-05 10:30-2026-10-09 23:59 周一、二、三、四、五 10:30-23:59\n"
        "- **领取时间**: 4日前收到\n"
        "- **标签**: 今日到期、到店专用、外送专用\n\n"
        "## 薯薯任选\n"
        "- **优惠**: ¥9.9 (用券价格)\n"
        "- **有效期**: 2026-10-05 10:30-2026-10-09 23:59\n"
        "- **标签**: 外送专用"
    )

    def test_parses_sections(self):
        coupons = parse_coupon_markdown(self.SAMPLE)
        self.assertEqual(len(coupons), 2)
        self.assertEqual(coupons[0]["name"], "麦旋风任选")

    def test_price_and_tags(self):
        coupons = parse_coupon_markdown(self.SAMPLE)
        self.assertEqual(coupons[0]["price_yuan"], 9.9)
        self.assertIn("外送专用", coupons[0]["tags"])
        self.assertIn("今日到期", coupons[0]["tags"])
        self.assertIn("2026-10-05", coupons[0]["valid_until"])

    def test_empty_input(self):
        self.assertEqual(parse_coupon_markdown(""), [])
        self.assertEqual(parse_coupon_markdown(None), [])


if __name__ == "__main__":
    unittest.main()
