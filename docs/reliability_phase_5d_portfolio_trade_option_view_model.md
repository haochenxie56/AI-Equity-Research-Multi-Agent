# Reliability Phase 5D — Portfolio / TradePlan / Option Overlay ViewModel Contract

**Date**: 2026-05-27
**Status**: Accepted.
**Type**: Read-only deterministic cockpit-ready view-model contract layer
sitting on top of Phase 4M-D allocation decision memory, Phase 4M-E option
trade plan memory, and the Phase 5A fixture-backed memory query contract.
**Module(s) added**:

- `lib/reliability/phase5_portfolio_views.py`

**Test script added**: `scripts/test_reliability_phase_5d_portfolio_trade_option_views.py`
(212/212 passing).

> **Phase 5D makes no live runtime changes.** It does not modify `app.py`,
> `pages/*`, `lib/llm_orchestrator.py`, `lib/workflow_state.py`,
> `lib/valuation.py`, `lib/technical.py`, `lib/rotation.py`,
> `lib/data_fetcher.py`, `lib/cache_manager.py`, `.claude/agents/*`, the
> existing Streamlit UI, the existing news/Finnhub/data-fetch behavior, or
> the live workflow state JSON file. Phase 4A
> (`lib/reliability/integration_boundary.py`) remains frozen and is **not**
> wired in. No database, file store, vector store, embedding pipeline, live
> Anthropic SDK call, HTTP request, broker/order/execution path, or
> brokerage account ID is introduced. `approved_for_execution` is not
> exposed by any Phase 5D view model.

---

## 1. Purpose

Phase 5D is the **fourth overlay contract** for Phase 5 (after Phase 5A's
memory query contract, Phase 5B's Company Research Hub view, and Phase 5C's
Horizon Decision Cards + ThesisTracker view). It is the third view-model
layer.

Phase 5D defines deterministic Pydantic projections of:

1. **Portfolio / Allocation Cockpit** — aggregate allocation summary, per-
   record position allocation, risk budget, cash impact (each populated
   only when the underlying Phase 4M-D records carry the corresponding
   fields).
2. **TradePlan card representation** — one trade-plan card per allocation
   memory record, enumerating descriptive entry / add / trim / stop /
   target / review slots sourced from the underlying allocation snapshot.
   Phase 5D never converts a trade-plan card into an executable order.
3. **Option Overlay representation** — one overlay per option trade plan
   memory record, surfacing strategy summary, risk/reward, liquidity /
   event-risk warnings, and an explicit `NoTradeReasonView` when the
   underlying record reports `no_trade`.

Phase 5D does **not** ship a UI, does **not** read live workflow state,
does **not** call an LLM, does **not** generate orders, and does **not**
authorize execution. It is a *contract layer only* — a stable Pydantic
shape Phase 5E (cockpit UI planning boundary) and later phases can
target without coupling to Streamlit, broker APIs, or live market data.

---

## 2. Relationship to Roadmap v4

Roadmap v4 calls out a **Portfolio / Allocation Cockpit**, a **TradePlan
UI**, and an **Option Overlay UI** as cockpit-side deliverables that sit
on top of the existing five-step workflow's memory trail. Phase 5D is the
**schema-only contract layer** for those deliverables. It defines:

- the deterministic, fixture-friendly Pydantic shape future renderers can
  target without coupling to Streamlit or a live workflow run;
- per-target aggregate views (positions, allocation summary, risk
  budget, cash impact);
- per-record trade-plan and option-overlay views;
- the safety boundary every cockpit renderer is expected to honor
  (`ExecutionSafetyBannerView`);
- the safe-degraded behavior when allocation / option / memory data is
  missing.

No rendering, no live data, no decisions are produced here. Phase 5E
(cockpit UI planning boundary) and beyond consume Phase 5D; they remain
pending.

---

## 3. Relationship to the Original README App

The README documents the existing Overview / Sector / Scanner / Equity /
Financial / PriceVolume Streamlit pages plus the five-step Overview
synthesis. The original app produces analysis artifacts but does **not**
ship a portfolio / trade-plan / option-overlay cockpit panel today.
Phase 5D provides the deterministic Pydantic contract a future cockpit
could render *next to* those pages without touching them.

Concretely, `lib/reliability/phase5_portfolio_views.py`:

- does not import `streamlit`,
- does not import any `pages/*` module,
- does not import `app.py`,
- does not import `lib/llm_orchestrator.py`,
- does not import `lib/workflow_state.py`,
- does not read `research/.workflow_state.json`,
- does not import any broker / brokerage / execution module,
- exposes only Pydantic models and deterministic builder functions.

---

## 4. Relationship to Phase 4M Memory

Phase 5D consumes Phase 4M memory records by reference; it does not
redefine or replace any of them:

| Phase 4M record                                  | Phase 5D usage                                                      |
|--------------------------------------------------|---------------------------------------------------------------------|
| `AllocationDecisionMemoryRecord` (Phase 4M-D)    | populates positions, allocation summary, risk budget, cash impact, trade-plan card |
| `OptionTradePlanMemoryRecord` (Phase 4M-E)       | populates option overlay; `no_trade` preserved as first-class state |
| `HumanFeedbackMemoryRecord` (Phase 4M-F)         | surfaces review reasons on positions, trade plans, and overlays     |

Phase 4M-A / 4M-B / 4M-C / 4M-G records are not consumed directly by
Phase 5D (they are consumed by Phase 5B for the Company Research Hub
identity / financial panel and by Phase 5C for the horizon decision cards
and ThesisTracker).

---

## 5. Relationship to Phase 5A Query Contract

Phase 5D consumes Phase 5A as follows:

| Phase 5A input            | How Phase 5D uses it                                       |
|---------------------------|------------------------------------------------------------|
| `MemoryStoreProtocol`     | runs a `MemoryQueryByTicker(target=…)` when no explicit query result is supplied |
| `MemoryQueryResult`       | direct input when callers pre-compute results; supersedes the store |

`build_portfolio_cockpit_view()` accepts:

- `target` (required, non-whitespace)
- `memory_store` (optional)
- `memory_query_result` (optional, takes precedence over store)

When both `memory_store` and `memory_query_result` are absent, the builder
still completes — every sub-view yields a safe empty value and the top-
level `warnings` / `missing_data` list explains that no memory was
supplied.

---

## 6. Optional Relationship to Phase 5C Horizon / Thesis Context

Phase 5D does **not** import Phase 5C's `phase5_horizon_views` module. A
cockpit composing both views can call them side-by-side using the same
`target` and the same `MemoryStoreProtocol`. The Phase 5C horizon decision
cards and the Phase 5D portfolio cockpit both honor the same Phase 5A
invariants (`approved_for_execution` rejected at the Phase 5A model layer;
deterministic IDs; no live wiring), so they are safe to render together
without cross-coupling.

If a future cockpit needs per-horizon context inside the trade plan or
option overlay (for example, to mark a TradePlanView card with the same
horizon's review-needed signal), the cockpit composer can call Phase 5C
builders alongside Phase 5D builders and join on `(target, horizon)` /
`(target, related_thesis_id)`.

---

## 7. View Model Contracts

All view models live in `lib/reliability/phase5_portfolio_views.py` and
use `pydantic.BaseModel` with `model_config = ConfigDict(extra="forbid")`.
**None of them declares `approved_for_execution`.** None declares any
executable order field (`order_type`, `time_in_force`, `broker_route`,
`account_id`, `quantity_to_execute`, `broker_payload`, etc.).

### 7.1 Safety / missing views

| View                              | Purpose                                                       |
|-----------------------------------|---------------------------------------------------------------|
| `ExecutionSafetyBannerView`       | always-present non-executable banner with required human review |
| `MissingPortfolioDataWarningView` | enumerates missing portfolio sub-views                         |
| `NoTradeReasonView`               | first-class projection of an option `no_trade` state           |

### 7.2 Portfolio / allocation views

| View                          | Purpose                                                                       |
|-------------------------------|-------------------------------------------------------------------------------|
| `AllocationSummaryView`       | aggregate counts by action / status / review_status                            |
| `PositionAllocationView`      | one allocation memory record projection (action / status / snapshot fields)    |
| `RiskBudgetView`              | aggregate risk projection (only populated when records carry risk fields)      |
| `CashImpactView`              | aggregate cash projection (only populated when records carry cash fields)      |

### 7.3 Trade plan views

| View                          | Purpose                                                              |
|-------------------------------|----------------------------------------------------------------------|
| `TradePlanView`               | one trade-plan card per allocation memory record                     |
| `TradePlanLevelView`          | descriptive entry / add / trim / stop / target / review slot         |
| `TradePlanReviewTriggerView`  | review-needed flag + reasons from status / review_status / human feedback |

### 7.4 Option overlay views

| View                          | Purpose                                                              |
|-------------------------------|----------------------------------------------------------------------|
| `OptionOverlayView`           | one option-overlay projection per option trade plan memory record    |
| `OptionStrategySummaryView`   | decision / strategy_type / expiration / contracts / risk_level       |
| `OptionRiskRewardView`        | max_loss / max_gain / breakeven / IV / underlying price / cash / RR ratio |
| `OptionLiquidityWarningView`  | surfaces upstream liquidity warnings                                  |
| `OptionEventRiskWarningView`  | surfaces upstream event-risk warnings                                 |

### 7.5 Aggregate view

| View                          | Purpose                                                              |
|-------------------------------|----------------------------------------------------------------------|
| `PortfolioCockpitView`        | top-level aggregate of all of the above + execution safety banner    |

### 7.6 Literal aliases / constants

- `PortfolioDataSource` — `"phase4m_allocation_memory" | "phase4m_option_trade_memory" | "phase4m_human_feedback_memory" | "memory_query_result" | "absent"`.
- `TradePlanLevelKind` — `"entry" | "add" | "trim" | "stop" | "target" | "review"`.
- `TRADE_PLAN_LEVEL_KINDS` — the canonical tuple.
- `MissingPortfolioPanel` — labels the missing sub-views.
- `OptionOverlayState` — `"option" | "stock" | "no_trade" | "wait" | "unknown" | "missing"`.

---

## 8. Portfolio / Allocation Semantics

- `PositionAllocationView` carries the underlying allocation memory id,
  the bounded snapshot fields (`target_allocation_pct`,
  `actual_allocation_pct`, `min_allocation_pct`, `max_allocation_pct`,
  `cash_pct`, `cash_impact`, `projected_cash_pct`, `portfolio_loss_pct`,
  `risk_budget_pct`), the risk level, action, status, and review status
  exactly as the underlying record reports them. Phase 5D **never**
  fabricates allocation numbers or live portfolio values.
- `AllocationSummaryView` aggregates counts by action / status /
  review_status. `has_any_records` is True only when at least one
  allocation record was inspected.
- `RiskBudgetView.has_risk_budget` is True only when at least one record
  contributed `risk_budget_pct` or `portfolio_loss_pct`. Otherwise the
  view returns empty aggregates and a warning explains that the underlying
  records did not carry risk fields.
- `CashImpactView.has_cash_impact` is True only when at least one record
  contributed `cash_impact` or `projected_cash_pct`. Otherwise the view
  returns empty aggregates and a warning explains the absence.
- Phase 5D does **not** read brokerage account positions, broker portfolio
  files, or any live portfolio data. The only inputs are Phase 4M-D
  allocation memory records supplied via the Phase 5A query layer.
- Phase 5D does **not** create executable allocation instructions: no
  order type, no time-in-force, no broker route, no account ID, no
  executable quantity is surfaced anywhere.

---

## 9. TradePlan Semantics

- `TradePlanView` projects one allocation memory record into a cockpit
  trade-plan card.
- `TradePlanLevelView` enumerates a fixed set of six descriptive slots
  (`entry`, `add`, `trim`, `stop`, `target`, `review`). Slot values come
  *only* from the underlying allocation snapshot's bounded percentage
  fields. The label is descriptive (e.g. "Snapshot target allocation
  percentage; descriptive only, not an executable order"). Phase 5D
  **does not** convert trade-plan memory into executable orders. It does
  not introduce broker types, order types, time-in-force, account IDs,
  routes, or quantities to execute.
- `TradePlanReviewTriggerView` surfaces the underlying allocation record's
  status / review_status / review_trigger plus any human-feedback record
  that flags review for the target. `review_needed` is True when any of
  the underlying signals fires.
- If the underlying record carries no levels for a particular kind, the
  corresponding `TradePlanLevelView.pct` and `value` remain `None`. Phase
  5D never fabricates levels.
- When no allocation memory records exist for a target, `TradePlanView`
  list is empty and `MissingPortfolioDataWarningView.missing_panels`
  includes `"trade_plan"`.
- The execution safety banner explicitly states the view is
  non-executable and review-only.

---

## 10. Option Overlay Semantics

- `OptionOverlayView` projects one Phase 4M-E option trade plan memory
  record into a cockpit overlay.
- `OptionStrategySummaryView` carries `decision`, `strategy_type`,
  `expiration`, `contracts`, `planned_exit_rule`, `actual_exit_reason`,
  and `risk_level` exactly as the underlying snapshot reports them.
- `OptionRiskRewardView` carries `max_loss`, `max_gain`, `breakeven`,
  `entry_iv`, `exit_iv`, `entry_underlying_price`, `exit_underlying_price`,
  `cash_required`, and `risk_reward_ratio`. Phase 5D **does not** compute
  live Greeks, IV rank, margin requirements, assignment risk, probability
  of profit, or any live market quantity.
- `OptionLiquidityWarningView` and `OptionEventRiskWarningView` surface
  only upstream warnings (filtered by substring); Phase 5D does not
  compute live liquidity scores or live event-risk assessments.
- Phase 5D **never** creates executable option orders. No leg / strike /
  side / quantity / broker route / account ID / execution authorization
  is introduced.

---

## 11. `no_trade` Semantics

`no_trade` is a **first-class valid state** for option overlays.

- When the underlying option trade plan memory record reports
  `decision="no_trade"`, `strategy_type="no_trade"`, or
  `outcome="no_trade"`:
  - `OptionOverlayView.state = "no_trade"`,
  - `OptionOverlayView.is_no_trade = True`,
  - `OptionOverlayView.no_trade_reason` is a populated `NoTradeReasonView`
    referencing the underlying `option_trade_memory_id`,
  - `OptionRiskRewardView` is **empty** — `max_loss`, `max_gain`,
    `breakeven`, `risk_reward_ratio`, etc. are all `None`.
- Phase 5D **never** infers a substitute strategy. If the record says
  `no_trade`, the overlay says `no_trade`. The cockpit can render the
  reason; no alternative trade is authorized.
- `NoTradeReasonView` carries the underlying record's `rationale`,
  `review_trigger`, and `source_record_id`. It does not invent a reason
  when none is supplied.

---

## 12. Execution Safety Boundary

Phase 5D enforces a strict execution-safety boundary at every level:

1. **No `approved_for_execution` field** is declared on any Phase 5D
   view model. The aggregate `PortfolioCockpitView` does not surface this
   field. Per-record views (`PositionAllocationView`, `TradePlanView`,
   `OptionOverlayView`) also do not declare it. The underlying Phase 4M
   records already enforce `approved_for_execution=False` at their model
   layers; Phase 5D inherits the invariant by construction.
2. **No executable order fields.** No view declares `order_type`,
   `time_in_force`, `broker_route`, `broker_id`, `account_id`,
   `quantity_to_execute`, `broker_payload`, `order_ticket`,
   `execution_id`, or `fill_price`. The test suite enforces this both at
   the field-level (`model_fields`) and at the source-substring level.
3. **`ExecutionSafetyBannerView` is always present** on a
   `PortfolioCockpitView`. The banner explicitly states the view is
   non-executable / review-only and that human review is required.
4. **No live wiring.** Phase 5D does not call broker APIs, does not read
   brokerage account positions, does not subscribe to live market data,
   and does not import any live workflow module.

---

## 13. Missing-Evidence / Degraded States

Phase 5D never raises when memory is incomplete. It returns safe
degraded views instead:

| Missing input                                  | Behavior                                                                  |
|-----------------------------------------------|---------------------------------------------------------------------------|
| no `memory_store` and no `memory_query_result`| every sub-view returns empty; `missing_panels` includes `"memory"`        |
| no allocation records for the target          | positions / trade_plans empty; `missing_panels` includes `"allocation"` and `"trade_plan"` |
| no option trade records for the target        | overlays empty; `missing_panels` includes `"option_overlay"`              |
| allocation records lack risk_budget fields    | `RiskBudgetView.has_risk_budget=False`; warning explains                   |
| allocation records lack cash fields           | `CashImpactView.has_cash_impact=False`; warning explains                   |
| no human feedback records for the target      | `missing_panels` includes `"human_feedback"`; review reasons from feedback are unavailable |
| missing ticker / unknown target               | safe empty view; no hallucinated content                                   |

The aggregate `PortfolioCockpitView` always carries the execution safety
banner. Missing data is **always** surfaced via warnings; nothing is
silently fabricated.

The builder rejects only one input: empty / whitespace-only `target`
(`ValueError`). Every other safe degradation is surfaced as warnings.

---

## 14. Evidence / Validation Handling

- `PositionAllocationView` surfaces `evidence_ids`, `artifact_refs`, and
  `source_ids` exactly as the underlying allocation record carries them.
- `TradePlanView` carries `related_evidence_ids` and
  `related_artifact_refs` from the underlying allocation record.
- `OptionOverlayView` carries `related_evidence_ids` and
  `related_artifact_refs` from the underlying option trade plan record.
- `AllocationSummaryView.has_any_records` is True only when at least one
  allocation record was inspected. The view does not claim a clean
  validation status; aggregate `MissingPortfolioDataWarningView` covers
  the gap.
- Validation never fabricates a clean status: when no records exist for
  a panel, the corresponding flag (`has_any_records`,
  `has_risk_budget`, `has_cash_impact`) remains False.
- Phase 5D does not declare decision readiness anywhere. The cockpit
  banner makes the boundary explicit.

---

## 15. Non-Goals

Phase 5D does **not**:

- Ship any new UI page.
- Modify any existing page or workflow.
- Add SQL, NoSQL, file, or vector store persistence.
- Embed records or build a similarity index.
- Call the Claude API, Anthropic SDK, or any HTTP service.
- Mutate `workflow_state`, agent definitions, or prompts.
- Route orders, place trades, or set `approved_for_execution = True`.
- Wire Phase 4A `integration_boundary.py` into the live app.
- Read the live workflow state JSON file.
- Read brokerage account positions or real portfolio files.
- Create executable allocation instructions, broker payloads, or order
  tickets.
- Calculate live option Greeks, IV rank, margin requirements, assignment
  risk, or probability of profit.
- Generate a cockpit UI (deferred to Phase 5E).
- Implement shadow-mode integration (deferred to Phase 5F planning).

---

## 16. Guardrails

### 16.1 Forbidden files (unchanged across Phase 5)

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

### 16.2 `approved_for_execution` invariant

- No Phase 5D view model declares `approved_for_execution`.
- The underlying Phase 4M memory records reject
  `approved_for_execution=True` at their respective model layers.
- The Phase 5A `MemoryQueryResult` enforces
  `approved_for_execution=False` on every returned result.
- The Phase 5D test suite asserts:
  - the JSON dump of every fixture-built view contains no
    `approved_for_execution=true` literal, and
  - every Phase 5D class does not declare an `approved_for_execution`
    field.

### 16.3 No executable order fields

- No Phase 5D view declares `order_type`, `time_in_force`,
  `broker_route`, `broker_id`, `account_id`, `quantity_to_execute`,
  `broker_payload`, `order_ticket`, `execution_id`, or `fill_price`.
- The source file contains none of those substrings.
- The Phase 5D test suite enforces both checks.

### 16.4 No live integration

- No import of `lib.workflow_state`, `lib.llm_orchestrator`,
  `lib.data_fetcher`, `lib.valuation`, `lib.technical`, `lib.rotation`,
  `lib.cache_manager`, Streamlit, or the Anthropic SDK in any Phase 5D
  module.
- No import of `lib.reliability.integration_boundary` (frozen Phase 4A).
- The Phase 5D test suite checks both `sys.modules` and the module source
  text for forbidden import substrings.
- The test suite also checks for the absence of the live workflow state
  JSON path substring in the source.

### 16.5 Deterministic offline behavior

- All view IDs derive from existing stable Phase 4M-D / 4M-E / 4M-F IDs.
- Phase 5D does not introduce a new content-hash factory; it surfaces
  `allocation_memory_id`, `option_trade_memory_id`, `feedback_memory_id`
  as produced upstream.
- Snapshot / view serialization round-trips by value.
- The same fixture pipeline produces byte-identical view JSON across
  rebuilds (asserted in the test suite).

---

## 17. Acceptance Criteria

Phase 5D is accepted when:

1. `lib/reliability/phase5_portfolio_views.py` exists and passes the
   dedicated test suite
   (`scripts/test_reliability_phase_5d_portfolio_trade_option_views.py`).
2. The Phase 5A complete fixture pack builds a fully populated
   `PortfolioCockpitView`, with `AllocationSummaryView` reporting
   `record_count=1` and `has_any_records=True`, one `PositionAllocationView`
   carrying the fixture allocation snapshot, one `TradePlanView` enumerating
   the six descriptive level kinds, and one `OptionOverlayView` carrying
   the fixture long-call strategy.
3. `RiskBudgetView.has_risk_budget` and `CashImpactView.has_cash_impact`
   are True only when the underlying allocation records carry the
   corresponding fields. The fixture record does not, so both flags
   default to False; a synthetic record carrying both fields flips both
   flags to True.
4. `OptionOverlayView` correctly preserves the `no_trade` state when the
   underlying record reports a no-trade state, including:
   - `state="no_trade"`,
   - `is_no_trade=True`,
   - empty `OptionRiskRewardView`,
   - populated `NoTradeReasonView` referencing the source record id.
5. Missing allocation records produce a safe degraded view with
   `missing_panels` including `"allocation"` and `"trade_plan"`.
6. Missing option records produce a safe degraded view with
   `missing_panels` including `"option_overlay"`.
7. Missing ticker / no records returns a safe empty
   `PortfolioCockpitView` with the execution safety banner still present.
8. `ExecutionSafetyBannerView` is always present and explicit.
9. No `approved_for_execution=True` appears in any view JSON; no Phase 5D
   class declares the field.
10. No executable order fields appear in any view class or in the module
    source.
11. `lib/reliability/__init__.py` re-exports the stable Phase 5D
    symbols.
12. No live runtime files are modified.
13. No DB, file persistence, vector store, external API, broker, or
    order path is introduced.
14. Phase 5A regression test
    (`scripts/test_reliability_phase_5a_memory_query.py`) continues to
    pass at 175/175.
15. Phase 5B regression test
    (`scripts/test_reliability_phase_5b_company_hub.py`) continues to
    pass at 163/163.
16. Phase 5C regression test
    (`scripts/test_reliability_phase_5c_horizon_views.py`) continues to
    pass at 179/179.
17. State files (`PROJECT_STATE.md`, `CURRENT_TASK.md`) record Phase 5D
    as "Implemented — Awaiting Codex Review" without claiming Phase 5E
    has started.

---

## 18. Future Phase 5E Dependency

Phase 5E (Cockpit UI Planning Boundary for Existing Streamlit App)
consumes Phase 5D as follows:

- A future cockpit planning document will describe how a Phase 5E render
  could draw a Portfolio / Allocation panel from `PortfolioCockpitView`,
  TradePlan cards from `TradePlanView`, Option Overlay cards from
  `OptionOverlayView`, and the explicit `ExecutionSafetyBannerView`
  *next to* (not inside) the existing six Streamlit pages.
- Phase 5E planning must not bypass Phase 5D's execution safety boundary.
  No `approved_for_execution` field may be reintroduced; no executable
  order field may be added; no broker / order / execution path may be
  introduced.
- Phase 5D's safe-degradation invariants (missing data → empty view +
  warnings) must be honored by any future renderer.

Phase 5F/5G/5H build on Phase 5B / 5C / 5D view-model contracts; none of
them adds live wiring.

---

## 19. Test Matrix

`scripts/test_reliability_phase_5d_portfolio_trade_option_views.py`
covers 212 assertions across 27 sections:

| Section | Topic                                                                |
|---------|----------------------------------------------------------------------|
| 1       | Module imports + forbidden-module non-load (`sys.modules`)            |
| 2       | Source-level forbidden import / executable-order substring check     |
| 3       | Public symbol imports + canonical level-kind tuple                    |
| 4       | Full `PortfolioCockpitView` build from Phase 5A complete fixture     |
| 5       | Allocation summary + positions populated from allocation memory       |
| 6       | Risk budget + cash impact populated only when fields supplied         |
| 7       | TradePlan view + 6 descriptive levels from allocation memory          |
| 8       | OptionOverlay view from option trade memory                           |
| 9       | `no_trade` option state preserved (no inferred substitute)            |
| 10      | Missing allocation records → safe degraded view + warning             |
| 11      | Missing option records → safe degraded view + warning                 |
| 12      | Missing ticker / no records → safe empty view                         |
| 13      | ExecutionSafetyBannerView present + explicit                          |
| 14      | No `approved_for_execution=True` anywhere; field not declared         |
| 15      | No executable order fields declared on any view                       |
| 16      | Builder rejects empty / whitespace target                             |
| 17      | Deterministic serialization across rebuilds                           |
| 18      | Build with explicit `MemoryQueryResult` equals store-driven build     |
| 19      | Human feedback `review_required=True` surfaces on trade plan / overlay / position |
| 20      | Direct builder calls match aggregator output                          |
| 21      | Package-level re-exports through `lib/reliability/__init__.py`        |
| 22      | Module `__all__` symmetry                                              |
| 23      | No filesystem writes during the pipeline                              |
| 24      | Phase 5C regression — `HorizonDecisionCardsView` still builds          |
| 25      | Phase 5B regression — `CompanyResearchHubView` still builds            |
| 26      | Phase 5A regression — `MemoryQueryResult` contract preserved          |
| 27      | Option overlay liquidity + event-risk warnings surface from upstream  |

All 212 assertions pass. Phase 5A regression passes 175/175. Phase 5B
regression passes 163/163. Phase 5C regression passes 179/179.
