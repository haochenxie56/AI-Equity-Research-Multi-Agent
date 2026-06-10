#!/usr/bin/env python3
"""
scripts/test_reliability_anchor_peer_match.py

Anchor Intelligence v2.5 — multi-dimensional peer profile + honest
peer_match_quality degrade (FINAL v2 round). Pure / offline.

Covers (see docs/reliability_anchor_intel_v2.md "Round v2.5"):
  * A — numeric peer dims (margin_band / profitability_stage / revenue_cyclicality)
        computed deterministically from already-fetched info (visible PEER_DIM_CONFIG).
  * B — theme-basket tags as the single source of truth (basket_membership reads the
        SAME curated theme_baskets membership the rotation pipeline uses).
  * C — peer_profiles manual override layer (KTOS-class corner baskets miss).
  * D — assess_peer_match qualifies on numeric-compat AND a shared basket/override
        tag; >= MIN_QUALIFIED_PEERS -> high (medians drive EV anchors); fewer -> low +
        insufficient_comparable_peers (NO raw-GICS padding). The peer-multiple anchors
        (EV/S, EV/EBITDA) are EXCLUDED on low; relative_pe is NOT gated.
  * REAL PATH — driven through the actual Equity-page peer path
        (_assemble_fair_value(peers=...) + a compute_app_fair_value plumbing proof):
        SNOW -> cloud-software peers (not all software); KTOS -> low + relative
        de-emphasized -> analyst-only. Discriminating: a low qualified set MUST
        exclude the EV anchor (would FAIL if the v2.5 exclusion were reverted).
  * Determinism — fixed info/basket/override fixture -> fixed peer set + quality.
  * Card parity — peer_match_quality is a ValuationDiagnosis field, render-bound,
        i18n-covered, and EXCLUDED from the snapshot (bind-or-exclude discipline).

Usage:
    python3 -B scripts/test_reliability_anchor_peer_match.py
"""

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from unittest import mock  # noqa: E402

import lib.equity_valuation as eqv  # noqa: E402
import lib.valuation_router as vr  # noqa: E402
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


# ===========================================================================
# 1. A — numeric peer dimensions (deterministic, from already-fetched info)
# ===========================================================================
check("1.1 margin_band high/mid/low/negative boundaries",
      (vr.margin_band(0.25) == "high" and vr.margin_band(0.10) == "mid"
       and vr.margin_band(0.0) == "low" and vr.margin_band(-0.01) == "negative"
       and vr.margin_band(None) == "unknown"))
check("1.2 profitability_stage profitable/transitional/unprofitable",
      (vr.profitability_stage(0.06) == "profitable"
       and vr.profitability_stage(0.03) == "transitional"
       and vr.profitability_stage(-0.10) == "unprofitable"
       and vr.profitability_stage(None) == "unknown"))
check("1.3 revenue_cyclicality reuses the classifier cyclical signals",
      (vr.revenue_cyclicality("MU") == "cyclical"           # ticker override
       and vr.revenue_cyclicality("X", "Energy") == "cyclical"  # cyclical sector
       and vr.revenue_cyclicality("AAPL", "Technology") == "non_cyclical"))
_snow_info = {"ticker": "SNOW", "sector": "Technology",
              "industry": "Software—Infrastructure", "revenueGrowth": 0.30,
              "marketCap": 7.0e10, "operatingMargins": -0.10,
              "priceToSalesTrailing12Months": 15.0}
_dims = vr.numeric_dims(_snow_info, ticker="SNOW")
check("1.4 numeric_dims computes all five dims from one info dict",
      (_dims["growth_band"] == "high" and _dims["size_band"] == "large"
       and _dims["margin_band"] == "negative"
       and _dims["profitability_stage"] == "unprofitable"
       and _dims["revenue_cyclicality"] == "non_cyclical"), detail=str(_dims))
check("1.5 _dims_compatible: band equality on all five; unknown never matches",
      (vr._dims_compatible(_dims, dict(_dims))
       and not vr._dims_compatible(_dims, {**_dims, "size_band": "mid"})
       and not vr._dims_compatible(_dims, {**_dims, "growth_band": "unknown"})))

# ===========================================================================
# 2. B/C — basket tags (single source of truth) + peer_profiles override
# ===========================================================================
_mem = vr.basket_membership()
check("2.1 basket_membership unifies with rotation (MU in hbm_memory, SNOW in "
      "data_infrastructure)",
      ("hbm_memory" in _mem.get("MU", frozenset())
       and "data_infrastructure" in _mem.get("SNOW", frozenset())),
      detail=str(sorted(_mem.get("MU", []))))
check("2.2 KTOS is in NO theme basket (the corner the override covers)",
      _mem.get("KTOS", frozenset()) == frozenset(), detail=str(_mem.get("KTOS")))
check("2.3 peer_tags_for unions basket membership + override tags",
      vr.peer_tags_for("MU", membership=_mem) >= {"hbm_memory"}
      and vr.peer_tags_for("KTOS", membership=_mem) >= {"defense_tech"})
check("2.4 PEER_PROFILES seed is minimal + KTOS-only (data-driven decision #3)",
      set(vr.PEER_PROFILES) == {"KTOS"}, detail=str(sorted(vr.PEER_PROFILES)))
# Determinism of tags: injected membership/profiles -> fixed tag set.
_inj_mem = {"AAA": frozenset({"basket_x"}), "BBB": frozenset({"basket_x"})}
check("2.5 peer_tags_for is deterministic under injected membership",
      vr.peer_tags_for("AAA", membership=_inj_mem, profiles={}) == frozenset({"basket_x"}))

# ===========================================================================
# 3. D — assess_peer_match: qualification, threshold, NO padding, multiples
# ===========================================================================
def _cloud(tk, g, mc, om, ps):
    return {"ticker": tk, "sector": "Technology",
            "industry": "Software—Infrastructure", "revenueGrowth": g,
            "marketCap": mc, "operatingMargins": om,
            "priceToSalesTrailing12Months": ps}


# Hermetic membership: a shared "cloud" basket for SNOW + four comparable names; an
# off-band member; and a different-basket name. Override empty (basket-only test).
_HMEM = {
    "SNOW": frozenset({"cloud"}), "MDB": frozenset({"cloud"}),
    "DDOG": frozenset({"cloud"}), "NET": frozenset({"cloud"}),
    "CFLT": frozenset({"cloud"}), "ORCL": frozenset({"cloud"}),
    "CRM": frozenset({"other_basket"}),
}
_snow_t = _cloud("SNOW", 0.30, 7.0e10, -0.10, 15.0)
_cands = [
    _cloud("MDB", 0.28, 2.5e10, -0.08, 14.0),
    _cloud("DDOG", 0.27, 4.0e10, -0.05, 16.0),
    _cloud("NET", 0.30, 3.0e10, -0.09, 20.0),
    _cloud("CFLT", 0.26, 1.2e10, -0.12, 12.0),
    _cloud("ORCL", 0.06, 4.0e11, 0.30, 8.0),    # off-band (mature) -> not numeric-compat
    _cloud("CRM", 0.30, 2.6e11, -0.10, 7.0),    # numeric-compat BUT different basket
]
_m = vr.assess_peer_match(_snow_t, _cands, membership=_HMEM, profiles={})
_qtk = {p["ticker"] for p in _m.qualified_peers}
check("3.1 qualified set = numeric-compat ∩ shared-basket (cloud names only)",
      _qtk == {"MDB", "DDOG", "NET", "CFLT"}, detail=str(sorted(_qtk)))
check("3.2 off-band basket member (ORCL) excluded by numeric dims",
      "ORCL" not in _qtk)
check("3.3 numeric-compat name in a DIFFERENT basket (CRM) is NOT a tag peer",
      "CRM" not in _qtk)
check("3.4 >= MIN_QUALIFIED_PEERS -> peer_match_quality high, no reason",
      _m.peer_match_quality == "high" and _m.reason == "",
      detail=f"{_m.peer_match_quality}/{_m.matched_count}")
check("3.5 high -> median multiple over the QUALIFIED set (median of 12,14,16,20 = 15)",
      _m.multiples.get("priceToSalesTrailing12Months") == 15.0,
      detail=str(_m.multiples))
# Fewer than MIN_QUALIFIED_PEERS -> low + reason, NO sector padding, multiples None.
_m_low = vr.assess_peer_match(_snow_t, _cands[:2] + [_cands[4], _cands[5]],
                              membership=_HMEM, profiles={})
check("3.6 < MIN_QUALIFIED_PEERS -> low + insufficient_comparable_peers",
      _m_low.peer_match_quality == "low"
      and _m_low.reason == vr.REASON_INSUFFICIENT_PEERS,
      detail=f"{_m_low.peer_match_quality}/{_m_low.matched_count}")
check("3.7 low -> NO raw-GICS padding: multiples withheld (None), never sector median",
      _m_low.multiples.get("priceToSalesTrailing12Months") is None,
      detail=str(_m_low.multiples))
check("3.8 no candidates -> peer_match_quality NOT assessed (\"\")",
      vr.assess_peer_match(_snow_t, [], membership=_HMEM).peer_match_quality == "")
check("3.9 target excluded from its own qualified set by ticker",
      "SNOW" not in {p["ticker"] for p in
                     vr.assess_peer_match(_snow_t, _cands + [_snow_t],
                                          membership=_HMEM, profiles={}).qualified_peers})

# ===========================================================================
# 4. C — override layer creates a tag peer baskets miss
# ===========================================================================
# Two names in NO basket, both tagged defense_tech via override -> they peer to each
# other (numeric-compat). Demonstrates the override mechanism end-to-end.
_def_a = {"ticker": "KTOS", "sector": "Industrials",
          "industry": "Aerospace & Defense", "revenueGrowth": 0.10,
          "marketCap": 4.0e9, "operatingMargins": 0.06, "enterpriseToEbitda": 18.0}
_def_b = {"ticker": "AVAV", "sector": "Industrials",
          "industry": "Aerospace & Defense", "revenueGrowth": 0.12,
          "marketCap": 4.5e9, "operatingMargins": 0.05, "enterpriseToEbitda": 20.0}
_prof = {"KTOS": {"business_model": ("defense_tech",)},
         "AVAV": {"business_model": ("defense_tech",)}}
_m_ovr = vr.assess_peer_match(_def_a, [_def_b], membership={}, profiles=_prof,
                              multiple_fields=("enterpriseToEbitda",))
check("4.1 override tag makes two basket-less names tag peers",
      {p["ticker"] for p in _m_ovr.qualified_peers} == {"AVAV"},
      detail=str(_m_ovr.target_tags))
check("4.2 single override peer is still < MIN_QUALIFIED_PEERS -> honest low",
      _m_ovr.peer_match_quality == "low")

# ===========================================================================
# 5. REAL PATH — _assemble_fair_value(peers=...) (the Equity-page core)
# ===========================================================================
# Honest, real-basket fixtures: SNOW (in data_infrastructure) + its real cloud
# basket-mates; KTOS (in no basket, override-tagged) + traditional defense primes.
# These drive the LIVE basket_membership() + PEER_PROFILES (no injection) — the same
# code the page reaches.
_SNOW_RAW = dict(
    sector="Technology", industry="Software—Infrastructure",
    revenue_growth=0.30, operating_margin=-0.10, profit_margin=-0.12,
    market_cap=7.0e10, total_revenue=3.0e9, shares=3.3e8,
    fcf_ttm=None, ebitda=None, forward_eps=None, trailing_eps=None,
    analyst_median=180.0, analyst_mean=180.0, analyst_high=210.0,
    analyst_low=150.0, analyst_count=30, live=False,
)
# Real data_infrastructure basket-mates (high-growth, unprofitable, large-cap cloud).
_SNOW_PEERS = [
    _cloud("MDB", 0.28, 2.5e10, -0.08, 14.0),
    _cloud("DDOG", 0.27, 4.0e10, -0.05, 16.0),
    _cloud("NET", 0.30, 3.0e10, -0.09, 20.0),
    _cloud("CFLT", 0.26, 1.2e10, -0.12, 12.0),
    _cloud("ORCL", 0.06, 4.0e11, 0.30, 8.0),  # in basket but mature -> off-band
    # CRM: same SECTOR (Technology, "Software—Application") but NOT in SNOW's basket.
    {"ticker": "CRM", "sector": "Technology", "industry": "Software—Application",
     "revenueGrowth": 0.10, "marketCap": 2.6e11, "operatingMargins": 0.20,
     "priceToSalesTrailing12Months": 7.0},
]
_snow_fv = eqv._assemble_fair_value("SNOW", 175.0, None, dict(_SNOW_RAW),
                                    peers=_SNOW_PEERS)
check("5.1 SNOW classifies growth_unprofitable (EV/S + analyst menu)",
      _snow_fv.company_type == "growth_unprofitable", detail=_snow_fv.company_type)
check("5.2 SNOW -> peer_match_quality high (>= 4 real cloud peers qualified)",
      _snow_fv.peer_match_quality == "high", detail=_snow_fv.peer_match_quality)
check("5.3 SNOW EV/S anchor IS blended (cloud-software peers, not excluded)",
      any("EV/S" in m for m in _snow_fv.methods_used)
      and not any(a.get("flag") == "insufficient_comparable_peers"
                  for a in _snow_fv.excluded_anchors),
      detail=str(_snow_fv.methods_used))
check("5.4 SNOW NOT peered to all-software: no peer_match_unreliable caveat",
      eqv.CAVEAT_PEER_MATCH_UNRELIABLE not in _snow_fv.caveats)

# KTOS — project_driven, no defense-tech peers in the universe -> honest low.
_KTOS_RAW = dict(
    sector="Industrials", industry="Aerospace & Defense", fcf_ttm=None,
    ebitda=2.5e8, shares=1.3e8, total_revenue=1.0e9, growth_rate=0.08,
    revenue_growth=0.10, trailing_eps=0.20, forward_eps=None,
    operating_margin=0.06, profit_margin=0.04, market_cap=4.0e9,
    analyst_median=30.0, analyst_mean=30.0, analyst_high=34.0,
    analyst_low=26.0, analyst_count=12,
    priceToSalesTrailing12Months=4.0, enterpriseToEbitda=18.0, live=False,
)
_KTOS_PEERS = [
    {"ticker": "LMT", "sector": "Industrials", "industry": "Aerospace & Defense",
     "revenueGrowth": 0.05, "marketCap": 1.1e11, "operatingMargins": 0.13,
     "enterpriseToEbitda": 15.0},
    {"ticker": "NOC", "sector": "Industrials", "industry": "Aerospace & Defense",
     "revenueGrowth": 0.06, "marketCap": 7.0e10, "operatingMargins": 0.12,
     "enterpriseToEbitda": 16.0},
]
_ktos_fv = eqv._assemble_fair_value("KTOS", 28.0, None, dict(_KTOS_RAW),
                                    peers=_KTOS_PEERS)
check("5.5 KTOS -> peer_match_quality low + insufficient_comparable_peers reason",
      _ktos_fv.peer_match_quality == "low"
      and _ktos_fv.peer_match_reason == "insufficient_comparable_peers",
      detail=f"{_ktos_fv.peer_match_quality}/{_ktos_fv.peer_match_reason}")
# DISCRIMINATING: the EV/EBITDA peer anchor MUST be excluded (would be blended if the
# v2.5 exclusion were reverted) and shown with the peer flag.
_ktos_excl_flags = {a["name"]: a.get("flag") for a in _ktos_fv.excluded_anchors}
check("5.6 KTOS relative (peer-multiple) anchor EXCLUDED with the peer flag "
      "(discriminating — fails if the v2.5 exclusion is reverted)",
      _ktos_excl_flags.get("ev_ebitda") == "insufficient_comparable_peers",
      detail=str(_ktos_excl_flags))
check("5.7 KTOS EV/EBITDA is NOT in the blended methods (de-emphasized)",
      not any("EV/EBITDA" in m for m in _ktos_fv.methods_used),
      detail=str(_ktos_fv.methods_used))
check("5.8 KTOS degrades to analyst-only (reconcilable, its correct shape)",
      _ktos_fv.methods_used == ["analyst target"]
      and _ktos_fv.blend_state == "blended" and _ktos_fv.fair_value_mid == 30.0,
      detail=f"{_ktos_fv.methods_used}/{_ktos_fv.fair_value_mid}")
check("5.9 KTOS surfaces the peer_match_unreliable caveat",
      eqv.CAVEAT_PEER_MATCH_UNRELIABLE in _ktos_fv.caveats, detail=str(_ktos_fv.caveats))

# ===========================================================================
# 6. Network-free / byte-stable: peers=None -> quality "" -> v2.4 behavior
# ===========================================================================
_ktos_nopeers = eqv._assemble_fair_value("KTOS", 28.0, None, dict(_KTOS_RAW),
                                         peers=None)
check("6.1 peers=None -> peer_match NOT assessed (quality \"\")",
      _ktos_nopeers.peer_match_quality == "", detail=_ktos_nopeers.peer_match_quality)
check("6.2 peers=None -> EV/EBITDA NOT peer-excluded (blended via sector fallback, "
      "byte-stable vs v2.4)",
      any("EV/EBITDA" in m for m in _ktos_nopeers.methods_used)
      and eqv.CAVEAT_PEER_MATCH_UNRELIABLE not in _ktos_nopeers.caveats,
      detail=str(_ktos_nopeers.methods_used))

# Public entry plumbing proof: compute_app_fair_value forwards peers -> the worker ->
# the assembler (the REAL Equity-page call shape). First in-process KTOS compute, so
# the (ticker, price, dcf) cache entry is fresh.
with mock.patch.object(eqv, "_fetch_raw", return_value=dict(_KTOS_RAW)):
    _ktos_pub = eqv.compute_app_fair_value("KTOS", 28.0, peers=_KTOS_PEERS)
check("6.3 compute_app_fair_value forwards peers end-to-end (public entry low-degrade)",
      _ktos_pub.peer_match_quality == "low"
      and not any("EV/EBITDA" in m for m in _ktos_pub.methods_used),
      detail=f"{_ktos_pub.peer_match_quality}/{_ktos_pub.methods_used}")

# ===========================================================================
# 7. Determinism — fixed info/basket/override fixture -> fixed result
# ===========================================================================
_r1 = vr.assess_peer_match(_snow_t, _cands, membership=_HMEM, profiles={})
_r2 = vr.assess_peer_match(_snow_t, list(_cands), membership=dict(_HMEM), profiles={})
check("7.1 assess_peer_match is deterministic (same inputs -> same quality + set)",
      (_r1.peer_match_quality == _r2.peer_match_quality
       and {p["ticker"] for p in _r1.qualified_peers}
       == {p["ticker"] for p in _r2.qualified_peers}
       and _r1.multiples == _r2.multiples))
# Order-invariance: shuffling the candidate order must not change the qualified set.
_r3 = vr.assess_peer_match(_snow_t, list(reversed(_cands)), membership=_HMEM,
                           profiles={})
check("7.2 qualified set is order-invariant",
      {p["ticker"] for p in _r1.qualified_peers}
      == {p["ticker"] for p in _r3.qualified_peers})

# ===========================================================================
# 8. Token / config integrity
# ===========================================================================
check("8.1 router + equity_valuation share the insufficient-peers reason token",
      vr.REASON_INSUFFICIENT_PEERS == eqv.REASON_INSUFFICIENT_PEERS
      == "insufficient_comparable_peers")
check("8.2 peer_match_unreliable is a registered VALUATION_CAVEAT",
      eqv.CAVEAT_PEER_MATCH_UNRELIABLE in eqv.VALUATION_CAVEATS)
check("8.3 only EV/S + EV/EBITDA are peer-quality-gated (relative_pe NOT gated)",
      eqv.PEER_MULTIPLE_ANCHOR_KEYS == frozenset({"ev_s", "ev_ebitda"}),
      detail=str(eqv.PEER_MULTIPLE_ANCHOR_KEYS))
check("8.4 MIN_QUALIFIED_PEERS is the visible N (4)", vr.MIN_QUALIFIED_PEERS == 4)

# ===========================================================================
# 9. Card parity — peer_match_quality is bound on the card + EXCLUDED from snapshot
# ===========================================================================
_diag_low = vd.build_valuation_diagnosis(_ktos_fv)
check("9.1 ValuationDiagnosis SOURCES peer_match_quality + reason from AppFairValue",
      _diag_low.peer_match_quality == "low"
      and _diag_low.peer_match_reason == "insufficient_comparable_peers")
_diag_high = vd.build_valuation_diagnosis(_snow_fv)
check("9.2 high-quality fv -> diagnosis carries peer_match_quality high",
      _diag_high.peer_match_quality == "high")

import ui_utils as _ui  # noqa: E402

_src = open(os.path.join(_REPO_ROOT, "ui_utils.py"), encoding="utf-8").read()
check("9.3 render_valuation_diagnosis_card binds peer_match_quality",
      "peer_match_quality" in _src and "valdiag_peer_match_low" in _src
      and "valdiag_peer_match_high" in _src)
_zh, _en = _ui.TRANSLATIONS["zh"], _ui.TRANSLATIONS["en"]
_need = ["valdiag_peer_match", "valdiag_peer_match_high", "valdiag_peer_match_low",
         "valdiag_reason_insufficient_comparable_peers"]
check("9.4 every peer-match card token has a bilingual key",
      all(k in _zh for k in _need) and all(k in _en for k in _need),
      detail=str([k for k in _need if k not in _zh or k not in _en]))

import lib.opportunity_ranker as _orr  # noqa: E402

_snap = " ".join(_orr.ANCHOR_SNAPSHOT_KEYS).lower()
check("9.5 peer_match is render-time only — NOT in the snapshot anchor-block keys "
      "(bind-or-exclude satisfied by explicit exclusion)",
      "peer_match" not in _snap, detail=str(_orr.ANCHOR_SNAPSHOT_KEYS))


# ===========================================================================
print("\n".join(_failures))
total = PASS + FAIL
print(f"\nAnchor Intelligence v2.5 — multi-dim peer match — {PASS}/{total} checks passed.")
if FAIL:
    sys.exit(1)
print("ALL PASSED.")
