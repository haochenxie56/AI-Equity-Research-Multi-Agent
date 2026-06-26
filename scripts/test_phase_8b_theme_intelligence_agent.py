"""
scripts/test_phase_8b_theme_intelligence_agent.py

Phase 8B — ThemeIntelligenceAgent production implementation, test suite.

Directly runnable (project hand-rolled harness, NOT pytest):
    wsl.exe -d ubuntu -- bash -lc 'python3 scripts/test_phase_8b_theme_intelligence_agent.py'

Discipline (mirrors test_phase_8b_sector_rotation_agent.py):
  * All LLM calls are mocked at the ``run_llm_agent`` SOURCE module
    (``lib.agent_framework.agent_runner``) — no Claude is ever hit. Because the
    agent imports its dependencies LAZILY, patching the source module is what
    makes the patched callable visible to the lazy ``from ... import``.
  * ``create_run_context`` is patched at its SOURCE
    (``lib.reliability.run_context``) with a no-disk stub so the suite leaves no
    stray ``research/runs/`` directory.
  * Fixtures are REAL ``ThemeMomentumResult`` dataclasses with
    ``constituent_rs`` populated, never raw dicts.
  * The role-mutation probe (§8B-TI3) patches ``get_ticker_role`` at its SOURCE
    (``lib.theme_transmission``) so the lazy import inside the agent picks it up.
"""

import os
import sys

# ── Repo root on path ──────────────────────────────────────────────────────
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ── Imports under test ─────────────────────────────────────────────────────
from lib.agents.theme_intelligence_agent import (
    _compute_short_confidence,
    _compute_mid_confidence,
    _compute_long_confidence,
    _compute_signal_basis,
    _rank_theme_constituents,
    run_theme_intelligence_agent,
    end_of_today_iso,
)
from lib.theme_baskets import ThemeMomentumResult
from lib.agent_framework.agent_output import AgentOutput
import lib.agent_framework.agent_runner as agent_runner_mod
import lib.reliability.run_context as run_context_mod
import lib.theme_transmission as tt_mod


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
           constituents=None, constituent_rs=None) -> ThemeMomentumResult:
    """A REAL ThemeMomentumResult with the fields the agent reads."""
    return ThemeMomentumResult(
        theme_key=theme_key,
        label_en=f"{theme_key} label",
        label_zh=theme_key,
        constituents=list(constituents) if constituents is not None else ["AAA", "BBB"],
        etf=None,
        data_source=data_source,
        stage=stage,
        stage_confirmed=stage_confirmed,
        momentum_score=momentum_score,
        constituent_rs=dict(constituent_rs) if constituent_rs is not None else {},
    )


def _fake_agent_output(**kwargs) -> AgentOutput:
    """Stand-in for run_llm_agent: echoes supporting_data onto a minimal valid
    AgentOutput so tests can read deterministically-computed fields."""
    return AgentOutput(
        agent_id=kwargs.get("agent_id", "ThemeIntelligenceAgent"),
        timestamp="2026-06-26T00:00:00+00:00",
        horizon=kwargs.get("horizon", "cross"),
        judgment="Role and asymmetry context assembled; manual review required.",
        confidence=0.5,
        evidence_refs=[],
        supporting_data=kwargs.get("supporting_data", {}),
        requires_human_confirmation=kwargs.get("requires_human_confirmation", True),
        judgment_source=kwargs.get("judgment_source", "llm_proposed"),
        valid_until=kwargs.get("valid_until", ""),
    )


class _FakeCtx:
    """No-disk stand-in for a RunContext (only run_id is consumed downstream)."""

    def __init__(self, run_id: str = "TEST_TI_20260626_000000_abcd"):
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


def _run_capture(themes) -> _Capture:
    """Run the agent with run_llm_agent + create_run_context patched; return the
    capture so the caller can inspect tool_results / call kwargs."""
    cap = _Capture()
    p = _patch()
    try:
        p.set(agent_runner_mod, "run_llm_agent", cap)
        p.set(run_context_mod, "create_run_context", _fake_create_run_context)
        run_theme_intelligence_agent(themes=themes)
    finally:
        p.restore()
    return cap


# Real theme_keys + real role-mapped tickers so get_ticker_role /
# get_transmission_order resolve for real.
def _real_keyed_themes() -> list:
    return [
        # ai_chips: order 1; NVDA/AVGO are seed leaders; rotating_in => asymmetric.
        _theme("ai_chips", data_source="etf", stage="rotating_in",
               stage_confirmed=True, momentum_score=0.9,
               constituents=["NVDA", "AVGO", "AMD"],
               constituent_rs={"NVDA": {"active": 5.0}, "AVGO": {"active": 3.0},
                               "AMD": {"active": 1.0}}),
        # hbm_memory: order 2; MU is a seed leader; leading => crowded contrast.
        _theme("hbm_memory", data_source="etf", stage="leading",
               stage_confirmed=True, momentum_score=0.6,
               constituents=["MU", "WDC"],
               constituent_rs={"MU": {"active": 4.0}, "WDC": {"active": 2.0}}),
        # ai_software: order 3; out_of_favor => crowded contrast, not asymmetric.
        _theme("ai_software", data_source="etf", stage="out_of_favor",
               stage_confirmed=False, momentum_score=0.1,
               constituents=["MSFT", "CRM"],
               constituent_rs={"MSFT": {"active": -1.0}}),
    ]


# ===========================================================================
# §8B-TI1 — short_confidence == 0.0 when all themes are fixture
# ===========================================================================
print("\n§8B-TI1: all fixture -> short=0.0")
ti1_themes = [
    _theme("ai_chips", data_source="fixture",
           constituents=["NVDA"], constituent_rs={"NVDA": {"active": 5.0}}),
    _theme("hbm_memory", data_source="fixture",
           constituents=["MU"], constituent_rs={"MU": {"active": 4.0}}),
]
sc1 = _compute_short_confidence(ti1_themes, {})
test("§8B-TI1: short_confidence == 0.0", sc1 == 0.0, reason=str(sc1))


# ===========================================================================
# §8B-TI2 — short=0.0 when live themes exist but constituent_rs empty on all
# ===========================================================================
print("\n§8B-TI2: live but constituent_rs empty -> short=0.0 (role_resolution 0)")
ti2_themes = [
    _theme("ai_chips", data_source="etf",
           constituents=["NVDA", "AVGO"], constituent_rs={}),
    _theme("hbm_memory", data_source="etf",
           constituents=["MU"], constituent_rs={}),
]
sc2 = _compute_short_confidence(ti2_themes, {})
test("§8B-TI2: short_confidence == 0.0", sc2 == 0.0, reason=str(sc2))


# ===========================================================================
# §8B-TI3 — short > 0 when a live theme has active_excess + non-unknown role;
#           mutation probe: all roles -> "unknown" drops short to 0.0
# ===========================================================================
print("\n§8B-TI3: live + active_excess + named role -> short>0; unknown roles drop it")
ti3_themes = [
    _theme("ai_chips", data_source="etf",
           constituents=["NVDA", "AVGO"],
           constituent_rs={"NVDA": {"active": 5.0}, "AVGO": {"active": 3.0}}),
]
sc3 = _compute_short_confidence(ti3_themes, {})
# coverage 1.0 x role_resolution (2 named / 2 constituents) = 1.0
test("§8B-TI3: short_confidence > 0.0", sc3 > 0.0, reason=str(sc3))
test("§8B-TI3b: short_confidence == 1.0", sc3 == 1.0, reason=str(sc3))
# Mutation probe: force every role to "unknown" at the SOURCE module.
p3 = _patch()
try:
    p3.set(tt_mod, "get_ticker_role", lambda *a, **k: "unknown")
    sc3m = _compute_short_confidence(ti3_themes, {})
finally:
    p3.restore()
test("§8B-TI3c (discriminating): all roles unknown -> short drops to 0.0",
     sc3m == 0.0 and sc3m != sc3, reason=f"named={sc3} unknown={sc3m}")


# ===========================================================================
# §8B-TI4 — mid=0.0 when no live theme is early-wave + rotating_in
# ===========================================================================
print("\n§8B-TI4: no early-wave rotating_in -> mid=0.0")
# ai_software is order 3 (not in {1,2}); stage rotating_in still not asymmetric.
ti4_themes = [
    _theme("ai_software", data_source="etf", stage="rotating_in",
           momentum_score=0.5),
]
mc4 = _compute_mid_confidence(ti4_themes, {})
test("§8B-TI4: mid_confidence == 0.0", mc4 == 0.0, reason=str(mc4))


# ===========================================================================
# §8B-TI5 — mid > 0 when a live theme is wave_order=1 AND rotating_in;
#           mutation probe: stage -> "leading" drops mid to 0.0
# ===========================================================================
print("\n§8B-TI5: wave_order 1 + rotating_in -> mid>0; stage flip drops it")
ti5_themes = [
    _theme("ai_chips", data_source="etf", stage="rotating_in",
           momentum_score=0.9),
]
mc5 = _compute_mid_confidence(ti5_themes, {})
test("§8B-TI5: mid_confidence > 0.0", mc5 > 0.0, reason=str(mc5))
test("§8B-TI5b: mid_confidence == 1.0", mc5 == 1.0, reason=str(mc5))
# Mutation probe: same theme, stage "leading" (not early) -> mid 0.0.
ti5_mut = [
    _theme("ai_chips", data_source="etf", stage="leading", momentum_score=0.9),
]
mc5m = _compute_mid_confidence(ti5_mut, {})
test("§8B-TI5c (discriminating): stage 'leading' -> mid drops to 0.0",
     mc5m == 0.0 and mc5m != mc5, reason=f"rotating_in={mc5} leading={mc5m}")


# ===========================================================================
# §8B-TI6 — long_confidence always 0.0
# ===========================================================================
print("\n§8B-TI6: long_confidence always 0.0")
test("§8B-TI6: _compute_long_confidence() == 0.0", _compute_long_confidence() == 0.0)


# ===========================================================================
# §8B-TI7 — signal_basis three-way classifier
# ===========================================================================
print("\n§8B-TI7: signal_basis present / degraded / no_role_signal")
# (a) signal_present when a confidence is positive.
test("§8B-TI7a: signal_present when short_conf > 0",
     _compute_signal_basis(ti3_themes, {}, 1.0, 0.0) == "signal_present",
     reason=_compute_signal_basis(ti3_themes, {}, 1.0, 0.0))
# (b) degraded_insufficient when fewer than half the themes are live.
#     4 themes, only 1 live -> 1 < 4//2 (2) -> degraded_insufficient.
ti7b_themes = [
    _theme("ai_software", data_source="etf", stage="", momentum_score=0.2),
    _theme("hbm_memory", data_source="fixture"),
    _theme("cybersecurity", data_source="fixture"),
    _theme("edge_ai_devices", data_source="fixture"),
]
test("§8B-TI7b: degraded_insufficient when < half live",
     _compute_signal_basis(ti7b_themes, {}, 0.0, 0.0) == "degraded_insufficient",
     reason=_compute_signal_basis(ti7b_themes, {}, 0.0, 0.0))
# (c) no_role_signal when live (>= half) but both confidences are 0.0.
ti7c_themes = [
    _theme("ai_software", data_source="etf", stage="leading", momentum_score=0.5),
    _theme("hbm_memory", data_source="etf", stage="leading", momentum_score=0.4),
]
test("§8B-TI7c: no_role_signal when live but both confidences 0.0",
     _compute_signal_basis(ti7c_themes, {}, 0.0, 0.0) == "no_role_signal",
     reason=_compute_signal_basis(ti7c_themes, {}, 0.0, 0.0))


# ===========================================================================
# §8B-TI8 — TR1 payload contains top_themes with ranked_constituents
# ===========================================================================
print("\n§8B-TI8: TR1 top_themes carry ranked_constituents")
cap8 = _run_capture(_real_keyed_themes())
trs8 = (cap8.kwargs or {}).get("tool_results", [])
tr1_8 = trs8[0] if trs8 else None
out1_8 = getattr(tr1_8, "outputs", {}) if tr1_8 else {}
test("§8B-TI8: TR1 tool_name == theme_intelligence_roles",
     getattr(tr1_8, "tool_name", None) == "theme_intelligence_roles",
     reason=str(getattr(tr1_8, "tool_name", None)))
test("§8B-TI8b: TR1 has top_themes list", isinstance(out1_8.get("top_themes"), list),
     reason=str(type(out1_8.get("top_themes"))))
_tt8 = out1_8.get("top_themes") or []
test("§8B-TI8c: each top_theme has ranked_constituents",
     all("ranked_constituents" in t for t in _tt8) and len(_tt8) > 0,
     reason=str([list(t.keys()) for t in _tt8]))
# The ai_chips theme (top momentum) should have a non-empty ranking led by NVDA.
_chips8 = next((t for t in _tt8 if t.get("theme_key") == "ai_chips"), None)
test("§8B-TI8d: ai_chips ranked_constituents non-empty, NVDA on top",
     _chips8 is not None and _chips8["ranked_constituents"]
     and _chips8["ranked_constituents"][0]["ticker"] == "NVDA",
     reason=str(_chips8))


# ===========================================================================
# §8B-TI9 — TR2 payload asymmetric_themes; all wave_order in {1,2}, rotating_in
# ===========================================================================
print("\n§8B-TI9: TR2 asymmetric_themes all early-wave + rotating_in")
trs9 = (cap8.kwargs or {}).get("tool_results", [])
tr2_9 = trs9[1] if len(trs9) > 1 else None
out2_9 = getattr(tr2_9, "outputs", {}) if tr2_9 else {}
test("§8B-TI9: TR2 tool_name == theme_intelligence_asymmetry",
     getattr(tr2_9, "tool_name", None) == "theme_intelligence_asymmetry",
     reason=str(getattr(tr2_9, "tool_name", None)))
_asym9 = out2_9.get("asymmetric_themes") or []
test("§8B-TI9b: asymmetric_themes is a list", isinstance(_asym9, list),
     reason=str(type(_asym9)))
# ai_chips (order 1, rotating_in) qualifies; hbm/ai_software do not.
test("§8B-TI9c: exactly ai_chips qualifies as asymmetric",
     [a["theme_key"] for a in _asym9] == ["ai_chips"],
     reason=str([a["theme_key"] for a in _asym9]))
test("§8B-TI9d: all asymmetric entries early-wave + rotating_in",
     all(a["wave_order"] in (1, 2) and a["stage"] == "rotating_in" for a in _asym9),
     reason=str([(a["wave_order"], a["stage"]) for a in _asym9]))
# Late-stage contrast set present (hbm leading + ai_software out_of_favor).
_late9 = out2_9.get("late_stage_themes") or []
test("§8B-TI9e: late_stage_themes present for contrast",
     {l["theme_key"] for l in _late9} == {"hbm_memory", "ai_software"},
     reason=str([l["theme_key"] for l in _late9]))


# ===========================================================================
# §8B-TI10 — three ToolResults with correct tool_names (ordered)
# ===========================================================================
print("\n§8B-TI10: three ToolResults with correct tool_names")
cap10 = _run_capture(_real_keyed_themes())
trs10 = (cap10.kwargs or {}).get("tool_results", [])
names10 = [getattr(tr, "tool_name", None) for tr in trs10]
test("§8B-TI10: exactly three tool_results", len(trs10) == 3, reason=str(len(trs10)))
test("§8B-TI10b: tool_names correct & ordered",
     names10 == ["theme_intelligence_roles", "theme_intelligence_asymmetry",
                 "theme_intelligence_confidence"],
     reason=str(names10))


# ===========================================================================
# §8B-TI11 — run_llm_agent call args: agent_id, horizon, valid_until, 3 TRs
# ===========================================================================
print("\n§8B-TI11: run_llm_agent call args")
cap11 = _run_capture(_real_keyed_themes())
kw11 = cap11.kwargs or {}
test("§8B-TI11: agent_id == 'ThemeIntelligenceAgent'",
     kw11.get("agent_id") == "ThemeIntelligenceAgent",
     reason=str(kw11.get("agent_id")))
test("§8B-TI11b: horizon == 'cross'", kw11.get("horizon") == "cross",
     reason=str(kw11.get("horizon")))
test("§8B-TI11c: valid_until == end_of_today_iso()",
     kw11.get("valid_until") == end_of_today_iso(),
     reason=str(kw11.get("valid_until")))
test("§8B-TI11d: three tool_results", len(kw11.get("tool_results", [])) == 3,
     reason=str(len(kw11.get("tool_results", []))))
test("§8B-TI11e: max_tokens == 1024", kw11.get("max_tokens") == 1024,
     reason=str(kw11.get("max_tokens")))
test("§8B-TI11f: requires_human_confirmation True",
     kw11.get("requires_human_confirmation") is True,
     reason=str(kw11.get("requires_human_confirmation")))
test("§8B-TI11g: judgment_source == 'llm_proposed'",
     kw11.get("judgment_source") == "llm_proposed",
     reason=str(kw11.get("judgment_source")))


# ===========================================================================
# §8B-TI12 — LLM failure -> fallback AgentOutput, no exception propagates
# ===========================================================================
print("\n§8B-TI12: LLM failure -> fallback, no exception propagates")


def _raise_llm(**kw):
    raise Exception("claude_unavailable")


p12 = _patch()
try:
    p12.set(agent_runner_mod, "run_llm_agent", _raise_llm)
    p12.set(run_context_mod, "create_run_context", _fake_create_run_context)
    # Suppress the fallback's disk write so the suite leaves no stray output.
    p12.set(agent_runner_mod, "append_agent_output", lambda *a, **k: "")
    raised12 = None
    out12 = None
    try:
        out12 = run_theme_intelligence_agent(themes=_real_keyed_themes())
    except Exception as e:  # noqa: BLE001
        raised12 = e
    test("§8B-TI12: no exception raised to caller", raised12 is None,
         reason=str(raised12))
    test("§8B-TI12b: returns an AgentOutput (fallback)",
         isinstance(out12, AgentOutput), reason=str(type(out12)))
    test("§8B-TI12c: fallback judgment_source == 'rule_based'",
         out12 is not None and out12.judgment_source == "rule_based",
         reason="" if out12 is None else out12.judgment_source)
finally:
    p12.restore()


# ===========================================================================
# §8B-TI13 — _rank_theme_constituents: None filtered, sorted descending;
#            mutation probe: reversed sort -> first no longer highest-excess
# ===========================================================================
print("\n§8B-TI13: _rank_theme_constituents filters None, sorts descending")
ti13_theme = _theme(
    "ai_chips", data_source="etf",
    constituents=["NVDA", "AVGO", "AMD", "MRVL"],
    constituent_rs={"NVDA": {"active": 5.0}, "AVGO": {"active": 9.0},
                    "AMD": {"active": 1.0}, "MRVL": {"active": None}})
ranked13 = _rank_theme_constituents(ti13_theme, n_top=5)
test("§8B-TI13: MRVL (None active_excess) filtered out",
     all(r["ticker"] != "MRVL" for r in ranked13) and len(ranked13) == 3,
     reason=str([r["ticker"] for r in ranked13]))
test("§8B-TI13b: sorted descending -> AVGO (9.0) first",
     ranked13 and ranked13[0]["ticker"] == "AVGO",
     reason=str([r["ticker"] for r in ranked13]))
test("§8B-TI13c: rank field is 1-based ascending",
     [r["rank"] for r in ranked13] == [1, 2, 3],
     reason=str([r["rank"] for r in ranked13]))
# Mutation probe: a REVERSED (ascending) sort would put AMD (1.0) first — the
# §8B-TI13b assertion would then FAIL, proving it genuinely discriminates.
_asc13 = sorted(ranked13, key=lambda r: r["active_excess"])
test("§8B-TI13d (discriminating): reversed sort first != highest-excess ticker",
     _asc13[0]["ticker"] != ranked13[0]["ticker"]
     and _asc13[0]["ticker"] == "AMD",
     reason=f"desc_first={ranked13[0]['ticker']} asc_first={_asc13[0]['ticker']}")


# ===========================================================================
# §8B-TI14 — fixture themes produce empty ranked_constituents (constituent_rs={})
# ===========================================================================
print("\n§8B-TI14: fixture theme (constituent_rs={}) -> ranked_constituents == []")
ti14_theme = _theme("ai_chips", data_source="fixture",
                    constituents=["NVDA", "AVGO"], constituent_rs={})
ranked14 = _rank_theme_constituents(ti14_theme, n_top=5)
test("§8B-TI14: empty constituent_rs -> []", ranked14 == [], reason=str(ranked14))


# ── Final summary ──────────────────────────────────────────────────────────

print(f"\n{'=' * 60}")
print(f"Phase 8B ThemeIntelligenceAgent Tests: {PASS} passed, {FAIL} failed")
if ERRORS:
    print("\nFailures:")
    for err in ERRORS:
        print(f"  - {err}")
print("=" * 60)

sys.exit(0 if FAIL == 0 else 1)
