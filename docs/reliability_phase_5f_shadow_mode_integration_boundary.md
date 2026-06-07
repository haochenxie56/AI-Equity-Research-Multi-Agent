# Reliability Phase 5F — Shadow Mode Integration Boundary Planning

**Date**: 2026-05-27
**Status**: Accepted (planning-only; no runtime changes; no actual shadow
mode is implemented).
**Type**: Repo-level planning / documentation boundary describing how a
*future* read-only, feature-flagged shadow mode could observe the existing
five-step workflow's outputs and route them through the Phase 5A query
contract and the Phase 5B–5D view-model layer, **without changing live
workflow behavior**.
**Module(s) added**: None (documentation only).
**Test script added (lightweight, optional)**:
`scripts/test_reliability_phase_5f_shadow_mode_planning.py` — section /
forbidden-file / planning-only assertions over this Phase 5F doc.

> **Phase 5F is not shadow mode implementation.** Phase 5F does **not**
> implement a shadow-mode runner, does **not** wire Phase 4A
> (`lib/reliability/integration_boundary.py`) into the live app, does
> **not** modify `app.py`, `pages/*`, `lib/llm_orchestrator.py`,
> `lib/workflow_state.py`, `lib/valuation.py`, `lib/technical.py`,
> `lib/rotation.py`, `lib/data_fetcher.py`, `lib/cache_manager.py`, or any
> `.claude/agents/*` file, does **not** read or write
> `research/.workflow_state.json`, does **not** add a database, file
> persistence layer, vector store, or embedding pipeline, does **not** call
> the Anthropic SDK or any external HTTP / API, does **not** introduce a
> broker / order / trade-execution path, and does **not** enable
> `approved_for_execution = True` anywhere. Phase 5F only describes the
> planning boundary for a *future* shadow mode; it ships no observation
> code, no comparison runner, and no live wiring.

---

## 1. Purpose

Phase 5F defines the **planning boundary** for a *future* read-only,
feature-flagged shadow mode that could observe the existing five-step
workflow's outputs (Sector → Scanner → Equity → Financial → PriceVolume
→ Synthesis) and route them — entirely as a sibling, side-by-side observer
— into the Phase 5A–5D cockpit/view-model layer, without changing any live
workflow behavior, prompt, output, or persisted state.

Phase 5F is the sixth Phase 5 subphase. It sits after Phase 5A (memory
query contract), Phase 5B (Company Research Hub view-model), Phase 5C
(Horizon Decision Cards + ThesisTracker view-model), Phase 5D (Portfolio /
TradePlan / Option Overlay view-model), and Phase 5E (Cockpit UI Planning
Boundary).

Phase 5F answers planning-level questions only:

- What is shadow mode allowed to observe?
- What is shadow mode forbidden to modify?
- How would the existing workflow outputs be snapshotted in the future?
- How would those snapshots feed the Phase 5A query contract and the
  Phase 5B–5D view models?
- What feature flags, failure modes, and rollback guarantees are required
  before any actual shadow mode integration is allowed to begin?
- What must be true before actual integration can begin?

Phase 5F is **documentation-only**. No Python runtime module is added; no
Streamlit page is added; no live wiring is introduced; no broker / order /
execution surface is introduced. Phase 5G (Fixture Demo Pack) and Phase 5H
(Phase 5 Closeout) build on top of Phase 5F; they remain pending.

---

## 2. Relationship to Roadmap v4 Phase 5 Investment Cockpit

Roadmap v4 envisions an **Investment Cockpit** layered on top of the
existing five-step workflow. The Phase 5A query contract, the Phase 5B
Company Research Hub view, the Phase 5C Horizon Decision Cards +
ThesisTracker view, and the Phase 5D Portfolio / TradePlan / Option
Overlay view are deterministic, read-only, fixture-friendly inputs to
that cockpit. Phase 5E is the planning boundary for the cockpit *UI*.

Phase 5F is the planning boundary for the **shadow-mode observation
channel** between the existing live workflow and that future cockpit. In
Roadmap v4 terms, Phase 5F documents how the existing workflow could
become the **source** of cockpit-displayable view-models in a
side-by-side, read-only mode — without anyone editing the existing
workflow, without replacing the existing synthesis, and without enabling
execution capability of any kind.

Phase 5F does **not** authorize live wiring. A later, explicitly approved
controlled integration phase (post-5G / 5H or later) is required before
any of the future shadow components ships as real code.

---

## 3. Relationship to the Original README Streamlit App

The README documents a working bilingual Streamlit application with six
pages (Overview / Sector / Scanner / Equity / Financial / PriceVolume)
and a five-step AI workflow orchestrated by `lib/llm_orchestrator.py`,
with workflow state persisted via `lib/workflow_state.py` to
`research/.workflow_state.json`.

Phase 5F preserves the original app entirely:

- Every existing page continues to render its existing content.
- The existing five-step Overview workflow continues to call
  `lib/llm_orchestrator.py` directly.
- The live workflow state at `research/.workflow_state.json` continues
  to be owned by `lib/workflow_state.py` only.
- The existing live news / Finnhub / data-fetch behavior is preserved.
- The existing local Parquet cache (`lib/cache_manager.py`) is preserved.
- The existing bilingual EN / ZH UX, dark / light theming, and per-page
  Markdown export are preserved.

A future shadow mode (planned, not built in Phase 5F) is positioned as a
**read-only sibling observer**. It would never alter prompts, never alter
LLM outputs, never block the workflow, never replace the existing
synthesis, never write `research/.workflow_state.json`, and never call an
external API on the workflow's behalf. It would simply *copy* completed
workflow outputs into deterministic Phase 5A-compatible snapshots and
feed them through Phase 5B / 5C / 5D view-models for cockpit display.

---

## 4. Relationship to the Phase 5A Memory Query Contract

The Phase 5A contract defined:

- `ExistingWorkflowSnapshot`, `ExistingWorkflowStepSnapshot`,
  `ExistingPageOutputRef`, and `ExistingWorkflowSynthesisSnapshot`
  (in `lib/reliability/workflow_memory_adapter.py`).
- `WORKFLOW_STEP_ORDER` enumerating the canonical step sequence
  (`sector`, `scanner`, `equity`, `financial`, `price_volume`,
  `synthesis`).
- `WorkflowMemoryBundle`, the `WorkflowToMemoryAdapter` Protocol, and the
  `InMemoryWorkflowToMemoryAdapter` reference implementation.
- `MemoryQuery*`, `MemoryQueryResult`, `MemoryStoreProtocol`, and
  `FixtureBackedMemoryStore` (in
  `lib/reliability/phase5_memory_query.py`).
- `make_workflow_snapshot_id(...)` and
  `build_fixture_memory_store_from_snapshot(...)` factories.

Future shadow mode (planning-only) would feed live workflow outputs
through this exact contract:

1. After the existing workflow finishes a step (sector / scanner /
   equity / financial / price_volume / synthesis), a future shadow
   adapter would *copy* the step's output (Markdown text, structured
   summary metadata, target identifiers, optional source page refs) into
   an `ExistingWorkflowStepSnapshot`-shaped dataclass.
2. Once a full session is observed, the adapter would assemble an
   `ExistingWorkflowSnapshot` carrying the canonical step order and an
   optional `ExistingWorkflowSynthesisSnapshot`.
3. The snapshot would be fed into a future shadow-mode equivalent of
   `build_fixture_memory_store_from_snapshot` (or a similar adapter) to
   produce a `FixtureBackedMemoryStore`-style read-only store keyed by
   Phase 4M-compatible record IDs.
4. Phase 5B / 5C / 5D builders would consume the resulting
   `MemoryStoreProtocol` / `MemoryQueryResult` exactly as today, with no
   change to their signatures.

The Phase 5A boundary is *not* extended in Phase 5F. Phase 5F only
documents how a future shadow adapter would *use* the Phase 5A boundary.
If Phase 5A's interface needs any extension (e.g. a snapshot envelope
versioning field), that extension would be a separately reviewed phase,
not Phase 5F.

---

## 5. Relationship to Phase 5B Company Research Hub View Models

Phase 5B exposes deterministic builders that consume either a
`MemoryStoreProtocol` / `MemoryQueryResult` or an
`ExistingWorkflowSnapshot` and produce `CompanyResearchHubView`,
`CompanyIdentityView`, `EquityResearchPanelView`,
`FinancialValuationPanelView`, `PriceVolumeTimingPanelView`,
`SourceWorkflowPanelView`, `EvidenceCoveragePanelView`,
`ValidationStatusPanelView`, and `MissingDataWarningView`.

A future shadow-mode pipeline would feed snapshots through these
builders unchanged. Missing-data warnings continue to surface for missing
equity / financial / price-volume steps; no Phase 5B builder is modified
in Phase 5F.

---

## 6. Relationship to Phase 5C Horizon Decision Cards / ThesisTracker

Phase 5C exposes `HorizonDecisionCardsView`, `HorizonDecisionCardView`,
`ThesisTrackerView`, and the supporting badge / row / evidence /
assumption / next-action views. These are driven by Phase 4M-B thesis,
Phase 4M-C event, Phase 4M-F human feedback, and Phase 4M-G agent
evaluation memory through the Phase 5A `MemoryStoreProtocol`.

In a future shadow mode, the same Phase 5C builders would consume the
read-only memory store produced from a live workflow snapshot. Cards
would still appear in the canonical `short → medium → long` order;
review-needed signals would still flip cards to `needs_review`; missing
thesis would still yield a safe `"missing"` card. Phase 5F does not
modify any Phase 5C builder.

---

## 7. Relationship to Phase 5D Portfolio / TradePlan / Option Overlay

Phase 5D exposes `PortfolioCockpitView`, `AllocationSummaryView`,
`PositionAllocationView`, optional `RiskBudgetView`, optional
`CashImpactView`, `TradePlanView`, `TradePlanLevelView`,
`TradePlanReviewTriggerView`, `OptionOverlayView`,
`OptionStrategySummaryView`, `OptionRiskRewardView`,
`OptionLiquidityWarningView`, `OptionEventRiskWarningView`,
`NoTradeReasonView`, `ExecutionSafetyBannerView`, and
`MissingPortfolioDataWarningView`.

In a future shadow mode, Phase 5D builders would consume Phase 4M-D
allocation, Phase 4M-E option trade plan, and Phase 4M-F human feedback
records reconstructed from observed workflow output. The
`ExecutionSafetyBannerView` would always be present; `no_trade` would
remain first-class; `approved_for_execution` would remain `False` (or
absent); no executable order fields would be reintroduced. Phase 5F does
not modify any Phase 5D builder.

---

## 8. Relationship to Phase 5E UI Planning Boundary

Phase 5E documented the **future cockpit UI** planning boundary:
navigation, surfaces, page-to-cockpit mapping, view-model-to-component
bindings, data dependency matrix, safe degraded UI states, review-only
semantics, and forbidden files.

Phase 5F is the planning boundary for the **observation channel** that
would feed those Phase 5E cockpit surfaces in a future shadow mode. The
two phases compose:

- Phase 5E says: "*here* is where each view-model would render in a
  future cockpit."
- Phase 5F says: "*here* is how the existing workflow's output could
  reach those view-models read-only, side-by-side with the live app, in
  a future shadow mode."

Neither phase wires anything. Both phases are documentation-only.

---

## 9. Explicit Statement — This Is Not Shadow Mode Implementation

Phase 5F does **not** implement shadow mode. Phase 5F does **not** add a
shadow runner, a snapshot adapter, a comparison harness, a diff
reporter, or any Python module that observes the live workflow. Phase 5F
does **not** wire Phase 4A's `DISABLED / SHADOW / ENFORCED` mode
framework into the live app. Phase 5F does **not** modify any existing
Streamlit page, `app.py`, `lib/llm_orchestrator.py`,
`lib/workflow_state.py`, or any other live runtime file. Phase 5F does
**not** read or write `research/.workflow_state.json`.

Phase 5F only produces:

- This planning document
  (`docs/reliability_phase_5f_shadow_mode_integration_boundary.md`).
- An optional lightweight planning-doc test script at
  `scripts/test_reliability_phase_5f_shadow_mode_planning.py` that
  asserts required sections exist in this doc, the doc forbids the
  correct files, and the doc does not positively authorize
  `approved_for_execution=True` or any executable order field.
- State-file reconciliation in `docs/ai_dev_state/PROJECT_STATE.md` and
  `docs/ai_dev_state/CURRENT_TASK.md`.

Any actual implementation of the shadow components described below is
deferred to a later, explicitly approved controlled integration phase
(post-Phase 5G / 5H or later). Until then, this Phase 5F description is
a **plan**, not a build instruction.

---

## 10. Future Shadow Mode Goals

Future shadow mode (planned, not built) would aim for the following
strictly read-only goals:

1. **Observe completed workflow outputs**, step by step, without
   altering the workflow's behavior or timing.
2. **Copy** those outputs into deterministic Phase 5A-compatible
   snapshots that can be replayed offline.
3. **Reconstruct** read-only Phase 4M memory records from the snapshots
   (research run / thesis / event / allocation / option / human feedback
   / agent evaluation), all in memory only, with no DB or vector store.
4. **Produce** Phase 5B / 5C / 5D view-models from the reconstructed
   memory records, using the existing accepted Phase 5A boundary.
5. **Surface** those view-models to a future cockpit UI gated by the
   Phase 5E `COCKPIT_PLANNING_ONLY` → `COCKPIT_FIXTURE_PREVIEW` →
   `COCKPIT_SHADOW_VIEW` flag ladder, with `COCKPIT_LIVE_VIEW` remaining
   forbidden.
6. **Diagnose** discrepancies between observed workflow outputs and
   downstream view-model expectations through separate, opt-in,
   structured shadow logs — never as a side effect on the live workflow.
7. **Fail closed** if any expected output is missing or malformed: the
   shadow channel must degrade silently without affecting the live app.

These goals are aspirational. Phase 5F does not implement any of them.

---

## 11. Future Shadow Mode Observation Boundaries

Future shadow mode would be allowed (in a *later* controlled integration
phase, not Phase 5F) to:

- **Read** completed workflow outputs (per-step Markdown text and any
  structured metadata already produced by the existing workflow), only
  *after* the live workflow has written them.
- **Read** the existing Streamlit per-page Markdown report exports
  already produced by the live app.
- **Read** the existing local Parquet cache (`lib/cache_manager.py`) for
  metadata that the live workflow has already cached, in a strictly
  read-only manner.
- **Construct** an `ExistingWorkflowSnapshot`-shaped dataclass from the
  observed outputs.
- **Construct** a `FixtureBackedMemoryStore`-style read-only memory store
  via Phase 5A's accepted adapter contract.
- **Build** Phase 5B / 5C / 5D view-models from that store.
- **Emit** opt-in structured shadow-diagnostic log entries to a
  *separate* sink (e.g. a future opt-in observer log file located
  outside `research/.workflow_state.json`), only when an explicit
  shadow-diagnostic feature flag is enabled.
- **Fail closed** without affecting existing app behavior whenever an
  observation step is missing, malformed, or otherwise unsafe to
  process.

Future shadow mode would **not** be allowed to:

- Read or write `research/.workflow_state.json`. The live workflow
  state file remains owned by `lib/workflow_state.py`.
- Modify any cached Parquet file or any other artifact produced by the
  live workflow.
- Block the live workflow at any step.
- Reorder, retry, or cancel any step of the live workflow.
- Inject or modify prompts.
- Modify LLM outputs.
- Replace the existing synthesis.

---

## 12. Future Prohibited Mutations

Future shadow mode is **forbidden** from performing any of the following
mutations:

- **Prompt mutation**: no change to any prompt used by
  `lib/llm_orchestrator.py` or any `.claude/agents/*` file.
- **LLM output mutation**: no rewriting, redaction, augmentation, or
  re-ordering of any LLM response received by the existing workflow.
- **Workflow-state mutation**: no write of any kind to
  `research/.workflow_state.json`. The live workflow continues to be
  the sole writer.
- **Cache mutation**: no write to `lib/cache_manager.py`-managed Parquet
  artifacts. Reads must be strictly read-only.
- **Page mutation**: no edit to any file in `pages/`. The existing six
  pages remain verbatim.
- **App mutation**: no edit to `app.py`.
- **Library mutation**: no edit to `lib/llm_orchestrator.py`,
  `lib/workflow_state.py`, `lib/valuation.py`, `lib/technical.py`,
  `lib/rotation.py`, `lib/data_fetcher.py`, or `lib/cache_manager.py`.
- **Phase 4A mutation**: no edit to
  `lib/reliability/integration_boundary.py`. Phase 4A remains frozen
  early integration infrastructure. Even though Phase 4A provides
  `DISABLED / SHADOW / ENFORCED` mode literals, Phase 5F does not wire
  Phase 4A into the live app, and Phase 5F does not modify Phase 4A.
- **Memory record mutation**: no Phase 4M memory module is altered.
  Reconstructed records flow through the existing accepted Pydantic
  models only.
- **Execution mutation**: no broker / order / execution path,
  `approved_for_execution=True` flag, order ticket, execution ID, fill
  price, account ID, time-in-force, broker route, broker payload,
  order_type, quantity_to_execute, or any equivalent execution field is
  ever introduced.

---

## 13. Proposed Future Shadow Data Flow

The proposed future shadow data flow is strictly read-only and one-way:

```
┌───────────────────────────────────────────────────────────────┐
│  Existing live Streamlit app (PRESERVED — Phase 5F does not   │
│  touch any of this)                                            │
│                                                                │
│  Sector → Scanner → Equity → Financial → PriceVolume →         │
│  Synthesis (five-step workflow via lib/llm_orchestrator.py)    │
│  Live workflow state → research/.workflow_state.json           │
│  Local Parquet cache via lib/cache_manager.py                  │
│  Per-page Markdown exports                                     │
└───────────────────────────────────────────────────────────────┘
                  │  (post-step: completed output is observable
                  │   ONLY after the live workflow finishes the step.
                  │   No blocking, no injection, no retry, no reorder)
                  ▼
┌───────────────────────────────────────────────────────────────┐
│  Future read-only snapshot adapter (planned, not built)        │
│                                                                │
│  • Copies completed step output into an                        │
│    ExistingWorkflowStepSnapshot-shaped dataclass.              │
│  • Assembles an ExistingWorkflowSnapshot when the session      │
│    completes.                                                  │
│  • NEVER writes back to research/.workflow_state.json.         │
│  • NEVER mutates Parquet cache files.                          │
│  • NEVER modifies LLM prompts or outputs.                      │
│  • Fails closed on any unexpected shape.                       │
└───────────────────────────────────────────────────────────────┘
                  │  (snapshot fed forward by reference;
                  │   no live wiring back to the app)
                  ▼
┌───────────────────────────────────────────────────────────────┐
│  Phase 5A query / memory boundary (ACCEPTED — used as-is)      │
│                                                                │
│  build_fixture_memory_store_from_snapshot-style adapter →      │
│  FixtureBackedMemoryStore (read-only, in-memory).              │
│  MemoryQuery* models + MemoryQueryResult enforce               │
│  approved_for_execution = False on every returned result.      │
└───────────────────────────────────────────────────────────────┘
                  │  (read-only MemoryStoreProtocol /
                  │   MemoryQueryResult consumed by downstream)
                  ▼
┌───────────────────────────────────────────────────────────────┐
│  Phase 5B / 5C / 5D view-model builders (ACCEPTED — used as-is)│
│                                                                │
│  build_company_research_hub_view (5B)                          │
│  build_horizon_decision_cards_view + thesis tracker (5C)       │
│  build_portfolio_cockpit_view + trade plan + option overlay (5D)│
│  Safe degraded behavior preserved at every level.              │
└───────────────────────────────────────────────────────────────┘
                  │  (view-models become inputs to the future
                  │   cockpit UI per Phase 5E mappings)
                  ▼
┌───────────────────────────────────────────────────────────────┐
│  Future cockpit UI (planned in Phase 5E, not built)            │
│                                                                │
│  Sibling navigation surfaces only. Always renders              │
│  ExecutionSafetyBannerView. Never renders execution actions.   │
│  Honors safe-degraded UI states (Phase 5E §13).                │
└───────────────────────────────────────────────────────────────┘
```

The arrow above only points forward. There is **no back-channel** from
the cockpit, the view-model layer, the Phase 5A boundary, or the
snapshot adapter into the live app. The live app never observes that
shadow mode exists.

---

## 14. Proposed Future Event / Snapshot Envelope Fields

The future shadow snapshot adapter would produce envelopes shaped like
the following (planning-only — no Python class is added in Phase 5F):

| Field name                  | Description                                                                              | Notes                                                                 |
|-----------------------------|------------------------------------------------------------------------------------------|-----------------------------------------------------------------------|
| `envelope_schema_version`   | Integer version of the snapshot envelope shape                                            | Allows safe rollback when the envelope shape changes                  |
| `shadow_mode`               | Literal: `"disabled"` / `"shadow"` / `"enforced"`                                          | Mirrors Phase 4A literals; Phase 5F never sets `"enforced"`           |
| `shadow_run_id`             | Deterministic shadow-side ID (separate from live run ID)                                  | Never collides with `research/.workflow_state.json` run IDs           |
| `live_workflow_run_id`      | Read-only copy of the live workflow's run ID, if available                                | Read-only; never overwritten                                          |
| `observed_at`               | UTC timestamp when the shadow adapter observed the step                                   | Adapter-controlled, not workflow-controlled                            |
| `step_name`                 | One of `WORKFLOW_STEP_ORDER`: sector / scanner / equity / financial / price_volume / synthesis | Mirrors Phase 5A `ExistingWorkflowStepSnapshot.step_name`             |
| `step_status`               | Literal: `"completed"` / `"missing"` / `"malformed"`                                        | Adapter classification of the observed output                          |
| `step_output_ref`           | Opaque reference to the source output (e.g. Markdown report path)                         | Read-only path or in-memory identifier; never modified by the adapter |
| `step_output_text`          | Optional copy of the observed Markdown / text output                                      | Optional; may be omitted to save memory                                |
| `step_target`               | Ticker / target identifier observed for the step                                          | Mirrors Phase 5A target field                                          |
| `step_horizon`              | Optional horizon hint (`"short"` / `"medium"` / `"long"`)                                  | Used to populate Phase 5C cards                                        |
| `evidence_refs`             | List of evidence identifiers attached to the observed step                                | Read-only copy                                                         |
| `validation_status`         | Literal: `"passed"` / `"warning"` / `"unknown"`                                            | Optional; defaults to `"unknown"` until validators run downstream      |
| `shadow_warnings`           | List of structured shadow-side diagnostic strings                                          | Opt-in; emitted to a separate sink only                                |
| `approved_for_execution`    | Literal: `False`                                                                          | Hardcoded to `False`; never overridden; never `True`                  |
| `executable_order_fields`   | Literal: empty list                                                                        | No `order_type`, `time_in_force`, `broker_route`, etc.                |

Notes:

- The envelope is **read-only**: every consumer is forbidden from
  modifying any field after construction.
- `shadow_mode = "enforced"` is **never** produced by Phase 5F-derived
  planning. Phase 4A's `ENFORCED` literal exists in the framework but is
  out of scope for this phase.
- The envelope must never carry executable order fields. The
  `executable_order_fields` field is documented here only to anchor a
  test assertion that the field is always empty.

---

## 15. Feature Flag Plan

A future controlled integration phase would gate any shadow-mode
behavior behind feature flags. Phase 5F only describes the readiness
ladder; it does not introduce the flags. Phase 5E already defined
cockpit-side flags; Phase 5F mirrors them on the observation side.

| Flag (planning-only)        | Effect                                                                                  | Phase 5F status        |
|-----------------------------|-----------------------------------------------------------------------------------------|------------------------|
| `SHADOW_MODE_OFF`            | Default. No observation, no snapshot adapter, no Phase 5A feed.                          | Default                |
| `SHADOW_MODE_FIXTURE_ONLY`   | Observation is *simulated* from offline fixtures (Phase 5G) outside the live Streamlit. | Not authorized yet     |
| `SHADOW_MODE_OBSERVE`        | Future read-only observation of completed live steps; emits envelopes to a separate sink. | Not authorized yet     |
| `SHADOW_MODE_DIAGNOSE`       | Future structured diagnostic logs side-by-side with the live workflow; never blocking.   | Not authorized yet     |
| `SHADOW_MODE_ENFORCE`        | **Forbidden.** Would enable enforcement; explicitly out of scope.                        | **Forbidden**          |

Cockpit-side flags from Phase 5E continue to gate UI rendering:

| Phase 5E flag (reaffirmed)    | Effect                                                                                            | Phase 5F status    |
|-------------------------------|---------------------------------------------------------------------------------------------------|--------------------|
| `COCKPIT_PLANNING_ONLY`        | Cockpit documented only; no nav entry; no rendering path.                                          | Default            |
| `COCKPIT_FIXTURE_PREVIEW`      | Future fixture-driven preview outside the live app (Phase 5G).                                     | Not authorized yet |
| `COCKPIT_SHADOW_VIEW`          | Future shadow-mode cockpit rendering, side-by-side, read-only.                                     | Not authorized yet |
| `COCKPIT_LIVE_VIEW`            | **Forbidden.** Would enable live cockpit; explicitly out of scope.                                 | **Forbidden**      |

Phase 5F does not implement any of these flags.

---

## 16. Fail-Closed Behavior

Future shadow mode must **fail closed**. A failure in the shadow channel
must never propagate back into the live workflow.

Required fail-closed behaviors (planning-only):

- If the snapshot adapter cannot observe a step (file missing,
  permission error, parsing error, schema mismatch), the adapter must
  log a structured warning to its separate sink and return without
  producing a snapshot. The live workflow continues unaffected.
- If the snapshot envelope schema version is unknown, the adapter must
  refuse to emit; it must not attempt to coerce the envelope. The live
  workflow continues unaffected.
- If `build_fixture_memory_store_from_snapshot`-style construction
  fails, the downstream cockpit must render with all
  `MissingDataWarningView` / `MissingPortfolioDataWarningView` /
  `HorizonDecisionCardView(status="missing")` surfaces; it must not
  fabricate content.
- If a view-model builder raises, the cockpit must surface an empty
  view + warning; it must not crash the live app.
- The shadow channel must never raise into `app.py`,
  `lib/llm_orchestrator.py`, or `lib/workflow_state.py`. Any exception
  must be caught at the shadow boundary.
- `approved_for_execution` must remain `False` (or absent) in every
  failure mode. Failure must never relax the execution safety
  invariant.

---

## 17. Rollback Plan

Future shadow mode must be trivially rollbackable. The shadow channel is
strictly additive; no live file is modified, so rollback is a no-op for
the live app.

Planned rollback levers (planning-only):

- **Flag-level rollback**: setting `SHADOW_MODE_OFF` immediately
  disables all shadow observation, with no live-app side effect.
- **File-level rollback**: removing the snapshot adapter and any
  shadow-side log sink is sufficient to revert; the live app does not
  import the adapter.
- **Phase-level rollback**: rolling back the Phase 5F-derived future
  observation phase does not require touching `app.py`, `pages/*`,
  `lib/llm_orchestrator.py`, `lib/workflow_state.py`, or any Phase 4M /
  Phase 5A–5D module.
- **Phase 4A** remains frozen. Rollback does not require unwiring
  Phase 4A (because Phase 4A is never wired in by Phase 5F).
- **Envelope version rollback**: if a new envelope shape is rejected by
  downstream consumers, the shadow channel falls back to the previous
  envelope version. Phase 5F does not bump any envelope version; it
  only documents the field.

---

## 18. Error Isolation Plan

Errors in the future shadow channel must be **isolated** from the live
runtime:

- Exceptions inside the snapshot adapter must be caught at the adapter
  boundary; nothing must bubble back into the live workflow.
- The shadow logger must write to a separate file or sink (planning
  detail; not specified here) that is distinct from
  `research/.workflow_state.json` and distinct from the existing
  per-page Markdown export directory.
- The shadow channel must use deterministic IDs (`shadow_run_id`) that
  cannot collide with live workflow run IDs.
- The shadow channel must enforce a single read direction. There is no
  retry hook into the live workflow, no callback to
  `lib/llm_orchestrator.py`, and no callback to
  `lib/workflow_state.py`.
- Phase 4M memory module behavior is unchanged. Any reconstruction
  occurs in memory only and is dropped at the end of a shadow session.

---

## 19. No-Blocking Guarantee for the Original Workflow

The future shadow channel must **never block** the original workflow.
Concretely:

- No shadow code path may sit on the existing five-step workflow's
  critical path.
- No shadow code path may add latency to a step's completion (for
  example by holding a lock the live workflow needs).
- No shadow code path may pause, retry, or abort the existing
  workflow.
- No shadow code path may modify the timing of `app.py` rendering or
  page transitions in `pages/*`.
- All shadow observation happens *after* a step has reported completion
  to the existing workflow.

This guarantee is documented here as a planning invariant. Phase 5F
does not implement it; a later controlled integration phase must
explicitly verify it.

---

## 20. No-Prompt-Modification Guarantee

The future shadow channel must **never modify a prompt**. Concretely:

- No prompt template in `lib/llm_orchestrator.py` is edited.
- No prompt scaffold in `.claude/agents/*` is edited.
- No prompt is rewritten on the way to the model.
- No prompt is rewritten on the way back from the model.
- No system prompt is injected by the shadow channel.

Phase 5F's lightweight planning-doc test asserts this guarantee is
restated in the doc; it does not run any prompt comparison.

---

## 21. No-Output-Modification Guarantee

The future shadow channel must **never modify an LLM output**.
Concretely:

- No LLM response is rewritten by the shadow channel.
- No LLM response is filtered or redacted before reaching the existing
  Streamlit pages.
- No LLM response is augmented with shadow-side content before being
  persisted.
- The existing per-page Markdown reports are untouched; the shadow
  channel only *copies* them at observation time.

Phase 5F's lightweight planning-doc test asserts this guarantee is
restated in the doc; it does not run any output diff.

---

## 22. No-Execution Guarantee

The future shadow channel must **never execute a trade**. Concretely:

- No broker connection is opened.
- No order ticket is constructed.
- No order route is selected.
- No fill price is recorded.
- No execution ID is generated.
- No account ID is referenced.
- No quantity-to-execute is computed.
- No `approved_for_execution` field is set to `True`, ever, in any
  envelope, view-model, or cockpit surface.
- `executed_manually` from Phase 4M-F human feedback remains a
  memory-only label and is **never** rendered as an executable action.

The `approved_for_execution = False` invariant is reaffirmed by the
Phase 5A `MemoryQueryResult`, Phase 5B / 5C / 5D view-models, the
Phase 5E cockpit UI planning boundary, and now by Phase 5F.

---

## 23. Review-Only Semantics

Every artifact along the proposed shadow data flow is review-only:

- The snapshot adapter is a one-way read.
- The Phase 5A query boundary returns immutable Pydantic models.
- The Phase 5B / 5C / 5D view-models are deterministic, deterministic,
  read-only.
- The Phase 5E cockpit UI planning boundary describes a read-only UI
  layer with an always-present `ExecutionSafetyBannerView`.
- The Phase 5F snapshot envelope hardcodes `approved_for_execution =
  False` and `executable_order_fields = []`.

No part of the future shadow channel may render a "Place Order",
"Submit Order", "Approve Execution", "Send to Broker", or equivalent
action. No part may bind an order field to a UI control.

---

## 24. Safe Degraded States

Future shadow mode must inherit and reinforce the safe-degraded states
already documented in Phase 5B / 5C / 5D / 5E:

- Missing step → no snapshot produced → downstream
  `MissingDataWarningView` / `HorizonDecisionCardView(status="missing")`
  / `MissingPortfolioDataWarningView` surfaces.
- Malformed step → adapter logs a structured warning and emits nothing.
- Missing target → snapshot is target-scoped; absent targets produce
  empty cockpit views with the always-present
  `ExecutionSafetyBannerView`.
- Missing horizon → `HorizonDecisionCardView(status="missing")` per
  affected horizon.
- Missing allocation records → `missing_panels` includes `"allocation"`
  and `"trade_plan"`.
- Missing option records → `missing_panels` includes
  `"option_overlay"`.
- `no_trade` option state → populated `NoTradeReasonView`, empty
  `OptionRiskRewardView`; no substitute strategy.

The shadow channel must never fabricate content to fill a degraded
state.

---

## 25. Security / Privacy Considerations for Local State

Local state along the future shadow path must be handled carefully:

- The shadow adapter must not exfiltrate observed text to any external
  system (no HTTP, no external API, no upload).
- The shadow adapter must not write observed text into the existing
  workflow state (`research/.workflow_state.json`).
- The shadow adapter must not persist observed text into the local
  Parquet cache.
- If the shadow adapter writes shadow logs, the log destination must
  be a *separate* path explicitly designated for shadow diagnostics,
  outside the existing live state directory.
- The shadow adapter must respect existing file permissions; it must
  never attempt to elevate permissions to read protected files.
- No PII collection beyond what the existing workflow already produces
  is permitted.
- No telemetry / monitoring sink is introduced by Phase 5F.

These considerations are planning invariants. Phase 5F does not
implement any of them; a later controlled integration phase must
explicitly verify them.

---

## 26. Explicit Forbidden Files List

Phase 5F must **not** modify any of the following files. The list is
identical to Phase 5A / 5B / 5C / 5D / 5E forbidden files and is
repeated here for clarity:

- `app.py`
- `pages/1_Overview.py`
- `pages/2_Sector.py`
- `pages/3_Scanner.py`
- `pages/4_Equity.py`
- `pages/5_Financial.py`
- `pages/6_PriceVolume.py`
- `pages/*` (any other file in `pages/`)
- `lib/llm_orchestrator.py`
- `lib/valuation.py`
- `lib/technical.py`
- `lib/rotation.py`
- `lib/data_fetcher.py`
- `lib/workflow_state.py`
- `lib/cache_manager.py` *(read-only conceptually; not modified)*
- `lib/reliability/integration_boundary.py` *(frozen Phase 4A; not
  modified; not wired in)*
- `.claude/agents/*`
- Existing live prompt files
- Existing Streamlit UI
- Existing news / Finnhub / data-fetch behavior
- Existing live workflow behavior
- `research/.workflow_state.json` *(not read / not modified by
  Phase 5F)*

The Phase 5F lightweight planning-doc test asserts none of these files
were modified by Phase 5F.

---

## 27. Explicit Non-Goals

Phase 5F does **not**:

- Implement an actual shadow runner.
- Implement a snapshot adapter.
- Implement a comparison harness.
- Implement a shadow log sink.
- Wire Phase 4A (`lib/reliability/integration_boundary.py`) into the
  live app.
- Modify Phase 4A.
- Modify any existing Streamlit page.
- Modify the existing five-step workflow.
- Modify or import `lib/llm_orchestrator.py`.
- Modify or import `lib/workflow_state.py`.
- Read or write `research/.workflow_state.json`.
- Read or write any cached Parquet file.
- Import Streamlit anywhere.
- Add a Python UI module.
- Add a database backend (SQL or NoSQL).
- Add a file-based persistence layer.
- Add a vector store / embedding pipeline / similarity index.
- Call the Anthropic SDK or any external HTTP / API.
- Introduce a broker / order / trade-execution path.
- Introduce executable order fields (`order_type`, `time_in_force`,
  `broker_route`, `broker_id`, `account_id`, `quantity_to_execute`,
  `broker_payload`, `order_ticket`, `execution_id`, `fill_price`).
- Set `approved_for_execution = True` anywhere.
- Implement Phase 5G fixture demo pack.
- Implement Phase 5H Phase 5 closeout.
- Implement Streamlit UI.
- Implement real monitoring, alerts, orders, or execution.

---

## 28. Guardrails

### 28.1 Documentation-only

Phase 5F is documentation-only. The only file changes performed under
Phase 5F are:

- This new planning document
  (`docs/reliability_phase_5f_shadow_mode_integration_boundary.md`).
- A lightweight planning-doc test script at
  `scripts/test_reliability_phase_5f_shadow_mode_planning.py` that
  asserts (i) required sections exist in this Phase 5F doc, (ii) Phase
  5F is planning-only, (iii) forbidden files list exists in the doc,
  (iv) the doc does not positively authorize
  `approved_for_execution=True`, (v) the doc does not contain
  implementation wording that claims actual shadow mode is active.
- State-file reconciliation in `docs/ai_dev_state/PROJECT_STATE.md` and
  `docs/ai_dev_state/CURRENT_TASK.md`.

### 28.2 `approved_for_execution` invariant

- No Phase 5F artifact declares an `approved_for_execution` field on
  any envelope, view, surface, or component.
- The underlying Phase 4M memory records reject
  `approved_for_execution=True` at their respective model layers.
- The Phase 5A `MemoryQueryResult` enforces
  `approved_for_execution=False` on every returned result.
- Phase 5F's lightweight test asserts the planning doc itself does not
  positively authorize `approved_for_execution=True` anywhere (any
  mention of `approved_for_execution = True` appears only inside an
  explicit forbidden / non-goal / guardrail context).

### 28.3 No executable order fields

- Phase 5F does not introduce `order_type`, `time_in_force`,
  `broker_route`, `broker_id`, `account_id`, `quantity_to_execute`,
  `broker_payload`, `order_ticket`, `execution_id`, or `fill_price` in
  any artifact.
- The Phase 5F lightweight test asserts the doc does not positively
  authorize any of these fields in a future shadow envelope or
  renderer.

### 28.4 No live integration

- Phase 5F adds no Python module that imports `streamlit`,
  `lib.llm_orchestrator`, `lib.workflow_state`, `lib.data_fetcher`,
  `lib.valuation`, `lib.technical`, `lib.rotation`,
  `lib.cache_manager`, the Anthropic SDK, or any HTTP client.
- Phase 5F does not modify `lib/reliability/integration_boundary.py`
  (Phase 4A, frozen).
- The Phase 5F lightweight test asserts:
  - the planning doc does not authorize importing Streamlit,
  - the planning doc does not authorize wiring Phase 4A into the live
    app,
  - no Phase 5F Python module has been added under `lib/reliability/`,
  - no Phase 5F page has been added under `pages/`.

### 28.5 Phase 4A guardrail

Phase 4A (`lib/reliability/integration_boundary.py`) remains accepted
as early integration infrastructure and is **frozen**. Phase 5F may
*describe* the Phase 4A `DISABLED / SHADOW / ENFORCED` mode framework
only as a *planning reference*. Phase 5F itself does not wire, extend,
or modify Phase 4A. Phase 5F also does not produce code that would
later set the Phase 4A mode literal to `ENFORCED`.

### 28.6 No persistence

Phase 5F does **not** introduce:

- a database (SQL or NoSQL),
- a file-based persistence layer for shadow envelopes or memory
  records,
- a vector store / embedding pipeline / similarity index,
- a workflow_state writer or reader,
- a broker connector / order router,
- a real monitoring or alerting sink.

The Phase 4M memory layer remains in-memory only; the Phase 5A query
boundary remains fixture-friendly only; Phase 5F does not change
either.

### 28.7 No actual shadow mode

- Phase 5F does **not** declare shadow mode active.
- Phase 5F does **not** claim a snapshot adapter exists.
- Phase 5F does **not** wire any observer into the live app.
- The doc's narrative consistently uses **future** / **proposed** /
  **planned** wording for the shadow components described, never
  present-tense activation wording.

---

## 29. Acceptance Criteria

Phase 5F is accepted when:

1. `docs/reliability_phase_5f_shadow_mode_integration_boundary.md`
   (this file) exists and contains the required sections: Purpose;
   Relationship to Roadmap v4 Phase 5 Investment Cockpit; Relationship
   to the Original README Streamlit App; Relationship to Phase 5A
   memory query contract; Relationship to Phase 5B Company Research
   Hub view models; Relationship to Phase 5C Horizon Decision Cards /
   ThesisTracker; Relationship to Phase 5D Portfolio / TradePlan /
   Option Overlay; Relationship to Phase 5E UI Planning Boundary;
   Explicit Statement — This Is Not Shadow Mode Implementation; Future
   Shadow Mode Goals; Future Shadow Mode Observation Boundaries; Future
   Prohibited Mutations; Proposed Future Shadow Data Flow; Proposed
   Future Event / Snapshot Envelope Fields; Feature Flag Plan;
   Fail-Closed Behavior; Rollback Plan; Error Isolation Plan;
   No-Blocking Guarantee for the Original Workflow;
   No-Prompt-Modification Guarantee; No-Output-Modification Guarantee;
   No-Execution Guarantee; Review-Only Semantics; Safe Degraded States;
   Security / Privacy Considerations for Local State; Explicit
   Forbidden Files List; Explicit Non-Goals; Guardrails; Acceptance
   Criteria; Future Phase 5G Dependency.
2. `scripts/test_reliability_phase_5f_shadow_mode_planning.py` exists
   and passes with assertions covering: required-section existence in
   this Phase 5F doc; Phase 5F is planning-only (no Python module added
   under `lib/reliability/`; no page added under `pages/`); forbidden
   file list exists in the doc; the doc does not positively authorize
   `approved_for_execution=True`; the doc does not contain
   implementation wording that claims actual shadow mode is active.
3. `docs/ai_dev_state/PROJECT_STATE.md` and
   `docs/ai_dev_state/CURRENT_TASK.md` record Phase 5E as **Accepted**
   and Phase 5F as **Implemented — Awaiting Codex Review**. Phase 5G is
   **not** claimed to have started.
4. No live runtime file was modified by Phase 5F.
5. No database, file persistence layer, vector store, external API
   call, broker, order, or execution path was introduced by Phase 5F.
6. No actual shadow runner / snapshot adapter / comparison harness was
   introduced by Phase 5F.
7. `approved_for_execution` remains `False` (or absent) everywhere it
   appears.

---

## 30. Future Phase 5G Dependency

Phase 5G (Fixture Demo Pack Based on Original App Flow) consumes
Phase 5F as follows:

- Phase 5G will produce a deterministic synthetic fixture pack
  demonstrating end-to-end overlay traversal (workflow outputs →
  snapshot adapter → memory records → view-models → shadow-mode
  comparison output → cockpit render plan), entirely offline.
- Phase 5G will reference the snapshot envelope fields and the data
  flow described in Phase 5F. It will not introduce live wiring.
- Phase 5G must not bypass Phase 5F's no-execution and
  no-output-modification guarantees. No `approved_for_execution = True`
  may be set. No executable order field may be added. No broker /
  order / execution path may be introduced. Phase 4A remains frozen.
- Phase 5G is itself planning / fixture-only. Live wiring is deferred
  to a later, explicitly approved controlled integration phase
  (post-Phase 5H or later).

Phase 5H (Phase 5 Cockpit Boundary Closeout) builds on Phase 5A / 5B /
5C / 5D / 5E / 5F / 5G together; it does not add live wiring either.
