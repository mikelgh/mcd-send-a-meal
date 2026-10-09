# 真实环境只读验证报告

> 本文档记录「麦麦代送 mcd-send-a-meal」使用**麦当劳真实 MCP Token** 完成的只读验证，
> 以及由此发现的官方接口**契约偏差**（已在代码中对齐）。

⚠️ **红线声明**：本次验证全部为**只读**调用，**从未执行下单、领券、支付或创建地址**，
不产生任何业务后果、不消耗任何权益。所有写操作在本项目中均需显式 `--confirm` 才会触发。

- 验证日期：2026-10-09
- MCP Server：`https://mcp.mcd.cn`（Streamable HTTP，Bearer Token）
- Token 来源：环境变量 `MCD_MCP_TOKEN`（项目根 `.env`，已被 `.gitignore` 排除，**不进版本库**）

---

## 1. 离线验证（无需 Token）

任何人在没有 Token 的情况下都能完整复现：

```bash
python tests/run_all.py
```

```
Ran 59 tests in 0.463s
OK
```

| 测试文件 | 覆盖内容 |
| --- | --- |
| `test_util.py` | 数值/字符串归一化（`to_float` / `pick` / `clamp`） |
| `test_contacts.py` | 地址簿解析与约束合并 |
| `test_profiles.py` | 收件人画像（长辈控钠 / 恋人控卡 / 同事要蛋白） |
| `test_store_match.py` | 按收件人地址排序门店、休息门店淘汰 |
| `test_menu.py` | 分类、营养对齐、约束求解 |
| `test_pricing.py` | 核价拆解（分→元、净省、配送费单列） |
| `test_planner.py` | 只读 `plan` 与写入 `send` 的门控 |
| `test_card.py` | 收件人 HTML 卡片渲染与转义 |
| `test_parsers.py` | **营养表字符串解析 + 券 markdown 解析**（真实样本锁定） |

另有 `--dry-run` 离线后端（`src/mcd_send/fixtures.py`），无 Token 也能跑通完整流程。

---

## 2. 真实 Token 只读验证结果

| 项目 | 结果 |
| --- | --- |
| ✅ `initialize` | MCP 会话建立成功 |
| ✅ `tools/list` | 拿到服务端真实工具清单 |
| ✅ `delivery-query-addresses` | 返回真实地址簿 |
| ✅ `delivery-query-stores` | 按**收件人地址**返回可配送门店（实测选中「麦当劳广州革新路餐厅 1400418」） |
| ✅ `query-meals` | 返回该门店**真实在售菜单 124 个餐品** |
| ✅ `list-nutrition-foods` | 返回官方营养表（自定义表格**字符串**） |
| ✅ `query-store-coupons` | 按收件人所在门店重查到 **2 张可用券**（带 `couponCode`） |
| ✅ `calculate-price` | 逐组试算真实应付，金额单位「分」 |
| ✅ 营养约束求解 | 生效：`538kcal · 钠978mg · 蛋白28g` |

### 真实 `plan` 输出（只读，原文摘录）

```
读取收件人「爸妈」
按收件人地址找可配送门店（广州）
选中门店 麦当劳广州革新路餐厅（1400418）
拉取该门店真实在售菜单
拉取官方营养表并做约束求解
按收件人所在门店重查可用券（门店 1400418）
调官方核价接口逐组试算真实应付

====================================================================
  代送方案 · 收件人 爸妈（广州）
====================================================================
  配送门店  麦当劳广州革新路餐厅（1400418）
  门店菜单  124 个在售餐品，其中 6 组进入核价
  可用券    2 张（已按收件人所在门店重查）
  收件人约束 长辈：控钠、去冰、避开难嚼和过辣的

  候选方案（已按官方核价排序）：
  [3] 主餐 + 小食      麦香鱼套餐 + 麦乐鸡
      应付 ¥47.50
         538kcal · 钠978mg · 蛋白28g  ★鸡

  [5] 全套           麦香鱼套餐 + 麦乐鸡 + 可乐
      应付 ¥57.00
         685kcal · 钠978mg · 蛋白28g  ★鸡
      · 饮品去冰
```

> 说明：部分新品（如「龙焰鸡腿堡三件套」「麦乐鸡套餐」）未被官方营养表收录，
> 程序**如实标注「营养数据缺失」并跳过该维度判定**，而非按 0 计算——这是设计上的诚实降级。

---

## 3. 实测发现的接口契约偏差（已在代码中对齐）

这部分是本项目对真实环境的主要工程贡献：官方文档/直觉与**服务端实际行为**存在多处偏差，
全部由实测定位并修正。

| 工具 | 直觉 / 假设 | 实测真实行为 | 我们的处理 |
| --- | --- | --- | --- |
| `delivery-query-stores` | 传 `beType=5` | **外送场景只接受 `beType=2`（麦乐送）或 `6`（团餐）**，传 5 报 `600049` | 固定 `DELIVERY_BE_TYPE = "2"` |
| `query-meals` | 带 `beCode` 查门店菜单 | 带 `beCode` 报 `600057`；真实目录在 `data.meals`（`dict[code]→{name,price}`），`categories` 只有分组 code | 不传 `beCode`，取 `data.meals` |
| `calculate-price` | 入参 `mealCode` + `count` | 实际要 **`productCode` + `quantity`**（否则 `600010`）；带 `beCode` 报 `600012` | 改用 `productCode`/`quantity`，去 `beCode` |
| `calculate-price` | 金额单位是「元」 | **单位是「分」**（`price: 3350` = ¥33.50） | `to_yuan()` 统一除以 100 |
| `list-nutrition-foods` | 返回 JSON 数组 | 返回**自定义表格字符串**（`[160]{列…}:\n 猪柳麦满分,null,308,…`） | 新增 `parse_nutrition_text()` 正则解析 |
| `query-store-coupons` | 返回 markdown 文案 | 实为**结构化 JSON**（含 `couponId`+`couponCode`+`products[]`） | 直取并按 item 级 `couponCode` 逐品注入核价 |
| `query-my-coupons` | 返回结构化数据 | 才是**纯 markdown 文案**（无 `couponCode`） | `parse_coupon_markdown()` 解析为可展示池 |
| 券的注入方式 | 订单级 `gmServiceCode` | 实为按 **item 级 `couponCode`** 逐品注入（`gmServiceCode` 是团餐专用） | 仅命中券适用商品 `products[].productCode` 的 item 才注入 |
| MCP 响应体 | 干净 JSON | 是**给 LLM 看的 markdown**，真实数据裹在 `{success,code,data}` 信封里 | `_extract_first_json()` 从文本抽平衡 JSON 信封 |

---

## 4. 已知限制（诚实披露）

1. **营养表覆盖不全**：官方营养表为字符串且未收录全部新品，未收录餐品的营养维度会跳过判定并逐条标注，不按 0 计算。
2. **真·外送下单未联调**：`orderType=2`（真外送）需传 `beCode`，且部分商品会报 `60006「商品已售罄或不可售」`。
   出于「替别人花钱」的红线，尚未用真实扣款验证该路径。
3. **账户券无 code**：`query-my-coupons` 返回的账户券是 markdown 文案、无 `couponCode`，仅作可展示池，不参与核价注入。

---

## 5. 如何复现

```bash
# A. 离线（无 Token，验证算法与流程）
python tests/run_all.py
python scripts/send_a_meal.py --dry-run --contacts examples/contacts.sample.json plan --to 爸妈

# B. 只读真实（需 Token，绝不产生业务后果）
export MCD_MCP_TOKEN='你的Token'          # Windows: $env:MCD_MCP_TOKEN='你的Token'
python scripts/send_a_meal.py inspect      # 打印服务端真实工具与参数名
python scripts/send_a_meal.py plan --to 爸妈   # 只读出方案，不下单
```

`inspect` 会打印 MCP Server **真实提供**的 tool 与入参名——正因为平台未公开入参 schema，
本项目才用 `ToolSchemas.resolve()` 做大小写/下划线不敏感的归一化，匹配不上就报错并列出合法参数名。
