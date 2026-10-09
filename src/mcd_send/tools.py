"""麦当劳 MCP 工具层。

这里解决一个真实的工程问题：**平台没有公开每个 tool 的入参 schema**，
只能通过 `tools/list` 在运行时问出来。如果代码里硬猜参数名（比如猜
`storeCode` 还是 `store_code`），换台机器、平台发一次版本就可能全线报错。

所以这层的做法是「schema 驱动」：

1. 首次调用时拉一次 `tools/list`，把每个 tool 的真实 inputSchema 缓存下来；
2. 我们代码里用自己定义的语义化参数名，交给 `ToolSchemas.resolve()`
   统一做一次「大小写 + 下划线不敏感」的归一化匹配；
3. 匹配不上就抛 `UnknownParam`，并把该 tool 的**合法参数名全列出来**，
   而不是让请求打过去收到一个看不懂的 400。

这样一来，即使某个参数名猜错了，第一次跑就能拿到明确提示并立刻修正，
不会出现「代码看着对、跑起来全是错」的情况。
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from .mcp_client import McpError, McDonaldMcpClient
from .util import to_float


class UnknownParam(McpError):
    """传入的参数名在该 tool 的 schema 里不存在。"""


def _norm(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", key.lower())


# 外送场景的门店类型：麦当劳 MCP 明确「外送仅支持麦乐送(beType=2)和团餐(beType=6)」。
# 代送项目只做个人外送，所以默认用 2。
DELIVERY_BE_TYPE = "2"
# 下单类型：1=外送。
DELIVERY_ORDER_TYPE = 1


def as_list(result: Any, *container_keys: str) -> list:
    """MCP 返回的列表有时裸数组、有时包在 data/list/items 里，统一抽出来。

    嵌套结构也覆盖：例如 envelope 的 data 是 {"addresses": [...]} 时，
    会把 container_keys（addresses）也算进内层查找键。
    """
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for key in ("data", "list", "items", "records", "result") + container_keys:
            value = result.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                for inner in ("list", "items", "records", "data", *container_keys):
                    if isinstance(value.get(inner), list):
                        return value[inner]
        for key in container_keys:
            if isinstance(result.get(key), list):
                return result[key]
    return []


def as_dict(result: Any, *container_keys: str) -> dict:
    if isinstance(result, dict):
        inner = result.get("data")
        if isinstance(inner, dict) and len(result) <= 2:
            return inner
        return result
    if isinstance(result, list) and result and isinstance(result[0], dict):
        return result[0]
    return {}


# ---------------------------------------------------------------------------
# 文本解析：麦当劳 MCP 的部分接口不返回结构化 JSON，而是给模型看的文本。
# 这里把已知格式尽力解析成结构化列表，供约束求解/展示使用。
# ---------------------------------------------------------------------------

_NUTRITION_NUM_COLS = (
    "energyKj", "energyKcal", "protein", "fat", "carbohydrate", "sodium", "calcium",
)


def parse_nutrition_text(text: str) -> list[dict]:
    """解析 list-nutrition-foods 返回的自定义表格字符串。

    格式示例：
        [160]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,
              carbohydrate,sodium,calcium}:
          猪柳麦满分,null,1288,308,16,16,24,781,213
          火腿扒麦满分,null,1092,261,14,12,24,608,131

    返回 [{name, productName, energyKcal, protein, fat, carbohydrate, sodium, calcium, ...}]。
    """
    if not isinstance(text, str) or not text.strip():
        return []
    header = re.search(r"\[\d+\]\{([^}]+)\}", text)
    if not header:
        return []
    cols = [c.strip() for c in header.group(1).split(",") if c.strip()]
    rows: list[dict] = []
    for line in text.splitlines():
        if "{" in line and "}" in line and header.group(0) in line:
            continue  # 表头行
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < len(cols):
            continue
        row: dict[str, Any] = {}
        for col, val in zip(cols, parts):
            row[col] = val
        name = (row.get("productName") or row.get("name") or "").strip()
        if not name:
            continue
        out: dict[str, Any] = {"name": name, "productName": name}
        for num_col in _NUTRITION_NUM_COLS:
            if num_col in row:
                out[num_col] = to_float(row[num_col])
        if row.get("nutritionDescription") not in (None, "null", ""):
            out["nutritionDescription"] = row["nutritionDescription"]
        rows.append(out)
    return rows


def parse_coupon_markdown(text: str) -> list[dict]:
    """解析 query-my-coupons 返回的 markdown 文案（账户券）。

    每段以 `## 券名` 开头，下面用 `- **优惠**: ¥9.9 (用券价格)` 等罗列。
    注意：markdown 里**不含 couponCode/couponId**，所以只能用于展示，
    无法直接拿去 calculate-price 核价（门店券 query-store-coupons 才有结构化 code）。
    返回 [{name, title, price_yuan, valid_until, tags}]。
    """
    if not isinstance(text, str) or not text.strip():
        return []
    sections = re.split(r"\n##\s+", text)
    coupons: list[dict] = []
    for sec in sections[1:]:
        lines = sec.splitlines()
        name = lines[0].strip()
        if not name:
            continue
        item: dict[str, Any] = {
            "name": name,
            "title": name,
            "price_yuan": None,
            "valid_until": None,
            "tags": [],
        }
        for line in lines[1:]:
            s = line.strip()
            if not s.startswith("-"):
                continue
            if "优惠" in s or "价" in s:
                m = re.search(r"¥\s*([\d.]+)", s)
                if m:
                    item["price_yuan"] = float(m.group(1))
            elif "有效期" in s:
                m = re.search(r"(\d{4}-\d{2}-\d{2}[^\n]*)", s)
                if m:
                    item["valid_until"] = m.group(1).strip().rstrip("。")
            elif "标签" in s:
                rest = re.sub(r"^[-*]\s*\*\*标签\*\*\s*[:：]?\s*", "", s).strip()
                item["tags"] = [t.strip() for t in rest.split("、") if t.strip()]
        coupons.append(item)
    return coupons


class ToolSchemas:
    """缓存 tools/list 的真实 schema，并据此归一化参数名。"""

    def __init__(self, client: McDonaldMcpClient) -> None:
        self._client = client
        self._schemas: dict[str, dict] = {}
        self._known: set[str] = set()
        self._loaded = False
        self.rename_log: list[str] = []

    def load(self, force: bool = False) -> None:
        if self._loaded and not force:
            return
        for tool in self._client.list_tools():
            name = tool.get("name")
            if not name:
                continue
            self._known.add(name)
            self._schemas[name] = (
                tool.get("inputSchema") or tool.get("input_schema") or {}
            )
        self._loaded = True

    @property
    def known_tools(self) -> set[str]:
        self.load()
        return set(self._known)

    def properties(self, tool: str) -> dict:
        self.load()
        schema = self._schemas.get(tool) or {}
        props = schema.get("properties")
        return props if isinstance(props, dict) else {}

    def required(self, tool: str) -> list[str]:
        self.load()
        schema = self._schemas.get(tool) or {}
        req = schema.get("required")
        return list(req) if isinstance(req, list) else []

    def resolve(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        """把我们写的语义化参数名映射到平台真实参数名。"""
        self.load()
        if tool not in self._known:
            raise UnknownParam(
                f"MCP Server 上没有名为 {tool!r} 的 tool。"
                f"当前可用：{', '.join(sorted(self._known)) or '(tools/list 为空)'}"
            )

        props = self.properties(tool)
        if not props:
            # 平台没给 schema，只能原样透传
            return dict(args)

        lookup = {_norm(name): name for name in props}
        out: dict[str, Any] = {}
        unmatched: list[str] = []

        for key, value in args.items():
            if key in props:
                out[key] = value
                continue
            real = lookup.get(_norm(key))
            if real:
                out[real] = value
                if real != key:
                    self.rename_log.append(f"{tool}: {key} -> {real}")
                continue
            unmatched.append(key)

        if unmatched:
            raise UnknownParam(
                f"{tool} 不认识这些参数：{unmatched}\n"
                f"  该 tool 的合法参数：{sorted(props)}\n"
                f"  必填参数：{self.required(tool)}"
            )
        return out

    def describe(self) -> str:
        self.load()
        lines = []
        for name in sorted(self._schemas):
            props = self.properties(name)
            req = set(self.required(name))
            if not props:
                lines.append(f"{name}  (平台未提供入参 schema)")
                continue
            args = ", ".join(
                f"{k}{'*' if k in req else ''}" for k in props
            )
            lines.append(f"{name}  ({args})")
        return "\n".join(lines)


class McpTools:
    """面向业务语义的 MCP 工具集。所有方法都是对真实 HTTP 调用的一层薄封装。"""

    def __init__(self, client: McDonaldMcpClient | None = None) -> None:
        self.client = client or McDonaldMcpClient()
        self.schemas = ToolSchemas(self.client)

    # ------------------------------------------------------------ 内部

    def _call(self, tool: str, **args: Any) -> Any:
        cleaned = {k: v for k, v in args.items() if v is not None}
        return self.client.call_tool(tool, self.schemas.resolve(tool, cleaned))

    def inspect(self) -> str:
        return self.schemas.describe()

    # ------------------------------------------------------------ 时间与地址

    def now(self) -> dict:
        return as_dict(self._call("now-time-info"))

    def list_addresses(self) -> list[dict]:
        return as_list(self._call("delivery-query-addresses"), "addresses")

    def create_address(
        self, contact_name: str, phone: str, address: str, city: str, address_detail: str | None = None
    ) -> dict:
        """创建一条可配送地址。收件人不在自己身边时，这一步是代送的前提。

        `addressDetail*` / `city*` 为真实必填项，必须显式传入。
        """
        return as_dict(
            self._call(
                "delivery-create-address",
                contactName=contact_name,
                phone=phone,
                address=address,
                addressDetail=address_detail or address,
                city=city,
            )
        )

    # ------------------------------------------------------------ 门店（关键：按收件人地址找店）

    def stores_for_address(self, address_id: str, be_type: str = DELIVERY_BE_TYPE) -> list[dict]:
        """按**收件人地址**查可配送门店——不是查我附近的店。

        这一步是整个代送项目的技术核心：异地送餐必须把「查店原点」
        从下单人切换到收件人。
        `beType` 为必填，外送默认 "2"（麦乐送）；团餐用 "6"。
        """
        return as_list(
            self._call("delivery-query-stores", addressId=address_id, beType=be_type), "stores"
        )

    def nearby_stores(self, keyword: str, be_type: str = DELIVERY_BE_TYPE, search_type: str = "1") -> list[dict]:
        return as_list(
            self._call("query-nearby-stores", beType=be_type, keyword=keyword, searchType=search_type), "stores"
        )

    # ------------------------------------------------------------ 菜单与营养

    def meals(self, store_code: str, be_code: str = "", be_type: str = DELIVERY_BE_TYPE) -> list[dict]:
        # 实测：query-meals 用 storeCode + beType=2 + orderType=1 即可返回菜单；
        # 带上 beCode 反而触发「门店可能已关闭」(600057)。代送只取菜单，故不传 beCode。
        data = self._call(
            "query-meals",
            storeCode=store_code,
            beType=be_type or None,
            orderType=DELIVERY_ORDER_TYPE,
        )
        inner = data.get("data", data) if isinstance(data, dict) else data
        # 真实目录在 data.meals：dict[code] -> {name, currentPrice, originalPrice, ...}
        catalog = inner.get("meals") if isinstance(inner, dict) else None
        if isinstance(catalog, dict):
            out: list[dict] = []
            for code, info in catalog.items():
                if isinstance(info, dict):
                    item = dict(info)
                    item.setdefault("code", str(code))
                    out.append(item)
            if out:
                return out
        # 兜底：展开 data.categories[].meals（仅含 code/tags，无名称价格）
        flat: list[dict] = []
        for cat in as_list(inner, "categories") if isinstance(inner, dict) else []:
            if isinstance(cat, dict):
                flat.extend(as_list(cat, "meals"))
        return flat

    def meal_detail(self, store_code: str, meal_code: str, be_code: str = "", be_type: str = DELIVERY_BE_TYPE) -> dict:
        return as_dict(
            self._call(
                "query-meal-detail",
                storeCode=store_code,
                beType=be_type or None,
                code=meal_code,
                orderType=DELIVERY_ORDER_TYPE,
            )
        )

    def nutrition(self) -> list[dict]:
        res = self._call("list-nutrition-foods")
        # list-nutrition-foods 的 data 是自定义表格字符串，不是 JSON 数组
        data = res.get("data", res) if isinstance(res, dict) else res
        if isinstance(data, str):
            return parse_nutrition_text(data)
        return as_list(res, "foods")

    # ------------------------------------------------------------ 优惠券

    def store_coupons(self, store_code: str, be_code: str = "", be_type: str = DELIVERY_BE_TYPE) -> list[dict]:
        """查**收件人所在门店**的可用券。

        异地场景下一个反直觉的事实：同一个账户在不同城市门店的可用券
        并不相同，必须按目标门店重查，不能复用本地下单时的结论。

        注意：query-store-coupons 带 beCode 会像 meals/核价一样异常，故不发送。
        """
        return as_list(
            self._call(
                "query-store-coupons",
                storeCode=store_code,
                beType=be_type or None,
                orderType=1,
            ), "coupons"
        )

    def claimable_coupons(self) -> list[dict]:
        return as_list(self._call("available-coupons"), "coupons")

    def auto_bind_coupons(self) -> dict:
        """一键领取麦麦省全部可领券。属于写操作，调用前必须让用户确认。"""
        return as_dict(self._call("auto-bind-coupons"))

    def my_coupons(self) -> list[dict]:
        res = self._call("query-my-coupons")
        # query-my-coupons 返回 markdown 文案；query-store-coupons 才是结构化 JSON
        if isinstance(res, str):
            return parse_coupon_markdown(res)
        return as_list(res, "coupons")

    # ------------------------------------------------------------ 核价与下单

    def calculate_price(self, payload: dict) -> dict:
        return as_dict(self._call("calculate-price", **payload))

    def create_order(self, payload: dict) -> dict:
        return as_dict(self._call("create-order", **payload))

    def query_order(self, order_id: str) -> dict:
        return as_dict(self._call("query-order", orderId=order_id))

    def cancel_order(self, order_id: str, reason: str = "1") -> dict:
        # 真实必填参数是 cancelReasonCode（不是 cancelReason）
        return as_dict(
            self._call("cancel-order", orderId=order_id, cancelReasonCode=reason)
        )


def iter_meal_codes(meals: Iterable[dict]) -> list[str]:
    """从菜单里尽力抽出餐品编码，兼容几种常见字段命名。"""
    codes: list[str] = []
    for meal in meals:
        if not isinstance(meal, dict):
            continue
        for key in ("code", "mealCode", "spuId", "id", "productCode"):
            value = meal.get(key)
            if value:
                codes.append(str(value))
                break
    return codes
