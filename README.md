<div align="center">

# 📈 AI Investment OS — Multi-Agent Equity Research & Decision Support
### 美股多 Agent 投研与决策支持系统

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.35%2B-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Anthropic](https://img.shields.io/badge/Claude-API-8B5CF6?logo=anthropic&logoColor=white)](https://www.anthropic.com/)
[![Tests](https://img.shields.io/badge/Reliability_Tests-1000%2B_assertions-1c7a3d)](#-可靠性工程--reliability-engineering)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![NYSE · NASDAQ](https://img.shields.io/badge/Market-NYSE%20%C2%B7%20NASDAQ-0052CC)](https://www.nyse.com/)

</div>

---

**EN** · A personal investment operating system for US equities, evolved from a multi-agent research workflow into a full decision-support stack: opportunity ranking, dual-track signal engine, market-internals fragility monitoring, type-routed valuation with a structured analyst-anchor pool and an append-only anchor history, entry strategy, and thesis monitoring — all surfaced through an Investment Cockpit. Deterministic code computes every number; Claude makes evidence-bound, human-confirmed judgment calls on top. **Review-only by design: the system never places orders.**

**中** · 一个面向美股的个人投资操作系统。由最初的多 Agent 研究工作流，演进为完整的决策支持栈：机会排序、双轨信号引擎、市场内部结构（脆弱度）监控、公司分型估值（结构化分析师锚池 + 只追加估值锚历史）、入场策略与持仓 thesis 监控，统一汇聚于「投研中枢 / Investment Cockpit」。**所有数字由确定性代码计算，LLM 在证据约束下做判断建议、由人确认；系统设计上仅供审阅（review-only），永不下单。**

> ⚠️ **风险提示 / Disclaimer** · 本系统输出内容仅供学习与研究参考，不构成任何投资建议。All outputs are for research and educational purposes only and do not constitute investment advice.

---

## 🧭 设计原则 / Design Principles

这些原则在多个开发阶段中沉淀，并由测试不变量强制执行：

| 原则 | 含义 |
|---|---|
| **数字交给代码，判断在证据约束下可由 LLM 建议** | 所有评分/估值/信号/阈值/技术指标/市场数据为确定性 Python（数值防火墙）；LLM 不做**不可追溯的数值判断**，但**可在证据约束下做判断建议**（valuation_role 升降、thesis 是否受削、处境综合），每条建议须引用证据、无证据标 unknown，并经显式人类确认（默认人工主控、可覆写、来源留痕） |
| **Review-only** | `approved_for_execution` 永远为 `False`；无券商接入；输出是研究队列，不是买入清单 |
| **Tighten-only（只收紧）** | 脆弱度层只收紧短线入场门槛、只做注释；永不翻转宏观 regime、永不放松任何门槛 |
| **单一数据 vintage** | 一次刷新内基准/标的/滚动序列同源同龄；跨源由 `data_vintage` / `vintage_mismatch` / `rs_stale` 守卫，静默过期结构性不可能 |
| **信号轨 / 审计轨分离** | 滚动重算（缓存行情的纯函数）回答「市场做了什么」并驱动迟滞；每日快照记录「系统当天说了什么」专司复盘审计 |
| **Parity 验证纪律** | 测试驱动真实刷新路径，断言 UI 渲染与快照 `_meta` 逐字段一致；快照每个字段要么绑定 UI surface 要么显式排除并注明理由 |
| **降级词汇表** | 每条数据不可用都有具体原因（`finnhub_unavailable` / `no_reports_in_window` / `partial_frame_coverage` / `implausible_count`…），监控组件永不静默消失 |
| **排除而非降权 / Exclude not down-weight** | 锚不可信时整条排除并打标（`excluded_anchors` + caveat），绝不引入连续降权旋钮；同业不足→排除 EV/S+EV/EBITDA，绝不用原始 GICS 凑数 |
| **绝不编造数字 / Never fabricate a number** | LLM 永不发明估值、技术指标、评分或市场数据；历史回填只重算「可计算锚」，分析师锚在历史日期绝不杜撰（`record_origin` + 分析师哨兵区分 live / backfill 行） |
| **前视防护 / Filing-lag look-ahead defence** | 历史锚重算按披露滞后门控（`FILING_LAG_DAYS`：年报 75 天 / 季报 45 天，`period_end + lag ≤ as-of` 方可使用），宁可用更晚的数据，绝不读尚未公开的财报 |
| **访问路径矩阵优先 / Access-path-matrix-first** | 统一一个生产者是「访问路径」问题，而非物理合并——先画 caller-contract 矩阵（页面=需区间+可联网；排序=零网络；刷新=不污染缓存）再动手 |
| **只追加审计轨 / Append-only audit trail** | 估值锚历史与每日快照只追加、绝不改写既有行；跨页共享同一锚生产者 + epoch，使任何分歧可被检出 |

---

## ✨ 功能特性 / Features

### 决策层 / Decision Layer（主线）

| 页面 / Page | 功能 / Description |
|---|---|
| 🧭 **投研中枢 / Investment Cockpit** | **系统主入口**。一键刷新聚合宏观 regime、市场内部结构读数、主题轮动结论与机会清单（20 候选 × 三时间维度独立评分/状态/触发器），每日快照落盘 |
| 🌐 **宏观仪表盘 / Macro Dashboard** | 宏观 regime 分类（live 数据）+ **Market Internals 工作台**：10 日脆弱度趋势、逐组件明细表（派发日 / 利好遭抛 / 广度 / 弱反弹 / 攻守）、数据 vintage 与迟滞来源标记 |
| 📋 **交易台 / Trading Desk** | 入场策略 v4（分批挂单区间 / 止损 / 仓位参考）、订单叙事、持仓 thesis monitor（区分价格噪音与逻辑破坏） |
| 🏭 **行业研究 / Sector** | **轮动工作台**：GICS 外环攻守读数（多窗口）+ AI 主题内环（vs QQQ 超额、5D×1M 背离矩阵 → 轮动阶段标签、广度确认） |

### 研究层 / Research Layer

| 页面 / Page | 功能 / Description |
|---|---|
| 🔍 **选股扫描 / Scanner** | 四策略并行扫描（动量/价值/质量成长/超卖反弹），AI 跨策略评估，接收主题轮动阶段上下文 |
| 🏢 **个股研究 / Equity** | 护城河雷达、同业对比、AI 深度研究、**AI 估值综合**（多锚融合 + 锚一致性门控：分歧过大时诚实输出「估值锚不一致」而非假中值） |
| 📊 **财务分析 / Financial** | 三张表、DCF 多情景、相对估值同业对比 |
| 📉 **量价分析 / PriceVolume** | K 线 + RSI/MACD/ADX/布林带、支撑压力位 |
| 🤖 **AI 工作流 / Overview** | 五步全自动研究流程（行业 → 选股 → 个股 → 财务 → 量价 → 综合结论），系统的起点，现为研究层组件 |

### 核心机制 / Core Mechanics

- 🧊 **市场内部结构脆弱度层** — 派发日计数（IBD 式）、利好遭抛（财报 beat 次日遭抛）、广度水平与斜率、弱反弹、攻守轮动读数 → 复合等级「正常 / 警戒 / 警报」，交易日历迟滞防单日尖峰；30 天回填校准中，警报领先 2026-06 初回撤约两周
- 🔄 **多窗口相对强弱** — 5D/10D/1M/3M/6M/12M 超额收益（vs SPY/QQQ，日期索引对齐），短/中/长周期各取所需窗口
- ⚓ **公司分型估值 + 多锚融合** — 按公司类型路由方法菜单（成熟盈利 / 成长盈利 / 成长未盈利 / 项目型 / 周期型，各取 DCF · EV/S · EV/EBITDA · PB/PS 区间）；forward 口径相对锚 + 结构化分析师锚池（`{median, mean, high, low, n}` + 离散度门控）+ DCF；锚分歧 >3x 拒绝融合并诚实输出「估值锚不一致」而非假中值；数据合理性守卫剔除异常年度并标记；锚缓存使 Cockpit 长线状态可分化
- 🗂️ **只追加估值锚历史** — 每个页面路径的 live 锚在单一生产者 chokepoint 按 ticker 分片、只追加落盘（`data/anchor_archive/<TICKER>.jsonl`，读取成本 O(单票)）；迁移读出按 30 交易日窗口刻画各序列方向 / 速度与跨序列一致性，thesis monitor 据此给出锚迁移 watch（只注释、永不自动卖出或改 thesis 状态）；离线回填以可重算锚 + 披露滞后门控为历史序列播种（分析师锚绝不杜撰）
- 📒 **每日快照** — 全量候选 + 宏观/脆弱度 `_meta` + 单 vintage 锚区块 原子落盘（JSONL），审计轨 + 未来反馈环的数据地基
- 🌐 **中英双语** / 🌙 **深色浅色主题** / ⚡ **Parquet 本地缓存** / 📄 **Markdown 报告导出**

---

## 🏗️ 系统架构 / Architecture

> **目标形态 = AI Fund 工作流 / Target shape = an AI Fund workflow.** 系统不是「Streamlit 页面直接消费确定性模块」的仪表盘，而是 **数据 → Foundation Agents → PM 层 → MasterPM → UI** 的投研团队流水线。**UI 是 AI-PM 的汇报与人工复核界面，不是做核心决策的地方**；确定性代码计算所有数字（数值防火墙），Foundation Agent 在证据约束下综合含义，PM 做时间维度内的冲突仲裁，MasterPM 做跨时间维度与组合层综合。**全程 review-only，永不下单。**
>
> The system is **not** a dashboard where Streamlit pages consume deterministic modules directly. It is an AI-fund pipeline: **Data → Foundation Agents → PM layer → MasterPM → UI**. The UI is the AI-PM **reporting + human-review surface, never where core decisions are made**. Deterministic code computes every number; Foundation Agents synthesize implications from evidence; PMs arbitrate conflicts within a horizon; MasterPM synthesizes across horizons and at portfolio level. **Review-only throughout — the system never places an order.**

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  数据层 / Data Layer                                          ✅ 已上线 / live  │
│  原始源 raw:  yfinance · FRED · Finnhub · Quiver · Massive Options             │
│  确定性加工信号 processed signals（代码算所有数字 / numeric firewall）:        │
│  macro_regime · market_internals · rotation / theme_baskets / theme_transmission│
│  relative_strength · opportunity_ranker · equity_valuation / anchor_* · gex_dex │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                ▼  证据化 evidence-bound AgentOutput
┌──────────────────────────────────────────────────────────────────────────────┐
│  Foundation Agent 层 / Foundation Agents  (lib/agents/)   🟡 逐个推进 / rolling │
│  ✅ MacroRegime · MoneyFlow · MarketStructure · SectorRotation · ThemeIntelligence │
│  📋 CandidateScreening（资格闸 enabler 已上线 / eligibility gate shipped）·     │
│     StockResearch · ValuationDebate · TechnicalEntry · SectorResearch · RiskOverlay │
│  代码算数字 → LLM 在证据约束下综合含义、引用 evidence_id（绝不发明数字）        │
│  每个 agent 输出三时间维度 finding + 三 confidence；valid_until = 当日           │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                ▼  按时间维度消费 finding + confidence
┌──────────────────────────────────────────────────────────────────────────────┐
│  PM 层 / PM Layer                                          📋 计划 / planned    │
│  ShortTermPM · MidTermPM · LongTermPM —— 各自做时间维度内冲突仲裁（非简单汇总）  │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  MasterPM                                                 📋 计划 / planned     │
│  跨时间维度 + 组合层冲突仲裁、组合级综合；绝不发出任何下单指令                    │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  UI 层 / UI Layer  (Streamlit)                               ✅ 已上线 / live  │
│  AI-PM 汇报 · 证据检视 · 人工复核确认 —— 仅供审阅，永不下单 / review-only       │
│  当前主入口 Investment Cockpit 已附加式接入 4 个 foundation agent 钩子           │
└──────────────────────────────────────────────────────────────────────────────┘
   排序/刷新路径 network-free（缓存行情纯函数）· Foundation Agent 之前的确定性栈
   即上方「加工信号层」· PM / MasterPM 为计划层，尚未生产化
```

### 各 Agent 职责 / Agent Responsibilities

系统中存在**三类**「agent」，必须区分，切勿混淆：

**A. 运行时 Foundation Agents / Runtime production agents（`lib/agents/`）** — 生产路径的真正 agent：包裹一个确定性加工信号生产者，代码先算好所有数字并落为证据，再让 LLM 在证据约束下综合三时间维度含义（绝不发明数字）。这是 **AI Fund 工作流**的 Foundation Agent 层（路线图规范 roster，见下表）。

| Foundation Agent | 分组 / Group | 确定性输入（代码算）| 状态 / Status |
|---|---|---|---|
| **MacroRegimeAgent** | 市场环境 Market env | `macro_regime.classify_regime`（regime/票数/coverage）+ 快照 regime 历史 | ✅ 已实现 `eabf0c2d` |
| **MarketStructureAgent** | 市场环境 Market env | `market_internals` 脆弱度读数（Cockpit Step 4 注入，不二次计算）| ✅ 已实现 `8792343f9` |
| **MoneyFlowAgent** | 市场环境 Market env | `gex_dex`（Massive）+ `compute_dark_pool_signal`（Quiver）| ✅ 已实现 `760f356a3` |
| **SectorRotationAgent** | 机会发现 Opportunity | `theme_baskets` + `theme_transmission` + 完整攻守 O/D reading | ✅ 已实现 `fbf0cc41d` |
| **ThemeIntelligenceAgent** | 机会发现 Opportunity | `theme_transmission`（传导棒次/簇/每票角色）| ✅ 已实现 `5ecfb7875` |
| **CandidateScreeningAgent** | 机会发现 Opportunity | `opportunity_ranker` + `candidate_generator` / `signal_engine` + `candidate_eligibility`（四态资格闸）| 🔄 进行中（资格闸 enabler 已并入 main；agent 本体为下一个）|
| **StockResearchAgent** | 个股研究 Stock research | `thesis_monitor` + 个股研究产物 | 📋 计划 |
| **ValuationDebateAgent** | 个股研究 Stock research | `equity_valuation` / `valuation_router` / `valuation_diagnosis` / `anchor_migration` + 反向 DCF（Phase 8D）| 📋 计划（Phase 8D）|
| **TechnicalEntryAgent** | 个股研究 Stock research | `technical` 指标 + 支撑压力 + `order_advisor` 入场策略 | 📋 计划 |
| **SectorResearchAgent** | 个股研究 Stock research | 行业研究（宏观/政策/产业链/景气度）| 📋 计划 |
| **RiskOverlayAgent** | 风险控制 Risk control | 组合/仓位/脆弱度风险叠加 | 📋 计划 |

> 部分历史临时命名（MarketInternalsAgent / RotationAgent / RelativeStrengthAgent / CandidateAgent / OpportunityAgent / ValuationAgent / TechnicalAgent / ThesisAgent / AnchorHistoryAgent）已并入上面的规范 roster。其中 `relative_strength`、`opportunity_ranker`、`thesis_monitor`、`anchor_migration` 等**不是**独立 agent，而是上表对应 agent 的**确定性输入**（加工信号层）。

**B. PM 层 agents / Future PM agents（计划）** — `ShortTermPM` / `MidTermPM` / `LongTermPM` 各自消费每个 Foundation Agent 对应时间维度的 finding + confidence，做**冲突仲裁**（非简单汇总）；`MasterPM` 做跨时间维度与组合层综合。**尚未生产化。**

**C. 旧版 `.claude/agents` 研究工作流定义 / Legacy developer-research workflow** — 下表是项目最初的多 Agent 研究工作流定义，由 **Claude Code 在对话模式下**调用，用于「AI 工作流 / Overview」研究层页面；它们**不是** `lib/agents/` 的运行时生产 Foundation Agents，也不是 PM 层。Streamlit 应用通过 `lib/llm_orchestrator.py` 直接调用 Claude API 驱动该五步工作流。

| Agent 定义文件 | 名称 | 核心职责 |
|---|---|---|
| `orchestrator.md` | Orchestrator | 意图理解、任务拆解、子 Agent 调度、结果整合 |
| `sector-research.md` | Sector Research | 宏观政策、产业链、行业景气度、ETF 趋势 |
| `stock-scanner.md` | Stock Scanner | 全市场筛选，四策略并行，输出候选标的 |
| `equity-research.md` | Equity Research | 商业模式、护城河、管理层、竞争格局 |
| `financial-analyst.md` | Financial Analyst | 三张表、DCF/相对估值、盈利质量分析 |
| `price-volume-analyst.md` | Price & Volume | 技术形态、资金流、RSI/MACD/ATR、情绪 |

---

## 🧪 可靠性工程 / Reliability Engineering

本项目把个人项目按生产标准开发：**每个阶段 = 实现（Claude Code）→ 独立审查（Codex）→ 修复 → 单点复审 → 关闭**，全部审查记录沉淀于 `docs/`。

- **68 个可靠性测试套件、数千条断言**（`scripts/test_reliability_*.py`）：机会排序、估值止血、估值分型路由、轮动与内部结构、交易台、入场策略、Cockpit 重建、渲染顺序、主题篮子、估值锚历史 / 历史回填、**估值诊断卡**、**多维同业画像 / `peer_match_quality` 诚实降级**等
- **决策层 canonical sweep（v2.3 收口 @ `84daa4a` 全绿）**：entry_v4 92 · 7A 115 · 7B 193 · 估值路由 104 · 估值止血 65 · Cockpit 重建 47 · 锚历史 60 · 历史回填 60 · 主题篮子 146 · 交易台 118 · 三周期评分 189 · 渲染顺序 50
- **v2.4（已关闭 / `--no-ff` 合并 main，approved @ `18dfcf2`；含 REQUEST CHANGES 修复轮）新增 / 更新**：估值诊断卡 50（新）· 锚历史 77（分片）· 历史回填 61 · entry_v4 92；full `test_reliability_*` sweep **GREEN=65 / RED=13**（13 红为既有正交项，与本轮无关）
- **v2.5（已关闭 / `--no-ff` 合并 main，approved @ `6f9c1ec`；v2 系列收官；含 B1 修复轮）新增 / 更新**：多维同业画像 `peer_match` 49（新，含 SNOW→高质量云同业、KTOS→低质量降级的真实路径验收 + **B1 缓存顺序无关性**双向测试）· 估值诊断卡 50→54；同业不足时显式降级（排除 EV/S+EV/EBITDA 同业倍数锚，绝不用原始 GICS 凑数），`peers=None` 时与 v2.4 逐字节一致；**B1 修复：同业集签名进入缓存键**（同业匹配同时影响 EV 锚的取舍与数值 → 同业版/无同业版分别缓存，消除首写者依赖，与轮回-1 epoch 混淆同类）；full `test_reliability_*` sweep **GREEN=66 / RED=13**（13 红为既有正交项，与本轮无关）
- **不变量测试**：tighten-only（脆弱度强制 high 时 regime 对象逐字节不变）、宏观镜头永不改主题排名、排序路径零网络调用（结构化断言）、历史回填零网络 / 零归档写入（冷排序 DoD）、分析师锚在历史日期绝不杜撰
- **Parity 测试**：驱动真实刷新函数，断言两个页面的渲染 token 与同次刷新写出的快照 `_meta` 完全一致，并以负向对照证明分歧必然被捕获
- **校准回填工具**：`scripts/calibrate_fragility_backfill.py` 重算过去 30 交易日逐日脆弱度组件表（四道质量门），供阈值校准与盘感对照

---

## 🛠️ 技术栈 / Tech Stack

| 层级 / Layer | 技术 / Technology |
|---|---|
| **AI** | [Anthropic Claude API](https://www.anthropic.com/) (`claude-sonnet-4-6`) · `lib/llm_orchestrator.py` |
| **Web UI** | [Streamlit](https://streamlit.io/) 1.35+ · CSS Variables (dark/light theming) |
| **数据 / Data** | [yfinance](https://github.com/ranaroussi/yfinance) (primary, 行情/财务) · [FRED](https://fred.stlouisfed.org/)（利率/信用/流动性宏观）· [Finnhub](https://finnhub.io/)（财报日历/新闻）· [Quiver](https://www.quiverquant.com/)（暗池/国会/内部人/机构）· Massive Options（期权链 Greeks/IV/OI → GEX/DEX；曾用名 / formerly Polygon.io）|
| **可视化 / Charts** | [Plotly](https://plotly.com/python/) |
| **技术分析 / TA** | [ta](https://github.com/bukosabino/ta) (SMA/EMA/RSI/MACD/ADX/Bollinger Bands) |
| **存储 / Storage** | Apache Parquet (pyarrow) · JSONL 快照 · `lib/cache_manager.py` |
| **状态管理 / State** | `lib/workflow_state.py` · JSON persistence |
| **双语翻译 / I18n** | LLM 双语产出 + [deep-translator](https://github.com/nidhaloff/deep-translator) 兜底 |
| **测试 / Testing** | Streamlit AppTest 渲染冒烟 + 自研可靠性断言套件 |
| **运行环境 / Runtime** | Python 3.11+ · WSL2 (Ubuntu) / Linux |

---

## 🚀 快速开始 / Quick Start

### 1. 克隆项目

```bash
git clone https://github.com/haochenxie56/AI-Equity-Research-Multi-Agent.git
cd AI-Equity-Research-Multi-Agent
```

### 2. 安装依赖

```bash
# Python 3.11+ required
pip install -r requirements.txt
```

> **Ubuntu / WSL 提示**：若遇到 `externally-managed-environment` 错误，使用虚拟环境：
> ```bash
> python3 -m venv .venv && source .venv/bin/activate
> pip install -r requirements.txt
> ```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的 API Keys
```

### 4. 启动应用

#### 🪟 Windows（需要 WSL2 + Ubuntu）

**一键静默启动（推荐）：双击 `launch.vbs`**

脚本自动检测端口占用 → 启动 WSL 中的 Streamlit → 等待就绪 → 打开浏览器，无命令行窗口弹出。

若需在桌面创建快捷方式，目标路径设为：
```
wscript.exe "\\wsl.localhost\Ubuntu\home\<你的用户名>\projects\investment-agents\launch.vbs"
```

#### 🍎 macOS / 🐧 Linux

```bash
streamlit run app.py
```

浏览器访问 → `http://localhost:8501`，从「投研中枢 / Investment Cockpit」开始。

> 💡 日常使用建议：每天打开 Cockpit 点一次「一键刷新」——快照历史是脆弱度迟滞、阈值校准与未来反馈环的数据口粮。

---

## 🔑 环境变量 / Environment Variables

参考 `.env.example`：

```env
# Anthropic API Key（AI 工作流 + Foundation Agents 必需 / Required for AI workflow + agents）
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Finnhub API Key（财报日历 → 「利好遭抛」组件 + 新闻。强烈建议 / Strongly recommended）
FINNHUB_API_KEY=your_finnhub_api_key_here

# FRED API Key（利率/信用/广义美元/流动性等宏观序列，可选 / Macro series, optional）
FRED_API_KEY=your_fred_api_key_here

# Quiver Quantitative API Key（暗池/国会/内部人/机构持仓，可选 / Alt-data, optional）
QUIVER_API_KEY=your_quiver_api_key_here

# Massive Options API Key（期权链 Greeks/IV/OI → GEX/DEX，可选 / Options chain, optional）
MASSIVE_API_KEY=your_massive_api_key_here
```

**各 Key 用途与降级 / Key purpose & graceful degradation：**

| Key | 用途 / Purpose | 必需性 / Requirement | 缺失时 / When absent |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Claude API：五步研究工作流 + Foundation Agent 的 LLM 综合 | AI 工作流与 agent 必需 | 确定性页面照常；agent 钩子按 `_has_llm_api_key()` 门控为 no-op，刷新不中断 |
| `FINNHUB_API_KEY` | 财报日历（「利好遭抛」组件）+ 新闻 | 强烈建议 | 财报反应组件按降级词汇表诚实降级（`finnhub_unavailable`），其余不受影响 |
| `FRED_API_KEY` | 宏观序列：利率 / 信用（HY OAS）/ 广义美元 / 货币市场流动性 | 可选 | 相关宏观读数回退到内置 fixture（per-series 隔离、fail-closed）|
| `QUIVER_API_KEY` | 暗池 / 国会 / 内部人 / 机构持仓（Phase 8B-0；喂 MoneyFlowAgent 暗池信号）| 可选 | 抓取 fail-closed 返回空；`compute_dark_pool_signal` 标 `insufficient_data` |
| `MASSIVE_API_KEY` | 期权链 Greeks / IV / OI → GEX/DEX（Phase 8B-0；喂 MoneyFlowAgent；曾用名 Polygon.io）| 可选 | 无 key → 降级快照；免费档无 Greeks/OI（`greeks_unavailable`），实时 GEX/DEX 需 Starter 档 |

**获取 API Key / Getting API Keys：**
- Anthropic API → [console.anthropic.com](https://console.anthropic.com/)
- Finnhub（免费）→ [finnhub.io/register](https://finnhub.io/register)
- FRED（免费）→ [fred.stlouisfed.org](https://fred.stlouisfed.org/)
- Quiver Quantitative → [quiverquant.com](https://www.quiverquant.com/)
- Massive Options（曾用名 Polygon.io）→ 供应商控制台

> yfinance 为主数据源，**无需任何 API Key** 即可运行基础页面。AI 工作流与 Foundation Agent 需要 `ANTHROPIC_API_KEY`；其余 key 均为可选，缺失时对应组件按降级词汇表诚实降级，不影响其它功能。

---

## 📁 项目结构 / Project Structure

```
investment-agents/
├── app.py                          # 主页 / Home (Streamlit entry point)
├── ui_utils.py                     # 共享工具：主题、图表、i18n、bi() 双语读取
├── CLAUDE.md                       # AI 协作开发约定（含验证纪律规则）
│
├── pages/
│   ├── 1_Overview.py               # AI 研究工作流（五步全自动，研究层组件）
│   ├── 2_Sector.py                 # 行业研究 — 轮动工作台（攻守 + 主题阶段/广度）
│   ├── 3_Scanner.py                # 选股扫描 — 四策略 + AI 选股
│   ├── 4_Equity.py                 # 个股研究 — 护城河/同业/AI 估值综合（锚门控）
│   ├── 5_Financial.py              # 财务分析 — 三张表 + DCF + 相对估值
│   ├── 6_PriceVolume.py            # 量价分析 — K 线 + 多指标叠加
│   ├── 7_Investment_Cockpit.py     # ⭐ 投研中枢 — 主入口（聚合 + 机会清单 + 快照）
│   ├── 8_Macro_Dashboard.py        # 宏观仪表盘 + Market Internals 工作台
│   ├── 9_Trading_Desk.py           # 交易台 — 入场策略 / 订单叙事 / thesis 监控
│   ├── 10_Thesis_Library.py            # 研报卡片库 — 摄入 / 浏览 / 管理（Thesis Ingestion MVP）
│   └── 11_Audit_Review.py             # 快照审计回顾 — 覆盖/脆弱度/状态历史/跟进/完整性（只读 · 双语）
│
├── lib/
│   ├── llm_orchestrator.py         # Claude API 调用（LLM 层）
│   ├── opportunity_ranker.py       # 机会排序编排（三周期评分/状态/快照）
│   ├── audit_query.py              # 快照审计查询层（只读 / 无信号引擎 / 无排序 / 无联网 / fail-closed）
│   ├── signal_engine.py            # 双轨信号引擎 + Finnhub 财报日历
│   ├── candidate_generator.py      # 候选生成（发布扫描 universe）
│   ├── candidate_eligibility.py    # 确定性四态资格闸（eligible/conditional/ineligible/unknown）；LLM-free 数值防火墙；六闸 thesis/eps/valuation/event(hard)+liquidity/distribution(soft)，横向按时间维度非对称；CandidateScreeningAgent 前置 enabler / deterministic four-state candidate eligibility gate feeding CandidateScreeningAgent
│   ├── order_advisor.py            # 状态推导 / 入场策略 v4 / 条件注册表
│   ├── thesis_monitor.py           # 持仓 thesis 监控（噪音 vs 逻辑破坏）
│   ├── thesis_ingestion/               # Thesis Ingestion MVP（schema / store / extractor / validator）
│   ├── market_internals.py         # 脆弱度层（组件/复合/迟滞/滚动重算/vintage 守卫）
│   ├── macro_regime.py             # 宏观 regime 分类（frozen）
│   ├── relative_strength.py        # 多窗口 RS（日期对齐 + vintage 标记）
│   ├── rotation.py                 # GICS 外环：轮动评分 + 攻守读数
│   ├── theme_baskets.py            # AI 主题内环：超额动量/背离矩阵/广度
│   ├── equity_valuation.py         # 多锚估值融合 + 分型方法菜单 + 锚一致性门控
│   ├── valuation_router.py         # 公司分型分类器 + 方法菜单 + 多维同业画像匹配（数值维 ∩ 主题篮子/覆盖标签 + peer_match_quality 诚实降级）
│   ├── valuation_anchor.py         # FairValueAnchor（forward 口径；已退役保留兼容）
│   ├── anchor_cache.py             # 估值锚本地缓存（版本守卫/原子写）
│   ├── anchor_archive.py           # 只追加估值锚历史（生产者 chokepoint / 按 ticker 分片 / 原子追加）
│   ├── anchor_migration.py         # 确定性锚迁移读出（方向/速度/跨序列一致性）
│   ├── anchor_backfill.py          # 离线历史回填引擎（可重算锚 + 披露滞后门控）
│   ├── valuation_diagnosis.py      # 估值诊断卡（纯确定性组装 + valuation_role 映射）
│   ├── quiver_fetcher.py           # Phase 8B-0：Quiver 暗池/国会/内部人/机构（fail-closed）+ 暗池信号纯聚合
│   ├── massive_options_fetcher.py  # Phase 8B-0：Massive(=Polygon) 期权链 → Phase 2E OptionChainSnapshot（source="massive"）
│   ├── gex_dex.py                  # Phase 8B-0：GEX/DEX 确定性计算器（OI 墙 + gamma 挤压监测；零 lib.reliability 导入）
│   ├── technical.py / data_fetcher.py / cache_manager.py / sectors.py
│   ├── valuation.py / financial_tab.py / pv_tab.py / report_writer.py
│   ├── workflow_state.py / translator.py
│   ├── reliability/                # 可靠性基础设施（适配器层 / World 2）
│   ├── agent_framework/            # Phase 8A：AgentOutput / agent_runner（含 _repair_llm_response 扁平响应结构修复层）/ world_adapter（lib.reliability 全惰性导入）
│   └── agents/                     # 运行时 Foundation Agents（5 个已生产化）：macro_regime_agent —— MacroRegimeAgent（三时间维度置信度 + 投票计数证据）；money_flow_agent —— MoneyFlowAgent（GEX/DEX + 暗池双数据源，三置信度 + prior_result 挤压条件 C）；market_structure_agent —— MarketStructureAgent（注入 FragilityReading，short=coverage×clarity / mid=连续恶化天数 / long=0.0，signal_basis 三值分类器）；sector_rotation_agent —— SectorRotationAgent（theme_baskets + theme_transmission + 完整攻守 O/D，short=coverage×stage_confirmed率 / mid=coverage×动量分散×wave清晰度，signal_basis 三值含 no_clear_leadership）；theme_intelligence_agent —— ThemeIntelligenceAgent（成分股实时 RS 排名×种子角色 + 跨波次非对称机会 wave {1,2}+rotating_in，short=coverage×role_resolution（全成分股分母）/ mid=coverage×asymmetry_strength / long=0.0，signal_basis 三值含 no_role_signal 非看空）。下一个：CandidateScreeningAgent
│
├── scripts/
│   ├── test_reliability_*.py       # 69 个可靠性测试套件（数千条断言）
│   ├── calibrate_fragility_backfill.py  # 30 日脆弱度校准回填工具
│   ├── test_reliability_thesis_ingestion.py  # 71 项 thesis 卡摄入可靠性断言
│   ├── test_reliability_phase_7d_audit_query.py  # 快照审计查询 §7D.1–§7D.10（含导入图守卫）
│   ├── test_agent_framework_foundation.py  # Phase 8A/8B Agent 框架 §8A.1–§8A.15（15 项；含子进程导入守卫 + _repair_llm_response 修复层单元 + 端到端）
│   ├── test_phase_8b0_quiver.py    # Phase 8B-0 Quiver §8B0-Q1–Q6（网络全 mock）
│   ├── test_phase_8b0_massive.py   # Phase 8B-0 Massive §8B0-M1–M5（含坏合约跳过判别）
│   ├── test_phase_8b0_gex_dex.py   # Phase 8B-0 GEX/DEX §8B0-G1–G9（含 prior_result 挤压判别）
│   ├── test_phase_8b_macro_regime_agent.py  # Phase 8B MacroRegimeAgent §8B-M1–M11（24 项；LLM/网络全 mock，含 Guard A/B 与投票判别）
│   ├── test_phase_8b_money_flow_agent.py     # Phase 8B MoneyFlowAgent §8B-MF1–MF11（34 项；LLM/网络全 mock，含信号翻转与 agree_count=2 判别）
│   ├── test_phase_8b_market_structure_agent.py  # Phase 8B MarketStructureAgent §8B-MS1–MS13 + MS6a–6e（44 项；LLM/网络全 mock，含 cap-vs-floor 边界与 coverage 判别）
│   ├── test_phase_8b_sector_rotation_agent.py  # Phase 8B SectorRotationAgent §8B-SR1–SR14（34 项；LLM/网络全 mock，含 coverage 翻转与 active_order=None 判别）
│   ├── test_phase_8b_theme_intelligence_agent.py  # Phase 8B ThemeIntelligenceAgent §8B-TI1–TI14（39 项；LLM/网络全 mock，含 roles→unknown / stage→leading / 排序翻转 3 个 mutation probe）
│   ├── test_phase_8b_candidate_eligibility.py  # CandidateScreeningAgent 资格闸 enabler（18 项 / 87 断言，全离线真实 OpportunityCard/CandidateSignal 实例；含 event 时间维度非对称、hard-fail 压制、valuation 两带×时间维度、forward_pe 不可用防火墙泄漏守卫、多条件完整性等判别）
│   ├── backfill_anchors.py         # 估值锚历史离线回填 CLI（可重算锚 + 披露滞后门控）
│   ├── migrate_anchor_archive_to_shards.py  # 一次性离线：单文件归档 → 按 ticker 分片
│   ├── daily_scan.py / fetch_financials.py / run_research.py
│
├── docs/
│   ├── reliability_*.md            # 各阶段 phase 文档（设计/审查/收口记录）
│   ├── ai_dev_state/               # AI 协作开发状态（PROJECT_STATE / CURRENT_TASK）
│   └── calibration/                # 校准回填产物（git-ignored）
│
├── .claude/agents/                 # Claude Code 子 Agent 定义
├── data/                           # Parquet 缓存 + 每日快照（git-ignored）
│   ├── snapshots/                  # opportunities_YYYYMMDD.jsonl（审计轨）
│   ├── agent_outputs/              # AgentOutput JSONL（<agent_id>/<date>.jsonl，Phase 8A）
│   └── agent_evidence/             # EvidenceStore tool_results（<agent_id>/<run_id>/，Phase 8A）
└── research/                       # 工作流状态 + 生成报告（git-ignored）
```

---

## 🗺️ 路线图 / Roadmap

开发模式：**Claude Code 实现 → Codex 独立审查 → 修复 → 复审通过后关闭**，逐阶段推进。

| 阶段 | 状态 | 内容 |
|---|---|---|
| 决策层基础（信号引擎 / 入场策略 / 交易台 / Cockpit） | ✅ | 双轨信号、entry v4、thesis monitor、聚合中枢 |
| Phase 7A — 机会排序 | ✅ | 三周期独立评分/状态、五状态映射、每日快照、network-free 排序 |
| 估值止血 | ✅ | 锚一致性门控、forward 口径、锚缓存 |
| Phase 7B — 轮动 + 市场内部结构 | ✅ | 多窗口 RS、两环轮动、脆弱度层（tighten-only + 迟滞 + 滚动双轨 + vintage 统一 + parity 纪律）；30 日校准通过 |
| 估值重构 v1 | ✅ | 公司分型路由器（五型方法菜单）+ 增长画像同业匹配；目标：实质降低「锚不可调和」率。REQUEST CHANGES 五项修复已应用（DCF 结构性排除、周期 ≤4 年年度区间、缓存拒绝旧版、token 边界匹配、状态文档对齐）；**复审通过，已于 ca5ad14 关闭** |
| 脆弱度小项批次 + 杂务 | ✅ | 脆弱度 banner + 量缩（vol_shrink）组件（B1/B2/B3）+ 校准回填工具扩展；杂务：Development Discipline 文档 + `scripts/diag/` 忽略（approved @ b5c128a） |
| Anchor Intelligence v2 | ✅ | **Round 1**：生产者统一 + 结构化分析师锚池 + epoch 戳（approved @ 9e53f04）。**v2.3**：只追加估值锚历史（U1）+ 单 vintage 快照锚区块（U2）+ 确定性迁移读出 + thesis 锚迁移 watch（U3，主体 approved @ 9f6c37e）+ **历史回填**（可重算锚 / 分析师绝不杜撰 / 披露滞后前视防护 / 同日接缝守卫，approved @ c57e56e，merged @ 84daa4a） |
| Anchor Intelligence v2.4 | ✅ | **估值诊断卡**（公司分型 · 适用/已排除方法及原因 · 锚一致性聚合/离群 · 认可区间 · 确定性 `valuation_role` 映射 → 7A 三时间维度接口 · 价格越界/锚池下移等可证伪机械条件；反向 DCF 与叙事催化为 Phase-8 占位）渲染于个股研究 + 交易台；**F4 估值锚归档按 ticker 分片**（`data/anchor_archive/<TICKER>.jsonl`，读取 O(全量)→O(单票)，一次性离线迁移脚本）。纯确定性、零新增锚计算、任何路径零联网；50 项诊断断言，full sweep GREEN=65/RED=13；**复审通过，approved @ `18dfcf2`，已 `--no-ff` 合并 main** |
| Anchor Intelligence v2.5（v2 系列收官） | ✅ | **多维同业画像**：在 v1 的行业 × 增长带 × 规模带上新增利润率/盈利阶段/收入周期性数值维（确定性，复用已抓取的 `info`）；**同业候选 = 数值维 ∩ 主题篮子成分（与轮动同一份策展名单，单一事实来源）∪ 人工复核的 `peer_profiles` 覆盖标签**（最小种子仅 KTOS——篮子未覆盖的国防科技角落；MSCI/Syntax/Morningstar 等付费黑箱分类已评估并拒绝）。**`peer_match_quality` 诚实降级**：合格同业 < 4 时置 `low` + `insufficient_comparable_peers`，**绝不用原始 GICS 凑数**，并将 EV/S+EV/EBITDA 同业倍数锚**排除**出融合（`relative_pe` 行业图谱锚不受影响）——非可比同业算出的倍数比没有同业锚更糟。诊断卡呈现同业质量。`peers=None`（排序/刷新/交易台）→ 不评估 → 与 v2.4 逐字节一致。SNOW→高质量云同业、KTOS→低质量降级至仅分析师锚的真实路径验收；`peer_match` 49 新套件、诊断卡 50→54、full sweep GREEN=66/RED=13。**B1 修复轮**：`_peers` 曾被排除出 `compute_app_fair_value` 缓存键，却决定 `peer_match_quality` 与 EV 锚取舍 → 首写者依赖（与轮回-1 epoch 混淆同类）；因同业匹配同时影响 EV 锚的取舍与**数值**，故采用 Option A——同业集签名 `peer_sig` 进入缓存键，同业版/无同业版分别缓存、调用顺序无关，无同业路径与 v2.4 逐字节一致（§10 双向测试，判别性已验证）。**复审通过，approved @ `6f9c1ec`，已 `--no-ff` 合并 main；本轮收官 Anchor Intelligence v2 系列** |
| Thesis Ingestion MVP | ✅ | 人工策展外部研报/访谈 → 单次 LLM 抽取 → 本地 JSON 结构化 thesis 卡；带可证伪条件、时效分级、双语渲染、卡片库独立页面（pages/10）、Cockpit 跳转入口；MVP 零消费（纯攒库），与排序/快照/锚系统零交集；UI验收批次已完成：侧边栏导航、主题卡/信号卡上下文跳转（switch_page）、备份文件夹自动创建与上传自动存档、docx/pdf/pptx格式支持、多卡提取去重逻辑、JSON修复（json-repair）、枚举规范化、测试 80 项 |
| Phase 7C — 主题传导映射 | ✅ | 12 个 AI 主题映射资本传导棒次（1–4）+ 传导簇 · 每票角色种子（主导/二阶/供应商/平台/投机/落后；未评估→`unknown`）；复用 `phase5_theme_intelligence` schema（零重复）· **仅展示用、绝不进入排序**；隔离不变量（只依赖 `theme_baskets` + `phase5_theme_intelligence`，不碰 ranker / pages）；Cockpit 主题卡传导行 + Sector 市场主题波次卡片重设计；新增 `theme_transmission` 套件 11 项全过（S1 隔离 / S7 ranker fail-closed / S8 无 `approved_for_execution` / S9 篮子 parity）；feature commit `bbdf5b0`（待审，未合并 main） |
| Phase 7D Block A — 快照审计查询接口 | ✅ | 只读审计查询层（`lib/audit_query.py`：`load_all_meta` / `load_all_opportunities` / `query_status_transitions` / `compute_actionable_follow_through` / `compute_fragility_series` + 类型化记录包，容忍叠加式 schema 漂移；**无信号引擎 / 无排序 / 无联网，fail-closed**）+ 双语审计回顾页（pages/11，A–E 节：覆盖表 / 脆弱度 Altair 图 / 状态历史 / 跟进分析 / 完整性，全部标签·表头·单元格随中英切换）；§7D.1–§7D.10 全过（tmp_path 内存；§7D.10 AST + 运行时守卫禁止引入 `signal_engine`）；feature `5b14da1`，`--no-ff` 合并 main @ `5a57850` 并推送；UI 验收 EN + 中文通过（2026-06-19） |
| Phase 8A — Agent Framework Foundation | ✅ | 激活 World 2 可靠性层的连接组织（7 个新文件）：统一 `AgentOutput` dataclass（嵌入校验后的 `AgentResult` + 证据引用从 findings/risks 扁平化 + `judgment` 数值约束守卫）· LLM agent runner（`run_llm_agent` 11 步：tool_results → `EvidenceStore` → 证据包 → 受约束提示 → Claude → 解析+校验 → `AgentOutput` → JSONL 落盘；fail-closed 兜底为 rule-based + 需人工确认，校验 error 抛 `AgentRunError`）· World1→World2 适配器（`llm_output_to_tool_result` / `processed_signals_to_tool_result`，dataclass 自动 `asdict` 归一化）· JSONL 持久化（`data/agent_outputs/<agent_id>/<date>.jsonl`）· **MacroRegimeAgent 端到端冒烟**。所有 `lib.reliability` 导入惰性化（导入 `agent_framework` 绝不触发 52 模块 eager `__init__`，子进程导入守卫验证）；`approved_for_execution` 恒 `False`；不接线既有页面（Phase 8B）。两轮 Codex 审查（REJECT→修复→APPROVE）；§8A.1–§8A.11 **11/11** 通过；`--no-ff` 合并 main @ `f6a0f74` |
| Phase 8B-0 — 新数据源接入层 | ✅ | 两个付费数据源的接入 + 加工信号层（抓取与计算严格分离）：**Quiver Quantitative**（暗池 / 国会 / 内部人 / 机构持仓——`lib/quiver_fetcher.py`，fail-closed + `@st.cache_data`，`compute_dark_pool_signal` 纯确定性聚合，阈值内联、`prev_close` 买卖代理 + 缺失时 50/50 降级）· **Massive Options（= Polygon）**（期权链含 Greeks/IV/OI——`lib/massive_options_fetcher.py`，映射进既有 Phase 2E `OptionContractSnapshot`/`OptionChainSnapshot`（`source="massive"`，2E 收益/证据层零改动）；`next_url` 分页 ≤5；逐合约 `try/except` 跳过坏合约并记 `contract_skipped` 警告；免费档无 Greeks/OI 时 `gamma=None` + `greeks_unavailable` 优雅降级）· **GEX/DEX 确定性计算器**（`lib/gex_dex.py`，零 `lib.reliability` 导入、绝不抛错：GEX/DEX 求和、OI 墙、A+B+C 三条件 gamma 挤压监测含 `prior_result` DEX 趋势 → low/mid/high；`regime_summary` 无任何数字）。免费档需升级 Starter 方可实时 GEX/DEX；Quiver `prev_close` 字段名待实盘 API 确认。三轮 Codex 审查（REJECT → APPROVE WITH FIXES → APPROVE）；24 项测试（Quiver 6 + Massive 5 + GEX/DEX 13），变异探针 RED 确认；feature `b365f25`，`--no-ff` 合并 main @ `69d7c9f` 并推送 |
| Phase 8B — MacroRegimeAgent 生产实现 | ✅ | 首个具体 agent 从 Phase 8A 冒烟升级为**生产版**：把确定性宏观状态分类转成三时间维度、带证据的 `AgentOutput`。**所有 LLM 可引用的数字（三置信度 + 投票计数 + 状态稳定天数）均由代码计算并在 LLM 调用前落为证据**（数值防火墙）。`lib/macro_regime.py` 叠加 `votes_risk_on/off/total`（`classify_regime` 填充，降级路径为 0；`macro_state` 字段白名单不受影响）；`lib/agents/macro_regime_agent.py` 全重写：`_compute_short_confidence`（投票一致率）· `_compute_mid_confidence`（`load_all_meta` 连续同状态天数，Guard A 当前状态降级 + Guard B 历史 unknown 硬断，`_MID_CONFIDENCE_BREAKPOINTS` 饱和曲线）· `_compute_long_confidence`（`data_coverage × short`）· `run_macro_regime_agent` 接受 `MacroRegimeResult`/dict/`None`，构建**两个** ToolResult（`classify_regime` + `macro_regime_confidence`）+ 动态三发现指令（无数字）+ 外层 fail-closed 兜底；`lib.reliability` 全惰性导入。Cockpit **附加式**钩子：复用已算 regime（不二次 `fetch_all_macro`）· `_has_llm_api_key()` 门控 · 独立 try/except（绝不中断刷新）· 仅写 `macro_regime_agent_output`；零 UI 改动。§8B-M1–M11 **24/24**（LLM/网络全 mock，真实 dataclass 夹具；M6a Guard-A / M6b Guard-B 判别、M11 非对称 5/1 投票判别，三处变异探针 RED 确认）；Phase 6A 宏观套件 337/337 回归 GREEN。两轮 Codex 审查（REJECT → APPROVE）；feature `c25efe1`，`--no-ff` 合并 main @ `eabf0c2d` 并推送。**合并后修复（当前 baseline `main @ a19b862`）**：①提示词 `REQUIRED OUTPUT FORMAT` 块 + judgment 取首句完整句（≤400 字符，`_JUDGMENT_MAX_LEN` 200→400，`8b84f17a`）；②`agent_runner._repair_llm_response()` 结构修复层——扁平 LLM 响应（顶层 text/evidence、float confidence）→ `AgentResult` 形状（包入 findings、注入 agent_name/run_id、float→`AgentConfidence` 对象），接在 `_extract_json_obj` 与 schema 校验之间（`a19b862`）；agent 框架套件升至 §8A.1–§8A.15 **15/15** |
| Phase 8B — MoneyFlowAgent | ✅ | GEX/DEX（Massive）+ 暗池（Quiver）双数据源；三置信度确定性计算（short=信号共振率/mid=暗池强度×方向/long=0.0）；prior_result DEX 趋势（11 字段 frozenset 验证 + 不可读即返回 None）；neutral GEX 必须输出期权结构策略；Cockpit 附加式钩子；34 项测试，Codex 两轮通过 |
| Phase 8B — MarketStructureAgent | ✅ | 注入已算好的 FragilityReading（Step 4 之后，无重复计算）；short=coverage×clarity（5核心组件，永久脚手架组件排除在外）；mid=连续恶化天数饱和曲线（vintage_mismatch→cap 0.1 非 floor）；signal_basis 三值分类器区分信号缺失/数据缺失/有信号；tighten-only 禁令写入 prompt；44 项测试含边界覆盖，Codex 两轮通过 |
| FragilityReading O/D 扩展 | ✅ | 把完整 offense_defense reading（avg_diff/by_window/n_windows/confirming_windows）透传到 FragilityReading.offense_defense；fragility_snapshot() 不变；mutation probe 确认判别性；229/229，Codex 一轮通过；为 SectorRotationAgent 提供所需数据 |
| Phase 8B — SectorRotationAgent | ✅ | 主题动量（theme_baskets）+ 传导波次（theme_transmission）+ 完整 O/D reading（avg_diff/confirming_windows）注入；short=coverage×stage_confirmed率；mid=coverage×momentum分散度×wave清晰度；signal_basis 三值含 no_clear_leadership（中性/等待，禁止方向性解读）；34 项测试含 2 个 mutation probe，Codex 一轮通过 |
| Phase 8B — ThemeIntelligenceAgent | ✅ | 成分股实时 RS 排名×种子角色（leader/2nd-derivative/supplier/laggard）；跨波次非对称机会（wave {1,2} + rotating_in，不含空字符串）；short=coverage×role_resolution（诚实全成分股分母）；mid=coverage×asymmetry_strength；no_role_signal 明确非看空；与 SRA 的波内落后者概念显式区分；39 项测试含 3 个 mutation probe，Codex 一轮通过 |
| constituent_rs 扩展 + 标签 lift | ✅ | ThemeIntelligenceAgent 前置：`CLUSTER_LABELS`/`ROLE_LABELS` 移入 `lib/theme_transmission.py`（单一事实来源，两个页面删本地 copy，lazy import + closure 经 `co_freevars` 验证）；`ThemeMomentumResult` 加 `constituent_rs` 字段（多窗口成分股超额，`_enrich_excess_stage_breadth` 填充，复用 `constituent_closes`，**零新增网络调用**，存 `{ticker:{"1m","3m","active"}}` 且过滤 None）；ETF 主题统一填充，fixture 主题保持 `{}`；`§TB-CR3` 判别性诚实记录（None 守卫与 `_pct_return` 冗余，真正保护是 `if _ticker_excess`，Exp B1/B2 验证 RED）；157/157，Codex 一轮通过 |
| Candidate 资格闸（CandidateScreeningAgent 前置 enabler） | ✅ | 确定性、LLM-free 四态资格闸（`lib/candidate_eligibility.py`）——**不是 agent**（无 LLM/AgentOutput/slate/Cockpit 钩子，均属 agent 本体下一阶段）。按 `(ticker, horizon)` 在 `OpportunityCard`+`CandidateSignal` 上判 `eligible/conditional/ineligible/unknown`（只读，dataclass 或 dict 皆容忍）。六闸两层：HARD `thesis`/`eps`/`valuation`/`event`（可判 ineligible）+ SOFT `liquidity`/`distribution`（永不 ineligible）；`eps`/`valuation`/`event` 按时间维度非对称（临近财报只闸 SHORT、不闸 LONG；EPS 恶化在 SHORT 为 conditional、MID/LONG 为 fail）；`event` 刻意排除 FOMC/CPI（市场级、主题内无区分度——MarketStructure 的 lane）。聚合优先级：hard-fail → hard-unknown → any-conditional → soft-unknown(→conditional) → eligible；理由列表取自全部闸（完整、字节稳定）。**数值防火墙 provenance 守卫**：`_forward_pe_is_usable` 拒 None/非数值/bool/≤0，堵住 `fetch_fundamental` 在无效 `forwardPE` 上仍标 `data_source["valuation"]="live"` 而 `_valuation_percentile` 默认 0.5 的泄漏——被默认的 0.5 记为 `VALUATION_UNKNOWN`，绝不当真值放行。模块导入仅 stdlib；两新文件、零改既有文件。18 项测试 / 87 断言全离线，真实 `OpportunityCard`/`CandidateSignal`/`Blocker`/`FundamentalResult`/`TrackAResult` 实例。Codex REJECT（provenance 泄漏）→ 修复轮（1 代码修复 + 4 测试 + 1 注释）→ APPROVE。Phase 文档 `docs/reliability_candidate_eligibility_gate.md` |
| Step 3 Narrative Disk Cache | ✅ | LLM narrative 结果磁盘持久化（data/narrative_cache/）；重启后命中跳过 LLM；指纹对齐 prompt 输入（news[:25] + headline + summary[:160]，json.dumps 序列化）；TTL 24h；原子写；27 项测试，Codex 三轮审查通过 |
| _meta 扩展（key_signals / opportunity_posture / confidence） | ✅ | 三个确定性 classify_regime 字段写入每日快照 _meta 块，为冷启动水化做准备；冲突守卫（ValueError，置于 try 之外确保不被吞掉）；MetaRecord 对应加字段（旧快照容忍缺失）；7 项断言含 mutation probe + 守卫判别性验证，Codex 两轮通过；feature `7a76bcb3`，`--no-ff` 合并 main @ `ffe9e1e2` 并推送 |
| Cockpit 冷启动水化 | ✅ | 重启后自动从最新日快照填充 Section A（含 key_signals / posture / confidence）和 Section C；双语 banner（bi()）；原子提交 + fail-closed；why_now crash guard；MacroRegimeAgent output / B / D / E 不从快照恢复；10 项测试，Codex 一轮通过，UI 人工验收 |
| **Phase 8B — Foundation Agent 实现（逐个推进）** | 🔄 进行中 | 已上线 MacroRegime / MoneyFlow / MarketStructure / SectorRotation / ThemeIntelligence 五个；**下一个 CandidateScreeningAgent（本体）——其确定性四态资格闸 enabler 已并入 main**；其后 StockResearch · TechnicalEntry · SectorResearch · RiskOverlay。每个：确定性信号 → ToolResult → 受约束提示（`REQUIRED OUTPUT FORMAT`）→ `_repair_llm_response` → 校验 `AgentOutput`；附加式 Cockpit 钩子 |
| **Phase 8C — PM 层** | 📋 计划 | `ShortTermPM` / `MidTermPM` / `LongTermPM` 按时间维度消费各 Foundation Agent 的 finding+confidence 做冲突仲裁（非汇总）→ `MasterPM` 跨时间维度 + 组合层综合、绝不出下单指令。**依赖：8B roster 足够填充** |
| **Phase 8D — ValuationDebateAgent / 证据基建** | 📋 计划 | 反向 DCF + 对抗式估值辩论 + 证据包；锚历史/迁移作为确定性输入。**依赖：估值基建 + 8B 个股研究组** |
| **Phase 9 — Judgment Console（人在环）** | 📋 远期 | 判断收口与人工确认工作流：LLM 在证据约束下给建议、人确认/覆写、判断来源留痕（provenance）、审计轨。**下游 gating 政策（自动化程度）仍待显式架构决策，尚未定型；依赖 8C/8D 累积输出** |
| **Phase 7D Block B — 判断绩效与校准** | 📋 计划 | 跨层比较 → 反馈环（推荐质量复盘）、判断绩效、PM 历史权重——**待足够 agent/PM 输出在快照中累积后**进行 |
| **Phase 6D — 持仓侧复核** | 📋 计划 | 按路线图既定顺序推进的 holdings-side review |
| 另类数据接入（持续）| 📋 远期 | 期权流/暗池作为**新增正交组件**叠加进脆弱度复合（非替换）；以快照对照验证领先性/误报率改善 |

---

## ⚠️ 免责声明 / Disclaimer

本系统及其所有输出内容（包括但不限于分析报告、图表、估值模型、AI 生成的文字）**仅供学习研究与技术展示使用**，不构成任何投资建议、买卖要约或投资推荐。本系统不接入任何券商、不执行任何交易（`approved_for_execution` 永远为 `False`）。

市场存在风险，过往表现不代表未来收益。在做出任何投资决策前，请咨询持牌的专业财务顾问。

---

All outputs from this system (including but not limited to reports, charts, valuation models, and AI-generated text) are **for research and educational purposes only** and do not constitute investment advice, an offer to buy or sell, or an investment recommendation. The system connects to no brokerage and executes no trades (`approved_for_execution` is permanently `False`).

Markets involve risk and past performance is not indicative of future results. Please consult a licensed financial advisor before making any investment decisions.

---

<div align="center">

Made with ☕ · Powered by [Claude](https://www.anthropic.com/) · Built for US Markets 🇺🇸

*Numbers by deterministic code · Evidence-bound judgment by LLM, confirmed by human · Review-only by design*

</div>
