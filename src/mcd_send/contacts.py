"""收件人地址簿。

存的是「给谁点、点去哪、有什么忌口」，而不是麦当劳账号里那串没有语义的地址 ID。
本地 JSON 文件，不进版本库（.gitignore 已排除），Token 和地址都不外传。

查找顺序：
    1. 环境变量 MCD_SEND_CONTACTS 指定的路径
    2. 项目根目录的 contacts.json
    3. 用户目录 ~/.mcd-send-a-meal/contacts.json
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from .profiles import RecipientProfile, profile_for

CONTACTS_ENV = "MCD_SEND_CONTACTS"


class ContactError(ValueError):
    """地址簿相关问题。继承 ValueError，让 CLI 能统一捕获并友好提示。"""


@dataclass
class Contact:
    alias: str
    address_id: str = ""
    city: str = ""
    relation: str = "friend"
    phone: str = ""
    full_address: str = ""
    profile: dict[str, Any] = field(default_factory=dict)

    @property
    def recipient_profile(self) -> RecipientProfile:
        return profile_for(self.relation, self.profile)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _candidate_paths() -> list[Path]:
    paths: list[Path] = []
    env = os.environ.get(CONTACTS_ENV, "").strip()
    if env:
        paths.append(Path(env).expanduser())
    paths.append(Path.cwd() / "contacts.json")
    paths.append(Path.home() / ".mcd-send-a-meal" / "contacts.json")
    return paths


def load_contacts(path: str | os.PathLike | None = None) -> list[Contact]:
    target = Path(path).expanduser() if path else None
    candidates = [target] if target else _candidate_paths()

    for candidate in candidates:
        if candidate and candidate.is_file():
            raw = json.loads(candidate.read_text(encoding="utf-8"))
            entries = raw.get("contacts", raw) if isinstance(raw, dict) else raw
            if not isinstance(entries, list):
                raise ContactError(f"{candidate} 格式不对：contacts 应该是数组")
            return [
                Contact(
                    alias=item.get("alias") or item.get("name") or "",
                    address_id=str(item.get("address_id") or ""),
                    city=item.get("city") or "",
                    relation=item.get("relation") or "friend",
                    phone=item.get("phone") or "",
                    full_address=item.get("full_address") or "",
                    profile=item.get("profile") or {},
                )
                for item in entries
                if isinstance(item, dict)
            ]

    looked = "\n  ".join(str(p) for p in candidates if p)
    raise ContactError(
        "没找到地址簿。请任选一种方式建一个：\n"
        "  1) 复制 examples/contacts.sample.json 到项目根目录并改名为 contacts.json\n"
        f"  2) 或者设置环境变量 {CONTACTS_ENV} 指向你自己的地址簿文件\n"
        f"已尝试查找：\n  {looked}"
    )


def find_contact(alias: str, path: str | os.PathLike | None = None) -> Contact:
    contacts = load_contacts(path)
    if not contacts:
        raise ContactError("地址簿是空的")

    exact = [c for c in contacts if c.alias == alias]
    if exact:
        return exact[0]

    fuzzy = [c for c in contacts if alias and alias in c.alias]
    if len(fuzzy) == 1:
        return fuzzy[0]
    if len(fuzzy) > 1:
        raise ContactError(
            f"「{alias}」匹配到多个联系人：{[c.alias for c in fuzzy]}，请写全称"
        )

    raise ContactError(
        f"地址簿里没有「{alias}」。当前有：{[c.alias for c in contacts]}"
    )


def save_contacts(
    contacts: list[Contact], path: str | os.PathLike | None = None
) -> Path:
    target = Path(path).expanduser() if path else _default_write_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_comment": "本文件含真实收货信息，已被 .gitignore 忽略，请勿提交到版本库。",
        "contacts": [c.to_dict() for c in contacts],
    }
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return target


def _default_write_path() -> Path:
    env = os.environ.get(CONTACTS_ENV, "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / ".mcd-send-a-meal" / "contacts.json"
