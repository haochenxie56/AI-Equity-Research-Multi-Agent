# Phase 1A: Isolated Valuation ToolResult Integration Plan

**Date**: 2026-05-21
**Status**: Planning / Implementation
**Author**: Reliability Refactor — Phase 1A
**Depends on**: Phase 0.2 (`docs/reliability_phase_0_2_adapter_plan.md`)

---

## A. Purpose

Phase 1A is an **isolated valuation reliability proof**.

Its sole goal is to demonstrate that deterministic valuation outputs can be
wrapped into versioned `ToolResult` evidence, persisted in an `EvidenceStore`,
referenced by `AgentResult` findings and risks with structured `EvidenceRef`
binding metadata, and validated end-to-end by `validate_agent_result()` — all
**without touching the Financial page, the main app workflow, or the computation
logic inside `lib/valuation.py`**.

### What Phase 1A does

- Creates a thin, isolated `scripts/test_reliability_valuation_adapter.py`
  that proves the end-to-end evidence loop using **synthetic** valuation output
  dicts (no live API calls, no yfinance, no Anthropic).
- Confirms that `valuation_tool_result()` from Phase 0.2 is the correct adapter
  for wrapping valuation outputs.
- Validates that `EvidenceRef.metric` and `EvidenceRef.field_path` binding
  correctly resolve against nested valuation output structures (DCF scenarios,
  WACC assumptions, relative multiples).
- Provides a template for how future phases will wrap real `lib/valuation.py`
  outputs.

### What Phase 1A does NOT do

- Does not compute valuations — all output dicts are synthetic test fixtures.
- Does not change `lib/valuation.py` or any existing computation logic.
- Does not change any Streamlit page.
- Does not change the main research workflow.
- Does not expose evidence artifacts in any UI.

---

## B. Target Pipeline

```
Synthetic valuation dict (or future: lib/valuation.py output)
  │
  ▼
valuation_tool_result(run_id, target, metric_group, outputs, inputs)
  │  tool_name = "valuation_model" (baked in)
  │  evidence_id = deterministic hash of run_id + outputs
  ▼
ToolResult (in-memory)
  │
  ▼
EvidenceStore.add_tool_result(tr)
  │  appends to tool_results.jsonl
  │  returns evidence_id
  ▼
EvidenceRef(
  evidence_id = ...,
  tool_name   = "valuation_model",
  metric      = "fair_value"          # top-level key in outputs
  # or
  field_path  = "dcf.base_case.fair_value"  # dot-path into nested outputs
)
  │
  ▼
Finding(text="DCF fair value is $200 ...", evidence=[ref])
  │  or
Risk(name="...", description="35% downside if WACC rises ...", evidence=[ref])
  │
  ▼
AgentResult(agent_name=..., run_id=..., ticker=..., findings=[...], risks=[...])
  │
  ▼
validate_agent_result(agent_result, evidence_store)
  │  checks: evidence_id exists, tool_name matches, metric/field_path resolves
  │  issues: INVALID_EVIDENCE_*, WEAK_NUMERIC_EVIDENCE_BINDING, UNSUPPORTED_NUMERIC_CLAIM
  ▼
ValidationReport(passed=bool, run_id=..., target_name=..., issues=[...])
  │
  ▼
Persisted artifacts
  ├── tool_results.jsonl         (appended by EvidenceStore)
  ├── evidence_manifest.json     (written by EvidenceStore.save_manifest())
  └── validation_report.json    (written by save_json_model())
```

---

## C. Valuation Evidence Boundaries

### What belongs in ToolResult.outputs

Only deterministic, code-computed values should be wrapped into `ToolResult`.
All of the following are valid valuation evidence outputs:

| Field / Group | Example keys |
|---|---|
| Fair value | `fair_value`, `current_price`, `upside_pct` |
| DCF scenarios | `dcf.base_case.fair_value`, `dcf.bull_case.fair_value`, `dcf.bear_case.fair_value` |
| Assumptions | `assumptions.wacc`, `assumptions.terminal_growth`, `assumptions.forecast_years` |
| WACC components | `wacc`, `cost_of_equity`, `cost_of_debt`, `tax_rate`, `beta` |
| FCF metrics | `fcf_ttm`, `fcf_per_share`, `fcf_yield`, `fcf_cagr_5y` |
| Relative multiples | `relative_multiples.pe`, `relative_multiples.ev_ebitda`, `ps_ratio`, `pb_ratio` |
| Valuation range | `bear_case`, `base_case`, `bull_case` |
| EBITDA / growth | `ebitda_margin`, `revenue_growth`, `implied_upside_pct` |

### What does NOT belong in ToolResult

- LLM-generated commentary, interpretation, or qualitative assessments.
- Free-text narrative written by an AI agent.
- Analyst ratings (these come from `data_fetcher.py` and map to `ToolResult`
  from a different tool: `analyst_rating_fetcher`).

### Where LLM interpretation goes

LLM analysis of valuation outputs should become `AgentResult.findings` or
`AgentResult.risks`, each with `EvidenceRef` entries that bind back to the
valuation `ToolResult`. The LLM never replaces or modifies `ToolResult` data.

---

## D. EvidenceRef Binding Examples

### D1. Top-level metric binding

```python
EvidenceRef(
    evidence_id="ORCL_20260521_...:valuation_model:ORCL:dcf:a3f8c9d0e1b2",
    tool_name="valuation_model",
    metric="fair_value",
)
```

Resolves against `ToolResult.outputs["fair_value"]`.
Validator accepts when `"fair_value"` is a top-level key in `outputs`.

### D2. Nested DCF field_path binding

```python
EvidenceRef(
    evidence_id="ORCL_20260521_...:valuation_model:ORCL:dcf:a3f8c9d0e1b2",
    tool_name="valuation_model",
    field_path="dcf.base_case.fair_value",
)
```

Resolves by traversing `outputs["dcf"]["base_case"]["fair_value"]`.
Validator accepts when all segments of the dot-path exist in `outputs`.

### D3. Assumption field_path binding

```python
EvidenceRef(
    evidence_id="ORCL_20260521_...:valuation_model:ORCL:dcf:a3f8c9d0e1b2",
    tool_name="valuation_model",
    field_path="assumptions.wacc",
)
```

Resolves against `outputs["assumptions"]["wacc"]`.
Useful for findings that cite specific model assumptions (WACC, terminal growth,
forecast horizon).

---

## E. What Counts as Valid Validation

### Passing conditions

| Condition | Expected result |
|---|---|
| Finding has no numeric content and no evidence | `MISSING_EVIDENCE` warning — passes |
| Finding has numeric content and valid metric binding | No issues — passes |
| Finding has numeric content and valid field_path binding | No issues — passes |
| Finding has numeric content, valid evidence_id, valid tool_name | No `WEAK_NUMERIC_EVIDENCE_BINDING` if at least one binding field resolves |
| Risk has numeric content and valid field_path binding | No issues — passes |

### Warning conditions (report.passed = True)

| Condition | Issue code |
|---|---|
| EvidenceRef.tool_name does not match ToolResult.tool_name | `INVALID_EVIDENCE_TOOL_BINDING` |
| EvidenceRef.metric not found in ToolResult.outputs | `INVALID_EVIDENCE_METRIC_BINDING` |
| EvidenceRef.field_path does not resolve in ToolResult.outputs | `INVALID_EVIDENCE_FIELD_PATH_BINDING` |
| Numeric finding has evidence but no valid binding metadata | `WEAK_NUMERIC_EVIDENCE_BINDING` |
| Numeric risk has evidence but no valid binding metadata | `WEAK_NUMERIC_EVIDENCE_BINDING` |
| Finding has no evidence (non-numeric) | `MISSING_EVIDENCE` |
| Numeric risk has no evidence | `RISK_NUMERIC_NO_EVIDENCE` |

### Error conditions (report.passed = False)

| Condition | Issue code |
|---|---|
| EvidenceRef.evidence_id not in EvidenceStore | `INVALID_EVIDENCE_ID` |
| Risk EvidenceRef.evidence_id not in EvidenceStore | `INVALID_RISK_EVIDENCE_ID` |
| Numeric finding has no evidence at all | `UNSUPPORTED_NUMERIC_CLAIM` |

---

## F. Future Integration — Not Phase 1A

The following integration steps are planned for **later phases only**. None of
them should happen in Phase 1A.

| Future Phase | Scope |
|---|---|
| **Phase 1B** | Create an isolated technical indicator evidence pipeline (RSI, MACD, SMA/EMA, ADX, Bollinger). Mirrors Phase 1A but for `lib/technical.py` outputs. |
| **Phase 1C** | Create an isolated scanner/rotation evidence pipeline for `lib/rotation.py` sector momentum and composite scores. |
| **Phase 1D** | Convert `llm_orchestrator.py` JSON output into `AgentResult` in an isolated script — no Streamlit, no UI changes. |
| **Phase 1E** | Run `validate_agent_result()` against real `EvidenceStore` entries created from actual `lib/valuation.py` + `lib/technical.py` outputs. |
| **Phase 2** | Wire adapter calls into `lib/workflow_state.py` — one deterministic step at a time. EvidenceStore becomes part of the research workflow. |
| **Phase 3** | Surface `ValidationReport` in Streamlit as an evidence trace panel. |

### Why deferred

- Phase 1A must prove the loop works with synthetic data before wiring into
  live computation.
- Each integration point (valuation, technical, scanner, LLM) should be
  independently testable and reversible.
- UI changes require careful Streamlit session state management and should not
  happen until the backend pipeline is stable.

---

## G. Non-Goals for Phase 1A

The following are explicitly **out of scope** for Phase 1A:

| Category | Out-of-scope items |
|---|---|
| **Streamlit** | No page changes, no UI panels, no session state modifications |
| **App workflow** | No changes to `app.py`, `lib/workflow_state.py`, or existing workflow steps |
| **Computation** | No changes to `lib/valuation.py`, `lib/technical.py`, `lib/rotation.py`, `lib/data_fetcher.py` |
| **LLM** | No changes to `lib/llm_orchestrator.py`, no LLM prompt changes |
| **Semantic validation** | The validator checks structural binding only — it does not interpret whether the claim is correct |
| **Debate / critique** | No agent-vs-agent checking |
| **Memory** | No long-term agent memory or cross-run learning |
| **Portfolio / cockpit** | Reliability stays in the research workflow only |
| **Breaking changes** | All Phase 1A additions are additive to `lib/reliability/` |

---

## Appendix: Valuation Tool Name Registry

From `docs/reliability_phase_0_2_adapter_plan.md` Section E, the stable
`tool_name` for all valuation module outputs is:

```
valuation_model
```

This must match exactly in every `EvidenceRef.tool_name` that references a
valuation `ToolResult`.

```python
# Correct
EvidenceRef(evidence_id=..., tool_name="valuation_model", metric="fair_value")

# Wrong — will trigger INVALID_EVIDENCE_TOOL_BINDING
EvidenceRef(evidence_id=..., tool_name="valuation", metric="fair_value")
EvidenceRef(evidence_id=..., tool_name="technical_indicator_engine", metric="fair_value")
```
