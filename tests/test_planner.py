"""planner 模块：端到端只读出方案 / 确认门控 / 主餐去重。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcd_send.contacts import Contact  # noqa: E402
from mcd_send.menu import Combo  # noqa: E402
from mcd_send.planner import _diversify, execute_send, plan_send  # noqa: E402
from _bootstrap import fixture_tools, make_contacts_file  # noqa: E402


def _plan(alias: str = "爸妈"):
    tools = fixture_tools()
    path = make_contacts_file(
        [Contact(alias=alias, address_id="A-PARENT", city="杭州", relation="parent")]
    )
    return tools, plan_send(tools, alias, contacts_path=path)


class TestPlanner(unittest.TestCase):
    def test_plan_send_readonly_produces_candidates(self):
        tools, plan = _plan()
        self.assertEqual(plan.contact.alias, "爸妈")
        self.assertEqual(plan.store.code, "HZ-0188")  # 杭州文三路店（最近且在营业）
        self.assertTrue(plan.combos, "应有候选套餐")
        # 门店是按收件人地址（杭州）查的，而非下单人附近
        self.assertTrue(plan.store.name.startswith("杭州"))

    def test_plan_send_prices_real_amounts(self):
        _, plan = _plan()
        first = plan.combos[0]
        self.assertIsNotNone(first.price)
        self.assertIsNotNone(first.price.get("payable_yuan"))
        self.assertGreaterEqual(first.price["payable_yuan"], 0)

    def test_diversify_keeps_distinct_mains(self):
        def fake(main_name):
            return Combo(label="x", items=[{"name": main_name}])

        combos = [fake("板烧鸡腿堡") for _ in range(4)] + [fake("巨无霸") for _ in range(4)]
        diversified = _diversify(combos, 6)
        mains = [c.names[0] for c in diversified]
        self.assertEqual(len(set(mains)), len(mains))  # 全不重复
        self.assertIn("板烧鸡腿堡", mains)
        self.assertIn("巨无霸", mains)

    def test_execute_send_requires_confirm(self):
        tools, plan = _plan()
        with self.assertRaises(PermissionError) as ctx:
            execute_send(tools, plan, confirm=False)
        self.assertIn("确认", str(ctx.exception))

    def test_execute_send_with_confirm_creates_order(self):
        tools, plan = _plan()
        result = execute_send(tools, plan, confirm=True)
        self.assertTrue(result.order_id)
        self.assertTrue(result.status)
        # 离线后端记录了 create-order 调用
        self.assertTrue(any(name == "create-order" for name, _ in tools.calls))


if __name__ == "__main__":
    unittest.main(verbosity=2)
