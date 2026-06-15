#!/usr/bin/env python3
"""
scripts/test_reliability_phase_5h_cockpit_ui_preview.py

Phase 5H — Controlled Streamlit Cockpit UI Integration v0.1 test suite.

Phase 5H adds exactly one new Streamlit page,
``pages/7_Investment_Cockpit.py``, which renders the Phase 5G fixture
demo pack through the Phase 5B / 5C / 5D view-model contracts.

This test is **static and import-safe**: it does NOT launch the
Streamlit server, does NOT call any external API, does NOT call any
LLM, and does NOT import the page module directly (importing the page
would call ``st.set_page_config`` outside of a Streamlit runtime).
Instead the test asserts source-level invariants and validates the
Phase 5G demo pack contract that the page consumes.

Usage:
    python3 scripts/test_reliability_phase_5h_cockpit_ui_preview.py
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

PAGE_PATH = os.path.join(_REPO_ROOT, "pages", "7_Investment_Cockpit.py")
PHASE_5H_DOC = os.path.join(
    _REPO_ROOT, "docs", "reliability_phase_5h_controlled_streamlit_cockpit_ui.md"
)
PHASE_5G_TEST = os.path.join(
    _REPO_ROOT,
    "scripts",
    "test_reliability_phase_5g_cockpit_demo_pack.py",
)


# Existing pages 1–6 and app.py must not be replaced or removed.
EXISTING_LIVE_PAGES = [
    "app.py",
    "pages/1_Overview.py",
    "pages/2_Sector.py",
    "pages/3_Scanner.py",
    "pages/4_Equity.py",
    "pages/5_Financial.py",
    "pages/6_PriceVolume.py",
]

FORBIDDEN_LIVE_RUNTIME_PATHS = EXISTING_LIVE_PAGES + [
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
# Section 1 — Phase 5H page exists; existing pages preserved
# ---------------------------------------------------------------------------

check("1.1 Phase 5H cockpit page exists", os.path.isfile(PAGE_PATH))

for rel in FORBIDDEN_LIVE_RUNTIME_PATHS:
    abs_path = os.path.join(_REPO_ROOT, rel)
    check(
        f"1.x forbidden live runtime path still exists: {rel}",
        os.path.exists(abs_path),
    )

# Capture a baseline hash of each existing live page so we can assert
# Phase 5H did not modify them in spirit. We do NOT compare contents to
# any baseline file (we have none); instead we check the file is small
# enough to read and does not contain Phase 5H-specific marker strings
# (which would imply Phase 5H modified the file).
_PHASE_5H_MARKERS = (
    "phase5_demo_pack",
    "Phase 5H",
    "Investment Cockpit",
    "DemoSafetyBanner",
    "build_default_cockpit_demo_pack",
)
for rel in EXISTING_LIVE_PAGES:
    abs_path = os.path.join(_REPO_ROOT, rel)
    if not os.path.exists(abs_path):
        # Already failed above; skip the marker check.
        continue
    src = _read_text(abs_path)
    for marker in _PHASE_5H_MARKERS:
        check(
            f"1.y existing page {rel} not modified to reference Phase 5H "
            f"marker: {marker}",
            marker not in src,
        )


# ---------------------------------------------------------------------------
# Section 2 — Page parses cleanly (does not import page; import-safe)
# ---------------------------------------------------------------------------

_PAGE_SRC = _read_text(PAGE_PATH) if os.path.isfile(PAGE_PATH) else ""

check(
    "2.1 Phase 5H page source parses as valid Python",
    bool(_PAGE_SRC),
    "page source empty or file missing",
)
try:
    _PAGE_AST = ast.parse(_PAGE_SRC, filename=PAGE_PATH)
    _PAGE_PARSED_OK = True
except SyntaxError as e:
    _PAGE_AST = None
    _PAGE_PARSED_OK = False
    _failures.append(f"FAIL  2.1 SyntaxError in page: {e}")

check("2.2 Phase 5H page AST built", _PAGE_PARSED_OK)


# Collect imported module names
_imported_module_names: set[str] = set()
if _PAGE_AST is not None:
    for node in ast.walk(_PAGE_AST):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _imported_module_names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                _imported_module_names.add(node.module.split(".")[0])

check(
    "2.3 Phase 5H page imports streamlit (UI library)",
    "streamlit" in _imported_module_names,
)


# ---------------------------------------------------------------------------
# Section 3 — Page consumes Phase 5G demo pack, NOT live workflow / LLM
# ---------------------------------------------------------------------------

# The page must consume the Phase 5G demo pack module.
check(
    "3.1 page imports lib.reliability.phase5_demo_pack",
    "lib.reliability.phase5_demo_pack" in _PAGE_SRC
    or "from lib.reliability.phase5_demo_pack" in _PAGE_SRC,
)

# Demo-pack public API symbols must be visibly used.
for sym in (
    "build_default_cockpit_demo_pack",
    "CockpitDemoPack",
    "CockpitDemoScenario",
    "DEMO_SCENARIO_ORDER",
):
    check(
        f"3.2 page references Phase 5G symbol: {sym}",
        sym in _PAGE_SRC,
    )

# The page must use Phase 5B/5C/5D view contracts (either directly imported
# or referenced via the demo pack view bundle).
#
# Phase 5N (Cockpit UI v0.2) repositioned the page from company/ticker-first
# to opportunity-first. The Horizon Cards tab was retired (its content is now
# carried by the Phase 5K Opportunity Queue + Phase 5M Decision Workspace), so
# the page no longer references ``HorizonDecisionCardsView``. It still renders
# the Phase 5B Company Research Hub (as the Research Snapshot tab), the Phase
# 5C ThesisTracker (folded into Research Snapshot), and the Phase 5D portfolio
# view.
for sym in (
    "CompanyResearchHubView",
    "ThesisTrackerView",
    "PortfolioCockpitView",
):
    check(
        f"3.3 page references Phase 5B/5C/5D view: {sym}",
        sym in _PAGE_SRC,
    )

# The page must NOT import live workflow / LLM / data-fetcher modules.
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
for mod in _FORBIDDEN_LIVE_IMPORTS:
    check(
        f"3.4 page does NOT import forbidden module: {mod}",
        f"import {mod}" not in _PAGE_SRC and f"from {mod}" not in _PAGE_SRC,
    )

# No live workflow state read. We allow the literal filename inside
# negation copy ("No reads of research/.workflow_state.json") but block
# any actual file-open / read pattern targeting the file.
_WORKFLOW_STATE_READ_PATTERNS = [
    'open("research/.workflow_state.json"',
    "open('research/.workflow_state.json'",
    'read_text("research/.workflow_state.json"',
    "read_text('research/.workflow_state.json'",
    "json.load(open(",
    'pathlib.Path("research/.workflow_state.json"',
    "Path(\"research/.workflow_state.json\"",
    "Path('research/.workflow_state.json'",
]
for pat in _WORKFLOW_STATE_READ_PATTERNS:
    check(
        f"3.5 page does NOT read research/.workflow_state.json via: {pat!r}",
        pat not in _PAGE_SRC,
    )


# ---------------------------------------------------------------------------
# Section 4 — Page does not call external APIs / broker / order routing
# ---------------------------------------------------------------------------

# External API tokens — we look for call sites, not for the bare word
# "broker" (the safety banner copy mentions "no broker" repeatedly).
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
for tok in _FORBIDDEN_EXTERNAL_API_TOKENS:
    check(
        f"4.x page does NOT contain external/broker token: {tok}",
        tok not in _PAGE_SRC,
    )


# ---------------------------------------------------------------------------
# Section 5 — Safety banner wording (Phase 5H.1: bilingual via TRANSLATIONS)
# ---------------------------------------------------------------------------
#
# Phase 5H.1 routes all user-facing cockpit text through ``ui_utils.t()``.
# The literal English safety phrases now live in
# ``ui_utils.TRANSLATIONS["en"]`` (cockpit_safety_* keys). Section 5 verifies:
#
#   (a) every required English phrase is present somewhere in the joined
#       English cockpit_safety_* values;
#   (b) each required cockpit_safety_* key also has a non-empty
#       ``TRANSLATIONS["zh"]`` counterpart (bilingual coverage).

try:
    from ui_utils import TRANSLATIONS as _UI_TRANSLATIONS
except Exception as _ti_exc:  # noqa: BLE001
    _UI_TRANSLATIONS = {"en": {}, "zh": {}}
    _failures.append(f"FAIL  5.0 could not import ui_utils.TRANSLATIONS: {_ti_exc}")

_COCKPIT_SAFETY_KEYS = (
    "cockpit_safety_headline",
    "cockpit_safety_b1",
    "cockpit_safety_b2",
    "cockpit_safety_b3",
    "cockpit_safety_b4",
    "cockpit_safety_b5",
    "cockpit_safety_b6",
)

_REQUIRED_SAFETY_PHRASES = [
    "Fixture/demo only",
    "No live workflow wiring",
    "No external API",
    "No orders",
    "approved_for_execution",
    "Not investment advice",
]

_en_safety_blob = "\n".join(
    _UI_TRANSLATIONS.get("en", {}).get(k, "") for k in _COCKPIT_SAFETY_KEYS
).lower()

for phrase in _REQUIRED_SAFETY_PHRASES:
    check(
        f"5.x EN safety banner mentions: {phrase!r}",
        phrase.lower() in _en_safety_blob,
    )

for key in _COCKPIT_SAFETY_KEYS:
    check(
        f"5.y ZH safety key non-empty: {key!r}",
        _UI_TRANSLATIONS.get("zh", {}).get(key, "").strip() != "",
    )


# ---------------------------------------------------------------------------
# Section 6 — Required tabs present (Phase 5H.1: bilingual via TRANSLATIONS)
# ---------------------------------------------------------------------------
#
# After Phase 5H.1 the tab labels live in ``ui_utils.TRANSLATIONS``. Section 6
# verifies:
#
#   (a) ``TRANSLATIONS["en"][cockpit_tab_*]`` matches the canonical English
#       label exactly — these labels are part of the Phase 5H acceptance
#       criteria and must not drift;
#   (b) ``TRANSLATIONS["zh"][cockpit_tab_*]`` is non-empty — bilingual
#       coverage is mandatory;
#   (c) the page source actually references each ``cockpit_tab_*`` key
#       (so the page actually consumes the translation, not just defines it).

# Phase 5N (Cockpit UI v0.2) replaced the Phase 5H tab set with an
# opportunity-first structure. The old ``cockpit_tab_company`` /
# ``cockpit_tab_horizon`` / ``cockpit_tab_thesis`` / ``cockpit_tab_portfolio``
# / ``cockpit_tab_feedback`` keys remain defined in ``ui_utils.TRANSLATIONS``
# (additive policy — nothing removed) but the page no longer presents them as
# primary tabs. The canonical v0.2 tab labels are asserted here.
_COCKPIT_TAB_KEY_TO_EN = {
    "cockpit_tab_overview":    "Overview / Safety",
    "cockpit_tab_themes":      "Market Themes",
    "cockpit_tab_opportunity": "Opportunity Queue",
    "cockpit_tab_decision":    "Decision Workspace",
    "cockpit_tab_research":    "Research Snapshot",
    "cockpit_tab_debate":      "Agent Debate",
    "cockpit_tab_trade":       "Trade / Allocation Plan",
    "cockpit_tab_option":      "Option Overlay",
    "cockpit_tab_review":      "Feedback / Review",
    "cockpit_tab_provenance":  "Provenance / Diagnostics",
}

for key, expected_en in _COCKPIT_TAB_KEY_TO_EN.items():
    check(
        f"6.a EN tab key {key!r} maps to {expected_en!r}",
        _UI_TRANSLATIONS.get("en", {}).get(key) == expected_en,
        detail=repr(_UI_TRANSLATIONS.get("en", {}).get(key)),
    )
    check(
        f"6.b ZH tab key {key!r} non-empty",
        _UI_TRANSLATIONS.get("zh", {}).get(key, "").strip() != "",
        detail=repr(_UI_TRANSLATIONS.get("zh", {}).get(key)),
    )
    check(
        f"6.c page source references {key!r}",
        key in _PAGE_SRC,
    )

# Phase 5H.1 — page also registers in the global sidebar as nav_p7.
check(
    "6.d ui_utils.TRANSLATIONS['en'] has nav_p7",
    _UI_TRANSLATIONS.get("en", {}).get("nav_p7", "").strip() != "",
    detail=repr(_UI_TRANSLATIONS.get("en", {}).get("nav_p7")),
)
check(
    "6.e ui_utils.TRANSLATIONS['zh'] has nav_p7",
    _UI_TRANSLATIONS.get("zh", {}).get("nav_p7", "").strip() != "",
    detail=repr(_UI_TRANSLATIONS.get("zh", {}).get("nav_p7")),
)

try:
    _UI_UTILS_SRC = _read_text(os.path.join(_REPO_ROOT, "ui_utils.py"))
except Exception as _uu_exc:  # noqa: BLE001
    _UI_UTILS_SRC = ""
    _failures.append(f"FAIL  6.f could not read ui_utils.py: {_uu_exc}")

check(
    "6.f ui_utils.render_sidebar registers pages/7_Investment_Cockpit.py",
    "pages/7_Investment_Cockpit.py" in _UI_UTILS_SRC
    and 'label=t("nav_p7")' in _UI_UTILS_SRC,
)


# ---------------------------------------------------------------------------
# Section 7 — No order-ticket-like fields exposed
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
    "broker route",
    "Broker route",
    "Account ID",
    "Time in force",
    "Order ticket",
    "Execution ID",
    "Quantity to execute",
]
for tok in _FORBIDDEN_ORDER_TICKET_TOKENS:
    check(
        f"7.x page does NOT contain order-ticket token: {tok!r}",
        tok not in _PAGE_SRC,
    )


# ---------------------------------------------------------------------------
# Section 8 — approved_for_execution is never positively authorized
# ---------------------------------------------------------------------------

# The string "approved_for_execution" may legitimately appear in safety
# banner copy and in JSON dumps that surface the underlying False value.
# What MUST NOT appear is any positive authorization assignment.
_POSITIVE_AUTH_FORMS = [
    "approved_for_execution=True",
    "approved_for_execution = True",
    'approved_for_execution":True',
    'approved_for_execution":  True',
    'approved_for_execution": True',
    "approved_for_execution: True",
]
for form in _POSITIVE_AUTH_FORMS:
    check(
        f"8.x page does NOT positively authorize approved_for_execution: "
        f"{form!r}",
        form not in _PAGE_SRC,
    )


# ---------------------------------------------------------------------------
# Section 9 — Phase 5G demo pack still builds (regression smoke import)
# ---------------------------------------------------------------------------

try:
    from lib.reliability.phase5_demo_pack import (  # noqa: E402
        CockpitDemoPack as _CockpitDemoPack,
        DEMO_SCENARIO_ORDER as _DEMO_SCENARIO_ORDER,
        build_default_cockpit_demo_pack as _build_pack,
    )

    _pack = _build_pack()
    check("9.1 Phase 5G demo pack builds", isinstance(_pack, _CockpitDemoPack))
    check(
        "9.2 Phase 5G demo pack has at least one scenario",
        len(_pack.scenarios) >= 1,
    )
    check(
        "9.3 Phase 5G demo pack includes a complete scenario",
        _pack.validation_summary.has_complete_scenario,
    )
    check(
        "9.4 Phase 5G demo pack approved_for_execution invariant",
        _pack.validation_summary.all_approved_for_execution_false,
    )
    check(
        "9.5 Phase 5G demo pack no-executable-order-fields invariant",
        _pack.validation_summary.no_executable_order_fields,
    )
    check(
        "9.6 Phase 5G demo pack has no validation errors",
        not _pack.validation_summary.errors,
        detail=str(_pack.validation_summary.errors),
    )
    check(
        "9.7 DEMO_SCENARIO_ORDER includes 'complete'",
        "complete" in _DEMO_SCENARIO_ORDER,
    )
except Exception as e:  # noqa: BLE001
    FAIL += 1
    _failures.append(f"FAIL  9.x Phase 5G demo pack import/build failed: {e}")


# ---------------------------------------------------------------------------
# Section 10 — Phase 5H design doc exists with required sections
# ---------------------------------------------------------------------------

check(
    "10.1 Phase 5H design doc exists",
    os.path.isfile(PHASE_5H_DOC),
)

if os.path.isfile(PHASE_5H_DOC):
    _doc = _read_text(PHASE_5H_DOC)
    for heading in (
        "Purpose",
        "Roadmap v4",
        "README",
        "Phase 5E",
        "Phase 5F",
        "Phase 5G",
        "Page created",
        "Existing pages preserved",
        "Fixture-only data flow",
        "UI sections",
        "Safety banner",
        "Degraded scenario",
        "Non-goals",
        "Guardrails",
        "Forbidden existing files",
        "Acceptance criteria",
        "Future Phase 5I",
    ):
        check(
            f"10.x Phase 5H doc mentions: {heading!r}",
            heading in _doc,
        )


# ---------------------------------------------------------------------------
# Section 11 — Phase 5G regression test file still exists
# ---------------------------------------------------------------------------

check(
    "11.1 Phase 5G test file still exists",
    os.path.isfile(PHASE_5G_TEST),
)


# ---------------------------------------------------------------------------
# Section 12 — Page does not write persistence / no DB / no vector store
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
]
for tok in _FORBIDDEN_PERSISTENCE_TOKENS:
    check(
        f"12.x page does NOT contain persistence token: {tok!r}",
        tok not in _PAGE_SRC,
    )


# ---------------------------------------------------------------------------
# Section 13 — Page contains a fail-closed fallback when the demo pack
# cannot be built (no LLM/API fallback)
# ---------------------------------------------------------------------------

check(
    "13.1 page has a fail-closed branch when demo pack build fails",
    "Failed to build" in _PAGE_SRC
    or "Fail-closed" in _PAGE_SRC
    or "fail closed" in _PAGE_SRC.lower(),
)
# 13.2 — the page must not silently fall back to a live LLM / live API
# path when the demo pack fails to build. We assert positive presence of
# a fail-closed statement; we do not block legitimate negation copy
# such as "No live LLM call" or "No live API".
check(
    "13.2 page asserts no live LLM / no live API fallback",
    ("no fallback to live" in _PAGE_SRC.lower())
    or ("No LLM" in _PAGE_SRC and "No external API" in _PAGE_SRC)
    or ("no live api" in _PAGE_SRC.lower() and "no fallback" in _PAGE_SRC.lower()),
)


# ---------------------------------------------------------------------------
# Section 14 — AppTest integration: render the page in EN and ZH (Phase 5H.1)
# ---------------------------------------------------------------------------
#
# Phase 5H shipped with a coverage gap: every assertion in sections 1-13 is
# static (source-string / AST / TRANSLATIONS lookups). A real bug in the
# original Phase 5H page (model_dump → model_validate round-trip on Pydantic
# models with Field(exclude=True)) shipped through unnoticed because no test
# actually ran the page. Section 14 closes that gap using Streamlit's
# AppTest harness:
#
#   * Run the page with ``language="en"``  → assert no exception, every
#     English tab label appears in a rendered subheader.
#   * Run the page with ``language="zh"``  → assert no exception, every
#     Chinese tab label appears in a rendered subheader.
#   * Assert no positive ``approved_for_execution=True`` authorization
#     appears in any rendered text.
#
# AppTest spins up an in-process Streamlit runtime; it does NOT bind a
# socket, does NOT call any external API, and does NOT touch the browser.

_APPTEST_AVAILABLE = False
try:
    from streamlit.testing.v1 import AppTest  # type: ignore
    _APPTEST_AVAILABLE = True
except Exception as _at_imp_exc:  # noqa: BLE001
    _failures.append(
        f"FAIL  14.0 streamlit.testing.v1.AppTest import failed: {_at_imp_exc}"
    )


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
    # Also walk every tab and collect its children's text.
    try:
        for tab in getattr(at, "tabs", []) or []:
            label = getattr(tab, "label", None)
            if isinstance(label, str):
                parts.append(label)
    except Exception:  # noqa: BLE001
        pass
    return "\n".join(parts)


if _APPTEST_AVAILABLE:
    _EN_TAB_LABELS = tuple(_COCKPIT_TAB_KEY_TO_EN.values())
    _ZH_TAB_LABELS = tuple(
        _UI_TRANSLATIONS.get("zh", {}).get(k, "") for k in _COCKPIT_TAB_KEY_TO_EN
    )

    # AppTest does not set up the multi-page-app runtime context, so
    # ``st.page_link()`` (called by ``ui_utils.render_sidebar``) raises
    # ``KeyError: 'url_pathname'`` inside AppTest. That's a known AppTest
    # limitation, not a real page bug — production Streamlit has the
    # multi-page context and ``page_link`` works there. We monkey-patch
    # ``render_sidebar`` to a no-op for the duration of the AppTest run so
    # the cockpit page's own ``main()`` actually gets to render its tabs.
    # The patched module attribute is restored at the end.
    import ui_utils as _ui_utils_mod  # type: ignore
    _orig_render_sidebar = _ui_utils_mod.render_sidebar
    _orig_apply_theme = _ui_utils_mod.apply_theme

    def _noop_render_sidebar() -> None:
        # Still initialize session-state defaults like the real sidebar would.
        try:
            _ui_utils_mod.init_session()
        except Exception:  # noqa: BLE001
            pass

    def _noop_apply_theme() -> None:
        # Skip CSS injection — irrelevant for AppTest text capture.
        return None

    _ui_utils_mod.render_sidebar = _noop_render_sidebar  # type: ignore[assignment]
    _ui_utils_mod.apply_theme = _noop_apply_theme  # type: ignore[assignment]

    try:
        for lang, expected_labels, tag in (
            ("en", _EN_TAB_LABELS, "EN"),
            ("zh", _ZH_TAB_LABELS, "ZH"),
        ):
            try:
                at = AppTest.from_file(PAGE_PATH, default_timeout=30)
                at.session_state["language"] = lang
                at.session_state["dark_mode"] = True
                at.run()
                ran_ok = True
                exc_info = None
                if at.exception:
                    ran_ok = False
                    exc_info = "; ".join(
                        str(getattr(e, "value", e)) for e in at.exception
                    )
            except Exception as _at_run_exc:  # noqa: BLE001
                ran_ok = False
                exc_info = f"{type(_at_run_exc).__name__}: {_at_run_exc}"
                at = None  # type: ignore[assignment]

            check(
                f"14.{tag}.1 AppTest {tag} render completed without exception",
                ran_ok,
                detail=exc_info or "",
            )

            if not ran_ok or at is None:
                # Skip downstream label / authorization checks for this language.
                continue

            rendered = _collect_rendered_text(at)
            for label in expected_labels:
                if not label:
                    continue
                check(
                    f"14.{tag}.2 {tag} render contains tab label: {label!r}",
                    label in rendered,
                )

            for form in _POSITIVE_AUTH_FORMS:
                check(
                    f"14.{tag}.3 {tag} render contains no positive auth: {form!r}",
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
print(f"Phase 5H Cockpit UI Preview Test Results: {PASS} passed, {FAIL} failed")
print("============================================================")
if _failures:
    for f in _failures:
        print(f)

sys.exit(0 if FAIL == 0 else 1)
