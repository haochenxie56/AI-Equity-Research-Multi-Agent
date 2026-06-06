# AI Investment Agent — Project State

**Last updated**: 2026-06-05 (**Phase 7B — Rotation & Internals — Implemented** —
see the section immediately below; Valuation Stop-the-Bleed and Phase 7A sections
follow. Prior status blob preserved verbatim afterward.)

## Phase 7B — Multi-window RS, Two-Ring Rotation, Market-Internals Fragility — Implemented (CURRENT TASK)

Makes rotation VISIBLE and market deterioration EARLY-VISIBLE. **All deterministic;
no LLM.** Phase doc `docs/reliability_phase_7b_rotation_internals.md`; suite
`scripts/test_reliability_phase_7b_rotation_internals.py` **122/122** (mock-only,
incl. Codex fix round + polish 1: same-date adjacency, volume-shrink flag, AST
guard, clock-drift; + polish 2: always render fragility at normal, LONG why_now
fix, theme excess-3M label; + polish 3: banner zero/null three-state, earnings
reactions WIRED via one bulk Finnhub earnings-calendar call with distinct degrade
reasons (finnhub_unavailable / no_reports_in_window / earnings_source_absent),
volume monitor now watches leading ∪ rotating_out (was excluding the distributing
ex-leader)). Full canonical set green: 7A 115, stopbleed 64, 6c_b
47, equity_render_order 50, 6c_trading_desk 118, 6c_v3_entry_v4 47,
6b_v3_horizon_scoring 189, theme_baskets 146, scanner_rotation_adapter 15.

**Fix round (Codex, 2 should-fix correctness):** (1) **Hysteresis adjacency via the
benchmark trading calendar** — `is_adjacent_session(d1,d2,benchmark_index)` (the
cached SPY→QQQ date index IS the trading calendar; no new dep/network) is true iff
no trading date lies strictly between the snapshot dates; `apply_hysteresis(...,
benchmark_index=)` breaks the chain on a non-adjacent pair (gap only DELAYS
escalation). Index can't cover the dates → falls back to
`hysteresis_max_calendar_gap_days=4` and flags `adjacency_degraded`. De-escalation
immediate. (2) **RS date-aligned excess** — `benchmark_frames` keeps dated Close Series;
`compute_relative_strength(..., bench_closes=)` inner-joins ticker∩bench on dates
before windowing (sufficiency on the aligned length); positional/fixture path
unchanged (7A byte-compat). History before 7B archived to
`docs/ai_dev_state/archive/CURRENT_TASK_pre_7b_20260605.md`.

**Task 1 — Multi-window RS** (`lib/relative_strength.py`): excess returns vs
SPY/QQQ over `RS_WINDOWS` (5d/10d/1m/3m/6m/12m); per-horizon composites
`rs_short`(5D/10D) / `rs_mid`(1M/3M) / `rs_long`(6M/12M) via
`compute_horizon_composites`; `composite_for(horizon)` falls back to the
unchanged legacy `rs_composite` (7A byte-identical). 12M→6M degrade sets
`rs_window_degraded`. Benchmarks fetch `2y` (single fetch). Ranker consumes the
per-horizon composite (`_horizon_rs_comp`, fallback-safe); `build_reason_codes(...,
horizon=)` makes the why_now RS line follow the selected horizon (5日/近1月/近6月);
cards carry `why_now_by_horizon`; full `windows` set persisted in the snapshot.

**Task 2 — Two-Ring Rotation**: OUTER (`lib/rotation.py`) —
`offense_defense_reading(sector_excess)` (pure) + `build_sector_excess(loader)`
(injectable, cache-only capable) + `compute_offense_defense()`; OFFENSE = IT /
Discretionary / Communication / Semis, DEFENSE = Utilities / Staples / Health
Care; direction+magnitude+confirming windows; **existing `compute_sector_scores`
score contract untouched**. INNER (`lib/theme_baskets.py`) —
`compute_theme_momentum` now EXCESS vs QQQ (per-theme `benchmark` overridable)
over the window set; `classify_divergence(5D,1M)` → stage
(rotating_in/leading/rotating_out/out_of_favor, boundary on the weak side);
`compute_theme_breadth` (% beating bench + % > SMA20) with direction-aware
confirmation (single-stock guard); `compute_all_themes(regime=)` macro-lens
default window (display only); `momentum_score` rebased to EXCESS-3M percentile.
Stage+breadth land on `OpportunityCard.theme_stage`/`theme_stage_confirmed`,
snapshot, Cockpit Section B, Sector theme table, and Send-to-Scanner.

**Task 3 — Market-Internals Fragility** (`lib/market_internals.py`, NEW): pure
components — `count_distribution_days` (IBD), `breadth_above_sma`,
`count_good_news_sold` (AVGO pattern), `detect_weak_bounce`, + offense/defense
(e). `compute_fragility` → level normal/elevated/high with `apply_hysteresis`
(escalate after 2 consecutive sessions — single-day spike never escalates;
de-escalate faster). `compute_market_fragility` orchestrates cache-only loaders;
`fragility_snapshot` + `read_recent_meta`/`history_from_snapshots` make the daily
snapshot `_meta` the hysteresis memory. **STRICT tighten-only**: `macro_regime.py`
FROZEN (byte-identical invariant tested); `GATE_BY_LEVEL` = high→SHORT,
elevated→none; `derive_status(..., fragility_gate_horizons=)` degrades SHORT
in-zone Actionable→Research Required with reason `internals_deteriorating`
(mirrors the calendar gate; never relaxes). `rank_opportunities(fragility_level=)`
threads it; Cockpit banner shows the fragility line + components; `thesis_monitor`
gets a WATCH-level `fragility_note`/`fragility_watch` annotation on signal D
(thesis_status untouched).

**Modified:** `lib/relative_strength.py`, `lib/rotation.py`, `lib/theme_baskets.py`,
`lib/opportunity_ranker.py`, `lib/thesis_monitor.py`, `pages/2_Sector.py`,
`pages/7_Investment_Cockpit.py`, `ui_utils.py` (EN/ZH keys), state docs.
**Created:** `lib/market_internals.py`,
`scripts/test_reliability_phase_7b_rotation_internals.py`,
`docs/reliability_phase_7b_rotation_internals.md`.

**Judgment calls** (see phase doc): legacy `rs_composite` frozen (7A safety);
sector `score` contract preserved (multi-window lives in `build_sector_excess` +
`offense_defense_reading`); theme breadth fetches constituents (single per-refresh
theme fetch, not the per-ticker ranking loop); fragility gate → Research Required;
thesis fragility is annotation-only. Pages render-smoke clean via AppTest.

## Valuation Stop-the-Bleed — Implemented (prior task)

Three deterministic valuation-layer fixes (no LLM). Phase doc
`docs/reliability_valuation_stopbleed.md`; suite
`scripts/test_reliability_valuation_stopbleed.py` **54/54**; five regressions +
7A green.

1. **Anchor consistency gate** — a `max/min` dispersion gate
   (`ANCHOR_DISPERSION_THRESHOLD = 3.0`, boundary `>`) in both
   `lib/equity_valuation.py` (DCF/relative/analyst blend) and
   `lib/valuation_anchor.py` (analyst/relative). Irreconcilable anchors are not
   blended — the band collapses, confidence is forced low,
   `AppFairValue.blend_state="anchors_irreconcilable"` /
   `FairValueAnchor.anchor_state` is set, `conservative_anchor=None`.
   `order_advisor`'s LONG initiate path degrades **explicitly** to *"valuation
   unreliable — technical reference only"* (SHORT/MID and all numerics
   elsewhere unchanged). `pages/4` shows anchors side-by-side with no range bar.
2. **Forward-estimates basis** — the relative anchor prefers `forwardEps`
   (`relative_basis`), trailing fallback flagged, forward × trailing sector P/E
   flagged `peer_pe_basis="mixed"`; basis badge in the valuation UI.
3. **Anchor cache** — `lib/anchor_cache.py` (`data/anchor_cache.json`, atomic
   write, 7-day default staleness). Write-through from
   `store_equity_research_result`; the Cockpit `rank_opportunities(anchor_cache=)`
   reads it read-only and feeds a fresh band to the LONG `compute_price_levels`
   so LONG differentiates (in/above/below) instead of collapsing to Research
   Required; `OpportunityCard.anchor_age_days` + snapshot field track staleness.
   On the fixture set a fresh anchor flips LONG **Research Required → Actionable
   Now** (age 2.0); stale/missing keep prior behavior.

## Phase 7A — Opportunity Ranking MVP — Implemented + fix round; Awaiting Codex Review

Turns the existing signal candidates into a ranked, actionable **opportunity
list** (a research queue, "worth 10 minutes of attention" — review-only, not a
buy list). Orchestration layer only: **no new entry-zone / stop / technical
threshold logic and no invented numbers.** `approved_for_execution` always
False/absent.

**Fix round (2026-06-05):** addressed 6 Codex should-fix items + 3 real-data
product issues. (1) Status mapping revised — **Avoid Chasing reserved** for
genuine overextension/risk-overlay failures (a pending entry **trigger** is now
**Wait for Breakout**, fixing the pullback-vs-Avoid contradiction), and
`below_zone` is **horizon-aware Research Required** (never a bullish breakout).
(2) Reason codes: commonality filter (drop codes shared by >50% of cards),
embedded RS magnitudes, removed the "priced-in" overclaim (→ `recent_catalyst`).
(3) Blocker hygiene: per-card chips are ticker-specific + horizon-filtered;
market-wide macro/FOMC/CPI shown once as a panel banner. (4) Concentration refs
computed at **display time** over the per-horizon-sorted list. (5) Contract
hardening: deterministic tie-break (score desc, ticker asc); network-free ranking
(missing/cache-miss RS → neutral + `rs_degraded`; benchmarks the single fetch);
atomic snapshot writes (temp + `os.replace`). (6) Setup scoping: thresholds moved
to a `SETUP_THRESHOLDS` config block; Post-earnings Reprice now uses **actual
days-since-report within a bounded window** (no LLM-recency/price-gap inference;
fixes the stale AAPL@35d mislabel).

**Fix round 2 (2026-06-05, Codex re-review):** (1) **Per-horizon status** —
status / next_trigger / reason are now computed for short/mid/long and stored as
maps; the Cockpit selector renders the selected horizon (fixes the MU mid-view
anomaly that showed a LONG valuation-anchor trigger in the MID view); snapshot
stores `status_by_horizon`. (2) Cockpit now actually uses the **cache-only RS
path** (`build_rs_map_cache_only` → `lib.cache_manager.load`, zero per-ticker
fetch; benchmarks the single fetch) + an integration test. (3) The fundamental
gate also reads the **engine's `missing_conditions`** (valuation/EPS/quality →
Avoid; trend/volume/price → Wait for Breakout). Nits: `trigger_pending` removed
from why_now (status reason only); page-import smoke now AST-parses the imports.
Row-4 precedence (price overextension beats provenance) pinned.

**Final fix (2026-06-05, Codex re-review):** the Fix-3 engine classifier is now
**registry-backed**. `lib/order_advisor.py` gained a `MISSING_CONDITION_REGISTRY`
(7 entries: stable `code` + `category` + bilingual text; `.text` reproduces the
exact emitted string) plus `missing_condition_category` /
`MISSING_CONDITION_TEXT_TO_CATEGORY`; `_short_confirmation` and the
`_GATE_REASON_*` constants now reference the registry. `lib.opportunity_ranker`
classifies engine blocks by the declared category first, substring matching only
as a legacy fallback (fundamental-wins-on-collision). **String/constants-only
refactor** — zero numeric/threshold/gate/control-flow change; emitted strings
byte-identical, so all consumers (LLM order narrative, Trading Desk cards, thesis
monitor, fixtures) are unaffected. Tests: registry-driven pinning through
`derive_status` + an AST completeness guard (any inline condition literal fails
the suite) + legacy-fallback/collision fixtures. Test suite now **115/115**.

**Created:** `lib/opportunity_ranker.py` (ranking, five-state status mapping,
setup classifier, rule + calendar blockers, why-now/why-it-matters reason codes,
concentration hint, daily snapshot), `lib/relative_strength.py` (simplified RS —
a new helper so the frozen `lib/technical.py` is untouched),
`scripts/test_reliability_phase_7a_opportunity_ranking.py` (mock-only, **115/115**),
`docs/reliability_phase_7a_opportunity_ranking.md` (phase doc: status mapping
table, weight config, snapshot schema).

**Modified:** `pages/7_Investment_Cockpit.py` (Section C → Opportunity Card panel
+ horizon selector; refresh ranks candidates + writes the daily snapshot),
`pages/9_Trading_Desk.py` (Section 3 adopts the unified five-state naming +
carries setup/status/blockers/grades), `ui_utils.py` (additive `opp_*` EN/ZH
keys), state docs.

**Five-state status** (unifies the legacy in_zone/above_zone/below_zone/blocked
vocabulary): Actionable Now / Wait for Pullback / Wait for Breakout / Research
Required / Avoid Chasing — derived from `order_advisor.compute_price_levels`
(deterministic numeric path only; never an LLM). **Three independent horizon
scores** (short/mid/long) from three weight tables (RS = 0.20 each); the UI shows
grades only (A ≥ 0.66, B ≥ 0.40, else C). **Performance:** all candidates scored
network-free (RS from cached OHLCV, benchmarks fetched once); the entry engine +
earnings fetch run only for the top N (default 20). **Daily snapshot** of ALL
ranked candidates → `data/snapshots/opportunities_YYYYMMDD.jsonl` (same-day
refreshes overwrite; per-ticker series reconstructable for Phase 7D review).
Optional LLM polish converts raw reason codes to sentences for the top cards only
— separate from the ranking path, degrades silently.

**Validation** (`wsl.exe -d ubuntu -- bash -lc 'python3 -B ...'`):
`test_reliability_phase_7a_opportunity_ranking.py` 115/115;
regression `test_reliability_phase_6c_b_cockpit_rebuild.py` 47/47,
`test_reliability_equity_render_order.py` 50/50,
`test_reliability_phase_6c_trading_desk.py` 118/118,
`test_reliability_phase_6c_v3_entry_v4.py` 47/47,
`test_reliability_phase_6b_v3_horizon_scoring.py` 189/189. (The pre-existing
`test_reliability_phase_6b_signal_layer.py` check 7.1 failure is unrelated to
Phase 7A — `lib/signal_engine.py`, untouched here, legitimately lazy-imports
`llm_orchestrator` for its Layer-2 narrative.)

**Out of scope (7A):** leader/laggard labels, group confirmation, theme rotation
stages, beneficiary tiers, thesis ingestion, LLM macro event layer, liquidity
plumbing fetchers, full universe expansion, alt data, any valuation-logic change.
**Not modified:** `lib/macro_regime.py`, `lib/workflow_state.py`,
`lib/technical.py`, `lib/macro_data.py`, `lib/signal_engine.py`,
`lib/candidate_generator.py`, `lib/theme_baskets.py`, `lib/order_advisor.py`,
`lib/data_fetcher.py`, `.claude/agents/*`, pages 1–6/8.

---

<!-- ===== Prior status blob (pre-Phase-7A) preserved verbatim below ===== -->

**Earlier last-updated**: 2026-05-29 (**Phase 5H / 5H.1 — Controlled Streamlit Cockpit UI Integration v0.1 + Cockpit Page Runtime Fix + Bilingual Surface — Accepted** (Phase 5H.1 test 226/226; Phase 5G 344/344; Phase 5A 175/175; Phase 5I review-cleanup marked superseded prose in the Phase 5H design doc §6/§7 as historical and strengthened §18.3 schema-identifier documentation — no module/runtime change). **Phase 5I — Investment Cockpit Product Logic Reconciliation / Opportunity-first + Horizon-aware Architecture — Accepted.** Phase 5I is product-logic reconciliation and roadmap/documentation only; it supersedes the earlier "Phase 5I — Read-only Shadow Integration" plan as the immediate next step; deliverables `docs/reliability_phase_5i_investment_cockpit_product_logic_reconciliation.md` + `scripts/test_reliability_phase_5i_product_logic_reconciliation.py`; no Theme Intelligence / Opportunity Queue / Auto Research Pack / Agent Debate / Macro Dashboard code; no UI redesign; no sidebar change; Financial/PriceVolume pages not removed; no live workflow integration; no shadow integration; no LLM/external API; no DB/vector/persistence; no broker/order/execution; `approved_for_execution` never positively authorized; **Phase 5J Theme Intelligence / Market Heat Schema is now Accepted** (schema / contract / helper / fixture only; offline / mock-only; Phase 5J test 202/202). **Phase 5K — Horizon-aware Opportunity Queue ViewModel — Accepted** (view-model / schema / helper / fixture only; offline / mock-only; consumes Phase 5J `ThemeRecord` / `ThemeCandidateTicker`; Phase 5K test 218/218; Phase 5J 202/202; Phase 5K review-cleanup performed during Phase 5L: backward-compatible clarification of `OpportunityQueueValidationSummary.distinct_tickers` — it counts distinct `(theme_id, ticker)` pairs, so the new sibling field `distinct_theme_candidate_opportunities` carries the same value under a clearer name while `distinct_tickers` is preserved for existing consumers; no decision-logic or other Phase 5K behavior change). **Phase 5L — Auto Research Pack Orchestration Boundary — Accepted** (schema / helper / orchestration-boundary / fixture only; offline / mock-only; consumes the Phase 5K `HorizonAwareOpportunityQueueView`; Phase 5L test 220/220; Phase 5K 218/218; Phase 5J 202/202). **Phase 5M — Agent Debate / Decision Workspace Contract — Accepted** (schema / helper / view-model / fixture only; offline / mock-only; consumes the Phase 5L `AutoResearchPackOrchestrationBoundary` / `ResearchPackBundle`; deterministic bull/bear/risk/critic/allocation/option role records with no live agent run; explicit `DebateConflictRecord` conflicts that the critic never hides; review-only `DecisionWorkspaceView` with `is_executable_decision=False` and `requires_human_review=True`; `approved_for_execution` absent on every model; Phase 5M test 263/263; Phase 5L 220/220; Phase 5K 218/218). **Phase 5N — Cockpit UI v0.2 Opportunity-first Redesign — Implemented; Awaiting Codex Review** (opportunity-first redesign of `pages/7_Investment_Cockpit.py` only + additive `ui_utils.py` EN/ZH chrome; ten v0.2 tabs Overview/Safety, Market Themes, Opportunity Queue, Decision Workspace, Research Snapshot, Agent Debate, Trade / Allocation Plan, Option Overlay, Feedback / Review, Provenance / Diagnostics; consumes the Phase 5G demo pack + Phase 5J/5K/5L/5M fixtures directly; fixture-only / offline / review-only; no live workflow / LLM / external API / DB / vector store / persistence / broker / order / execution; `approved_for_execution` False or absent; `no_trade` first-class; Phase 4A not wired in; Phase 5N test 683/683; reconciled Phase 5H test 235/235; Phase 5M 263/263; Phase 5L 220/220; Phase 5K 218/218; Phase 5J 202/202; **Phase 5N is now Accepted**; **Phase 5O — Macro Dashboard v0.1 — Accepted** (Codex verdict PASS); **Phase 5O.1 — Macro Indicator Expansion — Implemented; Awaiting Codex Review** (additive fixture-only concrete macro indicators — WTI, GC/gold, CNN Fear & Greed, QQQ, IWM, NFP, CPI, PPI — grouped into commodities / risk-appetite-leadership / economic-releases in `lib/reliability/phase5_macro_dashboard.py` via `MacroIndicatorPanel` + concrete indicator view models; a new Macro Indicators tab in `pages/8_Macro_Dashboard.py`; additive `ui_utils.py` EN/ZH `macro_*` indicator keys; fixture-only / offline / review-only; no yfinance/Finnhub/FRED/CNN/news/external API; no live macro data retrieval; no LLM; no DB / vector store / persistence; no broker / order / execution; produces no final buy/sell decision; `approved_for_execution` absent by construction; Phase 5O test 766/766; Phase 5N regression 683/683; **Phase 5O.1 is now Accepted**; **Phase 5P — Source Page Navigation Cleanup — Accepted** (Codex verdict PASS; navigation-cleanup-only `ui_utils.render_sidebar` change removing top-level `pages/5_Financial.py` / `pages/6_PriceVolume.py` links — they become source sub-surfaces under Equity Research — while keeping Macro Dashboard `nav_p8` and Investment Cockpit `nav_p7` first-class; source page files retained and unmodified; `nav_p5` / `nav_p6` keys retained as legacy labels; Phase 5P test 96/96; Phase 5O regression 766/766; Phase 5N regression 683/683; no LLM / external API / live workflow / DB / vector store / persistence / broker / order / execution; `approved_for_execution` False or absent); **Phase 5Q — Human Feedback UI v0.1 — Implemented; Awaiting Codex Review** (controlled session-only / non-persistent / non-executable human-feedback review surface in the Investment Cockpit Feedback / Review tab; new session/UI contract module `lib/reliability/phase5_human_feedback_ui.py` — `HumanFeedbackUIState` / `HumanFeedbackActionView` / `HumanFeedbackReviewTarget` / `HumanFeedbackFormState` / `HumanFeedbackSessionRecord` / `HumanFeedbackValidationSummary` / `HumanFeedbackSafetyBanner` + Literal aliases + deterministic builders + `build_default_human_feedback_ui_state()` fixture; review actions accept_for_watchlist / reject / modify_thesis / request_more_research / wait_for_pullback / manually_executed_outside_system / skip / review_later / no_trade_confirmed, every action `is_executable=False`; review targets bound to the Phase 5K opportunity queue, Phase 5M decision workspace status + agent-debate consensus/conflicts, and Phase 5G/5D trade plans + option overlays / no_trade state; submitted feedback held only in `st.session_state` (`phase5q_feedback_session`) — never persisted; enhanced `pages/7_Investment_Cockpit.py` Feedback / Review tab with a session-only form + preview using `st.radio` pickers that preserve the sidebar scenario selectbox ordering; additive EN/ZH `cockpit_review_hf_*` / `cockpit_review_action_*` keys in `ui_utils.py`; every Phase 5Q model `extra="forbid"` with `approved_for_execution` absent and `is_session_only=True` / `is_persisted=False`; Phase 5Q test 389/389; Phase 5N regression 683/683; Phase 5M regression 263/263; no live workflow / LLM / external API / DB / vector store / persistence / broker / order / execution; no permanent feedback persistence; no live shadow integration; no UI/UX visual polish (deferred to Phase 5R); Phase 4A not wired in; **Phase 5Q is now Accepted** (Codex verdict PASS); **Phase 5R — UI/UX Visual Polish + Demo Readiness — Implemented; Awaiting Codex Review** (bilingual demo-walkthrough expander on `pages/7_Investment_Cockpit.py` + `pages/8_Macro_Dashboard.py`; additive `cockpit_walkthrough_*` / `macro_walkthrough_*` EN/ZH chrome keys; UI/UX polish + demo readiness only — no product logic / scoring / schema / agent-contract / queue / research-pack / debate / feedback / macro-regime change; no live workflow / LLM / external API / DB / vector store / persistence / broker / order / execution; `approved_for_execution` False or absent; Phase 5R test 324/324; Phase 5Q 389/389; Phase 5N 683/683; Phase 5O 766/766; **Phase 5R is now Accepted** (accepted during the Phase 5S pass per the prior review's minor suggestion); **Phase 5S — Phase 5 Productization Closeout — Implemented; Awaiting Codex Review** (closeout / documentation / state / test-summary only — `docs/ai_dev_state/PHASE_5_CLOSEOUT.md` + `docs/reliability_phase_5s_productization_closeout.md` + `scripts/test_reliability_phase_5s_closeout.py`; no new runtime feature / UI layout / product-logic change; Phase 5 not formally accepted until Codex accepts Phase 5S; Phase 5S not yet accepted; **Phase 6A — Live Data Integration — is Implemented; Awaiting Codex Review (Phase 6B not started)**; recommended next phase after acceptance is Phase 6A — Phase 6 Planning / Real Integration Boundary Decision))). **File-provenance baseline (Phase 5J minor-suggestion cleanup):** the dirty / untracked worktree state includes accepted Phase 5H.1 live UI/sidebar/translation files (`pages/7_Investment_Cockpit.py`, `ui_utils.py`) which are part of the **accepted Phase 5H.1** change set and are NOT modified by Phase 5J or Phase 5K; the Phase 5J footprint is schema-only (`lib/reliability/phase5_theme_intelligence.py` + test + doc + additive `__init__` exports) and the Phase 5K footprint is view-model-only (`lib/reliability/phase5_opportunity_queue.py` + test + doc + additive `__init__` exports). Future reviews should treat the Phase 5H.1 UI/translation files as already-accepted and out of scope for Phase 5J / 5K. Prior history preserved below. — Phase 4M-H — Phase 4 Memory Closeout — **Accepted**. Phase 5P — Phase 5 Roadmap Decision / Planning — **Accepted**. Phase 5A — Existing Workflow Memory Adapter + Fixture-backed Memory Query Contract — **Accepted**. Phase 5B — Company Research Hub ViewModel Contract — **Accepted**. Phase 5C — Horizon Decision Cards + ThesisTracker ViewModel Contract — **Accepted**. Phase 5D — Portfolio / TradePlan / Option Overlay ViewModel Contract — **Accepted**. Phase 5E — Cockpit UI Planning Boundary for Existing Streamlit App — **Accepted**. Phase 5F — Shadow Mode Integration Boundary Planning — **Accepted**. **Phase 5G — Fixture Demo Pack Based on Original App Flow — Accepted.** Phase 5G review cleanup pass updated the Phase 5G design doc status line from "Implemented — awaiting Codex review" to "Accepted" and the test-count wording from "322 assertions expected" / "~322" to "344/344" (the actual passing count). No Phase 5G module / runtime / test behavior change. Phase 5G test still passes 344/344. **Phase 5H — Controlled Streamlit Cockpit UI Integration v0.1 — Implemented but had three post-implementation defects discovered during user-facing verification on 2026-05-27 (model_dump→model_validate round-trip incompatible with Phase 5G `Field(exclude=True)`; sidebar entry missing; no bilingual surface). Phase 5H.1 — Cockpit Page Runtime Fix + Bilingual Surface — Implemented; Awaiting Codex Review** (replaces `pages/7_Investment_Cockpit.py` with a `@st.cache_resource`-based loader; adds `apply_theme()` + `render_sidebar()` bootstrap; routes every page-chrome string through `ui_utils.t()`; adds `nav_p7` and ~140 `cockpit_*` translation keys to both `TRANSLATIONS["en"]` and `TRANSLATIONS["zh"]` in `ui_utils.py` strictly additively; adds one `st.page_link("pages/7_Investment_Cockpit.py", label=t("nav_p7"))` line in `ui_utils.render_sidebar`; reshapes the Phase 5H test to TRANSLATIONS-backed assertions and adds Section 14 — `streamlit.testing.v1.AppTest`-driven render coverage in EN and ZH; **226/226 passing** up from Phase 5H's 170/170; Phase 5G 344/344 unchanged; Phase 5A 175/175 unchanged; no live runtime file outside `pages/7_Investment_Cockpit.py` / `ui_utils.py` modified; Phase 5G schema unchanged — `Field(exclude=True)` preserved; `approved_for_execution` invariant preserved; `no_trade` invariant preserved; Phase 4A not imported). Phase 5H adds one new Streamlit page (`pages/7_Investment_Cockpit.py`) that consumes only the Phase 5G fixture demo pack and renders the Phase 5B / 5C / 5D view-model contracts through eight tabs (Overview / Safety, Company Research Hub, Horizon Cards, ThesisTracker, Portfolio / TradePlan, Option Overlay, Feedback / Agent Evaluation, Provenance / Diagnostics); one new design document (`docs/reliability_phase_5h_controlled_streamlit_cockpit_ui.md`); one new test (`scripts/test_reliability_phase_5h_cockpit_ui_preview.py`, 170/170 passing). The Phase 5H page is fixture/demo-only: it does **not** call any LLM, external API, broker, or order router; it does **not** read `research/.workflow_state.json`; it does **not** import `lib/workflow_state.py`, `lib/llm_orchestrator.py`, `lib/data_fetcher.py`, `lib/valuation.py`, `lib/technical.py`, `lib/rotation.py`, `lib/cache_manager.py`, `lib/reliability/integration_boundary.py`, `anthropic`, or `openai`; it does **not** write to disk; it does **not** introduce a DB / vector store / persistence; it does **not** introduce executable order fields or order-ticket labels; it fails closed on demo-pack builder error with no LLM/API fallback. The page surfaces both pack-level and scenario-level Phase 5G `DemoSafetyBanner` values and surfaces a top-of-tab safety banner with the required wording bullets. The scenario selector defaults to the complete scenario (`FIXTKR`) and exposes the degraded scenario (`FIXDEG`). The degraded scenario shows the missing financial panel safely, the missing long-horizon thesis card safely, and the `no_trade` option overlay state with a populated `NoTradeReasonView`. `approved_for_execution` remains `False` (or absent) everywhere it appears and is never positively authorized by the page. `no_trade` preserved as first-class option overlay state. Existing pages 1–6 and `app.py` are not modified; the Phase 5H test asserts each forbidden live runtime file still exists, asserts none of the existing pages contains Phase 5H marker strings, and asserts the page contains no live-runtime import or live workflow-state read. Phase 4A remains frozen and is not imported. Phase 5I (read-only shadow integration) **has not started**. Phase 5A regression test `scripts/test_reliability_phase_5a_memory_query.py` still passes 175/175. Phase 5G regression test `scripts/test_reliability_phase_5g_cockpit_demo_pack.py` still passes 344/344.)

## Phase 6C-B fix v3 — Equity page: layout-first extended to two more sections — Implemented (CURRENT TASK)

**`pages/4_Equity.py` layout-first, v3 (Codex-approved v2 + two follow-ups).**
After Codex approved the v2 full-page layout-first refactor, two more Overview
sub-sections — **Company Business Description** and **Research Report** — were
moved onto the same pre-created-slot pattern. Inside the layout block,
`with tab_overview:` now reserves `ov_top_slot = st.container()` (moat+peers),
`biz_slot = st.empty()` and `report_slot = st.empty()` (each with a `⏳` bilingual
placeholder), filled in the FILL PASS via `with ov_top_slot:` /
`biz_slot.container()` / `report_slot.container()`. The Business Description falls
back to source text on a `translate_to_chinese` failure (never hangs on the
placeholder); the Research Report is confirmed **deterministic (no LLM call)**, so
its auto-run behavior is unchanged and its disk write is now `try/except`-guarded.
**New layout block: lines 82–140** (was 82–119); first blocking call `load_info`
at line 147 — no blocking call precedes the layout block. On cold-cache entry ALL
frames (header, earnings, metrics, four tabs, business description, research
report, AI Valuation Summary) appear essentially immediately. Render-order only;
widget keys / bilingual / buttons / `equity_prefill_ticker` preserved.

The render-order test now registers the two new sections (their `st.empty` slots
join the slot set; `translate_to_chinese` joins the blocking set and is exercised
under `language="zh"`), via a single in-test `_BLOCKING_PATCHES` registry; the
docstring overclaim about "any new blocking call caught automatically" was
corrected to state coverage is limited to that registry (chose option (a); option
(b) shared registry judged over-engineering). Structural assertion re-run warm +
cold; negative control (Business Description) verified and reverted.
**Tests:** `scripts/test_reliability_equity_render_order.py` **50/50** (was
37/37); `scripts/test_reliability_phase_6c_b_cockpit_rebuild.py` regression
**47/47**. Full detail + manual checklist in `docs/ai_dev_state/CURRENT_TASK.md`.

---

## Phase 6C-B fix — Equity page AI Valuation Summary render-order — Implemented (v1/v2 history)

**`pages/4_Equity.py` render-order fix.** The "AI Valuation Summary" expander
only appeared after the whole page (Financials / Price-Volume / News + Research
Report) finished. Root cause: Streamlit streams element deltas in
script-execution order, and the valuation section was the **last top-level block**
— so its `st.empty()` placeholder (created at the bottom) could not render until
every blocking tab body ran first, dominated by the News tab's per-headline
`translate_to_chinese` loop (~0.4s × up to 20 ≈ 8–14s). Empirically (AppTest +
timing logs) the section was not reached until +12–18s.

**Fix — Option A (layout-first), completed in v2 after Codex REQUEST CHANGES.**
v1 moved only the valuation slot above the tab bodies, but `load_info` /
`load_earnings` (and the header / earnings / metrics that consume them) still ran
before it — so on a cold cache the frame was still not guaranteed immediate. v2
introduces **one contiguous LAYOUT-FIRST PASS (pages/4_Equity.py lines 82–120)**
that creates *every* top-level section frame — `header_slot`, `earnings_slot`,
`metrics_slot` (each `st.empty()` with a placeholder), the four `st.tabs(...)`
frames, and the valuation `fv_slot` + `summarizing...` placeholder — **before any
blocking call** (the only things above it are imports, the `equity_prefill_ticker`
session read, the ticker-input widget, and the empty-ticker guard). The **FILL
PASS** (line 122 onward; first fetch `load_info` at line 127) runs the data
fetches and fills each pre-created slot via `slot.container()` /
`fv_slot.container().expander(...)`. Option B (`st.fragment`) was rejected:
fragments execute inline on the initial run and only isolate reruns. Streamlit
1.57.0 installed. Rendering-order refactor only — no computation / LLM-prompt /
session-state-key change; all action buttons, `equity_prefill_ticker`, bilingual
header, and LIVE/FIXTURE preserved.

**Strengthened test.** `scripts/test_reliability_equity_render_order.py` now runs
the page under AppTest with a call log recording BOTH slot creations
(`st.empty`/`st.tabs`) and every blocking call (incl. `load_info` /
`load_earnings`), asserting structurally that `max(slot_seq) < min(blocking_seq)`
— so any fetch reintroduced above the layout block fails the test automatically.
Includes a cold-cache scenario and a verified negative control.

**Tests:** `scripts/test_reliability_equity_render_order.py` **37/37** (was
29/29); `scripts/test_reliability_phase_6c_b_cockpit_rebuild.py` regression
**47/47**. See `docs/ai_dev_state/CURRENT_TASK.md` for the full diagnosis table,
the v2 layout-block line range, and the manual verification checklist.

## Phase 6C-B — Investment Cockpit Rebuild — Implemented; Awaiting Codex Review

**Phase 6C-B — Investment Cockpit Rebuild — Implemented; Awaiting Codex Review.**
This is the **current task**, building on the accepted-pending Phase 6C-A v3 entry
engine. It rebuilds `pages/7_Investment_Cockpit.py` from the Phase 5N fixture/demo
surface into the app's **primary entry point and live data aggregation hub**, adds
an app-computed fair-value layer, and wires that fair value into the Trading Desk
order recommendations. **Phase 6C-B is not accepted in this pass. Phase 6D has not
started.** Recommended next phase after acceptance: **Phase 6D — Monitoring &
Review.**

Single acceptance criterion: *"The user opens Investment Cockpit, clicks Refresh,
selects tickers, and Trading Desk order recommendations use fair values computed
by the app rather than yfinance analyst targets alone."*

- **Sidebar restructure** (`ui_utils.render_sidebar`): new order Home · Investment
  Cockpit · Macro Dashboard · Sector Research · Stock Scanner · Equity Research ·
  Trading Desk. The AI Research Workflow (Overview, `pages/1_Overview.py`) is
  REMOVED from the sidebar (page retained, reachable by URL; `nav_p1` kept,
  marked deprecated). `nav_p5` / `nav_p6` source-page keys preserved.
- **`lib/equity_valuation.py`** (new) — `AppFairValue` dataclass +
  `compute_app_fair_value()` (yfinance only; cached TTL=3600; fail-closed) +
  pure `build_app_fair_value()` assembler + `store_equity_research_result()`
  (writes `st.session_state["equity_research_results"]`). Blends DCF
  (per-share Gordon growth, WACC=10%, growth cap=15%) + relative
  (`SECTOR_MEDIAN_PE × trailing_eps`) + analyst target into a
  low ≤ mid ≤ high band with high/medium/low confidence.
- **`lib/llm_orchestrator.py`** — additive `analyze_equity_fair_value_debate()`
  (one cached LLM call, TTL=7200 keyed `(ticker, confidence, macro_regime, lang)`;
  bilingual bull/bear/risk/synthesis + endorsed range + action; fail-closed to the
  app low/high band). The LLM only debates the code-computed numbers.
- **`lib/order_advisor.py`** — `PriceLevelResult.fair_value_source`
  (`app_computed` / `analyst_proxy` / `fixture`); `compute_price_levels()` Step 0
  reads `equity_research_results` and, when present with high/medium confidence,
  uses `fair_value_mid` as the primary anchor, `fair_value_low` as the LONG entry
  floor, and `fair_value_high` as the upside target; otherwise falls back to
  `lib/valuation_anchor.py`. `approved_for_execution` still always False.
- **`pages/4_Equity.py`** — new collapsed **AI Valuation Summary** section
  appended after all existing content (range bar, upside, confidence badge,
  methodology, per-source contributions, **Run AI Debate** + **Send to Trading
  Desk** buttons). No existing content modified.
- **`pages/7_Investment_Cockpit.py`** — full rebuild: header (title, last-refresh,
  **Refresh All**, module status indicators); Section A macro regime; Section B
  top-3 market themes; Section C signal candidates + ticker selection
  (`cockpit_selected_tickers`); Section D equity research results; Section E triple
  signal watch with Add-to-Holdings prefill. One-click refresh runs
  `fetch_all_macro`+`classify_regime` → `compute_all_themes` →
  `generate_candidates` → `compute_app_fair_value`/`store_equity_research_result`,
  all fail-closed; sets `cockpit_last_refresh`. The Trading Desk thesis monitor is
  NOT triggered by refresh.
- **`pages/9_Trading_Desk.py`** — order cards show a `fair_value_source` badge.
- **`ui_utils.py`** — additive EN/ZH `cockpit_hub_*` / `cockpit_fv_*` /
  `td_fair_value_source` / `td_fv_src_*` `t()` keys.
- **`scripts/test_reliability_phase_6c_b_cockpit_rebuild.py`** (new) — mock-only;
  **47/47**.
- **`scripts/test_reliability_phase_6c_trading_desk.py`** — assertion 9.5 updated
  to the new spec-mandated sidebar order (Trading Desk now after Equity; Cockpit
  leads). Re-passes **118/118**.

**Validation:** `phase_6c_b_cockpit_rebuild` 47/47; `phase_6c_v3_entry_v4` 47/47;
`phase_6c_trading_desk` 118/118; `phase_6b_v3_horizon_scoring` 189/189;
`phase_6a_live_data` 336/336. Guardrails: free sources only; no paid API; no
broker / order / execution; `approved_for_execution` always False; no DB / vector
store; no persistence beyond `st.session_state`. `lib/macro_regime.py`,
`lib/macro_data.py`, `lib/workflow_state.py`, `lib/signal_engine.py`,
`lib/thesis_monitor.py`, `lib/candidate_generator.py`, `lib/theme_baskets.py`,
`.claude/agents/*`, pages 2 / 3 / 5 / 6 not modified; `pages/1_Overview.py`
retained (only unregistered).

> Next step: Codex review of Phase 6C-B. Recommended next phase after acceptance:
> **Phase 6D — Monitoring & Review** (not started).

Design doc: `docs/reliability_phase_6c_b_cockpit_rebuild.md`.

---

## Phase 6C-A v3 — Entry Strategy v4 — Implemented; Awaiting Codex Review

**Phase 6C-A v3 — Entry Strategy v4 — Implemented; Awaiting Codex Review.** This is
the **current task**, superseding Phase 6C-A v2 (Entry Strategy v3). It refactors
`lib/order_advisor.py` + `lib/valuation_anchor.py` so building and adding positions
share the same **market-based Horizon Entry Zone Engine**; `cost_basis` enters ONLY
in the new **Existing Position Risk Overlay** for add scenarios. LONG uses a
**three-tier valuation confidence** system (`high` / `medium` / `low`, computed from
analyst-coverage breadth, sell-side dispersion, and analyst-vs-relative anchor
spread), and **portfolio settings are persisted in `data/holdings.json`** under a
top-level `portfolio_settings` key. **Phase 6C-A v3 is not accepted in this pass.
Phase 6C-B has not started.** Recommended next phase after acceptance: **Phase 6C-B
— Cockpit Rebuild.**

- **`lib/holdings.py`** — `PortfolioSettings` dataclass + `load_portfolio_settings`
  / `save_portfolio_settings` / `load_cash_position` / `save_cash_position`; the
  writer preserves the other top-level blocks on a single-field write. Fail-closed.
- **`lib/valuation_anchor.py`** — `FairValueAnchor` gained `analyst_anchor`
  (`targetMedianPrice` priority), `relative_anchor`, `dispersion`, `anchor_spread`,
  `analyst_count`, `confidence`, `conservative_anchor`, and a tier-dependent
  `fair_value_anchor`.
- **`lib/order_advisor.py`** — `PriceLevelResult` gained `valuation_confidence` /
  `conservative_anchor` / `risk_overlay_passed` / `risk_overlay_note` /
  `portfolio_weight_current` / `portfolio_weight_after_add` / `blended_cost_after_add`;
  LONG confidence-tier zone + `≥0.85` soft warning; LONG `add_tiny` band;
  `_gather_portfolio` + `_apply_add_overlay`. `approved_for_execution` always False.
- **`pages/9_Trading_Desk.py`** — Portfolio Settings expander + LONG
  `valuation_confidence` badge + `risk_overlay_note` + projected weight / blended
  cost on order cards; never writes `data/holdings.json` directly.
- **`scripts/test_reliability_phase_6c_v3_entry_v4.py`** (new) — mock-only; **47/47**.
- **`ui_utils.py`** — additive EN/ZH `td_portfolio_settings` / `td_*` settings,
  confidence, overlay, and `td_act_add_tiny` `t()` keys only.

**Validation:** `phase_6c_v3_entry_v4` 47/47; `phase_6c_v2_entry_strategy` 99/99;
`phase_6c_trading_desk` 118/118; `phase_6b_v3_horizon_scoring` 189/189;
`phase_6a_live_data` 336/336. Guardrails: free sources only; no paid API; no broker
/ order / execution; `approved_for_execution` always False; no DB / vector store;
`lib/macro_regime.py`, `lib/macro_data.py`, `lib/workflow_state.py`,
`lib/signal_engine.py`, `lib/thesis_monitor.py`, `lib/candidate_generator.py`,
`.claude/agents/*`, pages 1–8 not modified.

---

## Phase 6C-A v2 — Entry Strategy v3 Refactor — Superseded by v3 (Entry Strategy v4)

**Phase 6C-A v2 — Entry Strategy v3 — Implemented; Awaiting Codex Review.** This is
the **current task**. It is a full refactor of `lib/order_advisor.py`'s entry-zone,
add, and stop-loss logic into a **horizon-native, scenario-aware** (initiate vs add
vs manage) system. **Phase 6C-A v2 is not accepted in this pass. Phase 6C-B has not
started.** Recommended next phase after acceptance: **Phase 6C-B — Cockpit
Rebuild.**

- **`lib/technical.py`** — `snapshot()` now also returns `EMA_10`, `EMA_20`,
  `nearest_support` / `nearest_resistance` (largest swing low below / smallest
  swing high above price over the last 20 bars; `None` if not found) and
  `candlestick_pattern`. `SMA_50` / `SMA_200` / `ATR_14` were already present.
- **`lib/valuation_anchor.py`** (new) — `FairValueAnchor` + `compute_fair_value_anchor`
  (yfinance only, free; cached TTL=3600 keyed on ticker; fail-closed). Blends
  `analyst_anchor` (`targetMeanPrice × 0.90`), `relative_anchor` (median trailing
  P/E over the last ≤4 quarters × `trailingEps`), and a `valuation_anchor` fallback
  (`current_price × (1 − valuation_percentile × 0.30)`); `fair_value_anchor` is the
  `min` of the non-None anchors, else `current_price × 0.85` (always > 0).
- **`lib/order_advisor.py`** — refactored `PriceLevelResult` (v3 fields: `scenario`
  / `horizon` / `ema10` / `ema20` / `sma50` / `sma200` / `nearest_support` /
  `nearest_resistance` / `fair_value_anchor` / `action` / `entry_zone_low` /
  `entry_zone_high` / `stop_loss_level` / `position_sizing` / `reason` /
  `missing_conditions` / `next_trigger` / `risk_note` / `entry_status` /
  `risk_reward_ratio` / `data_source` / `approved_for_execution=False`; legacy
  `stop_loss` / `target_price` / `position_size_pct` / `support_levels` /
  `resistance_levels` / `volume_trend` / `candlestick_pattern` retained for the
  page + the Phase 6C-A regression test). New `compute_price_levels(..., scenario)`:
  Step 1 thesis gate (`broken → avoid`, scenario `manage`), Step 2 fundamental hard
  gate (`deteriorating` EPS OR valuation ≥ 0.70 → `wait`, entry None), Step 3
  `_compute_initiate_logic` / `_compute_add_logic`, Step 4 stop-vs-zone sanity +
  `entry_status` + `risk_reward_ratio` (0.0 when no zone). **SHORT** uses EMA10 +
  EMA20 (+ hard volume gate); **MID** uses SMA50 (healthy/neutral/unhealthy volume
  state); **LONG** uses SMA200 + `fair_value_anchor`. SHORT never averages down a
  loser (`wait_or_cut`); MID can `average_down_small` only when thesis intact + EPS
  not deteriorating; LONG can `average_down` when thesis intact; LONG stop is
  thesis/valuation-driven, not short-term technical. `generate_order_narrative` +
  `OrderNarrative` gained `next_trigger_note`; the LLM still only narrates.
- **`pages/9_Trading_Desk.py`** — order cards now show a scenario badge
  (建仓/Initiate · 加仓/Add · 管理/Manage), a color-coded action badge (green
  enter/add/average_down · yellow wait/hold · orange reduce/trim · red
  cut_loss/exit/avoid), a `missing_conditions` bullet list, a prominent
  `next_trigger` when there is no entry zone, the `position_sizing` band, and the
  LLM `next_trigger_note`. All chrome via `t()`.
- **`lib/thesis_monitor.py`** — added `short_time_stop_signal` + a SHORT-only time
  stop in `check_holding`: a `short`-horizon holding ≥ 5 days old still at
  ≤ `cost_basis × 1.02` adds `time_stop` to `technical_breakdown_reasons`, sets
  `technical_breakdown = True` (→ `broken`).
- **`scripts/test_reliability_phase_6c_v2_entry_strategy.py`** (new) — mock-only; **79/79**.
- **`ui_utils.py`** — additive EN/ZH `td_scenario_*` / `td_act_*` /
  `td_missing_conditions` / `td_next_trigger` / `td_risk_note` /
  `td_fair_value_anchor` `t()` keys only.

**Guardrails honored:** free sources only (yfinance via `compute_fair_value_anchor`
and `ui_utils.load_ohlcv`); no paid API; no broker / order / execution capability;
no order ticket / broker payload; `approved_for_execution` ALWAYS `False`; no DB /
vector store. `lib/macro_regime.py`, `lib/macro_data.py`, `lib/workflow_state.py`,
`lib/holdings.py`, `lib/signal_engine.py`, `.claude/agents/*`, and pages 1–8 not
modified. **Exception (documented):** `lib/thesis_monitor.py` was modified for the
SHORT time stop as explicitly required by the task spec (step 6) and its test
assertion, overriding the generic "do not modify" guardrail for that one additive
change.

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

**Phase 6C-A — Trading Desk — Implemented; Awaiting Codex Review.** Phase 6C-A is
**not accepted** in this pass. **Phase 6C-B has not started.** Phase 6C-A adds the
**execution layer** of the workflow as a new Streamlit page,
`pages/9_Trading_Desk.py`, with three sections: (1) **Holdings Monitor** — manual
position entry persisted to `data/holdings.json` with a four-signal **Thesis
Invalidation Monitor**; (2) **Order Recommendations** — code-computed entry/exit
levels with an LLM narrative; (3) **Opportunity Watch** — Scanner triple-signal
candidates turned into add-to-holdings setups.

Single acceptance criterion: *"The user can record a position in MU with a thesis,
open the app the next day, and immediately see whether the thesis is intact or
weakening, and what order to consider."*

- **`lib/holdings.py`** (new) — `HoldingRecord` dataclass (`id` uuid4 / `ticker` /
  `shares` / `cost_basis` / `entry_date` / `horizon` / `thesis_text` /
  `thesis_source` / `thesis_signals` / `status` / `closed_date` / `closed_price` /
  `notes`) + the SINGLE read/write API for `data/holdings.json`
  (`load_holdings` → `[]` on absent/corrupt; `save_holdings` → `False` on failure,
  temp-file + `os.replace`; `add_holding` / `update_holding` partial /
  `close_holding` / `get_active_holdings`). All fail-closed; never raises. The
  `data/` directory is created on first write. No DB / vector store.
- **`lib/thesis_monitor.py`** (new) — `ThesisCheckResult` + four independent,
  fail-closed signals: **A. News** (Finnhub `/company-news` 7d → ONE LLM call →
  `news_sentiment`/`thesis_relevant`/`key_development`; cached TTL=14400 keyed
  `(ticker, date)`), **B. EPS** (reuses `signal_engine.fetch_fundamental_signals`;
  flags `deteriorating`), **C. Technical breakdown** (`lib.technical.snapshot()` —
  loss of SMA200 entered above, RSI<30, or ADX>30 with >10% under cost),
  **D. Macro** (`macro_regime_result` risk_off/transition for short/mid only;
  long not flagged by macro alone). `thesis_status` is computed
  DETERMINISTICALLY by `compute_thesis_status` — `intact` (0 flags) / `watch`
  (1) / `weakening` (2) / `broken` (3+ OR technical_breakdown alone OR negative
  thesis-relevant news). `is_normal_pullback` (below cost AND above SMA200 AND
  RSI 35–50) distinguishes noise from a break. `run_thesis_monitor` runs active
  holdings in parallel (`ThreadPoolExecutor` max_workers=4) with a 4-hour
  in-process result cache keyed `(holdings signature, regime, date)` — NOT
  persisted.
- **`lib/order_advisor.py`** (new) — `compute_price_levels` is **pure code, no
  LLM**: entry zone (support / cost×0.97 .. price×1.01), ATR-based stop
  (cost−2×ATR or SMA200, nearer to price), target (resistance or cost+3×ATR),
  ATR(14), support/resistance (swing lows/highs, 20-day), volume_trend,
  candlestick_pattern (doji/engulfing/hammer/shooting_star/none — documented
  rules), `risk_reward_ratio` = (target−entry)/(entry−stop), and Kelly-lite
  `position_size_pct` (win_rate 0.55 assumed, half-Kelly, clamped 2%–10%).
  `data_source` live/fixture (fail-closed). `generate_order_narrative` is ONE LLM
  call that only synthesizes a narrative over the computed levels (action
  add|hold|trim|exit|wait, stop rationale, R:R<1.5 warning, candlestick note) —
  it invents no numbers; cached TTL=3600 keyed
  `(ticker, thesis_status, baseline_action, macro_regime, lang)`; zh via
  `translator`; fail-closed to a deterministic baseline narrative.
  `OrderRecommendation` / `OrderNarrative` / `PriceLevelResult` dataclasses.
- **`pages/9_Trading_Desk.py`** (new) — three sections per the spec; Thesis
  Monitor auto-runs on load when `trading_desk_last_refresh` is None or stale
  (>14400s); Section 1 renders active holdings as a SINGLE filterable table
  (status + horizon selectboxes; columns ticker / shares / cost / current price /
  P&L% / horizon / colored status badge / truncated key alert / per-row Edit), with
  inline, MUTUALLY-EXCLUSIVE Add and Edit/Close forms rendered below the table;
  Add Position form supports cockpit/scanner thesis import (`cockpit_all_signals`);
  Order Recommendation cards (broken-thesis holdings shown separately, exit-only);
  Opportunity Watch from `cockpit_triple_signals`. Never writes `holdings.json`
  directly — all access via `lib/holdings.py`.
- **`ui_utils.py`** (modified, additive only) — EN/ZH `nav_p9` + `td_*`
  translation keys and one `st.page_link("pages/9_Trading_Desk.py", ...)` in
  `render_sidebar`, positioned after Individual Stock Research (`nav_p4`) and
  before Investment Cockpit (`nav_p7`).
- **Tests:** new mock-only
  `scripts/test_reliability_phase_6c_trading_desk.py` **115/115**. Regressions:
  Phase 6B v3 189/189; Phase 6A 336/336; Phase 5S 116/116.
- **Guardrails honored:** holdings persist ONLY to local `data/holdings.json`; no
  DB / vector store; no paid API (yfinance + Finnhub free tier); no broker / order
  / execution capability; no order ticket / broker payload;
  `approved_for_execution` absent everywhere; all data calls fail-closed with
  fixture fallback. `lib/macro_regime.py`, `lib/macro_data.py`,
  `lib/workflow_state.py`, `lib/llm_orchestrator.py`, `.claude/agents/*`, and
  pages 1–8 not modified; `ui_utils.py` only gained `t()` keys + one sidebar link.
- Design doc: `docs/reliability_phase_6c_a_trading_desk.md` (new).

> Next step: Codex review of Phase 6C-A. Recommended next phase after acceptance
> is **Phase 6C-B — Investment Cockpit Rebuild** (not started).

---

## Phase 6B v3 — Horizon-Native Three-Track Signal Scoring — Implemented; Awaiting Codex Review

**Phase 6B v3 — Horizon-Native Signal Scoring — Implemented; Awaiting Codex
Review.** Phase 6B v3 is **not accepted** in this pass. **Phase 6C has not
started.** Phase 6B v3 replaces the v2 single composite score with **three
INDEPENDENT horizon scores** (short / mid / long), each with its own
deterministic weighting, and merges **catalyst detection** into the existing
single Layer-2 LLM narrative call. The Scanner renders results as **signal
cards** with horizon-checkbox filtering, and triple-hit candidates are staged to
`st.session_state` for a future Cockpit integration.

- **`lib/signal_engine.py`** — new `CandidateSignal` dataclass (subclasses the v2
  `TickerSignalResult` so existing dual-track consumers keep working — preserves
  `composite_score` / `horizon_fit` / `track_a` / `track_b` / `candidate_type` /
  `isinstance`). New fields: `short_score` / `mid_score` / `long_score` /
  `horizons_hit` / `signal_strength` (`triple`/`double`/`single`/`none`) /
  `catalyst_summary` / `catalyst_horizon` / `catalyst_recency` /
  `already_priced_in` / `narrative_stage` / `narrative_theme_tags` /
  `eps_revision_direction` / `valuation_percentile` / `entry_quality_label` /
  `track_b_score` / `key_signals` (≤5, code-generated) / `data_coverage`.
  - **SHORT** (sum 1.0): `technical_momentum` ×0.40 (RSI band + ADX/Vol/SMA200
    bonuses) + `catalyst_score` ×0.35 (catalyst horizon/recency, ×0.5 if
    `already_priced_in`) + `momentum_continuation` ×0.25 (1M return). Hit ≥ 0.65.
  - **MID** (sum 1.0): `eps_revision` ×0.35 + `narrative_stage` ×0.30 (+0.10 if
    macro-aligned) + `valuation` ×0.20 + `quality_composite` ×0.15. Hit ≥ 0.60.
  - **LONG** (sum 1.0): `valuation` ×0.35 + `quality_composite` ×0.35 +
    `narrative_stage` ×0.20 + `macro_alignment` ×0.10. Hit ≥ 0.55.
  - **Catalyst detection merged into the single `llm_narrative_match` call** (no
    extra LLM request; same TTL=3600 cache). The widened prompt requests
    `catalyst_summary` / `catalyst_horizon` / `catalyst_recency` /
    `already_priced_in` alongside the prior narrative fields; on any parse
    failure all catalyst fields fail-closed to safe values (`""` / `[]` /
    `"none"` / `False`). `score_ticker()` now returns a `CandidateSignal`;
    `build_candidate_signal()` assembles it. `key_signals` priority: triple badge
    → EPS inflection → catalyst → narrative+themes → entry quality → undervalued
    → ALT_SIGNAL trigger. Track A / Track B architecture and the standalone
    Track B trigger (≥ 0.7 → `ALT_SIGNAL`, still gets horizon scores) preserved.
- **`lib/candidate_generator.py`** — `generate_candidates()` returns
  `list[CandidateSignal]`, sorted triple → double → single → none (within each
  group by the average of (short+mid+long)/3 descending). After scoring it writes
  `st.session_state["cockpit_triple_signals"]` (triple hits) and
  `["cockpit_all_signals"]` (all candidates, each with `signal_strength` +
  `timestamp`) — review-only Cockpit hand-off; fail-closed. Universe construction
  / `UniverseConfig` / cache key unchanged.
- **`pages/3_Scanner.py`** — the candidate table is replaced by **signal cards**
  (`st.container(border=True)`): Row 1 ticker + signal_strength badge
  (triple=gold `#d4a017` border + 🔥, double=green, single=blue, none=gray) +
  candidate_type badge; Row 2 three color-coded score pills with ✓ (hit) / ○
  (below); Row 3 catalyst summary (⚡) + horizon tags + recency +
  `already_priced_in` warning; Row 4 first 3 key signals; Row 5 collapsed
  Details expander (full key_signals, EPS / valuation / entry, narrative + theme
  tags, Track A / Track B sub-scores). Three horizon checkboxes (短线/中线/长线,
  all default-checked) filter on `horizons_hit`; a `none` signal shows only when
  all three are checked. A summary line counts triple / double / single.
  `SCANNER_SIGNAL_MODE` flag, the universe config, and the entire manual scanner
  below `st.divider()` are preserved.
- **`ui_utils.py`** — additive EN/ZH `scn_sig_filter_label` / `scn_sig_hz_*` /
  `scn_sig_strength_*` / `scn_sig_triple_header` / `scn_sig_priced_in` /
  `scn_sig_details` / `scn_sig_summary` / `scn_sig_eps` / `scn_sig_val` /
  `scn_sig_narr_stage` / `scn_sig_theme_tags` `t()` keys only.
- **Tests:** new mock-only
  `scripts/test_reliability_phase_6b_v3_horizon_scoring.py` **189/189**.
  Regressions: Phase 6B v2 217/217; theme baskets 146/146; Phase 6A 336/336;
  Phase 5S 116/116.
- **LLM-coverage + Layer-1 tuning:** Scanner narrative-depth slider now 10–100
  (default 50); `generate_candidates` default `llm_n=50`, clamp ceiling 100 (S&P
  top-100 LLM coverage 31% @ 30 → 51% @ 50 → 100% @ 100, sharply cutting
  `unknown` narratives). Stale `FI` (yfinance 404) → `FISV` in `SP500_TOP_100`.
  New Layer-1 liquidity floor `_MIN_DOLLAR_ADV = $10M` average daily dollar
  volume (from yfinance `info`; skipped when absent; never consults
  RSI/momentum); `$2B` cap floor + `-50%` price-break retained.
- **Signal-card follow-up fixes:** (1) Chinese translation of the display fields
  (`catalyst_summary` / theme-tag labels / `key_signals`) via `lib/translator.py`
  when `language=="zh"` — English LLM prompt/response unchanged; `lang` threaded
  through `generate_candidates` and added to the `_generate_candidates_cached` +
  `_localize_texts` TTL cache keys; fail-closed. (2) Empty-`theme_tags` fallback
  via a `THEME_BASKETS` constituent reverse-lookup (`label_zh`/`label_en`) plus a
  strengthened taxonomy instruction in the LLM prompt. (3) Track B Finnhub
  free-tier data sources (insider `/stock/insider-transactions`, analyst
  `/stock/recommendation`, unusual news `/company-news`) documented in the v3
  design-doc section.
- **Guardrails honored:** no paid APIs (yfinance + Finnhub free tier only); no
  broker / order / execution; `approved_for_execution` False or absent; no DB /
  vector store / persistence; all data calls fail-closed with fixture fallback.
  `lib/macro_regime.py`, `lib/macro_data.py`, `lib/theme_baskets.py`,
  `lib/workflow_state.py`, `.claude/agents/*`, pages 1–2 and 4–8 (incl.
  `pages/7_Investment_Cockpit.py`, `pages/8_Macro_Dashboard.py`) not modified;
  `ui_utils.py` modified only to add `t()` keys. Phase 6C not started.
- Design doc: `docs/reliability_phase_6b_signal_layer.md` (new **"v3
  Horizon-Native Scoring"** section appended; v1 + v2 content retained).

> Next step: Codex review of Phase 6B v3. Recommended next phase after acceptance
> is **Phase 6C — Holdings & Thesis Monitor** (not started). **Phase 6C has not
> started.**

---

## Phase 6B v2 — Dual-Track Signal Architecture — Implemented; Awaiting Codex Review

**Phase 6B v2 — Dual-Track Candidate Architecture — Implemented; Awaiting Codex
Review.** Phase 6B v2 is **not accepted** in this pass. **Phase 6C has not
started.** Phase 6B v2 refactors the v1 single-pass, momentum-biased scoring in
`lib/signal_engine.py` + `lib/candidate_generator.py` into a **dual-track
candidate architecture** that can surface early-stage opportunities alongside
alternative-data-triggered candidates, both clearly labeled by signal source.
Single acceptance criterion: *"The candidate list can surface a ticker like MU at
cycle bottom — low RSI, far from 52W high, but with improving EPS revision and
narrative alignment — alongside a ticker flagged purely by an unusual
news/insider signal, with both clearly labeled by their signal source."*

- **Track A (main funnel, 70% of composite):** Layer 1 hard filter (code only —
  excludes only on market cap < $2B, a 30-day decline worse than −50%, or
  completely-missing yfinance fundamentals; **never** penalizes low RSI / low
  momentum / far-from-52W-high / low ADX). Layer 2 LLM narrative matching (the
  ONLY LLM in the layer — one call per ticker for the top `llm_n`, default 30,
  range 10–50; `llm_orchestrator` imported **inside** the function; fail-closed
  to a neutral narrative; cached TTL=3600 keyed `(ticker, macro_regime)`). Layer
  3 fundamental validation (code only — `eps_revision_direction` with the
  `inflecting_up` cycle-bottom signal = **a beat AFTER ≥1 miss**, not sustained
  beats; valuation percentile vs a hardcoded sector-median map; gross-margin
  trend; universe-normalized quality composite).
- **Track B (alternative data, 30% of composite, full universe, funnel-free):**
  `insider_buy_signal` (Finnhub /stock/insider-transactions), `unusual_news_signal`
  (Finnhub /company-news keyword scan), `analyst_revision_signal` (Finnhub
  /stock/recommendation), weighted insider 40% / unusual-news 35% / analyst 25%.
  A Track B composite **≥ 0.7** is a standalone trigger → the ticker enters the
  pool labeled **ALT_SIGNAL** regardless of Track A.
- **Composite / scoring:** Track A weights EPS 0.30 / narrative 0.25 / valuation
  0.20 / margin 0.15 / quality 0.10, then an entry-quality modifier (good **×1.1**
  BOOST / fair ×1.0 / extended ×0.85 / avoid ×0.7). Low RSI + far-from-52W-high →
  "good" entry quality (an MU-style cycle-bottom **boost**, not a penalty). Funnel
  composite = 0.7×Track A + 0.3×Track B; ALT_SIGNAL composite = Track B score.
  `candidate_type` ∈ {FUNNEL, ALT_SIGNAL, BOTH}.
- **`pages/3_Scanner.py`:** adds an LLM narrative-depth slider (10–50, default 30,
  est `~llm_n×2`s) passed to `generate_candidates`, a color-coded **Type** column
  (FUNNEL=blue / ALT_SIGNAL=orange / BOTH=green), a Track A / Track B sub-score
  expander, and the triggering Track B signal in Key Signals for ALT_SIGNAL rows.
  `SCANNER_SIGNAL_MODE` flag and the entire manual scanner preserved.
- **`ui_utils.py`:** additive EN/ZH `scn_sig_llm_*` / `scn_sig_col_type` /
  `scn_sig_subscores` / `scn_sig_col_track_*` / sub-signal column keys only.
- **Tests:** new mock-only `scripts/test_reliability_phase_6b_v2_dual_track.py`
  **217/217**. Regressions: Phase 6A 336/336; Phase 5S 116/116. The Phase 6B **v1**
  test `scripts/test_reliability_phase_6b_signal_layer.py` is **superseded** by v2
  and now reports **211 passed, 1 failed** — the single failing assertion (7.1)
  asserts the *v1* invariant that `signal_engine.py` imports/calls no
  `llm_orchestrator`, which v2 deliberately reverses by introducing the
  in-function Layer-2 LLM import. This is the only by-design v1 regression; all
  other v1 assertions still pass.
- **Guardrails honored:** no paid APIs (Quiver Quantitative and Unusual Whales
  **not** used — only yfinance + Finnhub free tier); no broker / order /
  execution; `approved_for_execution` False or absent; no DB / vector store /
  persistence; all data calls fail-closed. `lib/macro_regime.py`,
  `lib/macro_data.py`, `lib/workflow_state.py`, `.claude/agents/*`, pages 1–2 and
  4–8 (incl. `pages/7_Investment_Cockpit.py`, `pages/8_Macro_Dashboard.py`) not
  modified; `ui_utils.py` modified only to add `t()` keys. Phase 6C not started.
- Design doc: `docs/reliability_phase_6b_signal_layer.md` (new **"v2 Dual-Track
  Architecture"** section appended; v1 content retained as history).

> Next step: Codex review of Phase 6B v2. Recommended next phase after acceptance
> is **Phase 6C — Holdings & Thesis Monitor** (not started). **Phase 6C has not
> started.**

---

### Phase 6B sub-task — Cross-GICS Theme Basket Extension — Implemented; Awaiting Codex Review

**Current Phase 6B sub-task.** Extends Sector Research with **cross-GICS theme
baskets** alongside the existing GICS sector / subsector coverage. The current
Sector page covers traditional GICS sectors via ETFs (XLK, XLV, …) and
subsectors (SOXX, …); this sub-task adds a new **"Market Themes" tab** covering
cross-GICS investment themes relevant to the current AI-driven cycle. Theme data
is staged for downstream **Scanner universe** consumption (Scanner changes are
**not** part of this sub-task — next step).

- **New `lib/theme_baskets.py`** — hardcoded `THEME_BASKETS` (11 themes, source
  documented "manually curated, June 2026"): `model_training`, `hbm_memory`,
  `optical_interconnect`, `datacenter_infra`, `ai_power`, `cloud_data_platform`,
  `ai_software`, `semiconductor_equipment` (SOXX), `ai_robotics` (BOTZ),
  `biotech_ai` (XBI), `defense_space` (ITA). `ThemeMomentumResult` dataclass
  (theme_key / label_en / label_zh / constituents / etf / return_1m/3m/6m /
  momentum_score 0–1 / data_source ∈ {etf, equal_weight, fixture}).
  `compute_theme_momentum(theme_key, period="3mo")` — ETF themes use ETF price
  returns (data_source="etf"); ETF-less themes use the **equal-weight average**
  return across constituents via yfinance (data_source="equal_weight"); any fetch
  failure fails **closed** to a deterministic fixture (data_source="fixture").
  `compute_all_themes(period="3mo")` — runs all themes, assigns
  `momentum_score` as the percentile rank of the 3M return across all themes,
  sorts desc, cached `st.cache_data(ttl=1800)`. Hand-off helpers
  `send_top_theme_to_scanner` / `send_all_themes_to_scanner` write
  `st.session_state["theme_universe"]` + `["theme_universe_label"]` (review-only;
  no execution). All functions `try/except` fail-closed.
- **`pages/2_Sector.py`** — existing flat body wrapped (unchanged) into a
  **Sector Analysis** tab; new **Market Themes** tab added alongside it. The new
  tab shows a color-coded theme momentum heatmap (Theme / 1M / 3M / 6M /
  Momentum Score 0–100 / Data Source, sorted by score desc), per-theme expanders
  (constituent 1M/3M returns via `load_ohlcv`, a Plotly bar of constituent 3M
  returns sorted desc, description text EN/ZH), a per-theme **Analyze** button
  (calls `analyze_theme_basket` only on click), and **Send top theme** / **Send
  all theme constituents** Scanner hand-off buttons. No existing tab content or
  logic modified.
- **`lib/llm_orchestrator.py`** — additive `analyze_theme_basket(theme_key,
  momentum_result, macro_regime, lang)` mirroring `analyze_sector_full()`;
  returns JSON `macro_alignment` / `narrative_stage`
  (early|growing|mature|cooling) / `key_catalysts` / `risk_factors` /
  `horizon_bias` / `summary`; bilingual via the existing `add_bilingual` pattern;
  fail-closed.
- **`ui_utils.py`** — additive EN/ZH `theme_*` + `p2_tab_sector` `t()` keys only.
- **`scripts/test_reliability_theme_baskets.py`** — mock-only (fake yfinance);
  **137/137**. Asserts the 11 themes + required fields, the dataclass fields,
  equal_weight vs etf data sources, sorted-desc momentum in [0,1], the
  `theme_universe` hand-off (mock `st`), `analyze_theme_basket` existence /
  fail-closed, and no `approved_for_execution=True` in any modified file.
- **Guardrails honored:** `lib/workflow_state.py`, `.claude/agents/*`, pages 1 and
  3–8 (incl. `pages/7_Investment_Cockpit.py`, `pages/8_Macro_Dashboard.py`) not
  modified; `lib/llm_orchestrator.py` only gained a new analysis function;
  `ui_utils.py` only gained `t()` keys; no broker / order / execution; no DB /
  vector store / persistence; all data calls fail-closed with fixture fallback;
  no paid APIs (yfinance only); `approved_for_execution` remains False or absent.
- **Validation:** `scripts/test_reliability_theme_baskets.py` 137/137;
  `scripts/test_reliability_phase_6b_v2_dual_track.py` 217/217 regression;
  `scripts/test_reliability_phase_6a_live_data.py` 336/336 regression;
  `scripts/test_reliability_phase_6b_signal_layer.py` 211 passed / 1 failed
  (the pre-existing by-design v1 7.1 regression, unrelated to this sub-task).

> Next step: **Scanner universe integration** — done (see the sub-task below).

---

### Phase 6B sub-task — Scanner Universe Integration — Implemented; Awaiting Codex Review

**Current Phase 6B sub-task — COMPLETE (implemented).** Integrates the cross-GICS
theme baskets into Scanner **universe construction** and adds a **Universe
Configuration** UI to the Scanner page. The Scanner can now build its candidate
universe from a user-shaped mix of the S&P 500 top-100 anchor, selected theme
baskets, the Sector Research "Send to Scanner" hand-off, manual tickers, and
`research_state` subsector constituents.

- **`lib/candidate_generator.py`** — new `UniverseConfig` dataclass
  (`include_sp500_top100: bool = True`, `selected_themes: list = []`,
  `manual_tickers: list = []`, `max_size: int = 150`) and new
  `build_universe(config) -> list[str]`. Source order (deduped, first-wins,
  fail-closed): (1) `SP500_TOP_100` if `include_sp500_top100`; (2) each selected
  theme's constituents from `THEME_BASKETS`; (3)
  `st.session_state["theme_universe"]` if set by the Sector hand-off; (4)
  `manual_tickers`; (5) `research_state` subsector constituents. Capped at
  `config.max_size`. `generate_candidates(macro_regime, top_n, llm_n, config=None)`
  now accepts an optional `UniverseConfig` — when provided the universe is built
  by `build_universe`, when `None` the legacy `get_universe()` is used (backward
  compatible). The assembled universe (a hashable tuple) is now part of the
  `st.cache_data` key — so each universe configuration caches separately.
  Legacy `get_universe()` is preserved unchanged.
- **`pages/3_Scanner.py`** — a **Universe Configuration** expander is added above
  the AI Signal Candidates section: an "Include S&P 500 top 100" checkbox
  (default True), an "Add theme baskets" multi-select over all 11 `THEME_BASKETS`
  (label_en/label_zh by language), a comma-separated "Add tickers manually" text
  input, a "Max universe size" slider (50–300, default 150, step 25), and a live
  "Current universe: N tickers" caption (computed via `build_universe` with **no**
  market-data fetch). When `st.session_state["theme_universe"]` is set, an info
  banner ("Theme pre-loaded from Sector Research: {label} ({N} tickers)") with a
  **Clear** button is shown. The constructed `UniverseConfig` is passed to
  `generate_candidates(..., config=_uni_config)`. The manual scanner and the
  Phase 6B v2 dual-track section are preserved.
- **`ui_utils.py`** — additive EN/ZH `scn_uni_*` `t()` keys only (`scn_uni_title`,
  `scn_uni_sp500`, `scn_uni_themes`, `scn_uni_manual`, `scn_uni_max`,
  `scn_uni_current`, `scn_uni_preloaded`, `scn_uni_clear_btn`).
- **`scripts/test_reliability_scanner_universe.py`** (new) — mock-only / offline;
  **42/42**. Asserts the `UniverseConfig` fields + defaults, `build_universe`
  max_size cap + dedup + theme inclusion + manual inclusion + `theme_universe`
  session_state hand-off, `generate_candidates` `config` parameter, the Universe
  Configuration expander wiring in `pages/3_Scanner.py`, the EN/ZH `scn_uni_*`
  keys, and no positive `approved_for_execution` in any modified file.
- **Guardrails honored:** `lib/signal_engine.py` logic, `THEME_BASKETS`
  definitions, `lib/workflow_state.py`, `.claude/agents/*`, and pages 1–2 / 4–8
  not modified; `ui_utils.py` only gained `t()` keys; no broker / order /
  execution; `approved_for_execution` False or absent; no DB / vector store /
  persistence; no paid APIs (universe size preview is a pure offline set-union).
- **Validation:** `scripts/test_reliability_scanner_universe.py` 42/42;
  `scripts/test_reliability_theme_baskets.py` 137/137 regression;
  `scripts/test_reliability_phase_6b_v2_dual_track.py` 217/217 regression;
  `scripts/test_reliability_phase_6a_live_data.py` 336/336 regression.

> Next step: Codex review. Recommended next phase after acceptance is
> **Phase 6C — Holdings & Thesis Monitor** (not started).

---

### Historical — Phase 6B v1 (single-pass; superseded by v2 above)

**Phase 6B — Stock Selection Signal Layer (v1) — Implemented; Awaiting Codex Review.**
Phase 6B is **not accepted** in this pass. **Phase 6C has not started.** Phase 6B
upgrades the Scanner from manual ticker-pool entry to an **AI-generated candidate
list built from real free signals** — alternative data, EPS-revision trend,
narrative attribution, and entry quality — ranked by a deterministic composite
score and surfacing early-stage opportunity signals, not just the strongest
momentum names. Acceptance criterion: *"The user opens the Scanner page and sees
an AI-generated candidate list based on real signals, without manually entering a
ticker pool."*

- **New `lib/signal_engine.py`** — multi-factor per-ticker signals
  (`fetch_fundamental_signals` / `fetch_narrative_signals` / `compute_entry_quality`
  / `score_ticker`) returning `FundamentalSignals` / `NarrativeSignals` /
  `EntryQualityScore` / `TickerSignalResult`. Sources: yfinance fundamentals +
  Finnhub free tier (`/stock/recommendation`, `/stock/earnings`, `/company-news`)
  + the existing `lib/technical.snapshot()` engine. Composite weights: fundamental
  quality 30%, EPS surprise trend 25%, entry quality 25%, narrative strength +
  macro alignment 20%. **No LLM** — narrative/theme attribution is keyword-rule
  based. Every fetch is `try/except` fail-closed and cached
  `st.cache_data(ttl=1800)`.
- **New `lib/candidate_generator.py`** — `get_universe()` (hardcoded S&P 500
  top-100 by market cap + `research_state` subsector constituents, deduped, capped
  150) and `generate_candidates(macro_regime, top_n=20)` (`ThreadPoolExecutor`
  max_workers=8 + `st.progress`, sorted by composite score, cached TTL=1800).
- **`pages/3_Scanner.py`** — adds an **AI候选信号 / AI Signal Candidates** section
  at the top, gated by a single feature flag `SCANNER_SIGNAL_MODE = True` (when
  `False`, the page behaves exactly as before Phase 6B). Generate-Candidates
  button → `generate_candidates()` stored in `st.session_state["signal_candidates"]`;
  ranked table (Ticker / Composite Score colored green>0.65/yellow/red<0.4 / Entry
  Quality / Horizon Fit short-mid-long / first 2 Key Signals); Send-to-Manual-
  Scanner button that pre-fills the existing manual pool. The manual scanner is
  preserved unchanged below a `st.divider()`.
- **`ui_utils.py`** — additive EN/ZH `scn_sig_*` chrome keys only (no existing key
  renamed/removed).
- **Test**: `scripts/test_reliability_phase_6b_signal_layer.py` — mock-only (no
  real API calls); **212/212 passing**. Regressions: Phase 6A 336/336; Phase 5O
  page-8 766/766; Phase 5S closeout 116/116.
- **Cross-page macro regime sharing (follow-up, Plan A)**: the macro regime flows
  to the Scanner. `pages/8_Macro_Dashboard.py` publishes
  `st.session_state["macro_regime_result"]` (regime / confidence / horizon_bias /
  data_coverage) after a successful `classify_regime()` (additive, no existing
  macro rendering/logic change). `pages/3_Scanner.py` (Plan A) obtains the regime
  **directly** via `classify_regime(fetch_all_macro())` before
  `generate_candidates()` — both fail-closed + `st.cache_data`-cached, so a prior
  macro-page visit is a free cache hit and an unvisited session fetches live —
  publishes the same `macro_regime_result` dict, shows the loaded regime status
  (regime + confidence + coverage; **no** "visit macro page" hint), and on error
  reuses a prior regime / `"unknown"`. `generate_candidates` is a normalizing
  wrapper over the cached worker whose `st.cache_data` key is `(macro_regime,
  top_n)` so different regimes cache separately. Phase 5O page-8 regression
  766/766.
- **Guardrails honored**: `lib/llm_orchestrator.py`, `lib/workflow_state.py`,
  `.claude/agents/*`, pages 1–2 and 4–7 untouched (`pages/8_Macro_Dashboard.py`
  modified additively only — cross-page publish, no behavior change); the live AI
  research workflow (incl. `pages/1_Overview.py`) and the existing manual scanner
  are unchanged; no
  broker/order/execution; no order tickets / broker payloads / account IDs /
  execution IDs / executable trade instructions; `approved_for_execution` remains
  False or absent; no DB / vector store / persistence; no new LLM calls; only free
  APIs (Quiver Quantitative **not** included — deferred to a later phase).
- Design doc: `docs/reliability_phase_6b_signal_layer.md`.

> Next step: Codex review of Phase 6B. Recommended next phase after acceptance is
> **Phase 6C — Holdings & Thesis Monitor** (not started). **Phase 6C has not
> started.**

---

## Phase 6A — Live Data Integration — Accepted

**Phase 6A — Live Data Integration — Accepted.** Phase
6A replaces fixture/mock data on the Macro Dashboard with **live, free** market
and macro data so the user opens the app and sees **real current macro
conditions**.

- **New `lib/macro_data.py`** — the single place that fetches live macro data
  from free sources only (yfinance for `^VIX` + ETF proxies QQQ/IWM/SPY/GLD/USO/
  TLT/HYG; FRED for DGS10/DGS2/T10YIE/BAMLH0A0HYM2/DTWEXBGS/PAYEMS/CPIAUCSL/
  PPIACO via `FRED_API_KEY`; Finnhub free tier `/stock/social-sentiment` +
  `/news?category=general` via the existing `FINNHUB_API_KEY`). Eight public
  `fetch_*` functions, each individually `try/except` fail-closed and cached with
  `st.cache_data(ttl=900)`. Returns a `MacroDataResult` dataclass with a
  `data_source` ("live"/"fixture") per metric group, a `timestamp`, and a
  `data_coverage` float (fraction of groups fetched live).
- **New `lib/macro_regime.py`** — deterministic `classify_regime(MacroDataResult)
  -> MacroRegimeResult` (regime ∈ {risk_on, risk_off, transition, degraded};
  confidence; horizon_bias short/mid/long; key_signals; opportunity_posture;
  data_coverage). Hard guard: `data_coverage < 0.5` ⇒ `degraded`. No LLM —
  fully code-based, inline-documented thresholds.
- **`pages/8_Macro_Dashboard.py`** — adds a **Live Macro Conditions** section
  (LIVE/FIXTURE badge per metric group, data-coverage indicator, per-group
  freshness, muted inline fallback warnings) gated by a single feature flag
  `MACRO_LIVE_MODE = True`. When `False`, all API calls are skipped and the page
  uses fixture data exactly as before Phase 6A. The Phase 5O fixture regime tabs
  are preserved unchanged; the page never crashes (fail-closed).
- **`ui_utils.py`** — additive EN/ZH `macro_live_*` chrome keys (no existing key
  renamed/removed).
- **CNN Fear & Greed substitution**: no reliable free API exists, so a
  **VIX-derived fear/greed proxy** is computed (inverse of the latest VIX's
  trailing-252-day percentile, scaled to 0–100), documented in code + doc.
- **Test**: `scripts/test_reliability_phase_6a_live_data.py` — mock-only (no real
  API calls); **336/336 passing**. Regressions: Phase 5S closeout and Phase 5R
  UI/UX polish still pass.
- **Guardrails honored**: `lib/llm_orchestrator.py`, `lib/workflow_state.py`,
  `.claude/agents/*`, pages 1–6, and `pages/7_Investment_Cockpit.py` untouched;
  live AI research workflow behavior unchanged; no broker/order/execution; no
  order tickets / broker payloads / account IDs / execution IDs / executable
  trade instructions; `approved_for_execution` remains False or absent; no DB /
  vector store / persistence; no new LLM calls; only free APIs.
- Design doc: `docs/reliability_phase_6a_live_data_integration.md`.

> Note: the Phase 5S closeout artifacts (`docs/ai_dev_state/PHASE_5_CLOSEOUT.md`,
> `docs/reliability_phase_5s_productization_closeout.md`) reflect the **pre-6A**
> snapshot and remain unchanged; Phase 5S itself is still **Implemented; Awaiting
> Codex Review**. **Phase 6A is now Accepted**; the active task is **Phase 6B —
> Stock Selection Signal Layer** (Implemented; Awaiting Codex Review).

---

## Purpose

This file is the persistent repo-level context checkpoint for AI-assisted development.
Future Claude Code sessions should read this file before working.
Do not rely on prior chat context.

---

## Architecture Principle

> **Deterministic computation, agentic interpretation, auditable synthesis.**

- Deterministic code computes facts.
- `ToolResult` stores evidence-bearing outputs with versioned, immutable outputs.
- `EvidenceRef` binds agent findings to specific `ToolResult` fields.
- `AgentResult` is constrained JSON, not free-form LLM reasoning.
- `validate_agent_result()` audits evidence binding and schema compliance.
- `ValidationAggregate` summarizes all validation warnings per run.
- `StalenessReport` flags freshness risk on timestamps across all domains.
- Critic/Debate layers (future) challenge claims; they do not fabricate data.

---

## Global Guardrails

Unless a phase explicitly allows otherwise, **do not modify**:

- `app.py`
- `pages/*`
- `lib/llm_orchestrator.py`
- `.claude/agents/*`
- existing live prompt files
- `lib/valuation.py`
- `lib/technical.py`
- `lib/rotation.py`
- `lib/data_fetcher.py`
- `lib/workflow_state.py`
- existing Streamlit UI
- current live workflow behavior
- existing news/Finnhub/data-fetch behavior

**Do not introduce** (unless explicitly scoped):

- live app integration
- Streamlit UI changes
- live LLM calls
- live API / data fetching
- broker integration
- order placement
- investment conclusions from schema/helper phases
- agent implementations

---

## Roadmap Status

### Accepted

| Phase | Description |
|-------|-------------|
| Phase 6A | Live Data Integration — replaces fixture/mock data on the Macro Dashboard with live, free macro/market data (yfinance + FRED + Finnhub free tier) and a deterministic derived regime (`lib/macro_data.py`, `lib/macro_regime.py`, `pages/8_Macro_Dashboard.py` live section gated by `MACRO_LIVE_MODE = True`, additive `ui_utils.py` `macro_live_*` keys). Fail-closed per metric group; no broker/order/execution; `approved_for_execution` False or absent; no paid APIs. Phase 6A test 336/336. **Accepted** (cleanup from the Phase 6B pre-task; promoted from Implemented; Awaiting Codex Review). |
| Phase 0 | Reliability Foundation (schemas, RunContext, EvidenceStore, validators) |
| Phase 0.1 | Reliability Hardening |
| Phase 0.2 | ToolResult Adapter Planning |
| Phase 1A | Isolated Valuation ToolResult Integration |
| Phase 1B | Isolated Technical ToolResult Integration |
| Phase 1C | Isolated Scanner/Rotation ToolResult Integration |
| Phase 1D | AgentResult JSON Contract / LLM Output Adapter |
| Phase 1E | Prompt Contract Drafting / Constrained Agent Interface |
| Phase 1F | Mock Constrained Agent Roundtrip |
| Phase 1G | Feature-Flagged Reliability Orchestration Design |
| Phase 2A | Feature Flag Config Foundation |
| Phase 2B | Investment Horizon Schema Foundation |
| Phase 2C | Macro Data + ToolResult Schema Foundation |
| Phase 2D | Allocation / Position Sizing Tool Schema Foundation |
| Phase 2E | Option Data + Strategy Tool Schema Foundation |
| Phase 2F | News ToolResult Wrapper Foundation |
| Phase 2G | Catalyst / Earnings / Estimate Revision Schema Foundation |
| Phase 2H | Validation Aggregator |
| Phase 2H Cleanup | ValidationAggregate consistency / target test / docs wording cleanup |
| Phase 2I | Staleness Checker |
| Phase 2J | Critic Agent v0.1 |
| Phase 2K | Reliability Evaluation Harness (12 cases, 100% detection, fail-closed, 91/91 tests) |
| Phase 2 Closeout | Closeout docs, roadmap reconciliation, smoke test (107/107), full regression (23/23 scripts). |
| Phase 3A | Validated Agent Orchestration Skeleton — precomputed artifact passthrough, stable ToolResult payload, 81/81 tests (includes Phase 3A export smoke test). See `docs/reliability_phase_3a_validated_orchestration_skeleton.md`. |
| Phase 3B | Horizon-aware Synthesis Skeleton — content-sensitive evidence_id, 67/67 tests. See `docs/reliability_phase_3b_horizon_aware_synthesis_skeleton.md`. |
| Phase 3C | Macro Agent v0.1 Skeleton — standalone dry-run/mock-only. 8 enums, 7 Pydantic models, 16 helpers. Consumes macro ToolResults / MacroSnapshot / ValidationAggregate / StalenessReport / CriticResult. Produces MacroRegimeAssessment, MacroSectorBias, MacroHorizonImpact, MacroAgentResult. Evidence-aware, validation-aware, staleness-aware. AgentResult bridge + ToolResult wrapper. 101/101 tests. Full regression pass. Does NOT modify live app behavior. See `docs/reliability_phase_3c_macro_agent_v0_1_skeleton.md`. |
| Phase 3D | Debate by Horizon Skeleton — accepts Phase 3B `card.horizon` and `evidence_summary.supporting_evidence_ids`; standalone dry-run/mock-only. 54/54 tests. Full regression pass. See `docs/reliability_phase_3d_debate_by_horizon_skeleton.md`. |
| Phase 3E | DecisionPacket Schema / Decision Synthesis Skeleton — targeted evidence handoff fix applied: reads Phase 3B `card.evidence_summary.supporting_evidence_ids` and Phase 3C `regime_assessment.supporting_evidence_ids`, `horizon_impacts[*].evidence_ids`, `sector_biases[*].evidence_ids`; source IDs use `macro_agent_id` and `orchestration_id`. Standalone dry-run/mock-only. 58/58 tests. Accepted. See `docs/reliability_phase_3e_decision_packet_skeleton.md`. |
| Phase 3F | Human Review / Feedback Schema Skeleton — Codex fixes applied: (1) critical feedback always blocks regardless of revision_requests; (2) regression test 37b added; (3) Phase 3F symbols added to __all__; (4) __all__ smoke test 48b and source_id aggregation test 48c added. 57/57 tests + 28/28 regression = 113/113 total. Accepted. |
| Phase 3G | Offline Review Loop / Reliability Run Report Skeleton — status precedence corrected (block > needs_revision > failed > complete > unknown); HR changes_requested beats DP fail. 151/151 tests. Full regression pass (7 prior Phase 3 scripts). Accepted. See `docs/reliability_phase_3g_review_loop_skeleton.md`. |
| Phase 3 Closeout | Closeout docs, roadmap reconciliation, full regression (625 Phase 3 tests + 107 Phase 2 regression = 732 total, 8/8 scripts). See `docs/ai_dev_state/PHASE_3_CLOSEOUT.md`. Accepted. |
| Phase 4A | Reliability Integration Boundary Contract — 3 enums, 2 Pydantic models, 3 functions; DISABLED/SHADOW/ENFORCED modes; deterministic, side-effect-free; 64/64 tests. See `docs/reliability_phase_4a_integration_boundary.md`. **Reclassified: accepted early integration infrastructure. Does not start Roadmap Phase 4 Memory.** |
| Phase 3R-0 | Roadmap Alignment Reconciliation — gap analysis documented; Phase 3R backfill sequence established; ROADMAP_V4_ALIGNMENT.md created. |
| Phase 3R-A | Event Intelligence Agents Skeleton — 10 Literal aliases, 7 Pydantic models, 7 helpers; CatalystAssessment, NewsImpactAssessment, EarningsPlaybookAssessment, EstimateRevisionAssessment, EventIntelligenceBundle, EventIntelligenceSummary, EventIntelligenceReport; ToolResult adapter; 152/152 tests. Accepted. See `docs/reliability_phase_3r_event_intelligence.md`. |
| Phase 3R-B | Trade Plan Drafting Agent Skeleton — 6 Literal aliases, 7 Pydantic models, 6 helpers; TradePlanDraft, TradePlanInputBundle, TradePlanSummary, TradePlanReport; ToolResult adapter; approved_for_execution permanently False; 689/689 tests. Accepted. See `docs/reliability_phase_3r_trade_plan.md`. |
| Phase 3R-C | Allocation Agent v0.1 Non-live — 5 Literal aliases, 9 Pydantic models, 8 helpers; AllocationPortfolioSnapshot, AllocationPositionSnapshot, AllocationTargetSpec, RiskBudgetConstraint, AllocationCalculation, AllocationAssessment, AllocationInputBundle, AllocationSummary, AllocationReport; 7 deterministic calculators; ToolResult adapter; status/constraint-violation logic; 392/392 tests. Accepted. See `docs/reliability_phase_3r_allocation.md`. |
| Phase 3R-D | Option Expression Agent v0.1 Non-live — 11 Literal aliases (stock added), 8 Pydantic models, 7 helpers; OptionExpressionLeg, OptionMarketSnapshot, OptionStrategyCalculation, OptionExpressionCandidate, OptionExpressionInputBundle, OptionExpressionAssessment, OptionExpressionSummary, OptionExpressionReport; 12 deterministic calculators; ToolResult adapter; candidate selection and status logic; stock/option/no_trade as first-class outputs; no_trade_reason consistency enforced; status precedence corrected; approved_for_execution permanently False; 277/277 tests. Accepted. See `docs/reliability_phase_3r_option_expression.md`. |
| Phase 3R-E | Roadmap Alignment Closeout — closeout document created; state files updated; all Phase 3R tests confirmed passing. See `docs/ai_dev_state/PHASE_3R_CLOSEOUT.md`. Accepted. |
| Phase 4M-A | Research Run Memory Schema — 5 Literal aliases, 6 Pydantic models, 11 public helpers; MemorySourceRef, MemoryEvent, ResearchRunMemoryInputBundle, ResearchRunMemorySummary, ResearchRunMemoryRecord, ResearchRunMemoryIndexEntry; ToolResult adapter; status precedence blocked > needs_review > incomplete > recorded > unknown; approved_for_execution permanently False; Codex fixes applied: deterministic timestamps, full ToolResult record payload, artifact_refs filtering; 165/165 tests. See `docs/reliability_phase_4m_research_memory.md`. Accepted. |
| Phase 4M-B | Thesis Memory by Horizon — 8 Literal type aliases, 7 Pydantic models, 12 public helpers; ThesisAssumption, ThesisInvalidationCondition, ThesisMemoryEvent, HorizonThesisMemoryRecord, ThesisMemoryInputBundle, ThesisMemorySummary, ThesisMemoryReport; ToolResult adapter; status precedence blocked > needs_review > invalidated > active > archived > unknown; initial_status override; approved_for_execution permanently False; deterministic timestamps; duck-typed optional upstream artifacts; 291/291 tests. See `docs/reliability_phase_4m_thesis_memory.md`. Accepted. |
| Phase 4M-C | Catalyst / News / Earnings Memory — 8 Literal type aliases, 6 Pydantic models, 12 public helpers; source_refs dedup polish applied; 307/307 tests. See `docs/reliability_phase_4m_event_memory.md`. Accepted. |
| Phase 4M-D | Allocation Decision Memory — 7 Literal type aliases, 7 Pydantic models, 13 public helpers; ToolResult adapter; make_allocation_memory_record_id() content-sensitive; Section 31 collision tests + Section 32 builder sensitivity + Section 33 direct-function isolated A.1–A.6 tests added; 418/418 tests pass. See `docs/reliability_phase_4m_allocation_memory.md`. Accepted. |
| Phase 4M-E | Option Trade Plan Memory — 8 Literal aliases, 7 Pydantic models, 13 helpers; snapshot_id hash covers all 18 material fields; collect_option_trade_memory_evidence_ids() collects upstream artifact evidence_id; 448/448 tests pass. See `docs/reliability_phase_4m_option_trade_memory.md`. Accepted. |
| Phase 4M-F | Human Feedback Layer — 7 Literal aliases, 8 Pydantic models, 14 helpers; HumanFeedbackSourceRef/TargetRef/Entry/MemoryLogEntry/MemoryRecord/MemoryInputBundle/MemorySummary/MemoryReport; status precedence blocked > needs_review > resolved > recorded > archived > unknown; executed_manually memory-only label; agent_evaluation_flag tracking; ToolResult adapter; HumanFeedbackEntry raises ValueError when decision=="overrode" and override_reason missing/blank; 257/257 tests pass. See `docs/reliability_phase_4m_human_feedback_memory.md`. Accepted. |
| Phase 4M-G | Agent Evaluation — 8 Literal aliases (incl. AgentEvaluationActor), 9 Pydantic models, 15 helpers; AgentEvaluationSourceRef/TargetRef/Signal/Calibration/LogEntry/Record/InputBundle/Summary/Report; status precedence blocked > needs_review > incomplete > evaluated > archived > unknown; `initial_status` is a safe fallback only and never masks stronger conditions; correct/incorrect/partial/inconclusive/false_positive/false_negative/override/rejection tracking; explicit `rejection_count`/`rejection_rate` on Calibration and Summary, surfaced via ToolResult; calibration metrics (accuracy, FP/FN rate, override_rate, rejection_rate, calibration_gap signed in [-1,1]); per-agent / per-horizon / per-grade counts; non-negative validators on Summary count fields; ToolResult adapter; approved_for_execution permanently False; deterministic timestamps; lesson + human_feedback_memory_id linkage; 307/307 tests (Section 31 state-file assertions rewritten 2026-05-27 — first for Phase 4M-H acceptance, then again for Phase 5P planning — to match each newly accepted state; no module/runtime change); full Phase 4M regression PASS; offline/mock-only — no DB, no vector store, no persistence, no broker/order/execution, no prompt/model mutation. See `docs/reliability_phase_4m_agent_evaluation.md`. Accepted. |
| Phase 4M-H | Phase 4 Memory Closeout — closeout document `docs/ai_dev_state/PHASE_4M_CLOSEOUT.md` covering Phase 4M-A through 4M-G coverage map (Research Run Memory, Thesis Memory by Horizon, Catalyst/News/Earnings Memory, Allocation Decision Memory, Option Trade Plan Memory, Human Feedback Layer, Agent Evaluation), Phase 3 reliability backbone composition (Orchestration, DecisionPacket, Human Review/Feedback Schema, Review Loop), Phase 3R roadmap backfill composition (Event Intelligence, Trade Plan, Allocation, Option Expression), architectural boundaries (offline / mock-only, schema/helper-only, no DB, no file persistence, no vector store, no broker/order/execution, no prompt/model mutation, no Phase 4A live wiring), safety-specific notes per memory module (including `executed_manually` as a memory-only label and Agent Evaluation not mutating prompts or agent definitions), known non-blocking notes, and prior closeout recommendation for next phase. Section 31 of `scripts/test_reliability_agent_evaluation.py` rewritten 2026-05-27 to assert current accepted state — no module / runtime change; test passed 304/304 at Phase 4M-H acceptance time and now passes 307/307 after Phase 5P additionally bumped Section 31 assertions (no module / runtime change). Per-phase Phase 4M design docs reconciled to accepted state. Closeout test matrix rerun: Phase 4M 2190 tests + Phase 3/3R regression 2023 tests = **4213 total, 0 failures** at acceptance time (post-Phase-5P current counts: 2193 + 2023 = 4216, still 0 failures). Phase 4M mainline complete. **Accepted.** |
| Phase 5P | Phase 5 Roadmap Decision / Planning — repo-level planning task opening Phase 5. Deliverables: (1) planning document `docs/reliability_phase_5p_roadmap_decision.md` (accepted baseline, README-app ↔ Roadmap v4 relationship, overlay-not-replacement positioning, preserved app capabilities, Phase 5 goals, route comparison A–E, Phase 5A recommendation, full Phase 5A–5H sequence, non-goals / guardrails, forbidden files, acceptance criteria); (2) state-file reconciliation in `PROJECT_STATE.md` and `CURRENT_TASK.md`; (3) documentation-only Section 31 update in `scripts/test_reliability_agent_evaluation.py` so state-file assertions match the newly accepted Phase 4M-H state and the newly active Phase 5P planning phase (no module / runtime change); (4) review-fix pass (2026-05-27) reconciling stale "awaiting review" wording for Phase 4M-H / Phase 4M Closeout in `docs/ai_dev_state/PHASE_4M_CLOSEOUT.md`, plus current-state agent-evaluation test-count update from 304/304 to 307/307 (historical 298 → 304 → 307 narrative preserved). Recommended Phase 5A: **Existing Workflow Memory Adapter + Fixture-backed Memory Query Contract** — protocol/interface + fixture/mock query boundary only; no real DB, no vector store, no production persistence, no live `workflow_state` wiring, no Streamlit integration, no external API, no execution capability. **No runtime / app file modified.** **No DB / vector store / persistence introduced.** **No external API call introduced.** **No broker / order / execution path introduced.** `approved_for_execution` remains `False` everywhere it appears. **Phase 5A implementation has not started.** **Accepted.** |
| Phase 5A | Existing Workflow Memory Adapter + Fixture-backed Memory Query Contract — `lib/reliability/workflow_memory_adapter.py` (ExistingWorkflowSnapshot, ExistingWorkflowStepSnapshot, ExistingPageOutputRef, ExistingWorkflowSynthesisSnapshot, WORKFLOW_STEP_ORDER, WorkflowMemoryBundle, WorkflowToMemoryAdapter Protocol, InMemoryWorkflowToMemoryAdapter, `make_workflow_snapshot_id`); `lib/reliability/phase5_memory_query.py` (MemoryRecordType, MemoryHorizon, MemoryReviewStatus, MemoryQuery, MemoryQueryByTicker, MemoryQueryByRunId, MemoryQueryByHorizon, MemoryQueryByType, MemoryQueryByReviewStatus, MemoryQueryResult, MemoryStoreProtocol, MemoryQueryProtocol alias, FixtureBackedMemoryStore, `build_fixture_memory_store_from_snapshot`); `lib/reliability/phase5_fixtures.py` (one complete original-app-style fixture journey). Read-only fixture-backed query store; deterministic Phase 4M-compatible record IDs; no DB / vector store / file persistence / live `workflow_state` read / Streamlit / Anthropic SDK / external API / broker / order / execution. `approved_for_execution` rejected at snapshot / bundle / result / store-add boundaries. Test suite `scripts/test_reliability_phase_5a_memory_query.py` 175/175 passing. Design doc: `docs/reliability_phase_5a_memory_query_contract.md`. **Accepted.** |
| Phase 5B | Company Research Hub ViewModel Contract — `lib/reliability/company_research_hub.py` adds offline / mock-only deterministic Pydantic view-model contracts: `CompanyResearchHubView`, `CompanyIdentityView`, `EquityResearchPanelView`, `FinancialValuationPanelView`, `PriceVolumeTimingPanelView`, `SourceWorkflowPanelView`, `EvidenceCoveragePanelView`, `ValidationStatusPanelView`, `MissingDataWarningView`, plus `MissingDataPanel` Literal alias and deterministic builder helpers (`build_company_identity_view`, `build_equity_research_panel`, `build_financial_valuation_panel`, `build_price_volume_timing_panel`, `build_source_workflow_panel`, `build_evidence_coverage_panel`, `build_validation_status_panel`, `build_company_research_hub_view`). Builders consume the Phase 5A `MemoryStoreProtocol` / `MemoryQueryResult` and/or an `ExistingWorkflowSnapshot`; missing snapshot returns a safe empty view; missing Equity / Financial / PriceVolume step yields a degraded panel with a `MissingDataWarningView`. Test suite `scripts/test_reliability_phase_5b_company_hub.py` 163/163 passing. Design doc: `docs/reliability_phase_5b_company_research_hub_view_model.md` (status line updated to "Accepted" as part of Phase 5D minor-suggestion cleanup; §4.1 documentation clarification describes memory_query_result-vs-memory_store behavior — Phase 5B runtime / module unchanged). Phase 5A regression `scripts/test_reliability_phase_5a_memory_query.py` still passes 175/175. No live runtime files modified; no Streamlit / live wiring / DB / vector store / persistence / external API / broker / order / execution introduced; Phase 4A not wired in. **Accepted.** |
| Phase 5C | Horizon Decision Cards + ThesisTracker ViewModel Contract — `lib/reliability/phase5_horizon_views.py` adds offline / mock-only deterministic Pydantic view-model contracts: `HorizonDecisionCardsView`, `HorizonDecisionCardView`, `ThesisTrackerView`, `ThesisTrackerRowView`, `ThesisStatusView`, `InvalidationTriggerView`, `ReviewNeededBadgeView`, `MissingEvidenceBadgeView`, `HorizonEvidenceSummaryView`, `HorizonRiskSummaryView`, `HorizonAssumptionView`, `HorizonNextActionView`, plus `HorizonKey` / `HORIZON_ORDER` / `HORIZON_EVIDENCE_KINDS` / `HorizonEvidenceKind` / `CardStatus` literal aliases and deterministic builder helpers. Builders consume Phase 4M-B thesis, Phase 4M-C event, Phase 4M-F human-feedback, and Phase 4M-G agent-evaluation memory through the Phase 5A `MemoryStoreProtocol` / `MemoryQueryResult`. Cards always emitted in canonical `short → medium → long` order; missing thesis yields a safe `"missing"` card with warnings; review_needed signals from events / human feedback / agent evaluation flip the card to `needs_review`. Test suite `scripts/test_reliability_phase_5c_horizon_views.py` 179/179 passing. Design doc: `docs/reliability_phase_5c_horizon_decision_cards_thesis_tracker.md` (status line updated to "Accepted" as part of Phase 5D minor-suggestion cleanup). Phase 5D minor-suggestion cleanup also removed three unused imports (`MEMORY_RECORD_TYPES`, `MemoryQuery`, `MemoryQueryByHorizon`) from `lib/reliability/phase5_horizon_views.py`; the module still passes its full test suite. **Accepted.** |
| Phase 5D | Portfolio / TradePlan / Option Overlay ViewModel Contract — `lib/reliability/phase5_portfolio_views.py` adds offline / mock-only deterministic Pydantic view-model contracts: `PortfolioCockpitView`, `AllocationSummaryView`, `PositionAllocationView`, `RiskBudgetView`, `CashImpactView`, `TradePlanView`, `TradePlanLevelView`, `TradePlanReviewTriggerView`, `OptionOverlayView`, `OptionStrategySummaryView`, `OptionRiskRewardView`, `OptionLiquidityWarningView`, `OptionEventRiskWarningView`, `NoTradeReasonView`, `ExecutionSafetyBannerView`, `MissingPortfolioDataWarningView`, plus `PortfolioDataSource` / `TradePlanLevelKind` / `TRADE_PLAN_LEVEL_KINDS` / `MissingPortfolioPanel` / `OptionOverlayState` literal aliases and deterministic builder helpers (`build_execution_safety_banner`, `build_no_trade_reason_view`, `build_position_allocation_view`, `build_allocation_summary_view`, `build_trade_plan_view`, `build_option_overlay_view`, `build_portfolio_cockpit_view`). Builders consume Phase 4M-D allocation decision memory (`AllocationDecisionMemoryRecord`), Phase 4M-E option trade plan memory (`OptionTradePlanMemoryRecord`), and Phase 4M-F human feedback memory (`HumanFeedbackMemoryRecord`) through the Phase 5A `MemoryStoreProtocol` / `MemoryQueryResult`. `ExecutionSafetyBannerView` is always present on a `PortfolioCockpitView`; `RiskBudgetView` / `CashImpactView` populate only when underlying allocation records carry the corresponding fields; `no_trade` is preserved as first-class option overlay state with no inferred substitute strategy; missing allocation / option records yield safe degraded views with descriptive warnings; missing ticker / no records yields a safe empty cockpit. No Phase 5D class declares `approved_for_execution`; no executable order field (`order_type`, `time_in_force`, `broker_route`, `account_id`, `quantity_to_execute`, etc.) is introduced; the test suite enforces both invariants at field-level and source-substring level. Test suite `scripts/test_reliability_phase_5d_portfolio_trade_option_views.py` covers 212 assertions across 27 sections; 212/212 passing. Design doc: `docs/reliability_phase_5d_portfolio_trade_option_view_model.md` (status line updated from "Implemented — awaiting Codex review" to "Accepted" during Phase 5F pass; no module / runtime change). Phase 5E minor-suggestion cleanup applied during Phase 5E: unused `model_validator` import removed from `lib/reliability/phase5_portfolio_views.py`; Phase 5D test suite still passes 212/212 after cleanup. Phase 5A regression test (`scripts/test_reliability_phase_5a_memory_query.py`) still passes 175/175. Phase 5B regression test (`scripts/test_reliability_phase_5b_company_hub.py`) still passes 163/163. Phase 5C regression test (`scripts/test_reliability_phase_5c_horizon_views.py`) still passes 179/179. **Accepted.** |
| Phase 5E | Cockpit UI Planning Boundary for Existing Streamlit App — documentation/planning-only phase. Phase 5E defines the planning boundary for a future Investment Cockpit UI built on top of the existing README-based Streamlit app, without modifying any of the six existing pages (Overview / Sector / Scanner / Equity / Financial / PriceVolume), the existing five-step AI workflow, `app.py`, `lib/llm_orchestrator.py`, `lib/workflow_state.py`, `research/.workflow_state.json`, or any other live runtime file. Phase 5E adds: (1) planning document `docs/reliability_phase_5e_cockpit_ui_planning_boundary.md` (status updated from "Implemented — awaiting Codex review" to "Accepted" during Phase 5G review cleanup; no module / runtime change); (2) lightweight machine-readable state artifact `docs/ai_dev_state/PHASE_5E_COCKPIT_UI_PLAN.md`; (3) lightweight planning-doc test `scripts/test_reliability_phase_5e_cockpit_ui_planning.py` (136/136 passing). **No live runtime files modified.** **No Streamlit / live wiring / DB / vector store / persistence / external API / broker / order / execution introduced.** **No new Python module added under `lib/reliability/` for Phase 5E.** **No new page added under `pages/` for Phase 5E.** **Phase 4A not wired in.** `approved_for_execution` remains `False` (or absent) everywhere it appears. `no_trade` preserved as first-class option state. **Accepted.** |
| Phase 5F | Shadow Mode Integration Boundary Planning — documentation/planning-only phase. Phase 5F defines the planning boundary for a *future* read-only, feature-flagged shadow mode that could observe completed outputs of the existing five-step workflow and route them through the Phase 5A `MemoryStoreProtocol` / `MemoryQueryResult` boundary into the Phase 5B / 5C / 5D view-model contracts, without changing live workflow behavior, prompts, or outputs. Phase 5F adds: (1) planning document `docs/reliability_phase_5f_shadow_mode_integration_boundary.md` (status updated from "Implemented — awaiting Codex review" to "Accepted" during Phase 5G review cleanup; no module / runtime change); (2) lightweight planning-doc test `scripts/test_reliability_phase_5f_shadow_mode_planning.py` (137/137 passing) asserting required-section existence, planning-only constraints (no Phase 5F Python module under `lib/reliability/`, no Phase 5F page under `pages/`), forbidden-file enumeration, that the doc does not positively authorize `approved_for_execution=True`, that the doc does not positively claim shadow mode / snapshot adapter / Phase 4A is wired/active outside negation contexts, and that the envelope explicitly hardcodes `approved_for_execution = False` and empty `executable_order_fields`. **No live runtime files modified.** **No Streamlit / live wiring / DB / vector store / persistence / external API / broker / order / execution introduced.** **No actual shadow mode runner / snapshot adapter / comparison harness introduced.** **No new Python module added under `lib/reliability/` for Phase 5F.** **No new page added under `pages/` for Phase 5F.** **Phase 4A not wired in.** `approved_for_execution` remains `False` (or absent) everywhere it appears. `no_trade` preserved as first-class option state. **Accepted.** |
| Phase 5H / 5H.1 | Controlled Streamlit Cockpit UI Integration v0.1 + Cockpit Page Runtime Fix + Bilingual Surface — adds one additive Streamlit page `pages/7_Investment_Cockpit.py` consuming only the Phase 5G fixture demo pack and rendering the Phase 5B/5C/5D view-models through eight tabs (Overview / Safety, Company Research Hub, Horizon Cards, ThesisTracker, Portfolio / TradePlan, Option Overlay, Feedback / Agent Evaluation, Provenance / Diagnostics). Phase 5H.1 fixed three defects found in user-facing verification: (1) replaced the `@st.cache_data` + `model_dump`/`model_validate` JSON round-trip (incompatible with Phase 5G `Field(exclude=True)` on `adapter` / `memory_store`) with `@st.cache_resource` returning the live `CockpitDemoPack`; (2) added one `st.page_link("pages/7_Investment_Cockpit.py", label=t("nav_p7"))` line to `ui_utils.render_sidebar` (config has `showSidebarNavigation = false` + a hand-rolled bilingual sidebar, so new pages are not auto-discovered); (3) routed every page-chrome string through `ui_utils.t()` and added `apply_theme()` + `render_sidebar()` bootstrap, adding `nav_p7` + ~140 `cockpit_*` keys to both `TRANSLATIONS["en"]` and `TRANSLATIONS["zh"]` (strictly additive). Phase 5I review-cleanup pass (2026-05-28) marked superseded prose in the Phase 5H design doc as historical/superseded (§6 `@st.cache_data` round-trip; §7 filename-derived nav label) and strengthened §18.3's documentation of why remaining table-column-key and `field=value` diagnostic labels are intentionally retained as schema/fixture identifiers (no page refactor; no module/runtime change). Phase 5H.1 test `scripts/test_reliability_phase_5h_cockpit_ui_preview.py` 226/226; Phase 5G 344/344 unchanged; Phase 5A 175/175 unchanged. Files touched by Phase 5H.1: `pages/7_Investment_Cockpit.py`, `ui_utils.py` (additive only), the Phase 5H test, and the Phase 5H design doc. No existing live runtime file (`app.py`, pages 1–6, `lib/llm_orchestrator.py`, `lib/workflow_state.py`, etc.) modified. No live LLM / external API / broker / order / persistence / DB / vector store. `approved_for_execution` never positively authorized (surfaced only as a dynamic `DemoSafetyBanner` JSON value, always `False`). `no_trade` preserved as first-class option overlay state. Phase 4A not imported. See `docs/reliability_phase_5h_controlled_streamlit_cockpit_ui.md` §18. **Accepted.** |
| Phase 5G | Fixture Demo Pack Based on Original App Flow — deterministic, fixture/demo-only Cockpit Demo Pack that simulates the original README five-step Streamlit workflow end-to-end and feeds Phase 5A–5D overlay contracts. Phase 5G adds: (1) Python module `lib/reliability/phase5_demo_pack.py` defining the demo-pack contracts (`CockpitDemoPack`, `CockpitDemoScenario`, `OriginalWorkflowDemoFixture`, `MemoryDemoFixtureBundle`, `CockpitViewDemoBundle`, `DemoScenarioMetadata`, `DemoSafetyBanner`, `DemoDataProvenance`, `DemoPackValidationSummary`) and builders (`build_default_cockpit_demo_pack`, `build_original_workflow_demo_fixture`, `build_memory_demo_fixture_bundle`, `build_cockpit_view_demo_bundle`, `build_demo_scenario_metadata`, `build_demo_safety_banner`, `build_demo_data_provenance`, `validate_cockpit_demo_pack`); the default pack contains one complete scenario (`FIXTKR`, all six workflow steps + every Phase 4M-A through 4M-G record type + three populated horizon cards in canonical `short→medium→long` order) and one degraded scenario (`FIXDEG`, missing the `financial` workflow step, missing the long-horizon thesis, and an option overlay in the `no_trade` state with a populated `NoTradeReasonView`); both scenarios attach a `DemoSafetyBanner` and a `DemoDataProvenance`; (2) design document `docs/reliability_phase_5g_cockpit_demo_pack.md` (status updated to "Accepted" and test-count wording reconciled from "322 assertions expected" / "~322" to "344/344" during the Phase 5H pass); (3) test suite `scripts/test_reliability_phase_5g_cockpit_demo_pack.py` covering 344 assertions across 22 sections. **No live runtime files modified.** **No Streamlit page added.** **No live wiring introduced.** **No DB / vector store / file persistence introduced.** **No external API / Anthropic SDK / HTTP / data-fetcher call introduced.** **No broker / order / trade execution path introduced.** **No executable order fields introduced.** **No prompt / model / agent-definition mutation.** **Phase 4A not wired into live app and not imported by Phase 5G.** `research/.workflow_state.json` is **not** read by Phase 5G. `approved_for_execution` remains `False` (or absent) everywhere it appears. `no_trade` preserved as first-class option overlay state with no inferred substitute strategy. **Accepted.** |
| Phase 5I | Investment Cockpit Product Logic Reconciliation / Opportunity-first + Horizon-aware Architecture — product-logic reconciliation and roadmap/documentation only; supersedes the earlier "Phase 5I — Read-only Shadow Integration" plan as the immediate next step (shadow integration may happen later, but not first). Establishes the Cockpit as opportunity-first / macro-theme-aware / horizon-aware; separates source research modules from the Cockpit decision layer; documents future Theme Intelligence / Market Heat concepts (decomposed into industry-chain nodes), macro-first gating, "avoiding the top" (Theme Heat vs Entry Quality), and a revised Phase 5I–5S roadmap. Deliverables: `docs/reliability_phase_5i_investment_cockpit_product_logic_reconciliation.md` + `scripts/test_reliability_phase_5i_product_logic_reconciliation.py`. No Theme Intelligence / Opportunity Queue / Auto Research Pack / Agent Debate / Macro Dashboard code; no UI redesign; no sidebar change; Financial/PriceVolume pages not removed; no live workflow / shadow integration; no LLM / external API; no DB / vector store / persistence; no broker / order / execution; `approved_for_execution` never positively authorized. Phase 5I review-cleanup pass (2026-05-28) added superseded/historical notes to the Phase 5H design doc §2 / §16 clarifying that the earlier "Phase 5I — Read-only Shadow Integration" wording is historical (no Phase 5H / 5H.1 module/runtime change). **Accepted.** |
| Phase 5J | Theme Intelligence / Market Heat Schema — evidence-first schema / contract / helper / fixture only (offline / mock-only). Defines deterministic structures for detecting market themes, measuring market heat, decomposing industry chains, and representing theme candidate tickers — the **upstream input layer** for the Phase 5K Horizon-aware Opportunity Queue ViewModel. Adds `lib/reliability/phase5_theme_intelligence.py` (Pydantic schema `ThemeIntelligenceSnapshot`, `ThemeUniverseSnapshot`, `ThemeRecord`, `SubthemeRecord`, `IndustryChainNode`, `ThemeCandidateTicker`, `ThemeHeatSignal`, `NarrativeSignal`, `FundamentalConfirmationSignal`, `CrowdingSignal`, `ThemeHeatScore`, `ThemeDiscoverySource`, `ThemeEvidenceSummary`, `ThemeRiskWarning`, `ThemeIntelligenceValidationSummary`, `EntryQualityScorePlaceholder` + Literal aliases + deterministic helpers/fixtures), `docs/reliability_phase_5j_theme_intelligence_market_heat_schema.md`, `scripts/test_reliability_phase_5j_theme_intelligence.py` (202/202), and additive `lib/reliability/__init__.py` exports. Heat score is not a buy signal; entry quality deferred to Phase 5K; `CrowdingSignal` kept separate from `ThemeHeatScore`; missing evidence → partial/unknown; empty snapshot safe; serialization deterministic. No live wiring / LLM / external API / DB / vector store / persistence / broker / order / execution; `approved_for_execution` never positively authorized (every model `extra="forbid"`). Phase 4A not wired in. Codex review complete. **Accepted.** |
| Phase 5K | Horizon-aware Opportunity Queue ViewModel — view-model / schema / helper / fixture only (offline / mock-only). Converts Phase 5J Theme Intelligence / Market Heat records (`ThemeIntelligenceSnapshot` / `ThemeRecord` / `ThemeCandidateTicker`) into deterministic, horizon-aware opportunity queues: short-term trade, mid-term position, long-term investment, watch/wait, research more, and no-trade/avoid. Adds: (1) `lib/reliability/phase5_opportunity_queue.py` — Pydantic view-models (`HorizonAwareOpportunityQueueView`, `OpportunityQueueView`, `OpportunityCandidateView`, `HorizonCandidateView`, `HorizonFitScore`, `EntryQualityScore`, `ThemeHeatBadge`, `CrowdingRiskBadge`, `EvidenceCoverageBadge`, `OpportunityNextAction`, `OpportunityQueueWarning`, `OpportunitySourceSummary`, `CrossHorizonCandidateComparison`, `CrossHorizonEntry`, `OpportunityQueueValidationSummary`), the six queue sections + Literal aliases + deterministic builders + fixtures; (2) `docs/reliability_phase_5k_horizon_aware_opportunity_queue.md`; (3) `scripts/test_reliability_phase_5k_opportunity_queue.py` (218 assertions); (4) additive `lib/reliability/__init__.py` Phase 5K exports. Deterministic heuristic placeholder scoring from fixture fields only: `ThemeHeatScore` contributes to `opportunity_score` but never decides alone; `EntryQualityScore` is separate from heat (`is_heat_score=False`); crowding downgrades `trade_now` → `wait_for_pullback` / `too_extended` / `avoid_too_crowded`; missing evidence → `research_more` / `insufficient_evidence`; the same ticker appears across multiple horizons with different decisions; momentum may enter the short-term queue but mid/long require stronger evidence; empty snapshot → safe empty queues; degraded fixture → warnings. No final buy/sell recommendation; no executable order field; `approved_for_execution` never positively authorized (every model `extra="forbid"`; `ThemeHeatBadge.is_buy_signal=False`). No live wiring / LLM / external API / DB / vector store / persistence / broker / order / execution. Phase 4A not wired in. Phase 5K review-cleanup (performed during Phase 5L) added a backward-compatible clarification of `OpportunityQueueValidationSummary.distinct_tickers`: it counts distinct `(theme_id, ticker)` pairs, so a clarifying comment was added and a new sibling field `distinct_theme_candidate_opportunities` carries the same value under a clearer name while `distinct_tickers` is preserved for existing consumers; Phase 5K test still 218/218. Codex review complete. **Accepted.** |
| Phase 5L | Auto Research Pack Orchestration Boundary — schema / helper / orchestration-boundary / fixture only (offline / mock-only). Converts Phase 5K opportunity-queue candidates into structured research-pack requests and bundles: Opportunity Queue candidate → `ResearchPackRequest` → `ResearchPackPlan` → `ResearchPackBundle`/status → (future) Agent Debate input. `lib/reliability/phase5_research_pack.py` (Pydantic models `AutoResearchPackOrchestrationBoundary`, `ResearchPackRequest`, `ResearchPackPlan`, `ResearchPackBundle`, `ResearchModuleRequest`, `ResearchModuleResultRef`, `ResearchPackHorizonCoverage`, `ResearchPackEvidenceGap`, `ResearchPackValidationSummary`, `ResearchPackSafetyBanner`, `ResearchPackWarning` + Literal aliases + deterministic builders + fixtures); `docs/reliability_phase_5l_auto_research_pack_orchestration_boundary.md`; `scripts/test_reliability_phase_5l_research_pack_orchestration.py` (220 assertions); additive `lib/reliability/__init__.py` exports. Eleven conceptual source modules represented, never called. Horizon-specific module selection; `research_more`/`insufficient_evidence` promote gap-closing modules into required; `wait_for_pullback`/`too_extended` require `price_volume_analysis`+`risk_review`; `no_trade`/`avoid_too_crowded` → review-only minimal pack with no executable research-to-trade path; empty queue → safe empty boundary; degraded → blocked placeholder refs + warnings (no fabricated analysis). Module requests descriptive (`is_runtime_call=False`); module result refs placeholders (`is_placeholder=True`, `result_ref=None`). No final buy/sell recommendation; no executable order field; no `approved_for_execution` on any model (absent, never positively authorized; every model `extra="forbid"`). No Auto Research runtime; no original page functions called; no AI Research Workflow triggered. No live wiring / LLM / external API / DB / vector store / persistence / broker / order / execution. Phase 4A not wired in. Phase 5L test 220/220 (Phase 5K 218/218; Phase 5J 202/202 still pass). Codex review complete. **Accepted.** |

### Recently Accepted (Phase 5N / 5O / 5O.1 / 5P)

| Phase | Description |
|-------|-------------|
| Phase 5P | Source Page Navigation Cleanup — navigation-cleanup-only update to the hand-rolled custom sidebar in `ui_utils.render_sidebar()`. Financial Analysis (`pages/5_Financial.py`) and Price & Volume Analysis (`pages/6_PriceVolume.py`) removed as top-level source-page nav entries (now source sub-surfaces under Equity Research / 个股研究); Macro Dashboard (`pages/8_Macro_Dashboard.py`, `nav_p8`) and Investment Cockpit (`pages/7_Investment_Cockpit.py`, `nav_p7`) remain first-class; Overview / Sector / Scanner / Equity (`nav_p1`–`nav_p4`) and Home (`nav_home`) preserved. The two source-page files are **not deleted** and **not modified** — only their top-level custom-sidebar `st.page_link` entries are removed (direct URL access preserved where Streamlit allows). The `nav_p5` / `nav_p6` translation keys are retained in both `TRANSLATIONS["en"]` / `TRANSLATIONS["zh"]` as legacy source-module labels; no translation key renamed or removed. Deliverables: `ui_utils.py` (sidebar nav links + legacy-key doc comments — the only `ui_utils.py` change), `docs/reliability_phase_5p_source_page_navigation_cleanup.md`, `scripts/test_reliability_phase_5p_navigation_cleanup.py` (96/96), and state files. Validation (`python3 -B`): Phase 5P 96/96; Phase 5O regression 766/766; Phase 5N regression 683/683. No LLM / external API / live workflow / DB / vector store / persistence / broker / order / execution; `approved_for_execution` False or absent. `app.py`, `lib/llm_orchestrator.py`, `lib/workflow_state.py`, `.claude/agents/*`, pages 1–8 internals untouched; no UI/UX visual polish (deferred to Phase 5R); Phase 4A not wired in. Codex verdict PASS (no required fixes; no minor suggestions). **Accepted.** |
| Phase 5O.1 | Macro Indicator Expansion — additive enhancement on top of accepted Phase 5O modelling concrete fixture-only macro instruments and economic-release indicators in a `MacroIndicatorPanel`: eight `REQUIRED_MACRO_INDICATOR_KEYS` (WTI crude oil, GC / gold, CNN Fear & Greed Index, QQQ, IWM, NFP, CPI, PPI) grouped into commodities / risk-appetite-leadership / economic-releases. Pydantic contracts `MacroIndicatorView` → `MacroInstrumentSignalView` → `CommoditySignalView` / `IndexRiskAppetiteSignalView`, `RiskSentimentSignalView`, `MacroEconomicReleaseView` → `LaborMarketSignalView` / `InflationReleaseSignalView`, plus `MacroIndicatorPanel` + Literal aliases + helpers (`make_macro_indicator_id`, `collect_panel_indicators`); `MacroDashboardView` gains `indicator_panel`; validation summary gains indicator metrics. Four scenario panels (risk_on / risk_off / transition / degraded; degraded surfaces `missing_indicators` without fabrication). New Macro Indicators tab (`macro_tab_indicators`) in `pages/8_Macro_Dashboard.py` with three labelled subsections; additive EN/ZH `macro_*` keys in `ui_utils.py`; additive Phase 5O.1 exports in `lib/reliability/__init__.py`. Fixture-only / offline / review-only; no yfinance / Finnhub / FRED / CNN / news / external API; no live macro data retrieval; no LLM; no DB / vector store / persistence; no broker / order / execution; produces no final buy/sell decision; every indicator model `extra="forbid"` with no `approved_for_execution` field (absent, never positively authorized). Phase 5O test 766/766; Phase 5N regression 683/683. `app.py`, pages 1–7, `lib/llm_orchestrator.py`, `lib/workflow_state.py`, `.claude/agents/*` untouched; Phase 4A not wired in. Future live indicator integration deferred to a later controlled phase. **Accepted.** |
| Phase 5O | Macro Dashboard v0.1 — macro-regime view-model layer (`lib/reliability/phase5_macro_dashboard.py`) + additive fixture-only Streamlit page (`pages/8_Macro_Dashboard.py`) elevating macro into a first-class upstream input for the Investment Cockpit. Fixture-backed / offline / mock-only / review-only; no live macro data / LLM / external API / broker / order / execution / DB / vector store / persistence; produces no final buy/sell decision; `approved_for_execution` absent by construction (every model `extra="forbid"`). Pydantic contracts (`MacroDashboardView`, `MacroRegimeSnapshot`, `MacroRegimeStatus`, the eight section views, `MacroHorizonBiasView`, `MacroOpportunityPostureView`, `MacroThemeImplicationView`, `MacroDashboardSafetyBanner`, `MacroDashboardValidationSummary`) + deterministic fixtures (risk_on / risk_off / transition / degraded / empty) + nine-tab page (default risk_on) + additive EN/ZH `macro_*` chrome keys + `nav_p8`. Codex review verdict: PASS (no required fixes; no blocking minor suggestions). Phase 5O test 601/601 at acceptance; Phase 5N regression 683/683; Phase 5J 202/202; Phase 5K 218/218. `app.py`, pages 1–7, `lib/llm_orchestrator.py`, `lib/workflow_state.py`, `.claude/agents/*` untouched; Phase 4A not wired in. **Accepted.** |
| Phase 5N | Cockpit UI v0.2 Opportunity-first Redesign — product-facing Streamlit UI update to `pages/7_Investment_Cockpit.py` only (plus additive `ui_utils.py` EN/ZH `cockpit_*` v0.2 chrome keys, a new test, a reconciled test, and a doc). Redesigns the additive Investment Cockpit page from company/ticker-first (Phase 5H/5H.1) into an opportunity-first, macro/theme-aware, horizon-aware decision cockpit with ten v0.2 tabs (Overview / Safety, Market Themes, Opportunity Queue, Decision Workspace, Research Snapshot, Agent Debate, Trade / Allocation Plan, Option Overlay, Feedback / Review, Provenance / Diagnostics); Market Themes and Opportunity Queue precede Research Snapshot; Company Research Hub repositioned as Research Snapshot and no longer a primary tab. Consumes the Phase 5G demo pack + Phase 5J/5K/5L/5M fixture builders directly. Fixture-only / offline / review-only; no live workflow / LLM / external API / broker / order / execution; no `research/.workflow_state.json` read; no DB / vector store / persistence; fail-closed with no LLM/API fallback. `approved_for_execution` False or absent everywhere and never positively authorized; `no_trade` first-class; no order-ticket / broker-route / account-id / time-in-force / execution-id / quantity-to-execute / broker-payload fields; no final buy/sell/order instruction; Trade tab carries a "Review-only planning view — not an order ticket" boundary. Phase 4A not wired in. First Codex review verdict FAIL on a narrow Trade / Allocation bilingual-chrome issue (English-literal risk-budget / cash-impact / column-header / banner-flag labels) — fixed by routing them through `ui_utils.t()` with additive `cockpit_trade_*` keys + a static inactive-tab chrome scan (Phase 5N test Section 16). Phase 5N test 683/683; reconciled Phase 5H test 235/235; Phase 5M 263/263; Phase 5L 220/220; Phase 5K 218/218; Phase 5J 202/202. Phase 5O minor-suggestion cleanup (performed during Phase 5O): the `CURRENT_TASK.md` validation command block now uses `python3 -B …` (wording-only; no Phase 5N module / runtime / test change; Phase 5N test still 683/683 after the additive Phase 5O `ui_utils.py` / sidebar change). Codex review complete. **Accepted.** |
| Phase 5M | Agent Debate / Decision Workspace Contract — schema / helper / view-model / fixture only (offline / mock-only). Defines deterministic contracts for structuring agent debate and decision-workspace review **after** a Phase 5L research pack is assembled: Phase 5K Opportunity Candidate → Phase 5L Research Pack → Phase 5M Agent Debate / Decision Workspace → (future) Phase 5N Cockpit UI v0.2. Adds: (1) `lib/reliability/phase5_agent_debate.py` — Pydantic models `AgentDebateWorkspace`, `AgentDebateSession`, `AgentDebateRound`, `AgentDebateParticipant`, `AgentStanceRecord`, `BullCaseView`, `BearCaseView`, `RiskCaseView`, `CriticReviewView`, `AllocationPerspectiveView`, `OptionPerspectiveView`, `DebateConflictRecord`, `DebateConsensusSummary`, `DebateEvidenceCoverage`, `DebateWarning`, `DecisionWorkspaceView`, `DecisionWorkspaceRecommendationState`, `DecisionWorkspaceNextAction`, `DecisionWorkspaceSafetyBanner`, `DecisionWorkspaceValidationSummary` + Literal aliases (`AgentRole`, `BullStanceLabel`, `BearStanceLabel`, `RiskStanceLabel`, `CriticStanceLabel`, `AllocationStanceLabel`, `OptionStanceLabel`, `AgentStanceLabel`, `DebateConflictType`, `DebateConsensusLevel`, `DecisionWorkspaceStatus`, `DecisionWorkspaceNextActionType`, `DebateWarningType`, `DebateConfidence`) + deterministic builders (`build_agent_debate_workspace`, `build_debate_session_from_research_pack`, `build_bull_case_view`, `build_bear_case_view`, `build_risk_case_view`, `build_critic_review_view`, `build_allocation_perspective_view`, `build_option_perspective_view`, `build_debate_conflicts`, `build_debate_consensus_summary`, `build_debate_evidence_coverage`, `build_decision_workspace_view`, `build_decision_workspace_recommendation_state`, `build_decision_workspace_validation_summary`, `build_default_participants`) + fixtures (`build_default_agent_debate_workspace`, `build_degraded_agent_debate_workspace`, `build_empty_agent_debate_workspace`, `build_conflict_agent_debate_session`, `build_no_trade_option_agent_debate_session`, `build_research_more_agent_debate_session`); (2) `docs/reliability_phase_5m_agent_debate_decision_workspace.md`; (3) `scripts/test_reliability_phase_5m_agent_debate_workspace.py` (263 assertions); (4) additive `lib/reliability/__init__.py` Phase 5M exports. Seven deterministic participant roles (`bull`, `bear`, `risk`, `critic`, `allocation`, `option`, `synthesis`) — role records only, **no live agent run**. Bull/bear/risk/critic perspectives separated; allocation and option are review-only planning perspectives (`is_executable_allocation=False`, `is_executable_order=False`, `no_trade` first-class). Disagreements surface as `DebateConflictRecord` (bull/bear, risk override) and are never hidden; the critic acknowledges every unresolved conflict (`hides_unresolved_conflict=False`). Risk can downgrade the workspace state to `wait_for_pullback`/`research_more`. Missing evidence → `research_more`/`insufficient_evidence`/`no_decision`; degraded pack → `blocked`/`research_more` with `degraded_upstream` warnings (no fabricated analysis); empty pack → safe empty workspace. Consensus levels: `strong_consensus`, `moderate_consensus`, `mixed`, `conflict_unresolved`, `insufficient_evidence`. Decision-workspace next actions are review-only (`review`, `research_more`, `wait_for_pullback`, `watch`, `skip`, `no_trade`, `escalate_to_human`); `DecisionWorkspaceView.is_executable_decision=False`, `requires_human_review=True`. No final buy/sell recommendation; no executable order field; no `approved_for_execution` field on any model (absent, never positively authorized; every model `extra="forbid"`). No real agent runtime; no Claude/OpenAI/LLM call; no Auto Research runtime; no Macro Dashboard; no UI redesign; no shadow integration. No live wiring / external API / DB / vector store / persistence / broker / order / execution. Phase 4A not wired in. Phase 5M test 263/263; Phase 5L 220/220; Phase 5K 218/218. **Phase 5L is now accepted. Phase 5M is now accepted.** Codex review complete. **Accepted.** |

### Recently Accepted (Phase 5Q / 5R)

| Phase | Description |
|-------|-------------|
| Phase 5Q | Human Feedback UI v0.1 — controlled, **session-only / non-persistent / non-executable** human-feedback review surface added to the Investment Cockpit Feedback / Review tab, completing the human-in-the-loop loop at the UI level without persistence or execution. New session/UI contract module `lib/reliability/phase5_human_feedback_ui.py`: `HumanFeedbackUIState`, `HumanFeedbackActionView`, `HumanFeedbackReviewTarget`, `HumanFeedbackFormState`, `HumanFeedbackSessionRecord`, `HumanFeedbackValidationSummary`, `HumanFeedbackSafetyBanner` + Literal aliases (`HumanFeedbackActionType`, `HumanFeedbackReviewTargetKind`) + deterministic builders (`build_human_feedback_action_views`, `build_human_feedback_review_targets`, `build_human_feedback_session_record`, `build_human_feedback_validation_summary`, `build_human_feedback_ui_state`, `build_default_human_feedback_ui_state`, `build_human_feedback_safety_banner`, `make_human_feedback_session_record_id`) + additive `lib/reliability/__init__.py` exports. These are **UI/session contracts only, not a persistence layer**: every model `extra="forbid"`, declares no `approved_for_execution` field (absent), and carries `is_session_only=True` / `is_persisted=False`. Review-action vocabulary: accept_for_watchlist / reject / modify_thesis / request_more_research / wait_for_pullback / manually_executed_outside_system / skip / review_later / no_trade_confirmed — every action `is_executable=False`. Review targets are duck-typed from the Phase 5K opportunity queue, the Phase 5M decision workspace (status + consensus + conflicts), and the Phase 5G/5D portfolio trade plans + option overlays, so feedback is visibly bound to the selected opportunity candidate, horizon, decision-workspace status, agent-debate consensus/conflicts, trade/allocation plan review state, and option-overlay / no_trade state. Enhanced `pages/7_Investment_Cockpit.py` Feedback / Review tab: a session-only form (target-kind → target → action via `st.radio`, optional free-text note, add/clear buttons) appending only to a transient `st.session_state` list (`phase5q_feedback_session`) — never persisted — plus a session-only preview table and the retained read-only Phase 4M-F / 4M-G fixture summaries under an expander. The radio pickers preserve the sidebar scenario selectbox's AppTest widget ordering (Phase 5N regression intact). Additive EN/ZH `cockpit_review_hf_*` + nine `cockpit_review_action_*` keys in `ui_utils.py` (no key renamed/removed); fixture IDs / tickers / schema enum values untranslated. Deliverables: `lib/reliability/phase5_human_feedback_ui.py`, `pages/7_Investment_Cockpit.py`, `ui_utils.py` (additive), `scripts/test_reliability_phase_5q_human_feedback_ui.py` (389/389), `docs/reliability_phase_5q_human_feedback_ui_v01.md`, and these state files. Validation (`python3 -B`): Phase 5Q 389/389; Phase 5N regression 683/683; Phase 5M regression 263/263. No permanent feedback persistence; no writes to disk / DB / vector store / `research/.workflow_state.json` / production state; no live shadow integration; no LLM / yfinance / Finnhub / FRED / CNN / news / external API; no broker / order / execution; no order tickets / broker payloads / account IDs / order fields / executable trade instructions; no buy/sell/order instruction; `approved_for_execution` remains False or absent (never positively authorized). `app.py`, pages 1–6, `pages/8_Macro_Dashboard.py`, `lib/llm_orchestrator.py`, `lib/workflow_state.py`, `.claude/agents/*` untouched; no UI/UX visual polish (deferred to Phase 5R); Phase 4A not wired in. Codex verdict PASS (no required fixes; no blocking minor suggestions). **Accepted.** |
| Phase 5R | UI/UX Visual Polish + Demo Readiness — product-facing UI/UX polish + demo-readiness pass over the two Phase 5 product pages (`pages/7_Investment_Cockpit.py`, `pages/8_Macro_Dashboard.py`) plus additive `ui_utils.py` EN/ZH chrome keys. Adds a concise, bilingual **"How to read this page (demo walkthrough)"** `st.expander` to both pages, rendered under the page title/subtitle and above the tab strip, explaining fixture-only data, the opportunity-first (cockpit) / macro-first (macro) read order, the review-only nature, and that nothing executes or is persisted. Cross-page terminology made coherent (opportunity-first, horizon-aware, fixture/demo only, review-only, non-executable). All new chrome routes through `ui_utils.t()` with additive `cockpit_walkthrough_*` / `macro_walkthrough_*` keys in both `TRANSLATIONS["en"]` and `TRANSLATIONS["zh"]` (no key renamed/removed); fixture IDs / tickers / enum-schema values / run IDs / JSON keys remain untranslated. **No product logic, scoring, schema meaning, agent contracts, queue/research-pack/debate/feedback semantics, or macro-regime interpretation changed**; every Phase 5N / 5O tab key, EN/ZH label, and ordering preserved (asserted by the Phase 5R test); existing card/table/metric presentation uses the existing Streamlit-native containers/columns/metrics/captions/expanders/tables with no heavy custom CSS; degraded/empty/`no_trade`/`research_more`/unresolved-conflict states render through their existing safe view-model paths. Deliverables: `pages/7_Investment_Cockpit.py`, `pages/8_Macro_Dashboard.py`, `ui_utils.py` (additive), `scripts/test_reliability_phase_5r_ui_ux_polish.py` (324/324), `docs/reliability_phase_5r_ui_ux_visual_polish_demo_readiness.md`, and these state files. Validation (`python3 -B`): Phase 5R 324/324; Phase 5Q regression 389/389; Phase 5N regression 683/683; Phase 5O regression 766/766. No live workflow / LLM / yfinance / Finnhub / FRED / CNN / news / external API; no DB / vector store / persistence; no real onboarding/persistence system; no `research/.workflow_state.json` read/write; no broker / order / execution; no order tickets / broker payloads / account IDs / order fields / execution IDs / executable trade instructions; no buy/sell/order instruction; `approved_for_execution` remains False or absent (never positively authorized). `app.py`, pages 1–6, `lib/llm_orchestrator.py`, `lib/workflow_state.py`, `.claude/agents/*` untouched; Phase 5P sidebar labels unchanged; Phase 4A not wired in. **Phase 5R is now Accepted** (accepted during the Phase 5S pass per the prior review's minor suggestion). Next recommended phase after acceptance: Phase 5S — Phase 5 Productization Closeout (implemented; awaiting Codex review). **Accepted.** |

### Implemented — Awaiting Codex Review

| Phase | Description |
|-------|-------------|
| Phase 5S | Phase 5 Productization Closeout — closeout / documentation / state / test-summary pass that closes out Phase 5 by documenting the completed fixture-backed productization layer (Investment Cockpit + Macro Dashboard + Human Feedback UI), the original README app baseline (preserved live five-step Claude workflow), the accepted Phase 5 deliverables (5P planning + 5A–5R), the current product / UI state (sidebar Home / Overview / Sector / Scanner / Equity / Investment Cockpit / Macro Dashboard, with Financial / PriceVolume demoted to source sub-surfaces under Equity Research; ten-tab opportunity-first cockpit; ten-tab fixture-only macro dashboard with WTI / GC-gold / CNN Fear & Greed / QQQ / IWM / NFP / CPI / PPI indicators), the safety / guardrail status, the accepted dirty-worktree provenance, the validation matrix (Phase 5R 324/324; 5Q 389/389; 5O 766/766; 5N 683/683; 5M 263/263; 5L 220/220; 5K 218/218; 5J 202/202; earlier 5A–5H counts from state docs), the known non-goals / deferred work, a conservative recommended **Phase 6A — Phase 6 Planning / Real Integration Boundary Decision** next step, and a copy-paste session-migration hand-off. Adds **no** new runtime feature, UI layout change, or product-logic change. Deliverables: `docs/ai_dev_state/PHASE_5_CLOSEOUT.md` (authoritative state / hand-off), `docs/reliability_phase_5s_productization_closeout.md` (concise technical companion), `scripts/test_reliability_phase_5s_closeout.py`, and these state files. No live workflow / LLM / yfinance / Finnhub / FRED / CNN / news / external API; no DB / vector store / persistence; no broker / order / execution; no order tickets / broker payloads / account IDs / execution IDs / executable trade instructions; `approved_for_execution` remains False or absent (never positively authorized). `app.py`, pages 1–6, `pages/7_Investment_Cockpit.py`, `pages/8_Macro_Dashboard.py`, `ui_utils.py`, `lib/llm_orchestrator.py`, `lib/workflow_state.py`, `.claude/agents/*`, and all `lib/reliability/` modules untouched by Phase 5S. **Phase 5 is not formally accepted until Codex review accepts Phase 5S. Phase 5S is not yet accepted. Phase 6A — Live Data Integration — is now Accepted; Phase 6B — Stock Selection Signal Layer — is Implemented; Awaiting Codex Review.** **Implemented; Awaiting Codex Review.** |
| Phase 6B | Stock Selection Signal Layer — upgrades the Scanner from manual ticker-pool entry to an AI-generated candidate list built from real free signals (alternative data + EPS-revision trend + keyword narrative attribution + entry quality), ranked by a deterministic composite score (fundamental quality 30% / EPS surprise trend 25% / entry quality 25% / narrative strength + macro alignment 20%) and surfacing early-stage opportunity signals, not just momentum names. New `lib/signal_engine.py` (`fetch_fundamental_signals` / `fetch_narrative_signals` / `compute_entry_quality` / `score_ticker`; `FundamentalSignals` / `NarrativeSignals` / `EntryQualityScore` / `TickerSignalResult`; yfinance + Finnhub free tier `/stock/recommendation` + `/stock/earnings` + `/company-news` + `lib/technical.snapshot()`; every fetch `try/except` fail-closed and cached `st.cache_data(ttl=1800)`; **no LLM** — narrative/theme attribution keyword-rule based) and `lib/candidate_generator.py` (`get_universe()` hardcoded S&P 500 top-100 + `research_state` subsector constituents deduped capped 150; `generate_candidates(macro_regime, top_n=20)` ThreadPoolExecutor max_workers=8 + `st.progress`, cached TTL=1800). `pages/3_Scanner.py` adds an AI候选信号 / AI Signal Candidates section gated by `SCANNER_SIGNAL_MODE = True` (when `False`, exact pre-6B behavior); manual scanner preserved unchanged below a `st.divider()`. `ui_utils.py` additive EN/ZH `scn_sig_*` keys only. Cross-page follow-up (Plan A): `pages/8_Macro_Dashboard.py` additively publishes `st.session_state["macro_regime_result"]` after a successful `classify_regime()` (no behavior change), and the Scanner obtains the regime directly via `classify_regime(fetch_all_macro())` (cached → free hit if the macro page was visited, else live), publishes the same dict, shows the loaded regime status (no hint), and on error reuses a prior regime / `"unknown"`; `generate_candidates` normalizing wrapper over the cached worker keyed `(macro_regime, top_n)`. `scripts/test_reliability_phase_6b_signal_layer.py` 212/212 (mock-only); Phase 6A 336/336; Phase 5O page-8 regression 766/766; Phase 5S closeout 116/116. `lib/llm_orchestrator.py`, `lib/workflow_state.py`, `.claude/agents/*`, pages 1–2 / 4–7 untouched (`pages/8_Macro_Dashboard.py` additive-only); live AI research workflow + existing manual scanner unchanged; no broker / order / execution; `approved_for_execution` False or absent; no DB / vector store / persistence; no new LLM calls; only free APIs (Quiver Quantitative not included). Design doc `docs/reliability_phase_6b_signal_layer.md`. **Phase 6B is not accepted in this pass; Phase 6C has not started.** **Implemented; Awaiting Codex Review.** |
| Phase 6B v3 | Horizon-Native Three-Track Signal Scoring — replaces the v2 single composite score with three INDEPENDENT horizon scores (short ≥0.65 / mid ≥0.60 / long ≥0.55), each deterministically weighted (short: technical_momentum 0.40 / catalyst 0.35 / momentum_continuation 0.25; mid: eps_revision 0.35 / narrative_stage 0.30 / valuation 0.20 / quality 0.15; long: valuation 0.35 / quality 0.35 / narrative_stage 0.20 / macro_alignment 0.10), and merges catalyst detection into the single Layer-2 `llm_narrative_match` call (TTL=3600; safe-defaulted on parse failure). New `CandidateSignal` dataclass (subclasses `TickerSignalResult`) exposes `short_score`/`mid_score`/`long_score`/`horizons_hit`/`signal_strength` (triple/double/single/none)/catalyst fields/`key_signals` (≤5, code-generated)/`data_coverage`. `generate_candidates()` returns `list[CandidateSignal]` sorted triple→double→single→none (within group by horizon-average desc) and writes `st.session_state["cockpit_triple_signals"]` + `["cockpit_all_signals"]` (review-only Cockpit hand-off; fail-closed). `pages/3_Scanner.py` renders signal cards (`st.container(border=True)`; triple = gold `#d4a017` border + 🔥; score pills with ✓/○; catalyst row; Details expander) with three horizon-filter checkboxes; `SCANNER_SIGNAL_MODE` + manual scanner preserved. `ui_utils.py` additive EN/ZH `scn_sig_*` keys only. `scripts/test_reliability_phase_6b_v3_horizon_scoring.py` 189/189 (mock-only); regressions Phase 6B v2 217/217, theme baskets 146/146, Phase 6A 336/336, Phase 5S 116/116. Follow-up tuning: Scanner LLM-depth slider 10–100 (default 50); `generate_candidates` default `llm_n=50` / clamp ceiling 100 (S&P top-100 LLM coverage 31%→51%→100% across llm_n 30/50/100); stale `FI`→`FISV` in `SP500_TOP_100`; new Layer-1 `_MIN_DOLLAR_ADV=$10M` liquidity floor (yfinance `info` only; skipped when absent; never consults RSI/momentum). No paid APIs; no broker / order / execution; `approved_for_execution` False or absent; no DB / vector store / persistence; `lib/macro_regime.py` / `lib/macro_data.py` / `lib/theme_baskets.py` / `lib/workflow_state.py` / `.claude/agents/*` / pages 1–2 and 4–8 untouched. **Phase 6B v3 is not accepted in this pass; Phase 6C has not started.** **Implemented; Awaiting Codex Review.** |

### In Progress

_(none)_

### Pending

| Phase | Description |
|-------|-------------|
| Phase 6C-A | Trading Desk — new `pages/9_Trading_Desk.py` execution layer with three sections (Holdings Monitor / Order Recommendations / Opportunity Watch). New `lib/holdings.py` (`HoldingRecord` dataclass + the SINGLE read/write API for `data/holdings.json`; `load_holdings`→`[]` on absent/corrupt; `save_holdings`→`False` on failure via temp-file+`os.replace`; `add_holding`/`update_holding` partial/`close_holding`/`get_active_holdings`; all fail-closed; no DB/vector store). New `lib/thesis_monitor.py` (`ThesisCheckResult` + four fail-closed signals — A. News: Finnhub `/company-news` 7d → ONE LLM call → sentiment/relevance/key_development, cached TTL=14400 `(ticker,date)`; B. EPS: reuses `signal_engine.fetch_fundamental_signals`, flags `deteriorating`; C. Technical breakdown: `lib.technical.snapshot()` loss-of-SMA200 / RSI<30 / ADX>30 & >10% under cost; D. Macro: `macro_regime_result` risk_off/transition for short/mid only — and a DETERMINISTIC `compute_thesis_status` intact/watch/weakening/broken; `is_normal_pullback` below-cost & above-SMA200 & RSI 35–50; `run_thesis_monitor` ThreadPoolExecutor max_workers=4 with a 4h in-process result cache, not persisted). New `lib/order_advisor.py` (`compute_price_levels` PURE CODE — entry zone / ATR stop (cost−2×ATR or SMA200, nearer to price) / target (resistance or cost+3×ATR) / ATR(14) / support+resistance swing lows-highs / volume_trend / candlestick_pattern doji-engulfing-hammer-shooting_star-none / `risk_reward_ratio` (target−entry)/(entry−stop) / Kelly-lite `position_size_pct` win_rate 0.55 half-Kelly clamped 2%–10%; `data_source` live/fixture fail-closed; `generate_order_narrative` ONE LLM call synthesizing a narrative over the computed levels only, action add|hold|trim|exit|wait, cached TTL=3600, zh via translator, fail-closed to a deterministic baseline). `pages/9_Trading_Desk.py` auto-runs the monitor on load (4h TTL via `trading_desk_last_refresh`), renders holding cards + edit/close, an Add Position form with `cockpit_all_signals` thesis import, order cards (broken-thesis exit-only shown separately), and Opportunity Watch from `cockpit_triple_signals`; never writes `holdings.json` directly. `ui_utils.py` additive EN/ZH `nav_p9` + `td_*` keys + one `st.page_link("pages/9_Trading_Desk.py")` after `nav_p4` and before `nav_p7`. `scripts/test_reliability_phase_6c_trading_desk.py` 115/115 (mock-only); regressions Phase 6B v3 189/189, Phase 6A 336/336, Phase 5S 116/116. Holdings persist ONLY to local `data/holdings.json`; no DB/vector store; no paid API (yfinance + Finnhub free tier); no broker/order/execution capability; no order ticket/broker payload; `approved_for_execution` absent; all data calls fail-closed. `lib/macro_regime.py` / `lib/macro_data.py` / `lib/workflow_state.py` / `lib/llm_orchestrator.py` / `.claude/agents/*` / pages 1–8 untouched. Design doc `docs/reliability_phase_6c_a_trading_desk.md`. **Phase 6C-A is not accepted in this pass; Phase 6C-B has not started.** **Implemented; Awaiting Codex Review.** |
| Phase 6C-A v3 | Entry Strategy v4 — market-based Horizon Entry Zone Engine shared by build/add; `cost_basis` only in the Existing Position Risk Overlay; LONG three-tier valuation confidence; `portfolio_settings` persisted in `data/holdings.json`. `phase_6c_v3_entry_v4` 47/47. **Implemented; Awaiting Codex Review.** |
| Phase 6C-B | Investment Cockpit Rebuild — rebuilds `pages/7_Investment_Cockpit.py` into the primary entry point / live data aggregation hub (one-click Refresh All: macro regime → theme momentum → signal candidates → equity valuation; all fail-closed; Trading Desk thesis monitor NOT run here). New `lib/equity_valuation.py` (`AppFairValue` + `compute_app_fair_value` DCF [per-share Gordon growth, WACC=10%, growth cap=15%] + relative [`SECTOR_MEDIAN_PE × trailing_eps`] + analyst target → low ≤ mid ≤ high band, high/medium/low confidence; cached TTL=3600; fail-closed; `store_equity_research_result` → `st.session_state`). New `lib/llm_orchestrator.analyze_equity_fair_value_debate` (one cached LLM call TTL=7200; bilingual bull/bear/risk/synthesis + endorsed range + action; fail-closed to app low/high). `lib/order_advisor.py` `PriceLevelResult.fair_value_source` + Step 0 reads `equity_research_results` (app_computed > analyst_proxy > fixture). `pages/4_Equity.py` AI Valuation Summary section appended. `pages/9_Trading_Desk.py` fair_value_source badge. Sidebar restructured (Cockpit leads; Overview removed, page retained + `nav_p1` deprecated). `ui_utils.py` additive `cockpit_hub_*` / `cockpit_fv_*` / `td_fair_value_source` / `td_fv_src_*` keys. `scripts/test_reliability_phase_6c_b_cockpit_rebuild.py` 47/47 (mock-only); regressions `phase_6c_v3_entry_v4` 47/47, `phase_6c_trading_desk` 118/118 (assertion 9.5 updated for the new sidebar order), `phase_6b_v3_horizon_scoring` 189/189, `phase_6a_live_data` 336/336. Free sources only; no paid API; no broker / order / execution; `approved_for_execution` False or absent; no DB / vector store / persistence beyond `st.session_state`. `lib/macro_regime.py` / `lib/macro_data.py` / `lib/workflow_state.py` / `lib/signal_engine.py` / `lib/thesis_monitor.py` / `lib/candidate_generator.py` / `lib/theme_baskets.py` / `.claude/agents/*` / pages 2 / 3 / 5 / 6 untouched; `pages/1_Overview.py` retained. Design doc `docs/reliability_phase_6c_b_cockpit_rebuild.md`. **Phase 6C-B is not accepted in this pass; Phase 6D has not started.** **Implemented; Awaiting Codex Review.** |

> **Phase 5 status note (Phase 5S pass).** Phase 5L through Phase 5R are all
> **Accepted** (see the "Recently Accepted" tables above). The earlier aggregate
> row that listed "Phase 5L–5S … Not started" was stale and has been removed;
> only Phase 5S remains in flight (Implemented; Awaiting Codex Review); Phase 6A
> — Live Data Integration — is Implemented; Awaiting Codex Review and Phase 6B
> has not started. The revised-roadmap "Phase 5P — Source Page Navigation
> Cleanup" milestone (distinct from the accepted historical "Phase 5P — Phase 5
> Roadmap Decision / Planning") is **Accepted**. See
> `docs/reliability_phase_5i_investment_cockpit_product_logic_reconciliation.md` §9.

**Phase 4 Memory mainline complete — Phase 4M-A through 4M-H all accepted.**
**Phase 5 sequence: Phase 5P (Roadmap Decision / Planning) Accepted. Phase 5A through 5G all Accepted. Phase 5H / 5H.1 — Controlled Streamlit Cockpit UI Integration v0.1 + Cockpit Page Runtime Fix + Bilingual Surface — Accepted (Phase 5H.1 test 226/226; Phase 5G 344/344; Phase 5A 175/175). Phase 5I — Investment Cockpit Product Logic Reconciliation / Opportunity-first + Horizon-aware Architecture — Accepted. Phase 5J Theme Intelligence / Market Heat Schema is Accepted (Phase 5J test 202/202). Phase 5K — Horizon-aware Opportunity Queue ViewModel — Accepted (Phase 5K test 218/218). Phase 5L — Auto Research Pack Orchestration Boundary — Accepted (Phase 5L test 220/220). Phase 5M — Agent Debate / Decision Workspace Contract — Accepted (Phase 5M test 263/263). Phase 5N — Cockpit UI v0.2 Opportunity-first Redesign — Accepted (Phase 5N test 683/683; reconciled Phase 5H test 235/235). Phase 5O — Macro Dashboard v0.1 — Accepted (Codex verdict PASS; Phase 5O test 601/601 at acceptance). Phase 5O.1 — Macro Indicator Expansion — Accepted (Phase 5O test 766/766; Phase 5N regression 683/683). Phase 5P — Source Page Navigation Cleanup — Accepted (Codex verdict PASS; Phase 5P test 96/96). Phase 5Q — Human Feedback UI v0.1 — Accepted (Codex verdict PASS; Phase 5Q test 389/389). Phase 5R — UI/UX Visual Polish + Demo Readiness — Accepted (Phase 5R test 324/324; Phase 5Q regression 389/389; Phase 5N regression 683/683; Phase 5O regression 766/766). Phase 5S — Phase 5 Productization Closeout — Implemented; Awaiting Codex Review (closeout / documentation / state / test-summary only).**
**Next step: Codex review of Phase 5S — Phase 5 Productization Closeout (authoritative closeout doc `docs/ai_dev_state/PHASE_5_CLOSEOUT.md` + concise companion `docs/reliability_phase_5s_productization_closeout.md` + `scripts/test_reliability_phase_5s_closeout.py`; documents the completed Phase 5 productization layer, current UI state, validation matrix, safety boundaries, accepted dirty-worktree provenance, and a conservative Phase 6A starting point; no new runtime feature / UI layout change / product-logic change; no live workflow / LLM / external API / DB / vector store / persistence / broker / order / execution; `approved_for_execution` absent or False). Phase 5R is accepted in this pass. Phase 5 is not formally accepted until Codex review accepts Phase 5S; Phase 5S is not yet accepted. After Phase 5S is accepted, the next recommended phase is Phase 6B — Stock Selection Signal Layer. Phase 6A — Live Data Integration — is Implemented; Awaiting Codex Review; Phase 6B has not started.**
Phase 4A Integration Boundary remains accepted as early integration infrastructure and is frozen in its current standalone state. Phase 5 must not wire Phase 4A into the live app.

---

## Roadmap v4 Numbering Reconciliation

Roadmap v4 had two numbering views. The project followed the **compressed execution sequence**.
No detailed Roadmap v4 Phase 2 capability was skipped.

| Roadmap v4 Detailed | Implemented As | Notes |
|---------------------|---------------|-------|
| 2F — Catalyst Schema | 2G — Catalyst / Earnings / Estimate Revision Schema | Merged with Earnings + Revision |
| 2G — News ToolResult Wrapper | 2F — News ToolResult Wrapper | Order swapped; News implemented first |
| 2H — Earnings Data Schema | 2G — Catalyst / Earnings / Estimate Revision Schema | Merged |
| 2I — Estimate Revision Schema | 2G — Catalyst / Earnings / Estimate Revision Schema | Merged |
| 2J — Validation Aggregator | 2H — Validation Aggregator | Renumbered after merge compression |
| 2K — Staleness Checker | 2I — Staleness Checker | Renumbered |
| 2L — Critic Agent v0.1 | 2J — Critic Agent v0.1 | Renumbered |
| (inserted) | 2K — Evaluation Harness | Added before closeout to verify detection coverage |

Full reconciliation: `docs/ai_dev_state/PHASE_2_CLOSEOUT.md` and `docs/reliability_phase_2_closeout.md`.

---

## Key Implementation Files

| File | Description |
|------|-------------|
| `docs/ai_dev_state/PHASE_3R_CLOSEOUT.md` | Phase 3R-E: operational checkpoint / closeout |
| `lib/reliability/__init__.py` | Package entry point — all Phase 0–3R exports |
| `lib/reliability/evaluation.py` | Phase 2K: eval harness core |
| `evals/cases/*.json` | Phase 2K: 12 synthetic failure mode cases |
| `evals/expected/*.json` | Phase 2K: 12 expected detection outputs |
| `evals/run_evals.py` | Phase 2K: CLI runner (exit 0 = pass, 1 = fail) |
| `scripts/test_reliability_evaluation_harness.py` | Phase 2K: 91/91 assertions |
| `docs/reliability_phase_2k_evaluation_harness.md` | Phase 2K: full contract docs |
| `lib/reliability/critic.py` | Phase 2J: CriticIssue, CriticResult, 11 helpers |
| `scripts/test_reliability_critic.py` | Phase 2J test suite |
| `lib/reliability/staleness.py` | Phase 2I: staleness checker |
| `lib/reliability/validation_aggregator.py` | Phase 2H: ValidationAggregate |
| `docs/ai_dev_state/PHASE_2_CLOSEOUT.md` | Phase 2 Closeout: operational checkpoint |
| `docs/reliability_phase_2_closeout.md` | Phase 2 Closeout: technical closeout |
| `scripts/test_reliability_phase_2_closeout.py` | Phase 2 Closeout: smoke test (107/107) |
| `lib/reliability/orchestration.py` | Phase 3A: OrchestrationReport, 12 helpers, end-to-end skeleton (with precomputed artifact passthrough) |
| `scripts/test_reliability_orchestration_skeleton.py` | Phase 3A: 81/81 tests |
| `docs/reliability_phase_3a_validated_orchestration_skeleton.md` | Phase 3A: design doc |
| `lib/reliability/horizon_synthesis.py` | Phase 3B: 6 literals, 5 Pydantic models, 12 helpers — horizon-aware synthesis skeleton |
| `scripts/test_reliability_horizon_synthesis.py` | Phase 3B: 67/67 tests |
| `docs/reliability_phase_3b_horizon_aware_synthesis_skeleton.md` | Phase 3B: design doc |
| `lib/reliability/macro_agent.py` | Phase 3C: 8 enums, 7 Pydantic models, 16 helpers — Macro Agent v0.1 skeleton |
| `scripts/test_reliability_macro_agent.py` | Phase 3C: 101/101 tests |
| `docs/reliability_phase_3c_macro_agent_v0_1_skeleton.md` | Phase 3C: design doc |
| `lib/reliability/debate.py` | Phase 3D: 7 enums, 6 Pydantic models, 13 helpers — Debate by Horizon skeleton |
| `scripts/test_reliability_debate.py` | Phase 3D: 54/54 tests |
| `docs/reliability_phase_3d_debate_by_horizon_skeleton.md` | Phase 3D: design doc |
| `lib/reliability/decision_packet.py` | Phase 3E: 8 enums, 7 Pydantic models, 15 helpers — DecisionPacket synthesis skeleton |
| `scripts/test_reliability_decision_packet.py` | Phase 3E: 58/58 tests |
| `docs/reliability_phase_3e_decision_packet_skeleton.md` | Phase 3E: design doc |
| `lib/reliability/human_review.py` | Phase 3F: 7 enums, 6 Pydantic models, 14 helpers — Human Review / Feedback Schema Skeleton |
| `scripts/test_reliability_human_review.py` | Phase 3F: 113/113 tests |
| `docs/reliability_phase_3f_human_review_feedback_skeleton.md` | Phase 3F: design doc |
| `lib/reliability/review_loop.py` | Phase 3G: 1 Literal type alias, 3 Pydantic models, 6 helpers — Offline Review Loop / Reliability Run Report Skeleton |
| `scripts/test_reliability_review_loop.py` | Phase 3G: 151/151 tests |
| `docs/reliability_phase_3g_review_loop_skeleton.md` | Phase 3G: design doc |
| `docs/ai_dev_state/PHASE_3_CLOSEOUT.md` | Phase 3 Closeout: operational checkpoint |
| `lib/reliability/integration_boundary.py` | Phase 4A: 3 enums, 2 Pydantic models, 3 functions — Reliability Integration Boundary Contract (early infrastructure) |
| `scripts/test_reliability_integration_boundary.py` | Phase 4A: 64/64 tests |
| `docs/reliability_phase_4a_integration_boundary.md` | Phase 4A: design doc |
| `docs/ai_dev_state/ROADMAP_V4_ALIGNMENT.md` | Phase 3R-0: roadmap gap analysis and backfill sequence |
| `lib/reliability/event_intelligence.py` | Phase 3R-A: 10 Literal aliases, 7 Pydantic models, 7 helpers — Event Intelligence Agents Skeleton |
| `scripts/test_reliability_event_intelligence.py` | Phase 3R-A: 152/152 tests |
| `docs/reliability_phase_3r_event_intelligence.md` | Phase 3R-A: design doc |
| `lib/reliability/trade_plan.py` | Phase 3R-B: 6 Literal aliases, 7 Pydantic models, 6 helpers — Trade Plan Drafting Agent Skeleton |
| `scripts/test_reliability_trade_plan.py` | Phase 3R-B: 689/689 tests |
| `docs/reliability_phase_3r_trade_plan.md` | Phase 3R-B: design doc |
| `lib/reliability/allocation_report.py` | Phase 3R-C: 5 Literal aliases, 9 Pydantic models, 8 helpers + 7 calculators — Allocation Agent v0.1 Non-live |
| `scripts/test_reliability_allocation_report.py` | Phase 3R-C: 392/392 tests |
| `docs/reliability_phase_3r_allocation.md` | Phase 3R-C: design doc |
| `lib/reliability/option_expression.py` | Phase 3R-D: 10 Literal aliases, 8 Pydantic models, 12 calculators, 7 helpers — Option Expression Agent v0.1 Non-live |
| `scripts/test_reliability_option_expression.py` | Phase 3R-D: 277/277 tests |
| `docs/reliability_phase_3r_option_expression.md` | Phase 3R-D: design doc |
| `lib/reliability/research_memory.py` | Phase 4M-A: 5 Literal aliases, 6 Pydantic models, 11 helpers — Research Run Memory Schema |
| `scripts/test_reliability_research_memory.py` | Phase 4M-A: 165/165 tests |
| `docs/reliability_phase_4m_research_memory.md` | Phase 4M-A: design doc |
| `lib/reliability/thesis_memory.py` | Phase 4M-B: 8 Literal aliases, 7 Pydantic models, 12 helpers — Thesis Memory by Horizon |
| `scripts/test_reliability_thesis_memory.py` | Phase 4M-B: 291/291 tests |
| `docs/reliability_phase_4m_thesis_memory.md` | Phase 4M-B: design doc |
| `lib/reliability/event_memory.py` | Phase 4M-C: 8 Literal aliases, 6 Pydantic models, 12 helpers — Catalyst / News / Earnings Memory (source_refs dedup polish applied) |
| `scripts/test_reliability_event_memory.py` | Phase 4M-C: 307/307 tests (includes dedup section 36) |
| `docs/reliability_phase_4m_event_memory.md` | Phase 4M-C: design doc |
| `lib/reliability/allocation_memory.py` | Phase 4M-D: 7 Literal aliases, 7 Pydantic models, 13 helpers — Allocation Decision Memory |
| `scripts/test_reliability_allocation_memory.py` | Phase 4M-D: 418/418 tests (Section 31 + 32 + 33) |
| `docs/reliability_phase_4m_allocation_memory.md` | Phase 4M-D: design doc |
| `lib/reliability/option_trade_memory.py` | Phase 4M-E: 8 Literal aliases, 7 Pydantic models, 13 helpers — Option Trade Plan Memory |
| `scripts/test_reliability_option_trade_memory.py` | Phase 4M-E: 448/448 tests |
| `docs/reliability_phase_4m_option_trade_memory.md` | Phase 4M-E: design doc |
| `lib/reliability/human_feedback_memory.py` | Phase 4M-F: 7 Literal aliases, 8 Pydantic models, 14 helpers — Human Feedback Layer (Codex fix: overrode requires override_reason) |
| `scripts/test_reliability_human_feedback_memory.py` | Phase 4M-F: 257/257 tests |
| `docs/reliability_phase_4m_human_feedback_memory.md` | Phase 4M-F: design doc (Codex fixes reconciled) |
| `lib/reliability/agent_evaluation.py` | Phase 4M-G: 8 Literal aliases (incl. AgentEvaluationActor), 9 Pydantic models, 15 helpers — Agent Evaluation (offline/mock-only) |
| `scripts/test_reliability_agent_evaluation.py` | Phase 4M-G: 307/307 tests (includes Section 31a rejection analysis + Section 31b summary non-negative validators + Section 18 precedence rewrite + Section 31 state-file assertions updated 2026-05-27 — first Phase 4M-H acceptance rewrite, then Phase 5P planning rewrite — to reflect each newly accepted phase wording; no module change) |
| `docs/reliability_phase_4m_agent_evaluation.md` | Phase 4M-G: design doc |
| `docs/ai_dev_state/PHASE_4M_CLOSEOUT.md` | Phase 4M-H: Phase 4 Memory Closeout — coverage map, architectural boundaries, safety-specific notes, full test matrix, prior next-phase recommendation |
| `docs/reliability_phase_5p_roadmap_decision.md` | Phase 5P: Phase 5 Roadmap Decision / Planning — overlay positioning, route comparison, Phase 5A recommendation, full Phase 5A–5H subphase sequence, non-goals / guardrails, forbidden files |
| `lib/reliability/workflow_memory_adapter.py` | Phase 5A: ExistingWorkflowSnapshot + WorkflowToMemoryAdapter Protocol + InMemoryWorkflowToMemoryAdapter — read-only overlay contract for the existing five-step workflow outputs |
| `lib/reliability/phase5_memory_query.py` | Phase 5A: MemoryStoreProtocol + MemoryQuery* models + MemoryQueryResult + FixtureBackedMemoryStore — read-only, in-memory, fixture-backed memory query contract |
| `lib/reliability/phase5_fixtures.py` | Phase 5A: deterministic original-app-style fixture journey covering sector / scanner / equity / financial / price_volume / synthesis + short/medium/long thesis + event + allocation + option trade (approved_for_execution=False) + human feedback + agent evaluation |
| `scripts/test_reliability_phase_5a_memory_query.py` | Phase 5A: test suite, 175/175 across 19 sections |
| `docs/reliability_phase_5a_memory_query_contract.md` | Phase 5A: design / contract doc |
| `lib/reliability/company_research_hub.py` | Phase 5B: Company Research Hub view-model contracts (CompanyResearchHubView + CompanyIdentityView + EquityResearchPanelView + FinancialValuationPanelView + PriceVolumeTimingPanelView + SourceWorkflowPanelView + EvidenceCoveragePanelView + ValidationStatusPanelView + MissingDataWarningView) + deterministic builders |
| `scripts/test_reliability_phase_5b_company_hub.py` | Phase 5B: test suite (163/163) |
| `docs/reliability_phase_5b_company_research_hub_view_model.md` | Phase 5B: design / contract doc (post-acceptance §4.1 documentation clarification only — no module / runtime change) |
| `lib/reliability/phase5_horizon_views.py` | Phase 5C: Horizon Decision Cards + ThesisTracker view-model contracts (HorizonDecisionCardsView + HorizonDecisionCardView + ThesisTrackerView + ThesisTrackerRowView + ThesisStatusView + InvalidationTriggerView + ReviewNeededBadgeView + MissingEvidenceBadgeView + HorizonEvidenceSummaryView + HorizonRiskSummaryView + HorizonAssumptionView + HorizonNextActionView) + canonical horizon order (short → medium → long) + deterministic builders. Phase 5D minor-suggestion cleanup removed three unused imports (MEMORY_RECORD_TYPES, MemoryQuery, MemoryQueryByHorizon). |
| `scripts/test_reliability_phase_5c_horizon_views.py` | Phase 5C: test suite (179/179 across 27 sections, including Phase 5B regression) |
| `docs/reliability_phase_5c_horizon_decision_cards_thesis_tracker.md` | Phase 5C: design / contract doc (status: Accepted) |
| `lib/reliability/phase5_portfolio_views.py` | Phase 5D: Portfolio / TradePlan / Option Overlay view-model contracts (PortfolioCockpitView + AllocationSummaryView + PositionAllocationView + RiskBudgetView + CashImpactView + TradePlanView + TradePlanLevelView + TradePlanReviewTriggerView + OptionOverlayView + OptionStrategySummaryView + OptionRiskRewardView + OptionLiquidityWarningView + OptionEventRiskWarningView + NoTradeReasonView + ExecutionSafetyBannerView + MissingPortfolioDataWarningView) + canonical trade-plan level kinds (entry / add / trim / stop / target / review) + deterministic builders. No approved_for_execution field; no executable order fields; no_trade preserved as first-class state. Phase 5E minor-suggestion cleanup removed the unused `model_validator` import. |
| `scripts/test_reliability_phase_5d_portfolio_trade_option_views.py` | Phase 5D: test suite (212/212 across 27 sections, including Phase 5C / 5B / 5A regression) |
| `docs/reliability_phase_5d_portfolio_trade_option_view_model.md` | Phase 5D: design / contract doc |
| `docs/reliability_phase_5e_cockpit_ui_planning_boundary.md` | Phase 5E: Cockpit UI Planning Boundary for the existing Streamlit app — documentation/planning-only; describes proposed future cockpit navigation, surfaces, page-to-cockpit mapping, view-model-to-UI-component bindings, data dependency matrix, component boundary map, feature-flag readiness ladder, safe degraded UI states, review-only / non-execution UI semantics, forbidden files, non-goals, guardrails, acceptance criteria, and future Phase 5F dependency |
| `docs/ai_dev_state/PHASE_5E_COCKPIT_UI_PLAN.md` | Phase 5E: lightweight machine-readable state artifact summarizing preserved pages, cockpit surfaces, mappings, dependency matrix, feature-flag ladder, safe degraded states, review-only semantics, forbidden files, and acceptance criteria |
| `scripts/test_reliability_phase_5e_cockpit_ui_planning.py` | Phase 5E: lightweight planning-doc test suite (136/136 assertions) covering required-section existence, cockpit-surface coverage, existing-page coverage, planning-only constraints, forbidden-file enumeration, state-artifact existence and content, no Phase 5E UI module added under `lib/reliability/`, no Phase 5E page added under `pages/`, all forbidden live runtime files still present, and the Phase 5D `model_validator` cleanup |
| `docs/reliability_phase_5f_shadow_mode_integration_boundary.md` | Phase 5F: Shadow Mode Integration Boundary Planning — documentation/planning-only; describes future read-only shadow-mode observation channel from completed workflow outputs → read-only snapshot adapter → Phase 5A query/memory boundary → Phase 5B/5C/5D view-models → future cockpit UI; defines future shadow goals, observation boundaries, prohibited mutations, proposed data flow, snapshot envelope fields (with hardcoded `approved_for_execution = False` and empty `executable_order_fields`), feature-flag ladder, fail-closed / rollback / error-isolation / no-blocking / no-prompt-modification / no-output-modification / no-execution guarantees, review-only semantics, safe degraded states, security/privacy considerations, forbidden files, non-goals, guardrails, acceptance criteria, and future Phase 5G dependency |
| `scripts/test_reliability_phase_5f_shadow_mode_planning.py` | Phase 5F: lightweight planning-doc test suite (137/137 assertions) covering required-section existence in the Phase 5F doc, Phase 5A–5D contract references, existing-page mentions, Phase 4A frozen reminder, planning-only / future-tense framing (no positive claim that shadow mode / snapshot adapter / Phase 4A is wired / active outside negation contexts), forbidden-file enumeration, executable-order-field guard (any mention only inside forbidden / non-goal / guardrail / envelope-fields sections), no Phase 5F Python module added under `lib/reliability/`, no Phase 5F page added under `pages/`, all forbidden live runtime files still present, fail-closed / rollback / error-isolation / no-blocking / no-prompt-mod / no-output-mod / no-execution / review-only / safe-degraded / security invariants, and envelope-level `approved_for_execution = False` + empty `executable_order_fields` hardcoding |
| `lib/reliability/phase5_demo_pack.py` | Phase 5G: Fixture Demo Pack module — `CockpitDemoPack` + `CockpitDemoScenario` + `OriginalWorkflowDemoFixture` + `MemoryDemoFixtureBundle` + `CockpitViewDemoBundle` + `DemoScenarioMetadata` + `DemoSafetyBanner` + `DemoDataProvenance` + `DemoPackValidationSummary`; deterministic builders (`build_default_cockpit_demo_pack`, `build_original_workflow_demo_fixture`, `build_memory_demo_fixture_bundle`, `build_cockpit_view_demo_bundle`, `build_demo_scenario_metadata`, `build_demo_safety_banner`, `build_demo_data_provenance`, `validate_cockpit_demo_pack`); default pack contains one complete scenario (`FIXTKR`, all six workflow steps + every Phase 4M-A through 4M-G record type + three populated horizon cards) and one degraded scenario (`FIXDEG`, missing financial step + missing long-horizon thesis + `no_trade` option overlay). Offline / mock-only. No live wiring. No external API. No broker / order / execution. `approved_for_execution` permanently False. `no_trade` preserved as first-class option overlay state. |
| `scripts/test_reliability_phase_5g_cockpit_demo_pack.py` | Phase 5G: test suite (344/344 assertions across 22 sections) covering forbidden-module non-load + forbidden source substrings, demo-pack determinism, complete scenario coverage, Phase 4M memory coverage, Phase 5B/5C/5D view-bundle coverage, degraded scenario coverage, safety banner + provenance invariants, `approved_for_execution=False` everywhere, no executable order fields, `validate_cockpit_demo_pack` assertions, serialization determinism, standalone builders, helper builders, no filesystem writes, `__all__` checks, package re-exports, no positive authorization in source, Phase 5A/5B/5C/5D regression imports, pack-level degraded warnings, forbidden runtime files still present, and Phase 5G design doc required-section existence |
| `docs/reliability_phase_5g_cockpit_demo_pack.md` | Phase 5G: design / contract doc — purpose, Roadmap v4 relationship, README app relationship, Phase 4M relationship, Phase 5A/5B/5C/5D/5E/5F relationships, demo scenario structure, complete scenario contents, optional degraded scenario contents, demo-only provenance, safety banner semantics, non-goals, guardrails, acceptance criteria, future Phase 5H dependency (status updated to "Accepted" and test-count wording reconciled to 344/344 during the Phase 5H pass) |
| `pages/7_Investment_Cockpit.py` | Phase 5H: new Streamlit page — Investment Cockpit demo preview rendering the Phase 5G fixture demo pack through Phase 5B/5C/5D view-models with eight tabs (Overview / Safety, Company Research Hub, Horizon Cards, ThesisTracker, Portfolio / TradePlan, Option Overlay, Feedback / Agent Evaluation, Provenance / Diagnostics); fixture-only, fail-closed, no live wiring, no LLM/API call, no broker/order/execution path, `approved_for_execution` never positively authorized |
| `scripts/test_reliability_phase_5h_cockpit_ui_preview.py` | Phase 5H: import-safe test suite (170/170) covering page existence + existing-pages preserved, page imports Phase 5G demo pack and Phase 5B/5C/5D contracts only, no live workflow/LLM/external API imports, no `.workflow_state.json` read, required safety banner wording, required eight section/tab labels, no order-ticket-like field names, no positive `approved_for_execution=True` authorization, Phase 5G demo pack still builds clean, Phase 5H design doc required-section existence |
| `docs/reliability_phase_5h_controlled_streamlit_cockpit_ui.md` | Phase 5H: design / contract doc — purpose, Roadmap v4 Phase 5 relationship, original README app relationship, Phase 5E / 5F / 5G relationships, page additivity, existing-pages preservation, fixture-only data flow, UI sections / tabs, safety banner semantics, degraded scenario behavior, non-goals, guardrails (forbidden existing files, `approved_for_execution` invariant, `no_trade` invariant, no executable order fields, fail-closed behavior), acceptance criteria, future Phase 5I dependency, validation |

---

## Standard Session Start Protocol

Future Claude Code sessions **must** begin with:

1. Read `docs/ai_dev_state/PROJECT_STATE.md` (this file).
2. Read `docs/ai_dev_state/CURRENT_TASK.md`.
3. Run `git status`.
4. Inspect only files listed in `CURRENT_TASK.md`.
5. Continue only the current task.
6. **Do not rely on prior chat context.**
7. Before final response, update `PROJECT_STATE.md` and `CURRENT_TASK.md` if task status changes.
8. Run required tests listed in `CURRENT_TASK.md`.

---

## Standard Acceptance Protocol

When a phase is accepted by Codex:

1. Move it from **In Progress** to **Accepted** in the Roadmap.
2. Clear the detailed failed-review notes for that phase from this file.
3. Set the next phase in `CURRENT_TASK.md`.
4. Keep this file concise — do not paste full prompts or Codex reviews.
