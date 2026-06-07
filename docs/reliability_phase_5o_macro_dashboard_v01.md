# Phase 5O — Macro Dashboard v0.1

**Status**: Accepted (Codex verdict PASS). Phase 5O.1 — Macro Indicator
Expansion — Accepted (see the Phase 5O.1 section below).

**Deliverables**

- `lib/reliability/phase5_macro_dashboard.py` — macro-regime view-model layer
  (Pydantic schema / contracts + deterministic fixture builders).
- `pages/8_Macro_Dashboard.py` — additive, fixture-only Streamlit page.
- `ui_utils.py` — additive EN/ZH `macro_*` chrome keys + `nav_p8` + sidebar
  registration of the new page (no existing key renamed or removed).
- `scripts/test_reliability_phase_5o_macro_dashboard.py` — test suite.
- Additive Phase 5O exports in `lib/reliability/__init__.py`.

---

## Purpose

Phase 5O creates the first additive **Macro Dashboard** page and a macro-regime
view-model layer that elevates macro from a subsection inside Sector Research
into a **first-class upstream input** for the Investment Cockpit.

This phase makes macro visible and product-ready while remaining strictly
**fixture-backed / offline / mock-only / review-only**. It does not retrieve
live macro data, does not call any LLM or external API, does not introduce any
broker / order / execution capability, and does not produce final buy/sell
decisions.

Macro regime context is intended to influence whether the Investment Cockpit
favors:

- momentum trades,
- pullback entries,
- watchlist-only posture,
- risk-off / cash preservation (risk reduction),
- long-term accumulation.

These are **review-only posture leanings**, not trade instructions.

---

## Why macro is first-class

Opportunity selection without a macro read is fragile: the same ticker is a
momentum buy in a risk-on, liquidity-expanding regime and a watchlist-only name
in a risk-off, liquidity-tightening regime. Phase 5O therefore models macro as a
**first-class** upstream gate:

1. Read the macro regime (rates, inflation, liquidity, credit, volatility,
   breadth, dollar, risk appetite, earnings cycle, growth regime, policy risk).
2. Derive a regime **status** and horizon-specific **bias**.
3. Express a review-only opportunity **posture** and fixture-only **theme
   implications**.
4. Feed that context (later) into Theme Intelligence (Phase 5J) and the
   Opportunity Queue (Phase 5K).

Macro is context, not a decision: it never authorizes execution and never emits
a buy/sell call.

## Why this is fixture-only

Phase 5O is deliberately **fixture-only**. Live macro data retrieval, real-time
monitoring, and shadow integration are explicitly out of scope for this phase
(they are later-phase concerns). The deterministic fixtures let the product
surface and the contracts be reviewed without any external dependency, any
network call, or any risk of leaking an executable path. Every model sets
`extra="forbid"` and no model declares `approved_for_execution`, so the
non-execution invariant holds **by construction**.

---

## Relationship to Phase 5I product logic

Phase 5I (Investment Cockpit Product Logic Reconciliation) established the
Cockpit as **opportunity-first / macro-theme-aware / horizon-aware** and called
for macro-first gating ("read the regime before chasing the theme"). Phase 5O is
the first concrete, product-ready realization of that macro-first gating layer:
it provides the macro regime view-model that the opportunity-first Cockpit
described in Phase 5I/5N can consume as upstream context.

## Relationship to Phase 5J Theme Intelligence

Phase 5J defines Theme Intelligence / Market Heat (themes, heat scores,
industry-chain decomposition, candidate tickers). Phase 5O sits **upstream** of
Phase 5J: macro regime context informs which themes are tailwinds vs headwinds.
Phase 5O surfaces fixture-only **theme implications** (`MacroThemeImplicationView`)
that reference Phase 5J-style theme names, but Phase 5O **does not rewire Phase
5J runtime logic** — the relationship is by fixture / view-model reference only.

## Relationship to Phase 5K Opportunity Queue

Phase 5K converts theme records into horizon-aware opportunity queues. Phase 5O
provides the macro **horizon bias** and **opportunity posture** that should
later weight the Phase 5K queues (e.g. risk-off macro pushes candidates toward
watch/research_more; tightening liquidity penalizes long-duration entry
quality). Phase 5O **does not modify Phase 5K runtime logic**; it expresses the
context Phase 5K could consume.

## Relationship to Phase 5N Cockpit UI v0.2

Phase 5N redesigned `pages/7_Investment_Cockpit.py` into the opportunity-first
v0.2 cockpit (Market Themes / Opportunity Queue / Decision Workspace / ...).
Phase 5O is **additive and parallel**: it adds a *separate* `pages/8_Macro_
Dashboard.py` and does not modify the Phase 5N cockpit page. The macro dashboard
is the upstream regime context that a future cockpit revision could fold into
its Market Themes / Opportunity Queue tabs.

---

## Macro factor taxonomy

`MacroRegimeSnapshot.factors` is a flat list of `MacroRegimeFactorView`s. The
**required** factors (`REQUIRED_MACRO_FACTORS`) are:

| Factor (`MacroFactorKind`) | Meaning |
|---|---|
| `rates` | Policy & long-end rates |
| `inflation` | Inflation trajectory |
| `liquidity` | Net liquidity (expanding / tightening) |
| `credit_spreads` | IG / HY credit spreads (widening / narrowing) |
| `volatility` | Volatility / VIX |
| `market_breadth` | Participation / breadth |
| `dollar` | US dollar (DXY) |
| `risk_appetite` | Aggregate risk appetite |
| `earnings_cycle` | Earnings cycle / revision direction |
| `growth_regime` | Growth / recession regime |
| `policy_risk` | Monetary / fiscal / regulatory policy risk |

Each factor carries a `trend` (`MacroFactorTrend`: expanding / tightening /
rising / falling / widening / narrowing / improving / deteriorating / stable /
mixed / unknown), a `signal` (`MacroFactorSignal`: supportive / neutral /
headwind / mixed / unknown), and a fixture `value_placeholder` (a descriptor
string, **never** a computed indicator value). `is_live_data` is permanently
`False`.

Section views group factors for display: `MacroRatesInflationView`,
`MacroLiquidityView`, `MacroCreditVolatilityView`, `MacroMarketBreadthView`,
`MacroDollarView`, `MacroRiskAppetiteView`, `MacroEarningsCycleView`,
`MacroPolicyRiskView`.

## Regime status

`MacroRegimeStatus` carries a `primary_status` plus `supporting_statuses` drawn
from `MacroRegimeStatusLabel`:

`risk_on`, `risk_off`, `neutral`, `transition`, `liquidity_expanding`,
`liquidity_tightening`, `inflation_pressure`, `growth_slowdown`,
`earnings_revision_positive`, `earnings_revision_negative`, `unknown`.

`unknown` is a first-class state for degraded data — the dashboard never infers
`neutral` from missing factors (`is_decision` is permanently `False`).

## Horizon bias semantics

`MacroHorizonBiasView` expresses horizon-specific leanings
(`short_term_bias` / `mid_term_bias` / `long_term_bias`), each drawn from the
review-only posture vocabulary (`MacroHorizonBiasLabel`). Examples encoded in
the fixtures:

- **risk-on + improving breadth** → short-term `favor_momentum_trades`.
- **risk-on but overextended / volatility rising** → `favor_pullback_entries`.
- **risk-off** → `favor_watchlist_only` / `favor_risk_reduction` / `research_more`.
- **liquidity improving** → long-term `favor_long_term_accumulation`.
- **tightening liquidity / rising rates** → penalizes long-duration growth entry
  quality (research_more / risk reduction).

The same regime can favor momentum short-term and accumulation long-term —
horizon bias is intentionally not a single global verdict.

## Opportunity posture semantics

`MacroOpportunityPostureView` produces review-only posture guidance
(`MacroOpportunityPosture`):

`favor_momentum_trades`, `favor_pullback_entries`, `favor_watchlist_only`,
`favor_risk_reduction`, `favor_long_term_accumulation`, `research_more`,
`unknown`.

The model carries assertable invariants: `is_buy_signal=False`,
`is_executable=False`, `produces_final_decision=False`,
`requires_human_review=True`. **These are not trade instructions.** The posture
vocabulary contains no execution verbs (no "buy" / "sell" / "execute" / "order").

## Theme implications

`MacroThemeImplicationView` exposes fixture-only macro implications for themes
(AI infrastructure, data-center power, memory / HBM, optical networking, space,
embodied AI / robotics, biotech, nuclear / energy). Each carries an `implication`
(`tailwind` / `headwind` / `neutral` / `mixed` / `unknown`) and a rationale.
`is_live_market_claim` is permanently `False` — these are example relationships,
not current market facts or buy/sell calls.

---

## UI page structure

`pages/8_Macro_Dashboard.py` calls `apply_theme()` + `render_sidebar()`, routes
every chrome string through `ui_utils.t()`, registers in the custom sidebar via
`nav_p8`, and exposes a fixture scenario selector
(`risk_on` / `risk_off` / `transition` / `degraded`, defaulting to `risk_on`).
Tabs:

1. **Overview / Safety** — safety banner + regime status + scenario identity.
2. **Macro Regime** — primary/supporting status + every factor view.
3. **Liquidity / Rates / Inflation** — the dominant macro drivers.
4. **Credit / Volatility / Breadth** — confirm/diverge signals + dollar.
5. **Risk Appetite** — risk state + earnings cycle + growth regime + policy risk.
6. **Horizon Bias** — short / mid / long bias + rationale.
7. **Theme Implications** — fixture-only theme tailwind/headwind table.
8. **Opportunity Posture** — review-only posture + non-executability evidence.
9. **Provenance / Diagnostics** — validation summary + safety banner JSON +
   missing-factor surfacing + source fixture reference.

The page **fails closed** with a visible warning if fixture construction fails;
there is no fallback to live data, an LLM, or an external API.

## Bilingual rules

All page chrome routes through `t()` and has EN + ZH entries in
`ui_utils.TRANSLATIONS`. Fixture content (factor descriptors, theme names,
regime labels, JSON dumps, schema identifiers such as `is_buy_signal=`) is
intentionally **not** translated — it is deterministic demo data. The change to
`ui_utils.py` is strictly **additive** (no existing key renamed or removed), so
the Phase 5N cockpit page and its tests are unaffected.

## Safety boundaries

- Fixture/demo only — no live macro data wiring.
- No live macro API; no external API; no LLM.
- No broker / order / execution capability; no executable order fields.
- No reads of `research/.workflow_state.json`; no live workflow state.
- No DB / vector store / persistence; nothing written to disk.
- `approved_for_execution` is **absent** on every model (`extra="forbid"`) and
  surfaced on the page only as banner copy stating it is False/absent; it is
  **never** positively authorized.
- The macro dashboard produces **no final buy/sell decision** and emits no
  order instruction.

---

## Non-goals

- No live macro data retrieval (rates, inflation, liquidity, etc.).
- No real-time monitoring / alerts.
- No rewiring of Phase 5J Theme Intelligence or Phase 5K Opportunity Queue
  runtime logic (referenced by fixture / view-model only).
- No read-only shadow integration.
- No sidebar cleanup of the Financial / PriceVolume pages.
- No modification of `app.py`, pages 1–7, `lib/llm_orchestrator.py`,
  `lib/workflow_state.py`, or `.claude/agents/*`.
- No final buy/sell recommendation; no order ticket / broker payload.

## Guardrails

- New UI is limited to `pages/8_Macro_Dashboard.py`.
- `ui_utils.py` is touched only additively (sidebar registration + EN/ZH macro
  chrome keys + `nav_p8`).
- `lib/reliability/__init__.py` gains additive Phase 5O exports only.
- Every Phase 5O model sets `extra="forbid"`; no `approved_for_execution` field.
- Targeted forbidden live-runtime path checks must remain clean while unrelated
  dirty / untracked worktree items from earlier phases / local infrastructure
  may exist.

## Acceptance criteria

- `python3 -B scripts/test_reliability_phase_5o_macro_dashboard.py` passes.
- The default / risk_on / risk_off / transition / degraded macro fixtures build;
  the four required required factors and posture / horizon / theme contracts are
  present; the degraded fixture surfaces missing factors without fabrication.
- `pages/8_Macro_Dashboard.py` exists, compiles, registers via `nav_p8`, calls
  `apply_theme()` + `render_sidebar()`, uses `t()` for chrome, and renders in EN
  and ZH via `AppTest`.
- Phase 5N cockpit test (`scripts/test_reliability_phase_5n_cockpit_ui_v02.py`)
  still passes after the additive `ui_utils.py` / sidebar change.
- No `approved_for_execution=True`, no order-ticket fields, no external/macro API
  call, no live workflow-state read, no persistence/DB/vector store.

---

## Phase 5O.1 — Macro Indicator Expansion

**Status**: Accepted (additive enhancement on top of accepted Phase 5O).

### Why concrete indicators are needed

Phase 5O created the macro dashboard framework and a broad macro **factor**
taxonomy (rates, inflation, liquidity, credit, volatility, breadth, dollar,
risk appetite, earnings cycle, growth regime, policy risk), but it did not
explicitly model several concrete macro **instruments** and **economic-release**
indicators that users reason about directly. Phase 5O.1 adds those concrete
indicators as a dedicated, fixture-only **indicator panel** so the dashboard
speaks in the user's vocabulary (WTI, gold, Fear & Greed, QQQ, IWM, NFP, CPI,
PPI) while preserving every Phase 5O safety boundary.

### Indicator taxonomy

`MacroIndicatorPanel` groups eight concrete indicators
(`REQUIRED_MACRO_INDICATOR_KEYS`):

| Group | Indicators | Concrete view model |
|---|---|---|
| Commodities | WTI crude oil, Gold (GC) | `CommoditySignalView` |
| Risk appetite / leadership | CNN Fear & Greed, QQQ, IWM | `RiskSentimentSignalView`, `IndexRiskAppetiteSignalView` |
| Economic releases | NFP, CPI, PPI | `LaborMarketSignalView`, `InflationReleaseSignalView` |

Class hierarchy: `MacroIndicatorView` (base) → `MacroInstrumentSignalView`
(adds `symbol`) → `CommoditySignalView` / `IndexRiskAppetiteSignalView`;
`RiskSentimentSignalView` (base + sentiment); `MacroEconomicReleaseView` (base +
release fields) → `LaborMarketSignalView` / `InflationReleaseSignalView`. Each
indicator carries `indicator_id`, `indicator_key`, `display_name`, `category`,
`latest_value` / `fixture_value`, `trend`, `status`, `signal`,
`interpretation`, `macro_implication`, `horizon_implication`,
`source_type="fixture"`, `is_live_data=False`, `evidence_refs`, and `warnings`.

### Indicator interpretation (fixture-mapped)

- **WTI crude oil** — inflation pressure, growth sensitivity (demand proxy), and
  transportation / input-cost risk to margins.
- **Gold / GC** — safe-haven demand, real-rate sensitivity, dollar / risk-off
  proxy.
- **CNN Fear & Greed** — sentiment / risk appetite. *Greed* implies crowding
  (caution); *fear* implies risk-off or a contrarian watchlist context.
- **QQQ** — growth / large-cap tech / AI risk appetite; a narrow-leadership
  proxy.
- **IWM** — small-cap risk appetite; a breadth / broadening proxy.
- **NFP** — labor-market strength, Fed-reaction risk, growth resilience vs
  overheating risk.
- **CPI** — inflation pressure, rates sensitivity, long-duration growth
  valuation pressure.
- **PPI** — pipeline inflation, margin pressure, future CPI pass-through risk.

### Scenario behavior

- **Risk-on**: QQQ leading + IWM broadening (`supportive`), Fear & Greed in
  *greed* (crowding caution), disinflation (CPI/PPI `supportive`), resilient NFP
  with mild Fed-reaction risk, oil/gold firm. Panel `overall_signal=supportive`.
- **Risk-off**: QQQ/IWM weakening (poor breadth), Fear & Greed in *fear*, gold
  haven bid + weak oil (demand fears), cooling NFP, sticky/firming CPI/PPI.
  Panel `overall_signal=headwind`.
- **Transition**: overextended QQQ with unconfirmed IWM breadth, neutral
  sentiment, stalling disinflation, moderate NFP — `overall_signal=mixed`.
- **Degraded**: a few indicators present but `unknown` with warnings; the rest
  deliberately **missing** so the validator reports `missing_indicators` — never
  fabricated.

### Fixture-only boundary / no-live-API guarantee

Every indicator is fixture-only: `is_live_data=False` and
`source_type="fixture"` by construction; values are placeholder descriptors.
**No yfinance / Finnhub / FRED / CNN / news / external API is imported or
called.** No live macro data retrieval, no real-time monitoring, no DB / vector
store / persistence, no broker / order / execution, no LLM. Every indicator
model sets `extra="forbid"` and declares no `approved_for_execution` field.

### UI

`pages/8_Macro_Dashboard.py` adds a **Macro Indicators** tab (key
`macro_tab_indicators`) between Macro Regime and Liquidity, with three labelled
subsections (commodities; risk appetite / leadership; economic releases). All
new chrome routes through `ui_utils.t()` with additive EN/ZH `macro_*` keys; the
fixture/demo, non-live nature is stated in the section caption.

### Future live integration deferred

Live retrieval of these indicators (price feeds for WTI/gold/QQQ/IWM, the CNN
Fear & Greed value, and FRED/BLS economic releases for NFP/CPI/PPI) is
**deferred to a later controlled phase**. Phase 5O.1 remains fixture-only.

## Future Phase 5P dependency

After Phase 5O is accepted, the next recommended phase is **Phase 5P — Source
Page Navigation Cleanup** (e.g. consolidating Financial / PriceVolume entry
points now that the Cockpit and Macro Dashboard are the product-facing
surfaces). Phase 5O deliberately does **not** perform that sidebar cleanup;
Phase 5P has **not** started.
