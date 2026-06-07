# Phase 6C-B — Investment Cockpit Rebuild

**Status:** Implemented — Awaiting Codex Review. Phase 6C-B is **not accepted** in
this pass. **Phase 6D has not started.**

## Purpose

Rebuild the Investment Cockpit (`pages/7_Investment_Cockpit.py`) from a
fixture/demo surface (Phase 5N v0.2) into the app's **primary entry point and
live data aggregation hub**. A single **Refresh All** button pulls the macro
regime, market-theme momentum, and signal candidates, then values any
user-selected tickers — surfacing everything in one place. App-computed fair
values then flow into the Trading Desk so order recommendations are anchored on
the app's own valuation rather than yfinance analyst targets alone.

**Acceptance criterion:** *"The user opens Investment Cockpit, clicks Refresh,
selects tickers, and Trading Desk order recommendations use fair values computed
by the app rather than yfinance analyst targets alone."*

## What Phase 6C-B changes

- **Sidebar restructure** (`ui_utils.render_sidebar`): the Investment Cockpit is
  now the first non-home nav entry; the AI Research Workflow (Overview) is
  removed from the sidebar. New order:
  Home · Investment Cockpit · Macro Dashboard · Sector Research · Stock Scanner ·
  Equity Research · Trading Desk.
- **`lib/equity_valuation.py`** (new): standalone, deterministic fair-value
  module — `AppFairValue` dataclass + `compute_app_fair_value()` +
  `build_app_fair_value()` (pure assembler) + `store_equity_research_result()`.
- **`pages/4_Equity.py`**: a new collapsed **AI Valuation Summary** section at the
  bottom (range bar, upside, confidence badge, methodology, per-source
  contributions, **Run AI Debate** and **Send to Trading Desk** buttons). No
  existing content modified.
- **`lib/llm_orchestrator.py`**: new `analyze_equity_fair_value_debate()` — one
  cached LLM call producing a bilingual bull/bear/risk/synthesis debate and an
  endorsed fair-value range. Fail-closed to the app low/high band.
- **`lib/order_advisor.py`**: `compute_price_levels()` Step 0 now reads
  `st.session_state["equity_research_results"][ticker]` and, when present with
  high/medium confidence, uses the app fair value as the primary anchor; the new
  `PriceLevelResult.fair_value_source` field records provenance
  (`app_computed` / `analyst_proxy` / `fixture`).
- **`pages/9_Trading_Desk.py`**: order cards now show a `fair_value_source` badge
  next to the fair-value anchor.
- **`ui_utils.py`**: additive EN/ZH `cockpit_hub_*` / `cockpit_fv_*` /
  `td_fair_value_source` / `td_fv_src_*` `t()` keys; `nav_p1` retained
  (deprecated) but unregistered.

## What Phase 6C-B does not change

- `lib/macro_regime.py`, `lib/macro_data.py`, `lib/workflow_state.py`,
  `lib/signal_engine.py`, `lib/thesis_monitor.py`, `lib/candidate_generator.py`,
  `lib/theme_baskets.py` — **not modified** (only called).
- `.claude/agents/*`, pages 2 / 3 / 5 / 6 — **not modified**.
- `pages/1_Overview.py` — **not deleted**; only removed from the sidebar.
- No broker / order / execution capability is introduced.
  `approved_for_execution` remains False or absent everywhere.
- No DB / vector store; no paid APIs. All state lives in `st.session_state`.

## Sidebar restructure

| Position | Page | Key |
|---|---|---|
| 1 | Home (`app.py`) | `nav_home` |
| 2 | Investment Cockpit (`pages/7_Investment_Cockpit.py`) | `nav_p7` |
| 3 | Macro Dashboard (`pages/8_Macro_Dashboard.py`) | `nav_p8` |
| 4 | Sector Research (`pages/2_Sector.py`) | `nav_p2` |
| 5 | Stock Scanner (`pages/3_Scanner.py`) | `nav_p3` |
| 6 | Equity Research (`pages/4_Equity.py`) | `nav_p4` |
| 7 | Trading Desk (`pages/9_Trading_Desk.py`) | `nav_p9` |

Overview (`nav_p1`) and the Phase 5P source sub-surfaces (`nav_p5` / `nav_p6`)
keep their translation keys but are not registered.

## AppFairValue computation methodology

`AppFairValue` blends three independent, FREE per-share estimates into a
`fair_value_low <= fair_value_mid <= fair_value_high` band:

- **`dcf_value`** — simplified single-stage Gordon-growth DCF on a per-share TTM
  free-cash-flow base (see DCF assumptions below). `None` when FCF / shares /
  the `WACC − g` denominator are unavailable or non-positive.
- **`relative_value`** — `sector_median_pe × trailing_eps`, where
  `sector_median_pe` comes from the hardcoded `SECTOR_MEDIAN_PE` map in
  `lib/equity_valuation.py`. `None` when EPS ≤ 0 / unavailable.
- **`analyst_target`** — `targetMedianPrice` if available, else
  `targetMeanPrice`; `analyst_count` from `numberOfAnalystOpinions`.

Band construction (only present sources contribute):

- `fair_value_low` = `min(dcf×0.85, relative×0.90, analyst×0.80)`;
  `current_price × 0.85` when all None.
- `fair_value_mid` = weighted average (DCF 0.35 / relative 0.35 / analyst 0.30,
  renormalized over present sources); `current_price` when all None.
- `fair_value_high` = `max(dcf×1.10, relative×1.05, analyst×1.05)`;
  `current_price × 1.15` when all None.

`confidence`:

- **high** — all three sources present AND
  `(high − low) / mid < 0.40`.
- **medium** — ≥ 2 sources present, OR (≥ 1 source present AND spread < 0.60).
- **low** — otherwise (so the all-None / no-source case is always `low`).

`upside_pct = (mid − current_price) / current_price`. `methodology` names the
sources used; `computed_at` is an ISO timestamp; `data_source` is `live` when
yfinance returned info, else `fixture`. `compute_app_fair_value()` is cached
TTL=3600 keyed on `(ticker, current_price)` and is fully fail-closed.

## DCF assumptions

- **WACC = 10%** (fixed, documented inline as `_WACC`).
- **growth_rate** = `min(earningsGrowth | revenueGrowth | 0.05, 0.15)` — capped
  at 15%.
- **horizon** = 5 years: `dcf = fcf_per_share × (1 + g)^5 / (WACC − g)`.
- The growth cap (15%) exceeds WACC (10%); when the resolved growth ≥ WACC the
  Gordon-growth denominator is non-positive and `dcf_value` is `None`
  (not computable) rather than negative.
- `fcf_per_share` = TTM free cash flow / `sharesOutstanding`, where TTM FCF =
  Σ(last 4 quarters operating cash flow) − |Σ(last 4 quarters CapEx)| (CapEx is
  a negative cash outflow in yfinance, so its magnitude is subtracted). This
  per-share normalization makes the DCF comparable to the relative and analyst
  per-share estimates.

## Fair value source priority (app_computed > analyst_proxy)

`compute_price_levels()` Step 0 reads
`st.session_state["equity_research_results"].get(ticker)`:

- **If present and `confidence ∈ {high, medium}`** → `fair_value_mid` becomes the
  primary anchor, `fair_value_low` the conservative entry floor (LONG entry-zone
  high), `fair_value_high` the upside target;
  `PriceLevelResult.fair_value_source = "app_computed"`.
- **Else** → fall back to `lib/valuation_anchor.py` (existing Entry v4 behavior);
  `fair_value_source = "analyst_proxy"` over live data, or `"fixture"` when the
  technical/anchor fetch failed closed.

The LLM never produces or alters any of these numbers; it only debates them.

## One-click refresh sequence and fail-closed behavior

`Refresh All` runs four independent steps, each wrapped fail-closed (a failure in
one never aborts the others), with a `st.progress` bar and stage labels:

1. `fetch_all_macro()` + `classify_regime()` → `st.session_state["macro_regime_result"]`.
2. `compute_all_themes()` → `st.session_state["theme_momentum_results"]`.
3. `generate_candidates(macro_regime, top_n=20, llm_n=50)` → updates
   `cockpit_all_signals` + `cockpit_triple_signals` (written by the generator).
4. For each ticker in `cockpit_selected_tickers`:
   `compute_app_fair_value(ticker, current_price)` → `store_equity_research_result()`.

On completion the page sets `st.session_state["cockpit_last_refresh"]` and shows a
summary: `Refresh complete — Macro: ✅ Themes: ✅ Signals: N · Equity: M`. The
**Trading Desk thesis monitor is NOT run here** — it runs on the Trading Desk page
load as before.

## Files created or modified

**Created:**
- `lib/equity_valuation.py`
- `scripts/test_reliability_phase_6c_b_cockpit_rebuild.py`
- `docs/reliability_phase_6c_b_cockpit_rebuild.md`

**Modified:**
- `ui_utils.py` (sidebar restructure + additive `cockpit_hub_*` / `cockpit_fv_*` /
  `td_fair_value_source` / `td_fv_src_*` keys; `nav_p1` deprecated comment)
- `lib/order_advisor.py` (`fair_value_source` field + Step 0 app fair-value read +
  LONG app override + `_read_equity_research_result`)
- `lib/llm_orchestrator.py` (`analyze_equity_fair_value_debate`)
- `pages/4_Equity.py` (AI Valuation Summary section appended)
- `pages/7_Investment_Cockpit.py` (full rebuild)
- `pages/9_Trading_Desk.py` (fair_value_source badge)
- `scripts/test_reliability_phase_6c_trading_desk.py` (assertion 9.5 updated to
  the new spec-mandated sidebar order)
- `docs/ai_dev_state/PROJECT_STATE.md`, `docs/ai_dev_state/CURRENT_TASK.md`

## Validation summary

Run via WSL `wsl.exe -d ubuntu -- bash -lc 'python3 -B ...'`:

```bash
git status --short
python3 -B scripts/test_reliability_phase_6c_b_cockpit_rebuild.py   # 47/47
python3 -B scripts/test_reliability_phase_6c_v3_entry_v4.py         # 47/47 regression
python3 -B scripts/test_reliability_phase_6c_trading_desk.py        # 118/118 regression
python3 -B scripts/test_reliability_phase_6b_v3_horizon_scoring.py  # 189/189 regression
python3 -B scripts/test_reliability_phase_6a_live_data.py           # 336/336 regression
```

## Next phase recommendation

After Codex acceptance: **Phase 6D — Monitoring & Review**.

## Guardrails

Free sources only (yfinance / FRED / Finnhub free tier via existing fetchers); no
paid API; no broker / order / execution capability; no order ticket / broker
payload; `approved_for_execution` always False or absent; no DB / vector store;
no persistence beyond `st.session_state`. `lib/macro_regime.py`,
`lib/macro_data.py`, `lib/workflow_state.py`, `lib/signal_engine.py`,
`lib/thesis_monitor.py`, `lib/candidate_generator.py`, `lib/theme_baskets.py`,
`.claude/agents/*`, and pages 2 / 3 / 5 / 6 not modified; `pages/1_Overview.py`
retained (only unregistered from the sidebar).

## Acceptance criteria

The user opens the Investment Cockpit, clicks **Refresh All**, selects tickers,
and the Trading Desk order recommendations use the app-computed fair value
(`fair_value_source = "app_computed"`) rather than yfinance analyst targets
alone — falling back to `analyst_proxy` only when no app fair value has been
stored for the ticker.
