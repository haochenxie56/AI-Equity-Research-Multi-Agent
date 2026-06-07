<div align="center">

# 📈 AI Investment OS — Multi-Agent US Equity Research
### 美股多 Agent 投资决策系统

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.35%2B-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Anthropic](https://img.shields.io/badge/Claude-API-8B5CF6?logo=anthropic&logoColor=white)](https://www.anthropic.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![NYSE · NASDAQ](https://img.shields.io/badge/Market-NYSE%20%C2%B7%20NASDAQ-0052CC)](https://www.nyse.com/)

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/haochenxie56/AI-Equity-Research-Multi-Agent)

</div>

---

**EN** · A multi-agent investment decision platform for US equities (NYSE & NASDAQ), powered by Claude API. Goes beyond a research dashboard — the system autonomously discovers opportunities, monitors thesis integrity, computes fair value through agent debate, and generates horizon-aware trade recommendations with entry zones, stop-loss levels, and position sizing. Full bilingual (EN/ZH) support with dark/light theming.

**中** · 一个面向美股（NYSE & NASDAQ）的多 Agent 投资决策平台，基于 Claude API 构建。不止是研究仪表盘——系统能自主发现机会、监控投资逻辑完整性、通过 Agent 辩论计算合理估值，并生成包含入场区间、止损位和仓位建议的分周期交易推荐。支持中英双语切换与深色/浅色主题。

> ⚠️ **风险提示 / Disclaimer** · 本系统输出内容仅供学习与研究参考，不构成任何投资建议。All outputs are for research and educational purposes only and do not constitute investment advice.

---

## ✨ 核心功能 / Core Features

### 决策层 / Decision Layer

| 页面 / Page | 功能 / Description |
|---|---|
| 🧭 **投研中枢 / Investment Cockpit** | 一键刷新全链路数据（宏观→主题→选股→估值）；展示三线共振信号、市场主题热度、个股估值结论；统一调度所有研究模块 |
| 📋 **交易台 / Trading Desk** | 持仓监控（Thesis Invalidation Monitor）；按 Short/Mid/Long 三周期独立计算入场区间、止损位、仓位建议；Agent 辩论驱动的订单叙述 |

### 研究层 / Research Layer

| 页面 / Page | 功能 / Description |
|---|---|
| 🌐 **宏观仪表盘 / Macro Dashboard** | 实时宏观指标（VIX、利率曲线、信用利差、美元、ETF 收益、经济数据）；确定性规则引擎输出 risk_on/off/transition regime 及三周期 horizon bias |
| 🏭 **行业研究 / Sector Research** | 传统 GICS 行业分析 + 12 个跨 GICS AI 产业链主题篮子（GPU/HBM/光模块/数据中心/AI 电力等）；主题动量排名；LLM 主题叙事与 macro 对齐分析 |
| 🔍 **选股扫描 / Stock Scanner** | 双轨架构：Track A（四层漏斗：硬筛选→LLM 叙事匹配→基本面定量→入场质量评分）+ Track B（另类信号：Insider 买入、异常新闻、分析师上调）；三周期独立评分（Short/Mid/Long）；三线共振高亮 |
| 🏢 **个股研究 / Equity Research** | 护城河雷达图、同业对比、AI 深度研究报告；AI 估值综合（DCF + 相对估值 + 分析师目标价三源合并）；Bull/Bear/Risk Agent 辩论；估值结论直通交易台 |
| 📊 **财务分析 / Financial Analysis** | 三张表展示、多情景 DCF 估值、EV/EBITDA/P/S 同业对比；DCF 结果可更新至 AI 估值综合 |
| 📉 **量价分析 / Price & Volume** | K 线 + RSI/MACD/ADX/布林带；支撑压力位识别；技术指标直接输入入场区间计算 |

---

## 🏗️ 系统架构 / Architecture

### 数据流 / Data Flow

```
宏观仪表盘                行业研究                  选股扫描
Macro Dashboard  ──►   Sector Research  ──►    Stock Scanner
(regime + bias)      (主题热度 + 成分股)      (双轨信号 + 三周期评分)
      │                                               │
      └──────────────► 投研中枢 ◄────────────────────┘
                    Investment Cockpit
                   (一键刷新 + 信号汇总)
                          │
                          ▼
                   个股研究 + 估值
                   Equity Research
                (DCF + 相对估值 + Agent辩论)
                          │
                          ▼
                      交易台
                   Trading Desk
              (持仓监控 + 订单建议 + 机会看板)
```

### 选股信号架构 / Signal Architecture

```
Universe (S&P 500 top 100 + 12个主题篮子成分股, 上限可调)
         │
         ▼ Track A — 四层漏斗
Layer 1: 硬筛选（市值/流动性/数据可用性）
         │
Layer 2: LLM 叙事匹配（主题归属 + 叙事阶段 early/growing/mature/cooling + Catalyst）
         │
Layer 3: 基本面定量（EPS revision 方向 + 估值分位 + 毛利趋势 + 质量评分）
         │
Layer 4: 入场质量（RSI位置 + 均线距离 + ADX趋势强度）
         │
         ├── Short Score (EMA + 量价硬门槛 + Catalyst)
         ├── Mid Score   (EPS revision + 叙事阶段 + 估值)
         └── Long Score  (估值分位 + 业务质量 + 叙事早期)

         Track B — 另类信号（独立评分）
         ├── Insider 净买入（Finnhub）
         ├── 异常新闻关键词（政府合同/FDA批准/重大合作）
         └── 分析师评级上调

三线共振 (Short + Mid + Long 同时命中) → 投研中枢高优先级 + 交易台直通
```

### 入场区间逻辑 / Entry Zone Logic (Entry Strategy v4)

```
Short:  EMA10 + EMA21 趋势确认（硬门槛）→ dynamic_support ± ATR
Mid:    量价状态三档（healthy/neutral/unhealthy）→ SMA50 ± ATR 动态调整
Long:   三级估值置信度（high/medium/low）→ conservative_anchor × 0.85~0.90

加仓 vs 建仓:
  SHORT: 亏损仓位禁止摊低（wait_or_cut）
  MID:   thesis intact 时可小幅摊低
  LONG:  thesis intact + 估值更便宜时可分批摊低
  止损均基于技术面（ATR/均线），不使用成本价
```

---

## 🤖 AI 架构原则 / AI Architecture Principles

> **数字交给代码，语言交给 Claude**
> *"Facts from tools; interpretation from agents"*

| 层级 | 职责 | 实现 |
|---|---|---|
| **数据层** | 行情、财务、技术指标、宏观数据获取 | yfinance / Finnhub / FRED API |
| **计算层** | 所有定量计算（DCF、ATR、RSI、评分、仓位）| Python 确定性代码 |
| **验证层** | 入场门槛、止损约束、仓位上限 | 硬编码规则，不可被 LLM 覆盖 |
| **LLM 层** | 叙事归属、Agent 辩论、订单语言解释 | Claude API（仅处理语义，不做数值计算）|
| **双语层** | 所有 LLM 输出即时生成 EN/ZH 两版 | 单次 API 调用，切换语言无需重调用 |

**关键约束 / Key Constraints：**
- `approved_for_execution` 始终 `False` — 系统不下单，不接券商 API
- LLM 不计算任何数值 — 止损、入场价、仓位均由代码确定性计算
- 所有输出为 review-only — 用户手动在券商执行

---

## 🛠️ 技术栈 / Tech Stack

| 层级 / Layer | 技术 / Technology |
|---|---|
| **AI** | [Anthropic Claude API](https://www.anthropic.com/) (`claude-sonnet-4-6`) |
| **Web UI** | [Streamlit](https://streamlit.io/) 1.35+ · CSS Variables |
| **市场数据** | [yfinance](https://github.com/ranaroussi/yfinance) (主) · [Finnhub](https://finnhub.io/) (新闻/情绪/Insider) · [FRED API](https://fred.stlouisfed.org/) (宏观) |
| **可视化** | [Plotly](https://plotly.com/python/) |
| **技术分析** | `lib/technical.py` (EMA/SMA/RSI/ADX/ATR/布林带/支撑压力位/K线形态) |
| **存储** | Apache Parquet · `data/holdings.json` (持仓持久化) |
| **运行环境** | Python 3.11+ · WSL2 (Ubuntu) / Linux / macOS |

---

## 🚀 快速开始 / Quick Start

### 1. 克隆项目

```bash
git clone https://github.com/haochenxie56/AI-Equity-Research-Multi-Agent.git
cd AI-Equity-Research-Multi-Agent
```

### 2. 安装依赖

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`：

```env
# 必需 / Required
ANTHROPIC_API_KEY=your_anthropic_api_key

# 推荐 / Recommended（宏观数据免费）
FRED_API_KEY=your_fred_api_key          # fred.stlouisfed.org 免费注册

# 可选 / Optional
FINNHUB_API_KEY=your_finnhub_api_key    # finnhub.io 免费 tier
POLYGON_API_KEY=your_polygon_api_key    # 备用行情数据源
```

**获取 API Key：**
- Anthropic → [console.anthropic.com](https://console.anthropic.com/)
- FRED（免费）→ [fred.stlouisfed.org/docs/api/api_key.html](https://fred.stlouisfed.org/docs/api/api_key.html)
- Finnhub（免费）→ [finnhub.io/register](https://finnhub.io/register)

> **最小配置：** 仅 `ANTHROPIC_API_KEY` 即可运行所有 AI 功能，宏观仪表盘降级为 fixture 数据，行情数据通过 yfinance 免费获取。

### 4. 启动应用

#### 🪟 Windows（WSL2）

双击 `launch.vbs` — 自动检测端口 → 启动 Streamlit → 打开浏览器

#### 🍎 macOS / 🐧 Linux

```bash
streamlit run app.py
```

浏览器访问 `http://localhost:8501`

---

## 📁 项目结构 / Project Structure

```
investment-agents/
├── app.py                        # 主页入口
├── ui_utils.py                   # 全局工具：主题/双语/sidebar/图表
├── requirements.txt
│
├── pages/
│   ├── 1_Overview.py             # Legacy AI 工作流（保留，已从 sidebar 移除）
│   ├── 2_Sector.py               # 行业研究 + 12个主题篮子
│   ├── 3_Scanner.py              # 双轨选股 + 三周期信号
│   ├── 4_Equity.py               # 个股研究 + AI 估值综合 + Agent 辩论
│   ├── 5_Financial.py            # 财务分析（个股研究子模块）
│   ├── 6_PriceVolume.py          # 量价分析（个股研究子模块）
│   ├── 7_Investment_Cockpit.py   # 投研中枢（主入口）
│   ├── 8_Macro_Dashboard.py      # 宏观仪表盘
│   └── 9_Trading_Desk.py         # 交易台
│
├── lib/
│   ├── llm_orchestrator.py       # 所有 LLM 调用（双语输出）
│   ├── signal_engine.py          # 双轨信号评分 + 三周期评分
│   ├── candidate_generator.py    # Universe 构建 + 候选生成
│   ├── theme_baskets.py          # 12个主题篮子定义 + 动量计算
│   ├── order_advisor.py          # 入场区间 + 止损 + 仓位建议（Entry Strategy v4）
│   ├── equity_valuation.py       # AppFairValue（DCF + 相对 + 分析师三源合并）
│   ├── valuation_anchor.py       # 估值置信度（high/medium/low）
│   ├── thesis_monitor.py         # Thesis Invalidation Monitor（四维检测）
│   ├── holdings.py               # 持仓 CRUD + PortfolioSettings
│   ├── macro_data.py             # 宏观数据 fetch（FRED/yfinance/Finnhub）
│   ├── macro_regime.py           # 确定性 regime 分类引擎
│   ├── macro_state.py            # Regime 序列化/持久化工具
│   ├── technical.py              # 技术指标快照
│   ├── rotation.py               # 行业轮动评分
│   ├── financial_tab.py          # 财务页面组件
│   ├── pv_tab.py                 # 量价页面组件
│   ├── translator.py             # 翻译工具（fallback）
│   └── workflow_state.py         # Legacy 工作流状态管理
│
├── scripts/
│   └── test_reliability_*.py     # 各 phase 的 mock-only 测试套件
│
├── data/
│   ├── holdings.json             # 持仓数据 + 组合设置 + 现金仓位
│   └── us/                       # Parquet 行情缓存
│
├── .claude/agents/               # Claude Code 子 Agent 定义
└── .streamlit/config.toml
```

---

## 📊 典型使用流程 / Typical Workflow

```
1. 打开投研中枢 → 点击「一键刷新」
   → 自动拉取宏观数据、计算主题热度、生成候选信号

2. 查看信号候选 → 关注三线共振标的（Short + Mid + Long 同时命中）
   → 点击「加入交易台」

3. 前往个股研究 → 输入 ticker
   → 查看 AI 估值综合（DCF + 相对估值 + 分析师目标价）
   → 运行 AI 多空辩论 → 发送至交易台

4. 打开交易台
   → 持仓监控：查看 Thesis 状态（intact/watch/weakening/broken）
   → 订单建议：查看入场区间、止损位、建议仓位
   → 机会看板：查看来自投研中枢的候选信号

5. 手动在券商执行订单
   → 系统不下单，不接券商 API
```

---

## 🔄 Thesis Invalidation Monitor

交易台对每笔持仓持续监测四个维度：

| 信号 | 数据源 | 触发条件 |
|---|---|---|
| 新闻情绪 | Finnhub + LLM | 负面新闻且与 thesis 相关 |
| EPS Revision | Finnhub | 方向从 improving 转 deteriorating |
| 技术面破位 | yfinance | 跌破 SMA200 / RSI < 30 / ADX 下行 |
| 宏观 Regime 变化 | Macro Dashboard | risk_on → risk_off（Short/Mid 持仓） |

**Thesis 状态：**
- 🟢 `intact` — 无信号触发
- 🟡 `watch` — 1 个信号触发
- 🟠 `weakening` — 2 个信号触发
- 🔴 `broken` — 3+ 个信号 / 技术破位 / 相关负面新闻

> 系统区分「价格回调」（正常波动，above SMA200 + RSI 35-50）与「Thesis 破坏」（真实风险），避免在正常震仓中被洗出。

---

## ⚠️ 免责声明 / Disclaimer

本系统及其所有输出内容（包括但不限于分析报告、图表、估值模型、AI 生成文字、入场区间、止损建议）**仅供学习研究与技术展示使用**，不构成任何投资建议、买卖要约或投资推荐。系统不接入任何券商 API，不执行任何交易。

市场存在风险，过往表现不代表未来收益。在做出任何投资决策前，请咨询持牌的专业财务顾问。

---

All outputs from this system (including but not limited to reports, charts, valuation models, AI-generated text, entry zones, and stop-loss suggestions) are **for research and educational purposes only** and do not constitute investment advice, an offer to buy or sell, or an investment recommendation. The system does not connect to any brokerage API and does not execute any trades.

Markets involve risk and past performance is not indicative of future results. Please consult a licensed financial advisor before making any investment decisions.

---

<div align="center">

Made with ☕ · Powered by [Claude](https://www.anthropic.com/) · Built for US Markets 🇺🇸

</div>
