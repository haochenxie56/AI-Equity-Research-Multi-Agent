# Phase — Anchor Intelligence v2

> **Round-1 lesson (read first).** *Unifying a producer with multiple callers is
> an access-path problem, not a physical merge — map the caller-contract matrix
> (page = needs band + allows network; ranker = network-free; refresh = no-poison)
> before implementing.* The two fix rounds below all trace back to skipping that
> matrix: the same `compute_app_fair_value` producer is correct, but each caller
> reaches it under a different contract (network allowed vs. forbidden; first
> writer must not poison the shared cache entry; cold cache must degrade honestly
> rather than fabricate). Round 1 became "one producer, three access contracts,"
> not "one function."

**Status:** **Round 1 — CLOSED.** The round-1 delivery (U1/U2/U3) plus the two
hardening fix rounds (F-round, X-round) and the R3 real-path fix were reviewed and
**APPROVED at `9e53f04`**. Suite
`scripts/test_reliability_phase_6c_v3_entry_v4.py` **90/90** (52 → 73 after fix
round 1 → 87 after fix round 2 → 90 after the R3 missing-OHLCV real-path case);
canonical sweep green. **All deterministic; no LLM invents a fair-value anchor.**

**Update — v2.3 fully CLOSED.** The v2.3 anchor-historization main body (U1
append-only archive at the `store_equity_research_result` producer chokepoint / U2
single-vintage snapshot anchor block / U3 deterministic migration readout +
read-only `thesis_monitor` watch note; fix round F1–F4) was reviewed and **APPROVED
at `9f6c37e`** and merged into `main` at `97c8f1f`. The **historical backfill** —
recomputable anchors only, the analyst anchor never fabricated for a past date, with
the G1 filing-lag look-ahead defence and the G2 same-date seam guard; suite
`scripts/test_reliability_anchor_backfill.py` **60/60** — was reviewed and
**APPROVED at `c57e56e`** and merged now. **Round v2.4 is now CLOSED** (valuation
diagnosis card + F4 archive sharding; APPROVED at `18dfcf2`, merged into `main` via a
`--no-ff` merge commit). **Round v2.5 — multi-dimensional peer profile + honest
`peer_match_quality` degrade — is the FINAL v2 round; implemented on branch
`phase-anchor-intel-v2-5` (off `main` @ `ef8cb28`). The B1 fix round (peer signature
in the cache key — kills the cache-order dependence) is applied at `4feb9de`; new
suite `scripts/test_reliability_anchor_peer_match.py` 49/49 (incl. the §10
both-orders cache test), canonical sweep green, awaiting re-review.** See "Round
v2.5" below. With v2.5 the v2 series is complete.

## Goal

Eliminate the documented failure mode where the same ticker shows a different
fair-value anchor depending on which surface renders it (Trading Desk vs. Equity
page vs. Cockpit), because two producers (`lib/equity_valuation` and
`lib/valuation_anchor`) computed different fair values and different callers read
different ones. Round 1 collapses production onto a single producer, makes the
sell-side analyst input a structured pool rather than a scalar proxy, and stamps
every rendered card with the producer epoch so divergence is detectable.

## Round 1 — delivered tasks

- **U1 — single fair-value producer.** `order_advisor._gather_technicals` computes
  the anchor via `lib.equity_valuation.compute_app_fair_value` (`AppFairValue`)
  instead of the retired `lib.valuation_anchor.compute_fair_value_anchor`.
  Production now has ONE producer and ONE `st.cache_data` entry per ticker; the
  Trading Desk, Equity page, and Cockpit all render from the same producer/epoch.
  The entry-strategy FORMULAS are unchanged (×0.90 high-confidence, ×0.85
  medium-confidence margin of safety); only the anchor INPUTS migrated (field
  migration B → A):
  - `confidence` ← `AppFairValue.confidence`
  - `conservative_anchor` ← tier-dependent: high = `fair_value_mid`,
    medium = `analyst_target`, low/suppressed = None. **Not** `fair_value_low` —
    using the band floor here would double-discount against the ×0.90 MoS (see
    `_app_conservative_anchor`).
  - `fair_value_anchor` ← `fair_value_mid` (scalar)
  - irreconcilable check ← `blend_state == "anchors_irreconcilable"`
  - dropped: the `valuation_percentile` percentile-discount fallback (A has no
    such fallback; A's no-anchor band already degrades on current price, and the
    LONG path's existing low-confidence degrade covers it).
  `lib/valuation_anchor.py` is deprecated — retired from production, kept for
  backward compatibility only.
- **U2 — structured analyst anchor + pool-dispersion confidence gate.**
  `AppFairValue` carries the sell-side target distribution as a structured
  `analyst_pool` `{median, mean, high, low, n, as_of}`; the median remains the
  central estimate entering the blend. `_fetch_raw` now pulls
  `targetHighPrice`/`targetLowPrice`; `_assemble_fair_value` builds the pool. A
  pool-dispersion confidence gate — `pool_dispersion = (high − low) / median`,
  threshold **1.0×**, minimum **n = 3** — caps confidence at low and emits
  `CAVEAT_ANALYST_POOL_DISPERSED` when it fires. The gate is **confidence-only**:
  the blend still proceeds, and the pre-existing inter-method dispersion gate is
  untouched and still runs last.
- **U3 — epoch stamping + single-source-per-card.**
  `PriceLevelResult.fair_value_computed_at` carries the `AppFairValue` epoch (the
  external/session band's `computed_at` when that band drives the card, else the
  local `AppFairValue.computed_at`). `computed_at` is computed once and shared
  (also the pool's default `as_of`). Single-source-per-card: when an external band
  drives the card, `valuation_confidence` AND `conservative_anchor` AND the epoch
  all come from THAT band — no mixed-source read against the local `fva_obj`.

## Fix round 1 (F-round, all APPROVED at 9e53f04)

The first review surfaced that "one producer" was not yet "one cache entry."

- **F1 — true single cached producer.** The page-path cyclical-band fetcher is
  threaded into the producer call so all live-compute sites share ONE cache entry
  and ONE epoch. Parity is proven on the REAL invocations: the rewritten §10
  reproduces the actual Equity-page call WITH the cyclical fetcher (the prior
  parity test omitted it — the D2 gap), and asserts the REAL Equity vs. REAL
  Trading-Desk paths share one entry with identical anchor AND identical
  `computed_at` (first-writer-wins consistency).
- **F2 — external band single source.** The external band is sourced once rather
  than re-derived per caller.
- **F4 — token rename (C5).** The misleading `fair_value_source` token
  `analyst_proxy` (the local producer was never an "analyst proxy") is renamed to
  `app_fair_value`. The historical Phase 6C-B changelog row is left as the record
  of the original name.
- Suite grew 52 → 73, then 73 → 87 across the F-round work.

## Fix round 2 (X-round, all APPROVED at 9e53f04)

The X-round separated the caller contracts explicitly — the heart of the round-1
lesson.

- **X1 — ranking path structurally network-free.** `compute_price_levels` gains
  `allow_fetch: bool = False` (fail-closed), plumbed to
  `_gather_technicals(*, allow_fetch=False)`. The live producer
  (`compute_app_fair_value` + `fetch_cyclical_band_history`) is now imported AND
  called ONLY inside the `allow_fetch` branch, so the ranker / Cockpit-refresh path
  never reaches a live fetch. Page paths set `allow_fetch=True` (pages/9 both call
  sites + `build_order_recommendation`); `opportunity_ranker` does not pass it
  (stays False). A cold cache on the network-free path degrades honestly:
  `valuation_unreliable` + `fair_value_source="anchor_not_cached"` with
  `fair_value_anchor=None`.
- **X2 — Cockpit no cache poison (Option B).** `pages/7 _run_equity_research` is an
  interactive on-demand page path (not the network-free refresh/rank path), so it
  now passes `cyclical_history_fetcher=fetch_cyclical_band_history`. Because the
  fetcher is excluded from the `st.cache_data` key, a first writer that omitted it
  would poison the shared entry (a later band-requiring caller silently reuses a
  non-band entry). All three live-compute sites — pages/4,
  `order_advisor._gather_technicals`, pages/7 — now pass the fetcher, so no path
  can write a poisoning entry.
- **X3 — external band truly single-source (inverse leak).** The local `fva_obj`
  irreconcilable check is gated so a HEALTHY external band is not degraded by an
  irreconcilable LOCAL instance; `_compute_initiate_logic` degrades to
  technical-only when an external band is set but the app-FV branch could not build
  a band, rather than reading the local `fva_obj`.
- Suite grew 73 → 87 with the X-round real-path test sections (13/14/15).

## R3 fix (APPROVED at 9e53f04)

- **Clear the fabricated anchor on the cold / missing-OHLCV `anchor_not_cached`
  path.** When OHLCV is unavailable the cold-cache branch returns the
  `_gather_technicals` fixture dict, which seeds a back-computed
  `fair_value_anchor = current_price × 0.85` to keep the technical logic
  well-formed. The `anchor_not_cached` branch flagged the degrade but never cleared
  that fabricated scalar, so `cp×0.85` rode through — a fabricated number where the
  honest-degrade contract requires None. Fix: in the not-`allow_fetch` &
  band-is-None cold branch, explicitly set `tech["fair_value_anchor"] = None`. The
  contract now holds: `anchor_not_cached` ⇒ `fair_value_anchor` None, no zone,
  `valuation_unreliable`, degrade token.
- **Proven on the REAL transitive path.** §13.7–13.9 drive the actual ranker entry
  point `rank_opportunities → compute_price_levels → _gather_technicals` with an
  empty `anchor_cache` and `load_ohlcv` stubbed to None, so the missing-OHLCV
  branch is reached transitively (a thin observer captures each per-horizon
  `PriceLevelResult` without replacing the transitive logic). The earlier
  direct-call shape was removed as redundant — it was the same direct-call shape
  that let the original cold-cache network violation slip. Discrimination verified:
  reverting the one-line clear makes 13.8 FAIL with `[85.0]`. Suite 87 → 90.

## Reliability invariants preserved

- Deterministic computation unchanged: the fair value is computed by
  `lib/equity_valuation`, not inferred by an LLM. No anchor, band, confidence, or
  epoch is invented by a model.
- The honest-degrade contract is strengthened, not weakened: a cold / missing-data
  path now yields `fair_value_anchor=None` + `anchor_not_cached` rather than a
  fabricated `cp×0.85` scalar.
- The ranker / Cockpit-refresh path is structurally network-free
  (`allow_fetch=False` by default); live fetches happen only on explicit page
  paths.
- `lib/macro_regime.py` untouched; entry-strategy formulas (×0.90 / ×0.85)
  unchanged.

## Files

- **Modified (production):** `lib/order_advisor.py`, `lib/equity_valuation.py`,
  `lib/anchor_cache.py`, `lib/valuation_anchor.py` (deprecated), `pages/4_Equity.py`,
  `pages/7_Investment_Cockpit.py`, `pages/9_Trading_Desk.py`, `ui_utils.py`.
- **Added:** `.gitattributes` (enforce LF line endings — third CRLF churn
  incident).
- **Tests:** `scripts/test_reliability_phase_6c_v3_entry_v4.py` (90/90),
  `scripts/test_reliability_phase_6c_v2_entry_strategy.py`,
  `scripts/test_reliability_phase_6c_trading_desk.py`,
  `scripts/test_reliability_phase_6c_b_cockpit_rebuild.py`,
  `scripts/test_reliability_valuation_router.py`.
- **Docs:** this file (new); `docs/ai_dev_state/PROJECT_STATE.md`,
  `docs/ai_dev_state/CURRENT_TASK.md` (round-1 closure entries).

## Round v2.3 — anchor historization (fix round applied — awaiting re-review)

> **Round-1 lesson applied first.** Historization is again an *access-path*
> problem: the same anchor value must be (a) read read-only on the network-free
> ranking/refresh path, (b) written to an append-only archive ONLY on page paths,
> and (c) read read-only from the archive by migration consumers. Skipping the
> matrix is the documented cause of the prior fix rounds, so the matrix below is
> committed BEFORE any code (STEP 0).

### STEP 0 — caller-contract matrix (audited against the real call sites)

Every call site that touches `anchor_cache` or `compute_app_fair_value` was
audited and placed in exactly one row. No caller was left unclassified.

| caller (verified file:line) | reads anchor from | writes archive | live network |
|---|---|---|---|
| `pages/4_Equity.py:668,877` (compute) → `:748,855,891,900` (`store_equity_research_result`) | live compute (`compute_app_fair_value`, fetcher passed) | **YES** (append at the producer chokepoint, on the `compute_app_fair_value` call) | allowed |
| `pages/7_Investment_Cockpit.py::_run_equity_research` `:394` (compute) → `:404` (store) | live compute (fetcher passed) | **YES** (append at the producer chokepoint) | allowed |
| `pages/9_Trading_Desk.py:295,336` → `order_advisor.compute_price_levels(allow_fetch=True)` → `_gather_technicals:1422` → `compute_app_fair_value` | live compute (fetcher passed) | **YES** (append at the producer chokepoint) — **F1 correction:** pages/9 live-computes its OWN `AppFairValue` and never calls `store_equity_research_result`, so the earlier "originates from pages/4/7" claim was FALSE; it IS a write path | allowed (`allow_fetch=True`) |
| `pages/7_Investment_Cockpit.py::_run_refresh` `:267` → `rank_opportunities(anchor_cache=…)` `:328` → `compute_price_levels` (default `allow_fetch=False`) | `anchor_cache` hot cache ONLY (`load_all`, read-only) | **NO** (read-only) | **FORBIDDEN** (`allow_fetch=False`, already enforced X1) |
| `lib/opportunity_ranker.rank_opportunities` (default `price_levels_fn`) | `anchor_cache` map passed in (read-only) | **NO** | **FORBIDDEN** (never passes `allow_fetch`) |
| `lib/thesis_monitor.check_holding` / `run_thesis_monitor` (v2.3 NEW consumer) | archive (`anchor_archive.read_archive`, historical series) — read-only | **NO** | **FORBIDDEN** (no compute, no fetch) |

Derived invariants (all enforced by tests):

1. **Archive write only where `allow_fetch=True` — at the producer chokepoint.** The
   single archive-append site is `equity_valuation.compute_app_fair_value` itself
   (appended on its live return). Per X1 this producer is invoked ONLY on
   `allow_fetch=True` page paths — pages/4, pages/7 `_run_equity_research`, AND
   pages/9 via `order_advisor._gather_technicals` — so ALL three page paths are
   historized by one hook, while the ranking / `_run_refresh` path (which consumes
   `anchor_cache` and never calls the producer) appends NOTHING. **F1 fix:** the
   append was moved here from `store_equity_research_result`, which the Trading Desk
   (pages/9) never calls — the prior chokepoint silently dropped every pages/9 live
   anchor from history. Only `data_source == "live"` results are historized (a
   fixture fallback is never written), and identical `(ticker, computed_at)`
   re-reads from the cached worker are deduped (a cache re-surfacing of one vintage,
   not a new valuation); a genuine recompute carries a fresh `computed_at` and IS
   appended (append-only keeps real vintages). **Dedup decision:** append-only
   favors keeping distinct vintages, but the cached worker re-surfaces the SAME
   `computed_at` when one ticker is valued twice in a session (pages/4 then pages/9),
   which would double-count one vintage in the migration series — so identical
   `(ticker, computed_at)` is intentionally deduped, not accidentally duplicated.
2. **Append-only.** Archive records are never rewritten or mutated in place
   (mirrors git's no-rewrite-published-history rule). Only appends.
3. **Cold ranking = zero archive writes + zero network.** Extends the v2 §13
   transitive harness.
4. **Snapshot anchor block is single-vintage and read-only.** Sourced from the
   SAME `anchor_cache` read that drove the LONG status (no live compute); a ticker
   with no cached anchor records `anchor_not_cached` (the R3 token), never a
   fabricated value.
5. **Migration consumers read the archive only.** `thesis_monitor` reads the
   migration readout; it never triggers a compute or fetch, and a deteriorating
   migration may ELEVATE a watch annotation but never auto-generates a sell/exit
   (review-only invariant; mirrors the D2 fragility annotation).

### U1 — append-only anchor archive (`lib/anchor_archive.py`)

- New module mirroring `lib/anchor_cache.py` + the daily-snapshot atomic pattern:
  append-only JSONL at `data/anchor_archive.jsonl`. `anchor_cache.json` stays the
  hot "latest" cache (unchanged role).
- `ANCHOR_ARCHIVE_SCHEMA_VERSION = 1` (one visible constant; read-time version
  guard skips records of any other version → forward-migration safe).
- Record schema: `{schema_version, ticker, computed_at, data_vintage,
  company_type, fair_value_low, fair_value_mid, fair_value_high, blend_state,
  analyst_pool{median,mean,high,low,n}, methods_used, excluded_anchors, caveats}`.
  `data_vintage` is the date (`YYYY-MM-DD`) of the page-path compute, defaulted
  from `AppFairValue.computed_at` (the free-source snapshot is same-day); an
  explicit override is accepted for future precision. This is a documented real
  timestamp, not a fabricated bar-date.
- API: `record_from_app_fair_value(fv, *, data_vintage="")` (pure),
  `append_anchor_record(fv, *, data_vintage="", path=None) -> bool` (atomic
  append, fail-closed, never mutates a prior row), `read_archive(ticker, *,
  window=None, path=None)` and `load_all_records(path=None)` (read-only).
- Wired at the **producer chokepoint** `equity_valuation.compute_app_fair_value`
  (appended on its live return), so all three page paths — pages/4, pages/7
  `_run_equity_research`, AND pages/9 (Trading Desk, via
  `order_advisor._gather_technicals`) — are historized by ONE hook (F1). No page
  signature change. `data_source == "live"` only; identical `(ticker, computed_at)`
  re-reads deduped.

### U2 — snapshot carries the anchor block

- `anchor_cache` entry now also persists `analyst_pool` (additive in
  `entry_from_app_fair_value`; **no schema bump** — old v2 entries simply lack it
  and the snapshot records the pool as absent until rewarmed, which is graceful and
  avoids wiping the whole cache).
- `OpportunityCard.anchor_snapshot` (new field) is populated in
  `rank_opportunities` from the SAME `anchor_cache` lookup that drove LONG status
  (single vintage): `{company_type, fair_value_mid, analyst_pool{…}, computed_at,
  blend_state, caveats}` for a fresh entry, else `{"state": "anchor_not_cached"}`.
- `_card_snapshot_record` serializes it under the `"anchor"` key. PARITY: a
  §18-style test drives the real ranker → `write_daily_snapshot` → read-back and
  asserts `anchor.fair_value_mid` / `anchor.computed_at` equal the cache entry that
  drove the row (fails if they disagree), and `anchor_not_cached` when no entry.

### U3 — deterministic anchor-migration readout (`lib/anchor_migration.py`)

- `MIGRATION_WINDOW_SESSIONS = 30` (single visible config block). Pure,
  deterministic, no LLM, no I/O in the compute (`compute_migration(records,
  window=…)`); a thin `read_migration(ticker, …)` reads the archive read-only then
  computes.
- Per anchor series (`fair_value_mid`, `analyst_pool.median`,
  `analyst_pool.mean`): `direction` (rising/falling/flat), `speed` (Δ/session),
  and cross-series `consistency` — multi-anchor co-movement = `conviction`;
  lone-anchor drift = `low_consistency` (flagged). This is the data source for
  thesis_monitor's "logic break vs price noise" distinction.
- `thesis_monitor.check_holding` consumes the readout READ-ONLY of the archive:
  new fields `anchor_migration` / `anchor_migration_watch` / `anchor_migration_note`
  (mirrors the D2 fragility annotation). A systematic falling analyst-pool downshift
  (`falling` + `conviction`) ELEVATES a watch note (surfaced in `summary`); it
  NEVER changes `thesis_status` and NEVER emits a sell/exit. No new LONG/exit logic.

### R8 residue cleanup

With the archive in place the read paths are coherent: ranking/refresh reads
`anchor_cache` (hot) read-only with `allow_fetch=False`; migration consumers read
the archive read-only. No path is both forbidden-to-fetch and writing-archive (the
archive write lives only on the `allow_fetch=True` page chokepoint).

### Known operational characteristic — archive read cost (F4, document-only)

`anchor_archive._iter_records` reads the **entire** archive (`read_text`) and
filters by ticker/window only afterward, so every `read_migration` /
`read_archive` call is **O(total archive bytes)** in time and memory. This is
accepted for now: the archive starts empty and grows by one short JSONL line per
page-path live valuation (a few hundred bytes), so reads are negligible at current
scale. The F1 append-dedup does **not** amplify this — it is an O(1) in-process
memo and never reads the archive on the page path.

**Must-fix trigger (either):**
- the archive file exceeds **~5 MB** (≈ tens of thousands of valuation rows), OR
- the thesis-monitor refresh shows **perceptible latency attributable to archive
  reads** (a rule of thumb: > ~200 ms of a `check_holding` batch spent in
  `_iter_records`).

**Planned remedy (target round v2.4):** per-ticker sharding
(`data/anchor_archive/<TICKER>.jsonl`, so a read touches only one ticker's bytes),
OR a window-bounded reverse/tail read that stops after the most-recent N records,
OR a small ticker→byte-offset index. Sharding is the leading candidate (it also
bounds the dedup-memo growth and keeps the append atomic). Not implemented this
round — recorded here so the cost is intentional with a concrete repayment plan,
not a silent debt.

### Fix round (REQUEST CHANGES — F1–F4)

- **F1 (P1)** — archive every page-path live anchor. Moved the append from
  `store_equity_research_result` to the producer chokepoint
  `compute_app_fair_value`, so pages/4, pages/7 AND **pages/9** (Trading Desk, which
  never calls the hand-off) are all historized by one hook; `data_source=="live"`
  only; identical `(ticker, computed_at)` deduped (in-process O(1)). Matrix
  corrected (pages/9 IS a write path). Dedup decision documented (keep distinct
  vintages, collapse same-vintage cache re-reads).
- **F2 (P1)** — surfaced the migration note: `thesis_monitor._summary()` appends the
  bilingual note when deteriorating, and the Trading Desk order card renders it.
  Watch-level only — `thesis_status` unchanged, no sell/exit.
- **F3 (P2)** — §7 parity now asserts source-equality for ALL block fields
  (`fair_value_mid`, `computed_at`, `analyst_pool`, **`company_type`,
  `blend_state`, `caveats`**) vs the `anchor_cache` source, plus a binding/exclusion
  completeness partition over `ANCHOR_SNAPSHOT_KEYS` (mirrors §18).
- **F4 (P2)** — documented above (archive read is O(total bytes); trigger + remedy +
  target round v2.4); not implemented this round.

### Results

- **New suite** `scripts/test_reliability_anchor_archive.py` — **47 → 59** (fix
  round): U1 record/append-only/schema-guard; **F1** producer-chokepoint archive
  incl. the REAL pages/9 `compute_price_levels(allow_fetch=True)` path + dedup +
  fixture-not-archived + store-no-longer-writes; U3 migration determinism + read-only
  thesis consumption; **F2** summary surfacing + Trading-Desk binding; U2 + **F3**
  full snapshot-block parity + binding/exclusion completeness.
- **`scripts/test_reliability_phase_6c_v3_entry_v4.py`** grew **90 → 92** (§13.10 /
  §13.11): a cold `rank_opportunities` run appends **ZERO** archive records AND
  makes **ZERO** network calls — the real-path DoD guarding the page-path-only
  archive write.
- Suites exercising the change are green: `valuation_stopbleed`,
  `phase_7a_opportunity_ranking` (115/115), `phase_7b_rotation_internals`
  (193/193 — its §18 `_meta` parity is unaffected; the new `anchor` field is on the
  per-card record, and its parity lives in the new suite §7), `phase_6c_*`,
  `valuation_router`, `phase_6c_b_cockpit_rebuild` (47/47).
- The 13 red suites in the full `test_reliability_*` sweep are **pre-existing and
  orthogonal** — proven by stashing the v2.3 tracked edits and re-running: the
  identical 13 (CURRENT_TASK doc-state, page-file existence, sidebar nav,
  `signal_engine`/`llm_orchestrator`, Streamlit AppTest `url_pathname`) fail on the
  base commit `f6a930b` with identical counts. The v2.3 diff touches none of those
  files.
- `.gitattributes` keeps LF (`git diff --check` clean); `lib/macro_regime.py`
  untouched; i18n additive (the migration watch note is a bilingual inline string
  mirroring the D2 fragility annotation — no `TRANSLATIONS` change).
- New degradation state: none — `anchor_not_cached` is the existing R3 honest-degrade
  token, reused for the snapshot block.

## Round v2.3 — historical backfill (awaiting review)

> The archive (U1) only accumulates from today forward, so U3's migration readout
> would cold-start with 1–2 months of empty history. Anchors whose INPUTS are
> public historical series CAN be recomputed for past dates — this round adds a
> one-time, offline backfill for the **recomputable anchors ONLY**, giving the
> migration readout real history on day one.

### HARD INVARIANT — the never-fabricate line

| anchor | backfilled? | why |
|---|---|---|
| DCF | **YES** | historical FCF (annual OCF − \|CapEx\|) + shares + YoY growth — all dated |
| relative-PE (sector P/E × historical EPS) | **YES** | sector P/E is a static map; EPS is a dated income-statement row |
| PB/PS cyclical band | **YES** | the v1 builder already does as-of PB/PS; reused unchanged |
| **analyst pool** | **NEVER** | free sources expose ONLY the CURRENT pool — no historical analyst-target series exists anywhere. Backfilled `analyst_pool` = sentinel `analyst_history_unavailable` (never a number, never None, never today's pool back-dated) |
| forward-EPS consensus | **NEVER** | CURRENT-only; left absent (relative anchor falls to trailing EPS) |

A backfilled record is **PARTIAL by construction** (price/financial anchors
present, analyst absent + flagged), tagged `record_origin="backfill"`,
`data_vintage` = the historical as-of date.

### B1 — backfill engine (`lib/anchor_backfill.py`)

- Visible config block: `BACKFILL_WINDOW_MONTHS = 6`, `BACKFILL_CADENCE_DAYS = 7`
  (weekly → ≈ 26 as-of points; the grid is anchored at `end_date` and steps
  BACKWARD so the newest point lines up with the live series).
- Pure core `compute_backfill_records(...)` (no I/O): for each as-of date it slices
  the dated statements + price history to ≤ that date, builds an as-of `raw`
  (historical-derivable fields only; analyst/forward always `None`), and **reuses
  the live assembler** `equity_valuation._assemble_fair_value` with an as-of
  cyclical-band fetcher that calls the SAME `build_pb_ps_history` — no anchor math is
  reimplemented. The result is mapped to a partial archive record (analyst sentinel,
  historical `computed_at`/`data_vintage`).
- Degrade honesty: an as-of date with no real anchor (`blend_state == "no_anchor"`,
  insufficient fundamentals) ZEROES the band and adds
  `backfill_insufficient_fundamentals` — a current-price stub never enters history;
  an as-of date with no price at all yields NO record (price is never fabricated).

### B2 — one-time, offline, idempotent (`scripts/backfill_anchors.py`)

- Explicit on-demand script — NOT on app startup, NOT on the ranking/refresh path.
- **Idempotency = persistent guard:** `backfill_ticker` reads the archive's existing
  `record_origin=="backfill"` `data_vintage` set (`anchor_archive.backfilled_vintages`)
  and skips already-covered as-of dates, so a double-run writes ZERO duplicate rows
  (robust across process restarts — the in-process append memo is not). Append-only.
- Network discipline: the fetch reads historical prices + dated statements + the
  static `sector` label only; it NEVER calls any analyst-target endpoint.

### B3 — U3 consumes mixed-origin history honestly (`lib/anchor_migration.py`)

- Price-anchor migration (`fair_value_mid`) spans the FULL backfilled+live set; the
  analyst series spans ONLY the live records (the sentinel yields no analyst value,
  via `_value_for`). New additive readout keys: `origins{live,backfill}`,
  `price_span_n`, `analyst_span_n`, `analyst_history_available`, and
  `analyst_history_note` (+ `analyst_history_insufficient` caveat) — so the readout
  never pretends the analyst series reaches back as far as the price series.
- `thesis_monitor` surfaces the bilingual note (`分析师历史不足 | analyst history
  insufficient`) as INFORMATIONAL context (new `anchor_migration_analyst_note`) — NOT
  a watch, NEVER changes `thesis_status`.

### Schema decision

`record_origin` is purely **additive** with **no `schema_version` bump** (absent ⇒
`"live"`) — the same additive-no-bump precedent as U2's `anchor_cache.analyst_pool`.
Bumping would orphan older live rows behind the read-time version guard.

### Results

- **New suite** `scripts/test_reliability_anchor_backfill.py` — **46/46**:
  determinism + live-assembler reuse (no `_fetch_raw`/producer reached) + golden
  band; the never-fabricate sentinel + its discrimination; degrade/no-price honesty;
  idempotent double-run (zero dup rows) + append-only; mixed-origin migration
  (price full-span / analyst live-span) + honest labels; thesis info-note (no watch);
  cold-ranking offline-only.
- `scripts/test_reliability_anchor_archive.py` **59 → 60** (record_origin additive
  key + default-live assertion).
- Canonical sweep green: entry_v4 **92/92**, 7A **115/115**, 7B **193/193**,
  valuation_router **104/104**, 6c_b **47/47**, stopbleed **65/65**. Full
  `test_reliability_*` sweep **GREEN=64 / RED=13**; the 13 are the documented
  pre-existing orthogonal failures (5e–5s UI/AppTest, agent_evaluation,
  6b_signal_layer's `signal_engine`-imports-`llm_orchestrator` assertion) — none
  touch this round's files.
- `lib/macro_regime.py` untouched; i18n additive (inline bilingual note, no
  `TRANSLATIONS` change); `.gitattributes` keeps LF (`git diff --check` clean).

### Backfill fix round (REQUEST CHANGES — G1/G2, both P1)

- **G1 (P1, look-ahead leak — core defect).** `_slice_frame_asof` filtered by
  fiscal-period END, treating a statement as available on its period-end though it
  is filed weeks later — recomputing a past-date anchor with a not-yet-public
  statement is look-ahead bias that contaminates the whole backfilled history. The
  free loader has no filing-date metadata, so a **conservative publication-lag** is
  applied: visible config `FILING_LAG_DAYS = {annual: 75, quarterly: 45}`; a
  statement counts at as-of date `D` only when `period_end + filing_lag <= D` (errs
  toward using data LATER, never earlier — the only safe direction). The gate is
  threaded from `_backfill_one` (annual lag) into the slices feeding BOTH the
  DCF/relative `raw` (via `_newest_cols`) AND the cyclical PB/PS band (the gated
  frames are handed to `build_pb_ps_history`), so no anchor can read a too-fresh
  statement. A date the lag leaves with insufficient fundamentals degrades (zeroed
  band + `backfill_insufficient_fundamentals`) — it NEVER falls back to a
  not-yet-public statement. Corrected goldens: a date just after a period-end but
  before `period_end+75` uses the PRIOR year (mid **112.0**); after the lag the
  fresh statement is used (mid **103.47**). Discrimination: reverting the gate
  (`lag=0`) leaks the fresh statement and the assertions fail.
- **G2 (P1, seam double-count).** The weekly grid includes `end_date`, but the
  idempotency guard skipped only existing **backfill** vintages — an existing
  **live** row for that date did not prevent a backfill row, so migration counted
  the seam date twice. New read-only `anchor_archive.covered_vintages` spans BOTH
  origins; `backfill_ticker` now skips any date already covered by a live OR
  backfill record (live wins — a real contemporaneous compute beats a historical
  approximation). `backfilled_vintages` is retained for diagnostics.
- **Results.** `scripts/test_reliability_anchor_backfill.py` **46 → 60** (+8 G1
  filing-lag gate / corrected goldens / discrimination / pre-filing degrade; +6 G2
  same-date seam guard + single-count migration). Canonical sweep unchanged-green
  (entry_v4 92, 7A 115, 7B 193, router 104, 6c_b 47, stopbleed 65, archive 60);
  full `test_reliability_*` **GREEN=64 / RED=13** (identical pre-existing reds).
  `macro_regime.py` untouched; no i18n change this round; `git diff --check` clean.

## Round v2.4 — valuation diagnosis card + archive sharding (F4 repayment)

> **Round-1 lesson applied first (STEP 0 before any code).** Both features in this
> round are *access-path* problems, not feature-bolt-ons. The **diagnosis card** is
> an *assembly* problem: which surface already holds the `AppFairValue` / migration
> readout, and does reading it on that surface trigger a live compute (it must not
> on any network-free path)? **Archive sharding** is a *reader-migration* problem:
> every current reader of the single-file archive must move to the bounded
> per-shard read, or the O(total) cost survives in the un-migrated caller. The two
> matrices below are committed BEFORE the code.

### STEP 0 — caller-contract matrix (audited against the real call sites)

#### Matrix A — valuation diagnosis card

Every render surface that will show the card, the data it READS, and whether that
read triggers a live compute/fetch. The card is a **render-time assembly**; it adds
**no** anchor math and **no** new network call on any path.

| surface (verified file:line) | reads from | live compute / fetch? |
|---|---|---|
| `lib/valuation_diagnosis.build_valuation_diagnosis(fv, migration)` (NEW, pure) | its arguments only | **NO I/O** — pure function; identical inputs → identical `ValuationDiagnosis` |
| `lib/valuation_diagnosis.classify_valuation_role(...)` (NEW, A2) | `(confidence, anchor_consistency, upside_vs_price, blend_state)` scalars | **NO I/O** — pure deterministic config-table lookup |
| `pages/4_Equity.py` (renders in the `fv_slot` expander, after the range bar ~:838) | `_fv` — the `AppFairValue` ALREADY in `st.session_state[_fv_key]`, computed once on the page path at `pages/4_Equity.py:668` (`compute_app_fair_value`, `allow_fetch` page path) **+** `anchor_migration.read_migration(ticker)` (read-only archive) | **NO new compute** — reuses the already-computed `_fv`; `read_migration` is read-only, **zero network** |
| `pages/9_Trading_Desk.py` (renders in the LONG valuation block ~:925–1064) | `levels.app_fair_value_obj` — **NEW** `PriceLevelResult` field carrying the `fva_obj` the page-path `compute_price_levels(allow_fetch=True)` ALREADY live-computed at `order_advisor._gather_technicals:1422` **+** `_chk.anchor_migration` — the migration readout `thesis_monitor.check_holding` ALREADY read read-only at `thesis_monitor.py:590` | **NO new compute** — reuses the already-computed `fva_obj` + the migration the monitor already read |

Derived invariants (enforced by tests):

1. **No card read triggers a live compute or fetch.** pages/4 reuses the session
   `_fv`; pages/9 reuses the `fva_obj` already computed inside `compute_price_levels`
   (threaded out on the new `PriceLevelResult.app_fair_value_obj` field — set ONLY
   when `fva_obj` exists, i.e. the `allow_fetch=True` page path; it is `None` on the
   `allow_fetch=False` ranking/refresh path, so the ranking path carries no heavy
   object and the card is never assembled there). `read_migration` is a read-only
   archive read with no network on any path.
2. **`PriceLevelResult` stays a strict superset** (the order-advisor test
   constraint): `app_fair_value_obj: Optional[object] = None` is purely additive.
3. **Snapshot parity — explicit EXCLUSION.** No diagnosis-card field (including
   `valuation_role`) flows into the daily snapshot / `OpportunityCard.anchor_snapshot`
   this round. The card is a render-time assembly on pages/4 + pages/9 ONLY, so there
   is nothing to bind in the §18 / archive-suite §7 snapshot-parity partition. This
   is the *bind-or-explicitly-exclude* discipline satisfied by explicit exclusion +
   rationale. `valuation_role` is documented (A2) as the deterministic INTERFACE the
   7A three-horizon view will later consume; wiring it INTO the ranker / snapshot is
   **deferred** (out of scope this round — that would be a 7A scoring change).

#### Matrix B — archive readers (sharding migration)

Every CURRENT reader/writer of the append-only archive, audited against the real
call sites. **No reader is left unclassified.** All production READS are already
keyed by a single ticker — the one all-ticker reader (`load_all_records`) has **no
production caller** — so per-ticker sharding bounds every hot-path read.

| caller (verified file:line) | archive API | read scope | cost BEFORE (single file) | cost AFTER (sharded) |
|---|---|---|---|---|
| `anchor_migration.read_migration` `:242` | `read_archive(ticker, window, path)` | one ticker | O(total archive bytes) | **O(ticker shard)** |
| `thesis_monitor.check_holding` `:590` | `read_migration(ticker)` (default path) | one ticker | O(total) | **O(ticker shard)** |
| `anchor_backfill.backfill_ticker` `:525` | `covered_vintages(tk, path)` | one ticker | O(total) | **O(ticker shard)** |
| `anchor_archive.read_archive` `:307` | internal `_iter_records` then filter by ticker | one ticker | O(total) | **O(ticker shard)** — reads only `<root>/<TICKER>.jsonl` |
| `anchor_archive.covered_vintages` `:341` | internal `_iter_records` then filter | one ticker | O(total) | **O(ticker shard)** |
| `anchor_archive.backfilled_vintages` `:325` | internal `_iter_records` then filter | one ticker (diagnostics/tests) | O(total) | **O(ticker shard)** |
| `anchor_archive.load_all_records` `:302` | internal `_iter_records` | ALL tickers — **NO production caller** (diagnostics/tests only) | O(total) | O(total) — globs `<root>/*.jsonl`; unchanged, not on any hot path |
| **WRITE** `equity_valuation.compute_app_fair_value` `:1626` | `append_anchor_record(fv)` (no path) | one ticker append | O(1) append | O(1) append to `<root>/<TICKER>.jsonl` |
| **WRITE** `anchor_backfill.backfill_ticker` `:544` | `append_record(rec, path)` | one ticker append | O(1) | O(1) to shard |
| Tests: `test_reliability_anchor_archive.py`, `test_reliability_anchor_backfill.py`, `test_reliability_phase_6c_v3_entry_v4.py` §13.10 | inject `path` / patch `ANCHOR_ARCHIVE_PATH` | — | — | inject / patch the shard **ROOT** (`ANCHOR_ARCHIVE_DIR`) |

**Non-readers explicitly classified (not archive readers):**
`lib/reliability/company_research_hub.py:_result_iter_records` — a memory-query
result iterator (different module, unrelated to `anchor_archive`); NOT an archive
reader.

**Sharding strategy & layout.** Per-ticker sharding — chosen over a tail-bounded
read because the single file interleaves all tickers, so a tail read cannot bound a
*per-ticker* read (the most-recent N records for ticker T may sit arbitrarily far
back behind other tickers' appends); sharding makes a read for T touch only T's
bytes, robustly. New canonical store: directory `data/anchor_archive/` with one
shard `<TICKER>.jsonl` per ticker (constant `ANCHOR_ARCHIVE_DIR`). The injectable
`path` / `archive_path` parameter is reinterpreted as the shard **ROOT directory**
(default `ANCHOR_ARCHIVE_DIR`); the shard for ticker T is `<root>/<T>.jsonl`. The
legacy single-file `data/anchor_archive.jsonl` (constant `ANCHOR_ARCHIVE_PATH`,
retained) is read only by the one-time migration.

**Backward compatibility — one-time OFFLINE migration.** `data/` is fully
git-ignored, so the layout change touches **no tracked file**. A one-time
`scripts/migrate_anchor_archive_to_shards.py` splits the legacy single file into
per-ticker shards — an explicit offline step (like `backfill_anchors.py`), **never
on app startup** and never on the ranking/refresh path. Reads do NOT auto-migrate
(that would reintroduce the O(total) read). Append-only and atomicity are preserved
per shard: appends `open(shard, "a")` + `flush` + `fsync` of one line, unchanged;
the in-process dedup memo keys on `(canonical resolved shard path, ticker,
computed_at)` (F-B2 — `Path.resolve()` so alias root forms can't bypass dedup),
still unique. The seam guard (`covered_vintages` spanning live + backfill) is intact
— both origins live in the same per-ticker shard.

**Migration fidelity — SEMANTIC, not byte (F-B3).** The migration parses
(`json.loads`) and re-serializes (`json.dumps`) each record, so the on-disk BYTE
representation may legitimately differ (JSON key order / whitespace). The guarantee
is *semantic*: every migrated record's fields are preserved EXACTLY, the total
record count is preserved, and the append-only invariant holds. This (correct,
not-over-strong) contract is enforced by a field-level + count fidelity test
(`test_reliability_anchor_archive.py` §9), NOT a byte-equality assertion.

**Invariants preserved (re-tested on the new layout):** append-only (no row
mutation), page-path-only writes (the §13.10 cold-ranking zero-write/zero-network
test is ported to the sharded layout), single-vintage, never-fabricate, G2 seam
guard.

### PART A — valuation diagnosis card (`lib/valuation_diagnosis.py`, NEW)

- **A1 — `ValuationDiagnosis` (assembled, no new anchor math).** Pure
  `build_valuation_diagnosis(fv, *, migration=None, current_price=None)` reads ONLY
  fields already on `AppFairValue` + the migration readout: `company_type`;
  `applicable_methods` (= `methods_used`); `rejected_methods` WITH reasons (reuse the
  existing `excluded_anchors` `{name, value, basis, flag}` tokens incl.
  `cycle_distorted`, plus the menu's "DCF excluded for type" rationale); plus the
  Phase-8 `reverse_dcf` slot (A4); `anchor_consistency` — **SOURCED, not recomputed
  (F-A1)**: `state` from `blend_state` (+ the `single_anchor_blend` caveat),
  `dispersion` passed through from the producer's `anchor_dispersion`, `clustered`
  from the producer's kept `anchors`, and `outlier` from the producer's ONLY
  per-anchor signal — `excluded_anchors` (an outlier is named ONLY when EXACTLY ONE
  anchor was producer-excluded). The card NEVER derives a fresh outlier metric and
  NEVER picks one by list order; when the producer flagged the set irreconcilable but
  named no single culprit (or excluded none/several) it reports the sentinel
  `no_clear_outlier` (never-fabricate); `endorsed_range` (the blended
  `fair_value_low/high`, or the honest `anchors_irreconcilable` "shown separately"
  state); `confidence` (the existing value, already incl. the v2.2 pool-dispersion
  cap). Duck-typed via `getattr` (same tolerance as `record_from_app_fair_value`);
  never raises.
- **A2 — `valuation_role` (NEW deterministic mapping).** Single visible config block
  `VALUATION_ROLE_RULES` mapping `(confidence × anchor_consistency × upside-vs-price)`
  → `{informational | mid_term_supportive | long_term_eligible}`. Draft rules (tunable
  in the config, not hardcoded): `confidence == low` → `informational` regardless;
  `irreconcilable` anchors → `informational`; `medium` + consistent anchors →
  `mid_term_supportive`; `high` + consistent + `upside > 15%` → `long_term_eligible`;
  else `informational`. Fully deterministic, no LLM. **Documented intent:** this is
  the interface between the valuation layer and the 7A three-horizon view; the
  consumer wiring is a future round.
- **A3 — `what_would_change`.** (i) MECHANICAL conditions implemented now, in the
  same falsifiable-condition shape `thesis_monitor` uses: "price crosses above/below
  the endorsed range without an estimate revision" (sourced from `endorsed_range` +
  `current_price`), "analyst-pool migration crosses a deterioration threshold"
  (sourced from the v2.3 migration readout's `deteriorating` / `consistency`).
  (ii) NARRATIVE catalysts (margin guidance, etc.) — explicit **Phase-8 PLACEHOLDER**
  field, empty this round.
- **A4 — reverse-DCF slot.** A named, documented **Phase-8-pending** placeholder in
  the method menu / card. Reverse DCF is NOT implemented this round.
- **A5 — render on pages/4 + pages/9.** UI-copy discipline (the v1 #3 lesson):
  decision-relevant, bilingual wording in the main view; method-detail / token-level
  content folded into an expander/tooltip — no developer-text in primary cells. New
  `t()` keys are additive bilingual in both `TRANSLATIONS` blocks.

### PART B — F4 archive sharding repayment

- **B1 — per-ticker sharding** (strategy + rationale above). `ANCHOR_ARCHIVE_DIR`
  added; `_shard_path(ticker, root)` resolves `<root>/<TICKER>.jsonl`; `_iter_records`
  reads ONE shard (the ticker's) for the per-ticker readers, via a new
  ticker-scoped internal iterator.
- **B2 — reader migration.** `read_archive`, `covered_vintages`, `backfilled_vintages`
  read the single ticker shard; `load_all_records` globs all shards (diagnostics
  only). `read_migration` / `backfill_ticker` / `thesis_monitor` inherit the bounded
  read transparently (they already pass a ticker). Appends route to the per-ticker
  shard. `scripts/migrate_anchor_archive_to_shards.py` ships the one-time split.
- **B3 — invariants** preserved (append-only, page-path-only writes, §13.10
  zero-write/zero-network re-run on the new layout, single-vintage, never-fabricate,
  G2 seam guard).
- **B4 — read cost:** O(total archive bytes) → **O(one ticker's records)** for every
  hot-path read (Matrix B "AFTER" column).

### Results (CLOSED — APPROVED @ 18dfcf2, merged to main)

- **New module** `lib/valuation_diagnosis.py` (pure, deterministic, no I/O):
  `build_valuation_diagnosis` + `classify_valuation_role` + the visible
  `VALUATION_ROLE_RULES` config block. **New suite**
  `scripts/test_reliability_valuation_diagnosis.py` — **46/46**: assembly (§1),
  consistency cluster/outlier (§2), EVERY `valuation_role` boundary incl. the strict
  `>15%` long-eligible edge (§3), what_would_change mechanical/placeholder split (§4),
  reverse-DCF Phase-8 slot (§5), determinism + fail-soft (§6), the
  `PriceLevelResult.app_fair_value_obj` data-path threading — page sets it /
  network-free leaves it None, driven on the REAL `compute_price_levels` (§7), render
  bindings + snapshot EXCLUSION (§8), and i18n token coverage in both languages (§9).
- **Archive sharding** (`lib/anchor_archive.py`): `ANCHOR_ARCHIVE_DIR` +
  `shard_path()`; per-ticker reads via `_iter_ticker`; `load_all_records` globs all
  shards (diagnostics only). One-time offline `scripts/migrate_anchor_archive_to_shards.py`.
  Read cost **O(total) → O(one ticker's records)**. Tests migrated to the sharded
  layout + new assertions: `anchor_archive` **60 → 71** (shard isolation 2.11–2.13,
  migration-script split + idempotent double-run 9.1–9.7), `anchor_backfill`
  **60 → 61** (5.8 shard write), `phase_6c_v3_entry_v4` **92/92** (§13.10
  cold-ranking zero-write/zero-network re-run against `ANCHOR_ARCHIVE_DIR`).
- **Render** on pages/4 (fv expander) + pages/9 (LONG order card + LONG opportunity
  candidate). `PriceLevelResult.app_fair_value_obj` additive (superset preserved);
  no diagnosis field enters any snapshot (render-time only — parity by explicit
  exclusion).
- **Canonical sweep GREEN:** entry_v4 92 · trading_desk 126 · cockpit_rebuild 47 ·
  7A 115 · 7B 193 · router 117 · stopbleed 65 · render_order 50 · archive 71 ·
  backfill 61 · valuation_diagnosis 46. Full `test_reliability_*` sweep
  **GREEN=65 / RED=13** — the 13 are the documented pre-existing orthogonal reds
  (5e–5s UI/AppTest planning, agent_evaluation, 6b_signal_layer); GREEN rose 64 → 65
  from the new diagnosis suite. None of this round's files are in the red set.
- `lib/macro_regime.py` untouched; i18n additive bilingual (`valdiag_*` in both
  `TRANSLATIONS` blocks). **`.gitattributes` now fully enforced:** `ui_utils.py` —
  the LONE `i/crlf` file of 308 at the branch base — was normalized to LF, so
  `git ls-files --eol | grep i/crlf` is empty and `git diff --check` is clean.

### Reliability invariants preserved

- Deterministic computation unchanged: the diagnosis is assembled from existing
  `AppFairValue` / migration fields — no LLM, no new anchor math, no number invented.
- No card read triggers a compute/fetch on any path; the network-free ranking path
  carries no `app_fair_value_obj` and assembles no card.
- Archive: append-only, page-path-only writes (§13.10), single-vintage,
  never-fabricate, G2 seam guard — all preserved under per-ticker sharding.
- `valuation_role` is the documented deterministic INTERFACE to the 7A three-horizon
  view; reverse-DCF + narrative catalysts are NAMED Phase-8-pending placeholders.

### Fix round (REQUEST CHANGES — F-A1 / F-B2 / F-B3)

- **F-A1 (P1) — `anchor_consistency` is SOURCED, never recomputed.** The first cut
  computed a median-relative outlier inside the card (new judgment + order-dependent
  when two anchors tie). Now `_anchor_consistency` reads ONLY the producer's existing
  decisions: `state` ← `blend_state` (+ `single_anchor_blend`), `dispersion` ←
  `anchor_dispersion` (pass-through), `clustered` ← the producer's kept `anchors`, and
  `outlier` ← `excluded_anchors` — a name is reported ONLY when the producer excluded
  EXACTLY ONE anchor. When the producer flagged the set irreconcilable but named no
  single culprit (or excluded none/several), the card reports the sentinel
  `NO_CLEAR_OUTLIER` (`"no_clear_outlier"`, rendered "no clear outlier / 无明确离群锚")
  — never picks by list order. Tests: two equal-deviation anchors → `no_clear_outlier`
  in BOTH input orderings (order-invariance, §2.5); one producer-excluded anchor →
  reported by name (§2.6); multiple excluded → no single outlier (§2.7).
- **F-B2 (P1) — dedup key on the CANONICAL shard path.** `append_record` now keys the
  in-process dedup memo on `_canonical_shard_str(p)` = `Path(p).resolve()` (fail-closed
  to `.absolute()` then raw str), so alias root forms (relative vs. absolute, `./`
  prefix, symlink) collapse to ONE key and cannot bypass dedup (which would append the
  same vintage twice and corrupt the append-only series / migration speed). Test: the
  same `(ticker, computed_at)` appended via `root` and `root/.` → exactly one row
  (§2.14/2.15).
- **F-B3 (P2) — migration guarantee narrowed to SEMANTIC fidelity.** The migration
  parses + re-serializes records, so the on-disk byte representation may legitimately
  differ (key order / whitespace); byte-equality is NOT (and should not be) claimed or
  enforced. The documented guarantee (script docstring + the migration paragraph
  above) is now "semantically faithful — every record's fields preserved exactly,
  record count preserved, append-only intact; bytes may differ." Enforced by a
  field-level + count fidelity test (§9.8–9.10): every migrated record `==` its
  original field-for-field and the count is preserved, with NO byte-equality
  assertion.
- **Fix-round counts:** `valuation_diagnosis` **46 → 50** (F-A1 order-invariance +
  genuine/ambiguous outlier cases), `anchor_archive` **71 → 77** (F-B2 alias dedup +
  F-B3 field-level fidelity). Full `test_reliability_*` sweep **GREEN=65 / RED=13**
  (the 13 pre-existing orthogonal reds unchanged). `macro_regime.py` untouched; i18n
  additive (`valdiag_no_clear_outlier`); `git diff --check` clean (no EOL churn this
  round — `ui_utils.py` already LF).

## Round v2.5 — multi-dimensional peer profile + honest `peer_match_quality` (FINAL v2 round)

> **Round-1 lesson applied first (STEP 0 before any code).** Peer matching is an
> *access-path* problem, not a feature-bolt-on. Who already holds the per-ticker
> `info`/financials the numeric dims need, and does reading them on a surface trigger
> a fetch (it must not on any network-free path)? Where is peer matching INVOKED, and
> does the new logic add fan-out (it must not)? How does the relative (peer-multiple)
> anchor CONSUME the new `peer_match_quality` signal? The matrix below is committed
> BEFORE the code.

### The problem this closes

v1's peer matcher (`lib/valuation_router.match_growth_profile_peers`) is sector ×
growth-band × size-band, **falling back to a raw GICS/sector peer set when matches
< 4** (`peer_basis="sector_fallback"`). This mismatches reality: SNOW's peers should
be cloud-data-platform / high-growth consumption-software, not all
"Software—Application"; KTOS should compare to defense-tech / unmanned-systems, not
traditional defense primes. A peer multiple computed from non-comparable companies
is **worse than no peer anchor**, so the honest answer for KTOS-class names is to
*exclude* the peer-multiple anchor — not to pad to N with ill-fitting GICS peers.

### Paid-taxonomy rejection (documented so it is NOT revisited)

Paid sector/thematic taxonomies were evaluated and **REJECTED**:

| taxonomy | why rejected |
|---|---|
| MSCI Thematic | institutional licensing cost; classification scores are an unauditable black box |
| Syntax FIS (functional information system) | paid licence; proprietary, non-inspectable mapping |
| Morningstar sector/style | paid; black-box style scores conflict with deterministic/auditable principle |

All three conflict with the project's **deterministic, auditable, free-API**
principle — an LLM/3rd-party black box that "scores" peer similarity cannot be
evidence-backed or reproduced. v2.5 instead unifies on TWO already-owned, auditable
sources: the **deterministic numeric dims** (computed from already-fetched `info`)
and the **curated `theme_baskets` membership** (a human-curated, version-controlled
list), plus a small human-reviewed `peer_profiles` override for the corners baskets
miss. No new data source, no paid API, no runtime LLM.

### STEP 0 — caller-contract matrix (audited against the real call sites)

#### Matrix A — what the peer matcher READS, where it is INVOKED, network

Every site that reaches peer matching was audited. No caller left unclassified.
The numeric dims and the candidate `info` dicts are **already fetched** by the
Equity-page peer table — the matcher reads them, it does **not** fetch.

| caller (verified file:line) | reads from | live compute / fetch? | peer_match_quality assessed? |
|---|---|---|---|
| `pages/4_Equity.py:280-285` builds `peer_infos` (one `load_info` per peer, ALREADY fetched for the peer table) → `:667-669` / `:891-895` `compute_app_fair_value(..., peers=peer_infos)` | the peer-table `info` dicts (sector, industry, revenueGrowth, marketCap, P/S, EV/EBITDA, grossMargins, operatingMargins, profitMargins) + `theme_baskets` membership + `peer_profiles` config | the peer `info` was already fetched for the table; the matcher adds **ZERO** new per-ticker network | **YES** — `peers` supplied |
| `lib/equity_valuation._assemble_fair_value:1436-1452` — the existing `match_growth_profile_peers` call site (one per multiple field) | `peers` arg + target `raw` (already in hand) | none — pure over args | YES iff `peers` is non-empty |
| `pages/9_Trading_Desk.py` → `order_advisor._gather_technicals:1429` → `compute_app_fair_value(ticker, cp, cyclical_history_fetcher=…)` — **NO `peers` arg** | no peer set on this path | live `_fetch_raw` (gated `allow_fetch=True`), but **no peer fetch** | **NO** — `peers=None`; quality `""` (not assessed); card shows n/a |
| `lib/opportunity_ranker.rank_opportunities` → `compute_price_levels(allow_fetch=False)` → `_gather_technicals` (no `peers`, no live compute) | `anchor_cache` hot cache only | **FORBIDDEN** (network-free) | **NO** — never reaches the matcher; byte-stable |

**Derived invariant (THE network-free guarantee):** `peer_match_quality` is assessed
**only when `peers` is supplied**, which is **only** the Equity page. `peers=None`
(Trading Desk, ranking, refresh, every existing fixture that does not pass peers) →
quality `""` → **no anchor exclusion, behavior byte-identical to v2.4**. This is why
the ranking/refresh path is structurally untouched and the stopbleed/6c_b canaries
(which do not pass peers) stay byte-stable.

#### Matrix B — how the relative (peer-multiple) anchor CONSUMES `peer_match_quality`

| anchor (menu key) | derived from the matched peer set? | gated by `peer_match_quality`? |
|---|---|---|
| `ev_s` (`_compute_ev_s`, consumes `peer_ps`) | **YES** — median P/S over matched peers | **YES** — excluded on `low` |
| `ev_ebitda` (`_compute_ev_ebitda`, consumes `peer_ev_ebitda`) | **YES** — median EV/EBITDA over matched peers | **YES** — excluded on `low` |
| `relative_pe` (`get_sector_median_pe(sector) × EPS`) | **NO** — a static sector-median-P/E map, not the matched peers | **NO** — governed by its own `peer_pe_basis` flag (independent mechanism). Gating it on peer-match quality is a category error (low peer match does not make the sector map wrong) |
| `dcf` / `analyst` / `pb_ps_band` | NO | NO |

So a `low` `peer_match_quality` excludes **only** `ev_s` + `ev_ebitda` — the anchors
that literally consume the matched peer set. KTOS (`project_driven`, menu already
excludes `relative_pe`+`dcf`) then falls to **analyst-only**, which is its
reconcilable, correct valuation shape.

### Design decisions (recorded — confirmed with the user)

1. **EXCLUDE, never a continuous down-weight.** The v1/v2 system handles
   untrustworthy anchors by *exclude + flag*, never a tunable weight knob — a
   down-weight factor has no principled value and is an "invent-a-number" hazard.
   "Worse than no peer anchor" literally means *no peer anchor* (exclude). Reuse the
   existing `excluded_anchors` + caveat machinery; reason token
   `insufficient_comparable_peers`.
2. **Gate `ev_s`+`ev_ebitda` ONLY** (Matrix B) — surgical, not guilt-by-association.
3. **Data-driven, minimal `peer_profiles` seed.** Do NOT hand-write tags for the
   whole universe (redundant where numeric-dims ∩ baskets already work; 40 tags is
   too many to review carefully). First run matching on pure numeric-dims ∩ baskets,
   observe which tickers fall to `peer_match_quality=low`, and seed `peer_profiles`
   ONLY for those that (a) genuinely degrade AND (b) have an identifiable real
   sub-peer set baskets miss (KTOS defense-tech, SNOW cloud-data-platform are the
   known cases). Tickers that fall low with NO good peer set correctly STAY low
   (honest degrade — the right answer, not a gap to patch). Every entry is
   human-reviewed before it lands (same pattern as `CYCLICAL_TICKER_OVERRIDES`).

### A — numeric peer dimensions (deterministic; extend v1's 3 dims)

Adds to v1's sector × growth-band × size-band three new dims, all computed
deterministically from the already-fetched `info` (single visible config block
`PEER_DIM_CONFIG` for the bands/thresholds):

- **margin_band** — from `operatingMargins` (fallback `profitMargins`): `high` ≥ 0.25,
  `mid` ≥ 0.10, `low` ≥ 0.0, `negative` < 0.0, `unknown` when absent.
- **profitability_stage** — `profitable` (margin ≥ floor), `transitional`
  (near-zero ≤ margin < floor), `unprofitable` (margin < near-zero), `unknown`.
- **revenue_cyclicality** — `cyclical` when the target/candidate classifies cyclical
  (reuse `CYCLICAL_SECTORS` / `CYCLICAL_INDUSTRY_HINTS` / `CYCLICAL_TICKER_OVERRIDES`),
  else `non_cyclical`. (No new fan-out — derived from `sector`/`industry`/ticker.)

A candidate is **numerically compatible** when it shares the target's `growth_band`,
`size_band`, `margin_band`, `profitability_stage`, and `revenue_cyclicality` (band
equality, the v1 pattern; `unknown` on either side fails that dim). Borderline
handling consistent with v1 (a dim that is `unknown` does not match).

### B — theme-basket-derived tags (free, auditable, single source of truth)

A ticker's **theme tags = the `theme_baskets` it belongs to** (read-only of
`THEME_BASKETS[*].constituents`; no change to rotation behavior). The peer candidate
set = **(numeric-dim compatible) ∩ (shares ≥1 basket OR ≥1 override tag)**. This
unifies the peer taxonomy with the rotation pipeline — one curated membership list,
no second divergent classification (eliminates the "rotation says MU∈hbm_memory but
valuation peers MU to all semis" inconsistency).

### C — manual override layer (`peer_profiles` config)

A visible `PEER_PROFILES` config: `ticker → {business_model, theme_exposure}` tag
sets, for corners baskets don't cover (KTOS defense-tech). The override tags
participate in the tag-intersection exactly like basket tags. Deterministic input —
matching reads it, never invents tags at runtime. LLM MAY draft entries; every entry
human-reviewed before landing (the `CYCLICAL_TICKER_OVERRIDES` pattern). Seed is
data-driven + minimal (decision #3).

### D — honest `peer_match_quality` degrade (the CORE principle)

After numeric ∩ (basket ∪ override) matching, if the qualified peer set < `N`
(`MIN_QUALIFIED_PEERS = 4`): `peer_match_quality="low"` + reason
`insufficient_comparable_peers` — and **DO NOT pad with raw GICS peers to hit N**
(the v1 `sector_fallback` is NOT taken when `peers` are supplied for the new path).
Downstream, a `low` quality **EXCLUDES** `ev_s`+`ev_ebitda` from the blend (flagged
`insufficient_comparable_peers`, moved to `excluded_anchors`, caveat
`peer_match_unreliable`) — the values are still COMPUTED and shown for transparency,
just not blended. ≥ N → `peer_match_quality="high"`, the matched-peer median
multiples drive the EV anchors as before. `peers=None` → quality `""` (not assessed,
v2.4 behavior). Surfaced on the diagnosis card (`peer_match_quality` +
`peer_match_reason` are new `AppFairValue` fields the card reads). Tighten-only kin:
low quality only WEAKENS reliance on the relative anchor, never fabricates confidence.

### Invariants

- Deterministic, no runtime LLM. Peer selection + match-quality are pure Python;
  the LLM only drafts the offline `peer_profiles` config (human-reviewed).
- Network-free ranking/refresh preserved; numeric-dim reads reuse already-fetched
  page data; the matcher adds zero fan-out.
- The relative anchor's existing math is unchanged; only its INCLUSION changes via
  `peer_match_quality`. Default/existing-fixture behavior byte-stable where peer data
  is unchanged (stopbleed/6c_b canaries — they pass no peers).
- `macro_regime.py` frozen; i18n additive bilingual; LF clean.

### Implementation (delivered)

- **`lib/valuation_router.py`** — the v2.5 matcher (v1's `match_growth_profile_peers`
  kept byte-stable for its direct tests):
  - Visible `PEER_DIM_CONFIG` + `margin_band` / `profitability_stage` /
    `revenue_cyclicality` (the last reuses the classifier's cyclical signals so the
    dim never diverges) + `numeric_dims()` (reads already-fetched info only) +
    `_dims_compatible()` (band equality on all five dims; `unknown` never matches).
  - `basket_membership()` reads `theme_baskets.THEME_BASKETS` constituents read-only
    (lazy, fail-closed import) → `{TICKER: frozenset(baskets)}`; `peer_tags_for()` =
    basket tags ∪ `PEER_PROFILES` override tags. **One curated membership list shared
    with rotation** (verified: `MU ∈ hbm_memory`, `SNOW ∈ data_infrastructure`).
  - `PEER_PROFILES` minimal seed = **`KTOS` only** (in no basket; tagged
    `defense_tech` / `unmanned_systems` / `defense_space`). SNOW needs no override —
    its `data_infrastructure` basket + numeric dims already yield cloud peers
    (verified offline).
  - `assess_peer_match()` (pure, injectable membership/profiles): qualifies a
    candidate on numeric-compat **AND** a shared basket/override tag; `≥
    MIN_QUALIFIED_PEERS (4)` → `high` + medians over the qualified set; fewer → `low`
    + `insufficient_comparable_peers`, multiples `None` (**no raw-GICS padding**); no
    candidates → `""` (not assessed).
- **`lib/equity_valuation.py`** — `CAVEAT_PEER_MATCH_UNRELIABLE` (registered) +
  `PEER_MULTIPLE_ANCHOR_KEYS = {ev_s, ev_ebitda}` + local
  `REASON_INSUFFICIENT_PEERS` (mirrors the router token). `AppFairValue` gains
  `peer_match_quality` / `peer_match_reason`. `build_app_fair_value` EXCLUDES the
  peer-multiple anchors when quality is `low` (flag `insufficient_comparable_peers`,
  moved to `excluded_anchors`, caveat) — still computed + shown, only inclusion
  changes; `relative_pe` untouched. `_assemble_fair_value` calls `assess_peer_match`
  ONCE when `peers` is supplied (high → medians drive EV anchors; low → withheld →
  excluded downstream); `peers=None` → the matcher is never invoked → byte-identical.
- **`lib/valuation_diagnosis.py` + `ui_utils.py`** — the card SOURCES
  `peer_match_quality` / `peer_match_reason` (never recomputed) and renders a
  bilingual peer-match line (low → ⚠️ + reason; high → confirmation; `""` → nothing).
  Additive `valdiag_peer_match*` keys in both `TRANSLATIONS` blocks; the
  rejected-method reason map gains `insufficient_comparable_peers`. No diagnosis
  field enters any snapshot (render-time only — parity by explicit exclusion).

### Results (CLOSED — v2.5 closes the v2 series)

- **New suite** `scripts/test_reliability_anchor_peer_match.py` — **44/44**: numeric
  dims (§1); basket single-source + override + minimal-seed assertion (§2);
  `assess_peer_match` qualification / `≥N` high / `<N` low + **no padding** /
  not-assessed / self-exclusion (§3); override-creates-a-tag-peer (§4); **REAL
  Equity-page peer path** via `_assemble_fair_value(peers=…)` + a
  `compute_app_fair_value` plumbing proof — **SNOW → high** (qualified ⊆ cloud
  basket, CRM/all-software excluded, EV/S blended) and **KTOS → low** (EV/EBITDA
  excluded with the peer flag — *discriminating*, fails if the exclusion is reverted
  — → analyst-only $30, reconcilable) (§5); **byte-stable** `peers=None` path (§6);
  determinism + order-invariance (§7); token/config integrity (§8); card
  bind-or-exclude parity (§9); **B1 cache-order-independence, BOTH orders, REAL
  cached path (§10 — fix round below)**.
- **`scripts/test_reliability_valuation_diagnosis.py`** grew **50 → 54** (peer-match
  i18n guard + bind/exclude parity §10).
- **Canonical sweep GREEN:** entry_v4 92 · trading_desk 126 · cockpit_rebuild 47 ·
  7A 115 · 7B 193 · router 117 · stopbleed 65 · render_order 50 · archive 77 ·
  backfill 61 · valuation_diagnosis 54 · **peer_match 44 → 49 (B1 fix round)**. Full
  `test_reliability_*` sweep **GREEN=66 / RED=13** — the 13 are the documented
  pre-existing orthogonal reds (5e–5s UI/AppTest planning, agent_evaluation,
  6b_signal_layer); GREEN rose 65 → 66 from the new suite. None of this round's
  files are in the red set.
- `lib/macro_regime.py` untouched; i18n additive bilingual (`valdiag_peer_match*`);
  `git diff --check` clean (no EOL churn — all touched files `i/lf`).
- **Paid-taxonomy rejection** (MSCI Thematic / Syntax FIS / Morningstar) recorded
  above so it is not revisited.

### Fix round (REQUEST CHANGES — B1, P1: cache-order dependence)

> **Round-1 lesson recurring.** B1 is the SAME class as the round-1 epoch-mixing
> bug: a cache key that EXCLUDES a parameter which affects the cached VALUE makes the
> result first-writer-dependent. The first cut keyed `compute_app_fair_value` on
> `(ticker, current_price, dcf_override)` with `_peers` underscore-excluded — but
> `_peers` drives `peer_match_quality` AND the EV-anchor exclusion. So:
> Trading-Desk-first (no peers) → a later Equity call reused `quality=""` and wrongly
> BLENDED EV/S+EV/EBITDA; Equity-first (peers) → a later no-peer call inherited
> `"low"` and wrongly degraded to analyst-only. The Trading Desk legitimately has NO
> peers (it does no peer matching), so "make all callers pass peers" does not apply —
> the two callers want DIFFERENT valuation semantics for the same ticker.

**STEP 0 — A-vs-B coupling determination (the question that decides the model):**
*does peer matching affect only the INCLUSION of `ev_s`/`ev_ebitda`, or also their
NUMERIC VALUE?* **Answer: BOTH.** In `_assemble_fair_value`, a `high`
`peer_match_quality` makes the qualified-set **median multiples** (`peer_ps`,
`peer_ev_ebitda`) drive `_compute_ev_s` / `_compute_ev_ebitda` — so the EV anchor's
NUMERIC VALUE is computed from the matched peer set (v1's growth-matched-multiple
feature, carried into v2.5's qualified set). Because the value (not only inclusion)
depends on the peer set, **Option B (peer-agnostic cache + Equity post-process) is
ruled out** — it could not reproduce the peer-median EV value without re-doing anchor
math in a second place (violating one-producer / one-anchor-math). → **Option A: the
peer-set signature enters the cache key.**

**B1 fix (Option A).** `_peers_signature(peers)` = the SORTED, deduplicated peer
ticker list (or `""` when None/empty) — deterministic and order-independent. It is
threaded into `_compute_cached` as a **non-underscore keyed parameter** `peer_sig`,
so `st.cache_data` INCLUDES it: the key becomes
`(ticker, current_price, dcf_override, peer_sig)`. The `_peers` LIST stays
underscore-prefixed (the list object is not a stable hash input); `peer_sig` is its
stable key proxy. Now the peer-bearing Equity path (`peer_sig != ""`) and the
peer-less Trading-Desk / ranking / refresh / fixture paths (`peer_sig == ""`) cache
**separately** and never cross-contaminate **regardless of call order**; the
peer-less path is **v2.4-byte-identical by construction**. (`peers=None` and
`peers=[…]` produce distinct keys; the ticker set is the right granularity because
each ticker's `info` is itself session-cached/stable.) This also closes a **latent
v2.4 bug**: the EV value already differed `growth_matched` vs `sector_fallback`
between peer-bearing and peer-less calls under ONE shared entry, so v2.4 was already
first-writer-dependent for the EV value — Option A fixes that too.

**Test (the gap the review named — only fresh peer-first was tested).**
`anchor_peer_match` **44 → 49** (§10): the order-independence test drives the REAL
cached `compute_app_fair_value` in BOTH orders — (1) Trading-Desk-first (no peers)
then Equity (peers) → the later Equity call gets the correct peer-gated `low` →
analyst-only; (2) Equity-first (peers) then Trading-Desk (no peers) → the later
Trading-Desk call gets the v2.4 peer-agnostic result (quality `""`, EV blended, NOT
inheriting `low`) — plus a signature order-independence / `None`-vs-`[…]` check.
**Discrimination confirmed:** reverting only the call-site `peer_sig` argument
(reproducing the `bb150da` key) makes **exactly checks 10.2 + 10.4 FAIL** (the later
caller inherits the first writer's cached result) — i.e. the test catches precisely
this bug. Canaries (router 117 / stopbleed 65 / 6c_b 47 / entry_v4 92 — all
peer-less) byte-stable. Full canonical sweep GREEN; full `test_reliability_*`
**GREEN=66 / RED=13** (13 pre-existing orthogonal reds). `macro_regime.py` untouched;
`git diff --check` clean (LF). Commit `4feb9de`.

> **v2.5 closes the Anchor Intelligence v2 series.** Round 1 = single producer +
> structured analyst pool + epoch; v2.3 = append-only historical archive + migration
> readout; backfill = recomputable history seed; v2.4 = valuation diagnosis card +
> per-ticker archive sharding; **v2.5 = multi-dimensional peer profile + honest
> `peer_match_quality` degrade.**
