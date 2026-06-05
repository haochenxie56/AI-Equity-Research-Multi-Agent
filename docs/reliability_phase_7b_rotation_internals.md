# Phase 7B — Multi-window Relative Strength, Two-Ring Rotation Engine, and Market-Internals Fragility Layer

**Status**: Implemented + Codex fix round (×2) (lib + tests green). Review-only;
not investment advice.
**Suite**: `scripts/test_reliability_phase_7b_rotation_internals.py` — **90/90**,
mock-only / offline. Canonical regressions all green (7A 115, stopbleed 64,
6c_b 47, equity_render_order 50, 6c_trading_desk 118, 6c_v3_entry_v4 47,
6b_v3_horizon_scoring 189, theme_baskets 146, scanner_rotation_adapter 15).

All computation is **deterministic; no LLM anywhere in this phase**. Every window
and threshold lives in a visible config block for later calibration.

This phase makes **rotation VISIBLE** and **market deterioration EARLY-VISIBLE**.
It addresses three real observations:

1. All three horizon views showed the same 1-month RS — short-horizon grades were
   not backed by short-horizon evidence.
2. Single-window absolute theme momentum cannot see rotation (rotation *is* the
   divergence between windows) and keeps ranking yesterday's winners on crash days.
3. The regime classifier reads priced-in stress (VIX, spreads) and only flips
   *after* a drawdown, while market internals (strong earnings sold, shrinking
   volume in leading themes, narrowing breadth) deteriorate for days beforehand.

---

## Task 1 — Multi-window Relative Strength (`lib/relative_strength.py`)

### Window config

```python
RS_WINDOWS = {"5d": 5, "10d": 10, "1m": 21, "3m": 63, "6m": 126, "12m": 252}  # trading days
HORIZON_RS_WINDOWS = {
    "short": ("5d", "10d"),   # primary, secondary
    "mid":   ("1m", "3m"),
    "long":  ("6m", "12m"),
}
_BENCH_PERIOD = "2y"   # benchmarks are the single per-refresh fetch → always 12M-capable
```

* Excess returns vs **SPY and QQQ** are computed over every window. Flat fields
  (`ret_<win>`, `ret_<win>_vs_spy`, `ret_<win>_vs_qqq`) plus a full `windows`
  snapshot dict (`{win: {ret, vs_spy, vs_qqq}}`) are stored per ticker — the raw
  material for future RS-slope signals.
* **Horizon consumption**: each horizon's weight table consumes its **own**
  composite — `rs_short` (5D/10D), `rs_mid` (1M/3M), `rs_long` (6M/12M). The
  `RelativeStrength.composite_for(horizon)` helper returns the horizon composite,
  falling back to the legacy `rs_composite` when 7B did not compute one (so pre-7B
  RS objects and the 7A suite score **byte-identically**).
* **LONG RS is trend confirmation, not chase-the-winner.** The overextension
  blocker already guards the chase side; the LONG composite simply confirms the
  6M/12M trend is intact.
* **Data sufficiency / degrade**: cached history is ~1y. When **12M cannot be
  computed** the reading degrades to **6M** and sets `rs_window_degraded=True`.
  Cache-only discipline and the 7A `rs_degraded` behavior are unchanged.
* **Display**: the `why_now` RS line follows the **selected horizon** — SHORT
  shows `5日相对QQQ +x%`, MID `近1月…`, LONG `近6月…`. `build_reason_codes(...,
  horizon=…)` selects the window; the ranker stores `why_now_by_horizon` for
  enriched cards so the Cockpit selector renders the matching line.
* **Backward compat**: `compute_rs_composite` and all legacy flat fields are
  unchanged; consumers (scoring, snapshot, reason codes) were updated in one pass
  with systematic field naming.
* **Date-aligned excess** (fix round): `benchmark_frames` keeps the dated
  benchmark Close Series; `compute_relative_strength(..., bench_closes=)`
  inner-joins ticker∩benchmark on **dates** before windowing, so a halted/missing
  ticker session never compares N ticker bars vs N benchmark bars ending on
  different effective dates. Sufficiency runs on the **aligned** length (degrades
  honestly: 12M→6M / `rs_window_degraded`). The positional path (no dates / fixture
  frames) is unchanged → 7A byte-compat preserved.

---

## Task 2 — Two-Ring Rotation Engine

### Outer ring — GICS sector layer (`lib/rotation.py`)

* Multi-window **relative returns vs SPY** over `OD_WINDOW_DAYS`
  (`5d/10d/1m/3m/6m/12m`) via `build_sector_excess(ohlcv_loader=…)` (injectable —
  the network-free path passes a cache-only loader). The existing `score`
  contract in `compute_sector_scores` is **unchanged** (no numeric-contract break).
* **Offense / Defense reading** (`offense_defense_reading(sector_excess)`), a pure
  function consumed by both the Sector page and the fragility layer:

  | Basket | Sectors |
  |--------|---------|
  | OFFENSE | Information Technology, Consumer Discretionary, Communication Services, Semiconductors |
  | DEFENSE | Utilities, Consumer Staples, Health Care |

  Output: `direction` (offense / defense / balanced), `magnitude`
  (strong ≥ 5pp / moderate ≥ 2pp / mild), `avg_diff` (mean offense−defense pp),
  `by_window` breakdown, and `confirming_windows` (windows confirming the
  direction beyond `OD_CONFIRM_THRESHOLD_PP = 1.0`). `|avg_diff| ≤
  OD_BALANCED_PP (1.0)` → balanced. **This reading is also input (e) to Task 3.**

### Inner ring — AI theme layer (`lib/theme_baskets.py`)

* `compute_theme_momentum` now computes **EXCESS return vs benchmark** (config
  `THEME_BENCHMARK_DEFAULT = "QQQ"`, per-theme overridable via a `benchmark` key)
  over the multi-window set, replacing the single fixed window. `compute_all_themes`
  fetches each benchmark **once** and ranks `momentum_score` by the **EXCESS-3M**
  percentile.

* **Divergence matrix** — 5D vs 1M excess quadrants → deterministic stage label.
  "strong" = excess **strictly greater** than the threshold; the boundary value
  itself is on the weak side.

  ```python
  DIVERGENCE_THRESHOLDS = {"excess_5d_pp": 0.0, "excess_1m_pp": 0.0}
  ```

  | 5D excess | 1M excess | stage |
  |-----------|-----------|-------|
  | strong | strong | `leading` |
  | strong | flat/weak | `rotating_in` |
  | weak | strong | `rotating_out` |
  | weak | weak | `out_of_favor` |

* **Group-confirmation breadth** per theme: `% of constituents beating the
  benchmark over the active window` + `% above SMA20`. A stage is **confirmed**
  only when breadth passes `BREADTH_CONFIRM_FRACTION = 0.50` (direction-aware: a
  bullish stage needs broad participation `beat ≥ 0.5`; a bearish stage needs
  broad weakness `beat ≤ 0.5`). Otherwise the label carries **unconfirmed** — the
  single-stock event guard.

* **Macro lens** (display/default-window only — never re-ranks):

  ```python
  MACRO_LENS_WINDOW = {"risk_off": "5d", "transition": "5d", "risk_on": "1m", ...}
  ```

  `risk_off`/`transition` default to the 5D divergence + downside-resilience lens;
  `risk_on` to the 1M trend. Theme scores themselves are not regime-adjusted.

* Stage label + breadth land on `OpportunityCard.theme_stage` /
  `theme_stage_confirmed`, on the daily snapshot, and (via the ranker's
  excess-based `momentum_score`) on the theme-momentum scoring component.

---

## Task 3 — Market-Internals Fragility Layer (`lib/market_internals.py`)

Answers **"where are we HEADING"** while the regime layer keeps answering "where
are we CONFIRMED to be". **`lib/macro_regime.py` is FROZEN** — this module never
imports, calls, mutates, or overrides it.

### Components (each deterministic, each from cached/free data, each attributable)

| # | Component | Definition |
|---|-----------|------------|
| a | Earnings reaction quality | `count_good_news_sold` — a **beat** whose next-session return ≤ `good_news_sold_reaction_pp (0.0)` is "good news sold" (the AVGO pattern). Skipped silently where data is unavailable. |
| b | Breadth trend | `% of universe above SMA20/SMA50` (level) + slope vs a prior reading; `breadth_weak_pct = 0.40`, `breadth_slope_drop = 0.08`. Leading-theme internal-breadth narrowing flag. |
| c | Volume character | IBD-style **distribution-day** count on SPY/QQQ (down ≥ `0.2%` on higher volume than the prior session, rolling 25 sessions) + leading-theme shrinking-volume flag. |
| d | Rally quality | After a down day ≤ `rally_down_day_pct (-1%)`, was the bounce on **shrinking volume** (< `0.90×` the down-day volume) → weak-bounce flag. |
| e | Offense/defense | The Task 2 outer-ring reading (defensive lean adds points). |

### Composite + hysteresis

Points: distribution-days-high `+2` / -elevated `+1`; good-news-sold-high `+2` /
-elevated `+1`; breadth-weak `+1`; breadth-narrowing `+1`; leading-theme breadth
narrowing `+1`; leading-theme volume shrinking `+1`; weak-bounce `+1`; defensive
offense/defense strong `+2` / else `+1`. Raw level: `≥ high_points (4)` → **high**,
`≥ elevated_points (2)` → **elevated**, else **normal**.

**Hysteresis** (the snapshot history is the memory):
`hysteresis_escalate_sessions = 2`, `hysteresis_deescalate_sessions = 1`,
`hysteresis_max_calendar_gap_days = 4` (fallback only). Escalation to a higher
*effective* level requires the raw level to hold at/above it for **N consecutive
TRADING sessions including today** — a **single-day spike never escalates**.
Adjacency is decided by the **benchmark (SPY→QQQ) trading-date index** — the
cached OHLCV index *is* the trading calendar (no new dependency, no network):
`is_adjacent_session(d1, d2, index)` is true iff **no benchmark trading date lies
strictly between** the two snapshot dates (so Fri→Mon is adjacent, a holiday Monday
makes Fri→Tue adjacent, and Fri→Wed with Mon/Tue trading is a break). A break
restarts the count, so a gap can only **delay** escalation, never fabricate it.
When the index can't cover the dates (cache miss/stale) it **falls back** to the
`hysteresis_max_calendar_gap_days` bound and sets `adjacency_degraded` (never
silently assumes adjacency). De-escalation is **faster** (1 session below) and
gap-irrelevant. Prior level, recent raw levels, AND their dates come from the
daily snapshot `_meta` via `history_from_snapshots`.

### Effects — STRICT tighten-only contract

* Fragility **NEVER** changes the regime label, never flips `risk_on→off`, never
  relaxes any gate. Test invariant: with fragility forced **high**, the
  `MacroRegimeResult` object is **byte-identical** (`==`).
* `elevated`/`high` tighten **SHORT-horizon** status gating: an in-zone SHORT
  candidate degrades from *Actionable Now* to a wait state with reason code
  `internals_deteriorating` — mirroring the calendar gate in `derive_status`.
  Config: `GATE_BY_LEVEL = {"high": ("short",), "elevated": (), "normal": ()}` —
  **default: high gates SHORT, elevated only annotates.**
* Cockpit banner: alongside the regime line, fragility level + top triggered
  components with numbers (e.g. *"regime risk_on, but internals: distribution
  days 4/25, breadth 58%→41%, 2 good-news-sold"*). Bilingual. Sector page gets the
  full component table.
* `thesis_monitor`: fragility is a **WATCH-level annotation** on signal D
  (`fragility_note` / `fragility_watch`) — high fragility notes the holding but
  **never escalates `thesis_status`** by itself. The monitor's existing semantics
  (the test-pinned `compute_thesis_status`) are untouched.
* **Snapshot** (mandatory — fragility's lead/false-positive rate is judged from
  history later): daily level + raw level + points + triggered flags + **every
  component value** via `fragility_snapshot`.

### Performance & data constraints

* The ranking/refresh path stays **network-free** (7A contract): internals and
  breadth come from the signal pipeline's cached OHLCV (cache-only loaders, degrade
  flags on misses); benchmarks are the single fetch; the Finnhub earnings calendar
  is at most one bulk call per refresh, skippable/degradable.
* **Frozen**: `lib/macro_regime.py`, `lib/workflow_state.py`, `lib/technical.py`,
  `.claude/agents/*`. No paid APIs. Review-only outputs.

---

## Judgment calls

1. **`rs_composite` kept byte-identical.** Rather than rebasing the legacy
   composite onto the new windows (which would have moved every 7A score), the
   legacy 5D+1M roll-up is frozen and three **new** per-horizon composites were
   added. Pre-7B RS objects fall back to `rs_composite`, so the 7A suite is
   unaffected; the ranker consumes the per-horizon composite when present.
2. **Sector `score` contract preserved.** `compute_sector_scores` was *not*
   rewritten to multi-window relative returns (that would break Sector-page
   consumers); the multi-window machinery lives in `build_sector_excess` +
   `offense_defense_reading`, which the offense/defense panel and fragility layer
   consume. This satisfies "keep the existing score consumers working."
3. **Theme breadth fetches constituents.** Breadth is inherently constituent-level,
   so `compute_all_themes` reads constituent histories (cached 30 min) — analogous
   to the single per-refresh theme fetch, not part of the per-ticker network-free
   ranking loop (the ranker receives precomputed `themes`). The network-free
   fragility path uses its own cache-only loaders.
4. **Fragility gate → `Research Required`.** To mirror the calendar gate exactly,
   the SHORT in-zone degrade lands on `Research Required` (a wait state) with the
   `internals_deteriorating` reason, rather than introducing a new status value.
5. **Thesis fragility is annotation-only.** To keep `compute_thesis_status`
   byte-identical (it is test-pinned), fragility adds a note/flag and does not feed
   the four-flag tally at all — strictly within "never escalates beyond watch".

---

## Codex fix round (2 should-fix, both correctness)

1. **Hysteresis adjacency via the benchmark trading calendar** (revised).
   `history_from_snapshots` previously discarded dates, so snapshots from
   2026-06-01 and 2026-06-04 fabricated "2 consecutive" readings across missed
   days. The adjacency source is now the **benchmark (SPY→QQQ) trading-date
   index** — NOT a calendar-day heuristic and NOT a new dependency:
   `is_adjacent_session(d1, d2, benchmark_index)` is true iff no benchmark trading
   date lies strictly between the two dates. `apply_hysteresis(recent_dates=,
   today_date=, benchmark_index=)` breaks the chain (and restarts counting) on a
   non-adjacent pair → a gap can only **delay** escalation, never fabricate it;
   de-escalation stays immediate. When the index can't cover the dates it falls
   back to the `hysteresis_max_calendar_gap_days = 4` bound and flags
   `adjacency_degraded` on the reading (+ `hysteresis_adjacency` in `degraded`,
   `fragility_adjacency_degraded` in the snapshot). `compute_market_fragility`
   feeds the cached SPY (fallback QQQ) date index. Tests: Fri+Mon (weekend, no
   trading day between) consecutive; Fri+Wed with Mon/Tue between → break, no
   escalation; market-holiday Monday → Fri+Tue still consecutive; fallback path
   flags `adjacency_degraded`; pandas DatetimeIndex parity; config visible.
2. **RS excess needs date-aligned series.** Window returns were computed from
   independent positional close lists for ticker and benchmark, then subtracted —
   no date-index alignment, so a halted ticker session compared mismatched dates.
   `compute_relative_strength(..., bench_closes=)` now inner-joins on the common
   date index before windowing (`_aligned_window_returns`); sufficiency runs on the
   aligned length; the legacy positional/fixture path (and `rs_composite`) is
   untouched (7A byte-compat). Tests: a fixture with deliberately missing ticker
   dates → excess equals the hand-computed aligned value, not the positional-slice
   value; QQQ gaps align independently.
