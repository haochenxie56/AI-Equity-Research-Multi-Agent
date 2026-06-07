# Phase — Valuation Refactor v1 (method router + growth-profile peers)

**Status:** **COMPLETE & CLOSED** — the two REQUEST CHANGES fix rounds + the
documentation-closure round were re-reviewed and **APPROVED at ca5ad14**. Final
verdict: all five REQUEST CHANGES findings resolved, deterministic computation
preserved, canonical sweep green; the phase is closed. Suite
`scripts/test_reliability_valuation_router.py` **104/104** (54/54 originally →
81/81 after fix round 1 → 104/104 after fix round 2); full canonical set green
(stopbleed 65/65, 7A 115/115, 7B 187/187, 6c_b 47/47, equity_render_order 50/50,
6c_trading_desk 118/118, 6c_v3_entry_v4 47/47, 6b_v3_horizon_scoring 189/189,
theme_baskets 146/146, scanner_rotation_adapter 15/15).

## Review fix round (5 findings, all addressed)

- **F1 (D2)** — `growth_unprofitable` now excludes DCF **structurally** (menu
  `excluded`), not via a computability guard; a user DCF override cannot bypass it.
- **F2 (D1/I10)** — the cyclical PB/PS band is now a REAL **≤4y annual** band
  (yfinance annual fundamentals + cached prices, page path only; baked into the
  anchor cache so ranking/Cockpit stay network-free); degrades to analyst-only
  with the `cyclical_band_unavailable` caveat.
- **F3 (I4)** — `anchor_cache.load_all` now **rejects** bare un-versioned legacy
  maps (invalidate → recompute) instead of tolerating them.
- **F4 (I8)** — industry/sector hints are matched by **token boundary**
  (`industry_has_hint`), not substring containment.
- **F5 (I10)** — status docs aligned (now updated to COMPLETE & CLOSED on re-review
  approval at ca5ad14).

## Fix round 2 (re-review — live cyclical band + data sanity)

This round made the cyclical band a genuinely live page-path computation and
hardened the valuation against corrupt yfinance `info` (observed live for MU:
`forwardEps` 105.95 vs trailing 21.17, `revenue_growth` 1.963 = 196%, a $2966.66
relative anchor). Every guard is an **exclusion + caveat only** — a bad number is
dropped and flagged, never silently corrected or replaced with an invention.

- **Cyclical band builder — tz normalization + narrowed exceptions.** The PB/PS
  history builder now normalizes price-index timezones before the as-of join (a
  tz-aware vs tz-naive index silently produced an empty band) and narrows its
  exception handling to the specific lookup/arithmetic failures instead of a bare
  `except`, so a real defect surfaces rather than degrading to analyst-only
  silently. A parity check pins the tz-aware and tz-naive paths to identical
  `pb_history`.
- **Multi-year price window (page path only).** The cyclical fundamentals/price
  fetch pulls a multi-year price window so the ≤4y annual band has enough as-of
  prices to clear `MIN_CYCLICAL_BAND_OBS`. This is on the per-ticker page path
  only; the cached / ranking / Cockpit paths still read the baked band and stay
  network-free.
- **Update-Valuation call-site parity.** The "Update Valuation" button call site
  was passing a different argument set than the initial render path, so a manual
  refresh could produce a band that disagreed with the auto-render. The two call
  sites are now parity-aligned (page path only).
- **`DATA_SANITY_CONFIG` guards (ONE visible block).** Three deterministic
  plausibility rules, all exclude-and-flag, each with a bilingual caveat token in
  `VALUATION_CAVEATS`:
  | Rule | Config | Caveat token | Effect |
  |------|--------|--------------|--------|
  | forward/trailing EPS blow-up | `forward_eps_max_x_trailing = 3.0` (floor `eps_epsilon = 0.01`) | `implausible_forward_eps` | drop the relative anchor |
  | anchor wildly off vs price | `anchor_max_x_price = 10.0` (**high-side only**) | `anchor_implausible_vs_price` | drop that anchor |
  | corrupt revenue growth | `max_revenue_growth = 1.0` (100% yoy) | `implausible_growth_input` | treat growth as MISSING for the classifier + peer matching |
- **High-side-only price-plausibility scoping (rationale).** The
  `anchor_max_x_price` rule drops anchors only on the HIGH side. The magnitude /
  unit defects actually observed (corrupt `forwardEps`, stale share counts →
  4-digit anchors) are all high-side blow-ups. A LOW-side anchor (e.g. a $3
  trailing-PE relative anchor against a $100 price) is a real-but-inappropriate
  anchor that the **method router (PE exclusion) and the dispersion gate already
  handle** by marking the set `anchors_irreconcilable`. Dropping it here would
  silently UNDO that stop-the-bleed contract (regressing the $3.23-vs-$112.50
  audit case), so low-side anchors are deliberately delegated downstream to the
  dispersion gate.
- **`CYCLICAL_TICKER_OVERRIDES` — documented yfinance-taxonomy workaround.**
  `frozenset({"MU", "WDC", "STX"})` (`lib/valuation_router.py`) forces these
  memory / HDD makers to `cyclical` regardless of the industry string yfinance
  reports, because the live taxonomy mislabels them and the token matcher will
  not (and must not) treat the broad "Semiconductors" string as cyclical. The
  override is checked as a clear, deterministic signal and **beats** a (possibly
  corrupt) high-growth reading — exactly the live MU case where `revenue_growth`
  read 196%. X5a live dump (2026-06):

  | Ticker | yfinance `industry` (X5a live dump, 2026-06) | Why the override is needed |
  |--------|----------------------------------------------|----------------------------|
  | MU | `Semiconductors` | broad/growth-coded string; the token matcher correctly will not treat "Semiconductors" as cyclical |
  | WDC | `Computer Hardware` | not present in any cyclical hint list at all |
  | STX | `Computer Hardware` | not present in any cyclical hint list at all |

  All three are structurally cyclical, so a ticker-level override is the honest
  fix; the test fixtures (Section 12) carry these exact live strings. Control:
  NVDA / AVGO / TXN report the same `Semiconductors` string but are NOT in the
  override set and correctly stay `growth_profitable` (broadening the industry
  hint was rejected).
- **Deliberate assertion rewrites.** Two existing assertions were intentionally
  updated to match the corrected behavior, not worked around: router check **2.7**
  (DCF is now excluded for `growth_unprofitable`, per fix round 1 F1) and stopbleed
  check **5.17** (a bare un-versioned legacy anchor cache is now rejected, per F3).
  Suite grew 81/81 → **104/104**.

## Known limitations

- **`forward_eps > 3× trailing` guard can false-positive on recovering earnings.**
  The `forward_eps_max_x_trailing = 3.0` rule (caveat `implausible_forward_eps`)
  is a blunt magnitude check. A name whose earnings are recovering off a depressed
  trailing base legitimately shows a forward EPS several times the trailing EPS,
  and the guard will exclude its relative anchor even when that anchor is sound.
  Live AMD example: the relative anchor **$366.15** was excluded despite sitting
  *between* the two surviving anchors (EV/S **$356.64**, analyst **$487.50**) — so
  the band lost a perfectly reasonable input. The direction is conservative by
  design (exclude + caveat, never invent a number), so the failure mode is "a
  slightly wider / analyst-leaning band", not a wrong number. Calibration of the
  `K` multiplier (or a recovering-earnings carve-out) is **deferred** until
  snapshot history provides enough cases to tune it on evidence rather than a
  single anecdote. Cross-reference: caveat token `implausible_forward_eps`.

## Problem

The stop-the-bleed phase made irreconcilable anchors HONEST (dispersion gate +
forward basis + cache), but companies like the **KTOS case** stay stuck at "we
don't know": the relative and analyst anchors diverge 5×+ because **one PE×EPS
formula was applied to every company type** and peers were picked by GICS sector
regardless of growth profile. A project-driven defense contractor's trailing-PE
relative anchor is garbage ($3.80) next to a $30 analyst target → the gate
correctly flags `anchors_irreconcilable`, but the right fix is to **not use PE at
all** for that company and value it on EV/EBITDA instead.

This phase routes each company type to an appropriate **method menu** so the
irreconcilable rate materially drops. The dispersion gate from stop-the-bleed
still runs LAST on whatever the menu produced. Deterministic code only — no LLM
(reverse DCF and debate integration remain Phase 8).

---

## Task 1 — Company classifier (`lib/valuation_router.py`)

`classify_company(...)` → `CompanyClassification(company_type, confidence,
fired_rules, inputs, rationale)`. Pure, fail-closed; reads only fields already in
the valuation path's `tk.info` dict (no new per-ticker network). `fired_rules`
records each evaluated rule with value / operator / threshold (auditable, same
spirit as reason codes).

### Classifier config (ONE visible block, `CLASSIFIER_CONFIG`)

| Key | Default | Meaning |
|-----|---------|---------|
| `growth_high` | **0.25** | revenue growth ≥ → "high" band |
| `growth_moderate` | **0.10** | revenue growth ≥ → "moderate" band |
| `margin_floor` | **0.05** | net/operating margin ≥ → "profitable" |
| `margin_near_zero` | **0.02** | margin ≤ → unprofitable / near-zero |
| `revenue_cov_lumpy` | **0.25** | revenue CoV ≥ → lumpy (project hint, optional) |
| `margin_cov_cyclical` | **0.40** | margin CoV ≥ → cyclical (optional) |
| `size_large` / `size_mid` | **$10B / $2B** | size bands |
| `borderline_rel_band` | **0.15** | within this rel. fraction of a threshold → borderline |

Sector / industry hint lists: `PROJECT_DRIVEN_INDUSTRY_HINTS`
(aerospace, defense, engineering & construction, security & protection,
shipbuilding, marine shipping), `CYCLICAL_SECTORS` (Energy, Basic Materials),
`CYCLICAL_INDUSTRY_HINTS` (memory — *not* the broad "semiconductor" —, steel,
oil, gas, mining, chemical, auto manufacturers, airlines, copper, aluminum,
coal). Hints are matched by **token boundary** (`industry_has_hint`): the
industry/sector string is lower-cased and split on every non-alphanumeric
character (em-dash included, so "Software—Infrastructure" → `["software",
"infrastructure"]`); a single-word hint must equal a whole token (so "gas" never
matches inside "vegas" and "semiconductor" never matches "Semiconductors"), and a
multi-word hint must appear as a contiguous token run.

### Decision order (first match wins)

1. **project_driven** — backlog/contract industry hint (or declared backlog, or
   lumpy revenue). Name hint → `clear`; volatility-only → `borderline`.
2. **cyclical** — cyclical sector / industry hint (or volatile margins). Sector /
   industry hint → `clear`; volatility-only → `borderline`.
3. **growth_unprofitable** — high growth + margin ≤ `margin_near_zero`.
4. **growth_profitable** — high growth + margin ≥ `margin_floor`.
5. **mature_profitable** — default (stable margins / moderate growth / positive FCF).

**Borderline** classifications (near a threshold, or a project/cyclical call on
volatility alone) report the detected type but `select_method_menu()` routes them
to the **default `mature_profitable` menu** (the prior, conservative behavior).

### Type distribution over the fixture set

| Ticker | Type | Conf |
|--------|------|------|
| AAPL, MSFT, KO | mature_profitable | clear |
| NVDA | growth_profitable | clear |
| SNOW | growth_unprofitable | clear |
| DDOG | growth_unprofitable | borderline (growth 0.27 ≈ 0.25) |
| KTOS, LMT | project_driven | clear |
| XOM, MU | cyclical | clear |

Distribution: mature 3 · growth_profitable 1 · growth_unprofitable 2 ·
project_driven 2 · cyclical 2.

---

## Task 2 — Method menus (`lib/equity_valuation.py`)

`build_app_fair_value(..., company_type=...)` routes the blend's **input set** via
`METHOD_MENUS`. Only the menu-eligible anchors whose value is present enter the
blend (`anchors`); excluded / flagged anchors are computed but recorded in
`excluded_anchors` (`flag` = `excluded` | `cycle_distorted`). The default
(`company_type=""` / unknown / borderline) is `mature_profitable`, which
reproduces the prior DCF + relative-PE + analyst factors **byte-for-byte**.

| Type | Blended anchors | Excluded / flagged | Notes |
|------|-----------------|--------------------|-------|
| mature_profitable | DCF + relative-PE + analyst | — | unchanged |
| growth_profitable | EV/S + relative-PE + analyst | DCF (`excluded`) | Rule-of-40 modifies the EV/S multiple |
| growth_unprofitable | EV/S + analyst **only** | relative-PE (`excluded`), **DCF (`excluded`)** | PE is the garbage source; DCF excluded **structurally** (unreliable for loss-makers; a user DCF override cannot bypass the menu) |
| project_driven | EV/EBITDA + analyst | DCF, relative-PE (`excluded`) | `backlog_note` when backlog unavailable |
| cyclical | PB/PS band + analyst | DCF (`excluded`), relative-PE (`cycle_distorted`) | PB/PS band = ticker's own ≤4y annual history; degrades to analyst-only with a caveat when unavailable |

Per-anchor blend factors `(low, mid_weight, high)` live in `_ANCHOR_FACTORS`;
the mature trio reproduces the legacy 0.85/0.90/0.80 lows, 0.35/0.35/0.30
weights, 1.10/1.05/1.05 highs exactly. **The dispersion gate
(`ANCHOR_DISPERSION_THRESHOLD = 3.0`, `>` boundary) runs LAST** on the blended
set — routing reduces irreconcilables, the gate still catches the rest.

### Extra-anchor formulas (deterministic, free sources)

* **EV/S** (`_compute_ev_s`): equity-level P/S proxy — `target_ps × revenue/shares`,
  where `target_ps` is the growth-matched peer median P/S else the sector P/S
  fallback. Rule-of-40 multiplier (growth_profitable): `1 + (growth + fcf_margin −
  0.40) × 0.5`, bounded [0.80, 1.25]. (Uses P/S, not a true EV/S, because the peer
  table supplies P/S and this needs no net-debt bridge — documented in the basis.)
* **EV/EBITDA** (`_compute_ev_ebitda`): `(target × EBITDA − net_debt) / shares`;
  `net_debt = total_debt − total_cash`, else `enterprise_value − market_cap`,
  else 0. `target` = growth-matched peer median EV/EBITDA else sector fallback.
* **PB/PS band** (`_compute_pb_ps_band` + `build_pb_ps_history` +
  `fetch_cyclical_band_history`): a REAL **≤4-year ANNUAL** band built from
  yfinance annual fundamentals (annual balance sheet → equity & shares; annual
  income statement → revenue) combined with already-cached price history. For each
  fiscal year `PB = price_asof / (equity/shares)` and `PS = price_asof /
  (revenue/shares)`. The blended anchor is the **p50** of the historical multiple
  × the current per-share fundamental; p20 / p80 (config `PB_PS_BAND_PERCENTILES`
  = 20/50/80) contextualize the band in the basis label. It is labelled an
  **≤Ny annual approximation** everywhere — never a "5-year band". **Network
  discipline:** the fundamentals fetch runs ONLY on the per-ticker page path (a
  `cyclical_history_fetcher` passed from pages/4); the cached / ranking / Cockpit
  paths pass no fetcher and read the band baked into the anchor cache, so they
  stay network-free. **Degradation:** when fundamentals are unavailable or fewer
  than `MIN_CYCLICAL_BAND_OBS` (3) annual observations exist, the band is dropped,
  the blend degrades to analyst-only, and a real caveat token
  (`cyclical_band_unavailable`, plus `single_anchor_blend`) is emitted on
  `AppFairValue.caveats` and surfaced in pages/4.

Sector fallback maps: `SECTOR_MEDIAN_EV_EBITDA` (default 12.0), `SECTOR_MEDIAN_PS`
(default 2.5), alongside the existing `SECTOR_MEDIAN_PE`.

### Valuation caveat vocabulary

`VALUATION_CAVEATS` = `cyclical_band_unavailable` (history band could not be
built) · `single_anchor_blend` (only one anchor entered the blend). Carried on
`AppFairValue.caveats`, written to the anchor cache entry, surfaced bilingually in
pages/4 (`cockpit_fv_caveat_*`).

---

## Task 3 — Growth-profile peer matching (`lib/valuation_router.py`)

`match_growth_profile_peers(target, candidates, *, multiple_field, min_peers=4)`
→ `PeerMatchResult(peers, peer_basis, median_multiple, ...)`. A peer matches when
it shares the target's **sector AND revenue-growth band AND size band**. When
fewer than `min_peers` (config, default 4) match, it falls back to **sector-only**
peers and flags `peer_basis="sector_fallback"`. `candidates` are the peer `info`
dicts already fetched for the Equity page peer table — no new per-ticker fan-out.

Peer-band config reuses `CLASSIFIER_CONFIG`: growth bands `<10 / 10–25 / >25%`
(`growth_band`), size bands `large ≥ $10B / mid ≥ $2B / small` (`size_band`).

`pages/4_Equity.py` now collects each peer's raw `info` (`peer_infos`) in the
existing peer loop and passes it to `compute_app_fair_value(..., peers=...)`; the
peers path is uncached (the list is unhashable) but re-uses the page's already
fetched peers, so no new network. The Cockpit / cached path uses `peers=None` →
the sector-median fallback.

---

## Task 4 — Integration + UI

* **`AppFairValue`** carries `company_type`, `company_type_confidence`,
  `routing_rationale`, `methods_used`, `excluded_anchors`, `ev_s_value`,
  `ev_ebitda_value`, `pb_ps_value`, `peer_basis`, `backlog_note`.
* **Anchor cache** `_SCHEMA_VERSION` bumped **1 → 2**; the entry now carries
  `company_type` + `peer_basis` + `caveats`. `load_all` accepts ONLY a valid
  current-schema envelope: a version mismatch OR a bare un-versioned legacy map is
  **rejected** (invalidate → recompute), so stale entries lacking `company_type`
  cannot surface (review fix F3/I4); old files on disk degrade gracefully (Cockpit
  falls back to Research-Required until rewarmed). The LONG band consumer still
  reads only `fair_value_low/mid/high` + `blend_state` — **verified: no Cockpit
  change beyond the version bump**.
* **`pages/4` AI Valuation Summary** shows a company-type badge (+ borderline /
  peer-basis note), the per-anchor method labels (`name $value (method)`), and the
  excluded anchors with their flag; the irreconcilable view is otherwise unchanged.
* **`lib/financial_tab.py` (pages/5 DCF)** shows an honest "DCF is not the primary
  method for this company type" note (different from "not computable") when the
  router excludes DCF.
* **`ui_utils.py`** additive EN/ZH `cockpit_fv_*` router keys.

### KTOS-class acceptance fixture (before → after)

| | relative (PE) | analyst | EV/EBITDA | dispersion | blend_state | band (low/mid/high) |
|---|---|---|---|---|---|---|
| **BEFORE** (single PE path) | $3.80 | $30.00 | — | 7.89× | `anchors_irreconcilable` | 0 / 0 / 0 |
| **AFTER** (project_driven) | $3.80 *(excluded)* | $30.00 | $23.46 | 1.28× | `blended` | $19.94 / $25.91 / $31.50 |

The trailing-PE garbage is excluded; the company is valued on EV/EBITDA +
analyst, producing a usable band instead of "we don't know".

---

## Constraints honored

Deterministic code only (no LLM); free APIs (yfinance/Finnhub fields from the
already-fetched `info` dict); no new per-ticker network beyond the existing
valuation/peer fetches; frozen files untouched (`macro_regime`, `workflow_state`,
`technical`); review-only (`approved_for_execution` never produced); the
dispersion gate still runs last; the default path is byte-identical to
stop-the-bleed.

## Files touched

- `lib/valuation_router.py` *(new)* — classifier + peer matcher
- `lib/equity_valuation.py` — method menus, extra-anchor helpers, routed assembly
- `lib/anchor_cache.py` — schema v2 (company_type / peer_basis), migration guard
- `lib/financial_tab.py` — honest DCF-excluded note
- `pages/4_Equity.py` — company-type badge + methods + excluded anchors; peer wiring
- `ui_utils.py` — EN/ZH `cockpit_fv_*` router keys
- `scripts/test_reliability_valuation_router.py` *(new, 104 checks)*
- `scripts/test_reliability_valuation_stopbleed.py` — version-bump-aware assertions
