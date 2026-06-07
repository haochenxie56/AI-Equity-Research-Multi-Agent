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

import pandas as pd  # noqa: E402

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

# DELIBERATE ASSERTION CHANGE (review fix F1/D2): growth_unprofitable EXCLUDES
# DCF structurally — even when a positive DCF input is supplied (and a user DCF
# override must not bypass the menu). DCF output is unreliable for loss-makers.
_gub_dcf = eqv.build_app_fair_value(
    "GUD", 50.0, dcf_value=44.0, relative_value=80.0, analyst_target=45.0,
    analyst_count=6, company_type="growth_unprofitable", ev_s_value=40.0)
check("2.7 growth_unprofitable EXCLUDES DCF even when a positive DCF is available",
      "dcf" not in _names(_gub_dcf.anchors)
      and _excluded_flag(_gub_dcf, "dcf") == "excluded",
      detail=f"anchors={_names(_gub_dcf.anchors)} excl={_gub_dcf.excluded_anchors}")

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
# Section 8 — Token-boundary hint matching (review fix F4/I8)
# ===========================================================================

# Historical over-match #1: "Software—Infrastructure" must NOT be project_driven
# (the over-broad "infrastructure" hint was removed; phrases are token-matched).
_sw = vr.classify_company(
    ticker="SW", sector="Technology", industry="Software—Infrastructure",
    revenue_growth=0.40, profit_margin=-0.10, market_cap=2.0e10)
check("8.1 'Software—Infrastructure' is NOT project_driven",
      _sw.company_type != "project_driven", detail=_sw.company_type)

# Historical over-match #2: broad "Semiconductors" must NOT be cyclical
# (token-boundary: singular "memory"/"semiconductor" hint != plural token).
_semi = vr.classify_company(
    ticker="NVDA", sector="Technology", industry="Semiconductors",
    revenue_growth=0.60, profit_margin=0.50, market_cap=2.0e12)
check("8.2 'Semiconductors' (NVDA) is NOT cyclical",
      _semi.company_type != "cyclical", detail=_semi.company_type)
check("8.3 'Semiconductors' (NVDA) stays growth_profitable",
      _semi.company_type == "growth_profitable", detail=_semi.company_type)

# Intended positive matches preserved.
_lmt = vr.classify_company(
    ticker="LMT", sector="Industrials", industry="Aerospace & Defense",
    revenue_growth=0.05, profit_margin=0.10, market_cap=1.0e11)
check("8.4 'Aerospace & Defense' -> project_driven (LMT)",
      _lmt.company_type == "project_driven", detail=_lmt.company_type)
# FIXTURE HONESTY (X5c): yfinance reports MU's industry as the bare
# "Semiconductors" (same string as NVDA/AVGO/TXN) — the "memory" hint NEVER fires
# in production. MU must route to cyclical via the ticker-level override, tested
# here with the REAL live industry string (not a fabricated "Semiconductor Memory").
_mu_cls = vr.classify_company(
    ticker="MU", sector="Technology", industry="Semiconductors",
    revenue_growth=0.20, profit_margin=0.10, market_cap=1.0e11)
check("8.5 MU 'Semiconductors' (real yfinance string) -> cyclical via ticker override",
      _mu_cls.company_type == "cyclical", detail=_mu_cls.company_type)

# Matcher-level structural pins.
check("8.6 token matcher: 'semiconductor' does NOT match 'Semiconductors'",
      not vr.industry_has_hint("Semiconductors", ("semiconductor",)))
check("8.7 token matcher: 'gas' does NOT match inside 'Las Vegas Casinos'",
      not vr.industry_has_hint("Las Vegas Casinos & Resorts", ("gas",)))
check("8.8 token matcher: multi-word 'engineering & construction' matches",
      vr.industry_has_hint("Engineering & Construction Services",
                           ("engineering & construction",)))
check("8.9 token matcher: em-dash split ('oil' matches 'Oil—Gas Midstream')",
      vr.industry_has_hint("Oil—Gas Midstream", ("oil",)))


# ===========================================================================
# Section 9 — Cyclical ≤4y annual PB/PS history band (review fix F2/D1)
# ===========================================================================

# 9.1 percentile helper (linear interpolation, deterministic).
check("9.1 _percentile p50 of [10,20,30,40] == 25.0",
      eqv._percentile([10, 20, 30, 40], 50) == 25.0,
      detail=str(eqv._percentile([10, 20, 30, 40], 50)))

# 9.2 _compute_pb_ps_band: p50 × BVPS, honest ≤Ny annual label (NOT "5y").
_band_val, _band_basis = eqv._compute_pb_ps_band(
    {"book_value": 10.0}, pb_history=[1.0, 1.5, 2.0, 2.5], years=4)
check("9.2 PB band value = p50(1.75) × BVPS(10) = 17.5", _band_val == 17.5,
      detail=str(_band_val))
check("9.3 PB band basis is an annual approximation, never '5y'",
      "annual" in _band_basis and "p20/p50/p80" in _band_basis
      and "5y" not in _band_basis, detail=_band_basis)

# 9.4 build_pb_ps_history from synthetic annual statements + dated prices (PURE).
_dates = [pd.Timestamp("2025-12-31"), pd.Timestamp("2024-12-31"),
          pd.Timestamp("2023-12-31"), pd.Timestamp("2022-12-31")]
_bs = pd.DataFrame({
    _dates[0]: {"Stockholders Equity": 1.0e10, "Ordinary Shares Number": 1.0e9},
    _dates[1]: {"Stockholders Equity": 0.9e10, "Ordinary Shares Number": 1.0e9},
    _dates[2]: {"Stockholders Equity": 0.8e10, "Ordinary Shares Number": 1.0e9},
    _dates[3]: {"Stockholders Equity": 0.7e10, "Ordinary Shares Number": 1.0e9},
})
_is = pd.DataFrame({
    _dates[0]: {"Total Revenue": 2.0e10}, _dates[1]: {"Total Revenue": 1.8e10},
    _dates[2]: {"Total Revenue": 1.6e10}, _dates[3]: {"Total Revenue": 1.4e10},
})
_pidx = pd.date_range("2022-01-31", "2025-12-31", freq="ME")
_px = pd.DataFrame({"Close": [20.0 + i * 0.5 for i in range(len(_pidx))]}, index=_pidx)
_hist = eqv.build_pb_ps_history(_bs, _is, _px, ticker="CYC")
check("9.5 build_pb_ps_history yields 4 annual observations",
      _hist.get("years") == 4, detail=str(_hist.get("years")))
check("9.6 build_pb_ps_history pb + ps series populated",
      len(_hist.get("pb_history", [])) == 4 and len(_hist.get("ps_history", [])) == 4,
      detail=str(_hist))

# 9.7 MU full path: cyclical + injected history fetcher -> blended (band+analyst).
_MU_RAW = {
    "fcf_ttm": 2.0e9, "fcf_source": "", "ebitda": 8.0e9, "shares": 1.1e9,
    "growth_rate": 0.15, "trailing_eps": 5.0, "forward_eps": None,
    # FIXTURE HONESTY (X5c): real live yfinance string, not "Semiconductor Memory".
    # Cyclical routing comes from the ticker override on "MU".
    "sector": "Technology", "industry": "Semiconductors",
    "analyst_median": 110.0, "analyst_mean": 108.0, "analyst_count": 20,
    "revenue_growth": 0.20, "earnings_growth": 0.10, "profit_margin": 0.10,
    "operating_margin": 0.12, "market_cap": 1.1e11, "enterprise_value": 1.2e11,
    "total_revenue": 2.5e10, "total_debt": 1.0e10, "total_cash": 0.9e10,
    "book_value": 30.0, "price_to_book": 3.0, "price_to_sales": 4.0, "live": True,
}


def _mu_fetcher(_tk):
    return {"pb_history": [1.0, 1.4, 1.8, 2.2],
            "ps_history": [1.5, 2.0, 2.5, 3.0], "years": 4}


with mock.patch.object(eqv, "_fetch_raw", return_value=dict(_MU_RAW)):
    _mu = eqv.compute_app_fair_value("MU", 100.0, cyclical_history_fetcher=_mu_fetcher)
check("9.7 MU classified cyclical", _mu.company_type == "cyclical", detail=_mu.company_type)
check("9.8 MU blends PB/PS band + analyst (NOT analyst-only)",
      _names(_mu.anchors) == {"pb_ps", "analyst"}, detail=str(_names(_mu.anchors)))
check("9.9 MU blend_state blended + band value present",
      _mu.blend_state == "blended" and _mu.pb_ps_value is not None,
      detail=f"{_mu.blend_state}/{_mu.pb_ps_value}")
check("9.10 MU has NO cyclical_band_unavailable caveat",
      "cyclical_band_unavailable" not in (_mu.caveats or []), detail=str(_mu.caveats))
check("9.11 MU trailing-PE flagged cycle_distorted (excluded)",
      _excluded_flag(_mu, "relative") == "cycle_distorted", detail=str(_mu.excluded_anchors))

# 9.12 XOM full path: Energy sector cyclical + band -> blended.
_XOM_RAW = dict(_MU_RAW)
_XOM_RAW.update({"sector": "Energy", "industry": "Oil & Gas Integrated",
                 "analyst_median": 120.0, "book_value": 55.0})


def _xom_fetcher(_tk):
    return {"pb_history": [1.2, 1.5, 1.8, 2.0],
            "ps_history": [1.0, 1.3, 1.6, 1.9], "years": 4}


with mock.patch.object(eqv, "_fetch_raw", return_value=dict(_XOM_RAW)):
    _xom = eqv.compute_app_fair_value("XOM", 110.0, cyclical_history_fetcher=_xom_fetcher)
check("9.13 XOM classified cyclical", _xom.company_type == "cyclical", detail=_xom.company_type)
check("9.14 XOM blends PB/PS band + analyst", _names(_xom.anchors) == {"pb_ps", "analyst"},
      detail=str(_names(_xom.anchors)))
check("9.15 XOM blended band (mid > 0, not analyst-parroting)",
      _xom.blend_state == "blended" and _xom.fair_value_mid > 0
      and _xom.pb_ps_value != _xom.analyst_target,
      detail=f"{_xom.fair_value_mid}/{_xom.pb_ps_value}/{_xom.analyst_target}")

# 9.16 Degradation: cyclical with NO fetcher (cached/ranking path) -> analyst-only
# + the real caveat tokens. Network-free path takes this degrade.
with mock.patch.object(eqv, "_fetch_raw", return_value=dict(_MU_RAW)):
    _mu_deg = eqv.compute_app_fair_value("MU", 100.0)  # no fetcher (cyclical via override)
check("9.17 degraded cyclical -> analyst-only blend",
      _names(_mu_deg.anchors) == {"analyst"}, detail=str(_names(_mu_deg.anchors)))
check("9.18 degraded cyclical emits cyclical_band_unavailable caveat",
      "cyclical_band_unavailable" in (_mu_deg.caveats or []), detail=str(_mu_deg.caveats))
check("9.19 degraded single-anchor blend emits single_anchor_blend caveat",
      "single_anchor_blend" in (_mu_deg.caveats or []), detail=str(_mu_deg.caveats))
check("9.20 degraded cyclical still produces a usable band (mid > 0)",
      _mu_deg.blend_state == "blended" and _mu_deg.fair_value_mid > 0,
      detail=f"{_mu_deg.blend_state}/{_mu_deg.fair_value_mid}")

# 9.21 fewer than MIN_CYCLICAL_BAND_OBS annual obs -> degrade (band not trusted).
def _short_fetcher(_tk):
    return {"pb_history": [1.0, 1.5], "ps_history": [1.5, 2.0], "years": 2}


with mock.patch.object(eqv, "_fetch_raw", return_value=dict(_MU_RAW)):
    _mu_short = eqv.compute_app_fair_value("MU", 100.0,
                                           cyclical_history_fetcher=_short_fetcher)
check("9.22 < 3 annual obs -> band degraded + caveat",
      _mu_short.pb_ps_value is None
      and "cyclical_band_unavailable" in (_mu_short.caveats or []),
      detail=f"{_mu_short.pb_ps_value}/{_mu_short.caveats}")


# ===========================================================================
# Section 10 — X4 deterministic data-sanity guards (fix round 2)
# ===========================================================================

# Base mature_profitable raw (low growth, profitable, no sector/industry hint).
_SAN_RAW = {
    "fcf_ttm": 1.0e9, "fcf_source": "", "ebitda": 2.0e9, "shares": 1.0e8,
    "growth_rate": 0.05, "trailing_eps": 10.0, "forward_eps": None,
    "sector": "Technology", "industry": "Software—Application",
    "analyst_median": 300.0, "analyst_mean": 300.0, "analyst_count": 10,
    "revenue_growth": 0.05, "earnings_growth": 0.05, "profit_margin": 0.15,
    "operating_margin": 0.18, "market_cap": 4.0e10, "enterprise_value": 4.0e10,
    "total_revenue": 5.0e9, "total_debt": 0.0, "total_cash": 1.0e9,
    "book_value": 50.0, "price_to_book": 8.0, "price_to_sales": 8.0, "live": True,
}

# 10.1–10.3 Rule 1: forward_eps (100) > 3× trailing_eps (10) -> relative anchor
# EXCLUDED + caveat. Price (400) kept high enough that the garbage relative
# (28×100=2800) is within the price band, so ONLY rule 1 (not rule 2) excludes it.
_SAN_FE = dict(_SAN_RAW)
_SAN_FE.update({"forward_eps": 100.0, "trailing_eps": 10.0})
with mock.patch.object(eqv, "_fetch_raw", return_value=dict(_SAN_FE)):
    _fe = eqv.compute_app_fair_value("SANFE", 400.0)
check("10.1 implausible forward_eps -> relative excluded from blend",
      "relative" not in _names(_fe.anchors), detail=str(_names(_fe.anchors)))
check("10.2 implausible forward_eps -> relative flagged 'implausible'",
      _excluded_flag(_fe, "relative") == "implausible", detail=str(_fe.excluded_anchors))
check("10.3 implausible_forward_eps caveat emitted",
      "implausible_forward_eps" in (_fe.caveats or []), detail=str(_fe.caveats))
check("10.4 a bad number is NEVER replaced — relative_value still the raw garbage",
      _fe.relative_value == round(eqv.get_sector_median_pe("Technology") * 100.0, 2),
      detail=str(_fe.relative_value))

# 10.5–10.6 Rule 2 (high side): an anchor > 10× current price -> excluded + caveat.
_p2 = eqv.build_app_fair_value(
    "P2", 100.0, dcf_value=110.0, relative_value=105.0, analyst_target=9000.0,
    analyst_count=5, company_type="mature_profitable")
check("10.5 anchor > 10× price excluded (analyst 9000 vs price 100)",
      "analyst" not in _names(_p2.anchors)
      and _excluded_flag(_p2, "analyst") == "implausible_vs_price",
      detail=str(_p2.excluded_anchors))
check("10.6 anchor_implausible_vs_price caveat emitted",
      "anchor_implausible_vs_price" in (_p2.caveats or []), detail=str(_p2.caveats))
check("10.7 surviving sane anchors still blend (mid > 0)",
      _p2.blend_state == "blended" and _p2.fair_value_mid > 0,
      detail=f"{_p2.blend_state}/{_p2.fair_value_mid}")

# 10.8 Rule 2 is HIGH-SIDE ONLY by design: a LOW-side anchor ($3 relative vs $100
# price) is NOT dropped by price-sanity — it flows to the dispersion gate and the
# pair is marked anchors_irreconcilable (preserving the stop-the-bleed contract;
# dropping it here would silently undo the $3.23-vs-$112.50 audit guarantee).
_p3 = eqv.build_app_fair_value(
    "P3", 100.0, dcf_value=None, relative_value=3.0, analyst_target=112.0,
    analyst_count=5, company_type="mature_profitable")
check("10.8 low-side anchor NOT price-excluded -> dispersion gate -> irreconcilable",
      _excluded_flag(_p3, "relative") != "implausible_vs_price"
      and _p3.blend_state == "anchors_irreconcilable"
      and "anchor_implausible_vs_price" not in (_p3.caveats or []),
      detail=f"{_p3.blend_state}/{_p3.excluded_anchors}/{_p3.caveats}")

# 10.9–10.10 Rule 3: implausible revenue_growth (196%) treated as MISSING for
# classification — a name that WOULD be growth_profitable with the bad number
# falls back to mature_profitable, and the caveat is emitted.
_BADGROW_RAW = dict(_SAN_RAW)
_BADGROW_RAW.update({"revenue_growth": 1.963, "profit_margin": 0.15})
with mock.patch.object(eqv, "_fetch_raw", return_value=dict(_BADGROW_RAW)):
    _bg = eqv.compute_app_fair_value("ZZZ", 100.0)
check("10.9 implausible_growth_input caveat emitted",
      "implausible_growth_input" in (_bg.caveats or []), detail=str(_bg.caveats))
check("10.10 implausible growth -> classifier falls back (NOT growth_profitable)",
      _bg.company_type == "mature_profitable", detail=_bg.company_type)

# 10.11 Default path byte-compat: sane inputs trip NO sanity guard.
_clean = eqv.build_app_fair_value(
    "CLN", 100.0, dcf_value=100.0, relative_value=102.0, analyst_target=101.0,
    analyst_count=12, company_type="mature_profitable")
check("10.11 sane inputs -> no sanity caveats, all 3 anchors blend",
      not ({"implausible_forward_eps", "anchor_implausible_vs_price",
            "implausible_growth_input"} & set(_clean.caveats or []))
      and _names(_clean.anchors) == {"dcf", "relative", "analyst"},
      detail=f"{_clean.caveats}/{_names(_clean.anchors)}")


# ===========================================================================
# Section 11 — X1 live-path: build_pb_ps_history with a tz-AWARE price frame
# (the regression test that would have caught the root-cause tz bug)
# ===========================================================================

_fdates = [pd.Timestamp("2025-08-31"), pd.Timestamp("2024-08-31"),
           pd.Timestamp("2023-08-31"), pd.Timestamp("2022-08-31")]  # tz-NAIVE fiscal cols
_bs_tz = pd.DataFrame({
    d: {"Stockholders Equity": 1.0e10 - i * 1.0e9, "Ordinary Shares Number": 1.0e9}
    for i, d in enumerate(_fdates)})
_is_tz = pd.DataFrame({
    d: {"Total Revenue": 2.0e10 - i * 1.0e9} for i, d in enumerate(_fdates)})
# Multi-year, MONTHLY, tz-AWARE price index (both yfinance .history() and the
# local OHLCV cache produce tz-aware indexes — this is the exact shape that
# previously raised a swallowed TypeError and zeroed the band).
_pidx_tz = pd.date_range("2021-06-30", "2025-12-31", freq="ME", tz="America/New_York")
_px_tz = pd.DataFrame({"Close": [20.0 + i * 0.3 for i in range(len(_pidx_tz))]},
                      index=_pidx_tz)
_hist_tz = eqv.build_pb_ps_history(_bs_tz, _is_tz, _px_tz, ticker="TZAWARE")
check("11.1 tz-AWARE price frame still builds the band (>= 3 annual obs)",
      _hist_tz.get("years", 0) >= 3, detail=str(_hist_tz.get("years")))
check("11.2 tz-AWARE band is non-empty (pb + ps populated)",
      len(_hist_tz.get("pb_history", [])) >= 3 and len(_hist_tz.get("ps_history", [])) >= 3,
      detail=str(_hist_tz))
# Parity: tz-aware vs tz-naive copies of the SAME prices yield the SAME band.
_px_naive = _px_tz.copy()
_px_naive.index = _px_naive.index.tz_localize(None)
_hist_naive = eqv.build_pb_ps_history(_bs_tz, _is_tz, _px_naive, ticker="TZNAIVE")
check("11.3 tz-aware and tz-naive inputs produce identical pb_history",
      _hist_tz.get("pb_history") == _hist_naive.get("pb_history"),
      detail=f"{_hist_tz.get('pb_history')} vs {_hist_naive.get('pb_history')}")


# ===========================================================================
# Section 12 — X5 ticker-level cyclical overrides (taxonomy workaround)
# ===========================================================================

check("12.1 CYCLICAL_TICKER_OVERRIDES contains MU/WDC/STX",
      {"MU", "WDC", "STX"} <= set(vr.CYCLICAL_TICKER_OVERRIDES),
      detail=str(vr.CYCLICAL_TICKER_OVERRIDES))
# MU reports the real yfinance string 'Semiconductors'; WDC/STX report
# 'Computer Hardware' (X5a live dump, 2026-06) — NOT 'Semiconductors'. All three
# route to cyclical purely via CYCLICAL_TICKER_OVERRIDES, independent of the
# industry string, so the corrected fixture truth does not change the outcome.
for _tk, _ind in (("MU", "Semiconductors"), ("WDC", "Computer Hardware"),
                  ("STX", "Computer Hardware")):
    _ov = vr.classify_company(
        ticker=_tk, sector="Technology", industry=_ind,
        revenue_growth=0.20, profit_margin=0.10, market_cap=1.0e11)
    check(f"12.2 {_tk} '{_ind}' -> cyclical via override",
          _ov.company_type == "cyclical" and _ov.confidence == "clear",
          detail=f"{_ov.company_type}/{_ov.confidence}")
# The override BEATS a (possibly corrupt) high-growth signal — exactly the live MU
# case where revenue_growth read 196%.
_mu_hi = vr.classify_company(
    ticker="MU", sector="Technology", industry="Semiconductors",
    revenue_growth=0.60, profit_margin=0.40, market_cap=1.0e11)
check("12.3 MU override beats high-growth signal -> still cyclical",
      _mu_hi.company_type == "cyclical", detail=_mu_hi.company_type)
# Control: NVDA/AVGO/TXN report the SAME 'Semiconductors' string but are NOT in the
# override set -> must stay growth (broadening the hint was correctly rejected).
for _tk in ("NVDA", "AVGO", "TXN"):
    _ng = vr.classify_company(
        ticker=_tk, sector="Technology", industry="Semiconductors",
        revenue_growth=0.40, profit_margin=0.30, market_cap=1.0e12)
    check(f"12.4 {_tk} 'Semiconductors' NOT in override -> stays growth_profitable",
          _ng.company_type == "growth_profitable", detail=_ng.company_type)
# XOM-class oil/gas still routes via the industry string (override not needed).
_xom_cls = vr.classify_company(
    ticker="XOM", sector="Energy", industry="Oil & Gas Integrated",
    revenue_growth=0.05, profit_margin=0.12, market_cap=4.0e11)
check("12.5 XOM 'Oil & Gas Integrated' -> cyclical via industry/sector (no override)",
      _xom_cls.company_type == "cyclical", detail=_xom_cls.company_type)


# ===========================================================================
# Section 13 — Anchor Intelligence v2 (U2): structured analyst anchor +
#             pool-dispersion confidence gate
# ===========================================================================

# 13.1 Structured analyst pool carried on AppFairValue (median/mean/high/low/n/as_of);
# as_of stamped to computed_at. Median is the central estimate entering the blend.
_SP_RAW = {
    "fcf_ttm": None, "fcf_source": "", "ebitda": None, "shares": 1.0e9,
    "growth_rate": 0.05, "trailing_eps": 5.0, "forward_eps": None,
    "sector": "Technology", "industry": None,
    "analyst_median": 120.0, "analyst_mean": 122.0,
    "analyst_high": 140.0, "analyst_low": 105.0, "analyst_count": 12, "live": True,
}
with mock.patch.object(eqv, "_fetch_raw", return_value=dict(_SP_RAW)):
    _sp = eqv.compute_app_fair_value("SP1", 100.0)
check("13.1 AppFairValue carries structured analyst_pool dict",
      isinstance(_sp.analyst_pool, dict)
      and _sp.analyst_pool.get("median") == 120.0
      and _sp.analyst_pool.get("high") == 140.0
      and _sp.analyst_pool.get("low") == 105.0
      and _sp.analyst_pool.get("n") == 12,
      detail=str(_sp.analyst_pool))
check("13.2 analyst_pool.as_of stamped to computed_at",
      _sp.analyst_pool.get("as_of") == _sp.computed_at, detail=str(_sp.analyst_pool))
check("13.3 median is the analyst anchor entering the blend (robust to outliers)",
      _sp.analyst_target == 120.0, detail=str(_sp.analyst_target))

# 13.4 GATE FIRING — MU verified live pool (median 575, mean 739.48, high 1750,
# low 249, n 40 -> (1750-249)/575 = 2.61x > 1.0x). Median still blends; confidence
# is CAPPED at low and the caveat token is emitted. (Fixture honesty: real live MU.)
_MU_POOL = {"median": 575.0, "mean": 739.48, "high": 1750.0, "low": 249.0, "n": 40}
check("13.4 pool dispersion computed (MU 2.61x)",
      abs((eqv.analyst_pool_dispersion(_MU_POOL) or 0) - 2.6104) < 1e-3,
      detail=str(eqv.analyst_pool_dispersion(_MU_POOL)))
_mu_gate = eqv.build_app_fair_value("MU", 500.0, dcf_value=None, relative_value=None,
                                    analyst_target=575.0, analyst_count=40,
                                    analyst_pool=_MU_POOL)
check("13.5 dispersed pool -> confidence capped at low",
      _mu_gate.confidence == "low", detail=_mu_gate.confidence)
check("13.6 dispersed pool -> analyst_pool_dispersed caveat emitted",
      "analyst_pool_dispersed" in (_mu_gate.caveats or []), detail=str(_mu_gate.caveats))
check("13.7 dispersed pool -> median still entered the blend (mid > 0, not suppressed)",
      _mu_gate.blend_state == "blended" and _mu_gate.fair_value_mid > 0,
      detail=f"{_mu_gate.blend_state}/{_mu_gate.fair_value_mid}")

# 13.8 GATE NON-FIRING — a tight pool (median 100, high 110, low 95, n 10 -> 0.15x)
# does NOT cap confidence and emits no caveat.
_tight = {"median": 100.0, "mean": 101.0, "high": 110.0, "low": 95.0, "n": 10}
_tight_fv = eqv.build_app_fair_value("TGT", 100.0, dcf_value=95.0, relative_value=98.0,
                                     analyst_target=100.0, analyst_count=10,
                                     analyst_pool=_tight)
check("13.9 tight pool -> confidence NOT capped (high, 3 anchors)",
      _tight_fv.confidence == "high", detail=_tight_fv.confidence)
check("13.10 tight pool -> no analyst_pool_dispersed caveat",
      "analyst_pool_dispersed" not in (_tight_fv.caveats or []), detail=str(_tight_fv.caveats))

# 13.11 BOUNDARY — dispersion EXACTLY 1.0 is NOT dispersed (gate uses '>').
_edge = {"median": 100.0, "mean": 100.0, "high": 200.0, "low": 100.0, "n": 10}
check("13.11 boundary dispersion == 1.0 -> not dispersed",
      abs((eqv.analyst_pool_dispersion(_edge) or 0) - 1.0) < 1e-9,
      detail=str(eqv.analyst_pool_dispersion(_edge)))
_edge_fv = eqv.build_app_fair_value("EDG", 100.0, dcf_value=95.0, relative_value=98.0,
                                    analyst_target=100.0, analyst_count=10,
                                    analyst_pool=_edge)
check("13.12 boundary == 1.0 -> confidence not capped",
      _edge_fv.confidence == "high"
      and "analyst_pool_dispersed" not in (_edge_fv.caveats or []),
      detail=f"{_edge_fv.confidence}/{_edge_fv.caveats}")

# 13.13 GATE INERT — too few analysts (n < MIN_ANALYST_POOL_N) cannot trust the
# spread, so a wide pool with n=2 does NOT cap.
_fewn = {"median": 100.0, "mean": 100.0, "high": 300.0, "low": 50.0, "n": 2}
check("13.13 n < min -> dispersion None (gate inert)",
      eqv.analyst_pool_dispersion(_fewn) is None, detail=str(eqv.analyst_pool_dispersion(_fewn)))

# 13.14 GATE INERT — missing high/low (no pool extremes) cannot measure dispersion.
_nohl = {"median": 100.0, "mean": 100.0, "high": None, "low": None, "n": 20}
check("13.14 missing high/low -> dispersion None (gate inert)",
      eqv.analyst_pool_dispersion(_nohl) is None)


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
