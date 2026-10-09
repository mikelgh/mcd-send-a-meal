"""store_match 模块：按收件人地址排序门店 / 休息门店淘汰。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcd_send.store_match import pick_store, score_stores  # noqa: E402

OPEN = {"storeCode": "HZ-0188", "storeName": "杭州文三路店", "distance": 1.2, "eta": 26, "businessStatus": "营业中"}
FAR = {"storeCode": "HZ-0231", "storeName": "杭州黄龙店", "distance": 2.7, "eta": 34, "businessStatus": "营业中"}
CLOSED = {"storeCode": "HZ-0402", "storeName": "杭州西溪店", "distance": 4.9, "eta": 48, "businessStatus": "休息中"}


class TestStoreMatch(unittest.TestCase):
    def test_closed_store_is_excluded_from_ranking(self):
        scored = score_stores([OPEN, FAR, CLOSED])
        codes = [s.code for s in scored]
        # 休息中的店不丢，但被排到最末（score=0），不会成为首选
        self.assertEqual(codes[-1], "HZ-0402")
        self.assertEqual(codes[0], "HZ-0188")

    def test_nearest_open_wins(self):
        ranked = score_stores([FAR, OPEN])
        self.assertEqual(ranked[0].code, "HZ-0188")  # 更近 + 更快

    def test_pick_store_returns_best_open(self):
        best = pick_store([OPEN, FAR])
        self.assertEqual(best.code, "HZ-0188")
        self.assertTrue(best.is_open)

    def test_pick_store_skips_closed_and_keeps_open(self):
        best = pick_store([CLOSED, OPEN, FAR])
        self.assertEqual(best.code, "HZ-0188")  # 跳过休息中，取最近营业店
        self.assertTrue(best.is_open)

    def test_pick_store_raises_when_all_closed(self):
        with self.assertRaises(ValueError):
            pick_store([CLOSED])

    def test_score_weights_are_explainable(self):
        ranked = score_stores([OPEN])
        self.assertTrue(ranked[0].reasons)  # 至少有一条可读理由


if __name__ == "__main__":
    unittest.main(verbosity=2)
