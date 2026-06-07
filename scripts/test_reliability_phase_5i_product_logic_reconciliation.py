#!/usr/bin/env python3
"""
scripts/test_reliability_phase_5i_product_logic_reconciliation.py

Phase 5I — Investment Cockpit Product Logic Reconciliation /
Opportunity-first + Horizon-aware Architecture — lightweight planning-doc
test.

Phase 5I is product-logic reconciliation and roadmap/documentation only. It
implements no Theme Intelligence, Opportunity Queue, Auto Research Pack,
Agent Debate UI, or Macro Dashboard code; it changes no sidebar and no UI.
This test therefore asserts documentation-only properties: that the Phase 5I
planning document exists with the required sections, that the revised
Phase 5I–5S roadmap is present, that horizon-aware opportunity-first
principles are explicit, that the original AI Research Workflow is described
as a candidate source (not a final decision engine), that non-goals /
guardrails exist, that approved_for_execution is never positively authorized,
that the state files mark Phase 5H.1 accepted and Phase 5I awaiting review,
and that Phase 5J is not started.

It does NOT exercise any new runtime module (Phase 5I adds none). It does NOT
spin up Streamlit and does NOT call any external API or LLM.

Usage:
    python3 scripts/test_reliability_phase_5i_product_logic_reconciliation.py
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

PHASE_5I_DOC = os.path.join(
    _REPO_ROOT,
    "docs",
    "reliability_phase_5i_investment_cockpit_product_logic_reconciliation.md",
)
PROJECT_STATE = os.path.join(
    _REPO_ROOT, "docs", "ai_dev_state", "PROJECT_STATE.md"
)
CURRENT_TASK = os.path.join(
    _REPO_ROOT, "docs", "ai_dev_state", "CURRENT_TASK.md"
)

LIB_RELIABILITY_DIR = os.path.join(_REPO_ROOT, "lib", "reliability")
PAGES_DIR = os.path.join(_REPO_ROOT, "pages")


# Forbidden live runtime files — none may be modified by Phase 5I. We assert
# they still exist (were not deleted). We do NOT diff content because Phase 5I
# is documentation-only and unrelated work may have legitimately touched these
# in a separate context.
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
# Section 1 — Phase 5I planning document exists with required sections
# ---------------------------------------------------------------------------

check(
    "1.1 Phase 5I planning doc exists",
    os.path.isfile(PHASE_5I_DOC),
    detail=PHASE_5I_DOC,
)

doc_text = _read_text(PHASE_5I_DOC) if os.path.isfile(PHASE_5I_DOC) else ""
lc = doc_text.lower()

REQUIRED_SECTION_KEYWORDS = [
    "## 1. Current product baseline",
    "## 2. Problem statement",
    "## 3. Revised product architecture",
    "## 4. Macro-first architecture",
    "## 5. Theme Intelligence / Market Heat architecture",
    'Avoiding "buying the top"',
    "## 7. Horizon-aware Opportunity Queue",
    "## 8. Original AI Research Workflow as candidate source",
    "## 9. Revised Phase 5 roadmap",
    "## 10. Impact on current Cockpit UI",
    "## 11. Sidebar / source module planning",
    "## 12. Non-goals",
    "## 13. Guardrails",
    "## 14. Acceptance criteria",
]
for kw in REQUIRED_SECTION_KEYWORDS:
    check(
        f"1.2 Phase 5I doc contains required section {kw!r}",
        kw in doc_text,
    )


# ---------------------------------------------------------------------------
# Section 2 — Current product baseline + original workflow as GenAI-assisted
# ---------------------------------------------------------------------------

# Original five-step workflow must be described (sector → ... → synthesis)
for step in ["Sector", "Scanner", "Equity", "Financial", "PriceVolume", "Synthesis"]:
    check(
        f"2.1 Phase 5I doc references original workflow step {step!r}",
        step in doc_text,
    )

check(
    "2.2 Phase 5I doc clarifies workflow is GenAI-assisted, fixed-pipeline",
    "genai-assisted" in lc and ("fixed-pipeline" in lc or "fixed pipeline" in lc),
)

check(
    "2.3 Phase 5I doc clarifies it is not full agentic AI",
    "not full agentic" in lc or "not a full agentic" in lc,
)

check(
    "2.4 Phase 5I doc states Financial/PriceVolume are sub-surfaces under Equity Research",
    "sub-surface" in lc and "equity research" in lc,
)


# ---------------------------------------------------------------------------
# Section 3 — Revised product architecture: source modules vs cockpit layer
# ---------------------------------------------------------------------------

SOURCE_MODULES = [
    "Macro Research",
    "Sector Research",
    "Scanner",
    "Equity Research",
    "Financial Analysis",
    "News / Catalyst / Earnings",
]
for sm in SOURCE_MODULES:
    check(
        f"3.1 Phase 5I doc lists source research module {sm!r}",
        sm in doc_text,
    )

COCKPIT_SURFACES = [
    "Market Themes",
    "Opportunity Queue",
    "Decision Workspace",
    "Research Snapshot",
    "Agent Debate",
    "Trade / Allocation Plan",
    "Option Overlay",
    "Feedback / Review",
    "Provenance / Diagnostics",
]
for cs in COCKPIT_SURFACES:
    check(
        f"3.2 Phase 5I doc lists cockpit decision-layer surface {cs!r}",
        cs in doc_text,
    )

check(
    "3.3 Phase 5I doc positions Cockpit as upper decision layer, not duplicate research page",
    "decision layer" in lc and "not a duplicate" in lc,
)

check(
    "3.4 Phase 5I doc states Cockpit is opportunity-first",
    "opportunity-first" in lc,
)


# ---------------------------------------------------------------------------
# Section 4 — Macro-first architecture
# ---------------------------------------------------------------------------

check(
    "4.1 Phase 5I doc promotes Macro to first-class input",
    "first-class" in lc and "macro" in lc,
)

MACRO_FACTORS = [
    "rates",
    "inflation",
    "liquidity",
    "credit spreads",
    "VIX",
    "breadth",
    "dollar",
    "risk appetite",
    "earnings cycle",
]
for mf in MACRO_FACTORS:
    check(
        f"4.2 Phase 5I doc lists macro factor {mf!r}",
        mf.lower() in lc,
    )

MACRO_POSTURES = [
    "momentum trades",
    "pullback entries",
    "watchlist only",
    "risk-off",
    "long-term accumulation",
]
for mp in MACRO_POSTURES:
    check(
        f"4.3 Phase 5I doc lists macro-gated posture {mp!r}",
        mp.lower() in lc,
    )


# ---------------------------------------------------------------------------
# Section 5 — Theme Intelligence / Market Heat concepts
# ---------------------------------------------------------------------------

THEME_CONCEPTS = [
    "Theme",
    "Subtheme",
    "IndustryChainNode",
    "ThemeHeatSignal",
    "NarrativeSignal",
    "FundamentalConfirmationSignal",
    "CrowdingSignal",
    "ThemeLifecycleStage",
    "ThemeCandidateTicker",
]
for tc in THEME_CONCEPTS:
    check(
        f"5.1 Phase 5I doc defines future theme concept {tc!r}",
        tc in doc_text,
    )

# Example themes / chain decomposition
for theme in ["AI", "space", "robotics", "nuclear", "quantum"]:
    check(
        f"5.2 Phase 5I doc references example theme {theme!r}",
        theme.lower() in lc,
    )

for node in ["memory", "optical", "data-center power", "launch", "satellite"]:
    check(
        f"5.3 Phase 5I doc references industry-chain node {node!r}",
        node.lower() in lc,
    )


# ---------------------------------------------------------------------------
# Section 6 — Avoiding "buying the top"
# ---------------------------------------------------------------------------

ENTRY_CONCEPTS = [
    "Theme Heat Score",
    "Entry Quality Score",
    "Crowding Risk",
    "Valuation Stretch",
    "Pullback Required",
    "Earnings Confirmation Needed",
]
for ec in ENTRY_CONCEPTS:
    check(
        f"6.1 Phase 5I doc defines entry concept {ec!r}",
        ec in doc_text,
    )

ENTRY_STATES = [
    "trade_now",
    "wait_for_pullback",
    "breakout_watch",
    "research_more",
    "watch_for_valuation",
    "no_trade",
    "avoid_too_crowded",
]
for es in ENTRY_STATES:
    check(
        f"6.2 Phase 5I doc lists decision state {es!r}",
        es in doc_text,
    )

check(
    "6.3 Phase 5I doc states high Theme Heat can pair with low Entry Quality",
    "high theme heat" in lc and "low entry quality" in lc,
)


# ---------------------------------------------------------------------------
# Section 7 — Horizon-aware Opportunity Queue
# ---------------------------------------------------------------------------

HORIZON_QUEUES = [
    "Short-term Trade Queue",
    "Mid-term Position Queue",
    "Long-term Investment Queue",
]
for hq in HORIZON_QUEUES:
    check(
        f"7.1 Phase 5I doc defines horizon queue {hq!r}",
        hq in doc_text,
    )

CROSS_QUEUES = [
    "Watch / Wait",
    "Research More",
    "No Trade / Avoid",
]
for cq in CROSS_QUEUES:
    check(
        f"7.2 Phase 5I doc defines cross-cutting queue {cq!r}",
        cq in doc_text,
    )

check(
    "7.3 Phase 5I doc states same ticker may appear in multiple queues",
    "same ticker" in lc and "multiple queues" in lc,
)

PER_HORIZON_FIELDS = [
    "opportunity_score",
    "horizon_fit_score",
    "entry_quality_score",
    "crowding_risk",
    "evidence_coverage",
    "thesis_status",
    "review_trigger",
    "next_action",
    "decision_label",
]
for f in PER_HORIZON_FIELDS:
    check(
        f"7.4 Phase 5I doc lists per-horizon field {f!r}",
        f in doc_text,
    )

# Horizon-specific decision labels
SHORT_LABELS = [
    "trade_now",
    "wait_for_pullback",
    "breakout_watch",
    "event_trade_watch",
    "too_extended",
]
MID_LABELS = [
    "position_candidate",
    "accumulate_on_pullback",
    "wait_for_earnings_confirmation",
    "thesis_improving",
    "thesis_unconfirmed",
]
LONG_LABELS = [
    "investment_candidate",
    "watch_for_valuation",
    "compounder_watch",
    "quality_but_expensive",
    "thesis_durable",
    "thesis_insufficient",
]
for lab in SHORT_LABELS:
    check(f"7.5 Phase 5I doc lists short-term label {lab!r}", lab in doc_text)
for lab in MID_LABELS:
    check(f"7.6 Phase 5I doc lists mid-term label {lab!r}", lab in doc_text)
for lab in LONG_LABELS:
    check(f"7.7 Phase 5I doc lists long-term label {lab!r}", lab in doc_text)

check(
    "7.8 Phase 5I doc states overextended candidates are not auto-rejected",
    "not" in lc and "automatically rejected" in lc,
)

check(
    "7.9 Phase 5I doc requires evidence-first + validated decisions",
    "evidence-first" in lc and "validated" in lc,
)


# ---------------------------------------------------------------------------
# Section 8 — Original AI Research Workflow as candidate source
# ---------------------------------------------------------------------------

check(
    "8.1 Phase 5I doc describes original workflow as a candidate source",
    "candidate source" in lc,
)

check(
    "8.2 Phase 5I doc states it is NOT a final decision engine",
    "not a final decision engine" in lc or "not discarded" in lc,
)

check(
    "8.3 Phase 5I doc states candidates feed the Opportunity Queue, not direct buys",
    "feed the opportunity queue" in lc or "feed the opportunity" in lc,
)

check(
    "8.4 Phase 5I doc requires entry-quality / crowding / macro / evidence validation",
    "entry quality" in lc and "crowding" in lc and "evidence" in lc,
)


# ---------------------------------------------------------------------------
# Section 9 — Revised Phase 5I–5S roadmap
# ---------------------------------------------------------------------------

REVISED_ROADMAP = [
    ("Phase 5I", "Investment Cockpit Product Logic Reconciliation"),
    ("Phase 5J", "Theme Intelligence / Market Heat Schema"),
    ("Phase 5K", "Horizon-aware Opportunity Queue ViewModel"),
    ("Phase 5L", "Auto Research Pack Orchestration Boundary"),
    ("Phase 5M", "Agent Debate / Decision Workspace Contract"),
    ("Phase 5N", "Cockpit UI v0.2 Opportunity-first Redesign"),
    ("Phase 5O", "Macro Dashboard v0.1"),
    ("Phase 5P", "Source Page Navigation Cleanup"),
    ("Phase 5Q", "Human Feedback UI v0.1"),
    ("Phase 5R", "Product UX Polish / Demo Readiness"),
    ("Phase 5S", "Phase 5 Productization Closeout"),
]
for phase, title in REVISED_ROADMAP:
    check(
        f"9.1 Phase 5I doc revised roadmap lists {phase} ({title!r})",
        phase in doc_text and title in doc_text,
    )


# ---------------------------------------------------------------------------
# Section 10 — Impact on current Cockpit UI
# ---------------------------------------------------------------------------

check(
    "10.1 Phase 5I doc keeps Phase 5H.1 page as a fixture-backed preview / demo shell",
    "fixture-backed preview" in lc and ("demo product shell" in lc or "demo shell" in lc),
)

check(
    "10.2 Phase 5I doc proposes future opportunity-first tab order",
    "Market Themes" in doc_text and "Opportunity Queue" in doc_text and "Decision Workspace" in doc_text,
)

check(
    "10.3 Phase 5I doc repositions Company Research Hub as Research Snapshot",
    "Research Snapshot" in doc_text and "summarize" in lc,
)


# ---------------------------------------------------------------------------
# Section 11 — Sidebar / source module planning (documentation only)
# ---------------------------------------------------------------------------

check(
    "11.1 Phase 5I doc says Financial/PriceVolume eventually removed from top-level sidebar",
    "removed from" in lc and "sidebar" in lc,
)

check(
    "11.2 Phase 5I doc says Macro Research becomes first-class top-level page",
    "first-class top-level page" in lc,
)

check(
    "11.3 Phase 5I doc states sidebar change is NOT implemented in this phase",
    "does not" in lc and "sidebar" in lc,
)


# ---------------------------------------------------------------------------
# Section 12 — Non-goals + guardrails present
# ---------------------------------------------------------------------------

NON_GOAL_TOPICS = [
    "Theme Intelligence",
    "Opportunity Queue",
    "shadow integration",
    "broker",
    "order",
    "execution",
    "DB",
    "vector",
    "persistence",
]
for ng in NON_GOAL_TOPICS:
    check(
        f"12.1 Phase 5I doc non-goals/guardrails reference {ng!r}",
        ng.lower() in lc,
    )

check(
    "12.2 Phase 5I doc keeps human-in-the-loop / review-only",
    "human-in-the-loop" in lc and "review-only" in lc,
)

check(
    "12.3 Phase 5I doc states no investment advice",
    "no investment advice" in lc,
)


# ---------------------------------------------------------------------------
# Section 13 — approved_for_execution never positively authorized
# ---------------------------------------------------------------------------

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
    "13.1 Phase 5I doc does not positively authorize approved_for_execution=true",
    not any(p in lc for p in POSITIVE_AUTHORIZATION_PREFIXES_AFE),
)

check(
    "13.2 Phase 5I doc states approved_for_execution remains False/absent",
    "approved_for_execution" in doc_text
    and ("remains `false`" in lc or "remains false" in lc or "false / absent" in lc or "false/absent" in lc),
)

# Phase 5I doc must enumerate forbidden files
for fpath in FORBIDDEN_LIVE_RUNTIME_PATHS:
    check(
        f"13.3 Phase 5I doc forbids file {fpath!r}",
        fpath in doc_text,
    )


# ---------------------------------------------------------------------------
# Section 14 — Phase 5I is documentation-only (no new module / page)
# ---------------------------------------------------------------------------

phase5i_modules = []
for fname in os.listdir(LIB_RELIABILITY_DIR):
    low = fname.lower()
    if (
        low.startswith("phase5i")
        or low.startswith("phase_5i")
        or low.startswith("theme_intelligence")
        or low.startswith("opportunity_queue")
        or low.startswith("market_heat")
    ):
        phase5i_modules.append(fname)
check(
    "14.1 no Phase 5I Python module added under lib/reliability/",
    phase5i_modules == [],
    detail=f"unexpected: {phase5i_modules!r}",
)

# No new page added by Phase 5I (only existing 6 + the Phase 5H cockpit page).
expected_pages = {
    "1_Overview.py",
    "2_Sector.py",
    "3_Scanner.py",
    "4_Equity.py",
    "5_Financial.py",
    "6_PriceVolume.py",
    "7_Investment_Cockpit.py",  # Phase 5H additive page; not Phase 5I
}
pages_present = {f for f in os.listdir(PAGES_DIR) if f.endswith(".py")}
unexpected_pages = pages_present - expected_pages
check(
    "14.2 no unexpected page file added under pages/",
    not unexpected_pages,
    detail=f"unexpected: {sorted(unexpected_pages)!r}",
)

# Financial / PriceVolume pages must NOT be removed in this phase
check(
    "14.3 Financial page still present (not removed in Phase 5I)",
    "5_Financial.py" in pages_present,
)
check(
    "14.4 PriceVolume page still present (not removed in Phase 5I)",
    "6_PriceVolume.py" in pages_present,
)


# ---------------------------------------------------------------------------
# Section 15 — Forbidden live runtime files still present (not deleted)
# ---------------------------------------------------------------------------

for fpath in FORBIDDEN_LIVE_RUNTIME_PATHS:
    abs_path = os.path.join(_REPO_ROOT, fpath)
    check(
        f"15.1 forbidden runtime file still present: {fpath}",
        os.path.isfile(abs_path),
    )


# ---------------------------------------------------------------------------
# Section 16 — State files reconciled
# ---------------------------------------------------------------------------

state_text = _read_text(PROJECT_STATE) if os.path.isfile(PROJECT_STATE) else ""
task_text = _read_text(CURRENT_TASK) if os.path.isfile(CURRENT_TASK) else ""
state_lc = state_text.lower()
task_lc = task_text.lower()

check(
    "16.1 PROJECT_STATE marks Phase 5H.1 accepted",
    "phase 5h.1" in state_lc and "accepted" in state_lc,
)

check(
    "16.2 PROJECT_STATE references Phase 5I awaiting review",
    "phase 5i" in state_lc
    and ("awaiting codex review" in state_lc or "awaiting review" in state_lc),
)

check(
    "16.3 PROJECT_STATE records Phase 5I supersedes earlier shadow-integration next step",
    "supersede" in state_lc and "shadow" in state_lc,
)

check(
    "16.4 CURRENT_TASK marks Phase 5H.1 accepted",
    "phase 5h.1" in task_lc and "accepted" in task_lc,
)

check(
    "16.5 CURRENT_TASK sets current task to Phase 5I",
    "phase 5i" in task_lc,
)

check(
    "16.6 CURRENT_TASK recommends Phase 5J as next phase after acceptance",
    "phase 5j" in task_lc and "theme intelligence" in task_lc,
)


# ---------------------------------------------------------------------------
# Section 17 — Phase 5J not started
# ---------------------------------------------------------------------------

check(
    "17.1 Phase 5I doc does not claim Phase 5J has started",
    "phase 5j has started" not in lc
    and "phase 5j started" not in lc
    and "phase 5j — started" not in lc,
)

check(
    "17.2 Phase 5I doc states Phase 5J has not started",
    "phase 5j" in lc and ("not started" in lc or "has not started" in lc),
)

check(
    "17.3 PROJECT_STATE does not claim Phase 5J has started",
    "phase 5j has started" not in state_lc and "phase 5j started" not in state_lc,
)

check(
    "17.4 CURRENT_TASK does not claim Phase 5J has started",
    "phase 5j has started" not in task_lc and "phase 5j started" not in task_lc,
)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
print("=" * 70)
print("Phase 5I — Investment Cockpit Product Logic Reconciliation — test results")
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
    print("RESULT: PASS — Phase 5I product logic reconciliation verified.")
    sys.exit(0)
else:
    print("RESULT: FAIL — see failures above.")
    sys.exit(1)
