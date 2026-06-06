# Phase 6A — Live Data Integration

**Status**: Implemented — awaiting Codex review. **Phase 6A is not accepted in
this pass. Phase 6B has not started.**

> **Disclaimer**: This system and all of its outputs are for investment research
> and educational purposes only. They do not constitute investment advice. Live
> macro data shown on the Macro Dashboard is review-only context; it produces no
> buy/sell decision and authorizes no execution.

---

## Purpose

Phase 6A is the first phase that makes the app **genuinely usable for real
investment-decision support** by replacing fixture/mock data on the Macro
Dashboard with **live, free** market and macro data. After Phase 6A the user can
open the app and see **real current macro conditions** — today's volatility,
rates, credit, dollar, cross-asset ETF returns, economic releases, and a derived
risk regime — rather than placeholder data.

The single acceptance criterion for this phase is:

> "The user opens Macro Dashboard and sees real market data that reflects
> today's conditions."

---

## What Phase 6A changes

- **New module `lib/macro_data.py`** — the single place that fetches live macro
  data from free sources (yfinance, FRED, Finnhub free tier). Every fetch is
  fail-closed and returns a result tagged with a `data_source` of `"live"` or
  `"fixture"`.
- **New module `lib/macro_regime.py`** — a fully deterministic regime
  classification engine (`classify_regime`) that turns a `MacroDataResult` into a
  `MacroRegimeResult` (`risk_on` / `risk_off` / `transition` / `degraded`) with a
  confidence, a per-horizon bias, key signals, and a review-only opportunity
  posture.
- **`pages/8_Macro_Dashboard.py`** — adds a **Live Macro Conditions** section
  (rendered when the `MACRO_LIVE_MODE` feature flag is `True`) that shows the
  live regime, a data-coverage indicator, per-group data freshness, and a visible
  **LIVE / FIXTURE** badge on every metric group. The existing fixture-only macro
  regime tabs are preserved unchanged below the live section.
- **`ui_utils.py`** — additive EN/ZH `macro_live_*` chrome keys (no existing key
  renamed or removed).
- **`scripts/test_reliability_phase_6a_live_data.py`** — mock-only test suite.

## What Phase 6A does not change

- The **live AI research workflow** (Overview five-step Claude workflow) and its
  files: `lib/llm_orchestrator.py`, `lib/workflow_state.py`, and pages 1–6
  (Overview, Sector, Scanner, Equity, Financial, PriceVolume) are **untouched**.
- `.claude/agents/*`, the Investment Cockpit page (`pages/7_Investment_Cockpit.py`),
  and the sidebar registration / nav keys are **untouched**.
- No new LLM calls are introduced beyond what already exists in the live
  workflow. No broker / order / execution capability is introduced. No DB /
  vector store / persistence is introduced. `approved_for_execution` remains
  `False` or absent everywhere.
- No paid API is introduced; all Phase 6A data sources are free.
- No new Finnhub endpoints beyond the two reused here.

---

## Data sources used

| Source | Endpoint(s) | Free / paid | Metric groups | Fallback behavior |
|--------|-------------|-------------|---------------|-------------------|
| yfinance | `^VIX` history; batched `download` of QQQ/IWM/SPY/GLD/USO/TLT/HYG | **Free** (no key) | VIX + fear/greed proxy; ETF 1M/3M returns | On any error → deterministic fixture for that group (`data_source="fixture"`) |
| FRED | `series/observations` for `DGS10`, `DGS2`, `T10YIE`, `BAMLH0A0HYM2`, `DTWEXBGS`, `PAYEMS`, `CPIAUCSL`, `PPIACO` | **Free** (requires `FRED_API_KEY`) | Rates / inflation, credit, dollar, economic releases | Missing key or any error → fixture for that group |
| Finnhub | `/news?category=general` (primary), `/stock/social-sentiment` (best-effort) | **Free tier** (reuses existing `FINNHUB_API_KEY`) | Market sentiment (supplementary) | Both endpoints fail / no key → VIX-derived fear/greed proxy (`data_source="fixture"`) |

- The FRED key is read from the `FRED_API_KEY` environment variable.
- The Finnhub key reuses the project's existing `FINNHUB_API_KEY` and request
  pattern (token query param + short timeout + `raise_for_status` + try/except),
  matching `lib/data_fetcher.py`. Only the two Finnhub endpoints above are used —
  no new Finnhub endpoints are added.
- **Important free-tier reality:** `/stock/social-sentiment` is a **premium**
  Finnhub endpoint. With a free-tier key it returns **HTTP 403** ("You don't have
  access to this resource"). It is therefore called **best-effort** (per-symbol
  failure is swallowed) and is *not* required for a live sentiment reading. The
  **free** `/news?category=general` feed is the **primary live sentiment signal**:
  when it returns headlines, `fetch_market_sentiment` reports `data_source="live"`
  and derives the score from headline tone (or from premium social mentions when
  a premium key makes them available). Only when *both* Finnhub endpoints fail (or
  no key is set) does it fall back to the VIX-derived proxy (`data_source="fixture"`).
- Finnhub free tier rate limit is 60 RPM; all fetches are cached with
  `st.cache_data(ttl=900)` (15 minutes) so the page does not exceed the limit.

---

## CNN Fear & Greed substitution rationale and VIX proxy methodology

There is **no reliable free CNN Fear & Greed API**. Phase 6A therefore
substitutes a **VIX-derived fear/greed proxy** computed entirely from free
yfinance `^VIX` data:

1. Fetch the trailing 1 year of daily VIX closes.
2. Compute the **percentile rank** of the latest VIX close within the trailing
   **252 trading days**.
3. The proxy score is the **inverse** of that percentile, scaled to **0–100**:
   `fear_greed = (1 − percentile_rank) × 100`.

Interpretation: a **calm** VIX (low percentile) maps to a **high** score
("greed"); an **elevated** VIX (high percentile) maps to a **low** score
("fear"). The mapping to labels is: ≥75 extreme greed, ≥55 greed, 45–55 neutral,
25–45 fear, <25 extreme fear. This substitution is documented in code comments in
`lib/macro_data.py` (`fetch_vix`).

---

## Fail-closed behavior per metric group

Every public `fetch_*` function in `lib/macro_data.py` is wrapped in its own
`try/except`. On **any** failure — missing API key, network error, HTTP error,
empty/parse error — the function returns a deterministic **fixture** result whose
`data_source` field is `"fixture"`. Functions never raise to the caller.

| Metric group | Live source | On failure |
|--------------|-------------|------------|
| `vix` | yfinance `^VIX` | fixture VIX (value 16.5, neutral fear/greed) |
| `rates` | FRED DGS10/DGS2/T10YIE | fixture yields + spread |
| `credit` | FRED BAMLH0A0HYM2 | fixture HY spread |
| `dollar` | FRED DTWEXBGS | fixture dollar index |
| `etf_returns` | yfinance batch | fixture ETF returns |
| `economic_releases` | FRED PAYEMS/CPIAUCSL/PPIACO | fixture (values `None`, marked fixture) |
| `sentiment` | Finnhub free news (primary) + premium social (best-effort) | VIX-derived proxy (marked fixture) only if both fail |

`fetch_all_macro()` aggregates the seven groups and computes
`data_coverage` = (number of groups fetched live) / 7. The page renders a visible
**LIVE / FIXTURE** badge per group and a muted inline warning for any group that
fell back — never a full-page error or `st.exception()`.

The deterministic regime engine has its own fail-closed guard: if
`data_coverage < 0.5`, `classify_regime` returns `regime="degraded"` with a
neutral horizon bias regardless of any other signal.

---

## Feature flag location and behavior

- **Location**: `MACRO_LIVE_MODE` is defined near the top of
  `pages/8_Macro_Dashboard.py` (immediately after the imports).
- **Default**: `MACRO_LIVE_MODE = True`.
- **Behavior**: it is a **single boolean controlling the entire page**.
  - `True` → the page fetches live macro data (fail-closed per group) and renders
    the Live Macro Conditions section reflecting today's market.
  - `False` → **all API calls are skipped** and the page uses fixture data
    exactly as before Phase 6A (the Phase 5O fixture tabs only).

---

## Fixture fallback guarantee

The page can **never render empty or broken under any condition**:

- Per-group failure → that group shows fixture values with a FIXTURE badge.
- Whole-fetch failure → the Live Macro Conditions section shows a muted warning
  and the page continues to the preserved Phase 5O fixture tabs.
- The Phase 5O deterministic fixture builder
  (`build_macro_dashboard_view_by_scenario`) and its fail-closed branch are
  preserved, so the regime/indicator tabs always render.
- The live loader (`_load_live_macro`) is wrapped in `try/except` and is cached;
  a hard failure degrades gracefully to the fixture view.

---

## Files created or modified

**Created**

- `lib/macro_data.py`
- `lib/macro_regime.py`
- `scripts/test_reliability_phase_6a_live_data.py`
- `docs/reliability_phase_6a_live_data_integration.md` (this file)

**Modified**

- `pages/8_Macro_Dashboard.py` (live section + feature flag; fixture tabs preserved)
- `ui_utils.py` (additive EN/ZH `macro_live_*` chrome keys)
- `docs/ai_dev_state/PROJECT_STATE.md`, `docs/ai_dev_state/CURRENT_TASK.md` (state)

**Not modified** (guardrail): `app.py`, pages 1–6, `pages/7_Investment_Cockpit.py`,
`lib/llm_orchestrator.py`, `lib/workflow_state.py`, `lib/data_fetcher.py`,
`lib/valuation.py`, `lib/technical.py`, `lib/rotation.py`, `lib/cache_manager.py`,
`.claude/agents/*`, `lib/reliability/*`.

---

## Validation summary

Run with `python3 -B` via WSL:

- `scripts/test_reliability_phase_6a_live_data.py` — **336/336 PASS** (mock-only;
  no real API calls). Asserts module imports, dataclass contracts, `data_source`
  per group, deterministic `classify_regime` (including the degraded rule and
  horizon-bias keys), structured localizable `signals` (parallel to
  `key_signals`), fail-closed `fetch_all_macro`, `try/except` on every `fetch_*`
  (AST), the Finnhub social-403→free-news-live regression, the FRED-429 retry
  regression, the bilingual localization keys (EN+ZH present and differing,
  Chinese characters in ZH values), the page feature flag / badges / fixture
  fallback / localization + dynamic sub-regime wiring, and the no-execution /
  no-broker invariants.
- `scripts/test_reliability_phase_5s_closeout.py` — regression PASS.
- `scripts/test_reliability_phase_5r_ui_ux_polish.py` — regression PASS (the page
  contains no live data-vendor SDK token; all live calls are encapsulated in
  `lib/macro_data.py`).

---

## UX refinement (bilingual + terminal layout + live sub-regime)

A follow-up pass made the live Macro Dashboard genuinely usable and fully
bilingual:

1. **Full Chinese localization.** Every user-visible field on the live page
   routes through `ui_utils.t()` — including the regime value, confidence,
   horizon-bias values, key signals, opportunity posture, theme implications, and
   sub-regime status words. To localize the generated signal/posture text without
   duplicating classification logic, `classify_regime` now also emits a parallel
   structured `signals` list (`{"code", "values"}`) alongside the canonical
   English `key_signals`; the page renders `t("macro_sig_<code>").format(**values)`
   in ZH and falls back to the English text otherwise. Enum values are localized
   via `macro_regimeval_* / macro_confval_* / macro_biasval_*` maps. No English
   hardcoded strings render in ZH mode.
2. **Terminal-style metric cards.** Each indicator card surfaces 1–2 headline
   numbers via `st.metric` (large), shows a small colored `● LIVE` / `● FIXTURE`
   tag top-right, and collapses secondary information (data freshness, fear/greed
   proxy note, release dates, news headlines) into a muted `Details` expander so
   it does not compete with the core values.
3. **Live-driven sub-regime readouts.** The Macro Regime / Rates & Liquidity /
   Credit & Volatility / Market Sentiment tabs no longer show fixture placeholder
   descriptors. Their status descriptions
   (`elevated/contained/tightening/tight/wide/calm/stressed/broad/narrow/...`) are
   computed deterministically from the live FRED yields + breakeven, HY spread,
   broad-dollar change, VIX, and SPY/IWM ETF returns (thresholds mirror
   `lib/macro_regime.py`). The Phase 5O fixture scenario tabs are retained only as
   the `MACRO_LIVE_MODE=False` / full-failure fallback.

4. **Visual hierarchy upgrade.** A prominent top **hero regime banner** (large,
   color-coded by regime) shows the current market state above the tabs. Core
   metric values are enlarged (~1.5×) and **sign-colored** (green positive / red
   negative / theme-default neutral). Regime, horizon-bias, confidence, and
   sub-regime status are rendered as **color-coded badges** with consistent
   semantics (`risk_on`=green, `risk_off`=red, `transition`=amber, `degraded`=gray;
   favorable=green / unfavorable=red / cautious=amber). Each indicator card adds a
   **collapsible "History trend" table** (default collapsed) showing ~6 recent
   data points sliced from the **already-fetched** yfinance/FRED series — exposed
   via a new `history` field on the `VixResult / RatesResult / CreditResult /
   DollarResult / EconomicReleasesResult` dataclasses (FRED limits were widened on
   the *same* request; **no new API calls**). Cards are separated by spacing and
   bordered `st.container`s, and the tab titles were simplified to concise block
   titles without "/" separators (e.g. *Rates & Liquidity*, *Credit & Volatility*,
   *Market Sentiment*, *Data Sources*). All new chrome is bilingual via `t()`.

5. **Professional font system.** `ui_utils.py` injects a Google-Fonts-based font
   stack as a global `_FONT_CSS` block (first in `apply_theme()`, so the `@import`
   leads its stylesheet): **Inter** for headings / body / labels and **JetBrains
   Mono** for all data / numbers (metric values, tickers, percentages, prices),
   exposed as `--font-sans` / `--font-mono` CSS variables. Numeric elements
   (`stMetricValue`, custom number HTML, tables, the sidebar ticker input) use
   `font-variant-numeric: tabular-nums` so figures align in columns. The existing
   hardcoded `'SF Mono'` stacks were routed through `var(--font-mono)`. Because
   every page calls `apply_theme()`, all pages inherit the new typography with no
   per-page change; the page-8 big numbers were reduced to **1.6rem** (mono,
   tabular) to sit correctly in the type hierarchy.

6. **Trend line charts.** Each history expander renders a **Plotly line chart**
   above the data table (X=date, Y=value, **200px**, no legend, no gridlines, line
   color = the indicator's pos/neg semantic via `_line_color`). Charts reuse the
   global `apply_layout()` / `apply_legend()` then strip chrome for a clean
   sparkline. Covered indicators: **10Y, 2Y, 10Y-2Y spread, VIX, HY credit
   spread, broad dollar index, and per-ETF cumulative returns** (QQQ / IWM / SPY /
   GLD / USO / TLT / HYG). To feed them, `RatesResult.history` became a
   date-aligned `{10Y, 2Y, spread}` series and `EtfReturnsResult.history` became a
   per-ticker cumulative-return series — both **sliced from the already-fetched**
   yfinance/FRED data (FRED `DGS2` widened on the same request), so **no new API
   calls** are introduced. Each chart is given a unique `key` to avoid
   `StreamlitDuplicateElementId`.

7. **Economic-release trend charts + chrome cleanup.** The NFP / CPI / PPI
   expander now also shows trend charts derived from the FRED level history (no
   new API calls): **NFP monthly change** (level diff) and **CPI / PPI MoM %**
   (month-over-month percent), via `_render_releases_trend` /
   `_releases_change_series`, above the levels table. Separately, all
   user-facing macro **titles, card headers, and captions were de-jargoned**:
   parenthetical implementation details (data-source / endpoint names like FRED,
   Finnhub, yfinance, DTWEXBGS, BAMLH0A0HYM2; fallback logic; `MACRO_LIVE_MODE`;
   `source_type=fixture` / `is_live_data` / `is_buy_signal` schema flags;
   fixture/placeholder markers) were removed in favor of concise user-facing names
   (e.g. "Market volatility", "Rates & inflation", "Credit spreads", "Market
   sentiment"). Code comments and docstrings are unchanged. The Investment Cockpit
   (page 7) is an explicitly fixture/demo preview protected by guardrails and
   accepted test pins; its "demo / Phase 5x" labels are honest disclosures and
   were intentionally left unchanged.

8. **Overview intro page.** The Overview tab was rebuilt as a clean, user-facing
   intro: a simplified title ("Macro Dashboard" / "宏观仪表盘" — no version /
   "Demo Preview" / "Opportunity-first" annotations); **one merged data-mode
   banner** driven by `MACRO_LIVE_MODE` + actual coverage ("Live data mode" when
   coverage ≥ 50%, "showing demo data as a fallback" below 50%); **three concise
   blocks** — *current market state* (regime + confidence + horizon-bias badges,
   shown once — the duplicate bottom regime block was removed), *what this page
   covers* (six one-line analysis dimensions), and *data sources & update
   frequency* (one line, ~15 min, no endpoint names); and a **single short
   disclaimer** ("For research … not investment advice"). The developer guardrail
   bullets (No live macro API / No LLM / No broker / `approved_for_execution`)
   were removed from the user interface (the `macro_safety_b*` keys remain defined
   and are still referenced by the fixture-mode banner, so the bullets never
   surface on the live page). The "How to read this page" walkthrough remains but
   is collapsed by default.

## Next phase recommendation

**Phase 6B — Stock Selection Signal Layer**: build a deterministic, evidence-first
signal layer that consumes the live macro regime from Phase 6A (and the existing
scanner/rotation tooling) to surface candidate tickers as review-only context.
Phase 6B must preserve the live workflow, introduce no broker/order/execution,
and keep `approved_for_execution` False or absent.

---

## Guardrails

- No broad git cleanup / commit / staging / stash / reset.
- `lib/llm_orchestrator.py`, `lib/workflow_state.py`, `.claude/agents/*`, and
  pages 1–6 are not modified; the live AI research workflow behavior is unchanged.
- No broker / order / execution capability; no order tickets, broker payloads,
  account IDs, execution IDs, or executable trade instructions; no buy/sell/order
  instruction. `approved_for_execution` remains `False` or absent.
- No DB / vector store / persistence introduced.
- All live data calls are fail-closed: any failure falls back to fixture data
  with a visible indicator, never a crash.
- A single feature flag (`MACRO_LIVE_MODE`) switches the entire page between live
  and fixture mode.
- No new LLM calls beyond the existing live workflow.
- No paid APIs; only free sources (yfinance, FRED, Finnhub free tier).
- No new Finnhub endpoints beyond `/stock/social-sentiment` and
  `/news?category=general`.
- Phase 6B and beyond are not implemented in this phase.

---

## Acceptance criteria

1. `lib/macro_data.py` and `lib/macro_regime.py` exist, import cleanly, and
   expose `MacroDataResult` / `MacroRegimeResult` with the required fields and a
   per-group `data_source`.
2. `classify_regime` is deterministic, returns a valid regime, and returns
   `degraded` when `data_coverage < 0.5`; `horizon_bias` carries short/mid/long.
3. `pages/8_Macro_Dashboard.py` imports the new modules, defines
   `MACRO_LIVE_MODE = True`, renders LIVE/FIXTURE badges + coverage + freshness,
   and preserves the fixture fallback so the page cannot crash.
4. Every live call is fail-closed and only free sources are used.
5. `scripts/test_reliability_phase_6a_live_data.py` passes, and the Phase 5S /
   5R regression tests still pass.
6. No broker/order/execution capability; `approved_for_execution` remains False
   or absent; no new LLM calls; no paid APIs.

---

## Disclaimer

This document is for research purposes only and does not constitute investment
advice. Markets involve risk; invest with caution.
