# Phase 3A: Validated Agent Orchestration Skeleton

**Date**: 2026-05-22
**Phase**: 3A
**Status**: Accepted (Phase 3A cleanup implemented — awaiting Codex re-review)

---

## Purpose

Phase 3A creates a **standalone, deterministic, offline orchestration skeleton** that chains
Phase 0–2 reliability artifacts end-to-end.  Its goal is to demonstrate and verify that
all previously built schema, evidence, validation, staleness, and critic components
can be wired together into a single auditable pipeline — before any live agent, live
data feed, or Streamlit integration is added.

This phase establishes the structural and contractual foundation for future phases
(Macro Agent v0.1, Horizon-aware Synthesis, Debate by Horizon, DecisionPacket).

---

## Why Begin with a Dry-Run / Mock-Only Skeleton

Live orchestration introduces multiple failure modes simultaneously: API latency,
data staleness, LLM non-determinism, schema mismatches, and runtime errors.  By
starting with a fully deterministic mock skeleton:

1. **Contracts are verified offline** — every schema boundary (ToolResult → EvidenceStore
   → AgentResult → ValidationReport → ValidationAggregate → StalenessReport →
   CriticResult → OrchestrationReport) is exercised before any live dependency is added.
2. **Regression gates remain green** — the skeleton can be run as a regression test
   after every future change.
3. **Isolated incremental integration** — live agents or data sources can be plugged
   in one at a time, with the skeleton providing fallback mock behavior.

---

## Relationship to Phase 0–2 Artifacts

| Artifact | Origin | Role in Phase 3A |
|----------|--------|-----------------|
| `ToolResult` | Phase 0 | Primary evidence unit; registered in EvidenceStore |
| `EvidenceStore` | Phase 0 | Stores and retrieves ToolResults by evidence_id |
| `AgentResult` | Phase 1D/1E | LLM-constrained output; validated against EvidenceStore |
| `validate_agent_result()` | Phase 0 | Audits evidence binding and numeric claims |
| `ValidationReport` | Phase 0 | Output of validate_agent_result |
| `ValidationAggregate` | Phase 2H | Aggregated validation warnings across domains |
| `StalenessReport` | Phase 2I | Freshness risk report for ToolResult timestamps |
| `CriticResult` | Phase 2J | Deterministic structural critique |
| `ReliabilityScoreSummary` | Phase 2K | Eval harness summary (passed by reference) |

---

## New Schemas in Phase 3A

All new schemas are defined in `lib/reliability/orchestration.py`.

### OrchestrationStatus

```
pass | pass_with_warnings | fail | error | unknown
```

Auto-derived from nested reliability outputs.

### OrchestrationStage

```
input_collection | evidence_registration | agent_result |
validation | validation_aggregation | staleness | critic |
evaluation_reference | synthesis | unknown
```

### OrchestrationMode

```
mock | dry_run | replay
```

### OrchestrationRecommendation

```
accept | revise | reject | needs_more_evidence | unknown
```

Auto-derived from `OrchestrationStatus`.

### OrchestrationIssueType

```
validation_issue | stale_data | critic_issue | missing_input |
malformed_input | evidence_error | evaluation_gate_failure |
scope_violation | other
```

### OrchestrationIssue

One structured issue raised during orchestration.  Fields include `issue_id`
(deterministic), `issue_type`, `stage`, `severity`, `message`, and optional
`related_id`, `evidence_id`, `field_path`, `metadata`.

### OrchestrationStageResult

Result for one pipeline stage.  Tracks `started_at`, `completed_at`, `summary`,
`output_ids` (list of IDs produced), and `issues` raised during the stage.

### OrchestrationInputBundle

Container for all inputs to one orchestration run.  Accepts:
- `tool_results` — list of ToolResults to register as evidence
- `agent_result` — optional pre-built AgentResult (or mock is built)
- `validation_aggregate`, `staleness_report`, `critic_result` — optional pre-computed
  reliability outputs.  **When provided, `run_validated_orchestration()` uses them
  directly without recomputing.  Each corresponding stage result records
  `metadata["source"] = "precomputed"`.  When absent, the stage computes the artifact
  and records `metadata["source"] = "computed"`.**
- `reliability_score_summary` — optional reference to eval harness result

### OrchestrationReport

The primary auditable output.  Contains:
- `orchestration_id` — deterministic ID derived from bundle_id, as_of, mode
- `stage_results` — list of `OrchestrationStageResult` per pipeline stage
- `validation_aggregate`, `staleness_report`, `critic_result` — embedded outputs
- `issues` — top-level orchestration issues
- `status` and `recommendation` — auto-normalized

---

## End-to-End Pipeline

```
OrchestrationInputBundle
    │
    ▼ Stage 1: input_collection
    Check bundle contents; flag missing inputs as warnings.
    │
    ▼ Stage 2: evidence_registration
    register_tool_results_in_evidence_store()
    → EvidenceStore (temp dir, cleaned after run)
    │
    ▼ Stage 3: agent_result
    Use provided AgentResult OR build mock via build_minimal_mock_agent_result()
    │
    ▼ Stage 4: validation
    run_validation_stage() → validate_agent_result() → ValidationReport
    │
    ▼ Stage 5: validation_aggregation
    run_validation_aggregation_stage() → ValidationAggregate
    │
    ▼ Stage 6: staleness
    run_staleness_stage() → check_tool_result_staleness() per ToolResult → StalenessReport
    │
    ▼ Stage 7: critic
    run_critic_stage() → run_mock_critic() → CriticResult
    │
    ▼ Stage 8: synthesis
    build_orchestration_report() → OrchestrationReport (normalized)
```

All stages run inside a `tempfile.TemporaryDirectory` context.  The directory is
cleaned up on return; the `OrchestrationReport` is a fully serializable Pydantic model
that holds no references to the temp path.

---

## Status and Recommendation Derivation

`OrchestrationReport.status` and `recommendation` are auto-derived by a Pydantic
`model_validator(mode="after")` that runs on every construction:

| Condition | Status | Recommendation |
|-----------|--------|---------------|
| Any stage `status == "error"` | `error` | `unknown` |
| Any `OrchestrationIssue.severity == "critical"` in stage or top-level | `fail` | `reject` |
| `critic_result.status == "fail"` | `fail` | `reject` |
| `validation_aggregate.status == "fail"` | `fail` | `reject` |
| `staleness_report.critical_count > 0` | `fail` | `reject` |
| Any `OrchestrationIssue.severity == "warning"` | `pass_with_warnings` | `revise` |
| `critic_result.status == "pass_with_warnings"` | `pass_with_warnings` | `revise` |
| `validation_aggregate.status == "pass_with_warnings"` | `pass_with_warnings` | `revise` |
| `staleness_report.warning_count > 0` or stale/expired/near-stale findings | `pass_with_warnings` | `revise` |
| None of the above | `pass` | `accept` |

The validator does **not** mutate nested input objects.

---

## Difference from Live Agent Orchestration

| Aspect | Phase 3A Skeleton | Future Live Orchestration |
|--------|------------------|--------------------------|
| Agent results | Mock-built deterministically | Real LLM-generated AgentResults |
| Data | Synthetic ToolResults | Live yfinance / polygon.io data |
| EvidenceStore | Temp dir (cleaned up) | Persistent run directory |
| LLM calls | None | Claude API |
| Critic | Deterministic structural critique | May include LLM-based debate |
| Streamlit | Not integrated | Feature-flagged live cockpit |
| Investment decisions | None | Future DecisionPacket |

---

## Evaluation Harness as Regression Gate

The Phase 2K Evaluation Harness (`evals/run_evals.py`, 12 synthetic failure-mode cases,
100% detection requirement) is a hard regression gate that must continue to pass after
every future change.

Test 35 in `scripts/test_reliability_orchestration_skeleton.py` runs
`run_reliability_evals()` inline and fails if any case regresses.

The full regression suite (all 25 reliability test scripts + eval runner) should be
re-run before merging any Phase 3 change.

---

## Precomputed Artifact Passthrough

`run_validated_orchestration()` checks each optional artifact field of the input bundle
before running its corresponding pipeline stage:

| Stage | Checked field | Behavior when provided | Behavior when absent |
|-------|--------------|----------------------|---------------------|
| validation_aggregation | `input_bundle.validation_aggregate` | Used directly; `metadata["source"] = "precomputed"` | Computed from ValidationReport; `metadata["source"] = "computed"` |
| staleness | `input_bundle.staleness_report` | Used directly; `metadata["source"] = "precomputed"` | Computed via `run_staleness_stage()`; `metadata["source"] = "computed"` |
| critic | `input_bundle.critic_result` | Used directly; `metadata["source"] = "precomputed"` | Computed via `run_critic_stage()`; `metadata["source"] = "computed"` |

Supplied artifacts are never mutated.  The `OrchestrationReport` embeds exactly the
artifact that was used (precomputed or freshly computed).

---

## ToolResult Payload Contract

`orchestration_report_tool_result_from_report()` wraps an `OrchestrationReport` as a
`ToolResult` for evidence store registration.  The `ToolResult.outputs` payload contains:

| Key | Type | Description |
|-----|------|-------------|
| `report` | `dict` | Full `OrchestrationReport.model_dump(mode="json")` — complete audit trail |
| `summary` | `dict` | Compact `summarize_orchestration_report()` dict — quick inspection |
| `calculation_version` | `str` | Version tag for the orchestration skeleton |

The `evidence_id` is computed from a **stable ID payload** that excludes stage timestamps:

```python
{
    "orchestration_id": report.orchestration_id,
    "as_of": report.as_of,
    "mode": report.mode,
    "target": target,
    "calculation_version": calculation_version,
}
```

This ensures the `evidence_id` is consistent across repeated runs on identical inputs,
even though the full report includes wall-clock timestamps.

---

## What Phase 3A Does NOT Do

- No live Claude API calls or LLM orchestration
- No live Streamlit UI integration
- No live data fetching (yfinance, polygon.io, Finnhub)
- No broker or order functionality
- No investment recommendations or decisions
- No automated portfolio management
- No runtime blocking of the live Streamlit app
- No Debate Agent
- No Memory Layer
- No Macro Agent live behavior
- No News/Earnings/Catalyst live agents

---

## Future Relationship

| Phase | Planned Addition |
|-------|-----------------|
| Phase 3B | Macro Agent v0.1 — deterministic macro snapshot integration |
| Phase 3B alt | Horizon-aware Synthesis Skeleton |
| Phase 3C | Mock Debate Layer by Investment Horizon |
| Phase 3D | DecisionPacket schema — structured investment decision output |
| Phase 3E | Feature-flagged dry-run orchestration planning wired to live app |

Each future phase should extend `OrchestrationInputBundle` and/or
`OrchestrationReport` with new optional fields, preserving backward compatibility
with the Phase 3A skeleton.

---

## Key Files

| File | Description |
|------|-------------|
| `lib/reliability/orchestration.py` | Phase 3A: all enums, models, helpers |
| `scripts/test_reliability_orchestration_skeleton.py` | 49-assertion test suite |
| `docs/reliability_phase_3a_validated_orchestration_skeleton.md` | This document |
| `docs/ai_dev_state/PROJECT_STATE.md` | Project-level checkpoint |
| `docs/ai_dev_state/CURRENT_TASK.md` | Current task state |
