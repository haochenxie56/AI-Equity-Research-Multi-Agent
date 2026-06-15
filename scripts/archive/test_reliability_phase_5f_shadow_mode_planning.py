#!/usr/bin/env python3
"""
scripts/test_reliability_phase_5f_shadow_mode_planning.py

Phase 5F — Shadow Mode Integration Boundary Planning lightweight
planning-doc test.

This script validates *documentation-only* properties of Phase 5F. Phase 5F
is a planning boundary, not a code change, so this test asserts the
planning document exists with the required sections, that the planning is
documentation-only (no new Python runtime module under lib/reliability/,
no new page under pages/), that the forbidden files list exists, that the
doc does not positively authorize approved_for_execution=True, and that
the doc does not contain implementation wording that claims actual shadow
mode is active.

It does NOT exercise any new runtime module (Phase 5F adds none). It does
NOT spin up Streamlit or call any external API.

Usage:
    python3 scripts/test_reliability_phase_5f_shadow_mode_planning.py
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

PHASE_5F_DOC = os.path.join(
    _REPO_ROOT,
    "docs",
    "reliability_phase_5f_shadow_mode_integration_boundary.md",
)

LIB_RELIABILITY_DIR = os.path.join(_REPO_ROOT, "lib", "reliability")
PAGES_DIR = os.path.join(_REPO_ROOT, "pages")


# Forbidden live runtime files — none of these may be modified by Phase 5F.
# We check that they still exist (i.e. were not deleted) and that no Phase 5F
# artifact replaces them. We do NOT diff content here because Phase 5F is a
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
# Section 1 — Phase 5F planning document exists with required sections
# ---------------------------------------------------------------------------

check(
    "1.1 Phase 5F planning doc exists",
    os.path.isfile(PHASE_5F_DOC),
    detail=PHASE_5F_DOC,
)

doc_text = _read_text(PHASE_5F_DOC) if os.path.isfile(PHASE_5F_DOC) else ""

REQUIRED_SECTION_KEYWORDS = [
    "## 1. Purpose",
    "Relationship to Roadmap v4 Phase 5 Investment Cockpit",
    "Relationship to the Original README Streamlit App",
    "Relationship to the Phase 5A Memory Query Contract",
    "Relationship to Phase 5B Company Research Hub View Models",
    "Relationship to Phase 5C Horizon Decision Cards / ThesisTracker",
    "Relationship to Phase 5D Portfolio / TradePlan / Option Overlay",
    "Relationship to Phase 5E UI Planning Boundary",
    "Explicit Statement",  # Explicit Statement — This Is Not Shadow Mode Implementation
    "Future Shadow Mode Goals",
    "Future Shadow Mode Observation Boundaries",
    "Future Prohibited Mutations",
    "Proposed Future Shadow Data Flow",
    "Proposed Future Event / Snapshot Envelope Fields",
    "Feature Flag Plan",
    "Fail-Closed Behavior",
    "Rollback Plan",
    "Error Isolation Plan",
    "No-Blocking Guarantee for the Original Workflow",
    "No-Prompt-Modification Guarantee",
    "No-Output-Modification Guarantee",
    "No-Execution Guarantee",
    "Review-Only Semantics",
    "Safe Degraded States",
    "Security / Privacy Considerations for Local State",
    "Explicit Forbidden Files List",
    "Explicit Non-Goals",
    "Guardrails",
    "Acceptance Criteria",
    "Future Phase 5G Dependency",
]

for kw in REQUIRED_SECTION_KEYWORDS:
    check(
        f"1.2 Phase 5F doc contains required section {kw!r}",
        kw in doc_text,
    )

# Phase 5A–5D contract symbols and core artifacts must be referenced
PHASE_5_CONTRACTS = [
    "Phase 5A",
    "Phase 5B",
    "Phase 5C",
    "Phase 5D",
    "Phase 5E",
    "ExistingWorkflowSnapshot",
    "MemoryQueryResult",
    "MemoryStoreProtocol",
    "CompanyResearchHubView",
    "HorizonDecisionCardsView",
    "ThesisTrackerView",
    "PortfolioCockpitView",
    "TradePlanView",
    "OptionOverlayView",
    "NoTradeReasonView",
    "ExecutionSafetyBannerView",
    "MissingDataWarningView",
    "MissingPortfolioDataWarningView",
]
for sym in PHASE_5_CONTRACTS:
    check(
        f"1.3 Phase 5F doc references Phase 5 contract {sym!r}",
        sym in doc_text,
    )

# Five-step workflow must be explicitly referenced
lc = doc_text.lower()
check(
    "1.4 Phase 5F doc references the existing five-step AI workflow",
    "five-step" in lc or "5-step" in lc,
)

# The doc must reference the existing pages and the existing workflow file
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
        f"1.5 Phase 5F doc references existing page {p!r}",
        p in doc_text,
    )

# The doc must reference Phase 4A explicitly and remind that it stays frozen
check(
    "1.6 Phase 5F doc references Phase 4A",
    "Phase 4A" in doc_text,
)
check(
    "1.7 Phase 5F doc states Phase 4A remains frozen",
    "Phase 4A" in doc_text and "frozen" in lc,
)


# ---------------------------------------------------------------------------
# Section 2 — Planning-only constraints (Phase 5F is not implementation)
# ---------------------------------------------------------------------------

# The planning doc must explicitly state it is not shadow mode implementation.
check(
    "2.1 Phase 5F doc states it is not shadow mode implementation",
    "This Is Not Shadow Mode Implementation" in doc_text
    or "not shadow mode implementation" in doc_text
    or "not shadow mode implementation" in lc,
)

# The planning doc must use future/proposed/planned wording, never claim
# actual shadow mode is active. We sample a few present-tense activation
# substrings that would suggest implementation. Matches are allowed only
# when they appear inside a negation / disclaimer / forbidden context (e.g.
# inside "does not", "must not", "never", "no", "wording that claims",
# "claims actual", "does **not** declare", etc.).
FORBIDDEN_ACTIVE_WORDING = [
    "shadow mode is now active",
    "shadow mode is active",
    "shadow mode is enabled",
    "shadow mode enabled in production",
    "shadow runner is running",
    "shadow runner has been started",
    "snapshot adapter is wired",
    "snapshot adapter wired in",
    "phase 4a is now wired",
    "phase 4a has been wired",
    "approved_for_execution = true is enabled",
    "approved_for_execution=true is enabled",
]
NEGATION_MARKERS_LC = (
    "not",
    "never",
    "no ",
    "without",
    "claim",
    "claims",
    "wording that",
    "deny",
    "denies",
    "denying",
    "does **not**",
    "must **not**",
    "is **not**",
    "are **not**",
    "have **not**",
    "do **not**",
    "shall **not**",
    "forbid",
    "prohibit",
    "disclaimer",
)


def _has_negation_before(text_lc: str, position: int, window: int = 120) -> bool:
    start = max(0, position - window)
    window_text = text_lc[start:position]
    return any(marker in window_text for marker in NEGATION_MARKERS_LC)


for w in FORBIDDEN_ACTIVE_WORDING:
    # Treat each match as safe only when it is preceded by a negation marker
    # within a short window. If any occurrence is *not* negated, fail.
    safe = True
    idx = 0
    while True:
        i = lc.find(w, idx)
        if i < 0:
            break
        if not _has_negation_before(lc, i):
            safe = False
            break
        idx = i + len(w)
    check(
        f"2.2 Phase 5F doc does not positively claim {w!r}",
        safe,
        detail="match appears outside a negation / disclaimer context",
    )

# The planning doc must not positively authorize approved_for_execution = true.
# It is allowed to MENTION the literal "approved_for_execution = True" only
# in a forbidden / negative context (e.g. inside a "does not / never set"
# bullet). We assert that no positive-authorization phrasing surrounds it.
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
    "2.3 Phase 5F doc does not positively authorize approved_for_execution=true",
    not any(p in lc for p in POSITIVE_AUTHORIZATION_PREFIXES_AFE),
)

# The planning doc must reference the always-present execution safety banner.
check(
    "2.4 Phase 5F doc references ExecutionSafetyBannerView",
    "ExecutionSafetyBannerView" in doc_text,
)

# The planning doc must explicitly forbid broker / order / execution paths.
for kw in [
    "broker",
    "order",
    "execution",
]:
    check(
        f"2.5 Phase 5F doc explicitly references forbidden topic {kw!r}",
        kw in lc,
    )

# The planning doc must preserve `no_trade` semantics
check(
    "2.6 Phase 5F doc preserves no_trade as first-class state",
    "no_trade" in doc_text,
)

# The planning doc must reference Phase 5G as the next dependency
check(
    "2.7 Phase 5F doc references Phase 5G dependency",
    "Phase 5G" in doc_text,
)

# The planning doc must not claim Phase 5G has started
check(
    "2.8 Phase 5F doc does not claim Phase 5G has started",
    "Phase 5G started" not in doc_text
    and "Phase 5G has started" not in doc_text
    and "Phase 5G — Started" not in doc_text,
)

# The planning doc must contain a planning-only / future-tense framing for
# shadow components.
for kw in ["future", "planned", "proposed"]:
    check(
        f"2.9 Phase 5F doc uses planning-only wording {kw!r}",
        kw in lc,
    )


# ---------------------------------------------------------------------------
# Section 3 — Forbidden-file enumeration and executable-order-field guard
# ---------------------------------------------------------------------------

# The planning doc must enumerate forbidden files
for fpath in FORBIDDEN_LIVE_RUNTIME_PATHS:
    check(
        f"3.1 Phase 5F doc forbids file {fpath!r}",
        fpath in doc_text,
    )

# The planning doc must not authorize any executable order field outside a
# forbidden / non-goal / guardrail / non-execution / safety context.
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
    "no-execution",
    "prohibited",
    "envelope fields",  # the envelope explicitly hardcodes executable_order_fields=[]
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
            f"3.2 Phase 5F doc does not mention executable order field {ef!r}",
            True,
        )
        continue
    # For each occurrence, find the enclosing "## N. <Heading>" section.
    # The enclosing section must be a forbidden / guardrail / non-execution
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
        f"3.2 Phase 5F doc mentions {ef!r} only inside a forbidden/guardrail section",
        safe,
        detail="executable order field appears outside a non-goal/guardrail/non-execution section",
    )

# Phase 5F must not authorize importing Streamlit. The doc may mention
# Streamlit only to say it is not imported / not modified.
check(
    "3.3 Phase 5F doc does not positively authorize importing Streamlit",
    "import streamlit" not in lc
    or "does not import" in lc
    or "no import of" in lc
    or "must not" in lc
    or "not import" in lc,
)


# ---------------------------------------------------------------------------
# Section 4 — Phase 5F is documentation-only (no new Python module under
# lib/reliability/, no new page under pages/)
# ---------------------------------------------------------------------------

# Phase 5F must not add a new Python module under lib/reliability/. We assert
# that no `phase5f_*.py` / `shadow_mode*.py` module exists.
phase5f_modules = []
for fname in os.listdir(LIB_RELIABILITY_DIR):
    low = fname.lower()
    if (
        low.startswith("phase5f")
        or low.startswith("phase_5f")
        or low == "shadow_mode.py"
        or low.startswith("shadow_mode_")
        or low.startswith("shadow_runner")
        or low.startswith("shadow_snapshot")
    ):
        phase5f_modules.append(fname)

check(
    "4.1 no Phase 5F Python module added under lib/reliability/",
    phase5f_modules == [],
    detail=f"unexpected: {phase5f_modules!r}",
)

# Phase 5F must not add any file under pages/ (only the existing 6 pages
# allowed, no Phase 5F sibling page). The Phase 5H additive cockpit
# preview page (`7_Investment_Cockpit.py`) was added in a *later* phase
# (Phase 5H Controlled Streamlit Cockpit UI Integration v0.1) and is
# permitted to coexist; Phase 5F itself did not add it.
expected_pages = {
    "1_Overview.py",
    "2_Sector.py",
    "3_Scanner.py",
    "4_Equity.py",
    "5_Financial.py",
    "6_PriceVolume.py",
    # Phase 5H additive cockpit preview page (allowed; not Phase 5F):
    "7_Investment_Cockpit.py",
}
pages_present = {
    f
    for f in os.listdir(PAGES_DIR)
    if f.endswith(".py")
}
unexpected_pages = pages_present - expected_pages
check(
    "4.2 no unexpected page file added under pages/",
    not unexpected_pages,
    detail=f"unexpected: {sorted(unexpected_pages)!r}",
)


# ---------------------------------------------------------------------------
# Section 5 — Forbidden live runtime files still present (not deleted)
# ---------------------------------------------------------------------------

for fpath in FORBIDDEN_LIVE_RUNTIME_PATHS:
    abs_path = os.path.join(_REPO_ROOT, fpath)
    check(
        f"5.1 forbidden runtime file still present: {fpath}",
        os.path.isfile(abs_path),
    )


# ---------------------------------------------------------------------------
# Section 6 — Doc mandates fail-closed / rollback / error-isolation /
# no-blocking / no-prompt-mod / no-output-mod / no-execution / review-only /
# safe-degraded / security
# ---------------------------------------------------------------------------

# Each of these planning invariants must be explicitly named in the doc.
PLANNING_INVARIANTS = [
    "fail closed",
    "rollback",
    "error isolation",
    "no-blocking",
    "no-prompt-modification",
    "no-output-modification",
    "no-execution",
    "review-only",
    "safe degraded",
    "security",
]
for inv in PLANNING_INVARIANTS:
    check(
        f"6.1 Phase 5F doc references planning invariant {inv!r}",
        inv in lc,
    )

# The snapshot envelope must hardcode approved_for_execution = False and
# executable_order_fields = [] / empty list.
check(
    "6.2 Phase 5F envelope hardcodes approved_for_execution = False",
    "approved_for_execution" in doc_text
    and "False" in doc_text
    and (
        "hardcoded to `False`" in doc_text
        or "Hardcoded to `False`" in doc_text
        or "hardcodes `approved_for_execution = False`" in doc_text
    ),
)

check(
    "6.3 Phase 5F envelope explicitly bans executable order fields",
    "executable_order_fields" in doc_text
    and ("empty" in lc or "[]" in doc_text),
)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
print("=" * 70)
print("Phase 5F — Shadow Mode Integration Boundary Planning — test results")
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
    print("RESULT: PASS — Phase 5F planning boundary verified.")
    sys.exit(0)
else:
    print("RESULT: FAIL — see failures above.")
    sys.exit(1)
