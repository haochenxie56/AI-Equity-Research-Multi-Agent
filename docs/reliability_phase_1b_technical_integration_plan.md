# Phase 1B: Isolated Technical ToolResult Integration Plan

**Date**: 2026-05-21
**Status**: Planning / Implementation
**Author**: Reliability Refactor — Phase 1B
**Depends on**: Phase 1A (`docs/reliability_phase_1a_valuation_integration_plan.md`)

---

## A. Purpose

Phase 1B is an **isolated technical-analysis reliability proof**.

Its sole goal is to demonstrate that deterministic technical indicator outputs
can be wrapped into versioned `ToolResult` evidence, persisted in an
`EvidenceStore`, referenced by `AgentResult` findings and risks with structured
`EvidenceRef` binding metadata, and validated end-to-end by
`validate_agent_result()` — all **without touching the PriceVolume page, the
main app workflow, or the computation logic inside `lib/technical.py`**.

### What Phase 1B does

- Creates a thin, isolated `scripts/test_reliability_technical_adapter.py`
  that proves the end-to-end evidence loop using **synthetic** technical output
  dicts (no live API calls, no yfinance, no Anthropic).
- Confirms that `technical_tool_result()` from Phase 0.2 is the correct adapter
  for wrapping technical indicator outputs.
- Validates that `EvidenceRef.metric` and `EvidenceRef.field_path` binding
  correctly resolve against both top-level indicator values (RSI, MACD,
  volume ratio) and nested structures (moving averages, Bollinger bands,
  support/resistance levels, trend flags).
- Provides a template for how future phases will wrap real `lib/technical.py`
  outputs.

### What Phase 1B does NOT do

- Does not compute technical indicators — all output dicts are synthetic test
  fixtures.
- Does not change `lib/technical.py` or any existing computation logic.
- Does not change any Streamlit page.
- Does not change the main research workflow.
- Does not expose evidence artifacts in any UI.

---

## B. Target Pipeline

```
Synthetic technical dict (or future: lib/technical.py output)
  │
  ▼
technical_tool_result(run_id, target, metric_group, outputs, inputs)
  │  tool_name = "technical_indicator_engine" (baked in)
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
  tool_name   = "technical_indicator_engine",
  metric      = "rsi"                          # top-level key in outputs
  # or
  field_path  = "moving_averages.sma_50"       # dot-path into nested outputs
  # or
  field_path  = "levels.support"               # support / resistance levels
)
  │
  ▼
Finding(text="RSI is 62.5 ...", evidence=[ref])
  │  or
Risk(name="...", description="Downside if support at $175 breaks ...", evidence=[ref])
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

## C. Technical Evidence Boundaries

### What belongs in ToolResult.outputs

Only deterministic, code-computed indicator values should be wrapped into
`ToolResult`. All of the following are valid technical evidence outputs:

| Field / Group | Example keys |
|---|---|
| Momentum oscillators | `rsi`, `macd`, `macd_signal`, `macd_histogram` |
| Trend strength | `adx` |
| Moving averages | `moving_averages.sma_20`, `moving_averages.sma_50`, `moving_averages.sma_200`, `moving_averages.ema_20` |
| Bollinger Bands | `bollinger.upper`, `bollinger.middle`, `bollinger.lower` |
| Volume / ATR | `volume_ratio`, `atr` |
| Support & resistance | `levels.support`, `levels.resistance` |
| Trend flags | `trend.direction`, `trend.price_above_sma_50`, `trend.price_above_sma_200` |
| Price context | `price`, `price_change_pct`, `high_52w`, `low_52w` |

### What does NOT belong in ToolResult

- LLM-generated commentary, interpretation, or qualitative assessments.
- Free-text narrative written by an AI agent (e.g., "bullish setup forming").
- Analyst ratings or fundamental data — these come from different tool adapters
  (`analyst_rating_fetcher`, `financial_statement_fetcher`).

### Where LLM interpretation goes

LLM analysis of technical outputs should become `AgentResult.findings` or
`AgentResult.risks`, each with `EvidenceRef` entries that bind back to the
technical `ToolResult`. The LLM never replaces or modifies `ToolResult` data.

---

## D. EvidenceRef Binding Examples

### D1. Top-level metric binding (RSI)

```python
EvidenceRef(
    evidence_id="ORCL_20260521_...:technical_indicator_engine:ORCL:indicators:b4c9d1e2f3a0",
    tool_name="technical_indicator_engine",
    metric="rsi",
)
```

Resolves against `ToolResult.outputs["rsi"]`.

### D2. Nested moving average field_path binding

```python
EvidenceRef(
    evidence_id="ORCL_20260521_...:technical_indicator_engine:ORCL:indicators:b4c9d1e2f3a0",
    tool_name="technical_indicator_engine",
    field_path="moving_averages.sma_50",
)
```

Resolves by traversing `outputs["moving_averages"]["sma_50"]`.
Useful for findings that cite specific moving average levels.

### D3. Support/resistance field_path binding

```python
EvidenceRef(
    evidence_id="ORCL_20260521_...:technical_indicator_engine:ORCL:indicators:b4c9d1e2f3a0",
    tool_name="technical_indicator_engine",
    field_path="levels.support",
)
```

Resolves against `outputs["levels"]["support"]`.
Useful for risk entries that cite key price levels.

### D4. Bollinger Band field_path binding

```python
EvidenceRef(
    evidence_id="ORCL_20260521_...:technical_indicator_engine:ORCL:indicators:b4c9d1e2f3a0",
    tool_name="technical_indicator_engine",
    field_path="bollinger.upper",
)
```

Resolves against `outputs["bollinger"]["upper"]`.

---

## E. What Counts as Valid Validation

### Passing conditions

| Condition | Expected result |
|---|---|
| Finding has no numeric content and no evidence | `MISSING_EVIDENCE` warning — passes |
| Finding has numeric content and valid metric binding | No issues — passes |
| Finding has numeric content and valid field_path binding | No issues — passes |
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

## F. Future Integration — Not Phase 1B

The following integration steps are planned for **later phases only**. None of
them should happen in Phase 1B.

| Future Phase | Scope |
|---|---|
| **Phase 1C** | Create an isolated scanner/rotation evidence pipeline for `lib/rotation.py` sector momentum and composite scores. |
| **Phase 1D** | Convert `llm_orchestrator.py` JSON output into `AgentResult` in an isolated script. |
| **Phase 1E** | Validate `AgentResult` against real `EvidenceStore` entries from actual `lib/technical.py` + `lib/valuation.py` outputs. |
| **Phase 2** | Wire adapter calls into `lib/workflow_state.py` — one deterministic step at a time. |
| **Phase 3** | Surface `ValidationReport` in Streamlit as an evidence trace panel (PriceVolume page addition). |

---

## G. Non-Goals for Phase 1B

The following are explicitly **out of scope** for Phase 1B:

| Category | Out-of-scope items |
|---|---|
| **Streamlit** | No page changes, no UI panels, no session state modifications |
| **App workflow** | No changes to `app.py`, `lib/workflow_state.py`, or existing workflow steps |
| **Computation** | No changes to `lib/technical.py`, `lib/valuation.py`, `lib/rotation.py`, `lib/data_fetcher.py` |
| **LLM** | No changes to `lib/llm_orchestrator.py`, no LLM prompt changes |
| **Semantic validation** | The validator checks structural binding only — it does not interpret whether the claim is correct |
| **Debate / critique** | No agent-vs-agent checking |
| **Memory** | No long-term agent memory or cross-run learning |
| **Portfolio / cockpit** | Reliability stays in the research workflow only |
| **Breaking changes** | All Phase 1B additions are additive to `lib/reliability/` |

---

## Appendix: Technical Tool Name Registry

From `docs/reliability_phase_0_2_adapter_plan.md` Section E, the stable
`tool_name` for all technical module outputs is:

```
technical_indicator_engine
```

This must match exactly in every `EvidenceRef.tool_name` that references a
technical `ToolResult`.

```python
# Correct
EvidenceRef(evidence_id=..., tool_name="technical_indicator_engine", metric="rsi")

# Wrong — will trigger INVALID_EVIDENCE_TOOL_BINDING
EvidenceRef(evidence_id=..., tool_name="technical", metric="rsi")
EvidenceRef(evidence_id=..., tool_name="valuation_model", metric="rsi")
```

## Appendix: Comparison with Phase 1A

| Dimension | Phase 1A (Valuation) | Phase 1B (Technical) |
|---|---|---|
| Adapter | `valuation_tool_result()` | `technical_tool_result()` |
| `tool_name` | `"valuation_model"` | `"technical_indicator_engine"` |
| Top-level outputs | `fair_value`, `upside_pct` | `rsi`, `macd`, `adx`, `volume_ratio` |
| Nested outputs | `dcf.base_case.fair_value`, `assumptions.wacc` | `moving_averages.sma_50`, `levels.support` |
| Typical finding | "DCF fair value is $200" | "RSI is 62.5 in neutral territory" |
| Typical risk | "Bear case DCF implies 17% downside" | "Price risks breaking support at $175" |
