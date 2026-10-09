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
                 └─► create-order(payload, addressId) ──► 支付链接
                      └─► query-order() 跟踪配送 / cancel-order() 取消
```

**两段式设计理由**：代送是替别人花钱，比自点更易出错（地址错、忌口漏、对方不在家）。
所以「出方案」与「下单」之间必须由人确认，任何写操作不允许静默执行。

---

## 4. 关键工程问题：响应是「给模型看的」markdown，不是干净 JSON

`tools/list` **确实有**每个工具的 `inputSchema`（本项目 `inspect` 子命令就是读它），
参数名可以运行时拿到并归一化匹配。真正的坑在 `tools/call` 的**返回**：

- 麦当劳 MCP 的 `tools/call` 返回的是**面向 LLM 的 markdown 文本块**，真实数据往往
  裹在一个 JSON 信封 `{ "success": true, "code": 200, "data": {...} }` 里。
- 例如 `delivery-query-addresses` 会先给一段「字段展示规范」的 markdown 表格，最后才附上上面的 JSON。
- 所以 `_unwrap_tool_result` 不能只做 `json.loads`：先整体解析，失败再用
  `mcp_client._extract_first_json` 从 markdown 里提取第一个平衡的 JSON 信封。

本项目采用 **schema 驱动参数解析**（`src/mcd_send/tools.py` 的 `ToolSchemas`）：

1. 首次调用拉一次 `tools/list`，缓存每个 tool 的真实 `inputSchema`；
2. 业务代码用语义化参数名，交给 `ToolSchemas.resolve()` 做**大小写 + 下划线不敏感**归一化匹配；
3. 匹配不上就把该 tool 的**合法参数名全列出来**报错，而不是让请求带着错误参数打过去收一个看不懂的 400。

效果：即使某个参数名猜错，第一次运行就能拿到明确提示并立刻修正，不会出现「代码看着对、跑起来全错」。

---

## 5. 真实 API 契约（2026-10-09 实测）

以下均用真实 Token 跑通验证，是本项目能端到端出方案的依据。**参数名/单位与直觉差异很大，
单测与文档之外务必以 `inspect` 实时为准**。

### 5.1 门店类型 `beType` 与外送

| 值 | 含义 | 代送是否用 |
| --- | --- | --- |
| `1` | 到店取餐 | 否 |
| `2` | 麦乐送到家（外送） | ✅ 代送默认 |
| `5` | 得来速 DT | 否 |
| `6` | 企业团餐 | 否（券走 `gmServiceCode`） |

- `delivery-query-stores` 在外送场景**只接受 `beType=2`（或 `6`）**，传 `5` 会报
  `600049「外送场景下，仅支持麦乐送(beType=2)和团餐(beType=6)两种」`。本项目默认 `beType=2`。
- `orderType` 语义：`1`=到店（含自取+DT），`2`=外送（含麦乐送+团餐）。**只读出方案阶段用
  `beType=2 + orderType=1` 即可核价**（返回商品价，不含配送费）；真·外送下单 `orderType=2`
  必传 `beCode`，且部分商品会报 `60006「商品已售罄或不可售」`，需另行处理。

### 5.2 各工具返回结构与口径

| 工具 | 真实返回要点 | 本项目解析方式 |
| --- | --- | --- |
| `delivery-query-addresses` | 信封 `data.addresses[]`：`addressId/contactName/phone/fullAddress` | `as_list(res, "addresses")`，内层也查 `addresses` |
| `delivery-query-stores` | 信封 `data` 直接是门店数组；门店含 `storeCode/beCode/storeName/businessStatus` | `as_list(res, "stores")` |
| `query-meals` | 信封 `data.meals` 是 **dict[code]→{name,currentPrice,originalPrice,image,…}**；`data.categories[]` 仅展示分组（只有 `code`+`tags`，无名称价格） | 优先取 `data.meals` 目录；**不要**带 `beCode`（带则 `600057`） |
| `list-nutrition-foods` | `data` 是**字符串**（自定义表格：`[160]{列…}:\n 猪柳麦满分,值…`），非 JSON 数组 | 暂未结构化解析 → 营养约束降级为警告（已知缺口） |
| `query-store-coupons` / `query-my-coupons` | 返回**纯 markdown 文案**（如「麦旋风任选 ¥9.9」），无结构化 JSON | 暂未解析 → 券池为空（已知缺口），下单当前不带券 |
| `calculate-price` | 信封 `data`：`price/originalPrice/productOriginalPrice/discount`（**单位：分**）+ `productList[]` | `productCode`+`quantity` 入参（非 `mealCode`/`count`）；**不要**带 `beCode`（带则 `600012`）；金额 `to_yuan` 除以 100 |
| `create-order` | 必填入参 `storeCode/orderType/beType`，另需 `addressId/items` | 由 `execute_send` 在 `--confirm` 后构造（`include_address=True`） |

### 5.3 金额单位

- `calculate-price` 返回**分**（如 `price: 3350` = ¥33.50），`parse_price_result` 统一 `to_yuan()` 除以 100。
- `query-meals` 目录里的 `currentPrice/originalPrice` 是**元**的字符串（如 `"33.5"`），仅作展示/本地预估，
  **最终应付一律以 `calculate-price` 为准**。

### 5.4 待补齐的已知缺口（不影响只读出方案）

1. **官方营养表**为字符串格式，需写专门的文本解析器才能把「钠/热量/蛋白」挂上餐品，
   目前该约束在方案里降级为「未收录」警告。
2. **门店券/账户券**为 markdown 文案，需文本解析才能拿到 `couponCode/couponId`，
   目前下单不带券（不影响出方案与下单主流程）。
3. **真·外送下单** `orderType=2` 的 `beCode`/商品可售性组合仍需联调。

---

## 6. 业务价值

- **填补空白赛道**：96 个报名项目里「异地代送」0 命中，本项目是唯一的代送方案。
- **真正用对了 MCP 能力**：不是简单套 `query-nearby-stores` + `create-order`，而是把代送链路里
  最关键的 `delivery-query-stores`（按收件人地址找店）和 `query-store-coupons`（按门店重查券）
  用到位，这才是「代送」和「自点」的本质区别。
- **可解释、可复算**：门店排序权重、营养约束、核价拆解全部本地确定性计算，每一项都能对着原始数据复算，
  不依赖任何黑箱模型。
- **安全与隐私**：Token 仅读环境变量；收件人真实地址/手机号存在本地 `.gitignore` 排除的 JSON 里，不进版本库。

---

## 7. 错误处理与限流

- `401` → 提示 Token 无效/过期，引导去控制台重复制。
- `429` → 触发 `RateLimitError`，客户端指数退避后重试（最多 `max_retries` 次）。
- 网络不可达 → 退避重试，仍失败则抛出可读错误。
- SSE 响应统一在 `mcp_client._parse_sse` 解析；tool 返回的 content 文本块尽力 `json.loads`。
