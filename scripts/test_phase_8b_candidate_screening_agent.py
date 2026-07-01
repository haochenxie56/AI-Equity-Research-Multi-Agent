"""scripts/test_phase_8b_candidate_screening_agent.py

Offline, deterministic test suite for lib/agents/candidate_screening_agent.py
(Phase 8B — the SIXTH production agent, consuming the merged eligibility gate).

Real-path DoD:
  * REAL ``OpportunityCard`` / ``CandidateSignal`` / ``FundamentalSignals`` instances
    from the real modules (NOT mocks) — an upstream field rename breaks these tests.
  * The DETERMINISTIC layer (comparison table, frontrunner, no_clear_winner, slate
    skeleton, confidences, signal_basis) is tested WITHOUT any LLM by calling the
    deterministic helpers directly on real cards.
  * The LLM boundary is the ONLY thing stubbed: §CSA-8 drives the REAL
    ``run_llm_agent`` with ``agent_runner._call_llm`` patched to a canned valid
    AgentResult (success path) and to a raising stub (fail-closed fallback path).
  * Fully offline — no network, the module makes no network call itself.

Run:
    python3 scripts/test_phase_8b_candidate_screening_agent.py
"""

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# REAL upstream dataclasses — a rename here is a compile-time break, by design.
from lib.opportunity_ranker import OpportunityCard
from lib.signal_engine import CandidateSignal, FundamentalSignals

from lib.agents.candidate_screening_agent import (
    run_candidate_screening_agent,
    compute_screening,
    end_of_today_iso,
    CandidateProfile,
    CandidateSlate,
    _sort_key,
    _UNAVAILABLE,
    _KNOWN,
    _UNKNOWN,
    _BASIS_PRESENT,
    _BASIS_NO_WINNER,
    _BASIS_DEGRADED,
    _NT_THIN_GAP,
    _NT_CAPPED,
    _NT_EMPTY,
    _RS_GAP_DECISIVE_PCT,
    _MCAP_AMPLE,
)
from lib.candidate_eligibility import (
    EPS_UNKNOWN,
    VALUATION_UNKNOWN,
    DISTRIBUTION_UNKNOWN,
)
from lib.agent_framework.agent_output import AgentOutput
import lib.agent_framework.agent_runner as agent_runner_mod
import lib.reliability.run_context as run_context_mod


# ── Test runner ────────────────────────────────────────────────────────────

PASS = 0
FAIL = 0
ERRORS: list = []


def test(label: str, condition: bool, reason: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        ERRORS.append(f"{label}: {reason}")
        print(f"  [FAIL] {label}: {reason or 'condition was False'}")


# ── Real-instance builders ──────────────────────────────────────────────────

def _rs(short, mid, *, vol_ratio=1.5, above=True, composite=None) -> dict:
    return {
        "rs_short": short,
        "rs_mid": mid,
        "rs_composite": composite if composite is not None else round((short + mid) / 2, 4),
        "vol_ratio": vol_ratio,
        "above_sma20": above,
        "above_sma50": above,
        "ret_5d_vs_spy": 0.02, "ret_1m_vs_spy": 0.05,
        "ret_3m_vs_spy": 0.08, "ret_6m_vs_spy": 0.10,
        "ret_5d_vs_qqq": 0.01, "ret_1m_vs_qqq": 0.03,
    }


def _card(ticker, *, theme="ai_chips", rs_short=0.60, rs_mid=0.60,
          candidate_type="FUNNEL", status="Actionable Now", days_to_earnings=30,
          vol_ratio=1.5, above=True, rs_degraded=False, rs_stale=False,
          enriched=True) -> OpportunityCard:
    return OpportunityCard(
        ticker=ticker,
        theme=theme,
        theme_label_en="AI Chips",
        candidate_type=candidate_type,
        setup="Momentum Breakout",
        status_by_horizon={"short": status, "mid": status, "long": status},
        blockers=[],
        days_to_earnings=days_to_earnings,
        rs=_rs(rs_short, rs_mid, vol_ratio=vol_ratio, above=above),
        rs_degraded=rs_degraded,
        rs_stale=rs_stale,
        enriched=enriched,
    )


def _sig(ticker, *, eps="improving", val=0.30, entry="good",
         market_cap=None) -> CandidateSignal:
    kw = dict(
        ticker=ticker,
        eps_revision_direction=eps,
        valuation_percentile=val,
        entry_quality_label=entry,
    )
    if market_cap is not None:
        # Attach a v1 FundamentalSignals carrying market_cap. Provenance is set to
        # "live" with a usable forward P/E so the gate's valuation provenance still
        # certifies a REAL read (else the reachable fundamental would flip valuation
        # to UNKNOWN and the card would be rejected).
        kw["fundamental"] = FundamentalSignals(
            market_cap=market_cap,
            forward_pe=20.0,
            data_source={"valuation": "live", "eps": "live"},
        )
    return CandidateSignal(**kw)


# ── Patch harness (no pytest/mock dependency) ───────────────────────────────

class _patch:
    def __init__(self):
        self._saved = []

    def set(self, module, name, value):
        self._saved.append((module, name, getattr(module, name)))
        setattr(module, name, value)

    def restore(self):
        for module, name, old in reversed(self._saved):
            setattr(module, name, old)
        self._saved = []


class _FakeCtx:
    def __init__(self, run_id="TEST_CSA_20260701_000000_abcd"):
        self.run_id = run_id


def _fake_create_run_context(*a, **k):
    return _FakeCtx()


class _Capture:
    """Capturing run_llm_agent fake: records kwargs, echoes supporting_data."""

    def __init__(self):
        self.kwargs = None

    def __call__(self, **kw):
        self.kwargs = kw
        return AgentOutput(
            agent_id=kw.get("agent_id", "CandidateScreeningAgent"),
            timestamp="2026-07-01T00:00:00+00:00",
            horizon=kw.get("horizon", "cross"),
            judgment="Strongest candidate worth advancing to trade construction.",
            confidence=0.5,
            evidence_refs=[],
            supporting_data=kw.get("supporting_data", {}),
            requires_human_confirmation=kw.get("requires_human_confirmation", True),
            judgment_source=kw.get("judgment_source", "llm_proposed"),
            valid_until=kw.get("valid_until", ""),
        )


# ===========================================================================
# §CSA-1 — FRONTRUNNER BY RS-GAP (decisive)
#   Mutation caught: ranking by anything other than the RS composite gap.
# ===========================================================================
print("\n§CSA-1: decisive RS gap -> frontrunner is the higher-RS ticker")
c1 = [_card("AAA", rs_short=0.70, rs_mid=0.70),
      _card("BBB", rs_short=0.50, rs_mid=0.50)]
s1 = [_sig("AAA"), _sig("BBB")]
r1 = compute_screening(c1, s1, theme_key="ai_chips")
test("§CSA-1a: short frontrunner is AAA",
     r1["decisions"]["short"]["frontrunner"].ticker == "AAA",
     reason=str(r1["decisions"]["short"]["frontrunner"]))
test("§CSA-1b: short primary is AAA",
     r1["slates"]["short"].primary == "AAA",
     reason=str(r1["slates"]["short"].primary))
test("§CSA-1c: no_clear_winner False on decisive gap",
     r1["decisions"]["short"]["no_clear_winner"] is False)
test("§CSA-1d: signal_basis signal_present",
     r1["signal_basis"]["short"] == _BASIS_PRESENT,
     reason=r1["signal_basis"]["short"])
test("§CSA-1e: BBB is the secondary",
     r1["slates"]["short"].secondary == ("BBB",),
     reason=str(r1["slates"]["short"].secondary))
# Mutation probe: swap RS so BBB leads -> frontrunner must follow the RS gap.
r1m = compute_screening(
    [_card("AAA", rs_short=0.40, rs_mid=0.40), _card("BBB", rs_short=0.80, rs_mid=0.80)],
    s1, theme_key="ai_chips")
test("§CSA-1f (discriminating): frontrunner follows the RS gap, not the ticker",
     r1m["decisions"]["short"]["frontrunner"].ticker == "BBB",
     reason=str(r1m["decisions"]["short"]["frontrunner"]))


# ===========================================================================
# §CSA-2 — no_clear_winner ON THIN GAP
#   Mutation caught: ignoring _RS_GAP_DECISIVE_PCT (a primary is forced).
# ===========================================================================
print("\n§CSA-2: thin RS gap -> no_clear_winner, primary None")
c2 = [_card("AAA", rs_short=0.60, rs_mid=0.60),
      _card("BBB", rs_short=0.56, rs_mid=0.56)]  # gap 0.04 < 0.08
r2 = compute_screening(c2, [_sig("AAA"), _sig("BBB")], theme_key="ai_chips")
test("§CSA-2a: no_clear_winner True on thin gap",
     r2["decisions"]["short"]["no_clear_winner"] is True)
test("§CSA-2b: primary is None",
     r2["slates"]["short"].primary is None)
test("§CSA-2c: no_trade_reason is thin-gap",
     r2["slates"]["short"].no_trade_reason == _NT_THIN_GAP,
     reason=str(r2["slates"]["short"].no_trade_reason))
test("§CSA-2d: signal_basis no_clear_winner",
     r2["signal_basis"]["short"] == _BASIS_NO_WINNER,
     reason=r2["signal_basis"]["short"])
test("§CSA-2e: both eligible names fall to watch",
     set(r2["slates"]["short"].watch) == {"AAA", "BBB"},
     reason=str(r2["slates"]["short"].watch))


# ===========================================================================
# §CSA-3 — PENNY GUARD / quality_capped (frontrunner-key path (c))
#   A LONE eligible name that is quality_capped is NOT auto-advanced: cap dilutes
#   the credibility of its gap so the code refuses to force a primary. (A capped
#   frontrunner WITH a decisive lead over a runner-up is allowed-but-flagged per
#   the spec — path (c) only fires when the lead is not decisive, i.e. here where
#   the lone name has no contest.)
#   Mutation caught: cap not propagating -> a thin-float name is advanced as a
#   clean leader.
# ===========================================================================
print("\n§CSA-3: lone capped eligible -> refused (penny guard, path (c))")
# CAP is the ONLY eligible name (INE is ineligible), and it is quality_capped via
# a marginal market_cap (< _MCAP_AMPLE).
c3 = [_card("CAP", rs_short=0.99, rs_mid=0.99),
      _card("INE", rs_short=0.40, rs_mid=0.40, status="Avoid Chasing")]
s3 = [_sig("CAP", market_cap=_MCAP_AMPLE / 2.0), _sig("INE")]
r3 = compute_screening(c3, s3, theme_key="ai_chips")
prof3 = {p.ticker: p for p in r3["profiles"]}
test("§CSA-3a: CAP eligible (funnel liquidity, live valuation)",
     prof3["CAP"].short_status == "eligible", reason=prof3["CAP"].short_status)
test("§CSA-3b: CAP carries quality_capped True",
     prof3["CAP"].quality_capped is True)
test("§CSA-3c: CAP market_cap_tier marginal",
     prof3["CAP"].market_cap_tier == "marginal", reason=prof3["CAP"].market_cap_tier)
test("§CSA-3d: frontrunner is CAP and carries the capped flag",
     (r3["decisions"]["short"]["frontrunner"].ticker == "CAP"
      and r3["decisions"]["short"]["frontrunner"].quality_capped is True))
test("§CSA-3e: no_clear_winner True via the capped path (lone, no contest)",
     r3["decisions"]["short"]["no_clear_winner"] is True
     and r3["decisions"]["short"]["lead"] is None,
     reason=str(r3["decisions"]["short"]["lead"]))
test("§CSA-3f: no_trade_reason is the capped code",
     r3["slates"]["short"].no_trade_reason == _NT_CAPPED,
     reason=str(r3["slates"]["short"].no_trade_reason))
test("§CSA-3g: primary is None (capped name not advanced)",
     r3["slates"]["short"].primary is None)
# Mutation probe: with an AMPLE cap the SAME lone eligible name becomes primary.
r3m = compute_screening(
    [_card("CAP", rs_short=0.99, rs_mid=0.99),
     _card("INE", rs_short=0.40, rs_mid=0.40, status="Avoid Chasing")],
    [_sig("CAP"), _sig("INE")], theme_key="ai_chips")
prof3_big = {p.ticker: p for p in r3m["profiles"]}
test("§CSA-3h (discriminating): ample cap -> CAP not capped -> becomes primary",
     prof3_big["CAP"].quality_capped is False
     and r3m["slates"]["short"].primary == "CAP",
     reason=f"capped={prof3_big['CAP'].quality_capped} "
            f"primary={r3m['slates']['short'].primary}")


# ===========================================================================
# §CSA-4 — SHORT vs MID DIFFERENT FRONTRUNNER
#   Mutation caught: collapsing horizons (one primary reused for both).
# ===========================================================================
print("\n§CSA-4: short RS leader differs from mid RS leader")
c4 = [_card("XSH", rs_short=0.90, rs_mid=0.50),   # short leader
      _card("YMD", rs_short=0.55, rs_mid=0.92)]    # mid leader
r4 = compute_screening(c4, [_sig("XSH"), _sig("YMD")], theme_key="ai_chips")
test("§CSA-4a: short primary is XSH",
     r4["slates"]["short"].primary == "XSH", reason=str(r4["slates"]["short"].primary))
test("§CSA-4b: mid primary is YMD",
     r4["slates"]["mid"].primary == "YMD", reason=str(r4["slates"]["mid"].primary))
test("§CSA-4c: short and mid primaries differ",
     r4["slates"]["short"].primary != r4["slates"]["mid"].primary)


# ===========================================================================
# §CSA-5 — ELIGIBILITY ROUTING INTO THE SLATE
#   ineligible -> rejected (reasons); conditional -> watch (never primary);
#   eligible -> may be primary.
#   Mutation caught: routing that lets a conditional become primary.
# ===========================================================================
print("\n§CSA-5: gate states route correctly into the slate")
c5 = [
    _card("ELG", rs_short=0.80, rs_mid=0.80),                       # eligible
    _card("CON", rs_short=0.95, rs_mid=0.95, candidate_type="ALT_SIGNAL"),  # conditional
    _card("INE", rs_short=0.99, rs_mid=0.99, status="Avoid Chasing"),       # ineligible
]
r5 = compute_screening(c5, [_sig("ELG"), _sig("CON"), _sig("INE")],
                       theme_key="ai_chips")
sl5 = r5["slates"]["short"]
test("§CSA-5a: eligible ELG is the primary despite lower RS than CON/INE",
     sl5.primary == "ELG", reason=str(sl5.primary))
test("§CSA-5b: conditional CON is in watch, never primary/secondary",
     "CON" in sl5.watch and "CON" != sl5.primary and "CON" not in sl5.secondary,
     reason=str(sl5.watch))
rej_tickers = {e["ticker"] for e in sl5.rejected}
test("§CSA-5c: ineligible INE is rejected",
     "INE" in rej_tickers, reason=str(rej_tickers))
ine_entry = next((e for e in sl5.rejected if e["ticker"] == "INE"), {})
test("§CSA-5d: rejected INE carries gate reason codes",
     bool(ine_entry.get("reasons")), reason=str(ine_entry))
test("§CSA-5e: CON never in rejected (it is watch-only)",
     "CON" not in rej_tickers, reason=str(rej_tickers))


# ===========================================================================
# §CSA-6 — UNAVAILABLE DIMENSIONS EXCLUDED FROM THE KEY
#   Mutation caught: an unavailable dimension silently counted as a real value.
# ===========================================================================
print("\n§CSA-6: down-scoped dimensions are 'unavailable' and excluded from the key")
c6 = [_card("AAA", rs_short=0.75, rs_mid=0.75),
      _card("BBB", rs_short=0.50, rs_mid=0.50)]
r6 = compute_screening(c6, [_sig("AAA"), _sig("BBB")], theme_key="ai_chips")
prof6 = {p.ticker: p for p in r6["profiles"]}
test("§CSA-6a: short_crowding is unavailable for all",
     all(p.short_crowding_state == _UNAVAILABLE for p in r6["profiles"]))
test("§CSA-6b: options_structure is unavailable for all",
     all(p.options_structure_state == _UNAVAILABLE for p in r6["profiles"]))
# The sort key must reference NONE of the unavailable dims -> the frontrunner is
# still purely RS-driven and a slate is still produced.
test("§CSA-6c: a slate is still produced with the RS frontrunner",
     r6["slates"]["short"].primary == "AAA", reason=str(r6["slates"]["short"].primary))
comp6 = r6  # comparison rows carry the availability markers into evidence
from lib.agents.candidate_screening_agent import _comparison_payload
rows6 = _comparison_payload(comp6)["comparison_table"]
test("§CSA-6d: comparison table lists the two unavailable dimensions",
     _comparison_payload(comp6)["unavailable_dimensions"]
     == ["short_crowding", "options_structure"])
test("§CSA-6e: every comparison row marks short_crowding unavailable",
     all(row["short_crowding_state"] == _UNAVAILABLE for row in rows6))


# ===========================================================================
# §CSA-7 — DEGRADED COVERAGE
#   Mutation caught: degraded RS treated as usable.
# ===========================================================================
print("\n§CSA-7: all cards rs_degraded -> degraded_insufficient, confidences ~0")
c7 = [_card("AAA", rs_short=0.80, rs_mid=0.80, rs_degraded=True),
      _card("BBB", rs_short=0.50, rs_mid=0.50, rs_degraded=True)]
r7 = compute_screening(c7, [_sig("AAA"), _sig("BBB")], theme_key="ai_chips")
test("§CSA-7a: short signal_basis degraded_insufficient",
     r7["signal_basis"]["short"] == _BASIS_DEGRADED, reason=r7["signal_basis"]["short"])
test("§CSA-7b: mid signal_basis degraded_insufficient",
     r7["signal_basis"]["mid"] == _BASIS_DEGRADED, reason=r7["signal_basis"]["mid"])
test("§CSA-7c: short_confidence is 0.0", r7["confidence"]["short"] == 0.0,
     reason=str(r7["confidence"]["short"]))
test("§CSA-7d: mid_confidence is 0.0", r7["confidence"]["mid"] == 0.0,
     reason=str(r7["confidence"]["mid"]))
test("§CSA-7e: short coverage is 0.0 (no usable RS)",
     r7["confidence"]["short_coverage"] == 0.0,
     reason=str(r7["confidence"]["short_coverage"]))
# Mutation probe: the SAME cards with live RS -> coverage 1.0, not degraded.
r7m = compute_screening(
    [_card("AAA", rs_short=0.80, rs_mid=0.80), _card("BBB", rs_short=0.50, rs_mid=0.50)],
    [_sig("AAA"), _sig("BBB")], theme_key="ai_chips")
test("§CSA-7f (discriminating): live RS -> coverage 1.0 and not degraded",
     r7m["confidence"]["short_coverage"] == 1.0
     and r7m["signal_basis"]["short"] != _BASIS_DEGRADED,
     reason=str(r7m["confidence"]["short_coverage"]))


# ===========================================================================
# §CSA-8 — NUMERIC FIREWALL / OUTPUT SHAPE (real run_llm_agent, stubbed LLM)
#   and the fail-closed FALLBACK path.
# ===========================================================================
print("\n§CSA-8: real run_llm_agent with a stubbed LLM boundary")


def _stub_call_llm_ok(system, user, max_tokens):
    """Canned VALID AgentResult citing a real evidence_id parsed from the prompt.
    Emits NO digit / % / $ / metric token in any finding text (numeric firewall)."""
    # Exclude '<' so the REQUIRED-OUTPUT-FORMAT template placeholders
    # ("<id from packet>" / "<use the run_id...>") are never matched — only the
    # REAL content-addressed ids from the AVAILABLE EVIDENCE packet.
    ids = re.findall(r'"evidence_id":\s*"([^"<]+)"', user)
    rids = re.findall(r'"run_id":\s*"([^"<]+)"', user)
    ev = ids[0] if ids else "MISSING_EVIDENCE"
    run_id = rids[0] if rids else "MISSING_RUN_ID"
    obj = {
        "agent_name": "CandidateScreeningAgent",
        "run_id": run_id,
        "findings": [
            {"text": "The leading candidate is worth advancing to short-term trade "
                     "construction pending money-flow confirmation.",
             "evidence": [{"evidence_id": ev, "excerpt": "screening"}]},
            {"text": "A different name is the better mid-horizon expression and is "
                     "worth advancing pending technical entry checks.",
             "evidence": [{"evidence_id": ev, "excerpt": "slate"}]},
            {"text": "Long-horizon conviction defers to StockResearch and "
                     "ValuationDebate.",
             "evidence": [{"evidence_id": ev, "excerpt": "confidence"}]},
        ],
        "confidence": {"level": "medium", "rationale": "clear separation",
                        "score": 0.5},
    }
    return json.dumps(obj)


def _stub_call_llm_raise(system, user, max_tokens):
    raise RuntimeError("stubbed LLM boundary failure")


c8 = [_card("AAA", rs_short=0.80, rs_mid=0.80),
      _card("BBB", rs_short=0.55, rs_mid=0.55)]
s8 = [_sig("AAA"), _sig("BBB")]

# -- Success path: real run_llm_agent, only _call_llm stubbed. ---------------
p8 = _patch()
try:
    p8.set(agent_runner_mod, "_call_llm", _stub_call_llm_ok)
    p8.set(run_context_mod, "create_run_context", _fake_create_run_context)
    out8 = run_candidate_screening_agent(
        c8, theme_key="ai_chips", signals=s8,
        theme_context={"stage": "leading", "stage_confirmed": True,
                       "label_en": "AI Chips"})
finally:
    p8.restore()

test("§CSA-8a: returns an AgentOutput", isinstance(out8, AgentOutput))
test("§CSA-8b: judgment has no digit", not any(ch.isdigit() for ch in out8.judgment),
     reason=out8.judgment)
test("§CSA-8c: judgment has no % or $",
     "%" not in out8.judgment and "$" not in out8.judgment, reason=out8.judgment)
test("§CSA-8d: evidence_refs non-empty", len(out8.evidence_refs) > 0)
test("§CSA-8e: valid_until == end-of-today", out8.valid_until == end_of_today_iso(),
     reason=out8.valid_until)
test("§CSA-8f: supporting_data carries the short slate skeleton",
     isinstance(out8.supporting_data.get("short_slate"), dict)
     and out8.supporting_data["short_slate"].get("primary") == "AAA",
     reason=str(out8.supporting_data.get("short_slate")))
test("§CSA-8g: supporting_data carries the comparison table",
     isinstance(out8.supporting_data.get("comparison_table"), list)
     and len(out8.supporting_data["comparison_table"]) == 2)
test("§CSA-8h: review-only (human confirmation required, no execution field)",
     out8.requires_human_confirmation is True
     and not getattr(out8, "approved_for_execution", False))
test("§CSA-8i: judgment_source llm_proposed on the success path",
     out8.judgment_source == "llm_proposed", reason=out8.judgment_source)
# OPTIONAL (non-blocking) — the judgment is a single COMPLETE sentence (the runner
# extracts the first complete sentence), not a mid-sentence truncation.
test("§CSA-8i2: judgment is a single complete sentence",
     out8.judgment.endswith(".") and out8.judgment.count(".") == 1
     and len(out8.judgment) > 0, reason=repr(out8.judgment))

# -- Fallback path: _call_llm raises -> fail-closed rule-based AgentOutput. ---
p8b = _patch()
try:
    p8b.set(agent_runner_mod, "_call_llm", _stub_call_llm_raise)
    p8b.set(run_context_mod, "create_run_context", _fake_create_run_context)
    out8b = run_candidate_screening_agent(c8, theme_key="ai_chips", signals=s8)
finally:
    p8b.restore()

test("§CSA-8j: fallback still returns an AgentOutput (no exception escaped)",
     isinstance(out8b, AgentOutput))
test("§CSA-8k: fallback judgment_source is rule_based",
     out8b.judgment_source == "rule_based", reason=out8b.judgment_source)
test("§CSA-8l: fallback evidence_refs non-empty (synthetic runner_error ref)",
     len(out8b.evidence_refs) > 0)
test("§CSA-8m: fallback supporting_data retains theme_key",
     out8b.supporting_data.get("theme_key") == "ai_chips")


# ===========================================================================
# §CSA-9 — PER-THEME IDENTITY (ticker == theme_key; two themes independent)
#   Mutation caught: a global (non-per-theme) output.
# ===========================================================================
print("\n§CSA-9: one AgentOutput per theme, keyed by theme_key")
cards9 = [
    _card("AAA", theme="ai_chips", rs_short=0.80, rs_mid=0.80),
    _card("BBB", theme="ai_chips", rs_short=0.50, rs_mid=0.50),
    _card("MMM", theme="hbm_memory", rs_short=0.85, rs_mid=0.85),
    _card("NNN", theme="hbm_memory", rs_short=0.55, rs_mid=0.55),
]
sigs9 = [_sig("AAA"), _sig("BBB"), _sig("MMM"), _sig("NNN")]

cap_a = _Capture()
cap_b = _Capture()
p9 = _patch()
try:
    p9.set(run_context_mod, "create_run_context", _fake_create_run_context)
    p9.set(agent_runner_mod, "run_llm_agent", cap_a)
    out9a = run_candidate_screening_agent(cards9, theme_key="ai_chips", signals=sigs9)
    p9.set(agent_runner_mod, "run_llm_agent", cap_b)
    out9b = run_candidate_screening_agent(cards9, theme_key="hbm_memory", signals=sigs9)
finally:
    p9.restore()

test("§CSA-9a: ai_chips output ticker kwarg == theme_key",
     cap_a.kwargs["ticker"] == "ai_chips", reason=str(cap_a.kwargs.get("ticker")))
test("§CSA-9b: hbm_memory output ticker kwarg == theme_key",
     cap_b.kwargs["ticker"] == "hbm_memory", reason=str(cap_b.kwargs.get("ticker")))
test("§CSA-9c: ai_chips supporting_data is theme-scoped",
     out9a.supporting_data["theme_key"] == "ai_chips"
     and out9a.supporting_data["short_slate"]["primary"] == "AAA",
     reason=str(out9a.supporting_data.get("short_slate")))
test("§CSA-9d: hbm_memory supporting_data is a DIFFERENT, independent slate",
     out9b.supporting_data["theme_key"] == "hbm_memory"
     and out9b.supporting_data["short_slate"]["primary"] == "MMM",
     reason=str(out9b.supporting_data.get("short_slate")))
test("§CSA-9e: the two themes' slates are not the same object/content",
     out9a.supporting_data["short_slate"] != out9b.supporting_data["short_slate"])


# ===========================================================================
# §CSA-10 — DETERMINISM (identical inputs -> identical deterministic layer)
# ===========================================================================
print("\n§CSA-10: deterministic layer is byte-stable across runs")
cA = [_card("AAA", rs_short=0.80, rs_mid=0.70),
      _card("BBB", rs_short=0.55, rs_mid=0.90),
      _card("CON", rs_short=0.95, rs_mid=0.95, candidate_type="ALT_SIGNAL")]
sA = [_sig("AAA"), _sig("BBB"), _sig("CON")]
ra = compute_screening(cA, sA, theme_key="ai_chips")
rb = compute_screening([_card("AAA", rs_short=0.80, rs_mid=0.70),
                        _card("BBB", rs_short=0.55, rs_mid=0.90),
                        _card("CON", rs_short=0.95, rs_mid=0.95,
                              candidate_type="ALT_SIGNAL")],
                       [_sig("AAA"), _sig("BBB"), _sig("CON")], theme_key="ai_chips")
test("§CSA-10a: short slate identical across runs",
     ra["slates"]["short"].to_dict() == rb["slates"]["short"].to_dict())
test("§CSA-10b: mid slate identical across runs",
     ra["slates"]["mid"].to_dict() == rb["slates"]["mid"].to_dict())
test("§CSA-10c: profiles identical across runs",
     [p.to_dict() for p in ra["profiles"]] == [p.to_dict() for p in rb["profiles"]])
test("§CSA-10d: confidence identical across runs",
     ra["confidence"] == rb["confidence"])
test("§CSA-10e: frozen dataclasses (CandidateProfile / CandidateSlate)",
     isinstance(ra["profiles"][0], CandidateProfile)
     and isinstance(ra["slates"]["short"], CandidateSlate))
# The long horizon is not_applicable with zero confidence.
test("§CSA-10f: long horizon is not_applicable, long_confidence 0.0",
     ra["confidence"]["long"] == 0.0 and ra["confidence"]["long_status"] == "not_applicable")


# ===========================================================================
# §CSA-11 — LAZY IMPORT DISCIPLINE (module import pulls in no reliability layer)
# ===========================================================================
print("\n§CSA-11: importing the agent triggers no eager lib.reliability import")
_probe = (
    "import sys; "
    "import lib.agents.candidate_screening_agent as m; "
    "bad = [k for k in sys.modules "
    "if k.startswith('lib.reliability') or k.startswith('lib.agent_framework')]; "
    "print('LEAK' if bad else 'CLEAN')"
)
_proc = subprocess.run([sys.executable, "-c", _probe],
                       cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       capture_output=True, text=True)
test("§CSA-11a: no eager reliability / agent_framework import at module load",
     _proc.stdout.strip().endswith("CLEAN"),
     reason=f"stdout={_proc.stdout!r} stderr={_proc.stderr[-300:]!r}")


# ===========================================================================
# §CSA-12 (F2) — the tie-break chain is discriminating
#   With the PRIMARY key (RS composite) TIED, the documented chain decides:
#     -RS  ->  volume_confirmation  ->  valuation_elasticity  ->  tradability cap
#          ->  ticker  (confirmed by reading _sort_key).
#   In every sub-case the tie-break winner is the alphabetically-LATER ticker, so
#   if the deciding tier were dropped the FINAL ticker tie-break would pick the
#   OTHER name -> the assertion goes red.
#   Mutation caught: reordering or dropping any tie-break tier.
# ===========================================================================
print("\n§CSA-12: tie-break chain (RS tied) selects by the documented order")

# Tier 1 — volume_confirmation (confirmed 0 < unconfirmed 1). ZZZ confirmed beats
# AAA unconfirmed at equal RS; drop the volume tier and ticker would pick AAA.
r12a = compute_screening(
    [_card("ZZZ", rs_short=0.70, rs_mid=0.70, vol_ratio=1.5, above=True),
     _card("AAA", rs_short=0.70, rs_mid=0.70, vol_ratio=1.0, above=True)],
    [_sig("ZZZ"), _sig("AAA")], theme_key="ai_chips")
test("§CSA-12a: volume tier — confirmed ZZZ beats unconfirmed AAA at equal RS",
     r12a["decisions"]["short"]["frontrunner"].ticker == "ZZZ",
     reason=str(r12a["decisions"]["short"]["frontrunner"]))

# Tier 2 — valuation_elasticity (lower percentile wins). Both confirmed; ZZZ 0.20
# beats AAA 0.60; drop the valuation tier and ticker would pick AAA.
r12b = compute_screening(
    [_card("ZZZ", rs_short=0.70, rs_mid=0.70, vol_ratio=1.5, above=True),
     _card("AAA", rs_short=0.70, rs_mid=0.70, vol_ratio=1.5, above=True)],
    [_sig("ZZZ", val=0.20), _sig("AAA", val=0.60)], theme_key="ai_chips")
test("§CSA-12b: valuation tier — cheaper ZZZ beats AAA at equal RS+volume",
     r12b["decisions"]["short"]["frontrunner"].ticker == "ZZZ",
     reason=str(r12b["decisions"]["short"]["frontrunner"]))

# Tier 3 — tradability cap (not-capped 0 < capped 1). Both confirmed, same
# valuation; ZZZ uncapped beats AAA capped (marginal market cap); drop the
# tradability tier and ticker would pick AAA.
r12c = compute_screening(
    [_card("ZZZ", rs_short=0.70, rs_mid=0.70, vol_ratio=1.5, above=True),
     _card("AAA", rs_short=0.70, rs_mid=0.70, vol_ratio=1.5, above=True)],
    [_sig("ZZZ", val=0.30), _sig("AAA", val=0.30, market_cap=_MCAP_AMPLE / 2.0)],
    theme_key="ai_chips")
prof12c = {p.ticker: p for p in r12c["profiles"]}
test("§CSA-12c: tradability tier — uncapped ZZZ beats capped AAA (equal RS+vol+val)",
     r12c["decisions"]["short"]["frontrunner"].ticker == "ZZZ"
     and prof12c["AAA"].quality_capped is True,
     reason=str(r12c["decisions"]["short"]["frontrunner"]))

# Tier 4 — ticker (final byte-stable tie-break). Fully identical -> AAA < BBB.
r12d = compute_screening(
    [_card("BBB", rs_short=0.70, rs_mid=0.70, vol_ratio=1.5, above=True),
     _card("AAA", rs_short=0.70, rs_mid=0.70, vol_ratio=1.5, above=True)],
    [_sig("BBB", val=0.30), _sig("AAA", val=0.30)], theme_key="ai_chips")
test("§CSA-12d: ticker tier — fully identical falls to the ticker tie-break (AAA)",
     r12d["decisions"]["short"]["frontrunner"].ticker == "AAA",
     reason=str(r12d["decisions"]["short"]["frontrunner"]))


# ===========================================================================
# §CSA-13 (N2) — empty eligible set -> no_clear_winner path (a)
#   Mutation caught: an empty eligible set forcing a (nonexistent) primary or
#   crashing.
# ===========================================================================
print("\n§CSA-13: all ineligible/unknown -> no_clear_winner path (a), no primary")
# X is ineligible (Avoid Chasing thesis fail); Y is unknown (no signal supplied).
c13 = [_card("XIN", rs_short=0.90, rs_mid=0.90, status="Avoid Chasing"),
       _card("YUN", rs_short=0.85, rs_mid=0.85)]
r13 = compute_screening(c13, [_sig("XIN")], theme_key="ai_chips")  # only XIN has a signal
for _h in ("short", "mid"):
    test(f"§CSA-13a[{_h}]: frontrunner is None (empty eligible set)",
         r13["decisions"][_h]["frontrunner"] is None)
    test(f"§CSA-13b[{_h}]: no_clear_winner True",
         r13["decisions"][_h]["no_clear_winner"] is True)
    test(f"§CSA-13c[{_h}]: no_trade_reason is the empty-set code",
         r13["slates"][_h].no_trade_reason == _NT_EMPTY,
         reason=str(r13["slates"][_h].no_trade_reason))
    test(f"§CSA-13d[{_h}]: primary is None",
         r13["slates"][_h].primary is None)
    test(f"§CSA-13e[{_h}]: signal_basis degraded_insufficient",
         r13["signal_basis"][_h] == _BASIS_DEGRADED, reason=r13["signal_basis"][_h])
rej13 = {e["ticker"]: e for e in r13["slates"]["short"].rejected}
test("§CSA-13f: every ticker is rejected with gate reason codes",
     set(rej13) == {"XIN", "YUN"}
     and all(bool(rej13[t]["reasons"]) for t in rej13),
     reason=str(rej13))


# ===========================================================================
# §CSA-14 (N3-b) — capped-BUT-decisive frontrunner is ALLOWED with the flag
#   Pairs with §CSA-3 (capped + NOT decisive -> refused). A decisive lead over a
#   runner-up overrides the cap for path (c); the flag is still carried.
#   Mutation caught: treating any capped frontrunner as automatic no_clear_winner,
#   OR dropping the flag on a decisive capped leader.
# ===========================================================================
print("\n§CSA-14: capped leader WITH a decisive lead -> allowed, flag preserved")
c14 = [_card("CAP", rs_short=0.99, rs_mid=0.99),   # capped, decisive lead
       _card("RUN", rs_short=0.80, rs_mid=0.80)]   # runner-up
s14 = [_sig("CAP", market_cap=_MCAP_AMPLE / 2.0), _sig("RUN")]
r14 = compute_screening(c14, s14, theme_key="ai_chips")
prof14 = {p.ticker: p for p in r14["profiles"]}
test("§CSA-14a: CAP is quality_capped (marginal market cap)",
     prof14["CAP"].quality_capped is True)
test("§CSA-14b: lead is decisive (>= _RS_GAP_DECISIVE_PCT)",
     r14["decisions"]["short"]["lead"] >= _RS_GAP_DECISIVE_PCT,
     reason=str(r14["decisions"]["short"]["lead"]))
test("§CSA-14c: no_clear_winner is False (decisive lead overrides the cap)",
     r14["decisions"]["short"]["no_clear_winner"] is False)
test("§CSA-14d: primary IS the capped leader CAP (allowed)",
     r14["slates"]["short"].primary == "CAP",
     reason=str(r14["slates"]["short"].primary))
test("§CSA-14e: the frontrunner entry STILL carries quality_capped True",
     r14["decisions"]["short"]["frontrunner"].quality_capped is True)
test("§CSA-14f: no_trade_reason is None (a pick was made)",
     r14["slates"]["short"].no_trade_reason is None)


# ===========================================================================
# §CSA-15 (R2) — a missing signal FAILS CLOSED (never silently eligible)
#   Mutation caught: an unmatched by-ticker join defaulting to a pass.
# ===========================================================================
print("\n§CSA-15: missing signal -> hard-unknown -> rejected (fail closed)")


def _assert_failed_closed(label, result, ticker):
    sl = result["slates"]["short"]
    rej = {e["ticker"]: e for e in sl.rejected}
    prof = {p.ticker: p for p in result["profiles"]}
    unknowns = set(result["verdict_map"][ticker]["short"].unknowns)
    test(f"{label}: {ticker} status is unknown (not eligible)",
         prof[ticker].short_status == "unknown", reason=prof[ticker].short_status)
    test(f"{label}: {ticker} is REJECTED, never primary/secondary/watch",
         ticker in rej and ticker != sl.primary
         and ticker not in sl.secondary and ticker not in sl.watch,
         reason=f"primary={sl.primary} watch={sl.watch} rejected={list(rej)}")
    test(f"{label}: rejected {ticker} carries the gate's unknown reason codes",
         {EPS_UNKNOWN, VALUATION_UNKNOWN, DISTRIBUTION_UNKNOWN} <= unknowns,
         reason=str(unknowns))


# (a) signals=None entirely.
r15a = compute_screening([_card("AAA", rs_short=0.90, rs_mid=0.90)], None,
                         theme_key="ai_chips")
_assert_failed_closed("§CSA-15a (signals=None)", r15a, "AAA")

# (b) signals provided but the map does NOT contain the card's ticker.
r15b = compute_screening([_card("AAA", rs_short=0.90, rs_mid=0.90)],
                         [_sig("OTHER")], theme_key="ai_chips")
_assert_failed_closed("§CSA-15b (unmatched ticker)", r15b, "AAA")


# ===========================================================================
# §CSA-16 (R3) — a wrong-ticker signal does NOT cross-contaminate
#   Only BBB's (eligible-making) signal is supplied; AAA has none. An EXACT-by-
#   ticker join leaves AAA fail-closed; a positional/loose join would hand AAA
#   the BBB signal and wrongly make it eligible.
#   Mutation caught: a positional or loose join reading another card's signal.
# ===========================================================================
print("\n§CSA-16: exact-by-ticker join — no cross-contamination")
c16 = [_card("AAA", rs_short=0.95, rs_mid=0.95),   # first card, NO signal
       _card("BBB", rs_short=0.60, rs_mid=0.60)]    # second card, HAS the signal
r16 = compute_screening(c16, [_sig("BBB")], theme_key="ai_chips")
prof16 = {p.ticker: p for p in r16["profiles"]}
test("§CSA-16a: BBB (its own signal) resolves eligible",
     prof16["BBB"].short_status == "eligible", reason=prof16["BBB"].short_status)
test("§CSA-16b: AAA does NOT inherit BBB's signal -> unknown (fail closed)",
     prof16["AAA"].short_status == "unknown", reason=prof16["AAA"].short_status)
test("§CSA-16c: AAA is NOT the primary (a positional join would wrongly pick it)",
     r16["slates"]["short"].primary == "BBB",
     reason=str(r16["slates"]["short"].primary))
test("§CSA-16d: AAA appears only in rejected",
     "AAA" in {e["ticker"] for e in r16["slates"]["short"].rejected},
     reason=str([e["ticker"] for e in r16["slates"]["short"].rejected]))


# ===========================================================================
# §CSA-17 (U1) — unavailable dimensions cannot enter the sort key
#   Two profiles IDENTICAL on every available dimension AND ticker, differing ONLY
#   on the unavailable markers, must produce IDENTICAL sort keys.
#   Mutation caught: an "unavailable" marker silently participating in the key.
# ===========================================================================
print("\n§CSA-17: unavailable-dimension markers never enter _sort_key")


def _profile(**overrides) -> CandidateProfile:
    kw = dict(
        ticker="AAA", short_status="eligible", mid_status="eligible",
        long_status="not_applicable", data_quality="live",
        rs_short=0.70, rs_mid=0.70, rs_available=True, rs_excess={},
        valuation_percentile=0.30, valuation_state=_KNOWN,
        short_crowding_state=_UNAVAILABLE, theme_role="leader",
        volume_confirmation="confirmed", options_structure_state=_UNAVAILABLE,
        catalyst_proximity="far", market_cap_tier="unknown",
        liquidity_tier="ample", quality_capped=False,
    )
    kw.update(overrides)
    return CandidateProfile(**kw)


# Identical on every AVAILABLE dimension AND ticker; differ ONLY on the two
# unavailable markers (set to deliberately-different arbitrary values).
p17a = _profile(short_crowding_state="HOT", options_structure_state="supportive")
p17b = _profile(short_crowding_state="COLD", options_structure_state="resistance")
test("§CSA-17a: short sort keys are identical (unavailable markers ignored)",
     _sort_key(p17a, "short") == _sort_key(p17b, "short"),
     reason=f"{_sort_key(p17a, 'short')} vs {_sort_key(p17b, 'short')}")
test("§CSA-17b: mid sort keys are identical (unavailable markers ignored)",
     _sort_key(p17a, "mid") == _sort_key(p17b, "mid"))
# And the markers really are different, so the test would bite if they entered.
test("§CSA-17c: the two profiles genuinely differ on the unavailable markers",
     p17a.short_crowding_state != p17b.short_crowding_state
     and p17a.options_structure_state != p17b.options_structure_state)


# ===========================================================================
# §CSA-18 (U3) — valuation provenance is not re-leaked at the agent layer
#   A defaulted 0.5 (fixture provenance, or live provenance with an UNUSABLE
#   forward_pe) must resolve to valuation_state "unknown" (via the gate's
#   _valuation_missing), NOT a raw cheap 0.5 read. Such a ticker is a hard-unknown
#   and is REJECTED — it can never sway the frontrunner or confidence.
#   Mutation caught: the agent reading a defaulted 0.5 as a real valuation.
# ===========================================================================
print("\n§CSA-18: defaulted valuation stays 'unknown' at the agent layer")


def _sig_fixture_val(ticker):
    """Signal with a FIXTURE-provenance valuation and a raw 0.5 percentile."""
    return CandidateSignal(
        ticker=ticker, eps_revision_direction="improving", entry_quality_label="good",
        valuation_percentile=0.5,
        fundamental=FundamentalSignals(
            forward_pe=20.0, data_source={"valuation": "fixture", "eps": "live"}),
    )


def _sig_unusable_pe(ticker):
    """Signal with LIVE provenance but an UNUSABLE (0.0) forward_pe -> defaulted."""
    return CandidateSignal(
        ticker=ticker, eps_revision_direction="improving", entry_quality_label="good",
        valuation_percentile=0.5,
        fundamental=FundamentalSignals(
            forward_pe=0.0, data_source={"valuation": "live", "eps": "live"}),
    )


for _lbl, _mk in (("fixture-provenance", _sig_fixture_val),
                  ("unusable forward_pe", _sig_unusable_pe)):
    r18 = compute_screening([_card("AAA", rs_short=0.90, rs_mid=0.90)],
                            [_mk("AAA")], theme_key="ai_chips")
    prof18 = {p.ticker: p for p in r18["profiles"]}
    test(f"§CSA-18 [{_lbl}]: valuation_state is 'unknown' (not a raw 0.5 read)",
         prof18["AAA"].valuation_state == _UNKNOWN,
         reason=prof18["AAA"].valuation_state)
    test(f"§CSA-18 [{_lbl}]: hard-unknown -> AAA rejected, never primary",
         prof18["AAA"].short_status == "unknown"
         and r18["slates"]["short"].primary != "AAA",
         reason=prof18["AAA"].short_status)
    test(f"§CSA-18 [{_lbl}]: rejected AAA carries VALUATION_UNKNOWN",
         VALUATION_UNKNOWN in set(r18["verdict_map"]["AAA"]["short"].unknowns),
         reason=str(r18["verdict_map"]["AAA"]["short"].unknowns))


# ── Summary ─────────────────────────────────────────────────────────────────

print(f"\n{'=' * 60}")
print(f"CandidateScreeningAgent suite: {PASS} passed, {FAIL} failed "
      f"({PASS + FAIL} assertions)")
if ERRORS:
    print("\nFailures:")
    for e in ERRORS:
        print(f"  - {e}")
print('=' * 60)
sys.exit(1 if FAIL else 0)
