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

**EN** · A personal investment operating system for US equities, evolved from a multi-agent research workflow into a full decision-support stack: opportunity ranking, dual-track signal engine, market-internals fragility monitoring, valuation anchoring, entry strategy, and thesis monitoring — all surfaced through an Investment Cockpit. Deterministic code computes every number; Claude handles language and reasoning. **Review-only by design: the system never places orders.**

**中** · 一个面向美股的个人投资操作系统。由最初的多 Agent 研究工作流，演进为完整的决策支持栈：机会排序、双轨信号引擎、市场内部结构（脆弱度）监控、估值锚定、入场策略与持仓 thesis 监控，统一汇聚于「投研中枢 / Investment Cockpit」。**所有数字由确定性代码计算，LLM 只负责语言与推理；系统设计上仅供审阅（review-only），永不下单。**

> ⚠️ **风险提示 / Disclaimer** · 本系统输出内容仅供学习与研究参考，不构成任何投资建议。All outputs are for research and educational purposes only and do not constitute investment advice.

---

## 🧭 设计原则 / Design Principles

这些原则在多个开发阶段中沉淀，并由测试不变量强制执行：

| 原则 | 含义 |
|---|---|
| **数字交给代码，语言交给 LLM** | 所有评分、估值、信号、阈值判断均为确定性 Python；LLM 不做数值推理，只做结构化分析与叙事 |
| **Review-only** | `approved_for_execution` 永远为 `False`；无券商接入；输出是研究队列，不是买入清单 |
| **Tighten-only（只收紧）** | 脆弱度层只收紧短线入场门槛、只做注释；永不翻转宏观 regime、永不放松任何门槛 |
| **单一数据 vintage** | 一次刷新内基准/标的/滚动序列同源同龄；跨源由 `data_vintage` / `vintage_mismatch` / `rs_stale` 守卫，静默过期结构性不可能 |
| **信号轨 / 审计轨分离** | 滚动重算（缓存行情的纯函数）回答「市场做了什么」并驱动迟滞；每日快照记录「系统当天说了什么」专司复盘审计 |
| **Parity 验证纪律** | 测试驱动真实刷新路径，断言 UI 渲染与快照 `_meta` 逐字段一致；快照每个字段要么绑定 UI surface 要么显式排除并注明理由 |
| **降级词汇表** | 每条数据不可用都有具体原因（`finnhub_unavailable` / `no_reports_in_window` / `partial_frame_coverage` / `implausible_count`…），监控组件永不静默消失 |

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
- ⚓ **估值锚体系** — forward 口径相对锚 + 分析师锚 + DCF，锚分歧 >3x 拒绝融合；锚缓存使 Cockpit 长线状态可分化
- 📒 **每日快照** — 全量候选 + 宏观/脆弱度 `_meta` 原子落盘（JSONL），审计轨 + 未来反馈环的数据地基
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

- **12+ 个可靠性测试套件、约 1,000+ 条断言**（`scripts/test_reliability_*.py`）：机会排序、估值止血、轮动与内部结构、交易台、入场策略、Cockpit 重建、渲染顺序、主题篮子等
- **不变量测试**：tighten-only（脆弱度强制 high 时 regime 对象逐字节不变）、宏观镜头永不改主题排名、排序路径零网络调用（结构化断言）
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
│   └── 9_Trading_Desk.py           # 交易台 — 入场策略 / 订单叙事 / thesis 监控
│
├── lib/
│   ├── llm_orchestrator.py         # Claude API 调用（LLM 层）
│   ├── opportunity_ranker.py       # 机会排序编排（三周期评分/状态/快照）
│   ├── signal_engine.py            # 双轨信号引擎 + Finnhub 财报日历
│   ├── candidate_generator.py      # 候选生成（发布扫描 universe）
│   ├── order_advisor.py            # 状态推导 / 入场策略 v4 / 条件注册表
│   ├── thesis_monitor.py           # 持仓 thesis 监控（噪音 vs 逻辑破坏）
│   ├── market_internals.py         # 脆弱度层（组件/复合/迟滞/滚动重算/vintage 守卫）
│   ├── macro_regime.py             # 宏观 regime 分类（frozen）
│   ├── relative_strength.py        # 多窗口 RS（日期对齐 + vintage 标记）
│   ├── rotation.py                 # GICS 外环：轮动评分 + 攻守读数
│   ├── theme_baskets.py            # AI 主题内环：超额动量/背离矩阵/广度
│   ├── equity_valuation.py         # 多锚估值融合 + 锚一致性门控
│   ├── valuation_anchor.py         # FairValueAnchor（forward 口径）
│   ├── anchor_cache.py             # 估值锚本地缓存（版本守卫/原子写）
│   ├── technical.py / data_fetcher.py / cache_manager.py / sectors.py
│   ├── valuation.py / financial_tab.py / pv_tab.py / report_writer.py
│   ├── workflow_state.py / translator.py
│   └── reliability/                # 可靠性基础设施（适配器层）
│
├── scripts/
│   ├── test_reliability_*.py       # 12+ 可靠性测试套件（~1,000+ 断言）
│   ├── calibrate_fragility_backfill.py  # 30 日脆弱度校准回填工具
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
| Thesis Ingestion MVP | 计划 | 人选稿、机器结构化：访谈/研报 → 带可证伪条件的 thesis 卡片 |
| Phase 7C / 7D | 计划 | 主题受益层级与跨层比较 → 反馈环（推荐质量复盘） |
| Phase 8 — Evidence Infrastructure | 计划 | 证据包 + 反向 DCF + 对抗式估值辩论 + 宏观 LLM 事件/归因 + IPO/流动性日历；首个「章节 agent」在此验证 |
| Phase 9 — Agent Synthesis Layer | 远期 | 章节 agent + orchestrator 综合层（agent 吃结构化判断、不碰原始数字；orchestrator 做冲突仲裁、不出操作指令） |
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

*Numbers by deterministic code · Language by LLM · Review-only by design*

</div>
