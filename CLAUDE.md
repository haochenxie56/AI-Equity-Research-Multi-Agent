# Investment Research Agent System

## 项目目标

构建一个多 agent 协作的美股投资研究系统，覆盖 NYSE 和 NASDAQ 上市公司。系统通过六个专业化子 agent 分工协作，完成从行业研究、标的筛选、个股深度分析、财务建模到量价技术分析的完整研究流程。

> **风险提示**：本系统输出的所有内容仅供投资研究与学习参考，不构成任何投资建议。市场存在风险，投资须谨慎。

---

## Agent 协作架构

```
用户指令
    │
    ▼
┌─────────────────┐
│   Orchestrator  │  总调度：理解意图、拆解任务、汇总输出
└────────┬────────┘
         │ 按需调用
    ┌────┴─────────────────────────────────────┐
    │         │           │          │         │
    ▼         ▼           ▼          ▼         ▼
 Sector   Scanner    Equity     Financial  Price/Volume
Research  (筛选)    Research   Analyst    Analyst
 (行业)            (个股深度)  (财务/估值) (技术/量价)
```

---

## 各 Agent 职责一览

| Agent 文件 | 名称 | 核心职责 |
|-----------|------|---------|
| `orchestrator.md` | Orchestrator | 任务拆解、子 agent 调度、结果整合 |
| `sector-research.md` | Sector Research | 宏观、政策、产业链、行业景气度 |
| `stock-scanner.md` | Stock Scanner | 全市场筛选，输出候选标的列表 |
| `equity-research.md` | Equity Research | 商业模式、护城河、管理层、竞争格局 |
| `financial-analyst.md` | Financial Analyst | 三张表、DCF/相对估值、同业对比 |
| `price-volume-analyst.md` | Price & Volume | 技术形态、资金流、市场情绪 |

---

## 共享约定

### Python 环境

- Python 3.11+
- 虚拟环境：`.venv/`（`python -m venv .venv && source .venv/bin/activate`）
- 依赖：`pip install -r requirements.txt`

### 数据源

| 用途 | 主数据源 | 备选数据源 |
|------|---------|-----------|
| 行情 / 财务数据 | yfinance | polygon.io REST API |
| 市场元数据 | yfinance | polygon.io |
| 财经新闻 / 事件 | yfinance news | 手动补充 |

- polygon.io API Key 通过环境变量 `POLYGON_API_KEY` 注入（`.env` 文件，不纳入版本控制）
- 本地缓存由 `lib/cache_manager.py` 统一管理，避免重复拉取

### 市场范围

- **仅限美股**：NYSE + NASDAQ
- Ticker 格式：标准美股 ticker symbol（如 `AAPL`、`MSFT`、`NVDA`）
- 货币单位：USD
- 交易时区：US/Eastern

### 文件命名规范

| 类型 | 格式 | 示例 |
|------|------|------|
| 行业报告 | `YYYYMMDD_sector_<name>.md` | `20260512_sector_semiconductors.md` |
| 个股报告 | `YYYYMMDD_<TICKER>_<type>.md` | `20260512_NVDA_equity.md` |
| 扫描结果 | `YYYYMMDD_scan_<strategy>.md` | `20260512_scan_momentum.md` |
| 缓存数据 | `<TICKER>_<type>_<YYYYMMDD>.parquet` | `AAPL_ohlcv_20260512.parquet` |

### 报告格式

所有报告均为 Markdown，包含以下固定节：

```markdown
# [报告标题]

**日期**：YYYY-MM-DD
**标的 / 行业**：TICKER or Sector Name
**分析师 Agent**：<agent-name>

## 执行摘要
（3-5 句话的核心结论）

## 正文分析
（各 agent 专属内容）

## 主要风险
（至少 3 条）

## 风险提示
本报告仅供研究参考，不构成投资建议。
```

---

## 目录结构

```
investment-agents/
├── CLAUDE.md                  # 本文件
├── requirements.txt
├── .env.example               # 环境变量模板
├── .claude/
│   └── agents/                # 子 agent 定义
├── lib/                       # 共享 Python 工具
│   ├── cache_manager.py       # 本地缓存管理
│   ├── data_fetcher.py        # 数据拉取统一接口
│   ├── valuation.py           # 估值模型
│   ├── technical.py           # 技术指标
│   └── report_writer.py       # 报告生成
├── data/
│   └── us/                    # 美股缓存数据
├── research/
│   ├── sector/                # 行业研究报告
│   ├── stock/                 # 个股深度报告
│   └── scans/                 # 扫描结果
└── scripts/
    ├── daily_scan.py
    ├── fetch_financials.py
    └── run_research.py
```
