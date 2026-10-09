# 麦麦代送 · mcd-send-a-meal

> 用麦当劳中国 MCP，把一份麦当劳**送到别人手上**。

一句话定位：**不是「我给自己点」，而是「我给爸妈 / 恋人 / 加班的同事点一份，送到他们那儿」**。
这是 M-CODE 程序员创意开发大赛里目前**唯一一个异地代送**选题——96 个报名项目里 0 命中。

---

## 为什么做这个

所有人都在做「自点」：查我附近的店、按我的口味点、送到我家。
但「**代送**」是另一件事，约束全在**收件人**身上：

| 维度 | 自点（别人都在做） | 代送（本项目） |
| --- | --- | --- |
| 查店原点 | `query-nearby-stores`（我附近） | `delivery-query-stores`（**收件人地址**） |
| 券 | 我账户里有的券 | **按收件人所在门店重查**的券 |
| 忌口/营养 | 我的偏好 | **收件人画像**：长辈控钠、恋人控卡、同事要扛饿 |
| 出错成本 | 自己吃亏 | **替别人花钱**，地址错/忌口漏更致命 |

代送场景里最容易被忽略、但决定成败的一步是：**把「查店原点」从下单人切到收件人**。
给杭州的爸妈点餐，我附近的店根本送不到他们那儿。

---

## 核心能力

- **收件人地址簿**：存「给谁、点去哪、什么忌口」，本地 JSON，不进版本库（`.gitignore` 已排除）。
- **收件人画像约束求解**：把「关系」翻译成可执行营养硬约束，本地确定性计算（热量/钠/蛋白/脂肪），**数值不进 LLM**。
- **门店智能匹配**：按收件人地址的可配送门店排序（距离 0.45 / 预计送达 0.40 / 营业 0.15），休息中的店直接淘汰。
- **真实核价 + 券重查**：所有金额以官方 `calculate-price` 为准，单位「分→元」显式处理，券按目标门店重查。
- **确认门控**：任何写操作（创建订单、领券）必须显式 `--confirm`，绝不静默执行。
- **给收件人的卡片**：下单后生成一张单文件离线 HTML 卡片（含餐品、营养、价格、配送进度），顺手能转发。
- **零依赖 + 离线演示**：只用 Python 标准库；`--dry-run` 用内置样例数据，没有 Token 也能跑通完整流程。

---

## 安装

```bash
# 需要 Python 3.10+，无任何第三方依赖
git clone <你的仓库地址>
cd mcd-send-a-meal

# 看项目结构
python scripts/send_a_meal.py --help
```

> 本项目**不依赖** `requests` 等任何第三方包，标准库 `urllib` 直接打 MCP 的 Streamable HTTP。

---

## 快速开始（不需要 Token）

```bash
# 1) 用内置样例地址簿，先看「给爸妈点一份」会出什么方案（只读，不会下单）
python scripts/send_a_meal.py --dry-run --contacts examples/contacts.sample.json plan --to 爸妈

# 2) 生成一张给收件人的卡片（不下单）
python scripts/send_a_meal.py --dry-run --contacts examples/contacts.sample.json card --to 爸妈 --out out/card.html
```

`--dry-run` 走 `src/mcd_send/fixtures.py` 的离线后端，评委/同事在地铁上也能看完整流程。

---

## 真实使用（需要麦当劳 MCP Token）

1. 到 https://open.mcd.cn/mcp 登录并激活 Token。
2. 设置环境变量（**不要写进代码或配置文件**）：
   ```bash
   # Windows PowerShell
   $env:MCD_MCP_TOKEN = '你的Token'
   # Git Bash / macOS
   export MCD_MCP_TOKEN='你的Token'
   ```
3. 准备收件人地址簿：复制 `examples/contacts.sample.json` 为 `contacts.json`，把 `address_id` 换成真实值（用 `address-new` 子命令创建）。
4. 出方案 → 确认 → 下单：
   ```bash
   python scripts/send_a_meal.py plan --to 爸妈
   python scripts/send_a_meal.py send --to 爸妈 --combo 1 --confirm
   python scripts/send_a_meal.py track --order-id <订单号>
   ```
   MCP 接入配置见 [`mcp-config.example.json`](mcp-config.example.json)。

---

## 命令速查

| 命令 | 作用 | 是否写操作 |
| --- | --- | --- |
| `inspect` | 打印 MCP Server 真实提供的 tool 与参数 | 否 |
| `contacts` | 列出地址簿与各自约束 | 否 |
| `plan --to <称呼>` | 出一份代送方案（只读） | 否 |
| `send --to <称呼> --combo N --confirm` | 按方案下单 | **是（需 --confirm）** |
| `track --order-id <ID>` | 查配送进度 | 否 |
| `card --to <称呼> --out <path>` | 只生成收件人卡片 | 否 |
| `address-new --name --phone --address` | 为收件人新建配送地址 | 是（需 Token） |

---

## 架构

```
mcd-send-a-meal/
├── src/mcd_send/
│   ├── mcp_client.py    # 零依赖 Streamable HTTP 客户端（initialize/list/call）
│   ├── tools.py         # 业务工具层 + ToolSchemas（schema 驱动参数归一化）
│   ├── contacts.py      # 收件人地址簿
│   ├── profiles.py      # 收件人画像（关系→营养硬约束）
│   ├── store_match.py   # 按收件人地址排序门店（代送核心）
│   ├── menu.py          # 分类 + 营养对齐 + 约束求解
│   ├── pricing.py       # 核价拆解（分→元、净省、配送费单列）
│   ├── planner.py       # 流程编排：只读 plan_send / 写入 execute_send
│   ├── card.py          # 收件人 HTML 卡片
│   └── fixtures.py      # 离线演示后端（同接口，无需 Token）
├── scripts/send_a_meal.py   # CLI 入口
├── skills/mcd-send-a-meal/  # WorkBuddy Skill 入口
├── tests/                   # 离线确定性单测（52 例，零依赖）
└── examples/contacts.sample.json
```

**四条设计原则**

1. **数值不进 LLM**：热量、钠、蛋白的加总与阈值判定全部本地纯 Python 算，模型只讲人话。
2. **零依赖**：只标准库，任何机器可跑。
3. **Schema 驱动参数解析**：平台未公开 tool 入参 schema，故 `ToolSchemas.resolve()` 做大小写/下划线不敏感归一化，匹配不上就报错并列出合法参数名。
4. **确认门控**：替别人花钱，任何写操作必须人确认。

---

## 收件人画像（内置五类）

`parent`（控钠/去冰/忌辣）· `partner`（控卡/控脂）· `friend`（宽松）· `colleague`（高蛋白扛饿）· `client`（偏正式）。
联系人可在 `profile` 字段覆盖任意默认值。

---

## 参赛说明

- 参赛仓库声明见 [`CONTEST_DECLARATION.md`](CONTEST_DECLARATION.md)（内容不可改）。
- MCP 接入说明见 [`MCP_INTEGRATION.md`](MCP_INTEGRATION.md)。
- 本项目的 WorkBuddy 开发上下文见 [`workbuddy.md`](workbuddy.md)。

> 本项目非麦当劳官方产品，仅用于 M-CODE 大赛技术演示。

## License

MIT · Copyright (c) 2026 Michael Li
