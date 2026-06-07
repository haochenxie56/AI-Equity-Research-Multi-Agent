# Reliability Phase 5B — Company Research Hub ViewModel Contract

**Date**: 2026-05-27
**Status**: Accepted.
**Type**: Read-only deterministic cockpit-ready view-model contract layer
sitting on top of Phase 5A (Existing Workflow Memory Adapter +
Fixture-backed Memory Query Contract).
**Module(s) added**:

- `lib/reliability/company_research_hub.py`

**Test script added**: `scripts/test_reliability_phase_5b_company_hub.py`
(163/163 passing).

> **Phase 5B makes no live runtime changes.** It does not modify `app.py`,
> `pages/*`, `lib/llm_orchestrator.py`, `lib/workflow_state.py`,
> `lib/valuation.py`, `lib/technical.py`, `lib/rotation.py`,
> `lib/data_fetcher.py`, `lib/cache_manager.py`, `.claude/agents/*`, the
> existing Streamlit UI, the existing news/Finnhub/data-fetch behavior, or
> the live workflow state JSON file. Phase 4A
> (`lib/reliability/integration_boundary.py`) remains frozen and is **not**
> wired in. No database, file store, vector store, embedding pipeline, live
> Anthropic SDK call, HTTP request, or broker/order/execution path is
> introduced. `approved_for_execution` is not exposed by any Phase 5B view
> model.

---

## 1. Purpose

Phase 5B is the **second overlay contract** for Phase 5 and the first view-
model layer. It defines a deterministic Pydantic projection of one
original-app-style research run into a future cockpit-ready *Company
Research Hub* representation.

A Company Research Hub is a single cockpit view of one ticker's full
research record: who the company is, what equity research said, what
financial valuation said, what price/volume timing said, where the source
workflow stands, what evidence and memory coverage looks like, and what
validation signals are outstanding.

Phase 5B does **not** ship a UI, does **not** read live workflow state, and
does **not** generate recommendations or trade instructions. It is a
*contract layer only* — a stable Pydantic shape Phase 5C/5D/5E can target
without coupling to Streamlit or live data.

---

## 2. Relationship to the Original README App

The README documents a working Streamlit application whose six pages cover:

| Original README page | Covered concerns |
|----------------------|------------------|
| Equity | business model, moat, management, competitive landscape, peer comparison |
| Financial | financial statements, DCF / relative valuation, profitability / cash-flow quality, valuation reasonableness |
| PriceVolume | K-line / price-volume context, RSI / MACD / ADX / Bollinger / SMA-style indicators, support / resistance / timing interpretation |
| Sector | macro / policy / supply-chain / sector-cycle context |
| Scanner | full-market screen → candidate ticker list |
| Overview | five-step orchestration + synthesis |

The Company Research Hub projects these existing concerns into deterministic
view-models, **by reference**. Phase 5B never re-runs or re-derives the
underlying analyses. It surfaces:

- `ExistingPageOutputRef` objects (page name, step name, artifact ID, report
  path) sourced from a Phase 5A `ExistingWorkflowSnapshot`.
- `evidence_ids` and `artifact_refs` already attached to each step.
- Memory record IDs (research_run / thesis / event / allocation /
  option_trade / human_feedback / agent_evaluation) supplied by the Phase 5A
  `MemoryStoreProtocol`.

---

## 3. How Equity / Financial / PriceVolume Map into the Company Research Hub

```
   Equity page  (business model / moat / management / competitive
                landscape / peer comparison)
       │
       └──► EquityResearchPanelView
              ├─ step_status, summary  (from snapshot.steps["equity"])
              ├─ page_outputs          (by reference)
              ├─ evidence_ids          (from snapshot)
              ├─ artifact_refs         (from snapshot)
              └─ research_run_memory_ids
                                       (from Phase 4M-A records via Phase 5A
                                        memory store)

   Financial page (statements / DCF / relative valuation / profitability /
                  cash-flow quality / valuation reasonableness)
       │
       └──► FinancialValuationPanelView
              ├─ step_status, summary  (from snapshot.steps["financial"])
              ├─ page_outputs
              ├─ evidence_ids / artifact_refs
              ├─ allocation_memory_ids  (Phase 4M-D context for valuation
              │                          reasonableness)
              └─ valuation_context_notes (allocation rationales surfaced
                                          read-only)

   PriceVolume page (K-line / RSI / MACD / ADX / Bollinger / SMA /
                    support-resistance / timing interpretation)
       │
       └──► PriceVolumeTimingPanelView
              ├─ step_status, summary  (from snapshot.steps["price_volume"])
              ├─ page_outputs
              └─ evidence_ids / artifact_refs

   Overview synthesis
       │
       └──► SourceWorkflowPanelView
              ├─ workflow_name, present_step_keys, missing_step_keys
              ├─ step_statuses
              ├─ synthesis_present, synthesis_status, synthesis_summary
              └─ consolidated_report_ref
```

Aggregate panels:

```
   CompanyResearchHubView
      ├─ identity                  (CompanyIdentityView)
      ├─ equity_panel              (EquityResearchPanelView)
      ├─ financial_panel           (FinancialValuationPanelView)
      ├─ price_volume_panel        (PriceVolumeTimingPanelView)
      ├─ source_workflow_panel     (SourceWorkflowPanelView)
      ├─ evidence_coverage_panel   (EvidenceCoveragePanelView)
      ├─ validation_status_panel   (ValidationStatusPanelView)
      ├─ missing_data              (MissingDataWarningView)
      ├─ warnings
      └─ calculation_version
```

---

## 4. Relationship to Phase 5A Memory / Query Contract

Phase 5B consumes Phase 5A without modifying it:

| Phase 5A input | How Phase 5B uses it |
|----------------|----------------------|
| `ExistingWorkflowSnapshot` | populates equity / financial / price_volume / source_workflow panels |
| `MemoryStoreProtocol` | supplies memory record IDs for equity (research_run) and financial (allocation) panels |
| `MemoryQueryResult` | feeds evidence coverage counts and validation status |
| `MemoryQueryByTicker` | target-scoped query when only `memory_store` is supplied |

`build_company_research_hub_view()` accepts:

- `target` (required)
- `snapshot` (optional)
- `memory_store` (optional)
- `memory_query_result` (optional, takes precedence over store)
- `run_id` / `as_of` (optional identity overrides)

When both `memory_store` and `memory_query_result` are absent, the view
still builds — every panel that would have been populated from memory
returns empty lists; aggregate panels still return safe values; the
top-level `warnings` list explains that no memory was supplied.

### 4.1 Behavior when `memory_query_result` is supplied without `memory_store`

`memory_query_result` is consulted by the panels that need *aggregate*
memory state — specifically `EvidenceCoveragePanelView` and
`ValidationStatusPanelView`. Their counts and per-type breakdowns come
from `memory_query_result.count_by_type()` and from iterating the
records inside the supplied `MemoryQueryResult`, so passing a
`memory_query_result` alone is sufficient to drive those aggregates.

In contrast, the panel-level memory ID lists
(`EquityResearchPanelView.research_run_memory_ids` and
`FinancialValuationPanelView.allocation_memory_ids` /
`valuation_context_notes`) are populated by re-querying the `memory_store`
with a `MemoryQueryByTicker`. When `memory_store` is `None` and only
`memory_query_result` is supplied, those panel-level ID lists remain
empty by design — Phase 5B does not infer per-panel memory IDs from
the aggregate query result. Aggregate evidence and validation panels
will still reflect the supplied `memory_query_result`. If a future
caller needs per-panel memory IDs, supply both `memory_store` (for
panel scoping) and, optionally, `memory_query_result` (for aggregate
counts).

---

## 5. Why This Is Not Streamlit UI

Phase 5B introduces no Streamlit component, no page, no layout, no
session-state read, no widget. It defines a **stable Pydantic shape** that
a future Phase 5E cockpit UI planning document could describe rendering
next to (not inside) the existing six Streamlit pages. The Streamlit UI
contract belongs to Phase 5E and beyond; Phase 5B keeps the view-model
layer independent of any rendering technology.

Concretely, `lib/reliability/company_research_hub.py`:

- Does not import `streamlit`.
- Does not import any `pages/*` module.
- Does not import `app.py`.
- Exposes only Pydantic models and deterministic builder functions.

---

## 6. Why This Does Not Read Live `workflow_state`

The module does not import `lib.workflow_state`, does not import
`lib.llm_orchestrator`, does not import `lib.data_fetcher`, does not
import any Streamlit module, and does not import any Anthropic SDK module.
The test suite enforces this both at the loaded-module level (`sys.modules`
check) and at the source-substring level (forbidden `import` substrings
plus a forbidden "live workflow state JSON" path substring).

`ExistingWorkflowSnapshot` is populated only by fixtures supplied through
Phase 5A, or, in production use, by future explicit import paths approved
in a controlled integration phase outside Phase 5.

---

## 7. View Model Contracts

All view models live in `lib/reliability/company_research_hub.py` and use
`pydantic.BaseModel` with `model_config = ConfigDict(extra="forbid")`. None
of them declares an `approved_for_execution` field.

### 7.1 `CompanyIdentityView`

Identity-level coordinates for one research run.

| Field | Type | Notes |
|-------|------|-------|
| `target` | `str` | required, non-whitespace |
| `run_id` | `Optional[str]` | snapshot → override → None |
| `as_of` | `Optional[str]` | snapshot → override → None |
| `workflow_name` | `Optional[str]` | from snapshot |
| `snapshot_id` | `Optional[str]` | deterministic via `make_workflow_snapshot_id()` |
| `notes` | `str` | from snapshot.notes |
| `data_source` | `DataSourceTag` | `"existing_workflow_snapshot"` when snapshot supplied, else `"absent"` |

### 7.2 `EquityResearchPanelView`

| Field | Type | Notes |
|-------|------|-------|
| `is_populated` | `bool` | False when snapshot or "equity" step missing |
| `target` | `str` | required |
| `step_status` | `str` | from snapshot.steps["equity"].status |
| `summary` | `str` | from snapshot |
| `page_outputs` | `list[ExistingPageOutputRef]` | by reference |
| `research_run_memory_ids` | `list[str]` | Phase 4M-A IDs |
| `evidence_ids` / `artifact_refs` | `list[str]` | from snapshot |
| `warnings` | `list[str]` | non-empty when missing |
| `data_source` | `DataSourceTag` |

### 7.3 `FinancialValuationPanelView`

| Field | Type | Notes |
|-------|------|-------|
| `is_populated` | `bool` | False when missing |
| `target` | `str` | required |
| `step_status` | `str` | from snapshot.steps["financial"].status |
| `summary` | `str` | from snapshot |
| `page_outputs` | `list[ExistingPageOutputRef]` | by reference |
| `allocation_memory_ids` | `list[str]` | Phase 4M-D IDs |
| `valuation_context_notes` | `list[str]` | allocation rationales (read-only context) |
| `evidence_ids` / `artifact_refs` | `list[str]` | from snapshot |
| `warnings` | `list[str]` |
| `data_source` | `DataSourceTag` |

### 7.4 `PriceVolumeTimingPanelView`

| Field | Type | Notes |
|-------|------|-------|
| `is_populated` | `bool` | False when missing |
| `target` | `str` | required |
| `step_status` / `summary` | `str` |
| `page_outputs` | `list[ExistingPageOutputRef]` |
| `evidence_ids` / `artifact_refs` | `list[str]` |
| `warnings` | `list[str]` |
| `data_source` | `DataSourceTag` |

### 7.5 `SourceWorkflowPanelView`

| Field | Type | Notes |
|-------|------|-------|
| `workflow_name` | `Optional[str]` |
| `present_step_keys` / `missing_step_keys` | `list[str]` | deterministic order |
| `step_statuses` | `dict[str, str]` |
| `synthesis_present` | `bool` |
| `synthesis_status` / `synthesis_summary` | `str` |
| `consolidated_report_ref` | `Optional[ExistingPageOutputRef]` |
| `warnings` | `list[str]` |
| `data_source` | `DataSourceTag` |

### 7.6 `EvidenceCoveragePanelView`

| Field | Type | Notes |
|-------|------|-------|
| `available_source_steps` / `missing_source_steps` | `list[str]` |
| `available_memory_record_types` | `list[str]` | only types with count > 0 |
| `memory_record_counts_by_type` | `dict[str, int]` | all 7 keys present, zero if absent |
| `evidence_id_count_by_step` | `dict[str, int]` |
| `total_evidence_id_count` / `total_memory_record_count` | `int` |
| `has_complete_step_coverage` | `bool` | True only when all 6 workflow steps present |
| `has_any_memory_records` | `bool` |
| `warnings` | `list[str]` |

### 7.7 `ValidationStatusPanelView`

| Field | Type | Notes |
|-------|------|-------|
| `blocked_count` / `needs_review_count` / `review_required_count` | `int` |
| `inspected_record_count` | `int` |
| `record_status_counts` | `dict[str, int]` |
| `has_any_validation_signal` | `bool` | True only when at least one record inspected |
| `is_clean` | `bool` | True only when records inspected AND no blocked/needs_review/review_required |
| `warnings` | `list[str]` |

### 7.8 `MissingDataWarningView`

| Field | Type | Notes |
|-------|------|-------|
| `missing_panels` | `list[MissingDataPanel]` | subset of `{"equity","financial","price_volume","synthesis","identity","memory"}` |
| `warnings` | `list[str]` |

### 7.9 `CompanyResearchHubView`

Aggregates all panels plus a top-level `warnings` list and a stable
`calculation_version` string (`"company_research_hub_v1"`).

---

## 8. Safe Degraded States

Phase 5B never raises when a panel is missing. It returns safe degraded
panel views instead:

| Missing input | Behavior |
|---------------|----------|
| No `snapshot` | identity `data_source="absent"`; all panels report `is_populated=False`; `missing_data.missing_panels` includes `"identity"` and every missing concrete panel |
| `snapshot` present but no `"equity"` step | `EquityResearchPanelView.is_populated=False`; warnings note the absence; `missing_data` includes `"equity"` |
| `snapshot` present but no `"financial"` step | analogous to equity |
| `snapshot` present but no `"price_volume"` step | analogous to equity |
| `snapshot` present but no synthesis | `SourceWorkflowPanelView.synthesis_present=False`; `missing_data` includes `"synthesis"` |
| No `memory_store` and no `memory_query_result` | evidence coverage counts are zero; validation panel reports no signal; top-level `warnings` flag the missing memory layer |
| Missing ticker (no matching records and no snapshot) | empty safe view, no hallucinated content |

The builder rejects only one input: empty / whitespace-only `target`
(`ValueError`). Every other safe degradation is surfaced as warnings rather
than exceptions.

---

## 9. Evidence / Validation Handling

- View models tag every panel with a `data_source` so downstream code knows
  whether the data came from the snapshot, a memory query result, or was
  absent.
- `EvidenceCoveragePanelView.has_complete_step_coverage` is True only when
  the snapshot supplies every step in `WORKFLOW_STEP_ORDER`. There is no
  way to claim "complete coverage" from inferred state.
- `ValidationStatusPanelView.has_any_validation_signal` is True only when
  at least one record was inspected. `is_clean` is True only when records
  were inspected AND none was blocked / needs_review / review_required.
- The validation panel reads `record.review_required` first, then
  `record.summary.review_required` if the record has a summary, so it works
  uniformly across the seven Phase 4M record types without coupling to any
  specific status enum.
- The validation panel never raises and never fabricates: a record with no
  status / no review_required signal simply contributes nothing.

---

## 10. Non-Goals

Phase 5B does **not**:

- Ship any new UI page.
- Modify any existing page or workflow.
- Add SQL, NoSQL, file, or vector store persistence.
- Embed records or build a similarity index.
- Call the Claude API, Anthropic SDK, or any HTTP service.
- Mutate `workflow_state`, agent definitions, or prompts.
- Route orders, place trades, or set `approved_for_execution = True`.
- Wire Phase 4A `integration_boundary.py` into the live app.
- Read the live workflow state JSON file.
- Generate horizon decision cards (deferred to Phase 5C).
- Generate portfolio / trade plan / option overlay cockpits (deferred to
  Phase 5D).

---

## 11. Guardrails

### 11.1 Forbidden files (unchanged across Phase 5)

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

### 11.2 `approved_for_execution` invariant

- No Phase 5B view model declares `approved_for_execution`.
- The underlying `ExistingWorkflowSnapshot` (Phase 5A) rejects
  `approved_for_execution=True` at its model layer; the builder inherits
  that invariant by construction.
- `MemoryQueryResult` (Phase 5A) already enforces
  `approved_for_execution=False` on every returned result.
- The Phase 5B test suite asserts the JSON dump of every fixture-built
  view contains no `approved_for_execution=true` literal.

### 11.3 No live integration

- No import of `lib.workflow_state`, `lib.llm_orchestrator`,
  `lib.data_fetcher`, `lib.valuation`, `lib.technical`, `lib.rotation`,
  `lib.cache_manager`, Streamlit, or the Anthropic SDK in any Phase 5B
  module.
- The Phase 5B test suite checks both `sys.modules` and the module source
  text for forbidden import substrings.
- The test suite also checks for the absence of a live workflow state JSON
  path substring in the source.

### 11.4 Deterministic offline behavior

- All IDs derive from existing stable hash payloads.
- Snapshot serialization round-trips by value.
- The same fixture pipeline produces byte-identical view JSON across
  rebuilds.

---

## 12. Acceptance Criteria

Phase 5B is accepted when:

1. `lib/reliability/company_research_hub.py` exists and passes the
   dedicated test suite
   (`scripts/test_reliability_phase_5b_company_hub.py`).
2. The Phase 5A complete fixture pack builds a fully populated
   `CompanyResearchHubView` (equity / financial / price_volume / synthesis
   all populated; missing_panels empty).
3. Missing equity / financial / price_volume / synthesis snapshots each
   produce a safe degraded panel and a `MissingDataWarningView` entry.
4. Missing ticker / no-records returns a safe empty view (no hallucinated
   content).
5. `EvidenceCoveragePanelView` reports available / missing source steps
   deterministically and never claims complete coverage when steps are
   missing.
6. `ValidationStatusPanelView` does not claim validation success unless
   records were inspected AND none flagged a blocked / needs_review /
   review_required signal.
7. No `approved_for_execution=True` appears in any view JSON.
8. `lib/reliability/__init__.py` re-exports the stable Phase 5B
   symbols.
9. No live runtime files are modified.
10. No DB, file persistence, vector store, external API, broker, or order
    path is introduced.
11. Phase 5A regression test
    (`scripts/test_reliability_phase_5a_memory_query.py`) continues to
    pass at 175/175.
12. State files (`PROJECT_STATE.md`, `CURRENT_TASK.md`) record Phase 5B
    as "Implemented — Awaiting Codex Review" without claiming Phase 5C
    has started.

---

## 13. Future Phase 5C Dependency

Phase 5C (Horizon Decision Cards + ThesisTracker ViewModel Contract)
consumes Phase 5B as follows:

- A future `HorizonDecisionCardViewModel` will reference the same
  `CompanyResearchHubView.identity` coordinates and the same Phase 5A
  `MemoryStoreProtocol`.
- A future `ThesisTrackerViewModel` will reuse the Phase 5B identity /
  source workflow projection and add per-horizon thesis projections
  sourced via `MemoryQueryByHorizon` from Phase 5A.
- View-model construction must remain offline. Phase 5C introduces no UI
  page, no Streamlit integration, no live wiring.
- Phase 5C must not bypass Phase 5B's safe-degradation invariants or
  introduce an `approved_for_execution` field.

Phase 5D/5E/5F/5G/5H build on Phase 5B/5C view-model contracts; none of
them adds live wiring.

---

## 14. Test Matrix

`scripts/test_reliability_phase_5b_company_hub.py` covers 163 assertions
across 25 sections:

| Section | Topic |
|---------|-------|
| 1 | Module imports + forbidden-module non-load (sys.modules) |
| 2 | Source-level forbidden import / live-state-path substring check |
| 3 | Public symbol imports |
| 4 | Full `CompanyResearchHubView` build from Phase 5A complete fixture |
| 5 | Equity panel populated from fixture |
| 6 | Financial panel populated from fixture + allocation memory |
| 7 | PriceVolume panel populated from fixture |
| 8 | Source workflow panel + synthesis surfaced |
| 9 | Missing equity step → safe degraded panel + warning |
| 10 | Missing financial step → safe degraded panel + warning |
| 11 | Missing price_volume step → safe degraded panel + warning |
| 12 | Missing synthesis → safe degraded source workflow + warning |
| 13 | Missing ticker / empty store → safe empty view |
| 14 | Evidence coverage deterministic, no false complete coverage |
| 15 | Validation status panel never fabricates success |
| 16 | No `approved_for_execution=True` anywhere |
| 17 | Deterministic serialization across rebuilds |
| 18 | Build with explicit `MemoryQueryResult` |
| 19 | Builder rejects empty / whitespace target |
| 20 | Snapshot with `approved_for_execution=True` rejected at Phase 5A model layer |
| 21 | Per-builder direct calls match aggregator output |
| 22 | Package-level re-exports through `lib/reliability/__init__.py` |
| 23 | Module `__all__` symmetry |
| 24 | No filesystem writes anywhere in pipeline |
| 25 | Build with snapshot but no memory store (top-level warning surfaces) |

All 163 assertions pass. The Phase 5A regression test passes 175/175.
