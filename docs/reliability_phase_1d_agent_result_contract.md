# Phase 1D: AgentResult JSON Contract / LLM Output Adapter

**Date**: 2026-05-21
**Status**: Planning / Implementation
**Author**: Reliability Refactor — Phase 1D
**Depends on**: Phase 1C (`docs/reliability_phase_1c_scanner_rotation_integration_plan.md`)

---

## A. Purpose

Phase 1D defines the **AgentResult JSON contract** — the bridge between
deterministic `ToolResult` evidence and LLM-generated interpretation text.

Its sole goal is to prove that mock/synthetic LLM JSON can be:

1. Parsed from a raw JSON string or Python dict into a typed `AgentResult`
   (schema validation only — no Claude API calls).
2. Validated against a real `EvidenceStore` to check that every `EvidenceRef`
   points to an existing `ToolResult` and that numeric claims carry valid
   binding metadata.
3. Serialised back to JSON for persistence or downstream consumption.

All three operations are pure functions in `lib/reliability/agent_output.py`.
No Streamlit imports. No `lib/llm_orchestrator.py` imports. No live Claude API
calls.

### What Phase 1D does

- Introduces `lib/reliability/agent_output.py` with three public functions:
  - `parse_agent_result_json(raw)` — schema-only parse.
  - `parse_and_validate_agent_result(raw, evidence_store)` — parse + evidence
    validation in one call.
  - `agent_result_to_json(agent_result)` — Pydantic `model_dump_json()` wrapper.
- Updates `lib/reliability/__init__.py` to export all three functions.
- Creates `scripts/test_reliability_agent_output.py` with 17 test groups (A–Q)
  covering parsing, validation, and serialisation.

### What Phase 1D does NOT do

- Does not call the live Claude API.
- Does not modify `lib/llm_orchestrator.py` or any LLM prompt.
- Does not change any Streamlit page.
- Does not change the main research workflow.
- Does not expose `AgentResult` artefacts in any UI.

---

## B. Target Pipeline

```
Mock / synthetic LLM JSON string or dict
  │
  ▼
parse_agent_result_json(raw)
  │  schema validation only — no API calls, no evidence checks
  │  raises TypeError  if raw is not str or dict
  │  raises ValueError if JSON is malformed
  │  raises ValueError if dict does not conform to AgentResult schema
  ▼
AgentResult (in-memory)
  │
  ├── agent_result_to_json(agent_result) → JSON string (round-trip safe)
  │
  └── validate_agent_result(agent_result, evidence_store)
        │  checks evidence IDs exist in store
        │  checks numeric claims carry valid binding metadata
        ▼
      ValidationReport → (caller persists via serialization.py if needed)
```

The two-step convenience wrapper `parse_and_validate_agent_result(raw, store)`
combines both calls and always returns `(AgentResult, ValidationReport)`.

---

## C. AgentResult Schema Contract

All fields are defined in `lib/reliability/schemas.py`.  Extra fields are
forbidden (`ConfigDict(extra="forbid")`).

### Top-level `AgentResult`

| Field | Type | Required | Notes |
|---|---|---|---|
| `agent_name` | `str` (min_length=1) | ✓ | Stable agent identifier |
| `run_id` | `str` (min_length=1) | ✓ | Links agent output to a run context |
| `ticker` | `Optional[str]` | — | Ticker symbol or `None` for market-level outputs |
| `schema_version` | `str` | — | Defaults to `"0.1"` |
| `findings` | `list[Finding]` | — | LLM interpretations backed by evidence |
| `assumptions` | `list[Assumption]` | — | Named assumptions used by the agent |
| `risks` | `list[Risk]` | — | Identified risks, optionally backed by evidence |
| `confidence` | `Optional[AgentConfidence]` | — | Overall agent confidence level |
| `created_at` | `str` (ISO-8601) | — | Auto-generated if omitted |

### `Finding`

| Field | Type | Notes |
|---|---|---|
| `text` | `str` | Claim text — numeric claims trigger evidence checks |
| `evidence` | `list[EvidenceRef]` | Should be non-empty for numeric/metric claims |
| `confidence` | `float` (0–1) | Default `1.0` |

### `Assumption`

| Field | Type | Notes |
|---|---|---|
| `name` | `str` | |
| `rationale` | `str` | |
| `value` | `Optional[str]` | |
| `source` | `Literal["tool","user","agent","default"]` | Default `"agent"` |
| `sensitivity` | `Literal["low","medium","high"]` | Default `"medium"` |

> **Note**: `Assumption` does NOT have an `evidence` field.

### `Risk`

| Field | Type | Notes |
|---|---|---|
| `name` | `str` | |
| `description` | `str` | |
| `severity` | `Literal["low","medium","high"]` | Default `"medium"` |
| `evidence` | `list[EvidenceRef]` | Optional evidence binding |

### `EvidenceRef`

| Field | Type | Notes |
|---|---|---|
| `evidence_id` | `str` (min_length=1) | Must exist in `EvidenceStore` |
| `excerpt` | `str` | Default `""` |
| `tool_name` | `Optional[str]` | Validated against `ToolResult.tool_name` |
| `metric` | `Optional[str]` | Validated as top-level key or dot-path in `ToolResult.outputs` |
| `field_path` | `Optional[str]` | Dot-path traversal into `ToolResult.outputs` |
| `snapshot_id` | `Optional[str]` | Optional link to `DataSnapshot` |
| `description` | `Optional[str]` | Human-readable binding note |

### `AgentConfidence`

| Field | Type | Notes |
|---|---|---|
| `level` | `Literal["high","medium","low"]` | |
| `rationale` | `str` | |
| `score` | `float` (0–1) | Default `0.5` |

---

## D. Parse / Validate Separation

Schema parsing and evidence validation are **intentionally separate**:

| Function | What it checks | Side effects |
|---|---|---|
| `parse_agent_result_json(raw)` | JSON syntax + AgentResult schema | None |
| `validate_agent_result(ar, store)` | Evidence existence + binding | None |
| `parse_and_validate_agent_result(raw, store)` | Both, in sequence | None |

This separation means:

- A structurally valid `AgentResult` can be built from LLM output even when
  the evidence store is not yet populated (e.g., during prompt engineering).
- Evidence validation can run independently against any store, including
  stores constructed from persisted `tool_results.jsonl` files.
- Unit tests can verify parse behaviour without constructing a full store.

---

## E. Validation Issue Codes (Phase 1D Context)

The validator (`lib/reliability/validators.py`) produces `ValidationIssue`
objects with these codes, applicable to `AgentResult` findings and risks:

| Code | Severity | Trigger |
|---|---|---|
| `MISSING_EVIDENCE` | warning | Finding has no evidence refs at all |
| `UNSUPPORTED_NUMERIC_CLAIM` | **error** | Numeric/metric claim text, zero evidence refs |
| `INVALID_EVIDENCE_ID` | **error** | `evidence_id` not found in store |
| `INVALID_RISK_EVIDENCE_ID` | **error** | Risk `evidence_id` not found in store |
| `WEAK_NUMERIC_EVIDENCE_BINDING` | warning | Numeric claim, evidence refs exist but none has a valid binding |
| `INVALID_EVIDENCE_TOOL_BINDING` | warning | `EvidenceRef.tool_name` ≠ `ToolResult.tool_name` |
| `INVALID_EVIDENCE_METRIC_BINDING` | warning | `EvidenceRef.metric` not resolvable in `ToolResult.outputs` |
| `INVALID_EVIDENCE_FIELD_PATH_BINDING` | warning | `EvidenceRef.field_path` traversal fails |
| `RISK_NUMERIC_NO_EVIDENCE` | warning | Risk description contains numeric claim with zero evidence refs |

A `ValidationReport` passes (`passed=True`) as long as there are no `error`
severity issues.

---

## F. What Constitutes a Numeric Claim

`lib/reliability/validators.py` uses a compiled regex (`_NUMERIC_RE`) to
detect claims requiring evidence.  A finding or risk description triggers
evidence checks if it contains any of:

- A plain number: `42`, `3.14`, `0.5`
- A percentage: `11.1%`, `-5%`
- A dollar amount: `$200`, `$1,500`
- A financial keyword: `rsi`, `macd`, `wacc`, `dcf`, `growth`, `price`,
  `revenue`, `margin`, `ratio`, `yield`, `return`, `rate`, `pe`, `ev`,
  `ebitda`, `score`, `rank`, `momentum`, `upside`, `downside`

Non-numeric qualitative findings (e.g., "The company has strong brand equity")
do not require evidence.

---

## G. LLM Output Integration Path (Future — not Phase 1D)

Phase 1D establishes the contract using **synthetic** JSON fixtures.  Future
phases will wire real LLM output into this pipeline:

| Future Phase | Scope |
|---|---|
| **Phase 1E** | Adapt real `lib/llm_orchestrator.py` output into `AgentResult`; run full pipeline with real `lib/rotation.py` and `lib/valuation.py` outputs. |
| **Phase 2** | Wire adapter calls into `lib/workflow_state.py` for Scanner and Sector pages. |
| **Phase 3** | Surface `ValidationReport` in Streamlit as an evidence trace panel. |

The LLM prompt engineering to produce conformant `AgentResult` JSON is a
**Phase 1E** task.  Phase 1D only defines and tests the parser/validator
boundary.

---

## H. Non-Goals for Phase 1D

| Category | Out-of-scope items |
|---|---|
| **Claude API** | No live API calls; no `anthropic` SDK usage |
| **llm_orchestrator.py** | No modifications; no imports from it |
| **Streamlit** | No page changes, no UI panels, no session state modifications |
| **App workflow** | No changes to `app.py`, `lib/workflow_state.py`, or existing workflow steps |
| **Computation** | No changes to `lib/rotation.py`, `lib/technical.py`, `lib/valuation.py`, `lib/data_fetcher.py` |
| **Prompt engineering** | No LLM prompt changes |
| **Semantic validation** | Structural binding checks only — no interpretation of claim correctness |
| **Debate / critique** | No agent-vs-agent checking |

---

## Appendix: Public API Summary

```python
from lib.reliability.agent_output import (
    parse_agent_result_json,          # str | dict → AgentResult
    parse_and_validate_agent_result,  # str | dict, EvidenceStore → (AgentResult, ValidationReport)
    agent_result_to_json,             # AgentResult → str
)

# Also re-exported from lib.reliability:
from lib.reliability import (
    parse_agent_result_json,
    parse_and_validate_agent_result,
    agent_result_to_json,
)
```
