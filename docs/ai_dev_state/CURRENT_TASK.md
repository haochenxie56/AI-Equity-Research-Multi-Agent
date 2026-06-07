# Current Task

> **History archived.** Everything prior to Phase 7B now lives in
> `docs/ai_dev_state/archive/CURRENT_TASK_pre_7b_20260605.md` (full 1955-line
> history preserved verbatim). This file keeps only the active phase. The
> long-form running status remains in `docs/ai_dev_state/PROJECT_STATE.md`.

## Phase 7B — Multi-window RS, Two-Ring Rotation, Market-Internals Fragility (CURRENT — Implemented + fix round)

Makes rotation VISIBLE and market deterioration EARLY-VISIBLE. **All
deterministic; no LLM.** Phase doc
`docs/reliability_phase_7b_rotation_internals.md`; suite
`scripts/test_reliability_phase_7b_rotation_internals.py` **187/187** (mock-only).
Full canonical set green: 7A 115, stopbleed 64, 6c_b 47, equity_render_order 50,
6c_trading_desk 118, 6c_v3_entry_v4 47, 6b_v3_horizon_scoring 189, theme_baskets
146, scanner_rotation_adapter 15. Pages 2 & 7 render-smoke clean (AppTest).

- **Task 1 — Multi-window RS** (`lib/relative_strength.py`): excess vs SPY/QQQ
  over `RS_WINDOWS` (5d/10d/1m/3m/6m/12m); per-horizon composites `rs_short`
  (5D/10D) / `rs_mid` (1M/3M) / `rs_long` (6M/12M); `composite_for(horizon)` falls
  back to the unchanged legacy `rs_composite` (7A byte-identical). 12M→6M degrade
  sets `rs_window_degraded`. why_now RS line follows the selected horizon
  (5日/近1月/近6月); cards carry `why_now_by_horizon`; full `windows` set in the
  snapshot.
- **Task 2 — Two-Ring Rotation**: OUTER (`lib/rotation.py`)
  `offense_defense_reading` + `build_sector_excess(loader)` +
  `compute_offense_defense` (existing `score` contract untouched). INNER
  (`lib/theme_baskets.py`) EXCESS vs QQQ over the window set;
  `classify_divergence` → stage (rotating_in/leading/rotating_out/out_of_favor,
  boundary on the weak side); `compute_theme_breadth` with direction-aware
  confirmation (single-stock guard); macro-lens default window (display only);
  `momentum_score` rebased to EXCESS-3M percentile. Stage+breadth on the card,
  snapshot, Cockpit Section B, Sector theme table, Send-to-Scanner.
- **Task 3 — Market-Internals Fragility** (`lib/market_internals.py`, NEW): pure
  components (distribution days IBD, breadth ±SMA, good-news-sold, weak-bounce,
  offense/defense). `compute_fragility` → normal/elevated/high with
  `apply_hysteresis` (escalate after 2 **trading-day-adjacent** sessions — single
  spike never escalates; de-escalate faster). Snapshot `_meta` is the memory.
  **STRICT tighten-only**: `macro_regime.py` FROZEN (byte-identical invariant);
  high gates SHORT in-zone Actionable→Research Required (`internals_deteriorating`,
  mirrors calendar gate); elevated annotates; Cockpit banner; `thesis_monitor`
  watch-level annotation on signal D (thesis_status untouched).

### Fix round (Codex — 2 should-fix, both correctness)

1. **Hysteresis adjacency via the benchmark trading calendar** — adjacency comes
   from `is_adjacent_session(d1,d2,benchmark_index)` (the cached SPY→QQQ date index
   IS the trading calendar; no new dep/network): consecutive iff no trading date
   lies strictly between the dates. `apply_hysteresis(..., benchmark_index=)`
   breaks the chain on a non-adjacent pair (gap only DELAYS escalation). Index
   can't cover the dates → fallback to `hysteresis_max_calendar_gap_days=4` +
   `adjacency_degraded`. Tests: Fri+Mon consecutive; Fri+Wed (Mon/Tue between)
   break; holiday-Monday Fri+Tue consecutive; fallback flag; DatetimeIndex parity.
2. **RS date-aligned excess** — `benchmark_frames` keeps the dated benchmark Close
   Series; `compute_relative_strength(..., bench_closes=)` inner-joins ticker∩bench
   on dates per window so a halted/missing session never compares mismatched
   effective dates; sufficiency runs on the aligned length. Positional fallback
   (no dates / fixtures) unchanged → 7A byte-compat. Tests: gap fixture excess ==
   hand-computed aligned value, ≠ positional-slice value.

**Created:** `lib/market_internals.py`,
`scripts/test_reliability_phase_7b_rotation_internals.py`,
`docs/reliability_phase_7b_rotation_internals.md`.
**Modified:** `lib/relative_strength.py`, `lib/rotation.py`, `lib/theme_baskets.py`,
`lib/opportunity_ranker.py`, `lib/thesis_monitor.py`, `pages/2_Sector.py`,
`pages/7_Investment_Cockpit.py`, `ui_utils.py`, state docs.
