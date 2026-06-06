"""
scripts/test_reliability_integration_boundary.py

Phase 4A: Reliability Integration Boundary Contract — test suite.

Tests cover:
  1.  DISABLED mode pass-through: status, should_block, payload, diagnostics,
      reliability_summary, execution_mode, source_workflow fields.
  2.  SHADOW mode non-blocking: status, should_block, payload, diagnostics,
      reliability_summary.
  3.  ENFORCED mode contract (non-live): should_block=False, payload preserved,
      diagnostics non-empty, no mutation of live workflow.
  4.  normalize_execution_mode: lowercase, uppercase, enum passthrough, unknown
      raises ValueError.
  5.  normalize_source_workflow: lowercase, uppercase, enum passthrough, unknown
      raises ValueError.
  6.  Payload and metadata handling: None, non-None payload preserved across
      all modes.
  7.  Frozen model immutability: ReliabilityBoundaryRequest and
      ReliabilityBoundaryResult are frozen Pydantic models.
  8.  Determinism: identical inputs produce identical results.
  9.  Forbidden import checks: no streamlit, no anthropic, no app, no pages,
      no llm_orchestrator, no workflow_state in integration_boundary module.
  10. __init__.py exports: all Phase 4A public symbols accessible from
      lib.reliability namespace and present in __all__.
  11. Regression: existing Phase 3G and Phase 2 closeout test scripts still
      pass.

Usage:
    python3 scripts/test_reliability_integration_boundary.py
"""

import sys
import os

# Add repo root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import copy
import subprocess

import pydantic

from lib.reliability.integration_boundary import (
    ReliabilityBoundaryRequest,
    ReliabilityBoundaryResult,
    ReliabilityBoundaryStatus,
    ReliabilityExecutionMode,
    ReliabilitySourceWorkflow,
    evaluate_reliability_boundary,
    normalize_execution_mode,
    normalize_source_workflow,
)


# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------

PASS = 0
FAIL = 0
_failed_tests: list[str] = []


def ok(label: str) -> None:
    global PASS
    PASS += 1
    print(f"  PASS  {label}")


def fail(label: str, reason: str) -> None:
    global FAIL
    FAIL += 1
    _failed_tests.append(f"{label}: {reason}")
    print(f"  FAIL  {label} — {reason}")


def check(label: str, condition: bool, reason: str = "") -> None:
    if condition:
        ok(label)
    else:
        fail(label, reason or "condition is False")


# ---------------------------------------------------------------------------
# Group 1: DISABLED mode pass-through
# ---------------------------------------------------------------------------

print("\nGroup 1: DISABLED mode pass-through")

_disabled_req = ReliabilityBoundaryRequest(
    source_workflow=ReliabilitySourceWorkflow.EQUITY_PAGE,
    execution_mode=ReliabilityExecutionMode.DISABLED,
    ticker="AAPL",
    payload={"signal": "test"},
)
_disabled_result = evaluate_reliability_boundary(_disabled_req)

check(
    "1a: DISABLED → status=PASS_THROUGH",
    _disabled_result.status == ReliabilityBoundaryStatus.PASS_THROUGH,
    f"got {_disabled_result.status}",
)
check(
    "1b: DISABLED → should_block=False",
    _disabled_result.should_block is False,
    f"got {_disabled_result.should_block}",
)
check(
    "1c: DISABLED → payload preserved",
    _disabled_result.payload == {"signal": "test"},
    f"got {_disabled_result.payload}",
)
check(
    "1d: DISABLED → diagnostics non-empty",
    len(_disabled_result.diagnostics) > 0,
    "diagnostics list is empty",
)
check(
    "1e: DISABLED → reliability_summary is None",
    _disabled_result.reliability_summary is None,
    f"got {_disabled_result.reliability_summary}",
)
check(
    "1f: DISABLED → execution_mode echo",
    _disabled_result.execution_mode == ReliabilityExecutionMode.DISABLED,
    f"got {_disabled_result.execution_mode}",
)
check(
    "1g: DISABLED → source_workflow echo",
    _disabled_result.source_workflow == ReliabilitySourceWorkflow.EQUITY_PAGE,
    f"got {_disabled_result.source_workflow}",
)


# ---------------------------------------------------------------------------
# Group 2: SHADOW mode non-blocking
# ---------------------------------------------------------------------------

print("\nGroup 2: SHADOW mode non-blocking")

_shadow_req = ReliabilityBoundaryRequest(
    source_workflow=ReliabilitySourceWorkflow.SCANNER_PAGE,
    execution_mode=ReliabilityExecutionMode.SHADOW,
    ticker="NVDA",
    payload={"score": 42},
    step_name="scan_step",
)
_shadow_result = evaluate_reliability_boundary(_shadow_req)

check(
    "2a: SHADOW → should_block=False",
    _shadow_result.should_block is False,
    f"got {_shadow_result.should_block}",
)
check(
    "2b: SHADOW → status=SHADOW_EVALUATED",
    _shadow_result.status == ReliabilityBoundaryStatus.SHADOW_EVALUATED,
    f"got {_shadow_result.status}",
)
check(
    "2c: SHADOW → payload preserved",
    _shadow_result.payload == {"score": 42},
    f"got {_shadow_result.payload}",
)
check(
    "2d: SHADOW → diagnostics non-empty",
    len(_shadow_result.diagnostics) > 0,
    "diagnostics list is empty",
)
check(
    "2e: SHADOW → reliability_summary is dict",
    isinstance(_shadow_result.reliability_summary, dict),
    f"got type {type(_shadow_result.reliability_summary).__name__}",
)
check(
    "2f: SHADOW → reliability_summary.shadow_wired is False",
    _shadow_result.reliability_summary.get("shadow_wired") is False,
    f"got {_shadow_result.reliability_summary}",
)
check(
    "2g: SHADOW → execution_mode echo",
    _shadow_result.execution_mode == ReliabilityExecutionMode.SHADOW,
    f"got {_shadow_result.execution_mode}",
)


# ---------------------------------------------------------------------------
# Group 3: ENFORCED mode contract (non-live in Phase 4A)
# ---------------------------------------------------------------------------

print("\nGroup 3: ENFORCED mode contract (non-live)")

_enforced_req = ReliabilityBoundaryRequest(
    source_workflow=ReliabilitySourceWorkflow.FINANCIAL_PAGE,
    execution_mode=ReliabilityExecutionMode.ENFORCED,
    ticker="MSFT",
    payload={"valuation": "dcf_result"},
    run_id="run_test_001",
)
_enforced_result = evaluate_reliability_boundary(_enforced_req)

check(
    "3a: ENFORCED → should_block=False in Phase 4A",
    _enforced_result.should_block is False,
    f"got {_enforced_result.should_block}",
)
check(
    "3b: ENFORCED → payload preserved",
    _enforced_result.payload == {"valuation": "dcf_result"},
    f"got {_enforced_result.payload}",
)
check(
    "3c: ENFORCED → diagnostics non-empty",
    len(_enforced_result.diagnostics) > 0,
    "diagnostics list is empty",
)
check(
    "3d: ENFORCED → reliability_summary is dict",
    isinstance(_enforced_result.reliability_summary, dict),
    f"got type {type(_enforced_result.reliability_summary).__name__}",
)
check(
    "3e: ENFORCED → reliability_summary.enforced_wired is False",
    _enforced_result.reliability_summary.get("enforced_wired") is False,
    f"got {_enforced_result.reliability_summary}",
)
check(
    "3f: ENFORCED → execution_mode echo",
    _enforced_result.execution_mode == ReliabilityExecutionMode.ENFORCED,
    f"got {_enforced_result.execution_mode}",
)
check(
    "3g: ENFORCED → source_workflow echo",
    _enforced_result.source_workflow == ReliabilitySourceWorkflow.FINANCIAL_PAGE,
    f"got {_enforced_result.source_workflow}",
)


# ---------------------------------------------------------------------------
# Group 4: normalize_execution_mode
# ---------------------------------------------------------------------------

print("\nGroup 4: normalize_execution_mode")

check(
    "4a: normalize_execution_mode('disabled') → DISABLED",
    normalize_execution_mode("disabled") == ReliabilityExecutionMode.DISABLED,
)
check(
    "4b: normalize_execution_mode('DISABLED') → DISABLED (uppercase)",
    normalize_execution_mode("DISABLED") == ReliabilityExecutionMode.DISABLED,
)
check(
    "4c: normalize_execution_mode(enum) → passthrough",
    normalize_execution_mode(ReliabilityExecutionMode.DISABLED) == ReliabilityExecutionMode.DISABLED,
)
check(
    "4d: normalize_execution_mode('shadow') → SHADOW",
    normalize_execution_mode("shadow") == ReliabilityExecutionMode.SHADOW,
)
check(
    "4e: normalize_execution_mode('SHADOW') → SHADOW",
    normalize_execution_mode("SHADOW") == ReliabilityExecutionMode.SHADOW,
)
check(
    "4f: normalize_execution_mode('enforced') → ENFORCED",
    normalize_execution_mode("enforced") == ReliabilityExecutionMode.ENFORCED,
)
_raised_mode = False
try:
    normalize_execution_mode("unknown_mode_xyz")
except ValueError:
    _raised_mode = True
check(
    "4g: normalize_execution_mode(unknown string) → ValueError",
    _raised_mode,
    "expected ValueError not raised",
)
_raised_mode_type = False
try:
    normalize_execution_mode(42)
except ValueError:
    _raised_mode_type = True
check(
    "4h: normalize_execution_mode(int) → ValueError",
    _raised_mode_type,
    "expected ValueError not raised for non-string/non-enum",
)


# ---------------------------------------------------------------------------
# Group 5: normalize_source_workflow
# ---------------------------------------------------------------------------

print("\nGroup 5: normalize_source_workflow")

check(
    "5a: normalize_source_workflow('overview_workflow') → OVERVIEW_WORKFLOW",
    normalize_source_workflow("overview_workflow") == ReliabilitySourceWorkflow.OVERVIEW_WORKFLOW,
)
check(
    "5b: normalize_source_workflow('SECTOR_PAGE') → SECTOR_PAGE (uppercase)",
    normalize_source_workflow("SECTOR_PAGE") == ReliabilitySourceWorkflow.SECTOR_PAGE,
)
check(
    "5c: normalize_source_workflow(enum) → passthrough",
    normalize_source_workflow(ReliabilitySourceWorkflow.CLI) == ReliabilitySourceWorkflow.CLI,
)
check(
    "5d: normalize_source_workflow('unknown') → UNKNOWN",
    normalize_source_workflow("unknown") == ReliabilitySourceWorkflow.UNKNOWN,
)
check(
    "5e: normalize_source_workflow('cli') → CLI",
    normalize_source_workflow("cli") == ReliabilitySourceWorkflow.CLI,
)
_raised_workflow = False
try:
    normalize_source_workflow("nonexistent_page_xyz")
except ValueError:
    _raised_workflow = True
check(
    "5f: normalize_source_workflow(unknown string) → ValueError",
    _raised_workflow,
    "expected ValueError not raised",
)
_raised_workflow_type = False
try:
    normalize_source_workflow(99)
except ValueError:
    _raised_workflow_type = True
check(
    "5g: normalize_source_workflow(int) → ValueError",
    _raised_workflow_type,
    "expected ValueError not raised for non-string/non-enum",
)


# ---------------------------------------------------------------------------
# Group 6: Payload and metadata handling
# ---------------------------------------------------------------------------

print("\nGroup 6: Payload and metadata handling")

_no_payload_req = ReliabilityBoundaryRequest(
    source_workflow=ReliabilitySourceWorkflow.CLI,
    execution_mode=ReliabilityExecutionMode.DISABLED,
)
_no_payload_result = evaluate_reliability_boundary(_no_payload_req)
check(
    "6a: payload=None preserved in DISABLED",
    _no_payload_result.payload is None,
    f"got {_no_payload_result.payload}",
)

_rich_payload = {"ticker": "TSLA", "data": [1, 2, 3], "nested": {"x": 1}}
_rich_req_shadow = ReliabilityBoundaryRequest(
    source_workflow=ReliabilitySourceWorkflow.PRICE_VOLUME_PAGE,
    execution_mode=ReliabilityExecutionMode.SHADOW,
    payload=_rich_payload,
    metadata={"session": "abc123"},
)
_rich_shadow_result = evaluate_reliability_boundary(_rich_req_shadow)
check(
    "6b: rich payload preserved in SHADOW",
    _rich_shadow_result.payload == _rich_payload,
    f"got {_rich_shadow_result.payload}",
)

_rich_req_enforced = ReliabilityBoundaryRequest(
    source_workflow=ReliabilitySourceWorkflow.OVERVIEW_WORKFLOW,
    execution_mode=ReliabilityExecutionMode.ENFORCED,
    payload=_rich_payload,
)
_rich_enforced_result = evaluate_reliability_boundary(_rich_req_enforced)
check(
    "6c: rich payload preserved in ENFORCED",
    _rich_enforced_result.payload == _rich_payload,
    f"got {_rich_enforced_result.payload}",
)

check(
    "6d: metadata field in request does not affect payload in result",
    _rich_shadow_result.payload == _rich_payload,
    "payload changed unexpectedly",
)

_req_with_run_id = ReliabilityBoundaryRequest(
    source_workflow=ReliabilitySourceWorkflow.SECTOR_PAGE,
    execution_mode=ReliabilityExecutionMode.SHADOW,
    run_id="AAPL_20260524_120000_abc",
    step_name="sector_eval",
    ticker="AAPL",
)
_result_with_run_id = evaluate_reliability_boundary(_req_with_run_id)
check(
    "6e: optional fields (run_id, step_name, ticker) accepted without error",
    _result_with_run_id.should_block is False,
    "unexpected blocking",
)


# ---------------------------------------------------------------------------
# Group 7: Frozen model immutability
# ---------------------------------------------------------------------------

print("\nGroup 7: Frozen model immutability")

_frozen_req = ReliabilityBoundaryRequest(
    source_workflow=ReliabilitySourceWorkflow.CLI,
    execution_mode=ReliabilityExecutionMode.DISABLED,
)
_frozen_result = evaluate_reliability_boundary(_frozen_req)

_req_frozen_raised = False
try:
    _frozen_req.ticker = "MODIFIED"  # type: ignore[misc]
except Exception:
    _req_frozen_raised = True
check(
    "7a: ReliabilityBoundaryRequest is frozen (cannot set attribute)",
    _req_frozen_raised,
    "expected frozen model error not raised",
)

_res_frozen_raised = False
try:
    _frozen_result.should_block = True  # type: ignore[misc]
except Exception:
    _res_frozen_raised = True
check(
    "7b: ReliabilityBoundaryResult is frozen (cannot set attribute)",
    _res_frozen_raised,
    "expected frozen model error not raised",
)

check(
    "7c: input request is not mutated by evaluate_reliability_boundary",
    _frozen_req.execution_mode == ReliabilityExecutionMode.DISABLED,
    "request was mutated unexpectedly",
)


# ---------------------------------------------------------------------------
# Group 8: Determinism
# ---------------------------------------------------------------------------

print("\nGroup 8: Determinism")

_det_req = ReliabilityBoundaryRequest(
    source_workflow=ReliabilitySourceWorkflow.EQUITY_PAGE,
    execution_mode=ReliabilityExecutionMode.SHADOW,
    ticker="GOOG",
    payload={"price": 180.5},
)
_det_result_1 = evaluate_reliability_boundary(_det_req)
_det_result_2 = evaluate_reliability_boundary(_det_req)

check(
    "8a: identical inputs → identical status",
    _det_result_1.status == _det_result_2.status,
    f"{_det_result_1.status} vs {_det_result_2.status}",
)
check(
    "8b: identical inputs → identical should_block",
    _det_result_1.should_block == _det_result_2.should_block,
    f"{_det_result_1.should_block} vs {_det_result_2.should_block}",
)
check(
    "8c: identical inputs → identical diagnostics",
    _det_result_1.diagnostics == _det_result_2.diagnostics,
    "diagnostics differ",
)


# ---------------------------------------------------------------------------
# Group 9: Forbidden import checks
# ---------------------------------------------------------------------------

print("\nGroup 9: Forbidden import checks")

import importlib
import inspect

_ib_module = importlib.import_module("lib.reliability.integration_boundary")
_ib_src = inspect.getsource(_ib_module)

# Collect only lines that are actual import statements (not docstring mentions).
_import_lines = [
    ln for ln in _ib_src.splitlines()
    if ln.lstrip().startswith("import ") or ln.lstrip().startswith("from ")
]
_import_text = "\n".join(_import_lines)

check(
    "9a: 'streamlit' not in import lines of integration_boundary",
    "streamlit" not in _import_text,
    "streamlit import statement found in module",
)
check(
    "9b: 'anthropic' not in import lines of integration_boundary",
    "anthropic" not in _import_text,
    "anthropic import statement found in module",
)
check(
    "9c: 'app' (app.py) not in import lines of integration_boundary",
    "from app" not in _import_text and "import app" not in _import_text,
    "app import statement found in module",
)
check(
    "9d: 'pages.' not in import lines of integration_boundary",
    "from pages" not in _import_text and "import pages" not in _import_text,
    "pages import statement found in module",
)
check(
    "9e: 'llm_orchestrator' not in import lines of integration_boundary",
    "llm_orchestrator" not in _import_text,
    "llm_orchestrator import statement found in module",
)
check(
    "9f: 'workflow_state' not in import lines of integration_boundary",
    "workflow_state" not in _import_text,
    "workflow_state import statement found in module",
)


# ---------------------------------------------------------------------------
# Group 10: __init__.py exports
# ---------------------------------------------------------------------------

print("\nGroup 10: __init__.py exports")

import lib.reliability as _lib_rel

_PHASE_4A_EXPORTS = [
    "ReliabilityExecutionMode",
    "ReliabilitySourceWorkflow",
    "ReliabilityBoundaryStatus",
    "ReliabilityBoundaryRequest",
    "ReliabilityBoundaryResult",
    "normalize_execution_mode",
    "normalize_source_workflow",
    "evaluate_reliability_boundary",
]

for _sym in _PHASE_4A_EXPORTS:
    check(
        f"10: lib.reliability.{_sym} accessible",
        hasattr(_lib_rel, _sym),
        f"{_sym} not found in lib.reliability namespace",
    )

check(
    "10-all: all Phase 4A symbols in lib.reliability.__all__",
    all(sym in _lib_rel.__all__ for sym in _PHASE_4A_EXPORTS),
    str([s for s in _PHASE_4A_EXPORTS if s not in _lib_rel.__all__]),
)


# ---------------------------------------------------------------------------
# Group 11: Regression (existing Phase 3G and Phase 2 closeout)
# ---------------------------------------------------------------------------

print("\nGroup 11: Regression")

_regression_scripts = [
    "scripts/test_reliability_review_loop.py",
    "scripts/test_reliability_phase_2_closeout.py",
]

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for script in _regression_scripts:
    script_path = os.path.join(repo_root, script)
    if not os.path.exists(script_path):
        fail(f"Regression {script}", "script not found")
        continue
    result = subprocess.run(
        [sys.executable, script_path],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    if result.returncode == 0:
        ok(f"Regression {script}")
    else:
        fail(
            f"Regression {script}",
            result.stderr[-300:] if result.stderr else "exit code non-zero",
        )


# ---------------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------------

print(f"\n{'='*60}")
print(f"  Phase 4A Test Results: {PASS} passed, {FAIL} failed")
print(f"{'='*60}")
if _failed_tests:
    print("  Failed tests:")
    for t in _failed_tests:
        print(f"    - {t}")
    sys.exit(1)
else:
    print("  All tests passed.")
    sys.exit(0)
