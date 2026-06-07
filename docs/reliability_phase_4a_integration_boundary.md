# Phase 4A: Reliability Integration Boundary Contract

**Date**: 2026-05-24
**Status**: Implemented. Awaiting Codex review.
**Module**: `lib/reliability/integration_boundary.py`
**Test script**: `scripts/test_reliability_integration_boundary.py` (64/64 tests)

---

## What the Boundary Contract Is

The integration boundary contract is a **strongly typed, deterministic, isolated
interface** that defines how the reliability layer could later be connected to
the live AI workflow. It specifies:

- **What information must be provided** when calling the reliability layer from
  a live workflow step (via `ReliabilityBoundaryRequest`).
- **What the reliability layer will return** in each execution mode (via
  `ReliabilityBoundaryResult`).
- **How execution mode and source workflow identity are normalized** from
  configuration strings into typed enums.

The contract is the boundary, not the integration itself. In Phase 4A, no live
integration exists.

---

## Why Phase 4A Does Not Wire Into the Live Workflow

Phase 4A establishes the **contract first, wiring second**. This ordering is
intentional:

1. **Auditable contract before integration.** Defining the boundary as an
   isolated, testable module allows independent review of its semantics before
   any live code path depends on it.

2. **No risk to live app behavior.** `app.py`, `pages/*`, and
   `lib/llm_orchestrator.py` are not modified. The existing Streamlit UI and
   Claude API call behavior remain unchanged.

3. **Phase 4B+ can wire selectively.** Once the contract is accepted, a future
   phase can connect a single workflow step to the boundary without touching
   unrelated code. The contract acts as a stable target.

4. **Backward compatibility.** All Phase 0–3G accepted modules are unmodified.
   The Phase 4A module is additive only.

---

## Execution Modes

### `DISABLED`

The reliability layer is inactive. All requests pass through without evaluation.

- `status` = `PASS_THROUGH`
- `should_block` = `False`
- `payload` preserved (no modification)
- `reliability_summary` = `None`
- No validation, no critic, no staleness check

**Use case**: Default safe mode; reliability layer present but inactive.

### `SHADOW`

The reliability layer evaluates the request but does not block the workflow.
In Phase 4A, shadow evaluation is **not wired to live workflow components**
(i.e., no actual `validate_agent_result`, critic, or staleness check runs).
The boundary returns a `SHADOW_EVALUATED` status with diagnostics explaining
that shadow evaluation is defined but deferred.

- `status` = `SHADOW_EVALUATED`
- `should_block` = `False`
- `payload` preserved
- `reliability_summary` = `{"shadow_wired": False, "phase": "4A", ...}`

**Use case in future phases**: Run reliability checks alongside live workflow
and log results without affecting execution. Enables safe rollout.

### `ENFORCED`

The reliability layer would normally evaluate and potentially block the workflow.
In Phase 4A, enforcement is **not wired to live workflow** — the boundary
returns a deterministic non-live result with diagnostics explaining that
ENFORCED mode is deferred.

- `status` = `PASS_THROUGH` (in Phase 4A; live enforcement deferred)
- `should_block` = `False` (in Phase 4A)
- `payload` preserved
- `reliability_summary` = `{"enforced_wired": False, "phase": "4A", ...}`

**Use case in future phases**: Block a workflow step if reliability checks fail
below a threshold. Requires full integration of validation, critic, and decision
packet layers.

---

## Public API

### Enums

| Name | Values |
|------|--------|
| `ReliabilityExecutionMode` | `DISABLED`, `SHADOW`, `ENFORCED` |
| `ReliabilitySourceWorkflow` | `OVERVIEW_WORKFLOW`, `SECTOR_PAGE`, `SCANNER_PAGE`, `EQUITY_PAGE`, `FINANCIAL_PAGE`, `PRICE_VOLUME_PAGE`, `CLI`, `UNKNOWN` |
| `ReliabilityBoundaryStatus` | `PASS_THROUGH`, `SHADOW_EVALUATED`, `BLOCKED`, `ERROR_CAPTURED` |

### Models

| Name | Key Fields |
|------|-----------|
| `ReliabilityBoundaryRequest` | `source_workflow`, `execution_mode`, `run_id?`, `step_name?`, `ticker?`, `payload?`, `metadata?` |
| `ReliabilityBoundaryResult` | `status`, `execution_mode`, `source_workflow`, `should_block`, `diagnostics`, `payload?`, `reliability_summary?` |

Both models are **frozen Pydantic models** (immutable after construction).

### Functions

| Name | Description |
|------|-------------|
| `normalize_execution_mode(value)` | Normalize string or enum → `ReliabilityExecutionMode`; raises `ValueError` for unknown values |
| `normalize_source_workflow(value)` | Normalize string or enum → `ReliabilitySourceWorkflow`; raises `ValueError` for unknown values |
| `evaluate_reliability_boundary(request)` | Deterministic evaluation; returns `ReliabilityBoundaryResult` |

---

## Invariants Enforced

- `evaluate_reliability_boundary` is **deterministic**: identical inputs → identical outputs.
- `evaluate_reliability_boundary` is **side-effect-free**: no file writes, no API calls,
  no network calls, no mutation of input objects.
- `should_block` is **always `False`** in Phase 4A for all modes.
- `payload` is **always preserved** from request to result.
- Models are **frozen**: no post-construction mutation.

---

## Explicit Non-Goals

Phase 4A does NOT:

- Wire the reliability layer into any live workflow step.
- Modify `app.py`, `pages/*`, `lib/llm_orchestrator.py`, or `lib/workflow_state.py`.
- Change any live Streamlit page behavior.
- Call the Claude API or any external API.
- Perform actual validation, critic, staleness, or evaluation harness checks
  on live workflow data.
- Allow `should_block = True` in any live code path.
- Define how Phase 4B should wire the boundary (that is a Phase 4B decision).

---

## Future Phase Guidance (Informational Only)

Phase 4B and beyond may:

- Wire `SHADOW` mode to call `run_validated_orchestration` on a copy of live
  agent output, logging results without blocking.
- Wire `ENFORCED` mode to call the full orchestration + evaluation harness and
  set `should_block = True` when the reliability score falls below a threshold.
- Use `ReliabilitySourceWorkflow` to apply different mode configurations per
  page (e.g., SHADOW on equity page, DISABLED on sector page during rollout).
- Expose `reliability_summary` fields in a read-only Streamlit debug panel.

These are informational. Phase 4A does not implement or commit to any of them.

---

## Test Coverage (64/64 passing)

| Group | Description | Tests |
|-------|-------------|-------|
| 1 | DISABLED mode pass-through | 7 |
| 2 | SHADOW mode non-blocking | 7 |
| 3 | ENFORCED mode contract (non-live) | 7 |
| 4 | normalize_execution_mode | 8 |
| 5 | normalize_source_workflow | 7 |
| 6 | Payload and metadata handling | 5 |
| 7 | Frozen model immutability | 3 |
| 8 | Determinism | 3 |
| 9 | Forbidden import checks | 6 |
| 10 | __init__.py exports | 9 |
| 11 | Regression (Phase 3G + Phase 2 closeout) | 2 |
| **Total** | | **64** |
