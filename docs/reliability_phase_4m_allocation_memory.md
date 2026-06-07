# Reliability Phase 4M-D: Allocation Decision Memory

**Date**: 2026-05-26 (status reconciled 2026-05-27)
**Phase**: 4M-D
**Status**: **Accepted** (Codex FAIL fixes accepted)
**Module**: `lib/reliability/allocation_memory.py`
**Test suite**: `scripts/test_reliability_allocation_memory.py`

> **Note on historical phrasing below**: this document was drafted when later
> Phase 4M subphases (4M-E through 4M-G) were still pending. All Phase 4M
> subphases through 4M-G are now accepted, and Phase 4M-H Phase 4 Memory
> Closeout has been implemented and is awaiting Codex review. The
> "Future Subphases" section below is retained as historical roadmap context.

---

## Purpose

Phase 4M-D defines an offline, deterministic, mock-only memory schema and helper layer for recording allocation decisions. It captures target/actual allocation, risk budget, cash impact, projected outcomes, drawdown, forward return, and lessons learned — without any live portfolio data, brokerage calls, database writes, or execution pathways.

This phase is part of the Roadmap v4 Phase 4 Memory + Human Feedback mainline.

---

## Relationship to Other Phases

| Phase | Module | Relationship |
|-------|--------|--------------|
| Phase 4M-A | `research_memory.py` | `memory_id` optionally links to `ResearchRunMemoryRecord` |
| Phase 4M-B | `thesis_memory.py` | `thesis_id` optionally links to `HorizonThesisMemoryRecord` |
| Phase 4M-C | `event_memory.py` | Parallel memory stream: catalyst/news/earnings events |
| Phase 3R-C | `allocation_report.py` | `allocation_report_id` links to `AllocationReport` (Phase 3R-C) |
| Phase 3R-B | `trade_plan.py` | `trade_plan_report_id` links to `TradePlanReport` (Phase 3R-B) |
| Phase 3E | `decision_packet.py` | `decision_packet_id` links to `DecisionPacket` (Phase 3E) |
| Phase 4A | `integration_boundary.py` | Accepted early infrastructure; not part of memory mainline |

---

## Memory Schema

### Literal Type Aliases (7)

| Alias | Values |
|-------|--------|
| `AllocationMemoryStatus` | unknown, active, reviewed, needs_review, invalidated, archived, blocked |
| `AllocationDecisionAction` | hold, add, trim, exit, no_action, unknown |
| `AllocationDecisionReviewStatus` | not_required, pending, reviewed, escalated, blocked, unknown |
| `AllocationDecisionOutcome` | unknown, pending, positive, negative, neutral, mixed, invalidated |
| `AllocationMemoryEventType` | allocation_recorded, allocation_review_requested, allocation_review_completed, target_updated, risk_budget_updated, outcome_observed, lesson_added, human_feedback_added, archived, unknown |
| `AllocationMemoryRiskLevel` | low, medium, high, unknown |
| `AllocationMemoryActorType` | system, user, reviewer, agent, unknown |

### Pydantic Models (7)

#### AllocationMemorySourceRef
A stable pointer to an upstream artifact. Fields: `source_id` (required, non-empty), `source_type`, `artifact_id`, `evidence_id`, `field_path`, `label`, `metadata`, `warnings`.

#### AllocationDecisionSnapshot
A non-live snapshot of allocation numbers at decision time. Contains:
- Bounded pct fields [0, 1]: `target_allocation_pct`, `actual_allocation_pct`, `min_allocation_pct`, `max_allocation_pct`, `cash_pct`, `projected_cash_pct`
- Non-negative pct fields: `portfolio_loss_pct`, `risk_budget_pct`
- Signed numeric fields: `required_trade_value`, `required_shares`, `cash_impact`
- `risk_level`, `source_refs`, `evidence_ids`, `artifact_refs`, `warnings`
- No broker/order/account/execution fields. No live data.

#### AllocationMemoryLogEntry
A timestamped lifecycle entry: `event_id`, `event_type`, `created_at`, `actor`, `description`, `source_ids`, `evidence_ids`, `metadata`, `warnings`.

#### AllocationDecisionMemoryRecord
The main record. Fields:
- `allocation_memory_id`, `target` (required, non-empty)
- `run_id`, `memory_id`, `thesis_id` (optional upstream links)
- `allocation_report_id`, `trade_plan_report_id`, `decision_packet_id` (optional phase links)
- `action`, `status`, `review_status`, `outcome`
- `decision_snapshot` (AllocationDecisionSnapshot)
- `rationale` (required, non-empty)
- `review_trigger`, `forward_return_pct` (signed), `max_drawdown_pct` (non-negative), `lesson`
- `recorded_at`, `reviewed_at`
- `source_refs`, `evidence_ids`, `artifact_refs`, `event_log`, `warnings`
- `approved_for_execution` (always False; ValidationError if set True)

#### AllocationMemoryInputBundle
Input bundle for building reports. Optional upstream artifacts (duck-typed `Any`):
`research_run_memory_record`, `thesis_memory_report`, `allocation_report`, `trade_plan_report`, `decision_packet`, `human_review_report`. Missing artifacts produce warnings, not crashes.

#### AllocationMemorySummary
Aggregate counts: `record_count`, `action_counts`, `reviewed_count`, `needs_review_count`, `blocked_count`, `high_risk_count`, `pending_outcome_count`, `positive_outcome_count`, `negative_outcome_count`, `avg_forward_return_pct`, `max_drawdown_pct`, `top_warnings`. Always `approved_for_execution=False`.

#### AllocationMemoryReport
Full report: `report_id`, `target`, `run_id`, `status`, `records`, `summary`, `source_ids`, `evidence_ids`, `artifact_refs`, `warnings`, `created_at`, `updated_at`, `calculation_version`. Always `approved_for_execution=False`.

---

## Allocation Decision Lifecycle

```
Decision analyzed
      │
      ▼
build_allocation_decision_snapshot()  ← captures numbers at decision time
      │
      ▼
build_allocation_memory_record()      ← records action, rationale, status
      │
      ├── status auto-determined (or initial_status override)
      ├── event_log: allocation_recorded, [review_requested], [lesson_added], [outcome_observed]
      │
      ▼
build_allocation_memory_report()      ← aggregates records for target
      │
      ▼
allocation_memory_tool_result_from_report()  ← wraps as ToolResult
      │
      ▼
EvidenceStore.add_tool_result()  ← caller's responsibility (not this module)
```

---

## Risk Budget / Cash Impact / Drawdown / Forward Return / Lesson Tracking

- **Risk budget**: `decision_snapshot.risk_budget_pct` captures the portfolio risk allocated to this position. Non-negative.
- **Cash impact**: `decision_snapshot.cash_impact` captures the signed cash movement. Negative for purchases, positive for sales.
- **Drawdown**: `record.max_drawdown_pct` tracks the maximum observed drawdown for this decision. Non-negative. Aggregated as `max()` across records in the summary.
- **Forward return**: `record.forward_return_pct` tracks the return realized after the decision. May be signed (negative for losses). Aggregated as `avg()` across records with non-None values in the summary.
- **Lesson**: `record.lesson` captures a free-text lesson learned. Triggers a `lesson_added` event log entry.

---

## Event Log Design

Each `AllocationDecisionMemoryRecord` contains an `event_log` list of `AllocationMemoryLogEntry` objects built deterministically by the helper. Entries are built for:

| Trigger | EventType |
|---------|-----------|
| Record creation | `allocation_recorded` |
| Status is blocked or needs_review | `allocation_review_requested` |
| Lesson is provided | `lesson_added` |
| Outcome is not unknown/pending | `outcome_observed` |

All entries carry deterministic `event_id`s based on `(allocation_memory_id, event_type, created_at)`. Because `allocation_memory_id` is itself content-sensitive (see below), event IDs for two distinct records that share the same target/action/as_of/run_id will also differ automatically.

---

## Status Logic

### Single-Record Status (in `build_allocation_memory_record`)

Priority order:

1. `initial_status` override (if provided)
2. **blocked** — human review report has status="blocked", OR `review_status="blocked"`
3. **needs_review** — `risk_level="high"` with `review_status != "reviewed"`, OR `review_status in ("pending", "escalated")`
4. **reviewed** — `review_status="reviewed"`
5. **active** — default

### Report-Level Status (in `determine_allocation_memory_status`)

Precedence: **blocked > needs_review > reviewed > active > archived > unknown**

| Condition | Status |
|-----------|--------|
| HRR blocked OR any record blocked | blocked |
| Any record needs_review OR any high-risk non-reviewed record | needs_review |
| All non-archived/non-invalidated records reviewed | reviewed |
| Any active records | active |
| All records archived | archived |
| No records OR all invalidated/unknown | unknown |

---

## Record ID Design — Content Sensitivity

`make_allocation_memory_record_id()` produces a deterministic SHA-256 hash from:

| Field | Always included |
|-------|----------------|
| `target` | ✓ |
| `action` | ✓ |
| `as_of` | ✓ |
| `run_id` | when not None |
| `snapshot_id` | when not None (passed by `build_allocation_memory_record`) |
| `rationale` | when not None (passed by `build_allocation_memory_record`) |
| `review_status` | when not None (passed by `build_allocation_memory_record`) |
| `outcome` | when not None (passed by `build_allocation_memory_record`) |

`build_allocation_memory_record()` always finalizes the `AllocationDecisionSnapshot` **before** calling `make_allocation_memory_record_id()`, so that `snapshot_id`, `rationale`, `review_status`, and `outcome` are always included in the payload. This ensures two records that share the same target/action/as_of/run_id but differ in decision content receive distinct IDs.

Direct callers of `make_allocation_memory_record_id()` that omit the new optional parameters retain backward-compatible behaviour.

---

## ToolResult Adapter

`allocation_memory_tool_result_from_report(report, run_id=None)` wraps an `AllocationMemoryReport` as a `ToolResult`:

- **tool_name**: `"allocation_memory_report"` (stable)
- **ticker**: `report.target`
- **evidence_id**: deterministic SHA-256 hash of full payload including report dict, summary, record_count, and calculation_version
- **outputs include**: full report dict, summary dict, record_count, reviewed_count, needs_review_count, blocked_count, high_risk_count, pending_outcome_count, calculation_version, approved_for_execution=False
- **No fake evidence** — evidence_id changes when content changes
- **No execution implication** — this is not an order ticket

---

## No Persistence / No DB / No Vector Store

This phase introduces:
- ✅ Schema definitions (Pydantic models)
- ✅ Deterministic helper functions
- ✅ ToolResult adapter (wrapping only, no side effects)
- ❌ No file writes
- ❌ No database writes
- ❌ No vector store writes
- ❌ No network calls
- ❌ No LLM calls
- ❌ No Streamlit UI

---

## No Live Portfolio / Brokerage Import

- No brokerage account IDs, order IDs, execution IDs
- No live portfolio data imports
- No position imports from broker APIs
- All data must be passed in as explicit Python arguments
- `AllocationDecisionSnapshot` is a non-live snapshot — not a live portfolio query

---

## Offline/Mock-Only Nature

The entire module is designed for:
- Deterministic unit tests (no mocking needed — inputs are pure Python)
- Offline research audit trail construction
- Codex review without live infrastructure

---

## No Execution Authorization

`approved_for_execution` is always `False` in:
- `AllocationDecisionMemoryRecord`
- `AllocationMemorySummary`
- `AllocationMemoryReport`
- ToolResult outputs

Setting `approved_for_execution=True` raises `ValidationError`. No pathway exists to authorize execution from this module.

---

## Deduplication Behavior

All helpers deduplicate:
- `source_refs`: by `source_id` (first occurrence wins)
- `evidence_ids`: by value (first occurrence wins)
- `artifact_refs`: by value (first occurrence wins); empty/whitespace refs filtered

---

## Subsequent Phase 4M Subphases (historical roadmap context)

> Status reconciled 2026-05-27: all Phase 4M subphases through 4M-G are now
> accepted. Phase 4M-H Phase 4 Memory Closeout has been implemented and is
> awaiting Codex review. This table is retained as historical roadmap context.

| Subphase | Description | Status |
|----------|-------------|--------|
| Phase 4M-E | Option Trade Plan Memory | Accepted |
| Phase 4M-F | Human Feedback Layer | Accepted |
| Phase 4M-G | Agent Evaluation | Accepted |
| Phase 4M-H | Phase 4 Memory Closeout | Implemented — awaiting Codex review |

---

## Disclaimer

All outputs from this module are for research and educational purposes only. They do not constitute investment advice. Markets involve risk; invest with caution.
