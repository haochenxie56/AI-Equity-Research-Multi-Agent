"""
scripts/test_phase_8b_macro_regime_agent.py

Phase 8B — MacroRegimeAgent production implementation, test suite.

Directly runnable (project hand-rolled harness, NOT pytest):
    wsl.exe -d ubuntu -- bash -lc 'python3 scripts/test_phase_8b_macro_regime_agent.py'

Discipline:
  * All LLM calls are mocked at the ``run_llm_agent`` boundary (the agent module
    name) — no Claude is ever hit.
  * All network is mocked at the ``fetch_all_macro`` / ``load_all_meta``
    boundaries — no yfinance / FRED / snapshot file reads.
  * MacroRegimeResult / MacroDataResult field VALUES are NEVER fabricated: every
    fixture is the REAL dataclass constructed with realistic, documented values
    (e.g. the M11 MacroDataResult votes are produced by the real classify_regime
    thresholds, not asserted by hand).
"""

import os
import sys

# ── Repo root on path ──────────────────────────────────────────────────────
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ── Imports under test ─────────────────────────────────────────────────────
import lib.agents.macro_regime_agent as agent_mod
from lib.agents.macro_regime_agent import (
    _compute_short_confidence,
    _compute_mid_confidence,
    _compute_long_confidence,
    _count_consecutive_same_regime,
    run_macro_regime_agent,
)
from lib.macro_regime import MacroRegimeResult, classify_regime
from lib.macro_data import (
    MacroDataResult,
    VixResult,
    RatesResult,
    CreditResult,
    DollarResult,
    EtfReturnsResult,
    EconomicReleasesResult,
    SentimentResult,
)
from lib.agent_framework.agent_output import AgentOutput
import lib.audit_query as audit_query
from lib.audit_query import MetaRecord
import lib.macro_data as macro_data_mod
import lib.macro_regime as macro_regime_mod


# ── Test runner ────────────────────────────────────────────────────────────

PASS = 0
FAIL = 0
ERRORS: list = []


def _ok(label: str) -> None:
    global PASS
    PASS += 1
    print(f"  [PASS] {label}")


def _fail(label: str, reason: str = "") -> None:
    global FAIL
    FAIL += 1
    ERRORS.append(f"{label}: {reason}")
    print(f"  [FAIL] {label}: {reason}")


def test(label: str, condition: bool, reason: str = "") -> None:
    if condition:
        _ok(label)
    else:
        _fail(label, reason or "condition was False")


# ── Fixtures (real dataclasses; no fabricated values) ──────────────────────

def _regime(**overrides) -> MacroRegimeResult:
    """Build a real MacroRegimeResult with sensible defaults + overrides."""
    base = dict(
        regime="risk_on",
        confidence="medium",
        horizon_bias={"short": "favorable", "mid": "favorable", "long": "neutral"},
        key_signals=["sample signal"],
        opportunity_posture="Review-only context.",
        data_coverage=1.0,
        signals=[{"code": "vix_low", "values": {"vix": 15.0}}],
        votes_risk_on=0,
        votes_risk_off=0,
        votes_total=0,
    )
    base.update(overrides)
    return MacroRegimeResult(**base)


def _meta(date: str, regime: str) -> MetaRecord:
    """A real MetaRecord carrying only the fields this agent reads."""
    return MetaRecord.from_dict({"date": date, "macro_regime": regime})


def _make_macro_data_result(coverage: float = 1.0) -> MacroDataResult:
    """A real MacroDataResult whose values produce a MIXED 3-vs-3 tally under the
    real classify_regime thresholds (risk_on: VIX<18, fear_greed>60, breadth;
    risk_off: HY>5.0, curve<0, dollar>2%)."""
    return MacroDataResult(
        vix=VixResult(value=15.0, change_1m=-1.0, fear_greed=65.0, data_source="live"),
        rates=RatesResult(yield_10y=4.0, yield_2y=4.5, spread_10y_2y=-0.5,
                          breakeven_10y=2.3, data_source="live"),
        credit=CreditResult(hy_spread=6.0, data_source="live"),
        dollar=DollarResult(value=121.0, change_1m=3.0, data_source="live"),
        etf_returns=EtfReturnsResult(returns_1m={"SPY": 1.0, "IWM": 1.0},
                                     returns_3m={}, data_source="live"),
        economic_releases=EconomicReleasesResult(
            nfp=None, nfp_date=None, cpi=None, cpi_date=None,
            ppi=None, ppi_date=None, data_source="live"),
        sentiment=SentimentResult(score=60.0, label="greed", data_source="live"),
        timestamp="2026-06-20T00:00:00+00:00",
        data_coverage=coverage,
    )


def _make_macro_data_result_5on_1off(coverage: float = 1.0) -> MacroDataResult:
    """A real MacroDataResult engineered for an ASYMMETRIC 5-vs-1 tally under the
    real classify_regime thresholds:
        risk_on (5): VIX<18, fear_greed>60, HY<3.5, 10Y-2Y>0.5, breadth(SPY+IWM>0)
        risk_off (1): dollar 1M change > +2%
    -> votes_risk_on=5, votes_risk_off=1, votes_total=6. The (correct) additive
    total (5+1=6) differs from a `votes_risk_on*2` mutation (10), so the sum
    invariant is genuinely discriminating."""
    return MacroDataResult(
        vix=VixResult(value=12.0, change_1m=-1.0, fear_greed=70.0, data_source="live"),
        rates=RatesResult(yield_10y=5.0, yield_2y=4.0, spread_10y_2y=1.0,
                          breakeven_10y=2.3, data_source="live"),
        credit=CreditResult(hy_spread=2.0, data_source="live"),
        dollar=DollarResult(value=121.0, change_1m=3.0, data_source="live"),
        etf_returns=EtfReturnsResult(returns_1m={"SPY": 5.0, "IWM": 5.0},
                                     returns_3m={}, data_source="live"),
        economic_releases=EconomicReleasesResult(
            nfp=None, nfp_date=None, cpi=None, cpi_date=None,
            ppi=None, ppi_date=None, data_source="live"),
        sentiment=SentimentResult(score=70.0, label="greed", data_source="live"),
        timestamp="2026-06-20T00:00:00+00:00",
        data_coverage=coverage,
    )


def _fake_agent_output(**kwargs) -> AgentOutput:
    """Stand-in for run_llm_agent: echoes supporting_data onto a minimal valid
    AgentOutput so tests can read the deterministically-computed confidences."""
    return AgentOutput(
        agent_id=kwargs.get("agent_id", "MacroRegimeAgent"),
        timestamp="2026-06-20T00:00:00+00:00",
        horizon=kwargs.get("horizon", "cross"),
        judgment="Stay balanced across horizons pending clearer confirmation.",
        confidence=0.5,
        evidence_refs=[],
        supporting_data=kwargs.get("supporting_data", {}),
        requires_human_confirmation=kwargs.get("requires_human_confirmation", True),
        judgment_source=kwargs.get("judgment_source", "llm_proposed"),
        valid_until=kwargs.get("valid_until", ""),
    )


class _patch:
    """Tiny attribute-patcher with restore (avoids a pytest/mock dependency)."""

    def __init__(self):
        self._saved = []

    def set(self, module, name, value):
        self._saved.append((module, name, getattr(module, name)))
        setattr(module, name, value)

    def restore(self):
        for module, name, old in reversed(self._saved):
            setattr(module, name, old)
        self._saved = []


# ===========================================================================
# §8B-M1 — _compute_short_confidence == 0.0 on degraded (votes_total=0)
# ===========================================================================
print("\n§8B-M1: _compute_short_confidence on degraded")
r_degraded = _regime(regime="degraded", confidence="low", data_coverage=0.3,
                     votes_risk_on=0, votes_risk_off=0, votes_total=0)
test("§8B-M1: degraded/votes_total=0 -> 0.0",
     _compute_short_confidence(r_degraded) == 0.0,
     reason=str(_compute_short_confidence(r_degraded)))


# ===========================================================================
# §8B-M2 — clear majority
# ===========================================================================
print("\n§8B-M2: _compute_short_confidence clear majority")
r_major = _regime(votes_risk_on=5, votes_risk_off=1, votes_total=6)
sc2 = _compute_short_confidence(r_major)
test("§8B-M2: abs(5-1)/6 ≈ 0.667", abs(sc2 - 0.667) < 0.01, reason=str(sc2))


# ===========================================================================
# §8B-M3 — split vote -> 0.0, with discriminating check
# ===========================================================================
print("\n§8B-M3: _compute_short_confidence split vote")
r_split = _regime(votes_risk_on=3, votes_risk_off=3, votes_total=6)
test("§8B-M3: 3 vs 3 -> 0.0", _compute_short_confidence(r_split) == 0.0,
     reason=str(_compute_short_confidence(r_split)))
# DISCRIMINATING: nudge the tally off-balance -> must become positive.
r_split.votes_risk_on = 4
test("§8B-M3 (discriminating): 4 vs 3 -> > 0.0",
     _compute_short_confidence(r_split) > 0.0,
     reason=str(_compute_short_confidence(r_split)))


# ===========================================================================
# §8B-M4 — empty history -> 0.1
# ===========================================================================
print("\n§8B-M4: _compute_mid_confidence empty history")
p = _patch()
try:
    p.set(audit_query, "load_all_meta", lambda *a, **k: [])
    mc4 = _compute_mid_confidence("risk_on", snapshot_dir="data/snapshots")
    test("§8B-M4: empty -> 0.1", mc4 == 0.1, reason=str(mc4))
finally:
    p.restore()


# ===========================================================================
# §8B-M5 — consecutive same-regime days, with discriminating check
# ===========================================================================
print("\n§8B-M5: _compute_mid_confidence counts consecutive days")
seq_3 = [
    _meta("2026-06-01", "risk_on"),
    _meta("2026-06-02", "risk_on"),
    _meta("2026-06-03", "transition"),
    _meta("2026-06-04", "risk_on"),
    _meta("2026-06-05", "risk_on"),
    _meta("2026-06-06", "risk_on"),   # most recent
]
p = _patch()
try:
    p.set(audit_query, "load_all_meta", lambda *a, **k: seq_3)
    mc5 = _compute_mid_confidence("risk_on", snapshot_dir="data/snapshots")
    # 3 consecutive trailing days -> breakpoint value 0.4.
    test("§8B-M5: 3 consecutive -> 0.4", abs(mc5 - 0.4) < 1e-9, reason=str(mc5))
finally:
    p.restore()

# DISCRIMINATING: most recent becomes a different regime -> 0 consecutive -> 0.1.
seq_0 = seq_3[:-1] + [_meta("2026-06-06", "transition")]
p = _patch()
try:
    p.set(audit_query, "load_all_meta", lambda *a, **k: seq_0)
    mc5b = _compute_mid_confidence("risk_on", snapshot_dir="data/snapshots")
    test("§8B-M5 (discriminating): 0 consecutive -> 0.1",
         mc5b == 0.1, reason=str(mc5b))
finally:
    p.restore()


# ===========================================================================
# §8B-M6a — Guard A: current_regime "unknown"/"degraded" -> early-return 0.0
# ===========================================================================
# This fixture is built so ONLY Guard A (the `if current_regime in
# _DEGRADE_REGIMES: return 0.0` early-return in _compute_mid_confidence) makes it
# 0.0. The history is FIVE "unknown" records and current_regime is "unknown", so
# plain equality matching would NOT break on them — without Guard A the call
# falls through to _count_consecutive_same_regime, whose Guard B breaks on the
# first "unknown" giving count 0 -> 0.1 (a non-empty history is never 0.0). So
# removing Guard A flips the result 0.0 -> 0.1: genuinely discriminating.
print("\n§8B-M6a: Guard A early-return for current_regime='unknown'")
seq_unknown5 = [_meta(f"2026-06-0{i}", "unknown") for i in range(1, 6)]
p = _patch()
try:
    p.set(audit_query, "load_all_meta", lambda *a, **k: seq_unknown5)
    mc6a = _compute_mid_confidence("unknown", snapshot_dir="data/snapshots")
    test("§8B-M6a: current_regime='unknown' -> 0.0", mc6a == 0.0, reason=str(mc6a))
finally:
    p.restore()

# ===========================================================================
# §8B-M6b — Guard B: an "unknown"/"degraded" day in history breaks the streak
# ===========================================================================
# Most-recent (last) is risk_on, with an "unknown" day immediately before three
# older risk_on days. Guard B (the degrade hard-BREAK) stops the streak at the
# "unknown", so only the single trailing risk_on counts (1 day -> 0.2). The
# discriminating mutation is Guard B's `break` -> `continue`: that would SKIP the
# "unknown" and keep counting the 3 older risk_on days (4 days -> 0.5 != 0.2).
# Note M5's break is driven by a "transition" day (a NON-degrade mismatch), so
# M5 stays green under that mutation — M6b is what uniquely catches Guard B.
print("\n§8B-M6b: Guard B break on 'unknown' in history")
seq_b = [
    _meta("2026-06-01", "risk_on"),
    _meta("2026-06-02", "risk_on"),
    _meta("2026-06-03", "risk_on"),
    _meta("2026-06-04", "unknown"),
    _meta("2026-06-05", "risk_on"),   # most recent
]
p = _patch()
try:
    p.set(audit_query, "load_all_meta", lambda *a, **k: seq_b)
    mc6b = _compute_mid_confidence("risk_on", snapshot_dir="data/snapshots")
    # 1 consecutive trailing risk_on -> breakpoint value 0.2.
    test("§8B-M6b: 'unknown' breaks streak -> 1 day -> 0.2",
         abs(mc6b - 0.2) < 1e-9, reason=str(mc6b))
finally:
    p.restore()


# ===========================================================================
# §8B-M7 — long_confidence formula
# ===========================================================================
print("\n§8B-M7: _compute_long_confidence formula")
lc7 = _compute_long_confidence(0.8, 0.75)
test("§8B-M7: 0.8 * 0.75 == 0.6", abs(lc7 - 0.6) < 0.001, reason=str(lc7))
test("§8B-M7b: 0.0 * 0.9 == 0.0", _compute_long_confidence(0.0, 0.9) == 0.0)


# ===========================================================================
# §8B-M8 — run_macro_regime_agent accepts MacroRegimeResult directly
# ===========================================================================
print("\n§8B-M8: run_macro_regime_agent accepts MacroRegimeResult")
r8 = _regime(regime="risk_on", confidence="high", votes_risk_on=4,
             votes_risk_off=2, votes_total=6, data_coverage=0.85)
seq5 = [_meta(f"2026-06-0{i}", "risk_on") for i in range(1, 6)]  # 5 same-regime
p = _patch()
try:
    p.set(audit_query, "load_all_meta", lambda *a, **k: seq5)
    p.set(agent_mod, "run_llm_agent", lambda **kw: _fake_agent_output(**kw))
    raised8 = None
    try:
        out8 = run_macro_regime_agent(r8)
    except Exception as e:  # noqa: BLE001
        raised8 = e
        out8 = None
    test("§8B-M8: no exception raised", raised8 is None, reason=str(raised8))
    test("§8B-M8b: short_confidence > 0",
         out8 is not None and out8.supporting_data["short_confidence"] > 0,
         reason="" if out8 is None else str(out8.supporting_data.get("short_confidence")))
    test("§8B-M8c: mid_confidence > 0",
         out8 is not None and out8.supporting_data["mid_confidence"] > 0,
         reason="" if out8 is None else str(out8.supporting_data.get("mid_confidence")))
    test("§8B-M8d: consecutive_same_regime_days == 5",
         out8 is not None and out8.supporting_data["consecutive_same_regime_days"] == 5,
         reason="" if out8 is None else str(out8.supporting_data.get("consecutive_same_regime_days")))
finally:
    p.restore()


# ===========================================================================
# §8B-M9 — fetches internally when regime_signals is None
# ===========================================================================
print("\n§8B-M9: run_macro_regime_agent fetches internally on None")
fetch_calls = {"n": 0}
classify_calls = {"n": 0, "arg": None}
_data9 = _make_macro_data_result(coverage=0.9)
_regime9 = _regime(regime="risk_on", votes_risk_on=4, votes_risk_off=1,
                   votes_total=5, data_coverage=0.9)


def _fake_fetch_all_macro():
    fetch_calls["n"] += 1
    return _data9


def _fake_classify_regime(data):
    classify_calls["n"] += 1
    classify_calls["arg"] = data
    return _regime9


p = _patch()
try:
    p.set(macro_data_mod, "fetch_all_macro", _fake_fetch_all_macro)
    p.set(macro_regime_mod, "classify_regime", _fake_classify_regime)
    p.set(audit_query, "load_all_meta", lambda *a, **k: [])
    p.set(agent_mod, "run_llm_agent", lambda **kw: _fake_agent_output(**kw))
    out9 = run_macro_regime_agent(None)
    test("§8B-M9: fetch_all_macro called exactly once", fetch_calls["n"] == 1,
         reason=str(fetch_calls["n"]))
    test("§8B-M9b: classify_regime called exactly once", classify_calls["n"] == 1,
         reason=str(classify_calls["n"]))
    test("§8B-M9c: classify_regime called with the fetch result",
         classify_calls["arg"] is _data9)
finally:
    p.restore()


# ===========================================================================
# §8B-M10 — fail-closed on LLM error
# ===========================================================================
print("\n§8B-M10: run_macro_regime_agent fail-closed on LLM error")


def _raise_llm(**kw):
    raise Exception("claude_unavailable")


r10 = _regime(regime="risk_on", votes_risk_on=4, votes_risk_off=1,
              votes_total=5, data_coverage=0.8)
p = _patch()
try:
    p.set(audit_query, "load_all_meta", lambda *a, **k: [])
    p.set(agent_mod, "run_llm_agent", _raise_llm)
    raised10 = None
    out10 = None
    try:
        out10 = run_macro_regime_agent(r10)
    except Exception as e:  # noqa: BLE001
        raised10 = e
    test("§8B-M10: no exception raised to caller", raised10 is None,
         reason=str(raised10))
    test("§8B-M10b: returns an AgentOutput (fallback)",
         isinstance(out10, AgentOutput), reason=str(type(out10)))
finally:
    p.restore()


# ===========================================================================
# §8B-M11 — MacroRegimeResult now carries vote fields
# ===========================================================================
print("\n§8B-M11: classify_regime populates vote fields")
# ASYMMETRIC 5-vs-1 tally (NOT a symmetric split) so the additive total (6) is
# distinguishable from a `votes_risk_on*2` mutation (10).
data11 = _make_macro_data_result_5on_1off(coverage=1.0)
res11 = classify_regime(data11)   # the REAL classifier, real thresholds
test("§8B-M11: votes_risk_on == 5", res11.votes_risk_on == 5, reason=str(res11.votes_risk_on))
test("§8B-M11b: votes_risk_off == 1", res11.votes_risk_off == 1, reason=str(res11.votes_risk_off))
test("§8B-M11c: votes_total == 6", res11.votes_total == 6, reason=str(res11.votes_total))
# DISCRIMINATING invariant: the parts must sum to the whole. With an asymmetric
# 5/1 split this goes RED under a `votes_total = votes_risk_on * 2` mutation
# (5 + 1 == 6, but the mutation yields 10).
test("§8B-M11d: votes_risk_on + votes_risk_off == votes_total",
     res11.votes_risk_on + res11.votes_risk_off == res11.votes_total,
     reason=f"{res11.votes_risk_on}+{res11.votes_risk_off} != {res11.votes_total}")


# ── Final summary ──────────────────────────────────────────────────────────

print(f"\n{'=' * 60}")
print(f"Phase 8B MacroRegimeAgent Tests: {PASS} passed, {FAIL} failed")
if ERRORS:
    print("\nFailures:")
    for err in ERRORS:
        print(f"  - {err}")
print("=" * 60)

sys.exit(0 if FAIL == 0 else 1)
