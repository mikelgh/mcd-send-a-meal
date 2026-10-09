"""通用小工具：容错取值与数值解析。

麦当劳 MCP 各 tool 的返回字段命名并不完全统一（有的 camelCase、有的下划线、
有的把列表包一层 data）。业务层不应该到处写 `d.get('a') or d.get('b')`，
所以统一收在这里。
"""

from __future__ import annotations

import re
from typing import Any


def pick(source: Any, *keys: str, default: Any = None) -> Any:
    """按顺序找第一个存在且非空的字段。大小写与下划线不敏感。"""
    if not isinstance(source, dict):
        return default
    if not keys:
        return default

    normalized = {re.sub(r"[^a-z0-9]", "", str(k).lower()): v for k, v in source.items()}
    for key in keys:
        if key in source and source[key] not in (None, "", [], {}):
            return source[key]
        hit = normalized.get(re.sub(r"[^a-z0-9]", "", key.lower()))
        if hit not in (None, "", [], {}):
            return hit
    return default


_NUM = re.compile(r"-?\d+(?:\.\d+)?")


def to_float(value: Any, default: float | None = None) -> float | None:
    """从 '约 1.8km'、'约 25 分钟'、'1234.5' 这类字符串里抽出数字。"""
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    match = _NUM.search(str(value))
    if not match:
        return default
    try:
        return float(match.group(0))
    except ValueError:
        return default


def norm_text(value: Any) -> str:
    """把餐品名/地址等文本归一化，用于模糊匹配。"""
    if value is None:
        return ""
    return re.sub(r"[\s\-_·・()（）\[\]【】,，.。/、]+", "", str(value)).lower()


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
