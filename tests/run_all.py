"""一键跑全部离线确定性单测。

用法：
    python tests/run_all.py            # 跑 tests/test_*.py 全部
    python tests/test_pricing.py       # 也可单文件直跑（每个 test_* 自带 __main__）

零依赖：只用 Python 标准库 unittest，不连任何外部服务、不需要 Token。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# 保证 `from mcd_send import ...` 与 `from tests._bootstrap import ...` 都能用
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))


def main(argv: list[str] | None = None) -> int:
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=str(HERE), pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
