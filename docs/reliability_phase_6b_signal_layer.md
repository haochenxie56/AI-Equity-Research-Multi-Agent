# Phase 6B — Stock Selection Signal Layer

**Status**: Implemented — awaiting Codex review. **Phase 6B is not accepted in
this pass. Phase 6C has not started.**

> **v2 update (current pass):** the signal layer has been refactored from the v1
> single-pass momentum-biased scoring into a **dual-track candidate
> architecture** that can surface early-stage opportunities (MU-style: low RSI,
> depressed price, fundamental inflection) alongside alternative-data-triggered
> candidates. The v1 methodology below is **retained for history**; the
> authoritative current design is the new **"v2 Dual-Track Architecture"**
> section at the end of this document.

> **Disclaimer**: This system and all of its outputs are for investment research
> and educational purposes only. They do not constitute investment advice. The
> AI signal candidates surfaced by Phase 6B are review-only context; they produce
> no buy/sell decision and authorize no execution.

---

## Purpose

Phase 6B upgrades the Scanner from **manual ticker-pool entry** to a system that
**automatically generates candidates** using free alternative-data and
fundamental signals. After Phase 6B the user can open the Scanner page and see an
AI-generated candidate list based on real signals — ranked by a combination of
alternative data, EPS-revision trend, narrative attribution, and entry quality —
**without manually entering a ticker pool**, and crucially surfacing
**early-stage opportunity signals**, not just the strongest momentum names.

The single acceptance criterion for this phase is:

> "The user opens the Scanner page and sees an AI-generated candidate list based
> on real signals, without manually entering a ticker pool."

---

## What Phase 6B changes

- **New module `lib/signal_engine.py`** — computes multi-factor, evidence-first
  signals per ticker (fundamental, narrative, entry quality), then derives a
  weighted composite score, a per-horizon fit, and a human-readable signal
  summary. Every network fetch is fail-closed and cached (TTL=1800). **No LLM is
  used**; narrative/theme attribution is keyword-rule based.
- **New module `lib/candidate_generator.py`** — builds the ticker universe
  (hardcoded S&P 500 top-100 by market cap + currently-selected subsector
  constituents from `research_state` when available) and runs the signal engine
  over it with a bounded `ThreadPoolExecutor(max_workers=8)` and a `st.progress`
  bar, returning the top-N candidates by composite score (cached TTL=1800).
- **`pages/3_Scanner.py`** — adds an **AI Signal Candidates** section at the top
  of the page (above the existing manual scanner), gated by a single feature flag
  `SCANNER_SIGNAL_MODE = True`. It exposes a *Generate Candidates* button, renders
  a ranked candidate table (Ticker, Composite Score colored green/yellow/red,
  Entry Quality, Horizon Fit short/mid/long, Key Signals), and a *Send to Manual
  Scanner* button that pre-fills the existing manual pool input with the top
  candidate tickers. The entire existing manual scanner is preserved unchanged
  below a `st.divider()`.
- **`ui_utils.py`** — additive EN/ZH `scn_sig_*` chrome keys only (no existing
  key renamed or removed).
- **`scripts/test_reliability_phase_6b_signal_layer.py`** — mock-only test suite.

## What Phase 6B does not change

- The **live AI research workflow** (Overview five-step Claude workflow) and its
  files: `lib/llm_orchestrator.py`, `lib/workflow_state.py`, and pages 1–2 / 4–7
  are **untouched**. `pages/1_Overview.py` live workflow behavior is unchanged.
- `.claude/agents/*`, `pages/7_Investment_Cockpit.py`, and the sidebar
  registration / nav keys are **untouched**. `pages/8_Macro_Dashboard.py` receives
  only an **additive, behavior-preserving** cross-page publish (see *Cross-page
  macro regime sharing* below) — no existing macro rendering or logic changes.
- The **existing manual scanner** (pool input, four strategies, `run_scan`,
  results table, bubble chart, downloads) is preserved exactly; the new section is
  purely additive and sits above a `st.divider()`. With `SCANNER_SIGNAL_MODE =
  False` the page behaves exactly as before Phase 6B.
- No new LLM calls. No broker / order / execution capability. No DB / vector
  store / persistence. `approved_for_execution` remains `False` or absent
  everywhere. No paid API; Quiver Quantitative is **not** introduced (deferred to
  a later phase pending the user's confirmed subscription).

---

## Signal computation methodology

### Fundamental signals (`fetch_fundamental_signals`)

Computed from yfinance `info` + Finnhub free-tier endpoints:

- **`eps_surprise_trend`** ∈ {improving, deteriorating, mixed, unknown} — from the
  EPS actual-vs-estimate surprise series (Finnhub `/stock/earnings`, last ≤4
  quarters). Builds a surprise-percent series oldest→newest and compares the
  recent-half average to the older-half average: `> +1.0pp` → improving, `< −1.0pp`
  → deteriorating, otherwise mixed; `< 2` usable quarters → unknown.
- **`recommendation_momentum`** ∈ {upgrading, downgrading, stable, unknown} — from
  the analyst buy/sell ratio change (Finnhub `/stock/recommendation`, last ~3
  months). buy-ratio = (strongBuy + buy) / total; latest vs ~3-months-back delta
  `> +0.05` → upgrading, `< −0.05` → downgrading, otherwise stable; `< 2` periods
  → unknown.
- **`valuation_percentile`** ∈ [0.0, 1.0] — forward P/E relative to a **hardcoded
  sector-median forward-P/E map** (`_SECTOR_MEDIAN_FWD_PE`, manual snapshot
  2026-05, documented in code). `percentile = clamp(0.5 × forwardPE / sector_median,
  0, 1)`; at the median → 0.5, half the median → ~0.25 (cheap), twice the median →
  1.0 (rich). Lower = cheaper relative to sector. Missing forward P/E → 0.5.
- **`quality_score`** ∈ [0.0, 1.0] — equal-weight average of three independently
  min-max-normalized components: ROE / 0.30, gross margin / 0.60, revenue growth /
  0.25 (each clamped to [0,1]). Missing components are dropped; none present → 0.0.
- **`data_source`** — per-sub-field `"live"` / `"fixture"` provenance for
  fundamentals / recommendation / earnings.

### Narrative signals (`fetch_narrative_signals`) — keyword rules, NO LLM

Computed from Finnhub `/company-news` (last 30 days):

- **`theme_tags`** — subset of the fixed taxonomy `["AI", "semiconductor",
  "cloud", "energy", "biotech", "defense", "consumer", "financials",
  "industrials", "other"]`, attributed by **documented keyword substring rules**
  (`_THEME_KEYWORDS`), ordered by match frequency. News-but-no-match → `["other"]`;
  no news → `[]`. **No model inference is used anywhere.**
- **`narrative_strength`** ∈ {strong, moderate, weak, unknown} — by 30-day news
  volume: ≥12 strong, ≥5 moderate, ≥1 weak, 0 unknown.
- **`macro_alignment`** ∈ {aligned, neutral, misaligned} — deterministic
  theme↔regime mapping (`_REGIME_ALIGNED_THEMES` / `_REGIME_MISALIGNED_THEMES`):
  risk_on favors AI/semi/cloud/consumer/industrials; risk_off favors
  energy/defense/biotech/financials and disfavors AI/semi/cloud/consumer;
  transition/degraded/unknown → neutral.

### Entry quality (`compute_entry_quality`) — deterministic code only

From the `lib.technical.snapshot()` engine (the same engine the manual Scanner's
`run_scan` uses):

- **`distance_from_52w_high`** = `pct_from_52w_high`.
- **`rsi_position`** ∈ {oversold(<40), healthy(40–65), extended(65–75),
  overbought(>75), unknown}.
- **`trend_strength`** ∈ {strong(ADX>25), moderate(15–25), weak(<15), unknown}.
- **`above_sma200`** — boolean from the snapshot.
- **`entry_quality_label`** ∈ {good, fair, extended, avoid} — documented
  top-down combination rules: overbought RSI or (below SMA200 + weak trend) →
  avoid; extended RSI while above SMA200 → extended; above SMA200 + healthy RSI +
  ≥moderate trend + within 25% of the 52-week high → good; otherwise fair.

### Composite scoring weights (`score_ticker`)

`composite_score` ∈ [0.0, 1.0] is the weighted combination:

| Component | Weight | Mapping |
|-----------|--------|---------|
| Fundamental quality (`quality_score`) | **30%** | used directly (already 0–1) |
| EPS surprise trend | **25%** | improving 1.0 / mixed 0.5 / unknown 0.4 / deteriorating 0.0 |
| Entry quality | **25%** | good 1.0 / fair 0.6 / extended 0.3 / avoid 0.0 |
| Narrative strength + macro alignment | **20%** | average of (strength: strong 1.0 / moderate 0.6 / weak 0.3 / unknown 0.4) and (alignment: aligned 1.0 / neutral 0.5 / misaligned 0.0) |

**`horizon_fit`** (`{short, mid, long}` → strong_fit / possible_fit / weak_fit /
no_fit) is derived deterministically: short is timing-led (entry quality +
narrative), mid is trend-led (EPS surprise + entry quality), long is
fundamentals-led (EPS surprise + narrative). Rules are documented inline in
`_horizon_fit`.

### Cross-page macro regime sharing (follow-up)

To make the macro regime actually flow from the macro page (page 8) to the
Scanner, a small **additive** wiring step was added:

- **`pages/8_Macro_Dashboard.py`** — after each **successful** `classify_regime()`
  (at the non-cached `main()` call site, not inside the cached loader), publishes
  a plain JSON-able dict to `st.session_state["macro_regime_result"]` with
  `regime`, `confidence`, `horizon_bias`, and `data_coverage`. No existing macro
  rendering or logic is changed.
- **`pages/3_Scanner.py`** (Plan A) — before `generate_candidates()`, obtains the
  regime **directly** via `classify_regime(fetch_all_macro())`. Both are
  fail-closed and `st.cache_data`-cached, so a prior macro-page visit is a free
  cache hit and an unvisited session simply fetches the regime live now. It
  publishes the result dict to `st.session_state["macro_regime_result"]`
  (`regime` / `confidence` / `horizon_bias` / `data_coverage`) for cross-page
  reuse and uses the `regime` field as the `macro_regime` argument. The
  currently-loaded regime status (regime + confidence + data coverage, via the
  existing `macro_live_*` chrome keys) is shown directly — there is **no** "visit
  the macro page first" hint. On any failure it reuses a previously-published
  regime, else `"unknown"`.
- **`lib/candidate_generator.py`** — `generate_candidates(macro_regime, top_n)` is
  a thin normalizing wrapper (regime stripped + lowercased; empty → `"unknown"`)
  over the cached worker `_generate_candidates_cached(macro_regime, top_n)`, whose
  `st.cache_data` key is `(macro_regime, top_n)` — so **different regimes are
  cached separately** and the key is well-defined and case/whitespace-insensitive.

---

## Data sources used and their free/paid status

| Source | Endpoint(s) | Free / paid | Used for |
|--------|-------------|-------------|----------|
| yfinance | `Ticker(...).info` (trailingPE, forwardPE, marketCap, earningsGrowth, revenueGrowth, grossMargins, returnOnEquity, sector); OHLCV via `ui_utils.load_ohlcv` | **Free** (no key) | quality score, valuation percentile, technical snapshot |
| Finnhub | `/stock/recommendation`, `/stock/earnings`, `/company-news` | **Free tier** (reuses existing `FINNHUB_API_KEY`; 60 RPM, cached TTL=1800) | recommendation momentum, EPS surprise trend, narrative attribution |
| `lib/technical.snapshot()` | local computation | **Free** | RSI / ADX / SMA200 / Vol_ratio_20d / pct_from_52w_high → entry quality |

- **Quiver Quantitative ($30/month) is NOT included** in Phase 6B; it is deferred
  to a later phase after the user confirms a subscription.
- No paid API is called. No new Finnhub endpoints beyond the three named above.

---

## Fail-closed behavior and feature flag

- **Fail-closed per fetch function.** `fetch_fundamental_signals` and
  `fetch_narrative_signals` are each wrapped in `try/except`; on any error
  (missing key, network error, parse error, empty data) they return a
  deterministic neutral/fixture result tagged `data_source="fixture"` and never
  raise. `score_ticker` wraps every sub-step; `compute_entry_quality` handles an
  empty snapshot safely. `generate_candidates` drops any ticker that fails scoring
  and never raises to the page.
- **Caching.** The two network fetch functions and the technical-snapshot helper
  are cached with `st.cache_data(ttl=1800)`; `generate_candidates` is cached
  (TTL=1800) keyed on `(macro_regime, top_n)`, keeping the Finnhub free-tier 60
  RPM limit comfortably satisfied.
- **Feature flag.** `SCANNER_SIGNAL_MODE` is defined at the top of
  `pages/3_Scanner.py` and defaults to **`True`**. When `True`, the AI Signal
  Candidates section renders at the top of the page. When `False`, no signal code
  runs and the page behaves **exactly** as it did before Phase 6B (manual scanner
  only).

---

## Ticker universe construction

`get_universe()` returns a combined, deduplicated, capped (≤150) `list[str]`:

1. **`SP500_TOP_100`** — a hardcoded list of the largest ~100 S&P 500
   constituents by market cap (manual snapshot per slickcharts.com / S&P 500
   weightings, captured 2026-05; documented in code, refreshed manually).
2. **Selected subsector constituents** from `st.session_state.research_state`
   (sector results' constituents / a scan pool) when the existing AI workflow has
   populated them — read defensively and ignored if absent.

S&P names are added first; the combined set is deduplicated (first-seen order)
and truncated to 150 tickers.

---

## Files created or modified

**Created**

- `lib/signal_engine.py`
- `lib/candidate_generator.py`
- `scripts/test_reliability_phase_6b_signal_layer.py`
- `docs/reliability_phase_6b_signal_layer.md` (this file)

**Modified**

- `pages/3_Scanner.py` (AI Signal Candidates section + `SCANNER_SIGNAL_MODE` flag
  + new imports; Plan A — obtains the regime directly via
  `classify_regime(fetch_all_macro())`, publishes `macro_regime_result`, and shows
  the loaded regime status; manual scanner preserved unchanged below a
  `st.divider()`)
- `pages/8_Macro_Dashboard.py` (**additive** cross-page publish of
  `macro_regime_result` after a successful `classify_regime()`; no existing macro
  rendering or logic changed — see *Cross-page macro regime sharing*)
- `lib/candidate_generator.py` (normalizing wrapper over the cached worker so the
  cache key is explicitly `(macro_regime, top_n)`)
- `ui_utils.py` (additive EN/ZH `scn_sig_*` chrome keys only)
- `docs/ai_dev_state/PROJECT_STATE.md`, `docs/ai_dev_state/CURRENT_TASK.md` (state)

**Not modified** (guardrail): `lib/llm_orchestrator.py`, `lib/workflow_state.py`,
`.claude/agents/*`, pages 1–2 and 4–7 (`pages/1_Overview.py`, `pages/2_Sector.py`,
`pages/4_Equity.py`, `pages/5_Financial.py`, `pages/6_PriceVolume.py`,
`pages/7_Investment_Cockpit.py`), the existing live AI research workflow behavior,
and the existing news/Finnhub/data-fetch behavior. `pages/8_Macro_Dashboard.py` is
modified **additively only** (cross-page publish; no behavior change).

---

## Validation summary

Run with `python3 -B` via WSL:

- `scripts/test_reliability_phase_6b_signal_layer.py` — **mock-only** (no real API
  calls): asserts module imports, dataclass contracts, `score_ticker` returns a
  `TickerSignalResult` with `composite_score ∈ [0,1]`, `compute_entry_quality`
  boundary RSI/ADX cases, `horizon_fit` keys + valid values, `try/except` on the
  fetch functions (AST), keyword-only (no-LLM) narrative attribution,
  `get_universe` capped `list[str]`, `generate_candidates` callable + sorted, the
  Scanner feature flag + imports, the additive EN/ZH `scn_sig_*` keys, and the
  no-execution / no-broker / no-paid-API invariants.
- `scripts/test_reliability_phase_6a_live_data.py` — Phase 6A regression.
- `scripts/test_reliability_phase_5s_closeout.py` — Phase 5S regression.

---

## Next phase recommendation

**Phase 6C — Holdings & Thesis Monitor**: a review-only layer that tracks held
positions and their theses against the Phase 6A macro regime and the Phase 6B
signals, surfacing thesis drift / invalidation triggers. Phase 6C must preserve
the live workflow, introduce no broker/order/execution, and keep
`approved_for_execution` False or absent. Phase 6C has not started.

---

## Guardrails

- No broad git cleanup / commit / staging / stash / reset.
- `lib/llm_orchestrator.py`, `lib/workflow_state.py`, `.claude/agents/*`, pages
  1–2 and 4–8 are not modified; the live AI research workflow behavior (including
  `pages/1_Overview.py`) is unchanged; the existing manual scanner is unchanged.
- `ui_utils.py` is modified only to add new `t()` translation keys.
- No broker / order / execution capability; no order tickets, broker payloads,
  account IDs, execution IDs, or executable trade instructions; no buy/sell/order
  instruction. `approved_for_execution` remains `False` or absent.
- No DB / vector store / persistence introduced.
- All new data calls are fail-closed with fixture/neutral fallback.
- A single feature flag (`SCANNER_SIGNAL_MODE`, default `True`) gates the new
  section; `False` restores the exact pre-6B behavior.
- No LLM used in the signal layer; narrative attribution is keyword-rule based.
- No paid APIs; only free sources (yfinance, Finnhub free tier, local technical
  computation). Quiver Quantitative is not included in Phase 6B.
- Phase 6C and beyond are not implemented in this phase.

---

## Acceptance criteria

1. `lib/signal_engine.py` and `lib/candidate_generator.py` exist, import cleanly,
   and expose `FundamentalSignals` / `NarrativeSignals` / `EntryQualityScore` /
   `TickerSignalResult` with the required fields.
2. `score_ticker` returns a `TickerSignalResult` with `composite_score ∈ [0,1]`;
   `compute_entry_quality` returns correct labels at boundary RSI/ADX values;
   `horizon_fit` carries short/mid/long with valid values.
3. `pages/3_Scanner.py` imports the new modules, defines `SCANNER_SIGNAL_MODE =
   True`, surfaces an AI-generated candidate list without a manual pool, and
   preserves the manual scanner unchanged below a divider.
4. Narrative attribution is keyword-based (no LLM); no LLM call is introduced in
   the signal layer; every fetch is fail-closed; only free sources are used.
5. `scripts/test_reliability_phase_6b_signal_layer.py` passes, and the Phase 6A /
   5S regression tests still pass.
6. No broker/order/execution capability; `approved_for_execution` remains False or
   absent; no paid APIs (no Quiver Quantitative).

---

## v2 Dual-Track Architecture

**Status**: Implemented — awaiting Codex review. This section supersedes the v1
single-pass methodology above; the v1 content is retained for history.

### Why v2

The v1 composite was momentum-biased: entry quality rewarded names that were
already trending and near their highs, so the candidate list skewed toward the
strongest momentum leaders and structurally *missed* early-stage opportunities.
The single acceptance criterion for v2 is:

> "The candidate list can surface a ticker like MU at cycle bottom — low RSI, far
> from 52W high, but with improving EPS revision and narrative alignment —
> alongside a ticker flagged purely by an unusual news/insider signal, with both
> clearly labeled by their signal source."

### The two tracks

```
Track A (main funnel, 70% of composite)
  Layer 1  hard filter (code only)      -> exclude only: cap<$2B, 30d<-50%, no data
  Layer 2  LLM narrative matching        -> top-N tickers, one call each (ONLY LLM)
  Layer 3  fundamental validation (code) -> EPS revision / valuation / margin / quality

Track B (alternative data, 30% of composite, runs on the FULL universe,
         independent of the Track A funnel)
  insider_buy_signal   (Finnhub /stock/insider-transactions)
  unusual_news_signal  (Finnhub /company-news keyword scan)
  analyst_revision_signal (Finnhub /stock/recommendation)
  -> Track B composite >= 0.7  => standalone "ALT_SIGNAL" entry
```

**Layer 1 never penalizes low RSI, low momentum, far-from-52W-high, or low ADX.**
Those are potential early-opportunity signals, not disqualifiers. Layer 1 excludes
only on a sub-$2B market cap (liquidity), a worse-than-50% 30-day price decline
(likely fundamental break), or completely-missing yfinance fundamentals.

### Scoring weights

**Track A** raw score (then × entry-quality modifier, clamped to [0,1]):

| Sub-score | Weight | Mapping |
|-----------|--------|---------|
| `eps_revision_score`  | **0.30** | inflecting_up 1.0 / improving 0.75 / stable 0.4 / deteriorating 0.1 / unknown 0.3 |
| `narrative_score`     | **0.25** | stage early 1.0 / growing 0.75 / mature 0.3 / cooling 0.1, ±0.15 alignment, ±0.1 strength, clamp [0,1] |
| `valuation_score`     | **0.20** | 1.0 − valuation_percentile |
| `margin_score`        | **0.15** | expanding 1.0 / stable 0.5 / contracting 0.1 / unknown 0.3 |
| `quality_score`       | **0.10** | universe-normalized quality_composite |

**Entry quality modifier** (applied *after* the raw Track A score — a BOOST, not a
filter): good **×1.1** / fair ×1.0 / extended ×0.85 / avoid ×0.7, clamp [0,1]. Low
RSI + far from the 52W high → "good" entry quality, so early-stage names are
*boosted*, not penalized.

**Track B composite** = insider 40% + unusual_news 35% + analyst_revision 25%.

**Composite**: funnel candidates → `0.7 × track_a_score + 0.3 × track_b_score`;
ALT_SIGNAL-only candidates → `track_b_score` (displayed separately).

### EPS inflection logic (the key cycle-bottom signal)

`eps_revision_direction` is computed from the last ≤4 quarters of Finnhub
`/stock/earnings` (actual vs estimate, newest-first beat/miss flags):

- **`inflecting_up`** — the most recent quarter **beat, immediately after a miss**
  (`beats[0] and not beats[1]`). This is the MU signal: the *inflection point*,
  not sustained strength. Highest EPS reward (1.0).
- **`improving`** — 2+ consecutive beats (`beats[0] and beats[1]`): sustained
  strength, explicitly **not** the inflection case (0.75).
- **`deteriorating`** — consecutive misses. **`stable`** — other mixed pattern.
  **`unknown`** — < 2 usable quarters.

### Track B standalone trigger threshold

A ticker whose Track B composite is **≥ 0.7** enters the candidate pool
*regardless of the Track A funnel*, labeled **`ALT_SIGNAL`**. Its composite is the
Track B score, and its key-signal summary names the dominant Track B sub-signal
(insider / unusual_news / analyst_revision).

### LLM narrative stage logic (Layer 2)

For the top `llm_n` Layer 1 survivors (ranked by a lightweight quality pre-score;
`llm_n` is user-configurable, default 30, range 10–50), exactly one LLM call per
ticker receives the last 30 days of company-news headlines + summaries, the
current macro regime, and the fixed theme taxonomy. The prompt instructs the
model to judge `narrative_stage` from news **recency, volume, and sentiment
shift** — not mere keyword presence. `"early"`/`"growing"` are preferred (uncrowded);
`"mature"`/`"cooling"` are penalized so crowded leaders score lower. The call uses
existing `llm_orchestrator` patterns; `llm_orchestrator` is imported **inside the
function** so Track B and Layers 1/3 carry no LLM dependency. JSON parse failure /
missing key / no news → a neutral `NarrativeResult` (all fields `unknown`/`none`).
Cached TTL=3600 keyed on `(ticker, macro_regime)`.

### candidate_type labeling

Every candidate is labeled by signal source: **`FUNNEL`** (passed Track A only),
**`ALT_SIGNAL`** (Track B standalone trigger only), or **`BOTH`** (passed Track A
*and* Track B standalone-triggered). The Scanner color-codes them (FUNNEL = blue,
ALT_SIGNAL = orange, BOTH = green).

### Dataclasses (lib/signal_engine.py)

`NarrativeResult`, `FundamentalResult`, `EntryQualityResult`, `TrackAResult`,
`TrackBResult`, `TickerSignalResult` (`ticker` / `track_a` / `track_b` /
`composite_score` / `horizon_fit` / `signal_summary` / `candidate_type`). The v1
dataclasses (`FundamentalSignals` / `NarrativeSignals` / `EntryQualityScore`) and
`score_ticker` are retained as backward-compatible shims.

### Horizon fit (deterministic)

`horizon_fit` carries `short` / `mid` / `long` ∈ {strong_fit, possible_fit,
weak_fit, no_fit}: short is timing-led (entry quality + narrative stage + macro
short bias), mid is trend-led (EPS revision + narrative stage + macro mid bias),
long is fundamentals-led (valuation percentile + quality composite + margin
trend). Rules are documented inline in `compute_horizon_fit`.

### Files (v2 pass)

- `lib/signal_engine.py` — refactored to the dual-track architecture (+ v1 shims).
- `lib/candidate_generator.py` — `run_layer1_filter` / `run_layer2_narrative` /
  `run_layer3_fundamental` / `run_track_b` / `generate_candidates(macro_regime,
  top_n, llm_n)` with staged `st.progress` labels, cached TTL=1800 keyed
  `(macro_regime, top_n, llm_n)`.
- `pages/3_Scanner.py` — LLM narrative-depth slider (10–50, default 30, est
  `~llm_n×2`s), candidate **Type** column (color-coded), Track A / Track B
  sub-score expander, ALT_SIGNAL trigger source in Key Signals; `SCANNER_SIGNAL_MODE`
  preserved; manual scanner preserved.
- `ui_utils.py` — additive EN/ZH `scn_sig_llm_*` / `scn_sig_col_type` /
  `scn_sig_subscores` / `scn_sig_col_track_*` / sub-signal column keys.
- `scripts/test_reliability_phase_6b_v2_dual_track.py` — mock-only test suite.

### Guardrails (v2 pass)

No paid APIs (Quiver Quantitative and Unusual Whales are **not** used — all
sources free: yfinance + Finnhub free tier). No broker / order / execution; no
order tickets / broker payloads / account IDs / execution IDs; no buy/sell/order
instruction; `approved_for_execution` remains False or absent. No DB / vector
store / persistence. All data calls fail-closed with neutral/fixture fallback.
`lib/macro_regime.py`, `lib/macro_data.py`, `lib/workflow_state.py`,
`.claude/agents/*`, pages 1–2 and 4–8 (incl. `pages/7_Investment_Cockpit.py` and
`pages/8_Macro_Dashboard.py`) are not modified; `ui_utils.py` is modified only to
add new `t()` keys. Phase 6C is not implemented.

---

## v3 Horizon-Native Scoring

Phase 6B **v3** replaces the v2 **single composite score** with **three
INDEPENDENT horizon scores** (short / mid / long), each with its own
deterministic weighting, and merges **catalyst detection** into the existing
single Layer-2 LLM narrative call. The Scanner renders results as **signal
cards** with **horizon-checkbox filtering**, and triple-hit candidates are
staged to `st.session_state` for a future Cockpit integration. v1 (single-pass)
and v2 (dual-track) content above is retained as history.

### `CandidateSignal` dataclass

`CandidateSignal` **subclasses the v2 `TickerSignalResult`** so existing
dual-track consumers keep working (it preserves `composite_score`,
`horizon_fit`, `track_a`, `track_b`, `candidate_type`, and
`isinstance(..., TickerSignalResult)`). It adds:

| Field | Meaning |
|-------|---------|
| `short_score` / `mid_score` / `long_score` | The three independent horizon scores, each `0.0–1.0`. |
| `horizons_hit` | The horizons whose score clears its threshold (`["short","mid","long"]` subset). |
| `signal_strength` | `triple` (3 hit) / `double` (2) / `single` (1) / `none` (0). |
| `catalyst_summary` | One-sentence catalyst description (`""` if none) — from the merged LLM call. |
| `catalyst_horizon` | Subset of `short`/`mid`/`long`. |
| `catalyst_recency` | `recent` (≤7d) / `moderate` (8–30d) / `none`. |
| `already_priced_in` | `True` if the catalyst news is >2 weeks old AND the stock already moved >10%. |
| `narrative_stage` / `narrative_theme_tags` | From the LLM narrative. |
| `eps_revision_direction` / `valuation_percentile` / `entry_quality_label` | From Layer 3 / entry quality. |
| `track_b_score` | The Track B alternative-data composite. |
| `key_signals` | Up to 5 human-readable strings, **code-generated** (not LLM). |
| `data_coverage` | `0.0–1.0` estimate of input-layer availability. |

### Horizon scoring (all deterministic except the LLM narrative inputs)

**SHORT** (weights sum 1.0; hit threshold `≥ 0.65`):

* `technical_momentum` **×0.40** — RSI 45–65 → 1.0; 65–72 → 0.7; <45 → 0.5;
  >72 → 0.2; ADX >25 +0.15 / <15 −0.1; Vol_ratio_20d >1.3 +0.1; above_SMA200
  +0.05 (clamped).
* `catalyst_score` **×0.35** — `catalyst_horizon` contains "short" → base 0.8;
  `catalyst_recency=="recent"` → +0.2; `=="moderate"` → base 0.5; no catalyst →
  0.2; `already_priced_in` → ×0.5.
* `momentum_continuation` **×0.25** — 1M return >+10% → 0.9; 5–10% → 0.7; 0–5% →
  0.5; negative → 0.2.

**MID** (weights sum 1.0; hit threshold `≥ 0.60`):

* `eps_revision` **×0.35** — inflecting_up 1.0 / improving 0.75 / stable 0.40 /
  deteriorating 0.10 / unknown 0.30.
* `narrative_stage` **×0.30** — early 1.0 / growing 0.75 / mature 0.30 / cooling
  0.10; macro-aligned → +0.10.
* `valuation` **×0.20** — percentile <0.3 → 1.0; 0.3–0.5 → 0.65; 0.5–0.7 → 0.35;
  >0.7 → 0.10.
* `quality_composite` **×0.15** — the existing universe-normalized quality float.

**LONG** (weights sum 1.0; hit threshold `≥ 0.55`):

* `valuation` **×0.35** (same mapping as mid) + `quality_composite` **×0.35** +
  `narrative_stage` **×0.20** (early 1.0 / growing 0.60 / mature 0.25 / cooling
  0.05) + `macro_alignment` **×0.10** (aligned 1.0 / neutral 0.5 / misaligned 0.1).

`signal_strength = {3:"triple", 2:"double", 1:"single", 0:"none"}[len(horizons_hit)]`.

### Catalyst detection merged into the single LLM call

`llm_narrative_match()` is still the **only** LLM call (one per ticker for the
top-N; `llm_orchestrator` imported in-function; TTL=3600 keyed on
`(ticker, macro_regime)`). Its prompt is widened to also request
`catalyst_summary`, `catalyst_horizon`, `catalyst_recency`, and
`already_priced_in` (instructed: `already_priced_in` is true only if the
catalyst news is >2 weeks old AND the stock already moved >10% since the news).
On **any** parse failure / non-dict / missing key / no LLM key, all catalyst
fields fail-closed to safe values (`""` / `[]` / `"none"` / `False`) via
`neutral_narrative()`.

### `key_signals` priority order (code-generated)

1. `"Triple signal: short + mid + long"` if `signal_strength == "triple"`.
2. EPS inflection if `eps_revision_direction == "inflecting_up"`.
3. Catalyst summary if non-empty.
4. Narrative stage + theme tags.
5. Entry quality with RSI + distance from 52W high.
6. Undervalued flag if `valuation_percentile < 0.3`.
7. Track B trigger if `candidate_type == "ALT_SIGNAL"`.

### Cockpit `session_state` hand-off (review-only)

After scoring, `generate_candidates()` (the non-cached normalizing wrapper)
writes two review-only hand-off keys for a **future** Cockpit integration
(never an execution path; fail-closed if no Streamlit runtime):

* `st.session_state["cockpit_triple_signals"]` — triple-hit candidates only.
* `st.session_state["cockpit_all_signals"]` — every candidate, each carrying its
  `signal_strength`.

Each record is `{ticker, short_score, mid_score, long_score, catalyst_summary,
key_signals, signal_strength, timestamp}`. Output is sorted triple → double →
single → none, and within each group by the average of (short+mid+long)/3
descending. The standalone Track B trigger (`track_b_score ≥ 0.7` → `ALT_SIGNAL`)
still fires; those candidates get short/mid/long scores computed normally.

### Scanner signal-card UI

`pages/3_Scanner.py` replaces the candidate table with **signal cards**
(`st.container(border=True)`): Row 1 ticker + `signal_strength` badge (triple =
gold `#d4a017` border + 🔥, double = green, single = blue, none = gray) +
`candidate_type` badge; Row 2 three color-coded score pills with ✓ (hit) / ○
(below); Row 3 catalyst summary (⚡) + horizon tags + recency +
`already_priced_in` warning; Row 4 first 3 key signals; Row 5 a collapsed
Details expander (full key_signals, EPS / valuation / entry, narrative + theme
tags, Track A / Track B sub-scores). Three horizon checkboxes (短线 / 中线 /
长线, all default-checked) filter on `horizons_hit` — a `none` signal is opt-in
(shown only when all three are checked). A summary line counts triple / double /
single. `SCANNER_SIGNAL_MODE`, the universe configuration, and the entire manual
scanner below `st.divider()` are preserved.

### Track B data sources (Finnhub free tier)

All three Track B alternative-data signals are sourced from the **Finnhub free
tier** (reusing the existing `FINNHUB_API_KEY`; no paid API):

| Track B signal | Finnhub endpoint | Logic |
|----------------|------------------|-------|
| Insider buying (内部增持) | `/stock/insider-transactions` | Net insider BUYING over the last 60 days — more buy than sell transactions by count AND total buy value > $500K; score blends the net-buy ratio with a value score saturating at $5M. |
| Analyst upgrades (分析师上调) | `/stock/recommendation` | A strong-buy count increase of ≥ 2 between the latest and prior monthly snapshots; score scales with the increase (saturating at 1.0). |
| Unusual news (异常新闻) | `/company-news` | Keyword match (60-day window) over the documented unusual-news groups — government / defense contracts, regulatory approvals, major partnerships, political / policy signals; score driven by the most-recent match's recency. |

Track B weights are insider **40%** / unusual-news **35%** / analyst-revision
**25%**; a composite `≥ 0.7` is a standalone `ALT_SIGNAL` trigger. (Finnhub's
price-target endpoint is premium and is intentionally NOT used.) Every fetch is
`try/except` fail-closed and cached `st.cache_data(ttl=1800)`.

### Chinese localization of display fields

When the app language is Chinese (`st.session_state["language"] == "zh"`,
threaded as `lang="zh"` through `generate_candidates` → `build_candidate_signal`
/ `score_ticker`), the human-readable **display** fields — `catalyst_summary`,
the narrative theme-tag labels, and the `key_signals` list — are translated to
Chinese via `lib/translator.py` (deep-translator / Google Translate) **before**
being stored on the `CandidateSignal`. The English LLM prompt and the English LLM
response are **unchanged**; only the final display text is localized. Translation
runs through the cached `_localize_texts(texts, lang)` helper
(`st.cache_data(ttl=3600)`, key includes `lang`) and the
`_generate_candidates_cached(..., lang)` cache key also includes `lang`, so each
language caches separately and repeated strings are not re-translated.
Translation is fail-closed — any error returns the original English strings.

### Theme-tag fallback (THEME_BASKETS reverse lookup)

The merged LLM prompt now **requires** `theme_tags` to be chosen from the fixed
taxonomy (one or more; the closest label when only approximate; `"other"` only
when nothing applies). If the LLM still returns an empty `theme_tags` (or a
ticker carries the neutral fallback narrative), `build_candidate_signal` applies a
deterministic **reverse-lookup fallback** (`_theme_tags_for_ticker`): when the
ticker appears in one or more `lib/theme_baskets.THEME_BASKETS` constituent
lists, the matching theme's `label_zh` (zh) / `label_en` (en) is used as the
theme tag (up to 3). `THEME_BASKETS` is imported read-only and never modified.

### LLM-coverage tuning + Layer-1 liquidity floor

Because only the top `llm_n` Layer-1 survivors receive a real (merged-LLM)
narrative — the rest keep `neutral_narrative()` with `narrative_stage="unknown"`
and empty catalyst — coverage was tuned so far fewer cards read `unknown`:

* The Scanner LLM narrative-depth slider now ranges **10–100 (default 50)**, and
  `generate_candidates` defaults `llm_n=50` and clamps to **10–100**. For the S&P
  top-100 anchor (≈99 pass Layer 1), LLM narrative coverage rises from **31%** @
  `llm_n=30` → **51%** @ 50 → **100%** @ 100.
* The stale **`FI`** entry in `SP500_TOP_100` (yfinance returns a 404 — Yahoo only
  resolves Fiserv under the legacy **`FISV`** symbol) is replaced with `FISV`, so
  Fiserv is no longer dropped at Layer 1 as missing-fundamentals.
* A Layer-1 **liquidity floor** `_MIN_DOLLAR_ADV = $10M` (average daily DOLLAR
  volume = `averageVolume × price`, computed from the yfinance `info` dict — no
  extra fetch) excludes thinly-traded names (reason `"liquidity"`). It is applied
  ONLY when both a volume and a price field are present (missing data never
  excludes on liquidity), and it **never** consults RSI / momentum / 52W distance
  — so an oversold early-opportunity large-cap still passes. The `$2B` market-cap
  floor and `-50%` 30-day price-break gates are retained. For the (already large
  + liquid) S&P top-100 anchor this gate is a safety net rather than an aggressive
  trimmer; it mainly bites once illiquid theme-basket / manually-added small caps
  enter the universe, lifting the LLM-covered fraction of the remaining pool.

### Guardrails (v3)

Free sources only (yfinance + Finnhub free tier; no Quiver / Unusual Whales). No
broker / order / execution; no order-ticket / broker-payload / account-id /
execution-id fields; no buy/sell instruction; `approved_for_execution` remains
False or absent. No DB / vector store / persistence. All data calls fail-closed.
`lib/macro_regime.py`, `lib/macro_data.py`, `lib/theme_baskets.py`,
`lib/workflow_state.py`, `.claude/agents/*`, pages 1–2 and 4–8 (incl.
`pages/7_Investment_Cockpit.py` and `pages/8_Macro_Dashboard.py`) are not
modified; `ui_utils.py` is modified only to add new `t()` keys (plus updating the
existing LLM-depth help text to the new 10–100 range).
`scripts/test_reliability_phase_6b_v3_horizon_scoring.py` is mock-only
(**189/189**). Phase 6C is not implemented.

---

## Disclaimer

This document is for research purposes only and does not constitute investment
advice. Markets involve risk; invest with caution.
