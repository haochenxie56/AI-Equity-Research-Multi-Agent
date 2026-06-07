#!/usr/bin/env python3
"""
scripts/test_reliability_phase_5s_closeout.py

Phase 5S — Phase 5 Productization Closeout test suite.

Phase 5S is a closeout / documentation / state / test-summary pass. It adds no
runtime feature, no UI layout change, and no product-logic change. This test is
therefore **documentation-and-state only**: it asserts that the closeout
artifacts exist, contain the required sections, accurately document the current
product / UI / safety state, and that the state files mark Phase 5R accepted and
Phase 5S implemented / awaiting review without marking Phase 5S accepted or
claiming Phase 6 has started.

It launches no Streamlit server, calls no external API or LLM, and imports no
page module.

Usage:
    python3 scripts/test_reliability_phase_5s_closeout.py
"""

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


PASS = 0
FAIL = 0
_failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        d = f"  [{detail}]" if detail else ""
        _failures.append(f"FAIL  {label}{d}")


def _read(path: str) -> str:
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Paths under test
# ---------------------------------------------------------------------------

CLOSEOUT_DOC = os.path.join(_REPO_ROOT, "docs", "ai_dev_state", "PHASE_5_CLOSEOUT.md")
RELIABILITY_DOC = os.path.join(
    _REPO_ROOT, "docs", "reliability_phase_5s_productization_closeout.md"
)
PROJECT_STATE = os.path.join(_REPO_ROOT, "docs", "ai_dev_state", "PROJECT_STATE.md")
CURRENT_TASK = os.path.join(_REPO_ROOT, "docs", "ai_dev_state", "CURRENT_TASK.md")

_CLOSEOUT = _read(CLOSEOUT_DOC)
_RELIABILITY = _read(RELIABILITY_DOC)
_STATE = _read(PROJECT_STATE)
_TASK = _read(CURRENT_TASK)
_CLOSEOUT_DOCS = _CLOSEOUT + "\n" + _RELIABILITY


# ---------------------------------------------------------------------------
# Section 1 — Both closeout docs exist and are non-empty
# ---------------------------------------------------------------------------

check("1.1 PHASE_5_CLOSEOUT.md exists", os.path.isfile(CLOSEOUT_DOC))
check("1.2 PHASE_5_CLOSEOUT.md non-empty", bool(_CLOSEOUT.strip()))
check(
    "1.3 reliability_phase_5s_productization_closeout.md exists",
    os.path.isfile(RELIABILITY_DOC),
)
check("1.4 reliability doc non-empty", bool(_RELIABILITY.strip()))


# ---------------------------------------------------------------------------
# Section 2 — Required closeout sections in PHASE_5_CLOSEOUT.md
# ---------------------------------------------------------------------------

_CLOSEOUT_SECTIONS = [
    "Closeout Status",
    "Original README App Baseline",
    "Phase 5 Productization Summary",
    "Current Product UI State",
    "Safety / Guardrail Status",
    "Accepted Dirty Worktree Provenance",
    "Validation Matrix",
    "Non-Goals",
    "Recommended Phase 6 Direction",
    "Session Migration Summary",
]
for sec in _CLOSEOUT_SECTIONS:
    check(f"2.x PHASE_5_CLOSEOUT.md contains section: {sec!r}", sec in _CLOSEOUT)


# ---------------------------------------------------------------------------
# Section 3 — Required sections in the reliability companion doc
# ---------------------------------------------------------------------------

_RELIABILITY_SECTIONS = [
    "Purpose",
    "What Phase 5 changed",
    "What Phase 5 did not change",
    "Product architecture after Phase 5",
    "Fixture-only vs live boundaries",
    "UI pages after Phase 5",
    "Validation summary",
    "Next phase recommendation",
    "Guardrails",
    "Acceptance criteria",
]
for sec in _RELIABILITY_SECTIONS:
    check(f"3.x reliability doc contains section: {sec!r}", sec in _RELIABILITY)


# ---------------------------------------------------------------------------
# Section 4 — State files mark Phase 5R accepted + Phase 5S awaiting review
# ---------------------------------------------------------------------------

# Phase 5R accepted in both state files.
check(
    "4.1 PROJECT_STATE marks Phase 5R Accepted",
    "Phase 5R" in _STATE and "Phase 5R is now Accepted" in _STATE,
)
check(
    "4.2 CURRENT_TASK marks Phase 5R accepted",
    "Phase 5R" in _TASK and "Accepted" in _TASK,
)
# Phase 5S implemented / awaiting review in both state files.
check(
    "4.3 PROJECT_STATE marks Phase 5S Implemented — Awaiting Codex Review",
    "Phase 5S" in _STATE and "Implemented" in _STATE and "Awaiting Codex Review" in _STATE,
)
check(
    "4.4 CURRENT_TASK marks Phase 5S as current / awaiting review",
    "Phase 5S" in _TASK and "Awaiting Codex Review" in _TASK,
)


# ---------------------------------------------------------------------------
# Section 5 — Phase 5S is NOT marked accepted anywhere
# ---------------------------------------------------------------------------

# Affirmative-acceptance forms only. Conditional phrasings such as "after Phase
# 5S is accepted" / "until Phase 5S is accepted" are legitimate and must NOT be
# matched here, so the bare "Phase 5S is accepted" substring is intentionally
# excluded.
_PHASE_5S_ACCEPTED_FORMS = [
    "Phase 5S is now Accepted",
    "Phase 5S — Phase 5 Productization Closeout — Accepted",
    "Phase 5S Phase 5 Productization Closeout | **Accepted**",
    "Phase 5S accepted by Codex",
]
for blob_name, blob in (
    ("closeout doc", _CLOSEOUT),
    ("reliability doc", _RELIABILITY),
    ("PROJECT_STATE", _STATE),
    ("CURRENT_TASK", _TASK),
):
    for form in _PHASE_5S_ACCEPTED_FORMS:
        check(
            f"5.x {blob_name} does NOT mark Phase 5S accepted: {form!r}",
            form not in blob,
        )


# ---------------------------------------------------------------------------
# Section 6 — Phase 6 is NOT started
# ---------------------------------------------------------------------------

check(
    "6.1 closeout doc states Phase 6 has not started",
    "Phase 6 has not started" in _CLOSEOUT or "No Phase 6 started" in _CLOSEOUT,
)
check(
    "6.2 reliability doc states Phase 6 not started",
    "Phase 6 has not started" in _RELIABILITY or "Phase 6 has not started" in _CLOSEOUT_DOCS,
)
_PHASE_6_STARTED_FORMS = [
    "Phase 6 has started",
    "Phase 6 is now Accepted",
    "Phase 6A — Phase 6 Planning / Real Integration Boundary Decision | **Accepted**",
    "Phase 6 Accepted",
]
for blob_name, blob in (
    ("closeout doc", _CLOSEOUT),
    ("PROJECT_STATE", _STATE),
    ("CURRENT_TASK", _TASK),
):
    for form in _PHASE_6_STARTED_FORMS:
        check(f"6.x {blob_name} does NOT claim Phase 6 started: {form!r}", form not in blob)


# ---------------------------------------------------------------------------
# Section 7 — No positive approved_for_execution authorization in closeout docs
# ---------------------------------------------------------------------------

_POSITIVE_AUTH_FORMS = [
    "approved_for_execution=True",
    "approved_for_execution = True",
    'approved_for_execution":True',
    'approved_for_execution": True',
    "approved_for_execution: True",
    "approved for execution = True",
]
for form in _POSITIVE_AUTH_FORMS:
    check(
        f"7.x closeout docs contain no positive auth form: {form!r}",
        form not in _CLOSEOUT_DOCS,
    )
# Positive: closeout docs affirm the False/absent invariant.
check(
    "7.a closeout docs affirm approved_for_execution remains False or absent",
    "approved_for_execution remains False or absent" in _CLOSEOUT_DOCS
    or "approved_for_execution` remains False or absent" in _CLOSEOUT_DOCS,
)


# ---------------------------------------------------------------------------
# Section 8 — Guardrail language exists
# ---------------------------------------------------------------------------

_GUARDRAIL_TOKENS = [
    "fixture",
    "review-only",
    "session-only",
    "no broker",  # case-insensitive check below
    "external API",
    "DB / vector store",
    "broker / order / execution",
    "No investment advice",
]
_closeout_lower = _CLOSEOUT_DOCS.lower()
for tok in _GUARDRAIL_TOKENS:
    check(
        f"8.x guardrail language present: {tok!r}",
        tok.lower() in _closeout_lower,
    )


# ---------------------------------------------------------------------------
# Section 9 — Current sidebar structure documented
# ---------------------------------------------------------------------------

check("9.1 sidebar documents Investment Cockpit", "Investment Cockpit" in _CLOSEOUT)
check("9.2 sidebar documents Macro Dashboard", "Macro Dashboard" in _CLOSEOUT)
check("9.3 sidebar documents Overview", "Overview" in _CLOSEOUT)
check("9.4 sidebar documents Sector / Scanner / Equity",
      "Sector" in _CLOSEOUT and "Scanner" in _CLOSEOUT and "Equity" in _CLOSEOUT)
check(
    "9.5 Financial/PriceVolume documented as demoted source modules",
    ("Financial" in _CLOSEOUT and "PriceVolume" in _CLOSEOUT)
    and ("source" in _CLOSEOUT_DOCS and "no longer" in _CLOSEOUT),
)


# ---------------------------------------------------------------------------
# Section 10 — Macro indicators list documented
# ---------------------------------------------------------------------------

_MACRO_INDICATORS = ["WTI", "Gold", "CNN Fear & Greed", "QQQ", "IWM", "NFP", "CPI", "PPI"]
for ind in _MACRO_INDICATORS:
    check(f"10.a closeout doc lists macro indicator: {ind!r}", ind in _CLOSEOUT)
    check(f"10.b reliability doc lists macro indicator: {ind!r}", ind in _RELIABILITY)
# GC explicitly referenced too.
check("10.c closeout doc references GC (gold ticker)", "GC" in _CLOSEOUT)


# ---------------------------------------------------------------------------
# Section 11 — Validation matrix contains confirmed Phase 5 counts
# ---------------------------------------------------------------------------

_CONFIRMED_COUNTS = {
    "5R": "324/324",
    "5Q": "389/389",
    "5O": "766/766",
    "5N": "683/683",
    "5M": "263/263",
    "5L": "220/220",
    "5K": "218/218",
    "5J": "202/202",
}
for phase, count in _CONFIRMED_COUNTS.items():
    check(
        f"11.a closeout doc validation matrix has Phase {phase} count {count}",
        count in _CLOSEOUT,
    )
    check(
        f"11.b reliability doc validation summary has Phase {phase} count {count}",
        count in _RELIABILITY,
    )


# ---------------------------------------------------------------------------
# Section 12 — Next-phase (Phase 6A) recommendation exists
# ---------------------------------------------------------------------------

check(
    "12.1 closeout doc recommends Phase 6A planning / integration boundary decision",
    "Phase 6A" in _CLOSEOUT
    and ("Integration Boundary Decision" in _CLOSEOUT or "Real Integration" in _CLOSEOUT),
)
check(
    "12.2 reliability doc recommends Phase 6A",
    "Phase 6A" in _RELIABILITY,
)


# ---------------------------------------------------------------------------
# Section 13 — Closeout status block present in PHASE_5_CLOSEOUT.md
# ---------------------------------------------------------------------------

check(
    "13.1 closeout doc states Phase 5 not accepted until 5S accepted",
    "not accepted until" in _CLOSEOUT_DOCS,
)
check(
    "13.2 closeout doc lists prior accepted phases (0-3, 4M, 5A-5R)",
    "Phase 0–3" in _CLOSEOUT
    and "Phase 4M" in _CLOSEOUT
    and "Phase 5A through Phase 5R" in _CLOSEOUT,
)
check(
    "13.3 closeout doc documents session migration hand-off",
    "MUST-READ FILES" in _CLOSEOUT and "VALIDATION COMMANDS" in _CLOSEOUT,
)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
print("============================================================")
print(f"Phase 5S Productization Closeout Test Results: {PASS} passed, {FAIL} failed")
print("============================================================")
if _failures:
    for f in _failures:
        print(f)

sys.exit(0 if FAIL == 0 else 1)
