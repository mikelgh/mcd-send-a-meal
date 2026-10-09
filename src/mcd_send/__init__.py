"""麦麦代送 mcd-send-a-meal

把一份麦当劳送到**别人**手上。

自点和代送的根本区别，不在点什么，而在约束来自谁：
门店要按收件人地址找、券要按收件人所在门店重查、忌口要按收件人画像判。
这个包里没有一行代码是围绕「我自己」写的。
"""

from .mcp_client import McpError, McDonaldMcpClient, RateLimitError
from .contacts import Contact, ContactError, find_contact, load_contacts, save_contacts
from .profiles import RecipientProfile, profile_for, known_relations
from .store_match import StoreScore, pick_store, score_stores
from .menu import Combo, build_combos, build_nutrition_index
from .pricing import PriceBreakdown, parse_price_result, rank_by_price
from .planner import SendPlan, SendResult, execute_send, plan_send, track_order
from .card import render_card, write_card

__version__ = "0.1.0"

__all__ = [
    "McpError",
    "RateLimitError",
    "McDonaldMcpClient",
    "Contact",
    "ContactError",
    "find_contact",
    "load_contacts",
    "save_contacts",
    "RecipientProfile",
    "profile_for",
    "known_relations",
    "StoreScore",
    "pick_store",
    "score_stores",
    "Combo",
    "build_combos",
    "build_nutrition_index",
    "PriceBreakdown",
    "parse_price_result",
    "rank_by_price",
    "SendPlan",
    "SendResult",
    "execute_send",
    "plan_send",
    "track_order",
    "render_card",
    "write_card",
    "__version__",
]
