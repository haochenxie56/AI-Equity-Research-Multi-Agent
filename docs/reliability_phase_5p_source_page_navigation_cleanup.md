# Phase 5P — Source Page Navigation Cleanup

**Status**: Implemented — awaiting Codex review.

**Deliverables**

- `ui_utils.py` — custom sidebar navigation cleanup in `render_sidebar()`
  (remove the two top-level source-page links; legacy-key documentation; no
  existing translation key renamed or removed).
- `docs/reliability_phase_5p_source_page_navigation_cleanup.md` — this document.
- `scripts/test_reliability_phase_5p_navigation_cleanup.py` — test suite.
- State-file reconciliation in `docs/ai_dev_state/PROJECT_STATE.md` and
  `docs/ai_dev_state/CURRENT_TASK.md`.

---

## Purpose

Phase 5P is a **navigation-cleanup-only** phase. It updates the hand-rolled
custom sidebar in `ui_utils.render_sidebar()` so that the **top-level**
application navigation reflects the current product model rather than the
original flat six-page source layout:

- **Financial Analysis** (`pages/5_Financial.py`) and **Price & Volume
  Analysis** (`pages/6_PriceVolume.py`) are **no longer top-level source
  pages**. They are subordinate **source sub-surfaces under Equity Research /
  个股研究**.
- **Macro Dashboard** (`pages/8_Macro_Dashboard.py`) is a **first-class
  top-level page** (introduced in Phase 5O / 5O.1).
- **Investment Cockpit** (`pages/7_Investment_Cockpit.py`) remains a
  **first-class top-level page** (introduced in Phase 5H/5H.1, redesigned in
  Phase 5N).

The page files for Financial and Price & Volume are **retained unchanged** and
their underlying functionality is **preserved** — only their top-level entries
in the custom sidebar are removed.

This phase introduces **no UI/UX visual polish** (deferred to Phase 5R), no live
integration, no shadow mode, no LLM call, no external API call, no DB / vector
store / persistence, and no broker / order / execution capability.

---

## Relationship to Phase 5I product logic

Phase 5I (Investment Cockpit Product Logic Reconciliation / Opportunity-first +
Horizon-aware Architecture) established that the system has two conceptual
layers:

1. **Source research modules** — the deterministic / LLM research surfaces that
   produce evidence (Overview / AI Research Workflow, Sector Research, Scanner,
   Equity Research and its company / financial / price-volume / news facets).
2. **The product-facing decision layer** — opportunity-first, macro/theme-aware,
   horizon-aware surfaces (Macro Dashboard, Investment Cockpit).

Phase 5I explicitly separated **source research modules** from the **Cockpit
decision layer** and noted that company-level financial and price-volume
analysis are *facets of equity research*, not independent top-level products.
Phase 5P is the navigation expression of that reconciliation: the top-level
sidebar should not duplicate Financial Analysis and Price & Volume Analysis as
separate first-class pages when they are conceptually integrated under Equity
Research.

Phase 5I deferred sidebar changes ("no sidebar change" was an explicit Phase 5I
non-goal); Phase 5P is the controlled, navigation-only follow-up that performs
exactly that change and nothing more.

---

## Relationship to the original README app

The original README app (see `README.md`) describes a six-page Streamlit
multi-page app driven by a five-step AI workflow:

| Page | Role |
|------|------|
| Overview | AI Research Workflow (five steps + synthesis) |
| Sector | Sector Research |
| Scanner | Stock Scanner |
| Equity | Equity Research |
| Financial | Financial Analysis (3-statement, DCF, relative valuation) |
| PriceVolume | Price & Volume / technical analysis |

In the original flat layout, Financial and PriceVolume were peers of the other
four pages. The five-step workflow itself already treats Financial Analysis
(Step 4) and Price & Volume Analysis (Step 5) as **stages that follow Equity
Research (Step 3)** for a single chosen ticker — i.e. they are downstream
facets of researching one company, not independent entry points. Phase 5P aligns
the *navigation* with that *workflow* reality. The pages and their workflow
behavior are untouched.

---

## Relationship to Phase 5O Macro Dashboard

Phase 5O (Macro Dashboard v0.1, Accepted) and Phase 5O.1 (Macro Indicator
Expansion, Accepted) added `pages/8_Macro_Dashboard.py` and registered it in the
custom sidebar via `nav_p8`. Phase 5P keeps Macro Dashboard as a first-class
top-level entry. No Phase 5O / 5O.1 module, fixture, page logic, or test is
modified by Phase 5P (the additive `nav_p8` registration line is preserved
verbatim).

---

## Relationship to Phase 5N Investment Cockpit

Phase 5N (Cockpit UI v0.2 Opportunity-first Redesign, Accepted) redesigned
`pages/7_Investment_Cockpit.py` into the opportunity-first product surface and
relies on the additive `nav_p7` sidebar registration. Phase 5P keeps Investment
Cockpit as a first-class top-level entry. No Phase 5N page logic or test is
modified by Phase 5P (the additive `nav_p7` registration line is preserved
verbatim).

---

## Why Financial and Price & Volume are removed from the top-level sidebar

- **Product model alignment.** Per Phase 5I, financial analysis and
  price-volume / technical analysis are facets of researching a single company,
  i.e. sub-surfaces under Equity Research, not independent top-level products.
- **Avoid duplication.** Surfacing them as separate first-class pages duplicates
  research that conceptually belongs under Equity Research.
- **Top-level clarity.** The top-level nav should present the product-facing
  entry points (Overview / Macro Dashboard / Sector / Scanner / Equity Research
  / Investment Cockpit), keeping company-level source facets one level down.

## Why their underlying files / functionality are retained

- **No functional regression.** `pages/5_Financial.py` and
  `pages/6_PriceVolume.py` are **not deleted** and their internal logic is
  **not modified**. The Financial / Price & Volume functionality is fully
  preserved.
- **Direct access preserved.** Removing the custom-sidebar links does not
  delete the pages; if Streamlit still resolves the page routes, they remain
  reachable directly by URL. Phase 5P only removes them from the **custom**
  sidebar (the app runs with `showSidebarNavigation = false`, so the custom
  sidebar is the only curated nav surface).
- **Used by the workflow / Equity surface.** The Equity Research workflow and
  related surfaces continue to depend on the Financial / Price & Volume modules;
  removing the files would break that. Phase 5P is navigation-only.
- **Backward-compatible labels.** The `nav_p5` / `nav_p6` translation keys are
  intentionally **kept** in `ui_utils.TRANSLATIONS["en"]` and
  `ui_utils.TRANSLATIONS["zh"]` as **legacy source-module labels** for backward
  compatibility. They are documented as legacy in-place and are no longer shown
  in the top-level nav.

---

## New top-level sidebar structure

After Phase 5P, `render_sidebar()` lists exactly these top-level entries (in
order):

```
🏠 Home / 主页                    -> app.py
🔭 Overview / 总览                -> pages/1_Overview.py
🏭 Sector Research / 行业研究      -> pages/2_Sector.py
🔍 Stock Scanner / 选股扫描        -> pages/3_Scanner.py
🏢 Equity Research / 个股研究      -> pages/4_Equity.py
🧭 Investment Cockpit / 投研中枢   -> pages/7_Investment_Cockpit.py
🌐 Macro Dashboard / 宏观仪表盘    -> pages/8_Macro_Dashboard.py
```

`pages/5_Financial.py` and `pages/6_PriceVolume.py` are **no longer listed** as
top-level entries.

---

## Source module hierarchy

The conceptual source-module / decision-layer hierarchy the navigation now
reflects:

```
Overview / AI Research Workflow
Macro Dashboard                      (first-class top-level)
Sector Research
Scanner
Equity Research                      (first-class top-level)
  ├─ company overview
  ├─ financial analysis              (source sub-surface; pages/5_Financial.py)
  ├─ price-volume / K-line / technical analysis
  │                                  (source sub-surface; pages/6_PriceVolume.py)
  └─ news / sentiment
Investment Cockpit                   (first-class top-level)
```

Financial Analysis and Price & Volume Analysis are source sub-surfaces under
Equity Research; their files are retained and remain directly reachable.

---

## Bilingual sidebar behavior

- The custom sidebar continues to route every nav label through
  `ui_utils.t()`, so EN/ZH labels stay coherent.
- Active top-level nav keys (`nav_home`, `nav_p1`, `nav_p2`, `nav_p3`,
  `nav_p4`, `nav_p7`, `nav_p8`) remain present and non-empty in both
  `TRANSLATIONS["en"]` and `TRANSLATIONS["zh"]`.
- The legacy `nav_p5` / `nav_p6` keys remain present in both languages for
  backward compatibility but are not rendered in the top-level nav.
- No translation key is renamed or removed; the only `TRANSLATIONS` change is an
  additive in-place documentation comment marking `nav_p5` / `nav_p6` as legacy.

---

## Non-goals

- **No deletion** of `pages/5_Financial.py` or `pages/6_PriceVolume.py`.
- **No removal** of underlying Financial / Price & Volume functionality.
- **No modification** of Equity page internals (beyond what navigation
  documentation requires — in practice, none).
- **No modification** of `app.py`, `lib/llm_orchestrator.py`,
  `lib/workflow_state.py`, or `.claude/agents/*`.
- **No UI/UX visual polish** (deferred to Phase 5R).
- **No live integration, no shadow mode.**
- **No live workflow behavior change.**
- **No reordering-driven redesign** beyond removing the two source-page links.

---

## Guardrails

- No LLM call.
- No yfinance / Finnhub / FRED / CNN / news / external API call.
- No DB / vector store / production persistence.
- No broker / order / execution capability; no buy/sell/order instruction.
- `approved_for_execution` remains `False` or absent; never positively
  authorized.
- `app.py`, `lib/llm_orchestrator.py`, `lib/workflow_state.py`, and
  `.claude/agents/*` are not modified.
- `pages/5_Financial.py` and `pages/6_PriceVolume.py` are not deleted and not
  modified.
- Only `ui_utils.render_sidebar()` navigation links and the additive legacy-key
  documentation comments change in `ui_utils.py`.

---

## Acceptance criteria

1. `ui_utils.render_sidebar` includes the Macro Dashboard link
   (`pages/8_Macro_Dashboard.py`, `nav_p8`).
2. `ui_utils.render_sidebar` includes the Investment Cockpit link
   (`pages/7_Investment_Cockpit.py`, `nav_p7`).
3. `ui_utils.render_sidebar` includes top-level Overview / Sector / Scanner /
   Equity links (pages 1–4).
4. `ui_utils.render_sidebar` does **not** include top-level page links to
   `pages/5_Financial.py` or `pages/6_PriceVolume.py`.
5. `pages/5_Financial.py` and `pages/6_PriceVolume.py` still exist.
6. `app.py` is not modified.
7. Pages 7 and 8 still compile; the removed-nav page files still exist.
8. EN/ZH sidebar labels remain present for active nav keys.
9. No LLM / API / live-workflow imports are introduced by Phase 5P.
10. No positive `approved_for_execution` authorization is introduced; it
    remains `False` or absent.
11. Phase 5N and Phase 5O test suites still pass after the `ui_utils.py`
    navigation change.

---

## Future Phase 5Q dependency

Phase 5P is a prerequisite for **Phase 5Q — Human Feedback UI v0.1**. With the
top-level navigation consolidated around the product-facing surfaces (Macro
Dashboard, Equity Research, Investment Cockpit), Phase 5Q can layer a
fixture-backed human-feedback / review surface onto the Cockpit without the
top-level nav still advertising the now-subordinate source pages. Phase 5Q has
**not started** and must not begin until Phase 5P is accepted.

---

## Validation

Targeted validation only (run with `python3 -B`):

```bash
git status --short
python3 -B scripts/test_reliability_phase_5p_navigation_cleanup.py
python3 -B scripts/test_reliability_phase_5o_macro_dashboard.py
python3 -B scripts/test_reliability_phase_5n_cockpit_ui_v02.py
```

`git status --short`: targeted forbidden live-runtime path checks can be clean
while unrelated dirty / untracked worktree items may exist from prior phases.
