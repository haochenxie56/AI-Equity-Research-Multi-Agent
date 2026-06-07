# Reliability Phase 5C — Horizon Decision Cards + ThesisTracker ViewModel Contract

**Date**: 2026-05-27
**Status**: Accepted.
**Type**: Read-only deterministic cockpit-ready view-model contract layer
sitting on top of Phase 4M memory schemas and the Phase 5A fixture-backed
memory query contract.
**Module(s) added**:

- `lib/reliability/phase5_horizon_views.py`

**Test script added**: `scripts/test_reliability_phase_5c_horizon_views.py`
(179/179 passing).

> **Phase 5C makes no live runtime changes.** It does not modify `app.py`,
> `pages/*`, `lib/llm_orchestrator.py`, `lib/workflow_state.py`,
> `lib/valuation.py`, `lib/technical.py`, `lib/rotation.py`,
> `lib/data_fetcher.py`, `lib/cache_manager.py`, `.claude/agents/*`, the
> existing Streamlit UI, the existing news/Finnhub/data-fetch behavior, or
> the live workflow state JSON file. Phase 4A
> (`lib/reliability/integration_boundary.py`) remains frozen and is **not**
> wired in. No database, file store, vector store, embedding pipeline, live
> Anthropic SDK call, HTTP request, or broker/order/execution path is
> introduced. `approved_for_execution` is not exposed by any Phase 5C view
> model.

---

## 1. Purpose

Phase 5C is the **third overlay contract** for Phase 5 and the second
view-model layer (after Phase 5B's Company Research Hub view). It defines
deterministic Pydantic projections of:

1. **Horizon decision cards** — one card per investment horizon
   (`short` / `medium` / `long`). Each card surfaces the underlying
   Phase 4M-B thesis (text, status, direction, confidence), the assumptions
   and invalidation triggers attached to that thesis, plus review-needed
   and missing-evidence badges derived from Phase 4M catalyst / news /
   earnings, human feedback, and agent evaluation memory.
2. **ThesisTracker rows** — flat rows scoped to `(target, horizon)`. Rows
   capture status, last update / review timestamps, invalidation trigger
   counts, review-needed flags, missing-evidence kinds, evidence-id counts,
   and a stable next-action label.

Phase 5C does **not** ship a UI, does **not** read live workflow state,
does **not** call an LLM, does **not** generate new theses, and does
**not** generate trade instructions. It is a *contract layer only* — a
stable Pydantic shape Phase 5D/5E can target without coupling to Streamlit
or live data.

---

## 2. Relationship to Roadmap v4

Roadmap v4 calls out *Horizon Decision Cards* and a *Watchlist + Thesis
Tracker* as cockpit-side deliverables that sit on top of the existing
five-step workflow's memory trail. Phase 5C is the **schema-only contract
layer** for those deliverables. It defines:

- the deterministic, fixture-friendly Pydantic shape future renderers can
  target without coupling to Streamlit or to a live workflow run;
- the set of horizons (`short` / `medium` / `long`) and the canonical
  iteration order (`HORIZON_ORDER`);
- the badges, sub-views, and tracker rows that any cockpit renderer is
  expected to honor;
- the safe-degraded behavior when memory is missing.

No rendering, no live data, no decisions are produced here. Phase 5D
(portfolio / trade plan / option overlay) and Phase 5E (cockpit UI planning
boundary) consume Phase 5C; they remain pending.

---

## 3. Relationship to the Original README App

The README documents the existing Overview / Sector / Scanner / Equity /
Financial / PriceVolume Streamlit pages plus the five-step Overview
synthesis. The original app produces analysis artifacts but does **not** ship a
horizon-decision-cards cockpit panel today. Phase 5C provides the
deterministic Pydantic contract a future cockpit could render *next to*
those pages without touching them.

Concretely, `lib/reliability/phase5_horizon_views.py`:

- does not import `streamlit`,
- does not import any `pages/*` module,
- does not import `app.py`,
- does not import `lib/llm_orchestrator.py`,
- does not import `lib/workflow_state.py`,
- does not read `research/.workflow_state.json`,
- exposes only Pydantic models and deterministic builder functions.

---

## 4. Relationship to Phase 4M Memory

Phase 5C consumes Phase 4M memory records by reference; it does not redefine
or replace any of them:

| Phase 4M record                 | Phase 5C usage                                      |
|---------------------------------|------------------------------------------------------|
| `HorizonThesisMemoryRecord` (Phase 4M-B) | populates the per-horizon card and tracker row     |
| `EventMemoryRecord` (Phase 4M-C)         | drives review-needed signal when affected_horizons matches |
| `HumanFeedbackMemoryRecord` (Phase 4M-F) | drives review-needed signal and surfaces feedback IDs |
| `AgentEvaluationRecord` (Phase 4M-G)     | surfaces calibration / outcome context; review signal when review_required |

Phase 4M-A / 4M-D / 4M-E records are not consumed directly by Phase 5C
(they are consumed by Phase 5B for the Company Research Hub identity /
financial panel and by Phase 5D for portfolio / trade plan view-models).

---

## 5. Relationship to Phase 5A Query Contract

Phase 5C consumes Phase 5A as follows:

| Phase 5A input            | How Phase 5C uses it                                 |
|---------------------------|------------------------------------------------------|
| `MemoryStoreProtocol`     | runs a `MemoryQueryByTicker(target=…)` per target when no explicit query result is supplied |
| `MemoryQueryResult`       | direct input when callers pre-compute results; supersedes the store |
| `MEMORY_RECORD_TYPES`     | type tag references for per-kind evidence counts     |

`build_horizon_decision_cards_view()` accepts:

- `target` (required, non-whitespace)
- `memory_store` (optional)
- `memory_query_result` (optional, takes precedence over store)

`build_thesis_tracker_view()` accepts:

- `targets` (required list of non-empty strings, deduplicated by
  first-occurrence order)
- `memory_store` (optional)
- `memory_query_result` (optional)

When both `memory_store` and `memory_query_result` are absent, builders
still complete — every horizon yields a safe ``"missing"`` card / row and
the top-level `warnings` list explains that no memory was supplied.

---

## 6. Optional Relationship to Phase 5B Company Research Hub

Phase 5C does **not** import Phase 5B's `company_research_hub` module. A
cockpit composing both views can call them side-by-side using the same
`target` and the same `MemoryStoreProtocol`. The Phase 5B identity /
source-workflow panel and the Phase 5C horizon decision cards both honor
the same Phase 5A invariants (`approved_for_execution` rejected at the
Phase 5A model layer; deterministic IDs; no live wiring), so they are safe
to render together without cross-coupling.

---

## 7. View Model Contracts

All view models live in `lib/reliability/phase5_horizon_views.py` and use
`pydantic.BaseModel` with `model_config = ConfigDict(extra="forbid")`.
None of them declares `approved_for_execution`.

### 7.1 Primitive sub-views

| View                          | Purpose                                                |
|-------------------------------|--------------------------------------------------------|
| `HorizonAssumptionView`       | one Phase 4M-B `ThesisAssumption` projection           |
| `InvalidationTriggerView`     | one Phase 4M-B `ThesisInvalidationCondition` projection |
| `ThesisStatusView`            | one Phase 4M-B thesis record's status surface          |
| `ReviewNeededBadgeView`       | review_needed flag + reasons list                      |
| `MissingEvidenceBadgeView`    | missing_kinds + present_kinds + warnings               |
| `HorizonEvidenceSummaryView`  | per-horizon evidence aggregate (counts + IDs)          |
| `HorizonRiskSummaryView`      | invalidation trigger aggregate (count + triggers)      |
| `HorizonNextActionView`       | descriptive next-action label (never executive)        |

### 7.2 Aggregate views

| View                          | Purpose                                                |
|-------------------------------|--------------------------------------------------------|
| `HorizonDecisionCardView`     | one horizon's complete decision card                   |
| `HorizonDecisionCardsView`    | always exactly three cards in `short→medium→long` order |
| `ThesisTrackerRowView`        | one `(target, horizon)` row                            |
| `ThesisTrackerView`           | aggregate tracker (deterministic row ordering)         |

### 7.3 Card status semantics (`CardStatus`)

`CardStatus` is one of:

- `active` — thesis is active and no downstream review signal
- `needs_review` — thesis is needs_review, OR an event / human feedback /
  agent evaluation forces review while the thesis itself is active
- `invalidated` — thesis status invalidated
- `blocked` — thesis status blocked
- `archived` — thesis status archived
- `superseded` — thesis status superseded
- `missing` — no thesis record found for the horizon
- `unknown` — thesis exists but its status is `unknown`

Phase 5C does not declare its own status precedence beyond:

```
blocked > needs_review (incl. downstream-flipped) > invalidated >
archived > superseded > active > unknown > missing
```

`HorizonDecisionCardsView` validates the three-card invariant at the
Pydantic-model layer: exactly three cards must be present, in the canonical
horizon order.

---

## 8. Horizon Ordering

The canonical horizon iteration / sort order is:

```
HORIZON_ORDER = ("short", "medium", "long")
```

- `HorizonDecisionCardsView.cards` is always length-3 in this exact order.
- `ThesisTrackerView.rows` are sorted by `(target_index, horizon_index)`,
  with `target_index` reflecting the deduplicated `targets` argument's
  first-occurrence order and `horizon_index` reflecting `HORIZON_ORDER`.
- `HorizonEvidenceSummaryView.horizon` is one of the three canonical keys.

Phase 4M-B's `ThesisHorizon` literal includes `multi_horizon` and `unknown`
in addition to `short / medium / long`; Phase 5C surfaces only the three
canonical horizons. Records with `horizon="multi_horizon"` or
`horizon="unknown"` are not matched into any Phase 5C card.

---

## 9. ThesisTracker Row Semantics

A `ThesisTrackerRowView` is identified by `(target, horizon)` and carries
the following surface:

| Field                          | Source                                                |
|--------------------------------|--------------------------------------------------------|
| `target`                       | caller-supplied                                       |
| `horizon`                      | one of `short` / `medium` / `long`                    |
| `is_populated`                 | True iff a matching Phase 4M-B thesis exists          |
| `status`                       | derived `CardStatus` (see §7.3)                       |
| `direction` / `confidence`     | from thesis record, else `"unknown"`                  |
| `thesis_id`                    | from thesis record, else `None`                       |
| `last_updated_at`              | thesis.`updated_at`, else `None`                      |
| `last_reviewed_at`             | most recent matching `event_log` entry's `created_at`, else `None` |
| `invalidation_trigger_count`   | `len(thesis.invalidation_conditions)`                 |
| `review_needed`                | derived `ReviewNeededBadgeView.review_needed`         |
| `review_reasons`               | derived `ReviewNeededBadgeView.reasons`               |
| `missing_evidence_kinds`       | derived `MissingEvidenceBadgeView.missing_kinds`      |
| `evidence_id_count`            | `len(evidence_summary.evidence_ids)`                  |
| `next_action_label`            | derived `HorizonNextActionView.label`                 |
| `warnings`                     | non-empty when thesis is missing                      |

Missing thesis → row is created in safe degraded state (`is_populated=False`,
`status="missing"`, `next_action_label="none_supported"`, `warnings`
non-empty). The row is **always** emitted so the cockpit can render the
slot consistently.

---

## 10. Review-Needed Semantics

`ReviewNeededBadgeView.review_needed` is True when ANY of:

- thesis `status` is `blocked` / `needs_review` / `invalidated`;
- a horizon-matched `EventMemoryRecord` signals review, defined as any of:
  - `review_status` is `pending` or `escalated`,
  - `status` is `blocked` or `needs_review`,
  - `thesis_changing` is True,
  - `impact_magnitude` is `high`;
- a target-scoped `HumanFeedbackMemoryRecord` has `review_required=True`
  or has `status` `blocked` / `needs_review`;
- a horizon-matched `AgentEvaluationRecord` has `review_required=True`
  or has `status` `blocked` / `needs_review`.

Phase 4M-F human feedback records are **not** horizon-scoped, so they are
surfaced on every horizon's card for the same target (the cockpit can
render the same feedback alongside each horizon without double-counting).
Events and agent evaluations are horizon-scoped via
`affected_horizons` / `target_ref.horizon` / `signal.horizon`.

When `review_needed=True` while the thesis itself is `active`, the card's
`status` flips to `needs_review`. This is the intended way to surface
downstream signals without rewriting the underlying Phase 4M thesis
status.

---

## 11. Missing-Evidence / Degraded States

Phase 5C never raises when a horizon is uncovered. It returns safe
degraded views instead:

| Missing input                                  | Behavior                                                              |
|-----------------------------------------------|-----------------------------------------------------------------------|
| no matching thesis for horizon                | card `is_populated=False`, `status="missing"`, `warnings` non-empty   |
| no events for horizon                         | `MissingEvidenceBadgeView.missing_kinds` includes `"event"`           |
| no human feedback for target                  | `missing_kinds` includes `"human_feedback"`                           |
| no agent evaluation for horizon               | `missing_kinds` includes `"agent_evaluation"`                         |
| no `memory_store` and no `memory_query_result`| every card returned as missing; top-level `warnings` flag missing memory |
| missing target / unknown ticker               | three safe `"missing"` cards / rows; no hallucinated content          |

The aggregate `HorizonDecisionCardsView` always carries exactly three
cards. The aggregate `ThesisTrackerView` always carries `3 * len(deduped_targets)`
rows. Missing data is **always** surfaced as warnings, never silently
fabricated.

---

## 12. Evidence / Validation Handling

- `HorizonEvidenceSummaryView.evidence_ids` is sourced **only** from the
  thesis record (`thesis.evidence_ids`). Phase 5C never invents new
  evidence IDs.
- `HorizonEvidenceSummaryView.has_any_evidence` is True only when at least
  one Phase 4M record contributed (thesis, event, human feedback, or
  agent evaluation).
- `MissingEvidenceBadgeView.has_missing_evidence` is True if **any** of
  the four canonical kinds has zero contributing records.
- `HorizonRiskSummaryView.invalidation_trigger_count` reflects the
  thesis record's `invalidation_conditions` length; the view does not
  fabricate triggers.
- `HorizonNextActionView.label` is descriptive only:
  - `"review_thesis"` for `blocked` / `needs_review`,
  - `"refresh_invalidation"` for `invalidated`,
  - `"watch"` for `active`,
  - `"none_supported"` for `missing` / `unknown` / `archived` / `superseded`.

No view declares decision readiness. No view fabricates clean / success
state.

---

## 13. Non-Goals

Phase 5C does **not**:

- Ship any new UI page.
- Modify any existing page or workflow.
- Add SQL, NoSQL, file, or vector store persistence.
- Embed records or build a similarity index.
- Call the Claude API, Anthropic SDK, or any HTTP service.
- Mutate `workflow_state`, agent definitions, or prompts.
- Route orders, place trades, or set `approved_for_execution = True`.
- Wire Phase 4A `integration_boundary.py` into the live app.
- Read the live workflow state JSON file.
- Generate portfolio / trade plan / option overlay cockpits (deferred to
  Phase 5D).
- Render anything (deferred to Phase 5E planning + future cockpit work).
- Implement shadow-mode integration (deferred to Phase 5F planning).

---

## 14. Guardrails

### 14.1 Forbidden files (unchanged across Phase 5)

- `app.py`
- `pages/*`
- `lib/llm_orchestrator.py`
- `lib/valuation.py`
- `lib/technical.py`
- `lib/rotation.py`
- `lib/data_fetcher.py`
- `lib/workflow_state.py`
- `lib/cache_manager.py` *(read-only conceptually; not modified)*
- `lib/reliability/integration_boundary.py` *(frozen Phase 4A)*
- `.claude/agents/*`
- existing live prompt files
- existing Streamlit UI
- existing news / Finnhub / data-fetch behavior
- existing live workflow behavior
- the live workflow state JSON file

### 14.2 `approved_for_execution` invariant

- No Phase 5C view model declares `approved_for_execution`.
- The underlying Phase 4M memory records reject
  `approved_for_execution=True` at their respective model layers.
- The Phase 5A `MemoryQueryResult` already enforces
  `approved_for_execution=False` on every returned result.
- The Phase 5C test suite asserts the JSON dump of every fixture-built
  view contains no `approved_for_execution=true` literal and that every
  Phase 5C class does not declare an `approved_for_execution` field.

### 14.3 No live integration

- No import of `lib.workflow_state`, `lib.llm_orchestrator`,
  `lib.data_fetcher`, `lib.valuation`, `lib.technical`, `lib.rotation`,
  `lib.cache_manager`, Streamlit, or the Anthropic SDK in any Phase 5C
  module.
- No import of `lib.reliability.integration_boundary` (frozen Phase 4A).
- The Phase 5C test suite checks both `sys.modules` and the module source
  text for forbidden import substrings.
- The test suite also checks for the absence of the live workflow state
  JSON path substring in the source.

### 14.4 Deterministic offline behavior

- All view IDs derive from existing stable Phase 4M-B/4M-C/4M-F/4M-G IDs.
- Phase 5C does not introduce a new content-hash factory; it surfaces
  thesis_id / event_memory_id / feedback_memory_id / evaluation_id as
  produced upstream.
- Snapshot / view serialization round-trips by value.
- The same fixture pipeline produces byte-identical card and tracker JSON
  across rebuilds (asserted in the test suite).

---

## 15. Acceptance Criteria

Phase 5C is accepted when:

1. `lib/reliability/phase5_horizon_views.py` exists and passes the
   dedicated test suite
   (`scripts/test_reliability_phase_5c_horizon_views.py`).
2. The Phase 5A complete fixture pack builds a fully populated
   `HorizonDecisionCardsView` with three cards in `short→medium→long`
   order, each populated with the matching Phase 4M-B thesis.
3. Missing short / medium / long thesis records each produce a safe
   `"missing"` card and a corresponding card-level warning, while the
   remaining horizons remain populated.
4. Missing ticker / no records returns a safe empty
   `HorizonDecisionCardsView` (three `"missing"` cards) and a safe empty
   `ThesisTrackerView` row set without hallucinated content.
5. `ThesisTrackerView.rows` are created by `(target, horizon)` and ordered
   deterministically.
6. Catalyst / news / earnings memory with `review_status` `pending` /
   `escalated`, `thesis_changing=True`, `impact_magnitude=high`, or
   `status` `blocked` / `needs_review` correctly flips the card to
   `needs_review` and surfaces a review reason.
7. Human feedback memory with `review_required=True` or status
   `blocked` / `needs_review` surfaces on the review-needed badge.
8. Agent evaluation memory with `review_required=True` or status
   `blocked` / `needs_review` surfaces on the review-needed badge, and
   matching evaluations surface on `related_agent_evaluation_ids`.
9. Missing-evidence badge correctly identifies absent kinds for a
   thesis-only horizon and for an empty horizon.
10. Validation does not fabricate clean / success state: missing thesis
    → `status="missing"`, `next_action_label="none_supported"`, no
    `approved_for_execution`.
11. No `approved_for_execution=True` appears in any view JSON.
12. `lib/reliability/__init__.py` re-exports the stable Phase 5C
    symbols.
13. No live runtime files are modified.
14. No DB, file persistence, vector store, external API, broker, or order
    path is introduced.
15. Phase 5A regression test
    (`scripts/test_reliability_phase_5a_memory_query.py`) continues to
    pass at 175/175.
16. Phase 5B regression test
    (`scripts/test_reliability_phase_5b_company_hub.py`) continues to
    pass at 163/163.
17. State files (`PROJECT_STATE.md`, `CURRENT_TASK.md`) record Phase 5C
    as "Implemented — Awaiting Codex Review" without claiming Phase 5D
    has started.

---

## 16. Future Phase 5D Dependency

Phase 5D (Portfolio / TradePlan / Option Overlay ViewModel Contract) will
consume Phase 5C as follows:

- A future `PortfolioCockpitViewModel` will compose horizon decision card
  status across targets to inform portfolio-level summaries (without
  recomputing thesis content).
- A future `TradePlanCockpitViewModel` will reference the Phase 5C card's
  `status`, `review_needed_badge`, and `next_action_label` when shaping
  trade-plan eligibility (without authorizing execution;
  `approved_for_execution` remains `False`).
- A future `OptionOverlayCockpitViewModel` will reference Phase 5C cards
  alongside Phase 4M-E option trade memory to assess overlay candidates.
- View-model construction must remain offline. Phase 5D introduces no UI
  page, no Streamlit integration, no live wiring.
- Phase 5D must not bypass Phase 5C's safe-degradation invariants, must
  not introduce an `approved_for_execution` field, and must not invent
  thesis or risk content.

Phase 5E/5F/5G/5H build on Phase 5B/5C/5D view-model contracts; none of
them adds live wiring.

---

## 17. Test Matrix

`scripts/test_reliability_phase_5c_horizon_views.py` covers 179 assertions
across 27 sections:

| Section | Topic                                                           |
|---------|-----------------------------------------------------------------|
| 1       | Module imports + forbidden-module non-load (sys.modules)         |
| 2       | Source-level forbidden import / live-state-path substring check |
| 3       | Public symbol imports + canonical horizon ordering              |
| 4       | Full `HorizonDecisionCardsView` build from Phase 5A fixture pack |
| 5       | Short / medium / long cards preserve thesis content              |
| 6       | Evidence / risk / next-action sub-views                          |
| 7       | Missing short thesis → safe degraded card + warning              |
| 8       | Missing medium thesis → safe degraded card + warning             |
| 9       | Missing long thesis → safe degraded card + warning               |
| 10      | Missing ticker / no records → safe empty view                    |
| 11      | ThesisTracker rows created by `(target, horizon)`                |
| 12      | Multi-target tracker ordering + dedupe                           |
| 13      | Catalyst/news/earnings review-needed signal surfaces              |
| 14      | Human feedback status surfaces (incl. `review_required=True`)    |
| 15      | Agent evaluation summary surfaces (fixture record reaches card)  |
| 16      | Missing-evidence badge appears for incomplete horizons           |
| 17      | Validation does not fabricate clean / success state              |
| 18      | No `approved_for_execution=True` anywhere                        |
| 19      | Deterministic serialization across rebuilds                      |
| 20      | Build with explicit `MemoryQueryResult`                          |
| 21      | Builder rejects empty / whitespace target + bad horizon          |
| 22      | Build without any memory store                                   |
| 23      | Aggregate view validators reject malformed inputs                |
| 24      | Package-level re-exports through `lib/reliability/__init__.py`   |
| 25      | Module `__all__` symmetry                                        |
| 26      | No filesystem writes anywhere in pipeline                        |
| 27      | Phase 5B regression — `CompanyResearchHubView` still builds      |

All 179 assertions pass. Phase 5A regression passes 175/175. Phase 5B
regression passes 163/163.
