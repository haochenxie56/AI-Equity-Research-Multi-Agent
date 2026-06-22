"""
scripts/test_phase_8b_money_flow_agent.py

Phase 8B — MoneyFlowAgent production implementation, test suite.

Directly runnable (project hand-rolled harness, NOT pytest):
    wsl.exe -d ubuntu -- bash -lc 'python3 scripts/test_phase_8b_money_flow_agent.py'

Discipline (mirrors test_phase_8b_macro_regime_agent.py):
  * All LLM calls are mocked at the ``run_llm_agent`` SOURCE module
    (``lib.agent_framework.agent_runner``) — no Claude is ever hit. Because the
    agent imports its dependencies LAZILY, patching the source module is what
    makes the patched callable visible to the lazy ``from ... import``.
  * All network is mocked at the ``fetch_options_chain`` / ``compute_gex_dex`` /
    ``compute_dark_pool_signal`` source boundaries — no Massive / Quiver reads.
  * GexDexResult field VALUES are NEVER fabricated dishonestly: every fixture is
    the REAL ``GexDexResult`` dataclass, and every dark-pool fixture matches the
    exact dict schema ``compute_dark_pool_signal`` returns.
"""

import os
import sys
import tempfile

# ── Repo root on path ──────────────────────────────────────────────────────
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ── Imports under test ─────────────────────────────────────────────────────
import lib.agents.money_flow_agent as agent_mod
from lib.agents.money_flow_agent import (
    _compute_short_confidence,
    _compute_mid_confidence,
    _compute_long_confidence,
    _short_signal_count,
    _load_prior_gex_dex_result,
    run_money_flow_agent,
    end_of_today_iso,
)
from lib.gex_dex import GexDexResult
from lib.agent_framework.agent_output import AgentOutput
import lib.massive_options_fetcher as mof_mod
import lib.gex_dex as gex_dex_mod
import lib.quiver_fetcher as quiver_mod
import lib.agent_framework.agent_runner as agent_runner_mod


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


# ── Fixtures (real GexDexResult dataclass; real dark-pool schema) ───────────

def _gex(
    gex_sign: str = "positive",
    dex_sign: str = "positive",
    *,
    degraded: bool = False,
    call_wall=110.0,
    put_wall=90.0,
    squeeze_probability: str = "low",
    squeeze_direction="up",
    contracts_used: int = 10,
    gex_total=None,
    dex_total=None,
) -> GexDexResult:
    """A REAL GexDexResult with sensible defaults. gex_total/dex_total default to
    a magnitude consistent with the requested sign so the dataclass is coherent.
    """
    if gex_total is None:
        gex_total = 1.0 if gex_sign == "positive" else (-1.0 if gex_sign == "negative" else 0.0)
    if dex_total is None:
        dex_total = 1.0 if dex_sign == "positive" else (-1.0 if dex_sign == "negative" else 0.0)
    return GexDexResult(
        ticker="SPY",
        as_of="2026-06-20T00:00:00+00:00",
        underlying_price=100.0,
        gex_total=gex_total,
        gex_sign=gex_sign,
        gex_call=1.0,
        gex_put=0.0,
        dex_total=dex_total,
        dex_sign=dex_sign,
        dex_call=1.0,
        dex_put=0.0,
        call_wall=call_wall,
        put_wall=put_wall,
        call_wall_oi=500,
        put_wall_oi=400,
        squeeze_probability=squeeze_probability,
        squeeze_direction=squeeze_direction,
        squeeze_trigger_conditions=[],
        contracts_used=contracts_used,
        degraded=degraded,
        degraded_reasons=[],
        expiry_filter="this_week",
    )


def _dark_pool(
    net_direction: str = "bullish",
    signal_strength: str = "strong",
    *,
    degraded: bool = False,
    record_count: int = 5,
    total_amount: float = 1000.0,
) -> dict:
    """A dark-pool signal dict in the EXACT schema compute_dark_pool_signal
    returns (see lib/quiver_fetcher.py::compute_dark_pool_signal)."""
    return {
        "ticker": "SPY",
        "n_days": 5,
        "net_direction": net_direction,
        "total_amount": total_amount,
        "buy_amount": 700.0,
        "sell_amount": 300.0,
        "signal_strength": signal_strength,
        "record_count": record_count,
        "degraded": degraded,
        "source": "quiver_dark_pool",
    }


def _fake_agent_output(**kwargs) -> AgentOutput:
    """Stand-in for run_llm_agent: echoes supporting_data onto a minimal valid
    AgentOutput so tests can read the deterministically-computed fields."""
    return AgentOutput(
        agent_id=kwargs.get("agent_id", "MoneyFlowAgent"),
        timestamp="2026-06-20T00:00:00+00:00",
        horizon=kwargs.get("horizon", "cross"),
        judgment="Structure a defined-risk options position between the walls.",
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


# A capturing run_llm_agent fake: records the kwargs it was called with.
class _Capture:
    def __init__(self):
        self.kwargs = None

    def __call__(self, **kw):
        self.kwargs = kw
        return _fake_agent_output(**kw)


# ===========================================================================
# §8B-MF1 — short_confidence == 1.0 when all three signals usable
# ===========================================================================
print("\n§8B-MF1: short_confidence all-three usable -> 1.0")
g1 = _gex(gex_sign="positive", dex_sign="positive", degraded=False)
dp1 = _dark_pool(net_direction="bullish", signal_strength="strong", degraded=False)
sc1 = _compute_short_confidence(g1, dp1)
test("§8B-MF1: 3/3 -> 1.0", sc1 == 1.0, reason=str(sc1))
# Mutation probe: flip ONE signal to neutral -> confidence must drop below 1.0.
g1_flip = _gex(gex_sign="neutral", dex_sign="positive", degraded=False)
sc1b = _compute_short_confidence(g1_flip, dp1)
test("§8B-MF1 (discriminating): flip gex_sign->neutral drops below 1.0",
     sc1b < 1.0 and abs(sc1b - round(2 / 3.0, 6)) < 1e-9, reason=str(sc1b))


# ===========================================================================
# §8B-MF2 — short_confidence == 0.0 when gex_result.degraded=True
# ===========================================================================
print("\n§8B-MF2: short_confidence gex degraded -> GEX/DEX signals zeroed")
g2 = _gex(gex_sign="positive", dex_sign="negative", degraded=True)
dp2_neutral = _dark_pool(net_direction="neutral", signal_strength="none", degraded=True)
sc2 = _compute_short_confidence(g2, dp2_neutral)
test("§8B-MF2: gex degraded + dark pool neutral -> 0.0", sc2 == 0.0, reason=str(sc2))
# Discriminating: degraded zeros signals 1&2 SPECIFICALLY — a usable dark pool
# still counts as exactly one signal (1/3), proving the GEX/DEX pair was zeroed.
dp2_bull = _dark_pool(net_direction="bullish", signal_strength="strong", degraded=False)
sc2b = _compute_short_confidence(g2, dp2_bull)
test("§8B-MF2b (discriminating): degraded zeros GEX/DEX -> only dark pool counts (1/3)",
     abs(sc2b - round(1 / 3.0, 6)) < 1e-9, reason=str(sc2b))


# ===========================================================================
# §8B-MF3 — mid_confidence reflects strength_map × direction clarity
# ===========================================================================
print("\n§8B-MF3: mid_confidence strength_map")
mc_strong = _compute_mid_confidence(_dark_pool("bullish", "strong"))
test("§8B-MF3: strong+bullish -> 1.0", mc_strong == 1.0, reason=str(mc_strong))
mc_mod = _compute_mid_confidence(_dark_pool("bearish", "moderate"))
test("§8B-MF3b: moderate+bearish -> 0.6", abs(mc_mod - 0.6) < 1e-9, reason=str(mc_mod))
mc_weak = _compute_mid_confidence(_dark_pool("bullish", "weak"))
test("§8B-MF3c: weak+bullish -> 0.3", abs(mc_weak - 0.3) < 1e-9, reason=str(mc_weak))
mc_insuf = _compute_mid_confidence(
    _dark_pool("insufficient_data", "none", degraded=True, record_count=1)
)
test("§8B-MF3d: insufficient_data -> 0.0", mc_insuf == 0.0, reason=str(mc_insuf))
# Discriminating: strong strength but NEUTRAL direction must NOT borrow 1.0.
mc_neutral = _compute_mid_confidence(_dark_pool("neutral", "strong"))
test("§8B-MF3e (discriminating): strong+neutral direction -> 0.0",
     mc_neutral == 0.0, reason=str(mc_neutral))


# ===========================================================================
# §8B-MF4 — long_confidence always 0.0
# ===========================================================================
print("\n§8B-MF4: long_confidence always 0.0")
test("§8B-MF4: _compute_long_confidence() == 0.0", _compute_long_confidence() == 0.0)


# ===========================================================================
# §8B-MF5 — three ToolResults with correct tool_names
# ===========================================================================
print("\n§8B-MF5: three ToolResults with correct tool_names")
cap5 = _Capture()
p = _patch()
try:
    p.set(mof_mod, "fetch_options_chain", lambda *a, **k: object())
    p.set(gex_dex_mod, "compute_gex_dex",
          lambda *a, **k: _gex("positive", "positive"))
    p.set(quiver_mod, "compute_dark_pool_signal",
          lambda *a, **k: _dark_pool("bullish", "strong"))
    p.set(agent_runner_mod, "run_llm_agent", cap5)
    out5 = run_money_flow_agent(ticker="SPY")
    trs = (cap5.kwargs or {}).get("tool_results", [])
    names = [getattr(tr, "tool_name", None) for tr in trs]
    test("§8B-MF5: exactly three tool_results", len(trs) == 3, reason=str(len(trs)))
    test("§8B-MF5b: tool_names correct & ordered",
         names == ["gex_dex_signals", "dark_pool_signal", "money_flow_confidence"],
         reason=str(names))
finally:
    p.restore()


# ===========================================================================
# §8B-MF6 — run_llm_agent call args: valid_until, horizon, three tool_results
# ===========================================================================
print("\n§8B-MF6: run_llm_agent call args")
cap6 = _Capture()
p = _patch()
try:
    p.set(mof_mod, "fetch_options_chain", lambda *a, **k: object())
    p.set(gex_dex_mod, "compute_gex_dex",
          lambda *a, **k: _gex("negative", "negative"))
    p.set(quiver_mod, "compute_dark_pool_signal",
          lambda *a, **k: _dark_pool("bearish", "moderate"))
    p.set(agent_runner_mod, "run_llm_agent", cap6)
    run_money_flow_agent(ticker="SPY")
    kw = cap6.kwargs or {}
    test("§8B-MF6: horizon == 'cross'", kw.get("horizon") == "cross",
         reason=str(kw.get("horizon")))
    test("§8B-MF6b: valid_until == end_of_today_iso()",
         kw.get("valid_until") == end_of_today_iso(), reason=str(kw.get("valid_until")))
    test("§8B-MF6c: three tool_results", len(kw.get("tool_results", [])) == 3,
         reason=str(len(kw.get("tool_results", []))))
    test("§8B-MF6d: agent_id == 'MoneyFlowAgent'",
         kw.get("agent_id") == "MoneyFlowAgent", reason=str(kw.get("agent_id")))
    test("§8B-MF6e: max_tokens == 1024", kw.get("max_tokens") == 1024,
         reason=str(kw.get("max_tokens")))
finally:
    p.restore()


# ===========================================================================
# §8B-MF7 — LLM failure -> fallback AgentOutput, no exception
# ===========================================================================
print("\n§8B-MF7: LLM failure -> fallback, no exception propagates")


def _raise_llm(**kw):
    raise Exception("claude_unavailable")


p = _patch()
try:
    p.set(mof_mod, "fetch_options_chain", lambda *a, **k: object())
    p.set(gex_dex_mod, "compute_gex_dex",
          lambda *a, **k: _gex("positive", "positive"))
    p.set(quiver_mod, "compute_dark_pool_signal",
          lambda *a, **k: _dark_pool("bullish", "strong"))
    p.set(agent_runner_mod, "run_llm_agent", _raise_llm)
    # Suppress the fallback's disk write so the suite leaves no stray output.
    p.set(agent_runner_mod, "append_agent_output", lambda *a, **k: "")
    raised7 = None
    out7 = None
    try:
        out7 = run_money_flow_agent(ticker="SPY")
    except Exception as e:  # noqa: BLE001
        raised7 = e
    test("§8B-MF7: no exception raised to caller", raised7 is None, reason=str(raised7))
    test("§8B-MF7b: returns an AgentOutput (fallback)",
         isinstance(out7, AgentOutput), reason=str(type(out7)))
    test("§8B-MF7c: fallback judgment_source == 'rule_based'",
         out7 is not None and out7.judgment_source == "rule_based",
         reason="" if out7 is None else out7.judgment_source)
finally:
    p.restore()


# ===========================================================================
# §8B-MF8 — _load_prior_gex_dex_result -> None on cold start
# ===========================================================================
print("\n§8B-MF8: _load_prior_gex_dex_result cold start -> None")
with tempfile.TemporaryDirectory() as tmp:
    prior8 = _load_prior_gex_dex_result(tmp, "SPY")
    test("§8B-MF8: no prior dir/file -> None", prior8 is None, reason=str(prior8))

import json as _json8

# §8B-MF8b — supporting_data present but missing ONE required field -> None
# (no silent default of a fabricated prior state).
print("\n§8B-MF8b: missing one required field -> None")
with tempfile.TemporaryDirectory() as tmp:
    out_dir = os.path.join(tmp, "MoneyFlowAgent")
    os.makedirs(out_dir, exist_ok=True)
    # Every required field EXCEPT "gex_sign" (deliberately omitted).
    rec_missing = {
        "agent_id": "MoneyFlowAgent",
        "timestamp": "2026-06-20T00:00:00+00:00",
        "supporting_data": {
            "ticker": "SPY",
            "gex_total": 100.0,
            "dex_total": -50.0,
            # "gex_sign" intentionally absent
            "dex_sign": "negative",
            "call_wall": 110.0,
            "put_wall": 90.0,
            "squeeze_probability": "mid",
            "squeeze_direction": "down",
            "contracts_used": 10,
            "degraded": False,
        },
    }
    with open(os.path.join(out_dir, "2026-06-20.jsonl"), "w", encoding="utf-8") as fh:
        fh.write(_json8.dumps(rec_missing) + "\n")
    prior8b = _load_prior_gex_dex_result(tmp, "SPY")
    test("§8B-MF8b: missing 'gex_sign' -> None (no reconstruction)",
         prior8b is None, reason=str(type(prior8b)))

# §8B-MF8c — JSONL file exists but is invalid JSON -> None (fail-closed; does NOT
# fall through to older files: only one file present, must not return a default).
print("\n§8B-MF8c: invalid-JSON file -> None (fail-closed)")
with tempfile.TemporaryDirectory() as tmp:
    out_dir = os.path.join(tmp, "MoneyFlowAgent")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "2026-06-20.jsonl"), "w", encoding="utf-8") as fh:
        fh.write("{ this is not valid json ]\n")
    prior8c = _load_prior_gex_dex_result(tmp, "SPY")
    test("§8B-MF8c: invalid JSON -> None (not a default GexDexResult)",
         prior8c is None, reason=str(type(prior8c)))


# ===========================================================================
# §8B-MF9 — _load_prior_gex_dex_result reconstructs from fixture JSONL
# ===========================================================================
print("\n§8B-MF9: _load_prior_gex_dex_result reconstructs GexDexResult")
import json as _json
with tempfile.TemporaryDirectory() as tmp:
    out_dir = os.path.join(tmp, "MoneyFlowAgent")
    os.makedirs(out_dir, exist_ok=True)
    rec = {
        "agent_id": "MoneyFlowAgent",
        "timestamp": "2026-06-20T00:00:00+00:00",
        "supporting_data": {
            "ticker": "SPY",
            "gex_total": 12345.0,
            "dex_total": -6789.0,
            "gex_sign": "positive",
            "dex_sign": "negative",
            "call_wall": 110.0,
            "put_wall": 90.0,
            "squeeze_probability": "mid",
            "squeeze_direction": "down",
            "contracts_used": 42,
            "degraded": False,
        },
    }
    with open(os.path.join(out_dir, "2026-06-20.jsonl"), "w", encoding="utf-8") as fh:
        fh.write(_json.dumps(rec) + "\n")
    prior9 = _load_prior_gex_dex_result(tmp, "SPY")
    test("§8B-MF9: returns a GexDexResult", isinstance(prior9, GexDexResult),
         reason=str(type(prior9)))
    test("§8B-MF9b: dex_total reconstructed (used by squeeze condition C)",
         prior9 is not None and prior9.dex_total == -6789.0,
         reason="" if prior9 is None else str(prior9.dex_total))
    test("§8B-MF9c: gex_total reconstructed",
         prior9 is not None and prior9.gex_total == 12345.0,
         reason="" if prior9 is None else str(prior9.gex_total))
    test("§8B-MF9d: squeeze_probability reconstructed",
         prior9 is not None and prior9.squeeze_probability == "mid",
         reason="" if prior9 is None else prior9.squeeze_probability)
    # Wrong-ticker query must NOT match this SPY record -> None.
    prior9_miss = _load_prior_gex_dex_result(tmp, "QQQ")
    test("§8B-MF9e (discriminating): wrong ticker -> None",
         prior9_miss is None, reason=str(prior9_miss))
    # A record missing required fields -> None (fail-closed).
    out_dir2 = os.path.join(tmp, "MoneyFlowAgent")
    with open(os.path.join(out_dir2, "2026-06-21.jsonl"), "w", encoding="utf-8") as fh:
        fh.write(_json.dumps({"supporting_data": {"ticker": "SPY"}}) + "\n")
    prior9_missing = _load_prior_gex_dex_result(tmp, "SPY")
    test("§8B-MF9f (discriminating): most-recent record missing fields -> None",
         prior9_missing is None, reason=str(prior9_missing))


# ===========================================================================
# §8B-MF10 — supporting_data carries all GexDexResult fields for reconstruction
# ===========================================================================
print("\n§8B-MF10: supporting_data carries prior-reconstruction fields")
cap10 = _Capture()
p = _patch()
try:
    p.set(mof_mod, "fetch_options_chain", lambda *a, **k: object())
    p.set(gex_dex_mod, "compute_gex_dex",
          lambda *a, **k: _gex("positive", "negative", call_wall=111.0, put_wall=95.0,
                               squeeze_probability="high", squeeze_direction="up",
                               contracts_used=7))
    p.set(quiver_mod, "compute_dark_pool_signal",
          lambda *a, **k: _dark_pool("bullish", "moderate"))
    p.set(agent_runner_mod, "run_llm_agent", cap10)
    run_money_flow_agent(ticker="SPY")
    sd = (cap10.kwargs or {}).get("supporting_data", {})
    required = [
        "ticker", "gex_total", "dex_total", "gex_sign", "dex_sign",
        "call_wall", "put_wall", "squeeze_probability", "squeeze_direction",
        "contracts_used", "degraded", "dark_pool_direction", "dark_pool_strength",
    ]
    missing = [k for k in required if k not in sd]
    test("§8B-MF10: all reconstruction fields present", not missing,
         reason="missing: " + str(missing))
    test("§8B-MF10b: dark_pool_direction echoed",
         sd.get("dark_pool_direction") == "bullish",
         reason=str(sd.get("dark_pool_direction")))
finally:
    p.restore()


# ===========================================================================
# §8B-MF11 — short_confidence mutation probe: signals_agree_count==2
# ===========================================================================
print("\n§8B-MF11: short_confidence discriminating at count==2")
# Two usable signals (gex+dex directional, non-degraded) and dark pool neutral
# (zero) -> count==2 -> 0.666667: must be neither 1.0 nor 0.0.
g11 = _gex(gex_sign="positive", dex_sign="negative", degraded=False)
dp11 = _dark_pool("neutral", "none", degraded=False)
cnt11 = _short_signal_count(g11, dp11)
sc11 = _compute_short_confidence(g11, dp11)
test("§8B-MF11: signals_agree_count == 2", cnt11 == 2, reason=str(cnt11))
test("§8B-MF11b: confidence != 1.0 and != 0.0",
     sc11 != 1.0 and sc11 != 0.0, reason=str(sc11))
test("§8B-MF11c: confidence == round(2/3, 6)",
     abs(sc11 - round(2 / 3.0, 6)) < 1e-9, reason=str(sc11))


# ── Final summary ──────────────────────────────────────────────────────────

print(f"\n{'=' * 60}")
print(f"Phase 8B MoneyFlowAgent Tests: {PASS} passed, {FAIL} failed")
if ERRORS:
    print("\nFailures:")
    for err in ERRORS:
        print(f"  - {err}")
print("=" * 60)

sys.exit(0 if FAIL == 0 else 1)
