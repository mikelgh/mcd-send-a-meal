"""card 模块：给收件人的 HTML 卡片渲染 / 内容转义。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcd_send.card import render_card  # noqa: E402
from mcd_send.contacts import Contact  # noqa: E402
from mcd_send.menu import Combo  # noqa: E402
from mcd_send.planner import plan_send  # noqa: E402
from _bootstrap import fixture_tools, make_contacts_file  # noqa: E402


def _plan():
    tools = fixture_tools()
    path = make_contacts_file(
        [Contact(alias="老王", address_id="A-X", city="杭州", relation="friend")]
    )
    return plan_send(tools, "老王", contacts_path=path)


class TestCard(unittest.TestCase):
    def test_render_card_contains_core_sections(self):
        plan = _plan()
        combo = plan.combos[0]
        html = render_card(plan, combo, from_name="小李", message="食堂别吃了", order_id="DEMO-1")
        self.assertIn("有人", html)
        self.assertIn("请客", html)  # 印章文案
        self.assertIn("老王", html)  # 收件人
        self.assertIn("小李", html)  # 落款
        self.assertIn("DEMO-1", html)  # 订单号
        self.assertIn("<!DOCTYPE html>", html)

    def test_render_card_escapes_html_injection(self):
        plan = _plan()
        combo = Combo(label="简餐", items=[{"name": "<script>alert(1)</script>"}])
        html = render_card(plan, combo, message="<img src=x onerror=alert(1)>")
        # 危险标签必须被转义成纯文本，浏览器不会执行
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img", html)

    def test_render_card_shows_price_when_present(self):
        plan = _plan()
        combo = plan.combos[0]
        combo.price = {"payable_yuan": 24.5, "total_yuan": 30.0, "saved_yuan": 5.5}
        html = render_card(plan, combo)
        self.assertIn("24.50", html)
        self.assertIn("30.00", html)

    def test_render_card_is_self_contained(self):
        # 单文件、离线可开：不引用任何外部 CDN
        plan = _plan()
        html = render_card(plan, plan.combos[0])
        self.assertNotIn("cdn", html.lower())
        self.assertNotIn("https://", html)


if __name__ == "__main__":
    unittest.main(verbosity=2)
