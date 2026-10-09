"""pricing 模块：单位换算 / 核价拆解 / 净省（不被配送费误导）。"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcd_send.pricing import PriceBreakdown, fmt_yuan, parse_price_result, to_yuan  # noqa: E402


class TestPricing(unittest.TestCase):
    def setUp(self):
        os.environ.pop("MCD_PRICE_UNIT", None)

    def test_to_yuan_default_cent(self):
        self.assertEqual(to_yuan(2350), 23.5)
        self.assertEqual(to_yuan(900), 9.0)

    def test_to_yuan_yuan_mode(self):
        os.environ["MCD_PRICE_UNIT"] = "yuan"
        try:
            self.assertEqual(to_yuan(23.5), 23.5)
        finally:
            os.environ.pop("MCD_PRICE_UNIT", None)

    def test_to_yuan_none_passthrough(self):
        self.assertIsNone(to_yuan(None))
        self.assertIsNone(to_yuan("不是数"))

    def test_parse_price_result_cent_to_yuan(self):
        raw = {
            "totalAmount": 3050,
            "payableAmount": 1550,
            "deliveryFee": 900,
            "discountAmount": 1500,
        }
        pb = parse_price_result(raw)
        self.assertEqual(pb.total_yuan, 30.50)
        self.assertEqual(pb.payable_yuan, 15.50)
        self.assertEqual(pb.delivery_yuan, 9.00)
        self.assertEqual(pb.discount_yuan, 15.00)

    def test_net_saved_can_be_negative_when_delivery_eats_coupon(self):
        # 商品 21.50，券减 15.00，配送费 9.00 → 应付 30.50
        # 净省 = 21.50 - 30.50 = -9.00（配送费吃掉了券优惠还多花）
        pb = PriceBreakdown(
            total_yuan=21.50, payable_yuan=30.50,
            delivery_yuan=9.00, discount_yuan=15.00,
        )
        self.assertEqual(pb.net_saved_yuan, -9.00)
        self.assertEqual(pb.goods_payable_yuan, 6.50)  # 21.50 - 15.00

    def test_lines_exposes_full_breakdown(self):
        pb = PriceBreakdown(
            total_yuan=30.0, payable_yuan=24.0,
            delivery_yuan=9.0, discount_yuan=15.0, coupon_name="满30减15",
        )
        labels = [label for label, _ in pb.lines()]
        self.assertEqual(labels[0], "商品原价")
        self.assertTrue(labels[1].startswith("券优惠（满30减15）"))
        self.assertIn("配送费", labels)
        self.assertEqual(labels[-1], "应付")

    def test_parse_price_result_missing_payable_falls_back(self):
        # 只给总价和优惠、配送，缺 payableAmount 时按 total-discount+delivery 推算
        raw = {"totalAmount": 3050, "discountAmount": 1500, "deliveryFee": 900}
        pb = parse_price_result(raw)
        self.assertEqual(pb.payable_yuan, 24.50)

    def test_fmt_yuan_missing(self):
        self.assertEqual(fmt_yuan(None), "—")


if __name__ == "__main__":
    unittest.main(verbosity=2)
