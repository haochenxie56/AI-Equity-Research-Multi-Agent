#!/usr/bin/env python3
"""
scripts/test_reliability_evaluation_harness.py

Direct tests for Phase 2K Reliability Evaluation Harness.

Run with:
    python3 scripts/test_reliability_evaluation_harness.py

Tests covering schemas, loaders, runners, fail-closed behavior, and full eval suite.
Also runs full reliability regression for all prior phases.
"""

import os
import sys
import json
import subprocess
import tempfile
from pathlib import Path

# Add repo root to sys.path
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_CASES_DIR = os.path.join(_REPO_ROOT, "evals", "cases")
_EXPECTED_DIR = os.path.join(_REPO_ROOT, "evals", "expected")

_PASS = 0
_FAIL = 0


def _ok(label: str) -> None:
    global _PASS
    _PASS += 1
    print(f"  [PASS] {label}")


def _fail(label: str, detail: str = "") -> None:
    global _FAIL
    _FAIL += 1
    msg = f"  [FAIL] {label}"
    if detail:
        msg += f"\n         {detail}"
    print(msg)


def _assert(cond: bool, label: str, detail: str = "") -> None:
    if cond:
        _ok(label)
    else:
        _fail(label, detail)


# ---------------------------------------------------------------------------
# Import evaluation module
# ---------------------------------------------------------------------------

from lib.reliability.evaluation import (
    EvalCaseStatus,
    EvalDetectionStatus,
    ReliabilityFailureMode,
    ReliabilityEvalCase,
    ReliabilityExpectedOutput,
    ReliabilityEvalCaseResult,
    ReliabilityScoreSummary,
    REQUIRED_FAILURE_MODES,
    load_eval_cases,
    load_expected_outputs,
    run_single_eval_case,
    compare_actual_to_expected,
    run_reliability_evals,
    summarize_reliability_score,
    save_reliability_score_summary,
)


# ---------------------------------------------------------------------------
# Test 1: ReliabilityEvalCase accepts valid case
# ---------------------------------------------------------------------------

print("\n--- Test 1: ReliabilityEvalCase accepts valid case ---")
try:
    case = ReliabilityEvalCase(
        case_id="test_case_01",
        description="A test case",
        failure_mode="unsupported_numeric_claim",
        inputs={"agent_result": {}},
        metadata={"notes": "test"},
    )
    _assert(case.case_id == "test_case_01", "case_id set correctly")
    _assert(case.failure_mode == "unsupported_numeric_claim", "failure_mode set correctly")
except Exception as e:
    _fail("ReliabilityEvalCase construction", str(e))


# ---------------------------------------------------------------------------
# Test 2: ReliabilityEvalCase rejects empty case_id
# ---------------------------------------------------------------------------

print("\n--- Test 2: ReliabilityEvalCase rejects empty case_id ---")
try:
    ReliabilityEvalCase(
        case_id="",
        description="A test",
        failure_mode="other",
    )
    _fail("Should have rejected empty case_id")
except Exception:
    _ok("ReliabilityEvalCase rejects empty case_id")

try:
    ReliabilityEvalCase(
        case_id="   ",
        description="A test",
        failure_mode="other",
    )
    _fail("Should have rejected whitespace-only case_id")
except Exception:
    _ok("ReliabilityEvalCase rejects whitespace-only case_id")


# ---------------------------------------------------------------------------
# Test 3: ReliabilityExpectedOutput accepts valid expected output
# ---------------------------------------------------------------------------

print("\n--- Test 3: ReliabilityExpectedOutput accepts valid expected output ---")
try:
    exp = ReliabilityExpectedOutput(
        case_id="test_case_01",
        expected_status="fail",
        expected_issue_types=["missing_risk"],
        allowed_issue_types=["weak_evidence"],
        expected_min_critical=0,
        expected_min_warnings=1,
        expected_detected=True,
    )
    _assert(exp.case_id == "test_case_01", "expected case_id set correctly")
    _assert(exp.expected_min_warnings == 1, "expected_min_warnings set correctly")
    _assert(exp.expected_detected is True, "expected_detected set correctly")
except Exception as e:
    _fail("ReliabilityExpectedOutput construction", str(e))


# ---------------------------------------------------------------------------
# Test 4: ReliabilityEvalCaseResult accepts valid result
# ---------------------------------------------------------------------------

print("\n--- Test 4: ReliabilityEvalCaseResult accepts valid result ---")
try:
    result = ReliabilityEvalCaseResult(
        case_id="test_case_01",
        failure_mode="missing_downside_risk",
        status="pass",
        detection_status="detected",
        detected_issue_types=["missing_risk"],
        critical_count=0,
        warning_count=1,
        info_count=0,
        passed_expectation=True,
        messages=["PASS: missing_risk detected."],
    )
    _assert(result.status == "pass", "status set correctly")
    _assert(result.detection_status == "detected", "detection_status set correctly")
    _assert(result.warning_count == 1, "warning_count set correctly")
except Exception as e:
    _fail("ReliabilityEvalCaseResult construction", str(e))


# ---------------------------------------------------------------------------
# Test 5: ReliabilityScoreSummary validates counts and detection_rate
# ---------------------------------------------------------------------------

print("\n--- Test 5: ReliabilityScoreSummary validates counts and detection_rate ---")
try:
    summary = ReliabilityScoreSummary(
        total_cases=5,
        passed_cases=4,
        failed_cases=1,
        error_cases=0,
        skipped_cases=0,
        detection_rate=0.8,
        false_positive_count=0,
        missed_count=1,
        results=[],
    )
    _assert(summary.total_cases == 5, "total_cases set correctly")
    _assert(summary.detection_rate == 0.8, "detection_rate set correctly")

    # Test clamping
    summary2 = ReliabilityScoreSummary(detection_rate=1.5)
    _assert(summary2.detection_rate == 1.0, "detection_rate clamped to 1.0")

    summary3 = ReliabilityScoreSummary(detection_rate=-0.5)
    _assert(summary3.detection_rate == 0.0, "detection_rate clamped to 0.0")

    # Test negative counts rejected
    try:
        ReliabilityScoreSummary(total_cases=-1)
        _fail("Should have rejected negative total_cases")
    except Exception:
        _ok("Negative total_cases rejected")

except Exception as e:
    _fail("ReliabilityScoreSummary validation", str(e))


# ---------------------------------------------------------------------------
# Test 6: load_eval_cases loads fixed cases
# ---------------------------------------------------------------------------

print("\n--- Test 6: load_eval_cases loads fixed cases ---")
cases = load_eval_cases(_CASES_DIR)
_assert(len(cases) > 0, f"Loaded {len(cases)} cases from {_CASES_DIR}")
case_ids = [c.case_id for c in cases]
_assert("clean_minimal_case" in case_ids, "clean_minimal_case present")
_assert("unsupported_numeric_claim" in case_ids, "unsupported_numeric_claim present")


# ---------------------------------------------------------------------------
# Test 7: load_expected_outputs loads expected outputs
# ---------------------------------------------------------------------------

print("\n--- Test 7: load_expected_outputs loads expected outputs ---")
expected_map = load_expected_outputs(_EXPECTED_DIR)
_assert(len(expected_map) > 0, f"Loaded {len(expected_map)} expected outputs")
_assert("clean_minimal_case" in expected_map, "clean_minimal_case expected output present")


# ---------------------------------------------------------------------------
# Test 8: every case has a matching expected output
# ---------------------------------------------------------------------------

print("\n--- Test 8: every case has a matching expected output ---")
for c in cases:
    _assert(
        c.case_id in expected_map,
        f"Case '{c.case_id}' has expected output",
        f"Missing expected output for case_id='{c.case_id}'",
    )


# ---------------------------------------------------------------------------
# Test 9: every expected output has a matching case
# ---------------------------------------------------------------------------

print("\n--- Test 9: every expected output has a matching case ---")
case_id_set = {c.case_id for c in cases}
for exp_id in expected_map:
    _assert(
        exp_id in case_id_set,
        f"Expected output '{exp_id}' has matching case",
        f"No case found for expected output case_id='{exp_id}'",
    )


# ---------------------------------------------------------------------------
# Test 10: run_single_eval_case returns structured result
# ---------------------------------------------------------------------------

print("\n--- Test 10: run_single_eval_case returns structured result ---")
if cases:
    test_case = next((c for c in cases if c.case_id == "missing_downside_risk"), cases[0])
    result = run_single_eval_case(test_case)
    _assert(isinstance(result, ReliabilityEvalCaseResult), "Result is ReliabilityEvalCaseResult")
    _assert(result.case_id == test_case.case_id, "result.case_id matches")
    _assert(result.status in ("pass", "fail", "error", "skipped"), "status is valid")
else:
    _fail("No cases to run for test 10")


# ---------------------------------------------------------------------------
# Test 11: compare_actual_to_expected detects expected issue types
# ---------------------------------------------------------------------------

print("\n--- Test 11: compare_actual_to_expected detects expected issue types ---")
actual = ReliabilityEvalCaseResult(
    case_id="test_detect",
    failure_mode="missing_downside_risk",
    status="pass",
    detection_status="not_applicable",
    detected_issue_types=["missing_risk", "weak_evidence"],
    critical_count=0,
    warning_count=2,
    info_count=0,
    passed_expectation=True,
    messages=[],
)
expected_out = ReliabilityExpectedOutput(
    case_id="test_detect",
    expected_issue_types=["missing_risk"],
    allowed_issue_types=["weak_evidence"],
    expected_min_warnings=1,
    expected_detected=True,
)
compared = compare_actual_to_expected(actual, expected_out)
_assert(compared.detection_status == "detected", "detection_status == detected")
_assert(compared.passed_expectation is True, "passed_expectation is True")

# Test miss case
actual_miss = ReliabilityEvalCaseResult(
    case_id="test_miss",
    failure_mode="missing_downside_risk",
    status="pass",
    detection_status="not_applicable",
    detected_issue_types=[],
    critical_count=0,
    warning_count=0,
    info_count=0,
    passed_expectation=True,
    messages=[],
)
compared_miss = compare_actual_to_expected(actual_miss, expected_out)
_assert(compared_miss.detection_status == "missed", "detection_status == missed when nothing detected")
_assert(compared_miss.passed_expectation is False, "passed_expectation is False on miss")


# ---------------------------------------------------------------------------
# Test 12: clean_minimal_case does not false-positive critical/warning
# ---------------------------------------------------------------------------

print("\n--- Test 12: clean_minimal_case does not false-positive critical/warning ---")
clean_case = next((c for c in cases if c.case_id == "clean_minimal_case"), None)
clean_expected = expected_map.get("clean_minimal_case")
if clean_case and clean_expected:
    clean_result = run_single_eval_case(clean_case, expected=clean_expected)
    _assert(
        clean_result.passed_expectation,
        "clean_minimal_case passes expectation",
        f"status={clean_result.status}, detection={clean_result.detection_status}, "
        f"critical={clean_result.critical_count}, warning={clean_result.warning_count}, "
        f"types={clean_result.detected_issue_types}",
    )
    _assert(
        clean_result.detection_status != "false_positive",
        f"clean_minimal_case detection_status={clean_result.detection_status} (not false_positive)",
    )
else:
    _fail("clean_minimal_case or its expected output not found")


# ---------------------------------------------------------------------------
# Test 13: run_reliability_evals returns ReliabilityScoreSummary
# ---------------------------------------------------------------------------

print("\n--- Test 13: run_reliability_evals returns ReliabilityScoreSummary ---")
summary = run_reliability_evals(_CASES_DIR, _EXPECTED_DIR)
_assert(isinstance(summary, ReliabilityScoreSummary), "Returns ReliabilityScoreSummary")
_assert(summary.total_cases > 0, f"total_cases={summary.total_cases} > 0")
_assert(len(summary.results) == summary.total_cases, "results count matches total_cases")


# ---------------------------------------------------------------------------
# Test 14: eval suite contains at least 12 cases
# ---------------------------------------------------------------------------

print("\n--- Test 14: eval suite contains at least 12 cases ---")
_assert(len(cases) >= 12, f"At least 12 cases present (found {len(cases)})")


# ---------------------------------------------------------------------------
# Test 15: all required failure modes are present
# ---------------------------------------------------------------------------

print("\n--- Test 15: all required failure modes are present ---")
present_modes = {c.failure_mode for c in cases}
for mode in REQUIRED_FAILURE_MODES:
    _assert(
        mode in present_modes,
        f"Required failure mode '{mode}' present",
        f"Missing failure mode: {mode}",
    )


# ---------------------------------------------------------------------------
# Test 16: eval runner exits success when expectations pass
# ---------------------------------------------------------------------------

print("\n--- Test 16: eval runner exits success when expectations pass ---")
# Check that all cases currently pass (or at least the runner completes)
all_pass = all(r.passed_expectation for r in summary.results)
failed_ids = [r.case_id for r in summary.results if not r.passed_expectation]
_assert(
    all_pass,
    f"All {len(cases)} cases pass expectations",
    f"Failed: {failed_ids}",
)


# ---------------------------------------------------------------------------
# Test 17: ReliabilityScoreSummary serialization roundtrip
# ---------------------------------------------------------------------------

print("\n--- Test 17: ReliabilityScoreSummary serialization roundtrip ---")
try:
    with tempfile.NamedTemporaryFile(
        suffix=".json", delete=False, mode="w", encoding="utf-8"
    ) as f:
        tmp_path = f.name

    save_reliability_score_summary(summary, tmp_path)
    raw = Path(tmp_path).read_text(encoding="utf-8")
    parsed = ReliabilityScoreSummary.model_validate_json(raw)
    os.unlink(tmp_path)

    _assert(
        parsed.total_cases == summary.total_cases,
        f"Roundtrip total_cases: {parsed.total_cases} == {summary.total_cases}",
    )
    _assert(
        abs(parsed.detection_rate - summary.detection_rate) < 1e-6,
        f"Roundtrip detection_rate: {parsed.detection_rate:.4f} == {summary.detection_rate:.4f}",
    )
    _assert(
        len(parsed.results) == len(summary.results),
        f"Roundtrip results count: {len(parsed.results)}",
    )
except Exception as e:
    _fail("Serialization roundtrip", str(e))


# ---------------------------------------------------------------------------
# Test 18: No live app modules imported
# ---------------------------------------------------------------------------

print("\n--- Test 18: No live app modules imported ---")
live_modules = ["app", "pages", "lib.llm_orchestrator"]
for mod in live_modules:
    _assert(
        mod not in sys.modules,
        f"Live module '{mod}' not imported",
    )


# ---------------------------------------------------------------------------
# Test 19: No external API/network calls (verify no requests/httpx import)
# ---------------------------------------------------------------------------

print("\n--- Test 19: No external API/network calls ---")
network_modules = ["requests", "httpx", "urllib.request"]
for mod in network_modules:
    in_modules = mod in sys.modules
    # requests/httpx being imported is fine as long as we didn't actually call them
    # The evaluation module itself should not import them
    eval_source = Path(_REPO_ROOT) / "lib" / "reliability" / "evaluation.py"
    content = eval_source.read_text(encoding="utf-8")
    _assert(
        "requests" not in content and "httpx" not in content,
        "evaluation.py does not import requests or httpx",
    )
    break  # One check is enough


# ---------------------------------------------------------------------------
# Test 20: Existing critic/staleness/validation aggregator modules remain importable
# ---------------------------------------------------------------------------

print("\n--- Test 20: Existing modules remain importable ---")
try:
    from lib.reliability.critic import run_mock_critic, CriticResult
    from lib.reliability.staleness import StalenessReport, aggregate_staleness_findings
    from lib.reliability.validation_aggregator import ValidationAggregate, aggregate_validation_items
    _ok("critic, staleness, validation_aggregator all importable")
except ImportError as e:
    _fail("Module import failed", str(e))


# ---------------------------------------------------------------------------
# Test 21: run_single_eval_case with expected=None fails closed
# ---------------------------------------------------------------------------

print("\n--- Test 21: run_single_eval_case with expected=None fails closed ---")
if cases:
    _no_expected_result = run_single_eval_case(cases[0], expected=None)
    _assert(
        _no_expected_result.passed_expectation is False,
        "No expected → passed_expectation=False",
    )
    _assert(
        _no_expected_result.status in ("error", "fail"),
        f"No expected → status is error/fail (got {_no_expected_result.status!r})",
    )
    _assert(
        any("Missing expected output" in m for m in _no_expected_result.messages),
        "No expected → message mentions 'Missing expected output'",
        f"messages={_no_expected_result.messages}",
    )
else:
    _fail("No cases available for Test 21")


# ---------------------------------------------------------------------------
# Test 22: run_reliability_evals fails when a case lacks matching expected output
# ---------------------------------------------------------------------------

print("\n--- Test 22: run_reliability_evals fails when case lacks matching expected ---")
import tempfile as _tempfile

with _tempfile.TemporaryDirectory() as _tmp22:
    _cases22 = os.path.join(_tmp22, "cases")
    _exp22 = os.path.join(_tmp22, "expected")
    os.makedirs(_cases22)
    os.makedirs(_exp22)
    # Write one valid case
    _case22_data = {
        "case_id": "tmp_case_missing_expected",
        "description": "A test case with no matching expected output",
        "failure_mode": "other",
        "inputs": {},
    }
    with open(os.path.join(_cases22, "case.json"), "w") as _f:
        json.dump(_case22_data, _f)
    # No expected output file → empty expected dir → load_expected_outputs raises ValueError
    # run_reliability_evals catches it and returns a summary with error_cases > 0
    try:
        _s22 = run_reliability_evals(_cases22, _exp22)
        _assert(
            _s22.error_cases > 0 or _s22.failed_cases > 0,
            f"Summary has errors/failures when expected dir is empty "
            f"(error_cases={_s22.error_cases}, failed_cases={_s22.failed_cases})",
        )
        _assert(
            _s22.passed_cases == 0 or _s22.error_cases > 0,
            "No cases pass when expected dir is empty",
        )
    except ValueError:
        _ok("run_reliability_evals raises ValueError on empty expected dir")


# ---------------------------------------------------------------------------
# Test 23: run_reliability_evals fails when expected output has no matching case
# ---------------------------------------------------------------------------

print("\n--- Test 23: run_reliability_evals fails on orphan expected output ---")
with _tempfile.TemporaryDirectory() as _tmp23:
    _cases23 = os.path.join(_tmp23, "cases")
    _exp23 = os.path.join(_tmp23, "expected")
    os.makedirs(_cases23)
    os.makedirs(_exp23)
    # One valid case
    _case23_data = {
        "case_id": "real_case",
        "description": "A real case",
        "failure_mode": "other",
        "inputs": {},
    }
    with open(os.path.join(_cases23, "real_case.json"), "w") as _f:
        json.dump(_case23_data, _f)
    # Matching expected for real_case
    _exp23_real = {
        "case_id": "real_case",
        "expected_issue_types": [],
        "expected_detected": False,
    }
    with open(os.path.join(_exp23, "real_case.json"), "w") as _f:
        json.dump(_exp23_real, _f)
    # Orphan expected for nonexistent case
    _exp23_orphan = {
        "case_id": "nonexistent_orphan_case",
        "expected_issue_types": [],
        "expected_detected": True,
    }
    with open(os.path.join(_exp23, "orphan.json"), "w") as _f:
        json.dump(_exp23_orphan, _f)
    _s23 = run_reliability_evals(_cases23, _exp23)
    _assert(
        _s23.error_cases > 0,
        f"Orphan expected output → error_cases > 0 (got {_s23.error_cases})",
    )
    _orphan_msgs = [
        msg
        for r in _s23.results
        for msg in r.messages
        if "Expected output has no matching case" in msg
    ]
    _assert(
        len(_orphan_msgs) > 0,
        "Orphan expected output message present in results",
        f"results={[r.messages for r in _s23.results]}",
    )


# ---------------------------------------------------------------------------
# Test 24: CLI exits nonzero when expected dir is missing
# ---------------------------------------------------------------------------

print("\n--- Test 24: CLI exits nonzero when expected dir is missing ---")
_run_evals_path = os.path.join(_REPO_ROOT, "evals", "run_evals.py")
with _tempfile.TemporaryDirectory() as _tmp24:
    _proc24 = subprocess.run(
        [
            sys.executable,
            _run_evals_path,
            "--expected-dir",
            os.path.join(_tmp24, "nonexistent_expected"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    _assert(
        _proc24.returncode != 0,
        f"CLI exits nonzero when expected dir is missing (got {_proc24.returncode})",
        (_proc24.stdout + _proc24.stderr)[-200:],
    )


# ---------------------------------------------------------------------------
# Test 25: CLI exits nonzero when expected dir is empty
# ---------------------------------------------------------------------------

print("\n--- Test 25: CLI exits nonzero when expected dir is empty ---")
with _tempfile.TemporaryDirectory() as _tmp25:
    _emp_exp = os.path.join(_tmp25, "empty_expected")
    os.makedirs(_emp_exp)
    _proc25 = subprocess.run(
        [
            sys.executable,
            _run_evals_path,
            "--expected-dir",
            _emp_exp,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    _assert(
        _proc25.returncode != 0,
        f"CLI exits nonzero when expected dir is empty (got {_proc25.returncode})",
        (_proc25.stdout + _proc25.stderr)[-200:],
    )


# ---------------------------------------------------------------------------
# Test 26: CLI exits nonzero when one expected file is missing
# ---------------------------------------------------------------------------

print("\n--- Test 26: CLI exits nonzero when one expected file is missing ---")
with _tempfile.TemporaryDirectory() as _tmp26:
    _cases26 = os.path.join(_tmp26, "cases")
    _exp26 = os.path.join(_tmp26, "expected")
    os.makedirs(_cases26)
    os.makedirs(_exp26)
    # Two cases, only one expected
    for _cid, _idx in [("case_a", "a"), ("case_b", "b")]:
        _cdata = {
            "case_id": _cid,
            "description": f"Case {_cid}",
            "failure_mode": "other",
            "inputs": {},
        }
        with open(os.path.join(_cases26, f"{_idx}.json"), "w") as _f:
            json.dump(_cdata, _f)
    # Only one expected file
    _edata = {"case_id": "case_a", "expected_issue_types": [], "expected_detected": False}
    with open(os.path.join(_exp26, "a.json"), "w") as _f:
        json.dump(_edata, _f)
    _proc26 = subprocess.run(
        [
            sys.executable,
            _run_evals_path,
            "--cases-dir", _cases26,
            "--expected-dir", _exp26,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    _assert(
        _proc26.returncode != 0,
        f"CLI exits nonzero when one expected file is missing (got {_proc26.returncode})",
        (_proc26.stdout + _proc26.stderr)[-300:],
    )


# ---------------------------------------------------------------------------
# Test 27: Malformed case JSON fails
# ---------------------------------------------------------------------------

print("\n--- Test 27: Malformed case JSON fails ---")
with _tempfile.TemporaryDirectory() as _tmp27:
    _cases27 = os.path.join(_tmp27, "cases")
    os.makedirs(_cases27)
    with open(os.path.join(_cases27, "bad.json"), "w") as _f:
        _f.write("{not valid json at all {{")
    try:
        load_eval_cases(_cases27)
        _fail("Malformed case JSON should raise ValueError")
    except ValueError as _e:
        _assert(
            "Failed to load case fixture" in str(_e) or "load" in str(_e).lower(),
            f"ValueError raised for malformed case JSON: {_e!s:.100}",
        )
    except Exception as _e:
        _fail(f"Unexpected exception type for malformed case JSON: {type(_e).__name__}: {_e}")


# ---------------------------------------------------------------------------
# Test 28: Malformed expected JSON fails
# ---------------------------------------------------------------------------

print("\n--- Test 28: Malformed expected JSON fails ---")
with _tempfile.TemporaryDirectory() as _tmp28:
    _exp28 = os.path.join(_tmp28, "expected")
    os.makedirs(_exp28)
    with open(os.path.join(_exp28, "bad.json"), "w") as _f:
        _f.write("{not valid json at all {{")
    try:
        load_expected_outputs(_exp28)
        _fail("Malformed expected JSON should raise ValueError")
    except ValueError as _e:
        _assert(
            "Failed to load expected output fixture" in str(_e) or "load" in str(_e).lower(),
            f"ValueError raised for malformed expected JSON: {_e!s:.100}",
        )
    except Exception as _e:
        _fail(f"Unexpected exception type for malformed expected JSON: {type(_e).__name__}: {_e}")


# ---------------------------------------------------------------------------
# Full reliability regression
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
print("Running full reliability regression...")
print("=" * 60)

_REGRESSION_SCRIPTS = [
    "scripts/test_reliability_foundation.py",
    "scripts/test_reliability_negative_cases.py",
    "scripts/test_reliability_adapters.py",
    "scripts/test_reliability_valuation_adapter.py",
    "scripts/test_reliability_technical_adapter.py",
    "scripts/test_reliability_scanner_rotation_adapter.py",
    "scripts/test_reliability_agent_output.py",
    "scripts/test_reliability_prompt_contracts.py",
    "scripts/test_reliability_mock_agent_roundtrip.py",
    "scripts/test_reliability_orchestration_plan.py",
    "scripts/test_reliability_config.py",
    "scripts/test_reliability_horizon.py",
    "scripts/test_reliability_macro.py",
    "scripts/test_reliability_allocation.py",
    "scripts/test_reliability_options.py",
    "scripts/test_reliability_news.py",
    "scripts/test_reliability_catalysts.py",
    "scripts/test_reliability_validation_aggregator.py",
    "scripts/test_reliability_staleness.py",
    "scripts/test_reliability_critic.py",
]

regression_pass = 0
regression_fail = 0
for script in _REGRESSION_SCRIPTS:
    script_path = os.path.join(_REPO_ROOT, script)
    if not os.path.exists(script_path):
        print(f"  [SKIP] {script} (not found)")
        continue
    try:
        proc = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode == 0:
            regression_pass += 1
            print(f"  [PASS] {script}")
        else:
            regression_fail += 1
            print(f"  [FAIL] {script}")
            # Print last few lines of output for debugging
            out_lines = (proc.stdout + proc.stderr).strip().splitlines()
            for line in out_lines[-5:]:
                print(f"         {line}")
    except subprocess.TimeoutExpired:
        regression_fail += 1
        print(f"  [FAIL] {script} (timeout)")
    except Exception as e:
        regression_fail += 1
        print(f"  [FAIL] {script}: {e}")

print(f"\nRegression: {regression_pass} passed, {regression_fail} failed")


# ---------------------------------------------------------------------------
# Run evals/run_evals.py
# ---------------------------------------------------------------------------

print("\n--- Running evals/run_evals.py ---")
run_evals_path = os.path.join(_REPO_ROOT, "evals", "run_evals.py")
try:
    proc = subprocess.run(
        [sys.executable, run_evals_path],
        capture_output=True,
        text=True,
        timeout=60,
    )
    print(proc.stdout.strip())
    if proc.returncode == 0:
        _ok("evals/run_evals.py exits 0")
    else:
        _fail("evals/run_evals.py exited non-zero", proc.stderr.strip()[:300])
except Exception as e:
    _fail("evals/run_evals.py execution", str(e))


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n" + "=" * 60)
total = _PASS + _FAIL
print(f"Phase 2K Harness Tests: {_PASS}/{total} passed")
if regression_fail > 0:
    print(f"Regression failures:    {regression_fail}/{len(_REGRESSION_SCRIPTS)}")
else:
    print(f"Regression:             {regression_pass}/{len(_REGRESSION_SCRIPTS)} passed")
print("=" * 60)

if _FAIL > 0 or regression_fail > 0:
    sys.exit(1)
sys.exit(0)
