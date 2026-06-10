#!/usr/bin/env python3
"""
scripts/test_reliability_valuation_diagnosis.py

Anchor Intelligence v2.4 — valuation diagnosis card test suite (pure / offline).

Covers PART A:
  * A1 — build_valuation_diagnosis assembles a deterministic ValuationDiagnosis from
    AppFairValue + the migration readout, with NO new anchor math (every number comes
    off the inputs): applicable/rejected methods, anchor_consistency (cluster vs
    outlier), endorsed_range (incl. the honest irreconcilable state), confidence.
  * A2 — valuation_role deterministic mapping, EVERY boundary of the config ladder.
  * A3 — what_would_change: MECHANICAL falsifiable conditions implemented now
    (price-vs-range, analyst-pool deterioration) + the NARRATIVE Phase-8 placeholder.
  * A4 — reverse_dcf named Phase-8-pending slot (not computed this round).

Usage:
    python3 -B scripts/test_reliability_valuation_diagnosis.py
"""

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from unittest import mock  # noqa: E402

import pandas as pd  # noqa: E402

import lib.equity_valuation as eqv  # noqa: E402
import lib.holdings as holds  # noqa: E402
import lib.order_advisor as oa  # noqa: E402
import lib.valuation_diagnosis as vd  # noqa: E402

PASS = 0
FAIL = 0
_failures: list = []


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        d = f"  [{detail}]" if detail else ""
        _failures.append(f"FAIL  {label}{d}")


def _fv(**kw):
    base = dict(
        ticker="MU", computed_at="2026-06-08T13:00:00+00:00", company_type="cyclical",
        fair_value_low=95.0, fair_value_mid=110.0, fair_value_high=130.0,
        confidence="high", upside_pct=0.20, blend_state="blended",
        methods_used=["dcf", "relative", "analyst"],
        anchors=[{"name": "dcf", "value": 108.0, "basis": "fcf"},
                 {"name": "relative", "value": 112.0, "basis": "fwd-eps"}],
        excluded_anchors=[], caveats=[], anchor_dispersion=1.04,
        dcf_value=108.0, dcf_note="",
    )
    base.update(kw)
    return eqv.AppFairValue(**base)


# ===========================================================================
# 1. A1 — assembly: applicable + rejected methods, range, confidence (no new math)
# ===========================================================================
_d = vd.build_valuation_diagnosis(_fv(), current_price=100.0)
check("1.1 ticker / company_type passed through",
      _d.ticker == "MU" and _d.company_type == "cyclical")
check("1.2 applicable_methods == AppFairValue.methods_used (no recompute)",
      _d.applicable_methods == ["dcf", "relative", "analyst"])
check("1.3 confidence + upside passed straight through",
      _d.confidence == "high" and _d.upside_pct == 0.20)
check("1.4 endorsed_range == the blended low/mid/high",
      _d.endorsed_range.state == "endorsed"
      and (_d.endorsed_range.low, _d.endorsed_range.mid, _d.endorsed_range.high)
      == (95.0, 110.0, 130.0))
check("1.5 caveats passed through (empty here)", _d.caveats == [])
check("1.6 computed_at carried (epoch)", _d.computed_at == "2026-06-08T13:00:00+00:00")

# rejected methods: an excluded cycle-distorted PE + an unavailable DCF.
_fv_rej = _fv(
    methods_used=["relative", "analyst"], dcf_value=None,
    dcf_note="FCF unavailable for a cyclical trough year",
    excluded_anchors=[{"name": "pe", "value": 8.1, "basis": "trailing", "flag": "cycle_distorted"}],
)
_dr = vd.build_valuation_diagnosis(_fv_rej, current_price=100.0)
_rej_by_name = {r.name: r for r in _dr.rejected_methods}
check("1.7 excluded anchor surfaces as a rejected method WITH its flag reason",
      _rej_by_name.get("pe") is not None
      and _rej_by_name["pe"].reason == "cycle_distorted"
      and _rej_by_name["pe"].value == 8.1,
      detail=str(_dr.rejected_methods))
check("1.8 unavailable DCF surfaces as rejected (reason dcf_unavailable + note)",
      _rej_by_name.get("dcf") is not None
      and _rej_by_name["dcf"].reason == "dcf_unavailable"
      and "FCF unavailable" in _rej_by_name["dcf"].detail,
      detail=str(_rej_by_name.get("dcf")))
check("1.9 a DCF already in methods_used is NOT double-listed as rejected",
      "dcf" not in {r.name for r in vd.build_valuation_diagnosis(_fv()).rejected_methods})


# ===========================================================================
# 2. A1 — anchor_consistency: consistent / single / irreconcilable(outlier) / none
# ===========================================================================
check("2.1 two blended anchors within dispersion -> consistent, all cluster",
      _d.anchor_consistency.state == vd.CONSISTENCY_CONSISTENT
      and set(_d.anchor_consistency.clustered) == {"dcf", "relative"}
      and _d.anchor_consistency.outlier == "")

_single = vd.build_valuation_diagnosis(
    _fv(methods_used=["analyst"], anchors=[{"name": "analyst", "value": 110.0}],
        caveats=["single_anchor_blend"]))
check("2.2 single-anchor blend -> single_anchor state",
      _single.anchor_consistency.state == vd.CONSISTENCY_SINGLE
      and _single.anchor_consistency.clustered == ["analyst"])

# irreconcilable with NO producer per-anchor exclusion: the producer flagged the SET
# as irreconcilable but named no single culprit -> honest no_clear_outlier (F-A1).
# NEVER pick one by list order or a card-side distance metric.
_irr = vd.build_valuation_diagnosis(_fv(
    blend_state="anchors_irreconcilable", fair_value_low=0.0, fair_value_mid=0.0,
    fair_value_high=0.0, confidence="low", anchor_dispersion=3.4,
    anchors=[{"name": "dcf", "value": 105.0}, {"name": "relative", "value": 110.0},
             {"name": "analyst", "value": 360.0}]))
check("2.3 irreconcilable + no producer-excluded anchor -> outlier=no_clear_outlier (not invented)",
      _irr.anchor_consistency.state == vd.CONSISTENCY_IRRECONCILABLE
      and _irr.anchor_consistency.outlier == vd.NO_CLEAR_OUTLIER,
      detail=f"outlier={_irr.anchor_consistency.outlier}")
check("2.4 irreconcilable -> endorsed_range honest 'irreconcilable' (no fake mid)",
      _irr.endorsed_range.state == "irreconcilable"
      and _irr.endorsed_range.mid is None)

# F-A1 ORDER-INVARIANCE: two equal-deviation anchors, irreconcilable. Either input
# order must give the SAME (no_clear_outlier) classification — never order-dependent.
_pair_a = _fv(blend_state="anchors_irreconcilable", fair_value_low=0.0,
              fair_value_mid=0.0, fair_value_high=0.0, confidence="low",
              anchors=[{"name": "dcf", "value": 90.0}, {"name": "relative", "value": 110.0}])
_pair_b = _fv(blend_state="anchors_irreconcilable", fair_value_low=0.0,
              fair_value_mid=0.0, fair_value_high=0.0, confidence="low",
              anchors=[{"name": "relative", "value": 110.0}, {"name": "dcf", "value": 90.0}])
_oa = vd.build_valuation_diagnosis(_pair_a).anchor_consistency
_ob = vd.build_valuation_diagnosis(_pair_b).anchor_consistency
check("2.5 ORDER-INVARIANT: two equal-deviation anchors -> no_clear_outlier in BOTH orderings",
      _oa.outlier == vd.NO_CLEAR_OUTLIER and _ob.outlier == vd.NO_CLEAR_OUTLIER
      and _oa.outlier == _ob.outlier,
      detail=f"a={_oa.outlier}/b={_ob.outlier}")

# F-A1 GENUINE producer-flagged outlier: the producer excluded EXACTLY ONE anchor
# (its own per-anchor judgment) -> that name is reported; the kept anchors cluster.
_flagged = vd.build_valuation_diagnosis(_fv(
    methods_used=["dcf", "relative"],
    anchors=[{"name": "dcf", "value": 108.0}, {"name": "relative", "value": 112.0}],
    excluded_anchors=[{"name": "pe", "value": 8.1, "basis": "trailing",
                       "flag": "cycle_distorted"}]))
check("2.6 genuine producer-flagged outlier (1 excluded anchor) -> reported by name",
      _flagged.anchor_consistency.outlier == "pe"
      and set(_flagged.anchor_consistency.clustered) == {"dcf", "relative"},
      detail=f"outlier={_flagged.anchor_consistency.outlier}/clustered={_flagged.anchor_consistency.clustered}")

# Two excluded anchors -> NOT a single unambiguous outlier -> no name picked.
_two_ex = vd.build_valuation_diagnosis(_fv(
    blend_state="anchors_irreconcilable", fair_value_mid=0.0,
    anchors=[{"name": "dcf", "value": 100.0}, {"name": "relative", "value": 200.0}],
    excluded_anchors=[{"name": "pe", "value": 8.0}, {"name": "ev_s", "value": 300.0}]))
check("2.7 multiple excluded anchors -> no single outlier (irreconcilable -> no_clear_outlier)",
      _two_ex.anchor_consistency.outlier == vd.NO_CLEAR_OUTLIER,
      detail=f"outlier={_two_ex.anchor_consistency.outlier}")

_noanchor = vd.build_valuation_diagnosis(
    _fv(blend_state="no_anchor", fair_value_mid=0.0, anchors=[], methods_used=[]))
check("2.8 no_anchor band -> no_anchor consistency + unavailable range",
      _noanchor.anchor_consistency.state == vd.CONSISTENCY_NO_ANCHOR
      and _noanchor.endorsed_range.state == "unavailable")
check("2.9 consistent blend with no exclusions -> outlier '' (no disagreement)",
      _d.anchor_consistency.outlier == "")


# ===========================================================================
# 3. A2 — valuation_role: EVERY boundary of the deterministic ladder
# ===========================================================================
R_INFO, R_MID, R_LONG = (vd.VALUATION_ROLE_INFORMATIONAL, vd.VALUATION_ROLE_MID,
                         vd.VALUATION_ROLE_LONG)
check("3.1 low confidence -> informational (regardless of consistency/upside)",
      vd.classify_valuation_role("low", "consistent", 0.50, "blended") == R_INFO)
check("3.2 irreconcilable blend_state -> informational (even if confidence high)",
      vd.classify_valuation_role("high", "consistent", 0.50, "anchors_irreconcilable")
      == R_INFO)
check("3.3 medium + consistent -> mid_term_supportive",
      vd.classify_valuation_role("medium", "consistent", 0.50, "blended") == R_MID)
check("3.4 high + consistent + upside>15% -> long_term_eligible",
      vd.classify_valuation_role("high", "consistent", 0.16, "blended") == R_LONG)
check("3.5 BOUNDARY: high + consistent + upside EXACTLY 15% -> mid (strict > 15%)",
      vd.classify_valuation_role("high", "consistent", 0.15, "blended") == R_MID)
check("3.6 high + consistent + low upside -> mid_term (not long)",
      vd.classify_valuation_role("high", "consistent", 0.05, "blended") == R_MID)
check("3.7 single_anchor (not consistent) -> informational even at high conf+upside",
      vd.classify_valuation_role("high", vd.CONSISTENCY_SINGLE, 0.50, "blended") == R_INFO)
check("3.8 no_anchor consistency -> informational",
      vd.classify_valuation_role("high", vd.CONSISTENCY_NO_ANCHOR, 0.50, "blended") == R_INFO)
# end-to-end role on the assembled cards
check("3.9 assembled high+consistent+20% upside card -> long_term_eligible",
      _d.valuation_role == R_LONG, detail=_d.valuation_role)
check("3.10 assembled irreconcilable card -> informational",
      _irr.valuation_role == R_INFO, detail=_irr.valuation_role)
check("3.11 assembled single-anchor card -> informational",
      _single.valuation_role == R_INFO, detail=_single.valuation_role)


# ===========================================================================
# 4. A3 — what_would_change: MECHANICAL conditions + NARRATIVE placeholder
# ===========================================================================
# price 100 sits BELOW the endorsed low (95? no — 100 > 95). Use a price below 95.
_below = vd.build_valuation_diagnosis(_fv(), current_price=90.0)
_below_conds = {c.id: c for c in _below.what_would_change.mechanical}
check("4.1 price below endorsed low -> below-range condition MET, above NOT",
      _below_conds[vd.COND_PRICE_BELOW_RANGE].met is True
      and _below_conds[vd.COND_PRICE_ABOVE_RANGE].met is False,
      detail=str({k: v.met for k, v in _below_conds.items()}))
_above = vd.build_valuation_diagnosis(_fv(), current_price=140.0)
_above_conds = {c.id: c for c in _above.what_would_change.mechanical}
check("4.2 price above endorsed high -> above-range condition MET",
      _above_conds[vd.COND_PRICE_ABOVE_RANGE].met is True
      and _above_conds[vd.COND_PRICE_ABOVE_RANGE].threshold == 130.0
      and _above_conds[vd.COND_PRICE_ABOVE_RANGE].current == 140.0)
check("4.3 price inside the range -> neither boundary condition met",
      all(not c.met for c in _d.what_would_change.mechanical
          if c.id in (vd.COND_PRICE_ABOVE_RANGE, vd.COND_PRICE_BELOW_RANGE)))

# analyst-pool migration condition sourced from the v2.3 readout.
_mig_det = {"deteriorating": True, "consistency": "conviction", "direction": "falling"}
_mig_ok = {"deteriorating": False, "consistency": "conviction", "direction": "rising"}
_dmig = vd.build_valuation_diagnosis(_fv(), current_price=100.0, migration=_mig_det)
_dmig_ok = vd.build_valuation_diagnosis(_fv(), current_price=100.0, migration=_mig_ok)
_det_cond = {c.id: c for c in _dmig.what_would_change.mechanical}.get(
    vd.COND_ANALYST_POOL_DETERIORATING)
_ok_cond = {c.id: c for c in _dmig_ok.what_would_change.mechanical}.get(
    vd.COND_ANALYST_POOL_DETERIORATING)
check("4.4 deteriorating migration -> analyst-pool condition MET (basis migration_readout)",
      _det_cond is not None and _det_cond.met is True
      and _det_cond.basis == "migration_readout")
check("4.5 non-deteriorating migration -> analyst-pool condition NOT met",
      _ok_cond is not None and _ok_cond.met is False)
check("4.6 no migration supplied -> no analyst-pool condition emitted",
      vd.COND_ANALYST_POOL_DETERIORATING
      not in {c.id for c in _d.what_would_change.mechanical})
check("4.7 NARRATIVE catalysts are an explicit Phase-8 placeholder (empty + pending)",
      _d.what_would_change.narrative_catalysts == []
      and _d.what_would_change.narrative_pending is True)


# ===========================================================================
# 5. A4 — reverse-DCF is a NAMED Phase-8-pending slot (not computed this round)
# ===========================================================================
check("5.1 reverse_dcf slot present + labelled phase_8_pending, no implied growth",
      _d.reverse_dcf.status == "phase_8_pending"
      and _d.reverse_dcf.implied_growth is None)


# ===========================================================================
# 6. Determinism + fail-soft
# ===========================================================================
check("6.1 deterministic: identical inputs -> identical diagnosis",
      vd.build_valuation_diagnosis(_fv(), current_price=100.0, migration=_mig_det)
      == vd.build_valuation_diagnosis(_fv(), current_price=100.0, migration=_mig_det))
check("6.2 fail-soft: None fv -> default diagnosis (no raise)",
      isinstance(vd.build_valuation_diagnosis(None), vd.ValuationDiagnosis))
check("6.3 no current_price -> no price-vs-range conditions (migration cond still ok)",
      not any(c.id in (vd.COND_PRICE_ABOVE_RANGE, vd.COND_PRICE_BELOW_RANGE)
              for c in vd.build_valuation_diagnosis(_fv()).what_would_change.mechanical))


# ===========================================================================
# 7. A5 — the card's DATA PATH: PriceLevelResult.app_fair_value_obj threading
# ===========================================================================
# Matrix A: pages/9 builds the card from the AppFairValue the page-path
# compute_price_levels ALREADY computed (threaded out on app_fair_value_obj) — NO
# second compute. On the network-free ranking path the field stays None (no card,
# no heavy object). Drive the REAL order_advisor path with the producer mocked live.
_LIVE_RAW = {
    "fcf_ttm": 2.0e9, "fcf_source": "", "ebitda": 8.0e9, "shares": 1.1e9,
    "growth_rate": 0.15, "trailing_eps": 5.0, "forward_eps": None,
    "sector": "Technology", "industry": "Semiconductors",
    "analyst_median": 110.0, "analyst_mean": 108.0, "analyst_high": 130.0,
    "analyst_low": 95.0, "analyst_count": 20, "revenue_growth": 0.20,
    "earnings_growth": 0.10, "profit_margin": 0.10, "operating_margin": 0.12,
    "market_cap": 1.1e11, "enterprise_value": 1.2e11, "total_revenue": 2.5e10,
    "total_debt": 1.0e10, "total_cash": 0.9e10, "book_value": 30.0,
    "price_to_book": 3.0, "price_to_sales": 4.0, "live": True,
}


def _df40():
    rows = [[99.0, 102.0, 97.0, 100.0, 1_000_000.0] for _ in range(40)]
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"])


def _snap100():
    return {"price": 100.0, "EMA_10": None, "EMA_20": None, "SMA_50": None,
            "SMA_200": 80.0, "RSI_14": 50.0, "ADX": None, "ATR_14": 3.0,
            "Vol_ratio_20d": 1.0, "above_SMA200": True, "pct_from_52w_high": -5.0,
            "nearest_support": None, "nearest_resistance": None,
            "candlestick_pattern": "none"}


getattr(eqv._compute_cached, "clear", lambda: None)()
with mock.patch.object(eqv, "_fetch_raw", return_value=dict(_LIVE_RAW)), \
        mock.patch("ui_utils.load_ohlcv", return_value=_df40()), \
        mock.patch("lib.technical.snapshot", return_value=_snap100()), \
        mock.patch("lib.holdings.load_holdings", return_value=[]), \
        mock.patch("lib.holdings.load_cash_position", return_value=0.0), \
        mock.patch("lib.holdings.load_portfolio_settings",
                   return_value=holds.PortfolioSettings()):
    _lv_page = oa.compute_price_levels("VDX", None, horizon="long",
                                       valuation_percentile=0.3, allow_fetch=True)
check("7.1 page path (allow_fetch=True) threads the live AppFairValue onto the result",
      isinstance(getattr(_lv_page, "app_fair_value_obj", None), eqv.AppFairValue)
      and _lv_page.app_fair_value_obj.ticker == "VDX",
      detail=str(type(getattr(_lv_page, "app_fair_value_obj", None))))
# The card then assembles from that object with no further compute.
_diag_page = vd.build_valuation_diagnosis(_lv_page.app_fair_value_obj,
                                          current_price=_lv_page.current_price)
check("7.2 the threaded object assembles a real diagnosis (company_type carried)",
      isinstance(_diag_page, vd.ValuationDiagnosis) and bool(_diag_page.company_type))

# Network-free ranking path: app_fair_value_obj must be None (no card, no object).
_net = {"n": 0}


def _boom(*_a, **_k):
    _net["n"] += 1
    raise AssertionError("producer/fetch reached on the network-free path")


with mock.patch.object(eqv, "compute_app_fair_value", side_effect=_boom), \
        mock.patch.object(eqv, "fetch_cyclical_band_history", side_effect=_boom), \
        mock.patch.object(eqv, "_fetch_raw", side_effect=_boom), \
        mock.patch("ui_utils.load_ohlcv", return_value=_df40()), \
        mock.patch("lib.technical.snapshot", return_value=_snap100()), \
        mock.patch("lib.holdings.load_holdings", return_value=[]), \
        mock.patch("lib.holdings.load_cash_position", return_value=0.0), \
        mock.patch("lib.holdings.load_portfolio_settings",
                   return_value=holds.PortfolioSettings()):
    _lv_rank = oa.compute_price_levels("VDX", None, horizon="long",
                                       valuation_percentile=0.3, allow_fetch=False)
check("7.3 network-free path: app_fair_value_obj is None (no compute, no card there)",
      getattr(_lv_rank, "app_fair_value_obj", "x") is None and _net["n"] == 0,
      detail=f"obj={getattr(_lv_rank, 'app_fair_value_obj', 'x')}/net={_net['n']}")


# ===========================================================================
# 8. A5 — render bindings (source inspection) + snapshot EXCLUSION (parity discipline)
# ===========================================================================
def _read(p):
    return open(os.path.join(_REPO_ROOT, p), encoding="utf-8").read()


_p4 = _read(os.path.join("pages", "4_Equity.py"))
_p9 = _read(os.path.join("pages", "9_Trading_Desk.py"))
check("8.1 pages/4 builds + renders the valuation diagnosis card",
      "build_valuation_diagnosis" in _p4 and "render_valuation_diagnosis_card" in _p4)
check("8.2 pages/9 builds + renders the valuation diagnosis card",
      "build_valuation_diagnosis" in _p9 and "render_valuation_diagnosis_card" in _p9)
check("8.3 pages/4 feeds the read-only migration readout into the card (no live compute)",
      "read_migration(" in _p4)

# Snapshot EXCLUSION (Matrix A parity discipline): the diagnosis card is a render-time
# assembly — NO field flows into the daily snapshot. Assert it is NOT smuggled into the
# OpportunityCard snapshot key set (which would demand a §18 parity binding).
import lib.opportunity_ranker as orr  # noqa: E402

_snap_keys_join = " ".join(orr.ANCHOR_SNAPSHOT_KEYS).lower()
check("8.4 valuation_role / diagnosis is NOT in the snapshot anchor-block keys "
      "(render-time only; parity satisfied by explicit exclusion)",
      "valuation_role" not in _snap_keys_join and "diagnosis" not in _snap_keys_join,
      detail=str(orr.ANCHOR_SNAPSHOT_KEYS))


# ===========================================================================
# 9. A5 — i18n coverage: EVERY token the render can emit has a bilingual key
# ===========================================================================
import ui_utils as _ui  # noqa: E402

_zh = _ui.TRANSLATIONS["zh"]
_en = _ui.TRANSLATIONS["en"]
# The dynamic keys render_valuation_diagnosis_card builds via t(f"...{token}").
_needed = ["valdiag_header", "valdiag_role", "valdiag_consistency",
           "valdiag_endorsed_range", "valdiag_range_irreconcilable",
           "valdiag_range_unavailable", "valdiag_applicable_methods",
           "valdiag_rejected_methods", "valdiag_what_would_change",
           "valdiag_outlier", "valdiag_no_clear_outlier",
           "valdiag_cond_met", "valdiag_cond_armed",
           "valdiag_reverse_dcf_pending", "valdiag_narrative_pending",
           "valdiag_reason_dcf_unavailable", "valdiag_reason_excluded_anchor"]
_needed += [f"valdiag_role_{r}" for r in
            (vd.VALUATION_ROLE_INFORMATIONAL, vd.VALUATION_ROLE_MID, vd.VALUATION_ROLE_LONG)]
_needed += [f"valdiag_consistency_{s}" for s in
            (vd.CONSISTENCY_CONSISTENT, vd.CONSISTENCY_SINGLE,
             vd.CONSISTENCY_IRRECONCILABLE, vd.CONSISTENCY_NO_ANCHOR)]
_needed += [f"valdiag_cond_{c}" for c in
            (vd.COND_PRICE_ABOVE_RANGE, vd.COND_PRICE_BELOW_RANGE,
             vd.COND_ANALYST_POOL_DETERIORATING)]
# Anchor Intel v2.5 — the peer-match-quality card field's render tokens.
_needed += ["valdiag_peer_match", "valdiag_peer_match_high", "valdiag_peer_match_low",
            "valdiag_reason_insufficient_comparable_peers"]
_missing_zh = [k for k in _needed if k not in _zh]
_missing_en = [k for k in _needed if k not in _en]
check("9.1 every diagnosis-card token has a zh translation key",
      _missing_zh == [], detail=str(_missing_zh))
check("9.2 every diagnosis-card token has an en translation key",
      _missing_en == [], detail=str(_missing_en))
check("9.3 render helper + the role-reason flag key it reuses exist",
      hasattr(_ui, "render_valuation_diagnosis_card")
      and "cockpit_fv_flag_cycle_distorted" in _zh
      and "cockpit_fv_flag_cycle_distorted" in _en)


# ===========================================================================
# 10. Anchor Intel v2.5 — peer_match_quality card field (bind-or-exclude parity)
# ===========================================================================
# A "low" AppFairValue stand-in -> the diagnosis SOURCES the field (not recomputed);
# the render binds it; and it is EXCLUDED from the snapshot (render-time only).
_pm_fv = _fv(peer_match_quality="low", peer_match_reason="insufficient_comparable_peers")
_pm_diag = vd.build_valuation_diagnosis(_pm_fv)
check("10.1 diagnosis sources peer_match_quality + reason from AppFairValue (no recompute)",
      _pm_diag.peer_match_quality == "low"
      and _pm_diag.peer_match_reason == "insufficient_comparable_peers")
check("10.2 not-assessed fv ('') -> diagnosis carries '' (network-free / no peers)",
      vd.build_valuation_diagnosis(_fv()).peer_match_quality == "")
_ui_src = open(os.path.join(_REPO_ROOT, "ui_utils.py"), encoding="utf-8").read()
check("10.3 render BINDS the peer_match field (both high + low branches)",
      "peer_match_quality" in _ui_src
      and "valdiag_peer_match_low" in _ui_src and "valdiag_peer_match_high" in _ui_src)
check("10.4 peer_match is EXCLUDED from the snapshot anchor-block keys (parity)",
      "peer_match" not in " ".join(orr.ANCHOR_SNAPSHOT_KEYS).lower(),
      detail=str(orr.ANCHOR_SNAPSHOT_KEYS))


# ===========================================================================
print("\n".join(_failures))
total = PASS + FAIL
print(f"\nAnchor Intelligence v2.4 — valuation diagnosis card — {PASS}/{total} checks passed.")
if FAIL:
    sys.exit(1)
print("ALL PASSED.")
