# Investment Research Agent System

## Project Goal

Build a multi-agent collaborative US equity research system covering NYSE and
NASDAQ listed companies. Six specialized sub-agents divide responsibilities to
deliver a complete research workflow spanning sector analysis, candidate
screening, individual stock deep-dive, financial modeling, and price/volume
technical analysis.

> **Disclaimer**: All output from this system is for investment research and
> educational purposes only. It does not constitute investment advice. Markets
> involve risk; invest with caution.

---

## Agent Collaboration Architecture

```
User Instruction
      │
      ▼
┌─────────────────┐
│   Orchestrator  │  Master dispatcher: understand intent, decompose tasks, synthesize output
└────────┬────────┘
         │ delegates as needed
    ┌────┴──────────────────────────────────────┐
    │         │           │          │          │
    ▼         ▼           ▼          ▼          ▼
 Sector   Scanner    Equity     Financial  Price/Volume
Research  (screen)  Research   Analyst    Analyst
(sector)           (deep-dive) (fin/val)  (technical)
```

---

## Agent Responsibilities

| Agent File | Name | Core Responsibility |
|-----------|------|---------------------|
| `orchestrator.md` | Orchestrator | Task decomposition, sub-agent dispatch, result integration |
| `sector-research.md` | Sector Research | Macro, policy, supply chain, sector cycle assessment |
| `stock-scanner.md` | Stock Scanner | Full-market screening; outputs candidate ticker list |
| `equity-research.md` | Equity Research | Business model, moat, management, competitive landscape |
| `financial-analyst.md` | Financial Analyst | 3-statement model, DCF / relative valuation, peer comparison |
| `price-volume-analyst.md` | Price & Volume | Chart patterns, capital flows, market sentiment |

---

## Shared Conventions

### Python Environment

- Python 3.11+
- Virtual environment: `.venv/` (`python -m venv .venv && source .venv/bin/activate`)
- Dependencies: `pip install -r requirements.txt`

### Data Sources

| Purpose | Primary Source | Fallback Source |
|---------|---------------|----------------|
| Price / financial data | yfinance | polygon.io REST API |
| Market metadata | yfinance | polygon.io |
| Financial news / events | yfinance news | manual supplement |

- polygon.io API key is injected via environment variable `POLYGON_API_KEY` (`.env` file, not version-controlled)
- Local caching is managed by `lib/cache_manager.py` to avoid redundant fetches

### Market Scope

- **US equities only**: NYSE + NASDAQ
- Ticker format: standard US equity ticker symbol (e.g. `AAPL`, `MSFT`, `NVDA`)
- Currency: USD
- Trading timezone: US/Eastern

### File Naming Conventions

| Type | Format | Example |
|------|--------|---------|
| Sector report | `YYYYMMDD_sector_<name>.md` | `20260512_sector_semiconductors.md` |
| Equity report | `YYYYMMDD_<TICKER>_<type>.md` | `20260512_NVDA_equity.md` |
| Scan result | `YYYYMMDD_scan_<strategy>.md` | `20260512_scan_momentum.md` |
| Cached data | `<TICKER>_<type>_<YYYYMMDD>.parquet` | `AAPL_ohlcv_20260512.parquet` |

### Report Format

All reports are Markdown and include the following fixed sections:

```markdown
# [Report Title]

**Date**: YYYY-MM-DD
**Ticker / Sector**: TICKER or Sector Name
**Analyst Agent**: <agent-name>

## Executive Summary
(3–5 sentence core conclusions)

## Analysis Body
(Agent-specific content)

## Key Risks
(At least 3 items)

## Disclaimer
This report is for research purposes only and does not constitute investment advice.
```

---

## Directory Structure

```
investment-agents/
├── AGENTS.md                  # this file
├── requirements.txt
├── .env.example               # environment variable template
├── .Codex/
│   └── agents/                # sub-agent definitions
├── lib/                       # shared Python utilities
│   ├── cache_manager.py       # local cache management
│   ├── data_fetcher.py        # unified data fetch interface
│   ├── valuation.py           # valuation models
│   ├── technical.py           # technical indicators
│   └── report_writer.py       # report generation
├── data/
│   └── us/                    # US equity cached data
├── research/
│   ├── sector/                # sector research reports
│   ├── stock/                 # individual stock reports
│   └── scans/                 # scan results
└── scripts/
    ├── daily_scan.py
    ├── fetch_financials.py
    └── run_research.py
```
