"""contacts 模块：地址簿加载 / 精确与模糊匹配 / 友好错误。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mcd_send.contacts import Contact, ContactError, find_contact, load_contacts  # noqa: E402
from _bootstrap import make_contacts_file  # noqa: E402


class TestContacts(unittest.TestCase):
    def test_load_contacts_reads_sample(self):
        path = make_contacts_file()
        contacts = load_contacts(path)
        aliases = {c.alias for c in contacts}
        self.assertTrue({"爸妈", "小林", "运营组"} <= aliases)

    def test_find_contact_exact(self):
        path = make_contacts_file()
        c = find_contact("爸妈", path)
        self.assertEqual(c.relation, "parent")
        self.assertEqual(c.address_id, "A-PARENT")

    def test_find_contact_fuzzy_single(self):
        path = make_contacts_file()
        c = find_contact("小", path)  # 「小」唯一命中「小林」
        self.assertEqual(c.alias, "小林")

    def test_find_contact_fuzzy_ambiguous_raises(self):
        contacts = [
            Contact(alias="运营组", address_id="A1"),
            Contact(alias="测试组", address_id="A2"),
        ]
        p = make_contacts_file(contacts)
        with self.assertRaises(ContactError) as ctx:
            find_contact("组", p)
        self.assertIn("匹配到多个", str(ctx.exception))

    def test_find_contact_missing_raises(self):
        path = make_contacts_file()
        with self.assertRaises(ContactError) as ctx:
            find_contact("陌生人", path)
        self.assertIn("没有", str(ctx.exception))

    def test_contact_error_is_value_error(self):
        # CLI 用 `except (ValueError, ...)` 统一捕获，ContactError 必须可被捕获
        self.assertTrue(issubclass(ContactError, ValueError))
        with self.assertRaises(ValueError):
            raise ContactError("x")

    def test_recipient_profile_resolves_relation(self):
        c = Contact(alias="爸", relation="parent")
        self.assertEqual(c.recipient_profile.sodium_max_mg, 1500)


if __name__ == "__main__":
    unittest.main(verbosity=2)
