# MCP 接入说明 · MCP_INTEGRATION.md

本文件说明「麦麦代送 mcd-send-a-meal」如何使用**麦当劳中国 MCP Server**，
是 M-CODE 大赛的 MCP 接入证明文档。

---

## 1. 接入的 MCP Server

| 项 | 值 |
| --- | --- |
| Server 地址 | `https://mcp.mcd.cn` |
| 传输协议 | Streamable HTTP（MCP 规范） |
| 鉴权方式 | `Authorization: Bearer <MCD_MCP_TOKEN>`（Token 仅读环境变量 `MCD_MCP_TOKEN`，**不落代码/配置**） |
| 协议版本 | `2025-06-18` |
| 限流 | 每个 Token 每分钟最多 600 次，超限返回 `429`（客户端自动退避重试） |
| 客户端依赖 | **零依赖**，仅用 Python 标准库 `urllib`（见 `src/mcd_send/mcp_client.py`） |

接入配置样例见 `mcp-config.example.json`：

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": { "Authorization": "Bearer ${MCD_MCP_TOKEN}" }
    }
  }
}
```

---

## 2. 用到的 MCP 工具

本项目**不自己实现业务逻辑**，所有真实数据均来自以下麦当劳 MCP 工具。
下表标注了每个工具在「代送」场景下的特殊用法。

| MCP 工具名 | 本项目封装方法 | 用途 | 代送场景的特殊性 |
| --- | --- | --- | --- |
| `now-time-info` | `now()` | 当前时间/星期 | 用于展示「趁热吃」等文案 |
| `delivery-query-addresses` | `list_addresses()` | 列出已存配送地址 | 只读辅助 |
| `delivery-create-address` | `create_address()` | **新建收件人配送地址** | 代送前提：地址是收件人的 |
| `delivery-query-stores` | `stores_for_address()` | **按收件人地址查可配送门店** | ⭐ 核心：查店原点切到收件人，而非 `query-nearby-stores` |
| `query-nearby-stores` | `nearby_stores()` | 查我附近的店 | 自点用，**代送不用** |
| `query-meals` | `meals(store_code)` | 拉取门店在售菜单 | 用收件人门店的 `store_code` |
| `query-meal-detail` | `meal_detail()` | 单品详情/可定制项 | 展示「去冰/少酱」等 |
| `list-nutrition-foods` | `nutrition()` | 官方营养表 | 约束求解的数据源 |
| `query-store-coupons` | `store_coupons(store_code)` | **查收件人门店可用券** | ⭐ 核心：券按目标门店重查，不复用本地下单券包 |
| `available-coupons` | `claimable_coupons()` | 可领券列表 | 只读 |
| `auto-bind-coupons` | `auto_bind_coupons()` | 一键领券 | 写操作，需用户确认；本项目默认不自动领 |
| `query-my-coupons` | `my_coupons()` | 账户券包 | 门店券为空时回退使用 |
| `calculate-price` | `calculate_price()` | **官方核价** | 金额唯一权威来源，单位「分」 |
| `create-order` | `create_order()` | **创建订单** | 写操作，需 `--confirm` |
| `query-order` | `query_order()` | 查配送进度 | 代送比自点更重要（收件人不在场） |
| `cancel-order` | `cancel_order()` | 取消订单 | 写操作 |

> 写操作（创建地址 / 领券 / 下单 / 取消）全部走显式 `--confirm` 门控，绝不静默执行。

---

## 3. 调用流程

```
                 ┌──────────── 只读阶段 plan_send() ────────────┐
  收件人(本地) ──► delivery-query-stores(收件人 addressId)      # 找可配送门店
                 └─► 选店(store_match)                          # 距离/ETA/营业 加权
                      ├─► query-meals(store_code)               # 收件人门店真实菜单
                      ├─► list-nutrition-foods()                # 官方营养表
                      ├─► build_combos() 本地约束求解           # 数值不进 LLM
                      ├─► query-store-coupons(store_code)       # 按门店重查券
                      └─► calculate-price(...) ×N 组            # 官方核价，排序候选

                 ┌──────────── 写入阶段 execute_send(confirm) ─┐
                 └─► create-order(payload + couponId) ──► 支付链接
                      └─► query-order() 跟踪配送 / cancel-order() 取消
```

**两段式设计理由**：代送是替别人花钱，比自点更易出错（地址错、忌口漏、对方不在家）。
所以「出方案」与「下单」之间必须由人确认，任何写操作不允许静默执行。

---

## 4. 关键工程问题：平台未公开 tool 入参 schema

麦当劳 MCP 未公开每个工具的 `inputSchema`，参数名（`storeCode` 还是 `store_code`）
只能运行时通过 `tools/list` 问出来。硬猜参数名会在换机/平台发版时全线报错。

本项目采用 **schema 驱动参数解析**（`src/mcd_send/tools.py` 的 `ToolSchemas`）：

1. 首次调用拉一次 `tools/list`，缓存每个 tool 的真实 `inputSchema`；
2. 业务代码用语义化参数名，交给 `ToolSchemas.resolve()` 做**大小写 + 下划线不敏感**归一化匹配；
3. 匹配不上就把该 tool 的**合法参数名全列出来**报错，而不是让请求带着错误参数打过去收一个看不懂的 400。

效果：即使某个参数名猜错，第一次运行就能拿到明确提示并立刻修正，不会出现「代码看着对、跑起来全错」。

---

## 5. 业务价值

- **填补空白赛道**：96 个报名项目里「异地代送」0 命中，本项目是唯一的代送方案。
- **真正用对了 MCP 能力**：不是简单套 `query-nearby-stores` + `create-order`，而是把代送链路里
  最关键的 `delivery-query-stores`（按收件人地址找店）和 `query-store-coupons`（按门店重查券）
  用到位，这才是「代送」和「自点」的本质区别。
- **可解释、可复算**：门店排序权重、营养约束、核价拆解全部本地确定性计算，每一项都能对着原始数据复算，
  不依赖任何黑箱模型。
- **安全与隐私**：Token 仅读环境变量；收件人真实地址/手机号存在本地 `.gitignore` 排除的 JSON 里，不进版本库。

---

## 6. 错误处理与限流

- `401` → 提示 Token 无效/过期，引导去控制台重复制。
- `429` → 触发 `RateLimitError`，客户端指数退避后重试（最多 `max_retries` 次）。
- 网络不可达 → 退避重试，仍失败则抛出可读错误。
- SSE 响应统一在 `mcp_client._parse_sse` 解析；tool 返回的 content 文本块尽力 `json.loads`。
