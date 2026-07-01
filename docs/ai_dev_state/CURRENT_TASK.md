# Current Task

> **History archived.** Everything prior to Phase 7B now lives in
> `docs/ai_dev_state/archive/CURRENT_TASK_pre_7b_20260605.md` (full 1955-line
> history preserved verbatim). This file keeps only the active phase. The
> long-form running status remains in `docs/ai_dev_state/PROJECT_STATE.md`.

**Status:** **CandidateScreeningAgent eligibility gate (enabler): COMPLETE,
Codex-APPROVED, merging to `main` via `--no-ff`** (feature branch
`phase-8b-candidate-eligibility` off `main @ 0bcf01f09`; merge/feature hashes in
the closeout report). This is the **deterministic, LLM-free enabler that PRECEDES
CandidateScreeningAgent** — NOT the agent itself (no LLM, no `AgentOutput`, no
slate, no Cockpit hook; those belong to the agent body). New
`lib/candidate_eligibility.py`: a four-state candidate gate
(`eligible` / `conditional` / `ineligible` / `unknown`) computed per
`(ticker, horizon)` over `OpportunityCard` + `CandidateSignal` (read-only;
dataclass-or-dict tolerant). **Six gates**: HARD `thesis` / `eps` / `valuation` /
`event` (may reach `ineligible`) + SOFT `liquidity` / `distribution` (never
`ineligible`). `eps` / `valuation` / `event` are **horizon-asymmetric** (e.g.
imminent earnings gates SHORT, not LONG; deteriorating EPS is a SHORT caution but
a MID/LONG fail). Fixed aggregation precedence: hard-fail → hard-unknown →
any-conditional → soft-unknown(→conditional) → eligible. **Numeric-firewall
provenance guard:** `_forward_pe_is_usable` rejects `None` / non-numeric / `bool`
/ `<= 0`, closing the leak where `fetch_fundamental` stamps
`data_source["valuation"]="live"` on an invalid `forwardPE` while
`_valuation_percentile` defaults to 0.5 — a defaulted 0.5 is treated as
`VALUATION_UNKNOWN`, never a real pass. Stdlib-only at import (no
`lib.reliability` / `lib.llm_orchestrator` / network / LLM). **18 tests / 87
assertions offline.** Codex REJECT (provenance leak) → fix round (1 code fix + 4
tests + 1 comment) → APPROVE. Phase doc
`docs/reliability_candidate_eligibility_gate.md`.

**Completed:** CandidateScreeningAgent eligibility gate enabler
(`lib/candidate_eligibility.py` + `scripts/test_phase_8b_candidate_eligibility.py`).

**Next:** **Phase 8B — CandidateScreeningAgent (agent body)**
— The agent that CONSUMES this gate: per-theme comparison table over the
`eligible` candidates + deterministic frontrunner + code-decided
`no_clear_winner` + constrained LLM synthesis (machine-readable slate) + additive
per-theme Cockpit hook. Wraps the `opportunity_ranker` / `candidate_generator`
deterministic producers behind the eligibility gate. Follows the established
agent pattern (deterministic confidences before the LLM; `REQUIRED OUTPUT
FORMAT`; `valid_until = end_of_today_iso()`; `approved_for_execution` never
`True`; additive key-gated fail-closed Cockpit hook).

**Last completed:** Phase 8B ThemeIntelligenceAgent (COMPLETE, Codex-APPROVED,
merged to `main` via `--no-ff` @ `5ecfb7875`, feature commit `7b86dcaba`, pushed).
Fifth production foundation agent. Distinct from SectorRotationAgent: per-ticker
role (`constituent_rs` active-window ranking × seed role) + cross-wave asymmetry
(`wave_order` {1,2} AND `stage="rotating_in"` = structurally early, un-crowded).
`short = theme_coverage × role_resolution` (all-constituent denominator — honest
coverage); `mid = theme_coverage × asymmetry_strength`; `long = 0.0`.
`_EARLY_STAGES = frozenset({"rotating_in"})` excludes `""`. `signal_basis`
`no_role_signal` = seed map sparse, NOT bearish. **39/39** ThemeIntelligence · 3
mutation probes confirmed. Phase doc
`docs/reliability_theme_intelligence_agent.md`.

**Prior:** Phase 8B MarketStructureAgent (merge `8792343f9`)
- New `lib/agents/market_structure_agent.py`: `FragilityReading` INJECTED from
  Cockpit Step 4 (never calls `compute_market_fragility` — no second compute, no
  vintage divergence). Three deterministic confidences before the LLM:
  `short = coverage × clarity` (coverage = 1 − degraded_core/5,
  `leading_theme_breadth_narrowing` excluded as permanently scaffolded;
  clarity = min(points,4)/4); `mid` = trailing elevated+ run via saturating curve
  `[(0,0.0),(2,0.4),(4,0.7),(6,1.0)]`, `vintage_mismatch`/snapshot fallback →
  `min(interpolated, 0.1)` cap (NOT floor), empty series → 0.0; `long = 0.0`.
  `signal_basis` three-way classifier (signal_present / degraded_insufficient /
  full_data_no_signal) in TR2. Three ToolResults (`market_fragility_signals` /
  `market_fragility_health` / `market_structure_confidence`).
- Prompt `REQUIRED OUTPUT FORMAT` (4-space indent, no fences); tighten-only
  prohibitions explicit (no bullish/add/loosen, never override regime,
  normal+degraded ≠ healthy, SHORT-only tighten, evidence_ids only); no numbers
  in findings. All `lib.reliability`/`lib.agent_framework` imports lazy; outer
  fail-closed guard; `valid_until = end_of_today_iso()`.
- Cockpit hook: additive (`market_structure_agent_output`), key-gated,
  fail-closed, AFTER Step 4 (reuses `_fragility` + `(_clk_suspect, _clk_reason)`,
  no second compute).
- **44 tests** (`§8B-MS1..MS13` + `§8B-MS6a..6e`; LLM/network mocked, real
  `FragilityReading` fixtures); `§8B-MS2` and `§8B-MS13` mutation probes
  discriminating; cap-vs-floor boundary fully covered. Codex 2 passes; fix round
  resolved 1 finding (`mid_confidence` floor → cap), Finding 2 approved AS-IS.
  Regression: MarketStructure 44, MacroRegime 24, MoneyFlow 34, AgentFramework 15,
  gex_dex 13, massive 5, quiver 6, 7B rotation 226. Phase doc
  `docs/reliability_market_structure_agent.md`.

**Prior:** Phase 8B MoneyFlowAgent (merge `760f356a3`)
- New `lib/agents/money_flow_agent.py`: GEX/DEX (`compute_gex_dex`) + dark pool
  (`compute_dark_pool_signal`) → evidence-backed `AgentOutput`. Three
  deterministic confidences before the LLM: `short = signals_agree_count/3`
  (degraded→0), `mid = strength_map × direction_valid` (strong 1.0/moderate
  0.6/weak 0.3), `long = 0.0` (intraday-to-3-week signal). Three ToolResults
  (`gex_dex_signals` / `dark_pool_signal` / `money_flow_confidence`).
- `_load_prior_gex_dex_result`: newest `MoneyFlowAgent` JSONL → `GexDexResult`
  for squeeze condition C; validates an 11-key `_REQUIRED_PRIOR_FIELDS` frozenset
  (missing field → `None`); fail-closed on unreadable/invalid file (`None`, no
  fall-through to older files). `supporting_data` carries all `GexDexResult`
  fields for next-run reconstruction.
- Prompt `REQUIRED OUTPUT FORMAT` (4-space indent, no fences); neutral GEX must
  name an options-structure strategy; no numbers in findings. All
  `lib.reliability`/`lib.agent_framework` imports lazy; outer fail-closed guard;
  `valid_until = end_of_today_iso()`.
- Cockpit hook: additive (`money_flow_agent_output`), key-gated, fail-closed,
  `ticker="SPY"`, no second fetch — immediately after the MacroRegimeAgent hook.
- **34 tests** (`§8B-MF1..11` + `§8B-MF8b/8c`; LLM/network mocked); `§8B-MF1`
  and `§8B-MF11` mutation probes confirmed discriminating. Codex 2 passes; fix
  round resolved 2 findings (required-field validation + unreadable-file
  fail-closed). Regression: MoneyFlow 34, MacroRegime 24, AgentFramework 15,
  gex_dex 13, quiver 6, reliability-foundation green. Phase doc
  `docs/reliability_money_flow_agent.md`.

**Prior:** Cockpit cold-start hydration (merge `3eb4a8912`)
- New Streamlit-free `lib/cockpit_hydration.py::hydrate_cockpit_from_snapshot`
  (injected loaders, default `audit_query`). Gated on absence of
  `macro_regime_result` AND `cockpit_hydrated_from_snapshot` → runs at most once;
  takes `metas[-1]` (most recent), filters opportunities to that date only.
- Hydrates **Section A** (`macro_regime_result` as a raw dict — regime /
  confidence / `key_signals` / `opportunity_posture` / `horizon_bias` /
  `fragility_level`; NOT via `save_regime_to_state` which would strip
  `fragility_level`) + `cockpit_fragility` (rebuilt from `MetaRecord.raw`, only
  when present) and **Section C** (`cockpit_opportunities` from `raw`, latest date;
  `why_now` non-dict reason-code strings dropped so the render can't crash).
- **Atomic** `session_state` commit, **fail-closed** (`try/except → None`), **no
  `st.rerun()`**. `cockpit_last_refresh = snapshot date` (hook before header).
  `macro_regime_agent_output` (valid_until=EOD) + Sections B/D/E **not** populated.
  Bilingual banner (`bi()`, EN+ZH) shown only on success.
- **10 tests** (`§CS-1..7` + 3 extra; injected loaders, no `AppTest`); `§CS-7`
  mutation probe confirmed discriminating. Regression: audit-query 10/10,
  cockpit-rebuild 47/47. Codex APPROVED (1 pass, 0 findings). UI verified. Phase
  doc `docs/reliability_cockpit_cold_start.md`.

**Prior:** _meta Extension — key_signals / opportunity_posture /
confidence (merge `ffe9e1e2`)
- Three deterministic `classify_regime` outputs persisted in the daily snapshot
  `_meta` block for cold-start hydration. `write_daily_snapshot` gains three
  kwargs (safe defaults) + a **pre-`try` collision guard** (`ValueError` on a
  `fragility` dict carrying a protected key — placed before the best-effort
  `try/except` so it propagates, not swallowed).
- `MetaRecord` gains three `.get()`-defaulted fields declared **after `raw`**
  (dataclass field-ordering); old snapshots missing the keys parse cleanly.
  Cockpit call site wired via `get_regime_field()`; lib stays Streamlit-free.
  Canonical ENGLISH persisted (no translation at write); no LLM values.
- **7 new parity checks** (`18.24` live-path + `§18-meta-new-1..6`). Mutation
  probe on `new-1` confirmed discriminating. Regression: 7b 226/226, 7a 115/115,
  7d 10/10, anchor_archive 77/77. Codex APPROVED (2 passes, 0 findings). Phase
  doc `docs/reliability_meta_extension.md`.

**Prior (recent):** Step 3 — Narrative Disk Cache (merge `a2e43cd3`)
- Disk-backed persistence for `llm_narrative_match` (`lib/signal_engine.py`): LLM
  narrative results (`data/narrative_cache/<TICKER>/<regime>_<fp>.json`) survive
  process restarts; a fresh hit skips the LLM entirely. In-memory `@st.cache_data`
  stays the hot path; disk is the cold-start fallback underneath.
- Cache key `(ticker, macro_regime, news_fingerprint)`. Fingerprint =
  `json.dumps([head, summ])` per record over `news[:25]` with `.strip()` +
  `summary[:160]`, joined `"\n"` — exact alignment with the LLM prompt input;
  collision-resistant. TTL 24h. Atomic write (temp + `os.replace`). All disk ops
  fail-closed; only `data_source="live"` results persisted (neutral fallbacks
  never written). `@st.cache_data` decorator + `(ticker, macro_regime)` signature
  untouched.
- Tests `scripts/test_narrative_disk_cache.py` **27/27** (§NC-1–7 + §NC-8a–8f;
  network/LLM fully mocked). Regression: 6b_v3 189/189, 6b_v2 217/217 GREEN.
  Three Codex passes (separator-collision + json.dumps field-boundary fix rounds)
  → APPROVED. Phase doc `docs/reliability_narrative_disk_cache.md`.

**Prior:** Phase 8B — MacroRegimeAgent production implementation (merge
`eabf0c2d`)
- Upgrades the first concrete agent from the Phase 8A smoke test to a production
  agent: deterministic macro regime classification → horizon-aware,
  evidence-backed `AgentOutput`. Every cited number (three confidence metrics +
  vote tally + regime-stability count) is computed in code and persisted as
  evidence BEFORE the LLM runs. **4 files changed; 24 tests; Phase 6A live macro
  suite 337/337 GREEN** after the `macro_regime.py` change.
- `lib/macro_regime.py`: additive `votes_risk_on` / `votes_risk_off` /
  `votes_total` on `MacroRegimeResult`, populated by `classify_regime()` (degraded
  path stays 0); `macro_state.serialize_regime` unaffected (field whitelist).
- `lib/agents/macro_regime_agent.py` (full rewrite): `_compute_short_confidence`
  (vote-agreement ratio), `_compute_mid_confidence` (consecutive same-regime days
  via `load_all_meta`, Guard A current-regime degrade + Guard B unknown-history
  break, `_MID_CONFIDENCE_BREAKPOINTS` saturating curve), `_compute_long_confidence`
  (`data_coverage × short_confidence`); `run_macro_regime_agent` accepts
  `MacroRegimeResult`/dict/`None`, builds TWO ToolResults, dynamic numeric-free
  task instruction, outer fail-closed guard; lazy `lib.reliability` imports.
- `pages/7_Investment_Cockpit.py`: additive, key-gated, fail-closed hook reusing
  the already-computed regime; stores `macro_regime_agent_output` only.
- Tests: `scripts/test_phase_8b_macro_regime_agent.py` 24/24 (M6 split into M6a
  Guard-A / M6b Guard-B; M11 asymmetric 5/1 tally). Two Codex rounds:
  Round 1 REJECT (M6 + M11 not discriminating; numeric in instruction) → Round 2
  APPROVE. All three mutation probes RED-confirmed.

**Prior (Phase 8B-0):** New Data Source Ingestion Layer (merge `69d7c9f`)
- Greenfield ingestion + processed-signal layer for two paid sources (Quiver
  Quantitative, Massive Options = Polygon). **3 new lib modules, 3 new test
  files, 1-line `signal_engine.py` comment, `.env.example` key rename; no other
  existing file modified.** 24 tests total (Quiver 6 + Massive 5 + GEX/DEX 13).
- `lib/quiver_fetcher.py`: `fetch_dark_pool` / `fetch_congress_trades` /
  `fetch_insider_trades` / `fetch_hedge_fund_positions` — fail-closed,
  `@st.cache_data` (TTL dark_pool=3600, others=86400); `compute_dark_pool_signal`
  pure deterministic aggregator (bullish/bearish/neutral thresholds inline;
  `prev_close` buy/sell proxy with 50/50 degraded fallback when absent).
- `lib/massive_options_fetcher.py`: `fetch_options_chain(ticker, expiry_filter)`
  → populates the Phase 2E `OptionContractSnapshot`/`OptionChainSnapshot`
  (`source="massive"`); paginated ≤5 pages; per-contract `try/except` skips bad
  contracts with a `contract_skipped:` warning; free-tier graceful
  (gamma=None + `greeks_unavailable: free tier`). TTL 900.
- `lib/gex_dex.py`: pure deterministic `GexDexResult` + `compute_gex_dex(chain,
  expiry_filter, prior_result=None)` (GEX/DEX sums, OI walls, 3-condition gamma
  squeeze monitor incl. `prior_result` DEX-trend), `find_walls`,
  `gex_dex_to_signals` (numeric-free `regime_summary`). Zero `lib.reliability`
  imports; never raises.
- **Free-tier caveat:** Massive free tier has NO Greeks/OI — live GEX/DEX needs
  the Starter plan ($29/mo). **Quiver `prev_close` field names need live-API
  confirmation** (parsers read defensively; fail-closed if absent).
- **Three Codex review rounds:** REJECT (per-contract guard + `prior_result`
  missing) → APPROVE WITH FIXES (verbose trigger token, test used `str()`) →
  APPROVE. All mutation probes RED-confirmed.

**Prior (Phase 8A):** Agent Framework Foundation (merge `f6a0f74`)
- The connective tissue that activates the dormant World 2 reliability layer.
  **7 new files; no existing file modified.** Two new namespace-only packages
  `lib/agent_framework/` and `lib/agents/`.
- `lib/agent_framework/agent_output.py`: `AgentOutput` `@dataclass` (10 required
  fields + `agent_result: Optional[AgentResult]` embedded + `debate_report`
  forward-ref for Phase 8B). `validate_judgment` blocks digits / % / $ / metric
  tokens. `agent_result_to_agent_output` flattens `findings[].evidence +
  risks[].evidence` (raises on empty). JSONL persistence `append_agent_output`
  / `load_agent_outputs` at `data/agent_outputs/<agent_id>/<date>.jsonl`.
- `lib/agent_framework/agent_runner.py`: `run_llm_agent` 11-step pipeline
  (tool_results → `EvidenceStore` at `data/agent_evidence/<agent_id>/<run_id>/`
  → evidence packet → constrained prompt → Claude → parse+validate →
  `AgentOutput` → persist). `AgentRunError` on validation `severity==error`;
  fail-closed fallback (`judgment_source="rule_based"`, human-confirm, synthetic
  EvidenceRef) on LLM/parse failure. System prompt carries the invariants
  (JSON-only, evidence-bound, no numeric fabrication, judgment constraint,
  `approved_for_execution` always False).
- `lib/agent_framework/world_adapter.py`: `llm_output_to_tool_result` +
  `processed_signals_to_tool_result`; `_normalize_to_dict` converts dataclass
  inputs (e.g. `MacroRegimeResult`) via `dataclasses.asdict` before validation.
- `lib/agents/macro_regime_agent.py`: `run_macro_regime_agent` MacroRegimeAgent
  smoke test (accepts the `MacroRegimeResult` dataclass or a plain dict) +
  `end_of_today_iso`.
- **Import discipline:** every `lib.reliability` / `lib.llm_orchestrator` import
  is lazy (inside functions); importing `agent_framework` never triggers the
  52-module eager `lib.reliability.__init__`. Verified by a subprocess guard.
- Tests `scripts/test_agent_framework_foundation.py` §8A.1–§8A.11 **11/11**
  (in-memory / monkeypatched; §8A.10 subprocess import guard; §8A.11 dataclass
  normalization discriminating test, RED confirmed without `_normalize_to_dict`).
- **Two Codex review rounds:** REJECT (R4.2 — dataclass normalization missing) →
  fix → APPROVE WITH FIXES (docstring drift) → fix → APPROVE.

**Earlier:** Phase 7D Block A — Snapshot Audit Query Interface CLOSED (merge
`5a57850`, UI-verified EN + 中文 2026-06-19). Phase 7C / 7B / Anchor Intelligence
v2 series history below and in `PROJECT_STATE.md`.

**Next:** Cockpit cold-start hydration (冷启动快照水化) — load the latest
`data/snapshots/` daily snapshot into Sections A/C on restart with empty
`session_state` (B/D/E degraded placeholders + a snapshot-date banner; needs an
`audit_query` import in `pages/7_Investment_Cockpit.py`). Phase 8B continued
(MoneyFlowAgent, consuming the 8B-0 GEX/DEX + dark-pool signals) remains queued
after it.

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
