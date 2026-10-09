# 演示提示词 · demo-prompts.md

> 可直接复制的演示话术与命令。分两部分：**A. Skill 自然语言**（接了 MCP 的 Agent 里直接说）、
> **B. CLI 命令**（终端里跑）。全部默认**只读**，不会下单、不会扣款。

---

## A. 在 Agent 里直接说（Skill 触发句）

先装载 Skill：把 [`../skills/mcd-send-a-meal/SKILL.md`](../skills/mcd-send-a-meal/SKILL.md) 放进你的技能目录
（WorkBuddy：`~/.workbuddy/skills/mcd-send-a-meal/`），并配好 `mcd-mcp` 连接器。

### 场景 1 · 给异地爸妈点一份（最典型）

```
给我爸妈点一份麦当劳，送到他们家。他们年纪大了，要少盐、别太辣、饮料不要冰。
```

<details><summary>预期行为</summary>

Agent 会：确认地址簿里的「爸妈」→ 按**收件人地址**找可配送门店（不是你附近）→
拉该门店真实菜单 → 按长辈画像（控钠/去冰/忌辣）求解 → 按**收件人门店**重查券 → 官方核价 →
把「商品价 / 券优惠 / 配送费 / 应付」分开讲清楚 → **停下来等你确认**。

</details>

### 场景 2 · 给恋人点（控卡）

```
帮我给女朋友点份晚餐，她在控制热量，700 大卡以内，别太油腻。
```

### 场景 3 · 给加班同事点（要扛饿）

```
给加班的同事点份晚餐，他要能扛饿，蛋白质高点，送到公司。
```

### 场景 4 · 给客户送（偏正式）

```
给客户送份餐，正式一点，别太随意，送到他们公司前台。
```

### 场景 5 · 只要方案，先别下单

```
先别下单，帮我看看给爸妈点的话有哪几种组合，各自多少钱、多少钠。
```

### 场景 6 · 生成给收件人的卡片

```
下单之后，生成一张卡片发给我妈，写上「妈，生日快乐，记得趁热吃」。
```

### ⚠️ 触发确认红线的话术（用来验证门控）

```
就这个，点吧
```

> 只有明确说了「下单 / 就这个 / 点吧」这类话，Agent 才会加 `--confirm`。
> 说「先看看」「再想想」绝不会下单——这是替别人花钱的红线。

---

## B. 终端里跑（CLI）

### 最省事的三步（无 Token，纯离线演示）

```bash
# 1) 看地址簿里都有谁
python scripts/send_a_meal.py --dry-run --contacts examples/contacts.sample.json contacts

# 2) 出一份给爸妈的代送方案（只读，不会下单）
python scripts/send_a_meal.py --dry-run --contacts examples/contacts.sample.json plan --to 爸妈

# 3) 生成一张给收件人的卡片（不下单）
python scripts/send_a_meal.py --dry-run --contacts examples/contacts.sample.json card --to 爸妈 --out out/card.html
```

### 接真实 MCP（只读验证，绝不产生业务后果）

```bash
export MCD_MCP_TOKEN='你的Token'          # Windows PowerShell: $env:MCD_MCP_TOKEN='你的Token'

# 打印服务端真实提供的工具与入参名
python scripts/send_a_meal.py inspect

# 只读出方案：按收件人地址找店 → 真实菜单 → 营养求解 → 按门店重查券 → 官方核价
python scripts/send_a_meal.py plan --to 爸妈
```

### 真下单（⚠️ 会真实扣款，仅在你想清楚时执行）

```bash
# --confirm 是硬门控，不加只会预演
python scripts/send_a_meal.py send --to 爸妈 --combo 1 --confirm

# 下单后查进度
python scripts/send_a_meal.py track --order-id <订单号>
```

### 为收件人新建配送地址（写操作）

```bash
python scripts/send_a_meal.py address-new --name "妈妈" --phone "138****" --address "广州市海珠区革新路…"
```

---

## C. 评委 / 同事 30 秒体验路径

不想配 Token 也想看完整效果，跑这一条就够：

```bash
python tests/run_all.py                                                    # 59 例单测全绿
python scripts/send_a_meal.py --dry-run --contacts examples/contacts.sample.json plan --to 爸妈
```

离线后端 `src/mcd_send/fixtures.py` 与真实 MCP **同接口**，输出结构与真实调用一致，
地铁上、断网时都能演示完整链路。
