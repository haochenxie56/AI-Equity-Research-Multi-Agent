#!/usr/bin/env python3
"""
scripts/test_reliability_phase_5e_cockpit_ui_planning.py

Phase 5E — Cockpit UI Planning Boundary lightweight planning-doc test.

This script validates *documentation-only* properties of Phase 5E. Phase 5E
is a planning boundary, not a code change, so this test asserts the
planning document and the state artifact exist with the required sections,
that the planning is documentation-only, and that no live runtime files
were touched by Phase 5E.

It does NOT exercise any new runtime module (Phase 5E adds none). It does
NOT spin up Streamlit or call any external API.

Usage:
    python3 scripts/test_reliability_phase_5e_cockpit_ui_planning.py
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


# ---------------------------------------------------------------------------
# Paths under test
# ---------------------------------------------------------------------------

PHASE_5E_DOC = os.path.join(
    _REPO_ROOT,
    "docs",
    "reliability_phase_5e_cockpit_ui_planning_boundary.md",
)
PHASE_5E_STATE_ARTIFACT = os.path.join(
    _REPO_ROOT,
    "docs",
    "ai_dev_state",
    "PHASE_5E_COCKPIT_UI_PLAN.md",
)

PHASE_5D_MODULE = os.path.join(
    _REPO_ROOT, "lib", "reliability", "phase5_portfolio_views.py"
)

LIB_RELIABILITY_DIR = os.path.join(_REPO_ROOT, "lib", "reliability")
PAGES_DIR = os.path.join(_REPO_ROOT, "pages")


# Forbidden live runtime files — none of these may be modified by Phase 5E.
# We check that they still exist (i.e. were not deleted) and that no Phase 5E
# artifact replaces them. We do NOT diff content here because Phase 5E is a
# documentation phase and other phases or unrelated work may have legitimately
# touched these files in a separate context.
FORBIDDEN_LIVE_RUNTIME_PATHS = [
    "app.py",
    "pages/1_Overview.py",
    "pages/2_Sector.py",
    "pages/3_Scanner.py",
    "pages/4_Equity.py",
    "pages/5_Financial.py",
    "pages/6_PriceVolume.py",
    "lib/llm_orchestrator.py",
    "lib/valuation.py",
    "lib/technical.py",
    "lib/rotation.py",
    "lib/data_fetcher.py",
    "lib/workflow_state.py",
    "lib/cache_manager.py",
    "lib/reliability/integration_boundary.py",
]


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Section 1 — Phase 5E planning document exists with required sections
# ---------------------------------------------------------------------------

check(
    "1.1 Phase 5E planning doc exists",
    os.path.isfile(PHASE_5E_DOC),
    detail=PHASE_5E_DOC,
)

doc_text = _read_text(PHASE_5E_DOC) if os.path.isfile(PHASE_5E_DOC) else ""

REQUIRED_SECTION_KEYWORDS = [
    "## 1. Purpose",
    "Relationship to Roadmap v4 Phase 5 Investment Cockpit",
    "Relationship to the Original README Streamlit App",
    "Explicit Statement",  # "Explicit Statement — This Is Not UI Implementation"
    "Existing Pages To Preserve",
    "Proposed Future Cockpit Navigation Structure",
    "Proposed Future Cockpit Surfaces",
    "Mapping From Existing Pages to Future Cockpit Surfaces",
    "Mapping From Phase 5A",  # Mapping From Phase 5A–5D View-Models
    "Data Dependency Matrix",
    "Component Boundary Map",
    "Feature Flag",  # Feature Flag / Integration Readiness Plan
    "Safe Degraded UI States",
    "Review-Only",  # Review-Only / Non-Execution UI Semantics
    "Explicit Forbidden Files List",
    "Explicit Non-Goals",
    "Guardrails",
    "Acceptance Criteria",
    "Future Phase 5F Dependency",
]

for kw in REQUIRED_SECTION_KEYWORDS:
    check(
        f"1.2 Phase 5E doc contains required section {kw!r}",
        kw in doc_text,
    )

# Cockpit surfaces required by the task brief
COCKPIT_SURFACES = [
    "Investment Cockpit",
    "Company Research Hub",
    "Horizon Decision Cards",
    "ThesisTracker",
    "Portfolio / Allocation Cockpit",
    "TradePlan Review",
    "Option Overlay",
    "Human Feedback Review",
    "Catalyst / News / Earnings Monitor",
    "Macro Dashboard",
]
for surf in COCKPIT_SURFACES:
    check(
        f"1.3 Phase 5E doc references cockpit surface {surf!r}",
        surf in doc_text,
    )

# Each preserved existing page must be enumerated
EXISTING_PAGES = [
    "Overview",
    "Sector",
    "Scanner",
    "Equity",
    "Financial",
    "PriceVolume",
]
for p in EXISTING_PAGES:
    check(
        f"1.4 Phase 5E doc references existing page {p!r}",
        p in doc_text,
    )

# Five-step workflow must be explicitly referenced
check(
    "1.5 Phase 5E doc references the existing five-step AI workflow",
    "five-step" in doc_text.lower() or "5-step" in doc_text.lower(),
)


# ---------------------------------------------------------------------------
# Section 2 — Planning-only constraints (planning doc text)
# ---------------------------------------------------------------------------

# The planning doc must explicitly state it is not UI implementation.
check(
    "2.1 Phase 5E doc states it is not UI implementation",
    "This Is Not UI Implementation" in doc_text or "not UI implementation" in doc_text,
)

# The planning doc must not authorize approved_for_execution = true.
# It is allowed to MENTION the literal "approved_for_execution = True" only
# in a forbidden / negative context (e.g. inside a "does not / never set"
# bullet). We assert that no positive-authorization phrasing surrounds it.
lc = doc_text.lower()
POSITIVE_AUTHORIZATION_PREFIXES_AFE = [
    "set approved_for_execution = true",
    "set approved_for_execution=true",
    "enable approved_for_execution = true",
    "enable approved_for_execution=true",
    "authorize approved_for_execution = true",
    "authorize approved_for_execution=true",
    "render approved_for_execution = true",
    "render approved_for_execution=true",
    "introduce approved_for_execution = true",
    "introduce approved_for_execution=true",
    "approved_for_execution = true is allowed",
    "approved_for_execution=true is allowed",
]
check(
    "2.2 Phase 5E doc does not positively authorize approved_for_execution=true",
    not any(p in lc for p in POSITIVE_AUTHORIZATION_PREFIXES_AFE),
)

# The planning doc must reference the always-present execution safety banner.
check(
    "2.3 Phase 5E doc references ExecutionSafetyBannerView",
    "ExecutionSafetyBannerView" in doc_text,
)

# The planning doc must explicitly forbid broker / order / execution paths.
for kw in [
    "broker",
    "order",
    "execution",
]:
    check(
        f"2.4 Phase 5E doc explicitly references forbidden topic {kw!r}",
        kw in lc,
    )

# The planning doc must mention each Phase 5A–5D contract by name
PHASE_5_CONTRACTS = [
    "Phase 5A",
    "Phase 5B",
    "Phase 5C",
    "Phase 5D",
    "MemoryQueryResult",
    "CompanyResearchHubView",
    "HorizonDecisionCardsView",
    "ThesisTrackerView",
    "PortfolioCockpitView",
    "TradePlanView",
    "OptionOverlayView",
    "NoTradeReasonView",
]
for sym in PHASE_5_CONTRACTS:
    check(
        f"2.5 Phase 5E doc references Phase 5 contract {sym!r}",
        sym in doc_text,
    )

# The planning doc must preserve `no_trade` semantics
check(
    "2.6 Phase 5E doc preserves no_trade as first-class state",
    "no_trade" in doc_text,
)

# The planning doc must reference Phase 5F as the next dependency
check(
    "2.7 Phase 5E doc references Phase 5F dependency",
    "Phase 5F" in doc_text,
)

# The planning doc must not claim Phase 5F has started
check(
    "2.8 Phase 5E doc does not claim Phase 5F has started",
    "Phase 5F started" not in doc_text
    and "Phase 5F has started" not in doc_text
    and "Phase 5F — Started" not in doc_text,
)


# ---------------------------------------------------------------------------
# Section 3 — Forbidden-file references and forbidden runtime substrings
# ---------------------------------------------------------------------------

# The planning doc must enumerate forbidden files
for fpath in FORBIDDEN_LIVE_RUNTIME_PATHS:
    check(
        f"3.1 Phase 5E doc forbids file {fpath!r}",
        fpath in doc_text,
    )

# The planning doc must not authorize any executable order field
EXECUTABLE_ORDER_FIELDS = [
    "order_type",
    "time_in_force",
    "broker_route",
    "broker_id",
    "account_id",
    "quantity_to_execute",
    "broker_payload",
    "order_ticket",
    "execution_id",
    "fill_price",
]
# These names may appear in the doc — but only in *forbidden* contexts
# (e.g. inside a "does not / must not" enumeration). We assert that no
# positive-authorization phrasing surrounds any of them.
POSITIVE_AUTHORIZATION_VERBS = (
    "render",
    "show",
    "add",
    "expose",
    "include",
    "introduce",
    "set",
    "authorize",
    "enable",
    "surface",
)
SAFE_SECTION_KEYWORDS_LC = (
    "non-goal",
    "guardrail",
    "forbidden",
    "non-execution",
    "review-only",
    "boundary",
    "safety",
    "explicit statement",
    "safe degraded",
    "acceptance criteria",
)


def _enclosing_section_header_lc(text: str, position: int) -> str:
    # Walk backward to the most recent line starting with "## " and return
    # the header line lowercased. Empty string if none found.
    idx = text.rfind("\n## ", 0, position)
    if idx < 0:
        if text.startswith("## "):
            line_end = text.find("\n")
            return text[:line_end].lower() if line_end > 0 else text.lower()
        return ""
    line_start = idx + 1
    line_end = text.find("\n", line_start)
    if line_end < 0:
        line_end = len(text)
    return text[line_start:line_end].lower()


for ef in EXECUTABLE_ORDER_FIELDS:
    if ef not in doc_text:
        check(
            f"3.2 Phase 5E doc does not mention executable order field {ef!r}",
            True,
        )
        continue
    # For each occurrence, find the enclosing "## N. <Heading>" section.
    # The enclosing section must be a forbidden/guardrail/non-execution
    # context (its header must contain one of SAFE_SECTION_KEYWORDS_LC).
    safe = True
    idx = 0
    while True:
        i = doc_text.find(ef, idx)
        if i < 0:
            break
        header_lc = _enclosing_section_header_lc(doc_text, i)
        if not any(kw in header_lc for kw in SAFE_SECTION_KEYWORDS_LC):
            safe = False
            break
        idx = i + len(ef)
    check(
        f"3.2 Phase 5E doc mentions {ef!r} only inside a forbidden/guardrail section",
        safe,
        detail="executable order field appears outside a non-goal/guardrail/non-execution section",
    )

# Phase 5E must not import Streamlit in any new Python module.
# We assert by searching the Phase 5E doc for any positive authorization to
# import Streamlit.
check(
    "3.3 Phase 5E doc does not authorize importing Streamlit",
    "import streamlit" not in lc
    or "does not import" in lc
    or "no import of" in lc
    or "must not" in lc,
)


# ---------------------------------------------------------------------------
# Section 4 — Phase 5E state artifact exists
# ---------------------------------------------------------------------------

check(
    "4.1 Phase 5E state artifact exists",
    os.path.isfile(PHASE_5E_STATE_ARTIFACT),
    detail=PHASE_5E_STATE_ARTIFACT,
)

state_text = (
    _read_text(PHASE_5E_STATE_ARTIFACT)
    if os.path.isfile(PHASE_5E_STATE_ARTIFACT)
    else ""
)

# State artifact must reference each cockpit surface
for surf in COCKPIT_SURFACES:
    check(
        f"4.2 Phase 5E state artifact references cockpit surface {surf!r}",
        surf in state_text,
    )

# State artifact must reference each existing page
for p in EXISTING_PAGES:
    check(
        f"4.3 Phase 5E state artifact references existing page {p!r}",
        p in state_text,
    )

# State artifact must reference forbidden files
for fpath in FORBIDDEN_LIVE_RUNTIME_PATHS:
    check(
        f"4.4 Phase 5E state artifact forbids file {fpath!r}",
        fpath in state_text,
    )

# State artifact must not authorize approved_for_execution = True
state_lc = state_text.lower()
check(
    "4.5 Phase 5E state artifact does not authorize approved_for_execution=true",
    "approved_for_execution = true" not in state_lc
    and "approved_for_execution=true" not in state_lc,
)


# ---------------------------------------------------------------------------
# Section 5 — Phase 5E is documentation-only (no new Python UI module)
# ---------------------------------------------------------------------------

# Phase 5E must not add a new Python module under lib/reliability/. We assert
# that no `phase5e_*.py` module exists.
phase5e_modules = []
for fname in os.listdir(LIB_RELIABILITY_DIR):
    low = fname.lower()
    if (
        low.startswith("phase5e")
        or low.startswith("phase_5e")
        or low == "cockpit_ui.py"
        or low.startswith("cockpit_ui_")
    ):
        phase5e_modules.append(fname)

check(
    "5.1 no Phase 5E Python module added under lib/reliability/",
    phase5e_modules == [],
    detail=f"unexpected: {phase5e_modules!r}",
)

# Phase 5E must not add any file under pages/ (only the existing 6 pages
# allowed, no Phase 5E sibling page). The Phase 5H additive cockpit
# preview page (`7_Investment_Cockpit.py`) was added in a *later* phase
# (Phase 5H Controlled Streamlit Cockpit UI Integration v0.1) and is
# permitted to coexist; Phase 5E itself did not add it.
expected_pages = {
    "1_Overview.py",
    "2_Sector.py",
    "3_Scanner.py",
    "4_Equity.py",
    "5_Financial.py",
    "6_PriceVolume.py",
    # Phase 5H additive cockpit preview page (allowed; not Phase 5E):
    "7_Investment_Cockpit.py",
}
pages_present = {
    f
    for f in os.listdir(PAGES_DIR)
    if f.endswith(".py")
}
unexpected_pages = pages_present - expected_pages
check(
    "5.2 no unexpected page file added under pages/",
    not unexpected_pages,
    detail=f"unexpected: {sorted(unexpected_pages)!r}",
)


# ---------------------------------------------------------------------------
# Section 6 — Forbidden live runtime files still present (not deleted)
# ---------------------------------------------------------------------------

for fpath in FORBIDDEN_LIVE_RUNTIME_PATHS:
    abs_path = os.path.join(_REPO_ROOT, fpath)
    check(
        f"6.1 forbidden runtime file still present: {fpath}",
        os.path.isfile(abs_path),
    )


# ---------------------------------------------------------------------------
# Section 7 — Phase 5D minor-suggestion cleanup applied
# ---------------------------------------------------------------------------

check(
    "7.1 lib/reliability/phase5_portfolio_views.py still exists",
    os.path.isfile(PHASE_5D_MODULE),
)

module_text = (
    _read_text(PHASE_5D_MODULE) if os.path.isfile(PHASE_5D_MODULE) else ""
)

# After Phase 5D minor-suggestion cleanup, model_validator must NOT appear in
# the module's import block (search the first 200 lines / 8000 chars).
header_window = module_text[:8000]
check(
    "7.2 model_validator no longer imported in Phase 5D module",
    "model_validator" not in header_window,
    detail="unused import survived Phase 5D minor-suggestion cleanup",
)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
print("=" * 70)
print("Phase 5E — Cockpit UI Planning Boundary — planning-doc test results")
print("=" * 70)

if _failures:
    print()
    for line in _failures:
        print(line)

print()
print(f"Passed: {PASS}")
print(f"Failed: {FAIL}")
print(f"Total:  {PASS + FAIL}")
print()

if FAIL == 0:
    print("RESULT: PASS — Phase 5E planning boundary verified.")
    sys.exit(0)
else:
    print("RESULT: FAIL — see failures above.")
    sys.exit(1)
