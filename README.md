<div align="center">

# 📈 AI Equity Research — Multi-Agent System
### 美股多 Agent 投资研究系统

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.35%2B-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Anthropic](https://img.shields.io/badge/Claude-API-8B5CF6?logo=anthropic&logoColor=white)](https://www.anthropic.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![NYSE · NASDAQ](https://img.shields.io/badge/Market-NYSE%20%C2%B7%20NASDAQ-0052CC)](https://www.nyse.com/)

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/haochenxie56/AI-Equity-Research-Multi-Agent)

</div>

---

**EN** · A multi-agent investment research platform for US equities (NYSE & NASDAQ), powered by Claude API. An AI-driven 5-step workflow automatically selects sectors, screens stocks, and produces a comprehensive research report — all through an interactive Streamlit dashboard with full bilingual (EN/ZH) support and dark/light theming.

**中** · 一个面向美股（NYSE & NASDAQ）的多 Agent 投资研究平台，基于 Claude API 构建。AI 驱动的五步自动化研究工作流，从行业筛选到量价分析一键完成，通过 Streamlit 交互式仪表盘呈现，支持中英双语切换与深色/浅色主题。

> ⚠️ **风险提示 / Disclaimer** · 本系统输出内容仅供学习与研究参考，不构成任何投资建议。All outputs are for research and educational purposes only and do not constitute investment advice.

---

## ✨ 功能特性 / Features

| 页面 / Page | 功能 / Description |
|---|---|
| 🤖 **AI 工作流 / Overview** | 一键启动五步自动化研究流程，LLM 自主完成行业选择 → 选股扫描 → 个股分析 → 财务评估 → 技术分析，最终生成综合投资结论 |
| 🏭 **行业研究 / Sector** | 六维行业分析（宏观/轮动/动量/ETF/资金流/子板块）、ETF 归一化收益对比、行业轮动热力图 |
| 🔍 **选股扫描 / Scanner** | 四策略并行扫描（动量/价值/质量成长/超卖反弹），AI 跨策略评估选出最优标的 |
| 🏢 **个股研究 / Equity** | 护城河雷达图、同业对比、AI 深度研究（业务模式/竞争格局/管理层评估）|
| 📊 **财务分析 / Financial** | 三张表展示、DCF 多情景估值、EV/EBITDA/P/S 相对估值同业对比 |
| 📉 **量价分析 / PriceVolume** | K 线 + RSI/MACD/ADX/布林带叠加，支撑压力位，止损参考 |

**其他亮点 / Additional highlights：**
- 🌐 **中英双语** — LLM 分析生成时即产出中英双语版本，语言切换即时生效，无需重新调用 AI
- 🌙 **深色/浅色主题** — CSS 变量驱动全局主题切换
- ⚡ **本地 Parquet 缓存** — 避免重复拉取行情数据，降低 API 消耗
- 📄 **研究报告导出** — 各分析页面支持一键生成 Markdown 研究报告

---

## 🏗️ 系统架构 / Architecture

### AI 研究工作流（五步全自动）

```
┌──────────────────────────────────────────────────────────┐
│                   Overview (AI Workflow)                  │
│                                                          │
│  Step 1          Step 2         Step 3                   │
│  行业分析  ──►  选股扫描  ──►  个股研究                  │
│  Sector         4-Strategy      Equity                   │
│  Analysis       Scan            Research                 │
│                                     │                    │
│                              Step 4 ▼  Step 5            │
│                              财务分析 ──► 量价分析        │
│                              Financial    PriceVolume    │
│                                               │          │
│                              ┌────────────────▼────────┐ │
│                              │  综合结论 / Synthesis   │ │
│                              │  recommendation + risks │ │
│                              └─────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
         │ each step: code layer (quantitative) +
         │            LLM layer (Claude API, JSON)
         ▼
   workflow_state.json  (persisted between sessions)
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

## 🛠️ 技术栈 / Tech Stack

| 层级 / Layer | 技术 / Technology |
|---|---|
| **AI** | [Anthropic Claude API](https://www.anthropic.com/) (`claude-sonnet-4-6`) · `lib/llm_orchestrator.py` |
| **Web UI** | [Streamlit](https://streamlit.io/) 1.35+ · CSS Variables (dark/light theming) |
| **数据 / Data** | [yfinance](https://github.com/ranaroussi/yfinance) (primary) · [polygon.io](https://polygon.io/) (fallback) |
| **可视化 / Charts** | [Plotly](https://plotly.com/python/) |
| **技术分析 / TA** | [ta](https://github.com/bukosabino/ta) (SMA/EMA/RSI/MACD/ADX/Bollinger Bands) |
| **存储 / Storage** | Apache Parquet (pyarrow) · `lib/cache_manager.py` |
| **状态管理 / State** | `lib/workflow_state.py` · JSON persistence (`research/.workflow_state.json`) |
| **双语翻译 / I18n** | [deep-translator](https://github.com/nidhaloff/deep-translator) · `lib/translator.py` (Google Translate, no API key) |
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

浏览器访问 → `http://localhost:8501`

---

## 🔑 环境变量 / Environment Variables

参考 `.env.example`：

```env
# Anthropic API Key（AI 工作流必需 / Required for AI workflow）
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# polygon.io API Key（备用数据源，可选 / Fallback data source, optional）
POLYGON_API_KEY=your_polygon_api_key_here

# Finnhub API Key（新闻情绪分析，可选 / News sentiment, optional）
FINNHUB_API_KEY=your_finnhub_api_key_here
```

**获取 API Key / Getting API Keys：**
- Anthropic API → [console.anthropic.com](https://console.anthropic.com/)
- Polygon.io（免费套餐）→ [polygon.io/dashboard](https://polygon.io/dashboard)
- Finnhub（免费）→ [finnhub.io/register](https://finnhub.io/register)

> yfinance 为主数据源，**无需任何 API Key** 即可运行基础功能（行业/个股/财务/量价页面）。AI 工作流页面需要 `ANTHROPIC_API_KEY`。

---

## 📁 项目结构 / Project Structure

```
investment-agents/
├── app.py                      # 主页 / Home page (Streamlit entry point)
├── ui_utils.py                 # 共享工具：主题、图表、数据加载、bi() 双语读取
├── requirements.txt
├── packages.txt                # Streamlit Cloud 系统依赖
├── .env.example                # 环境变量模板
│
├── pages/                      # Streamlit 多页面应用
│   ├── 1_Overview.py           # AI 研究工作流 — 五步全自动 + 综合结论
│   ├── 2_Sector.py             # 行业研究 — 六维分析 + ETF 对比 + 轮动
│   ├── 3_Scanner.py            # 选股扫描 — 四策略筛选 + AI 选股
│   ├── 4_Equity.py             # 个股研究 — 护城河 + 同业对比 + AI 深度研究
│   ├── 5_Financial.py          # 财务分析 — 三张表 + DCF + 相对估值
│   └── 6_PriceVolume.py        # 量价分析 — K 线 + 多指标叠加
│
├── lib/                        # 共享 Python 工具库
│   ├── llm_orchestrator.py     # Claude API 调用：六个 LLM 分析函数 + _llm_json_call
│   ├── workflow_state.py       # 五步工作流状态管理（session + JSON 持久化）
│   ├── translator.py           # 双语支持：add_bilingual() / translate_str_list()
│   ├── sectors.py              # 行业配置：GICS / ETF 主题 / 自定义股票池
│   ├── rotation.py             # 行业轮动评分、动量计算、选股排名
│   ├── technical.py            # 技术指标快照：RSI/ADX/SMA/Vol_ratio
│   ├── data_fetcher.py         # 数据拉取统一接口（yfinance + polygon.io）
│   ├── cache_manager.py        # Parquet 本地缓存管理
│   ├── valuation.py            # DCF 估值模型 + WACC 计算
│   ├── financial_tab.py        # 财务页面组件（图表 + 指标卡）
│   ├── pv_tab.py               # 量价页面组件（K 线 + 技术指标叠加）
│   └── report_writer.py        # Markdown 研究报告生成
│
├── .claude/
│   └── agents/                 # Claude Code 子 Agent 定义（Markdown）
│       ├── orchestrator.md
│       ├── sector-research.md
│       ├── stock-scanner.md
│       ├── equity-research.md
│       ├── financial-analyst.md
│       └── price-volume-analyst.md
│
├── scripts/
│   ├── daily_scan.py           # 每日自动扫描脚本
│   ├── fetch_financials.py     # 批量拉取财务数据
│   └── run_research.py         # 命令行启动完整研究流程
│
├── data/                       # 本地 Parquet 缓存（git-ignored）
│   └── us/
│
├── research/                   # 工作流状态 + 生成报告（git-ignored）
│   ├── .workflow_state.json    # 五步工作流持久化状态
│   ├── sector/
│   ├── stock/
│   └── scans/
│
└── .streamlit/
    └── config.toml             # Streamlit 主题配置
```

---

## 🔄 AI 工作流详解 / AI Workflow

Overview 页面实现五步全自动研究，每步包含**代码层**（量化计算）和 **LLM 层**（Claude 分析）：

| 步骤 | 代码层 | LLM 层 |
|---|---|---|
| **Step 1 行业分析** | 计算 11 个 GICS 行业的轮动评分（动量/RSI/资金流/超额收益）| 六维结构化分析（宏观/轮动/动量/ETF/资金/子板块），输出行业决策 |
| **Step 2 选股扫描** | 四策略（动量/价值/质量成长/超卖反弹）对子板块 ETF 持仓扫描 | 跨策略综合评估，选出 1-5 支最优标的 |
| **Step 3 个股研究** | 拉取价格快照、分析师评级、新闻 | 商业模式/护城河/管理层/竞争格局分析 |
| **Step 4 财务分析** | 三张表 TTM 数据、估值倍数 | 盈利质量、FCF 转化、估值合理性评估 |
| **Step 5 量价分析** | RSI/ADX/SMA/成交量比等技术指标快照 | 趋势强度、动量方向、买卖时机判断 |
| **综合结论** | 汇总五步输出 | 生成综合建议 + 风险提示 |

所有 LLM 输出在生成时即产出中英双语（`field_en` / `field_zh`），语言切换无需重新调用 API。

---

## 📸 截图 / Screenshots

> 📌 *Screenshots will be added — dark/light mode examples for each page.*

---

## ⚠️ 免责声明 / Disclaimer

本系统及其所有输出内容（包括但不限于分析报告、图表、估值模型、AI 生成的文字）**仅供学习研究与技术展示使用**，不构成任何投资建议、买卖要约或投资推荐。

市场存在风险，过往表现不代表未来收益。在做出任何投资决策前，请咨询持牌的专业财务顾问。

---

All outputs from this system (including but not limited to reports, charts, valuation models, and AI-generated text) are **for research and educational purposes only** and do not constitute investment advice, an offer to buy or sell, or an investment recommendation.

Markets involve risk and past performance is not indicative of future results. Please consult a licensed financial advisor before making any investment decisions.

---

<div align="center">

Made with ☕ · Powered by [Claude](https://www.anthropic.com/) · Built for US Markets 🇺🇸

</div>
