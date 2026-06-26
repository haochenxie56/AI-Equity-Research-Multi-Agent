# 路线图 / Roadmap — AI Investment OS

> **本文件是什么**：一份"同步对齐后"的完整路线图，把"已完成进度"和"未来各阶段的设计初衷与目标"合并在一处，作为**防漂移的权威备份 + 跨会话迁移的压舱石**。归档于 `docs/`，与 `docs/ai_dev_state/PROJECT_STATE.md` / `docs/AI_Investment_OS_Master_Memo_v3.md`（Master Memo）/ README 并列。
>
> **为什么要有它**：过去几轮对齐发现，光记"要做什么"不够——容易在跨会话时把一个条目的**本质**记串。所以这份路线图的每个未来条目都固定写清五件事：**它是什么 / 为什么做 / 做到什么算完成 / 它绝不能变成什么（防漂移护栏）/ 谁来用它**。
>
> 对齐基线：`main @ 6cc972e9a`（Phase 8B ThemeIntelligenceAgent docs closeout；最后一个 feature merge `5ecfb7875`）。Active parity 套件：69 `test_reliability_*` GREEN；外加 agent framework 15 + MacroRegime 24 + MoneyFlow 34 + MarketStructure 44 + SectorRotation 34 + ThemeIntelligence 39 + 8B-0 24 + 7B rotation 229 + theme_baskets 157。
> 更新日期 2026-06-26。**本版更新：ThemeIntelligenceAgent 已落地（第五个生产 agent）；constituent_rs 扩展 + 标签 lift 已完成；下一个 CandidateScreeningAgent。baseline 由 `1e389549b` 推进至 `6cc972e9a`；roster 状态、数据源接入状态、两世界连接状态对齐 PROJECT_STATE。**
> 沿革（v12，2026-06-24，基线 `1e389549b`）：MoneyFlowAgent / MarketStructureAgent / SectorRotationAgent 三个生产 agent 已落地（共四个 foundation agent 在产）；7D Block A / 8A / 8B-0 已收口；baseline 由 `a19b862` 推进至 `1e389549b`。
>
> 沿革：v11（2026-06-21，基线 `a19b862`）首次写入 MoneyFlowAgent 完整设计（GEX/DEX/Gamma Squeeze）、数据源决策（Quiver + Massive）、Phase 8B-0 数据接入基础层、TechnicalEntryAgent GEX 扩展——彼时仅 MacroRegimeAgent 在产。

---

## 〇、协作模式与纪律（会话迁移必读）

### 0.1 协作模式

* John 用中文讨论架构与产品思路，实现 prompt 用英文。
* Claude 是架构讨论搭档 + task-level prompt 工程师：产出给 Claude Code（实现）和 Codex（独立审查）的英文 prompt，**但自己从不写生产代码**。
* 管线：John 中文提需求 → Claude 出英文实现 prompt 给 Claude Code → John 贴结果 → Claude 出带 PREFLIGHT 的审查 prompt 给 Codex → John 贴 verdict → Claude 裁决修复轮或收口。
* 每个 phase 的节奏：STEP 0 画 access-path 矩阵 → 实现 → Codex 审查（含 mutation probe 验判别性）→ 修复轮（逐条裁决）→ APPROVE → John 转达明确 go（带"解锁什么"）→ Claude Code 做收口。
* Claude 要直接、有主见地 pushback，不附和；遇到 spec 真实歧义就停下提问，不自作主张选"更软"的。

### 0.2 git / 环境纪律

* WSL2/Ubuntu 仓库，Windows git 经 UNC 路径访问；实现在主 worktree（有 venv），审查在 standing review worktree `../investment-agents-review`（detached）。两者共享 `.git`、永不共用工作区。
* Claude Code 每会话跑在自己的临时 worktree（`claude/*`），会自生自灭；standing set 永远只该是 primary + review 两个。
* 单 actor 写入：一个工作区一个会话；git 拓扑操作（merge/push/分支退役）是串行屏障，操作前确认所有其他会话已停。
* merge 一律 `--no-ff`，绝不 rebase/force；push/merge 只在 John 转达明确 APPROVE 后。
* APPROVE 转达要带"解锁什么"——只说 approve 会被误读。
* 提交信息用 POSIX heredoc（`cat <<'EOF'`），**不要用 PowerShell here-string**（`@'...'@` 会漏 `@`，犯过三次）。
* Codex 审查除验代码外，把"**测试在 bug 存在时是否真的会红（判别性）**"当一等标准；后期 finding 多落在测试质量上（**假绿测试比没测试更危险**）。
* 意外 git 状态 → 停下报告（reflog 诊断，别乱动）。

### 0.3 文档纪律

每个 phase 收口的 docs commit **必须同步**：PROJECT_STATE.md + CURRENT_TASK.md + phase doc + README.md。README 是一等交付物、**绝不滞后**。曾发生过一次 README 编辑误删五条不变量原则行 + 整段 v2 roadmap 的事故——须警惕任何"简化"README 的操作。

### 0.4 Phase 0–5 地基扫描纪律

每个新 phase 开始前，STEP 0 勘察**必须**显式扫描 Phase 0–5 的遗留代码，检查是否有可复用的结构、数据类型或半成品实现。**有地基优先复用，无地基再新建。**

典型范例：Phase 7C 本可新建 tier/role 体系，但勘察发现 `lib/reliability/phase5_theme_intelligence.py` 已有完整的 `IndustryChainNode`、`ThemeCandidateRole` schema，节省了约 1,500 行已验合约的重复建设。

### 0.5 Agent 架构纪律（2026-06-19）

本项目的核心目标是 **AI Fund 工作流系统**，不是人工驾驶的研究仪表盘。所有新 phase 的设计决策必须以此为准绳：

* **代码判断 vs LLM 判断的边界**：凡是可以被确定性规则计算的分类（risk-on/off、regime label、PPI 方向、脆弱度评级），一律由代码给出，**LLM 不重复判断这些**。LLM 负责的是：把多个代码已算出的信号综合成"对具体交易的可操作含义"——必须具体到 ticker、时间窗口、入场条件、失效触发器，**绝不输出泛论**。
* **Agent 价值标准**：每个 agent 的 output 必须能回答"PM agent 拿到这个输出，能做出它原本做不了的决策吗？"否则这个 agent 没有价值。
* **有价值输出的判别标准**：✅ 包含具体条件（"当 X 发生时"）、✅ 具体标的或 sector、✅ 时间窗口、✅ 失效条件；❌ 只有方向性描述、❌ 没有可观察触发器。
* **AgentOutput schema 优先**：在写任何 agent 实现之前，必须先确认该 agent 遵循统一的 `AgentOutput` dataclass（见§1.5）。
* **UI 定位**：UI 的最终目标是"AI PM 向人类用户汇报的 dashboard"，而非决策工具本身。每个 agent judgment 必须可展开查看 evidence chain。

---

## 一、贯穿所有阶段的底层原则（压舱石）

### 1.1 LLM 判断的边界（核心原则，经校正）

> **数字交给代码；判断在证据约束下可以由 LLM 提建议；但人始终握最终否决权，且默认是人主控。**

* **数值这一侧（只能更硬，永不松）**：估值、评分、阈值、技术指标、市场数据，永远是确定性 Python 算出来的。LLM **绝不**看着原始数字自己下数值结论。
* **判断这一侧（在证据约束下可以有）**：LLM **可以**做"判断建议"，但三条铁律：
  1. **每条判断必须引用证据**：能追溯到证据包里的具体条目；没有证据支撑就标 `unknown`。
  2. **必须经人显式确认才生效**：默认状态是空白等人填；LLM 填充是按一个按钮触发的，可以为空、可以被人覆写。
  3. **判断来源要留痕**：每个判断字段标明"来源 = LLM 建议"还是"来源 = 人工"，写进审计轨。

### 1.2 不可删除的硬纪律

* **排除而非降权**：某个估值锚不可信时，整条排除并打标，不引入"连续降权旋钮"。
* **绝不编造数字**：LLM 永不发明估值/指标/评分/市场数据。
* **前视防护**：历史数据重算严格按披露滞后门控（`FILING_LAG_DAYS`）。
* **访问路径矩阵优先**：统一一个数据生产者，先画清矩阵再动手。
* **只追加审计轨**：估值锚历史和每日快照只追加、绝不改写旧行。
* **Tighten-only（只收紧）**：脆弱度层只能收紧短线入场门槛，**永不**翻转宏观 regime、**永不**放松任何门槛。
* **单一数据 vintage**：一次刷新内所有数据同源同龄，过期由守卫显式标记，绝不静默。
* **信号轨 / 审计轨分离**：实时滚动重算回答"市场做了什么"；每日快照记录"系统当天说了什么"，专供复盘。
* **降级词汇表**：任何数据缺位都有具体原因标签，监控组件**绝不静默消失**。

### 1.3 共享情景卡 Schema（三处共用一套）

未来有三个地方会产出"情景/假说"类结构：Thesis 卡里的宏观假说、宏观事件层的 LLM 情景、Phase 8 辩论的失效条件。它们**用同一套数据结构**：

```
{ 事件·假说 / 传导链 / 影响的时间维度·主题 / 确认条件 / 证伪条件 / 当前证据状态 }
```

设计要点：**先把完整结构定下来，早期只是"稀疏地填"**。带 `schema_version` 守卫。**消费者只能用这套结构的子集，不许各自加私有字段。**

### 1.4 已建成的地基（只作前提，不再展开）

Anchor Intelligence v2 系列已经把"锚情报层"建成：估值锚有了时间维度、可信度评估、可读诊断卡、诚实的同业匹配。append-only 审计轨、降级而非编造的纪律都已落地（`main @ 6f9c1ec`）。后面的阶段都站在这个地基上。

### 1.5 统一 AgentOutput Schema（2026-06-19）

**所有 agent 必须遵守此 schema，不得自定义替代结构。**

```python
@dataclass
class AgentOutput:
    agent_id: str                    # 唯一标识，如 "MacroRegimeAgent"
    timestamp: str                   # ISO 格式
    horizon: str                     # "short" | "mid" | "long" | "cross"
    judgment: str                    # 核心判断，一句话，必须具体可操作
    confidence: float                # 0.0–1.0
    evidence_refs: list[EvidenceRef] # 必填，空列表不允许
    supporting_data: dict            # agent-specific 结构化数据（代码算出的指标）
    requires_human_confirmation: bool
    judgment_source: str             # "llm_proposed" | "rule_based" | "human"
    valid_until: str                 # 判断有效期（MoneyFlowAgent = 当日，LongTermPM = 下季度）
```

**复用原则**：`EvidenceRef` / `EvidenceStore` / `validate_agent_result` / `DebateReport` 直接复用 `lib/reliability/` 已有实现。Phase 4M 的 in-memory 内存模型**放弃**，用新的 JSONL 持久化替代（路径：`data/agent_outputs/<agent_id>/<date>.jsonl`）。

> **落地补记（Phase 8A 实测）**：实现时 `AgentOutput` 落为 `@dataclass`，内嵌一个校验后的 `Optional[AgentResult]`（不继承 Pydantic）；evidence 从 `findings[].evidence + risks[].evidence` 扁平化、为空即 raise；judgment 取首句完整句（≤400 字符）、不得含数字/`%`/`$`/指标 token；`valid_until = end_of_today_iso()`；`approved_for_execution` 恒 `False`。所有 `lib.reliability` 导入惰性化（导入 agent 框架绝不触发 52 模块 eager `__init__`）。**`_repair_llm_response()` 结构修复层为每个 agent 必备**（见§七.12）。

---

## 二、已完成进度（状态快照）

全部在 `main`，已 push 到 origin。「收口位置」列为 docs-closeout 提交，括注对应的 `--no-ff` merge 提交（与 PROJECT_STATE 对齐）。

| 阶段 | 状态 | 收口位置 |
|---|---|---|
| 决策层基础（信号引擎 / 入场策略 v4 / 交易台 / Cockpit） | ✅ 完成 | — |
| Phase 7A — 机会排序（三周期独立评分/状态、每日快照、零网络排序） | ✅ 完成 | — |
| 估值止血（锚一致性门控、forward 口径、锚缓存） | ✅ 完成 | — |
| Phase 7B — 轮动 + 市场内部结构（多窗口 RS、两环轮动、脆弱度层） | ✅ 完成 | 30 日校准通过 |
| 估值重构 v1（公司分型路由器 + 增长画像同业匹配） | ✅ 完成 | `ca5ad14` |
| 脆弱度小项批次 + 杂务 | ✅ 完成 | `b5c128a` |
| **Anchor Intelligence v2 系列** | ✅ 完成 | Round1 `9e53f04` / v2.3 `84daa4a` / v2.4 `18dfcf2` / v2.5 `6f9c1ec` |
| **Banner 清理批 — 段一**（市场内部结构文案白话化 + i18n 收口 + README 原则校正 port） | ✅ 完成 | `f99ed2f` |
| **Banner 清理批 — 段二**（bulk 财报日历提前 + FRED 流动性 fetchers） | ✅ 完成 | `372dd25` |
| **Thesis Ingestion MVP**（研报卡库 + UI 验收批） | ✅ 完成 | `b323c09` |
| **Legacy Red Suite Archival**（13 个 Phase-5 红套件归档） | ✅ 完成 | `4f39838` + `8e6f891` |
| **Phase 7D Block A** — 快照审计查询接口（audit_query + pages/11） | ✅ 完成 | `a93909f`（merge `5a57850`） |
| **Phase 8A** — Agent 框架地基（AgentOutput + runner + adapter + 11 tests） | ✅ 完成 | `8ca5051`（merge `f6a0f74`） |
| **Phase 8B-0** — 新数据源接入基础层（Quiver + Massive + gex_dex，24 tests） | ✅ 完成 | `af3de6b`（merge `69d7c9f`） |
| **Phase 8B MacroRegimeAgent** — 首个生产 agent + prompt fix + repair layer（39 tests） | ✅ 完成 | `a19b862`（merge `eabf0c2d`） |
| **Step 3 Narrative Disk Cache**（LLM 叙事磁盘持久化，27 tests） | ✅ 完成 | `649b1f9`（merge `a2e43cd3`） |
| **_meta 扩展**（key_signals / opportunity_posture / confidence，7 tests） | ✅ 完成 | `a8adc4b`（merge `ffe9e1e2`） |
| **Cockpit 冷启动水化**（重启从快照填充 A/C 节，10 tests） | ✅ 完成 | `0f8a145`（merge `3eb4a89`） |
| **Phase 8B MoneyFlowAgent** — 第二个生产 agent（GEX/DEX + 暗池双源，34 tests） | ✅ 完成 | `7b7eb71`（merge `760f356`） |
| **Phase 8B MarketStructureAgent** — 第三个生产 agent（注入脆弱度读数，44 tests） | ✅ 完成 | `d74be8a`（merge `8792343`） |
| **FragilityReading O/D 扩展**（透传完整攻守 reading，229/229） | ✅ 完成 | `f016342`（merge `bb77ee2`） |
| **Phase 8B SectorRotationAgent** — 第四个生产 agent（主题+传导+O/D，34 tests） | ✅ 完成 | `1e38954`（merge `fbf0cc4`） |
| **constituent_rs 扩展 + 标签 lift**（ThemeIntelligenceAgent 前置） | ✅ 完成 | `3962e57`（merge `107e0f09`） |
| **Phase 8B ThemeIntelligenceAgent** — 第五个生产 agent（成分股角色 × RS + 跨波次非对称，39 tests） | ✅ 完成 | `6cc972e`（merge `5ecfb78`） |

### 架构现状快照（2026-06-26 更新）

**两个世界由 Phase 8A 连接组织接通，连接正逐个 agent 推进：**

| | World 1 — 活的生产 app | World 2 — 可靠性多 agent 层 |
|---|---|---|
| 位置 | `lib/*.py` + `pages/*.py` + `lib/llm_orchestrator.py` | `lib/reliability/`（52 个模块）+ `lib/agent_framework/` + `lib/agents/` |
| LLM 调用 | **有真实 Claude 调用**（claude-sonnet-4-6） | **agent runner 经证据约束调 LLM**；`lib/reliability/` 合约层仍零 LLM、100% 确定性 |
| 状态 | 已上线，用户可见 | 框架已激活；**5 个 foundation agent 在产**，其余仍休眠 |
| 数据流 | 页面直接调 `llm_orchestrator`（研究层）；Cockpit 另附加 5 个 agent 钩子 | `AgentOutput` 内嵌校验后的 `AgentResult`；ToolResult → `EvidenceStore` → 受约束提示 → 校验 → JSONL 落盘 |

**关键 gap（G3）现状：**
1. ~~没有能调 LLM 并返回合法 `AgentResult` 的 agent runner~~ → **已建（Phase 8A `run_llm_agent` 11 步管线）**
2. ~~没有 World 1 → World 2 的 adapter~~ → **已建（`llm_output_to_tool_result` / `processed_signals_to_tool_result`）**
3. Phase 4M "内存"模块 51 个类全是 in-memory，无磁盘持久化 → **绕过**（改用 `data/agent_outputs/<agent_id>/<date>.jsonl` 持久化，不复用 4M 内存模型）
4. Agent 间无消息总线，hand-off 靠 `session_state` dict → **仍未建**（PM 层 Phase 8C 之前不需要）

**好消息**：`EvidenceRef` / `EvidenceStore` / `validate_agent_result` / `DebateReport` / `DecisionPacket` / `approved_for_execution` 硬锁全部已有且已被 Phase 8A 接通使用，直接复用。

---

## 三、项目核心目标与 Agent 架构（2026-06-19 确认）

### 3.1 项目定位重申

**AI Investment OS 的核心目标是 AI Fund 工作流系统**：一个多 agent 协作的投资研究与决策支持系统，模拟基金工作流，每个环节有专属 agent 负责，PM agent 层消费所有基础 agent 输出进行决策。UI 是"AI PM 向人类用户汇报"的 dashboard，不是人工驾驶的研究工具。

这个定位在过去数个 phase 中发生了漂移（向"人工仪表盘"方向），已于 2026-06-19 架构讨论中校正。所有后续 phase 以此为准。

### 3.2 Agent Map（已确认）

> 状态图例：✅ 已实现并在产 · ⏳ 下一个（STEP 0）· 📋 计划。Foundation Agent 规范 roster 共 11 个；行 1–5 已在产，行 6 为下一个。

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 DATA LAYER
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Raw Sources:
  yfinance / Finnhub / FRED（已接入）
  Quiver Quantitative Hobbyist $25/月（✅ 已接入 Phase 8B-0）→ 暗池 / 国会交易 / 内幕交易 / 对冲基金持仓
  Massive Options Starter $29/月（✅ 已接入 Phase 8B-0；曾用名 Polygon.io）→ 期权链原始数据（Greeks / IV / OI / 成交量）

Processed Signals（代码，非 LLM）:
  macro_regime.classify_regime()    → regime label + indicators（+ vote 字段）
  market_internals                  → breadth / fragility signals
  relative_strength                 → multi-window RS scores
  opportunity_ranker                → 3-horizon opportunity scores
  rotation                          → sector rotation ring + offense/defense reading
  theme_transmission                → wave order + cluster
  valuation_router + anchor_cache   → valuation anchors + confidence
  quiver_fetcher（✅）              → 暗池净流向 / 国会交易情绪 / 机构持仓变化
  massive_options_fetcher（✅）     → 期权链 OI / Greeks / IV（原始数据 → Phase 2E OptionChainSnapshot）
  gex_dex（✅，原称 gex_calculator）→ GEX / DEX / Call wall / Put wall / Gamma Squeeze 概率
                                      （从 Massive 原始数据确定性计算，非 LLM；零 lib.reliability 导入、绝不抛错）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 FOUNDATION AGENT LAYER
 （各自独立，输出 AgentOutput，evidence-backed）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【市场环境类】

MacroRegimeAgent ✅ 已实现（a19b862）
  Code:  regime label / risk-on-off / yield curve（已有 classify_regime）+ 三置信度 + 投票计数
  LLM:   当前 regime 组合对三个时间维度的交易含义
         → 具体 sector 偏向、入场条件、失效触发器
  复用:  MacroHorizonImpact schema（已有）

MarketStructureAgent ✅ 已实现（8792343）
  Code:  fragility level / breadth trend / tighten 状态（从 Cockpit Step 4 注入，不二次计算）
         short=coverage×clarity（5 核心组件，永久脚手架组件排除）/ mid=连续恶化天数饱和曲线
         （vintage_mismatch → cap 0.1 非 floor）/ long=0.0；signal_basis 三值分类器
  LLM:   这个结构组合对本周可操作性的含义 → 哪类标的应回避，哪类有结构性保护
         tighten-only 禁令写入 prompt（绝不 bullish/加仓/放松，绝不翻转 regime）

MoneyFlowAgent ✅ 已实现（760f356） ← Quiver + Massive 双数据源
  数据来源（两个独立数据源，各司其职）:
    Quiver Off-Exchange → 暗池净流向（3天-3周有效，机构建仓/出货方向）
    Massive Options     → 期权链原始数据 → gex_dex 计算以下指标

  Code 层确定性计算（非 LLM，由 gex_dex 处理）:
    GEX = Σ(Gamma × OI × 合约乘数 × 标的价格²)，call 正 put 负
      正 GEX → dealer long gamma → 价格被压制在区间，波动率压缩
      负 GEX → dealer short gamma → 趋势被放大，波动率扩张
    DEX = Σ(Delta × OI × 合约乘数 × 标的价格)，call 正 put 负
      正 DEX → dealer 持多头对冲，市场有天然买盘支撑
      负 DEX → dealer 持空头对冲，市场失去买盘支撑
    DEX 变化率（日环比）: 变化方向比绝对值更重要（prior_result 经 11 字段 frozenset 校验重建）
    Call wall / Put wall: OI 最集中的行权价（按到期日分层：本周/下周/月度）
    GammaSqueezeMonitor（A+B+C 三条件）:
      A 负 GEX + B 价格接近大量 call OI（put wall 上方 3% 内）+ C DEX 快速转正
      Squeeze 概率评级: 0–1 低 / 2 中 / 3 高
      估算上行/下行空间: 基于 net GEX / 流通市值（确定性计算）
    暗池净流向（连续 N 日方向）: 单日噪音大，连续3-5天方向才有效

  三置信度（代码先算、落为证据）: short=信号共振率（signals_agree/3）/
    mid=强度×方向有效（strong 1.0 / moderate 0.6 / weak 0.3）/ long=0.0

  LLM synthesis:
    输入：以上所有代码已算好的信号结构体（数字进 evidence_refs，不进 prompt）
    输出必须包含:
      当前 GEX 环境（正/负）及对波动率的含义
      Key levels（call wall / put wall），来自 evidence_refs
      暗池方向与 GEX 是否共振或背离
      Gamma Squeeze 概率及方向（如评级为中/高）
      对 ShortTermPM 的具体操作含义，例如:
        "当前正 GEX 环境，暗池连续净买入，适合在 put wall 附近
         做多，靠近 call wall 减仓，put wall 突破则止损。
         若 DEX 明日转负则本判断失效。"
      neutral GEX 也必须给出期权结构策略（绝不"观望即可"）
    输出禁止: 泛论；直接在 judgment 中出现具体价格数字

  valid_until: 当日收盘（GEX/DEX 是当日指标，次日必须重算）

  适用标的（按用途）:
    宏观环境判断 → SPY / QQQ 的 GEX/DEX
    主题/板块判断 → SMH / XLF / XLE 等行业 ETF 的 GEX
    个股 → 高 OI 标的（NVDA / AAPL / TSLA 等）

  消费层:
    主要 → ShortTermPM（GEX 区间策略 + gamma squeeze 机会）
    辅助 → MidTermPM（暗池净流向的中期趋势方向）
    不供 → LongTermPM（当日信号对长期判断无意义）

  信号组合用法（供 ShortTermPM 仲裁参考）:
    正 GEX + 正 DEX + 暗池净买入 → 最强做多信号，put wall 附近重仓
    负 GEX + 负 DEX + 暗池净卖出 → 最强回避信号，不做多
    GEX/DEX 与暗池方向矛盾       → 观望，等信号统一
    负 GEX + DEX 快速转正        → Gamma Squeeze 预警，监控升级

【机会发现类】

SectorRotationAgent ✅ 已实现（fbf0cc4）
  Code:  sector 轮动位置 / 入场窗口（已有 rotation）+ 主题动量（theme_baskets）
         + 传导波次（theme_transmission）+ 完整攻守 O/D reading（注入）
         short=coverage×stage_confirmed率 / mid=coverage×动量分散×wave清晰度 / long=0.0
  LLM:   哪个 sector 处于 Wave 入场点，哪个已过热 → 下周可操作的 sector 优先级排序
         signal_basis 三值含 no_clear_leadership（中性/等待，禁止方向性解读）

ThemeIntelligenceAgent ✅ 已实现（5ecfb78）
  Code:  constituent_rs（成分股多窗口超额，theme_baskets 计算时存下）×
         theme_transmission 种子角色（leader/2nd-derivative/supplier/laggard）
         short=coverage×role_resolution（全成分股诚实分母）/
         mid=coverage×asymmetry_strength（wave{1,2} + rotating_in，""排除）/
         long=0.0；signal_basis 三值（no_role_signal=中性/等待，绝非看空）
  LLM:   哪个 Wave 有最大非对称机会；具体 cluster 内哪类公司最先受益；
         live RS 排名与种子角色是否背离（kind=leader但RS落后=恶化信号）

CandidateScreeningAgent ⏳ 下一个（STEP 0）
  Code:  opportunity_ranker 评分（已有）+ candidate_generator / signal_engine
  LLM:   从候选池筛出值得深研的标的 → 优先级排序 + 筛选理由

【个股深研类】

StockResearchAgent 📋 计划
  Code:  thesis 健康度 / 可证伪条款当前状态（已有 thesis_monitor）
  LLM:   当前 thesis 哪条论据最脆弱 → 具体可观察验证条件

ValuationDebateAgent 📋 计划（Phase 8D）
  Code:  reverse DCF 计算 / anchor 分歧度（已有 valuation_router）+ anchor_migration
  LLM:   多空立场隔离对抗 → 裁判综合 → endorsed range + 核心争议点
  复用:  DebateReport schema（已有）

TechnicalEntryAgent 📋 计划
  Code:  入场条件满足度 / 止损锚（已有 order_advisor）+ GEX walls（见§5.9）
  LLM:   当前技术结构对入场时机的具体判断 → 入场触发条件 + 失效条件

SectorResearchAgent 📋 计划
  Code:  sector 内个股分化指标
  LLM:   sector 内结构性机会驱动因素 → 分化背后逻辑，哪条业务线最先兑现
  位置:  在 StockResearchAgent 之上聚合，不是独立数据源

【风险控制类】

RiskOverlayAgent 📋 计划
  Code:  各 agent confidence 加权 / 集中度
  LLM:   当前判断组合中哪个不确定性最高 → 对哪个 PM 输出打折，理由是什么
  约束:  不产生买卖判断，只产生修正系数

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 PM LAYER（消费基础 Agent output，核心职责是冲突仲裁）  📋 计划（Phase 8C）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ShortTermPM（1–4 周）
  消费: MoneyFlowAgent + MarketStructureAgent + TechnicalEntryAgent
  仲裁: 资金方向 vs 技术结构不一致时谁优先
  输出: 本周可操作入场/回避建议 + 具体 ticker + 条件

MidTermPM（1–3 月）
  消费: SectorRotationAgent + ThemeIntelligenceAgent + ValuationDebateAgent
  仲裁: 轮动窗口 vs 估值安全边际不一致时的权重
  输出: 本月结构性机会清单 + 建仓条件

LongTermPM（6–18 月）
  消费: MacroRegimeAgent + StockResearchAgent + SectorResearchAgent
  仲裁: 宏观周期 vs thesis 成立性的优先级
  输出: 长期持有逻辑完整性评估

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 MASTER PM AGENT  📋 计划（Phase 8C）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MasterPM
  消费: 三个子 PM output + RiskOverlayAgent
  权重: 基于各子 PM 历史准确率动态调整
        （依赖 Phase 7D Block B 快照审计轨积累）
  输出: 最终 DecisionPacket（复用已有 schema）
        → UI dashboard 顶层展示 evidence chain；绝不出下单指令

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 UI LAYER（AI PM 向人类用户汇报的 dashboard）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  每个 AgentOutput 可展开查看 evidence_refs
  每个 PM judgment 显示消费了哪些 agent + 冲突如何仲裁
  MasterPM DecisionPacket 顶层展示
  Judgment Console（人工确认入口，Phase 9）
  ——仅供审阅 / review-only，永不下单
  当前：Investment Cockpit 已附加式接入 5 个 foundation agent 钩子（macro_regime_agent_output /
        money_flow_agent_output / market_structure_agent_output / sector_rotation_agent_output /
        theme_intelligence_agent_output），各为 key-gated、fail-closed、复用已算信号、绝不中断刷新
```

### 3.3 实施策略（已确认）

**Option A 为主，局部 Option B：**

* **复用**：`EvidenceRef` / `EvidenceStore` / `validate_agent_result` / `DebateReport` / `DecisionPacket` / `approved_for_execution` 硬锁
* **重新定义**：统一 `AgentOutput` dataclass（比 World 2 的 `AgentResult` 更精简，加入 `valid_until` / `horizon` / `judgment` 字段）
* **放弃**：Phase 4M 的 in-memory 内存模型，用新的 JSONL 持久化替代（`data/agent_outputs/<agent_id>/<date>.jsonl`）
* **新建**：World 1 → World 2 的 adapter（live 分析 → `ToolResult` evidence）；LLM agent runner（调 LLM 并返回合法 `AgentOutput`）

> 上述四条均已由 Phase 8A 落地并经两轮 Codex 审查通过。

---

## 四、当前位置与下一步

> **Phase 8B ThemeIntelligenceAgent ✅ 完成（`5ecfb7875`，docs `6cc972e9a`）→ 下一步：CandidateScreeningAgent（STEP 0 先行）**

已在产的 5 个 foundation agent：MacroRegimeAgent · MoneyFlowAgent · MarketStructureAgent · SectorRotationAgent · ThemeIntelligenceAgent。其后顺序：CandidateScreeningAgent → StockResearchAgent → TechnicalEntryAgent → SectorResearchAgent → RiskOverlayAgent（ValuationDebateAgent 归 Phase 8D）。

### 4.1 为什么 Phase 7D Block A 先于 Phase 8 的其余部分

MasterPM 的子 PM 历史权重调整，依赖能系统性查询快照审计轨的机制。没有它，Phase 8 的 agent 输出进了系统却无法被复盘——判断无法被验证，LLM 兑现率无从统计。**Block A 是 Phase 8 能自证清白的地基，已先行完成（`a93909f` / merge `5a57850`）。** 真正吃 agent 输出做校准的 **Block B 推迟到 Phase 8 输出在快照中积累之后**（见§5.1）。

### 4.2 Phase 7D 的范围拆分

**Block A（✅ 已完成）**：用已有的 `data/snapshots/*.jsonl`，做复盘查询接口——"Actionable Now 后续真走出机会了多少 / Avoid Chasing 的误报率"。只读、无信号引擎、无排序、无联网、fail-closed；双语审计回顾页 pages/11。收口时快照轨有 9 个文件 / 180 条 ticker 记录 / 43 个 ticker。

**Block B（依赖 Phase 8 输出积累）**：阈值自动校准、LLM judgment 兑现率统计、子 PM 历史权重计算。Phase 8 完成后回头做。

---

## 五、未来阶段（已入账本）

这些阶段是同一条价值链的不同环节（✅ 已完成 / 🔄 进行中 / 📋 计划）：

* ✅ **7D Block A** — 快照审计查询接口（自我校准前提）
* ✅ **Phase 8A** — Agent 框架地基（AgentOutput schema + agent runner + World1→World2 adapter）
* ✅ **Phase 8B-0** — 新数据源接入基础层（Quiver + Massive + gex_dex）
* 🔄 **Phase 8B** — 基础 Agent 实现（已在产 MacroRegime / MoneyFlow / MarketStructure / SectorRotation / ThemeIntelligence；下一个 CandidateScreening）
* 📋 **Phase 8C** — PM 层实现（ShortTermPM → MidTermPM → LongTermPM → MasterPM）
* 📋 **Phase 8D** — ValuationDebateAgent（证据基础设施 + 反向 DCF + 对抗辩论）
* 📋 **Phase 9** — Judgment Console（人工确认入口，LLM 提议人裁决；下游 gating 政策待定）
* 📋 **7D Block B** — 阈值自动校准 + 子 PM 历史权重（需要 Phase 8 输出积累）
* 📋 **Phase 6D** — 持有侧复盘（持仓逻辑健康度追踪）
* 📋 **另类数据接入** — 期权链/暗池叠加进脆弱度复合指标（MoneyFlowAgent 已建成，进入评估）

### 5.1 Phase 7D — 反馈环 / 推荐质量复盘

| | |
|---|---|
| **它是什么** | 把"系统说得对不对"从人工盘感对照，变成制度化的自动统计。Block A（✅ 已完成）是查询接口，Block B（📋 计划）是自动校准。 |
| **为什么做** | MasterPM 的子 PM 权重调整需要历史准确率数据。没有这个机制，多 agent 系统的自我改进能力为零。 |
| **做到什么算完成（Block A）** | ✅ 用快照审计轨回头检验：哪些"Actionable Now"后续真走出机会、哪些"Avoid Chasing"真避开下跌；脆弱度警报的领先性和误报率随时间演变；接口供 Block B 和 MasterPM 消费。 |
| **绝不能变成什么** | **绝不用滚动重算**——复盘必须审计"系统当时基于当时的代码和数据说了什么"。信号轨/审计轨分离在这里是成败关键。 |
| **谁来用它** | MasterPM 权重调整；Judgment Console 的 LLM 判断兑现率统计；阈值校准。 |

### 5.2 Phase 8A — Agent 框架地基 ✅ 已完成（`8ca5051` / merge `f6a0f74`）

| | |
|---|---|
| **它是什么** | 建立 multi-agent 系统的连接组织：统一 `AgentOutput` schema、LLM agent runner、World1→World2 adapter、JSONL 持久化层。 |
| **为什么做** | World 2 的骨架完整但休眠，缺的是能调 LLM 并返回合法 `AgentOutput` 的 runner，以及把 live 分析转化为 evidence 的 adapter。这是所有后续 agent 的共同前提。 |
| **做到什么算完成** | ✅ ① `AgentOutput` dataclass 定义并通过 Codex 审查；② `run_llm_agent` 能调 LLM、解析结构化输出、写入 `EvidenceStore`、返回合法 `AgentOutput`；③ adapter 能把 `llm_orchestrator` 现有输出转化为 `ToolResult`；④ JSONL 持久化写入/读取验证；⑤ 第一个端到端 smoke test：`MacroRegimeAgent` 跑通并产出合法 `AgentOutput`。两轮 Codex 审查（REJECT → APPROVE），§8A.1–§8A.11 11/11（后随 repair-layer 升至 15/15）。 |
| **绝不能变成什么** | 不是新的 `llm_orchestrator`（不替换，是补充层）；不跳过 Codex 审查；schema 不允许 agent 自定义覆盖。所有 `lib.reliability` 导入惰性、绝不触发 52 模块 eager `__init__`。 |
| **谁来用它** | 所有后续 agent 实现的共同基础。 |

### 5.3 Phase 8B — 基础 Agent 实现（逐 agent 验证）

| | |
|---|---|
| **它是什么** | 按 Agent Map 逐个实现基础 agent，每个 agent 独立验证后再实现下一个。**第一步先完成数据接入基础层（Phase 8B-0），再实现 agent。** |
| **为什么做** | 单 agent 先行、逐项 gate——和"单章节先行"是同一条纪律。避免多个 agent 同时实现、发现架构问题时返工成本巨大。 |
| **做到什么算完成** | 每个 agent：① Code 层 processed signals 正确；② LLM synthesis prompt 输出具体可操作（含 ticker/时间窗口/失效条件）；③ `evidence_refs` 非空且可追溯；④ `valid_until` 正确设置；⑤ Codex mutation probe 验判别性。 |
| **绝不能变成什么** | Agent 不复述代码已算出的指标（那是 reporting，不是 synthesis）；LLM prompt 不允许输出泛论；`evidence_refs` 不允许为空。 |

**Phase 8B-0 — 新数据源接入基础层 ✅ 已完成（`af3de6b` / merge `69d7c9f`）**

> 实际落地的模块名/测试名与下方初始设计略有出入：计算器最终命名 `lib/gex_dex.py`（非 `gex_calculator`）；测试为 `scripts/test_phase_8b0_quiver.py` / `test_phase_8b0_massive.py` / `test_phase_8b0_gex_dex.py`（非 `test_data_layer_*`）。期权链映射进既有 Phase 2E `OptionChainSnapshot`/`OptionContractSnapshot`（`source="massive"`）。24 tests（Quiver 6 + Massive 5 + GEX/DEX 13），三轮 Codex 审查通过。以下为原始设计意图，保留备查：

在实现任何 agent 之前，必须先完成两个新数据源的 fetcher + processed signals：

    Quiver Quantitative 接入（Hobbyist $25/月）:
      lib/quiver_fetcher.py
        fetch_dark_pool(ticker, date_range) → 暗池净流向 JSONL
        fetch_congress_trades(lookback_days) → 国会交易记录
        fetch_insider_trades(ticker)         → 内幕交易记录
        fetch_hedge_fund_positions(ticker)   → 对冲基金持仓变化
      Processed signal: compute_dark_pool_signal(ticker, n_days) → 方向 + 强度
      降级守卫: API 不可用时 fail-closed 返回空 + insufficient_data，不静默

    Massive Options 接入（Starter $29/月，曾用名 Polygon.io）:
      lib/massive_options_fetcher.py
        fetch_options_chain(ticker, expiry_filter) → OI / Volume / Greeks / IV
      lib/gex_dex.py（纯确定性计算，无网络调用，零 lib.reliability 导入）:
        compute_gex_dex(chain, expiry_filter, prior_result=None)
          → GEX/DEX 求和 + 正负判断 + 变化率（prior_result 提供前日 DEX）
        find_walls(chain, expiry="this_week") → call_wall, put_wall 价位
        gamma squeeze monitor（A+B+C 三条件）:
          → {probability: low|mid|high, direction, estimated_move_pct, trigger_conditions}
      降级守卫: API 不可用时返回降级快照；免费档无 Greeks/OI → gamma=None + greeks_unavailable

    测试要求（实际）:
      scripts/test_phase_8b0_quiver.py    — Quiver fetcher + dark_pool signal
      scripts/test_phase_8b0_massive.py   — Massive fetcher + 坏合约跳过判别
      scripts/test_phase_8b0_gex_dex.py   — gex_dex 全函数 unit test，不依赖网络
      mutation probe: GEX 正负判断翻转 / prior_result DEX 趋势 时测试必须 RED

**Phase 8B 实现顺序（8B-0 完成后）:**

    MacroRegimeAgent      ✅ 已完成（a19b862，从 Phase 8A smoke test 升级为生产实现）
    MoneyFlowAgent        ✅ 已完成（760f356，消费 Quiver + Massive 两个数据源）
    MarketStructureAgent  ✅ 已完成（8792343）
    SectorRotationAgent   ✅ 已完成（fbf0cc4）
    ThemeIntelligenceAgent ✅ 已完成（5ecfb78）
    CandidateScreeningAgent  ⏳ 下一个（STEP 0）
    StockResearchAgent       📋
    TechnicalEntryAgent      📋（消费 GEX walls 作为动态支撑阻力，见§5.9）
    SectorResearchAgent      📋
    RiskOverlayAgent         📋
    （ValuationDebateAgent 归入 Phase 8D）

### 5.4 Phase 8C — PM 层实现

| | |
|---|---|
| **它是什么** | ShortTermPM / MidTermPM / LongTermPM / MasterPM 的实现。PM 的核心职责是**冲突仲裁**，不是汇总。 |
| **为什么做** | PM layer 是整个 AI Fund 工作流的决策收口。没有 PM layer，基础 agent 的输出是散的，无法形成可审核的投资建议。 |
| **做到什么算完成** | 每个 PM：① 正确消费指定基础 agent 的 `AgentOutput`；② 有明确的冲突仲裁逻辑（不是加权平均，是有立场的解释）；③ 输出写入 `DecisionPacket`；④ MasterPM 能读取三线 PM 的 output 并综合。Block B 的历史权重调整是后期增强，不阻塞 Phase 8C。 |
| **绝不能变成什么** | PM 不直接调 raw data；PM 的仲裁结论必须 evidence-backed（引用基础 agent 的 `AgentOutput` 作为 evidence）；`approved_for_execution` 永远 False。 |
| **前置依赖** | Phase 8B roster 足够填充（至少各 PM 消费的基础 agent 已在产）。 |

### 5.5 Phase 8D — ValuationDebateAgent（证据基础设施）

（原 Phase 8 设计，调整为 8B 顺序之后的一环，详细设计保留）

| | |
|---|---|
| **它是什么** | 证据包基础设施 + 估值辩论 agent。填上 v2.4 诊断卡留的两个占位（反向 DCF 锚位、叙事型 what-would-change）。 |
| **做到什么算完成** | 反向 DCF 确定性计算 + 多空立场隔离对抗调用 + 裁判综合 → endorsed range + 可证伪结论写回 thesis_monitor。 |
| **绝不能变成什么** | 辩论不碰原始数字、不产生新数值；禁止概率剧场（不输出"衰退概率 60%"这类伪数字，只输出条件式情景 + 可观察触发器）。 |
| **前置依赖** | 估值基建 + Phase 8B 个股研究组。 |

### 5.6 Phase 9 — Judgment Console（第一形态）

| | |
|---|---|
| **它是什么** | 把系统里所有需要主观判断的地方（agent judgment 采纳、辩论结论、thesis 健康度……）收口到一处。每个判断字段配"LLM 建议"按钮 + 人工确认/覆写。 |
| **节奏** | 人在环 Console（人裁决每一项）→ 用 7D/6D 验证 LLM 判断兑现率 → 证明够准了再逐步提高自动化程度。**下游 gating 政策（自动化到什么程度）仍是未定的显式架构决策，不在本阶段锁死。** |
| **不变量 ①（传递性）** | 下游只读"人已确认"的判断。 |
| **不变量 ②（可见性）** | 任何下游若依赖未确认判断，UI 必须显式提示。 |
| **范围（当前路线图所支持的层级）** | 人工复核/确认、判断来源留痕（provenance）、覆写能力、审计轨。 |
| **前置依赖** | Phase 8B/8C 完成（有 agent / PM output 可供确认）+ 7D/6D 输出积累。 |

### 5.7 Phase 6D — 监控与持有侧复盘

（设计不变，排序较后）持有侧逻辑健康度追踪：区分"价格噪音"和"逻辑破坏"，跟踪持仓 thesis 的可证伪条款当前状态。按路线图既定顺序，排在 Phase 8 / 9 主链之后。

### 5.8 数据源决策（2026-06-19 确认 · 2026-06-20 选型 · 2026-06-24 状态更新）

**已接入数据源：**

    已接入: yfinance / Finnhub / FRED / Alpha Vantage（部分）
    已接入（Phase 8B-0 落地）:
      Quiver Quantitative Hobbyist $25/月
        → Off-Exchange（暗池）/ 国会交易 / 内幕交易 / 对冲基金持仓
        → 供 MoneyFlowAgent 暗池信号（+ 未来 MacroRegimeAgent 情绪信号）
      Massive Options Starter $29/月（曾用名 Polygon.io）
        → 期权链 OI / Greeks / IV（Real-time Greeks and IV + Daily OI）
        → 供 gex_dex 计算 GEX/DEX/walls → MoneyFlowAgent（+ 未来 TechnicalEntryAgent）
    排除:
      Unusual Whales API → $125/月起，大单扫单功能对 GEX 策略非必须，性价比不合理

**数据源分工原则：**

    Quiver 负责"谁在买/卖"（机构行为方向）
    Massive 负责"dealer 被迫怎么对冲"（GEX/DEX 结构）
    两者互补，不重叠，MoneyFlowAgent 同时消费两者做 synthesis

**期权数据使用原则（防漂移）：**

    期权链原始数据（OI/Greeks/IV）由代码确定性计算 GEX/DEX/walls
    LLM 只消费计算结果，不接触原始数字
    GEX/DEX 是当日信号，valid_until = 当日收盘，次日强制重算
    Gamma Squeeze 概率是代码算出的分级（低/中/高），LLM 解读含义，不自行估算概率

**接入状态与待确认项（实盘前）：**

    Massive 免费档无 Greeks/OI → 实时 GEX/DEX 需 Starter 档（~$29/月）；未升级前优雅降级（gamma=None + greeks_unavailable）
    Quiver prev_close 字段名仍待实盘 API 确认（解析多候选键、缺失时 fail-closed 50/50 降级）

**环境变量（与 .env.example / 运行时对齐）：**

    ANTHROPIC_API_KEY  — Claude（研究工作流 + Foundation Agents）；agent 必需
    FINNHUB_API_KEY    — 财报日历 + 新闻；强烈建议
    FRED_API_KEY       — 利率/信用/广义美元/流动性宏观；可选（缺失回退 fixture）
    QUIVER_API_KEY     — 暗池/国会/内部人/机构；可选
    MASSIVE_API_KEY    — 期权链 Greeks/IV/OI → GEX/DEX；可选（曾用名 POLYGON_API_KEY）
    注: .env.example 当前未列 FRED_API_KEY（运行时 macro_data.py 实际读取）——待补；
        lib/data_fetcher.py 仍存 POLYGON_API_KEY 价格回退死代码（未被调用），待清理。

### 5.9 TechnicalEntryAgent 扩展（GEX walls 作为动态支撑阻力）

TechnicalEntryAgent（📋 计划）在原有技术结构判断基础上，增加 GEX walls 作为输入：

    新增 Code 层输入（来自 gex_dex）:
      call_wall / put_wall 价位（当周到期）
      当前价格距 walls 的距离百分比
      GEX 环境（正/负，影响 wall 强度）

    对 LLM synthesis 的影响:
      正 GEX 环境下 walls 更可靠（dealer 对冲行为更强）
      负 GEX 环境下 walls 可能被突破（dealer 顺势加仓）
      入场条件需结合 GEX 环境调整置信度

---

## 六、痛点 — 机制对应（贯穿设计的锚）

| 痛点 | 对应机制 | 相关阶段 |
|---|---|---|
| **MU**：被价格止损洗出、错过主升 | 区分"价格噪音"和"逻辑破坏" | thesis monitor、6D、StockResearchAgent |
| **DELL**：看对了却没买、缺入场触发器 | 状态 / 触发器分级 | 7A、TechnicalEntryAgent |
| **SNOW**：回调中平仓过早 | 估值锚 + 周期分层 + 正确同业匹配 | ValuationDebateAgent、Anchor Intelligence v2 |

---

## 七、踩过的坑 / 决策范例（供未来会话参考）

1. **README 回退事故**：一次 README 编辑在旧基底上做，误删 5 条不变量原则行 + 整段 roadmap。处置：以权威 README 为基底，只 port 新原则，Codex 加回归守卫。教训：任何"简化"README 的操作都要 diff 全文、逐行核对。

2. **实现 prompt 给了错误机制**：ITEM 1 prompt 建议用 `earnings_reactions=` 喂入，Claude Code 查了代码发现那条路径会改计算，正确否决并用重放闭包替代。教训：实现 prompt 里的"具体机制建议"要么先只读勘察核实，要么标"建议非强制、以代码事实为准"。

3. **厂商 token 守卫**：ITEM 1 第一版 `raise RuntimeError("finnhub_unavailable")` 引入小写 `finnhub` 字面量，触发真实的 5h 厂商 token 守卫。修正为捕获重抛原始异常。

4. **Thesis Ingestion 目标漂移**：跨会话时"外部作者研报卡"被误读成"持仓监控卡"。根因：迁移总结把痛点机制放最显眼处。处置：每个条目显式带"它是什么/它不是什么"，schema 层用 `provenance` 字段区分。

5. **Phase 7C 语义演进**：原始规划用"tier_1/2/3"表达受益层级，实施时发现与 `rotation.py` 的 `tier` 命名冲突。最终改用 `transmission_order`（Wave 1–4）+ `transmission_cluster`。

6. **Phase 0–5 地基扫描价值**：Phase 7C 实施前做了 `phase5_theme_intelligence.py` 专项勘察，发现可复用 schema 直接复用。从此确立每个新 phase 开始前必须扫描 Phase 0–5 地基为项目纪律。

7. **项目目标漂移（2026-06-19 校正）**：过去数个 phase 向"人工驾驶仪表盘"方向漂移，远离了"AI Fund 多 agent 工作流"的原始目标。根因：每个 phase 的合理工程决策积累（数值防火墙 → 过度压缩 LLM 判断空间；数据质量优先 → 建了数据基础设施而非 agent 基础设施）。处置：本次架构对齐重申项目目标，更新 §0.5 agent 架构纪律，调整后续 phase 路径。**关键结论：World 2 骨架完整，缺的是连接组织，不是从零重建。**

8. **Agent 分工原则（2026-06-19 确认）**：Agent 的价值不在于复述 processed data，而在于跨维度综合后给出对具体交易的可操作含义。代码负责"是什么"，LLM 负责"对交易意味着什么"。泛论（"市场偏弱，谨慎操作"）不是合格的 agent output。

9. **数据源选型（2026-06-20）**：评估了 Unusual Whales API（$125/月）、Quiver Quantitative（$25/月）、Massive Options（$29/月）三个选项。结论：Unusual Whales 的大单扫单功能对 GEX 策略非必须，$125 性价比不合理，排除。选 Quiver（暗池/机构行为）+ Massive（期权链 Greeks/OI）组合，$54/月覆盖 MoneyFlowAgent 所需的全部数据。

10. **期权流 vs 订单流区分（2026-06-20）**：期权流（Options Flow）= 期权市场大单方向押注，1天-1周有效；暗池净流向（Dark Pool）= 机构建仓/出货方向，3天-3周有效；GEX/DEX = dealer 被迫对冲产生的结构性价格约束，当日有效。三者互补，不重叠，供 ShortTermPM 的不同时间窗口消费。

11. **LLM schema 遵守问题（2026-06-21）**：MacroRegimeAgent 上线调试时发现 LLM 持续把 `findings[]` 里的字段放到顶层，导致 `extra="forbid"` Pydantic 验证失败。单纯靠 prompt 示例不够稳定。最终解法：在 `agent_runner.py` 加 `_repair_llm_response()` 结构修复层，在 `parse_and_validate_agent_result` 之前自动把扁平结构转换成正确的 `AgentResult` 格式。教训：凡是依赖 LLM 遵守复杂 JSON schema 的地方，都要加防御性 repair layer。**每个新 agent 直接复用此层。**

12. **Streamlit secrets 不稳定（2026-06-21）**：`_has_llm_api_key()` 先读 `os.environ` 再读 `st.secrets`，但 Streamlit rerun 时 `st.secrets` 并不总是可用。解法：启动时用 `set -a && source .env && set +a && streamlit run app.py` 把 `.env` export 到环境变量，确保 key 永远在 `os.environ` 里，不依赖 `st.secrets`。

13. **模块热重载不可靠（2026-06-21）**：Cockpit hook 里的懒加载 import（`try` 块内动态 `import`）不会被 Streamlit 热重载更新。修改代码后必须完整重启 Streamlit 进程，不能只用 rerun 按钮。

14. **附加式、key-gated、fail-closed 是把 agent 接进活页面的安全方式（Phase 8B 反复验证）**：四个 Cockpit agent 钩子都遵守同一模式——复用已算好的确定性信号（绝不二次 fetch/compute）、`_has_llm_api_key()` 门控、各自 try/except、只写自己那个 `*_agent_output` session key。一个无 key 或失败的 agent 是干净的 no-op，绝不中断刷新。

15. **注入而非重算，杜绝 vintage 分歧（MarketStructureAgent）**：脆弱度读数从 Cockpit Step 4 注入，agent 绝不自己调 `compute_market_fragility`——避免 banner 与 agent 之间出现二次计算与 vintage 漂移。同理 SectorRotationAgent 复用 Step 2 的 themes + 注入的 O/D reading。

16. **cap-vs-floor 边界要测出判别性（MarketStructureAgent）**：`mid_confidence` 在 `vintage_mismatch` 时应是 `min(interpolated, 0.1)` 的**上限**而非下限——一个平淡的 normal 轨仍应得 0.0。Codex 修复轮专门把 floor 改 cap，并以 6a–6e 边界用例覆盖。

17. **中性状态绝不可读成方向（SectorRotationAgent）**：`signal_basis` 三值含 `no_clear_leadership`（数据齐但既无确认 stage 也无清晰 wave）——这是"中性/等待"，prompt 显式禁止把它框成 bullish/bearish。

---

*Numbers by deterministic code · Evidence-bound judgment by LLM, confirmed by human · Review-only by design · AI Fund workflow, not a dashboard*
