# Current Task

> **History archived.** Everything prior to Phase 7B now lives in
> `docs/ai_dev_state/archive/CURRENT_TASK_pre_7b_20260605.md` (full 1955-line
> history preserved verbatim). This file keeps only the active phase. The
> long-form running status remains in `docs/ai_dev_state/PROJECT_STATE.md`.

**Status:** Phase 7C — Theme Transmission Mapping: **implemented + UI-verified;
feature commit on branch `phase-7c-theme-transmission` @ `bbdf5b0`. Awaiting
review — NOT merged to `main`, NOT pushed.**

**Last completed:** Phase 7C — Theme Transmission Mapping (feature commit
`bbdf5b0`)
- New `lib/theme_transmission.py`: `THEME_TRANSMISSION_ORDER` (12 AI themes →
  capital propagation order 1–4 + transmission cluster) + `TICKER_ROLE_MAP`
  (per-ticker role seed; unassessed → `unknown`); builds onto the existing
  `phase5_theme_intelligence` schema (zero duplication); public API
  `get_transmission_order` / `_cluster` / `get_ticker_role` /
  `get_theme_transmission_summary` / `get_diffusion_context`. Zero network,
  zero LLM, deterministic.
- Display-only wiring: `opportunity_ranker` rationale tags (fail-closed import;
  no scoring change), Cockpit theme-card transmission row, Sector Market-Themes
  wave-card redesign. `phase5_theme_intelligence.py` and `theme_baskets.py`
  untouched.
- Tests: `scripts/test_reliability_theme_transmission.py` — **ALL 11 TESTS
  PASSED** (incl. S1 isolation, S7 ranker fail-closed, S8 no
  `approved_for_execution`, S9 `theme_baskets` parity). Active parity suites
  now **68** (was 67). Phase doc:
  `docs/reliability_phase_7c_theme_transmission.md`.

**Prior baseline:** Legacy Red Suite Archival (independent batch) — moved 13
Phase-5 RED suites to `scripts/archive/` (`git mv`); baseline **GREEN=67 /
RED=0** at `main @ b323c09`; archived suites excluded automatically (the
canonical glob `scripts/test_reliability_*.py` is non-recursive).

**Next:** Phase 7C review → merge to `main` (`--no-ff`, after explicit
approval); then Phase 7D (cross-layer comparison → feedback loop).

> **Thesis Ingestion MVP — CLOSED (Codex-approved, 2026-06-14) + UI verification batch
> COMPLETE (2026-06-15, 16 fix commits, 80 tests passing).** UI batch fixes: sidebar nav,
> contextual jump buttons (switch_page), backup folder auto-setup, docx/pdf/pptx support,
> json-repair for LLM JSON, enum normalisation, multi-card dedup, doc_hash-scoped overwrite,
> isinstance guards. Full summary in `docs/ai_dev_state/PROJECT_STATE.md` and the phase doc
> `docs/reliability_thesis_ingestion_mvp.md`.

## Batch Segment 2 — ITEM 1 (earnings-calendar fetch hoist) + ITEM 2 (FRED liquidity fetchers) (CLOSED — Codex-approved, committed direct to `main` 2026-06-12)

Two independent data-layer changes shipped together as ONE closing commit (direct to the
main worktree, not a `--no-ff` branch merge). Both Codex-approved with discriminating
mutation probes. Phase docs: `docs/reliability_phase_7b_rotation_internals.md` (ITEM 1),
`docs/reliability_phase_5o_macro_dashboard_v01.md` (ITEM 2).

**ITEM 1 — bulk earnings-calendar fetch hoisted before the Track B fan-out** (timing/wiring
only; no logic/threshold/computation change). The single uncached bulk Finnhub
`fetch_earnings_reactions_calendar` call ran LAST (Step 4); on a cold cache the Step-3
Track B per-ticker Finnhub burst (full scan universe × 8 workers) exhausted the free 60
req/min budget and 429'd it. Now it fires ONCE **before Step 3** and the raw REPORTS are
**replayed** into `compute_market_fragility` via `earnings_calendar_fn` (NOT
`earnings_reactions=`, which would bypass the Round-4 scan-universe pipeline and change the
computation). Step-4 computation byte-identical; exactly one network call; no second call
site. On early failure the **captured exception is re-raised** at Step 4 → identical
`finnhub_unavailable` degrade, never crashes (also keeps pages/7 free of the lowercase
`finnhub` token the 5H/5N guardrails forbid). Ranking path (`opportunity_ranker`) reaches
none of this code (structural guard). Tests: `phase_7b` §20 (211→219) drives the REAL
`_run_refresh` recording call ORDER — 20.2 exactly-once, 20.3 before Track B, 20.4 replay
still computes, 20.5–20.7 failure degrades without crash, 20.8 ranking zero-network;
mutations proven (duplicate → `['earnings','earnings','track_b']` 20.2 RED; late fetch →
`['track_b','earnings']` 20.3/20.6 RED). signal_engine.py untouched.

**ITEM 2 — FRED liquidity fetchers (SOFR / ON RRP / TGA / bank reserves), display-only,
snapshot-excluded.** New `LiquidityResult` + `_liquidity_fixture()` + `@st.cache_data`
`fetch_liquidity()` in `lib/macro_data.py` pulling SOFR / RRPONTSYD / WTREGEN / WRESBAL via
the existing `_fred_observations` (existing `FRED_API_KEY`; no `fredapi`, no new key; per-
series isolation; fail-closed to fixture). **Deliberately NOT in `fetch_all_macro` /
`MacroDataResult`** → `classify_regime` and `write_daily_snapshot` never see it; fetched
**on demand** from the pages/8 `_render_live_liquidity` tab (added to it; rates content
intact). Five bilingual `t()` keys (`macro_live_grp_liquidity`, `_sofr` / `_on_rrp` /
`_tga` / `_reserves`) in BOTH locales. Tests: `phase_5o` §L (+9) — fail-closed
(L.1/L.1b/L.2/L.3) + the load-bearing SNAPSHOT-EXCLUSION guard (L.4–L.7) + no-fredapi
(L.8); mutations proven (fixture tagged live → L.1/L.1b/L.2/L.3 RED; `sofr` added to
`MacroDataResult` → L.4 RED). README NOT re-touched (segment-1 principle correction already
shipped @ `f99ed2f`).

**Verification.** `phase_7b` 219/219; `phase_5o` 738/3 (3 pre-existing `url_pathname`
AppTest reds, identical to HEAD); 5H 179/24 and 5N 545/104 — identical to HEAD baseline,
**zero new failures** from the shared `ui_utils.py` / `pages/8` edits.

## UI Cleanup Batch — Segment 1: Market-Internals Fragility plain-language + i18n pass (CLOSED — Codex-approved, committed direct to `main` 2026-06-10)

A **display-and-i18n-only** readability pass over the **市场内部结构 / Market-Internals
Fragility** component across its two render surfaces (Cockpit banner +
Macro Dashboard "Market Internals" workbench), folded together with the
previously-approved README principle correction. **No computation, threshold,
snapshot field, or `macro_regime.py` change** — strings + render formatting only.
**Direct commit to the main worktree (not a `--no-ff` branch merge).** Phase doc:
`docs/reliability_phase_7b_rotation_internals.md` ("Plain-Language + i18n Readability
Pass" section).

- **Scope (5 files):** `ui_utils.py`, `pages/7_Investment_Cockpit.py`,
  `pages/8_Macro_Dashboard.py`,
  `scripts/test_reliability_phase_7b_rotation_internals.py`, `README.md`.
- **Headers** (`mi_component`→Signal/信号项, `mi_value`→Reading/读数,
  `mi_triggered`→Triggered?/是否触发, `mi_degrade`→Data note/数据说明; column retained).
  **Labels:** new `mi_c_breadth20`/`mi_c_breadth50` (`>20-day MA %` / `20日均线以上占比`
  …); `mi_c_slope`→Breadth trend (slope) / 广度趋势（斜率）.
- **Value rendering:** weak-bounce bool→Yes/No · 是/否; breadth float→`50%`;
  good-news-sold = **compact `num/den` banner** + **full phrase** in the table
  (`1 of 12 post-beat names sold off` / `12 次财报中 1 次遭抛售`); offense/defense gains
  ZH words via `frag_od_value` — **EN values equal the raw `rotation.py` tokens
  (byte-identical surface), tokens untouched.**
- **Discipline semantics preserved (reworded only):** `cockpit_frag_lvl_explain`
  (elevated = alert-only/no tighten; high = SHORT-horizon tighten, mid/long unaffected)
  [TIGHTEN-ONLY]; `cockpit_hub_internals_note` (tighten-only, regime unchanged)
  [TIGHTEN-ONLY]; `mi_note` (tighten-only + research-only/not-advice)
  [TIGHTEN-ONLY][REVIEW-ONLY]. **Degrade tokens (降级词汇表) unchanged** — `frag_reason_gloss`
  appends a ZH gloss, EN keeps the bare audit token. `mi_source` label gets a ZH note;
  the **value stays raw** [AUDIT-PROVENANCE].
- **Exclusions honored:** `mi_c_vol` (vol_shrink) label AND value untouched (pending
  caliber ruling); EN level badges `normal/elevated/high` unchanged (parity-pinned);
  regime line + `horizon_bias` values untouched.
- **Tests.** Parity helpers synced; 14.12 + 16.10 expected strings updated for the new
  wording (not weakened). **New discriminating guards 19.1–19.10** go RED on an EN
  badge change (iii), a dropped tighten-only/review-only clause (D, EN+ZH), or an
  altered/dropped degrade token (E); + offense/defense ZH-localizes / EN-raw.
  `phase_7b` **211/211 GREEN**; Codex review verified the mutation probes. Pre-existing
  unrelated reds in 5o (`url_pathname` AppTest) and 5n (`cockpit_trade_col_*`) confirmed
  pre-existing at `HEAD` in an isolated worktree.
- **README correction (previously approved, same commit):** "数字交给代码，语言交给 LLM"
  → judgment-under-evidence framing ("数字交给代码，判断在证据约束下可由 LLM 建议"); EN
  tagline + Phase 9 roadmap (human-in-the-loop **Judgment Console**) updated to match.
  Numeric-firewall + review-only invariants unchanged.

## Anchor Intelligence v2.5 — Multi-Dimensional Peer Profile + Honest `peer_match_quality` (CLOSED — APPROVED @ 6f9c1ec, merged to main; FINAL v2 round, closes the v2 series)

Branch `phase-anchor-intel-v2-5` off `main` @ `ef8cb28`. Access-path-first (STEP 0
matrix committed at `8521f15` BEFORE any code). **Deterministic, no runtime LLM;
numeric-dim reads reuse already-fetched page data — zero new fan-out; the
network-free ranking/refresh path is structurally untouched.** Phase doc
`docs/reliability_anchor_intel_v2.md` ("Round v2.5"). Paid taxonomies (MSCI / Syntax /
Morningstar) evaluated + REJECTED (black-box/paid — documented, not to be revisited).

- **A — numeric dims** (`lib/valuation_router.py`, `PEER_DIM_CONFIG`): add
  `margin_band` / `profitability_stage` / `revenue_cyclicality` to v1's sector ×
  growth × size, all from already-fetched `info`. `numeric_dims()` +
  `_dims_compatible()` (band equality on all five; `unknown` never matches).
- **B — basket tags (single source of truth):** `basket_membership()` reads
  `theme_baskets` constituents read-only — the peer taxonomy shares ONE curated list
  with rotation (no second classification).
- **C — override** `PEER_PROFILES` (human-reviewed). Data-driven MINIMAL seed =
  **KTOS only** (in no basket); SNOW covered by its basket + numeric dims (verified).
- **D — honest degrade:** `assess_peer_match()` qualifies on numeric-compat AND a
  shared basket/override tag; `≥ MIN_QUALIFIED_PEERS (4)` → `high`; fewer → `low` +
  `insufficient_comparable_peers`, NO raw-GICS padding. `build_app_fair_value`
  EXCLUDES EV/S+EV/EBITDA on `low` (flag + `peer_match_unreliable` caveat) — still
  shown; `relative_pe` NOT gated. `AppFairValue` gains `peer_match_quality` /
  `peer_match_reason`; the diagnosis card SOURCES + renders them. **EXCLUDE, never a
  down-weight knob** (confirmed). `peers=None` → quality `""` → byte-identical to v2.4.
- **Acceptance (real peer path):** SNOW → `high` (cloud peers, not all software);
  KTOS → `low` → EV/EBITDA excluded (discriminating) → analyst-only $30.
- **Tests.** New `test_reliability_anchor_peer_match.py` **49/49**;
  `valuation_diagnosis` **50 → 54**. Canonical sweep GREEN (entry_v4 92,
  trading_desk 126, 6c_b 47, 7A 115, 7B 193, router 117, stopbleed 65, render_order
  50, archive 77, backfill 61, valuation_diagnosis 54, peer_match 49). Full
  `test_reliability_*` **GREEN=66 / RED=13** (13 pre-existing orthogonal reds).
  `macro_regime.py` untouched; i18n additive; `git diff --check` clean.
- **Fix round (REQUEST CHANGES — B1, P1).** `_peers` excluded from the
  `compute_app_fair_value` cache key but it drives `peer_match_quality` + EV exclusion
  → first-writer-dependent (round-1 epoch-mixing class). STEP 0: peer matching affects
  BOTH inclusion AND the EV anchor's VALUE (qualified-set medians drive the EV
  anchors) → **Option A**: `_peers_signature` enters the key as `peer_sig`.
  Peer-bearing (Equity) / peer-less (Trading Desk) cache SEPARATELY regardless of
  order; peer-less byte-identical to v2.4; also closes a latent v2.4 EV-value bug.
  §10 both-orders test; discrimination confirmed (revert the arg → 10.2+10.4 FAIL).
  `peer_match` 44 → 49.
- **Commits:** `8521f15` (STEP 0), `e93164e` (lib matcher + blend), `1466630` (card +
  suite), `4feb9de` (**B1 cache-key fix**). **Re-review APPROVED at `6f9c1ec`; merged
  to `main` via a `--no-ff` merge commit — v2.5 CLOSED.** With v2.5 the Anchor
  Intelligence v2 series is COMPLETE.

## Anchor Intelligence v2.4 — Valuation Diagnosis Card + F4 Archive Sharding (CLOSED — APPROVED @ 18dfcf2, merged to main)

Branch `phase-anchor-intel-v2-4` off `990ed90`. Access-path-first (STEP 0 matrices
committed at `b5277b8` before any code). **Deterministic; no LLM invents a number;
the diagnosis adds no anchor math and triggers no compute/fetch on any path.** Phase
doc `docs/reliability_anchor_intel_v2.md`.

- **PART A — valuation diagnosis card.** New pure `lib/valuation_diagnosis.py`:
  `build_valuation_diagnosis` ASSEMBLES a `ValuationDiagnosis` from existing
  `AppFairValue` + migration fields (company_type, applicable/rejected methods with
  reasons, anchor consistency cluster-vs-outlier, endorsed range incl. honest
  irreconcilable state, confidence). NEW deterministic `classify_valuation_role`
  (visible config block) → `{informational|mid_term_supportive|long_term_eligible}`,
  the documented interface to 7A (wiring deferred). `what_would_change` = MECHANICAL
  conditions now (price-vs-range, analyst-pool deterioration) + NARRATIVE Phase-8
  placeholder; reverse-DCF = named Phase-8 slot. Rendered on pages/4 + pages/9 via
  `ui_utils.render_valuation_diagnosis_card`; threaded via additive
  `PriceLevelResult.app_fair_value_obj` (no second compute; None on the network-free
  path). No snapshot field (render-time only). Suite **50/50**.
- **PART B — F4 sharding.** `lib/anchor_archive.py` sharded per ticker
  (`data/anchor_archive/<TICKER>.jsonl`); reads O(total) → O(ticker). One-time
  offline `scripts/migrate_anchor_archive_to_shards.py`. Invariants preserved
  (append-only, page-path-only writes/§13.10, single-vintage, never-fabricate, G2
  seam). `anchor_archive` 60→77, `anchor_backfill` 60→61, `entry_v4` 92/92.
- **Sweep** GREEN=65 / RED=13 (pre-existing orthogonal reds). `ui_utils.py`
  normalized to LF (lone CRLF outlier); `git diff --check` clean.
- **Fix round (REQUEST CHANGES — re-review pending):** F-A1 `anchor_consistency`
  sourced from the producer (no recomputed/order-dependent outlier; `no_clear_outlier`
  when ambiguous) · F-B2 dedup key on the canonical resolved shard path (alias forms
  can't bypass dedup) · F-B3 migration guarantee narrowed to SEMANTIC fidelity
  (field-level + count test, not byte-equality). `valuation_diagnosis` 46→50,
  `anchor_archive` 71→77. **Re-review APPROVED at `18dfcf2`; merged to `main` via a
  `--no-ff` merge commit — v2.4 CLOSED.** Next active phase: **v2.5** (multi-dim peer
  profile + honest `peer_match_quality` degrade) — pending, not started.

## Anchor Intelligence v2.3 — Anchor Historization + Historical Backfill (fully CLOSED)

v2.3 turns the unified anchor (Round 1) into an **append-only historical series** and
seeds it with recomputable history. **Deterministic; no LLM invents an anchor, and
the analyst input is never fabricated for a past date.** Phase doc
`docs/reliability_anchor_intel_v2.md`. Both review-gated bodies are CLOSED:

- **Main body — APPROVED at `9f6c37e`, merged at `97c8f1f`.** **U1** append-only
  anchor archive at the `store_equity_research_result` producer chokepoint; **U2**
  daily snapshot carries a single-vintage anchor block; **U3** deterministic
  migration readout + read-only `thesis_monitor` anchor-migration watch note
  (thesis_status untouched). Fix round F1–F4 hardened the chokepoint capture,
  surfaced the watch note, and recorded the archive-read cost.
- **Historical backfill — APPROVED at `c57e56e`, merging now.** Offline engine
  (`lib/anchor_backfill.py`, `scripts/backfill_anchors.py`) seeds **recomputable
  anchors only**; the **analyst anchor is never fabricated** for a historical date
  (additive `record_origin` + analyst sentinel keep live vs. backfilled rows
  distinct). B1/B2/B3 + the **G1/G2 fix round** added a **filing-lag look-ahead
  defence** (`FILING_LAG_DAYS = {annual: 75, quarterly: 45}`, period_end + lag <= D,
  threaded into the DCF/relative raw AND the cyclical PB/PS band) and a **same-date
  seam guard** (`covered_vintages` spans both origins; live wins). Suite
  `scripts/test_reliability_anchor_backfill.py` **60/60**; canonical sweep
  unchanged-green.

**Rounds v2.4 / v2.5 remain pending** (future scope, not started).

---

## Anchor Intelligence v2 — Round 1 (CLOSED — review APPROVED at 9e53f04)

Unifies the fair-value anchor onto a single producer, makes the sell-side analyst
input structured, and stamps every card with the producer epoch. **Deterministic;
no LLM invents anchors.** Phase doc `docs/reliability_anchor_intel_v2.md`; suite
`scripts/test_reliability_phase_6c_v3_entry_v4.py` **90/90** (52 → 73 → 87 → 90
across the two fix rounds + the R3 real-path case); canonical sweep green. Review
**APPROVED at 9e53f04 — round 1 is CLOSED. Rounds v2.2–v2.5 remain pending**
(future scope, not started).

- **U1 — single producer**: `order_advisor._gather_technicals` computes the anchor
  via `compute_app_fair_value` (`AppFairValue`); one producer + one `st.cache_data`
  entry/epoch shared by Trading Desk / Equity / Cockpit. Entry FORMULAS unchanged
  (×0.90 high, ×0.85 medium); `conservative_anchor` tier-dependent (high =
  `fair_value_mid`, medium = `analyst_target`, low = None) to avoid
  double-discounting the MoS. `lib/valuation_anchor.py` deprecated (kept for compat).
- **U2 — structured analyst anchor + pool-dispersion gate**: `AppFairValue.analyst_pool`
  {median, mean, high, low, n, as_of}; pool-dispersion gate ((high−low)/median,
  threshold 1.0×, min n=3) caps confidence at low + emits
  `CAVEAT_ANALYST_POOL_DISPERSED` (confidence-only; blend still proceeds).
- **U3 — epoch stamping + single-source-per-card**: `PriceLevelResult.fair_value_computed_at`
  carries the producer epoch; an external/session band drives confidence AND
  `conservative_anchor` AND epoch from THAT band (no mixed-source read).

**Fix rounds (all APPROVED at 9e53f04).** **F** — true single cached producer
(page-path fetcher threaded; first-writer-wins parity on the REAL Equity vs
Trading-Desk paths); external band single-source; `analyst_proxy` →
`app_fair_value` token rename (C5). **X** — `compute_price_levels(allow_fetch=False)`
makes the ranker / Cockpit-refresh path structurally network-free (cold cache →
`anchor_not_cached` + `fair_value_anchor=None`); Cockpit on-demand research passes
the cyclical fetcher (no cache poison, Option B); external-band single-source gated
so a healthy external band is not degraded by an irreconcilable local instance.
**R3** — cold / missing-OHLCV path clears the fixture `cp×0.85` scalar to None
(honest-degrade contract), proven on the REAL transitive ranker path.

**Round-1 lesson:** *Unifying a producer with multiple callers is an access-path
problem, not a physical merge — map the caller-contract matrix (page = needs band +
allows network; ranker = network-free; refresh = no-poison) before implementing.*

---

## Valuation Refactor v1 — Method Router + Growth-Profile Peers (COMPLETE & CLOSED — re-review APPROVED at ca5ad14)

Each company type gets an appropriate valuation method menu so the
irreconcilable-anchor rate drops (KTOS class no longer dead-ends). **Deterministic;
no LLM** (reverse DCF + debate = Phase 8). Phase doc
`docs/reliability_valuation_router.md`; suite
`scripts/test_reliability_valuation_router.py` **104/104**. Full canonical set green:
stopbleed 65, 7A 115, 7B 187, 6c_b 47, equity_render_order 50, 6c_trading_desk
118, 6c_v3_entry_v4 47, 6b_v3_horizon_scoring 189, theme_baskets 146,
scanner_rotation_adapter 15.

**Review status: COMPLETE & CLOSED** — the REQUEST CHANGES fix rounds and the
documentation-closure round (ca5ad14) were re-reviewed and **APPROVED**; the phase
is closed. Fixes: **F1** growth_unprofitable excludes DCF structurally;
**F2** real cyclical ≤4y annual PB/PS band (page-path fetch, cached, network-free
ranking; degrades to analyst-only + `cyclical_band_unavailable` caveat); **F3**
anchor cache rejects bare legacy maps; **F4** token-boundary hint matching
(`industry_has_hint`); **F5** status docs aligned. Two deliberate test-assertion
changes: router 2.7 (DCF now excluded for growth_unprofitable) + stopbleed 5.17
(bare legacy cache now rejected).

- **Task 1 — Classifier** (`lib/valuation_router.py`, NEW): `classify_company` →
  5 types from one visible `CLASSIFIER_CONFIG` block + sector/industry hints, over
  the already-fetched `tk.info` dict (no new network). Auditable `fired_rules`;
  `clear`/`borderline` (borderline → default mature menu).
- **Task 2 — Method menus** (`lib/equity_valuation.py`): `build_app_fair_value(...,
  company_type=)` routes the blend input set via `METHOD_MENUS`. PE excluded for
  growth_unprofitable; trailing-PE `cycle_distorted` for cyclical; DCF excluded for
  growth/project. New `_compute_ev_s`/`_compute_ev_ebitda`/`_compute_pb_ps_band` +
  sector fallback maps + Rule-of-40. Default path byte-identical; **dispersion gate
  (3.0×) still runs last**.
- **Task 3 — Growth-profile peers**: `match_growth_profile_peers` (sector AND
  growth band AND size band; `sector_fallback` when < `min_peers`). `pages/4`
  passes already-fetched peer info; cached path → sector fallback.
- **Task 4 — Integration**: `AppFairValue` carries company_type + routing fields;
  anchor cache schema **1 → 2** (version guard migrates old → empty); `pages/4`
  badge + per-anchor methods + excluded anchors; `financial_tab` honest
  DCF-excluded note; Cockpit unchanged beyond cache bump (verified). KTOS:
  irreconcilable 7.89× ($0 band) → blended EV/EBITDA $23.46 + analyst $30 →
  $19.94/$25.91/$31.50.

**Created:** `lib/valuation_router.py`, `scripts/test_reliability_valuation_router.py`,
`docs/reliability_valuation_router.md`. **Modified:** `lib/equity_valuation.py`,
`lib/anchor_cache.py`, `lib/financial_tab.py`, `pages/4_Equity.py`, `ui_utils.py`,
`scripts/test_reliability_valuation_stopbleed.py`, state docs.

---

## Phase 7B — Multi-window RS, Two-Ring Rotation, Market-Internals Fragility (Implemented + fix round)

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
