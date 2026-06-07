# Reliability Phase 5G — Fixture Demo Pack Based on Original App Flow

**Date**: 2026-05-27
**Status**: Accepted (fixture/demo-only; no runtime app changes; no UI;
no live wiring).
**Type**: Deterministic fixture/demo pack that represents the original
README five-step Streamlit workflow end-to-end and feeds the Phase 5A–5D
overlay contracts (Existing Workflow Memory Adapter + memory query
contract → Company Research Hub view → Horizon Decision Cards +
ThesisTracker views → Portfolio / TradePlan / Option Overlay views).
**Module(s) added**:

- `lib/reliability/phase5_demo_pack.py`

**Test script added**:
`scripts/test_reliability_phase_5g_cockpit_demo_pack.py` (344/344
assertions passing at acceptance time; full Phase 5A–5D regression
covered through the demo pack and a smoke-import surface check).

> **Phase 5G is not a UI implementation.** Phase 5G adds **no**
> Streamlit page, modifies **no** existing page or `app.py`, modifies
> **no** `lib/llm_orchestrator.py`, `lib/valuation.py`, `lib/technical.py`,
> `lib/rotation.py`, `lib/data_fetcher.py`, `lib/workflow_state.py`,
> `lib/cache_manager.py`, `.claude/agents/*`, the existing news /
> Finnhub / data-fetch behavior, or `research/.workflow_state.json`.
> Phase 4A (`lib/reliability/integration_boundary.py`) remains frozen
> and is **not** imported. No database, file persistence, vector store,
> embedding pipeline, Anthropic SDK call, HTTP request, or broker /
> order / execution path is introduced. `approved_for_execution`
> remains `False` (or absent) everywhere it appears. `no_trade` is
> preserved as a first-class option overlay state.

---

## 1. Purpose

Phase 5G provides a **deterministic, fixture/demo-only Cockpit Demo
Pack** that:

1. Simulates one complete run of the original README five-step
   Streamlit workflow (Sector → Stock Scanner → Equity Research →
   Financial Analysis → PriceVolume Analysis → Synthesis).
2. Reuses the Phase 5A `ExistingWorkflowSnapshot` /
   `InMemoryWorkflowToMemoryAdapter` / `WorkflowMemoryBundle` /
   `FixtureBackedMemoryStore` contracts to thread the synthetic run
   through the Phase 4M-A through 4M-G memory record types.
3. Feeds the Phase 5B `CompanyResearchHubView`, Phase 5C
   `HorizonDecisionCardsView` + `ThesisTrackerView`, and Phase 5D
   `PortfolioCockpitView` builders so the cockpit-side view-model
   layer can be exercised end-to-end offline.
4. Carries explicit **demo-only provenance** and a **safety banner**
   that reasserts the non-execution / no-live-wiring / no-broker /
   no-investment-advice invariants Phase 5G must always honor.

Phase 5G is intended to support a future **Phase 5H Controlled
Streamlit Cockpit UI Integration v0.1**. Phase 5G itself never builds
any UI, never wires into the live app, and never authorizes execution.

---

## 2. Relationship to Roadmap v4 Investment Cockpit

Roadmap v4 Phase 5 describes an Investment Cockpit overlay that
projects the existing six-page Streamlit app's per-page outputs and the
Phase 4M memory layer into a horizon-aware, allocation-aware cockpit
surface. The Phase 5A–5G subphases form the **planning + contract +
demo** ladder underneath that overlay:

| Subphase | Role |
|----------|------|
| 5P | Phase 5 Roadmap Decision / Planning (overlay positioning, route comparison) |
| 5A | Existing Workflow Memory Adapter + Fixture-backed Memory Query Contract |
| 5B | Company Research Hub ViewModel Contract |
| 5C | Horizon Decision Cards + ThesisTracker ViewModel Contract |
| 5D | Portfolio / TradePlan / Option Overlay ViewModel Contract |
| 5E | Cockpit UI Planning Boundary for the existing Streamlit app |
| 5F | Shadow Mode Integration Boundary Planning |
| **5G** | **Fixture Demo Pack Based on Original App Flow (this doc)** |
| 5H | Controlled Streamlit Cockpit UI Integration v0.1 (future) |

Phase 5G is the **first phase that exercises all of 5A–5D end-to-end**
without any live wiring. It produces deterministic synthetic data that
a future Phase 5H integration can render against, and that an
ultra-conservative shadow mode (Phase 5F) could swap out for live
observations once the snapshot adapter is built.

---

## 3. Relationship to the Original README App

The README app already produces six page outputs (Overview / Sector /
Scanner / Equity / Financial / PriceVolume) and an automated five-step
AI workflow on the Overview page (Sector Analysis → Stock Scanner →
Equity Research → Financial Analysis → PriceVolume Analysis →
Synthesis). Phase 5G's complete scenario mirrors this exact shape:

```
Original README App                       Phase 5G Complete Scenario
───────────────────                       ──────────────────────────
Overview page                       →     ExistingWorkflowSnapshot (FIXTKR)
  Step 1: Sector Analysis           →       steps["sector"]
  Step 2: Stock Scanner             →       steps["scanner"]
  Step 3: Equity Research           →       steps["equity"]
  Step 4: Financial Analysis        →       steps["financial"]
  Step 5: PriceVolume Analysis      →       steps["price_volume"]
  Synthesis                         →       steps["synthesis"] + synthesis
```

Phase 5G never reads or writes `research/.workflow_state.json`, never
imports `lib/workflow_state.py`, never imports `lib/llm_orchestrator.py`,
and never calls the Claude API.

---

## 4. Relationship to Phase 4M Memory Records

Phase 5G reuses **every** Phase 4M-A through 4M-G memory record type
without redefining or replacing any of them. The complete scenario
populates one record of each type; the degraded scenario omits one
horizon's thesis and the agent evaluation record to demonstrate safe
degraded behavior:

| Phase 4M | Record | Complete | Degraded |
|----------|--------|----------|----------|
| 4M-A | `ResearchRunMemoryRecord` | ✓ | ✓ |
| 4M-B | `HorizonThesisMemoryRecord` (short / medium / long) | 3 | 2 (no long) |
| 4M-C | `EventMemoryRecord` | ✓ | — |
| 4M-D | `AllocationDecisionMemoryRecord` | ✓ | ✓ |
| 4M-E | `OptionTradePlanMemoryRecord` (`approved_for_execution=False`) | ✓ (long_call) | ✓ (no_trade) |
| 4M-F | `HumanFeedbackMemoryRecord` | ✓ | ✓ |
| 4M-G | `AgentEvaluationRecord` | ✓ | — |

All records are deterministic. Identical fixture inputs yield
identical IDs across runs.

---

## 5. Relationship to Phase 5A Memory Query Contract

Each scenario builds its own `FixtureBackedMemoryStore` from the
scenario's `WorkflowMemoryBundle` and exposes a target-scoped
`MemoryQueryResult` directly on the `MemoryDemoFixtureBundle`. This
mirrors how a future Phase 5H cockpit would query the same boundary:

- `MemoryQueryByTicker(target=…)` is the canonical scope.
- `MemoryQueryByHorizon(horizon=…)` exercises Phase 5C surfaces.
- `MemoryQueryByType(record_type=…)` exercises per-type views.

Phase 5G never creates a shared cross-scenario store. Each scenario is
self-contained.

---

## 6. Relationship to Phase 5B Company Hub

Phase 5G constructs one `CompanyResearchHubView` per scenario using
`build_company_research_hub_view(target=…, snapshot=…, memory_store=…,
memory_query_result=…)`. The complete scenario produces a fully
populated hub (Equity / Financial / PriceVolume panels populated,
synthesis present, evidence + validation panels populated). The
degraded scenario produces a hub whose `financial_panel.is_populated`
is `False`, whose `missing_data.missing_panels` contains `"financial"`,
and whose equity / price/volume panels remain populated — exactly the
safe-degraded shape Phase 5B promises.

---

## 7. Relationship to Phase 5C Horizon Cards / ThesisTracker

Phase 5G builds one `HorizonDecisionCardsView` per scenario using
`build_horizon_decision_cards_view(target=…, memory_store=…,
memory_query_result=…)`. The complete scenario yields three populated
cards in canonical `short → medium → long` order, each with an
`"active"` card status. The degraded scenario yields three cards in
canonical order, but the long-horizon card carries
`is_populated=False`, `status="missing"`, and explanatory warnings.

The `ThesisTrackerView` mirrors the same per-horizon rows. Phase 5G
does not cross-target the tracker; a future cockpit can compose
multi-target tracker views from multiple Phase 5G scenarios externally.

---

## 8. Relationship to Phase 5D Portfolio / TradePlan / Option Overlay

Phase 5G builds one `PortfolioCockpitView` per scenario using
`build_portfolio_cockpit_view(target=…, memory_store=…,
memory_query_result=…)`. The complete scenario produces:

- One `PositionAllocationView` from the allocation record.
- One `TradePlanView` with descriptive `entry / add / trim / stop /
  target / review` level slots.
- One `OptionOverlayView` in the `option` state with bounded
  risk/reward fields, `approved_for_execution=False`, and no
  executable order fields.
- An `ExecutionSafetyBannerView` always present.

The degraded scenario produces a `PortfolioCockpitView` whose option
overlay is in the `no_trade` state, with a `NoTradeReasonView`
attached. Phase 5G never infers a substitute strategy for a `no_trade`
record — `no_trade` is a first-class option overlay state.

---

## 9. Relationship to Phase 5E and Relationship to Phase 5F

Phase 5G remains strictly inside the Phase 5E "UI planning boundary":
Phase 5G adds no Streamlit page, no UI component, no live wiring, and
no modifications to any of the six existing pages. Phase 5G also
remains strictly inside the Phase 5F "shadow mode planning boundary":
Phase 5G adds no actual shadow runner, no snapshot adapter against
live workflow output, no comparison harness, and never reads
`research/.workflow_state.json`.

Phase 5G's deterministic synthetic snapshots are the kind of input a
future Phase 5F shadow mode would emit — but Phase 5G never claims
shadow mode is wired or active.

---

## 10. Demo scenario structure

A `CockpitDemoPack` aggregates one or more `CockpitDemoScenario`
entries. Each scenario carries:

- `metadata: DemoScenarioMetadata` — scenario id, kind
  (`complete` / `degraded`), title, description, ticker, run_id,
  as_of, safety banner, provenance.
- `workflow_fixture: OriginalWorkflowDemoFixture` — the
  `ExistingWorkflowSnapshot`, the `InMemoryWorkflowToMemoryAdapter`
  (excluded from JSON serialization), the resulting
  `WorkflowMemoryBundle`, and present/missing step keys.
- `memory_fixture: MemoryDemoFixtureBundle` — the Phase 4M records
  (research run / thesis list / event list / allocation list / option
  trade list / human feedback list / agent evaluation list), plus the
  `FixtureBackedMemoryStore` (excluded from JSON serialization) and a
  target-scoped `MemoryQueryResult`.
- `view_bundle: CockpitViewDemoBundle` — Phase 5B
  `CompanyResearchHubView`, Phase 5C `HorizonDecisionCardsView` +
  `ThesisTrackerView`, Phase 5D `PortfolioCockpitView`.
- `warnings: list[str]` — per-scenario explanatory warnings (the
  degraded scenario lists the missing financial step, the missing
  long-horizon thesis, and the `no_trade` option overlay).

The pack itself additionally carries:

- `pack_id`, `title`, `description`.
- `safety_banner: DemoSafetyBanner` (pack-level).
- `provenance: DemoDataProvenance` (pack-level, listing all fixture
  tickers and the demo `as_of`).
- `validation_summary: DemoPackValidationSummary` populated by
  `validate_cockpit_demo_pack(pack)` during construction.

---

## 11. Complete scenario contents

The complete scenario uses fictional ticker `FIXTKR`, run_id
`FIXTKR_20260524_120000_fix5g_complete`, and `as_of`
`2026-05-24T12:00:00+00:00`. It contains:

- All six workflow steps (sector / scanner / equity / financial /
  price_volume / synthesis), each with one fixture
  `ExistingPageOutputRef` and one evidence ID.
- One `ResearchRunMemoryRecord` referencing all six steps.
- Three `HorizonThesisMemoryRecord`s (short bullish, medium neutral,
  long bullish) each with one assumption and one invalidation
  condition.
- One `EventMemoryRecord` (mock Q1 2026 earnings, neutral impact,
  affects short + medium horizons).
- One `AllocationDecisionMemoryRecord` (`action="add"`,
  `risk_level="medium"`, target 5% / actual 4% allocation).
- One `OptionTradePlanMemoryRecord` (`decision="option"`,
  `strategy_type="long_call"`, bounded max_loss / max_gain /
  breakeven, `approved_for_execution=False`).
- One `HumanFeedbackMemoryRecord` (`decision="accepted"`,
  `outcome="positive"`).
- One `AgentEvaluationRecord` (medium-horizon `evaluation_grade="mixed"`).

Downstream view bundle:

- `CompanyResearchHubView` with every panel populated.
- `HorizonDecisionCardsView` with three populated `"active"` cards.
- `ThesisTrackerView` with three rows in canonical order.
- `PortfolioCockpitView` with one position, one trade plan, one
  option overlay in `option` state, and the execution-safety banner.

---

## 12. Optional degraded scenario contents

The degraded scenario uses fictional ticker `FIXDEG`, run_id
`FIXDEG_20260524_120100_fix5g_degraded`, and the same `as_of`. It
contains:

- Five workflow steps (sector / scanner / equity / price_volume /
  synthesis) — the **financial step is intentionally omitted**.
- One `ResearchRunMemoryRecord`.
- Two `HorizonThesisMemoryRecord`s (short neutral/low,
  medium neutral/low) — the **long-horizon thesis is intentionally
  omitted**.
- One `AllocationDecisionMemoryRecord` (`action="add"`).
- One `OptionTradePlanMemoryRecord` with `decision="no_trade"` and
  `strategy_type="no_trade"`.
- One `HumanFeedbackMemoryRecord`.
- No event record and no agent evaluation record.

Downstream view bundle:

- `CompanyResearchHubView` whose `financial_panel.is_populated=False`,
  whose `missing_data.missing_panels` contains `"financial"`, and whose
  equity / price_volume panels remain populated.
- `HorizonDecisionCardsView` with three cards in canonical order;
  the long card has `status="missing"`, `is_populated=False`, and a
  populated `warnings` list.
- `ThesisTrackerView` with three rows; the long-horizon row is a safe
  `"missing"` row.
- `PortfolioCockpitView` with one position, one trade plan, and one
  `OptionOverlayView` in the `no_trade` state carrying a populated
  `NoTradeReasonView`. The execution-safety banner remains present.

Scenario-level warnings on the degraded scenario explicitly call out:
*"Degraded scenario: financial step is intentionally missing."*,
*"Degraded scenario: long-horizon thesis is intentionally absent."*,
*"Degraded scenario: option overlay reports no_trade."*

---

## 13. Demo-only provenance

Every Phase 5G fixture / pack carries a `DemoDataProvenance` value
that hardcodes the fixture-only invariants:

```text
generator:                 "phase5_demo_pack"
generator_version:         "phase5_demo_pack_v1"
is_fixture_only:           True
uses_live_data:            False
uses_external_api:         False
uses_live_workflow_state:  False
uses_llm:                  False
uses_broker:               False
fixture_tickers:           [FIXTKR, FIXDEG]
as_of:                     2026-05-24T12:00:00+00:00
notes:                     "Phase 5G fixture/demo pack only. No live
                            workflow read, no live API, no live broker
                            call."
```

A future cockpit / Phase 5H integration must always surface this
provenance alongside the demo pack so reviewers cannot mistake demo
data for live data.

---

## 14. Safety banner semantics

Every Phase 5G fixture / pack carries a `DemoSafetyBanner` value that
hardcodes:

- `is_demo_only = True`
- `is_non_executable = True`
- `requires_human_review = True`
- `no_live_workflow_wiring = True`
- `no_external_api = True`
- `no_broker_or_order = True`
- `no_investment_advice = True`
- `approved_for_execution = False` *(validator rejects True)*
- `message` — a multi-sentence non-execution reminder.

Phase 5G's `DemoSafetyBanner` is intentionally distinct from
Phase 5D's `ExecutionSafetyBannerView`. Phase 5D's banner appears on
every `PortfolioCockpitView` and states that the cockpit projection is
research-only. Phase 5G's banner is **stricter**: it additionally
states that the pack is fixture/demo-only, that no live workflow
wiring exists, that no external API is called, and that no broker /
order path exists.

---

## 15. Non-Goals

Phase 5G does **not**:

- Ship any new UI page.
- Modify any existing page, `app.py`, `lib/llm_orchestrator.py`,
  `lib/workflow_state.py`, `lib/valuation.py`, `lib/technical.py`,
  `lib/rotation.py`, `lib/data_fetcher.py`, or `lib/cache_manager.py`.
- Read or write `research/.workflow_state.json`.
- Add SQL / NoSQL / file / vector store persistence.
- Embed records or build a similarity index.
- Call the Claude API, Anthropic SDK, or any HTTP service.
- Modify any agent definition (`.claude/agents/*`) or live prompt.
- Modify any existing live prompt file.
- Route orders, place trades, or set `approved_for_execution=True`.
- Wire Phase 4A `integration_boundary.py` into the live app or import
  it from Phase 5G.
- Generate investment advice beyond fixture text.
- Build the Phase 5H Controlled Streamlit Cockpit UI Integration.
- Implement real shadow mode (Phase 5F runtime).
- Introduce executable order fields (`order_type`, `time_in_force`,
  `broker_route`, `broker_id`, `account_id`, `quantity_to_execute`,
  `broker_payload`, `order_ticket`, `execution_id`, `fill_price`).

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
- `research/.workflow_state.json`

### 16.2 `approved_for_execution` invariant

- `DemoSafetyBanner` rejects construction with
  `approved_for_execution=True`.
- `OriginalWorkflowDemoFixture` rejects bundles or snapshots whose
  `approved_for_execution` is `True`.
- `MemoryDemoFixtureBundle` rejects `MemoryQueryResult` with
  `approved_for_execution=True`.
- `validate_cockpit_demo_pack(pack)` records an error if any record /
  snapshot / bundle / query result on any scenario has
  `approved_for_execution=True`.
- Every underlying Phase 4M memory record (research run, thesis,
  event, allocation, option trade, human feedback, agent evaluation)
  already enforces `approved_for_execution=False` at its model layer.

### 16.3 `no_trade` invariant

- The degraded scenario's option trade plan memory record reports
  `decision="no_trade"` and `strategy_type="no_trade"`.
- The downstream `OptionOverlayView` is in the `no_trade` state with a
  populated `NoTradeReasonView`. Phase 5G never infers a substitute
  strategy.

### 16.4 No executable order fields

Phase 5G's source asserts that none of the Phase 5G models declare any
of the following field names: `order_type`, `time_in_force`,
`broker_route`, `broker_id`, `account_id`, `quantity_to_execute`,
`broker_payload`, `order_ticket`, `execution_id`, `fill_price`. The
Phase 5G test suite enforces both the field-name check and a
source-substring check.

### 16.5 No live integration

Phase 5G does not import `lib.workflow_state`, `lib.llm_orchestrator`,
`lib.data_fetcher`, `lib.valuation`, `lib.technical`, `lib.rotation`,
`streamlit`, or the Anthropic SDK in any Phase 5G module. Phase 5G
does not import `lib.reliability.integration_boundary` (Phase 4A
remains frozen).

### 16.6 Deterministic offline behavior

- All IDs derive from stable hashes.
- Identical fixture inputs produce identical JSON-serialized scenarios.
- No filesystem writes occur during pack construction.

---

## 17. Acceptance Criteria

Phase 5G is accepted when:

1. `lib/reliability/phase5_demo_pack.py` exists and passes the
   dedicated test suite
   (`scripts/test_reliability_phase_5g_cockpit_demo_pack.py`).
2. `build_default_cockpit_demo_pack()` produces a pack with at least
   one complete scenario and one degraded scenario, each fully
   self-contained and deterministic.
3. The complete scenario covers all six workflow steps and every
   Phase 4M memory record type.
4. The complete scenario produces three Phase 5C horizon decision
   cards in canonical `short → medium → long` order, all populated.
5. The degraded scenario demonstrates safe degraded behavior for at
   least one missing data path (missing workflow step OR missing
   horizon thesis OR `no_trade` option overlay). The default pack
   demonstrates all three.
6. `DemoSafetyBanner` and `DemoDataProvenance` are present on the
   pack and on every scenario, with the required invariants set.
7. `validate_cockpit_demo_pack(pack)` records no errors,
   `all_approved_for_execution_false=True`, and
   `no_executable_order_fields=True`.
8. `lib/reliability/__init__.py` re-exports the stable Phase 5G
   symbols.
9. No live runtime files are modified.
10. `approved_for_execution` remains `False` (or absent) everywhere.
11. `no_trade` is preserved as a first-class option overlay state.
12. Phase 5A / 5B / 5C / 5D regression tests still pass.
13. State files (`PROJECT_STATE.md`, `CURRENT_TASK.md`) record Phase
    5G as "Implemented — Awaiting Codex Review" and do not claim
    Phase 5H has started.

---

## 18. Future Phase 5H Dependency

Phase 5H (Controlled Streamlit Cockpit UI Integration v0.1) is the
**next phase** that may render Phase 5G demo packs in a Streamlit
surface alongside the existing six pages. Phase 5H must:

- Render Phase 5G safety banners verbatim and visibly.
- Render Phase 5G provenance verbatim alongside the cockpit surface.
- Not collapse or hide `is_demo_only`, `no_live_workflow_wiring`,
  `no_external_api`, `no_broker_or_order`, `no_investment_advice`, or
  `approved_for_execution=False` indicators.
- Continue to honor every Phase 5A–5G guardrail (no `app.py`
  modification, no `pages/*` modification, no `lib/workflow_state.py`
  read, no live LLM call from cockpit code, no broker / order /
  execution path).
- Treat Phase 5G as **demo data**, never as a substitute for real
  workflow output.

Phase 5G itself does not start Phase 5H. Phase 5G must not claim Phase
5H is wired or active.

---

## 19. Test Matrix

`scripts/test_reliability_phase_5g_cockpit_demo_pack.py` covers 344
assertions across 22 sections (344/344 passing at acceptance time):

| Section | Topic |
|---------|-------|
| 1 | Module import + forbidden-module non-load |
| 2 | Source-level forbidden import substring check |
| 3 | `build_default_cockpit_demo_pack()` smoke + determinism |
| 4 | Complete scenario workflow coverage (all 6 steps) |
| 5 | Complete scenario Phase 4M memory coverage |
| 6 | Complete scenario Phase 5B/5C/5D view-bundle |
| 7 | Degraded scenario coverage (missing financial, missing long thesis, no_trade overlay) |
| 8 | Safety banner + provenance invariants |
| 9 | `approved_for_execution=False` everywhere |
| 10 | No executable order field names on any Phase 5G model |
| 11 | `validate_cockpit_demo_pack(pack)` assertions |
| 12 | Serialization determinism + JSON round-trip |
| 13 | Standalone builders (safety banner / provenance / metadata) |
| 14 | Helper builders work standalone (workflow / memory / view) |
| 15 | No filesystem writes during build |
| 16 | Exports / `__all__` |
| 17 | Package-level re-exports |
| 18 | No live wiring / no positive authorization in source |
| 19 | Regression: Phase 5A / 5B / 5C / 5D contract surfaces intact |
| 20 | Pack-level invariants on degraded scenario warnings |
| 21 | Forbidden live runtime files still present |
| 22 | Phase 5G design doc required-section existence |

All assertions pass at acceptance time.
