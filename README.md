<div align="center">

# 📈 AI Equity Research — Multi-Agent System
### 美股多 Agent 投资研究系统

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.35%2B-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Anthropic](https://img.shields.io/badge/Claude-Agent_SDK-8B5CF6?logo=anthropic&logoColor=white)](https://www.anthropic.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![NYSE · NASDAQ](https://img.shields.io/badge/Market-NYSE%20%C2%B7%20NASDAQ-0052CC)](https://www.nyse.com/)

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/haochenxie56/AI-Equity-Research-Multi-Agent)
[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://YOUR-APP.streamlit.app)

</div>

---

**EN** · A multi-agent investment research platform for US equities (NYSE & NASDAQ), powered by Claude Agent SDK. Six specialized AI agents collaborate — from sector trends to price-volume technicals — delivering a full research workflow through an interactive Streamlit dashboard with dark/light theming.

**中** · 一个面向美股（NYSE & NASDAQ）的多 Agent 投资研究平台，基于 Claude Agent SDK 构建。六个专业化 AI Agent 协同工作，覆盖从行业趋势到量价技术分析的完整研究流程，通过 Streamlit 交互式仪表盘呈现，支持深色 / 浅色主题切换。

> ⚠️ **风险提示 / Disclaimer** · 本系统输出内容仅供学习与研究参考，不构成任何投资建议。All outputs are for research and educational purposes only and do not constitute investment advice.

---

## ✨ 功能特性 / Features

| 模块 / Module | 功能 / Description |
|---|---|
| 🔭 **总览 / Overview** | 一键启动完整研究流程，汇总六个子 Agent 结论 |
| 🏭 **行业研究 / Sector** | ETF 走势 + 自定义标的归一化收益对比，行业轮动分析 |
| 🔍 **选股扫描 / Scanner** | 动量/价值策略筛选自定义股票池，输出排序候选列表 |
| 🏢 **个股研究 / Equity** | 护城河雷达图、同业对比、AI 深度业务描述（中文翻译）|
| 📊 **财务分析 / Financial** | 三张表展示、DCF 多情景估值、相对估值同业对比 |
| 📉 **量价分析 / PriceVolume** | K 线 + RSI/MACD/ADX/布林带、盘前盘后行情、止损参考 |

**其他亮点 / Additional highlights：**
- 🌙 深色 / 浅色模式全局切换，CSS 变量驱动实时重渲染
- ⚡ 本地 Parquet 缓存层，避免重复 API 拉取
- 📄 各页面一键生成并下载 Markdown 研究报告
- 🤖 Claude Agent SDK 驱动六个专业化子 Agent，可独立调用或由 Orchestrator 统一调度

---

## 🏗️ 系统架构 / Architecture

### Agent 协作流程

```
User Request
     │
     ▼
┌────────────────────┐
│    Orchestrator    │  ← 任务理解 · 拆解 · 调度 · 汇总
│   (总调度 Agent)   │    Task routing & result synthesis
└─────────┬──────────┘
          │ spawns sub-agents on demand
    ┌─────┴──────────────────────────────────────┐
    │         │           │          │           │
    ▼         ▼           ▼          ▼           ▼
┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌─────────────┐
│ Sector │ │Scanner │ │Equity  │ │Finan-  │ │Price/Volume │
│Research│ │ 选股   │ │Research│ │cial    │ │  Analyst    │
│ 行业   │ │ 扫描   │ │ 个股   │ │Analyst │ │  量价分析   │
└────────┘ └────────┘ └────────┘ └────────┘ └─────────────┘
    │           │           │          │           │
    └───────────┴───────────┴──────────┴───────────┘
                            │
                            ▼
                   Consolidated Report
                     (Markdown / UI)
```

### 各 Agent 职责 / Agent Responsibilities

| Agent | 文件 / File | 核心职责 / Role |
|---|---|---|
| **Orchestrator** | `orchestrator.md` | 意图理解、任务拆解、子 Agent 调度、结果整合 |
| **Sector Research** | `sector-research.md` | 宏观政策、产业链、行业景气度、ETF 趋势 |
| **Stock Scanner** | `stock-scanner.md` | 全市场筛选，动量/价值策略，输出候选标的 |
| **Equity Research** | `equity-research.md` | 商业模式、护城河、管理层、竞争格局 |
| **Financial Analyst** | `financial-analyst.md` | 三张表、DCF/相对估值、盈利质量分析 |
| **Price & Volume** | `price-volume-analyst.md` | 技术形态、资金流、RSI/MACD/ATR、情绪 |

---

## 🛠️ 技术栈 / Tech Stack

| 层级 / Layer | 技术 / Technology |
|---|---|
| **AI / Agents** | [Anthropic Claude API](https://www.anthropic.com/) · Claude Agent SDK · Claude Code |
| **Web UI** | [Streamlit](https://streamlit.io/) 1.35+ · CSS Variables (dark/light theming) |
| **数据 / Data** | [yfinance](https://github.com/ranaroussi/yfinance) (primary) · [polygon.io](https://polygon.io/) (fallback) |
| **可视化 / Charts** | [Plotly](https://plotly.com/python/) · mplfinance |
| **分析 / Analysis** | pandas · numpy · scipy · pandas-ta |
| **存储 / Storage** | Apache Parquet (pyarrow) · local cache manager |
| **翻译 / Translation** | deep-translator (Google Translate, no API key) |
| **运行环境 / Runtime** | Python 3.11+ · WSL2 (Ubuntu) / Linux |

---

## 🚀 一键部署 / One-Click Deploy

| 平台 / Platform | 操作 / Action | 说明 / Notes |
|---|---|---|
| **GitHub Codespaces** | [![Open in Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/haochenxie56/AI-Equity-Research-Multi-Agent) | 浏览器内完整开发环境，自动安装依赖并启动 Streamlit |
| **Streamlit Cloud** | [![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://YOUR-APP.streamlit.app) | 部署完成后替换链接 / Replace link after deployment |

> **Codespaces 首次启动约需 2-3 分钟**安装依赖，之后端口 8501 自动打开。
> 在 [GitHub Codespace Secrets](https://github.com/settings/codespaces) 中配置 `ANTHROPIC_API_KEY` 和 `POLYGON_API_KEY`。

---

## 📸 截图 / Screenshots

> 📌 *Screenshots will be added here — dark mode and light mode examples for each of the six analysis pages.*

<!-- Dark Mode -->
<!-- ![Overview Dark](docs/screenshots/overview_dark.png) -->

<!-- Light Mode -->
<!-- ![Overview Light](docs/screenshots/overview_light.png) -->

<!-- Financial Analysis -->
<!-- ![Financial](docs/screenshots/financial.png) -->

<!-- Price & Volume -->
<!-- ![PriceVolume](docs/screenshots/pricevolume.png) -->

---

## 🚀 本地运行 / Quick Start (WSL / Linux)

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

> **Ubuntu / WSL 提示**：若遇到 `externally-managed-environment` 错误，添加 `--break-system-packages` 参数，或使用虚拟环境：
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

```bash
streamlit run app.py
```

浏览器访问 → `http://localhost:8501`

---

## 🔑 环境变量配置 / Environment Variables

参考 `.env.example`：

```env
# polygon.io API Key（备用数据源，可选）
POLYGON_API_KEY=your_polygon_api_key_here

# Anthropic API Key（Agent 功能必需）
ANTHROPIC_API_KEY=your_anthropic_api_key_here
```

**获取 API Key / Getting API Keys：**
- Polygon.io（免费套餐够用）→ [polygon.io/dashboard](https://polygon.io/dashboard)
- Anthropic API → [console.anthropic.com](https://console.anthropic.com/)

> yfinance 为主数据源，**无需任何 API Key** 即可运行基础功能。
> yfinance is the primary data source and requires **no API key** for core features.

---

## 📁 项目结构 / Project Structure

```
investment-agents/
├── app.py                      # 主页 / Home page (entry point)
├── ui_utils.py                 # 共享工具：主题、图表、数据加载、格式化
├── requirements.txt
├── .env.example                # 环境变量模板
│
├── pages/                      # Streamlit 多页面
│   ├── 1_总览.py               # Overview — orchestrator dashboard
│   ├── 2_行业研究.py           # Sector Research — ETF + peer comparison
│   ├── 3_选股扫描.py           # Stock Scanner — momentum / value screen
│   ├── 4_个股研究.py           # Equity Research — moat radar + comps
│   ├── 5_财务分析.py           # Financial Analysis — 3 statements + DCF
│   └── 6_量价分析.py           # Price & Volume — candlestick + technicals
│
├── .claude/
│   └── agents/                 # Claude sub-agent definitions (Markdown)
│       ├── orchestrator.md
│       ├── sector-research.md
│       ├── stock-scanner.md
│       ├── equity-research.md
│       ├── financial-analyst.md
│       └── price-volume-analyst.md
│
├── lib/                        # 共享 Python 工具库
│   ├── cache_manager.py        # Parquet 本地缓存管理
│   ├── data_fetcher.py         # 数据拉取统一接口（yfinance + polygon.io）
│   ├── technical.py            # 技术指标计算（SMA/RSI/MACD/ATR/ADX/BB）
│   ├── valuation.py            # DCF 估值模型 + WACC 计算
│   └── report_writer.py        # Markdown 报告生成
│
├── scripts/
│   ├── daily_scan.py           # 每日自动扫描脚本
│   ├── fetch_financials.py     # 批量拉取财务数据
│   └── run_research.py         # 命令行启动完整研究流程
│
├── data/                       # 本地 Parquet 缓存（git-ignored）
│   └── us/
│
├── research/                   # 生成的研究报告（git-ignored）
│   ├── sector/
│   ├── stock/
│   └── scans/
│
└── .streamlit/
    └── config.toml             # Streamlit 主题配置
```

---

## ⚠️ 免责声明 / Disclaimer

本系统及其所有输出内容（包括但不限于分析报告、图表、估值模型、AI Agent 生成的文字）**仅供学习研究与技术展示使用**，不构成任何投资建议、买卖要约或投资推荐。

市场存在风险，过往表现不代表未来收益。在做出任何投资决策前，请咨询持牌的专业财务顾问。

---

All outputs from this system (including but not limited to reports, charts, valuation models, and AI-generated text) are **for research and educational purposes only** and do not constitute investment advice, an offer to buy or sell, or an investment recommendation.

Markets involve risk and past performance is not indicative of future results. Please consult a licensed financial advisor before making any investment decisions.

---

<div align="center">

Made with ☕ · Powered by [Claude](https://www.anthropic.com/) · Built for US Markets 🇺🇸

</div>
