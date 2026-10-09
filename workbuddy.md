# WorkBuddy 开发上下文 · workbuddy.md

> 本文件记录「麦麦代送 mcd-send-a-meal」在 **WorkBuddy**（腾讯 AI 编程助手）中的开发过程，
> 作为 M-CODE 大赛 **WorkBuddy 专项奖励**（3000 积分凭据）的提交材料。

---

## 1. 项目是怎么在 WorkBuddy 里长出来的

本项目的完整生命周期都在 WorkBuddy 中完成，典型节奏是「先规划、再执行、每步可验证」：

1. **赛事核实**：让 WorkBuddy 先核实 M-CODE 的排名机制（GitHub Star 是唯一指标）、报名格式、必需文件清单，
   避免方向上跑偏。
2. **竞争态势调研**：WorkBuddy 实时抓取 96 个报名 Issue → 解析各仓库的 `MCP_INTEGRATION.md` 做工具覆盖度统计，
   定位出「异地代送」是 0 命中的真空白赛道，据此锁定选题 A。
3. **骨架 + 实现**：在 `C:\DevOps\mcd-send-a-meal` 建仓库，逐个模块实现
   （MCP 客户端 → 工具封装 → 收件人画像 → 门店匹配 → 菜单求解 → 核价 → 流程编排 → 卡片 → CLI）。
4. **离线测试**：用内置 `fixtures.py` 跑通无 Token 全流程，并补 `tests/` 下 52 例确定性单测。
5. **文档与交付**：产出 `README.md` / `MCP_INTEGRATION.md` / `workbuddy.md` / `CONTEST_DECLARATION.md`。

---

## 2. 关键工程决策（WorkBuddy 协助定型）

| 决策 | 为什么 | 在哪 |
| --- | --- | --- |
| **零依赖**（仅标准库 `urllib`） | 评委/同事任何机器都能直接跑，不卡环境 | `mcp_client.py` |
| **数值不进 LLM** | 热量/钠/蛋白加总与阈值判定本地确定性计算，模型只讲人话 | `menu.py` / `planner.py` |
| **Schema 驱动参数解析** | 平台未公开 tool 入参 schema，归一化匹配 + 明确报错 | `tools.py` 的 `ToolSchemas` |
| **确认门控** | 替别人花钱，任何写操作必须 `--confirm` | `planner.execute_send` |
| **查店原点切到收件人** | 代送的本质：用 `delivery-query-stores` 而非 `query-nearby-stores` | `store_match.py` |
| **券按门店重查** | 异地账户在同城门店券不同，不复用本地下单券包 | `planner.plan_send` |
| **配送费单列、不误导「省¥X」** | 外送配送费会吃掉券优惠，净省可能为负 | `pricing.py` 的 `net_saved_yuan` |

---

## 3. 调试中修过的真实 Bug（WorkBuddy 辅助定位）

- **门店属性初始化顺序**：`list_tools()` 引用未初始化的 `self._tools_raw` → 在 `__init__` 显式初始化。
- **长辈钠上限不现实**：原 670mg 会让真实菜单直接无解 → 改为 1500mg（按「一天最多两餐快餐」权衡），代码注释说明。
- **「省¥X」误导**：原计算把配送费算进优惠 → 改为完整明细行（商品/券/配送/应付）。
- **候选主餐全重复**：求解器前几名常是同一主餐 → 新增 `_diversify()` 按主餐去重。
- **错误路径抛裸 traceback** → `ContactError` 继承 `ValueError`，CLI 统一友好提示。
- **休息中门店被选为交付店** → `pick_store` 显式跳过不可配送门店，全休息时直接报错。

---

## 4. 如何复现

```bash
# 1) 用 WorkBuddy 打开本仓库（或任意终端进入目录）
cd mcd-send-a-meal

# 2) 离线跑通完整流程（不需要 Token，也不需要 WorkBuddy）
python scripts/send_a_meal.py --dry-run --contacts examples/contacts.sample.json plan --to 爸妈

# 3) 跑确定性单测
python tests/run_all.py

# 4) 真实接入：设置环境变量 MCD_MCP_TOKEN 后去掉 --dry-run 即可
```

---

## 5. 工作流偏好（本项目的协作风格）

- **结构化交付**：先给赛道拥挤度/工具热力图等调研结论，再动手写代码。
- **分步可执行**：每个技术节点给出具体命令与预期输出，而非空泛介绍。
- **可验证优先**：任何功能写完立刻用 `--dry-run` 或单测验证，再往下走。
- **不改声明文件**：`CONTEST_DECLARATION.md` 内容按大赛要求原样保留，不增删。

---

> 本文件仅描述开发上下文，便于评审理解项目在 WorkBuddy 中的演进；项目本身与麦当劳官方无隶属关系。
