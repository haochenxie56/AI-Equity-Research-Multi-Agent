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
**Rounds v2.2–v2.5 remain pending** (future scope, not started — to be specified
when each round opens).

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

## Pending — rounds v2.2–v2.5

Not started. Scope to be specified when each round opens. Round 1 establishes the
single-producer / structured-pool / epoch foundation those rounds build on.
