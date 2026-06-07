# Phase 3G — Offline Review Loop / Reliability Run Report Skeleton

**Date**: 2026-05-23
**Status**: Implemented — awaiting Codex review
**File**: `lib/reliability/review_loop.py`
**Tests**: `scripts/test_reliability_review_loop.py`

---

## Purpose

Phase 3G creates a standalone, deterministic, offline/mock-only layer that
composes the accepted Phase 3A–3F reliability artifacts into a single auditable
research/review package: the **ReliabilityRunReport**.

The report represents a full offline reliability review loop:

1. Orchestration / plan artifact (Phase 3A)
2. Horizon-aware synthesis artifact (Phase 3B)
3. Macro context artifact (Phase 3C)
4. Debate-by-horizon artifact (Phase 3D)
5. Decision packet artifact (Phase 3E)
6. Human review artifact (Phase 3F)
7. **Final offline reliability run report** (Phase 3G)

The purpose of the report is traceability and review packaging, not live
execution. This layer does not modify the live application, live LLM workflow,
broker/order system, or runtime research workflow.

---

## Relationship to Phase 3A–3F

| Prior Phase | Artifact | Consumed By Phase 3G |
|-------------|----------|----------------------|
| Phase 3A | `OrchestrationReport` | duck-typed via `orchestration_report` |
| Phase 3B | `HorizonSynthesisReport` | duck-typed via `horizon_synthesis_report` |
| Phase 3C | `MacroAgentResult` | duck-typed via `macro_agent_result` |
| Phase 3D | `DebateReport` | duck-typed via `debate_report` |
| Phase 3E | `DecisionPacket` | duck-typed via `decision_packet` |
| Phase 3F | `HumanReviewReport` | typed via `human_review_report` |

Duck typing (Optional[Any]) is used for Phase 3A–3E artifacts to avoid hard
cross-module import dependencies at package import time.  Phase 3F's
`HumanReviewReport` is typed because Phase 3G's status logic reads its
`.status`, `.feedback_items`, `.revision_requests`, and `.outcome` fields.

---

## Input Bundle

`ReliabilityRunInputBundle` holds all phase artifacts:

```python
ReliabilityRunInputBundle(
    bundle_id="...",          # Unique bundle identifier
    run_id="...",             # Run identifier (e.g. AAPL_20260523_...)
    as_of="...",              # ISO timestamp
    ticker="...",             # Optional ticker symbol
    orchestration_report=..., # Phase 3A (Optional[Any])
    horizon_synthesis_report=..., # Phase 3B (Optional[Any])
    macro_agent_result=...,   # Phase 3C (Optional[Any])
    debate_report=...,        # Phase 3D (Optional[Any])
    decision_packet=...,      # Phase 3E (Optional[Any])
    human_review_report=...,  # Phase 3F (Optional[HumanReviewReport])
    validation_aggregate=..., # Optional[ValidationAggregate]
    staleness_report=...,     # Optional[StalenessReport]
    critic_result=...,        # Optional[CriticResult]
    tool_results=[...],       # list[ToolResult] — direct evidence chain
)
```

All fields except `bundle_id`, `run_id`, and `as_of` are optional.  Missing
artifacts produce warnings, not errors.

---

## Report Schema

### `ReliabilityRunStatus`

```python
Literal["unknown", "complete", "needs_revision", "blocked", "failed"]
```

### `ReliabilityRunSummary`

| Field | Type | Notes |
|-------|------|-------|
| `target` | str | ticker or run_id |
| `run_id` | str | |
| `status` | ReliabilityRunStatus | |
| `decision_summary` | Optional[str] | from decision_packet |
| `review_status` | Optional[str] | from human_review_report |
| `blocking_reasons` | list[str] | |
| `revision_reasons` | list[str] | |
| `horizon_count` | int | cards in horizon_synthesis_report |
| `debate_count` | int | rounds in debate_report |
| `evidence_count` | int | unique source_ids |
| `validation_issue_count` | int | items in validation_aggregate |
| `staleness_issue_count` | int | findings in staleness_report |
| `critic_issue_count` | int | issues in critic_result |
| `approved_for_execution` | bool | **always False** |

### `ReliabilityRunReport`

| Field | Type | Notes |
|-------|------|-------|
| `report_id` | str | `rlr_<hash16>` |
| `schema_version` | str | "1.0" |
| `target` | str | ticker or run_id |
| `run_id` | str | |
| `as_of` | str | ISO timestamp |
| `status` | ReliabilityRunStatus | |
| `summary` | ReliabilityRunSummary | |
| `source_ids` | list[str] | deduplicated evidence/artifact IDs |
| `warnings` | list[str] | missing optional artifact warnings |
| `created_at` | str | ISO timestamp |
| `calculation_version` | str | "reliability_run_report_v1" |
| `approved_for_execution` | bool | **always False** — enforced by Pydantic model_validator |

---

## Status Logic

`determine_reliability_run_status()` applies the following priority rules
(highest priority first):

| Priority | Condition | Status |
|----------|-----------|--------|
| 1 (highest) | `human_review_report.status == "blocked"` (critical feedback) | `blocked` |
| 1 | `decision_packet.status == "blocked"` | `blocked` |
| 2 | `human_review_report.status == "changes_requested"` | `needs_revision` |
| 3 | `decision_packet.status == "fail"` and no HR revision request / block | `failed` |
| 4 | `human_review_report.status == "approved_for_research_only"` | `complete` |
| 5 (lowest) | `human_review_report` is None or any other state | `unknown` |

**Key contract:** A human-review revision request (`changes_requested`) takes
priority over a decision-packet `"fail"`.  The human reviewer's explicit request
for changes must be resolved before a failed decision state can stand alone.
`decision_packet.status == "fail"` returns `"failed"` **only** when there is no
human-review revision request and no block signal.

`blocked` always takes priority over `needs_revision` or `complete`.
`complete` means approved for **research only** — it does not authorize execution.
No status value ever implies `approved_for_execution = True`.

---

## ToolResult Wrapper

`reliability_run_tool_result_from_report()` wraps the report as a `ToolResult`
for evidence-aware pipelines:

- `tool_name` is stable: `"reliability_run_report"`
- `target` defaults to `report.target`
- `outputs` includes the full serialized report, a compact summary dict, and
  `calculation_version`
- `evidence_id` is deterministic and content-sensitive: same report payload →
  same evidence_id
- Does not mutate the report
- `outputs["summary"]["approved_for_execution"]` is always `False`

---

## Execution-Safety Guardrails

Phase 3G enforces no-execution at every layer:

1. `ReliabilityRunSummary.approved_for_execution` has a `model_validator` that
   raises `ValidationError` if it is set to `True`.
2. `ReliabilityRunReport.approved_for_execution` has the same `model_validator`.
3. `reliability_run_tool_result_from_report()` hard-codes
   `outputs["summary"]["approved_for_execution"] = False`.
4. `status == "complete"` means approved for **research only**, not execution.
5. The module docstring and all helper docstrings contain explicit execution
   prohibition language.

---

## Why This Remains Offline/Mock-Only

- No imports from `app.py`, `pages/*`, `lib/llm_orchestrator.py`, or any live
  workflow module.
- No network calls, no HTTP clients, no live data fetching.
- No LLM API calls.
- No broker or order placement APIs.
- All computation is deterministic: sorting, hashing, rule-based status
  inference.
- Missing artifacts produce warnings; they do not trigger fallback LLM calls.

---

## Future Integration Boundaries

When Phase 3G is ready to be wired into the live workflow (a future phase), the
integration boundary will be:

1. The live orchestration runner produces Phase 3A–3F artifacts.
2. `ReliabilityRunInputBundle` is constructed from those artifacts.
3. `build_reliability_run_report()` is called offline (after the run).
4. The resulting `ReliabilityRunReport` is persisted to the run directory as a
   review package.
5. Human analysts access the report via the review UI (a future phase).

No live app files are modified in Phase 3G.

---

## Explicit Non-Authorization Statement

**Phase 3G does not authorize trading, order placement, broker submission, or
any form of execution.** `approved_for_execution` is always `False` and is
enforced by Pydantic model validators.  A `status` of `"complete"` means the
research package is approved for research review only.

This report is for research and educational purposes only. It does not
constitute investment advice. Markets involve risk.

---

## Key Files

| File | Description |
|------|-------------|
| `lib/reliability/review_loop.py` | Phase 3G implementation |
| `scripts/test_reliability_review_loop.py` | Test suite |
| `lib/reliability/__init__.py` | Updated with Phase 3G exports |
| `docs/ai_dev_state/PROJECT_STATE.md` | Updated roadmap |
| `docs/ai_dev_state/CURRENT_TASK.md` | Updated task status |
