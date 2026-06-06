# Phase — Valuation Stop-the-Bleed

**Status:** Implemented · suite `scripts/test_reliability_valuation_stopbleed.py`
**54/54**; regressions green (7A 115/115, 6c_b 47/47, equity_render_order 50/50,
6c_trading_desk 118/118, 6c_v3_entry_v4 47/47, 6b_v3_horizon_scoring 189/189).

## Problem (real-data audit)

The blended fair value averaged irreconcilable anchors — relative **$3.23** vs
analyst **$112.50** → mid **$53.66** at confidence *medium*. Garbage averaged
with signal, and it propagated: `order_advisor` LONG entry zones consume the
conservative anchor, so a bad valuation became a bad entry zone. Separately, the
Cockpit long-horizon enrichment could not see valuation anchors on its
network-free path, so LONG status collapsed to **Research Required** for every
candidate.

Three deterministic (no-LLM) tasks, all in the valuation layer.

---

## Task 1 — Anchor consistency gate

A **dispersion gate** runs before any blend. Dispersion = `max/min` ratio across
the available anchors after unit sanity (positive finite). When it exceeds the
threshold the anchors are **not blended**: each is presented separately with its
basis, confidence is forced **low**, and the conservative anchor is **None**.

### Gate threshold config

| Module | Constant | Default | Anchors compared |
|--------|----------|---------|------------------|
| `lib/equity_valuation.py` | `ANCHOR_DISPERSION_THRESHOLD` | **3.0** | DCF / relative / analyst (the blend) |
| `lib/valuation_anchor.py` | `ANCHOR_DISPERSION_THRESHOLD` | **3.0** | analyst_anchor / relative_anchor |

Boundary is `>` (a ratio of exactly 3.0× is still blended). Both are
module-level, configurable.

- **`equity_valuation.AppFairValue`** gains `blend_state`
  (`blended` | `anchors_irreconcilable` | `no_anchor`), `anchor_dispersion`,
  `anchors` (side-by-side `{name, value, basis}` list), `relative_basis`,
  `peer_pe_basis`. On the irreconcilable branch the low/mid/high band collapses
  to `0.0` so no consumer mistakes it for precision.
- **`valuation_anchor.FairValueAnchor`** gains `anchor_state`; an irreconcilable
  state short-circuits the three-tier confidence to `low` (→ `conservative_anchor`
  None).
- **`order_advisor` LONG path** consumes the new states. **Both** the
  irreconcilable-anchor path AND the missing / low-confidence anchor path on LONG
  **initiate** emit the SAME explicit degrade (unified reason + code +
  next_trigger): action `wait`, no zone, code
  `valuation_unreliable_technical_only`, reason *"LONG: valuation unreliable —
  technical reference only / 估值不可靠——仅供技术参考"*, next_trigger *"Reconcile
  valuation anchors before entry / 入场前需先校准估值锚"* — so the UI and Trading Desk
  always know WHY there is no LONG zone. SHORT/MID are untouched; no numeric
  change elsewhere; `approved_for_execution` stays False.
- **UI** (`pages/4` AI Valuation Summary) renders the irreconcilable state
  honestly: a warning, an explanation line, each anchor side by side with its
  basis, the current price marker, and **no range bar**. Bilingual via `t()`.

---

## Task 2 — Forward-estimates basis

The relative anchor in `equity_valuation` now prefers **forward consensus EPS**
(`yfinance forwardEps`); it falls back to trailing EPS with
`relative_basis = "trailing_fallback"`. Because the sector-median P/E map is a
trailing-basis hardcoded table, a forward-EPS relative is flagged
`peer_pe_basis = "mixed"` (forward earnings × trailing multiple). The basis is
surfaced as a small badge under the relative-value metric in the valuation UI.

---

## Task 3 — Anchor cache for Cockpit LONG enrichment

`lib/anchor_cache.py` — a tiny, deterministic, **network-free** JSON cache.

### Cache schema (`data/anchor_cache.json`)

```json
{
  "version": 1,
  "anchors": {
    "NVDA": {
      "ticker": "NVDA",
      "anchors": [{"name": "relative", "value": 3.23, "basis": "trailing_fallback"},
                  {"name": "analyst", "value": 112.5, "basis": "analyst (n=10)"}],
      "blend_state": "anchors_irreconcilable",
      "confidence": "low",
      "relative_basis": "forward",
      "peer_pe_basis": "mixed",
      "fair_value_low": 0.0,
      "fair_value_mid": 0.0,
      "fair_value_high": 0.0,
      "conservative_anchor": null,
      "computed_at": "2026-06-05T13:00:00+00:00"
    }
  }
}
```

- **Atomic write** (`tmp` + `os.replace`, mirroring `lib/holdings`), fail-closed,
  merge-preserving (other tickers retained).
- **Write-through** from `equity_valuation.store_equity_research_result` (the
  Equity page valuation hand-off) and the `write_app_fair_value` helper.
- **Staleness:** `DEFAULT_STALENESS_DAYS = 7` calendar days (~5 trading days),
  configurable per call. A missing / unparseable `computed_at` is stale.
- **Cockpit enrichment:** `rank_opportunities(..., anchor_cache=<map>,
  anchor_staleness_days=None)` reads the cache (read-only, no network). A **fresh**
  high/medium band is passed to `compute_price_levels(app_fair_value=...)` for the
  top-N tickers so the LONG status differentiates (in / above / below the value
  band). Stale / missing → prior behavior (Research Required). `pages/7` loads the
  cache via `anchor_cache.load_all()` and passes it.
- **Snapshot:** `OpportunityCard.anchor_age_days` (and the snapshot record) record
  the age of the cached anchor that drove the LONG status (None when none was
  used), so future review can assess staleness impact.

---

## LONG statuses changed (fixture set)

On the mock-only Cockpit fixture (`NVDA`, fresh high-confidence band low/mid/high
80/100/130 vs current 100):

| Cache state | LONG status before | LONG status after | `anchor_age_days` |
|-------------|--------------------|-------------------|-------------------|
| Fresh (2 days old) | Research Required | **Actionable Now** | 2.0 |
| Stale (35 days old) | Research Required | Research Required | None |
| No cache | Research Required | Research Required | None |
| Fresh **irreconcilable** band | Research Required | Research Required (LONG entry degraded to "valuation unreliable — technical reference only") | 2.0 |

SHORT / MID statuses are unchanged in every case.

> **`anchor_age_days` is independent of usability.** It records the age of a
> *fresh* cached anchor whenever one existed — including a fresh-but-unusable
> (irreconcilable) anchor (age `2.0` above). That a fresh anchor existed yet
> could not anchor a LONG zone is itself useful review signal; **usability** is
> carried separately by `blend_state` (`anchors_irreconcilable`) / the LONG
> degrade reason, not by the age field.

---

## Constraints honored

Deterministic code only (no LLM); no changes to
`macro_regime`/`workflow_state`/`technical`; the `order_advisor` change is limited
to consuming the new anchor states on the LONG path (no numeric change elsewhere);
free APIs only (yfinance); review-only outputs (`approved_for_execution` always
False; no broker / order / DB / vector store).

## Files touched

- `lib/anchor_cache.py` *(new)*
- `lib/equity_valuation.py` — gate + forward basis + write-through
- `lib/valuation_anchor.py` — anchor_state gate
- `lib/order_advisor.py` — LONG state consumption (`app_fair_value` kwarg)
- `lib/opportunity_ranker.py` — cache-driven LONG enrichment + `anchor_age_days`
- `pages/4_Equity.py` — irreconcilable UI + basis badge
- `pages/7_Investment_Cockpit.py` — load + pass the anchor cache
- `ui_utils.py` — bilingual i18n keys
- `scripts/test_reliability_valuation_stopbleed.py` *(new, 54 checks)*
