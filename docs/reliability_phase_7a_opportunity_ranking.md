# Phase 7A — Opportunity Ranking MVP

**Status:** Implemented + **fix round 1** (6 Codex items + 3 product issues) +
**fix round 2** (Codex re-review: 3 should-fix + 2 nits) — Awaiting Codex Review.
Phase 7A is **not accepted** in this pass. Phase 7B has not started.

Fix round 1 revised the status mapping (Avoid Chasing reserved; horizon-aware
`below_zone`), reason-code informativeness, blocker hygiene (per-card horizon
filtering + market-wide banner), display-time concentration refs, contract
hardening (deterministic tie-break, cache-only RS, atomic snapshot writes), and
setup scoping. **Fix round 2** added: **per-horizon status** (status / reason /
next_trigger are computed for short/mid/long and stored as maps — the Cockpit
selector now shows the correct status per view, fixing the MU mid-view anomaly);
the Cockpit now actually uses the **cache-only RS path** (`build_rs_map_cache_only`
→ `lib.cache_manager.load`); the fundamental gate also reads the **engine's own
`missing_conditions`** (Fix 3); `trigger_pending` removed from the why_now
vocabulary (status reason only); and the Row-4 precedence is pinned.

**Final fix** (Codex re-review): the Fix-3 engine classifier is now
**registry-backed** — `lib/order_advisor.py` owns a `MISSING_CONDITION_REGISTRY`
(stable `code` + `category` + bilingual text) that its emission sites reference;
the ranker classifies by the declared category first and only falls back to
substring matching for legacy/unregistered conditions. A pure string/constants
refactor (no numeric/control-flow change). See the inline "REVISED" / "Fix round
2" / "Fix 3" sections.

## Purpose

The project's entry/risk backend (Entry Strategy v4 in `lib/order_advisor.py`,
the Thesis Monitor, the Trading Desk) is mature, but the **idea-generation front
end is weak**. Phase 7A turns the existing signal candidates into a ranked,
actionable **opportunity list** that answers five questions for every name:

1. Which tickers deserve 10 minutes of attention today?
2. Why now / why does it matter?
3. Can I buy now?
4. If not, what am I waiting for?
5. What is the risk?

This is an **MVP and an orchestration layer**. It implements **no new
entry-zone, stop, or technical-threshold logic**. Every number/zone/threshold
comes from existing deterministic code. The card framing is a **research queue
("worth 10 minutes of attention"), not a buy list** — all wording is
review-only. `approved_for_execution` is never set.

## Single source of truth

| Concept | Single source |
|---|---|
| Entry zone position, stop, target, R:R, position size, hard gates | `lib.order_advisor.compute_price_levels` (deterministic numeric path only — never `generate_order_narrative`, never an LLM) |
| Three horizon scores' raw inputs | `lib.candidate_generator` / `lib.signal_engine` `CandidateSignal` fields |
| Theme momentum & membership | `lib.theme_baskets.compute_all_themes` + `THEME_BASKETS` |
| Macro regime + horizon bias | `lib.macro_regime.classify_regime` (read-only) |
| Economic release dates (CPI/PPI/NFP) | `lib.macro_data.fetch_economic_releases` (read-only) |
| Next earnings date | `lib.data_fetcher.get_earnings_calendar` (read-only) |
| Relative strength | `lib.relative_strength` (new; reads cached OHLCV via `ui_utils.load_ohlcv`) |

The opportunity ranker **translates** these outputs; it does not recompute them.

## Files created / modified

**Created:**
- `lib/relative_strength.py` — simplified RS (Task 2). New helper module so the
  frozen `lib/technical.py` is left untouched.
- `lib/opportunity_ranker.py` — the orchestration layer (Tasks 1, 3, 4).
- `scripts/test_reliability_phase_7a_opportunity_ranking.py` — mock-only suite.
- `docs/reliability_phase_7a_opportunity_ranking.md` — this doc.

**Modified:**
- `pages/7_Investment_Cockpit.py` — Section C upgraded to the Opportunity Card
  panel + horizon selector; refresh now ranks candidates and writes the daily
  snapshot.
- `pages/9_Trading_Desk.py` — Section 3 adopts the unified five-state naming and
  carries the new fields (setup/status/blockers/grade) from `td_pending_signals`.
- `ui_utils.py` — additive bilingual `opp_*` / unified `td_status_*` `t()` keys.
- `lib/order_advisor.py` — **string/constants-only** refactor (final fix):
  `MISSING_CONDITION_REGISTRY` + `MissingCondition` + `missing_condition_category`
  + `MISSING_CONDITION_TEXT_TO_CATEGORY`; emission sites and `_GATE_REASON_*` now
  reference the registry. Zero numeric/threshold/gate/control-flow change; emitted
  strings byte-identical.
- `docs/ai_dev_state/PROJECT_STATE.md`, `docs/ai_dev_state/CURRENT_TASK.md`.

## Five-state opportunity status

The existing `in_zone / above_zone / below_zone / blocked` vocabulary (Trading
Desk Section 3) is **unified** into one five-state system shared by the Cockpit
and the Trading Desk:

| State | Meaning |
|---|---|
| **Actionable Now** | In the entry zone, gates pass, no critical/calendar blocker for the displayed horizon. |
| **Wait for Pullback** | Extended above the entry zone; quality otherwise good. |
| **Wait for Breakout** | Entry requires a trigger not yet fired (price below the zone — must reclaim/break a level to enter). |
| **Research Required** | System lacks sufficient data/confidence for an entry judgment. |
| **Avoid Chasing** | Blocked by overextension / a critical hard gate. |

### Mapping table (engine outputs → five states) — REVISED (fix round)

`derive_status(levels, candidate, blockers, horizon)` applies this **priority
order** (first match wins). Inputs come from `PriceLevelResult` (`entry_status`,
`risk_overlay_passed`, `valuation_confidence`, `next_trigger`,
`missing_conditions`) and the candidate (`candidate_type`,
`eps_revision_direction`).

Two semantic corrections vs the first cut:

- **(a) Avoid Chasing is RESERVED** for genuine overextension and risk-overlay
  failures. A `blocked` status caused by an unconfirmed entry **trigger** (EMA
  trend / volume / breakout pending — a missing *trigger*, not overextension) is
  **Wait for Breakout**, not Avoid Chasing. This removes the user-visible
  contradiction where a Pullback-to-Support card also read "Avoid Chasing".
- **(b) `below_zone` is horizon-aware** and never a bullish "breakout": below a
  support/SMA zone (SHORT/MID) is breakdown territory, and below a valuation band
  (LONG) is "cheaper than the value zone" — both → **Research Required** (never
  Wait for Breakout; never Avoid Chasing merely for being cheap).

| # | Condition | State |
|---|---|---|
| 1 | `risk_overlay_passed is False` | **Avoid Chasing** |
| 2 | `entry_status == "above_zone"` **AND** a critical blocker (valuation stretched / overextended) | **Avoid Chasing** |
| 3 | `entry_status == "above_zone"` (otherwise — quality name extended) | **Wait for Pullback** |
| 4 | `candidate_type == "ALT_SIGNAL"` (Track-B-only) **OR** (`horizon == "long"` **AND** `valuation_confidence == "low"`) | **Research Required** |
| 5 | `entry_status ∈ {below_zone, wait}` (horizon-aware: stabilization / below-value) | **Research Required** |
| 6 | `entry_status == "blocked"` **AND** a **fundamental gate** (`eps_revision_direction == "deteriorating"`, a critical ranker valuation/overextension blocker, **or** an engine `missing_conditions` entry classed fundamental — Fix 3) | **Avoid Chasing** |
| 7 | `entry_status == "blocked"` (pending entry trigger — trend/volume not yet confirmed) | **Wait for Breakout** (card surfaces `next_trigger`) |
| 8 | `entry_status == "in_zone"` **AND** a fundamental gate | **Avoid Chasing** |
| 9 | `entry_status == "in_zone"` **AND** the **earnings** calendar blocker gates the displayed horizon | **Research Required** |
| 10 | `entry_status == "in_zone"` (no blocking conditions) | **Actionable Now** |

**Per-horizon status (Fix round 2).** Status is **derived independently for
short / mid / long** during top-N enrichment — `compute_price_levels` is called
once per horizon (deterministic local math over cached OHLCV; ≤ 3 × top_n calls,
still zero per-ticker network fetch). The card stores `status_by_horizon`,
`next_trigger_by_horizon`, and `status_reason_by_horizon` maps; `status` /
`next_trigger` remain as **dominant-horizon convenience** values (the Trading
Desk single-value hand-off also carries the maps). The Cockpit selector renders
the **selected** horizon's status and `next_trigger`, so a mid-view name no
longer shows a long-horizon "valuation anchor" trigger (the MU anomaly). The
earnings gate (row 9) is horizon-parameterized, so the displayed-horizon
behaviour is automatic, not special-cased.

**Row-4 precedence (pinned, intended).** A price-based overextension verdict
(rows 1–3: Avoid Chasing / Wait for Pullback) is evaluated **before**
provenance-based Research-Required (row 4, `ALT_SIGNAL`). Avoid Chasing is the
more protective state, so a price warning wins: `ALT_SIGNAL + above_zone +
critical → Avoid Chasing` (and `+ above_zone` without a critical → Wait for
Pullback). Pinned by a test fixture.

### Fix 3 — engine `missing_conditions` classification (registry-backed)

`derive_status`'s fundamental gate also consults the **engine's own**
`missing_conditions` (so an engine valuation/EPS block routes to Avoid Chasing
even when the candidate arrives via a legacy hand-off with no ranker blockers).

**Classification is registry-backed (final fix).** `lib/order_advisor.py` owns a
`MISSING_CONDITION_REGISTRY` — one entry per emitted condition, each a stable
`code` + `category` + bilingual text (`MissingCondition.text` reproduces the
exact emitted string). The engine's emission sites reference the registry
instead of inlining literals, and the ranker classifies by the **declared
category first** (via `order_advisor.MISSING_CONDITION_TEXT_TO_CATEGORY`), so a
wording change in `order_advisor` can never silently misroute a block. The
substring matcher (`ENGINE_*_MARKERS`) is a **fallback only** for legacy /
unregistered conditions (e.g. stale pending signals in `session_state`).
**Fundamental wins on collision.**

| Registry code | category | text (EN / ZH) | blocked → |
|---|---|---|---|
| `price_below_ema20` | trigger | price not above EMA20 / 价格未站上EMA20 | **Wait for Breakout** |
| `ema10_below_ema20` | trigger | EMA10 below EMA20 / EMA10低于EMA20 | **Wait for Breakout** |
| `rsi_out_of_band` | trigger | RSI outside 40–68 / RSI不在40–68 | **Wait for Breakout** |
| `volume_not_confirmed` | trigger | volume not confirmed / 量能未确认 | **Wait for Breakout** |
| `bearish_candlestick` | trigger | bearish candlestick / 出现看跌K线 | **Wait for Breakout** |
| `eps_deteriorating` | fundamental | EPS revisions deteriorating / EPS预期下修 | **Avoid Chasing** |
| `valuation_stretched` | fundamental | Valuation stretched (≥70th pct) / 估值偏高(≥70百分位) | **Avoid Chasing** |

Fallback markers (legacy/unregistered only): fundamental — `eps`, `valuation`,
`estimate`, `quality`, `fundamental` / `估值`, `下修`, `基本面`, `质量`; trigger —
`ema`, `sma`, `rsi`, `volume`, `candlestick`, `price`, `trend`, `breakout` /
`支撑`, `突破`, `均线`, `量能`, `价格`, `看跌`. Anything `blocked` not classed
fundamental is a pending entry trigger → Wait for Breakout. The refactor is
**string/constants only** — no numeric logic / threshold / gate / control-flow
change; `missing_conditions` stays a list of the same display strings, so every
consumer (LLM order-narrative serializer, Trading Desk cards, thesis monitor,
existing fixtures) is unaffected. A test pins every registry entry through
`derive_status` and an AST guard fails the suite if any inline condition literal
is added outside the registry.

`status_next_trigger()` surfaces the engine's own `next_trigger` text (Wait for
Breakout) or a horizon-aware reason code (`stabilization_needed` for SHORT/MID
below-zone, `below_value_zone` for LONG below-zone) onto the card. Only the
**earnings** calendar blocker gates status; FOMC/CPI are market-wide and shown in
the panel banner (Task 3), not as per-ticker status gates.

**Invariants (asserted by the test suite):** `pullback_to_support=True` never
co-occurs with **Avoid Chasing** (a name the engine flags Avoid has its pullback
badge dropped during enrichment); `below_zone` never yields **Wait for Breakout**.

Status is only derived for the **top-N enriched** cards; outside the top N it is
`None` (the candidate was scored but the entry engine was not run for it — see
Performance below).

## Opportunity score & weight tables

Three **independent** horizon scores (no blended single score). Each is a
weighted sum of normalized [0,1] component scores, minus rule-based blocker
penalties, clamped to [0,1]. Component scores:

| Component | Source | Normalization |
|---|---|---|
| `signal` | the horizon's own `short/mid/long_score` | already 0–1 |
| `theme` | candidate theme's `momentum_score` | already 0–1 |
| `rs` | `RelativeStrength.rs_composite` | already 0–1 |
| `catalyst` | `catalyst_recency` + `already_priced_in` | recent & not-priced-in → high |
| `valuation` | `1 − valuation_percentile` | cheaper → higher |
| `entry` | `entry_quality_label` | good 1.0 / fair 0.6 / extended 0.3 / avoid 0.0 |

**Starting weight tables** (calibration baseline — kept in one visible
`HORIZON_WEIGHTS` config block in `lib/opportunity_ranker.py`; RS carries 0.20 in
every horizon per the outline):

| Component | short | mid | long |
|---|---|---|---|
| signal | 0.30 | 0.30 | 0.25 |
| rs | 0.20 | 0.20 | 0.20 |
| catalyst | 0.20 | 0.10 | 0.05 |
| theme | 0.15 | 0.20 | 0.15 |
| entry | 0.10 | 0.05 | 0.10 |
| valuation | 0.05 | 0.15 | 0.25 |

Each column sums to 1.00. The differing weights produce different orderings of
the same candidate set across horizons (asserted by the test suite).

### Blocker score penalties (`BLOCKER_PENALTIES`)

Applied to **all** candidates (network-free, **ticker-specific** signals only):
`valuation_high` 0.10, `theme_lagging` 0.05. `macro_regime_mismatch` is **no
longer a per-card penalty** — it is uniform across all candidates at a horizon
(so it never changes the ranking) and is shown once as a panel banner (Task 3).
Calendar blockers (earnings/FOMC/CPI) are display/status signals, not score
penalties.

### Grades (UI shows grades only, never decimals)

`GRADE_BANDS`: **A** ≥ 0.66, **B** ≥ 0.40, **C** otherwise. Boundaries are
inclusive on the lower edge (0.66 → A, 0.40 → B). Three independent grades
(short/mid/long) are displayed; internal continuous scores are never shown.

## Setup classifier

`classify_setup(candidate, rs, theme_momentum, days_since_earnings=None)` → one
of six rule-based types, priority order. **Every threshold lives in the
`SETUP_THRESHOLDS` config block** next to the weights (Task 6).

1. **Post-earnings Reprice** — `days_since_earnings` (calendar days since the last
   **actual** reported quarter) within a **bounded window** (`post_earnings_window_days`,
   default 21) **and** EPS revisions improving/inflecting up. It is **never**
   inferred from the LLM catalyst-recency field or from price gaps, and is only
   assigned during top-N enrichment (when actual earnings dates are fetched). A
   stale report (e.g. 35 days) is therefore not mislabelled.
2. **Momentum Breakout** — short dominant, strong RS (1m beating SPY & QQQ),
   above SMA20 & SMA50, volume ratio > `momentum_vol_ratio` (1.20).
3. **Oversold Rebound** — entry quality oversold / negative 1m return.
4. **Mid-term Rotation** — mid dominant + theme momentum ≥ `theme_strong` (0.50)
   + RS ≥ `rs_moderate` (0.50).
5. **Long-term Accumulation** — long dominant + cheap valuation + above SMA50.
6. **Speculative Watch** — fallback (ALT_SIGNAL / Track-B standalone / thin data).

Additionally, the **Pullback-to-Support** pattern is a high-quality **variant
flag** (`pullback_to_support=True`, badge on the card): RS ≥ `pullback_rs_min`
(0.60) **and** a fired signal **and** entry quality good/fair (not extended)
**and** above SMA50 **and** a short-term dip (5d return ≤ 0).

### Scoping note — taxonomy thresholds vs entry logic (Task 6)

The setup taxonomy is the **ranker's own domain**: it produces a descriptive
label, never an entry/stop/zone/threshold judgment (those stay exclusively in
`lib/order_advisor.py`). Therefore its taxonomy cutoffs (RS/vol/return windows,
SMA conditions) legitimately live in the ranker's `SETUP_THRESHOLDS` block. The
ranker does **not** maintain any parallel copy of the entry engine's MID
volume-confirmation state (`order_advisor._mid_volume_state`): the only volume
signal it uses is the RS **volume-surge** ratio for the short Momentum-Breakout
label — a distinct concept (recent surge vs. trailing average) from the engine's
entry volume-confirmation, which the ranker consumes via `entry_status` /
`missing_conditions` at enrichment. This boundary is documented here so future
reviews do not re-litigate it.

## Why-now / why-it-matters reason codes — REVISED (Task 2)

Generated as **structured reason codes** (machine-readable `code` + bilingual
`text_en`/`text_zh`), always **stored raw** on the card (and in the snapshot).
Three rules fix the screenshot homogenization:

- **Commonality filter** (`filter_common_reasons`, `REASON_COMMONALITY_SHARE`
  default 0.50): a code that fires for more than ~50% of today's ranked
  candidates is **demoted** from the card's `*_display` list — *unless* dropping
  it would leave fewer than `MIN_DISTINCTIVE_CODES` (2), in which case the raw
  list is kept. A reason shared by everyone differentiates no one. Raw codes are
  never mutated.
- **Numeric magnitudes embedded** from already-computed RS / theme / valuation
  fields: e.g. `outperforming_qqq` renders "1M vs QQQ +X.X%",
  `theme_momentum_strong` renders "…(NNth pct)" — no new computation.
- **No overclaiming:** the old `catalyst_not_priced_in` ("not fully priced in")
  claimed a judgment the system does not make; it is renamed `recent_catalyst`
  ("Recent catalyst flagged"), stating only what the rule checked. `recent_earnings`
  reports the actual days-since gap; RS codes state the measured excess return.

`why_now` codes: `in_entry_zone`, `near_support_not_overextended`,
`outperforming_qqq`/`outperforming_spy`, `recent_catalyst`, `recent_earnings`.
`why_it_matters` codes: `theme_momentum_strong`, `eps_revisions_improving`,
`valuation_reasonable`, `triple_horizon_signal`.

**Fix round 2 nit:** the status reasons `trigger_pending` /
`stabilization_needed` / `below_value_zone` are **status reasons only**
(`status_reason_by_horizon`) and are **no longer injected into `why_now`** — they
duplicated the card's "⏭️ Waiting for:" (`next_trigger`) line. The ≥2-distinctive
commonality floor still behaves with the smaller vocabulary.

An **optional** LLM polish step (`polish_opportunity_cards`) may convert the raw
codes to natural bilingual sentences for the **top displayed cards only** — a
single API call that must not alter any judgment or number and **degrades
silently to raw-code display** if it fails or no API key is present. It is a
**separate function the UI calls**; `rank_opportunities` itself performs **no LLM
call**.

## Concentration hint — computed at DISPLAY time (Task 4)

The concentration marker is **not** stored on the card in the ranker's canonical
order (that produced the QCOM "#4 → same bet as #5" backwards reference).
`concentration_refs(displayed_cards)` is called in the UI **after** the
per-horizon sort, over the currently displayed list, returning `{ticker: "#K"}`
where #K is the position of the **first** card in that theme **within the shown
order** — so "#K" always points to a card visible above. The snapshot keeps the
`theme` field (grouping info) but stores no display ref.

## Calendar blockers (Task 3)

- `days_to_earnings` / `days_since_earnings` — `default_earnings_timing(ticker)`
  (top-N only; per-ticker fetch from actual yfinance earnings dates).
  `days_since_earnings` drives the bounded Post-earnings setup window.
- `days_to_fomc` — hardcoded `FOMC_DATES` list (FRED has no FOMC schedule).
  Market-wide; computed once.
- `days_to_cpi` — `fetch_economic_releases().cpi_date` projected forward to the
  next monthly release. Market-wide.

**Per-card vs banner.** The **earnings** blocker is ticker-specific: it is a
per-card chip (filtered to the displayed horizon) and gates short-horizon
status. **Market-wide** conditions — `macro_regime_mismatch` and FOMC/CPI
proximity (`market_banner_blockers`) — are shown **once as a panel-level banner**
above the cards (filtered to the displayed horizon), never repeated per card.
`MARKET_WIDE_BLOCKER_CODES` enumerates these so both pages filter them out of
per-card chips. Windows live in `CALENDAR_CONFIG` (earnings 7d, FOMC/CPI 3d).

## Daily snapshot (Task 4)

On every Cockpit refresh, **all** ranked candidates (not just top N) are
persisted under `data/snapshots/opportunities_YYYYMMDD.jsonl`:

- **Same-day semantics:** the day's file is **rewritten** on each refresh, so
  multiple same-day refreshes keep only the latest snapshot (no duplicates). The
  write is **atomic** — temp file + `os.replace` — so a failed/partial write
  never corrupts the prior day's file and degrades silently (Codex #6).
- **Format:** line 1 is a `{"_meta": true, ...}` header (date, `refreshed_at`,
  `macro_regime`, `horizon_bias`, `theme_momentum` map for the day); each
  subsequent line is one ticker record.
- **Per-ticker record schema:**

```json
{
  "date": "2026-06-05",
  "ticker": "NVDA",
  "theme": "ai_chips",
  "theme_momentum": 0.82,
  "short_score": 0.71, "mid_score": 0.65, "long_score": 0.58,
  "short_grade": "A", "mid_grade": "B", "long_grade": "B",
  "rs": { ... }, "rs_degraded": false,
  "setup": "Momentum Breakout",
  "pullback_to_support": false,
  "status_by_horizon": {"short": "Wait for Breakout", "mid": "Actionable Now",
                        "long": "Research Required"},
  "next_trigger_by_horizon": {"short": "Wait for EMA trend + volume", "mid": "",
                              "long": "Wait for valuation anchor"},
  "status": "Actionable Now",
  "blockers": [{"code": "earnings_within_window", "severity": "caution"}],
  "why_now": ["in_entry_zone", "outperforming_qqq"],
  "why_it_matters": ["eps_revisions_improving"],
  "days_to_earnings": 12, "days_since_earnings": 40,
  "days_to_fomc": 8, "days_to_cpi": 3,
  "macro_regime": "risk_on"
}
```

- The **per-horizon `status_by_horizon` map (all three) replaces the single
  `status` field** (Fix round 2); `status` is retained as the dominant-horizon
  convenience for backward-compatible readers. Statuses are `null` outside the
  top N. Reason codes are stored **raw** (display filtering is view-only). The
  **concentration ref is NOT stored** (view-local); the `theme` field carries the
  grouping info. `load_ticker_series(ticker)` reconstructs the per-ticker series
  (it returns whole records, so the per-horizon map is preserved); the per-day
  `theme_momentum` meta map is the Phase 7D review benchmark.

## Performance / contract (Task 5, Codex #3/#5/#6)

Ranking up to 150 candidates must not run the entry engine or a per-ticker
network fetch for every candidate:

- **Deterministic ordering (Codex #3):** cards are sorted by score **descending,
  then ticker ascending**, so identical inputs always produce identical order
  (snapshot diffs / stored ordering are stable).
- **Network-free ranking (Codex #5):** `rank_opportunities` reads RS from
  `rs_map` and performs **zero per-ticker fetches** during scoring; a ticker
  missing from `rs_map` (or built from a fixture/empty frame) degrades to a
  neutral RS component (`_RS_NEUTRAL`) and the card/snapshot carries
  `rs_degraded=True`. **The Cockpit now actually uses the cache-only path (Fix
  round 2):** `build_rs_map_cache_only(tickers)` reads per-ticker OHLCV
  **cache-only** from `lib.cache_manager.load(tk, "ohlcv")` (the frames the signal
  pipeline already persisted) — a miss degrades, it never fetches — while the
  SPY/QQQ benchmark series is the single per-refresh fetch. An integration test
  drives this path with a counting benchmark loader + a cache-only frame stub and
  deliberate misses, asserting the candidate tickers are never fetched.
- **Phase 1 (all candidates):** three horizon scores + grades + setup + RS +
  ticker-specific blockers + reason codes. No `compute_price_levels`, no earnings
  fetch.
- **Phase 2 (top N, default 20):** `price_levels_fn` **once per horizon** (≤ 3 ×
  top_n) + `default_earnings_timing` once per ticker → per-horizon status /
  next_trigger / entry zone, earnings blocker, setup refinement.

The test suite passes a counting `price_levels_fn` and asserts it is called **at
most 3 × top_n times** (and zero on the full scoring loop), that the cache-only
Cockpit RS path performs **zero per-ticker fetches**, and that **no LLM** is
invoked on the ranking path.

## Out of scope for 7A

Leader/laggard labels, group confirmation, theme rotation stages, beneficiary
tiers, thesis ingestion, LLM macro event layer, liquidity plumbing fetchers
(SOFR/ON RRP/TGA), full universe expansion, alternative data, any change to
valuation logic.

## Guardrails

Free sources only (yfinance / FRED / Finnhub free tier via existing fetchers);
no paid API; no broker / order / execution; no order ticket / broker payload;
`approved_for_execution` always False/absent; no DB / vector store (local
`data/snapshots/` JSONL only). `lib/macro_regime.py`, `lib/workflow_state.py`,
`lib/technical.py`, `lib/macro_data.py`, `lib/signal_engine.py`,
`lib/candidate_generator.py`, `lib/theme_baskets.py`, `lib/order_advisor.py`,
`lib/data_fetcher.py`, `.claude/agents/*`, and pages 1–6/8 are **not modified**
(only called). The optional polish step touches language only.

## Tests

`scripts/test_reliability_phase_7a_opportunity_ranking.py` (mock-only, offline,
**115/115**): revised five-state mapping incl. horizon-aware `below_zone`, the
engine-`missing_conditions` fundamental gate (Fix 3), the pinned Row-4 precedence,
**per-horizon status** (different status per horizon; dominant convenience), and
both invariants (pullback never co-occurs with Avoid Chasing; `below_zone` never
→ Wait for Breakout); per-card vs market-wide banner blocker assembly; setup
classification incl. the bounded post-earnings window; three weight tables →
different orderings + deterministic tie-break; grade boundaries; snapshot write +
same-day dedup + reconstruction + atomic-write failure + the per-horizon status
map; RS from fixtures + cache-only mode + the **Cockpit cache-only integration**
(zero per-ticker fetches); reason-code commonality filter / numeric embedding /
no-overclaim / `trigger_pending`-not-in-why_now (Fix 4); display-time
concentration refs; AST-parsed page-import + render smoke (Fix 5); no-LLM
structural assertion. Regression (all pass):
`test_reliability_phase_6c_b_cockpit_rebuild.py` 47/47,
`test_reliability_equity_render_order.py` 50/50,
`test_reliability_phase_6c_trading_desk.py` 118/118,
`test_reliability_phase_6c_v3_entry_v4.py` 47/47,
`test_reliability_phase_6b_v3_horizon_scoring.py` 189/189.
