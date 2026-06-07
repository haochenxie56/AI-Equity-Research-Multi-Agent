#!/usr/bin/env python3
"""
scripts/test_reliability_phase_5r_ui_ux_polish.py

Phase 5R — UI/UX Visual Polish + Demo Readiness test suite.

Phase 5R is a product-facing UI/UX polish + demo-readiness pass over the two
Phase 5 product pages:

    pages/7_Investment_Cockpit.py
    pages/8_Macro_Dashboard.py

It adds a concise "How to read this page" / demo-walkthrough expander to both
pages (routed through ``ui_utils.t()`` with additive EN/ZH chrome keys) and
keeps every product/data contract, scoring, schema, and safety boundary from
Phase 5I / 5N / 5O / 5Q unchanged. No product logic is modified.

This test is **static + import-safe + AppTest-backed**: it does NOT launch a
Streamlit server socket, does NOT call any external API or LLM, and does NOT
import the page modules at top level (importing a page would call
``st.set_page_config`` outside a Streamlit runtime). It asserts source-level
invariants and renders both pages through Streamlit's in-process ``AppTest``
harness in both EN and ZH.

Usage:
    python3 scripts/test_reliability_phase_5r_ui_ux_polish.py
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


# ---------------------------------------------------------------------------
# Paths under test
# ---------------------------------------------------------------------------

COCKPIT_PATH = os.path.join(_REPO_ROOT, "pages", "7_Investment_Cockpit.py")
MACRO_PATH = os.path.join(_REPO_ROOT, "pages", "8_Macro_Dashboard.py")
PHASE_5R_DOC = os.path.join(
    _REPO_ROOT, "docs", "reliability_phase_5r_ui_ux_visual_polish_demo_readiness.md"
)

# Prior-phase tests whose green status the Phase 5R validation set re-runs.
PRIOR_TESTS = [
    "scripts/test_reliability_phase_5q_human_feedback_ui.py",
    "scripts/test_reliability_phase_5n_cockpit_ui_v02.py",
    "scripts/test_reliability_phase_5o_macro_dashboard.py",
]


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


_COCKPIT_SRC = _read_text(COCKPIT_PATH) if os.path.isfile(COCKPIT_PATH) else ""
_MACRO_SRC = _read_text(MACRO_PATH) if os.path.isfile(MACRO_PATH) else ""

_PAGES = (
    ("cockpit", COCKPIT_PATH, _COCKPIT_SRC),
    ("macro", MACRO_PATH, _MACRO_SRC),
)


# ---------------------------------------------------------------------------
# Section 1 — Both pages exist and parse cleanly (still compile)
# ---------------------------------------------------------------------------

for tag, path, src in _PAGES:
    check(f"1.1 {tag} page exists", os.path.isfile(path))
    check(f"1.2 {tag} page source non-empty", bool(src))
    parsed_ok = False
    if src:
        try:
            ast.parse(src, filename=path)
            parsed_ok = True
        except SyntaxError as e:  # noqa: PERF203
            _failures.append(f"FAIL  1.3 SyntaxError in {tag} page: {e}")
    check(f"1.3 {tag} page parses (compiles)", parsed_ok)


# ---------------------------------------------------------------------------
# Section 2 — Both pages bootstrap apply_theme() + render_sidebar()
# ---------------------------------------------------------------------------

for tag, _path, src in _PAGES:
    check(
        f"2.1 {tag} page imports apply_theme + render_sidebar from ui_utils",
        "from ui_utils import" in src
        and "apply_theme" in src
        and "render_sidebar" in src,
    )
    check(f"2.2 {tag} page calls apply_theme()", "apply_theme()" in src)
    check(f"2.3 {tag} page calls render_sidebar()", "render_sidebar()" in src)


# ---------------------------------------------------------------------------
# Section 3 — Both pages contain a demo walkthrough / how-to-read section
# ---------------------------------------------------------------------------

check(
    "3.1 cockpit page renders demo walkthrough helper",
    "_render_demo_walkthrough" in _COCKPIT_SRC,
)
check(
    "3.2 macro page renders demo walkthrough helper",
    "_render_demo_walkthrough" in _MACRO_SRC,
)
check(
    "3.3 cockpit page references cockpit_walkthrough_header",
    "cockpit_walkthrough_header" in _COCKPIT_SRC,
)
check(
    "3.4 macro page references macro_walkthrough_header",
    "macro_walkthrough_header" in _MACRO_SRC,
)


# ---------------------------------------------------------------------------
# Section 4 — Both pages retain safety boundaries
# ---------------------------------------------------------------------------

# Cockpit: opportunity-first safety banner + Phase 5Q feedback safety banner.
check(
    "4.1 cockpit page retains safety headline banner",
    "cockpit_safety_headline" in _COCKPIT_SRC,
)
check(
    "4.2 cockpit page retains review-only / no-execution boundary copy",
    "cockpit_trade_boundary" in _COCKPIT_SRC,
)
check(
    "4.3 cockpit page retains Phase 5Q session-only safety banner",
    "cockpit_review_hf_safety_headline" in _COCKPIT_SRC,
)
# Macro: safety headline banner + posture-not-a-decision boundary copy.
check(
    "4.4 macro page retains safety headline banner",
    "macro_safety_headline" in _MACRO_SRC,
)
check(
    "4.5 macro page retains posture-not-decision boundary copy",
    "macro_posture_not_decision" in _MACRO_SRC,
)


# ---------------------------------------------------------------------------
# Section 5 — No forbidden live-runtime imports on either page
# ---------------------------------------------------------------------------

_FORBIDDEN_LIVE_IMPORTS = [
    "lib.workflow_state",
    "lib.llm_orchestrator",
    "lib.data_fetcher",
    "lib.valuation",
    "lib.technical",
    "lib.rotation",
    "lib.cache_manager",
    "lib.reliability.integration_boundary",
    "anthropic",
    "openai",
    "workflow_state",
]
for tag, _path, src in _PAGES:
    for mod in _FORBIDDEN_LIVE_IMPORTS:
        check(
            f"5.x {tag} page does NOT import forbidden module: {mod}",
            f"import {mod}" not in src and f"from {mod}" not in src,
        )


# ---------------------------------------------------------------------------
# Section 6 — No external API / broker / order routing call sites
# ---------------------------------------------------------------------------

_FORBIDDEN_EXTERNAL_API_TOKENS = [
    "requests.get",
    "requests.post",
    "httpx.",
    "urllib.request.urlopen",
    "anthropic.Anthropic",
    "openai.",
    "yfinance",
    "finnhub",
    "polygon.io",
    "broker_client",
    "broker_api",
    "BrokerClient",
    "order_router",
    "submit_order",
    "place_order",
    "execute_trade",
]
for tag, _path, src in _PAGES:
    for tok in _FORBIDDEN_EXTERNAL_API_TOKENS:
        check(
            f"6.x {tag} page does NOT contain external/broker token: {tok}",
            tok not in src,
        )


# ---------------------------------------------------------------------------
# Section 7 — No reads/writes of research/.workflow_state.json (call sites)
# ---------------------------------------------------------------------------

_WORKFLOW_STATE_CALL_PATTERNS = [
    'open("research/.workflow_state.json"',
    "open('research/.workflow_state.json'",
    'read_text("research/.workflow_state.json"',
    "read_text('research/.workflow_state.json'",
    'write_text("research/.workflow_state.json"',
    'Path("research/.workflow_state.json"',
    "Path('research/.workflow_state.json'",
    "json.load(open(",
]
for tag, _path, src in _PAGES:
    for pat in _WORKFLOW_STATE_CALL_PATTERNS:
        check(
            f"7.x {tag} page does NOT read/write workflow-state via: {pat!r}",
            pat not in src,
        )


# ---------------------------------------------------------------------------
# Section 8 — No persistence / DB / vector store on either page
# ---------------------------------------------------------------------------

_FORBIDDEN_PERSISTENCE_TOKENS = [
    "sqlite3",
    "psycopg2",
    "pymongo",
    "redis.Redis",
    "chromadb",
    "pinecone",
    "faiss",
    "open(",
    ".to_parquet",
    ".to_csv",
    "json.dump(",
    "pickle.dump",
    "joblib.dump",
]
for tag, _path, src in _PAGES:
    for tok in _FORBIDDEN_PERSISTENCE_TOKENS:
        check(
            f"8.x {tag} page does NOT contain persistence token: {tok!r}",
            tok not in src,
        )


# ---------------------------------------------------------------------------
# Section 9 — No order-ticket-like fields; no positive execution authorization
# ---------------------------------------------------------------------------

_FORBIDDEN_ORDER_TICKET_TOKENS = [
    "broker_route",
    "broker_payload",
    "account_id",
    "time_in_force",
    "order_ticket",
    "execution_id",
    "quantity_to_execute",
    "order_type",
    "fill_price",
    "Broker route",
    "Account ID",
    "Time in force",
    "Order ticket",
    "Execution ID",
    "Quantity to execute",
]
for tag, _path, src in _PAGES:
    for tok in _FORBIDDEN_ORDER_TICKET_TOKENS:
        check(f"9.a {tag} page has no order-ticket token: {tok!r}", tok not in src)

_POSITIVE_AUTH_FORMS = [
    "approved_for_execution=True",
    "approved_for_execution = True",
    'approved_for_execution":True',
    'approved_for_execution":  True',
    'approved_for_execution": True',
    "approved_for_execution: True",
]
for tag, _path, src in _PAGES:
    for form in _POSITIVE_AUTH_FORMS:
        check(
            f"9.b {tag} page does NOT positively authorize: {form!r}",
            form not in src,
        )


# ---------------------------------------------------------------------------
# Section 10 — EN/ZH walkthrough chrome keys exist + referenced by pages
# ---------------------------------------------------------------------------

try:
    from ui_utils import TRANSLATIONS as _UI_TRANSLATIONS
except Exception as _ti_exc:  # noqa: BLE001
    _UI_TRANSLATIONS = {"en": {}, "zh": {}}
    _failures.append(f"FAIL  10.0 could not import ui_utils.TRANSLATIONS: {_ti_exc}")

_EN = _UI_TRANSLATIONS.get("en", {})
_ZH = _UI_TRANSLATIONS.get("zh", {})

_COCKPIT_WALK_KEYS = [
    "cockpit_walkthrough_header",
    "cockpit_walkthrough_intro",
    "cockpit_walkthrough_step1",
    "cockpit_walkthrough_step2",
    "cockpit_walkthrough_step3",
    "cockpit_walkthrough_step4",
    "cockpit_walkthrough_step5",
    "cockpit_walkthrough_step6",
    "cockpit_walkthrough_safety",
]
_MACRO_WALK_KEYS = [
    "macro_walkthrough_header",
    "macro_walkthrough_intro",
    "macro_walkthrough_step1",
    "macro_walkthrough_step2",
    "macro_walkthrough_step3",
    "macro_walkthrough_step4",
    "macro_walkthrough_step5",
    "macro_walkthrough_safety",
]

for key in _COCKPIT_WALK_KEYS:
    check(f"10.a EN cockpit chrome key {key!r} non-empty", _EN.get(key, "").strip() != "")
    check(f"10.b ZH cockpit chrome key {key!r} non-empty", _ZH.get(key, "").strip() != "")
    check(f"10.c cockpit page references chrome key {key!r}", key in _COCKPIT_SRC)
    check(
        f"10.d cockpit chrome key {key!r} EN != ZH (actually translated)",
        _EN.get(key, "") != _ZH.get(key, ""),
    )

for key in _MACRO_WALK_KEYS:
    check(f"10.e EN macro chrome key {key!r} non-empty", _EN.get(key, "").strip() != "")
    check(f"10.f ZH macro chrome key {key!r} non-empty", _ZH.get(key, "").strip() != "")
    check(f"10.g macro page references chrome key {key!r}", key in _MACRO_SRC)
    check(
        f"10.h macro chrome key {key!r} EN != ZH (actually translated)",
        _EN.get(key, "") != _ZH.get(key, ""),
    )

# Walkthrough copy reinforces the demo-readiness terminology (cross-page).
_en_cockpit_safety = _EN.get("cockpit_walkthrough_safety", "").lower()
check(
    "10.i EN cockpit walkthrough safety states fixture + review-only + non-exec",
    "fixture" in _en_cockpit_safety
    and "review-only" in _en_cockpit_safety
    and "non-executable" in _en_cockpit_safety,
)
_en_macro_safety = _EN.get("macro_walkthrough_safety", "").lower()
check(
    "10.j EN macro walkthrough safety states fixture + review-only",
    "fixture" in _en_macro_safety and "review-only" in _en_macro_safety,
)


# ---------------------------------------------------------------------------
# Section 11 — Tab keys / order preserved (no product-structure change)
# ---------------------------------------------------------------------------

# Phase 5R is polish only: the Phase 5N / 5O tab vocabulary (keys + EN labels)
# must be unchanged. This guards against an accidental structural edit.
_COCKPIT_TAB_EN = {
    "cockpit_tab_overview": "Overview / Safety",
    "cockpit_tab_themes": "Market Themes",
    "cockpit_tab_opportunity": "Opportunity Queue",
    "cockpit_tab_decision": "Decision Workspace",
    "cockpit_tab_research": "Research Snapshot",
    "cockpit_tab_debate": "Agent Debate",
    "cockpit_tab_trade": "Trade / Allocation Plan",
    "cockpit_tab_option": "Option Overlay",
    "cockpit_tab_review": "Feedback / Review",
    "cockpit_tab_provenance": "Provenance / Diagnostics",
}
for key, expected_en in _COCKPIT_TAB_EN.items():
    check(f"11.a EN cockpit tab key {key!r} unchanged", _EN.get(key) == expected_en)
    check(f"11.b cockpit page references tab key {key!r}", key in _COCKPIT_SRC)

# Phase 6A visual upgrade simplified the macro tab labels to concise block
# titles (removed "/" separators); the keys and order are unchanged.
_MACRO_TAB_EN = {
    "macro_tab_overview": "Overview",
    "macro_tab_regime": "Macro Regime",
    "macro_tab_indicators": "Macro Indicators",
    "macro_tab_liquidity": "Rates & Liquidity",
    "macro_tab_credit": "Credit & Volatility",
    "macro_tab_risk": "Market Sentiment",
    "macro_tab_horizon": "Horizon Bias",
    "macro_tab_themes": "Theme Implications",
    "macro_tab_posture": "Opportunity Posture",
    "macro_tab_provenance": "Data Sources",
}
for key, expected_en in _MACRO_TAB_EN.items():
    check(f"11.c EN macro tab key {key!r} unchanged", _EN.get(key) == expected_en)
    check(f"11.d macro page references tab key {key!r}", key in _MACRO_SRC)


# ---------------------------------------------------------------------------
# Section 12 — Phase 5R design doc exists with required sections
# ---------------------------------------------------------------------------

check("12.1 Phase 5R design doc exists", os.path.isfile(PHASE_5R_DOC))
if os.path.isfile(PHASE_5R_DOC):
    _doc = _read_text(PHASE_5R_DOC)
    for heading in (
        "Purpose",
        "Phase 5I",
        "Phase 5N",
        "Phase 5O",
        "Phase 5Q",
        "Visual hierarchy",
        "Card",
        "Safety banner",
        "Bilingual",
        "Demo walkthrough",
        "Empty",
        "Non-goals",
        "Guardrails",
        "Acceptance criteria",
        "Phase 5S",
    ):
        check(f"12.x Phase 5R doc mentions: {heading!r}", heading in _doc)


# ---------------------------------------------------------------------------
# Section 13 — Prior-phase regression test files still present
# ---------------------------------------------------------------------------

for rel in PRIOR_TESTS:
    check(
        f"13.x prior regression test present: {rel}",
        os.path.isfile(os.path.join(_REPO_ROOT, rel)),
    )


# ---------------------------------------------------------------------------
# Section 14 — AppTest render of both pages in EN and ZH
# ---------------------------------------------------------------------------

_APPTEST_AVAILABLE = False
try:
    from streamlit.testing.v1 import AppTest  # type: ignore
    _APPTEST_AVAILABLE = True
except Exception as _at_imp_exc:  # noqa: BLE001
    _failures.append(f"FAIL  14.0 AppTest import failed: {_at_imp_exc}")


def _collect_rendered_text(at) -> str:
    parts: list[str] = []
    for collection_name in (
        "title",
        "header",
        "subheader",
        "caption",
        "markdown",
        "info",
        "warning",
        "error",
        "code",
        "text",
        "metric",
    ):
        try:
            elements = getattr(at, collection_name, []) or []
        except Exception:  # noqa: BLE001
            elements = []
        for el in elements:
            for attr in ("value", "body", "label"):
                try:
                    v = getattr(el, attr, None)
                except Exception:  # noqa: BLE001
                    v = None
                if isinstance(v, str):
                    parts.append(v)
    return "\n".join(parts)


if _APPTEST_AVAILABLE:
    import ui_utils as _ui_utils_mod  # type: ignore
    _orig_render_sidebar = _ui_utils_mod.render_sidebar
    _orig_apply_theme = _ui_utils_mod.apply_theme

    def _noop_render_sidebar() -> None:
        try:
            _ui_utils_mod.init_session()
        except Exception:  # noqa: BLE001
            pass

    def _noop_apply_theme() -> None:
        return None

    _ui_utils_mod.render_sidebar = _noop_render_sidebar  # type: ignore[assignment]
    _ui_utils_mod.apply_theme = _noop_apply_theme  # type: ignore[assignment]

    _PAGE_RENDER_TARGETS = (
        ("cockpit", COCKPIT_PATH, "cockpit_page_title", "cockpit_safety_headline"),
        ("macro", MACRO_PATH, "macro_page_title", "macro_safety_headline"),
    )

    try:
        for page_tag, page_path, title_key, safety_key in _PAGE_RENDER_TARGETS:
            for lang, lang_tag in (("en", "EN"), ("zh", "ZH")):
                try:
                    at = AppTest.from_file(page_path, default_timeout=60)
                    at.session_state["language"] = lang
                    at.session_state["dark_mode"] = True
                    at.run()
                    ran_ok = not bool(at.exception)
                    exc_info = (
                        "; ".join(str(getattr(e, "value", e)) for e in at.exception)
                        if at.exception
                        else None
                    )
                except Exception as _at_run_exc:  # noqa: BLE001
                    ran_ok = False
                    exc_info = f"{type(_at_run_exc).__name__}: {_at_run_exc}"
                    at = None  # type: ignore[assignment]

                check(
                    f"14.{page_tag}.{lang_tag}.1 render completed without exception",
                    ran_ok,
                    detail=exc_info or "",
                )
                if not ran_ok or at is None:
                    continue

                rendered = _collect_rendered_text(at)
                lang_map = _UI_TRANSLATIONS.get(lang, {})
                # Page title + safety headline render.
                check(
                    f"14.{page_tag}.{lang_tag}.2 render contains page title",
                    lang_map.get(title_key, "\x00") in rendered,
                )
                check(
                    f"14.{page_tag}.{lang_tag}.3 render contains safety headline",
                    lang_map.get(safety_key, "\x00") in rendered,
                )
                # No positive approved_for_execution authorization rendered.
                for form in _POSITIVE_AUTH_FORMS:
                    check(
                        f"14.{page_tag}.{lang_tag}.4 render has no positive auth: {form!r}",
                        form not in rendered,
                    )
    finally:
        _ui_utils_mod.render_sidebar = _orig_render_sidebar  # type: ignore[assignment]
        _ui_utils_mod.apply_theme = _orig_apply_theme  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
print("============================================================")
print(f"Phase 5R UI/UX Polish + Demo Readiness Test Results: {PASS} passed, {FAIL} failed")
print("============================================================")
if _failures:
    for f in _failures:
        print(f)

sys.exit(0 if FAIL == 0 else 1)
