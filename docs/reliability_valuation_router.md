# Phase — Valuation Refactor v1 (method router + growth-profile peers)

**Status:** Implemented · suite `scripts/test_reliability_valuation_router.py`
**54/54**; full canonical set green (stopbleed 65/65, 7A 115/115, 7B 187/187,
6c_b 47/47, equity_render_order 50/50, 6c_trading_desk 118/118, 6c_v3_entry_v4
47/47, 6b_v3_horizon_scoring 189/189, theme_baskets 146/146,
scanner_rotation_adapter 15/15).

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
coal).

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
| growth_unprofitable | EV/S + analyst (+ DCF *if computable*) | relative-PE (`excluded`) | PE is the garbage source |
| project_driven | EV/EBITDA + analyst | DCF, relative-PE (`excluded`) | `backlog_note` when backlog unavailable |
| cyclical | PB/PS band + analyst | DCF (`excluded`), relative-PE (`cycle_distorted`) | PB/PS band needs 5y history |

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
* **PB/PS band** (`_compute_pb_ps_band`): mid-cycle multiple = median of an
  injected 5y series × BVPS (or sales/share). Free `info` carries only the current
  multiple, so on the network-free path this returns `None` and a `backlog_note`/
  cyclical caveat is emitted (honest about the limit); a richer source / tests can
  inject `pb_history` / `ps_history`.

Sector fallback maps: `SECTOR_MEDIAN_EV_EBITDA` (default 12.0), `SECTOR_MEDIAN_PS`
(default 2.5), alongside the existing `SECTOR_MEDIAN_PE`.

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
  `company_type` + `peer_basis`. The version guard from stop-the-bleed handles
  migration: a stale version-1 envelope loads as empty (Cockpit falls back to
  Research-Required until rewarmed). The LONG band consumer still reads only
  `fair_value_low/mid/high` + `blend_state` — **verified: no Cockpit change beyond
  the version bump**.
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
- `scripts/test_reliability_valuation_router.py` *(new, 54 checks)*
- `scripts/test_reliability_valuation_stopbleed.py` — version-bump-aware assertions
