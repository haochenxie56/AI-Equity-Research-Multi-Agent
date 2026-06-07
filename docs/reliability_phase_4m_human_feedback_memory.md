# Phase 4M-F: Human Feedback Layer — Design Document

## 1. Purpose

Phase 4M-F introduces a **Human Feedback Layer** for the investment agent reliability
system. It provides a schema-only, deterministic, offline/mock-only memory module for
recording, auditing, and summarizing human feedback on agent-produced research artifacts.

The module does **not** authorize, trigger, or imply trade execution. It is a pure
evidence and audit layer.

---

## 2. Roadmap Relationship

| Phase | Scope |
|-------|-------|
| 4M-A | Research Run Memory schema |
| 4M-B | Thesis Memory by Horizon |
| 4M-C | Catalyst / News / Earnings Memory |
| 4M-D | Allocation Decision Memory |
| 4M-E | Option Trade Plan Memory |
| **4M-F** | **Human Feedback Layer** (this phase) |

Phase 4M-F accepts upstream artifacts from any prior phase (research_run_memory_record,
thesis_memory_report, event_memory_report, allocation_memory_report,
option_trade_memory_report, decision_packet, human_review_report, review_loop_report)
via a duck-typed InputBundle.

---

## 3. Memory Lifecycle

```
InputBundle (upstream artifacts, target, run_id)
    │
    ▼
build_human_feedback_memory_record()   ← one per feedback event
    │  builds: TargetRef, FeedbackEntries, EventLog
    ▼
build_human_feedback_memory_report()   ← aggregates records
    │  computes: status, summary, source_ids, evidence_ids
    ▼
human_feedback_memory_tool_result_from_report()  ← wraps as ToolResult
```

Records carry immutable IDs derived from all material fields. The ID is
deterministic: identical inputs always produce the same ID.

---

## 4. Schema Summary

| Class | Purpose |
|-------|---------|
| `HumanFeedbackSourceRef` | Points to a source artifact for a feedback entry |
| `HumanFeedbackTargetRef` | Identifies the research artifact being reviewed |
| `HumanFeedbackEntry` | A single human feedback decision with audit fields |
| `HumanFeedbackMemoryLogEntry` | Append-only event log entry for a record |
| `HumanFeedbackMemoryRecord` | Full feedback record for one target |
| `HumanFeedbackMemoryInputBundle` | Aggregates upstream artifacts + metadata |
| `HumanFeedbackMemorySummary` | Aggregate counts and status for a report |
| `HumanFeedbackMemoryReport` | Top-level output wrapping records + summary |

---

## 5. Literal Type Aliases

| Alias | Values |
|-------|--------|
| `HumanFeedbackMemoryStatus` | unknown, recorded, needs_review, resolved, superseded, archived, blocked |
| `HumanFeedbackDecision` | accepted, rejected, overrode, skipped, deferred, needs_revision, executed_manually, unknown |
| `HumanFeedbackTargetType` | research_run_memory, thesis_memory, event_memory, allocation_memory, option_trade_memory, decision_packet, review_loop, human_review, trade_plan, option_expression, unknown |
| `HumanFeedbackReasonType` | thesis_disagreement, risk_too_high, evidence_insufficient, valuation_disagreement, timing_disagreement, catalyst_disagreement, allocation_disagreement, option_structure_disagreement, execution_not_desired, external_information, preference, other, unknown |
| `HumanFeedbackOutcome` | unknown, pending, positive, negative, neutral, mixed, avoided_loss, missed_gain, prevented_bad_action, caused_bad_action |
| `HumanFeedbackEventType` | feedback_recorded, feedback_updated, feedback_resolved, outcome_updated, lesson_added, agent_evaluation_flagged, archived, unknown |
| `HumanFeedbackActor` | user, reviewer, system, agent, unknown |

---

## 6. ID Strategy

All IDs are derived via `stable_hash_payload()` (SHA-256, hex, truncated):

| ID | Prefix | Payload fields |
|----|--------|---------------|
| `feedback_memory_id` | `hfm_` | target_id, target_type, decisions[], reason_types[], feedback_texts[], override_reasons[], outcome, run_id, as_of |
| `event_id` (log entry) | `hfmev_` | feedback_memory_id, event_type, created_at |
| `report_id` | `hfmrpt_` | target, as_of, run_id, tool_name |
| `target_ref_id` | `hftref_` | target_id, target_type, run_id, memory_id, as_of |

IDs are content-sensitive: changing any material field changes the ID.

---

## 7. ToolResult Adapter

`human_feedback_memory_tool_result_from_report(report, run_id=None)` wraps a
`HumanFeedbackMemoryReport` as a `ToolResult`. The `evidence_id` is derived from all
output fields, ensuring that distinct reports produce distinct evidence IDs.

The adapter always sets `approved_for_execution=False` in outputs.

---

## 8. Safety Guardrails

- `approved_for_execution` is schema-enforced `False` on all four models that carry it
  (`HumanFeedbackEntry`, `HumanFeedbackMemoryRecord`, `HumanFeedbackMemorySummary`,
  `HumanFeedbackMemoryReport`). Setting it to `True` raises `ValueError`.
- `decision="overrode"` requires a non-empty `override_reason` (Phase 4M-F Codex fix):
  `HumanFeedbackEntry` raises `ValueError` if `decision == "overrode"` and `override_reason`
  is missing, empty, or whitespace-only. This is a hard validation failure, not a soft warning,
  so override audit context cannot silently be omitted.
- No live imports: streamlit, anthropic, alpaca, finnhub, polygon, requests are absent.
- No persistence, database, vector store, or file writes.
- No brokerage, order, or execution fields.
- No pathway to authorize any trade.

---

## 9. executed_manually Semantics

`decision="executed_manually"` is a **memory label** only. It records that the human
reported they executed a trade manually, outside the system. It does not:

- Set `approved_for_execution=True`
- Trigger any execution
- Create any order or account reference

Status derivation treats `executed_manually` the same as `accepted` or `skipped` —
the resulting record status is `"recorded"`, not `"needs_review"`.

The `manual_execution_count` in `HumanFeedbackMemorySummary` tracks how many entries
carried this decision for audit purposes.

---

## 10. Status Precedence

Status is determined by `determine_human_feedback_memory_status()` using this precedence:

1. **blocked** — HumanReviewReport.status == "blocked" OR any record status == blocked
2. **needs_review** — any record status == needs_review
3. **resolved** — all non-archived/non-unknown/non-superseded records are resolved
4. **recorded** — all non-archived/non-unknown/non-superseded records are recorded (or any recorded)
5. **archived** — all records are archived
6. **unknown** — no records or no non-terminal statuses

Record-level status is derived by `_derive_record_status()`:
- `initial_status` overrides all derivation if provided
- `hrr_blocked=True` → blocked
- `review_required=True` → needs_review
- `rejected`, `overrode`, `needs_revision` in decisions → needs_review
- Otherwise → recorded

---

## 11. Deduplication

All collection and builder functions deduplicate using first-occurrence-wins:
- `source_refs` deduplicated by `source_id`
- `evidence_ids`, `artifact_refs`, `source_ids` deduplicated by value
- Order is preserved from first occurrence

---

## 12. Relationship to Phase 3F (Human Review) and Phase 3G (Review Loop)

Phase 4M-F sits **downstream and parallel** to Phase 3F and Phase 3G:

- **Phase 3F — Human Review / Feedback Schema Skeleton**: defines the per-run human review
  artifact (`HumanReviewReport`, `ReviewRequest`, etc.). Its scope is the **review event itself**:
  did the reviewer block, request revisions, or approve a single run's decision packet.
  Phase 4M-F consumes a Phase 3F `human_review_report` (duck-typed) as an upstream artifact in
  its `HumanFeedbackMemoryInputBundle`. If the human review report is `blocked`, the
  derived `HumanFeedbackMemoryReport.status` is forced to `blocked` (status precedence).

- **Phase 3G — Offline Review Loop / Reliability Run Report Skeleton**: aggregates the
  decision packet, human review report, validation aggregate, and staleness report into a
  single per-run reliability run report. Phase 4M-F consumes a Phase 3G `review_loop_report`
  (duck-typed) as an upstream artifact when available. Source IDs and evidence IDs propagate
  from the review loop report into the human feedback memory report.

- **Phase 4M-F adds**: a **memory layer** that persists multiple feedback entries per target
  across time, supports outcome tracking (`positive`, `negative`, `avoided_loss`,
  `caused_bad_action`, …), records lessons, and flags entries for downstream agent evaluation.
  Phase 3F captures the human's verdict on a single review event; Phase 4M-F retains and
  summarizes those verdicts as a feedback corpus that later subphases can mine.

No Phase 3F or Phase 3G artifact is mutated by Phase 4M-F. The relationship is consumer-only.

---

## 13. Downstream Phase 4M Status

| Phase | Status | Scope |
|-------|--------|-------|
| 4M-G | **Accepted** | **Agent Evaluation** — feedback-driven agent scoring (per `PROJECT_STATE.md` / `CURRENT_TASK.md`). Cross-memory feedback aggregation and lesson synthesis were folded into Agent Evaluation rather than carved out as a separate numbered subphase. Agent Evaluation records remain offline / mock-only descriptive artifacts; no prompt, model, or agent-definition mutation, no DB / vector store / persistence, no live integration. |
| 4M-H | **Implemented — awaiting Codex re-review** | **Phase 4 Memory Closeout** — closeout / acceptance package for Roadmap v4 Phase 4 Memory + Human Feedback + Review covering 4M-A through 4M-G. Documentation and state-file reconciliation only; no functional code, no DB / vector store / persistence, no UI, no live integration, no Phase 4A live wiring, no Phase 5 implementation. |

> Retained as historical roadmap context. Phase 5 has not started.