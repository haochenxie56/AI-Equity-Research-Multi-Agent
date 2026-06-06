# Reliability Phase 5H — Controlled Streamlit Cockpit UI Integration v0.1

**Date**: 2026-05-27
**Status**: Implemented — awaiting Codex review (fixture/demo-only;
read-only; no live wiring; no execution).
**Type**: Single new Streamlit page that renders the Phase 5G fixture
demo pack through the Phase 5B / 5C / 5D view-model contracts.

**Files added**

- `pages/7_Investment_Cockpit.py`
- `scripts/test_reliability_phase_5h_cockpit_ui_preview.py`
- `docs/reliability_phase_5h_controlled_streamlit_cockpit_ui.md` (this
  document)

> **Phase 5H is the first controlled UI surface for the Investment
> Cockpit overlay.** It adds one new Streamlit page and consumes only
> the Phase 5G fixture demo pack. Phase 5H does **not** modify
> `app.py`, any of the six existing pages
> (`pages/1_Overview.py` … `pages/6_PriceVolume.py`),
> `lib/llm_orchestrator.py`, `lib/valuation.py`, `lib/technical.py`,
> `lib/rotation.py`, `lib/data_fetcher.py`, `lib/workflow_state.py`,
> `lib/cache_manager.py`, `.claude/agents/*`, existing live prompt
> files, or `research/.workflow_state.json`. Phase 4A
> (`lib/reliability/integration_boundary.py`) remains frozen and is
> **not** imported. No live LLM call, no external API call, no broker
> call, no order routing, no database, no file persistence, no vector
> store, no shadow mode runner. `approved_for_execution` remains
> `False` (or absent) everywhere it appears, and the page does not
> positively authorize it anywhere.

---

## 1. Purpose

Phase 5H gives reviewers a product-facing way to **see** the
Investment Cockpit v0.1 surface defined by Phase 5A–5G without any
live wiring. The page:

1. Loads the deterministic Phase 5G `CockpitDemoPack` via
   `build_default_cockpit_demo_pack()`.
2. Presents a scenario selector (`complete` `FIXTKR` by default;
   `degraded` `FIXDEG` available).
3. Renders the Phase 5B `CompanyResearchHubView`, Phase 5C
   `HorizonDecisionCardsView` / `ThesisTrackerView`, and Phase 5D
   `PortfolioCockpitView` for the selected scenario.
4. Surfaces both the pack-level and scenario-level safety banner and
   provenance information explicitly, so a reviewer cannot mistake the
   demo for live output.
5. Fails closed: if the demo pack builder raises, the page displays a
   visible error block and does not attempt any LLM / API fallback.

Phase 5H is the **product-facing demo preview** referenced by
Roadmap v4 Phase 5 Investment Cockpit. It is **not** a live
integration of the cockpit into the existing five-step workflow, and
it is **not** the Phase 5F shadow-mode runtime.

---

## 2. Relationship to Roadmap v4 Phase 5 Investment Cockpit

Roadmap v4 Phase 5 describes an Investment Cockpit overlay that sits
**on top of** the existing six-page Streamlit app. The Phase 5
subphase ladder is:

| Subphase | Role |
|----------|------|
| 5P | Phase 5 Roadmap Decision / Planning |
| 5A | Existing Workflow Memory Adapter + Fixture-backed Memory Query Contract |
| 5B | Company Research Hub ViewModel Contract |
| 5C | Horizon Decision Cards + ThesisTracker ViewModel Contract |
| 5D | Portfolio / TradePlan / Option Overlay ViewModel Contract |
| 5E | Cockpit UI Planning Boundary for the existing Streamlit app |
| 5F | Shadow Mode Integration Boundary Planning |
| 5G | Fixture Demo Pack Based on Original App Flow |
| **5H** | **Controlled Streamlit Cockpit UI Integration v0.1 (this doc)** |
| 5I | Read-only Shadow Integration (future, not started) |

> **Superseded note (Phase 5I review cleanup, 2026-05-28):** the "Phase 5I —
> Read-only Shadow Integration" wording in the row above (and in §16 below) is
> **historical / superseded**. The accepted Phase 5I is **"Investment Cockpit
> Product Logic Reconciliation / Opportunity-first + Horizon-aware
> Architecture"** (see
> `docs/reliability_phase_5i_investment_cockpit_product_logic_reconciliation.md`),
> which repositions the Cockpit as opportunity-first and pushes read-only
> shadow integration to a later, separately scoped phase. The text here is
> retained for historical continuity only; no Phase 5H / 5H.1 runtime or module
> behavior changes as a result of this note.

Phase 5H is the first phase that **renders** the cockpit overlay in
Streamlit. Phase 5H consciously stays inside the Phase 5G fixture
boundary — it does not call the Phase 5F shadow runner (which has not
been implemented), does not read `research/.workflow_state.json`, and
does not modify the existing six README pages.

---

## 3. Relationship to the original README Streamlit app

The README app today exposes six pages:

```
pages/1_Overview.py     — AI workflow control center
pages/2_Sector.py       — Sector analysis
pages/3_Scanner.py      — Stock scanner
pages/4_Equity.py       — Equity research
pages/5_Financial.py    — Financial analysis
pages/6_PriceVolume.py  — Price/volume analysis
```

Phase 5H adds one **additive** page:

```
pages/7_Investment_Cockpit.py — Phase 5H demo preview
```

The new page is presented alongside the existing six pages. None of
the existing pages, `app.py`, `ui_utils.py`, `lib/workflow_state.py`,
`lib/llm_orchestrator.py`, or any other live runtime file is
modified. The Phase 5H page does not call any live workflow function
and does not import live runtime modules.

---

## 4. Relationship to Phase 5E (Cockpit UI Planning Boundary)

Phase 5E documented what a future cockpit UI **could** look like next
to the existing six pages. Phase 5E added no Python module and no new
page. Phase 5H is the first phase that materializes a tiny slice of
that plan, but **strictly inside the Phase 5G fixture boundary** and
strictly as an **additive** new page. Phase 5H still honors every
Phase 5E constraint:

- No existing page is modified.
- `app.py` is unchanged.
- `lib/workflow_state.py` is not read or imported.
- `lib/llm_orchestrator.py` is not called.
- `research/.workflow_state.json` is not read.

---

## 5. Relationship to Phase 5F (Shadow Mode Integration Boundary)

Phase 5F documented the planning boundary for a **future** read-only
shadow mode that would observe completed workflow outputs and route
them through Phase 5A / 5B / 5C / 5D into a future cockpit UI. Phase
5F added no runtime module, no snapshot adapter, no comparison
harness, and explicitly hardcoded the envelope's
`approved_for_execution = False` and empty
`executable_order_fields`.

Phase 5H **does not** start the Phase 5F runtime. The Phase 5H page
does not call any shadow runner, does not read live workflow output,
and does not enable any feature flag. Phase 5H consumes only the
Phase 5G fixture demo pack.

---

## 6. Relationship to Phase 5G (Fixture Demo Pack)

Phase 5G provided the deterministic `CockpitDemoPack` with one
complete scenario (`FIXTKR`) and one degraded scenario (`FIXDEG`).
Phase 5H consumes the demo pack exclusively. The page:

- Imports only `CockpitDemoPack`, `CockpitDemoScenario`,
  `DEMO_SCENARIO_ORDER`, and `build_default_cockpit_demo_pack` from
  `lib.reliability.phase5_demo_pack`.
- Imports the Phase 5B / 5C / 5D view-model classes for type access.
- Caches the built pack once per process and renders the Phase 5B /
  5C / 5D view-models from it.

> **Superseded (historical) note — original Phase 5H caching design.**
> The original Phase 5H page used `@st.cache_data` to memoize a
> `pack.model_dump(mode="json")` JSON dump and rebuilt the Pydantic
> pack from that dump on each render. **This design was a defect** and
> is **superseded by Phase 5H.1** (see §18.1): the Phase 5G
> `OriginalWorkflowDemoFixture.adapter` and
> `MemoryDemoFixtureBundle.memory_store` carry `Field(exclude=True)`,
> so the JSON round-trip could never reconstruct the pack and the page
> hit its fail-closed branch on every render. Phase 5H.1 replaced this
> with `@st.cache_resource` returning the live `CockpitDemoPack`
> directly (no JSON round-trip). The current page does **not** use the
> `@st.cache_data` / `model_dump` → `model_validate` round-trip.

---

## 7. Page created and why it is additive

`pages/7_Investment_Cockpit.py` is a new file. It is added next to the
existing pages. The page is additive: it does not replace, hide, or
modify any existing page, and it does not change the navigation order
of pages 1–6.

> **Superseded (historical) note — original Phase 5H navigation
> assumption.** The original Phase 5H doc assumed the page would surface
> automatically in the Streamlit sidebar under the filename-derived label
> "7 Investment Cockpit". **This assumption was wrong** and is
> **superseded by Phase 5H.1** (see §18.1, defect 2): `.streamlit/config.toml`
> sets `showSidebarNavigation = false`, and `ui_utils.render_sidebar`
> hand-rolls a fully custom bilingual sidebar via explicit `st.page_link`
> calls — so a new page is **not** auto-discovered from its filename.
> Phase 5H.1 added one
> `st.page_link("pages/7_Investment_Cockpit.py", label=t("nav_p7"))`
> line to `ui_utils.render_sidebar`, giving the page a translated nav
> label ("🧭 Investment Cockpit" / "🧭 投研中枢") rather than a
> filename-derived one.

---

## 8. Existing pages preserved

The Phase 5H test
(`scripts/test_reliability_phase_5h_cockpit_ui_preview.py`) explicitly
asserts that:

- `app.py` still exists.
- `pages/1_Overview.py` through `pages/6_PriceVolume.py` all still
  exist.
- None of these existing files contains Phase 5H marker strings
  (`phase5_demo_pack`, `Phase 5H`, `Investment Cockpit`,
  `DemoSafetyBanner`, `build_default_cockpit_demo_pack`), which would
  indicate Phase 5H reached into them.
- `lib/llm_orchestrator.py`, `lib/workflow_state.py`,
  `lib/valuation.py`, `lib/technical.py`, `lib/rotation.py`,
  `lib/data_fetcher.py`, `lib/cache_manager.py`, and
  `lib/reliability/integration_boundary.py` all still exist.

---

## 9. Fixture-only data flow

The page's data flow is:

```
build_default_cockpit_demo_pack()
        │
        ▼
  CockpitDemoPack
   ├── safety_banner (DemoSafetyBanner)
   ├── provenance    (DemoDataProvenance)
   ├── validation_summary (DemoPackValidationSummary)
   └── scenarios: list[CockpitDemoScenario]
            ├── metadata     (DemoScenarioMetadata)
            ├── workflow_fixture (OriginalWorkflowDemoFixture)
            ├── memory_fixture (MemoryDemoFixtureBundle)
            └── view_bundle  (CockpitViewDemoBundle)
                     ├── CompanyResearchHubView      [Phase 5B]
                     ├── HorizonDecisionCardsView    [Phase 5C]
                     ├── ThesisTrackerView           [Phase 5C]
                     └── PortfolioCockpitView        [Phase 5D]
```

Phase 5H **never** fetches data from any other source. No
`requests`, `httpx`, `urllib`, `anthropic`, `openai`, `yfinance`,
`finnhub`, `polygon`, broker SDK, or order router is called.

---

## 10. UI sections / tabs

The page exposes eight tabs in this fixed order:

1. **Overview / Safety** — safety banner (pack + scenario level),
   scenario identity, scenario warnings.
2. **Company Research Hub** — Phase 5B `CompanyResearchHubView`
   identity, equity / financial / price-volume panels, source
   workflow panel, evidence coverage panel, validation status
   panel, missing-data warnings. Degraded panels are explicitly
   surfaced as `is_populated=False` with a visible "missing
   financial panel" warning. The page does not regenerate analysis
   text.
3. **Horizon Cards** — Phase 5C `HorizonDecisionCardsView` rendered as
   three columns in canonical `short → medium → long` order. Missing
   cards remain visible as safe degraded slots. Review-needed badge
   and missing-evidence badge are surfaced. The page does not
   fabricate thesis or recommendation text.
4. **ThesisTracker** — Phase 5C `ThesisTrackerView` rendered as a
   deterministic table by `(target, horizon)`. Status, direction,
   confidence, invalidation trigger count, review-needed flag, and
   the descriptive next-action label are surfaced.
5. **Portfolio / TradePlan** — Phase 5D `PortfolioCockpitView`
   surfaces the execution-safety banner, allocation summary, risk
   budget / cash impact aggregates, positions table, and per-trade-
   plan level tables (entry / add / trim / stop / target / review).
   No order tickets, broker routes, account IDs, time-in-force
   values, executable quantities, or order-ticket payloads are
   displayed.
6. **Option Overlay** — Phase 5D `OptionOverlayView` rendered per
   record. `no_trade` is shown as a first-class state with a
   populated `NoTradeReasonView`. Other states show strategy summary
   and the bounded risk/reward fields the fixture provides. No
   executable option order is displayed.
7. **Feedback / Agent Evaluation** — fixture-backed Phase 4M-F human
   feedback and Phase 4M-G agent evaluation summaries when the
   scenario contains those records.
8. **Provenance / Diagnostics** — pack-level and scenario-level
   provenance, demo pack validation summary, source fixture name,
   explicit note that this is **not** live workflow output.

---

## 11. Safety banner semantics

The page displays two layers of safety statements:

- **Top-of-tab safety banner** rendered on the Overview / Safety tab.
  Contains required wording bullets (`Fixture/demo only`, `No live
  workflow wiring`, `No external API`, `No orders`,
  `approved_for_execution is False`, `Not investment advice`). The
  Phase 5H test asserts each phrase is present in the source.
- **Phase 5G `DemoSafetyBanner` JSON dumps** rendered next to each
  other (pack-level and scenario-level), confirming
  `is_demo_only=True`, `is_non_executable=True`,
  `requires_human_review=True`, `no_live_workflow_wiring=True`,
  `no_external_api=True`, `no_broker_or_order=True`,
  `no_investment_advice=True`, `approved_for_execution=False`.

The Phase 5D `ExecutionSafetyBannerView` is additionally rendered on
the Portfolio / TradePlan tab — every `PortfolioCockpitView` always
carries this banner.

---

## 12. Degraded scenario behavior

When the user selects the `degraded` scenario (`FIXDEG`):

- The Company Research Hub tab surfaces a missing-data warning for
  the missing `financial` panel and renders the financial panel as
  `is_populated=False`.
- The Horizon Cards tab still renders three cards in canonical order;
  the long-horizon card is `status="missing"`, `is_populated=False`,
  with explanatory warnings.
- The Portfolio / TradePlan tab renders the allocation and trade plan
  if present.
- The Option Overlay tab renders the `no_trade` overlay state with a
  populated `NoTradeReasonView`. Phase 5H **never** infers a
  substitute strategy.
- The Provenance / Diagnostics tab continues to indicate the demo /
  fixture origin.

The page degrades safely — it never replaces missing data with
fabricated content, and it never positively authorizes
`approved_for_execution`.

---

## 13. Non-goals

Phase 5H does **not**:

- Modify any existing page or `app.py`.
- Modify `lib/llm_orchestrator.py`, `lib/valuation.py`,
  `lib/technical.py`, `lib/rotation.py`, `lib/data_fetcher.py`,
  `lib/workflow_state.py`, `lib/cache_manager.py`, or
  `lib/reliability/integration_boundary.py`.
- Read or write `research/.workflow_state.json`.
- Call any LLM (Anthropic / OpenAI / other).
- Call any external API (HTTP, broker, market data).
- Add or use a database / vector store / cache backend.
- Implement Phase 5F shadow mode runtime.
- Implement Phase 5I live read-only shadow integration.
- Produce orders, order tickets, broker payloads, executable
  instructions, or any `approved_for_execution=True` artifact.
- Wire Phase 4A `integration_boundary.py` into the live app or
  import it from Phase 5H.
- Mutate any agent definition (`.claude/agents/*`) or live prompt
  file.
- Generate investment advice.

---

## 14. Guardrails

### 14.1 Forbidden existing files (unchanged across Phase 5)

The Phase 5H page does not modify or import any of the following live
runtime files:

- `app.py`
- `pages/1_Overview.py`
- `pages/2_Sector.py`
- `pages/3_Scanner.py`
- `pages/4_Equity.py`
- `pages/5_Financial.py`
- `pages/6_PriceVolume.py`
- `lib/llm_orchestrator.py`
- `lib/valuation.py`
- `lib/technical.py`
- `lib/rotation.py`
- `lib/data_fetcher.py`
- `lib/workflow_state.py`
- `lib/cache_manager.py`
- `lib/reliability/integration_boundary.py` *(frozen Phase 4A)*
- `.claude/agents/*`
- existing live prompt files
- `research/.workflow_state.json`

The Phase 5H test enforces this invariant by:

- Asserting each forbidden file still exists.
- Asserting none of the existing pages contains Phase 5H marker
  strings (which would indicate Phase 5H modified them).
- Asserting the page source contains no `import ${MODULE}` or
  `from ${MODULE}` statement for any forbidden module.
- Asserting the page source contains no live file-open pattern for
  `research/.workflow_state.json`.

### 14.2 `approved_for_execution` invariant

- The page does not positively assign `approved_for_execution = True`
  anywhere.
- The page surfaces the underlying boolean from `DemoSafetyBanner` as
  a dynamic JSON value (always `False`).
- The Phase 5H test asserts source-level absence of every common
  positive-authorization form.

### 14.3 `no_trade` invariant

- The Option Overlay tab renders the `no_trade` state explicitly with
  a populated `NoTradeReasonView`.
- The page never infers a substitute strategy.

### 14.4 No executable order fields

The page source does not contain any of:

- `order_type`, `time_in_force`, `broker_route`, `broker_id`,
  `account_id`, `quantity_to_execute`, `broker_payload`,
  `order_ticket`, `execution_id`, `fill_price`
- Their human-readable label variants
  (`Broker route`, `Account ID`, `Time in force`, `Order ticket`,
  `Execution ID`, `Quantity to execute`).

### 14.5 Fail-closed behavior

If `build_default_cockpit_demo_pack()` raises, the page renders an
error block and stops. It does **not** retry with a live source,
does **not** call any LLM or API, and does **not** silently fall
back to any other data path.

---

## 15. Acceptance criteria

Phase 5H is accepted when:

1. `pages/7_Investment_Cockpit.py` exists and consumes only the
   Phase 5G fixture demo pack and the Phase 5B / 5C / 5D view
   contracts.
2. The page exposes the eight required tabs (Overview / Safety,
   Company Research Hub, Horizon Cards, ThesisTracker, Portfolio /
   TradePlan, Option Overlay, Feedback / Agent Evaluation,
   Provenance / Diagnostics).
3. The page surfaces a visible safety banner with the required
   wording bullets and surfaces both the pack-level and scenario-
   level Phase 5G safety banner values.
4. The page exposes a scenario selector defaulting to the complete
   scenario (`FIXTKR`), with the degraded scenario (`FIXDEG`)
   available.
5. The page handles the degraded scenario safely — missing financial
   panel, missing long-horizon thesis, and `no_trade` option overlay
   are all rendered without fabricated content.
6. The page contains no `import` or `from` reference to live runtime
   modules (`lib.workflow_state`, `lib.llm_orchestrator`,
   `lib.data_fetcher`, `lib.valuation`, `lib.technical`,
   `lib.rotation`, `lib.cache_manager`,
   `lib.reliability.integration_boundary`, `anthropic`, `openai`).
7. The page contains no actual file-open pattern targeting
   `research/.workflow_state.json`.
8. The page contains no order-ticket-like field names or labels.
9. The page does not positively authorize `approved_for_execution`.
10. `scripts/test_reliability_phase_5h_cockpit_ui_preview.py` passes
    all assertions.
11. `scripts/test_reliability_phase_5g_cockpit_demo_pack.py` still
    passes 344/344.
12. No existing live runtime file is modified.
13. State files (`PROJECT_STATE.md`, `CURRENT_TASK.md`) mark Phase
    5G as Accepted and Phase 5H as Implemented — Awaiting Codex
    Review.

---

## 16. Future Phase 5I dependency

> **Superseded note (Phase 5I review cleanup, 2026-05-28):** the framing in this
> section — "Phase 5I — Read-only Shadow Integration" — is **historical /
> superseded**. The accepted Phase 5I is **"Investment Cockpit Product Logic
> Reconciliation / Opportunity-first + Horizon-aware Architecture"**
> (`docs/reliability_phase_5i_investment_cockpit_product_logic_reconciliation.md`).
> Read-only shadow integration is no longer the immediate next step; it may
> still happen later, but only after the opportunity-first / horizon-aware
> product logic is established. The shadow-integration description below remains
> accurate as a future capability sketch, just not as the Phase 5I label.

Phase 5I — Read-only Shadow Integration — is **not started**. Phase
5I would (in a future, separately scoped phase):

- Activate the Phase 5F shadow-mode runtime planning.
- Add a read-only snapshot adapter that converts completed live
  five-step workflow output into an `ExistingWorkflowSnapshot`
  without mutating the live workflow.
- Route that snapshot through Phase 5A / 5B / 5C / 5D into the same
  view-model classes the Phase 5H cockpit page already renders.
- Continue to honor every Phase 5A–5H guardrail (no modifications to
  `app.py`, `pages/1_Overview.py`…`pages/6_PriceVolume.py`,
  `lib/llm_orchestrator.py`, `lib/workflow_state.py`, etc.; no live
  LLM call from cockpit code; no broker / order / execution path;
  `approved_for_execution` remains `False`).

Phase 5H itself does not start Phase 5I.

---

## 17. Validation

```bash
python3 scripts/test_reliability_phase_5h_cockpit_ui_preview.py
python3 scripts/test_reliability_phase_5g_cockpit_demo_pack.py
```

At Phase 5H implementation time:

- `scripts/test_reliability_phase_5h_cockpit_ui_preview.py` — 170/170
  assertions passing.
- `scripts/test_reliability_phase_5g_cockpit_demo_pack.py` — 344/344
  assertions passing.

At Phase 5H.1 implementation time (see Section 18):

- `scripts/test_reliability_phase_5h_cockpit_ui_preview.py` — 226/226
  assertions passing (sections 5/6 reshaped to TRANSLATIONS-backed
  bilingual checks; new section 14 adds AppTest-driven render
  verification in both EN and ZH).
- `scripts/test_reliability_phase_5g_cockpit_demo_pack.py` — 344/344
  assertions passing (unchanged).
- `scripts/test_reliability_phase_5a_memory_query.py` — 175/175
  assertions passing (regression).

---

## 18. Phase 5H.1 — Cockpit Page Runtime Fix + Bilingual Surface

**Date**: 2026-05-27
**Status**: Implemented — awaiting Codex review.
**Type**: Follow-up runtime / coverage / bilingual pass on the Phase 5H
page; strictly additive to `ui_utils.TRANSLATIONS`; no new live runtime
file; no schema change to Phase 5G.

Phase 5H shipped with three defects discovered during user-facing
verification on 2026-05-27. None were caught by the static Phase 5H test
suite:

1. **Runtime contradiction** — the page cached
   `pack.model_dump(mode="json")` via `@st.cache_data` and then rebuilt
   the Pydantic pack with `CockpitDemoPack.model_validate(dump)`. The
   Phase 5G schema declares
   `OriginalWorkflowDemoFixture.adapter: InMemoryWorkflowToMemoryAdapter
   = Field(exclude=True)` and
   `MemoryDemoFixtureBundle.memory_store: FixtureBackedMemoryStore =
   Field(exclude=True)` — fields are required but excluded from JSON
   output. The dump-then-rehydrate round trip cannot succeed by
   construction. The page hit its fail-closed branch on every render.
2. **Sidebar entry missing** — `.streamlit/config.toml` sets
   `showSidebarNavigation = false`, and `ui_utils.render_sidebar` builds
   a fully custom bilingual sidebar via hand-rolled `st.page_link` calls
   that only enumerated `app.py` + pages 1-6. The new page was reachable
   only by direct URL.
3. **No bilingual surface** — every user-facing string on the page was
   an English literal. The app's language toggle (which lives in
   `ui_utils.render_sidebar`) had no effect on the cockpit page, and the
   cockpit page never called `apply_theme()` / `render_sidebar()` so the
   language toggle was not even visible while on the cockpit page.

### 18.1 Scope of Phase 5H.1

| File | Change |
|------|--------|
| `pages/7_Investment_Cockpit.py` | Replaced `@st.cache_data` + `model_dump`/`model_validate` round-trip with `@st.cache_resource` returning the live `CockpitDemoPack`. Added `apply_theme()` + `render_sidebar()` bootstrap at module top. Every user-facing string now routes through `ui_utils.t()`. Fail-closed branch preserved; no LLM/API fallback. |
| `ui_utils.py` | Strictly additive. Added one `st.page_link("pages/7_Investment_Cockpit.py", label=t("nav_p7"))` line to `render_sidebar` after the page-6 entry. Added `nav_p7` and ~140 `cockpit_*` translation keys to both `TRANSLATIONS["en"]` and `TRANSLATIONS["zh"]` blocks for page title, subtitle, scenario selector, safety banner (headline + 6 bullets + 2 captions), 8 tab labels, section subheaders, missing-data warnings, no-trade overlay copy, provenance / fail-closed messages. No existing key renamed or removed. |
| `scripts/test_reliability_phase_5h_cockpit_ui_preview.py` | Reshaped Sections 5 and 6 to assert against `ui_utils.TRANSLATIONS[en]/[zh]` instead of literal page source (the literals moved to the translation dict). Added Section 6.d/e/f asserting `nav_p7` exists in both languages and that the sidebar registers the new page. Added Section 14 — `streamlit.testing.v1.AppTest`-driven render verification in EN and ZH: asserts no exception, asserts every required EN tab label appears in rendered subheaders, asserts every required ZH tab label appears, asserts no positive `approved_for_execution=True` appears in any rendered element. AppTest monkey-patches `ui_utils.render_sidebar` / `ui_utils.apply_theme` to no-ops for the test run only (AppTest does not provide a multi-page-app context, so `st.page_link()` raises `KeyError: 'url_pathname'` there — known AppTest limitation, not a page bug). |
| `docs/reliability_phase_5h_controlled_streamlit_cockpit_ui.md` | This Section 18 + Section 17 validation count update. No earlier sections modified. |
| `docs/ai_dev_state/PROJECT_STATE.md` | Phase 5H.1 row added; Phase 5H entry annotated as superseded by 5H.1. |
| `docs/ai_dev_state/CURRENT_TASK.md` | Phase 5H.1 status / next-action update. |

### 18.2 Files NOT touched

`app.py`, `pages/1_Overview.py` … `pages/6_PriceVolume.py`,
`lib/llm_orchestrator.py`, `lib/valuation.py`, `lib/technical.py`,
`lib/rotation.py`, `lib/data_fetcher.py`, `lib/workflow_state.py`,
`lib/cache_manager.py`, `lib/reliability/integration_boundary.py`
(Phase 4A, frozen), `lib/reliability/phase5_demo_pack.py` (Phase 5G
schema unchanged — no `Field(exclude=True)` mutation), `.claude/agents/*`,
existing live prompt files, `research/.workflow_state.json`,
`.streamlit/config.toml`.

### 18.3 Bilingual scope (what is and is not translated)

**Translated** (routed through `t()`): page title, subtitle, scenario
selector label + help text, sidebar pack/scenario id captions, sidebar
data-source caption, safety banner headline + 6 bullets + 2 captions,
all eight tab labels, every section subheader, every section's
populated/status/direction/confidence row labels, missing-data warnings,
horizon-card review-needed/missing-evidence/next-action labels,
trade-plan/option-overlay decision/strategy/risk-reward labels,
no-trade overlay copy, feedback/agent-evaluation labels,
provenance/validation panel headers, fail-closed headline + note.

**Not translated** (intentional, by design):

- Fixture content inside the demo pack — ticker symbols (`FIXTKR`,
  `FIXDEG`), run IDs, fixture thesis text, JSON dumps of
  `DemoSafetyBanner` / `DemoDataProvenance` / `DemoPackValidationSummary`.
  This is deterministic demo data; translating it would (a) corrupt the
  demo, (b) break the Phase 5G accepted contract, and (c) misleadingly
  imply real bilingual content.
- Phase 5D `ExecutionSafetyBannerView.message` — comes from the Phase 5D
  contract, not from page chrome.
- Schema-level identifiers when surfaced as field labels
  (`approved_for_execution`, `no_trade`, `no_external_api`, etc.). These
  are contract identifiers, not natural language.
- Some inline rendering text in trade-plan / risk-budget / cash-impact
  rows (e.g. `Max risk budget %`, `Min projected cash %`,
  `Max portfolio loss %`, `Total cash impact`, `High / medium / low /
  unknown risk counts`) — these are metric labels closely tied to the
  Phase 5D contract field names. They remain English to stay aligned
  with the underlying schema.
- **Table column header keys** in `st.table(...)` rows (e.g. `target`,
  `horizon`, `status`, `direction`, `confidence`, `kind`, `label`,
  `pct`, `value`, `note`, `target_alloc_pct`, `actual_alloc_pct`,
  `review_needed`, `next_action`) — these are **dict keys that mirror
  Phase 5B/5C/5D ViewModel field names**, not page chrome. They are
  intentionally left as schema identifiers so the table stays a faithful,
  reviewer-legible projection of the underlying contract fields.
- **Inline diagnostic field labels** rendered as `field=value` (e.g.
  `decision=`, `actor=`, `grade=`, `outcome=`, `importance=`, `type=`,
  `is_non_executable=`, `requires_human_review=`) — these are
  Phase 4M / Phase 5D **schema field identifiers** surfaced verbatim for
  provenance/diagnostic transparency, not natural-language UI copy.

> **Phase 5H.1 cleanup decision (Phase 5I review pass):** rather than
> route the schema-identifier table-column keys and `field=value`
> diagnostic labels above through `t()` — which would (a) decouple them
> from the Phase 5B/5C/5D contract field names they intentionally mirror
> and (b) constitute a broad page refactor outside the Phase 5H.1 scope —
> they are **deliberately retained as schema/fixture identifiers** and
> documented here. The translated page chrome (titles, subheaders, tab
> labels, warnings, captions, fail-closed copy) remains fully bilingual.

### 18.4 Invariants preserved

- `approved_for_execution` never positively authorized. It is surfaced
  only as a dynamic JSON value from `DemoSafetyBanner` (always `False`).
  Test Section 14.x asserts no positive form (`approved_for_execution=True`,
  `approved_for_execution: True`, etc.) appears in any rendered element.
- `no_trade` remains a first-class option overlay state. The Option
  Overlay tab renders `no_trade` with a populated `NoTradeReasonView`
  using `cockpit_option_no_trade_msg` + `cockpit_option_no_trade_reason`
  translations. Phase 5H.1 never infers a substitute strategy.
- No live LLM / external API / broker / order routing / persistence /
  database / vector store introduced. No Phase 4A
  (`lib/reliability/integration_boundary.py`) import.
- `research/.workflow_state.json` not read.
- Fail-closed behavior unchanged: on demo-pack builder error, the page
  shows the error block and stops, with no fallback path.

### 18.5 Known AppTest limitation (test environment, not page)

`streamlit.testing.v1.AppTest` does not provide a multi-page-app runtime
context. As a result, calling `st.page_link()` inside an AppTest run
raises `KeyError: 'url_pathname'` from
`streamlit/elements/widgets/button.py:_page_link`. This is purely a test
harness limitation — `st.page_link()` works correctly in the actual
running Streamlit server. To exercise the cockpit page's tab rendering
inside AppTest, Section 14 monkey-patches `ui_utils.render_sidebar` and
`ui_utils.apply_theme` to no-ops for the duration of the AppTest run
and restores them in a `finally` block. The patch never affects the
production runtime.

### 18.6 Acceptance criteria

Phase 5H.1 is accepted when:

1. `pages/7_Investment_Cockpit.py` renders successfully in production
   Streamlit for both the complete (`FIXTKR`) and degraded (`FIXDEG`)
   scenarios — no `ValidationError`, no fail-closed fallback during
   normal demo-pack builds.
2. The "🧭 Investment Cockpit" / "🧭 投研中枢" entry appears in the
   bilingual sidebar on every page, including the cockpit page itself.
3. Toggling EN ↔ ZH on the cockpit page swaps every page-chrome string
   (title, subtitle, scenario selector, safety banner, tab labels,
   section headers, warnings, fail-closed copy). Fixture content
   (tickers, run IDs, fixture text, JSON dumps) stays in its original
   deterministic form.
4. `scripts/test_reliability_phase_5h_cockpit_ui_preview.py` passes
   226/226.
5. `scripts/test_reliability_phase_5g_cockpit_demo_pack.py` still passes
   344/344.
6. `scripts/test_reliability_phase_5a_memory_query.py` still passes
   175/175 (regression).
7. No existing live runtime file modified; no Phase 5G schema change;
   no Phase 4A wiring; no new live LLM / API / broker / persistence
   path; `approved_for_execution` invariant preserved; `no_trade`
   invariant preserved.
