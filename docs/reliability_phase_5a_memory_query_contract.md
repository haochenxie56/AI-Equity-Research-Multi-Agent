# Reliability Phase 5A — Existing Workflow Memory Adapter + Fixture-backed Memory Query Contract

**Date**: 2026-05-27
**Status**: Implemented — awaiting Codex review.
**Type**: Read-only overlay contract for the existing README five-step workflow,
plus a fixture-backed memory query boundary for future Phase 5 view-models.
**Module(s) added**:

- `lib/reliability/workflow_memory_adapter.py`
- `lib/reliability/phase5_memory_query.py`
- `lib/reliability/phase5_fixtures.py`

**Test script added**: `scripts/test_reliability_phase_5a_memory_query.py`
(175/175 passing).

> **Phase 5A makes no live runtime changes.** It does not modify `app.py`,
> `pages/*`, `lib/llm_orchestrator.py`, `lib/workflow_state.py`,
> `lib/valuation.py`, `lib/technical.py`, `lib/rotation.py`,
> `lib/data_fetcher.py`, `lib/cache_manager.py`, `.claude/agents/*`, the
> existing Streamlit UI, the existing news/Finnhub/data-fetch behavior, or
> `research/.workflow_state.json`. Phase 4A
> (`lib/reliability/integration_boundary.py`) remains frozen and is **not**
> wired in. No database, file store, vector store, embedding pipeline, live
> Anthropic SDK call, HTTP request, or broker/order/execution path is
> introduced. `approved_for_execution` is `False` everywhere it appears.

---

## 1. Purpose

Phase 5A is the **first overlay contract** for Phase 5. It defines two
things, both offline / mock-only:

1. **Existing Workflow Memory Adapter** — a typed, read-only adapter
   contract that maps the *outputs* of the original README five-step
   Streamlit workflow (sector → scanner → equity → financial → price_volume
   → synthesis) onto Phase 4M-compatible memory record references.
2. **Fixture-backed Memory Query Contract** — a `MemoryStoreProtocol` plus
   a deterministic `FixtureBackedMemoryStore` implementation that future
   cockpit / view-model layers can query for Phase 4M memory records.

Both pieces are **protocol/interface plus fixture/mock query boundary
only**. Phase 5A does not start any real persistence layer and does not
read live workflow state.

---

## 2. Relationship to the Original README App

The README describes a working Streamlit app whose live entry point is:

```
Overview / Sector / Scanner / Equity / Financial / PriceVolume pages
   └── Five-step automated AI workflow on the Overview page
        Sector Analysis → Stock Scanner → Equity Research →
        Financial Analysis → PriceVolume Analysis → Synthesis
   └── Live Claude API via lib/llm_orchestrator.py
   └── Workflow state persisted at research/.workflow_state.json via
       lib/workflow_state.py
```

Phase 5A treats these existing outputs as **upstream data we describe by
reference**. It does not read `research/.workflow_state.json`, does not
import `lib/workflow_state.py`, and does not import `app.py` or `pages/*`.
Instead, an `ExistingWorkflowSnapshot` describes the *shape* of one such
run, and Phase 5A fixtures populate one entirely synthetic instance so the
boundary contract can be tested in isolation.

```
                ┌─────────────────────────────────────────────┐
                │   Existing Streamlit App (README, intact)   │
                │   five-step workflow + live Claude calls    │
                │   workflow_state.json persistence            │
                └───────────────┬─────────────────────────────┘
                                │  (NO Phase 5A live wiring)
                                ▼
   ExistingWorkflowSnapshot (fixture only)
                                │
                                ▼
   WorkflowToMemoryAdapter.adapt() (deterministic, offline)
                                │
                                ▼
   WorkflowMemoryBundle  (Phase 4M record references)
                                │
                                ▼
   FixtureBackedMemoryStore (read-only, in-memory)
                                │
                                ▼
   MemoryQueryResult  →  future Phase 5B/5C/5D cockpit view-models
```

---

## 3. Relationship to Phase 4M Memory

Phase 5A reuses the accepted Phase 4M memory record types **without
redefining or replacing them**:

| Phase 4M record | Reused as |
|-----------------|-----------|
| `ResearchRunMemoryRecord` (Phase 4M-A) | research run memory in the bundle |
| `HorizonThesisMemoryRecord` (Phase 4M-B) | per-horizon thesis memory in the bundle |
| `EventMemoryRecord` (Phase 4M-C) | catalyst/news/earnings memory in the bundle |
| `AllocationDecisionMemoryRecord` (Phase 4M-D) | allocation decision memory in the bundle |
| `OptionTradePlanMemoryRecord` (Phase 4M-E) | option trade plan memory in the bundle |
| `HumanFeedbackMemoryRecord` (Phase 4M-F) | human feedback memory in the bundle |
| `AgentEvaluationRecord` (Phase 4M-G) | agent evaluation memory in the bundle |

Phase 5A schemas are purely *pointer / adapter / query* shapes. They do
not duplicate Phase 4M record content.

---

## 4. Why This Is Not Real Persistence

The `FixtureBackedMemoryStore` is an **in-memory list-of-references**
holding fixture records. It exposes:

- No `save_to_disk()`, no `commit()`, no `flush()`.
- No SQL / NoSQL / file / vector / embedding backend.
- No external API call.
- No mutation of `research/.workflow_state.json`.

Records are stored in Python lists keyed by insertion order. The store
never serializes records to a persistence layer. The convenience helper
`build_fixture_memory_store_from_snapshot()` reads only the fixture
snapshot's already-registered records — there is no I/O.

---

## 5. Why It Does Not Read Live `workflow_state`

`workflow_memory_adapter.py` and `phase5_memory_query.py` do not import
`lib.workflow_state`, do not import `lib.llm_orchestrator`, do not import
`lib.data_fetcher`, do not import any Streamlit module, and do not import
any Anthropic SDK module. The test suite enforces this both at the
loaded-module level (`sys.modules` check) and at the source-substring
level (forbidden `import` substrings). The `ExistingWorkflowSnapshot` is
populated only by fixtures or, in production use, by future explicit
import paths approved in a controlled integration phase outside Phase 5.

---

## 6. Data Flow

```
   ┌──────────────────────────────────────────────────────────┐
   │ 1. ExistingWorkflowSnapshot fixture                      │
   │    - run_id, target, as_of                               │
   │    - 5 step sub-snapshots (sector/scanner/equity/         │
   │      financial/price_volume)                             │
   │    - synthesis sub-snapshot                              │
   │    - ExistingPageOutputRef objects per step              │
   └──────────────────────────┬───────────────────────────────┘
                              │
                              ▼
   ┌──────────────────────────────────────────────────────────┐
   │ 2. InMemoryWorkflowToMemoryAdapter.register_records()    │
   │    - associates Phase 4M memory records with snapshot    │
   │    - detects run_id / target mismatch as warnings        │
   │    - approved_for_execution stays False everywhere       │
   └──────────────────────────┬───────────────────────────────┘
                              │
                              ▼
   ┌──────────────────────────────────────────────────────────┐
   │ 3. WorkflowMemoryBundle                                  │
   │    - research_run_memory                                 │
   │    - thesis_records (short/medium/long)                  │
   │    - event_records                                       │
   │    - allocation_records                                  │
   │    - option_trade_records                                │
   │    - human_feedback_records                              │
   │    - agent_evaluation_records                            │
   │    - workflow_step_keys (deterministic order)            │
   └──────────────────────────┬───────────────────────────────┘
                              │
                              ▼
   ┌──────────────────────────────────────────────────────────┐
   │ 4. FixtureBackedMemoryStore.register_bundle()            │
   │    - in-memory only; no DB, no file, no vector store     │
   │    - rejects records with approved_for_execution=True    │
   └──────────────────────────┬───────────────────────────────┘
                              │
                              ▼
   ┌──────────────────────────────────────────────────────────┐
   │ 5. Query                                                 │
   │    - MemoryQueryByTicker                                 │
   │    - MemoryQueryByRunId                                  │
   │    - MemoryQueryByHorizon                                │
   │    - MemoryQueryByType                                   │
   │    - MemoryQueryByReviewStatus                           │
   │    - MemoryQuery (all)                                   │
   └──────────────────────────┬───────────────────────────────┘
                              │
                              ▼
   ┌──────────────────────────────────────────────────────────┐
   │ 6. MemoryQueryResult                                     │
   │    - 7 record-list fields (one per Phase 4M record type) │
   │    - deterministic ordering (insertion order, filtered)  │
   │    - total_count (pre-limit clamp)                       │
   │    - approved_for_execution=False                        │
   │    - consumed by future Phase 5B/5C/5D view-models       │
   └──────────────────────────────────────────────────────────┘
```

---

## 7. Query Contract

### 7.1 Query inputs

| Query | Filters on | Notes |
|-------|-----------|-------|
| `MemoryQuery()` | nothing | returns all records in insertion order |
| `MemoryQueryByTicker(target, record_types?)` | `target`; optional record-type filter | empty result if target missing |
| `MemoryQueryByRunId(run_id, record_types?)` | `run_id`; optional record-type filter | empty result if run_id missing |
| `MemoryQueryByHorizon(horizon, target?)` | thesis `horizon`; optional target | only thesis records returned |
| `MemoryQueryByType(record_type, target?, run_id?)` | single record type, scoped by optional target/run_id | empty result if no records of type |
| `MemoryQueryByReviewStatus(review_status, target?, record_types?)` | `any` / `needs_review` / `blocked` / `review_required` / `clean` | works across all record types |

All queries support an optional `limit` clamp.

### 7.2 Query result

Returned `MemoryQueryResult` carries seven typed record-list fields
(`research_run_records`, `thesis_records`, `event_records`,
`allocation_records`, `option_trade_records`, `human_feedback_records`,
`agent_evaluation_records`), a `total_count` (pre-limit), `warnings`, and
`approved_for_execution = False`. Convenience helpers `is_empty()` and
`count_by_type()` are provided.

### 7.3 Empty states

- Missing ticker → empty result, `total_count=0`, no hallucination.
- Missing run_id → empty result.
- Missing horizon → empty result.
- Unknown memory type → **validation error at query construction** (the
  query model rejects unknown types deterministically).
- Invalid snapshot (empty `run_id`/`target`, unknown step keys,
  `approved_for_execution=True`) → Pydantic `ValidationError`.

### 7.4 Determinism

- Snapshot IDs derive deterministically from `(run_id, target, as_of)`
  via `make_workflow_snapshot_id()`.
- Phase 4M record IDs (`memory_id`, `thesis_id`, etc.) come from their
  existing content-sensitive ID factories; identical fixture inputs yield
  identical IDs across runs.
- The store returns records in insertion order, filtered by query
  predicate. There is no randomized ordering.

---

## 8. Fixture-only Boundary

`lib/reliability/phase5_fixtures.py` provides:

- `SAMPLE_FIXTURE_TICKER = "FIXTKR"` — fictional, not a real US ticker.
- `SAMPLE_FIXTURE_RUN_ID`, `SAMPLE_FIXTURE_AS_OF` — deterministic.
- `make_sample_workflow_snapshot()` — one complete five-step snapshot
  plus synthesis.
- `make_sample_research_run_memory()`, `make_sample_thesis_records()`
  (short / medium / long), `make_sample_event_record()`,
  `make_sample_allocation_record()`, `make_sample_option_trade_record()`
  (with `approved_for_execution=False`),
  `make_sample_human_feedback_record()`,
  `make_sample_agent_evaluation_record()`.
- `build_sample_fixture_pack()` returns the tuple
  `(snapshot, adapter, bundle)` representing one complete journey through
  the original-app shape.

All fixture identifiers begin with `fix5a_` or `FIXTKR_` and are clearly
synthetic. No live API call is involved. No real prices, no real news.

---

## 9. Non-Goals

Phase 5A does **not**:

- Ship any new UI page.
- Modify any existing page or workflow.
- Add SQL, NoSQL, file, or vector store persistence.
- Embed records or build a similarity index.
- Call the Claude API, Anthropic SDK, or any HTTP service.
- Mutate `workflow_state`, agent definitions, or prompts.
- Route orders, place trades, or set `approved_for_execution = True`.
- Wire Phase 4A `integration_boundary.py` into the live app.
- Read `research/.workflow_state.json`.

---

## 10. Guardrails

### 10.1 Forbidden files (unchanged across Phase 5)

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
- `research/.workflow_state.json`

### 10.2 `approved_for_execution` invariant

- `ExistingWorkflowSnapshot` rejects `approved_for_execution=True`.
- `WorkflowMemoryBundle` rejects `approved_for_execution=True`.
- `MemoryQueryResult` rejects `approved_for_execution=True`.
- `FixtureBackedMemoryStore.add_*()` methods reject any record whose
  `approved_for_execution` is truthy.
- `register_bundle()` rejects any bundle with
  `approved_for_execution=True`.
- The option-trade fixture explicitly sets `approved_for_execution=False`.

### 10.3 No live integration

- No import of `lib.workflow_state`, `lib.llm_orchestrator`,
  `lib.data_fetcher`, `lib.valuation`, `lib.technical`, `lib.rotation`,
  Streamlit, or the Anthropic SDK in any Phase 5A module.
- The Phase 5A test suite checks both `sys.modules` and the module source
  text for forbidden import substrings.

### 10.4 Deterministic offline behavior

- All IDs are stable hash payloads.
- Snapshot serialization round-trips by value.
- The same fixture pipeline produces byte-identical IDs across runs.

---

## 11. Acceptance Criteria

Phase 5A is accepted when:

1. `lib/reliability/workflow_memory_adapter.py`,
   `lib/reliability/phase5_memory_query.py`, and
   `lib/reliability/phase5_fixtures.py` exist and pass the dedicated
   test suite (`scripts/test_reliability_phase_5a_memory_query.py`).
2. The fixture pipeline produces one complete original-app-style journey
   covering sector / scanner / equity / financial / price_volume /
   synthesis plus short/medium/long thesis records, one event record,
   one allocation record, one option trade record with
   `approved_for_execution=False`, one human feedback record, and one
   agent evaluation record.
3. Queries by ticker, run_id, horizon, type, and review status all
   return deterministic results, with safe empty behavior for missing
   inputs.
4. `lib/reliability/__init__.py` re-exports the stable Phase 5A
   symbols.
5. No live runtime files are modified.
6. `approved_for_execution` remains `False` everywhere.
7. No DB, file persistence, vector store, external API, broker, or order
   path is introduced.
8. Phase 4M-G regression test (`test_reliability_agent_evaluation.py`)
   continues to pass at 307/307.
9. State files (`PROJECT_STATE.md`, `CURRENT_TASK.md`) record Phase 5A
   as "Implemented — Awaiting Codex Review" without claiming Phase 5B
   has started.

---

## 12. Future Phase 5B Dependency

Phase 5B (Company Research Hub ViewModel Contract) consumes Phase 5A as
follows:

- A future `CompanyResearchHubViewModel` reads from a
  `MemoryStoreProtocol` instance (typically the
  `FixtureBackedMemoryStore` during planning) via
  `MemoryQueryByTicker` / `MemoryQueryByRunId` / `MemoryQueryByHorizon`.
- View-model construction must remain offline. Phase 5B introduces no UI
  page, no Streamlit integration, no live wiring.
- The Phase 5A `WorkflowMemoryBundle.workflow_step_keys` (ordered
  sector / scanner / equity / financial / price_volume / synthesis)
  gives Phase 5B a stable layout key for ordering view-model sections
  that mirror the existing five-step workflow.
- Phase 5B must not bypass Phase 5A's `approved_for_execution=False`
  invariant.

Phase 5C/5D/5E/5F/5G/5H build on Phase 5B's view-model contracts; none
of them adds live wiring.

---

## 13. Test Matrix

`scripts/test_reliability_phase_5a_memory_query.py` covers 175
assertions across 19 sections:

| Section | Topic |
|---------|-------|
| 1 | Module imports + forbidden-module non-load (sys.modules) |
| 2 | Source-level forbidden import substring check |
| 3 | `ExistingWorkflowSnapshot` construction, validation, round-trip |
| 4 | `InMemoryWorkflowToMemoryAdapter` adapt + register |
| 5 | Adapter mismatch detection (run_id / target) |
| 6 | `FixtureBackedMemoryStore` basics + `MemoryStoreProtocol` |
| 7 | `MemoryQueryByTicker` (incl. missing-ticker empty result) |
| 8 | `MemoryQueryByRunId` (incl. missing-run_id empty result) |
| 9 | `MemoryQueryByHorizon` (incl. missing-horizon empty result) |
| 10 | `MemoryQueryByType` across all 7 record types + invalid type |
| 11 | `MemoryQueryByReviewStatus` `any` / `clean` / `needs_review` / `blocked` / `review_required` |
| 12 | `approved_for_execution=False` invariant across results |
| 13 | `limit` clamp + deterministic ordering across builds |
| 14 | `build_fixture_memory_store_from_snapshot()` convenience |
| 15 | Store rejects approved=True records (defense in depth) |
| 16 | Unknown query type raises `TypeError` |
| 17 | No filesystem writes during Phase 5A pipeline |
| 18 | `__all__` lists match expected exports |
| 19 | Package-level re-exports through `lib/reliability/__init__.py` |

All 175 assertions pass. The Phase 4M-G regression test passes 307/307.
