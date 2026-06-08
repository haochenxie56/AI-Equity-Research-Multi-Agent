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
**APPROVED at `c57e56e`** and merged now. **Rounds v2.4–v2.5 remain pending**
(future scope, not started — to be specified when each round opens).

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

## Pending — rounds v2.4–v2.5

Not started. Scope to be specified when each round opens. Round 1 establishes the
single-producer / structured-pool / epoch foundation those rounds build on; v2.3
adds the append-only historical series + migration readout, and the backfill round
seeds that series with recomputable history.
