# Phase 5R — UI/UX Visual Polish + Demo Readiness

**Status**: Implemented — awaiting Codex review.

**Scope**: Product-facing UI/UX polish + demo readiness for the two Phase 5
product pages only:

- `pages/7_Investment_Cockpit.py`
- `pages/8_Macro_Dashboard.py`
- `ui_utils.py` (additive EN/ZH chrome keys only)

---

## Purpose

Phase 5R polishes the product-facing Phase 5 UI so the Investment Cockpit and
the Macro Dashboard are easier to **demo and understand**, without changing any
product logic or data contract. It improves the read order / visual hierarchy
of the pages, standardizes the bilingual demo-readiness copy, and adds a concise
"How to read this page" / demo-walkthrough expander to both pages.

Phase 5R is **UI/UX polish and demo readiness only**. It does not change
investment logic, scoring logic, schema meaning, agent contracts, queue logic,
research-pack logic, debate logic, feedback semantics, or macro-regime
interpretation. The deterministic view-model contracts from Phase 5B/5C/5D/5J/
5K/5L/5M and the macro view-models from Phase 5O are surfaced exactly as before.

---

## Relationship to Phase 5I product logic

Phase 5I established the opportunity-first + horizon-aware product logic
reconciliation for the Investment Cockpit. Phase 5R preserves that product logic
unchanged: the demo walkthrough explicitly names the opportunity-first,
horizon-aware reading order (Market Themes → Opportunity Queue → Research Pack →
Agent Debate → Decision Workspace → Review). No scoring, ranking, horizon, or
decision-state meaning is altered.

## Relationship to Phase 5N Investment Cockpit UI v0.2

Phase 5N delivered the opportunity-first v0.2 cockpit page and its ten-tab
structure. Phase 5R keeps every Phase 5N tab key, EN/ZH tab label, and tab
ordering unchanged (asserted by the Phase 5R test). The only additions are a
top-of-page demo-walkthrough expander and additive `cockpit_walkthrough_*`
EN/ZH chrome keys. The Phase 5N bilingual rule — fixture IDs, tickers, run IDs,
enum/schema values, and JSON keys remain untranslated — is preserved.

## Relationship to Phase 5O Macro Dashboard

Phase 5O (and the Phase 5O.1 Macro Indicator expansion) delivered the
fixture-only macro dashboard and its ten-tab structure. Phase 5R keeps every
macro tab key, EN/ZH tab label, and ordering unchanged and adds a top-of-page
demo-walkthrough expander plus additive `macro_walkthrough_*` EN/ZH chrome keys.
The macro-first context framing and the "posture is review-only, never a final
buy/sell decision" boundary are reinforced, not changed.

## Relationship to Phase 5Q Human Feedback UI

Phase 5Q added the session-only / non-persistent / non-executable human-feedback
review surface in the cockpit Feedback / Review tab. Phase 5R leaves the Phase
5Q form, session-state key (`phase5q_feedback_session`), action vocabulary, and
session-only safety banner unchanged. The walkthrough's "Feedback / Review"
step describes the session-only, non-persistent behavior so a demo viewer
understands nothing is stored.

---

## Visual hierarchy changes

- Both pages now open with a consistent, bilingual **"How to read this page
  (demo walkthrough)"** expander rendered immediately under the page title /
  subtitle and above the tab strip, so it is visible regardless of which tab is
  active.
- The walkthrough lays out the intended read order as a short, ordered set of
  one-line step descriptions, clarifying the opportunity-first (cockpit) and
  macro-first (macro) flow.
- Cross-page terminology is coherent: **opportunity-first**, **horizon-aware**,
  **fixture/demo only**, **review-only**, **non-executable**. The Phase 5P
  sidebar labels are unchanged.

## Card / table / metric polish

Phase 5R relies on the existing Streamlit-native presentation already used by
the pages — bordered `st.container`s for cards, `st.columns` + `st.metric` for
metric rows, `st.table` for tabular data, `st.caption` for secondary text, and
`st.expander` for drill-down detail. No heavy custom CSS is introduced; the
project-standard theme from `ui_utils.apply_theme()` continues to style metric
cards, tables, expanders, and tabs. Existing values, column names, and model
meanings are preserved exactly.

## Safety banner treatment

The standardized safety treatment is preserved and reinforced:

- Cockpit: the opportunity-first safety headline + bullets, the Phase 5D
  execution-safety banner ("review-only planning view — not an order ticket"),
  and the Phase 5Q session-only feedback safety banner all remain.
- Macro: the macro safety headline + bullets and the "posture is not a decision"
  boundary remain.
- The walkthrough adds a single concise safety summary line per page
  (`*_walkthrough_safety`) restating fixture/demo only, review-only,
  non-executable, no live workflow / LLM / external API / broker / order, and
  "not investment advice". `approved_for_execution` remains False or absent
  everywhere and is never positively authorized.

## Bilingual copy polish

All new user-facing chrome routes through `ui_utils.t()` with additive EN/ZH
keys (`cockpit_walkthrough_*`, `macro_walkthrough_*`) added to both
`TRANSLATIONS["en"]` and `TRANSLATIONS["zh"]`. No existing key is renamed or
removed. Fixture IDs, tickers, enum/schema values, run IDs, JSON keys, and
deterministic fixture content remain untranslated.

## Demo walkthrough behavior

The walkthrough is a static, read-only `st.expander`. It explains:

- fixture-only data (deterministic, offline);
- the opportunity-first flow (cockpit) / macro-first context (macro);
- the review-only nature of every output;
- that nothing executes and nothing is persisted.

It introduces **no** onboarding state, no persistence, and no tracking — the
copy is static and lives only in `TRANSLATIONS`.

## Empty / degraded state treatment

Phase 5R does not change the degraded/empty behavior already implemented in
Phase 5N / 5O / 5Q: the degraded fixture scenario, missing macro indicators /
factors, missing evidence, `research_more`, `no_trade`, and unresolved conflicts
continue to render through their existing safe, descriptive view-model paths.
The walkthrough helps a demo viewer interpret these states by framing the page
as review-only fixture data. AppTest coverage continues to render the degraded
cockpit scenario without exception (Phase 5N / 5Q tests).

---

## Non-goals

- No change to investment logic, scoring, schema meaning, agent contracts,
  queue logic, research-pack logic, debate logic, feedback semantics, or
  macro-regime interpretation.
- No live workflow integration, LLM call, or external/market/news API call.
- No DB, vector store, or production persistence.
- No broker / order / execution capability; no order tickets, broker payloads,
  account IDs, order fields, execution IDs, or executable trade instructions.
- No real onboarding / persistence system.
- No Phase 5S productization closeout.

## Guardrails

- `app.py`, pages 1–6, `lib/llm_orchestrator.py`, `lib/workflow_state.py`, and
  `.claude/agents/*` are not modified.
- Only `pages/7_Investment_Cockpit.py`, `pages/8_Macro_Dashboard.py`, and
  additive `ui_utils.py` chrome keys are touched.
- `approved_for_execution` remains False or absent and is never positively
  authorized.
- No buy/sell/order instruction is produced.
- Phase 5P sidebar labels are unchanged; Phase 4A is not wired in.

## Acceptance criteria

1. `pages/7_Investment_Cockpit.py` and `pages/8_Macro_Dashboard.py` still
   compile.
2. Both pages call `apply_theme()` and `render_sidebar()`.
3. Both pages contain a demo-walkthrough / how-to-read section.
4. Both pages retain their safety boundaries.
5. Neither page imports `lib/workflow_state.py` or `lib/llm_orchestrator.py`,
   calls an external API, or reads/writes `research/.workflow_state.json`.
6. EN/ZH translation keys exist for all new chrome and are referenced by the
   pages.
7. AppTest renders the Investment Cockpit and the Macro Dashboard in EN and ZH
   without exception.
8. No positive `approved_for_execution=True`; no order-ticket-like fields.
9. The Phase 5Q, Phase 5N, and Phase 5O regression tests still pass.

Validated by `scripts/test_reliability_phase_5r_ui_ux_polish.py`.

## Future Phase 5S dependency

After Phase 5R is accepted, the next recommended phase is **Phase 5S — Phase 5
Productization Closeout**, which would consolidate the Phase 5 deliverables and
documentation. Phase 5S has **not** started and must not be started until Phase
5R is accepted.
