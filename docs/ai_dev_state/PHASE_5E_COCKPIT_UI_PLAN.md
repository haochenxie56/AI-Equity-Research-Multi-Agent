# Phase 5E — Cockpit UI Planning Boundary (state artifact)

**Last updated**: 2026-05-27
**Status**: Implemented — Awaiting Codex Review (planning-only).
**Companion document**: `docs/reliability_phase_5e_cockpit_ui_planning_boundary.md`
**Type**: Documentation only. No Python UI module. No Streamlit page.
No live wiring. No DB / vector store / persistence / external API /
broker / order / execution.

> Phase 5E does not implement a UI. It defines the planning boundary
> for a future Investment Cockpit UI on top of the existing
> README-based Streamlit app. The existing six pages (Overview /
> Sector / Scanner / Equity / Financial / PriceVolume) and the
> existing five-step AI workflow are preserved verbatim. Live wiring
> is deferred to a later, explicitly approved controlled integration
> phase.

---

## Preserved existing Streamlit pages

| Existing page  | File                       | Preservation rule |
|----------------|----------------------------|-------------------|
| Overview       | `pages/1_Overview.py`      | Untouched         |
| Sector         | `pages/2_Sector.py`        | Untouched         |
| Scanner        | `pages/3_Scanner.py`       | Untouched         |
| Equity         | `pages/4_Equity.py`        | Untouched         |
| Financial      | `pages/5_Financial.py`     | Untouched         |
| PriceVolume    | `pages/6_PriceVolume.py`   | Untouched         |

Existing five-step AI workflow:
`Sector Analysis → Stock Scanner → Equity Research → Financial
Analysis → PriceVolume Analysis → Synthesis`, owned by
`lib/llm_orchestrator.py` and persisted via `lib/workflow_state.py`
to `research/.workflow_state.json`. **Preserved without modification.**

---

## Proposed future cockpit surfaces

| # | Future surface                          | Upstream Phase 5 contract                                                                 |
|---|------------------------------------------|-------------------------------------------------------------------------------------------|
| 1 | Investment Cockpit (home)               | Phase 5A `MemoryQueryResult` + Phase 5B/5C/5D headers + review-needed badges              |
| 2 | Company Research Hub                    | Phase 5B `CompanyResearchHubView`                                                          |
| 3 | Horizon Decision Cards                  | Phase 5C `HorizonDecisionCardsView` (canonical short → medium → long)                     |
| 4 | Watchlist + ThesisTracker               | Phase 5C `ThesisTrackerView`                                                              |
| 5 | Portfolio / Allocation Cockpit          | Phase 5D `PortfolioCockpitView`                                                            |
| 6 | TradePlan Review                        | Phase 5D `TradePlanView` (descriptive `entry → add → trim → stop → target → review`)      |
| 7 | Option Overlay                          | Phase 5D `OptionOverlayView` (+ `NoTradeReasonView` when `no_trade`)                       |
| 8 | Human Feedback Review                   | Phase 5C `ReviewNeededBadgeView` + Phase 5D `TradePlanReviewTriggerView`                  |
| 9 | Catalyst / News / Earnings Monitor      | Phase 5C `MissingEvidenceBadgeView` + `HorizonEvidenceSummaryView`                        |
| 10| Macro Dashboard (future / optional)     | Deferred — no Phase 5* macro view-model exists yet                                         |

All surfaces are sibling navigation entries, not edits to the
existing six pages.

---

## Mapping from existing pages to future cockpit surfaces

| Existing page | Sibling cockpit surface(s)                       | Relationship                                                                |
|---------------|---------------------------------------------------|-----------------------------------------------------------------------------|
| Overview      | Investment Cockpit home                          | Parallel landing surface; Overview workflow untouched.                       |
| Sector        | Macro Dashboard (future / optional)              | Deferred; Sector page continues to own macro/rotation today.                 |
| Scanner       | Investment Cockpit home (candidate summary)      | Cockpit home surfaces recent scan targets; Scanner unchanged.                |
| Equity        | Company Research Hub (Equity Research panel)     | Reuses equity-research artifact via Phase 5B; Equity page preserved.         |
| Financial     | Company Research Hub (Financial Valuation panel) | Reuses financial artifact via Phase 5B; Financial page preserved.            |
| PriceVolume   | Company Research Hub (PriceVolume Timing panel)  | Reuses price/volume artifact via Phase 5B; PriceVolume page preserved.       |

---

## Phase 5A–5D view-model → future UI component bindings

| Future UI component                | Upstream Phase 5 contract                                                              |
|------------------------------------|-----------------------------------------------------------------------------------------|
| Cockpit home — recent-run tile      | Phase 5A `MemoryQueryResult`; Phase 5B `CompanyResearchHubView` header                   |
| Cockpit home — review-needed badge  | Phase 5C `ReviewNeededBadgeView`; Phase 5D `TradePlanReviewTriggerView`                  |
| Company Research Hub identity       | Phase 5B `CompanyIdentityView`                                                           |
| Equity Research panel               | Phase 5B `EquityResearchPanelView`                                                       |
| Financial Valuation panel           | Phase 5B `FinancialValuationPanelView`                                                   |
| PriceVolume Timing panel            | Phase 5B `PriceVolumeTimingPanelView`                                                    |
| Source Workflow panel               | Phase 5B `SourceWorkflowPanelView`                                                       |
| Evidence Coverage panel             | Phase 5B `EvidenceCoveragePanelView`                                                     |
| Validation Status panel             | Phase 5B `ValidationStatusPanelView`                                                     |
| Horizon decision card (short)       | Phase 5C `HorizonDecisionCardView(horizon="short")`                                      |
| Horizon decision card (medium)      | Phase 5C `HorizonDecisionCardView(horizon="medium")`                                     |
| Horizon decision card (long)        | Phase 5C `HorizonDecisionCardView(horizon="long")`                                       |
| Invalidation trigger row            | Phase 5C `InvalidationTriggerView`                                                       |
| Missing-evidence badge              | Phase 5C `MissingEvidenceBadgeView`                                                      |
| ThesisTracker table row             | Phase 5C `ThesisTrackerRowView`                                                          |
| Allocation summary                  | Phase 5D `AllocationSummaryView`                                                         |
| Position allocation row             | Phase 5D `PositionAllocationView`                                                        |
| Risk budget surface                 | Phase 5D `RiskBudgetView` (only when present)                                             |
| Cash impact surface                 | Phase 5D `CashImpactView` (only when present)                                             |
| TradePlan card                      | Phase 5D `TradePlanView`                                                                  |
| TradePlan level row                 | Phase 5D `TradePlanLevelView` (descriptive only)                                          |
| TradePlan review trigger            | Phase 5D `TradePlanReviewTriggerView`                                                     |
| Option overlay card                 | Phase 5D `OptionOverlayView`                                                              |
| Option strategy summary             | Phase 5D `OptionStrategySummaryView`                                                      |
| Option risk/reward                  | Phase 5D `OptionRiskRewardView`                                                           |
| Option liquidity warning            | Phase 5D `OptionLiquidityWarningView`                                                     |
| Option event-risk warning           | Phase 5D `OptionEventRiskWarningView`                                                     |
| No-trade reason surface             | Phase 5D `NoTradeReasonView`                                                              |
| Execution safety banner             | Phase 5D `ExecutionSafetyBannerView` (always present)                                     |
| Missing-data warning                | Phase 5B `MissingDataWarningView`; Phase 5D `MissingPortfolioDataWarningView`             |

---

## Data dependency matrix (future cockpit)

| Future surface                  | Phase 4M memory dependencies                                                                |
|---------------------------------|----------------------------------------------------------------------------------------------|
| Cockpit home                    | 4M-A run + 4M-B thesis + 4M-D allocation + 4M-E option + 4M-F feedback + 4M-G evaluation     |
| Company Research Hub            | 4M-A research run                                                                            |
| Horizon Decision Cards          | 4M-B thesis + 4M-C event + 4M-F feedback + 4M-G evaluation                                   |
| ThesisTracker                   | 4M-B thesis + 4M-C event + 4M-F feedback + 4M-G evaluation                                   |
| Portfolio / Allocation Cockpit  | 4M-D allocation + 4M-F feedback                                                              |
| TradePlan Review                | 4M-D allocation + 4M-F feedback                                                              |
| Option Overlay                  | 4M-E option + 4M-F feedback                                                                  |
| Human Feedback Review           | 4M-F feedback (composed via 5C / 5D contracts)                                               |
| Catalyst / News / Earnings Mon. | 4M-C event (composed via 5C contracts)                                                       |
| Macro Dashboard (future/opt.)   | Not yet defined                                                                              |

All memory reads go through the Phase 5A read-only
`MemoryStoreProtocol` / `MemoryQueryResult`. No live workflow_state
read; no DB; no vector store.

---

## Feature flag / integration readiness ladder

| Flag (planning only)          | Effect                                                                                         | Phase 5E status   |
|-------------------------------|-------------------------------------------------------------------------------------------------|--------------------|
| `COCKPIT_PLANNING_ONLY`        | Documented only; no code path renders the cockpit; no nav entry in the live app.                | Default            |
| `COCKPIT_FIXTURE_PREVIEW`      | Future fixture-driven preview outside the live app (Phase 5G).                                  | Not authorized yet |
| `COCKPIT_SHADOW_VIEW`          | Future shadow-mode rendering side-by-side with existing pages (Phase 5F+).                      | Not authorized yet |
| `COCKPIT_LIVE_VIEW`            | Live cockpit rendering — requires later, explicitly approved controlled integration phase.     | **Forbidden**      |

Phase 5E does not implement any of these flags.

---

## Safe degraded UI states (inherited from Phase 5B / 5C / 5D)

- Missing snapshot / target → empty cockpit + `MissingDataWarningView`
  / `MissingPortfolioDataWarningView` + `ExecutionSafetyBannerView`.
- Missing equity / financial / price-volume step → degraded Phase 5B
  panel + warning.
- Missing thesis for a horizon → `HorizonDecisionCardView(status="missing")`
  + missing-evidence badge.
- Missing allocation records → `missing_panels` includes
  `"allocation"` and `"trade_plan"`.
- Missing option records → `missing_panels` includes
  `"option_overlay"`.
- `no_trade` option state → populated `NoTradeReasonView`, empty
  `OptionRiskRewardView`; no substitute strategy.
- Allocation records lacking risk_budget fields →
  `RiskBudgetView.has_risk_budget = False`.
- Allocation records lacking cash fields →
  `CashImpactView.has_cash_impact = False`.
- Any review-needed signal → non-executable review prompt only.

The UI must never hide a missing-data warning or the execution-safety
banner, must never invent content, and must never reinterpret
`no_trade` as a tradeable state.

---

## Review-only / non-execution UI semantics

- `ExecutionSafetyBannerView` always rendered.
- No "Place Order" / "Submit Order" / "Approve Execution" /
  "Send to Broker" surface.
- No `approved_for_execution` toggle / button / status indicator.
- No executable order fields surfaced (`order_type`, `time_in_force`,
  `broker_route`, `broker_id`, `account_id`, `quantity_to_execute`,
  `broker_payload`, `order_ticket`, `execution_id`, `fill_price`).
- `executed_manually` from human-feedback memory is rendered as a
  memory-only label, never as an executable action.
- TradePlan level rows are descriptive, not executable.

---

## Forbidden files (Phase 5E does not modify any of these)

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
- `lib/cache_manager.py`
- `lib/reliability/integration_boundary.py` (frozen Phase 4A)
- `.claude/agents/*`
- Existing live prompt files
- Existing Streamlit UI
- Existing news / Finnhub / data-fetch behavior
- Existing live workflow behavior
- `research/.workflow_state.json`

The Phase 5E lightweight test asserts none of these forbidden live
runtime files were modified by Phase 5E.

---

## Acceptance criteria summary

1. `docs/reliability_phase_5e_cockpit_ui_planning_boundary.md` exists
   with the required sections.
2. This state artifact
   (`docs/ai_dev_state/PHASE_5E_COCKPIT_UI_PLAN.md`) exists.
3. `scripts/test_reliability_phase_5e_cockpit_ui_planning.py` exists
   and passes.
4. Phase 5D minor-suggestion cleanup applied
   (`model_validator` removed from
   `lib/reliability/phase5_portfolio_views.py`); Phase 5D test suite
   still passes 212/212.
5. `PROJECT_STATE.md` and `CURRENT_TASK.md` mark Phase 5D as
   **Accepted** and Phase 5E as **Implemented — Awaiting Codex
   Review**, without claiming Phase 5F has started.
6. No live runtime file modified.
7. No DB / vector store / persistence / external API / broker / order
   / execution introduced.
8. `approved_for_execution` remains `False` or absent everywhere.

---

## Recommended next step

**Codex review of Phase 5E.** Phase 5F (Shadow Mode Integration
Boundary Planning) must not be started until Phase 5E is accepted.
