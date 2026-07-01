"""scripts/test_phase_8b_candidate_eligibility.py

Offline, deterministic test suite for lib/candidate_eligibility.py (Phase 8B
enabler). Builds REAL ``OpportunityCard`` / ``CandidateSignal`` instances imported
from the real modules (NOT mocks / SimpleNamespace) so an upstream field rename
breaks these tests instead of silently passing. No network, no LLM, no
lib.reliability — runs fully offline.

Run:
    python3 scripts/test_phase_8b_candidate_eligibility.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# REAL upstream dataclasses — a rename here is a compile-time break, by design.
from lib.opportunity_ranker import OpportunityCard, Blocker
from lib.signal_engine import CandidateSignal, FundamentalResult, TrackAResult

from lib.candidate_eligibility import (
    compute_eligibility,
    eligibility_by_horizon,
    EligibilityVerdict,
    # reason-code vocabulary
    LIQUIDITY_FUNNEL_VERIFIED,
    LIQUIDITY_UNVERIFIED_ALT,
    LIQUIDITY_UNKNOWN,
    THESIS_AVOID_CHASING,
    THESIS_RISK_OVERLAY_FAILED,
    THESIS_STATUS_UNKNOWN,
    EPS_DETERIORATING,
    EPS_UNKNOWN,
    VALUATION_PROHIBITED,
    VALUATION_ELEVATED,
    VALUATION_UNKNOWN,
    DISTRIBUTION_PROXY_AVOID,
    DISTRIBUTION_PROXY_EXTENDED,
    DISTRIBUTION_UNKNOWN,
    EVENT_EARNINGS_IMMINENT,
    EVENT_EARNINGS_WITHIN_WINDOW,
    EVENT_EARNINGS_PENDING_MID,
    EVENT_EARNINGS_DATE_UNKNOWN,
)


# ---------------------------------------------------------------------------
# Tiny assertion harness (counts assertions; loud on failure)
# ---------------------------------------------------------------------------

_PASS = 0
_FAIL = 0


def check(cond, msg):
    global _PASS, _FAIL
    if cond:
        _PASS += 1
    else:
        _FAIL += 1
        print(f"  FAIL: {msg}")


# ---------------------------------------------------------------------------
# Real-instance builders (every field is a real upstream field)
# ---------------------------------------------------------------------------

def healthy_card(**overrides):
    """A fully-populated, healthy, enriched card (passes every hard gate)."""
    kw = dict(
        ticker="AAPL",
        theme="ai_infra",
        theme_label_en="AI Infrastructure",
        candidate_type="FUNNEL",
        setup="Momentum Breakout",
        status_by_horizon={"short": "Actionable Now",
                           "mid": "Actionable Now",
                           "long": "Actionable Now"},
        blockers=[],
        days_to_earnings=30,   # well outside the window
        rs={},
        rs_degraded=False,
        rs_stale=False,
        enriched=True,
    )
    kw.update(overrides)
    return OpportunityCard(**kw)


def healthy_signal(**overrides):
    """A healthy CandidateSignal: improving EPS, cheap valuation, good entry."""
    kw = dict(
        ticker="AAPL",
        eps_revision_direction="improving",
        valuation_percentile=0.30,
        entry_quality_label="good",
    )
    kw.update(overrides)
    return CandidateSignal(**kw)


# ---------------------------------------------------------------------------
# Test 1 — EVENT HORIZON ASYMMETRY (canonical probe)
# RED if the gate applied earnings to long, or used the same code across horizons.
# ---------------------------------------------------------------------------

def test_event_horizon_asymmetry():
    card = healthy_card(days_to_earnings=2)
    sig = healthy_signal()
    v = eligibility_by_horizon(card, sig)

    check(EVENT_EARNINGS_IMMINENT in v["short"].conditions,
          "short with d2e=2 must carry EVENT_EARNINGS_IMMINENT")
    check(EVENT_EARNINGS_PENDING_MID in v["mid"].conditions,
          "mid with d2e=2 must carry EVENT_EARNINGS_PENDING_MID")
    # long must NOT be conditional on ANY earnings code (long earnings gate = pass).
    long_codes = set(v["long"].conditions) | set(v["long"].blockers) | set(v["long"].unknowns)
    earnings_codes = {EVENT_EARNINGS_IMMINENT, EVENT_EARNINGS_WITHIN_WINDOW,
                      EVENT_EARNINGS_PENDING_MID, EVENT_EARNINGS_DATE_UNKNOWN}
    check(not (long_codes & earnings_codes),
          "long must carry NO earnings code (a print is noise over 6-18 months)")
    # short status is conditional (imminent earnings is the only non-pass gate).
    check(v["short"].status == "conditional",
          "short with only an imminent-earnings caution must be 'conditional'")


# ---------------------------------------------------------------------------
# Test 2 — HARD-FAIL DOMINATES SCORE (precedence step 1)
# RED if high grades could rescue a deteriorating-EPS mid candidate.
# ---------------------------------------------------------------------------

def test_hard_fail_dominates():
    # Strong grades on the card; deteriorating EPS on the signal.
    card = healthy_card(short_grade="A", mid_grade="A", long_grade="A")
    sig = healthy_signal(eps_revision_direction="deteriorating")
    v = compute_eligibility(card, sig, horizon="mid")
    check(v.status == "ineligible", "deteriorating EPS at mid -> ineligible")
    check(EPS_DETERIORATING in v.blockers,
          "EPS_DETERIORATING must be in blockers at mid")
    # And short only down-rates to conditional (asymmetry), never ineligible here.
    vs = compute_eligibility(card, sig, horizon="short")
    check(vs.status == "conditional" and EPS_DETERIORATING in vs.conditions,
          "deteriorating EPS at short -> conditional, not ineligible")


# ---------------------------------------------------------------------------
# Test 3 — HARD-UNKNOWN vs SOFT-UNKNOWN ASYMMETRY (precedence steps 2 vs 4)
# ---------------------------------------------------------------------------

def test_hard_vs_soft_unknown():
    # (a) signal=None -> eps & valuation unknown (HARD) -> overall "unknown".
    card = healthy_card()
    va = compute_eligibility(card, None, horizon="mid")
    check(va.status == "unknown", "signal=None (hard unknowns) -> status 'unknown'")
    check(EPS_UNKNOWN in va.unknowns and VALUATION_UNKNOWN in va.unknowns,
          "hard unknowns must list EPS_UNKNOWN and VALUATION_UNKNOWN")

    # (b) candidate_type=None (liquidity SOFT-unknown) but every HARD gate passes
    #     -> "conditional", NOT "unknown".
    card_b = healthy_card(candidate_type=None)
    sig_b = healthy_signal()
    vb = compute_eligibility(card_b, sig_b, horizon="mid")
    check(vb.status == "conditional",
          "soft-only unknown (liquidity) must be 'conditional', not 'unknown'")
    check(LIQUIDITY_UNKNOWN in vb.unknowns,
          "LIQUIDITY_UNKNOWN must appear in unknowns")
    check(not vb.blockers, "soft-unknown path must have no blockers")


# ---------------------------------------------------------------------------
# Test 4 — SOFT GATES NEVER FAIL
# RED if a soft gate could push a candidate to ineligible.
# ---------------------------------------------------------------------------

def test_soft_gates_never_fail():
    # entry_quality_label="avoid" -> conditional, never ineligible on that account.
    card = healthy_card()
    sig = healthy_signal(entry_quality_label="avoid")
    v = compute_eligibility(card, sig, horizon="mid")
    check(DISTRIBUTION_PROXY_AVOID in v.conditions,
          "entry_quality 'avoid' -> DISTRIBUTION_PROXY_AVOID in conditions")
    check(DISTRIBUTION_PROXY_AVOID not in v.blockers,
          "DISTRIBUTION_PROXY_AVOID must never be a blocker")
    check(v.status == "conditional",
          "an 'avoid' distribution proxy alone -> conditional, not ineligible")

    # ALT_SIGNAL liquidity -> conditional, never a blocker.
    card2 = healthy_card(candidate_type="ALT_SIGNAL")
    sig2 = healthy_signal()
    v2 = compute_eligibility(card2, sig2, horizon="mid")
    check(LIQUIDITY_UNVERIFIED_ALT in v2.conditions,
          "ALT_SIGNAL -> LIQUIDITY_UNVERIFIED_ALT in conditions")
    check(LIQUIDITY_UNVERIFIED_ALT not in v2.blockers,
          "LIQUIDITY_UNVERIFIED_ALT must never be a blocker")
    check(v2.status == "conditional", "ALT_SIGNAL liquidity alone -> conditional")

    # entry_quality_label="extended" -> the extended proxy code.
    sig3 = healthy_signal(entry_quality_label="extended")
    v3 = compute_eligibility(healthy_card(), sig3, horizon="mid")
    check(DISTRIBUTION_PROXY_EXTENDED in v3.conditions,
          "entry_quality 'extended' -> DISTRIBUTION_PROXY_EXTENDED in conditions")


# ---------------------------------------------------------------------------
# Test 5 — VALUATION TWO-BAND x HORIZON (three percentile points)
# ---------------------------------------------------------------------------

def test_valuation_two_band():
    card = healthy_card()

    # 0.50 -> a REAL read below the elevated band -> pass (no valuation code) all H.
    v50 = eligibility_by_horizon(card, healthy_signal(valuation_percentile=0.50))
    for h in ("short", "mid", "long"):
        codes = set(v50[h].conditions) | set(v50[h].blockers) | set(v50[h].unknowns)
        check(VALUATION_ELEVATED not in codes and VALUATION_PROHIBITED not in codes
              and VALUATION_UNKNOWN not in codes,
              f"percentile 0.50 must carry no valuation code at {h}")
    check(v50["short"].status == "eligible" and v50["mid"].status == "eligible",
          "a clean 0.50-valuation card must be eligible short & mid")

    # 0.75 -> elevated band: short pass, mid/long conditional.
    v75 = eligibility_by_horizon(card, healthy_signal(valuation_percentile=0.75))
    check(VALUATION_ELEVATED not in v75["short"].conditions,
          "percentile 0.75 must NOT down-rate short valuation")
    check(VALUATION_ELEVATED in v75["mid"].conditions,
          "percentile 0.75 -> VALUATION_ELEVATED conditional at mid")
    check(VALUATION_ELEVATED in v75["long"].conditions,
          "percentile 0.75 -> VALUATION_ELEVATED conditional at long")

    # 0.90 -> prohibited band: short conditional, mid/long ineligible (blocker).
    v90 = eligibility_by_horizon(card, healthy_signal(valuation_percentile=0.90))
    check(VALUATION_PROHIBITED in v90["short"].conditions
          and v90["short"].status != "ineligible",
          "percentile 0.90 short -> VALUATION_PROHIBITED conditional (not ineligible)")
    check(VALUATION_PROHIBITED in v90["mid"].blockers and v90["mid"].status == "ineligible",
          "percentile 0.90 mid -> VALUATION_PROHIBITED blocker, ineligible")
    check(VALUATION_PROHIBITED in v90["long"].blockers and v90["long"].status == "ineligible",
          "percentile 0.90 long -> VALUATION_PROHIBITED blocker, ineligible")


# ---------------------------------------------------------------------------
# Test 5b — VALUATION PROVENANCE: a defaulted (fixture) 0.5 is UNKNOWN, not pass.
# Proves the auxiliary data_source flag distinguishes computed-0.5 from default-0.5.
# RED if the gate trusted the bare 0.5 value.
# ---------------------------------------------------------------------------

def test_valuation_provenance_unknown():
    card = healthy_card()
    # Real nested provenance: track_a.layer3_fundamental.data_source["valuation"]="fixture".
    fixture_fund = FundamentalResult(
        valuation_percentile=0.5,
        data_source={"eps": "fixture", "valuation": "fixture",
                     "margin": "fixture", "quality": "fixture"},
    )
    sig = CandidateSignal(
        ticker="AAPL",
        eps_revision_direction="improving",
        valuation_percentile=0.5,
        entry_quality_label="good",
        track_a=TrackAResult(layer3_fundamental=fixture_fund),
    )
    v = compute_eligibility(card, sig, horizon="mid")
    check(VALUATION_UNKNOWN in v.unknowns,
          "fixture-provenance valuation 0.5 -> VALUATION_UNKNOWN (not a pass)")
    check(v.status == "unknown",
          "a hard-unknown valuation -> overall status 'unknown'")

    # Control: the SAME 0.5 with NO provenance is treated as a real read -> pass.
    sig_real = healthy_signal(valuation_percentile=0.5)
    v_real = compute_eligibility(card, sig_real, horizon="mid")
    check(VALUATION_UNKNOWN not in v_real.unknowns,
          "a directly-constructed 0.5 (no provenance) is a real read, not unknown")
    check(v_real.status == "eligible",
          "a clean real-0.5 card is eligible at mid")


# ---------------------------------------------------------------------------
# Test 6 — AVOID CHASING -> ineligible for that horizon
# ---------------------------------------------------------------------------

def test_avoid_chasing_ineligible():
    card = healthy_card(status_by_horizon={"short": "Avoid Chasing"})
    sig = healthy_signal()
    v = compute_eligibility(card, sig, horizon="short")
    check(v.status == "ineligible", "Avoid Chasing at short -> ineligible")
    check(THESIS_AVOID_CHASING in v.blockers, "THESIS_AVOID_CHASING must be a blocker")


# ---------------------------------------------------------------------------
# Test 6b — risk_overlay_failed blocker code -> THESIS hard fail (defensive branch).
# ---------------------------------------------------------------------------

def test_risk_overlay_blocker_fail():
    # NOTE: opportunity_ranker does NOT currently attach a Blocker with code
    # "risk_overlay_failed" to a card (a risk-overlay failure surfaces as the
    # "Avoid Chasing" status). This test feeds a MANUALLY-constructed Blocker to
    # exercise the gate's forward-compatible/defensive branch — no production card
    # reaches it today.
    card = healthy_card(blockers=[Blocker("risk_overlay_failed", "critical")])
    sig = healthy_signal()
    v = compute_eligibility(card, sig, horizon="mid")
    check(v.status == "ineligible", "risk_overlay_failed blocker -> ineligible")
    check(THESIS_RISK_OVERLAY_FAILED in v.blockers,
          "THESIS_RISK_OVERLAY_FAILED must be a blocker")


# ---------------------------------------------------------------------------
# Test 7 — NEVER DEFAULT TO PASS (sparse card, signal=None, not enriched)
# ---------------------------------------------------------------------------

def test_never_default_to_pass():
    # Minimal card: only ticker. status_by_horizon empty, days_to_earnings None,
    # candidate_type defaults to "FUNNEL" (so liquidity passes), no enrichment.
    card = OpportunityCard(ticker="ZZZZ")
    v = compute_eligibility(card, None, horizon="short")
    check(v.status == "unknown", "sparse card + signal=None -> status 'unknown'")
    check(EPS_UNKNOWN in v.unknowns, "EPS_UNKNOWN required for signal=None")
    check(VALUATION_UNKNOWN in v.unknowns, "VALUATION_UNKNOWN required for signal=None")
    check(EVENT_EARNINGS_DATE_UNKNOWN in v.unknowns,
          "short with days_to_earnings None -> EVENT_EARNINGS_DATE_UNKNOWN")
    check(THESIS_STATUS_UNKNOWN in v.unknowns,
          "empty status_by_horizon -> THESIS_STATUS_UNKNOWN")
    check(v.status != "eligible", "a sparse unknown card must NEVER be eligible")


# ---------------------------------------------------------------------------
# Test 8 — CLEAN ELIGIBLE, then flip exactly one hard gate (each is required).
# ---------------------------------------------------------------------------

def test_clean_eligible_and_required_hard_gates():
    card = healthy_card()
    sig = healthy_signal()
    v = eligibility_by_horizon(card, sig)
    check(v["short"].status == "eligible", "clean card -> short eligible")
    check(v["mid"].status == "eligible", "clean card -> mid eligible")
    check(v["short"].blockers == () and v["mid"].blockers == (),
          "clean eligible verdicts have empty blockers")

    # Flip ONE hard gate at a time at mid; each must remove 'eligible'.
    # thesis
    f1 = compute_eligibility(
        healthy_card(status_by_horizon={"short": "Actionable Now",
                                        "mid": "Avoid Chasing", "long": "Actionable Now"}),
        sig, horizon="mid")
    check(f1.status != "eligible", "flipping thesis (Avoid Chasing) removes eligible")
    # eps
    f2 = compute_eligibility(card, healthy_signal(eps_revision_direction="deteriorating"),
                             horizon="mid")
    check(f2.status != "eligible", "flipping eps (deteriorating) removes eligible")
    # valuation
    f3 = compute_eligibility(card, healthy_signal(valuation_percentile=0.90), horizon="mid")
    check(f3.status != "eligible", "flipping valuation (prohibited) removes eligible")
    # event
    f4 = compute_eligibility(healthy_card(days_to_earnings=1), sig, horizon="mid")
    check(f4.status != "eligible", "flipping event (imminent earnings) removes eligible")


# ---------------------------------------------------------------------------
# Test 9 — data_quality
# ---------------------------------------------------------------------------

def test_data_quality():
    # rs_degraded -> "degraded".
    v_deg = compute_eligibility(healthy_card(rs_degraded=True), healthy_signal(), horizon="mid")
    check(v_deg.data_quality == "degraded", "rs_degraded=True -> data_quality 'degraded'")

    # not enriched -> "degraded".
    v_ne = compute_eligibility(healthy_card(enriched=False), healthy_signal(), horizon="mid")
    check(v_ne.data_quality == "degraded", "enriched=False -> data_quality 'degraded'")

    # all-clean -> "live".
    v_live = compute_eligibility(healthy_card(), healthy_signal(), horizon="mid")
    check(v_live.data_quality == "live", "all-clean card -> data_quality 'live'")

    # clean hard gates but a soft unknown -> "partial" (unknowns present, not degraded).
    v_part = compute_eligibility(healthy_card(candidate_type=None), healthy_signal(),
                                 horizon="mid")
    check(v_part.data_quality == "partial",
          "clean+enriched with a soft unknown -> data_quality 'partial'")


# ---------------------------------------------------------------------------
# Test 10 — DETERMINISM + sorted reason tuples + frozen
# ---------------------------------------------------------------------------

def test_determinism_and_sorting():
    card = healthy_card(candidate_type="ALT_SIGNAL", days_to_earnings=2)
    sig = healthy_signal(entry_quality_label="avoid", valuation_percentile=0.75)
    a = compute_eligibility(card, sig, horizon="mid", as_of="2026-06-26")
    b = compute_eligibility(card, sig, horizon="mid", as_of="2026-06-26")
    check(a == b, "identical inputs -> identical EligibilityVerdict")
    check(isinstance(a, EligibilityVerdict), "result is an EligibilityVerdict")
    check(list(a.conditions) == sorted(a.conditions), "conditions tuple is sorted")
    check(list(a.blockers) == sorted(a.blockers), "blockers tuple is sorted")
    check(list(a.unknowns) == sorted(a.unknowns), "unknowns tuple is sorted")
    # frozen: assignment must raise.
    try:
        a.status = "eligible"  # type: ignore[misc]
        check(False, "EligibilityVerdict must be frozen (assignment should raise)")
    except Exception:
        check(True, "EligibilityVerdict is frozen")
    # strategy_type passthrough.
    check(a.strategy_type == "Momentum Breakout", "strategy_type passes card.setup through")
    # horizon validation.
    try:
        compute_eligibility(card, sig, horizon="weekly")
        check(False, "an invalid horizon must raise ValueError")
    except ValueError:
        check(True, "invalid horizon raises ValueError")


# ---------------------------------------------------------------------------
# Test 11 — dict inputs tolerated (dataclass-or-dict)
# ---------------------------------------------------------------------------

def test_dict_inputs_tolerated():
    card = {
        "ticker": "MSFT",
        "candidate_type": "FUNNEL",
        "setup": "Mid-term Rotation",
        "status_by_horizon": {"mid": "Wait for Pullback"},
        "blockers": [{"code": "theme_lagging", "severity": "caution"}],
        "days_to_earnings": 20,
        "rs_degraded": False,
        "enriched": True,
    }
    sig = {
        "eps_revision_direction": "stable",
        "valuation_percentile": 0.40,
        "entry_quality_label": "fair",
    }
    v = compute_eligibility(card, sig, horizon="mid")
    check(v.status == "eligible", "dict card+signal, all gates clean -> eligible")
    check(v.strategy_type == "Mid-term Rotation", "dict setup passthrough works")
    check(v.ticker == "MSFT", "dict ticker read works")


# ---------------------------------------------------------------------------
# Test 5c — VALUATION FIREWALL LEAK GUARD (FIX 1)
# Live provenance ("valuation":"live") but an UNUSABLE forward_pe means
# _valuation_percentile defaulted to 0.5 — the gate must treat it as UNKNOWN, not
# accept the fabricated 0.5 as a real read.
# MUTATION: if the gate accepted live-provenance 0.5 with unusable forward_pe, this
# goes red (it would pass valuation and the card would be eligible).
# ---------------------------------------------------------------------------

def _signal_live_provenance_fpe(fpe):
    """Real CandidateSignal whose track_a.layer3_fundamental has valuation
    provenance "live" but the given (possibly unusable) forward_pe + a defaulted 0.5."""
    fund = FundamentalResult(
        valuation_percentile=0.5,
        data_source={"eps": "live", "valuation": "live",
                     "margin": "live", "quality": "live"},
        forward_pe=fpe,
    )
    return CandidateSignal(
        ticker="AAPL",
        eps_revision_direction="improving",
        valuation_percentile=0.5,
        entry_quality_label="good",
        track_a=TrackAResult(layer3_fundamental=fund),
    )


def test_valuation_live_provenance_unusable_fpe():
    card = healthy_card()
    # forward_pe in {0, negative, non-numeric string, bool} must all be UNUSABLE ->
    # VALUATION_UNKNOWN even though provenance says "live" and percentile is 0.5.
    for bad_fpe, label in [(0, "zero"), (-5, "negative"),
                           ("n/a", "non-numeric string"), (True, "bool")]:
        sig = _signal_live_provenance_fpe(bad_fpe)
        v = compute_eligibility(card, sig, horizon="mid")
        check(VALUATION_UNKNOWN in v.unknowns,
              f"live-provenance 0.5 with unusable forward_pe ({label}) -> VALUATION_UNKNOWN")
        check(v.status == "unknown",
              f"unusable forward_pe ({label}) -> hard-unknown valuation -> status 'unknown'")

    # Positive control: live provenance WITH a usable forward_pe + a cheap percentile
    # is a genuine real read -> the guard must NOT over-fire (eligible).
    good_fund = FundamentalResult(
        valuation_percentile=0.30,
        data_source={"eps": "live", "valuation": "live",
                     "margin": "live", "quality": "live"},
        forward_pe=25.0,
    )
    good_sig = CandidateSignal(
        ticker="AAPL", eps_revision_direction="improving",
        valuation_percentile=0.30, entry_quality_label="good",
        track_a=TrackAResult(layer3_fundamental=good_fund),
    )
    vg = compute_eligibility(card, good_sig, horizon="mid")
    check(VALUATION_UNKNOWN not in vg.unknowns,
          "usable forward_pe live read must NOT be flagged VALUATION_UNKNOWN")
    check(vg.status == "eligible",
          "a genuine live-provenance cheap valuation -> eligible (guard doesn't over-fire)")


# ---------------------------------------------------------------------------
# Test M1 — precedence step 1 over step 3 (hard-fail dominates a co-present conditional)
# MUTATION: if conditional were checked before hard-fail, status would be "conditional".
# ---------------------------------------------------------------------------

def test_hard_fail_over_conditional():
    card = healthy_card(status_by_horizon={"short": "Avoid Chasing"},
                        candidate_type="ALT_SIGNAL")  # THESIS fail + LIQUIDITY conditional
    sig = healthy_signal(entry_quality_label="avoid")  # DISTRIBUTION conditional
    v = compute_eligibility(card, sig, horizon="short")
    check(v.status == "ineligible",
          "a hard fail co-present with conditionals -> 'ineligible' (not 'conditional')")
    check(THESIS_AVOID_CHASING in v.blockers, "THESIS_AVOID_CHASING must be a blocker")
    # The conditionals are still recorded (complete reason lists from ALL gates).
    check(LIQUIDITY_UNVERIFIED_ALT in v.conditions,
          "co-present LIQUIDITY_UNVERIFIED_ALT still recorded in conditions")
    check(DISTRIBUTION_PROXY_AVOID in v.conditions,
          "co-present DISTRIBUTION_PROXY_AVOID still recorded in conditions")


# ---------------------------------------------------------------------------
# Test E2 — earnings imminent vs window band (short)
# MUTATION: collapsing the two earnings bands.
# ---------------------------------------------------------------------------

def test_earnings_window_band_short():
    card = healthy_card(days_to_earnings=5)  # inside window (2 < 5 <= 7), not imminent
    sig = healthy_signal()
    v = compute_eligibility(card, sig, horizon="short")
    check(EVENT_EARNINGS_WITHIN_WINDOW in v.conditions,
          "short d2e=5 -> EVENT_EARNINGS_WITHIN_WINDOW in conditions")
    check(EVENT_EARNINGS_IMMINENT not in v.conditions,
          "short d2e=5 must NOT be EVENT_EARNINGS_IMMINENT (band separation)")


# ---------------------------------------------------------------------------
# Test E4 — mid + earnings date unknown PASSES (not unknown)
# MUTATION: treating mid unknown-earnings as unknown instead of pass.
# ---------------------------------------------------------------------------

def test_mid_earnings_unknown_passes():
    card = healthy_card(days_to_earnings=None)
    sig = healthy_signal()
    v = compute_eligibility(card, sig, horizon="mid")
    event_codes = {EVENT_EARNINGS_IMMINENT, EVENT_EARNINGS_WITHIN_WINDOW,
                   EVENT_EARNINGS_PENDING_MID, EVENT_EARNINGS_DATE_UNKNOWN}
    all_codes = set(v.conditions) | set(v.blockers) | set(v.unknowns)
    check(not (all_codes & event_codes),
          "mid with days_to_earnings=None -> NO event code (event gate passes)")
    check(v.status == "eligible",
          "mid unknown-earnings with all other gates clean -> eligible")


# ---------------------------------------------------------------------------
# Test — MULTI-CONDITION COMPLETENESS (Task 4 gap)
# MUTATION: if conditions were populated only from the dominant gate, one code would
# be missing.
# ---------------------------------------------------------------------------

def test_multi_condition_completeness():
    card = healthy_card(candidate_type="ALT_SIGNAL")     # LIQUIDITY conditional
    sig = healthy_signal(entry_quality_label="avoid")    # DISTRIBUTION conditional
    v = compute_eligibility(card, sig, horizon="short")  # both soft; hard gates pass
    check(v.status == "conditional", "two soft conditionals -> status 'conditional'")
    check(LIQUIDITY_UNVERIFIED_ALT in v.conditions,
          "LIQUIDITY_UNVERIFIED_ALT must be present (both gates reported)")
    check(DISTRIBUTION_PROXY_AVOID in v.conditions,
          "DISTRIBUTION_PROXY_AVOID must be present (both gates reported)")
    check(len(v.conditions) >= 2, "conditions must carry BOTH codes, not just one")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main():
    tests = [
        test_event_horizon_asymmetry,
        test_hard_fail_dominates,
        test_hard_vs_soft_unknown,
        test_soft_gates_never_fail,
        test_valuation_two_band,
        test_valuation_provenance_unknown,
        test_valuation_live_provenance_unusable_fpe,
        test_avoid_chasing_ineligible,
        test_risk_overlay_blocker_fail,
        test_hard_fail_over_conditional,
        test_earnings_window_band_short,
        test_mid_earnings_unknown_passes,
        test_multi_condition_completeness,
        test_never_default_to_pass,
        test_clean_eligible_and_required_hard_gates,
        test_data_quality,
        test_determinism_and_sorting,
        test_dict_inputs_tolerated,
    ]
    for tfn in tests:
        print(f"running {tfn.__name__} ...")
        tfn()
    print(f"\nassertions passed: {_PASS}, failed: {_FAIL}")
    if _FAIL:
        print("RESULT: FAIL")
        sys.exit(1)
    print("RESULT: PASS")
    sys.exit(0)


if __name__ == "__main__":
    main()
