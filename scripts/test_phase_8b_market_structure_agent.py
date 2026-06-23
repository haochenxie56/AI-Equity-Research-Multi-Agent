"""
scripts/test_phase_8b_market_structure_agent.py

Phase 8B — MarketStructureAgent production implementation, test suite.

Directly runnable (project hand-rolled harness, NOT pytest):
    wsl.exe -d ubuntu -- bash -lc 'python3 scripts/test_phase_8b_market_structure_agent.py'

Discipline (mirrors test_phase_8b_money_flow_agent.py):
  * All LLM calls are mocked at the ``run_llm_agent`` SOURCE module
    (``lib.agent_framework.agent_runner``) — no Claude is ever hit. Because the
    agent imports its dependencies LAZILY, patching the source module is what
    makes the patched callable visible to the lazy ``from ... import``.
  * ``create_run_context`` is patched at its SOURCE
    (``lib.reliability.run_context``) with a no-disk stub so the suite leaves no
    stray ``research/runs/`` directory.
  * Fixtures are REAL ``FragilityReading`` / ``FragilityComponents`` dataclasses,
    never raw dicts. Field VALUES are kept physically plausible: a reading whose
    five CORE data components are all degraded carries at most the weak_bounce
    point (the only non-core scorer), never a fabricated higher points count.
"""

import os
import sys

# ── Repo root on path ──────────────────────────────────────────────────────
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ── Imports under test ─────────────────────────────────────────────────────
import lib.agents.market_structure_agent as agent_mod
from lib.agents.market_structure_agent import (
    _compute_short_confidence,
    _compute_mid_confidence,
    _compute_long_confidence,
    _compute_signal_basis,
    _coverage,
    _clarity,
    _trailing_elevated_run,
    run_market_structure_agent,
    end_of_today_iso,
)
from lib.market_internals import FragilityReading, FragilityComponents
from lib.agent_framework.agent_output import AgentOutput
import lib.agent_framework.agent_runner as agent_runner_mod
import lib.reliability.run_context as run_context_mod


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


# ── The five CORE degrade codes (mirror the agent module) ───────────────────
_CORE = ["distribution_days", "breadth", "earnings_reaction",
         "offense_defense", "leading_theme_volume"]


# ── Fixtures (real FragilityReading / FragilityComponents dataclasses) ───────

def _reading(
    *,
    level: str = "normal",
    raw_level: str | None = None,
    points: int = 0,
    triggered=None,
    degraded=None,
    rolling_raw_series=None,
    vintage_mismatch: bool = False,
    hysteresis_source: str = "rolling",
    consecutive_raw: int = 1,
    earnings_degrade_reason: str = "",
    adjacency_degraded: bool = False,
    data_vintage: str = "2026-06-20",
    **comp_kw,
) -> FragilityReading:
    """A REAL FragilityReading. Component values are supplied as keyword args
    (forwarded into a real FragilityComponents)."""
    series = list(rolling_raw_series or [])
    return FragilityReading(
        level=level,
        raw_level=raw_level if raw_level is not None else level,
        points=points,
        triggered=list(triggered or []),
        components=FragilityComponents(**comp_kw),
        degraded=list(degraded or []),
        consecutive_raw=consecutive_raw,
        adjacency_degraded=adjacency_degraded,
        earnings_degrade_reason=earnings_degrade_reason,
        hysteresis_source=hysteresis_source,
        rolling_window=len(series),
        rolling_raw_series=series,
        data_vintage=data_vintage,
        vintage_mismatch=vintage_mismatch,
    )


def _series(*levels) -> list:
    """Build a rolling_raw_series of (date, raw_level, points) tuples."""
    out = []
    for i, lv in enumerate(levels):
        pts = {"normal": 0, "elevated": 2, "high": 4}.get(lv, 0)
        out.append((f"2026-06-{i + 1:02d}", lv, pts))
    return out


def _fake_agent_output(**kwargs) -> AgentOutput:
    """Stand-in for run_llm_agent: echoes supporting_data onto a minimal valid
    AgentOutput so tests can read deterministically-computed fields."""
    return AgentOutput(
        agent_id=kwargs.get("agent_id", "MarketStructureAgent"),
        timestamp="2026-06-20T00:00:00+00:00",
        horizon=kwargs.get("horizon", "cross"),
        judgment="Market structure deteriorating; wait for confirmation before adding.",
        confidence=0.5,
        evidence_refs=[],
        supporting_data=kwargs.get("supporting_data", {}),
        requires_human_confirmation=kwargs.get("requires_human_confirmation", True),
        judgment_source=kwargs.get("judgment_source", "llm_proposed"),
        valid_until=kwargs.get("valid_until", ""),
    )


class _FakeCtx:
    """No-disk stand-in for a RunContext (only run_id is consumed downstream)."""

    def __init__(self, run_id: str = "TEST_MS_20260622_000000_abcd"):
        self.run_id = run_id


def _fake_create_run_context(*a, **k):
    return _FakeCtx()


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


class _Capture:
    """A capturing run_llm_agent fake: records the kwargs it was called with."""

    def __init__(self):
        self.kwargs = None

    def __call__(self, **kw):
        self.kwargs = kw
        return _fake_agent_output(**kw)


def _run_capture(reading) -> _Capture:
    """Run the agent with run_llm_agent + create_run_context patched; return the
    capture so the caller can inspect tool_results / call kwargs."""
    cap = _Capture()
    p = _patch()
    try:
        p.set(agent_runner_mod, "run_llm_agent", cap)
        p.set(run_context_mod, "create_run_context", _fake_create_run_context)
        run_market_structure_agent(
            reading=reading,
            fragility_series=list(reading.rolling_raw_series),
        )
    finally:
        p.restore()
    return cap


# ===========================================================================
# §8B-MS1 — short_confidence == 0.0 when points=0 and degraded=[]
#           (full_data_no_signal — NOT a degraded path)
# ===========================================================================
print("\n§8B-MS1: points=0, degraded=[] -> short=0.0, basis=full_data_no_signal")
r1 = _reading(level="normal", points=0, triggered=[], degraded=[])
sc1 = _compute_short_confidence(r1)
test("§8B-MS1: short_confidence == 0.0", sc1 == 0.0, reason=str(sc1))
test("§8B-MS1b: coverage == 1.0 (no degrade)", _coverage(r1) == 1.0,
     reason=str(_coverage(r1)))
test("§8B-MS1c: signal_basis == 'full_data_no_signal'",
     _compute_signal_basis(r1) == "full_data_no_signal",
     reason=_compute_signal_basis(r1))


# ===========================================================================
# §8B-MS2 — short_confidence == 0.0 when all 5 core components degraded;
#           signal_basis == 'degraded_insufficient'; mutation probe on coverage
# ===========================================================================
print("\n§8B-MS2: all 5 core degraded -> short=0.0, basis=degraded_insufficient")
r2 = _reading(level="normal", points=0, triggered=[], degraded=list(_CORE))
sc2 = _compute_short_confidence(r2)
test("§8B-MS2: short_confidence == 0.0", sc2 == 0.0, reason=str(sc2))
test("§8B-MS2b: coverage == 0.0 (all core degraded)", _coverage(r2) == 0.0,
     reason=str(_coverage(r2)))
test("§8B-MS2c: signal_basis == 'degraded_insufficient'",
     _compute_signal_basis(r2) == "degraded_insufficient",
     reason=_compute_signal_basis(r2))
# Mutation probe: weak_bounce (a NON-core scorer) fires -> points=1 -> clarity>0,
# so coverage now propagates into short_confidence. With all 5 core degraded:
# coverage=0 -> short=0.0. Remove ONE core degrade code -> coverage=0.2 ->
# short=0.2*0.25=0.05. Removing a degrade code MUST change short_confidence.
print("\n§8B-MS2 (mutation probe): removing a core degrade code changes short")
r2m_all = _reading(points=1, triggered=["weak_bounce"], degraded=list(_CORE),
                   weak_bounce=True)
r2m_four = _reading(points=1, triggered=["weak_bounce"], degraded=list(_CORE[1:]),
                    weak_bounce=True)
sc2m_all = _compute_short_confidence(r2m_all)
sc2m_four = _compute_short_confidence(r2m_four)
test("§8B-MS2d: all-core-degraded probe -> short == 0.0", sc2m_all == 0.0,
     reason=str(sc2m_all))
test("§8B-MS2e (discriminating): drop one degrade code -> short changes",
     sc2m_four != sc2m_all and abs(sc2m_four - 0.05) < 1e-9,
     reason=f"all={sc2m_all} four={sc2m_four}")


# ===========================================================================
# §8B-MS3 — short_confidence -> 1.0 when points=4, triggered non-empty, degraded=[]
# ===========================================================================
print("\n§8B-MS3: points=4, triggered, degraded=[] -> short=1.0")
r3 = _reading(level="high", points=4,
              triggered=["distribution_days_high", "breadth_weak"], degraded=[])
sc3 = _compute_short_confidence(r3)
test("§8B-MS3: short_confidence == 1.0", sc3 == 1.0, reason=str(sc3))
test("§8B-MS3b: clarity == 1.0", _clarity(r3) == 1.0, reason=str(_clarity(r3)))


# ===========================================================================
# §8B-MS4 — short_confidence saturates at points >= _HIGH_POINTS_THRESHOLD
# ===========================================================================
print("\n§8B-MS4: points=6 gives same clarity as points=4 (saturation)")
r4a = _reading(level="high", points=4, triggered=["a", "b"], degraded=[])
r4b = _reading(level="high", points=6, triggered=["a", "b", "c"], degraded=[])
test("§8B-MS4: clarity(points=6) == clarity(points=4)",
     _clarity(r4b) == _clarity(r4a) == 1.0,
     reason=f"4->{_clarity(r4a)} 6->{_clarity(r4b)}")
test("§8B-MS4b: short(points=6) == short(points=4)",
     _compute_short_confidence(r4b) == _compute_short_confidence(r4a),
     reason=f"4->{_compute_short_confidence(r4a)} 6->{_compute_short_confidence(r4b)}")


# ===========================================================================
# §8B-MS5 — mid_confidence == 0.0 when rolling_raw_series is empty
# ===========================================================================
print("\n§8B-MS5: empty rolling_raw_series -> mid=0.0")
r5 = _reading(rolling_raw_series=[])
test("§8B-MS5: mid_confidence == 0.0", _compute_mid_confidence(r5) == 0.0,
     reason=str(_compute_mid_confidence(r5)))


# ===========================================================================
# §8B-MS6 — the degraded-path 0.1 is a CAP, not a floor: the trailing run is
#           still interpolated, then clamped to <= 0.1. A flat normal trail
#           (run 0) must yield 0.0, never 0.1.
# ===========================================================================
print("\n§8B-MS6: degraded path caps mid at 0.1 (not a floor)")
# 6a: vintage_mismatch BUT a flat normal trail (run 0) must still be 0.0.
r6a = _reading(rolling_raw_series=_series("normal", "normal", "normal"),
               vintage_mismatch=True, hysteresis_source="rolling")
test("§8B-MS6a: vintage_mismatch + trailing_run==0 -> mid==0.0",
     _trailing_elevated_run(r6a) == 0 and _compute_mid_confidence(r6a) == 0.0,
     reason=f"run={_trailing_elevated_run(r6a)} mid={_compute_mid_confidence(r6a)}")
# 6b: vintage_mismatch + run 2 -> min(0.4, 0.1) == 0.1 (cap applies).
r6b = _reading(rolling_raw_series=_series("normal", "elevated", "elevated"),
               vintage_mismatch=True, hysteresis_source="rolling")
test("§8B-MS6b: vintage_mismatch + trailing_run==2 -> mid==0.1 (capped)",
     _trailing_elevated_run(r6b) == 2 and _compute_mid_confidence(r6b) == 0.1,
     reason=f"run={_trailing_elevated_run(r6b)} mid={_compute_mid_confidence(r6b)}")
# 6c: clean rolling path, run 2 -> 0.4 (cap does NOT apply on the clean path).
r6c = _reading(rolling_raw_series=_series("normal", "elevated", "elevated"),
               vintage_mismatch=False, hysteresis_source="rolling")
test("§8B-MS6c: clean rolling + trailing_run==2 -> mid==0.4 (no cap)",
     _trailing_elevated_run(r6c) == 2 and _compute_mid_confidence(r6c) == 0.4,
     reason=f"run={_trailing_elevated_run(r6c)} mid={_compute_mid_confidence(r6c)}")
# 6d (discriminating): the snapshot fallback (hysteresis_source != "rolling")
# triggers the same cap — run 2 -> 0.1 — while a snapshot fallback with run 0
# still yields 0.0 (proving the cap is not a floor on the fallback path either).
r6d = _reading(rolling_raw_series=_series("normal", "elevated", "elevated"),
               vintage_mismatch=False, hysteresis_source="snapshot")
test("§8B-MS6d (discriminating): snapshot source caps run==2 at 0.1",
     _compute_mid_confidence(r6d) == 0.1, reason=str(_compute_mid_confidence(r6d)))
r6e = _reading(rolling_raw_series=_series("normal", "normal"),
               vintage_mismatch=False, hysteresis_source="snapshot")
test("§8B-MS6e (discriminating): snapshot source run==0 -> 0.0 (cap not floor)",
     _compute_mid_confidence(r6e) == 0.0, reason=str(_compute_mid_confidence(r6e)))


# ===========================================================================
# §8B-MS7 — mid_confidence interpolates: run=2->0.4, run=4->0.7, run>=6->1.0
# ===========================================================================
print("\n§8B-MS7: trailing-run interpolation")
# run=2: two trailing elevated+ after a leading normal.
r7a = _reading(rolling_raw_series=_series("normal", "elevated", "elevated"),
               hysteresis_source="rolling")
test("§8B-MS7: trailing_run==2 -> mid==0.4",
     _trailing_elevated_run(r7a) == 2 and _compute_mid_confidence(r7a) == 0.4,
     reason=f"run={_trailing_elevated_run(r7a)} mid={_compute_mid_confidence(r7a)}")
# run=4
r7b = _reading(
    rolling_raw_series=_series("normal", "elevated", "elevated", "high", "elevated"),
    hysteresis_source="rolling")
test("§8B-MS7b: trailing_run==4 -> mid==0.7",
     _trailing_elevated_run(r7b) == 4 and _compute_mid_confidence(r7b) == 0.7,
     reason=f"run={_trailing_elevated_run(r7b)} mid={_compute_mid_confidence(r7b)}")
# run>=6 (7 trailing elevated+) -> clamp 1.0
r7c = _reading(
    rolling_raw_series=_series("elevated", "elevated", "elevated", "elevated",
                               "elevated", "elevated", "high"),
    hysteresis_source="rolling")
test("§8B-MS7c: trailing_run>=6 -> mid==1.0",
     _trailing_elevated_run(r7c) >= 6 and _compute_mid_confidence(r7c) == 1.0,
     reason=f"run={_trailing_elevated_run(r7c)} mid={_compute_mid_confidence(r7c)}")
# Discriminating: a trailing normal breaks the run -> run=0 -> 0.0.
r7d = _reading(rolling_raw_series=_series("elevated", "elevated", "normal"),
               hysteresis_source="rolling")
test("§8B-MS7d (discriminating): trailing normal breaks run -> mid==0.0",
     _trailing_elevated_run(r7d) == 0 and _compute_mid_confidence(r7d) == 0.0,
     reason=f"run={_trailing_elevated_run(r7d)} mid={_compute_mid_confidence(r7d)}")


# ===========================================================================
# §8B-MS8 — long_confidence always 0.0
# ===========================================================================
print("\n§8B-MS8: long_confidence always 0.0")
test("§8B-MS8: _compute_long_confidence() == 0.0",
     _compute_long_confidence() == 0.0)


# ===========================================================================
# §8B-MS9 — three ToolResults with correct tool_names (ordered)
# ===========================================================================
print("\n§8B-MS9: three ToolResults with correct tool_names")
cap9 = _run_capture(_reading(level="high", points=4, triggered=["a", "b"]))
trs9 = (cap9.kwargs or {}).get("tool_results", [])
names9 = [getattr(tr, "tool_name", None) for tr in trs9]
test("§8B-MS9: exactly three tool_results", len(trs9) == 3, reason=str(len(trs9)))
test("§8B-MS9b: tool_names correct & ordered",
     names9 == ["market_fragility_signals", "market_fragility_health",
                "market_structure_confidence"],
     reason=str(names9))


# ===========================================================================
# §8B-MS10 — TR2 payload carries signal_basis with correct value per case
# ===========================================================================
print("\n§8B-MS10: TR2 (health) signal_basis correct for all three cases")
cases10 = [
    ("signal_present",
     _reading(level="high", points=4, triggered=["distribution_days_high"])),
    ("degraded_insufficient",
     _reading(points=0, triggered=[], degraded=list(_CORE))),
    ("full_data_no_signal",
     _reading(points=0, triggered=[], degraded=[])),
]
for expected, rdg in cases10:
    cap = _run_capture(rdg)
    trs = (cap.kwargs or {}).get("tool_results", [])
    tr2 = trs[1] if len(trs) > 1 else None
    basis = getattr(tr2, "outputs", {}).get("signal_basis") if tr2 else None
    test(f"§8B-MS10: TR2 tool_name == market_fragility_health ({expected})",
         getattr(tr2, "tool_name", None) == "market_fragility_health",
         reason=str(getattr(tr2, "tool_name", None)))
    test(f"§8B-MS10: TR2.signal_basis == '{expected}'", basis == expected,
         reason=str(basis))


# ===========================================================================
# §8B-MS11 — run_llm_agent call args: agent_id, horizon, valid_until, 3 TRs
# ===========================================================================
print("\n§8B-MS11: run_llm_agent call args")
cap11 = _run_capture(_reading(level="elevated", points=2, triggered=["a", "b"]))
kw11 = cap11.kwargs or {}
test("§8B-MS11: agent_id == 'MarketStructureAgent'",
     kw11.get("agent_id") == "MarketStructureAgent", reason=str(kw11.get("agent_id")))
test("§8B-MS11b: horizon == 'cross'", kw11.get("horizon") == "cross",
     reason=str(kw11.get("horizon")))
test("§8B-MS11c: valid_until == end_of_today_iso()",
     kw11.get("valid_until") == end_of_today_iso(), reason=str(kw11.get("valid_until")))
test("§8B-MS11d: three tool_results", len(kw11.get("tool_results", [])) == 3,
     reason=str(len(kw11.get("tool_results", []))))
test("§8B-MS11e: max_tokens == 1024", kw11.get("max_tokens") == 1024,
     reason=str(kw11.get("max_tokens")))
test("§8B-MS11f: requires_human_confirmation True",
     kw11.get("requires_human_confirmation") is True,
     reason=str(kw11.get("requires_human_confirmation")))
test("§8B-MS11g: judgment_source == 'llm_proposed'",
     kw11.get("judgment_source") == "llm_proposed",
     reason=str(kw11.get("judgment_source")))


# ===========================================================================
# §8B-MS12 — LLM failure -> fallback AgentOutput, no exception propagates
# ===========================================================================
print("\n§8B-MS12: LLM failure -> fallback, no exception propagates")


def _raise_llm(**kw):
    raise Exception("claude_unavailable")


p = _patch()
try:
    p.set(agent_runner_mod, "run_llm_agent", _raise_llm)
    p.set(run_context_mod, "create_run_context", _fake_create_run_context)
    # Suppress the fallback's disk write so the suite leaves no stray output.
    p.set(agent_runner_mod, "append_agent_output", lambda *a, **k: "")
    raised12 = None
    out12 = None
    try:
        out12 = run_market_structure_agent(
            reading=_reading(level="normal", points=0),
            fragility_series=[],
        )
    except Exception as e:  # noqa: BLE001
        raised12 = e
    test("§8B-MS12: no exception raised to caller", raised12 is None,
         reason=str(raised12))
    test("§8B-MS12b: returns an AgentOutput (fallback)",
         isinstance(out12, AgentOutput), reason=str(type(out12)))
    test("§8B-MS12c: fallback judgment_source == 'rule_based'",
         out12 is not None and out12.judgment_source == "rule_based",
         reason="" if out12 is None else out12.judgment_source)
finally:
    p.restore()


# ===========================================================================
# §8B-MS13 — short_confidence mutation probe: points=2, degraded=[] -> 0.5
# ===========================================================================
print("\n§8B-MS13: short_confidence discriminating at points=2, degraded=[]")
r13 = _reading(level="elevated", points=2, triggered=["a", "b"], degraded=[])
sc13 = _compute_short_confidence(r13)
test("§8B-MS13: short != 0.0 and short != 1.0", sc13 != 0.0 and sc13 != 1.0,
     reason=str(sc13))
test("§8B-MS13b: short == 0.5 (coverage 1.0 x clarity 0.5)",
     abs(sc13 - 0.5) < 1e-9, reason=str(sc13))
# Discriminating both terms: drop coverage AND clarity independently.
r13_cov = _reading(level="elevated", points=2, triggered=["a", "b"],
                   degraded=[_CORE[0]])           # coverage 0.8
test("§8B-MS13c (discriminating): one degrade -> short == 0.8*0.5 == 0.4",
     abs(_compute_short_confidence(r13_cov) - 0.4) < 1e-9,
     reason=str(_compute_short_confidence(r13_cov)))


# ── Final summary ──────────────────────────────────────────────────────────

print(f"\n{'=' * 60}")
print(f"Phase 8B MarketStructureAgent Tests: {PASS} passed, {FAIL} failed")
if ERRORS:
    print("\nFailures:")
    for err in ERRORS:
        print(f"  - {err}")
print("=" * 60)

sys.exit(0 if FAIL == 0 else 1)
