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
├── CLAUDE.md                  # this file
├── requirements.txt
├── .env.example               # environment variable template
├── .claude/
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

---

## Evidence-First Reliable Multi-Agent Refactor

### Architecture Principle

> **Deterministic computation, agentic interpretation, auditable synthesis.**
>
> Code computes facts. Tools produce versioned deterministic outputs. LLM agents interpret, critique, and synthesize.

### Reliability Rules

- Financial data extraction must be performed by code, not LLM inference.
- DCF, FCF, WACC, relative valuation, technical indicators, scanner scores, and portfolio risk calculations must be performed by deterministic tools.
- LLM agents must not invent financial numbers, valuation outputs, technical indicators, scanner scores, market data, or portfolio metrics.
- LLM output should be structured as `AgentResult` and must reference `ToolResult` evidence IDs.
- Numeric or metric-related claims must be backed by evidence IDs.
- Unsupported numeric claims must be flagged by validators.
- Do not replace deterministic workflow logic with free-form LLM reasoning.
- Preserve existing Streamlit pages unless the task explicitly requests UI changes.
- Prefer small, reviewable changes. Avoid broad rewrites unless specifically requested.

### Development Workflow

**Before editing:**
- Inspect relevant files.
- Summarize the planned change.
- Avoid touching unrelated code.

**After editing:**
- Report changed files.
- Report any errors or warnings.
- Explain whether the change preserves deterministic computation.
- If a relevant test exists, run it and report the result.

### Verification Discipline (live-path rule)

- **Any reported "today's reading" / live value in a final response MUST come from
  executing the REAL refresh path** (the same code the UI button triggers —
  `_run_refresh` for the Cockpit), NOT from an inline reconstruction of the
  computation. Inline reconstructions silently diverge from the live path on
  call-site details (loader choice, universe argument, field nesting), which is the
  documented cause of repeated report-vs-UI mismatches.
- **State the function actually invoked** to obtain the reading (e.g. "driven via
  `pages/7_Investment_Cockpit.py::_run_refresh` under AppTest with mocked network").
- A reading whose source the page reads (`_meta` / session_state) and a banner
  rendering must be proven equal by a parity test that drives one refresh end to
  end (see `scripts/test_reliability_phase_7b_rotation_internals.py` §18). The
  parity test must FAIL if the rendered banner and the `_meta` written by that same
  refresh disagree.

### Development Discipline (additional rules)

- **Real-path verification DoD.** Any phase that touches a data path must include
  **at least one test that drives the REAL fetch/refresh path** — one that would
  have FAILED on the broken commit it is meant to guard. A fixture-injected
  shortcut (seeding `session_state` / passing a prebuilt reading straight into the
  renderer) does **not** satisfy acceptance: it bypasses exactly the call-site
  details (loader choice, universe argument, field nesting) where the documented
  mismatches live. The real-path test is the Definition of Done, not an extra.
- **Fixture honesty.** Tests MAY stub network transport (mock the fetch/calendar
  call), but MUST NOT fabricate field VALUES that contradict documented production
  reality (e.g. inventing live yfinance `industry` strings that the real API never
  returns). When the real live values have been dumped during diagnosis, fixtures
  MUST use those dumped values rather than convenient stand-ins. A test that passes
  only because its fixture lies is a false green.
- **Session startup.** Run `git stash list` at the start of every session. A
  **non-empty stash must be reported to the user before any git operation**. Never
  `git stash pop` without listing first — popping blind can silently resurrect or
  clobber unrelated work.

### Phase 0: Reliability Foundation

Phase 0 is the **Reliability Foundation**. Its purpose is to create a standalone evidence and validation layer that can later wrap existing deterministic tools and LLM outputs **without changing** the current Streamlit UI or the existing research workflow.

**Planned package:** `lib/reliability/`

| File | Purpose |
|------|---------|
| `__init__.py` | Package init |
| `schemas.py` | Pydantic data models |
| `run_context.py` | RunContext dataclass and factory |
| `evidence_store.py` | EvidenceStore: add/get/persist tool results |
| `validators.py` | validate_agent_result() |
| `serialization.py` | save_json_model(), save_json() helpers |

**Key schemas** (all defined in `schemas.py`):
`DataSnapshot`, `ToolResult`, `EvidenceRef`, `Finding`, `Assumption`, `Risk`, `AgentConfidence`, `AgentResult`, `ValidationIssue`, `ValidationReport`

**Run context:**
- `RunContext` dataclass with a unique `run_id` of the form `TICKER_YYYYMMDD_HHMMSS_shortuuid`
- Each run exposes a `run_dir` under `research/runs/`
- Factory: `create_run_context(ticker=None, task=None, base_dir="research/runs")`

**Evidence store behavior:**
- `add_tool_result(result: ToolResult) -> str` — returns an `evidence_id`
- Persists records to `tool_results.jsonl`
- Persists manifest to `evidence_manifest.json`

**Validator requirements:**
- Detect findings with no evidence
- Detect evidence IDs that do not exist in the store
- Detect numeric or metric-related claims without evidence
- Detect risk evidence references pointing to missing evidence IDs

**Planned test script:** `scripts/test_reliability_foundation.py`

**Preferred test command:**
```bash
python scripts/test_reliability_foundation.py
```

Expected behavior after Phase 0 is implemented:
- Validation passes.
- A run directory is created under `research/runs/`.
- `tool_results.jsonl` is persisted.
- `evidence_manifest.json` is persisted.
