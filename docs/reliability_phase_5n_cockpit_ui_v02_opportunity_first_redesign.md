# Phase 5N — Cockpit UI v0.2 Opportunity-first Redesign

**Status**: Implemented — awaiting Codex review.

**Scope**: Product-facing Streamlit UI update to
`pages/7_Investment_Cockpit.py` only (plus additive `ui_utils.py`
translation keys and tests/docs). Fixture/demo-only, offline/mock-only,
review-only. No live workflow, LLM, external API, DB, vector store,
persistence, or broker/order/execution is introduced.

---

## Purpose

Phase 5N redesigns the additive Investment Cockpit page from a
company/ticker-first research display (Phase 5H/5H.1) into an
**opportunity-first, macro/theme-aware, horizon-aware** decision cockpit.

The user no longer has to manually pick a ticker as the main path. Instead
the cockpit leads with market-level theme intelligence and a horizon-aware
opportunity queue, then bridges through an agent-debate / decision-workspace
review layer before surfacing company research, trade-plan, and option
overlays as review-only context.

The page remains a deterministic preview over **fixture-backed** Phase
5G–5M data. It does not call any LLM, external API, broker, or order router;
it does not read `research/.workflow_state.json`; it does not import
`lib/workflow_state.py` or `lib/llm_orchestrator.py`; it does not persist
anything. `approved_for_execution` is `False` (or absent) everywhere it
appears and is never positively authorized.

---

## Relationship to Phase 5I product logic

Phase 5I (Investment Cockpit Product Logic Reconciliation) established the
cockpit as **opportunity-first / macro-theme-aware / horizon-aware**, and
separated the *source research modules* from the *cockpit decision layer*.
Phase 5N is the first UI realization of that product logic: Market Themes
and Opportunity Queue lead the page, the old Company Research Hub is
repositioned as a downstream **Research Snapshot**, and the cockpit
explicitly distinguishes Theme Heat from Entry Quality ("avoiding the top").

## Relationship to Phase 5J Theme Intelligence

The **Market Themes** tab renders the Phase 5J
`ThemeIntelligenceSnapshot` produced by
`build_default_theme_intelligence_snapshot()`. It surfaces, per theme, the
lifecycle stage, heat score / status, subtheme and candidate-ticker counts,
crowding/risk warnings, the AI and Space **industry-chain decompositions**,
and the schema invariant that heat score is **not** a buy signal
(`ThemeHeatScore.is_buy_signal == False`, plus the
`entry_quality_placeholder.note` disclaimer).

## Relationship to Phase 5K Opportunity Queue

The **Opportunity Queue** tab renders the Phase 5K
`HorizonAwareOpportunityQueueView`
(`build_default_opportunity_queue_view()` /
`build_degraded_opportunity_queue_view()`): separate short-term,
mid-term, and long-term queues plus the cross-cutting Watch/Wait, Research
More, and No-Trade/Avoid queues, each candidate showing ticker, theme,
horizon, decision label, opportunity score, horizon fit, entry quality,
crowding risk, next action, and warnings. A cross-horizon comparison table
makes the "same ticker, different decision by horizon" property visible. The
tab explicitly states that high theme heat does **not** automatically imply
`trade_now`.

## Relationship to Phase 5L Research Pack

The **Research Snapshot** tab includes a Phase 5L research-pack module
coverage expander (`build_default_research_pack_bundle()` /
`build_degraded_research_pack_bundle()`): per-request horizon, decision
label, and the descriptive list of source modules a pack would draw on. The
module requests are descriptive (`is_runtime_call == False`) and module
result refs are placeholders (`is_placeholder == True`, `result_ref is
None`); no source module is ever called.

## Relationship to Phase 5M Agent Debate / Decision Workspace

The **Decision Workspace** and **Agent Debate** tabs render the Phase 5M
`AgentDebateWorkspace` (`build_default_agent_debate_workspace()` /
`build_degraded_agent_debate_workspace()`). Decision Workspace shows the
review-only recommendation state, status, consensus, evidence coverage,
unresolved conflicts, and review-only next action. Agent Debate shows the
bull/bear/risk/critic/allocation/option participant roles and stances (key
claims, risks, missing evidence, invalidation conditions, review triggers),
the critic's unresolved-conflict acknowledgement, and the explicit
non-executability of the allocation and option perspectives.

## Relationship to Phase 5H.1 controlled Streamlit page

Phase 5H.1 fixed the page's sidebar registration, bilingual chrome,
theme/sidebar bootstrap, and `@st.cache_resource` handling. Phase 5N
preserves all of that infrastructure — `apply_theme()` / `render_sidebar()`
bootstrap, the `@st.cache_resource` loader pattern, the `cockpit_*`
`ui_utils.t()` translation namespace, and the `nav_p7` sidebar entry — and
only changes the page's tab structure and the fixtures it consumes. The
Phase 5H test was reconciled (tab mapping + view-reference assertions) to the
v0.2 structure and still passes.

---

## Why v0.2 is opportunity-first

A ticker-first cockpit forces the user to already know what to look at. The
v0.2 cockpit instead starts from *where the market is hot* (Market Themes)
and *what is actionable by horizon* (Opportunity Queue), and only then drills
into a specific name's research, debate, and plan. This matches the Phase 5I
product logic: macro/theme context first, entry quality separated from heat,
and a review-only decision bridge before any company-level plan is shown.

---

## New tab / section structure

| # | Tab | Source |
|---|-----|--------|
| 1 | Overview / Safety | Phase 5G banners + flow |
| 2 | Market Themes | Phase 5J |
| 3 | Opportunity Queue | Phase 5K |
| 4 | Decision Workspace | Phase 5M |
| 5 | Research Snapshot | Phase 5B (+ 5C thesis, 5L pack coverage) |
| 6 | Agent Debate | Phase 5M |
| 7 | Trade / Allocation Plan | Phase 5D |
| 8 | Option Overlay | Phase 5D |
| 9 | Feedback / Review | Phase 4M-F / 4M-G fixtures |
| 10 | Provenance / Diagnostics | Phase 5G + 5J/5K/5L/5M validation |

Market Themes and Opportunity Queue appear **before** Research Snapshot. The
Company Research Hub is repositioned as the Research Snapshot tab; the old
`cockpit_tab_company` / `cockpit_tab_horizon` / `cockpit_tab_thesis` /
`cockpit_tab_portfolio` / `cockpit_tab_feedback` translation keys remain
defined in `ui_utils.TRANSLATIONS` (additive policy — nothing removed) but
are no longer presented as primary tabs.

### Overview / Safety behavior

Preserves the Phase 5H.1 safety banner (fixture/demo only, no live workflow
wiring, no external API, no broker/order, `approved_for_execution` False,
not investment advice). Adds an explicit opportunity-first v0.2 preview note
and shows the high-level flow: **Market Themes → Opportunity Queue →
Research Pack → Agent Debate → Decision Workspace → Review**. Shows the
selected scenario and demo provenance.

### Market Themes UI behavior

Renders the Phase 5J theme intelligence: one card per theme (AI, Space, and a
degraded/emerging theme) with lifecycle stage, heat score / status, subtheme
count, candidate count, and crowding/risk warnings; an industry-chain
decomposition expander; and a candidate-tickers expander. Heat-is-not-a-buy-
signal is stated explicitly and the entry-quality-deferred disclaimer is
surfaced. Fixture-only disclaimers preserved.

### Opportunity Queue UI behavior

Renders the Phase 5K view: short/mid/long-term queues and the cross-cutting
Watch/Wait, Research More, No-Trade/Avoid queues; per-candidate decision
label, opportunity score, horizon fit, entry quality, crowding risk, next
action, and warnings; and a cross-horizon comparison table. Explicitly notes
that high theme heat does not auto-imply `trade_now`.

### Decision Workspace UI behavior

Renders the Phase 5M `DecisionWorkspaceView`: workspace status,
recommendation/review state, review-only next action, consensus summary,
unresolved conflicts, evidence coverage, and the safety banner. Uses
review-only language; surfaces `is_executable_decision == False` and
`requires_human_review == True`. No buy/sell/order is shown.

### Research Snapshot repositioning

The old Company Research Hub content (Phase 5B equity / financial /
price-volume / source / evidence panels and missing-data warnings) is
repositioned here and labeled **Research Snapshot / Company Research
Snapshot**, with an explicit note that it summarizes source research-module
outputs rather than replacing or regenerating the original Equity Research. A
Phase 5C horizon-thesis snapshot expander and a Phase 5L research-pack module
coverage expander are included as source-output summaries. No live company
research is called.

### Agent Debate UI behavior

Renders the Phase 5M bull/bear/risk/critic/allocation/option perspectives:
participant roles, stance labels, confidence, key claims, risks, missing
evidence, invalidation conditions, and review triggers; `DebateConflictRecord`
entries; the critic's explicit unresolved-conflict / needs-more-evidence
acknowledgement; and clearly non-executable allocation and option
perspectives.

### Trade / Allocation and Option Overlay safety boundaries

The Phase 5D portfolio / trade plan view is rendered **after** the decision
workspace and debate, behind a visible boundary statement — *"Review-only
planning view — not an order ticket."* No broker route, account, time in
force, quantity to execute, execution id, or broker payload is displayed. The
Option Overlay preserves `no_trade` as a first-class state, shows option
state/strategy only when the fixture provides it, infers no substitute
strategy, and makes the no-execution wording visible.

---

## Bilingual acceptance rules

All new user-facing chrome strings route through `ui_utils.t()`. EN/ZH
translation keys for the new chrome are added to `ui_utils.TRANSLATIONS`
(additive only; no existing key renamed or removed). Fixture content (ticker
symbols, theme names, run IDs, deterministic fixture text), schema
identifiers (`approved_for_execution`, `no_trade`, `is_buy_signal`, JSON
keys, enum values), and JSON dumps are intentionally **not** translated. EN
and ZH `AppTest` render coverage is preserved.

## Fixture-only data flow

```
Phase 5G demo pack (scenario / safety / provenance / company / feedback)
Phase 5J build_default_theme_intelligence_snapshot()      → Market Themes
Phase 5K build_default/degraded_opportunity_queue_view()  → Opportunity Queue
Phase 5L build_default/degraded_research_pack_bundle()    → Research Snapshot
Phase 5M build_default/degraded_agent_debate_workspace()  → Decision / Debate
        │
        ▼
  pages/7_Investment_Cockpit.py  (st.cache_resource; fail-closed)
```

The Phase 5G demo pack does not bundle Phase 5J–5M artifacts, so the page
calls the deterministic Phase 5J–5M fixture builders directly, as permitted
by the Phase 5N task boundary. The scenario selector maps `complete` → the
default Phase 5K/5L/5M fixtures and `degraded` → the degraded fixtures;
Market Themes are market-level and always use the default snapshot (which
contains AI, Space, and a degraded/emerging theme).

---

## Non-goals

- No read-only shadow integration.
- No live Auto Research runtime; no live Agent runtime; no LLM call.
- No Macro Dashboard page (deferred to Phase 5O).
- No sidebar cleanup of Financial / PriceVolume.
- No changes to `app.py`, pages 1–6, the live five-step workflow,
  `lib/llm_orchestrator.py`, `lib/workflow_state.py`, or `.claude/agents/*`.
- No final executable buy/sell recommendation; no order instructions.

## Guardrails

- Only `pages/7_Investment_Cockpit.py` (UI) and `ui_utils.py` (additive
  translation keys) are modified for the live surface.
- No DB / vector store / production persistence; no file writes; no
  `research/.workflow_state.json` read.
- No broker/order/execution capability; no order tickets, broker payloads,
  account IDs, time-in-force, quantity-to-execute, or execution IDs.
- `approved_for_execution` remains `False` or absent and is never positively
  authorized.
- `no_trade` remains a first-class option overlay / decision state with no
  inferred substitute strategy.
- Fails closed on builder error — no LLM/API fallback.
- Phase 4A is not wired in and not imported.

## Acceptance criteria

- `pages/7_Investment_Cockpit.py` exists, compiles, and renders in EN and ZH
  via `AppTest` without exception, for both the complete and degraded
  scenarios.
- The page imports/uses the Phase 5G demo pack and the Phase 5J/5K/5L/5M
  fixture/view builders, and does not import live workflow / LLM /
  data-fetcher modules or read `research/.workflow_state.json`.
- The page presents the ten v0.2 tabs; Market Themes and Opportunity Queue
  precede Research Snapshot; Company Research Hub is repositioned as Research
  Snapshot and is no longer wired as a primary tab.
- New chrome translation keys exist in both EN and ZH; the safety banner
  still appears.
- No order-ticket-like fields; no positive `approved_for_execution=True`.
- Phase 5J/5K/5L/5M and Phase 5G fixture contracts build with their safety
  invariants intact.
- `scripts/test_reliability_phase_5n_cockpit_ui_v02.py` passes; the
  reconciled `scripts/test_reliability_phase_5h_cockpit_ui_preview.py` still
  passes; Phase 5J/5K/5L/5M suites still pass.

## Future Phase 5O dependency

Phase 5O — **Macro Dashboard v0.1** — will add macro regime / sector-bias
context as the upstream gating layer that feeds the Market Themes and
Opportunity Queue tabs. Phase 5N intentionally does **not** implement the
Macro Dashboard as a separate page; that is Phase 5O's scope and has not
started.
