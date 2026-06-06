"""
scripts/test_reliability_config.py

Isolated test suite for Phase 2A: Feature Flag Config Foundation.

Tests cover:
  A. parse_bool — bool passthrough
  B. parse_bool — truthy strings
  C. parse_bool — falsy strings
  D. parse_bool — whitespace stripping and case-insensitivity
  E. parse_bool — rejection of invalid strings
  F. parse_bool — rejection of unsupported types
  G. load_reliability_flags_from_mapping — empty mapping uses safe defaults
  H. Mapping can enable reliability with dry_run=True
  I. Mapping can represent future strict mode
  J. Invalid mapping value raises ValueError
  K. Input mapping is not mutated
  L. load_reliability_flags_from_env with injected mapping
  M. reliability_flags_to_env_dict roundtrip
  N. describe_reliability_config includes key mode information
  O. Integration with orchestration_plan remains compatible
  P. Existing default behavior remains disabled and dry-run safe
  Q. Present None value for recognized key raises ValueError
  R. Dry-run + block_on_validation_error=True — description is safe

Run:
    python3 scripts/test_reliability_config.py
"""

import os
import sys

# Ensure project root is on sys.path.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.reliability.config import (
    parse_bool,
    load_reliability_flags_from_mapping,
    load_reliability_flags_from_env,
    reliability_flags_to_env_dict,
    describe_reliability_config,
)
from lib.reliability.orchestration_plan import (
    ReliabilityFeatureFlags,
    get_default_reliability_flags,
    reliability_mode_description,
    build_orchestration_step_plan,
    validate_flag_combination,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PASS = "\033[32mPASS\033[0m"
_FAIL = "\033[31mFAIL\033[0m"

_passed = 0
_failed = 0


def _check(label: str, condition: bool) -> None:
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  {_PASS}  {label}")
    else:
        _failed += 1
        print(f"  {_FAIL}  {label}")


def _assert_raises(label: str, exc_type: type, fn, *args, **kwargs) -> None:
    global _passed, _failed
    try:
        fn(*args, **kwargs)
        _failed += 1
        print(f"  {_FAIL}  {label}  (expected {exc_type.__name__}, got no exception)")
    except exc_type:
        _passed += 1
        print(f"  {_PASS}  {label}")
    except Exception as e:
        _failed += 1
        print(f"  {_FAIL}  {label}  (expected {exc_type.__name__}, got {type(e).__name__}: {e})")


def _section(title: str) -> None:
    print(f"\n[{title}]")


# ---------------------------------------------------------------------------
# A. parse_bool — bool passthrough
# ---------------------------------------------------------------------------

_section("A")
print("parse_bool — actual bool passthrough")

_check("A1: True -> True",  parse_bool(True) is True)
_check("A2: False -> False", parse_bool(False) is False)
_check("A3: True with name kwarg", parse_bool(True, name="some_flag") is True)

# ---------------------------------------------------------------------------
# B. parse_bool — truthy strings
# ---------------------------------------------------------------------------

_section("B")
print("parse_bool — truthy strings")

_check("B1: '1' -> True",     parse_bool("1") is True)
_check("B2: 'true' -> True",  parse_bool("true") is True)
_check("B3: 'yes' -> True",   parse_bool("yes") is True)
_check("B4: 'y' -> True",     parse_bool("y") is True)
_check("B5: 'on' -> True",    parse_bool("on") is True)

# ---------------------------------------------------------------------------
# C. parse_bool — falsy strings
# ---------------------------------------------------------------------------

_section("C")
print("parse_bool — falsy strings")

_check("C1: '0' -> False",     parse_bool("0") is False)
_check("C2: 'false' -> False", parse_bool("false") is False)
_check("C3: 'no' -> False",    parse_bool("no") is False)
_check("C4: 'n' -> False",     parse_bool("n") is False)
_check("C5: 'off' -> False",   parse_bool("off") is False)

# ---------------------------------------------------------------------------
# D. parse_bool — whitespace and case
# ---------------------------------------------------------------------------

_section("D")
print("parse_bool — whitespace stripping and case-insensitivity")

_check("D1: '  TRUE  ' -> True",    parse_bool("  TRUE  ") is True)
_check("D2: 'True' -> True",        parse_bool("True") is True)
_check("D3: 'YES' -> True",         parse_bool("YES") is True)
_check("D4: '  FALSE  ' -> False",  parse_bool("  FALSE  ") is False)
_check("D5: 'NO' -> False",         parse_bool("NO") is False)
_check("D6: ' On ' -> True",        parse_bool(" On ") is True)
_check("D7: ' Off ' -> False",      parse_bool(" Off ") is False)

# ---------------------------------------------------------------------------
# E. parse_bool — rejection of invalid strings
# ---------------------------------------------------------------------------

_section("E")
print("parse_bool — rejection of invalid strings")

_assert_raises("E1: empty string",   ValueError, parse_bool, "")
_assert_raises("E2: 'maybe'",        ValueError, parse_bool, "maybe")
_assert_raises("E3: '2'",            ValueError, parse_bool, "2")
_assert_raises("E4: 'enabled'",      ValueError, parse_bool, "enabled")
_assert_raises("E5: 'disabled'",     ValueError, parse_bool, "disabled")

def _check_err_contains_name() -> bool:
    try:
        parse_bool("bad", name="my_flag")
        return False
    except ValueError as e:
        return "my_flag" in str(e)

_check("E6: error message includes name", _check_err_contains_name())

# ---------------------------------------------------------------------------
# F. parse_bool — rejection of unsupported types
# ---------------------------------------------------------------------------

_section("F")
print("parse_bool — rejection of unsupported types")

_assert_raises("F1: None",     ValueError, parse_bool, None)
_assert_raises("F2: int 1",   ValueError, parse_bool, 1)
_assert_raises("F3: int 0",   ValueError, parse_bool, 0)
_assert_raises("F4: list []", ValueError, parse_bool, [])

# ---------------------------------------------------------------------------
# G. load_reliability_flags_from_mapping — empty mapping → safe defaults
# ---------------------------------------------------------------------------

_section("G")
print("load_reliability_flags_from_mapping — empty mapping uses safe defaults")

_defaults = load_reliability_flags_from_mapping({})
_check("G1: reliability_enabled is False",          _defaults.reliability_enabled is False)
_check("G2: dry_run is True",                        _defaults.dry_run is True)
_check("G3: block_on_validation_error is False",     _defaults.block_on_validation_error is False)
_check("G4: show_ui_trace is False",                 _defaults.show_ui_trace is False)
_check("G5: use_constrained_prompts is False",       _defaults.use_constrained_prompts is False)
_check("G6: enable_repair_prompt is False",          _defaults.enable_repair_prompt is False)
_check("G7: equals get_default_reliability_flags()", _defaults == get_default_reliability_flags())

# ---------------------------------------------------------------------------
# H. Mapping can enable reliability with dry_run=True
# ---------------------------------------------------------------------------

_section("H")
print("Explicit mapping — reliability enabled, dry-run active")

_dry_run_flags = load_reliability_flags_from_mapping({
    "RELIABILITY_ENABLED": "true",
    "RELIABILITY_DRY_RUN": "true",
})
_check("H1: reliability_enabled is True",    _dry_run_flags.reliability_enabled is True)
_check("H2: dry_run is True",               _dry_run_flags.dry_run is True)
_check("H3: block_on_validation_error False", _dry_run_flags.block_on_validation_error is False)

# Step plan produced for dry-run mode
_plan = build_orchestration_step_plan("financial_analysis", _dry_run_flags)
_check("H4: collect_tool_results True in dry-run",   _plan["collect_tool_results"] is True)
_check("H5: block_on_error False in dry-run",         _plan["block_on_error"] is False)
_check("H6: fallback is dry_run_artifacts_only",
       _plan["fallback_behavior"] == "dry_run_artifacts_only")

# No warnings for clean dry-run config
_dry_run_warnings = validate_flag_combination(_dry_run_flags)
_check("H7: clean dry-run config has no warnings", len(_dry_run_warnings) == 0)

# Bool value True (not string) accepted for enabled
_bool_flags = load_reliability_flags_from_mapping({
    "RELIABILITY_ENABLED": True,
    "RELIABILITY_DRY_RUN": True,
})
_check("H8: bool True accepted as mapping value", _bool_flags.reliability_enabled is True)

# ---------------------------------------------------------------------------
# I. Mapping can represent future strict mode
# ---------------------------------------------------------------------------

_section("I")
print("Explicit mapping — future strict mode")

_strict_flags = load_reliability_flags_from_mapping({
    "RELIABILITY_ENABLED": "true",
    "RELIABILITY_DRY_RUN": "false",
    "RELIABILITY_BLOCK_ON_VALIDATION_ERROR": "true",
})
_check("I1: reliability_enabled True",         _strict_flags.reliability_enabled is True)
_check("I2: dry_run False",                     _strict_flags.dry_run is False)
_check("I3: block_on_validation_error True",    _strict_flags.block_on_validation_error is True)

# Strict mode triggers warnings (existing validation preserves safety)
_strict_warnings = validate_flag_combination(_strict_flags)
_check("I4: strict mode produces warnings",     len(_strict_warnings) >= 1)
_check("I5: strict-mode warning mentions dry_run",
       any("dry_run" in w for w in _strict_warnings))

_strict_plan = build_orchestration_step_plan("financial_analysis", _strict_flags)
_check("I6: block_on_error True in strict mode", _strict_plan["block_on_error"] is True)
_check("I7: fallback is reliability_enforced",
       _strict_plan["fallback_behavior"] == "reliability_enforced")

# ---------------------------------------------------------------------------
# J. Invalid mapping value raises ValueError
# ---------------------------------------------------------------------------

_section("J")
print("Invalid mapping value raises ValueError")

_assert_raises("J1: RELIABILITY_ENABLED='maybe'", ValueError,
               load_reliability_flags_from_mapping, {"RELIABILITY_ENABLED": "maybe"})
_assert_raises("J2: RELIABILITY_DRY_RUN=''", ValueError,
               load_reliability_flags_from_mapping, {"RELIABILITY_DRY_RUN": ""})
_assert_raises("J3: RELIABILITY_BLOCK_ON_VALIDATION_ERROR='2'", ValueError,
               load_reliability_flags_from_mapping, {"RELIABILITY_BLOCK_ON_VALIDATION_ERROR": "2"})

def _check_j4_err_contains_key() -> bool:
    try:
        load_reliability_flags_from_mapping({"RELIABILITY_SHOW_UI_TRACE": "oops"})
        return False
    except ValueError as e:
        return "RELIABILITY_SHOW_UI_TRACE" in str(e)

_check("J4: error message includes env key name", _check_j4_err_contains_key())

# ---------------------------------------------------------------------------
# K. Input mapping is not mutated
# ---------------------------------------------------------------------------

_section("K")
print("Input mapping is not mutated")

_original = {"RELIABILITY_ENABLED": "true"}
_original_copy = dict(_original)
load_reliability_flags_from_mapping(_original)
_check("K1: mapping dict unchanged after load",  _original == _original_copy)
_check("K2: no extra keys injected",             set(_original.keys()) == set(_original_copy.keys()))

_orig_env = {"RELIABILITY_ENABLED": "false", "RELIABILITY_DRY_RUN": "true"}
_orig_env_copy = dict(_orig_env)
load_reliability_flags_from_env(_orig_env)
_check("K3: env mapping unchanged after env load", _orig_env == _orig_env_copy)

# ---------------------------------------------------------------------------
# L. load_reliability_flags_from_env with injected mapping
# ---------------------------------------------------------------------------

_section("L")
print("load_reliability_flags_from_env with injected mapping")

_env_default = load_reliability_flags_from_env({})
_check("L1: empty env → reliability_enabled False", _env_default.reliability_enabled is False)
_check("L2: empty env → dry_run True",               _env_default.dry_run is True)

_env_enabled = load_reliability_flags_from_env({
    "RELIABILITY_ENABLED": "1",
    "RELIABILITY_DRY_RUN": "yes",
})
_check("L3: RELIABILITY_ENABLED=1 → True",           _env_enabled.reliability_enabled is True)
_check("L4: RELIABILITY_DRY_RUN=yes → True",          _env_enabled.dry_run is True)

# Unknown keys are silently ignored
_env_extra = load_reliability_flags_from_env({
    "RELIABILITY_ENABLED": "false",
    "SOME_UNRELATED_VAR": "something",
    "PATH": "/usr/bin",
})
_check("L5: unknown keys are silently ignored",       _env_extra.reliability_enabled is False)

# ---------------------------------------------------------------------------
# M. reliability_flags_to_env_dict roundtrip
# ---------------------------------------------------------------------------

_section("M")
print("reliability_flags_to_env_dict roundtrip")

_default_flags = get_default_reliability_flags()
_env_dict = reliability_flags_to_env_dict(_default_flags)

_check("M1: RELIABILITY_ENABLED is 'false'",
       _env_dict.get("RELIABILITY_ENABLED") == "false")
_check("M2: RELIABILITY_DRY_RUN is 'true'",
       _env_dict.get("RELIABILITY_DRY_RUN") == "true")
_check("M3: all six keys present", len(_env_dict) == 6)
_check("M4: all values are strings",
       all(isinstance(v, str) for v in _env_dict.values()))
_check("M5: all values are lowercase 'true'/'false'",
       all(v in ("true", "false") for v in _env_dict.values()))

_roundtripped = load_reliability_flags_from_mapping(_env_dict)
_check("M6: roundtrip produces same flags as original", _roundtripped == _default_flags)

# Roundtrip for dry-run-enabled flags
_dry_run_enabled = ReliabilityFeatureFlags(reliability_enabled=True, dry_run=True)
_dry_env = reliability_flags_to_env_dict(_dry_run_enabled)
_dry_restored = load_reliability_flags_from_mapping(_dry_env)
_check("M7: dry-run flags roundtrip correctly", _dry_restored == _dry_run_enabled)

# Roundtrip for strict flags
_strict = ReliabilityFeatureFlags(
    reliability_enabled=True, dry_run=False,
    block_on_validation_error=True, show_ui_trace=True,
    use_constrained_prompts=True, enable_repair_prompt=True,
)
_strict_env = reliability_flags_to_env_dict(_strict)
_strict_restored = load_reliability_flags_from_mapping(_strict_env)
_check("M8: strict flags roundtrip correctly", _strict_restored == _strict)

# ---------------------------------------------------------------------------
# N. describe_reliability_config includes key mode information
# ---------------------------------------------------------------------------

_section("N")
print("describe_reliability_config includes key mode information")

_desc_default = describe_reliability_config(get_default_reliability_flags())
_check("N1: description is a non-empty string",  isinstance(_desc_default, str) and len(_desc_default) > 0)
_check("N2: mentions reliability_enabled",        "reliability_enabled" in _desc_default.lower())
_check("N3: mentions dry_run",                    "dry_run" in _desc_default.lower())
_check("N4: mentions block_on_validation_error",  "block_on_validation_error" in _desc_default.lower())
_check("N5: mentions use_constrained_prompts",    "use_constrained_prompts" in _desc_default.lower())
_check("N6: mentions enable_repair_prompt",       "enable_repair_prompt" in _desc_default.lower())
_check("N7: mentions show_ui_trace",              "show_ui_trace" in _desc_default.lower())
_check("N8: indicates layer inactive (default)",
       "inactive" in _desc_default.lower() or "disabled" in _desc_default.lower() or "False" in _desc_default)
_check("N9: does not claim app behavior changed",
       "completely unchanged" in _desc_default or "unchanged" in _desc_default)

_desc_dry_run = describe_reliability_config(
    ReliabilityFeatureFlags(reliability_enabled=True, dry_run=True)
)
_check("N10: dry-run desc mentions artifacts-only or unchanged",
       "unchanged" in _desc_dry_run or "artifacts" in _desc_dry_run or "dry" in _desc_dry_run.lower())

_desc_strict = describe_reliability_config(
    ReliabilityFeatureFlags(reliability_enabled=True, dry_run=False,
                            block_on_validation_error=True)
)
_check("N11: strict mode desc mentions warnings",
       "warning" in _desc_strict.lower() or "!" in _desc_strict)

_desc_no_warn = describe_reliability_config(
    ReliabilityFeatureFlags(reliability_enabled=True, dry_run=True)
)
_check("N12: clean config description mentions no warnings",
       "no flag combination warnings" in _desc_no_warn.lower() or "no warnings" in _desc_no_warn.lower())

# ---------------------------------------------------------------------------
# O. Integration with orchestration_plan remains compatible
# ---------------------------------------------------------------------------

_section("O")
print("Integration with orchestration_plan — compatibility")

# Flags loaded from mapping are usable by all orchestration_plan helpers
_compat_flags = load_reliability_flags_from_mapping({
    "RELIABILITY_ENABLED": "true",
    "RELIABILITY_DRY_RUN": "true",
})
_compat_plan = build_orchestration_step_plan("sector_analysis", _compat_flags)
_check("O1: plan dict has all required keys",
       all(k in _compat_plan for k in [
           "step_name", "collect_tool_results", "build_evidence_packet",
           "use_constrained_prompt", "parse_agent_result", "validate_agent_result",
           "persist_validation_report", "block_on_error", "show_trace", "fallback_behavior"
       ]))
_check("O2: step_name echoed correctly", _compat_plan["step_name"] == "sector_analysis")

# Flags from env helper are likewise usable
_env_compat = load_reliability_flags_from_env({"RELIABILITY_ENABLED": "false"})
_plan_disabled = build_orchestration_step_plan("equity_research", _env_compat)
_check("O3: disabled plan has fallback=existing_workflow_unchanged",
       _plan_disabled["fallback_behavior"] == "existing_workflow_unchanged")

# reliability_flags_to_env_dict output → reload → orchestration works
_rebuilt = load_reliability_flags_from_mapping(
    reliability_flags_to_env_dict(ReliabilityFeatureFlags(reliability_enabled=True, dry_run=True))
)
_check("O4: flags reloaded from env_dict integrate with step plan",
       build_orchestration_step_plan("synthesis", _rebuilt)["collect_tool_results"] is True)

# validate_flag_combination works on loaded flags
_warn_flags = load_reliability_flags_from_mapping({
    "RELIABILITY_ENABLED": "false",
    "RELIABILITY_BLOCK_ON_VALIDATION_ERROR": "true",
})
_warns = validate_flag_combination(_warn_flags)
_check("O5: validate_flag_combination detects warnings from loaded flags",
       len(_warns) >= 1)

# ---------------------------------------------------------------------------
# P. Existing default behavior remains disabled and dry-run safe
# ---------------------------------------------------------------------------

_section("P")
print("Existing default behavior — fully disabled and dry-run safe")

_p_flags = get_default_reliability_flags()
_p_env_flags = load_reliability_flags_from_env({})  # empty env, safe defaults
_p_map_flags = load_reliability_flags_from_mapping({})

_check("P1: default flags — reliability disabled",   _p_flags.reliability_enabled is False)
_check("P2: env-loaded flags — reliability disabled", _p_env_flags.reliability_enabled is False)
_check("P3: map-loaded flags — reliability disabled", _p_map_flags.reliability_enabled is False)

for i, (label, ff) in enumerate([
    ("default", _p_flags),
    ("env-loaded", _p_env_flags),
    ("map-loaded", _p_map_flags),
], start=4):
    _plan_p = build_orchestration_step_plan("financial_analysis", ff)
    _check(f"P{i}: {label} — step plan inert (collect_tool_results=False)",
           _plan_p["collect_tool_results"] is False)
    _check(f"P{i+3}: {label} — step plan inert (fallback=existing_workflow_unchanged)",
           _plan_p["fallback_behavior"] == "existing_workflow_unchanged")

# ---------------------------------------------------------------------------
# Q. Present None value for recognized key raises ValueError
# ---------------------------------------------------------------------------

_section("Q")
print("Present None value for recognized key — raises ValueError")

_assert_raises("Q1: RELIABILITY_ENABLED=None raises ValueError",
               ValueError, load_reliability_flags_from_mapping,
               {"RELIABILITY_ENABLED": None})

_assert_raises("Q2: RELIABILITY_DRY_RUN=None raises ValueError",
               ValueError, load_reliability_flags_from_mapping,
               {"RELIABILITY_DRY_RUN": None})

_assert_raises("Q3: RELIABILITY_BLOCK_ON_VALIDATION_ERROR=None raises ValueError",
               ValueError, load_reliability_flags_from_mapping,
               {"RELIABILITY_BLOCK_ON_VALIDATION_ERROR": None})

# Absent key still uses safe default (None-as-absent is NOT the same as None-as-value)
_q_flags = load_reliability_flags_from_mapping({"RELIABILITY_ENABLED": "false"})
_check("Q4: absent RELIABILITY_DRY_RUN still uses safe default True",
       _q_flags.dry_run is True)

# ---------------------------------------------------------------------------
# R. Dry-run + block_on_validation_error=True — description is safe
# ---------------------------------------------------------------------------

_section("R")
print("Dry-run + block_on_validation_error=True — description reflects actual safe behavior")

_r_flags = ReliabilityFeatureFlags(
    reliability_enabled=True,
    dry_run=True,
    block_on_validation_error=True,
)
_r_desc = reliability_mode_description(_r_flags)

_check("R1: reliability_active is True",           _r_desc["reliability_active"] is True)
_check("R2: dry_run_active is True",               _r_desc["dry_run_active"] is True)
_check("R3: blocks_on_error is False (dry-run overrides blocking)",
       _r_desc["blocks_on_error"] is False)
_check("R4: alters_app_output is False (dry-run)",
       _r_desc["alters_app_output"] is False)

# Step plan for the same flags must also not block
_r_plan = build_orchestration_step_plan("financial_analysis", _r_flags)
_check("R5: step plan block_on_error is False in dry-run",
       _r_plan["block_on_error"] is False)
_check("R6: step plan collect_tool_results True in dry-run",
       _r_plan["collect_tool_results"] is True)
_check("R7: description does not claim strict-mode blocking",
       "blocking on validation error" not in _r_desc.get("summary", ""))

# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

print()
print("=" * 62)
if _failed == 0:
    print(f"\033[32mResults: {_passed} passed, {_failed} failed\033[0m")
else:
    print(f"\033[31mResults: {_passed} passed, {_failed} failed\033[0m")
print("=" * 62)

if _failed > 0:
    sys.exit(1)
