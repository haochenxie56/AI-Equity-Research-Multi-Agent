# Phase 4M-A: Research Run Memory Schema

**Date**: 2026-05-24 (status reconciled 2026-05-27)
**Status**: **Accepted** (Codex fixes applied and accepted)
**Module**: `lib/reliability/research_memory.py`
**Test suite**: `scripts/test_reliability_research_memory.py` (165/165)

> **Note on historical phrasing below**: this document was originally drafted
> when Phase 4M-A was the first Phase 4M subphase and 4M-B through 4M-G were
> still future work. All Phase 4M subphases through 4M-G are now accepted, and
> Phase 4M-H Phase 4 Memory Closeout has been implemented and is awaiting
> Codex review. Historical "(future)" labels and the "Future Subphases" section
> below are preserved for context but no longer describe current state.

---

## 1. Purpose

Phase 4M-A implements the **Research Run Memory Schema** — the first subphase of
Roadmap v4 Phase 4 (Memory + Human Feedback + Review).

The goal is to create a standalone, deterministic, offline/mock-only memory schema
layer for recording research runs and their decision-trail references.  This phase
defines memory records and helper functions only.  It does not create a database,
persistence engine, vector store, UI, live workflow integration, or broker/order
behavior.

All outputs are auditable research artifacts only.  `approved_for_execution` is
always `False`.

---

## 2. Relationship to Roadmap v4 Phase 4

### Phase 4 Memory + Human Feedback + Review

Phase 4M-A starts the mainline:

```
Phase 4M-A  Research Run Memory Schema          (Accepted — this phase)
Phase 4M-B  Thesis Memory by Horizon            (Accepted)
Phase 4M-C  Catalyst / News / Earnings Memory   (Accepted)
Phase 4M-D  Allocation Decision Memory          (Accepted)
Phase 4M-E  Option Trade Plan Memory            (Accepted)
Phase 4M-F  Human Feedback Layer                (Accepted)
Phase 4M-G  Agent Evaluation                    (Accepted)
Phase 4M-H  Phase 4 Memory Closeout             (Implemented — awaiting Codex review)
```

### Phase 4A Integration Boundary Contract

Phase 4A (`lib/reliability/integration_boundary.py`) was accepted before the Phase 3R
roadmap alignment review.  It is **early integration infrastructure** — a standalone,
no-op/pass-through contract that enables future live wiring — and is explicitly **not**
the Phase 4 Memory mainline.

Phase 4A is retained, frozen, and not wired into the live app.  Phase 4M-A does not
modify, extend, or depend on Phase 4A.

### Relationship to Accepted Phase 3 and Phase 3R Artifacts

Phase 4M-A consumes references to upstream reliability artifacts from Phase 3A–3G and
Phase 3R-A through 3R-D:

| Upstream Phase | Artifact Referenced |
|----------------|---------------------|
| Phase 3A | OrchestrationReport (via source_refs) |
| Phase 3B | HorizonSynthesisReport (via source_refs) |
| Phase 3C | MacroAgentResult (via source_refs) |
| Phase 3D | DebateReport (via source_refs) |
| Phase 3E | DecisionPacket (status read for memory status determination) |
| Phase 3F | HumanReviewReport (status read for blocked detection) |
| Phase 3G | ReliabilityRunReport (status read for review signal) |
| Phase 3R-A | EventIntelligenceReport (optional artifact ref) |
| Phase 3R-B | TradePlanReport (optional artifact ref) |
| Phase 3R-C | AllocationReport (optional artifact ref) |
| Phase 3R-D | OptionExpressionReport (optional artifact ref) |
| Phase 4A | IntegrationBoundary result (optional artifact ref) |

All upstream artifacts are **duck-typed** (`Optional[Any]`) in `ResearchRunMemoryInputBundle`.
Only a small number of attributes (`status`, `report_id`, etc.) are accessed by name.
Full artifact content is **not duplicated** — this phase records references and
snapshots only.

---

## 3. Memory Schema

### 3.1 Literal Type Aliases (Enums)

| Alias | Values |
|-------|--------|
| `MemoryRecordStatus` | unknown, active, archived, superseded, invalidated, needs_review |
| `ResearchRunMemoryStatus` | unknown, recorded, incomplete, needs_review, blocked |
| `ResearchRunMemorySourceType` | orchestration, horizon_synthesis, macro, debate, decision_packet, human_review, review_loop, event_intelligence, trade_plan, allocation, option_expression, integration_boundary, validation, staleness, critic, tool_result, user_feedback, unknown |
| `MemoryEventType` | research_run_created, thesis_created, decision_created, review_requested, human_feedback_added, outcome_updated, superseded, invalidated, unknown |
| `MemoryActorType` | system, user, reviewer, agent, unknown |

### 3.2 Pydantic Models

#### `MemorySourceRef`

A stable pointer to an upstream reliability artifact.  Used to trace the decision
trail without duplicating full artifact content.

| Field | Type | Notes |
|-------|------|-------|
| source_id | str | Non-empty. Primary deduplication key. |
| source_type | ResearchRunMemorySourceType | Which agent/module produced this. |
| artifact_id | Optional[str] | ID of the specific upstream artifact. |
| run_id | Optional[str] | The run that produced this artifact. |
| target | Optional[str] | Ticker or research target. |
| field_path | Optional[str] | Specific field within the artifact. |
| evidence_id | Optional[str] | Evidence store ID if registered. |
| label | Optional[str] | Human-readable label. |
| metadata | dict | Open-ended context. |
| warnings | list[str] | Ref-level warnings. |

#### `MemoryEvent`

A timestamped lifecycle event in the memory record's event log.

| Field | Type | Notes |
|-------|------|-------|
| event_id | str | Deterministic hash ID (prefix: `mevt_`). |
| event_type | MemoryEventType | What happened. |
| created_at | str | ISO timestamp. |
| actor | MemoryActorType | Who triggered this event. Default: system. |
| description | str | Free-form description. |
| source_refs | list[MemorySourceRef] | Associated artifact refs. |
| metadata | dict | Open-ended context. |
| warnings | list[str] | Event-level warnings. |

#### `ResearchRunMemoryInputBundle`

Input bundle for building a research run memory record from accepted artifacts.

| Field | Type | Notes |
|-------|------|-------|
| run_id | str | Non-empty. Required. |
| target | str | Non-empty. Required (ticker or research target). |
| as_of | Optional[str] | Reference timestamp. |
| created_at | Optional[str] | Override created_at for determinism. |
| workflow_name | Optional[str] | Name of originating workflow. |
| source_refs | list[MemorySourceRef] | Caller-supplied artifact pointers. |
| tool_result_ids | list[str] | Evidence-store tool result IDs. |
| evidence_ids | list[str] | Evidence-store evidence IDs. |
| artifact_refs | list[str] | Opaque artifact ID strings. |
| reliability_report | Optional[Any] | Phase 3G ReliabilityRunReport (duck-typed). |
| decision_packet | Optional[Any] | Phase 3E DecisionPacket (duck-typed). |
| human_review_report | Optional[Any] | Phase 3F HumanReviewReport (duck-typed). |
| event_intelligence_report | Optional[Any] | Phase 3R-A (duck-typed). |
| trade_plan_report | Optional[Any] | Phase 3R-B (duck-typed). |
| allocation_report | Optional[Any] | Phase 3R-C (duck-typed). |
| option_expression_report | Optional[Any] | Phase 3R-D (duck-typed). |
| integration_boundary_report | Optional[Any] | Phase 4A (duck-typed). |
| validation_summary | Optional[Any] | ValidationAggregate or summary (duck-typed). |
| warnings | list[str] | Caller-supplied bundle-level warnings. |

#### `ResearchRunMemorySummary`

Compact summary computed from the memory record.  `approved_for_execution` is always
`False` (schema-enforced by `model_validator`).

| Field | Type | Notes |
|-------|------|-------|
| run_id | str | — |
| target | str | — |
| status | ResearchRunMemoryStatus | — |
| source_count | int | Number of distinct MemorySourceRefs. |
| evidence_count | int | Number of distinct evidence IDs. |
| tool_result_count | int | Number of distinct tool result IDs. |
| artifact_count | int | Number of artifact_refs. |
| has_decision_packet | bool | — |
| has_human_review | bool | — |
| has_event_intelligence | bool | — |
| has_trade_plan | bool | — |
| has_allocation | bool | — |
| has_option_expression | bool | — |
| has_integration_boundary | bool | — |
| review_required | bool | — |
| blocked | bool | — |
| top_warnings | list[str] | First 5 warnings. |
| approved_for_execution | bool | Always False. |

#### `ResearchRunMemoryRecord`

Full memory record for one research run.  Captures the decision trail by reference.
`approved_for_execution` is always `False` (schema-enforced).

| Field | Type | Notes |
|-------|------|-------|
| memory_id | str | Deterministic hash ID (prefix: `rmem_`). |
| run_id | str | — |
| target | str | — |
| status | ResearchRunMemoryStatus | — |
| summary | ResearchRunMemorySummary | Compact summary. |
| source_refs | list[MemorySourceRef] | Deduplicated artifact pointers. |
| evidence_ids | list[str] | Deduplicated evidence IDs. |
| tool_result_ids | list[str] | Deduplicated tool result IDs. |
| artifact_refs | list[str] | Opaque artifact IDs. |
| event_log | list[MemoryEvent] | Lifecycle event log. |
| created_at | str | ISO timestamp. |
| updated_at | str | ISO timestamp. |
| calculation_version | str | `"research_run_memory_v1"`. |
| warnings | list[str] | Aggregated warnings. |
| approved_for_execution | bool | Always False. |

#### `ResearchRunMemoryIndexEntry`

Lightweight index entry for fast-access memory lookup.

| Field | Type | Notes |
|-------|------|-------|
| memory_id | str | — |
| run_id | str | — |
| target | str | — |
| status | ResearchRunMemoryStatus | — |
| created_at | str | — |
| updated_at | str | — |
| source_count | int | — |
| evidence_count | int | — |
| review_required | bool | — |
| blocked | bool | — |
| tags | list[str] | Optional caller-supplied tags. |

---

## 4. Source / Evidence / Artifact Reference Strategy

Phase 4M-A uses a **reference-based** approach:

- **Source refs**: `MemorySourceRef` objects point to upstream artifact IDs without
  embedding full content.  This avoids memory bloat as the number of upstream artifacts
  grows.
- **Evidence IDs**: Collected from caller-supplied lists and from `evidence_id` fields
  in source refs.  Deduplicated with first-occurrence order preserved.
- **Tool result IDs**: Collected from caller-supplied lists.  Deduplicated.
- **Artifact refs**: Opaque strings for caller-supplied artifact reference IDs.

Deduplication is deterministic: first occurrence wins, insertion order preserved.

### Auto-detection of source refs

If optional upstream artifacts are provided in `ResearchRunMemoryInputBundle`,
`collect_memory_source_refs()` auto-generates `MemorySourceRef` objects from them
using `report_id`, `packet_id`, or `bundle_id` attributes.  Caller-supplied
source_refs take precedence.

---

## 5. Status Logic

### Precedence (highest wins)

```
blocked > needs_review > incomplete > recorded > unknown
```

| Status | Condition |
|--------|-----------|
| blocked | Human review report status is "blocked" OR decision packet status is "blocked" |
| needs_review | review_required signal present AND missing artifacts are not both dp and rr |
| incomplete | Both decision_packet and reliability_report missing |
| recorded | Clean run with sufficient source/evidence/artifact refs (dp and rr present, no issues) |
| unknown | No refs available; unexpected state |

### Core artifacts

The following are treated as "important" for status purposes:
- `decision_packet` (Phase 3E)
- `reliability_report` (Phase 3G)

Missing both → `incomplete`.
Missing one with other review signals → `needs_review`.
Both present, clean run → `recorded`.
Human review blocked → always `blocked` (overrides all).

---

## 6. Event Log Design

The event log traces the lifecycle of a memory record:

1. **research_run_created** — always added on record creation.
2. **review_requested** — added when `review_required=True` or `blocked=True`.
3. Future: **human_feedback_added**, **outcome_updated**, **superseded**,
   **invalidated** (added by future Human Feedback Layer subphases).

Each `MemoryEvent` has a deterministic `event_id` derived from `memory_id`,
`event_type`, and `created_at`.  Events are not mutable after creation in this phase.

---

## 7. ToolResult Adapter

`research_run_memory_tool_result_from_record()` wraps a `ResearchRunMemoryRecord`
as a `ToolResult` for evidence-store integration.

| Property | Value |
|----------|-------|
| `tool_name` | `"research_run_memory_record"` (stable) |
| `ticker` | `record.target` |
| `run_id` | `record.run_id` |
| `inputs` | `{"run_id": ..., "target": ...}` |
| `outputs` | Full memory record (`record.model_dump()`), `summary`, `calculation_version`, and summary count fields |
| `evidence_id` | Deterministic hash of the full outputs payload — content-sensitive to `source_refs`, `event_log`, `warnings`, and `artifact_refs`, not just summary counts |

The `outputs` payload includes:
- `record`: `record.model_dump()` — the full serialized record including `source_refs`,
  `event_log`, `artifact_refs`, and `warnings`.
- `summary`: `record.summary.model_dump()` — the compact summary.
- `calculation_version`: version string.
- Summary count fields and flags for backward compatibility.

This ensures two records with the same `memory_id` / status / counts but different
`source_refs`, `event_log`, `warnings`, or `artifact_refs` produce distinct evidence IDs.

The adapter does not:
- Look like an order ticket or persistence operation receipt.
- Contain broker, account, order, or execution fields.
- Set `approved_for_execution = True`.
- Make network calls, write to database, or modify any input.
- Imply that the record has been persisted or written anywhere.

---

## 8. No Persistence / No DB / No Vector Store

Phase 4M-A is **schema and helper only**.  There is no:

- File write or persistence layer.
- Database (SQL, NoSQL, or otherwise).
- Vector store (chromadb, pinecone, weaviate, etc.).
- External API call or network connection.
- Claude API call or live LLM inference.

The `ResearchRunMemoryRecord` is a pure in-memory Python object.  Persistence is left
to future phases.

---

## 9. Offline / Mock-only Nature

All Phase 4M-A helpers are pure functions:

- **Deterministic output** for identical inputs — including when no explicit timestamps
  are provided.  `build_research_run_memory_record()` resolves `created_at` /
  `updated_at` using this priority order:
  1. explicit `created_at` / `updated_at` arguments;
  2. `input_bundle.created_at` if present;
  3. `input_bundle.as_of` if present;
  4. `_DETERMINISTIC_TIMESTAMP_DEFAULT` (`"1970-01-01T00:00:00Z"`).
  No wall-clock time is ever used in record construction.
- **Explicit timestamp override** is fully supported by passing `created_at` and/or
  `updated_at` to `build_research_run_memory_record()`.
- **No side effects** — no mutation of inputs, no file writes, no network calls.
- **No external dependencies** beyond `pydantic` and `lib.reliability.adapters`.
- Tests use mock duck-typed objects (stdlib `types.SimpleNamespace`) without any live
  reliability-layer artifacts.

---

## 10. No Execution Authorization

- `approved_for_execution` is `False` in `ResearchRunMemoryRecord`,
  `ResearchRunMemorySummary`, and the ToolResult adapter output.
- Schema-enforced via `model_validator` in `ResearchRunMemoryRecord` and
  `ResearchRunMemorySummary` — any attempt to set it `True` raises `ValueError`.
- No pathway exists in this module to set `approved_for_execution = True`.

---

## 11. Helper Functions

| Function | Description |
|----------|-------------|
| `make_research_run_memory_id(run_id, target, as_of)` | Deterministic `rmem_` prefixed ID |
| `make_memory_event_id(memory_id, event_type, created_at)` | Deterministic `mevt_` prefixed ID |
| `collect_memory_source_refs(bundle)` | Deduplicated MemorySourceRef list |
| `collect_memory_evidence_ids(bundle, source_refs)` | Deduplicated evidence ID list |
| `collect_memory_tool_result_ids(bundle, source_refs)` | Deduplicated tool result ID list |
| `determine_research_run_memory_status(bundle, refs)` | Returns (status, review_required, blocked, warnings) |
| `build_memory_event(event_type, description, memory_id, ...)` | Build a single MemoryEvent |
| `summarize_research_run_memory(bundle, status, ...)` | Build ResearchRunMemorySummary |
| `build_research_run_memory_record(bundle, created_at, updated_at)` | Full record builder |
| `build_memory_index_entry(record, tags)` | Build ResearchRunMemoryIndexEntry |
| `research_run_memory_tool_result_from_record(record)` | ToolResult adapter |

---

## 12. Subsequent Phase 4M Subphases (historical roadmap context)

> Status reconciled 2026-05-27: all Phase 4M subphases through 4M-G are now
> accepted. Phase 4M-H Phase 4 Memory Closeout has been implemented and is
> awaiting Codex review. This section originally described future work and is
> retained as historical roadmap context.

| Subphase | Description | Status |
|----------|-------------|--------|
| Phase 4M-B | Thesis Memory by Horizon — record thesis evolution per horizon per ticker | Accepted |
| Phase 4M-C | Catalyst / News / Earnings Memory — record event intelligence findings | Accepted |
| Phase 4M-D | Allocation Decision Memory — record allocation decisions and constraint history | Accepted |
| Phase 4M-E | Option Trade Plan Memory — record option expression decisions | Accepted |
| Phase 4M-F | Human Feedback Layer — record human corrections and feedback for agent improvement | Accepted |
| Phase 4M-G | Agent Evaluation — offline evaluation of agent output quality over time | Accepted |
| Phase 4M-H | Phase 4 Memory Closeout — Roadmap v4 Phase 4 coverage map, regression sweep, and conservative next-phase recommendation | Implemented — awaiting Codex review |

---

## 13. Key Files

| File | Role |
|------|------|
| `lib/reliability/research_memory.py` | Main implementation |
| `scripts/test_reliability_research_memory.py` | Test suite (138/138) |
| `docs/reliability_phase_4m_research_memory.md` | This document |
| `lib/reliability/__init__.py` | Package entry point (Phase 4M-A exports added) |

---

## 14. Disclaimer

All outputs from this module are for research and educational purposes only.
They do not constitute investment advice.  Markets involve risk; invest with caution.
