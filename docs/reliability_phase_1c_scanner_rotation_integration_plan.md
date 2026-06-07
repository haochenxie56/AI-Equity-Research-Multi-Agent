# Phase 1C: Isolated Scanner / Rotation ToolResult Integration Plan

**Date**: 2026-05-21
**Status**: Planning / Implementation
**Author**: Reliability Refactor — Phase 1C
**Depends on**: Phase 1B (`docs/reliability_phase_1b_technical_integration_plan.md`)

---

## A. Purpose

Phase 1C is an **isolated scanner / sector-rotation reliability proof**.

Its sole goal is to demonstrate that deterministic scanner scores, sector
rotation metrics, ETF momentum signals, and candidate ranking outputs can be
wrapped into versioned `ToolResult` evidence, persisted in an `EvidenceStore`,
referenced by `AgentResult` findings and risks with structured `EvidenceRef`
binding metadata, and validated end-to-end by `validate_agent_result()` — all
**without touching the Scanner page, the Sector page, the main app workflow,
or the computation logic inside `lib/rotation.py`**.

### What Phase 1C does

- Introduces `sector_rotation_tool_result()`, a new thin convenience wrapper in
  `lib/reliability/adapters.py` that bakes in `tool_name="sector_rotation_model"`.
- Reuses existing `scanner_tool_result()` (from Phase 0.2) for stock scanner
  outputs — no duplication.
- Creates a self-contained `scripts/test_reliability_scanner_rotation_adapter.py`
  that proves the end-to-end evidence loop using **synthetic** scanner and
  rotation output dicts (no live API calls, no yfinance, no Anthropic).
- Validates that `EvidenceRef.field_path` correctly resolves multi-level nested
  paths such as `"sectors.Technology.sector_score"` and
  `"candidates.ORCL.strategy_breakdown.quality_growth_score"`.

### What Phase 1C does NOT do

- Does not compute scanner scores or rotation metrics — all output dicts are
  synthetic test fixtures.
- Does not change `lib/rotation.py` or any existing computation logic.
- Does not change any Streamlit page.
- Does not change the main research workflow.
- Does not expose evidence artifacts in any UI.

---

## B. Target Pipeline

```
Synthetic rotation dict (or future: lib/rotation.py sector output)
  │
  ▼
sector_rotation_tool_result(run_id, target, metric_group, outputs, inputs)
  │  tool_name = "sector_rotation_model" (baked in)
  │  evidence_id = deterministic hash of run_id + outputs
  ▼
ToolResult (in-memory)
  │
  ├── EvidenceStore.add_tool_result(tr_rotation)   → tool_results.jsonl
  │
  └── (optionally in same store)

Synthetic scanner dict (or future: lib/rotation.py scanner output)
  │
  ▼
scanner_tool_result(run_id, target, metric_group, outputs, inputs)
  │  tool_name = "stock_scanner" (baked in)
  │  evidence_id = deterministic hash of run_id + outputs
  ▼
ToolResult (in-memory)
  │
  └── EvidenceStore.add_tool_result(tr_scanner)    → tool_results.jsonl (same file)

EvidenceRef(
  evidence_id = ...,
  tool_name   = "sector_rotation_model",
  field_path  = "sectors.Technology.sector_score"
)
─── or ───
EvidenceRef(
  evidence_id = ...,
  tool_name   = "stock_scanner",
  field_path  = "candidates.ORCL.composite_score"
)
─── or ───
EvidenceRef(
  evidence_id = ...,
  tool_name   = "stock_scanner",
  field_path  = "candidates.ORCL.strategy_breakdown.quality_growth_score"
)
  │
  ▼
AgentResult(findings=[...], risks=[...])
  │
  ▼
validate_agent_result(agent_result, evidence_store)
  │
  ▼
ValidationReport → validation_report.json
```

---

## C. Scanner / Rotation Evidence Boundaries

### What belongs in ToolResult.outputs

Only deterministic, code-computed values should be wrapped into `ToolResult`.

#### Sector rotation model (`tool_name = "sector_rotation_model"`)

| Field / Group | Example keys |
|---|---|
| Sector summary | `top_sector`, `as_of` |
| Per-sector scores | `sectors.Technology.sector_score`, `sectors.Technology.sector_rank` |
| Momentum signals | `sectors.Technology.sector_momentum`, `sectors.Technology.relative_strength` |
| ETF metrics | `sectors.Technology.etf`, `sectors.Technology.etf_return_1m`, `sectors.Technology.etf_return_3m` |
| Volume trend | `sectors.Technology.volume_trend` |

#### Stock scanner (`tool_name = "stock_scanner"`)

| Field / Group | Example keys |
|---|---|
| Universe summary | `selected_tickers`, `as_of`, `universe_size` |
| Per-candidate scores | `candidates.ORCL.composite_score`, `candidates.ORCL.candidate_rank` |
| Strategy breakdown | `candidates.ORCL.strategy_breakdown.momentum_score` |
| | `candidates.ORCL.strategy_breakdown.value_score` |
| | `candidates.ORCL.strategy_breakdown.quality_growth_score` |
| | `candidates.ORCL.strategy_breakdown.oversold_rebound_score` |
| Candidate metadata | `candidates.ORCL.sector` |

### What does NOT belong in ToolResult

- LLM-generated stock selection rationale or recommendation text.
- Qualitative characterisation of momentum ("strong uptrend") — these become
  `AgentResult.findings`.
- Analyst ratings or fundamental data — those come from separate adapters.

---

## D. EvidenceRef Binding Examples

### D1. Sector score — metric binding

```python
EvidenceRef(
    evidence_id="...:sector_rotation_model:market:sector_rotation:hash",
    tool_name="sector_rotation_model",
    metric="top_sector",
)
```

### D2. Nested sector score — field_path binding

```python
EvidenceRef(
    evidence_id="...:sector_rotation_model:market:sector_rotation:hash",
    tool_name="sector_rotation_model",
    field_path="sectors.Technology.sector_score",
)
```

Resolves by traversing
`outputs["sectors"]["Technology"]["sector_score"]`.

### D3. ETF return — field_path binding

```python
EvidenceRef(
    evidence_id="...:sector_rotation_model:market:sector_rotation:hash",
    tool_name="sector_rotation_model",
    field_path="sectors.Technology.etf_return_1m",
)
```

### D4. Scanner composite score — field_path binding

```python
EvidenceRef(
    evidence_id="...:stock_scanner:market:stock_scanner:hash",
    tool_name="stock_scanner",
    field_path="candidates.ORCL.composite_score",
)
```

Resolves by traversing
`outputs["candidates"]["ORCL"]["composite_score"]`.

### D5. Strategy sub-score — deep field_path binding

```python
EvidenceRef(
    evidence_id="...:stock_scanner:market:stock_scanner:hash",
    tool_name="stock_scanner",
    field_path="candidates.ORCL.strategy_breakdown.quality_growth_score",
)
```

Resolves by traversing four levels:
`outputs["candidates"]["ORCL"]["strategy_breakdown"]["quality_growth_score"]`.

---

## E. What Counts as Valid Validation

| Condition | Expected result |
|---|---|
| Numeric finding cites valid sector score via field_path | No issues — passes |
| Numeric finding cites valid composite score via field_path | No issues — passes |
| Numeric finding cites deep strategy sub-score via field_path | No issues — passes |
| EvidenceRef.tool_name mismatch | `INVALID_EVIDENCE_TOOL_BINDING` warning — passes |
| EvidenceRef.metric not in outputs | `INVALID_EVIDENCE_METRIC_BINDING` warning — passes |
| EvidenceRef.field_path does not resolve | `INVALID_EVIDENCE_FIELD_PATH_BINDING` warning — passes |
| Numeric finding with no valid binding | `WEAK_NUMERIC_EVIDENCE_BINDING` warning — passes |
| Numeric finding with no evidence | `UNSUPPORTED_NUMERIC_CLAIM` error — **fails** |
| EvidenceRef.evidence_id missing from store | `INVALID_EVIDENCE_ID` error — **fails** |

---

## F. Future Integration — Not Phase 1C

| Future Phase | Scope |
|---|---|
| **Phase 1D** | Convert `llm_orchestrator.py` JSON output into `AgentResult` in an isolated script; validate stock-selection conclusions against scanner evidence. |
| **Phase 1E** | End-to-end validation: real `lib/rotation.py` outputs wrapped by adapters, validated against LLM findings. |
| **Phase 2** | Wire adapter calls into `lib/workflow_state.py` for Scanner and Sector pages. |
| **Phase 3** | Surface `ValidationReport` in Streamlit as an evidence trace panel on Scanner and Sector pages. |

---

## G. Non-Goals for Phase 1C

| Category | Out-of-scope items |
|---|---|
| **Streamlit** | No page changes, no UI panels, no session state modifications |
| **App workflow** | No changes to `app.py`, `lib/workflow_state.py`, or existing workflow steps |
| **Computation** | No changes to `lib/rotation.py`, `lib/technical.py`, `lib/valuation.py`, `lib/data_fetcher.py` |
| **LLM** | No changes to `lib/llm_orchestrator.py`, no LLM prompt changes |
| **Semantic validation** | Structural binding checks only — no interpretation of claim correctness |
| **Debate / critique** | No agent-vs-agent checking |
| **Memory** | No long-term agent memory or cross-run learning |
| **Portfolio / cockpit** | Reliability stays in the research workflow only |

---

## Appendix: Tool Name Registry (complete as of Phase 1C)

| Source module | `tool_name` | Adapter function |
|---|---|---|
| `lib/valuation.py` | `valuation_model` | `valuation_tool_result()` |
| `lib/technical.py` | `technical_indicator_engine` | `technical_tool_result()` |
| `lib/rotation.py` (sector) | `sector_rotation_model` | `sector_rotation_tool_result()` ← **new** |
| `lib/rotation.py` (scanner) | `stock_scanner` | `scanner_tool_result()` |
| `lib/data_fetcher.py` (price) | `price_volume_snapshot` | *(future)* |
| `lib/data_fetcher.py` (financials) | `financial_statement_fetcher` | *(future)* |
| `lib/data_fetcher.py` (ratings) | `analyst_rating_fetcher` | *(future)* |
| `lib/data_fetcher.py` (metadata) | `market_data_fetcher` | *(future)* |
