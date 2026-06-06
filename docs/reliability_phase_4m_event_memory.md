# Phase 4M-C: Catalyst / News / Earnings Memory

**Phase**: 4M-C  
**Status**: **Accepted**  
**Last updated**: 2026-05-26 (status reconciled 2026-05-27)  

> **Note on historical phrasing below**: this document was drafted when Phase
> 4M-D through 4M-G were still pending. All Phase 4M subphases through 4M-G
> are now accepted, and Phase 4M-H Phase 4 Memory Closeout has been
> implemented and is awaiting Codex review. "Pending" labels and the
> "Future Subphases" section below are retained as historical roadmap context.

---

## Purpose

Phase 4M-C implements the **Catalyst / News / Earnings Memory** layer of the
Roadmap v4 Phase 4 Memory + Human Feedback mainline. It provides a standalone,
deterministic, offline/mock-only schema and helper layer for recording and
reviewing event-type memory records covering:

- Catalysts (product announcements, partnerships, strategic decisions)
- News (regulatory probes, analyst actions, macro news)
- Earnings (quarterly results, EPS surprises, revenue beats/misses)
- Guidance (management guidance updates, raised/cut guidance)
- Estimate revisions (analyst consensus changes)
- Regulatory, product, management, legal, macro, and other events

This phase defines memory record schemas and helper functions only. It does
**not** create a database, persistence engine, UI, live workflow integration,
vector store, external API, Finnhub calls, earnings API calls, or
broker/order/execution behavior.

---

## Relationship to Roadmap v4 Phase 4

Roadmap v4 Phase 4 defines the Memory + Human Feedback mainline. The Phase 4M
subphase sequence is:

| Subphase | Description | Status |
|----------|-------------|--------|
| Phase 4M-A | Research Run Memory Schema | Accepted |
| Phase 4M-B | Thesis Memory by Horizon | Accepted |
| **Phase 4M-C** | **Catalyst / News / Earnings Memory** | **Accepted (this phase)** |
| Phase 4M-D | Allocation Decision Memory | Accepted |
| Phase 4M-E | Option Trade Plan Memory | Accepted |
| Phase 4M-F | Human Feedback Layer | Accepted |
| Phase 4M-G | Agent Evaluation | Accepted |
| Phase 4M-H | Phase 4 Memory Closeout | Implemented — awaiting Codex review |

Phase 4A (Integration Boundary Contract) remains accepted early infrastructure
and is **not** part of the Phase 4M memory mainline.

---

## Relationship to Prior Phases

### Phase 4M-A — Research Run Memory Schema

`ResearchRunMemoryRecord` captures the overall research run decision trail.
`EventMemoryRecord` is a fine-grained event-level complement: each event (earnings
beat, catalyst, news item) links to the parent research run via the optional
`memory_id` field.

### Phase 4M-B — Thesis Memory by Horizon

`HorizonThesisMemoryRecord` captures horizon-specific investment theses.
`EventMemoryRecord` can link to a specific thesis via the optional `thesis_id`
field, allowing events (especially thesis-changing ones) to be traced back to
the thesis they affect.

### Phase 3R-A — Event Intelligence Agents Skeleton

`EventIntelligenceReport` from Phase 3R-A is an optional upstream artifact in
`EventMemoryInputBundle`. Event Intelligence produces `CatalystAssessment`,
`NewsImpactAssessment`, `EarningsPlaybookAssessment`, and
`EstimateRevisionAssessment` objects. Phase 4M-C persists the memory record of
these events for audit and cross-run comparison, without re-computing them.

---

## Memory Schema

### Literal Type Aliases (8)

| Alias | Values |
|-------|--------|
| `EventMemoryStatus` | unknown, active, reviewed, needs_review, thesis_changing, archived, blocked |
| `EventMemoryType` | catalyst, news, earnings, guidance, estimate_revision, regulatory, product, management, legal, macro, other, unknown |
| `EventMemoryImpactDirection` | positive, negative, mixed, neutral, unknown |
| `EventMemoryImpactMagnitude` | low, medium, high, unknown |
| `EventMemoryReviewStatus` | not_required, pending, reviewed, escalated, blocked, unknown |
| `EventMemoryEventType` | event_recorded, review_requested, review_completed, thesis_changed, market_reaction_observed, human_feedback_added, archived, unknown |
| `EventMemoryActorType` | system, user, reviewer, agent, unknown |
| `EventMemorySourceType` | news, earnings_report, sec_filing, analyst_note, event_intelligence, research_memory, thesis_memory, catalyst_snapshot, human_review, tool_result, user_input, unknown |

### Models (6)

#### `EventMemorySourceRef`

A stable pointer to an upstream artifact, news item, filing, or analyst note.
Fields: `source_id` (required), `source_type`, `artifact_id`, `evidence_id`,
`url`, `published_at`, `field_path`, `label`, `metadata`, `warnings`.

#### `EventMemoryLogEntry`

A timestamped lifecycle event in an `EventMemoryRecord`'s event log.
Fields: `event_id`, `event_type`, `created_at`, `actor`, `description`,
`source_ids`, `evidence_ids`, `metadata`, `warnings`.

#### `EventMemoryRecord`

The core event memory record for a single catalyst, news item, earnings event,
guidance update, estimate revision, or other market event. Fields include:
- Identity: `event_memory_id`, `target`, `run_id`, `memory_id`, `thesis_id`
- Classification: `event_type`, `status`, `review_status`, `event_name`,
  `event_date`, `recorded_at`, `reviewed_at`
- Impact: `impact_direction`, `impact_magnitude`, `thesis_changing`,
  `affected_horizons`
- Content: `summary`, `market_reaction`, `guidance_update`,
  `estimate_revision_summary`
- References: `source_refs`, `evidence_ids`, `artifact_refs`
- Lifecycle: `event_log`, `warnings`
- Guard: `approved_for_execution` (always False)

#### `EventMemoryInputBundle`

Input bundle for building an `EventMemoryReport`. Optional duck-typed upstream
artifacts: `research_run_memory_record`, `thesis_memory_report`,
`event_intelligence_report`, `decision_packet`, `human_review_report`.

#### `EventMemorySummary`

Aggregated counts: `record_count`, `catalyst_count`, `news_count`,
`earnings_count`, `guidance_count`, `estimate_revision_count`,
`thesis_changing_count`, `needs_review_count`, `reviewed_count`,
`high_impact_count`, `affected_horizons`, `top_warnings`.

#### `EventMemoryReport`

Full event memory report containing all `EventMemoryRecord` objects for a
target, with a summary, aggregated source/evidence/artifact refs, and a status.

---

## Event Review Lifecycle

```
event_recorded → review_requested → review_completed (→ human_feedback_added)
     ↓                    ↓
  archived          thesis_changed
```

An event begins as `event_recorded` in the log. If the event requires review
(thesis_changing, high impact, or pending review_status), a `review_requested`
entry is appended. When a human reviews the event, a `review_completed` entry
is added (future phase: via human feedback layer). If human feedback is
provided, `human_feedback_added` is appended.

---

## Thesis-Changing Event Tracking

A `thesis_changing=True` flag on an `EventMemoryRecord` signals that the event
is material enough to potentially invalidate or require update of an existing
investment thesis. Auto-status logic:

1. `thesis_changing=True` + `review_status` in (`pending`, `escalated`) → `needs_review`
2. `thesis_changing=True` + other review statuses → `thesis_changing`

At the report level, any record with `thesis_changing=True` elevates the report
status to at least `thesis_changing` (higher than `needs_review`, lower than
`blocked`).

The `thesis_id` field on `EventMemoryRecord` optionally links the event to the
specific `HorizonThesisMemoryRecord` from Phase 4M-B that is being affected.

---

## Market Reaction / Guidance / Estimate Revision Memory

Three optional text fields on `EventMemoryRecord` capture structured narrative
for common event types:

- `market_reaction`: Observed price/volume reaction to the event.
- `guidance_update`: New guidance text if the event includes a guidance update.
- `estimate_revision_summary`: Summary of estimate revision if applicable.

These are free-form optional strings and do not imply computation or data
fetching. They are populated by callers who have processed upstream artifacts.

---

## Event Log Design

Each `EventMemoryRecord` contains an `event_log: list[EventMemoryLogEntry]`.
The builder (`build_event_memory_record`) automatically creates:

1. An `event_recorded` entry on creation.
2. A `review_requested` entry if the record requires review or is blocked.
3. A `thesis_changed` entry if `thesis_changing=True` and status is `thesis_changing`.

Log entries have deterministic `event_id` values derived from
`event_memory_id + event_type + created_at`.

---

## Status Logic

### Single-Record Status (auto-determined in `build_event_memory_record`)

Priority:
1. `initial_status` override (explicit caller override)
2. `blocked` — human_review_report blocked, or `review_status=blocked`
3. `thesis_changing` — `thesis_changing=True` (unless review pending → `needs_review`)
4. `needs_review` — `impact_magnitude=high` with unreviewed status, or `review_status` in (`pending`, `escalated`)
5. `reviewed` — `review_status=reviewed`
6. `active` — default clean state

### Report-Level Status (`determine_event_memory_status`)

**Precedence: blocked > thesis_changing > needs_review > reviewed > active > archived > unknown**

| Status | Condition |
|--------|-----------|
| `blocked` | HRR blocked in input_bundle, OR any record has `status=blocked` |
| `thesis_changing` | Any record has `status=thesis_changing` or `thesis_changing=True` |
| `needs_review` | Any record has `status=needs_review`, OR any high-impact unreviewed record |
| `reviewed` | All records have `status=reviewed` |
| `active` | Records exist, no above signals |
| `archived` | All records are archived |
| `unknown` | No records, or only unknown statuses |

---

## ToolResult Adapter

`event_memory_tool_result_from_report(report, run_id=None)` wraps an
`EventMemoryReport` as a `ToolResult` for evidence-store integration.

- Stable tool name: `"event_memory_report"`
- `evidence_id` is deterministic from the full report payload (includes all
  records, event logs, source_refs, evidence_ids, warnings)
- `outputs` includes: `report_id`, `target`, `status`, full `report`, `summary`,
  `record_count`, `thesis_changing_count`, `needs_review_count`,
  `high_impact_count`, `calculation_version`, `approved_for_execution=False`
- No fake evidence; no execution implication; no persistence side effect

---

## No Persistence / No DB / No Vector Store

This phase is schema-only/helper-only. There is:

- No file write
- No database write (SQL, NoSQL, time-series)
- No vector store (Chroma, Pinecone, Weaviate, etc.)
- No external API call (Finnhub, news API, earnings API, broker)
- No live LLM call
- No Streamlit UI

Memory records are Python objects returned by helpers. Persistence is a
responsibility of future phases or the caller.

---

## Offline/Mock-Only Nature

All builders accept explicit timestamps to ensure determinism. When no
timestamp is provided, the fallback `"1970-01-01T00:00:00Z"` is used:

```
Timestamp resolution priority:
  1. Explicit argument (recorded_at / created_at)
  2. input_bundle.as_of
  3. "1970-01-01T00:00:00Z" (deterministic fallback)
```

Identical inputs always produce identical outputs. No wall-clock dependency.

---

## No Execution Authorization

`approved_for_execution` is `False` on all models (`EventMemoryRecord`,
`EventMemorySummary`, `EventMemoryReport`) and is schema-enforced by
`@model_validator`. Any attempt to set `approved_for_execution=True` raises
`ValidationError`. There is no code path that can set it to `True`.

---

## Key Files

| File | Description |
|------|-------------|
| `lib/reliability/event_memory.py` | Phase 4M-C: 8 Literal type aliases, 6 Pydantic models, 12 helpers |
| `scripts/test_reliability_event_memory.py` | Test suite: 298/298 pass (35 sections) |
| `docs/reliability_phase_4m_event_memory.md` | This design document |

---

## Public API Summary

**Literal type aliases (8)**:
`EventMemoryActorType`, `EventMemoryEventType`, `EventMemoryImpactDirection`,
`EventMemoryImpactMagnitude`, `EventMemoryReviewStatus`, `EventMemorySourceType`,
`EventMemoryStatus`, `EventMemoryType`

**Models (6)**:
`EventMemoryInputBundle`, `EventMemoryLogEntry`, `EventMemoryRecord`,
`EventMemoryReport`, `EventMemorySourceRef`, `EventMemorySummary`

**Helpers (12)**:
`build_event_memory_log_entry`, `build_event_memory_record`,
`build_event_memory_report`, `collect_event_memory_artifact_refs`,
`collect_event_memory_evidence_ids`, `collect_event_memory_source_ids`,
`determine_event_memory_status`, `event_memory_tool_result_from_report`,
`make_event_memory_log_entry_id`, `make_event_memory_record_id`,
`make_event_memory_report_id`, `summarize_event_memory`

---

## Subsequent Phase 4M Subphases (historical roadmap context)

> Status reconciled 2026-05-27: all Phase 4M subphases through 4M-G are now
> accepted. Phase 4M-H Phase 4 Memory Closeout has been implemented and is
> awaiting Codex review. This table is retained as historical roadmap context.

| Subphase | Description | Status |
|----------|-------------|--------|
| Phase 4M-D | Allocation Decision Memory — records allocation decisions and constraint violations | Accepted |
| Phase 4M-E | Option Trade Plan Memory — records option expression decisions and thesis linkage | Accepted |
| Phase 4M-F | Human Feedback Layer — structured human feedback integration across memory records | Accepted |
| Phase 4M-G | Agent Evaluation — correctness and calibration scoring across memory-augmented runs | Accepted |
| Phase 4M-H | Phase 4 Memory Closeout — Roadmap v4 Phase 4 coverage map, regression sweep, conservative next-phase recommendation | Implemented — awaiting Codex review |

---

## Disclaimer

All outputs from this module are for research and educational purposes only.
They do not constitute investment advice. Markets involve risk; invest with caution.
