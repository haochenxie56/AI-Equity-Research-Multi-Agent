#!/usr/bin/env python3
"""
scripts/test_reliability_valuation_router.py

Phase "Valuation Refactor v1 — method router + growth-profile peer matching"
test suite (mock-only / offline). Runs entirely WITHOUT real API calls.

Covers:
  Task 1 — Company classifier (lib/valuation_router.classify_company):
    * each of the five types fires from deterministic financial rules;
    * borderline confidence (volatility-only / near-threshold) routes to the
      default mature menu via select_method_menu;
    * fired_rules are auditable.

  Task 2 — Method menus (lib/equity_valuation.build_app_fair_value routing):
    * each company type's BLENDED anchor set composition;
    * PE exclusion for growth_unprofitable (relative in excluded_anchors, not
      blended);
    * cyclical trailing-PE flagged cycle_distorted; project/growth DCF excluded;
    * the dispersion gate still runs LAST on the menu-produced set.

  Task 3 — Growth-profile peer matching (match_growth_profile_peers):
    * growth+size band match; sector_fallback flag when < min_peers;
    * median multiple over the matched set.

  Task 4 — Integration:
    * anchor_cache schema version bump + migration (old loads empty);
    * AppFairValue carries company_type + routing rationale;
    * the KTOS-class acceptance fixture: a project_driven company with
      trailing-PE garbage produces a usable EV/EBITDA + analyst band instead of
      anchors_irreconcilable.

Usage:
    python3 -B scripts/test_reliability_valuation_router.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ["FINNHUB_API_KEY"] = ""

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import lib.valuation_router as vr  # noqa: E402
import lib.equity_valuation as eqv  # noqa: E402
import lib.anchor_cache as ac  # noqa: E402


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


def _names(anchors) -> set:
    return {a.get("name") for a in (anchors or [])}


def _excluded_flag(fv, name):
    for a in fv.excluded_anchors:
        if a.get("name") == name:
            return a.get("flag")
    return None


# ===========================================================================
# Section 1 — Classifier rules (Task 1)
# ===========================================================================

# mature_profitable: moderate growth, positive margin, no sector/industry hint.
_mature = vr.classify_company(
    ticker="MAT", sector="Consumer Defensive", industry="Packaged Foods",
    revenue_growth=0.04, profit_margin=0.12, fcf=1.0e9, market_cap=5.0e10)
check("1.1 mature_profitable default", _mature.company_type == "mature_profitable",
      detail=_mature.company_type)
check("1.2 mature confidence clear", _mature.confidence == "clear",
      detail=_mature.confidence)
check("1.3 fired_rules are auditable (list of dicts with thresholds)",
      isinstance(_mature.fired_rules, list) and _mature.fired_rules
      and all("threshold" in r and "fired" in r for r in _mature.fired_rules))

# growth_profitable: high growth + healthy margin.
_gp = vr.classify_company(
    ticker="GP", sector="Technology", industry="Software—Application",
    revenue_growth=0.35, profit_margin=0.18, fcf=5.0e8, market_cap=2.0e10)
check("1.4 growth_profitable", _gp.company_type == "growth_profitable",
      detail=_gp.company_type)

# growth_unprofitable: high growth + negative margin.
_gu = vr.classify_company(
    ticker="GU", sector="Technology", industry="Software—Infrastructure",
    revenue_growth=0.45, profit_margin=-0.20, fcf=-2.0e8, market_cap=8.0e9)
check("1.5 growth_unprofitable", _gu.company_type == "growth_unprofitable",
      detail=_gu.company_type)

# project_driven: defense industry hint (KTOS-class).
_pd = vr.classify_company(
    ticker="PD", sector="Industrials", industry="Aerospace & Defense",
    revenue_growth=0.10, profit_margin=0.05, fcf=1.0e8, market_cap=4.0e9)
check("1.6 project_driven via industry hint", _pd.company_type == "project_driven",
      detail=_pd.company_type)
check("1.7 project_driven from name hint is clear", _pd.confidence == "clear",
      detail=_pd.confidence)

# cyclical: energy sector.
_cy = vr.classify_company(
    ticker="CY", sector="Energy", industry="Oil & Gas E&P",
    revenue_growth=0.05, profit_margin=0.15, fcf=2.0e9, market_cap=6.0e10)
check("1.8 cyclical via sector", _cy.company_type == "cyclical",
      detail=_cy.company_type)

# cyclical: semiconductor/memory industry hint even outside Energy/Materials.
_cy2 = vr.classify_company(
    ticker="CY2", sector="Technology", industry="Semiconductor Memory",
    revenue_growth=0.05, profit_margin=0.10, fcf=1.0e9, market_cap=5.0e10)
check("1.9 cyclical via memory industry hint", _cy2.company_type == "cyclical",
      detail=_cy2.company_type)

# Borderline: project_driven on volatility ALONE (no name hint) -> borderline.
_pd_vol = vr.classify_company(
    ticker="PDV", sector="Industrials", industry="Specialty Business Services",
    revenue_growth=0.06, profit_margin=0.05, fcf=1.0e8, market_cap=3.0e9,
    revenue_cov=0.40)
check("1.10 project_driven volatility-only -> borderline",
      _pd_vol.company_type == "project_driven" and _pd_vol.confidence == "borderline",
      detail=f"{_pd_vol.company_type}/{_pd_vol.confidence}")

# Borderline: growth right on the high threshold.
_gp_edge = vr.classify_company(
    ticker="GPE", sector="Technology", industry="Software—Application",
    revenue_growth=0.26, profit_margin=0.18, fcf=1.0e8, market_cap=1.0e10)
check("1.11 growth on threshold -> borderline confidence",
      _gp_edge.company_type == "growth_profitable" and _gp_edge.confidence == "borderline",
      detail=f"{_gp_edge.company_type}/{_gp_edge.confidence}")

# select_method_menu: borderline routes to the default mature menu.
check("1.12 borderline routes to mature menu",
      vr.select_method_menu(_pd_vol) == "mature_profitable",
      detail=vr.select_method_menu(_pd_vol))
check("1.13 clear project_driven routes to its own menu",
      vr.select_method_menu(_pd) == "project_driven",
      detail=vr.select_method_menu(_pd))

# growth_band / size_band helpers.
check("1.14 growth_band high/moderate/low",
      vr.growth_band(0.30) == "high" and vr.growth_band(0.15) == "moderate"
      and vr.growth_band(0.02) == "low")
check("1.15 size_band large/mid/small",
      vr.size_band(2.0e10) == "large" and vr.size_band(5.0e9) == "mid"
      and vr.size_band(5.0e8) == "small")


# ===========================================================================
# Section 2 — Method menu anchor-set composition (Task 2)
# ===========================================================================

# mature: DCF + relative + analyst all blended (legacy behavior).
_m = eqv.build_app_fair_value(
    "M", 100.0, dcf_value=100.0, relative_value=102.0, analyst_target=101.0,
    analyst_count=10, company_type="mature_profitable")
check("2.1 mature blends dcf+relative+analyst",
      _names(_m.anchors) == {"dcf", "relative", "analyst"}, detail=str(_names(_m.anchors)))
check("2.2 mature has no excluded anchors", _m.excluded_anchors == [],
      detail=str(_m.excluded_anchors))

# growth_profitable: ev_s + relative + analyst blended; DCF excluded.
_gpb = eqv.build_app_fair_value(
    "GPB", 50.0, dcf_value=100.0, relative_value=42.0, analyst_target=45.0,
    analyst_count=8, company_type="growth_profitable", ev_s_value=40.0)
check("2.3 growth_profitable blends ev_s+relative+analyst",
      _names(_gpb.anchors) == {"ev_s", "relative", "analyst"},
      detail=str(_names(_gpb.anchors)))
check("2.4 growth_profitable excludes DCF (flag 'excluded')",
      _excluded_flag(_gpb, "dcf") == "excluded", detail=str(_gpb.excluded_anchors))

# growth_unprofitable: ev_s + analyst; PE EXCLUDED.
_gub = eqv.build_app_fair_value(
    "GUB", 50.0, dcf_value=None, relative_value=80.0, analyst_target=45.0,
    analyst_count=6, company_type="growth_unprofitable", ev_s_value=40.0)
check("2.5 growth_unprofitable blends ev_s+analyst only",
      _names(_gub.anchors) == {"ev_s", "analyst"}, detail=str(_names(_gub.anchors)))
check("2.6 growth_unprofitable EXCLUDES relative-PE (the garbage source)",
      "relative" not in _names(_gub.anchors)
      and _excluded_flag(_gub, "relative") == "excluded",
      detail=str(_gub.excluded_anchors))

# growth_unprofitable: DCF included only if computable (blend_if_present).
_gub_dcf = eqv.build_app_fair_value(
    "GUD", 50.0, dcf_value=44.0, relative_value=80.0, analyst_target=45.0,
    analyst_count=6, company_type="growth_unprofitable", ev_s_value=40.0)
check("2.7 growth_unprofitable adds DCF when computable",
      "dcf" in _names(_gub_dcf.anchors), detail=str(_names(_gub_dcf.anchors)))

# project_driven: ev_ebitda + analyst; DCF + PE excluded.
_pdb = eqv.build_app_fair_value(
    "PDB", 28.0, dcf_value=100.0, relative_value=3.8, analyst_target=30.0,
    analyst_count=12, company_type="project_driven", ev_ebitda_value=23.0,
    backlog_note="backlog n/a")
check("2.8 project_driven blends ev_ebitda+analyst",
      _names(_pdb.anchors) == {"ev_ebitda", "analyst"}, detail=str(_names(_pdb.anchors)))
check("2.9 project_driven excludes DCF + relative-PE",
      _excluded_flag(_pdb, "dcf") == "excluded"
      and _excluded_flag(_pdb, "relative") == "excluded",
      detail=str(_pdb.excluded_anchors))
check("2.10 project_driven carries backlog_note",
      "backlog" in (_pdb.backlog_note or "").lower(), detail=_pdb.backlog_note)

# cyclical: pb_ps_band + analyst; trailing-PE flagged cycle_distorted.
_cyb = eqv.build_app_fair_value(
    "CYB", 30.0, dcf_value=100.0, relative_value=20.0, analyst_target=30.0,
    analyst_count=9, company_type="cyclical", pb_ps_value=28.0)
check("2.11 cyclical blends pb_ps+analyst",
      _names(_cyb.anchors) == {"pb_ps", "analyst"}, detail=str(_names(_cyb.anchors)))
check("2.12 cyclical flags trailing-PE cycle_distorted (not blended)",
      "relative" not in _names(_cyb.anchors)
      and _excluded_flag(_cyb, "relative") == "cycle_distorted",
      detail=str(_cyb.excluded_anchors))

# methods_used + company_type recorded.
check("2.13 methods_used labels recorded",
      isinstance(_pdb.methods_used, list) and len(_pdb.methods_used) == 2
      and any("EV/EBITDA" in m for m in _pdb.methods_used), detail=str(_pdb.methods_used))
check("2.14 company_type stored on AppFairValue",
      _pdb.company_type == "project_driven", detail=_pdb.company_type)


# ===========================================================================
# Section 3 — Dispersion gate STILL runs last on the routed set (Task 1+2)
# ===========================================================================

# project_driven menu, but ev_ebitda vs analyst > 3x -> still irreconcilable.
_pd_irr = eqv.build_app_fair_value(
    "PDI", 28.0, dcf_value=None, relative_value=3.8, analyst_target=90.0,
    analyst_count=12, company_type="project_driven", ev_ebitda_value=10.0)
check("3.1 routed set still gated: ev_ebitda 10 vs analyst 90 -> irreconcilable",
      _pd_irr.blend_state == "anchors_irreconcilable", detail=_pd_irr.blend_state)
check("3.2 irreconcilable routed set collapses band",
      _pd_irr.fair_value_mid == 0.0, detail=str(_pd_irr.fair_value_mid))

# project_driven menu, ev_ebitda vs analyst within 3x -> blended.
_pd_ok = eqv.build_app_fair_value(
    "PDO", 28.0, dcf_value=None, relative_value=3.8, analyst_target=30.0,
    analyst_count=12, company_type="project_driven", ev_ebitda_value=23.0)
check("3.3 routed set within gate -> blended band",
      _pd_ok.blend_state == "blended" and _pd_ok.fair_value_mid > 0,
      detail=f"{_pd_ok.blend_state}/{_pd_ok.fair_value_mid}")
check("3.4 excluded relative-PE does NOT enter the dispersion gate",
      _pd_ok.anchor_dispersion is not None and _pd_ok.anchor_dispersion < 3.0,
      detail=str(_pd_ok.anchor_dispersion))


# ===========================================================================
# Section 4 — Default-path byte-compatibility (no company_type)
# ===========================================================================

_legacy = eqv.build_app_fair_value(
    "LEG", 100.0, dcf_value=100.0, relative_value=102.0, analyst_target=101.0,
    analyst_count=12)
_routed_mature = eqv.build_app_fair_value(
    "LEG", 100.0, dcf_value=100.0, relative_value=102.0, analyst_target=101.0,
    analyst_count=12, company_type="mature_profitable")
check("4.1 default (no company_type) low/mid/high == mature menu",
      (_legacy.fair_value_low, _legacy.fair_value_mid, _legacy.fair_value_high)
      == (_routed_mature.fair_value_low, _routed_mature.fair_value_mid,
          _routed_mature.fair_value_high),
      detail=f"{_legacy.fair_value_mid} vs {_routed_mature.fair_value_mid}")
check("4.2 default confidence preserved (high)", _legacy.confidence == "high",
      detail=_legacy.confidence)


# ===========================================================================
# Section 5 — Growth-profile peer matching (Task 3)
# ===========================================================================

_target = {"ticker": "TGT", "sector": "Technology", "revenue_growth": 0.30,
           "market_cap": 2.0e10}
# Four growth+size matched peers (Technology, high growth, large) + one off-band.
_cands = [
    {"ticker": "P1", "sector": "Technology", "revenueGrowth": 0.32,
     "marketCap": 3.0e10, "forwardPE": 40.0},
    {"ticker": "P2", "sector": "Technology", "revenueGrowth": 0.28,
     "marketCap": 2.5e10, "forwardPE": 44.0},
    {"ticker": "P3", "sector": "Technology", "revenueGrowth": 0.35,
     "marketCap": 5.0e10, "forwardPE": 50.0},
    {"ticker": "P4", "sector": "Technology", "revenueGrowth": 0.40,
     "marketCap": 1.5e10, "forwardPE": 46.0},
    {"ticker": "OFF", "sector": "Technology", "revenueGrowth": 0.03,
     "marketCap": 5.0e8, "forwardPE": 12.0},  # low growth + small -> off band
]
_pm = vr.match_growth_profile_peers(_target, _cands, multiple_field="forwardPE", min_peers=4)
check("5.1 growth-matched peers found (>=4) -> growth_matched basis",
      _pm.peer_basis == "growth_matched", detail=_pm.peer_basis)
check("5.2 off-band peer excluded from the matched set",
      "OFF" not in {p["ticker"] for p in _pm.peers}, detail=str([p["ticker"] for p in _pm.peers]))
check("5.3 median multiple over matched peers (median of 40,44,46,50 = 45)",
      _pm.median_multiple == 45.0, detail=str(_pm.median_multiple))

# Fewer than min_peers matched -> sector_fallback.
_pm_fb = vr.match_growth_profile_peers(
    _target, _cands[:2] + [_cands[-1]], multiple_field="forwardPE", min_peers=4)
check("5.4 < min_peers matched -> sector_fallback basis",
      _pm_fb.peer_basis == "sector_fallback", detail=_pm_fb.peer_basis)
check("5.5 sector_fallback still computes a median over sector peers",
      _pm_fb.median_multiple is not None, detail=str(_pm_fb.median_multiple))

# Target excluded from candidates by ticker.
_pm_self = vr.match_growth_profile_peers(
    {"ticker": "P1", "sector": "Technology", "revenue_growth": 0.30, "market_cap": 2.0e10},
    _cands, multiple_field="forwardPE", min_peers=3)
check("5.6 target ticker excluded from its own peer set",
      "P1" not in {p["ticker"] for p in _pm_self.peers},
      detail=str([p["ticker"] for p in _pm_self.peers]))


# ===========================================================================
# Section 6 — anchor_cache schema version bump + migration (Task 4)
# ===========================================================================

check("6.1 schema version bumped to 2", ac._SCHEMA_VERSION == 2,
      detail=str(ac._SCHEMA_VERSION))

with tempfile.TemporaryDirectory() as _td:
    _p = Path(_td) / "anchor_cache.json"
    # An OLD version-1 envelope must load as empty (migration via version guard).
    with open(_p, "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "anchors": {"OLD": {"fair_value_mid": 9.0}}}, fh)
    check("6.2 old version-1 envelope loads as empty (migration)",
          ac.load_all(_p) == {}, detail=str(ac.load_all(_p)))

    # A current-version write/read round-trips and carries company_type.
    _fv = eqv.build_app_fair_value(
        "PDB", 28.0, dcf_value=None, relative_value=3.8, analyst_target=30.0,
        analyst_count=12, company_type="project_driven", ev_ebitda_value=23.0,
        peer_basis="sector_fallback")
    ac.write_app_fair_value(_fv, path=_p)
    _entry = ac.read_anchor("PDB", path=_p)
    check("6.3 current-version entry round-trips", _entry is not None
          and _entry.get("fair_value_mid", 0) > 0, detail=str(_entry))
    check("6.4 cache entry carries company_type (schema v2)",
          _entry.get("company_type") == "project_driven", detail=str(_entry))
    check("6.5 cache entry carries peer_basis", _entry.get("peer_basis") == "sector_fallback",
          detail=str(_entry))


# ===========================================================================
# Section 7 — KTOS-class acceptance fixture (project_driven, PE garbage)
# ===========================================================================

# A defense contractor: trailing-PE relative is garbage ($3.80) vs a $30 analyst
# target. Under the OLD single-PE path these two anchors are irreconcilable.
_KTOS_RAW = {
    "fcf_ttm": None, "fcf_source": "", "ebitda": 2.5e8, "shares": 1.3e8,
    "growth_rate": 0.08, "trailing_eps": 0.20, "forward_eps": None,
    "sector": "Industrials", "industry": "Aerospace & Defense",
    "analyst_median": 30.0, "analyst_mean": 29.0, "analyst_count": 12,
    "revenue_growth": 0.08, "earnings_growth": 0.05, "profit_margin": 0.04,
    "operating_margin": 0.06, "market_cap": 4.0e9, "enterprise_value": 4.2e9,
    "total_revenue": 1.0e9, "total_debt": 5.0e8, "total_cash": 3.0e8,
    "book_value": 8.0, "price_to_book": 3.5, "price_to_sales": 4.0, "live": True,
}

# BEFORE: applying one PE formula to every company (mature path) -> the trailing
# relative ($3.80) vs analyst ($30) are irreconcilable.
_before = eqv.build_app_fair_value(
    "KTOS", 28.0, dcf_value=None,
    relative_value=round(eqv.get_sector_median_pe("Industrials") * 0.20, 2),
    analyst_target=30.0, analyst_count=12)  # no company_type -> mature
check("7.1 BEFORE (single PE path) -> anchors_irreconcilable",
      _before.blend_state == "anchors_irreconcilable", detail=_before.blend_state)

# AFTER: the routed valuation path classifies project_driven and produces an
# EV/EBITDA + analyst band (PE excluded).
with mock.patch.object(eqv, "_fetch_raw", return_value=dict(_KTOS_RAW)):
    _after = eqv.compute_app_fair_value("KTOS", 28.0)
check("7.2 AFTER classified project_driven", _after.company_type == "project_driven",
      detail=_after.company_type)
check("7.3 AFTER blend_state blended (no longer irreconcilable)",
      _after.blend_state == "blended", detail=_after.blend_state)
check("7.4 AFTER produces a usable band (mid > 0)", _after.fair_value_mid > 0,
      detail=str(_after.fair_value_mid))
check("7.5 AFTER blends EV/EBITDA + analyst",
      _names(_after.anchors) == {"ev_ebitda", "analyst"},
      detail=str(_names(_after.anchors)))
check("7.6 AFTER excludes trailing-PE relative anchor",
      "relative" not in _names(_after.anchors), detail=str(_after.anchors))
check("7.7 AFTER DCF note is the honest 'excluded for type' reason",
      "excluded" in (_after.dcf_note or "").lower(), detail=_after.dcf_note)
check("7.8 AFTER carries a backlog_note (free-source limit honesty)",
      bool(_after.backlog_note), detail=_after.backlog_note)


# ===========================================================================
# Summary
# ===========================================================================

print()
for f in _failures:
    print(f)
print()
print(f"Valuation Refactor v1 (router) — {PASS}/{PASS + FAIL} checks passed.")
if FAIL == 0:
    print("ALL PASSED.")
    sys.exit(0)
else:
    print(f"{FAIL} FAILED.")
    sys.exit(1)
