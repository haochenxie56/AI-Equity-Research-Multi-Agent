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

```
┌────────────────────────── Investment Cockpit（主入口）──────────────────────────┐
│                                                                                  │
│  宏观层                 主题层                  信号/排序层          执行参考层    │
│  macro_regime (frozen)  theme_baskets           signal_engine        order_advisor│
│  market_internals  ──►  rotation (两环)    ──►  candidate_generator  (entry v4)  │
│  (tighten-only,         阶段标签+广度确认       opportunity_ranker   thesis_     │
│   只收紧短线门槛)                               (三周期独立状态)      monitor     │
│                                                                                  │
│        ▼                       ▼                       ▼                  ▼      │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │   每日快照 data/snapshots/*.jsonl   ·   锚缓存 data/anchor_cache.json    │  │
│  │   （审计轨：系统当天说了什么）          （估值锚跨页共享）                  │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────┘
   排序/刷新路径 network-free（缓存行情纯函数）· 每步：代码层（数字）+ LLM 层（语言）
```

### 各 Agent 职责 / Agent Responsibilities

| Agent 定义文件 | 名称 | 核心职责 |
|---|---|---|
| `orchestrator.md` | Orchestrator | 意图理解、任务拆解、子 Agent 调度、结果整合 |
| `sector-research.md` | Sector Research | 宏观政策、产业链、行业景气度、ETF 趋势 |
| `stock-scanner.md` | Stock Scanner | 全市场筛选，四策略并行，输出候选标的 |
| `equity-research.md` | Equity Research | 商业模式、护城河、管理层、竞争格局 |
| `financial-analyst.md` | Financial Analyst | 三张表、DCF/相对估值、盈利质量分析 |
| `price-volume-analyst.md` | Price & Volume | 技术形态、资金流、RSI/MACD/ATR、情绪 |

> Agent 定义文件位于 `.claude/agents/`，由 Claude Code 在对话模式下调用。Streamlit 应用通过 `lib/llm_orchestrator.py` 直接调用 Claude API 执行自动化工作流。

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
| **数据 / Data** | [yfinance](https://github.com/ranaroussi/yfinance) (primary) · [Finnhub](https://finnhub.io/)（财报日历/预估）· [polygon.io](https://polygon.io/) (fallback) |
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
# Anthropic API Key（AI 工作流必需 / Required for AI workflow）
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Finnhub API Key（财报日历 → 「利好遭抛」组件；预估数据。强烈建议 / Strongly recommended）
FINNHUB_API_KEY=your_finnhub_api_key_here

# polygon.io API Key（备用数据源，可选 / Fallback data source, optional）
POLYGON_API_KEY=your_polygon_api_key_here
```

**获取 API Key / Getting API Keys：**
- Anthropic API → [console.anthropic.com](https://console.anthropic.com/)
- Finnhub（免费）→ [finnhub.io/register](https://finnhub.io/register)
- Polygon.io（免费套餐）→ [polygon.io/dashboard](https://polygon.io/dashboard)

> yfinance 为主数据源，**无需任何 API Key** 即可运行基础页面。AI 工作流需要 `ANTHROPIC_API_KEY`；缺少 `FINNHUB_API_KEY` 时财报反应组件按降级词汇表诚实降级，其余功能不受影响。

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
│   ├── technical.py / data_fetcher.py / cache_manager.py / sectors.py
│   ├── valuation.py / financial_tab.py / pv_tab.py / report_writer.py
│   ├── workflow_state.py / translator.py
│   └── reliability/                # 可靠性基础设施（适配器层）
│
├── scripts/
│   ├── test_reliability_*.py       # 69 个可靠性测试套件（数千条断言）
│   ├── calibrate_fragility_backfill.py  # 30 日脆弱度校准回填工具
│   ├── test_reliability_thesis_ingestion.py  # 71 项 thesis 卡摄入可靠性断言
│   ├── test_reliability_phase_7d_audit_query.py  # 快照审计查询 §7D.1–§7D.10（含导入图守卫）
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
│   └── snapshots/                  # opportunities_YYYYMMDD.jsonl（审计轨）
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
| Phase 7D（其余） | 计划 | 跨层比较 → 反馈环（推荐质量复盘） |
| Phase 8 — Evidence Infrastructure | 计划 | 证据包 + 反向 DCF + 对抗式估值辩论 + 宏观 LLM 事件/归因 + IPO/流动性日历；首个「章节 agent」在此验证 |
| Phase 9 — Agent Synthesis Layer | 远期 | 先做人在环 **Judgment Console**（判断收口页：LLM 在证据约束下给建议、人确认/覆写、来源留痕）→ 验证判断质量后逐步提高自动化；终态 = 章节 agent + orchestrator（agent 吃结构化判断、不碰原始数字；orchestrator 做冲突仲裁、不出操作指令） |
| 另类数据接入 | 远期 | 期权流/暗池作为**新增正交组件**叠加进脆弱度复合（非替换）；以快照对照验证领先性/误报率改善 |

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
