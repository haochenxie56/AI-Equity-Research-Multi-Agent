#!/usr/bin/env python3
"""
scripts/test_reliability_phase_5p_navigation_cleanup.py

Phase 5P — Source Page Navigation Cleanup test suite.

Phase 5P updates the hand-rolled custom sidebar in ``ui_utils.render_sidebar()``
so that Financial Analysis (``pages/5_Financial.py``) and Price & Volume
Analysis (``pages/6_PriceVolume.py``) are no longer top-level source-page nav
entries — they become source sub-surfaces under Equity Research — while Macro
Dashboard (``pages/8_Macro_Dashboard.py``) and Investment Cockpit
(``pages/7_Investment_Cockpit.py``) remain first-class top-level pages.

This test is **static + import-safe**: it does NOT launch a Streamlit server,
does NOT render any page, does NOT call any LLM / external API, and does NOT
import any Streamlit page module at top level. It asserts source-level
invariants on ``ui_utils.py`` and the page files, and imports only
``ui_utils.TRANSLATIONS`` for label-presence checks.

Usage:
    python3 scripts/test_reliability_phase_5p_navigation_cleanup.py
"""

from __future__ import annotations

import ast
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


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Paths under test
# ---------------------------------------------------------------------------

UI_UTILS_PATH = os.path.join(_REPO_ROOT, "ui_utils.py")
DOC_PATH = os.path.join(
    _REPO_ROOT, "docs", "reliability_phase_5p_source_page_navigation_cleanup.md"
)

APP_PATH = os.path.join(_REPO_ROOT, "app.py")
FINANCIAL_PAGE = os.path.join(_REPO_ROOT, "pages", "5_Financial.py")
PRICEVOLUME_PAGE = os.path.join(_REPO_ROOT, "pages", "6_PriceVolume.py")
COCKPIT_PAGE = os.path.join(_REPO_ROOT, "pages", "7_Investment_Cockpit.py")
MACRO_PAGE = os.path.join(_REPO_ROOT, "pages", "8_Macro_Dashboard.py")

ALL_PAGES = [
    "app.py",
    "pages/1_Overview.py",
    "pages/2_Sector.py",
    "pages/3_Scanner.py",
    "pages/4_Equity.py",
    "pages/5_Financial.py",
    "pages/6_PriceVolume.py",
    "pages/7_Investment_Cockpit.py",
    "pages/8_Macro_Dashboard.py",
]


# ---------------------------------------------------------------------------
# Section 1 — Key files exist (no deletion of source pages)
# ---------------------------------------------------------------------------

check("1.1 ui_utils.py exists", os.path.isfile(UI_UTILS_PATH))
check("1.2 Phase 5P design doc exists", os.path.isfile(DOC_PATH))
check("1.3 app.py exists", os.path.isfile(APP_PATH))
check("1.4 pages/5_Financial.py still exists", os.path.isfile(FINANCIAL_PAGE))
check("1.5 pages/6_PriceVolume.py still exists", os.path.isfile(PRICEVOLUME_PAGE))
check("1.6 pages/7_Investment_Cockpit.py exists", os.path.isfile(COCKPIT_PAGE))
check("1.7 pages/8_Macro_Dashboard.py exists", os.path.isfile(MACRO_PAGE))


# ---------------------------------------------------------------------------
# Section 2 — Source files compile (AST parse, import-safe)
# ---------------------------------------------------------------------------

_UI_SRC = _read_text(UI_UTILS_PATH) if os.path.isfile(UI_UTILS_PATH) else ""
check("2.0 ui_utils.py source non-empty", bool(_UI_SRC))
try:
    ast.parse(_UI_SRC, filename=UI_UTILS_PATH)
    check("2.1 ui_utils.py parses", True)
except SyntaxError as e:  # noqa: BLE001
    check("2.1 ui_utils.py parses", False, str(e))

# Pages 1-8 + app.py compile if present (at minimum 5/6/7/8 + app.py).
for rel in ALL_PAGES:
    abs_path = os.path.join(_REPO_ROOT, rel)
    if not os.path.isfile(abs_path):
        check(f"2.x {rel} present", False, "missing")
        continue
    try:
        ast.parse(_read_text(abs_path), filename=abs_path)
        check(f"2.x {rel} parses", True)
    except SyntaxError as e:  # noqa: BLE001
        check(f"2.x {rel} parses", False, str(e))


# ---------------------------------------------------------------------------
# Section 3 — render_sidebar() navigation content
# ---------------------------------------------------------------------------

# Isolate the render_sidebar function source so checks are not fooled by
# unrelated text elsewhere in the module (e.g. the legacy-key comment).
def _extract_func_src(src: str, name: str) -> str:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return ""
    lines = src.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            start = node.lineno - 1
            end = getattr(node, "end_lineno", len(lines))
            return "\n".join(lines[start:end])
    return ""


_SIDEBAR_SRC = _extract_func_src(_UI_SRC, "render_sidebar")
check("3.0 render_sidebar() found in ui_utils.py", bool(_SIDEBAR_SRC))

# Preserved first-class top-level links.
_PRESERVED_LINKS = [
    ('app.py', 'nav_home'),
    ('pages/1_Overview.py', 'nav_p1'),
    ('pages/2_Sector.py', 'nav_p2'),
    ('pages/3_Scanner.py', 'nav_p3'),
    ('pages/4_Equity.py', 'nav_p4'),
    ('pages/7_Investment_Cockpit.py', 'nav_p7'),
    ('pages/8_Macro_Dashboard.py', 'nav_p8'),
]
for page, key in _PRESERVED_LINKS:
    check(
        f"3.1 render_sidebar links {page} via {key}",
        f'st.page_link("{page}"' in _SIDEBAR_SRC
        and f'label=t("{key}")' in _SIDEBAR_SRC,
    )

# Explicit acceptance criteria 1-3.
check(
    "3.2 render_sidebar includes Macro Dashboard (nav_p8)",
    'st.page_link("pages/8_Macro_Dashboard.py"' in _SIDEBAR_SRC
    and 'label=t("nav_p8")' in _SIDEBAR_SRC,
)
check(
    "3.3 render_sidebar includes Investment Cockpit (nav_p7)",
    'st.page_link("pages/7_Investment_Cockpit.py"' in _SIDEBAR_SRC
    and 'label=t("nav_p7")' in _SIDEBAR_SRC,
)
check(
    "3.4 render_sidebar includes top-level Overview/Sector/Scanner/Equity",
    all(
        f'st.page_link("{p}"' in _SIDEBAR_SRC
        for p in (
            "pages/1_Overview.py",
            "pages/2_Sector.py",
            "pages/3_Scanner.py",
            "pages/4_Equity.py",
        )
    ),
)

# Acceptance criterion 4: no top-level page_link to Financial / PriceVolume.
check(
    "3.5 render_sidebar does NOT page_link pages/5_Financial.py",
    'st.page_link("pages/5_Financial.py"' not in _SIDEBAR_SRC,
)
check(
    "3.6 render_sidebar does NOT page_link pages/6_PriceVolume.py",
    'st.page_link("pages/6_PriceVolume.py"' not in _SIDEBAR_SRC,
)


# ---------------------------------------------------------------------------
# Section 4 — Bilingual labels: active keys present; legacy keys retained
# ---------------------------------------------------------------------------

try:
    from ui_utils import TRANSLATIONS as _T  # noqa: E402
    _EN = _T.get("en", {})
    _ZH = _T.get("zh", {})
    check("4.0 ui_utils.TRANSLATIONS imported", bool(_EN) and bool(_ZH))
except Exception as e:  # noqa: BLE001
    _EN, _ZH = {}, {}
    check("4.0 ui_utils.TRANSLATIONS imported", False, str(e))

_ACTIVE_NAV_KEYS = ["nav_home", "nav_p1", "nav_p2", "nav_p3", "nav_p4", "nav_p7", "nav_p8"]
for k in _ACTIVE_NAV_KEYS:
    check(f"4.1 EN label present for active key {k}", _EN.get(k, "").strip() != "")
    check(f"4.2 ZH label present for active key {k}", _ZH.get(k, "").strip() != "")

# Legacy keys retained for backward compatibility (not rendered top-level).
for k in ("nav_p5", "nav_p6"):
    check(f"4.3 EN legacy key {k} retained", _EN.get(k, "").strip() != "")
    check(f"4.4 ZH legacy key {k} retained", _ZH.get(k, "").strip() != "")

# The legacy nature is documented in ui_utils.py source.
check(
    "4.5 ui_utils.py documents nav_p5 / nav_p6 as legacy source-module labels",
    "legacy source-module label" in _UI_SRC,
)


# ---------------------------------------------------------------------------
# Section 5 — Forbidden files not modified to reference Phase 5P
# ---------------------------------------------------------------------------

# app.py and the retained source pages must not be modified to carry Phase 5P
# navigation markers (consistent with prior-phase "not modified" checks).
_PHASE_5P_MARKERS = ("Phase 5P", "navigation cleanup", "5p_source_page_navigation")
for rel in ("app.py", "pages/5_Financial.py", "pages/6_PriceVolume.py"):
    abs_path = os.path.join(_REPO_ROOT, rel)
    if not os.path.isfile(abs_path):
        continue
    src = _read_text(abs_path)
    for marker in _PHASE_5P_MARKERS:
        check(
            f"5.1 {rel} not modified to reference marker: {marker!r}",
            marker not in src,
        )

# app.py must not import the cockpit / macro overlay pages or reliability views.
_app_src = _read_text(APP_PATH) if os.path.isfile(APP_PATH) else ""
check(
    "5.2 app.py does not import phase5 overlay modules",
    "phase5_" not in _app_src and "reliability" not in _app_src,
)


# ---------------------------------------------------------------------------
# Section 6 — No LLM / API / live-workflow imports introduced; no positive auth
# ---------------------------------------------------------------------------

# ui_utils.py legitimately lazy-imports data_fetcher inside loader functions
# (pre-existing). Phase 5P must not introduce LLM / orchestrator / workflow-state
# / SDK imports into ui_utils.py.
_FORBIDDEN_IN_UI_UTILS = (
    "import lib.llm_orchestrator",
    "from lib.llm_orchestrator",
    "import llm_orchestrator",
    "from llm_orchestrator",
    "import lib.workflow_state",
    "from lib.workflow_state",
    "import workflow_state",
    "from workflow_state",
    "import anthropic",
    "from anthropic",
    "import openai",
    "from openai",
)
for frag in _FORBIDDEN_IN_UI_UTILS:
    check(
        f"6.1 ui_utils.py does NOT contain forbidden import: {frag!r}",
        frag not in _UI_SRC,
    )

# No positive approved_for_execution authorization in ui_utils.py or the doc.
_DOC_SRC = _read_text(DOC_PATH) if os.path.isfile(DOC_PATH) else ""
for src_name, src in (("ui_utils.py", _UI_SRC), ("Phase 5P doc", _DOC_SRC)):
    check(
        f"6.2 {src_name} does NOT positively authorize approved_for_execution=True",
        "approved_for_execution=True" not in src
        and "approved_for_execution = True" not in src,
    )

# No order-ticket / broker / execution capability introduced in ui_utils.py.
for frag in ("order_type", "broker_route", "time_in_force", "place_order", "submit_order"):
    check(
        f"6.3 ui_utils.py does NOT introduce execution field/call: {frag!r}",
        frag not in _UI_SRC,
    )


# ---------------------------------------------------------------------------
# Section 7 — Design document has required sections
# ---------------------------------------------------------------------------

_REQUIRED_DOC_HEADINGS = [
    "## Purpose",
    "## Relationship to Phase 5I product logic",
    "## Relationship to the original README app",
    "## Relationship to Phase 5O Macro Dashboard",
    "## Relationship to Phase 5N Investment Cockpit",
    "## Why Financial and Price & Volume are removed from the top-level sidebar",
    "## Why their underlying files / functionality are retained",
    "## New top-level sidebar structure",
    "## Source module hierarchy",
    "## Bilingual sidebar behavior",
    "## Non-goals",
    "## Guardrails",
    "## Acceptance criteria",
    "## Future Phase 5Q dependency",
]
for h in _REQUIRED_DOC_HEADINGS:
    check(f"7.x doc contains heading: {h!r}", h in _DOC_SRC)


# ---------------------------------------------------------------------------
# Section 8 — Cross-phase additive guard (Phase 5N / 5O registrations preserved)
# ---------------------------------------------------------------------------

# Phase 5N (nav_p7) and Phase 5O (nav_p8) sidebar registrations must remain so
# their test suites continue to pass after this ui_utils.py change.
check(
    "8.1 Phase 5N cockpit registration preserved",
    'st.page_link("pages/7_Investment_Cockpit.py"' in _UI_SRC,
)
check(
    "8.2 Phase 5O macro registration preserved",
    'st.page_link("pages/8_Macro_Dashboard.py"' in _UI_SRC,
)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
print("============================================================")
print(f"Phase 5P Navigation Cleanup Test Results: {PASS} passed, {FAIL} failed")
print("============================================================")
if _failures:
    for f in _failures:
        print(f)

sys.exit(0 if FAIL == 0 else 1)
