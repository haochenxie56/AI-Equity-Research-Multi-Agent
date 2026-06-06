"""
scripts/test_reliability_orchestration_plan.py

Phase 1G: Feature-Flagged Reliability Orchestration Design — test suite.

Tests ReliabilityFeatureFlags, get_default_reliability_flags(),
reliability_mode_description(), build_orchestration_step_plan(),
validate_flag_combination(), and list_supported_future_steps().

No live Claude API calls. No Streamlit. No llm_orchestrator. No app imports.
No file I/O. No external dependencies.

Run:
    python scripts/test_reliability_orchestration_plan.py
"""

import sys
import tempfile
import traceback
from pathlib import Path

# ---------------------------------------------------------------------------
# Path bootstrap
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.reliability.orchestration_plan import (
    ReliabilityFeatureFlags,
    get_default_reliability_flags,
    reliability_mode_description,
    build_orchestration_step_plan,
    validate_flag_combination,
    list_supported_future_steps,
)

# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

_PASSED = 0
_FAILED = 0


def _pass(label: str) -> None:
    global _PASSED
    _PASSED += 1
    print(f"  PASS  {label}")


def _fail(label: str, reason: str) -> None:
    global _FAILED
    _FAILED += 1
    print(f"  FAIL  {label}")
    print(f"        {reason}")


def _run(label: str, fn):
    try:
        fn()
    except AssertionError as exc:
        _fail(label, str(exc) or "AssertionError")
    except Exception:
        _fail(label, traceback.format_exc().strip().splitlines()[-1])


# ===========================================================================
# Test Group A — Default flags are safe
# ===========================================================================

def test_a():
    print("\n[A] Default flags are safe")

    flags = get_default_reliability_flags()

    def _a1():
        assert flags.reliability_enabled is False
        _pass("A1: reliability_enabled is False by default")

    def _a2():
        assert flags.dry_run is True
        _pass("A2: dry_run is True by default")

    def _a3():
        assert flags.block_on_validation_error is False
        _pass("A3: block_on_validation_error is False by default")

    def _a4():
        assert flags.show_ui_trace is False
        _pass("A4: show_ui_trace is False by default")

    def _a5():
        assert flags.use_constrained_prompts is False
        _pass("A5: use_constrained_prompts is False by default")

    def _a6():
        assert flags.enable_repair_prompt is False
        _pass("A6: enable_repair_prompt is False by default")

    def _a7():
        # Default factory is deterministic — two calls return equal objects
        flags2 = get_default_reliability_flags()
        assert flags == flags2
        _pass("A7: get_default_reliability_flags() is deterministic")

    _run("A1", _a1)
    _run("A2", _a2)
    _run("A3", _a3)
    _run("A4", _a4)
    _run("A5", _a5)
    _run("A6", _a6)
    _run("A7", _a7)


# ===========================================================================
# Test Group B — Default mode does not alter app output
# ===========================================================================

def test_b():
    print("\n[B] Default mode description does not alter app output")

    flags = get_default_reliability_flags()
    desc = reliability_mode_description(flags)

    def _b1():
        assert isinstance(desc, dict)
        _pass("B1: reliability_mode_description returns a dict")

    def _b2():
        assert desc["reliability_active"] is False
        _pass("B2: reliability_active is False")

    def _b3():
        assert desc["alters_app_output"] is False
        _pass("B3: alters_app_output is False — existing output unchanged")

    def _b4():
        assert desc["blocks_on_error"] is False
        _pass("B4: blocks_on_error is False — no blocking")

    def _b5():
        assert desc["shows_ui_trace"] is False
        _pass("B5: shows_ui_trace is False — no UI changes")

    def _b6():
        assert desc["uses_constrained_prompts"] is False
        _pass("B6: uses_constrained_prompts is False — existing prompts unchanged")

    def _b7():
        assert desc["repair_prompt_enabled"] is False
        _pass("B7: repair_prompt_enabled is False")

    def _b8():
        assert "summary" in desc
        summary = desc["summary"].lower()
        assert "inactive" in summary or "unchanged" in summary, \
            f"Summary does not indicate inactivity: {desc['summary']!r}"
        _pass("B8: summary indicates reliability is inactive / app unchanged")

    def _b9():
        # dry_run_active should also be False when reliability_enabled=False
        assert desc["dry_run_active"] is False
        _pass("B9: dry_run_active is False when reliability is disabled")

    _run("B1", _b1)
    _run("B2", _b2)
    _run("B3", _b3)
    _run("B4", _b4)
    _run("B5", _b5)
    _run("B6", _b6)
    _run("B7", _b7)
    _run("B8", _b8)
    _run("B9", _b9)


# ===========================================================================
# Test Group C — Disabled step plan is fully inert
# ===========================================================================

def test_c():
    print("\n[C] Disabled reliability produces inert step plan")

    flags = get_default_reliability_flags()
    plan = build_orchestration_step_plan("financial_analysis", flags)

    def _c1():
        assert isinstance(plan, dict)
        assert plan["step_name"] == "financial_analysis"
        _pass("C1: plan is a dict with correct step_name")

    def _c2():
        assert plan["collect_tool_results"] is False
        _pass("C2: collect_tool_results is False")

    def _c3():
        assert plan["build_evidence_packet"] is False
        _pass("C3: build_evidence_packet is False")

    def _c4():
        assert plan["use_constrained_prompt"] is False
        _pass("C4: use_constrained_prompt is False")

    def _c5():
        assert plan["parse_agent_result"] is False
        _pass("C5: parse_agent_result is False")

    def _c6():
        assert plan["validate_agent_result"] is False
        _pass("C6: validate_agent_result is False")

    def _c7():
        assert plan["persist_validation_report"] is False
        _pass("C7: persist_validation_report is False")

    def _c8():
        assert plan["block_on_error"] is False
        _pass("C8: block_on_error is False")

    def _c9():
        assert plan["show_trace"] is False
        _pass("C9: show_trace is False")

    def _c10():
        assert plan["fallback_behavior"] == "existing_workflow_unchanged", \
            f"Expected 'existing_workflow_unchanged', got {plan['fallback_behavior']!r}"
        _pass("C10: fallback_behavior == 'existing_workflow_unchanged'")

    def _c11():
        # All steps produce same inert plan when disabled
        for step in list_supported_future_steps():
            p = build_orchestration_step_plan(step, flags)
            assert p["fallback_behavior"] == "existing_workflow_unchanged", \
                f"Step {step!r} has wrong fallback: {p['fallback_behavior']!r}"
        _pass("C11: all supported steps are inert when reliability disabled")

    _run("C1", _c1)
    _run("C2", _c2)
    _run("C3", _c3)
    _run("C4", _c4)
    _run("C5", _c5)
    _run("C6", _c6)
    _run("C7", _c7)
    _run("C8", _c8)
    _run("C9", _c9)
    _run("C10", _c10)
    _run("C11", _c11)


# ===========================================================================
# Test Group D — Enabled dry-run step plan
# ===========================================================================

def test_d():
    print("\n[D] Enabled dry-run step plan")

    flags = ReliabilityFeatureFlags(
        reliability_enabled=True,
        dry_run=True,
    )
    plan = build_orchestration_step_plan("financial_analysis", flags)

    def _d1():
        assert plan["collect_tool_results"] is True
        _pass("D1: collect_tool_results is True in dry-run")

    def _d2():
        assert plan["build_evidence_packet"] is True
        _pass("D2: build_evidence_packet is True in dry-run")

    def _d3():
        assert plan["validate_agent_result"] is True
        _pass("D3: validate_agent_result is True in dry-run")

    def _d4():
        assert plan["persist_validation_report"] is True
        _pass("D4: persist_validation_report is True in dry-run")

    def _d5():
        # CRITICAL: dry-run never blocks
        assert plan["block_on_error"] is False, \
            "block_on_error must be False in dry-run mode"
        _pass("D5: block_on_error is False (never blocks in dry-run)")

    def _d6():
        fallback = plan["fallback_behavior"]
        assert "dry_run" in fallback or "unchanged" in fallback or "artifact" in fallback, \
            f"Unexpected fallback in dry-run: {fallback!r}"
        _pass("D6: fallback_behavior indicates dry-run does not alter output")

    def _d7():
        # alters_app_output should be False in dry-run
        desc = reliability_mode_description(flags)
        assert desc["alters_app_output"] is False
        _pass("D7: mode description shows alters_app_output=False in dry-run")

    def _d8():
        desc = reliability_mode_description(flags)
        assert desc["dry_run_active"] is True
        _pass("D8: dry_run_active is True in mode description")

    _run("D1", _d1)
    _run("D2", _d2)
    _run("D3", _d3)
    _run("D4", _d4)
    _run("D5", _d5)
    _run("D6", _d6)
    _run("D7", _d7)
    _run("D8", _d8)


# ===========================================================================
# Test Group E — Constrained prompts controlled separately
# ===========================================================================

def test_e():
    print("\n[E] Constrained prompts controlled independently")

    def _e1():
        flags = ReliabilityFeatureFlags(
            reliability_enabled=True,
            dry_run=True,
            use_constrained_prompts=False,
        )
        plan = build_orchestration_step_plan("financial_analysis", flags)
        assert plan["use_constrained_prompt"] is False
        _pass("E1: use_constrained_prompt=False when flag is False")

    def _e2():
        flags = ReliabilityFeatureFlags(
            reliability_enabled=True,
            dry_run=True,
            use_constrained_prompts=True,
        )
        plan = build_orchestration_step_plan("financial_analysis", flags)
        assert plan["use_constrained_prompt"] is True
        _pass("E2: use_constrained_prompt=True when flag is True")

    def _e3():
        # parse_agent_result should follow use_constrained_prompts
        flags_off = ReliabilityFeatureFlags(
            reliability_enabled=True, use_constrained_prompts=False
        )
        flags_on = ReliabilityFeatureFlags(
            reliability_enabled=True, use_constrained_prompts=True
        )
        plan_off = build_orchestration_step_plan("financial_analysis", flags_off)
        plan_on = build_orchestration_step_plan("financial_analysis", flags_on)
        assert plan_off["parse_agent_result"] is False
        assert plan_on["parse_agent_result"] is True
        _pass("E3: parse_agent_result follows use_constrained_prompts flag")

    def _e4():
        # Mode description also reflects use_constrained_prompts
        flags = ReliabilityFeatureFlags(
            reliability_enabled=True, use_constrained_prompts=True
        )
        desc = reliability_mode_description(flags)
        assert desc["uses_constrained_prompts"] is True
        _pass("E4: mode description reflects use_constrained_prompts=True")

    _run("E1", _e1)
    _run("E2", _e2)
    _run("E3", _e3)
    _run("E4", _e4)


# ===========================================================================
# Test Group F — UI trace controlled separately
# ===========================================================================

def test_f():
    print("\n[F] UI trace controlled independently")

    def _f1():
        flags = ReliabilityFeatureFlags(
            reliability_enabled=True,
            show_ui_trace=False,
        )
        plan = build_orchestration_step_plan("financial_analysis", flags)
        assert plan["show_trace"] is False
        _pass("F1: show_trace=False when flag is False")

    def _f2():
        flags = ReliabilityFeatureFlags(
            reliability_enabled=True,
            show_ui_trace=True,
        )
        plan = build_orchestration_step_plan("financial_analysis", flags)
        assert plan["show_trace"] is True
        _pass("F2: show_trace=True when flag is True")

    def _f3():
        flags = ReliabilityFeatureFlags(
            reliability_enabled=True, show_ui_trace=True
        )
        desc = reliability_mode_description(flags)
        assert desc["shows_ui_trace"] is True
        _pass("F3: mode description reflects show_ui_trace=True")

    def _f4():
        # show_trace=False when reliability disabled, even if flag is True
        flags = ReliabilityFeatureFlags(
            reliability_enabled=False, show_ui_trace=True
        )
        plan = build_orchestration_step_plan("financial_analysis", flags)
        assert plan["show_trace"] is False
        _pass("F4: show_trace=False when reliability disabled (master switch)")

    _run("F1", _f1)
    _run("F2", _f2)
    _run("F3", _f3)
    _run("F4", _f4)


# ===========================================================================
# Test Group G — Blocking controlled separately
# ===========================================================================

def test_g():
    print("\n[G] Blocking behavior controlled independently")

    def _g1():
        flags = ReliabilityFeatureFlags(
            reliability_enabled=True,
            dry_run=True,
            block_on_validation_error=False,
        )
        plan = build_orchestration_step_plan("financial_analysis", flags)
        assert plan["block_on_error"] is False
        _pass("G1: block_on_error=False when flag is False")

    def _g2():
        # Even if block_on_validation_error=True, dry_run overrides → False
        flags = ReliabilityFeatureFlags(
            reliability_enabled=True,
            dry_run=True,
            block_on_validation_error=True,  # overridden by dry_run
        )
        plan = build_orchestration_step_plan("financial_analysis", flags)
        assert plan["block_on_error"] is False, \
            "dry_run=True must prevent blocking even when block_on_validation_error=True"
        _pass("G2: dry_run=True prevents blocking even if block_on_validation_error=True")

    def _g3():
        # Only strict mode enables blocking
        flags = ReliabilityFeatureFlags(
            reliability_enabled=True,
            dry_run=False,
            block_on_validation_error=True,
        )
        plan = build_orchestration_step_plan("financial_analysis", flags)
        assert plan["block_on_error"] is True
        _pass("G3: block_on_error=True only in strict mode (dry_run=False)")

    def _g4():
        # Mode description reflects blocks_on_error
        flags = ReliabilityFeatureFlags(
            reliability_enabled=True,
            dry_run=False,
            block_on_validation_error=True,
        )
        desc = reliability_mode_description(flags)
        assert desc["blocks_on_error"] is True
        _pass("G4: mode description reflects blocks_on_error=True in strict mode")

    def _g5():
        # block_on_error=False when reliability disabled
        flags = ReliabilityFeatureFlags(
            reliability_enabled=False,
            block_on_validation_error=True,  # overridden by master switch
        )
        plan = build_orchestration_step_plan("financial_analysis", flags)
        assert plan["block_on_error"] is False
        _pass("G5: block_on_error=False when reliability disabled")

    _run("G1", _g1)
    _run("G2", _g2)
    _run("G3", _g3)
    _run("G4", _g4)
    _run("G5", _g5)


# ===========================================================================
# Test Group H — validate_flag_combination produces correct warnings
# ===========================================================================

def test_h():
    print("\n[H] validate_flag_combination warnings")

    def _h1():
        flags = ReliabilityFeatureFlags(
            reliability_enabled=False,
            block_on_validation_error=True,
        )
        warnings = validate_flag_combination(flags)
        assert len(warnings) >= 1
        assert any("block_on_validation_error" in w for w in warnings), \
            f"Expected block_on_validation_error warning in {warnings}"
        _pass("H1: warns when block_on_validation_error=True while disabled")

    def _h2():
        flags = ReliabilityFeatureFlags(
            reliability_enabled=False,
            show_ui_trace=True,
        )
        warnings = validate_flag_combination(flags)
        assert len(warnings) >= 1
        assert any("show_ui_trace" in w for w in warnings), \
            f"Expected show_ui_trace warning in {warnings}"
        _pass("H2: warns when show_ui_trace=True while disabled")

    def _h3():
        flags = ReliabilityFeatureFlags(
            reliability_enabled=False,
            use_constrained_prompts=True,
        )
        warnings = validate_flag_combination(flags)
        assert len(warnings) >= 1
        assert any("use_constrained_prompts" in w for w in warnings), \
            f"Expected use_constrained_prompts warning in {warnings}"
        _pass("H3: warns when use_constrained_prompts=True while disabled")

    def _h4():
        flags = ReliabilityFeatureFlags(
            reliability_enabled=True,
            use_constrained_prompts=False,
            enable_repair_prompt=True,
        )
        warnings = validate_flag_combination(flags)
        assert len(warnings) >= 1
        assert any("enable_repair_prompt" in w or "repair" in w.lower()
                   for w in warnings), \
            f"Expected repair_prompt warning in {warnings}"
        _pass("H4: warns when enable_repair_prompt=True without constrained prompts")

    def _h5():
        flags = ReliabilityFeatureFlags(
            reliability_enabled=True,
            dry_run=False,
            block_on_validation_error=True,
        )
        warnings = validate_flag_combination(flags)
        assert len(warnings) >= 1
        assert any("strict" in w.lower() or "block" in w.lower() for w in warnings), \
            f"Expected strict-mode warning in {warnings}"
        _pass("H5: warns when dry_run=False and block_on_validation_error=True")

    def _h6():
        # Clean config → no warnings
        flags = ReliabilityFeatureFlags(
            reliability_enabled=True,
            dry_run=True,
        )
        warnings = validate_flag_combination(flags)
        assert warnings == [], f"Expected no warnings for clean config, got {warnings}"
        _pass("H6: clean dry-run config produces no warnings")

    def _h7():
        # Default flags → no warnings
        flags = get_default_reliability_flags()
        warnings = validate_flag_combination(flags)
        assert warnings == [], f"Expected no warnings for defaults, got {warnings}"
        _pass("H7: default flags produce no warnings")

    def _h8():
        # Multiple flags → multiple warnings returned
        flags = ReliabilityFeatureFlags(
            reliability_enabled=False,
            block_on_validation_error=True,
            show_ui_trace=True,
            use_constrained_prompts=True,
        )
        warnings = validate_flag_combination(flags)
        assert len(warnings) >= 3, \
            f"Expected ≥3 warnings (one per bad flag), got {len(warnings)}: {warnings}"
        _pass("H8: multiple inconsistent flags produce multiple warnings")

    _run("H1", _h1)
    _run("H2", _h2)
    _run("H3", _h3)
    _run("H4", _h4)
    _run("H5", _h5)
    _run("H6", _h6)
    _run("H7", _h7)
    _run("H8", _h8)


# ===========================================================================
# Test Group I — list_supported_future_steps
# ===========================================================================

def test_i():
    print("\n[I] list_supported_future_steps")

    steps = list_supported_future_steps()

    def _i1():
        assert isinstance(steps, list)
        assert len(steps) >= 4
        _pass("I1: returns a non-empty list of step names")

    def _i2():
        assert "sector_analysis" in steps
        _pass("I2: sector_analysis in supported steps")

    def _i3():
        assert "stock_scanner" in steps
        _pass("I3: stock_scanner in supported steps")

    def _i4():
        assert "equity_research" in steps
        _pass("I4: equity_research in supported steps")

    def _i5():
        assert "financial_analysis" in steps
        _pass("I5: financial_analysis in supported steps")

    def _i6():
        assert "price_volume_analysis" in steps
        _pass("I6: price_volume_analysis in supported steps")

    def _i7():
        assert "synthesis" in steps
        _pass("I7: synthesis in supported steps")

    def _i8():
        # All step names should work as step_name argument
        flags = get_default_reliability_flags()
        for step in steps:
            plan = build_orchestration_step_plan(step, flags)
            assert plan["step_name"] == step
        _pass("I8: all supported step names accepted by build_orchestration_step_plan")

    def _i9():
        # Deterministic — same list every call
        steps2 = list_supported_future_steps()
        assert steps == steps2
        _pass("I9: list_supported_future_steps is deterministic")

    _run("I1", _i1)
    _run("I2", _i2)
    _run("I3", _i3)
    _run("I4", _i4)
    _run("I5", _i5)
    _run("I6", _i6)
    _run("I7", _i7)
    _run("I8", _i8)
    _run("I9", _i9)


# ===========================================================================
# Test Group J — No side effects
# ===========================================================================

def test_j():
    print("\n[J] No side effects — orchestration_plan is pure")

    def _j1():
        # No files created in temp dir by importing or calling planning functions
        with tempfile.TemporaryDirectory() as tmp:
            before = set(Path(tmp).iterdir())

            # Call all planning functions
            flags = get_default_reliability_flags()
            reliability_mode_description(flags)
            build_orchestration_step_plan("financial_analysis", flags)
            validate_flag_combination(flags)
            list_supported_future_steps()

            after = set(Path(tmp).iterdir())
            new_files = after - before
            assert not new_files, f"Unexpected files created: {new_files}"
        _pass("J1: no files created in temp dir by planning helpers")

    def _j2():
        # Calling with different flags does not mutate the original
        flags = ReliabilityFeatureFlags(reliability_enabled=False)
        original_enabled = flags.reliability_enabled

        # "Enable" by building a plan (should not mutate flags)
        build_orchestration_step_plan("financial_analysis", flags)
        assert flags.reliability_enabled == original_enabled
        _pass("J2: build_orchestration_step_plan does not mutate flags")

    def _j3():
        # validate_flag_combination does not mutate flags
        flags = ReliabilityFeatureFlags(
            reliability_enabled=False,
            block_on_validation_error=True,
        )
        original = (flags.reliability_enabled, flags.block_on_validation_error)
        validate_flag_combination(flags)
        assert (flags.reliability_enabled, flags.block_on_validation_error) == original
        _pass("J3: validate_flag_combination does not mutate flags")

    def _j4():
        # reliability_mode_description is idempotent
        flags = ReliabilityFeatureFlags(reliability_enabled=True, dry_run=True)
        desc1 = reliability_mode_description(flags)
        desc2 = reliability_mode_description(flags)
        assert desc1 == desc2
        _pass("J4: reliability_mode_description is idempotent for same flags")

    def _j5():
        # build_orchestration_step_plan is idempotent
        flags = ReliabilityFeatureFlags(reliability_enabled=True, dry_run=True)
        plan1 = build_orchestration_step_plan("financial_analysis", flags)
        plan2 = build_orchestration_step_plan("financial_analysis", flags)
        assert plan1 == plan2
        _pass("J5: build_orchestration_step_plan is idempotent for same inputs")

    def _j6():
        # Dataclass equality: same field values → equal
        a = ReliabilityFeatureFlags(reliability_enabled=True, dry_run=True)
        b = ReliabilityFeatureFlags(reliability_enabled=True, dry_run=True)
        assert a == b
        _pass("J6: ReliabilityFeatureFlags supports equality comparison")

    _run("J1", _j1)
    _run("J2", _j2)
    _run("J3", _j3)
    _run("J4", _j4)
    _run("J5", _j5)
    _run("J6", _j6)


# ===========================================================================
# Test Group K — Additional plan completeness checks
# ===========================================================================

def test_k():
    print("\n[K] Plan completeness and key invariants")

    required_plan_keys = {
        "step_name", "collect_tool_results", "build_evidence_packet",
        "use_constrained_prompt", "parse_agent_result", "validate_agent_result",
        "persist_validation_report", "block_on_error", "show_trace",
        "fallback_behavior",
    }

    def _k1():
        flags = get_default_reliability_flags()
        plan = build_orchestration_step_plan("synthesis", flags)
        missing = required_plan_keys - set(plan.keys())
        assert not missing, f"Plan missing keys: {missing}"
        _pass("K1: disabled plan has all required keys")

    def _k2():
        flags = ReliabilityFeatureFlags(reliability_enabled=True, dry_run=True)
        plan = build_orchestration_step_plan("synthesis", flags)
        missing = required_plan_keys - set(plan.keys())
        assert not missing, f"Plan missing keys: {missing}"
        _pass("K2: dry-run plan has all required keys")

    def _k3():
        flags = ReliabilityFeatureFlags(
            reliability_enabled=True, dry_run=False,
            block_on_validation_error=True, use_constrained_prompts=True,
            show_ui_trace=True,
        )
        plan = build_orchestration_step_plan("financial_analysis", flags)
        missing = required_plan_keys - set(plan.keys())
        assert not missing, f"Plan missing keys: {missing}"
        _pass("K3: strict-mode plan has all required keys")

    def _k4():
        # Invalid step_name raises ValueError
        flags = get_default_reliability_flags()
        try:
            build_orchestration_step_plan("", flags)
            _fail("K4", "Expected ValueError for empty step_name")
        except ValueError:
            _pass("K4: empty step_name raises ValueError")

    def _k5():
        # Required mode description keys
        required_desc_keys = {
            "reliability_active", "dry_run_active", "alters_app_output",
            "blocks_on_error", "shows_ui_trace", "uses_constrained_prompts",
            "repair_prompt_enabled", "summary",
        }
        flags = get_default_reliability_flags()
        desc = reliability_mode_description(flags)
        missing = required_desc_keys - set(desc.keys())
        assert not missing, f"Mode description missing keys: {missing}"
        _pass("K5: mode description has all required keys")

    def _k6():
        # In strict mode, alters_app_output should be True
        flags = ReliabilityFeatureFlags(
            reliability_enabled=True,
            dry_run=False,
        )
        desc = reliability_mode_description(flags)
        assert desc["alters_app_output"] is True, \
            "Strict mode (dry_run=False) should indicate output may be altered"
        _pass("K6: strict mode shows alters_app_output=True")

    _run("K1", _k1)
    _run("K2", _k2)
    _run("K3", _k3)
    _run("K4", _k4)
    _run("K5", _k5)
    _run("K6", _k6)


# ===========================================================================
# Main
# ===========================================================================

if __name__ == "__main__":
    print("=" * 64)
    print("Phase 1G: Feature-Flagged Orchestration Design — test suite")
    print("=" * 64)

    test_a()
    test_b()
    test_c()
    test_d()
    test_e()
    test_f()
    test_g()
    test_h()
    test_i()
    test_j()
    test_k()

    print("\n" + "=" * 64)
    print(f"Results: {_PASSED} passed, {_FAILED} failed")
    print("=" * 64)
    sys.exit(0 if _FAILED == 0 else 1)
