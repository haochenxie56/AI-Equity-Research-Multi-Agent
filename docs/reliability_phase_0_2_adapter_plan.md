# Phase 0.2: ToolResult Adapter Plan

**Date**: 2026-05-21  
**Status**: Planning / Scaffold  
**Author**: Reliability Refactor — Phase 0.2

---

## A. Current Architecture

The AI Investment Agent processes US equity research through a deterministic pipeline backed by six modules:

| Module | Role |
|---|---|
| `lib/data_fetcher.py` | Fetches price history, financial statements, analyst ratings, and company metadata from yfinance / polygon.io |
| `lib/valuation.py` | Computes DCF, WACC, FCF, relative valuation multiples, and valuation ranges |
| `lib/technical.py` | Computes RSI, MACD, SMA/EMA, ADX, Bollinger Bands, volume ratios |
| `lib/rotation.py` | Computes sector momentum, ETF relative strength, scanner scores, and strategy rankings |
| `lib/llm_orchestrator.py` | Sends structured quantitative data to Claude; returns natural-language commentary as JSON |
| `lib/workflow_state.py` | Manages Streamlit session state across workflow steps |

The current flow is:

```
data_fetcher → valuation / technical / rotation
             → llm_orchestrator (Claude commentary)
             → Streamlit UI
```

Each deterministic module produces Python dicts or DataFrames that are consumed directly by the Streamlit pages. LLM commentary is appended but there is no formal link between numeric claims in the commentary and the deterministic outputs that support them.

**The reliability foundation** (`lib/reliability/`) exists as a standalone layer that does not yet touch this pipeline.

---

## B. Adapter Purpose

Adapters are thin conversion functions that accept already-computed Python dicts and return `ToolResult` or `DataSnapshot` objects.

They do not:
- Perform any computation themselves
- Import or call `valuation.py`, `technical.py`, `rotation.py`, or `data_fetcher.py`
- Change what is computed or how it is computed
- Affect the Streamlit UI or session state

They do:
- Convert dict outputs into versioned, auditable evidence records
- Generate deterministic `evidence_id` values from run context + outputs
- Make it possible for future `AgentResult` findings and risks to reference specific numeric outputs with provable binding

This separation means the reliability layer can be added incrementally — one deterministic module at a time — without changing computation logic or UI behavior.

---

## C. Candidate Deterministic Sources

### `lib/valuation.py`

| Metric Group | Candidate Outputs |
|---|---|
| `dcf` | `intrinsic_value_per_share`, `npv`, `terminal_value`, `implied_upside_pct` |
| `wacc` | `wacc`, `cost_of_equity`, `cost_of_debt`, `tax_rate`, `beta` |
| `fcf` | `fcf_ttm`, `fcf_per_share`, `fcf_yield`, `fcf_cagr_5y` |
| `relative_valuation` | `pe_ratio`, `ev_ebitda`, `ev_sales`, `ps_ratio`, `pb_ratio`, `peer_median_pe` |
| `valuation_range` | `bear_case`, `base_case`, `bull_case`, `current_price` |

### `lib/technical.py`

| Metric Group | Candidate Outputs |
|---|---|
| `rsi` | `rsi_14`, `rsi_signal`, `overbought`, `oversold` |
| `macd` | `macd_line`, `signal_line`, `histogram`, `crossover` |
| `moving_averages` | `sma_50`, `sma_200`, `ema_20`, `price_vs_sma_200_pct` |
| `adx` | `adx`, `plus_di`, `minus_di`, `trend_strength` |
| `bollinger` | `upper_band`, `lower_band`, `pct_b`, `bandwidth` |
| `volume` | `volume_ratio_20d`, `obv`, `avg_volume_20d` |

### `lib/rotation.py`

| Metric Group | Candidate Outputs |
|---|---|
| `sector_momentum` | `sector_momentum_score`, `relative_return_4w`, `relative_return_12w` |
| `etf_strength` | `etf_rs_score`, `etf_vs_spy_pct`, `sector_rank` |
| `scanner_score` | `composite_score`, `fundamental_score`, `technical_score`, `momentum_score` |
| `strategy_rank` | `rank_within_universe`, `universe_size`, `strategy_name` |

### `lib/data_fetcher.py`

| Metric Group | Candidate Outputs |
|---|---|
| `price_history` | `close`, `volume`, `high`, `low`, `date_range` |
| `financial_statements` | `revenue`, `net_income`, `ebitda`, `total_debt`, `cash` |
| `analyst_ratings` | `consensus`, `buy_count`, `hold_count`, `sell_count`, `median_pt` |
| `company_metadata` | `sector`, `industry`, `market_cap`, `employees`, `description` |
| `market_snapshot` | `spy_return_ytd`, `vix`, `sector_etf_returns` |

### `lib/llm_orchestrator.py` (future only)

LLM outputs will eventually become `AgentResult` objects, not `ToolResult`. Do not touch this module in Phase 0.2.

---

## D. Evidence ID Convention

### Format

```
{run_id}:{tool_name}:{target}:{metric_group}:{payload_hash}
```

### Rules

- All five segments are sanitized (spaces and path-unsafe characters → underscores).
- `run_id` comes from `create_run_context()` — format `TICKER_YYYYMMDD_HHMMSS_shortuuid`.
- `payload_hash` is a 12-character SHA-256 hex prefix of the JSON-serialized outputs (keys sorted).
- The hash ensures two different output dicts within the same run produce different evidence IDs.
- Including `run_id` as a prefix ensures no cross-run collisions even for identical outputs.

### Examples

```
ORCL_20260521_021342_2f8d7a23:valuation_model:ORCL:dcf:a3f8c9d0e1b2
ORCL_20260521_021342_2f8d7a23:technical_indicator_engine:ORCL:rsi_macd:7c4e1a9f3d82
SECTOR_20260521_021342_abcd1234:sector_rotation_model:XLK:sector_score:9b1f7e3c4a56
AAPL_20260521_021342_f1e2d3c4:market_data_fetcher:AAPL:financial_statements:2c8a4b7d1e90
```

### Stability vs. Uniqueness

Evidence IDs are **stable**: same run + same tool + same target + same metric group + same outputs always yield the same ID. This makes them safe to reference in `EvidenceRef` entries created in the same workflow execution. They are **unique enough** because the hash covers the full output dict.

---

## E. ToolResult Naming Convention

| Source module | Proposed `tool_name` |
|---|---|
| `lib/valuation.py` | `valuation_model` |
| `lib/technical.py` | `technical_indicator_engine` |
| `lib/rotation.py` | `sector_rotation_model` |
| `lib/rotation.py` (scanner) | `stock_scanner` |
| `lib/data_fetcher.py` (price) | `price_volume_snapshot` |
| `lib/data_fetcher.py` (financials) | `financial_statement_fetcher` |
| `lib/data_fetcher.py` (ratings) | `analyst_rating_fetcher` |
| `lib/data_fetcher.py` (metadata) | `market_data_fetcher` |

These names are stable string constants. `EvidenceRef.tool_name` must match exactly for the binding validator to accept a reference as valid.

---

## F. Run ID Propagation Strategy

### Principle

One `run_id` per research workflow execution. All `ToolResult`, `AgentResult`, and `ValidationReport` objects produced in a single research run share the same `run_id`.

### Proposed call sequence (future Phase 1+)

```python
ctx = create_run_context(ticker="ORCL", task="full_research")
store = EvidenceStore(run_dir=ctx.run_dir)

# Deterministic computation (unchanged)
dcf_outputs = valuation.compute_dcf(ticker, inputs)

# Adapter wraps outputs into evidence (new)
tr = valuation_tool_result(
    run_id=ctx.run_id,
    target="ORCL",
    metric_group="dcf",
    outputs=dcf_outputs,
    inputs={"wacc": 0.09, "forecast_years": 5},
)
store.add_tool_result(tr)

# LLM analysis (future)
agent_result = AgentResult(
    agent_name="FinancialAgent",
    run_id=ctx.run_id,
    ticker="ORCL",
    findings=[Finding(
        text="DCF indicates $142 intrinsic value with 12% upside.",
        evidence=[EvidenceRef(
            evidence_id=tr.evidence_id,
            tool_name="valuation_model",
            metric="intrinsic_value_per_share",
        )],
    )],
)

report = validate_agent_result(agent_result, store)
store.save_manifest()
```

### Key constraint

`run_id` must be passed explicitly into every adapter call. It must not be inferred or generated inside an adapter.

---

## G. DataSnapshot vs. ToolResult Boundary

| Concept | Use |
|---|---|
| `DataSnapshot` | Raw or near-raw source data: price history rows, raw financial statement values, API response data. Source-level provenance. |
| `ToolResult` | Computed or normalized output: DCF result, RSI values, scanner composite scores. Tool-level provenance. |
| `AgentResult` | LLM interpretation: findings, assumptions, risks. Never a `ToolResult`. |

### Embedding pattern

A `ToolResult` may embed one or more `DataSnapshot` objects in its `data_snapshots` list to record the source data used as inputs:

```python
price_snap = data_snapshot_from_payload(
    snapshot_id=f"{ctx.run_id}:price:ORCL:20260521",
    source="yfinance",
    payload={"close": 127.40, "volume": 8_200_000, "date": "2026-05-21"},
)
tr = ToolResult(
    ...,
    data_snapshots=[price_snap],
)
```

This creates a two-level provenance chain: `EvidenceRef → ToolResult → DataSnapshot → raw source`.

---

## H. Future Integration Sequence

| Phase | Scope | Files touched |
|---|---|---|
| **1A** | Wrap `valuation.py` DCF/WACC/FCF outputs into `ToolResult` in an isolated script | `scripts/run_valuation_with_evidence.py` (new) |
| **1B** | Wrap `technical.py` indicator outputs into `ToolResult` in an isolated script | `scripts/run_technical_with_evidence.py` (new) |
| **1C** | Wrap `rotation.py` scanner/sector outputs into `ToolResult` | `scripts/run_rotation_with_evidence.py` (new) |
| **1D** | Convert `llm_orchestrator.py` JSON output into `AgentResult` in isolated script | `scripts/run_llm_with_evidence.py` (new) |
| **1E** | Validate `AgentResult` against `EvidenceStore` in isolated script | `scripts/run_validation.py` (new) |
| **2** | Wire adapter calls into existing workflow — one step at a time | `lib/workflow_state.py` (incremental) |
| **3** | Surface `ValidationReport` in Streamlit evidence trace panel | `pages/` (UI addition only) |

Each phase is independently testable and reversible.

---

## I. Non-Goals for Phase 0.2 and Phase 1

The following are explicitly out of scope:

- **No Streamlit changes** — no pages, no UI panels, no session state modifications
- **No workflow behavior changes** — computation, caching, data fetching remain identical
- **No LLM prompt changes** — `llm_orchestrator.py` is not touched
- **No semantic validator** — the validator does not interpret claim meaning, only structural binding
- **No debate or critique layer** — no agent-vs-agent checking
- **No memory layer** — no long-term agent memory or cross-run learning
- **No portfolio or cockpit integration** — reliability stays in research workflow only
- **No breaking changes to `lib/reliability/`** — all Phase 0.x additions are additive

---

## Appendix: Adapter Data Flow

```
Existing deterministic module
  │ computes dict / DataFrame
  │ (unchanged)
  ▼
Adapter function (lib/reliability/adapters.py)
  │ accepts already-computed dict
  │ generates evidence_id
  ▼
ToolResult (in-memory)
  │
  ├─ add_tool_result() → tool_results.jsonl (appended)
  │
  └─ save_manifest() → evidence_manifest.json
          │
          ▼
     EvidenceStore
          │
          └─ referenced by EvidenceRef in Finding / Risk
                    │
                    ▼
               AgentResult
                    │
                    ▼
           validate_agent_result()
                    │
                    ▼
            ValidationReport
```
