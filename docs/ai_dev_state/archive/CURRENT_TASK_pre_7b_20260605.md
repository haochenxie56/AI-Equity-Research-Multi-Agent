# Current Task

## Valuation Stop-the-Bleed (CURRENT TASK — Implemented)

Three deterministic (no-LLM) valuation-layer fixes. Phase doc:
`docs/reliability_valuation_stopbleed.md`. New suite
`scripts/test_reliability_valuation_stopbleed.py` **54/54**; the five regressions
+ 7A all green (7A 115/115, 6c_b 47/47, equity_render_order 50/50,
6c_trading_desk 118/118, 6c_v3_entry_v4 47/47, 6b_v3_horizon_scoring 189/189).

- **Task 1 — Anchor consistency gate.** Dispersion gate (`max/min`,
  `ANCHOR_DISPERSION_THRESHOLD = 3.0` in both `lib/equity_valuation.py` and
  `lib/valuation_anchor.py`; boundary `>`). Irreconcilable anchors are NOT
  blended: `AppFairValue.blend_state="anchors_irreconcilable"` (band collapses to
  0), `FairValueAnchor.anchor_state` set, confidence forced low,
  `conservative_anchor` None. `order_advisor` LONG **initiate** degrades
  explicitly to *"valuation unreliable — technical reference only"* (SHORT/MID
  untouched). `pages/4` renders anchors side-by-side, no range bar.
- **Task 2 — Forward-estimates basis.** Relative anchor prefers `forwardEps`
  (`relative_basis="forward"`); trailing fallback flagged `trailing_fallback`;
  forward-EPS × trailing sector P/E flagged `peer_pe_basis="mixed"`. Basis badge
  in the valuation UI.
- **Task 3 — Anchor cache.** `lib/anchor_cache.py` (`data/anchor_cache.json`,
  atomic write, `DEFAULT_STALENESS_DAYS=7`). Write-through from
  `store_equity_research_result`. `rank_opportunities(anchor_cache=...)` reads it
  read-only and feeds a FRESH high/medium band to the LONG `compute_price_levels`
  so LONG differentiates (in/above/below) instead of Research Required;
  `OpportunityCard.anchor_age_days` + snapshot field record staleness. On the
  fixture set a fresh anchor flips LONG `Research Required → Actionable Now`
  (age 2.0); stale/missing keep prior behavior.

---

## Phase 7A final fix (Implemented; Awaiting Codex Review)

Codex's last should-fix: the Fix-3 engine classifier matched substrings over free
bilingual text and the pinning test used hand-written approximations, so an
`order_advisor` wording change could silently misroute fundamental blocks.

Fixed at the source — a **string/constants-only** refactor of
`lib/order_advisor.py` (zero numeric/threshold/gate/control-flow change):
- `MissingCondition` dataclass + `MISSING_CONDITION_REGISTRY` (7 entries: stable
  `code` + `category` ∈ {fundamental, trigger} + `text_en`/`text_zh`;
  `.text` == `f"{en} / {zh}"` reproduces the exact prior string). 5 trigger
  (SHORT confirmation) + 2 fundamental (EPS / valuation gates) strings lifted.
- `_short_confirmation` appends `MISSING_CONDITION_REGISTRY[code].text`;
  `_GATE_REASON_EPS`/`_GATE_REASON_VAL` are sourced from the registry.
- `missing_condition_category()` + `MISSING_CONDITION_TEXT_TO_CATEGORY` reverse
  index exported for the ranker.
- **Consumers needing adjustment: none.** `missing_conditions` stays a list of
  byte-identical strings, so the LLM order-narrative `"; ".join`/`split`, Trading
  Desk cards, thesis monitor, and existing fixtures all keep working.

`lib.opportunity_ranker.engine_block_is_fundamental` now classifies by the
registry category first (lazy-imported + cached); substring markers are a
**fallback only** for legacy/unregistered conditions; fundamental wins on
collision.

Tests added: registry-driven pinning (iterate every entry → assert its category
through the full `derive_status` path); AST completeness guard (any
`*missing*.append("<literal>")` in `order_advisor` fails the suite); legacy
text-only fallback + collision fixtures. Suite **115/115**; all five regression
suites green (incl. the trading-desk/entry suites that consume
`missing_conditions` display text — the canary for consumer breakage).

---

## Phase 7A fix round 2 (prior — Implemented)

Codex re-review returned REQUEST CHANGES: 3 should-fix + 2 nits. All addressed;
7A suite **115/115**; regressions green (6c_b 47/47, equity_render_order 50/50,
6c_trading_desk 118/118, 6c_v3_entry_v4 47/47, 6b_v3_horizon_scoring 189/189).

- **Fix 1 — per-horizon status (root cause of the MU mid-view anomaly).** During
  top-N enrichment, `compute_price_levels` + `derive_status` run for **all three
  horizons** (≤ 3 × top_n deterministic local calls; still zero per-ticker
  network fetch). The card carries `status_by_horizon` / `next_trigger_by_horizon`
  / `status_reason_by_horizon` maps; `status` / `next_trigger` stay as
  dominant-horizon convenience. The Cockpit renders the **selected** horizon's
  status + trigger; the TD hand-off carries the maps. Snapshot stores
  `status_by_horizon` (null outside top N). Structural test: engine ≤ 3 × top_n,
  zero on the scoring loop.
- **Fix 2 — Cockpit actually uses the cache-only RS path.** pages/7 now calls
  `build_rs_map_cache_only(_tickers)`, which fetches SPY/QQQ once and reads
  per-ticker OHLCV cache-only from `lib.cache_manager.load(tk, "ohlcv")` (miss →
  neutral + `rs_degraded`, never a fetch). Integration test drives this path with
  a counting benchmark loader + a cache-only frame stub and deliberate misses,
  asserting zero candidate fetches.
- **Fix 3 — fundamental gate reads engine `missing_conditions`.** New
  `engine_block_is_fundamental` + marker config classify the engine's own block
  reasons: valuation/EPS/quality → Avoid Chasing; trend/volume/price → Wait for
  Breakout. Works even with no ranker blockers (legacy hand-off). Fixture pins it.
- **Fix 4 (nit)** — `trigger_pending` removed from the why_now vocabulary (status
  reason only; it duplicated the "⏭️ Waiting for:" line). ≥2-distinctive floor
  re-checked.
- **Fix 5 (nit)** — doc/count drift fixed (now 115/115 everywhere); phase-doc
  mapping table reflects per-horizon status + the Fix-3 gate; smoke 9.0 now
  AST-parses `from lib.opportunity_ranker import …` from both page files instead
  of a hand-maintained list.
- **Row-4 ordering pinned** — price overextension (Avoid/Pullback) intentionally
  precedes provenance Research-Required (ALT_SIGNAL); documented + test fixture.

---

## Phase 7A fix round 1 (prior — Implemented)

Codex returned 6 should-fix items and real-data screenshots surfaced 3
user-visible product issues. All fixed in one pass; 7A test suite then 90/90;
regressions green (6c_b 47/47, equity_render_order 50/50, 6c_trading_desk
118/118, 6c_v3_entry_v4 47/47, 6b_v3_horizon_scoring 189/189).

**Codex items confirmed (by number):**
1. **below_zone → Wait for Breakout was wrong** → now horizon-aware **Research
   Required** (SHORT/MID stabilization, LONG below-value); invariant tested.
2. **Setup classifier scoping** → thresholds moved to `SETUP_THRESHOLDS` config;
   Post-earnings now gated on **actual days-since-report ≤ 21d** (no inference);
   scoping rationale documented (taxonomy is the ranker's domain; no parallel MID
   volume-state).
3. **Deterministic ordering** → sort key `(-score, ticker)`; tie-break tested.
4. **(product) Concentration marker** → computed at display time over the
   per-horizon-sorted list (`concentration_refs`); "#K" always points above.
5. **Network-free ranking** → `rank_opportunities` does zero per-ticker fetches;
   missing/cache-miss RS → neutral + `rs_degraded`; `compute_rs_for_tickers(cache_only)`
   reads only supplied frames; benchmarks the single fetch.
6. **Snapshot atomicity** → temp-file + `os.replace`; failure degrades silently
   (tested: prior file intact, no `.tmp` leftover).

**Product issues from screenshots:**
- (a) pullback_to_support + "Avoid Chasing" contradiction → **Avoid Chasing
  reserved** for risk-overlay failure / genuine overextension; pending trigger →
  Wait for Breakout (surfaces engine `next_trigger`); pullback flag dropped if
  status is Avoid (invariant tested).
- (b) homogenized why_now lines → commonality filter + embedded RS magnitudes +
  de-overclaimed text (`catalyst_not_priced_in` → `recent_catalyst`).
- (c) macro blocker repeated on every card (incl. mid/long) → per-card chips are
  ticker-specific + horizon-filtered; market-wide macro/FOMC/CPI shown once as a
  panel banner (`market_banner_blockers` + `MARKET_WIDE_BLOCKER_CODES`).

Reframes Phase 7: the entry/risk backend (Entry Strategy v4, Thesis Monitor,
Trading Desk) is mature, but the idea-generation front end was weak. Phase 7A
turns existing signal candidates into a ranked, actionable **opportunity list**
that answers: which tickers deserve attention today, why, can I buy now, if not
what am I waiting for, and what's the risk. MVP / orchestration only — **no new
entry-zone / stop / technical thresholds, no invented numbers, no new schemas,
no shadow modes, no DB.**

### What was built

- **`lib/opportunity_ranker.py`** — orchestration layer. `rank_opportunities()`
  scores ALL candidates network-free (Phase 1), then enriches only the top N
  (default 20) with the entry engine + earnings (Phase 2). Provides the
  five-state `derive_status`, `classify_setup` (+ Pullback-to-Support variant),
  rule + calendar blockers, raw why-now/why-it-matters reason codes, concentration
  hint, daily snapshot (`write_daily_snapshot` / `load_ticker_series`), and an
  OPTIONAL `polish_opportunity_cards` LLM step that is NOT on the ranking path.
- **`lib/relative_strength.py`** — simplified RS (5d/1m vs SPY & QQQ, above/below
  SMA20/50, volume ratio, `rs_composite`). New module so frozen
  `lib/technical.py` stays untouched; benchmarks fetched once, per-ticker history
  reuses the `ui_utils.load_ohlcv` cache.
- **`pages/7_Investment_Cockpit.py`** — Section C upgraded to the Opportunity Card
  panel (grade badge, five-state status badge, setup label, why-now lines,
  blocker chips, days_to_earnings, concentration marker, pullback flag) + a
  horizon selector that re-sorts the queue. Refresh now ranks candidates and
  persists the daily snapshot. All existing buttons/flows preserved
  (Add to Trading Desk, ticker selection, Run Equity Research, nav prefill).
- **`pages/9_Trading_Desk.py`** — Section 3 adopts the unified five-state naming
  via `derive_status`; carries setup/status/blockers/grades from
  `td_pending_signals`.
- **`ui_utils.py`** — additive bilingual `opp_*` keys (five states, panel chrome,
  setup labels).

### Status mapping (engine → five states), priority order

1. ALT_SIGNAL (Track-B only) OR (long horizon + valuation_confidence low) OR
   entry_status `wait` → **Research Required**.
2. risk overlay failed OR critical/hard-gate blocker OR blocked-with-missing →
   **Avoid Chasing**.
3. blocked, no hard gate → **Research Required**.
4. above_zone → **Wait for Pullback**; 5. below_zone → **Wait for Breakout**.
6. in_zone + calendar blocker on the displayed horizon → **Research Required**;
   7. in_zone otherwise → **Actionable Now**.

### Weight tables (RS = 0.20 each; columns sum to 1.00)

| comp | short | mid | long |
|---|---|---|---|
| signal | 0.30 | 0.30 | 0.25 |
| rs | 0.20 | 0.20 | 0.20 |
| catalyst | 0.20 | 0.10 | 0.05 |
| theme | 0.15 | 0.20 | 0.15 |
| entry | 0.10 | 0.05 | 0.10 |
| valuation | 0.05 | 0.15 | 0.25 |

Grades: A ≥ 0.66, B ≥ 0.40, else C. Penalties: valuation_high 0.10,
theme_lagging 0.05, macro_regime_mismatch 0.08.

### Snapshot record

`data/snapshots/opportunities_YYYYMMDD.jsonl`: meta header line (date,
refreshed_at, macro_regime, horizon_bias, per-theme momentum map) + one line per
ticker (scores, grades, rs dict, setup, pullback flag, status [null outside top
N], blockers, days_to_earnings/fomc/cpi, concentration_ref, signal_strength).
Same-day refresh overwrites; `load_ticker_series` reconstructs per-ticker series.

### Judgment calls

- The v3 outline PDF was not present in `docs/`, so the prompt was treated as
  self-contained; weight values are the documented calibration baseline (RS fixed
  at 0.20 per the brief).
- RS lives in a **new** `lib/relative_strength.py` rather than editing the frozen
  `lib/technical.py` (the prompt allowed either; this keeps the frozen file
  untouched).
- Calendar blockers gate the SHORT horizon and downgrade in-zone Actionable → 
  Research Required for that horizon; FOMC/CPI are market-wide status gates
  (not score penalties, which would shift all candidates uniformly). Earnings
  is per-ticker, so it is fetched only during top-N enrichment.
- `concentration_ref` references the ranker's canonical best-of-three order; the
  per-horizon UI re-sort may differ slightly — accepted for the MVP.
- FOMC dates are a hardcoded `FOMC_DATES` list (FRED provides no FOMC schedule).

### Validation

`test_reliability_phase_7a_opportunity_ranking.py` **115/115**; regression
`test_reliability_phase_6c_b_cockpit_rebuild.py` 47/47,
`test_reliability_equity_render_order.py` 50/50,
`test_reliability_phase_6c_trading_desk.py` 118/118,
`test_reliability_phase_6c_v3_entry_v4.py` 47/47,
`test_reliability_phase_6b_v3_horizon_scoring.py` 189/189. The one failing check
in `test_reliability_phase_6b_signal_layer.py` (7.1) is pre-existing and
unrelated (untouched `lib/signal_engine.py` lazy-imports `llm_orchestrator`).

---

## Phase 6C-B fix v3 — Equity page: extend layout-first to two more sections (prior task)

Codex **APPROVED** the v2 layout-first refactor (layout block 82–119, first
blocking call 126) and asked for two follow-ups.

**Task 1 — extend the pre-created-slot pattern to two more Overview sub-sections.**
The **Company Business Description** and **Research Report** expanders still
rendered sequentially inside `tab_overview`, so their frames did not appear until
the peer fetches (and, for the description, the `translate_to_chinese` call)
completed. Both now follow the same slot pattern as header/earnings/metrics/fv:

- Inside the layout block, `with tab_overview:` now reserves three sub-section
  frames in their on-page vertical order: `ov_top_slot = st.container()` (moat
  radar + peer comparison), `biz_slot = st.empty()` (Business Description), and
  `report_slot = st.empty()` (Research Report) — each painted with a lightweight
  `⏳ {p4_loading}` placeholder (bilingual via `t()`), matching the fv_slot style.
- In the FILL PASS the moat+peers render into `with ov_top_slot:`, the
  description into `with biz_slot.container():`, and the report into
  `with report_slot.container():` — no body re-indentation (the dedicated `with`
  blocks sit at the same indent the shared `with tab_overview:` used).
- **Business Description**: filled automatically; on a `translate_to_chinese`
  failure it falls back to the source English text, and empty data shows `N/A` —
  the slot is never left on the placeholder.
- **Research Report**: confirmed to make **no LLM call** — it is assembled
  deterministically from already-fetched `info`/`scores`/`peer_data` via
  f-strings. Auto-run behavior is therefore **unchanged**; the frame shows a
  placeholder until the (fast, deterministic) fill replaces it. The only I/O —
  writing the `.md` to `research/stock/` — is now wrapped in `try/except` so a
  read-only/failed write still leaves a fully-rendered report on screen.

**New layout block: lines 82–140** (was 82–119). First blocking call
(`load_info`) is at **line 147**; reading top-to-bottom, no blocking call appears
before line 140. On cold-cache entry, ALL frames — header, earnings, metrics, the
four tabs, **business description, research report**, and AI Valuation Summary —
are on screen essentially immediately. Widget keys (`moat_*`, `peer_input`),
bilingual modes, all buttons, and `equity_prefill_ticker` preserved.

**Task 2 — strengthen `scripts/test_reliability_equity_render_order.py`.**

- The two new sections are registered: `biz_slot` / `report_slot` join the slot
  set automatically (both are `st.empty()`, counted by the patched `st.empty`);
  the Business Description's `translate_to_chinese` is added to the blocking set
  and is actually exercised (the harness runs with `language="zh"` and a stubbed
  `longBusinessSummary`). The Research Report makes no fetch/LLM call, so only its
  slot is tracked (its frame-before-first-blocking ordering is still asserted).
- **Overclaim fixed (chose option (a) — honest scoping, plus a single-location
  registry).** The docstring no longer claims "any new kind of blocking call is
  caught automatically." It now states coverage is limited to the helpers in the
  one `_BLOCKING_PATCHES` registry, and that a new page fetch/LLM helper must be
  added there. Option (b) (a registry shared/imported between page and test) was
  judged over-engineering for one page; the single in-test registry gives the
  same single-place-to-edit benefit without cross-module coupling.
- Structural assertion `max(slot_seq) < min(blocking_seq)` re-run for **warm and
  cold** cache, now over the expanded sets (incl. `translate_to_chinese` and the
  two new slots; asserts ≥ 6 `st.empty` slots). **Negative control** for the
  Business Description (`translate_to_chinese` temporarily moved above the layout
  block) was verified to fail (`first_block_seq=1 < last_slot_seq=8`) and reverted.

**Tests:** `scripts/test_reliability_equity_render_order.py` — **50/50** (was
37/37); `scripts/test_reliability_phase_6c_b_cockpit_rebuild.py` regression —
**47/47**.

**Manual verification checklist (v3):**

1. Open Equity Research with a ticker (cold cache). The header, metrics, the four
   tab frames, **the Company Business Description expander, the Research Report
   subheader**, and the AI Valuation Summary expander all appear within ~1–2s,
   each showing a placeholder while data loads.
2. Each placeholder is replaced in place by its content — no second frame, no
   layout jump; section vertical order is unchanged.
3. Switch EN↔ZH: the Business Description re-translates; Research Report relabels;
   nothing reorders.
4. **Run AI Debate / Update Valuation / Send to Trading Desk** still work; the
   report **Download** button and on-disk `.md` still produced.

```bash
python3 -B scripts/test_reliability_equity_render_order.py          # 50/50
python3 -B scripts/test_reliability_phase_6c_b_cockpit_rebuild.py   # 47/47 regression
```

---

## Phase 6C-B fix — Equity page AI Valuation Summary render-order

**Bug:** On `pages/4_Equity.py`, the "AI Valuation Summary" expander (default
expanded) only appeared *after* the rest of the page (Financials / Price-Volume /
News, and the Research Report) finished, instead of immediately on page load.
Multiple prior `st.empty()` placeholder attempts failed.

**Diagnosis (empirical, AppTest + per-section timing logging).** Streamlit
streams element deltas in *script-execution order*, so a section appears in the
browser only once the line that **creates** it runs. The valuation section was
the **last top-level block** in the script. Before it ran, on a fresh AAPL load:

| t (s) | section |
|------:|---------|
| +0.8  | shared `load_info` / `load_earnings` |
| +1.1→+2.0 | Overview peer `load_info ×8` |
| +2.0→+3.3 | `render_financial_tab` (yfinance financials/BS/CF) |
| +3.3→+3.6 | `render_pv_tab` (OHLCV + indicators) |
| +3.6→+3.8 | `load_news` (243 articles returned) |
| +3.8→**+12–18** | **News article loop** — `translate_to_chinese` per headline (~0.4s × up to 20 ≈ 8–14s) |
| **+12–18** | valuation section finally reached; `st.empty()` placeholder created **here** |

**Why the prior `st.empty()` fixes could not work:** the placeholder *and* its
spinner were created at line ~581, at the bottom of the script. An `st.empty()`
slot only renders when the line that creates it executes — and that line was
downstream of every blocking tab body (especially the ~8–14s News translation
loop). Changing what was shown *inside* the placeholder never changed *when* the
creating line was reached.

**Fix (Option A — layout-first, NOT Option B).** Option B (`st.fragment`) was
rejected because fragments still execute inline on the **initial** full run; they
only isolate *reruns*, so they would not move the valuation frame earlier on
first load — the exact symptom. Option A creates the section containers before the
blocking work (see the **v2** note below for the completed, full-page version).

### v2 — completing the layout-first pass (Codex REQUEST CHANGES round)

Codex's first review returned **REQUEST CHANGES**: the v1 fix only moved the
*valuation* slot above the tab bodies, but `load_info(ticker)` / `load_earnings(
ticker)` (and the header / earnings / metrics that consume them) still ran
**before** `fv_slot = st.empty()`. On a cold cache (the acceptance scenario)
those two fetches block, so the valuation frame was still not guaranteed to
appear immediately. The render-order test also only covered the tab-body calls,
not those two earlier fetches.

**v2 restructure (`pages/4_Equity.py`):**

- **One contiguous LAYOUT-FIRST PASS (lines 82–120)** creates *every* top-level
  section frame before any blocking call: `header_slot` / `earnings_slot` /
  `metrics_slot` (each `st.empty()`), the four `st.tabs(...)` frames, and the
  valuation `fv_slot = st.empty()` with its `📊 AI Valuation summarizing...`
  placeholder. The header slot shows a lightweight `### \`TICKER\` …` placeholder
  (the ticker is known with no fetch). The **only** things above the block are
  imports, the `equity_prefill_ticker` session read, the ticker-input widget, and
  the empty-ticker guard — **no blocking call precedes line 120.**
- **FILL PASS (line 122 onward)** runs `load_info` / `load_earnings` (first
  blocking call at **line 127**), fills `header_slot` / `earnings_slot` /
  `metrics_slot` via `slot.container()`, fills the four tab bodies, then computes
  the fair value and fills `fv_slot.container().expander(...)`.
- The header / earnings / metrics adopt the same pre-created-slot pattern as the
  valuation section (preferred option from the review). Ticker validity is **not**
  a blocking gate before the layout pass — the empty-ticker case is handled by the
  pre-existing guard above the block (renders placeholder expanders + `st.stop()`,
  no fetch).

Rendering-order refactor only — no computation / LLM-prompt / session-state-key
changes; all three action buttons, `equity_prefill_ticker` hand-off, bilingual
header, and LIVE/FIXTURE behavior preserved.

**Strengthened test (`scripts/test_reliability_equity_render_order.py`).** It now
runs the page under AppTest with a **call log** that records BOTH slot creations
(`st.empty` / `st.tabs`) and **every** blocking call (`load_info`,
`load_earnings`, `load_news`, `render_financial_tab`, `render_pv_tab`,
`compute_app_fair_value`), then asserts **structurally** that
`max(slot_seq) < min(blocking_seq)` — i.e. the last frame is created before the
first fetch. Because it is last-slot-vs-first-blocking (not enumerated pairs),
any future fetch moved above the layout block is caught automatically, including
new kinds of blocking call. A **cold-cache** scenario (`st.cache_data.clear()`
before the run) confirms the order is unchanged with every real cache empty.
A negative-control run (a `load_info` deliberately placed above the layout block)
was verified to fail the structural assertion (`first_block_seq=1 <
last_slot_seq=6`).

**Tests:** `scripts/test_reliability_equity_render_order.py` — **37/37**
(was 29/29); `scripts/test_reliability_phase_6c_b_cockpit_rebuild.py` regression —
**47/47**.

**Manual verification checklist** (render *timing* is not fully observable via
AppTest — confirm visually):

1. Open Equity Research with a ticker (e.g. NVDA). The company header, key-metrics
   row, the four tab frames, and the "AI Valuation Summary" expander **frame +
   `summarizing...` placeholder** all appear within ~1–2s, while the data is still
   loading.
2. The header / metrics / valuation placeholders are replaced in place by their
   computed content — no second frame, no layout jump.
3. **Run AI Debate**, **Update Valuation** (enabled after a Financials-tab DCF
   edit), and **Send to Trading Desk** all still work.
4. Switching EN/ZH still re-labels the section; LIVE/FIXTURE badge unchanged.
5. Investment Cockpit "View Full Research" hand-off still lands here pre-filled
   (`equity_prefill_ticker`).

```bash
python3 -B scripts/test_reliability_equity_render_order.py          # 37/37
python3 -B scripts/test_reliability_phase_6c_b_cockpit_rebuild.py   # 47/47 regression
```

---

## Phase 6C-B — Investment Cockpit Rebuild — Implemented; Awaiting Codex Review

**The current task is Phase 6C-B — Investment Cockpit Rebuild.** It rebuilds
`pages/7_Investment_Cockpit.py` from the Phase 5N fixture/demo surface into the
app's **primary entry point and live data aggregation hub**, adds a standalone
app-computed fair-value layer (`lib/equity_valuation.py`), surfaces it on the
Equity Research page, and wires it into the Trading Desk so order recommendations
use app-computed fair values rather than yfinance analyst targets alone. **Phase
6C-B is not accepted in this pass. Phase 6D has not started.**

Single acceptance criterion: *"The user opens Investment Cockpit, clicks Refresh,
selects tickers, and Trading Desk order recommendations use fair values computed
by the app rather than yfinance analyst targets alone."*

**Implementation status:**

- **Sidebar restructure** (`ui_utils.render_sidebar`): Home · Investment Cockpit ·
  Macro Dashboard · Sector Research · Stock Scanner · Equity Research · Trading
  Desk. Overview (`pages/1_Overview.py`) removed from the sidebar (page retained;
  `nav_p1` kept, deprecated).
- **`lib/equity_valuation.py`** (new) — `AppFairValue` + `compute_app_fair_value`
  (DCF per-share Gordon growth [WACC=10%, growth cap=15%] + relative
  [`SECTOR_MEDIAN_PE × trailing_eps`] + analyst target → low ≤ mid ≤ high band,
  high/medium/low confidence; cached TTL=3600; fail-closed) +
  `build_app_fair_value` (pure) + `store_equity_research_result`.
- **`lib/llm_orchestrator.analyze_equity_fair_value_debate`** — one cached LLM
  call (TTL=7200; bilingual bull/bear/risk/synthesis + endorsed range + action;
  fail-closed to the app low/high band).
- **`lib/order_advisor.py`** — `PriceLevelResult.fair_value_source`; Step 0 reads
  `equity_research_results` (app_computed > analyst_proxy > fixture).
- **`pages/4_Equity.py`** — AI Valuation Summary section appended (no existing
  content modified).
- **`pages/7_Investment_Cockpit.py`** — full rebuild (header + Refresh All +
  Sections A–E + one-click refresh; Trading Desk thesis monitor not run here).
- **`pages/9_Trading_Desk.py`** — fair_value_source badge.
- **`scripts/test_reliability_phase_6c_b_cockpit_rebuild.py`** (new) — 47/47.

**Validation:** `phase_6c_b_cockpit_rebuild` 47/47; `phase_6c_v3_entry_v4` 47/47;
`phase_6c_trading_desk` 118/118; `phase_6b_v3_horizon_scoring` 189/189;
`phase_6a_live_data` 336/336.

**Recommended next step:** Codex review of Phase 6C-B. **Recommended next phase
after acceptance:** **Phase 6D — Monitoring & Review** (not started).

---

## Phase 6C-A v3 — Entry Strategy v4 — Implemented; Awaiting Codex Review

**The current task is Phase 6C-A v3 — Entry Strategy v4.** It refactors
`lib/order_advisor.py` + `lib/valuation_anchor.py` so that **building and adding
positions share the same market-based Horizon Entry Zone Engine**; `cost_basis`
enters ONLY in the new **Existing Position Risk Overlay** for add scenarios. LONG
uses a **three-tier valuation confidence** system, and portfolio settings are
**persisted in `data/holdings.json`**. **Phase 6C-A v3 is not accepted in this
pass. Phase 6C-B has not started.** Recommended next phase after acceptance:
**Phase 6C-B — Cockpit Rebuild.**

**Implementation status:**

- **`lib/holdings.py`** — new `PortfolioSettings` dataclass (`max_position_pct=0.15`,
  `short_max_loss_pct=0.02`, `mid_max_loss_pct=0.05`, `long_stop="thesis_break"`) +
  `load_portfolio_settings()` / `save_portfolio_settings()` (top-level
  `"portfolio_settings"` key) + `load_cash_position()` / `save_cash_position()`
  (already present). The low-level writer now PRESERVES the other top-level blocks
  (holdings list, cash, settings) on any single-field write. All fail-closed.
- **`lib/valuation_anchor.py`** — `FairValueAnchor` gained `analyst_anchor`
  (`targetMedianPrice` priority, else `targetMeanPrice`, else None), `relative_anchor`
  (median trailing P/E × `trailingEps`), `dispersion`
  (`(targetHigh−targetLow)/analyst_anchor`), `anchor_spread`
  (`|analyst−relative|/min(…)`), `analyst_count` (`numberOfAnalystOpinions`),
  `confidence` (high/medium/low), `conservative_anchor`, and a tier-dependent
  `fair_value_anchor` (high `×0.90`, medium `×0.85`, low soft percentile fallback).
  Cached TTL=3600.
- **`lib/order_advisor.py`** — `PriceLevelResult` gained `valuation_confidence`,
  `conservative_anchor`, `risk_overlay_passed`, `risk_overlay_note`,
  `portfolio_weight_current`, `portfolio_weight_after_add`, `blended_cost_after_add`
  (all existing fields preserved). LONG `_compute_initiate_logic` now uses the
  three confidence tiers (high → `conservative_anchor × (0.90+vol_bonus)`; medium →
  `analyst_anchor × (0.85+vol_bonus×0.5)`; low → no zone) + a non-blocking
  `valuation_percentile ≥ 0.85` soft warning. LONG `_compute_add_logic` adds an
  `add_tiny` branch for `0.50 ≤ pct < 0.70`. New `_gather_portfolio` (total assets
  via a cost-free price proxy) + `_apply_add_overlay` (position-limit + SHORT/MID
  risk-to-stop budget + share-count sizing + blended cost; LONG checks the position
  limit + thesis intactness only). SHORT add still never averages down a loser
  (`wait_or_cut`). `generate_order_narrative` threads the new fields into the prompt
  and enforces "failed overlay ⇒ hold/wait" in code. `approved_for_execution` is
  ALWAYS False.
- **`pages/9_Trading_Desk.py`** — a collapsed "⚙️ 组合设置 / Portfolio Settings"
  expander at the top of Section 1 (max-position / short-loss / mid-loss sliders +
  a non-editable long-stop label + a Save button → `save_portfolio_settings`); order
  cards now show a LONG `valuation_confidence` badge (high=green/medium=yellow/
  low=gray), the `risk_overlay_note` when the overlay fails, and the projected
  `portfolio_weight_after_add` / `blended_cost_after_add`. The page never writes
  `data/holdings.json` directly.
- **`scripts/test_reliability_phase_6c_v3_entry_v4.py`** (new) — mock-only; **47/47**.
- **`ui_utils.py`** — additive EN/ZH `td_portfolio_settings` / `td_max_position_pct`
  / `td_short_max_loss` / `td_mid_max_loss` / `td_long_stop_label` /
  `td_long_stop_value` / `td_save_settings` / `td_settings_saved` /
  `td_valuation_confidence` / `td_conf_*` / `td_risk_overlay_note` /
  `td_weight_after_add` / `td_blended_cost` / `td_act_add_tiny` `t()` keys only.

**Guardrails honored:** free sources only (yfinance); no paid API; no broker /
order / execution; `approved_for_execution` always False; no DB / vector store.
`lib/macro_regime.py`, `lib/macro_data.py`, `lib/workflow_state.py`,
`lib/signal_engine.py`, `lib/thesis_monitor.py`, `lib/candidate_generator.py`,
`.claude/agents/*`, pages 1–8 not modified.

**Validation (run via WSL `wsl.exe -d ubuntu -- bash -lc 'python3 -B ...'`):**

```bash
git status --short
python3 -B scripts/test_reliability_phase_6c_v3_entry_v4.py          # 47/47
python3 -B scripts/test_reliability_phase_6c_v2_entry_strategy.py    # 99/99 regression
python3 -B scripts/test_reliability_phase_6c_trading_desk.py         # 118/118 regression
python3 -B scripts/test_reliability_phase_6b_v3_horizon_scoring.py   # 189/189 regression
python3 -B scripts/test_reliability_phase_6a_live_data.py            # 336/336 regression
```

**Next step:** Codex review of Phase 6C-A v3 Entry Strategy v4. **Recommended next
phase after acceptance:** **Phase 6C-B — Cockpit Rebuild** (not started).

---

## Phase 6C-A v2 — Entry Strategy v3 Refactor — Superseded by v3 (Entry Strategy v4)

**The current task is Phase 6C-A v2 — Entry Strategy v3.** It is a full refactor of
`lib/order_advisor.py`'s entry-zone, add, and stop-loss logic, replacing the single
build-vs-add-agnostic path with a **horizon-native, scenario-aware** system
(initiate vs add vs manage). **Phase 6C-A v2 is not accepted in this pass. Phase
6C-B has not started.**

Purpose: SHORT uses **EMA10 + EMA20** (fast trend + hard volume gate), MID uses
**SMA50** (healthy/neutral/unhealthy volume state), LONG uses **SMA200 +
fair_value_anchor** (valuation margin of safety). SHORT never averages down a
losing position (`wait_or_cut`); MID can `average_down_small` only when the thesis
is intact and EPS is not deteriorating; LONG can `average_down` when the thesis is
intact; the LONG stop is thesis/valuation-driven, not short-term technical. The
result exposes `action`, `entry_zone`, `stop_loss_level`, `position_sizing`,
`reason`, `missing_conditions`, `next_trigger`, and `risk_note`.

**Implementation status:**

- **`lib/technical.py`** — `snapshot()` additively returns `EMA_10`, `EMA_20`,
  `nearest_support`, `nearest_resistance`, `candlestick_pattern` (SMA_50 / SMA_200 /
  ATR_14 already present).
- **`lib/valuation_anchor.py`** (new) — `FairValueAnchor` + `compute_fair_value_anchor`
  (yfinance only; cached TTL=3600 keyed on ticker; fail-closed). `analyst_anchor` =
  `targetMeanPrice × 0.90`; `relative_anchor` = median trailing P/E (last ≤4
  quarters) × `trailingEps`; `valuation_anchor` = `price × (1 − pctile × 0.30)`;
  `fair_value_anchor` = `min` of non-None anchors, else `price × 0.85` (> 0).
- **`lib/order_advisor.py`** — refactored `PriceLevelResult` (v3 fields + retained
  legacy fields), horizon-native `_compute_initiate_logic` / `_compute_add_logic`,
  horizon-differentiated stops (SHORT EMA/support+1ATR clamp [0.93,0.99]; MID
  SMA50−1.5ATR / −2ATR clamp [0.80,0.99]; LONG SMA200 / −3ATR clamp [0.70,0.99]),
  universal thesis + fundamental gates, Step-4 stop-vs-zone sanity, `entry_status`,
  `risk_reward_ratio` (0.0 when no zone), `approved_for_execution` ALWAYS False.
  `generate_order_narrative` + `OrderNarrative` gained `next_trigger_note`.
- **`pages/9_Trading_Desk.py`** — scenario badge, color-coded action badge,
  `missing_conditions` list, prominent `next_trigger`, `position_sizing`, and the
  LLM `next_trigger_note`. All chrome via `t()`.
- **`lib/thesis_monitor.py`** — `short_time_stop_signal` + SHORT time stop wired
  into `check_holding` (≥5 days, price ≤ cost×1.02 → `time_stop` → broken). This is
  the one allowed exception to the generic "do not modify thesis_monitor" guardrail,
  as explicitly required by the task spec (step 6) + the test assertion.
- **`scripts/test_reliability_phase_6c_v2_entry_strategy.py`** (new) — mock-only; **79/79**.
- **`ui_utils.py`** — additive EN/ZH `td_scenario_*` / `td_act_*` / `td_missing_conditions`
  / `td_next_trigger` / `td_risk_note` / `td_fair_value_anchor` `t()` keys only.

**Guardrails honored:** free sources only (yfinance); no paid API; no broker / order
/ execution; `approved_for_execution` always False; no DB / vector store.
`lib/macro_regime.py`, `lib/macro_data.py`, `lib/workflow_state.py`,
`lib/holdings.py`, `lib/signal_engine.py`, `.claude/agents/*`, pages 1–8 not
modified (`lib/thesis_monitor.py` modified only for the spec-mandated SHORT time
stop).

**Validation (run via WSL `wsl.exe -d ubuntu -- bash -lc 'python3 -B ...'`):**

```bash
git status --short
python3 -B scripts/test_reliability_phase_6c_v2_entry_strategy.py   # 79/79
python3 -B scripts/test_reliability_phase_6c_trading_desk.py        # 118/118 regression
python3 -B scripts/test_reliability_phase_6b_v3_horizon_scoring.py  # 189/189 regression
python3 -B scripts/test_reliability_phase_6a_live_data.py           # 336/336 regression
```

**Next step:** Codex review of Phase 6C-A v2. **Recommended next phase after
acceptance:** **Phase 6C-B — Cockpit Rebuild** (not started).

---

## Phase 6C-A — Trading Desk — Implemented; Awaiting Codex Review

**The current task is Phase 6C-A — Trading Desk.** It adds the **execution
layer** of the workflow as a new Streamlit page `pages/9_Trading_Desk.py` with
three sections: (1) **Holdings Monitor** — manual position entry persisted to
`data/holdings.json` with a four-signal **Thesis Invalidation Monitor**;
(2) **Order Recommendations** — code-computed entry/exit levels with an LLM
narrative; (3) **Opportunity Watch** — Scanner triple-signal candidates turned
into add-to-holdings setups.

**Phase 6C-A is not accepted in this pass. Phase 6C-B has not started.**

Single acceptance criterion: *"The user can record a position in MU with a
thesis, open the app the next day, and immediately see whether the thesis is
intact or weakening, and what order to consider."*

**Implementation status:**

- **`lib/holdings.py`** (new) — `HoldingRecord` dataclass + the SINGLE read/write
  API for `data/holdings.json` (`load_holdings`→`[]` on absent/corrupt;
  `save_holdings`→`False` on failure via temp-file + `os.replace`;
  `add_holding`/`update_holding` partial/`close_holding`/`get_active_holdings`).
  All fail-closed; never raises; `data/` created on first write; no DB/vector store.
- **`lib/thesis_monitor.py`** (new) — `ThesisCheckResult` + four fail-closed
  signals (News LLM cached TTL=14400 `(ticker,date)`; EPS via
  `fetch_fundamental_signals`; Technical breakdown via `lib.technical.snapshot()`;
  Macro regime for short/mid only) and a DETERMINISTIC `compute_thesis_status`
  (intact/watch/weakening/broken). `is_normal_pullback` = below cost AND above
  SMA200 AND RSI 35–50. `run_thesis_monitor` ThreadPoolExecutor max_workers=4,
  4h in-process result cache (not persisted).
- **`lib/order_advisor.py`** (new) — `compute_price_levels` PURE CODE (entry zone,
  ATR stop, target, support/resistance, volume_trend, candlestick_pattern,
  `risk_reward_ratio`, Kelly-lite `position_size_pct` clamped 2%–10%; live/fixture
  fail-closed). `generate_order_narrative` is ONE LLM call synthesizing a narrative
  over the computed levels only (no numbers invented); cached TTL=3600; zh via
  translator; fail-closed baseline. `OrderRecommendation`/`OrderNarrative`/
  `PriceLevelResult` dataclasses.
- **`pages/9_Trading_Desk.py`** (new) — three sections; monitor auto-runs on load
  (4h TTL); Section 1 is a SINGLE filterable holdings table (status + horizon
  filters; ticker / shares / cost / current price / P&L% / horizon / colored status
  badge / truncated key alert / per-row Edit) with inline, MUTUALLY-EXCLUSIVE Add
  and Edit/Close forms below the table; Add Position with `cockpit_all_signals`
  thesis import; order cards (broken-thesis exit-only separated); Opportunity
  Watch from `cockpit_triple_signals`. Never writes `holdings.json` directly.
- **`ui_utils.py`** (additive only) — EN/ZH `nav_p9` + `td_*` keys + one
  `st.page_link("pages/9_Trading_Desk.py")` after `nav_p4` / before `nav_p7`.
- **`scripts/test_reliability_phase_6c_trading_desk.py`** (new) — mock-only;
  **115/115**.

**Guardrails honored:** holdings persist ONLY to local `data/holdings.json`; no
DB/vector store; no paid API (yfinance + Finnhub free tier); no broker/order/
execution capability; no order ticket/broker payload; `approved_for_execution`
absent everywhere; all data calls fail-closed with fixture fallback.
`lib/macro_regime.py`, `lib/macro_data.py`, `lib/workflow_state.py`,
`lib/llm_orchestrator.py`, `.claude/agents/*`, and pages 1–8 not modified.

**Validation (run via WSL `wsl.exe -d ubuntu -- bash -lc 'python3 -B ...'`):**

```bash
git status --short
python3 -B scripts/test_reliability_phase_6c_trading_desk.py       # 115/115
python3 -B scripts/test_reliability_phase_6b_v3_horizon_scoring.py  # 189/189 regression
python3 -B scripts/test_reliability_phase_6a_live_data.py           # 336/336 regression
python3 -B scripts/test_reliability_phase_5s_closeout.py            # 116/116 regression
```

**Next step:** Codex review of Phase 6C-A. **Recommended next phase after
acceptance:** **Phase 6C-B — Investment Cockpit Rebuild** (not started).

---

## Phase 6B v3 — Horizon-Native Signal Scoring — Implemented; Awaiting Codex Review

**The current task is Phase 6B v3 — Horizon-Native Three-Track Signal Scoring.**
It replaces the v2 single composite score in `lib/signal_engine.py` +
`lib/candidate_generator.py` with **three INDEPENDENT horizon scores** (short /
mid / long), merges **catalyst detection** into the existing single Layer-2 LLM
narrative call, outputs a `CandidateSignal` dataclass exposing `signal_strength`
(triple / double / single / none) and `horizons_hit`, renders results as
**signal cards** with horizon-checkbox filtering in `pages/3_Scanner.py`, and
writes triple-hit candidates to `st.session_state` for a future Cockpit
integration.

**Phase 6B v3 is not accepted in this pass. Phase 6C has not started.**

**Implementation status:**

- **`lib/signal_engine.py`** — new `CandidateSignal` dataclass (subclasses the v2
  `TickerSignalResult`). Three independent horizon scorers (`compute_short_score`
  / `compute_mid_score` / `compute_long_score`) + `derive_horizons_hit` /
  `derive_signal_strength` / `build_key_signals` / `build_candidate_signal`.
  - SHORT (sum 1.0): technical_momentum ×0.40 / catalyst ×0.35 /
    momentum_continuation ×0.25; hit ≥ 0.65.
  - MID (sum 1.0): eps_revision ×0.35 / narrative_stage ×0.30 (+0.10 aligned) /
    valuation ×0.20 / quality_composite ×0.15; hit ≥ 0.60.
  - LONG (sum 1.0): valuation ×0.35 / quality_composite ×0.35 / narrative_stage
    ×0.20 / macro_alignment ×0.10; hit ≥ 0.55.
  - Catalyst detection merged into the single `llm_narrative_match` call (same
    TTL=3600; widened prompt for `catalyst_summary` / `catalyst_horizon` /
    `catalyst_recency` / `already_priced_in`; safe-defaulted on parse failure).
    `score_ticker()` returns a `CandidateSignal`. Track A / Track B architecture
    and the standalone Track B trigger (≥ 0.7 → `ALT_SIGNAL`) preserved.
- **`lib/candidate_generator.py`** — `generate_candidates()` returns
  `list[CandidateSignal]`, sorted triple → double → single → none (within group
  by (short+mid+long)/3 desc), and writes
  `st.session_state["cockpit_triple_signals"]` (triple hits) +
  `["cockpit_all_signals"]` (all, with `signal_strength` + `timestamp`);
  fail-closed.
- **`pages/3_Scanner.py`** — signal cards (`st.container(border=True)`; triple =
  gold `#d4a017` border + 🔥; score pills with ✓/○; catalyst row;
  `already_priced_in` warning; Details expander) + three horizon-filter
  checkboxes filtering on `horizons_hit` + a triple/double/single summary line.
  `SCANNER_SIGNAL_MODE` + universe config + manual scanner preserved.
- **`ui_utils.py`** — additive EN/ZH `scn_sig_*` (`scn_sig_filter_label` /
  `scn_sig_hz_*` / `scn_sig_strength_*` / `scn_sig_triple_header` /
  `scn_sig_priced_in` / `scn_sig_details` / `scn_sig_summary` / `scn_sig_eps` /
  `scn_sig_val` / `scn_sig_narr_stage` / `scn_sig_theme_tags`) `t()` keys only.
- **Signal-card fixes (follow-up pass):** (1) **Chinese translation** — when
  `language=="zh"`, the display fields `catalyst_summary` / theme-tag labels /
  `key_signals` are translated via `lib/translator.py` (deep-translator) before
  being stored on the `CandidateSignal`; the English LLM prompt/response are
  unchanged; `lang` is threaded `generate_candidates → build_candidate_signal /
  score_ticker` and added to the `_generate_candidates_cached` + `_localize_texts`
  TTL cache keys; fail-closed. (2) **Empty theme_tags fallback** — the LLM prompt
  now requires choosing `theme_tags` from the fixed taxonomy; if still empty, a
  `THEME_BASKETS` constituent reverse-lookup (`_theme_tags_for_ticker`) supplies
  the matching theme's `label_zh`/`label_en`. (3) **Track B data sources**
  documented in the v3 design doc (insider `/stock/insider-transactions`,
  analyst `/stock/recommendation`, unusual news `/company-news` keyword match —
  all Finnhub free tier).
- **LLM-coverage + Layer-1 tuning (follow-up pass):** (a) the Scanner LLM
  narrative-depth slider now ranges **10–100 (default 50)** and
  `generate_candidates` default `llm_n` is **50**, clamp ceiling **100** — so a
  far larger fraction of Layer-1 survivors get a real narrative instead of the
  `unknown` neutral fallback (S&P top-100 coverage: 31% @ llm_n=30 → 51% @ 50 →
  100% @ 100). (b) The stale **`FI`** entry in `SP500_TOP_100` (yfinance 404) is
  replaced with **`FISV`** (the symbol Yahoo/yfinance resolves Fiserv under). (c)
  A Layer-1 **liquidity floor** (`_MIN_DOLLAR_ADV = $10M` average daily dollar
  volume, computed from yfinance `info` only — no extra fetch; skipped when
  volume/price absent; never consults RSI/momentum) trims illiquid theme/manual
  small-caps before the LLM cut; the `$2B` market-cap floor and `-50%`
  price-break gates are retained.
- **`scripts/test_reliability_phase_6b_v3_horizon_scoring.py`** (new) — mock-only;
  **189/189**.

**Guardrails honored:** no paid APIs (yfinance + Finnhub free tier only); no
broker / order / execution; `approved_for_execution` False or absent; no DB /
vector store / persistence; all data calls fail-closed with fixture fallback.
`lib/macro_regime.py`, `lib/macro_data.py`, `lib/theme_baskets.py`,
`lib/workflow_state.py`, `.claude/agents/*`, pages 1–2 and 4–8 not modified;
`ui_utils.py` only gained `t()` keys. Phase 6C not started.

**Validation (run via WSL `wsl.exe -d ubuntu -- bash -lc 'python3 -B ...'`):**

```bash
git status --short
python3 -B scripts/test_reliability_phase_6b_v3_horizon_scoring.py  # 189/189
python3 -B scripts/test_reliability_phase_6b_v2_dual_track.py       # 217/217 regression
python3 -B scripts/test_reliability_theme_baskets.py               # 146/146 regression
python3 -B scripts/test_reliability_phase_6a_live_data.py          # 336/336 regression
python3 -B scripts/test_reliability_phase_5s_closeout.py           # 116/116 regression
```

**Next step:** Codex review. **Recommended next phase after acceptance:**
**Phase 6C — Holdings & Thesis Monitor** (not started).

---

## Phase 6B sub-task — Scanner Universe Integration — Implemented; Awaiting Codex Review

**The current sub-task is the Scanner Universe Integration** (under Phase 6B). It
integrates the cross-GICS theme baskets into Scanner **universe construction** and
adds a **Universe Configuration** UI to `pages/3_Scanner.py`. The Scanner builds
its candidate universe from a user-shaped mix of the S&P 500 top-100 anchor,
selected theme baskets, the Sector Research `theme_universe` hand-off, manual
tickers, and `research_state` subsector constituents.

**Implementation status:**

- **`lib/candidate_generator.py`** — new `UniverseConfig` dataclass
  (`include_sp500_top100=True` / `selected_themes=[]` / `manual_tickers=[]` /
  `max_size=150`) + `build_universe(config) -> list[str]` (source order: S&P 500
  anchor → selected `THEME_BASKETS` constituents → `theme_universe` session
  hand-off → manual tickers → `research_state`; deduped, capped at `max_size`,
  fail-closed). `generate_candidates(macro_regime, top_n, llm_n, config=None)`
  now accepts an optional `UniverseConfig` (legacy `get_universe()` used when
  `None`); the assembled universe tuple is part of the `st.cache_data` key so
  each configuration caches separately. Legacy `get_universe()` preserved.
- **`pages/3_Scanner.py`** — a **Universe Configuration** expander above the AI
  Signal Candidates section (Include S&P 500 top 100 checkbox; Add theme baskets
  multi-select over all 11 themes; comma-separated manual-ticker input; Max
  universe size slider 50–300 / default 150 / step 25; live "Current universe: N
  tickers" caption with no market-data fetch). A `theme_universe` pre-load info
  banner + **Clear** button when the Sector hand-off is set. The
  `UniverseConfig` is passed to `generate_candidates(..., config=_uni_config)`.
- **`ui_utils.py`** — additive EN/ZH `scn_uni_*` `t()` keys only.
- **`scripts/test_reliability_scanner_universe.py`** (new) — mock-only; **42/42**.

**Guardrails honored:** `lib/signal_engine.py` logic and `THEME_BASKETS`
definitions unchanged; `lib/workflow_state.py`, `.claude/agents/*`, pages 1–2 /
4–8 not modified; `ui_utils.py` only gained `t()` keys; no broker / order /
execution; no DB / vector store / persistence; no paid APIs;
`approved_for_execution` False or absent.

**Validation (run via WSL `wsl.exe -d ubuntu -- bash -lc 'python3 -B ...'`):**

```bash
git status --short
python3 -B scripts/test_reliability_scanner_universe.py        # 42/42
python3 -B scripts/test_reliability_theme_baskets.py           # 137/137 regression
python3 -B scripts/test_reliability_phase_6b_v2_dual_track.py  # 217/217 regression
python3 -B scripts/test_reliability_phase_6a_live_data.py      # 336/336 regression
```

**Next step:** Codex review. Recommended next phase after acceptance is
**Phase 6C — Holdings & Thesis Monitor** (not started).

---

## Phase 6B sub-task — Cross-GICS Theme Basket Extension — Implemented; Awaiting Codex Review

**The current sub-task is the Theme Basket Extension** (under Phase 6B). It
extends Sector Research with **cross-GICS theme baskets** alongside the existing
GICS sector / subsector coverage, surfaced as a new **"Market Themes" tab** on
`pages/2_Sector.py`. Theme momentum is computed deterministically and staged into
`st.session_state["theme_universe"]` for a future Scanner universe integration.

**Implementation status:**

- **`lib/theme_baskets.py`** (new) — `THEME_BASKETS` (11 themes, "manually
  curated, June 2026"); `ThemeMomentumResult` dataclass; `compute_theme_momentum`
  (ETF themes → ETF returns `data_source="etf"`; ETF-less → equal-weight average
  across constituents `data_source="equal_weight"`; failure → `data_source=
  "fixture"`); `compute_all_themes` (3M-return percentile `momentum_score`, sorted
  desc, `st.cache_data(ttl=1800)`); `send_top_theme_to_scanner` /
  `send_all_themes_to_scanner` hand-off helpers. All fail-closed.
- **`pages/2_Sector.py`** — existing body wrapped unchanged into a **Sector
  Analysis** tab; new **Market Themes** tab (color-coded momentum heatmap;
  per-theme expanders with constituent 1M/3M returns + a Plotly 3M-return bar +
  description; per-theme **Analyze** button → `analyze_theme_basket` on click;
  **Send top theme** / **Send all** Scanner hand-off buttons).
- **`lib/llm_orchestrator.py`** — additive `analyze_theme_basket` (macro_alignment
  / narrative_stage / key_catalysts / risk_factors / horizon_bias / summary;
  bilingual; fail-closed).
- **`ui_utils.py`** — additive EN/ZH `theme_*` + `p2_tab_sector` `t()` keys only.
- **`scripts/test_reliability_theme_baskets.py`** (new) — mock-only; **137/137**.

**Guardrails honored:** `lib/workflow_state.py`, `.claude/agents/*`, pages 1 and
3–8 not modified; `lib/llm_orchestrator.py` only gained a new analysis function;
`ui_utils.py` only gained `t()` keys; no broker / order / execution; no DB /
vector store / persistence; all data calls fail-closed with fixture fallback; no
paid APIs (yfinance only); `approved_for_execution` False or absent.

**Validation (run via WSL `wsl.exe -d ubuntu -- bash -lc 'python3 -B ...'`):**

```bash
git status --short
python3 -B scripts/test_reliability_theme_baskets.py            # 137/137
python3 -B scripts/test_reliability_phase_6b_v2_dual_track.py   # 217/217 regression
python3 -B scripts/test_reliability_phase_6a_live_data.py       # 336/336 regression
python3 -B scripts/test_reliability_phase_6b_signal_layer.py    # 211 passed, 1 failed (pre-existing v1 7.1)
```

**Next step:** **Scanner universe integration** — consume
`st.session_state["theme_universe"]` in `pages/3_Scanner.py` (not started).

---

## Phase 6B v2 — Dual-Track Signal Architecture — Implemented; Awaiting Codex Review

**The current task is now Phase 6B v2 — Dual-Track Candidate Architecture.**
Phase 6B v2 refactors the v1 single-pass, momentum-biased scoring in
`lib/signal_engine.py` + `lib/candidate_generator.py` into a **dual-track**
architecture so the candidate list can surface *early-stage* opportunities
(MU-style: low RSI, depressed price, fundamental inflection) alongside
alternative-data-triggered candidates, both clearly labeled by signal source.
Single acceptance criterion: *"The candidate list can surface a ticker like MU
at cycle bottom — low RSI, far from 52W high, but with improving EPS revision and
narrative alignment — alongside a ticker flagged purely by an unusual
news/insider signal, with both clearly labeled by their signal source."*

**Phase 6B v2 is not accepted in this pass. Phase 6C has not started.**

**Implementation status (Phase 6B v2):**

- **`lib/signal_engine.py`** — dual-track contracts `NarrativeResult` /
  `FundamentalResult` / `EntryQualityResult` / `TrackAResult` / `TrackBResult` /
  `TickerSignalResult` (`ticker` / `track_a` / `track_b` / `composite_score` /
  `horizon_fit` / `signal_summary` / `candidate_type` ∈ {FUNNEL, ALT_SIGNAL,
  BOTH}). Track A = Layer 1 hard filter (`passes_layer1`, code only — market cap
  < $2B / 30-day decline < −50% / missing fundamentals; **never** RSI / momentum
  / 52W / ADX) + Layer 2 LLM narrative (`llm_narrative_match`, the ONLY LLM,
  in-function `llm_orchestrator` import, fail-closed, TTL=3600) + Layer 3
  fundamentals (`fetch_fundamental` — `eps_revision_direction` where
  `inflecting_up` = a beat AFTER ≥1 miss; valuation percentile; margin trend;
  universe-normalized quality). Track B (`compute_track_b`) = insider 40% /
  unusual-news 35% / analyst 25% over the full universe; composite ≥ 0.7 =
  standalone ALT_SIGNAL. Entry-quality modifier good ×1.1 (boost) / fair / ext /
  avoid. v1 shims retained.
- **`lib/candidate_generator.py`** — `get_universe()` (unchanged; S&P 500 top-100
  incl. MU + research_state subsector, capped 150), `run_layer1_filter`,
  `run_layer2_narrative(filtered, macro_regime, llm_n)`, `run_layer3_fundamental`,
  `run_track_b(universe, macro_regime)`, `generate_candidates(macro_regime,
  top_n=20, llm_n=30)` with staged `st.progress` labels, cached TTL=1800 keyed
  `(macro_regime, top_n, llm_n)`; ALT_SIGNAL-only appended after FUNNEL.
- **`pages/3_Scanner.py`** — LLM narrative-depth slider (10–50, default 30, est
  `~llm_n×2`s), color-coded Type column, Track A / Track B sub-score expander,
  ALT_SIGNAL trigger source in Key Signals; `SCANNER_SIGNAL_MODE` + manual
  scanner preserved.
- **`ui_utils.py`** — additive EN/ZH `scn_sig_llm_*` / `scn_sig_col_type` /
  `scn_sig_subscores` / `scn_sig_col_track_*` / sub-signal column keys only.
- **`scripts/test_reliability_phase_6b_v2_dual_track.py`** — mock-only; **217/217**.
- **`docs/reliability_phase_6b_signal_layer.md`** — new "v2 Dual-Track
  Architecture" section appended (v1 content retained).

**Validation (run via WSL `wsl.exe -d ubuntu -- bash -lc 'python3 -B ...'`):**

```bash
git status --short
python3 -B scripts/test_reliability_phase_6b_v2_dual_track.py   # 217/217
python3 -B scripts/test_reliability_phase_6b_signal_layer.py    # 211 passed, 1 failed (v1 superseded — see note)
python3 -B scripts/test_reliability_phase_6a_live_data.py       # 336/336 regression
python3 -B scripts/test_reliability_phase_5s_closeout.py        # 116/116 regression
```

> Note on the v1 test: `test_reliability_phase_6b_signal_layer.py` encodes the
> v1 contract and is **superseded** by v2. Its single failing assertion (7.1)
> asserts that `signal_engine.py` imports/calls no `llm_orchestrator` — which v2
> deliberately reverses by introducing the in-function Layer-2 LLM import. This
> is the only by-design v1 regression; all other v1 assertions still pass
> (backward-compat shims preserved).

**Recommended next step:** Codex review of Phase 6B v2. **Recommended next phase
after acceptance:** Phase 6C — Holdings & Thesis Monitor (not started). **Phase 6C
has not started.**

---

### Historical — Phase 6B v1 (single-pass; superseded by v2 above)

**Phase 6B — Stock Selection Signal Layer (v1).** Phase 6B
upgrades the Scanner from manual ticker-pool entry to a system that
**automatically generates candidates** using free alternative-data and
fundamental signals — surfacing early-stage opportunity signals, not just the
strongest momentum names — ranked by a combination of alternative data,
EPS-revision trend, narrative attribution, and entry quality. Acceptance
criterion: *"The user opens the Scanner page and sees an AI-generated candidate
list based on real signals, without manually entering a ticker pool."*

**Phase 6B is not accepted in this pass. Phase 6C has not started.** (**Phase 6A
— Live Data Integration — is now Accepted** as part of the Phase 6B pre-task
cleanup. Phase 5S — Phase 5 Productization Closeout — remains **Implemented;
Awaiting Codex Review**; its closeout artifacts reflect the pre-6A snapshot and
are unchanged. The historical Phase 6A / Phase 5 narrative below is retained for
context.)

**Implementation status (Phase 6B):**

- `lib/signal_engine.py` (new) — multi-factor per-ticker signals. Public:
  `fetch_fundamental_signals` (yfinance fundamentals + Finnhub
  `/stock/recommendation` → recommendation momentum + Finnhub `/stock/earnings`
  → EPS surprise trend + hardcoded sector-median forward-P/E valuation percentile
  + ROE/gross-margin/revenue-growth quality score), `fetch_narrative_signals`
  (Finnhub `/company-news`, **keyword-rule** theme attribution + narrative
  strength + macro alignment — **no LLM**), `compute_entry_quality` (deterministic
  from `lib/technical.snapshot()`: RSI position / ADX trend / SMA200 /
  distance-from-52w-high → entry_quality_label), and `score_ticker`
  (`FundamentalSignals` / `NarrativeSignals` / `EntryQualityScore` →
  `TickerSignalResult` with composite score, horizon fit, signal summary).
  Composite weights: fundamental quality 30% / EPS surprise trend 25% / entry
  quality 25% / narrative strength + macro alignment 20%. Every fetch
  `try/except` fail-closed, cached `st.cache_data(ttl=1800)`.
- `lib/candidate_generator.py` (new) — `get_universe()` (hardcoded S&P 500
  top-100 by market cap + `research_state` subsector constituents, deduped,
  capped 150) and `generate_candidates(macro_regime, top_n=20)`
  (`ThreadPoolExecutor` max_workers=8 + `st.progress`, sorted by composite score,
  cached TTL=1800).
- `pages/3_Scanner.py` — AI候选信号 / AI Signal Candidates section at the top,
  gated by `SCANNER_SIGNAL_MODE = True` (when `False`, exact pre-6B behavior);
  Generate-Candidates button → `st.session_state["signal_candidates"]`; ranked
  table (Ticker / Composite Score colored green>0.65/yellow/red<0.4 / Entry
  Quality / Horizon Fit short-mid-long / first 2 Key Signals); Send-to-Manual-
  Scanner button pre-fills the existing manual pool. Manual scanner preserved
  unchanged below a `st.divider()`.
- `ui_utils.py` — additive EN/ZH `scn_sig_*` chrome keys only.
- `scripts/test_reliability_phase_6b_signal_layer.py` — mock-only; **212/212**.
- Cross-page macro regime sharing (follow-up, Plan A): `pages/8_Macro_Dashboard.py`
  additively publishes `st.session_state["macro_regime_result"]` (regime /
  confidence / horizon_bias / data_coverage) after a successful `classify_regime()`
  — no existing macro rendering/logic change. The Scanner obtains the regime
  **directly** via `classify_regime(fetch_all_macro())` before
  `generate_candidates()` (both fail-closed + `st.cache_data`-cached, so a prior
  macro-page visit is a free cache hit and an unvisited session fetches live),
  publishes the same dict, shows the loaded regime status (no "visit macro page"
  hint), and on error reuses a prior regime / `"unknown"`. `generate_candidates`
  is a normalizing wrapper over the cached worker keyed `(macro_regime, top_n)`
  so each regime caches separately. Phase 5O page-8 regression 766/766.
- Guardrails honored: `lib/llm_orchestrator.py`, `lib/workflow_state.py`,
  `.claude/agents/*`, pages 1–2 and 4–7 untouched (`pages/8_Macro_Dashboard.py`
  modified additively only — cross-page publish, no behavior change); live AI
  research workflow (incl. `pages/1_Overview.py`) and the existing manual scanner
  unchanged; no broker/order/execution; `approved_for_execution` False or absent;
  no DB / vector store / persistence; no new LLM calls; only free APIs (Quiver
  Quantitative not included).
- Design doc: `docs/reliability_phase_6b_signal_layer.md`.

**Recommended next step:** Codex review of Phase 6B. **Recommended next phase
after acceptance:** Phase 6C — Holdings & Thesis Monitor (not started).
**Neither Phase 6B nor Phase 6C is accepted.**

**Validation (run via WSL `wsl.exe -d ubuntu -- bash -lc 'python3 -B ...'`):**

```bash
git status --short
python3 -B scripts/test_reliability_phase_6b_signal_layer.py   # 212/212
python3 -B scripts/test_reliability_phase_6a_live_data.py      # 336/336 regression
python3 -B scripts/test_reliability_phase_5o_macro_dashboard.py # 766/766 page-8 regression
python3 -B scripts/test_reliability_phase_5s_closeout.py       # 116/116 regression
```

---

### Historical — Phase 6A (now Accepted; retained for context)

## Phase 6A — Live Data Integration — Accepted

**Phase 6A — Live Data Integration — Accepted.** Phase 6A was the
first phase that made the app genuinely usable for real investment-decision
support: it replaces fixture/mock data on the Macro Dashboard with **live, free**
market and macro data. Acceptance criterion: *"The user opens Macro Dashboard and
sees real market data that reflects today's conditions."*

**Implementation status (Phase 6A):**

- `lib/macro_data.py` (new) — all live macro fetching from free sources only:
  yfinance (`^VIX` + ETF proxies QQQ/IWM/SPY/GLD/USO/TLT/HYG), FRED
  (DGS10/DGS2/T10YIE/BAMLH0A0HYM2/DTWEXBGS/PAYEMS/CPIAUCSL/PPIACO via
  `FRED_API_KEY`), and Finnhub free tier (`/stock/social-sentiment`,
  `/news?category=general` via the existing `FINNHUB_API_KEY`). Eight public
  `fetch_*` functions, each individually `try/except` fail-closed and cached
  `st.cache_data(ttl=900)`; returns `MacroDataResult` with a `data_source` per
  metric group, a `timestamp`, and a `data_coverage` float.
- `lib/macro_regime.py` (new) — deterministic `classify_regime` →
  `MacroRegimeResult` (regime/confidence/horizon_bias/key_signals/
  opportunity_posture/data_coverage); `data_coverage < 0.5` ⇒ `degraded`.
- `pages/8_Macro_Dashboard.py` — Live Macro Conditions section with LIVE/FIXTURE
  badges, data-coverage + freshness indicators, and a single `MACRO_LIVE_MODE`
  feature flag (default `True`); fixture tabs preserved; fail-closed.
- `ui_utils.py` — additive EN/ZH `macro_live_*` chrome keys.
- `scripts/test_reliability_phase_6a_live_data.py` — mock-only; **336/336**.
- UX refinement: the Macro Dashboard live page is now fully bilingual (regime /
  confidence / horizon-bias / key-signals / posture / theme implications all via
  `t()`), uses terminal-style metric cards (1–2 headline numbers, small top-right
  LIVE/FIXTURE tag, collapsed detail footers), and drives the sub-regime readouts
  (rates / inflation / liquidity / credit / volatility / breadth / dollar / risk
  appetite) from the live FRED + ETF data instead of fixture placeholders.
- Visual upgrade: prominent top **hero regime banner** (large, color-coded by
  regime); core metric values enlarged (~1.5×) and sign-colored (green/red);
  regime / bias / status rendered as **color-coded badges** (risk_on=green,
  risk_off=red, transition=amber, degraded=gray); per-card collapsible **history
  trend** tables sliced from the existing yfinance/FRED fetches (no new API
  calls); cleaner card spacing + simplified tab titles (no "/" separators).
- Font system: `ui_utils.py` loads a professional financial font stack via Google
  Fonts (**Inter** headings/body, **JetBrains Mono** for all data/numbers) as a
  global `_FONT_CSS` block in `apply_theme()`; numeric elements use
  `font-variant-numeric: tabular-nums` so columns align. All pages inherit it;
  page-8 hardcoded big numbers were reduced to **1.6rem** (mono, tabular).
- Trend charts: each history expander now shows a **Plotly line chart** above the
  table (X=date, Y=value, 200px, no legend/gridlines, line color = pos/neg
  semantic), built with the global `apply_layout()`/`apply_legend()`. Covers 10Y,
  2Y, 10Y-2Y spread, VIX, HY credit, dollar index, and per-ETF cumulative returns
  (QQQ/IWM/SPY/GLD/USO/TLT/HYG). Data sliced from the existing yfinance/FRED
  fetches (rates gained date-aligned 2Y+spread history; ETF gained per-ticker
  cumulative-return history) — no new API calls; each chart has a unique key.
- Release charts + chrome cleanup: the NFP/CPI/PPI expander adds NFP monthly
  change + CPI/PPI MoM % charts derived from FRED levels (no new API calls); all
  user-facing macro titles/captions were de-jargoned (removed FRED/Finnhub/
  yfinance/endpoint/fallback/MACRO_LIVE_MODE/source_type/schema-flag/fixture
  parentheticals → concise names). Code comments/docstrings unchanged; the
  cockpit (page 7) demo labels left intact (guardrail + honest disclosure).
- Overview intro page: the Overview tab is now a user-facing intro — simple title
  ("宏观仪表盘"/"Macro Dashboard", no version/demo annotations), one merged
  data-mode banner (live vs degraded by actual coverage), three concise blocks
  (current market state = regime + confidence + horizon bias; what this page
  covers = 6 one-line dimensions; data sources & update frequency), and a single
  short disclaimer. Developer guardrail bullets (No live macro API / LLM / broker
  / approved_for_execution) removed from the UI; demo walkthrough kept but
  collapsed.
- CNN Fear & Greed → VIX-derived proxy (documented). No paid API; no new LLM;
  no broker/order/execution; `approved_for_execution` False or absent. Live AI
  research workflow, pages 1–6, `pages/7_Investment_Cockpit.py`,
  `lib/llm_orchestrator.py`, `lib/workflow_state.py`, `.claude/agents/*` untouched.
- Design doc: `docs/reliability_phase_6a_live_data_integration.md`.

**Phase 6A is now Accepted** (promoted during the Phase 6B pre-task cleanup). The
active task is **Phase 6B — Stock Selection Signal Layer** (Implemented; Awaiting
Codex Review); see the top of this file. **Phase 6B is not accepted; Phase 6C has
not started.**

**Validation (run via WSL `wsl.exe -d ubuntu -- bash -lc 'python3 -B ...'`):**

```bash
git status --short
python3 -B scripts/test_reliability_phase_6a_live_data.py    # 336/336
python3 -B scripts/test_reliability_phase_5s_closeout.py     # regression
python3 -B scripts/test_reliability_phase_5r_ui_ux_polish.py # regression
```

---

### Historical — Phase 5 productization (retained for context)

**Last updated**: 2026-05-29 — **Phase 5H / 5H.1 / 5I / 5J / 5K / 5L / 5M / 5N
Accepted; Phase 5O — Macro Dashboard v0.1 — Accepted (Codex verdict PASS);
Phase 5O.1 — Macro Indicator Expansion — Accepted; Phase 5P — Source Page
Navigation Cleanup — Accepted (Codex verdict PASS); Phase 5Q — Human Feedback UI
v0.1 — Accepted (Codex verdict PASS); Phase 5R — UI/UX Visual Polish + Demo
Readiness — Accepted; Phase 5S — Phase 5 Productization Closeout — Implemented;
Awaiting Codex Review.**
The current task is now **Phase 5S** (see the **Current Task** and **Next
Action** sections below). Phase 5S is a **closeout / documentation / state /
test-summary** pass that documents the completed Phase 5 productization layer,
the current UI state, the accepted phase history, the validation matrix, the
safety boundaries, the accepted dirty-worktree provenance, and a recommended
conservative Phase 6 starting point. It adds **no** new runtime feature, UI
layout change, or product-logic change. Deliverables:
`docs/ai_dev_state/PHASE_5_CLOSEOUT.md`,
`docs/reliability_phase_5s_productization_closeout.md`,
`scripts/test_reliability_phase_5s_closeout.py`, and these state files. No live
workflow / LLM / external API is called; no DB / vector store / persistence /
broker / order / execution is introduced; `approved_for_execution` is False or
absent everywhere. **Phase 5 is not formally accepted until Codex review accepts
Phase 5S; Phase 5S is not marked accepted in this pass; Phase 6 has not
started.** **Phase 5R — UI/UX Visual Polish + Demo Readiness — is now Accepted**
in this pass per the prior review's minor suggestion. The historical Phase 5R /
5Q / 5P / 5O.1 / 5O / 5N narrative in this file is retained for context.
Phase 5M was
schema / helper / view-model / fixture only (offline / mock-only). It
structures agent debate and decision-workspace review **after** a Phase 5L
research pack is assembled (Phase 5K Opportunity Candidate → Phase 5L
Research Pack → Phase 5M Agent Debate / Decision Workspace → future Phase 5N
Cockpit UI v0.2) without running any real agent, LLM, or external API. Agent
roles (bull / bear / risk / critic / allocation / option / synthesis) are
deterministic role records; bull/bear/risk/critic perspectives are
separated; allocation and option are review-only planning perspectives;
disagreements surface as explicit `DebateConflictRecord`s the critic never
hides; the `DecisionWorkspaceView` is review-only
(`is_executable_decision=False`, `requires_human_review=True`). Phase 5M test
263/263; Phase 5L 220/220; Phase 5K 218/218. Next recommended phase after
Phase 5M acceptance: **Phase 5N — Cockpit UI v0.2 Opportunity-first
Redesign** (not started). See the **Current Task** and **Next Action**
sections below for the active state. The historical Phase 5H narrative below
("What Was Done (Phase 5H)") is retained for context only.

<details><summary>Prior header (historical — Phase 4M-H / Phase 5P / Phase 5A–5H.1)</summary>

(Phase 4M-H Phase 4 Memory Closeout
**Accepted**. Phase 5P Phase 5 Roadmap Decision / Planning **Accepted**.
Phase 5A Existing Workflow Memory Adapter + Fixture-backed Memory Query
Contract **Accepted**. Phase 5B Company Research Hub ViewModel Contract
**Accepted**. Phase 5C Horizon Decision Cards + ThesisTracker ViewModel
Contract **Accepted**. Phase 5D Portfolio / TradePlan / Option Overlay
ViewModel Contract **Accepted**. Phase 5E Cockpit UI Planning Boundary
for Existing Streamlit App **Accepted**. Phase 5F Shadow Mode Integration
Boundary Planning **Accepted**. **Phase 5G Fixture Demo Pack Based on
Original App Flow — Accepted.** Phase 5G review cleanup (no module /
runtime change) updated the Phase 5G design doc status line to
"Accepted" and reconciled the test-count wording from "322 assertions
expected" / "~322" to "344/344" (the actual count); Phase 5G test still
passes 344/344. **Phase 5H Controlled Streamlit Cockpit UI Integration
v0.1 — Implemented but had three post-implementation defects discovered
during user-facing verification on 2026-05-27: (1) runtime
`model_dump`/`model_validate` round-trip on the cached Pydantic pack
incompatible with Phase 5G's `Field(exclude=True)` on the demo pack's
`adapter` and `memory_store` fields, so every render hit the
fail-closed branch with a `ValidationError`; (2) the new page was
missing a sidebar entry because `.streamlit/config.toml` has
`showSidebarNavigation = false` and `ui_utils.render_sidebar` hand-rolls
a fully custom bilingual sidebar via `st.page_link` calls that only
enumerated `app.py` + pages 1-6; (3) every user-facing string on the
cockpit page was an English literal and the page never called
`apply_theme()` / `render_sidebar()`, so the EN ↔ ZH language toggle
had no effect on the page. **Phase 5H.1 Cockpit Page Runtime Fix +
Bilingual Surface — Implemented; Awaiting Codex Review.** Phase 5H.1
rewrites `pages/7_Investment_Cockpit.py` with a `@st.cache_resource`
loader returning the live `CockpitDemoPack` (no model_dump round-trip);
adds `apply_theme()` + `render_sidebar()` bootstrap at module top;
routes every page-chrome string through `ui_utils.t()`; adds `nav_p7`
and ~140 `cockpit_*` translation keys to both `TRANSLATIONS["en"]` and
`TRANSLATIONS["zh"]` in `ui_utils.py` (strictly additive — no existing
key renamed or removed); adds one
`st.page_link("pages/7_Investment_Cockpit.py", label=t("nav_p7"))`
line in `ui_utils.render_sidebar`; reshapes
`scripts/test_reliability_phase_5h_cockpit_ui_preview.py` Sections 5
and 6 to assert against `ui_utils.TRANSLATIONS[en]/[zh]` instead of
literal page source (Sections 6.d/e/f also assert `nav_p7` exists in
both languages and the sidebar registers the new page); adds Section
14 — `streamlit.testing.v1.AppTest`-driven render verification in EN
and ZH (no exception, every required EN tab label appears in rendered
subheaders, every required ZH tab label appears, no positive
`approved_for_execution=True` appears in any rendered element). AppTest
monkey-patches `ui_utils.render_sidebar` / `ui_utils.apply_theme` to
no-ops for the test run only (AppTest does not provide multi-page-app
context, so `st.page_link()` raises `KeyError: 'url_pathname'` inside
AppTest — known harness limitation, not a page bug); patch is restored
in a `finally` block. Phase 5H.1 test count: **226/226 passing** up
from Phase 5H's 170/170. Phase 5G regression: **344/344** unchanged.
Phase 5A regression: **175/175** unchanged. Bilingual scope: page
chrome translated; fixture content (ticker symbols `FIXTKR`/`FIXDEG`,
run IDs, fixture thesis text, JSON dumps of `DemoSafetyBanner` /
`DemoDataProvenance` / `DemoPackValidationSummary`) intentionally NOT
translated; schema-level identifiers (`approved_for_execution`,
`no_trade`, etc.) NOT translated. Files modified by Phase 5H.1:
`pages/7_Investment_Cockpit.py`, `ui_utils.py` (additive only),
`scripts/test_reliability_phase_5h_cockpit_ui_preview.py`,
`docs/reliability_phase_5h_controlled_streamlit_cockpit_ui.md`
(Section 17 count update + new Section 18). Files NOT touched: `app.py`,
`pages/1_Overview.py` … `pages/6_PriceVolume.py`,
`lib/llm_orchestrator.py`, `lib/valuation.py`, `lib/technical.py`,
`lib/rotation.py`, `lib/data_fetcher.py`, `lib/workflow_state.py`,
`lib/cache_manager.py`, `lib/reliability/integration_boundary.py`
(Phase 4A, frozen), `lib/reliability/phase5_demo_pack.py` (Phase 5G
schema unchanged — `Field(exclude=True)` preserved), `.claude/agents/*`,
existing live prompt files, `research/.workflow_state.json`,
`.streamlit/config.toml`. Invariants preserved: `approved_for_execution`
remains `False` (or absent) everywhere it appears and is never
positively authorized; `no_trade` remains a first-class option overlay
state with a populated `NoTradeReasonView` in the degraded scenario;
no live LLM / external API / broker / order routing / persistence /
DB / vector store; Phase 4A not wired in and not imported. Phase 5I
read-only shadow integration **has not started**.)

</details>

---

## Status

| Phase | Status |
|-------|--------|
| Phase 3A–3G | Accepted |
| Phase 3 Closeout | Accepted |
| Phase 4A Integration Boundary Contract | Accepted — reclassified as early infrastructure |
| Phase 3R-0 Roadmap Alignment Reconciliation | **Accepted** |
| Phase 3R-A Event Intelligence Agents Skeleton | **Accepted** |
| Phase 3R-B Trade Plan Drafting Agent Skeleton | **Accepted** |
| Phase 3R-C Allocation Agent v0.1 Non-live | **Accepted** |
| Phase 3R-D Option Expression Agent v0.1 Non-live | **Accepted** |
| Phase 3R-E Roadmap Alignment Closeout | **Accepted** |
| Phase 4M-A Research Run Memory Schema | **Accepted** |
| Phase 4M-B Thesis Memory by Horizon | **Accepted** |
| Phase 4M-C Catalyst / News / Earnings Memory | **Accepted** |
| Phase 4M-D Allocation Decision Memory | **Accepted** |
| Phase 4M-E Option Trade Plan Memory | **Accepted** |
| Phase 4M-F Human Feedback Layer | **Accepted** |
| Phase 4M-G Agent Evaluation | **Accepted** |
| Phase 4M-H Phase 4 Memory Closeout | **Accepted** |
| Phase 4 Memory mainline | **Complete** |
| Phase 5P Phase 5 Roadmap Decision / Planning | **Accepted** |
| Phase 5A Existing Workflow Memory Adapter + Fixture-backed Memory Query Contract | **Accepted** |
| Phase 5B Company Research Hub ViewModel Contract | **Accepted** |
| Phase 5C Horizon Decision Cards + ThesisTracker ViewModel Contract | **Accepted** |
| Phase 5D Portfolio / TradePlan / Option Overlay ViewModel Contract | **Accepted** |
| Phase 5E Cockpit UI Planning Boundary for Existing Streamlit App | **Accepted** |
| Phase 5F Shadow Mode Integration Boundary Planning | **Accepted** |
| Phase 5G Fixture Demo Pack Based on Original App Flow | **Accepted** (Phase 5H review-cleanup bumped doc status to "Accepted" and reconciled test-count wording to 344/344; no module/runtime change) |
| Phase 5H Controlled Streamlit Cockpit UI Integration v0.1 | **Accepted** (superseded by Phase 5H.1) |
| Phase 5H.1 Cockpit Page Runtime Fix + Bilingual Surface | **Accepted** |
| Phase 5I Investment Cockpit Product Logic Reconciliation / Opportunity-first + Horizon-aware Architecture | **Accepted** (supersedes earlier read-only shadow integration plan) |
| Phase 5J Theme Intelligence / Market Heat Schema | **Accepted** |
| Phase 5K Horizon-aware Opportunity Queue ViewModel | **Accepted** |
| Phase 5L Auto Research Pack Orchestration Boundary | **Accepted** |
| Phase 5M Agent Debate / Decision Workspace Contract | **Accepted** |
| Phase 5N Cockpit UI v0.2 Opportunity-first Redesign | **Accepted** |
| Phase 5O Macro Dashboard v0.1 | **Accepted** |
| Phase 5O.1 Macro Indicator Expansion | **Accepted** |
| Phase 5P Source Page Navigation Cleanup | **Accepted** |
| Phase 5Q Human Feedback UI v0.1 | **Accepted** (Codex verdict PASS) |
| Phase 5R UI/UX Visual Polish + Demo Readiness | **Accepted** |
| Phase 5S Phase 5 Productization Closeout | **Implemented — Awaiting Codex Review** |
| Phase 6A Live Data Integration | **Accepted** (promoted during the Phase 6B pre-task cleanup) |
| Phase 6B Stock Selection Signal Layer (v1) | **Implemented — Awaiting Codex Review** (superseded by Phase 6B v2) |
| Phase 6B v2 Dual-Track Signal Architecture | **Implemented — Awaiting Codex Review** |
| Phase 6B v3 Horizon-Native Three-Track Signal Scoring | **Implemented — Awaiting Codex Review** |
| Phase 6C-A Trading Desk | **Implemented — Awaiting Codex Review** |
| Phase 6C-A v2 Entry Strategy v3 Refactor | **Implemented — Awaiting Codex Review** (current task) |

---

## Current Task

**Phase 5S — Phase 5 Productization Closeout — Implemented; Awaiting Codex
Review.** (**Phase 5R — UI/UX Visual Polish + Demo Readiness — Accepted** as part
of this pass, per the prior review's minor suggestion. **Phase 5Q — Human
Feedback UI v0.1 — Accepted** (Codex verdict PASS). **Phase 5P — Source Page
Navigation Cleanup — Accepted** (Codex verdict PASS). **Phase 5O.1 / 5O —
Accepted.** Phase 5I / 5J / 5K / 5L / 5M / 5N — **Accepted**.)

Phase 5S is a **closeout / documentation / state / test-summary** pass. It adds
**no** new runtime feature, UI layout change, or product-logic change. It
documents the completed Phase 5 productization layer, the current UI state, the
accepted phase history, the validation matrix, the safety boundaries, the
accepted dirty-worktree provenance, and a recommended conservative Phase 6
starting point.

**Phase 5 productization closeout status:** Phase 5 is **not** formally accepted
until Codex review accepts Phase 5S. Phase 5S is **not** marked accepted in this
pass. **Phase 6A — Live Data Integration — is Implemented; Awaiting Codex
Review; Phase 6B has not started.**

**Deliverables:** `docs/ai_dev_state/PHASE_5_CLOSEOUT.md` (authoritative state /
hand-off doc), `docs/reliability_phase_5s_productization_closeout.md` (concise
technical companion), `scripts/test_reliability_phase_5s_closeout.py`, and these
state files. The prior Phase 5R minor-suggestion cleanup is performed in this
pass: PROJECT_STATE.md no longer lists Phase 5Q under "Implemented — Awaiting
Codex Review", and the stale aggregate "Phase 5L–5S Not started / Pending"
wording is corrected.

### Phase 5R (now Accepted; retained for context)

Phase 5R was a product-facing **UI/UX polish + demo-readiness** pass over the two
Phase 5 product pages. It improved the read order / visual hierarchy and added a
concise bilingual demo walkthrough so the cockpit and the macro dashboard are
easier to demo and understand — **without changing any product logic or data
contract**.

- **Demo walkthrough / "How to read this page" expander** added to both
  `pages/7_Investment_Cockpit.py` and `pages/8_Macro_Dashboard.py`, rendered
  under the page title/subtitle and above the tab strip (via a small
  `_render_demo_walkthrough()` helper using `st.expander` + `st.markdown` +
  `st.caption` + `st.info`). It explains fixture-only data, the opportunity-first
  (cockpit) / macro-first (macro) read order, the review-only nature, and that
  nothing executes or is persisted. No onboarding/persistence system is added —
  the copy is static and lives only in `TRANSLATIONS`.
- **Visual hierarchy / cross-page consistency:** the walkthrough lays out the
  intended tab read order (cockpit: Market Themes → Opportunity Queue → Research
  Pack → Agent Debate → Decision Workspace → Review; macro: Macro Regime →
  Indicators → Horizon Bias → Theme Implications → Opportunity Posture) and uses
  coherent terminology across both pages (opportunity-first, horizon-aware,
  fixture/demo only, review-only, non-executable). Phase 5P sidebar labels are
  unchanged.
- **Safety banners preserved + reinforced:** the cockpit opportunity-first
  safety banner, the Phase 5D execution-safety banner, and the Phase 5Q
  session-only feedback banner remain; the macro safety banner and the
  "posture is not a decision" boundary remain. The walkthrough adds one concise
  per-page safety summary line (`*_walkthrough_safety`).
- **Card / table / metric presentation:** unchanged — continues to use the
  existing Streamlit-native containers / columns / metrics / captions /
  expanders / tables and the project-standard `apply_theme()` styling; no heavy
  custom CSS. Existing values, column names, and model meanings preserved.
- **Empty / degraded states:** unchanged — degraded fixture scenario, missing
  macro indicators/factors, missing evidence, `research_more`, `no_trade`, and
  unresolved conflicts render through their existing safe view-model paths.
- **Bilingual:** all new chrome routes through `ui_utils.t()`; additive EN/ZH
  `cockpit_walkthrough_*` (9 keys) and `macro_walkthrough_*` (8 keys) added to
  both `TRANSLATIONS["en"]` and `TRANSLATIONS["zh"]` (no existing key
  renamed/removed). Fixture IDs / tickers / enum-schema values / run IDs / JSON
  keys remain untranslated.

**Deliverables:** `pages/7_Investment_Cockpit.py`,
`pages/8_Macro_Dashboard.py`, `ui_utils.py` (additive EN/ZH
`cockpit_walkthrough_*` / `macro_walkthrough_*` keys),
`scripts/test_reliability_phase_5r_ui_ux_polish.py` (324/324),
`docs/reliability_phase_5r_ui_ux_visual_polish_demo_readiness.md`, and these
state files.

**Guardrails honored:** UI/UX polish + demo readiness only; **no change** to
investment logic, scoring logic, schema meaning, agent contracts, queue logic,
research-pack logic, debate logic, feedback semantics, or macro-regime
interpretation; every Phase 5N / 5O tab key, EN/ZH label, and ordering
preserved; no live workflow behavior change; no LLM; no yfinance / Finnhub /
FRED / CNN / news / external API; no DB / vector store / persistence; no real
onboarding/persistence system; no `research/.workflow_state.json` read/write;
no broker / order / execution; no order tickets / broker payloads / account IDs
/ order fields / execution IDs / executable trade instructions; no
buy/sell/order instruction; `approved_for_execution` remains False or absent
(never positively authorized); `app.py`, pages 1–6,
`lib/llm_orchestrator.py`, `lib/workflow_state.py`, `.claude/agents/*`
untouched; Phase 4A not wired in.

**Phase 5R acceptance performed in this pass:** state files now mark **Phase 5R
Accepted** and the stale Phase 5Q "Implemented — Awaiting Codex Review" /
"Phase 5L–5S Not started" aggregate wording in `PROJECT_STATE.md` is corrected
(documentation / state wording only — no module / runtime / test change).

**Next required step:** Codex review of Phase 5S. **Phase 5S is not yet
accepted, and Phase 5 is not formally accepted until Phase 5S is accepted.**
After Phase 5S is accepted, the next recommended phase was **Phase 6A — Live
Data Integration**, which is now **Implemented; Awaiting Codex Review**.
**Phase 6A is Implemented; Awaiting Codex Review; Phase 6B has not started.**

---

### Historical — Phase 5O.1 (Accepted; retained for context)

**Phase 5O.1 — Macro Indicator Expansion — Accepted.**

Phase 5O.1 is a small **additive enhancement** on top of accepted Phase 5O. It
extends the existing macro dashboard schema, fixtures, page, tests, and doc to
explicitly model concrete, user-requested macro instruments and economic-release
indicators in a fixture-only **indicator panel**:

- **Commodities**: WTI crude oil, GC / gold.
- **Risk appetite / leadership**: CNN Fear & Greed Index, QQQ, IWM.
- **Economic releases**: NFP / Nonfarm Payrolls, CPI, PPI.

It remains **fixture-backed / offline / mock-only / review-only**: it retrieves
no live macro data, imports/calls no yfinance / Finnhub / FRED / CNN / news /
external API, calls no LLM, introduces no DB / vector store / persistence and no
broker / order / execution path, and produces **no final buy/sell decision**.

**Schema:** new `MacroIndicatorView` (base) → `MacroInstrumentSignalView` →
`CommoditySignalView` / `IndexRiskAppetiteSignalView`; `RiskSentimentSignalView`;
`MacroEconomicReleaseView` → `LaborMarketSignalView` / `InflationReleaseSignalView`;
plus `MacroIndicatorPanel`, Literal aliases (`MacroIndicatorKey`,
`MacroIndicatorCategory`, `CommodityType`, `IndexLeadershipRole`, `FearGreedZone`,
`EconomicReleaseSurprise`, `LaborMarketStrength`, `InflationPipelineStage`),
`REQUIRED_MACRO_INDICATOR_KEYS`, and helpers `make_macro_indicator_id` /
`collect_panel_indicators`. Each indicator carries `indicator_id`,
`display_name`, `category`, `latest_value`/`fixture_value`, `trend`, `status`,
`signal`, `interpretation`, `macro_implication`, `horizon_implication`,
`source_type="fixture"`, `is_live_data=False`, and `warnings`.
`MacroDashboardView` gains an `indicator_panel`; the validation summary gains
indicator metrics (count, has_all_required_indicators, missing_indicators,
per-group counts, all_indicators_fixture_only).

**Fixtures:** risk-on (greed/crowding caution, leading QQQ + broadening IWM,
disinflation CPI/PPI, resilient NFP), risk-off (fear, weak QQQ/IWM, gold haven
bid + weak oil, sticky CPI/PPI, cooling NFP), transition (mixed/unconfirmed),
degraded (a few unknown indicators with warnings; the rest surfaced as
`missing_indicators` — nothing fabricated).

**Page:** `pages/8_Macro_Dashboard.py` adds a **Macro Indicators** tab
(`macro_tab_indicators`) between Macro Regime and Liquidity, with three labelled
subsections (commodities; risk appetite / leadership; economic releases). All
new chrome routes through `ui_utils.t()` with additive EN/ZH `macro_*` keys; the
section caption states the fixture/demo, non-live nature.

**Deliverables (allowed files only):**
`lib/reliability/phase5_macro_dashboard.py` (indicator models + panel + 4 scenario
panel builders + validation), `pages/8_Macro_Dashboard.py` (Macro Indicators
tab), `ui_utils.py` (additive EN/ZH indicator chrome keys), additive Phase 5O.1
exports in `lib/reliability/__init__.py`,
`scripts/test_reliability_phase_5o_macro_dashboard.py` (766/766; Section 16 +
expanded Sections 6/7/11/15), `docs/reliability_phase_5o_macro_dashboard_v01.md`
(Phase 5O.1 — Macro Indicator Expansion section).

**Invariants:** every indicator model sets `extra="forbid"` and declares no
`approved_for_execution` field (absent, never positively authorized); every
indicator is fixture-only (`is_live_data=False`, `source_type="fixture"`); no
order-ticket / broker-route / account-id / time-in-force / execution-id /
quantity-to-execute / broker-payload fields; no buy/sell/order instruction.
Future live indicator integration (price feeds, the CNN value, FRED/BLS
releases) is deferred to a later controlled phase.

**Phase 5O acceptance performed in this pass:** Phase 5O is marked **Accepted**
in both state files (Codex verdict PASS, no required fixes, no blocking minor
suggestions). The historical Phase 5O narrative is retained in the
**Historical — Phase 5O** subsection below.

---

### Historical — Phase 5O (Accepted; retained for context)

**Phase 5O — Macro Dashboard v0.1 — Accepted** (Codex verdict PASS). Phase 5O
created the macro dashboard framework and broad macro **factor** taxonomy:
`lib/reliability/phase5_macro_dashboard.py` (regime view-models + deterministic
risk_on/risk_off/transition/degraded fixtures + validation summary) and the
additive fixture-only `pages/8_Macro_Dashboard.py` (Overview/Safety, Macro
Regime, Liquidity/Rates/Inflation, Credit/Volatility/Breadth, Risk Appetite,
Horizon Bias, Theme Implications, Opportunity Posture, Provenance/Diagnostics)
registered via `nav_p8`. Fixture-only / offline / review-only; no live macro
data / LLM / external API / broker / order / execution; produces no final
buy/sell decision; `approved_for_execution` absent by construction. Phase 5O.1
(this pass) extends it with concrete macro indicators. Phase 5O test at
acceptance: 601/601.

### Historical — Phase 5N (Accepted; retained for context)

**Phase 5N — Cockpit UI v0.2 Opportunity-first Redesign — Accepted.**

Phase 5N is a **product-facing Streamlit UI update to
`pages/7_Investment_Cockpit.py` only** (plus additive `ui_utils.py` EN/ZH
chrome keys, a new test, an updated test, and a design doc). It redesigns the
additive Investment Cockpit page from the company/ticker-first Phase 5H/5H.1
layout into an **opportunity-first, macro/theme-aware, horizon-aware**
decision cockpit with ten v0.2 tabs:

```
Overview / Safety
Market Themes          (Phase 5J Theme Intelligence / Market Heat)
Opportunity Queue      (Phase 5K Horizon-aware Opportunity Queue)
Decision Workspace     (Phase 5M Decision Workspace review state)
Research Snapshot      (Phase 5B Company Research Hub, repositioned;
                        + Phase 5C thesis + Phase 5L pack coverage)
Agent Debate           (Phase 5M bull/bear/risk/critic/alloc/option)
Trade / Allocation Plan(Phase 5D portfolio / trade plan, review-only)
Option Overlay         (Phase 5D option overlay; no_trade first-class)
Feedback / Review      (Phase 4M-F / 4M-G fixture summaries)
Provenance / Diagnostics (Phase 5G + 5J/5K/5L/5M validation summaries)
```

Market Themes and Opportunity Queue appear **before** Research Snapshot;
Company Research Hub is repositioned as the **Research Snapshot** tab and is
no longer wired as a primary tab (the old `cockpit_tab_company` /
`cockpit_tab_horizon` / `cockpit_tab_thesis` / `cockpit_tab_portfolio` /
`cockpit_tab_feedback` keys remain defined in `ui_utils.TRANSLATIONS` under
the additive policy). The Phase 5G demo pack does not bundle Phase 5J–5M
artifacts, so the page calls the deterministic Phase 5J–5M fixture builders
directly (permitted by the Phase 5N boundary); the scenario selector maps
`complete` → default fixtures and `degraded` → degraded fixtures, while
Market Themes always use the default theme snapshot (AI + Space + degraded
theme).

**Fixture-only / offline / review-only.** The page calls no LLM, external
API, broker, or order router; does not read `research/.workflow_state.json`;
does not import `lib/workflow_state.py` or `lib/llm_orchestrator.py`; writes
nothing; introduces no DB / vector store / persistence; and fails closed on
builder error with no LLM/API fallback. `approved_for_execution` is `False`
(or absent) everywhere and is never positively authorized. `no_trade` remains
a first-class option-overlay / decision state. No order-ticket / broker-route
/ account-id / time-in-force / execution-id / quantity-to-execute /
broker-payload fields are shown; the Trade tab carries an explicit
"Review-only planning view — not an order ticket." boundary statement. No
final buy/sell/order instruction is produced. Phase 4A is not wired in.

**Deliverables:** `pages/7_Investment_Cockpit.py` (rewritten), `ui_utils.py`
(additive EN/ZH `cockpit_*` v0.2 keys + v0.2 page title/subtitle),
`scripts/test_reliability_phase_5n_cockpit_ui_v02.py` (683/683), reconciled
`scripts/test_reliability_phase_5h_cockpit_ui_preview.py` (235/235; tab
mapping + view-reference assertions updated to v0.2),
`docs/reliability_phase_5n_cockpit_ui_v02_opportunity_first_redesign.md`.

**Phase 5M acceptance cleanup performed in this pass:** state files now mark
**Phase 5M Accepted** and reconcile the stale Phase 5L "Implemented; Awaiting
Codex Review" wording in `PROJECT_STATE.md` to "Accepted" (documentation /
state wording only — no Phase 5L / 5M module / runtime / test change).

**Phase 5N bilingual re-fix (post first Codex review — verdict FAIL):** the
first review passed scope, product logic, data dependency, UI structure,
safety, docs, state, guardrails, and validation, but FAILED on a narrow
blocking issue — several visible Trade / Allocation labels (around
`pages/7_Investment_Cockpit.py` lines ~811–825) remained English literals
instead of routing through `t()`. Fixed in this pass:

- The Trade / Allocation execution-safety banner flag labels, the risk-budget
  metric labels (`Max risk budget %`, `Max portfolio loss %`,
  `High / medium / low / unknown risk counts`), the cash-impact metric labels
  (`Total cash impact`, `Min projected cash %`, `Max projected cash %`), the
  positions table column headers (`target`, `horizon`, `action`, `status`,
  `target_alloc_pct`, `actual_alloc_pct`, `review_needed`), and the trade-plan
  level table column headers (`kind`, `label`, `pct`, `value`, `note`) now all
  route through `ui_utils.t()`.
- Added 20 additive EN/ZH `cockpit_trade_*` keys to `ui_utils.TRANSLATIONS`
  (`cockpit_trade_non_executable`, `cockpit_trade_requires_review`,
  `cockpit_trade_max_risk_budget`, `cockpit_trade_max_portfolio_loss`,
  `cockpit_trade_risk_counts`, `cockpit_trade_total_cash_impact`,
  `cockpit_trade_min_cash`, `cockpit_trade_max_cash`, and the
  `cockpit_trade_col_*` column-header keys).
- Added `scripts/test_reliability_phase_5n_cockpit_ui_v02.py` Section 16 — a
  **static inactive-tab chrome scan**: it asserts the known English Trade /
  Allocation chrome literals are absent from the page source, that the
  Trade-slice source does not hardcode raw table column-key chrome or
  `field=value` banner flag labels, and that the new `cockpit_trade_*` keys
  exist in both EN and ZH and are referenced by the page. This catches
  untranslated chrome in any tab regardless of which tab AppTest renders as
  open (AppTest tab-label checks alone missed it). The raw
  `is_executable_*=` / `requires_human_review=` schema-flag form remains
  intentionally visible as non-executability evidence in the Decision
  Workspace / Agent Debate tabs and is scoped out of the Trade-slice check.
- Phase 5N test now **683/683** (up from 604/604); EN/ZH AppTest render
  coverage preserved; safety tests not weakened. Files changed:
  `pages/7_Investment_Cockpit.py`, `ui_utils.py` (additive),
  `scripts/test_reliability_phase_5n_cockpit_ui_v02.py`, and these state files.

---

### Historical — Phase 5M (Accepted; retained for context)

**Phase 5M — Agent Debate / Decision Workspace Contract — Accepted.**

Phase 5M is **schema / helper / view-model / fixture only** (offline /
mock-only). It defines the deterministic contracts for structuring agent
debate and decision-workspace review **after** a Phase 5L research pack has
been assembled:

```
Phase 5K Opportunity Candidate
  -> Phase 5L Research Pack (ResearchPackBundle / boundary)
  -> Phase 5M Agent Debate / Decision Workspace   (this phase)
  -> (future) Phase 5N Cockpit UI v0.2
```

It defines the **contract only**. It does **not** run any real agent, call
any LLM / external API, fetch live data, persist anything, or produce an
executable trade / allocation / option decision. Agent participants are
deterministic role records (`is_live_agent=False`); stance records carry
`is_live_agent_output=False`.

**Agent Debate / Decision Workspace Contract implementation status:**

- New module `lib/reliability/phase5_agent_debate.py` defines the Pydantic
  contracts: `AgentDebateWorkspace`, `AgentDebateSession`, `AgentDebateRound`,
  `AgentDebateParticipant`, `AgentStanceRecord`, `BullCaseView`,
  `BearCaseView`, `RiskCaseView`, `CriticReviewView`,
  `AllocationPerspectiveView`, `OptionPerspectiveView`, `DebateConflictRecord`,
  `DebateConsensusSummary`, `DebateEvidenceCoverage`, `DebateWarning`,
  `DecisionWorkspaceView`, `DecisionWorkspaceRecommendationState`,
  `DecisionWorkspaceNextAction`, `DecisionWorkspaceSafetyBanner`,
  `DecisionWorkspaceValidationSummary`, plus Literal aliases (`AgentRole`,
  `BullStanceLabel`, `BearStanceLabel`, `RiskStanceLabel`, `CriticStanceLabel`,
  `AllocationStanceLabel`, `OptionStanceLabel`, `AgentStanceLabel`,
  `DebateConflictType`, `DebateConsensusLevel`, `DecisionWorkspaceStatus`,
  `DecisionWorkspaceNextActionType`, `DebateWarningType`, `DebateConfidence`)
  and deterministic builders (`build_agent_debate_workspace`,
  `build_debate_session_from_research_pack`, `build_bull_case_view`,
  `build_bear_case_view`, `build_risk_case_view`, `build_critic_review_view`,
  `build_allocation_perspective_view`, `build_option_perspective_view`,
  `build_debate_conflicts`, `build_debate_consensus_summary`,
  `build_debate_evidence_coverage`, `build_decision_workspace_view`,
  `build_decision_workspace_recommendation_state`,
  `build_decision_workspace_validation_summary`, `build_default_participants`).
- Seven deterministic participant roles — `bull`, `bear`, `risk`, `critic`,
  `allocation`, `option`, `synthesis` — are **role records only; no live agent
  is run**. Bull/bear/risk/critic perspectives are separated; allocation and
  option are **review-only planning** perspectives
  (`is_executable_allocation=False`, `is_executable_order=False`; `no_trade`
  first-class).
- Disagreements surface as explicit `DebateConflictRecord`s (bull/bear
  disagreement, risk override) and are never hidden; the critic acknowledges
  every unresolved conflict (`hides_unresolved_conflict=False`). Risk can
  downgrade the workspace state to `wait_for_pullback` / `research_more`.
  Missing evidence → `research_more` / `insufficient_evidence` / `no_decision`;
  degraded pack → `blocked` / `research_more` with `degraded_upstream`
  warnings (no fabricated analysis); empty pack → safe empty workspace.
  Consensus levels: `strong_consensus`, `moderate_consensus`, `mixed`,
  `conflict_unresolved`, `insufficient_evidence`. Decision-workspace next
  actions are review-only (`review`, `research_more`, `wait_for_pullback`,
  `watch`, `skip`, `no_trade`, `escalate_to_human`).
- Deterministic fixtures: `build_default_agent_debate_workspace()` (from the
  Phase 5L default research pack bundle), `build_degraded_agent_debate_workspace()`,
  `build_empty_agent_debate_workspace()`, `build_conflict_agent_debate_session()`
  (bull constructive while bear/risk flag overextension/crowding),
  `build_no_trade_option_agent_debate_session()`, and
  `build_research_more_agent_debate_session()`. Serialization is deterministic.

**Deliverables:**
`lib/reliability/phase5_agent_debate.py`,
`scripts/test_reliability_phase_5m_agent_debate_workspace.py`
(263 assertions),
`docs/reliability_phase_5m_agent_debate_decision_workspace.md`, and
additive Phase 5M exports in `lib/reliability/__init__.py`.

**Phase 5L acceptance cleanup performed in this pass:** State files now mark
**Phase 5L Accepted** and **Phase 5M Implemented; Awaiting Codex Review**. No
Phase 5L module / runtime / test behavior change.

**Guardrails honored:** no live wiring; no real agent runtime; no
Claude/OpenAI/LLM call; no external API; no DB / vector store / production
persistence; no broker / order / execution; no executable order fields; no
Auto Research runtime; no Macro Dashboard; no UI redesign; no sidebar
cleanup; no read-only shadow integration; no final buy/sell recommendation;
no order instructions; `approved_for_execution` absent on every Phase 5M
model and never positively authorized (every model `extra="forbid"`);
`app.py`, pages 1–7, `ui_utils.py`, `lib/llm_orchestrator.py`,
`lib/workflow_state.py`, `.claude/agents/*` untouched; Phase 4A not wired in.

**Next required step**: Codex review of Phase 5M. **Phase 5M is not yet
accepted.** After Phase 5M is accepted, the next recommended phase is
**Phase 5N — Cockpit UI v0.2 Opportunity-first Redesign**. **Phase 5N has
not started.**

---

## What Was Done (Phase 5H) — historical (Accepted; retained for context)

### New Streamlit page — Phase 5H Investment Cockpit demo preview

- `pages/7_Investment_Cockpit.py` adds a new Streamlit page that:
  - Loads the Phase 5G demo pack via
    `lib.reliability.phase5_demo_pack.build_default_cockpit_demo_pack()`.
  - Caches the JSON dump of the built pack with
    `@st.cache_data(show_spinner=False)` and rebuilds the Pydantic
    pack from that dump on each render (deterministic + free of
    unhashable internals — the Phase 5G
    `InMemoryWorkflowToMemoryAdapter` and
    `FixtureBackedMemoryStore` are intentionally excluded from JSON
    serialization on their Pydantic models).
  - Exposes a sidebar scenario selector defaulting to the complete
    scenario (`FIXTKR`) and offering the degraded scenario
    (`FIXDEG`).
  - Renders eight tabs:
    1. **Overview / Safety** — top-of-tab safety banner (`Fixture/
       demo only`, `No live workflow wiring`, `No external API`,
       `No orders`, `approved_for_execution is False`, `Not
       investment advice`) + pack-level and scenario-level
       `DemoSafetyBanner` JSON dumps + scenario identity (kind,
       ticker, run_id, description) + scenario warnings.
    2. **Company Research Hub** — Phase 5B `CompanyResearchHubView`
       identity + Equity / Financial / Price-Volume panels +
       Source-workflow panel + Evidence coverage panel +
       Validation status panel + `MissingDataWarningView`. The
       degraded scenario surfaces `financial_panel.is_populated=
       False`, the `missing_data.missing_panels` list, and a clear
       error block stating that no analysis is regenerated.
    3. **Horizon Cards** — Phase 5C `HorizonDecisionCardsView`
       rendered as three columns in canonical
       `short → medium → long` order. Each card shows status,
       thesis direction / confidence / text, assumptions,
       invalidation triggers, review-needed badge, missing-
       evidence badge, and the descriptive next-action label. The
       degraded scenario's long-horizon card surfaces as
       `status="missing"` / `is_populated=False` with warnings.
    4. **ThesisTracker** — Phase 5C `ThesisTrackerView` rendered as
       a deterministic table by `(target, horizon)`.
    5. **Portfolio / TradePlan** — Phase 5D `PortfolioCockpitView`
       with `ExecutionSafetyBannerView`, allocation summary, risk
       budget aggregate, cash impact aggregate, positions table,
       and per-trade-plan level tables (`entry / add / trim /
       stop / target / review`). No order tickets, broker routes,
       account IDs, time-in-force values, executable quantities,
       or broker payloads are displayed.
    6. **Option Overlay** — Phase 5D `OptionOverlayView` rendered
       per record. `no_trade` is shown as a first-class state
       with a populated `NoTradeReasonView`. Other states show
       `OptionStrategySummaryView` + `OptionRiskRewardView` +
       liquidity / event-risk warnings.
    7. **Feedback / Agent Evaluation** — fixture-backed Phase
       4M-F human feedback and Phase 4M-G agent evaluation
       summaries when present.
    8. **Provenance / Diagnostics** — pack-level + scenario-level
       `DemoDataProvenance` JSON dumps + Phase 5G
       `DemoPackValidationSummary` + source fixture name + an
       explicit note that this is not live workflow output.
  - Fails closed: if the demo-pack builder raises, the page
    displays an error block and does not attempt any LLM / API
    fallback.

### New design document

- `docs/reliability_phase_5h_controlled_streamlit_cockpit_ui.md`
  covering:
  - Purpose.
  - Relationship to Roadmap v4 Phase 5 Investment Cockpit.
  - Relationship to the original README Streamlit app.
  - Relationship to Phase 5E Cockpit UI Planning Boundary.
  - Relationship to Phase 5F Shadow Mode Integration Boundary
    Planning.
  - Relationship to Phase 5G Fixture Demo Pack.
  - Page created and why it is additive.
  - Existing pages preserved (assertion list).
  - Fixture-only data flow (diagram).
  - UI sections / tabs (8 tabs).
  - Safety banner semantics (top-of-tab + Phase 5G banner + Phase
    5D execution banner).
  - Degraded scenario behavior (missing financial panel + missing
    long-horizon card + `no_trade` overlay).
  - Non-goals.
  - Guardrails (forbidden existing files,
    `approved_for_execution` invariant, `no_trade` invariant, no
    executable order fields, fail-closed behavior).
  - Forbidden existing files (full enumeration).
  - Acceptance criteria.
  - Future Phase 5I dependency.
  - Validation.

### New test

- `scripts/test_reliability_phase_5h_cockpit_ui_preview.py` covers
  170 assertions across 13 sections:
  1. Page existence + forbidden live-runtime path existence +
     existing pages do not contain Phase 5H marker strings.
  2. Page source parses as valid Python; page imports Streamlit.
  3. Page imports `lib.reliability.phase5_demo_pack` and the Phase
     5B / 5C / 5D view contracts; page does NOT import live
     workflow / LLM / data-fetcher / Phase 4A / Anthropic / OpenAI;
     page does NOT read `research/.workflow_state.json` via any
     file-open pattern.
  4. Page does NOT contain external API / broker / order routing
     call sites.
  5. Required safety banner phrases (`Fixture/demo only`, `No live
     workflow wiring`, `No external API`, `No orders`,
     `approved_for_execution`, `Not investment advice`) present.
  6. Required eight section / tab labels (Overview / Safety,
     Company Research Hub, Horizon Cards, ThesisTracker, Portfolio
     / TradePlan, Option Overlay, Feedback / Agent Evaluation,
     Provenance / Diagnostics) present.
  7. No order-ticket-like field names or labels.
  8. No positive `approved_for_execution=True` authorization.
  9. Phase 5G demo pack still builds with
     `all_approved_for_execution_false=True`,
     `no_executable_order_fields=True`, and no validation errors.
  10. Phase 5H design doc exists and contains every required
      heading.
  11. Phase 5G test file still exists.
  12. No persistence / DB / vector store / file-open patterns.
  13. Fail-closed branch present; no LLM/API fallback path.

### Constraints honored

- **No existing live runtime files modified.** `app.py`,
  `pages/1_Overview.py` … `pages/6_PriceVolume.py`,
  `lib/llm_orchestrator.py`, `lib/valuation.py`, `lib/technical.py`,
  `lib/rotation.py`, `lib/data_fetcher.py`, `lib/workflow_state.py`,
  `lib/cache_manager.py`, `.claude/agents/*`, and
  `lib/reliability/integration_boundary.py` (Phase 4A, frozen) all
  untouched.
- **One additive Streamlit page added**
  (`pages/7_Investment_Cockpit.py`).
- **No live wiring introduced.**
- **No DB / vector store / file persistence introduced.**
- **No external API call introduced** (no Anthropic SDK, no
  OpenAI SDK, no HTTP client, no data-fetcher call).
- **No broker / order / trade execution path introduced.**
- **No executable order fields or labels introduced.**
- **No prompt / model / agent-definition mutation.**
- **Phase 4A not wired into live app and not imported by Phase
  5H.**
- `approved_for_execution` remains `False` (or absent) everywhere
  it appears and is never positively authorized.
- `no_trade` preserved as first-class option overlay state with no
  inferred substitute strategy.
- `research/.workflow_state.json` is **not** read by Phase 5H.

---

## Validation Run

Phase 5S targeted validation set (run with `python3 -B`):

```bash
git status --short
python3 -B scripts/test_reliability_phase_5s_closeout.py
python3 -B scripts/test_reliability_phase_5r_ui_ux_polish.py
python3 -B scripts/test_reliability_phase_5q_human_feedback_ui.py
python3 -B scripts/test_reliability_phase_5n_cockpit_ui_v02.py
python3 -B scripts/test_reliability_phase_5o_macro_dashboard.py
```

Results:

- `git status --short`: targeted forbidden live-runtime path checks can be
  clean while unrelated dirty / untracked worktree items may exist. None of
  `app.py`, `pages/1_Overview.py` … `pages/6_PriceVolume.py`,
  `lib/llm_orchestrator.py`, `lib/valuation.py`, `lib/technical.py`,
  `lib/rotation.py`, `lib/data_fetcher.py`, `lib/workflow_state.py`,
  `lib/cache_manager.py`, `.claude/agents/*`, or
  `lib/reliability/integration_boundary.py` was modified by Phase 5S. Phase 5S
  is closeout / documentation / state / test-summary only; it touched only:
  `docs/ai_dev_state/PHASE_5_CLOSEOUT.md` (new),
  `docs/reliability_phase_5s_productization_closeout.md` (new),
  `scripts/test_reliability_phase_5s_closeout.py` (new), and these state files.
  No live runtime file, no page, and no `lib/reliability/` module was modified
  by Phase 5S.
- `scripts/test_reliability_phase_5s_closeout.py`:
  **PASS** (see final response for the run count).
- `scripts/test_reliability_phase_5r_ui_ux_polish.py` (regression):
  **324 passed, 0 failed**.
- `scripts/test_reliability_phase_5q_human_feedback_ui.py` (regression):
  **389 passed, 0 failed**.
- `scripts/test_reliability_phase_5n_cockpit_ui_v02.py` (regression):
  **683 passed, 0 failed**.
- `scripts/test_reliability_phase_5o_macro_dashboard.py` (regression):
  **766 passed, 0 failed**.

---

## Next Action

**Phase 5S — Phase 5 Productization Closeout — Implemented; Awaiting Codex
Review.** (Phase 5R — UI/UX Visual Polish + Demo Readiness — **Accepted** in this
pass. Phase 5Q — Human Feedback UI v0.1 — **Accepted**, Codex verdict PASS.
Phase 5P — Source Page Navigation Cleanup — **Accepted**, Codex verdict PASS.
Phase 5O.1 / 5O — **Accepted**. Phase 5I / 5J / 5K / 5L / 5M / 5N — **Accepted**.)

Codex should review:

1. `docs/ai_dev_state/PHASE_5_CLOSEOUT.md` — the authoritative state / hand-off
   closeout document. Verify it contains the required sections (closeout status;
   original README app baseline; Phase 5 productization summary; current product
   UI state; safety / guardrail status; accepted dirty-worktree provenance;
   validation matrix; non-goals / deferred work; recommended Phase 6 direction;
   session-migration hand-off), that it marks Phase 5R accepted and Phase 5S
   awaiting review without marking Phase 5S accepted, and that it does not claim
   any Phase 6 work has begun.
2. `docs/reliability_phase_5s_productization_closeout.md` — the concise technical
   companion. Verify Purpose; what Phase 5 changed / did not change; product
   architecture after Phase 5; fixture-only vs live boundaries; UI pages after
   Phase 5; validation summary; next-phase recommendation; guardrails; acceptance
   criteria.
3. `scripts/test_reliability_phase_5s_closeout.py` — verify the coverage: both
   closeout docs exist with required sections; state files mark Phase 5R accepted
   and Phase 5S awaiting review; Phase 5S is not marked accepted; Phase 6 is not
   started; no positive `approved_for_execution` authorization in the closeout
   docs; guardrail language present; sidebar structure documented; macro
   indicators (WTI, Gold/GC, CNN Fear & Greed, QQQ, IWM, NFP, CPI, PPI) listed;
   the confirmed Phase 5R/5Q/5N/5O/5M/5L/5K/5J validation counts present; Phase 6A
   recommendation present.
4. The Phase 5R → Accepted / Phase 5S → Implemented; Awaiting Codex Review
   state-file updates in `docs/ai_dev_state/PROJECT_STATE.md` and
   `docs/ai_dev_state/CURRENT_TASK.md`, including the Phase 5R minor-suggestion
   cleanup (Phase 5Q no longer under "Implemented — Awaiting Codex Review"; stale
   "Phase 5L–5S Not started / Pending" aggregate wording corrected).

After Phase 5S is accepted, **Phase 5 is formally complete**, and the next
recommended phase is:

**Phase 6A — Phase 6 Planning / Real Integration Boundary Decision** — a
conservative planning / contract-only phase deciding whether the first
real-integration step is a Real Portfolio / Brokerage Import Contract or a Live
Data Integration Boundary Planning effort. **Phase 6A — Live Data Integration —
is now Implemented; Awaiting Codex Review** (it must not be marked accepted until
Codex accepts it). **Phase 6B has not started.**

---

## Forbidden Files

Do **not** modify:

- `app.py`
- `pages/1_Overview.py`
- `pages/2_Sector.py`
- `pages/3_Scanner.py`
- `pages/4_Equity.py`
- `pages/5_Financial.py`
- `pages/6_PriceVolume.py`
- `lib/llm_orchestrator.py`
- `lib/valuation.py`
- `lib/technical.py`
- `lib/rotation.py`
- `lib/data_fetcher.py`
- `lib/workflow_state.py`
- `lib/cache_manager.py` *(read-only conceptually; not modified during Phase 5 implementation)*
- `lib/reliability/integration_boundary.py` *(frozen Phase 4A; not modified)*
- `.claude/agents/*`
- Existing live prompt files
- Existing Streamlit UI behavior on pages 1–6
- Existing news / Finnhub / data-fetch behavior
- Existing live workflow behavior
- `research/.workflow_state.json`
