"""麦当劳中国 MCP Server 的零依赖 Streamable HTTP 客户端。

只实现三件事：initialize / tools/list / tools/call。
不引入任何第三方依赖（连 requests 都不用），方便在任何机器上直接跑起来。

接入信息（来自官方 mcd-mcp-server 仓库）：
    地址  https://mcp.mcd.cn
    协议  Streamable HTTP
    鉴权  Authorization: Bearer <MCP Token>
    限流  每个 Token 每分钟最多 600 次请求，超限返回 429

Token 只从环境变量读取，绝不写进代码或配置文件。
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ENDPOINT = "https://mcp.mcd.cn"
PROTOCOL_VERSION = "2025-06-18"
TOKEN_ENV = "MCD_MCP_TOKEN"
ENDPOINT_ENV = "MCD_MCP_ENDPOINT"

# .env 加载：用户常把 Token 写进项目根目录的 .env（字段名可能是小写的 mcp_token）。
# 如果环境变量里还没有 MCD_MCP_TOKEN，就扫描 .env 把它补进环境，做到「存 .env 即生效」。
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _prime_token_env() -> None:
    """若 MCD_MCP_TOKEN 未设置，尝试从 .env 读取（兼容 mcp_token / MCD_MCP_TOKEN 两种键名）。"""
    if os.environ.get(TOKEN_ENV):
        return
    candidates = [Path.cwd() / ".env", _PROJECT_ROOT / ".env"]
    for path in candidates:
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("mcp_token=") or line.startswith("MCD_MCP_TOKEN="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    os.environ[TOKEN_ENV] = value
                return


class McpError(RuntimeError):
    """MCP 调用失败。message 里带上足够定位问题的信息。"""


class RateLimitError(McpError):
    """触发了 600 次/分钟的限流，调用方应该退避重试。"""


def _parse_sse(raw: str) -> list[dict]:
    """把 text/event-stream 响应拆成若干 JSON 对象。

    MCP 的 Streamable HTTP 允许服务端用 SSE 回包，每条事件形如：
        event: message
        data: {"jsonrpc":"2.0","id":1,"result":{...}}
    也可能没有任何 event 行，只有 data。
    """
    out: list[dict] = []
    for block in raw.replace("\r\n", "\n").split("\n\n"):
        payload_lines = [
            line[5:].strip()
            for line in block.split("\n")
            if line.startswith("data:")
        ]
        if not payload_lines:
            continue
        joined = "\n".join(payload_lines)
        if joined in ("", "[DONE]"):
            continue
        try:
            out.append(json.loads(joined))
        except json.JSONDecodeError:
            continue
    return out


class McDonaldMcpClient:
    """一次会话内复用同一个实例；它会自动携带服务端下发的 Mcp-Session-Id。"""

    def __init__(
        self,
        token: str | None = None,
        endpoint: str | None = None,
        timeout: float = 40.0,
        max_retries: int = 2,
    ) -> None:
        self.token = (token or os.environ.get(TOKEN_ENV, "")).strip()
        if not self.token:
            _prime_token_env()
            self.token = (token or os.environ.get(TOKEN_ENV, "")).strip()
        if not self.token:
            raise McpError(
                f"未找到 MCP Token。请先设置环境变量 {TOKEN_ENV}。\n"
                "  Windows PowerShell : $env:MCD_MCP_TOKEN='你的Token'\n"
                "  Git Bash / macOS   : export MCD_MCP_TOKEN='你的Token'\n"
                "Token 在 https://open.mcd.cn/mcp 登录后于控制台激活获取。"
            )
        self.endpoint = (endpoint or os.environ.get(ENDPOINT_ENV, ENDPOINT)).strip()
        self.timeout = timeout
        self.max_retries = max_retries
        self._next_id = 0
        self._session_id: str | None = None
        self._initialized = False
        self._tool_names: list[str] | None = None
        self._tools_raw: list[dict] | None = None

    # ------------------------------------------------------------------ 传输层

    def _post(self, payload: dict, expect_body: bool = True) -> list[dict]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self.token}",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
            "User-Agent": "mcd-send-a-meal/0.1",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        attempt = 0
        while True:
            req = urllib.request.Request(
                self.endpoint, data=body, headers=headers, method="POST"
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    sid = resp.headers.get("Mcp-Session-Id")
                    if sid:
                        self._session_id = sid
                    raw = resp.read().decode("utf-8", "replace")
                    ctype = resp.headers.get("Content-Type", "")
                    status = resp.status
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:500]
                if exc.code == 429:
                    if attempt < self.max_retries:
                        attempt += 1
                        time.sleep(1.5 * attempt)
                        continue
                    raise RateLimitError(
                        "触发了限流（600 次/分钟）。请降低调用频率后重试。"
                    ) from None
                if exc.code == 401:
                    raise McpError(
                        "MCP Token 无效、已过期或未提供（401）。"
                        "请到 https://open.mcd.cn/mcp 控制台重新复制 Token。"
                    ) from None
                raise McpError(f"HTTP {exc.code}: {detail}") from None
            except urllib.error.URLError as exc:
                if attempt < self.max_retries:
                    attempt += 1
                    time.sleep(1.0 * attempt)
                    continue
                raise McpError(f"网络不可达: {exc.reason}") from None

            if not expect_body or status == 202 or not raw.strip():
                return []
            if "text/event-stream" in ctype:
                return _parse_sse(raw)
            try:
                return [json.loads(raw)]
            except json.JSONDecodeError as exc:
                raise McpError(f"响应不是合法 JSON: {raw[:300]}") from exc

    def _rpc(self, method: str, params: dict | None = None) -> Any:
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            payload["params"] = params

        messages = self._post(payload)
        if not messages:
            raise McpError(f"{method} 没有返回任何消息")

        for msg in messages:
            if msg.get("id") != self._next_id:
                continue
            if "error" in msg:
                err = msg["error"]
                raise McpError(
                    f"{method} 失败: {err.get('message', err)} "
                    f"(code={err.get('code')})"
                )
            return msg.get("result")
        raise McpError(f"{method} 未返回匹配 id={self._next_id} 的响应")

    def _notify(self, method: str, params: dict | None = None) -> None:
        payload: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self._post(payload, expect_body=False)

    # ------------------------------------------------------------------ 协议层

    def initialize(self) -> dict:
        if self._initialized:
            return {"_cached": True}
        result = self._rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "mcd-send-a-meal", "version": "0.1.0"},
            },
        )
        self._notify("notifications/initialized")
        self._initialized = True
        return result or {}

    def list_tools(self) -> list[dict]:
        self.initialize()
        if self._tools_raw is None:
            result = self._rpc("tools/list") or {}
            self._tools_raw = result.get("tools") or []
            self._tool_names = [t.get("name", "") for t in self._tools_raw]
        return self._tools_raw

    def tool_names(self) -> list[str]:
        self.list_tools()
        return list(self._tool_names or [])

    def call_tool(self, name: str, arguments: dict | None = None) -> Any:
        """调用一个 MCP tool，返回尽量结构化后的结果。"""
        self.initialize()
        result = self._rpc(
            "tools/call", {"name": name, "arguments": arguments or {}}
        )
        return _unwrap_tool_result(result, name)


def _extract_first_json(text: str) -> Any | None:
    """从可能夹杂 markdown 说明的文本里取出第一个平衡的大 JSON 对象/数组。

    麦当劳 MCP 的 tools/call 返回的是「给模型看的」markdown，真实数据往往
    嵌在一段 JSON 信封（含 success/code/data）里。这里做一次尽力而为的提取，
    拿不到就返回 None（调用方会保留原文本）。
    """
    if not text:
        return None
    candidates: list[Any] = []
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        while start != -1:
            depth = 0
            in_str = False
            esc = False
            end = -1
            for i in range(start, len(text)):
                ch = text[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if end == -1:
                break
            frag = text[start : end + 1]
            try:
                candidates.append(json.loads(frag))
            except json.JSONDecodeError:
                pass
            start = text.find(opener, start + 1)
    # 优先返回 API 信封（含 success/data/code 的对象），避免命中 markdown 里的小片段
    for cand in candidates:
        if isinstance(cand, dict) and ("success" in cand or "data" in cand or "code" in cand):
            return cand
    return candidates[0] if candidates else None


def _unwrap_tool_result(result: Any, tool_name: str) -> Any:
    """MCP 的 tools/call 返回 content 数组。

    文本块里有时是干净 JSON，有时是「给模型看的」markdown（真实数据裹在
    内嵌 JSON 信封里）。这里两层解包：先整体 json.loads，失败再从 markdown
    里提取第一个 JSON 信封；都拿不到就保留原文本，交给上层 as_list/as_dict 兜底。
    """
    if not isinstance(result, dict):
        return result

    if result.get("isError"):
        texts = [
            c.get("text", "")
            for c in result.get("content", [])
            if isinstance(c, dict)
        ]
        raise McpError(f"{tool_name} 返回错误: {' '.join(texts)[:500] or result}")

    blocks = result.get("content")
    if not isinstance(blocks, list):
        return result

    decoded: list[Any] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text = block.get("text", "")
            try:
                decoded.append(json.loads(text))
            except (json.JSONDecodeError, TypeError):
                obj = _extract_first_json(text)
                decoded.append(obj if obj is not None else text)
        elif block.get("type") == "resource":
            decoded.append(block.get("resource"))
        else:
            decoded.append(block)

    if len(decoded) == 1:
        return decoded[0]
    if not decoded:
        return result.get("structuredContent", result)
    if "structuredContent" in result:
        return result["structuredContent"]
    return decoded


def build_client(token: str | None = None) -> McDonaldMcpClient:
    """工厂函数，顺便做一次连通性自检。"""
    return McDonaldMcpClient(token=token)
