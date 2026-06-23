"""
scripts/test_phase_8b_sector_rotation_agent.py

Phase 8B — SectorRotationAgent production implementation, test suite.

Directly runnable (project hand-rolled harness, NOT pytest):
    wsl.exe -d ubuntu -- bash -lc 'python3 scripts/test_phase_8b_sector_rotation_agent.py'

Discipline (mirrors test_phase_8b_market_structure_agent.py):
  * All LLM calls are mocked at the ``run_llm_agent`` SOURCE module
    (``lib.agent_framework.agent_runner``) — no Claude is ever hit. Because the
    agent imports its dependencies LAZILY, patching the source module is what
    makes the patched callable visible to the lazy ``from ... import``.
  * ``create_run_context`` is patched at its SOURCE
    (``lib.reliability.run_context``) with a no-disk stub so the suite leaves no
    stray ``research/runs/`` directory.
  * Fixtures are REAL ``ThemeMomentumResult`` dataclasses, never raw dicts.
  * The confidence-function unit tests pass a hand-built ``diffusion`` dict so
    ``active_order`` is controlled directly; the full-agent integration tests use
    real theme_keys so ``get_diffusion_context`` (pure arithmetic) runs for real.
"""

import os
import sys

# ── Repo root on path ──────────────────────────────────────────────────────
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ── Imports under test ─────────────────────────────────────────────────────
from lib.agents.sector_rotation_agent import (
    _compute_short_confidence,
    _compute_mid_confidence,
    _compute_long_confidence,
    _compute_signal_basis,
    _theme_coverage,
    _short_clarity,
    _dispersion,
    run_sector_rotation_agent,
    end_of_today_iso,
)
from lib.theme_baskets import ThemeMomentumResult
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


# ── Fixtures (real ThemeMomentumResult dataclasses) ─────────────────────────

def _theme(theme_key: str, *, data_source: str = "etf", stage: str = "",
           stage_confirmed: bool = False, momentum_score: float = 0.0,
           excess_3m=None, breadth_beat_pct=None) -> ThemeMomentumResult:
    """A REAL ThemeMomentumResult with the fields the agent reads."""
    return ThemeMomentumResult(
        theme_key=theme_key,
        label_en=f"{theme_key} label",
        label_zh=theme_key,
        constituents=["AAA", "BBB"],
        etf=None,
        data_source=data_source,
        stage=stage,
        stage_confirmed=stage_confirmed,
        momentum_score=momentum_score,
        excess_3m=excess_3m,
        breadth_beat_pct=breadth_beat_pct,
    )


def _fake_agent_output(**kwargs) -> AgentOutput:
    """Stand-in for run_llm_agent: echoes supporting_data onto a minimal valid
    AgentOutput so tests can read deterministically-computed fields."""
    return AgentOutput(
        agent_id=kwargs.get("agent_id", "SectorRotationAgent"),
        timestamp="2026-06-20T00:00:00+00:00",
        horizon=kwargs.get("horizon", "cross"),
        judgment="Rotation leadership unclear; wait for confirmation.",
        confidence=0.5,
        evidence_refs=[],
        supporting_data=kwargs.get("supporting_data", {}),
        requires_human_confirmation=kwargs.get("requires_human_confirmation", True),
        judgment_source=kwargs.get("judgment_source", "llm_proposed"),
        valid_until=kwargs.get("valid_until", ""),
    )


class _FakeCtx:
    """No-disk stand-in for a RunContext (only run_id is consumed downstream)."""

    def __init__(self, run_id: str = "TEST_SR_20260622_000000_abcd"):
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


def _run_capture(themes, offense_defense=None) -> _Capture:
    """Run the agent with run_llm_agent + create_run_context patched; return the
    capture so the caller can inspect tool_results / call kwargs."""
    cap = _Capture()
    p = _patch()
    try:
        p.set(agent_runner_mod, "run_llm_agent", cap)
        p.set(run_context_mod, "create_run_context", _fake_create_run_context)
        run_sector_rotation_agent(
            themes=themes,
            offense_defense=offense_defense or {},
        )
    finally:
        p.restore()
    return cap


# Real theme_keys so get_diffusion_context maps them to transmission orders.
def _real_keyed_themes() -> list:
    return [
        _theme("ai_chips", stage="leading", stage_confirmed=True,
               momentum_score=0.9, excess_3m=12.0, breadth_beat_pct=0.7),
        _theme("hbm_memory", stage="rotating_in", stage_confirmed=True,
               momentum_score=0.6, excess_3m=8.0, breadth_beat_pct=0.55),
        _theme("ai_software", stage="out_of_favor", stage_confirmed=False,
               momentum_score=0.1, excess_3m=-2.0, breadth_beat_pct=0.3),
    ]


# ===========================================================================
# §8B-SR1 — short_confidence == 0.0 when all themes are fixture
# ===========================================================================
print("\n§8B-SR1: all fixture -> short=0.0")
sr1_themes = [_theme("ai_chips", data_source="fixture", stage_confirmed=True),
              _theme("hbm_memory", data_source="fixture", stage_confirmed=True)]
sc1 = _compute_short_confidence(sr1_themes, {"active_order": 1})
test("§8B-SR1: short_confidence == 0.0", sc1 == 0.0, reason=str(sc1))


# ===========================================================================
# §8B-SR2 — short_confidence == 0.0 when live themes exist but none confirmed
# ===========================================================================
print("\n§8B-SR2: live but no stage_confirmed -> short=0.0")
sr2_themes = [_theme("ai_chips", stage="leading", stage_confirmed=False),
              _theme("hbm_memory", stage="rotating_out", stage_confirmed=False)]
sc2 = _compute_short_confidence(sr2_themes, {"active_order": 1})
test("§8B-SR2: short_confidence == 0.0", sc2 == 0.0, reason=str(sc2))
test("§8B-SR2b: short_clarity == 0.0", _short_clarity(sr2_themes) == 0.0,
     reason=str(_short_clarity(sr2_themes)))


# ===========================================================================
# §8B-SR3 — short -> 1.0 when all live confirmed & coverage 1.0; mutation probe
# ===========================================================================
print("\n§8B-SR3: all live confirmed, coverage 1.0 -> short=1.0; flip drops it")
sr3_themes = [_theme("ai_chips", stage="leading", stage_confirmed=True),
              _theme("hbm_memory", stage="rotating_in", stage_confirmed=True),
              _theme("ai_software", stage="leading", stage_confirmed=True)]
sc3 = _compute_short_confidence(sr3_themes, {"active_order": 1})
test("§8B-SR3: short_confidence == 1.0", sc3 == 1.0, reason=str(sc3))
test("§8B-SR3b: coverage == 1.0", _theme_coverage(sr3_themes) == 1.0,
     reason=str(_theme_coverage(sr3_themes)))
# Mutation probe: flip ONE theme to fixture -> coverage drops -> short drops.
sr3_mut = [_theme("ai_chips", data_source="fixture", stage="leading",
                  stage_confirmed=True),
           _theme("hbm_memory", stage="rotating_in", stage_confirmed=True),
           _theme("ai_software", stage="leading", stage_confirmed=True)]
sc3m = _compute_short_confidence(sr3_mut, {"active_order": 1})
test("§8B-SR3c (discriminating): flip one to fixture -> short < 1.0",
     sc3m < sc3 and abs(sc3m - round(2 / 3, 6)) < 1e-9, reason=f"full={sc3} mut={sc3m}")


# ===========================================================================
# §8B-SR4 — mid_confidence == 0.0 when diffusion has no active_order
# ===========================================================================
print("\n§8B-SR4: no active_order -> mid=0.0 (wave_clear 0)")
sr4_themes = [_theme("ai_chips", momentum_score=0.9),
              _theme("hbm_memory", momentum_score=0.3)]
mc4 = _compute_mid_confidence(sr4_themes, {"active_order": None})
test("§8B-SR4: mid_confidence == 0.0", mc4 == 0.0, reason=str(mc4))


# ===========================================================================
# §8B-SR5 — mid_confidence == 0.0 when all momentum_score identical
# ===========================================================================
print("\n§8B-SR5: flat momentum field -> mid=0.0 (dispersion 0)")
sr5_themes = [_theme("ai_chips", momentum_score=0.5),
              _theme("hbm_memory", momentum_score=0.5),
              _theme("ai_software", momentum_score=0.5)]
mc5 = _compute_mid_confidence(sr5_themes, {"active_order": 2})
test("§8B-SR5: mid_confidence == 0.0", mc5 == 0.0, reason=str(mc5))
test("§8B-SR5b: dispersion == 0.0", _dispersion(sr5_themes) == 0.0,
     reason=str(_dispersion(sr5_themes)))


# ===========================================================================
# §8B-SR6 — mid > 0 when active_order set AND scores differ; mutation probe
# ===========================================================================
print("\n§8B-SR6: active_order + dispersion -> mid>0; active_order=None drops it")
sr6_themes = [_theme("ai_chips", momentum_score=0.9),
              _theme("hbm_memory", momentum_score=0.5),
              _theme("ai_software", momentum_score=0.1)]
mc6 = _compute_mid_confidence(sr6_themes, {"active_order": 1})
# coverage 1.0 x dispersion (0.9 - 0.5) x wave_clear 1.0 = 0.4
test("§8B-SR6: mid_confidence > 0.0", mc6 > 0.0, reason=str(mc6))
test("§8B-SR6b: mid == 0.4 (coverage 1.0 x dispersion 0.4 x wave 1.0)",
     abs(mc6 - 0.4) < 1e-9, reason=str(mc6))
# Mutation probe: set active_order=None -> wave_clear 0 -> mid 0.0.
mc6m = _compute_mid_confidence(sr6_themes, {"active_order": None})
test("§8B-SR6c (discriminating): active_order=None -> mid drops to 0.0",
     mc6m == 0.0 and mc6m != mc6, reason=f"set={mc6} none={mc6m}")


# ===========================================================================
# §8B-SR7 — long_confidence always 0.0
# ===========================================================================
print("\n§8B-SR7: long_confidence always 0.0")
test("§8B-SR7: _compute_long_confidence() == 0.0", _compute_long_confidence() == 0.0)


# ===========================================================================
# §8B-SR8 — signal_basis 'signal_present' when n_confirmed>0 and active_order set
# ===========================================================================
print("\n§8B-SR8: signal_basis == 'signal_present'")
sr8_themes = [_theme("ai_chips", stage="leading", stage_confirmed=True),
              _theme("hbm_memory", stage="rotating_out", stage_confirmed=False)]
test("§8B-SR8: signal_basis == 'signal_present'",
     _compute_signal_basis(sr8_themes, {"active_order": 1}) == "signal_present",
     reason=_compute_signal_basis(sr8_themes, {"active_order": 1}))


# ===========================================================================
# §8B-SR9 — signal_basis 'degraded_insufficient' when < half themes are live
# ===========================================================================
print("\n§8B-SR9: < half live -> 'degraded_insufficient'")
# 4 themes, only 1 live -> 1 < 4//2 (2) -> degraded_insufficient.
sr9_themes = [_theme("ai_chips", data_source="etf", stage_confirmed=True),
              _theme("hbm_memory", data_source="fixture"),
              _theme("ai_software", data_source="fixture"),
              _theme("cybersecurity", data_source="fixture")]
test("§8B-SR9: signal_basis == 'degraded_insufficient'",
     _compute_signal_basis(sr9_themes, {"active_order": None})
     == "degraded_insufficient",
     reason=_compute_signal_basis(sr9_themes, {"active_order": None}))


# ===========================================================================
# §8B-SR10 — three ToolResults with correct tool_names (ordered)
# ===========================================================================
print("\n§8B-SR10: three ToolResults with correct tool_names")
cap10 = _run_capture(_real_keyed_themes())
trs10 = (cap10.kwargs or {}).get("tool_results", [])
names10 = [getattr(tr, "tool_name", None) for tr in trs10]
test("§8B-SR10: exactly three tool_results", len(trs10) == 3, reason=str(len(trs10)))
test("§8B-SR10b: tool_names correct & ordered",
     names10 == ["sector_rotation_signals", "sector_rotation_health",
                 "sector_rotation_confidence"],
     reason=str(names10))


# ===========================================================================
# §8B-SR11 — TR2 payload contains signal_basis and od_available
# ===========================================================================
print("\n§8B-SR11: TR2 (health) carries signal_basis + od_available")
cap11 = _run_capture(_real_keyed_themes(),
                     offense_defense={"direction": "offense", "magnitude": "moderate"})
trs11 = (cap11.kwargs or {}).get("tool_results", [])
tr2_11 = trs11[1] if len(trs11) > 1 else None
out2_11 = getattr(tr2_11, "outputs", {}) if tr2_11 else {}
test("§8B-SR11: TR2 tool_name == sector_rotation_health",
     getattr(tr2_11, "tool_name", None) == "sector_rotation_health",
     reason=str(getattr(tr2_11, "tool_name", None)))
test("§8B-SR11b: TR2 carries signal_basis", "signal_basis" in out2_11,
     reason=str(list(out2_11.keys())))
test("§8B-SR11c: TR2 od_available is True when O/D dict supplied",
     out2_11.get("od_available") is True, reason=str(out2_11.get("od_available")))


# ===========================================================================
# §8B-SR12 — LLM failure -> fallback AgentOutput, no exception propagates
# ===========================================================================
print("\n§8B-SR12: LLM failure -> fallback, no exception propagates")


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
        out12 = run_sector_rotation_agent(
            themes=_real_keyed_themes(), offense_defense={})
    except Exception as e:  # noqa: BLE001
        raised12 = e
    test("§8B-SR12: no exception raised to caller", raised12 is None,
         reason=str(raised12))
    test("§8B-SR12b: returns an AgentOutput (fallback)",
         isinstance(out12, AgentOutput), reason=str(type(out12)))
    test("§8B-SR12c: fallback judgment_source == 'rule_based'",
         out12 is not None and out12.judgment_source == "rule_based",
         reason="" if out12 is None else out12.judgment_source)
finally:
    p.restore()


# ===========================================================================
# §8B-SR13 — run_llm_agent call args: agent_id, horizon, valid_until, 3 TRs
# ===========================================================================
print("\n§8B-SR13: run_llm_agent call args")
cap13 = _run_capture(_real_keyed_themes())
kw13 = cap13.kwargs or {}
test("§8B-SR13: agent_id == 'SectorRotationAgent'",
     kw13.get("agent_id") == "SectorRotationAgent", reason=str(kw13.get("agent_id")))
test("§8B-SR13b: horizon == 'cross'", kw13.get("horizon") == "cross",
     reason=str(kw13.get("horizon")))
test("§8B-SR13c: valid_until == end_of_today_iso()",
     kw13.get("valid_until") == end_of_today_iso(), reason=str(kw13.get("valid_until")))
test("§8B-SR13d: three tool_results", len(kw13.get("tool_results", [])) == 3,
     reason=str(len(kw13.get("tool_results", []))))
test("§8B-SR13e: max_tokens == 1024", kw13.get("max_tokens") == 1024,
     reason=str(kw13.get("max_tokens")))
test("§8B-SR13f: requires_human_confirmation True",
     kw13.get("requires_human_confirmation") is True,
     reason=str(kw13.get("requires_human_confirmation")))
test("§8B-SR13g: judgment_source == 'llm_proposed'",
     kw13.get("judgment_source") == "llm_proposed",
     reason=str(kw13.get("judgment_source")))


# ===========================================================================
# §8B-SR14 — full offense_defense fields appear in TR1 payload (O/D extension)
# ===========================================================================
print("\n§8B-SR14: TR1 carries od_avg_diff / od_confirming_windows / od_n_windows")
_OD_FULL = {
    "direction": "defense", "magnitude": "moderate",
    "avg_diff": -3.1,
    "by_window": {"1m": {"offense": 1.0, "defense": 4.1, "diff": -3.1}},
    "confirming_windows": ["1m", "3m"],
    "n_windows": 4,
}
cap14 = _run_capture(_real_keyed_themes(), offense_defense=_OD_FULL)
trs14 = (cap14.kwargs or {}).get("tool_results", [])
tr1_14 = trs14[0] if trs14 else None
out1_14 = getattr(tr1_14, "outputs", {}) if tr1_14 else {}
test("§8B-SR14: TR1 tool_name == sector_rotation_signals",
     getattr(tr1_14, "tool_name", None) == "sector_rotation_signals",
     reason=str(getattr(tr1_14, "tool_name", None)))
test("§8B-SR14b: TR1 od_avg_diff == -3.1 (from injected dict)",
     out1_14.get("od_avg_diff") == -3.1, reason=str(out1_14.get("od_avg_diff")))
test("§8B-SR14c: TR1 od_confirming_windows == ['1m','3m']",
     out1_14.get("od_confirming_windows") == ["1m", "3m"],
     reason=str(out1_14.get("od_confirming_windows")))
test("§8B-SR14d: TR1 od_n_windows == 4",
     out1_14.get("od_n_windows") == 4, reason=str(out1_14.get("od_n_windows")))


# ── Final summary ──────────────────────────────────────────────────────────

print(f"\n{'=' * 60}")
print(f"Phase 8B SectorRotationAgent Tests: {PASS} passed, {FAIL} failed")
if ERRORS:
    print("\nFailures:")
    for err in ERRORS:
        print(f"  - {err}")
print("=" * 60)

sys.exit(0 if FAIL == 0 else 1)
