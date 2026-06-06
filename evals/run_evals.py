#!/usr/bin/env python3
"""
evals/run_evals.py

CLI runner for the Phase 2K Reliability Evaluation Harness.

Usage:
    python3 evals/run_evals.py
    python3 evals/run_evals.py --cases-dir evals/cases --expected-dir evals/expected
    python3 evals/run_evals.py --output evals/latest_summary.json

Exits nonzero if any case fails expectation or errors.
"""

import argparse
import os
import sys

# Add repo root to sys.path so lib.reliability imports work
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from lib.reliability.evaluation import (
    run_reliability_evals,
    save_reliability_score_summary,
    summarize_reliability_score,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the Phase 2K Reliability Evaluation Harness."
    )
    parser.add_argument(
        "--cases-dir",
        default=os.path.join(os.path.dirname(__file__), "cases"),
        help="Directory containing eval case JSON files (default: evals/cases).",
    )
    parser.add_argument(
        "--expected-dir",
        default=os.path.join(os.path.dirname(__file__), "expected"),
        help="Directory containing expected output JSON files (default: evals/expected).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path to write ReliabilityScoreSummary JSON.",
    )
    args = parser.parse_args()

    print(f"[eval] Running reliability evaluation harness...")
    print(f"[eval] Cases dir   : {args.cases_dir}")
    print(f"[eval] Expected dir: {args.expected_dir}")
    print()

    # Pre-flight: explicit checks before calling the runner
    if not os.path.isdir(args.expected_dir):
        print(
            f"[eval] ERROR: Expected outputs directory not found: {args.expected_dir!r}"
        )
        print("[eval] RESULT: FAIL")
        return 1

    if not os.path.isdir(args.cases_dir):
        print(f"[eval] ERROR: Cases directory not found: {args.cases_dir!r}")
        print("[eval] RESULT: FAIL")
        return 1

    try:
        summary = run_reliability_evals(
            cases_dir=args.cases_dir,
            expected_dir=args.expected_dir,
        )
    except Exception as exc:
        print(f"[eval] ERROR: Unexpected error during eval run: {exc}")
        print("[eval] RESULT: FAIL")
        return 1

    # Print per-case results
    for result in summary.results:
        icon = "PASS" if result.passed_expectation else "FAIL"
        if result.status == "error":
            icon = "ERROR"
        elif result.status == "skipped":
            icon = "SKIP"
        print(
            f"  [{icon}] {result.case_id:<50} "
            f"detection={result.detection_status}  "
            f"critical={result.critical_count}  warning={result.warning_count}  "
            f"types={result.detected_issue_types}"
        )
        if not result.passed_expectation or result.status in ("error", "fail"):
            for msg in result.messages:
                if (
                    msg.startswith("FAIL")
                    or msg.startswith("ERROR")
                    or msg.startswith("[critic]")
                    or "Missing expected output" in msg
                    or "Expected output has no matching case" in msg
                    or "load error" in msg.lower()
                ):
                    print(f"         {msg}")

    print()
    brief = summarize_reliability_score(summary)
    print("=" * 60)
    print(f"Total cases:     {brief['total_cases']}")
    print(f"Passed:          {brief['passed_cases']}")
    print(f"Failed:          {brief['failed_cases_count']}")
    print(f"Errors:          {brief['error_cases_count']}")
    print(f"Skipped:         {brief['skipped_cases']}")
    print(f"Detection rate:  {brief['detection_rate']:.1%}")
    print(f"Missed:          {brief['missed_count']}")
    print(f"False positives: {brief['false_positive_count']}")
    if brief["failed_case_ids"]:
        print(f"Failed cases:    {brief['failed_case_ids']}")
    if brief["missed_case_ids"]:
        print(f"Missed cases:    {brief['missed_case_ids']}")
    if brief["error_case_ids"]:
        print(f"Error cases:     {brief['error_case_ids']}")
    print("=" * 60)

    # Failure summary with specific classification
    if summary.failed_cases > 0 or summary.error_cases > 0:
        print()
        print("[eval] FAILURE SUMMARY:")
        missing_expected = [
            r.case_id for r in summary.results
            if r.status == "error"
            and any("Missing expected output" in m for m in r.messages)
        ]
        orphan_expected = [
            r.case_id for r in summary.results
            if r.status == "error"
            and any("Expected output has no matching case" in m for m in r.messages)
        ]
        load_errors = [
            r.case_id for r in summary.results
            if r.status == "error"
            and any(
                ("load error" in m.lower() or "Failed to load" in m)
                for m in r.messages
            )
        ]
        failed_ids = [r.case_id for r in summary.results if r.status == "fail"]
        error_ids = [r.case_id for r in summary.results if r.status == "error"]
        if missing_expected:
            print(f"  Missing expected outputs : {missing_expected}")
        if orphan_expected:
            print(f"  Orphan expected files    : {orphan_expected}")
        if load_errors:
            print(f"  Fixture load errors      : {load_errors}")
        if failed_ids:
            print(f"  Failed cases             : {failed_ids}")
        if error_ids and not (missing_expected or orphan_expected or load_errors):
            print(f"  Error cases              : {error_ids}")

    if args.output:
        save_reliability_score_summary(summary, args.output)
        print(f"[eval] Summary written to: {args.output}")

    # Exit nonzero if any case failed or errored
    if summary.failed_cases > 0 or summary.error_cases > 0:
        print("[eval] RESULT: FAIL")
        return 1

    print("[eval] RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
