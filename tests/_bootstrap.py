"""测试公共引导：把项目 src/ 加入 sys.path，并提供通用夹具。

所有 test_*.py 都 import 本模块，从而可以：
  - 直接 `python tests/test_xxx.py` 单文件运行
  - 也可以 `python tests/run_all.py` 一键跑全部
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# 把项目 src/ 加进来，保证 `from mcd_send import ...` 可用
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mcd_send.contacts import Contact, save_contacts  # noqa: E402
from mcd_send.fixtures import FixtureTools  # noqa: E402


def make_contacts_file(contacts: list[Contact] | None = None) -> Path:
    """在临时目录写一份地址簿，返回路径；测试用完后自动随进程退出清理。"""
    if contacts is None:
        contacts = [
            Contact(alias="爸妈", address_id="A-PARENT", city="杭州", relation="parent"),
            Contact(alias="小林", address_id="A-PARTNER", city="深圳", relation="partner"),
            Contact(alias="运营组", address_id="A-TEAM", city="广州", relation="colleague"),
        ]
    tmp = Path(tempfile.mkdtemp(prefix="mcdtest-"))
    path = tmp / "contacts.json"
    save_contacts(contacts, path)
    return path


def fixture_tools() -> FixtureTools:
    return FixtureTools(city="杭州")


def load_json_sample(name: str) -> dict:
    """读取项目根目录 examples/ 下的样例文件。"""
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))
