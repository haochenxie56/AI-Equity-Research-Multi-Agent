# Reliability Phase 5E — Cockpit UI Planning Boundary for Existing Streamlit App

**Date**: 2026-05-27
**Status**: Accepted (planning-only; no runtime changes).
**Type**: Repo-level planning / documentation boundary describing how a
future Investment Cockpit UI could render the Phase 5B / 5C / 5D
view-model contracts *next to* the existing Overview / Sector / Scanner /
Equity / Financial / PriceVolume Streamlit pages, without modifying any
of them.
**Module(s) added**: None (documentation and state files only).
**Test script added (lightweight)**:
`scripts/test_reliability_phase_5e_cockpit_ui_planning.py` — section /
forbidden-file / planning-only assertions over the Phase 5E doc itself.

> **Phase 5E is not UI implementation.** Phase 5E does **not** add a
> Streamlit page, modify `pages/*`, modify `app.py`, modify
> `lib/llm_orchestrator.py`, modify `lib/workflow_state.py`, modify
> `lib/valuation.py`, modify `lib/technical.py`, modify `lib/rotation.py`,
> modify `lib/data_fetcher.py`, modify `lib/cache_manager.py`, modify any
> `.claude/agents/*` file, modify the live news/Finnhub/data-fetch
> behavior, modify the live workflow behavior, modify or read
> `research/.workflow_state.json`, wire Phase 4A
> (`lib/reliability/integration_boundary.py`) into the live app, add a
> database, add a file persistence layer, add a vector store, add an
> embedding pipeline, call the Anthropic SDK or any external HTTP API,
> introduce a broker / order / trade-execution path, or enable
> `approved_for_execution = True` anywhere. Phase 5E only describes the
> planning boundary for a *future* cockpit; it ships no UI and no live
> wiring.

---

## 1. Purpose

Phase 5E defines the **planning boundary** for a future Investment
Cockpit UI built on top of the existing README-based Streamlit app. It
is the fifth Phase 5 subphase, sitting after Phase 5A (memory query
contract), Phase 5B (Company Research Hub view-model), Phase 5C
(Horizon Decision Cards + ThesisTracker view-model), and Phase 5D
(Portfolio / TradePlan / Option Overlay view-model).

Phase 5E answers planning-level questions only:

- How would the existing app navigation evolve?
- Which existing pages are preserved verbatim?
- Which *future* cockpit surfaces would consume the Phase 5A–5D
  view-model contracts?
- What data dependency would each future cockpit component have?
- What must remain forbidden until a later, explicitly approved
  controlled integration phase?
- What review-only / non-execution UI semantics must be honored by any
  future renderer?

Phase 5E is **documentation-only**. No Python UI module, no Streamlit
page, no live wiring, no broker/order/execution surface is introduced.
Phase 5F (Shadow Mode Integration Boundary Planning) and beyond
consume Phase 5E; they remain pending.

---

## 2. Relationship to Roadmap v4 Phase 5 Investment Cockpit

Roadmap v4 envisions a **Phase 5 Investment Cockpit** layered on top of
the existing five-step workflow:

- A unified review home for the human investor.
- Horizon-keyed decision cards (short / medium / long) with thesis
  evolution context.
- A Company Research Hub aggregating equity research, financial
  valuation, and price/volume timing.
- A Portfolio / Allocation cockpit, TradePlan review surface, and
  Option Overlay surface.
- Catalyst / news / earnings monitoring.
- A human-feedback review surface and an agent-evaluation calibration
  surface.

Phase 5E is the **planning boundary** for those Roadmap v4 surfaces.
It maps each future surface to the Phase 5A–5D deterministic
view-model contracts already accepted in the overlay layer. Phase 5E
does **not** implement any of those surfaces. Phase 5E does **not**
authorize live wiring. A later, explicitly approved controlled
integration phase is required before any of these surfaces ships as
real UI.

---

## 3. Relationship to the Original README Streamlit App

The README documents a working bilingual Streamlit application with
six pages and a five-step AI workflow. Phase 5E preserves the
existing app entirely: every existing page continues to render its
existing content, the existing five-step Overview workflow continues
to call `lib/llm_orchestrator.py` directly, and the existing live
workflow state at `research/.workflow_state.json` continues to be
owned by `lib/workflow_state.py` only.

The future cockpit surfaces described below are positioned as **new
sibling surfaces** next to the existing six pages. They are *not*
edits to the existing pages, *not* replacements for the existing
pages, and *not* live wiring into `lib/llm_orchestrator.py` or
`lib/workflow_state.py`. Until a later, explicitly approved controlled
integration phase, all proposed cockpit surfaces remain on paper.

Phase 5E preserves the existing app's:

- Six Streamlit pages: Overview, Sector, Scanner, Equity, Financial,
  PriceVolume.
- Five-step Overview workflow: Sector Analysis → Stock Scanner →
  Equity Research → Financial Analysis → PriceVolume Analysis →
  Synthesis.
- Live Claude API workflow via `lib/llm_orchestrator.py`.
- Workflow state persistence via `lib/workflow_state.py` to
  `research/.workflow_state.json`.
- Local Parquet cache via `lib/cache_manager.py`.
- Bilingual EN / ZH UX, dark / light theming.
- Per-page Markdown report export.

---

## 4. Explicit Statement — This Is Not UI Implementation

Phase 5E does **not** implement a UI. Phase 5E does **not** add a
Streamlit page. Phase 5E does **not** modify any existing Streamlit
page. Phase 5E does **not** import Streamlit. Phase 5E does **not**
introduce a Python UI module (no widgets, no layout code, no
`st.*` calls). Phase 5E only produces a planning document plus a
lightweight planning artifact and a lightweight planning-doc test
script that asserts the *document's* sections and guardrail
properties.

Any actual implementation of the surfaces described below is deferred
to a later, explicitly approved controlled integration phase
(post-Phase 5G / 5H or later). Until then, the cockpit description in
this document is a **plan**, not a build instruction.

---

## 5. Existing Pages To Preserve

Phase 5E must preserve all six existing Streamlit pages without
modification. Each page is captured below with its existing
responsibility (mirroring the README):

| Existing page | File | Existing responsibility |
|---------------|------|--------------------------|
| Overview      | `pages/1_Overview.py` | One-click five-step AI workflow (Sector → Scanner → Equity → Financial → PriceVolume → Synthesis); workflow state persisted via `lib/workflow_state.py`. |
| Sector        | `pages/2_Sector.py`   | Six-dimensional sector analysis, ETF normalized return comparison, sector rotation heatmap. |
| Scanner       | `pages/3_Scanner.py`  | Four-strategy parallel screening (momentum / value / quality growth / oversold rebound) plus AI cross-strategy evaluation. |
| Equity        | `pages/4_Equity.py`   | Moat radar, peer comparison, AI deep-research view (business model, competitive landscape, management). |
| Financial     | `pages/5_Financial.py`| Three-statement table, multi-scenario DCF, EV/EBITDA / P/S relative valuation. |
| PriceVolume   | `pages/6_PriceVolume.py` | K-line plus RSI / MACD / ADX / Bollinger Bands, support / resistance, stop-loss reference. |

Phase 5E **must not** modify any of these files. Phase 5E **must not**
modify `app.py`. Phase 5E **must not** modify the five-step workflow
orchestration in `lib/llm_orchestrator.py`. Phase 5E **must not**
modify `lib/workflow_state.py` or any other live runtime file.

---

## 6. Proposed Future Cockpit Navigation Structure (Planning)

Below is a *proposed* navigation outline for a future Investment
Cockpit. It is descriptive, not prescriptive: a later controlled
integration phase will decide the exact shape. None of it is built in
Phase 5E.

```
Existing App Sidebar (preserved verbatim)
├── Overview                 [existing — preserved]
├── Sector                   [existing — preserved]
├── Scanner                  [existing — preserved]
├── Equity                   [existing — preserved]
├── Financial                [existing — preserved]
└── PriceVolume              [existing — preserved]

Future Investment Cockpit Sidebar Group (proposed; not built)
├── Investment Cockpit (home)
├── Company Research Hub
├── Horizon Decision Cards
├── Watchlist + ThesisTracker
├── Portfolio / Allocation Cockpit
├── TradePlan Review
├── Option Overlay
├── Human Feedback Review
├── Catalyst / News / Earnings Monitor
└── Macro Dashboard          [future / optional]
```

Notes:

- The future cockpit group is rendered as a **sibling sidebar group**,
  not inside any existing page. The existing six pages are untouched.
- A future controlled integration phase would choose whether to use
  Streamlit's native multipage sidebar, a tabbed cockpit page, or a
  separate cockpit entrypoint. Phase 5E does not commit to any of
  those choices.
- All Phase 5E cockpit surfaces are **review-only** and
  **non-executable** by construction (Section 12). No surface ships
  with a "Place Order" / "Approve Execution" button.
- The Macro Dashboard is listed as future / optional. The existing
  Sector page already covers macro / sector rotation context; a future
  Macro Dashboard would only be added if a later phase produces a
  macro view-model contract.

---

## 7. Proposed Future Cockpit Surfaces

Each future surface below is described by purpose, the upstream Phase
5A–5D view-model contract that would feed it, and the safe degraded
behavior it inherits from the contract layer. None of these surfaces
is built in Phase 5E.

### 7.1 Investment Cockpit (home)

- **Purpose**: A landing surface that summarizes the most recent runs
  (per target / per horizon) and surfaces review-needed badges
  consolidated across the cockpit.
- **Upstream contract**: aggregates per-target snapshots of
  `CompanyResearchHubView` (5B), `HorizonDecisionCardsView` (5C), and
  `PortfolioCockpitView` (5D) plus a `MemoryQueryResult` summary from
  Phase 5A.
- **Safe degraded behavior**: when no recent run exists, the home
  surface shows a warning panel ("no recent run for target") and the
  always-present execution-safety banner. No content is fabricated.

### 7.2 Company Research Hub

- **Purpose**: One target-scoped page projecting equity research,
  financial valuation, price/volume timing, source workflow attribution,
  evidence coverage, and validation status.
- **Upstream contract**: `CompanyResearchHubView` (Phase 5B) →
  `CompanyIdentityView`, `EquityResearchPanelView`,
  `FinancialValuationPanelView`, `PriceVolumeTimingPanelView`,
  `SourceWorkflowPanelView`, `EvidenceCoveragePanelView`,
  `ValidationStatusPanelView`, `MissingDataWarningView`.
- **Safe degraded behavior**: a missing equity / financial /
  price-volume step yields a degraded panel with a
  `MissingDataWarningView`; the surface renders the warning, not a
  fabricated panel.

### 7.3 Horizon Decision Cards

- **Purpose**: Three cards per target (short / medium / long horizon)
  showing thesis status, invalidation triggers, review-needed badges,
  missing-evidence badges, and the next-action label.
- **Upstream contract**: `HorizonDecisionCardsView` (Phase 5C) → a
  list of `HorizonDecisionCardView` rendered in the canonical
  `short → medium → long` order. Each card carries
  `ThesisStatusView`, `InvalidationTriggerView`,
  `ReviewNeededBadgeView`, `MissingEvidenceBadgeView`,
  `HorizonEvidenceSummaryView`, `HorizonRiskSummaryView`,
  `HorizonAssumptionView`, `HorizonNextActionView`.
- **Safe degraded behavior**: when a horizon has no thesis, the card
  renders as a `"missing"` card with warnings. Review-needed signals
  from Phase 4M-C events, Phase 4M-F human feedback, and Phase 4M-G
  agent evaluation flip the card status to `needs_review`. Phase 5E
  never invents a thesis.

### 7.4 Watchlist + ThesisTracker

- **Purpose**: A flat per-target × per-horizon view of thesis status
  evolution, last update timestamps, invalidation trigger counts,
  evidence id counts, review-needed flags, and missing-evidence kinds.
- **Upstream contract**: `ThesisTrackerView` (Phase 5C) and its rows
  `ThesisTrackerRowView`. The cockpit composer joins on
  `(target, horizon)` to render a sortable table.
- **Safe degraded behavior**: a missing thesis surfaces a row with
  `status="missing"` and a populated `missing_evidence_badge`. Phase
  5E never fabricates rows.

### 7.5 Portfolio / Allocation Cockpit

- **Purpose**: A target-scoped portfolio review surface aggregating
  per-record allocation projections, allocation summary counts, optional
  risk budget, and optional cash impact.
- **Upstream contract**: `PortfolioCockpitView` (Phase 5D) →
  `AllocationSummaryView`, `PositionAllocationView`, optional
  `RiskBudgetView`, optional `CashImpactView`,
  `ExecutionSafetyBannerView` (always present),
  `MissingPortfolioDataWarningView` (when sub-views are missing).
- **Safe degraded behavior**: missing allocation records yield empty
  aggregates and `missing_panels` includes `"allocation"`. Risk budget
  / cash impact only populate when the underlying records carry the
  corresponding fields. Phase 5E never fabricates portfolio numbers.

### 7.6 TradePlan Review

- **Purpose**: One review card per allocation memory record enumerating
  descriptive entry / add / trim / stop / target / review slots; surfaces
  review triggers from status / review_status / human feedback.
- **Upstream contract**: `TradePlanView` (Phase 5D) →
  `TradePlanLevelView` × 6 (canonical
  `entry → add → trim → stop → target → review`) and
  `TradePlanReviewTriggerView`.
- **Safe degraded behavior**: a missing trade plan yields an empty
  TradePlan list and the missing-data warning surface. Phase 5E never
  converts a TradePlan card into an executable order; no order type,
  no time-in-force, no broker route, no account ID, no quantity to
  execute is rendered.

### 7.7 Option Overlay

- **Purpose**: One overlay card per option trade plan memory record
  surfacing strategy summary, risk/reward, liquidity warnings, event-risk
  warnings, and an explicit `NoTradeReasonView` when the underlying
  record reports `no_trade`.
- **Upstream contract**: `OptionOverlayView` (Phase 5D) →
  `OptionStrategySummaryView`, `OptionRiskRewardView`,
  `OptionLiquidityWarningView`, `OptionEventRiskWarningView`,
  `NoTradeReasonView`.
- **Safe degraded behavior**: `no_trade` is preserved as first-class
  overlay state; the cockpit renders the populated `NoTradeReasonView`
  and an empty `OptionRiskRewardView` rather than inferring a
  substitute strategy. Liquidity / event-risk warnings render from
  upstream records only.

### 7.8 Human Feedback Review

- **Purpose**: A target-scoped surface showing human-feedback memory
  entries (decision / override reason / review status) and where each
  entry's review_required flag surfaces back into the cockpit
  (horizon card / TradePlan / overlay / position).
- **Upstream contract**: surfaced through Phase 5C
  `ReviewNeededBadgeView` and Phase 5D `TradePlanReviewTriggerView`
  derived from `HumanFeedbackMemoryRecord` (Phase 4M-F).
  Phase 5E does **not** add a new view-model; it composes the existing
  Phase 5C / 5D contracts and surfaces the same warnings.
- **Safe degraded behavior**: missing human feedback records yield no
  badge / no trigger. `executed_manually` is treated as a memory-only
  label and is **not** rendered as an executable action.

### 7.9 Catalyst / News / Earnings Monitor

- **Purpose**: A target-scoped surface listing event memory entries
  (Phase 4M-C) with review-needed flags, missing-evidence badges, and
  links back to Horizon Decision Cards.
- **Upstream contract**: surfaced through Phase 5C
  `MissingEvidenceBadgeView` and `HorizonEvidenceSummaryView` derived
  from event memory.
  Phase 5E does **not** add a new view-model; it composes the existing
  Phase 5C contract.
- **Safe degraded behavior**: missing event memory yields empty
  evidence-summary panes and `missing_evidence_kinds` badges. No event
  content is fabricated.

### 7.10 Macro Dashboard (future / optional)

- **Purpose**: A potential future surface aggregating macro regime
  context and per-horizon macro impact.
- **Upstream contract**: would require a future Phase 5* macro view-model
  (not part of Phase 5A–5D). Until that view-model exists, the cockpit
  composer would simply not render this surface.
- **Safe degraded behavior**: deferred entirely; the existing Sector
  page already covers macro / rotation today.

---

## 8. Mapping From Existing Pages to Future Cockpit Surfaces

The existing pages are **preserved verbatim**. The cockpit surfaces are
**siblings**, not replacements. The table below documents the
conceptual mapping so a later integration phase can decide how the two
are co-presented; it does **not** authorize any edit to the existing
pages.

| Existing page | Sibling cockpit surface(s)                                          | Relationship                                                                 |
|---------------|----------------------------------------------------------------------|------------------------------------------------------------------------------|
| Overview      | Investment Cockpit home                                              | Cockpit home is a *parallel* landing surface; Overview's five-step workflow is untouched. |
| Sector        | Macro Dashboard (future / optional)                                  | Macro Dashboard is deferred; Sector page continues to own macro / rotation today. |
| Scanner       | Investment Cockpit home (candidate summary tile)                     | Cockpit home would surface "recent scan targets"; Scanner page logic is unchanged. |
| Equity        | Company Research Hub (Equity Research panel)                         | Cockpit panel reuses the same equity-research artifact via Phase 5B; Equity page is preserved. |
| Financial     | Company Research Hub (Financial Valuation panel)                     | Cockpit panel reuses the same financial artifact via Phase 5B; Financial page is preserved. |
| PriceVolume   | Company Research Hub (PriceVolume Timing panel)                      | Cockpit panel reuses the same price/volume artifact via Phase 5B; PriceVolume page is preserved. |

Mapping rules:

- The mapping is *additive*, not destructive. Existing pages never lose
  features.
- No mapping authorizes an edit to a `pages/*` file. Each cockpit
  surface is its own file, rendered in a sibling navigation group, at a
  later controlled integration phase.
- No mapping authorizes live wiring. The cockpit always consumes the
  Phase 5A–5D view-model contracts, which are fixture-friendly and
  offline.

---

## 9. Mapping From Phase 5A–5D View-Models to Future UI Components

Phase 5E pre-binds each future cockpit component to a specific
Phase 5A–5D view-model. The cockpit composer is read-only.

| Future UI component                | Upstream Phase 5 contract                                                                 |
|-----------------------------------|-------------------------------------------------------------------------------------------|
| Cockpit home — recent-run tile     | Phase 5A `MemoryQueryResult` summary; Phase 5B `CompanyResearchHubView` ticker/run header |
| Cockpit home — review-needed badge | Phase 5C `ReviewNeededBadgeView`; Phase 5D `TradePlanReviewTriggerView`                   |
| Company Research Hub identity      | Phase 5B `CompanyIdentityView`                                                            |
| Equity Research panel              | Phase 5B `EquityResearchPanelView`                                                        |
| Financial Valuation panel          | Phase 5B `FinancialValuationPanelView`                                                    |
| PriceVolume Timing panel           | Phase 5B `PriceVolumeTimingPanelView`                                                     |
| Source Workflow panel              | Phase 5B `SourceWorkflowPanelView`                                                        |
| Evidence Coverage panel            | Phase 5B `EvidenceCoveragePanelView`                                                      |
| Validation Status panel            | Phase 5B `ValidationStatusPanelView`                                                      |
| Missing-data warning surface       | Phase 5B `MissingDataWarningView` + Phase 5D `MissingPortfolioDataWarningView`            |
| Horizon Decision Card (short)      | Phase 5C `HorizonDecisionCardView(horizon="short")`                                       |
| Horizon Decision Card (medium)     | Phase 5C `HorizonDecisionCardView(horizon="medium")`                                      |
| Horizon Decision Card (long)       | Phase 5C `HorizonDecisionCardView(horizon="long")`                                        |
| Invalidation trigger row           | Phase 5C `InvalidationTriggerView`                                                        |
| Review-needed badge                | Phase 5C `ReviewNeededBadgeView`                                                          |
| Missing-evidence badge             | Phase 5C `MissingEvidenceBadgeView`                                                       |
| Horizon evidence summary           | Phase 5C `HorizonEvidenceSummaryView`                                                     |
| Horizon risk summary               | Phase 5C `HorizonRiskSummaryView`                                                         |
| Horizon assumption                 | Phase 5C `HorizonAssumptionView`                                                          |
| Horizon next action                | Phase 5C `HorizonNextActionView`                                                          |
| ThesisTracker table                | Phase 5C `ThesisTrackerView` rows (`ThesisTrackerRowView`)                                |
| Allocation summary                 | Phase 5D `AllocationSummaryView`                                                          |
| Position allocation row            | Phase 5D `PositionAllocationView`                                                         |
| Risk budget surface                | Phase 5D `RiskBudgetView` (only when present)                                              |
| Cash impact surface                | Phase 5D `CashImpactView` (only when present)                                              |
| TradePlan card                     | Phase 5D `TradePlanView`                                                                   |
| TradePlan level row                | Phase 5D `TradePlanLevelView`                                                              |
| TradePlan review trigger           | Phase 5D `TradePlanReviewTriggerView`                                                      |
| Option Overlay card                | Phase 5D `OptionOverlayView`                                                               |
| Option strategy summary            | Phase 5D `OptionStrategySummaryView`                                                       |
| Option risk/reward                 | Phase 5D `OptionRiskRewardView`                                                            |
| Option liquidity warning           | Phase 5D `OptionLiquidityWarningView`                                                      |
| Option event-risk warning          | Phase 5D `OptionEventRiskWarningView`                                                      |
| No-trade reason surface            | Phase 5D `NoTradeReasonView`                                                               |
| Execution safety banner            | Phase 5D `ExecutionSafetyBannerView` (always present on cockpit)                          |

The cockpit composer **must not** invent new view-model classes for
Phase 5E. If a surface needs additional context, a later phase must
extend Phase 5A–5D first (in a documented, Codex-reviewed phase),
*not* Phase 5E.

---

## 10. Data Dependency Matrix

Each future cockpit surface depends on a small, well-defined set of
Phase 4M memory record types, mediated through the Phase 5A query
contract. The matrix below is read-only at every layer.

| Future surface                  | Phase 4M dependencies                                                                                 | Phase 5 contract surface                                                |
|---------------------------------|--------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| Cockpit home                    | 4M-A run, 4M-B thesis, 4M-D allocation, 4M-E option, 4M-F feedback, 4M-G evaluation                    | 5A `MemoryQueryResult` + 5B/5C/5D snapshots                              |
| Company Research Hub            | 4M-A research run + 4M-A run snapshot context                                                          | 5B `CompanyResearchHubView`                                              |
| Horizon Decision Cards          | 4M-B thesis + 4M-C event + 4M-F feedback + 4M-G evaluation                                             | 5C `HorizonDecisionCardsView`                                            |
| ThesisTracker                   | 4M-B thesis + 4M-C event + 4M-F feedback + 4M-G evaluation                                             | 5C `ThesisTrackerView`                                                   |
| Portfolio / Allocation Cockpit  | 4M-D allocation + 4M-F feedback                                                                        | 5D `PortfolioCockpitView` (allocation summary / positions / risk / cash) |
| TradePlan Review                | 4M-D allocation + 4M-F feedback                                                                        | 5D `TradePlanView`                                                       |
| Option Overlay                  | 4M-E option + 4M-F feedback                                                                            | 5D `OptionOverlayView` + `NoTradeReasonView`                             |
| Human Feedback Review           | 4M-F feedback (read-through composition)                                                               | 5C `ReviewNeededBadgeView` + 5D `TradePlanReviewTriggerView`             |
| Catalyst / News / Earnings Mon. | 4M-C event (read-through composition)                                                                  | 5C `MissingEvidenceBadgeView` + `HorizonEvidenceSummaryView`             |
| Macro Dashboard (future/opt.)   | not yet defined                                                                                        | deferred                                                                  |

Read direction:

- All Phase 4M memory layers are **in-memory only**, with no DB / file
  / vector backend.
- All Phase 5A reads go through the read-only `MemoryStoreProtocol` /
  `MemoryQueryResult` boundary.
- The cockpit composer must never read `research/.workflow_state.json`
  directly. The existing live workflow continues to own that file.

---

## 11. Component Boundary Map

Phase 5E enforces a strict component boundary between the existing
runtime and the future cockpit composer:

```
┌──────────────────────────────────────────────────────────────────┐
│  Existing Streamlit App (PRESERVED — Phase 5E does not touch)    │
│                                                                  │
│  pages/1_Overview.py  pages/2_Sector.py  pages/3_Scanner.py      │
│  pages/4_Equity.py    pages/5_Financial.py  pages/6_PriceVolume  │
│  app.py                                                          │
│  lib/llm_orchestrator.py  lib/workflow_state.py                  │
│  lib/valuation.py  lib/technical.py  lib/rotation.py             │
│  lib/data_fetcher.py  lib/cache_manager.py                       │
│  research/.workflow_state.json (live; owned by existing app)     │
└──────────────────────────────────────────────────────────────────┘
                                  │  (no Phase 5E call into this band;
                                  │   live wiring deferred)
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│  Phase 5E — Cockpit UI Planning Boundary (THIS DOC)              │
│                                                                  │
│  • Defines navigation, surfaces, mappings, dependencies.         │
│  • Defines forbidden files, non-goals, guardrails.               │
│  • Defines feature-flag / readiness plan.                        │
│  • Defines safe degraded UI states.                              │
│  • Adds NO Python module.                                        │
│  • Adds NO Streamlit page.                                       │
│  • Adds NO live wiring.                                          │
└──────────────────────────────────────────────────────────────────┘
                                  │  (planning consumes the offline
                                  │   contracts below by reference)
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│  Phase 5A / 5B / 5C / 5D — Offline View-Model Contracts (accepted)│
│                                                                  │
│  lib/reliability/workflow_memory_adapter.py    (5A)              │
│  lib/reliability/phase5_memory_query.py        (5A)              │
│  lib/reliability/phase5_fixtures.py            (5A)              │
│  lib/reliability/company_research_hub.py       (5B)              │
│  lib/reliability/phase5_horizon_views.py       (5C)              │
│  lib/reliability/phase5_portfolio_views.py     (5D)              │
└──────────────────────────────────────────────────────────────────┘
                                  │  (Phase 4M memory consumed by 5A
                                  │   read-only; no DB, no vector store)
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│  Phase 4M Memory Layer (accepted; in-memory Pydantic only)       │
│  research / thesis / event / allocation / option /                │
│  human_feedback / agent_evaluation                                │
└──────────────────────────────────────────────────────────────────┘
```

Boundary rules:

- The cockpit composer (future) reads Phase 5A–5D contracts only.
- The cockpit composer (future) never writes to Phase 4M memory.
- The cockpit composer (future) never reads
  `research/.workflow_state.json`.
- Phase 4A (`lib/reliability/integration_boundary.py`) remains frozen
  and is *not* wired in by Phase 5E.

---

## 12. Feature Flag / Integration Readiness Plan

A later, explicitly approved controlled integration phase would gate
any cockpit rendering behind a feature flag. Phase 5E only describes
the readiness plan; it does not introduce the flag.

Proposed readiness gates (planning-only):

1. **`COCKPIT_PLANNING_ONLY`** — default state at Phase 5E acceptance:
   cockpit surfaces are documented only; no code path renders them; no
   navigation entry exists in the live app.
2. **`COCKPIT_FIXTURE_PREVIEW`** — set during Phase 5G fixture demo
   work: a future fixture-driven preview may render cockpit surfaces
   from deterministic fixtures *outside* the live Streamlit app (for
   example, in a separate offline script). Live wiring remains
   forbidden.
3. **`COCKPIT_SHADOW_VIEW`** — set during a future Phase 5F-derived
   controlled integration phase only: a future surface may render
   cockpit panels in shadow mode (read-only, side-by-side with the
   existing pages, no behavior change). This is **not** authorized in
   Phase 5E.
4. **`COCKPIT_LIVE_VIEW`** — never set during any planning phase. A
   later, explicitly approved controlled integration phase (post-5G /
   5H or later) would gate this. Phase 5E forbids it.

Phase 5E does not implement these flags. They are described here so
later phases can be reviewed against a single, named readiness ladder.

---

## 13. Safe Degraded UI States

Any future cockpit renderer must honor the safe-degraded behavior
already baked into Phase 5B / 5C / 5D contracts:

- Missing snapshot / missing target → return an empty cockpit view
  with `MissingDataWarningView` / `MissingPortfolioDataWarningView`
  surfaces and the always-present `ExecutionSafetyBannerView`. The UI
  renders the warning, not fabricated content.
- Missing equity / financial / price-volume step → degraded panel +
  `MissingDataWarningView` (Phase 5B). The UI renders the missing
  reason.
- Missing thesis for a horizon → `HorizonDecisionCardView(status="missing")`
  with `MissingEvidenceBadgeView` (Phase 5C). The UI renders the
  missing card.
- Missing allocation records → empty positions + `missing_panels`
  includes `"allocation"` and `"trade_plan"` (Phase 5D). The UI renders
  the missing reason.
- Missing option records → empty overlays + `missing_panels` includes
  `"option_overlay"` (Phase 5D). The UI renders the missing reason.
- `no_trade` option state → render `NoTradeReasonView` plus empty
  `OptionRiskRewardView`; do **not** infer a substitute strategy.
- Allocation records lacking `risk_budget_pct` / `portfolio_loss_pct`
  → `RiskBudgetView.has_risk_budget = False`; the UI suppresses the
  risk-budget tile or renders an explicit "not available" state.
- Allocation records lacking `cash_impact` / `projected_cash_pct` →
  `CashImpactView.has_cash_impact = False`; same suppression rule.
- Any review-needed signal (Phase 5C `ReviewNeededBadgeView`, Phase 5D
  `TradePlanReviewTriggerView`) → renders a non-executable review
  prompt; never a "place order" prompt.

The cockpit UI must never:

- Synthesize a thesis or recommendation it did not receive from
  Phase 5B / 5C / 5D.
- Hide a `MissingDataWarningView` / `MissingPortfolioDataWarningView`
  surface.
- Hide the `ExecutionSafetyBannerView`.
- Reinterpret `no_trade` as a tradeable state.

---

## 14. Review-Only / Non-Execution UI Semantics

Every future cockpit surface is **review-only** by construction.

- The `ExecutionSafetyBannerView` is always rendered at the top of
  any cockpit page that surfaces a `PortfolioCockpitView`.
- No surface ships a "Place Order", "Submit Order", "Approve
  Execution", "Send to Broker", or equivalent action.
- No surface renders an `approved_for_execution` toggle, button, or
  status indicator that could be set to True. Phase 5D view-models do
  not declare this field; Phase 5E forbids reintroducing it in any
  future cockpit code.
- No surface renders executable order fields (`order_type`,
  `time_in_force`, `broker_route`, `broker_id`, `account_id`,
  `quantity_to_execute`, `broker_payload`, `order_ticket`,
  `execution_id`, `fill_price`).
- `executed_manually` from Phase 4M-F human feedback is treated as a
  **memory-only label**, surfaced as text or a badge; it is **never**
  rendered as an executable action.
- TradePlan level rows are descriptive ("entry snapshot percentage",
  "stop snapshot percentage") and never executable.
- Any review trigger (`TradePlanReviewTriggerView.review_needed = True`,
  `ReviewNeededBadgeView`) opens a human-review surface, not an order
  surface.

---

## 15. Explicit Forbidden Files List

Phase 5E must **not** modify any of the following files. The list is
identical to Phase 5A / 5B / 5C / 5D forbidden files and is repeated
here for clarity:

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
- `lib/reliability/integration_boundary.py` *(frozen Phase 4A;
  not modified)*
- `.claude/agents/*`
- Existing live prompt files
- Existing Streamlit UI
- Existing news / Finnhub / data-fetch behavior
- Existing live workflow behavior
- `research/.workflow_state.json` *(not read / not modified by
  Phase 5E)*

The Phase 5E lightweight planning-doc test asserts none of these
files were modified by Phase 5E.

---

## 16. Explicit Non-Goals

Phase 5E does **not**:

- Ship any new Streamlit page.
- Modify any existing Streamlit page.
- Modify the existing five-step workflow.
- Modify or import `lib/llm_orchestrator.py`.
- Modify or import `lib/workflow_state.py`.
- Read or write `research/.workflow_state.json`.
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
- Wire Phase 4A `integration_boundary.py` into the live app.
- Implement Phase 5F Shadow Mode integration.
- Implement Phase 5G fixture demo pack.
- Implement Phase 5H Phase 5 closeout.

---

## 17. Guardrails

### 17.1 Documentation-only

Phase 5E is documentation-only. The only file changes performed under
Phase 5E are:

- This new planning document
  (`docs/reliability_phase_5e_cockpit_ui_planning_boundary.md`).
- A lightweight machine-readable planning artifact at
  `docs/ai_dev_state/PHASE_5E_COCKPIT_UI_PLAN.md`.
- A lightweight planning-doc test script at
  `scripts/test_reliability_phase_5e_cockpit_ui_planning.py` that
  asserts (i) required sections exist in this Phase 5E doc,
  (ii) forbidden live runtime files were not touched by Phase 5E,
  and (iii) Phase 5E is documentation/planning-only (no Python UI
  module, no Streamlit import, no live wiring substrings).
- Phase 5D's minor-suggestion cleanup of one unused import
  (`model_validator`) in `lib/reliability/phase5_portfolio_views.py`,
  performed in the same pass.
- State-file reconciliation in `docs/ai_dev_state/PROJECT_STATE.md`
  and `docs/ai_dev_state/CURRENT_TASK.md`.

### 17.2 `approved_for_execution` invariant

- No Phase 5E artifact declares an `approved_for_execution` field on
  any view, surface, or component.
- The underlying Phase 4M memory records reject
  `approved_for_execution=True` at their respective model layers.
- The Phase 5A `MemoryQueryResult` enforces
  `approved_for_execution=False` on every returned result.
- Phase 5E's lightweight test asserts the planning doc itself does
  not positively authorize `approved_for_execution=True` anywhere
  (the doc's policy text reads `approved_for_execution=False` or
  "remains False / absent"; any mention of
  `approved_for_execution = True` appears only inside an explicit
  forbidden / non-goal / guardrail context).

### 17.3 No executable order fields

- Phase 5E does not introduce `order_type`, `time_in_force`,
  `broker_route`, `broker_id`, `account_id`, `quantity_to_execute`,
  `broker_payload`, `order_ticket`, `execution_id`, or `fill_price`
  in any artifact.
- The Phase 5E lightweight test asserts the doc does not authorize
  any of these fields in a future renderer.

### 17.4 No live integration

- Phase 5E adds no Python module that imports `streamlit`,
  `lib.llm_orchestrator`, `lib.workflow_state`, `lib.data_fetcher`,
  `lib.valuation`, `lib.technical`, `lib.rotation`, `lib.cache_manager`,
  the Anthropic SDK, or any HTTP client.
- Phase 5E does not modify `lib/reliability/integration_boundary.py`
  (Phase 4A, frozen).
- The Phase 5E lightweight test asserts:
  - the planning doc does not import Streamlit or any forbidden live
    runtime module,
  - the planning doc does not authorize wiring Phase 4A into the live
    app,
  - no Phase 5E artifact has been added under `pages/`,
  - no Phase 5E artifact has been added that imports `streamlit`.

### 17.5 Phase 4A guardrail

Phase 4A (`lib/reliability/integration_boundary.py`) remains accepted
as early integration infrastructure and is **frozen**. Phase 5E may
*describe* shadow-mode planning concepts that would later consume
Phase 4A's `DISABLED / SHADOW / ENFORCED` mode framework, but only as
a *planning reference* for Phase 5F. Phase 5E itself does not wire,
extend, or modify Phase 4A.

### 17.6 No persistence

Phase 5E does **not** introduce:

- a database (SQL or NoSQL),
- a file-based persistence layer for memory records,
- a vector store / embedding pipeline / similarity index,
- a workflow_state writer or reader,
- a broker connector / order router.

The Phase 4M memory layer remains in-memory only; the Phase 5A query
boundary remains fixture-friendly only.

---

## 18. Acceptance Criteria

Phase 5E is accepted when:

1. `docs/reliability_phase_5e_cockpit_ui_planning_boundary.md` (this
   file) exists and contains the following required sections:
   Purpose; Relationship to Roadmap v4 Phase 5 Investment Cockpit;
   Relationship to the Original README Streamlit App; Explicit
   Statement — This Is Not UI Implementation; Existing Pages To
   Preserve; Proposed Future Cockpit Navigation Structure; Proposed
   Future Cockpit Surfaces; Mapping From Existing Pages to Future
   Cockpit Surfaces; Mapping From Phase 5A–5D View-Models to Future
   UI Components; Data Dependency Matrix; Component Boundary Map;
   Feature Flag / Integration Readiness Plan; Safe Degraded UI States;
   Review-Only / Non-Execution UI Semantics; Explicit Forbidden Files
   List; Explicit Non-Goals; Guardrails; Acceptance Criteria; Future
   Phase 5F Dependency.
2. `docs/ai_dev_state/PHASE_5E_COCKPIT_UI_PLAN.md` exists with a
   machine-readable / table-friendly summary of the navigation,
   surfaces, mappings, and forbidden-file list.
3. `scripts/test_reliability_phase_5e_cockpit_ui_planning.py` exists
   and passes with assertions covering: required-section existence in
   this Phase 5E doc; forbidden-runtime-files-not-modified by Phase 5E
   (relative to a previous accepted Phase 5D state); planning-only
   constraints (no new Python module added under `lib/reliability/`
   for Phase 5E; no Streamlit import added; no broker / order /
   execution substrings authorized in the doc; the doc does not
   positively authorize `approved_for_execution=True`).
4. The Phase 5D minor-suggestion cleanup (remove unused
   `model_validator` import in `lib/reliability/phase5_portfolio_views.py`)
   is applied. The Phase 5D test suite continues to pass at 212/212.
5. `docs/ai_dev_state/PROJECT_STATE.md` and
   `docs/ai_dev_state/CURRENT_TASK.md` record Phase 5D as **Accepted**
   and Phase 5E as **Implemented — Awaiting Codex Review**. Phase 5F
   is **not** claimed to have started.
6. No live runtime file was modified by Phase 5E.
7. No database, file persistence layer, vector store, external API
   call, broker, order, or execution path was introduced by Phase 5E.
8. `approved_for_execution` remains `False` (or absent) everywhere it
   appears.

---

## 19. Future Phase 5F Dependency

Phase 5F (Shadow Mode Integration Boundary Planning) consumes
Phase 5E as follows:

- Phase 5F planning will describe how the existing five-step workflow
  could be observed *in shadow mode* by the Phase 4A integration
  boundary (`DISABLED / SHADOW / ENFORCED`), without affecting the
  existing workflow's outputs.
- Phase 5F will reference the navigation and surfaces defined in
  Phase 5E only to identify *where* a shadow-mode badge / comparison
  panel could surface — not to authorize live wiring.
- Phase 5F must not bypass Phase 5E's execution-safety boundary. No
  `approved_for_execution` field may be reintroduced. No executable
  order field may be added. No broker / order / execution path may be
  introduced. Phase 4A remains frozen.
- Phase 5F is itself documentation-only. Live wiring is deferred to a
  later, explicitly approved controlled integration phase
  (post-Phase 5G / 5H or later).

Phase 5G (Fixture Demo Pack Based on Original App Flow) and Phase 5H
(Phase 5 Cockpit Boundary Closeout) build on Phase 5B / 5C / 5D /
5E / 5F together; none of them adds live wiring.
