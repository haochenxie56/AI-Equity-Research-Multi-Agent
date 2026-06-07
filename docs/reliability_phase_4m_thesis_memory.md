# Reliability Phase 4M-B: Thesis Memory by Horizon

**Date**: 2026-05-24 (status reconciled 2026-05-27)
**Phase**: 4M-B
**Status**: **Accepted** (import path fix accepted)

> **Note on historical phrasing below**: this document was drafted when later
> Phase 4M subphases were still pending. All Phase 4M subphases through 4M-G
> are now accepted, and Phase 4M-H Phase 4 Memory Closeout has been
> implemented and is awaiting Codex review. "Pending" labels and the
> "Future Subphases" section below are retained as historical roadmap context.

---

## 1. Purpose

Phase 4M-B implements a standalone, deterministic, offline/mock-only schema and helper layer for recording horizon-specific investment thesis records and their status over time.

A **thesis memory record** (`HorizonThesisMemoryRecord`) captures:
- The thesis text for one investment horizon (short / medium / long / multi_horizon)
- Key underlying assumptions and their evidence references
- Invalidation conditions that, if triggered, would require revisiting the thesis
- A lifecycle event log (creation, review requests, invalidation, etc.)
- Status tracking (active, needs_review, invalidated, superseded, archived, blocked)

A **thesis memory report** (`ThesisMemoryReport`) aggregates all horizon-specific thesis records for a target ticker into one auditable artifact, resolves a report-level status, and exposes a ToolResult wrapper for evidence-store integration.

This phase introduces **no** database, persistence engine, UI, live workflow integration, vector store, external API calls, or broker/order/execution behavior.

---

## 2. Relationship to Roadmap v4 Phase 4

Phase 4M-B is the second subphase of Roadmap v4 Phase 4 — Memory + Human Feedback:

| Subphase | Name | Status |
|----------|------|--------|
| Phase 4M-A | Research Run Memory Schema | Accepted |
| **Phase 4M-B** | **Thesis Memory by Horizon** | **Accepted (this phase)** |
| Phase 4M-C | Catalyst / News / Earnings Memory | Accepted |
| Phase 4M-D | Allocation Decision Memory | Accepted |
| Phase 4M-E | Option Trade Plan Memory | Accepted |
| Phase 4M-F | Human Feedback Layer | Accepted |
| Phase 4M-G | Agent Evaluation | Accepted |
| Phase 4M-H | Phase 4 Memory Closeout | Implemented — awaiting Codex review |

Phase 4A (Integration Boundary Contract) was accepted as early infrastructure prior to Phase 4 Memory mainline. It is frozen in its current standalone state and is not the Phase 4 Memory implementation.

---

## 3. Relationship to Phase 4M-A Research Run Memory

Phase 4M-A (`research_memory.py`) records run-level summaries — which agents ran, which artifacts were produced, whether a decision packet and reliability run report are present.

Phase 4M-B records thesis content — the actual investment thesis text, assumptions, and invalidation conditions — organized by investment horizon.

The two layers link through an optional `memory_id` field on `HorizonThesisMemoryRecord`, which can reference the `memory_id` of a `ResearchRunMemoryRecord`. The `ThesisMemoryInputBundle` accepts a duck-typed `research_run_memory_record` to auto-extract source IDs.

---

## 4. Relationship to Accepted Phase 3 Components

Phase 4M-B consumes outputs from the following Phase 3 and Phase 3R reliability modules (all optional, duck-typed, no hard imports):

| Source Module | Field in ThesisMemoryInputBundle | Used For |
|--------------|----------------------------------|---------|
| `horizon_synthesis.py` (Phase 3B) | `horizon_synthesis` | Source ID extraction, evidence IDs |
| `debate.py` (Phase 3D) | `debate_report` | Source ID extraction |
| `decision_packet.py` (Phase 3E) | `decision_packet` | Status signals (blocked) |
| `human_review.py` (Phase 3F) | `human_review_report` | Block detection |
| `event_intelligence.py` (Phase 3R-A) | `event_intelligence_report` | Source IDs |
| `trade_plan.py` (Phase 3R-B) | `trade_plan_report` | Source IDs |
| `allocation_report.py` (Phase 3R-C) | `allocation_report` | Source IDs |
| `option_expression.py` (Phase 3R-D) | `option_expression_report` | Source IDs |
| `research_memory.py` (Phase 4M-A) | `research_run_memory_record` | memory_id linkage |

Missing optional artifacts produce warnings but never crash the build.

---

## 5. Memory Schema

### 5.1 Literal Type Aliases (8 public)

| Alias | Values |
|-------|--------|
| `ThesisMemoryStatus` | unknown, active, needs_review, invalidated, superseded, archived, blocked |
| `ThesisHorizon` | short, medium, long, multi_horizon, unknown |
| `ThesisDirection` | bullish, bearish, neutral, mixed, unknown |
| `ThesisConfidence` | low, medium, high, unknown |
| `ThesisInvalidationType` | price_level, fundamental, macro, earnings, catalyst, news, estimate_revision, technical, risk_limit, time_based, other, unknown |
| `ThesisMemoryEventType` | thesis_created, thesis_updated, thesis_review_requested, thesis_invalidated, thesis_superseded, thesis_archived, human_feedback_added, outcome_observed, unknown |
| `ThesisAssumptionImportance` | low, medium, high, unknown |
| `ThesisActorType` | system, user, reviewer, agent, unknown |

### 5.2 Models (7 public)

**ThesisAssumption**
- assumption_id, description (non-empty required)
- horizon, importance (ThesisAssumptionImportance)
- source_ids, evidence_ids, warnings (list fields, default_factory)

**ThesisInvalidationCondition**
- condition_id, description (non-empty required)
- invalidation_type, horizon
- trigger_level (Optional[float], non-negative if present)
- trigger_date (Optional[str])
- review_required (bool, defaults False)
- source_ids, evidence_ids, warnings (list fields)

**ThesisMemoryEvent**
- event_id, description, created_at (non-empty required)
- event_type, actor
- source_ids, evidence_ids, metadata, warnings

**HorizonThesisMemoryRecord**
- thesis_id, target, thesis_text (non-empty required)
- run_id (optional), memory_id (optional — links to ResearchRunMemoryRecord)
- horizon, direction, status, confidence
- assumptions, invalidation_conditions, source_ids, evidence_ids, artifact_refs
- event_log, created_at, updated_at, calculation_version, warnings
- **approved_for_execution: always False — schema-enforced**

**ThesisMemoryInputBundle**
- target (non-empty required), run_id (optional), memory_id (optional), as_of (optional)
- source_ids, evidence_ids, artifact_refs, warnings
- 9 duck-typed optional upstream artifacts (Any type)

**ThesisMemorySummary**
- target, status
- thesis_count, active_count, needs_review_count, invalidated_count, superseded_count, archived_count
- horizons_covered (sorted list), direction_counts (dict)
- high_confidence_count, invalidation_condition_count, review_required_count
- top_warnings, **approved_for_execution: always False**

**ThesisMemoryReport**
- report_id, target (non-empty required), run_id (optional)
- status, theses, summary
- source_ids, evidence_ids, artifact_refs, warnings
- created_at, updated_at, calculation_version
- **approved_for_execution: always False — schema-enforced**

---

## 6. Horizon-Specific Thesis Strategy

Each `HorizonThesisMemoryRecord` is scoped to one investment horizon. A `ThesisMemoryReport` typically contains 1–4 thesis records covering short, medium, long, and/or multi_horizon views.

This allows independent tracking of:
- Short-term theses (e.g. near-term earnings beat, catalyst-driven move)
- Medium-term theses (e.g. margin expansion over 1–2 years)
- Long-term theses (e.g. platform transformation over 3–5 years)

Each horizon has its own assumptions, invalidation conditions, and event log. A change to the short thesis (e.g. invalidation) does not automatically affect the long thesis.

---

## 7. Assumptions Design

`ThesisAssumption` records a trackable claim underlying the thesis:
- Scoped to a specific horizon
- Rated by importance (high / medium / low / unknown)
- Linked to source IDs and evidence IDs
- Non-empty assumption_id and description required

Assumptions are not validated by the schema layer for correctness — that is an LLM interpretation task. The schema only requires structural integrity.

---

## 8. Invalidation Conditions Design

`ThesisInvalidationCondition` records a threshold or event that, if triggered, would invalidate or require review of the thesis:

- `invalidation_type`: the domain of the condition (price_level, earnings, macro, etc.)
- `trigger_level`: optional non-negative float (e.g. a price threshold)
- `trigger_date`: optional date string (e.g. "2026-Q4")
- `review_required`: if True, the condition triggers a `needs_review` status signal during `build_horizon_thesis_memory_record`

The schema layer does not evaluate whether a condition has actually been triggered — that is the responsibility of the calling agent or evaluation layer.

---

## 9. Event Log Design

Each `HorizonThesisMemoryRecord` carries an `event_log: list[ThesisMemoryEvent]`. Events are created deterministically by the builder:

- **thesis_created** — always the first event
- **thesis_review_requested** — added when status is blocked or needs_review

Additional event types (thesis_updated, thesis_invalidated, thesis_superseded, thesis_archived, human_feedback_added, outcome_observed) are available for future use by higher-level memory management layers.

Event IDs are derived deterministically from `(thesis_id, event_type, created_at)` using the same SHA-256 hash pattern as the rest of the reliability layer.

---

## 10. Status Logic

### Single-thesis status (build_horizon_thesis_memory_record)

Priority (highest wins):
1. `initial_status` override, if provided by caller
2. `blocked` — human_review_report.status == "blocked" in input_bundle
3. `needs_review` — any invalidation_condition has review_required=True, OR decision_packet.status == "blocked"
4. `active` — default for a clean thesis with no signals

### Report-level status (determine_thesis_memory_status)

Precedence: **blocked > needs_review > invalidated > active > archived > unknown**

| Condition | Report Status |
|-----------|--------------|
| input_bundle.human_review_report.status == "blocked" | blocked |
| Any thesis is blocked | blocked |
| Any thesis is needs_review | needs_review |
| Any thesis is invalidated (no blocked/needs_review) | invalidated |
| All primary theses active | active |
| All theses archived | archived |
| No theses, or only superseded/unknown | unknown |

"Primary theses" excludes archived, unknown, and superseded statuses for the active check.

---

## 11. Helper Functions (12 public)

| Helper | Purpose |
|--------|---------|
| `make_thesis_id(target, horizon, as_of, run_id)` | Deterministic ID for HorizonThesisMemoryRecord |
| `make_thesis_memory_event_id(thesis_id, event_type, created_at)` | Deterministic ID for ThesisMemoryEvent |
| `make_thesis_memory_report_id(target, as_of, run_id)` | Deterministic ID for ThesisMemoryReport |
| `build_thesis_memory_event(...)` | Build a ThesisMemoryEvent with deterministic event_id |
| `determine_thesis_memory_status(theses, input_bundle)` | Derive report-level status and warnings |
| `collect_thesis_memory_source_ids(input_bundle, theses)` | Collect and deduplicate source IDs |
| `collect_thesis_memory_evidence_ids(input_bundle, theses)` | Collect and deduplicate evidence IDs (incl. assumptions + conditions) |
| `collect_thesis_memory_artifact_refs(input_bundle, theses)` | Collect and filter artifact refs |
| `summarize_thesis_memory(target, status, theses, warnings)` | Build ThesisMemorySummary |
| `build_horizon_thesis_memory_record(...)` | Build a single HorizonThesisMemoryRecord |
| `build_thesis_memory_report(input_bundle, theses, ...)` | Build ThesisMemoryReport |
| `thesis_memory_tool_result_from_report(report, run_id)` | ToolResult adapter |

### Timestamp Resolution Priority

For both builders:
1. Explicit `created_at` argument (highest priority)
2. `input_bundle.as_of` if present
3. `_DETERMINISTIC_TIMESTAMP_DEFAULT` = `"1970-01-01T00:00:00Z"` (fallback)

If only `created_at` resolves, `updated_at` defaults to `created_at`.

### Deduplication

Source IDs, evidence IDs, and artifact refs are deduplicated with first-occurrence order preserved. Empty / whitespace-only artifact refs are filtered. Evidence IDs are collected across the input_bundle, thesis-level fields, assumption fields, and invalidation condition fields.

---

## 12. ToolResult Adapter

`thesis_memory_tool_result_from_report(report, run_id=None)` wraps a `ThesisMemoryReport` as a `ToolResult`:

- **tool_name**: `"thesis_memory_report"` (stable)
- **evidence_id**: deterministic, derived from full outputs dict (including `"report": report.model_dump()`)
- **outputs**: includes `report`, `summary`, `calculation_version`, `thesis_count`, `active_count`, `needs_review_count`, `invalidated_count`, `approved_for_execution=False`
- **run_id**: uses `run_id` arg → `report.run_id` → `report.target` as fallback
- No fake evidence, no execution implication, no persistence side effect

The `evidence_id` changes when thesis_text, assumptions, or invalidation conditions change (content-sensitive), because the full report dict is included in the payload.

---

## 13. Offline / Mock-Only Nature

This phase is **strictly offline and mock-only**:

- No live LLM calls
- No live data fetching (no yfinance, no polygon.io)
- No Streamlit dependency
- No database writes
- No file persistence
- No vector store
- No broker / order / execution behavior
- No pathway to set `approved_for_execution = True`
- No import of `app.py`, `pages/*`, `lib/llm_orchestrator.py`, or any live workflow module

All inputs are caller-provided. All outputs are deterministic for identical inputs.

---

## 14. No Execution Authorization

`approved_for_execution` is **permanently False** in all models that carry it:
- `HorizonThesisMemoryRecord`
- `ThesisMemorySummary`
- `ThesisMemoryReport`

Pydantic `model_validator(mode="after")` raises `ValueError` if any caller attempts to set `approved_for_execution=True`. No pathway exists to produce an approved record, summary, or report.

All output from this layer is for research and educational purposes only. It does not constitute investment advice.

---

## 15. Subsequent Phase 4M Subphases (historical roadmap context)

> Status reconciled 2026-05-27: all Phase 4M subphases through 4M-G are now
> accepted. Phase 4M-H Phase 4 Memory Closeout has been implemented and is
> awaiting Codex review. This table is retained as historical roadmap context.

| Subphase | Scope | Status |
|----------|-------|--------|
| Phase 4M-C | Catalyst / News / Earnings Memory — record event intelligence findings across runs | Accepted |
| Phase 4M-D | Allocation Decision Memory — record allocation decisions and constraint history | Accepted |
| Phase 4M-E | Option Trade Plan Memory — record option expression decisions | Accepted |
| Phase 4M-F | Human Feedback Layer — record human corrections and feedback for agent improvement | Accepted |
| Phase 4M-G | Agent Evaluation — offline evaluation of agent output quality over time | Accepted |
| Phase 4M-H | Phase 4 Memory Closeout — Roadmap v4 Phase 4 coverage map, regression sweep, conservative next-phase recommendation | Implemented — awaiting Codex review |

---

## 16. Files

| File | Purpose |
|------|---------|
| `lib/reliability/thesis_memory.py` | Main implementation |
| `scripts/test_reliability_thesis_memory.py` | Test suite (291/291 pass) |
| `docs/reliability_phase_4m_thesis_memory.md` | This document |
| `lib/reliability/__init__.py` | Updated — Phase 4M-B imports and `__all__` entries added |

---

## Disclaimer

All output from this system is for investment research and educational purposes only. It does not constitute investment advice. Markets involve risk; invest with caution.
