#!/usr/bin/env python3
"""
scripts/test_reliability_phase_5o_macro_dashboard.py

Phase 5O — Macro Dashboard v0.1 test suite.

Phase 5O adds a macro-regime view-model layer
(``lib/reliability/phase5_macro_dashboard.py``) and a single additive Streamlit
page (``pages/8_Macro_Dashboard.py``) that elevates macro from a Sector Research
subsection into a first-class, fixture-only upstream input for the Investment
Cockpit.

This test is **static + import-safe + AppTest-backed**: it does NOT launch a
Streamlit server socket, does NOT call any external/macro API, does NOT call any
LLM, and does NOT import the page module at top level (importing the page would
call ``st.set_page_config`` outside a Streamlit runtime). It asserts source-level
invariants, validates the fixture contracts the page consumes, and renders the
page through Streamlit's in-process ``AppTest`` harness in both EN and ZH.

Usage:
    python3 scripts/test_reliability_phase_5o_macro_dashboard.py
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

PAGE_PATH = os.path.join(_REPO_ROOT, "pages", "8_Macro_Dashboard.py")
MODULE_PATH = os.path.join(
    _REPO_ROOT, "lib", "reliability", "phase5_macro_dashboard.py"
)
PHASE_5O_DOC = os.path.join(
    _REPO_ROOT, "docs", "reliability_phase_5o_macro_dashboard_v01.md"
)

EXISTING_LIVE_PAGES = [
    "app.py",
    "pages/1_Overview.py",
    "pages/2_Sector.py",
    "pages/3_Scanner.py",
    "pages/4_Equity.py",
    "pages/5_Financial.py",
    "pages/6_PriceVolume.py",
    "pages/7_Investment_Cockpit.py",
]

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
# Section 1 — Page + module exist + compile; existing pages preserved
# ---------------------------------------------------------------------------

check("1.1 macro page exists", os.path.isfile(PAGE_PATH))
check("1.2 macro module exists", os.path.isfile(MODULE_PATH))

for rel in FORBIDDEN_LIVE_RUNTIME_PATHS:
    check(
        f"1.x forbidden live runtime path still exists: {rel}",
        os.path.exists(os.path.join(_REPO_ROOT, rel)),
    )

# Existing live pages (1-7 + app.py) must not be modified to reference Phase 5O
# macro markers.
_PHASE_5O_MARKERS = (
    "phase5_macro_dashboard",
    "Macro Dashboard",
    "MacroDashboardView",
)
for rel in EXISTING_LIVE_PAGES:
    abs_path = os.path.join(_REPO_ROOT, rel)
    if not os.path.exists(abs_path):
        continue
    src = _read_text(abs_path)
    for marker in _PHASE_5O_MARKERS:
        check(
            f"1.y existing page {rel} not modified to reference marker: {marker}",
            marker not in src,
        )


# ---------------------------------------------------------------------------
# Section 2 — Page parses cleanly (import-safe)
# ---------------------------------------------------------------------------

_PAGE_SRC = _read_text(PAGE_PATH) if os.path.isfile(PAGE_PATH) else ""

check("2.1 page source non-empty", bool(_PAGE_SRC))
try:
    _PAGE_AST = ast.parse(_PAGE_SRC, filename=PAGE_PATH)
    _PAGE_PARSED_OK = True
except SyntaxError as e:
    _PAGE_AST = None
    _PAGE_PARSED_OK = False
    _failures.append(f"FAIL  2.1 SyntaxError in page: {e}")
check("2.2 page AST built", _PAGE_PARSED_OK)

_imported_module_names: set[str] = set()
if _PAGE_AST is not None:
    for node in ast.walk(_PAGE_AST):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _imported_module_names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                _imported_module_names.add(node.module.split(".")[0])

check("2.3 page imports streamlit", "streamlit" in _imported_module_names)

# Module parses too.
_MODULE_SRC = _read_text(MODULE_PATH) if os.path.isfile(MODULE_PATH) else ""
try:
    ast.parse(_MODULE_SRC, filename=MODULE_PATH)
    _MODULE_PARSED_OK = True
except SyntaxError as e:
    _MODULE_PARSED_OK = False
    _failures.append(f"FAIL  2.4 SyntaxError in module: {e}")
check("2.4 module AST built", _MODULE_PARSED_OK)


# ---------------------------------------------------------------------------
# Section 3 — Page consumes the Phase 5O macro fixtures only
# ---------------------------------------------------------------------------

check(
    "3.1 page imports lib.reliability.phase5_macro_dashboard",
    "from lib.reliability.phase5_macro_dashboard" in _PAGE_SRC,
)
for sym in (
    "build_macro_dashboard_view_by_scenario",
    "MACRO_DASHBOARD_SCENARIO_ORDER",
    "MacroDashboardView",
):
    check(f"3.2 page references Phase 5O symbol: {sym}", sym in _PAGE_SRC)

# Page calls apply_theme() and render_sidebar() and uses t().
check("3.3 page calls apply_theme()", "apply_theme()" in _PAGE_SRC)
check("3.4 page calls render_sidebar()", "render_sidebar()" in _PAGE_SRC)
check("3.5 page uses t() for chrome", 't("macro_' in _PAGE_SRC)

# Forbidden live-runtime imports.
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
        f"3.6 page does NOT import forbidden module: {mod}",
        f"import {mod}" not in _PAGE_SRC and f"from {mod}" not in _PAGE_SRC,
    )
    check(
        f"3.6m module does NOT import forbidden module: {mod}",
        f"import {mod}" not in _MODULE_SRC and f"from {mod}" not in _MODULE_SRC,
    )

# No live workflow-state read.
_WORKFLOW_STATE_READ_PATTERNS = [
    'open("research/.workflow_state.json"',
    "open('research/.workflow_state.json'",
    'read_text("research/.workflow_state.json"',
    "read_text('research/.workflow_state.json'",
    "json.load(open(",
    'Path("research/.workflow_state.json"',
    "Path('research/.workflow_state.json'",
]
for pat in _WORKFLOW_STATE_READ_PATTERNS:
    check(
        f"3.7 page does NOT read research/.workflow_state.json via: {pat!r}",
        pat not in _PAGE_SRC,
    )


# ---------------------------------------------------------------------------
# Section 4 — No external/macro API / broker / order routing call sites
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
    "fredapi",
    "Fred(",
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
        f"4.x page does NOT contain external/macro/broker token: {tok}",
        tok not in _PAGE_SRC,
    )
    check(
        f"4.m module does NOT contain external/macro/broker token: {tok}",
        tok not in _MODULE_SRC,
    )


# ---------------------------------------------------------------------------
# Section 5 — Import ui_utils.TRANSLATIONS
# ---------------------------------------------------------------------------

try:
    from ui_utils import TRANSLATIONS as _UI_TRANSLATIONS
except Exception as _ti_exc:  # noqa: BLE001
    _UI_TRANSLATIONS = {"en": {}, "zh": {}}
    _failures.append(f"FAIL  5.0 could not import ui_utils.TRANSLATIONS: {_ti_exc}")

_EN = _UI_TRANSLATIONS.get("en", {})
_ZH = _UI_TRANSLATIONS.get("zh", {})


# ---------------------------------------------------------------------------
# Section 6 — Sidebar registration + nav_p8 + tab structure
# ---------------------------------------------------------------------------

try:
    _UI_UTILS_SRC = _read_text(os.path.join(_REPO_ROOT, "ui_utils.py"))
except Exception as _uu_exc:  # noqa: BLE001
    _UI_UTILS_SRC = ""
    _failures.append(f"FAIL  6.0 could not read ui_utils.py: {_uu_exc}")

check(
    "6.1 ui_utils.render_sidebar registers pages/8_Macro_Dashboard.py with nav_p8",
    "pages/8_Macro_Dashboard.py" in _UI_UTILS_SRC
    and 'label=t("nav_p8")' in _UI_UTILS_SRC,
)
check("6.2 EN nav_p8 non-empty", _EN.get("nav_p8", "").strip() != "")
check("6.3 ZH nav_p8 non-empty", _ZH.get("nav_p8", "").strip() != "")

# Additivity: Phase 5N nav_p7 + the cockpit page registration must be preserved.
check("6.4 EN nav_p7 still present (additive)", _EN.get("nav_p7", "").strip() != "")
check(
    "6.5 cockpit page still registered (additive)",
    "pages/7_Investment_Cockpit.py" in _UI_UTILS_SRC
    and 'label=t("nav_p7")' in _UI_UTILS_SRC,
)

# Phase 6A visual upgrade — tab labels simplified to concise block titles
# (removed the "/" separators that previously concatenated sub-topics).
_TAB_KEY_TO_EN = {
    "macro_tab_overview":   "Overview",
    "macro_tab_regime":     "Macro Regime",
    "macro_tab_indicators": "Macro Indicators",
    "macro_tab_liquidity":  "Rates & Liquidity",
    "macro_tab_credit":     "Credit & Volatility",
    "macro_tab_risk":       "Market Sentiment",
    "macro_tab_horizon":    "Horizon Bias",
    "macro_tab_themes":     "Theme Implications",
    "macro_tab_posture":    "Opportunity Posture",
    "macro_tab_provenance": "Data Sources",
}
for key, expected_en in _TAB_KEY_TO_EN.items():
    check(
        f"6.a EN tab key {key!r} == {expected_en!r}",
        _EN.get(key) == expected_en,
        detail=repr(_EN.get(key)),
    )
    check(f"6.b ZH tab key {key!r} non-empty", _ZH.get(key, "").strip() != "")
    check(f"6.c page references tab key {key!r}", key in _PAGE_SRC)


# ---------------------------------------------------------------------------
# Section 7 — New chrome translation keys exist in EN + ZH and are referenced
# ---------------------------------------------------------------------------

_REQUIRED_CHROME_KEYS = [
    # Page
    "macro_page_title",
    "macro_page_subtitle",
    "macro_scenario_select_label",
    "macro_scenario_select_help",
    # Safety
    "macro_safety_headline",
    "macro_safety_b1",
    "macro_safety_b2",
    "macro_safety_b3",
    "macro_safety_b4",
    "macro_safety_b5",
    "macro_safety_b6",
    # Overview
    "macro_overview_caption",
    "macro_overview_first_class",
    "macro_overview_regime_status",
    # Regime
    "macro_regime_caption",
    "macro_regime_primary",
    "macro_regime_growth",
    # Factor display
    "macro_factor_trend",
    "macro_factor_signal",
    "macro_factor_value",
    "macro_section_overall_signal",
    # Liquidity / Rates / Inflation
    "macro_liquidity_caption",
    "macro_liquidity_header",
    "macro_rates_header",
    "macro_inflation_header",
    # Credit / Volatility / Breadth
    "macro_credit_caption",
    "macro_credit_header",
    "macro_volatility_header",
    "macro_breadth_header",
    "macro_dollar_header",
    "macro_earnings_header",
    "macro_policy_header",
    # Risk appetite
    "macro_risk_caption",
    "macro_risk_state",
    # Horizon bias
    "macro_horizon_caption",
    "macro_horizon_short",
    "macro_horizon_mid",
    "macro_horizon_long",
    "macro_horizon_not_decision",
    # Theme implications
    "macro_themes_caption",
    "macro_themes_not_live",
    "macro_themes_no_implications",
    # Opportunity posture
    "macro_posture_caption",
    "macro_posture_primary",
    "macro_posture_not_decision",
    # Macro Indicators (Phase 5O.1)
    "macro_tab_indicators",
    "macro_indicators_caption",
    "macro_indicators_not_live",
    "macro_indicators_commodities_header",
    "macro_indicators_risk_header",
    "macro_indicators_releases_header",
    "macro_ind_value",
    "macro_ind_trend",
    "macro_ind_signal",
    "macro_ind_macro_implication",
    "macro_ind_horizon_implication",
    "macro_ind_category",
    # Provenance
    "macro_provenance_caption",
    "macro_provenance_no_api",
    "macro_provenance_validation",
    "macro_provenance_not_live",
    # Fail-closed
    "macro_failclosed_headline",
    "macro_failclosed_note",
]
for key in _REQUIRED_CHROME_KEYS:
    check(f"7.a EN chrome key {key!r} non-empty", _EN.get(key, "").strip() != "")
    check(f"7.b ZH chrome key {key!r} non-empty", _ZH.get(key, "").strip() != "")
    check(f"7.c page references chrome key {key!r}", key in _PAGE_SRC)

# The safety bullets must enumerate the required boundaries.
_b2 = _EN.get("macro_safety_b2", "").lower()
_b4 = _EN.get("macro_safety_b4", "").lower()
_b5 = _EN.get("macro_safety_b5", "").lower()
_b6 = _EN.get("macro_safety_b6", "").lower()
check("7.d safety bullet mentions no live macro API", "macro api" in _b2)
check("7.e safety bullet mentions no LLM", "llm" in _b4)
check(
    "7.f safety bullet mentions no broker/order/execution",
    "broker" in _b5 and "order" in _b5,
)
check(
    "7.g safety bullet mentions approved_for_execution false/absent",
    "approved_for_execution" in _b6,
)


# ---------------------------------------------------------------------------
# Section 8 — No order-ticket-like fields exposed in the page or module
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
]
for tok in _FORBIDDEN_ORDER_TICKET_TOKENS:
    check(f"8.x page has no order-ticket token: {tok!r}", tok not in _PAGE_SRC)
    check(f"8.m module has no order-ticket token: {tok!r}", tok not in _MODULE_SRC)


# ---------------------------------------------------------------------------
# Section 9 — approved_for_execution never positively authorized
# ---------------------------------------------------------------------------

_POSITIVE_AUTH_FORMS = [
    "approved_for_execution=True",
    "approved_for_execution = True",
    'approved_for_execution":True',
    'approved_for_execution":  True',
    'approved_for_execution": True',
    "approved_for_execution: True",
]
for form in _POSITIVE_AUTH_FORMS:
    check(f"9.x page does NOT positively authorize: {form!r}", form not in _PAGE_SRC)
    check(
        f"9.m module does NOT positively authorize: {form!r}",
        form not in _MODULE_SRC,
    )


# ---------------------------------------------------------------------------
# Section 10 — Macro view-model fixtures build with safety invariants
# ---------------------------------------------------------------------------

try:
    from lib.reliability.phase5_macro_dashboard import (  # noqa: E402
        MACRO_DASHBOARD_SCENARIO_ORDER,
        MACRO_OPPORTUNITY_POSTURES,
        REQUIRED_MACRO_FACTORS,
        MacroDashboardView,
        build_all_macro_dashboard_views,
        build_default_macro_dashboard_view,
        build_degraded_macro_dashboard_view,
        build_empty_macro_dashboard_view,
        build_macro_dashboard_view_by_scenario,
        build_risk_off_macro_dashboard_view,
        build_risk_on_macro_dashboard_view,
        build_transition_macro_dashboard_view,
    )

    # 10.1 — every required fixture exists / builds.
    _default = build_default_macro_dashboard_view()
    _ron = build_risk_on_macro_dashboard_view()
    _roff = build_risk_off_macro_dashboard_view()
    _trans = build_transition_macro_dashboard_view()
    _deg = build_degraded_macro_dashboard_view()
    _empty = build_empty_macro_dashboard_view()
    check("10.1 default fixture builds", isinstance(_default, MacroDashboardView))
    check("10.2 risk_on fixture builds", isinstance(_ron, MacroDashboardView))
    check("10.3 risk_off fixture builds", isinstance(_roff, MacroDashboardView))
    check("10.4 transition fixture builds", isinstance(_trans, MacroDashboardView))
    check("10.5 degraded fixture builds", isinstance(_deg, MacroDashboardView))

    # 10.6 — scenario registry exposes the four selectable scenarios.
    check(
        "10.6 scenario order has the four scenarios",
        set(MACRO_DASHBOARD_SCENARIO_ORDER)
        == {"risk_on", "risk_off", "transition", "degraded"},
    )
    _all = build_all_macro_dashboard_views()
    check("10.7 build_all returns all scenarios", set(_all) == set(MACRO_DASHBOARD_SCENARIO_ORDER))

    # 10.8 — scenario kinds match expectation.
    check("10.8 risk_on regime is risk_on",
          _ron.regime_snapshot.regime_status.primary_status == "risk_on")
    check("10.9 risk_off regime is risk_off",
          _roff.regime_snapshot.regime_status.primary_status == "risk_off")
    check("10.10 transition regime is transition",
          _trans.regime_snapshot.regime_status.primary_status == "transition")
    check("10.11 degraded regime is unknown",
          _deg.regime_snapshot.regime_status.primary_status == "unknown")

    # 10.12 — required macro factors appear in complete fixtures.
    for v, tag in ((_ron, "risk_on"), (_roff, "risk_off"), (_trans, "transition")):
        present = {f.factor for f in v.regime_snapshot.factors}
        for fk in REQUIRED_MACRO_FACTORS:
            check(f"10.12 {tag} has required factor {fk!r}", fk in present)
        check(
            f"10.12v {tag} validation has_all_required_factors",
            v.validation_summary.has_all_required_factors is True,
        )

    # 10.13 — safety invariants on every fixture.
    for v, tag in (
        (_default, "default"), (_ron, "risk_on"), (_roff, "risk_off"),
        (_trans, "transition"), (_deg, "degraded"),
    ):
        vs = v.validation_summary
        check(f"10.13 {tag} no_final_decision", vs.no_final_decision is True)
        check(f"10.13 {tag} no_buy_signal_fields", vs.no_buy_signal_fields is True)
        check(
            f"10.13 {tag} no_executable_order_fields",
            vs.no_executable_order_fields is True,
        )
        check(
            f"10.13 {tag} approved_for_execution_absent",
            vs.approved_for_execution_absent is True,
        )
        check(f"10.13 {tag} no_live_macro_api", vs.no_live_macro_api is True)

    # 10.14 — posture outputs are review-only and not trade instructions.
    for v, tag in (
        (_default, "default"), (_ron, "risk_on"), (_roff, "risk_off"),
        (_trans, "transition"), (_deg, "degraded"),
    ):
        op = v.opportunity_posture
        check(f"10.14 {tag} posture is_buy_signal False", op.is_buy_signal is False)
        check(f"10.14 {tag} posture is_executable False", op.is_executable is False)
        check(
            f"10.14 {tag} posture produces_final_decision False",
            op.produces_final_decision is False,
        )
        check(
            f"10.14 {tag} posture requires_human_review True",
            op.requires_human_review is True,
        )
        check(
            f"10.14 {tag} primary posture in review-only vocabulary",
            op.primary_posture in MACRO_OPPORTUNITY_POSTURES,
        )

    # 10.15 — posture vocabulary contains no execution verbs.
    for posture in MACRO_OPPORTUNITY_POSTURES:
        for verb in ("buy", "sell", "execute", "order"):
            check(
                f"10.15 posture {posture!r} has no execution verb {verb!r}",
                verb not in posture,
            )

    # 10.16 — risk-on / risk-off / transition produce the expected posture leaning.
    check(
        "10.16 risk_on favors momentum",
        _ron.opportunity_posture.primary_posture == "favor_momentum_trades",
    )
    check(
        "10.17 risk_off favors watchlist-only",
        _roff.opportunity_posture.primary_posture == "favor_watchlist_only",
    )
    check(
        "10.18 transition favors pullback entries",
        _trans.opportunity_posture.primary_posture == "favor_pullback_entries",
    )
    check(
        "10.19 degraded -> research_more",
        _deg.opportunity_posture.primary_posture == "research_more",
    )

    # 10.20 — horizon biases exist for short / mid / long.
    for v, tag in (
        (_default, "default"), (_ron, "risk_on"), (_roff, "risk_off"),
        (_trans, "transition"), (_deg, "degraded"),
    ):
        hb = v.horizon_bias
        check(
            f"10.20 {tag} short_term_bias set",
            hb.short_term_bias in MACRO_OPPORTUNITY_POSTURES,
        )
        check(
            f"10.20 {tag} mid_term_bias set",
            hb.mid_term_bias in MACRO_OPPORTUNITY_POSTURES,
        )
        check(
            f"10.20 {tag} long_term_bias set",
            hb.long_term_bias in MACRO_OPPORTUNITY_POSTURES,
        )
        check(f"10.20 {tag} horizon bias is_decision False", hb.is_decision is False)

    # 10.21 — theme implications are fixture-only, not live market claims.
    for v, tag in ((_ron, "risk_on"), (_roff, "risk_off"), (_trans, "transition")):
        check(f"10.21 {tag} has theme implications", len(v.theme_implications) >= 1)
        check(
            f"10.21 {tag} all theme implications not live market claims",
            all(ti.is_live_market_claim is False for ti in v.theme_implications),
        )
        check(
            f"10.21 {tag} all theme implications are fixture examples",
            all(ti.is_fixture_example is True for ti in v.theme_implications),
        )

    # 10.22 — degraded fixture surfaces missing factors + warnings (nothing faked).
    check(
        "10.22 degraded has missing factors",
        len(_deg.validation_summary.missing_factors) >= 1,
    )
    check("10.23 degraded flagged is_degraded", _deg.validation_summary.is_degraded is True)
    check("10.24 degraded has warnings", len(_deg.warnings) >= 1)

    # 10.25 — empty fixture is a safe empty state.
    check("10.25 empty is safe empty", _empty.validation_summary.is_safe_empty is True)

    # 10.26 — no model declares approved_for_execution (absent by construction).
    check(
        "10.26 MacroDashboardView has no approved_for_execution field",
        "approved_for_execution" not in MacroDashboardView.model_fields,
    )
    check(
        "10.27 posture view has no approved_for_execution field",
        "approved_for_execution"
        not in type(_ron.opportunity_posture).model_fields,
    )
    check(
        "10.28 safety banner has no approved_for_execution field",
        "approved_for_execution" not in type(_ron.safety_banner).model_fields,
    )

    # 10.29 — by-scenario builder is deterministic (stable dashboard_id).
    check(
        "10.29 by-scenario builder deterministic",
        build_macro_dashboard_view_by_scenario("risk_on").dashboard_id
        == build_macro_dashboard_view_by_scenario("risk_on").dashboard_id,
    )
except Exception as e:  # noqa: BLE001
    FAIL += 1
    _failures.append(f"FAIL  10.x macro dashboard import/build failed: {e}")


# ---------------------------------------------------------------------------
# Section 11 — Phase 5O design doc exists with required sections
# ---------------------------------------------------------------------------

check("11.1 Phase 5O design doc exists", os.path.isfile(PHASE_5O_DOC))
if os.path.isfile(PHASE_5O_DOC):
    _doc = _read_text(PHASE_5O_DOC)
    for heading in (
        "Purpose",
        "Phase 5I",
        "Phase 5J",
        "Phase 5K",
        "Phase 5N",
        "first-class",
        "fixture-only",
        "Macro factor taxonomy",
        "Regime status",
        "Horizon bias",
        "Opportunity posture",
        "Theme implications",
        "UI page structure",
        "Bilingual",
        "Safety boundaries",
        "Non-goals",
        "Guardrails",
        "Acceptance criteria",
        "Phase 5P",
        # Phase 5O.1 — Macro Indicator Expansion
        "Phase 5O.1",
        "Macro Indicator Expansion",
        "WTI",
        "Gold",
        "CNN Fear & Greed",
        "QQQ",
        "IWM",
        "NFP",
        "CPI",
        "PPI",
    ):
        check(f"11.x Phase 5O doc mentions: {heading!r}", heading in _doc)


# ---------------------------------------------------------------------------
# Section 12 — No persistence / DB / vector store / file-open
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
    check(f"12.x page does NOT contain persistence token: {tok!r}", tok not in _PAGE_SRC)
    check(
        f"12.m module does NOT contain persistence token: {tok!r}",
        tok not in _MODULE_SRC,
    )


# ---------------------------------------------------------------------------
# Section 13 — Fail-closed branch (no live/LLM/API fallback)
# ---------------------------------------------------------------------------

check(
    "13.1 page has a fail-closed branch",
    "Fail-closed" in _PAGE_SRC or "fail closed" in _PAGE_SRC.lower(),
)
check(
    "13.2 page asserts no live fallback",
    "no fallback to live" in _PAGE_SRC.lower(),
)


# ---------------------------------------------------------------------------
# Section 14 — AppTest render in EN and ZH (+ degraded scenario)
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
        "title", "header", "subheader", "caption", "markdown",
        "info", "warning", "error", "code", "text", "metric",
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
    _EN_TAB_LABELS = tuple(_TAB_KEY_TO_EN.values())
    _ZH_TAB_LABELS = tuple(_ZH.get(k, "") for k in _TAB_KEY_TO_EN)

    # AppTest has no multi-page-app context, so ``st.page_link`` (called by
    # ui_utils.render_sidebar) raises inside AppTest — a known harness
    # limitation, not a page bug. Monkey-patch render_sidebar / apply_theme to
    # no-ops for the AppTest run only; restore in finally.
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

    try:
        for lang, expected_labels, tag in (
            ("en", _EN_TAB_LABELS, "EN"),
            ("zh", _ZH_TAB_LABELS, "ZH"),
        ):
            try:
                at = AppTest.from_file(PAGE_PATH, default_timeout=60)
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
                f"14.{tag}.1 AppTest {tag} render completed without exception",
                ran_ok,
                detail=exc_info or "",
            )
            if not ran_ok or at is None:
                continue

            rendered = _collect_rendered_text(at)
            for label in expected_labels:
                if not label:
                    continue
                check(
                    f"14.{tag}.2 {tag} render contains tab label: {label!r}",
                    label in rendered,
                )

            check(
                f"14.{tag}.3 {tag} render contains safety headline",
                _UI_TRANSLATIONS.get(lang, {}).get("macro_safety_headline", "X")
                in rendered,
            )

            for form in _POSITIVE_AUTH_FORMS:
                check(
                    f"14.{tag}.4 {tag} render has no positive auth: {form!r}",
                    form not in rendered,
                )

        # Degraded scenario renders without exception.
        try:
            at2 = AppTest.from_file(PAGE_PATH, default_timeout=60)
            at2.session_state["language"] = "en"
            at2.run()
            if at2.selectbox:
                at2.selectbox[0].set_value("degraded").run()
            ran_ok2 = not bool(at2.exception)
            exc_info2 = (
                "; ".join(str(getattr(e, "value", e)) for e in at2.exception)
                if at2.exception
                else None
            )
        except Exception as _at_run_exc2:  # noqa: BLE001
            ran_ok2 = False
            exc_info2 = f"{type(_at_run_exc2).__name__}: {_at_run_exc2}"
        check(
            "14.DEGRADED.1 degraded scenario renders without exception",
            ran_ok2,
            detail=exc_info2 or "",
        )
    finally:
        _ui_utils_mod.render_sidebar = _orig_render_sidebar  # type: ignore[assignment]
        _ui_utils_mod.apply_theme = _orig_apply_theme  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Section 15 — Package export surface (additive Phase 5O exports)
# ---------------------------------------------------------------------------

try:
    import lib.reliability as _rel  # noqa: E402

    for sym in (
        "MacroDashboardView",
        "MacroRegimeSnapshot",
        "MacroRegimeStatus",
        "MacroOpportunityPostureView",
        "MacroHorizonBiasView",
        "MacroThemeImplicationView",
        "MacroDashboardSafetyBanner",
        "MacroDashboardValidationSummary",
        "build_default_macro_dashboard_view",
        "build_risk_on_macro_dashboard_view",
        "build_risk_off_macro_dashboard_view",
        "build_transition_macro_dashboard_view",
        "build_degraded_macro_dashboard_view",
        "build_macro_dashboard_view_by_scenario",
        "REQUIRED_MACRO_FACTORS",
        "MACRO_DASHBOARD_SCENARIO_ORDER",
        # Phase 5O.1 — Macro Indicator Expansion
        "MacroIndicatorView",
        "MacroInstrumentSignalView",
        "MacroEconomicReleaseView",
        "CommoditySignalView",
        "RiskSentimentSignalView",
        "IndexRiskAppetiteSignalView",
        "LaborMarketSignalView",
        "InflationReleaseSignalView",
        "MacroIndicatorPanel",
        "REQUIRED_MACRO_INDICATOR_KEYS",
        "collect_panel_indicators",
        "make_macro_indicator_id",
    ):
        check(f"15.x lib.reliability exports {sym!r}", hasattr(_rel, sym))
except Exception as e:  # noqa: BLE001
    FAIL += 1
    _failures.append(f"FAIL  15.x lib.reliability export check failed: {e}")


# ---------------------------------------------------------------------------
# Section 16 — Phase 5O.1 Macro Indicator Expansion coverage
# ---------------------------------------------------------------------------

try:
    from lib.reliability.phase5_macro_dashboard import (  # noqa: E402
        REQUIRED_MACRO_INDICATOR_KEYS,
        CommoditySignalView,
        IndexRiskAppetiteSignalView,
        InflationReleaseSignalView,
        LaborMarketSignalView,
        MacroIndicatorPanel,
        MacroIndicatorView,
        RiskSentimentSignalView,
        build_default_macro_dashboard_view as _bdef,
        build_degraded_macro_dashboard_view as _bdeg,
        build_risk_off_macro_dashboard_view as _broff,
        build_risk_on_macro_dashboard_view as _bron,
        build_transition_macro_dashboard_view as _btrn,
        collect_panel_indicators,
    )

    # 16.1 — the eight requested indicators exist in the default fixture.
    _dview = _bdef()
    _dinds = collect_panel_indicators(_dview.indicator_panel)
    _dkeys = {i.indicator_key for i in _dinds}
    for k in ("wti", "gold", "fear_greed", "qqq", "iwm", "nfp", "cpi", "ppi"):
        check(f"16.1 default fixture has indicator {k!r}", k in _dkeys)
    check(
        "16.2 default fixture has all required indicators",
        _dview.validation_summary.has_all_required_indicators is True,
    )
    check(
        "16.3 REQUIRED keys are the eight requested",
        set(REQUIRED_MACRO_INDICATOR_KEYS)
        == {"wti", "gold", "fear_greed", "qqq", "iwm", "nfp", "cpi", "ppi"},
    )

    # 16.4 — indicators are grouped into commodities / risk-appetite / releases.
    _panel = _dview.indicator_panel
    check(
        "16.4 commodities group has WTI + Gold",
        {c.indicator_key for c in _panel.commodities} == {"wti", "gold"},
    )
    check("16.5 fear_greed present in risk-appetite group", _panel.fear_greed is not None)
    check(
        "16.6 index leadership group has QQQ + IWM",
        {i.indicator_key for i in _panel.index_leadership} == {"qqq", "iwm"},
    )
    check(
        "16.7 labor releases group has NFP",
        {r.indicator_key for r in _panel.labor_releases} == {"nfp"},
    )
    check(
        "16.8 inflation releases group has CPI + PPI",
        {r.indicator_key for r in _panel.inflation_releases} == {"cpi", "ppi"},
    )

    # 16.9 — every indicator is fixture-only (never live data).
    for ind in _dinds:
        check(
            f"16.9 indicator {ind.indicator_key!r} is_live_data False",
            ind.is_live_data is False,
        )
        check(
            f"16.9s indicator {ind.indicator_key!r} source_type fixture",
            ind.source_type == "fixture",
        )
    check(
        "16.10 validation all_indicators_fixture_only",
        _dview.validation_summary.all_indicators_fixture_only is True,
    )

    # 16.11 — concrete typed views are used per group.
    check(
        "16.11 commodities are CommoditySignalView",
        all(isinstance(c, CommoditySignalView) for c in _panel.commodities),
    )
    check(
        "16.12 fear_greed is RiskSentimentSignalView",
        isinstance(_panel.fear_greed, RiskSentimentSignalView),
    )
    check(
        "16.13 index leadership are IndexRiskAppetiteSignalView",
        all(isinstance(i, IndexRiskAppetiteSignalView) for i in _panel.index_leadership),
    )
    check(
        "16.14 labor releases are LaborMarketSignalView",
        all(isinstance(r, LaborMarketSignalView) for r in _panel.labor_releases),
    )
    check(
        "16.15 inflation releases are InflationReleaseSignalView",
        all(isinstance(r, InflationReleaseSignalView) for r in _panel.inflation_releases),
    )

    # 16.16 — each indicator carries the required descriptive fields.
    for ind in _dinds:
        check(
            f"16.16 indicator {ind.indicator_key!r} has display_name",
            bool(ind.display_name),
        )
        check(
            f"16.16c indicator {ind.indicator_key!r} has category",
            ind.category in ("commodity", "risk_appetite", "economic_release"),
        )
        check(
            f"16.16m indicator {ind.indicator_key!r} has macro_implication",
            bool(ind.macro_implication),
        )
        check(
            f"16.16h indicator {ind.indicator_key!r} has horizon_implication",
            bool(ind.horizon_implication),
        )
        check(
            f"16.16id indicator {ind.indicator_key!r} has indicator_id",
            bool(ind.indicator_id),
        )

    # 16.17 — risk-on / risk-off / transition each carry all eight indicators
    # with coherent overall signals; degraded surfaces missing indicators.
    _ron, _roff, _trn, _deg = _bron(), _broff(), _btrn(), _bdeg()
    for v, tag in ((_ron, "risk_on"), (_roff, "risk_off"), (_trn, "transition")):
        check(
            f"16.17 {tag} has all eight indicators",
            v.validation_summary.has_all_required_indicators is True,
        )
        check(
            f"16.17c {tag} indicator_count == 8",
            v.validation_summary.indicator_count == 8,
        )
    check(
        "16.18 risk_on indicator panel overall_signal supportive",
        _ron.indicator_panel.overall_signal == "supportive",
    )
    check(
        "16.19 risk_off indicator panel overall_signal headwind",
        _roff.indicator_panel.overall_signal == "headwind",
    )
    check(
        "16.20 transition indicator panel overall_signal mixed",
        _trn.indicator_panel.overall_signal == "mixed",
    )
    # Risk-on Fear & Greed in a greed zone (crowding caution); risk-off in fear.
    check(
        "16.21 risk_on fear_greed sentiment_zone greed",
        _ron.indicator_panel.fear_greed.sentiment_zone == "greed",
    )
    check(
        "16.22 risk_off fear_greed sentiment_zone fear",
        _roff.indicator_panel.fear_greed.sentiment_zone == "fear",
    )
    # Degraded: missing indicators surfaced (not fabricated) + warnings.
    check(
        "16.23 degraded has missing indicators",
        len(_deg.validation_summary.missing_indicators) >= 1,
    )
    check(
        "16.24 degraded not has_all_required_indicators",
        _deg.validation_summary.has_all_required_indicators is False,
    )
    _deg_inds = collect_panel_indicators(_deg.indicator_panel)
    check(
        "16.25 degraded present indicators carry warnings",
        all(len(i.warnings) >= 1 for i in _deg_inds) and len(_deg_inds) >= 1,
    )
    check(
        "16.26 degraded indicators still fixture-only",
        _deg.validation_summary.all_indicators_fixture_only is True,
    )

    # 16.27 — no indicator model declares approved_for_execution.
    for cls in (
        MacroIndicatorView,
        CommoditySignalView,
        IndexRiskAppetiteSignalView,
        RiskSentimentSignalView,
        LaborMarketSignalView,
        InflationReleaseSignalView,
        MacroIndicatorPanel,
    ):
        check(
            f"16.27 {cls.__name__} has no approved_for_execution field",
            "approved_for_execution" not in cls.model_fields,
        )

    # 16.28 — the page renders the indicator section and references the panel.
    check(
        "16.28 page references indicator section render",
        "_render_indicators_section" in _PAGE_SRC,
    )
    check(
        "16.29 page references view.indicator_panel",
        "indicator_panel" in _PAGE_SRC,
    )
    check(
        "16.30 page references macro_tab_indicators tab key",
        "macro_tab_indicators" in _PAGE_SRC,
    )
except Exception as e:  # noqa: BLE001
    FAIL += 1
    _failures.append(f"FAIL  16.x macro indicator expansion check failed: {e}")


# ---------------------------------------------------------------------------
# Section L — ITEM 2 (batch seg 2): FRED liquidity fetchers — fail-closed behavior
# + the load-bearing SNAPSHOT-EXCLUSION guard (display-only; never persisted).
# ---------------------------------------------------------------------------
try:
    import dataclasses as _dcL
    import inspect as _inspL
    import json as _jsonL
    import tempfile as _tfL
    from pathlib import Path as _PathL
    import lib.macro_data as _mdL
    import lib.opportunity_ranker as _orrL

    # (i) fail-closed: a forced fetch exception → fixture, no raise, not "live".
    #     MUTATION: remove fetch_liquidity's try/except (let _fred_observations raise)
    #     → L.1 RED (the call raises instead of returning a fixture).
    _orig_obs = _mdL._fred_observations
    try:
        _mdL.fetch_liquidity.clear()

        def _boom_obs(*a, **k):
            raise RuntimeError("forced-fred-failure")

        _mdL._fred_observations = _boom_obs
        _liq_exc = _mdL.fetch_liquidity()
        check("L.1 fetch_liquidity fail-closes to a fixture on fetch exception (no raise)",
              getattr(_liq_exc, "data_source", None) == "fixture")
        check("L.1b the failed-fetch result is NOT tagged live",
              getattr(_liq_exc, "data_source", None) != "live")
    finally:
        _mdL._fred_observations = _orig_obs
        _mdL.fetch_liquidity.clear()

    # (i) no-key path: FRED_API_KEY absent → _fred_observations returns [] → fixture.
    _orig_key = _mdL.FRED_API_KEY
    try:
        _mdL.fetch_liquidity.clear()
        _mdL.FRED_API_KEY = ""
        _liq_nokey = _mdL.fetch_liquidity()
        check("L.2 fetch_liquidity fail-closes to a fixture when no FRED key is set",
              _liq_nokey.data_source == "fixture")
    finally:
        _mdL.FRED_API_KEY = _orig_key
        _mdL.fetch_liquidity.clear()

    # The fixture carries all four series + the data_source/as_of contract.
    _fx = _mdL._liquidity_fixture()
    check("L.3 liquidity fixture exposes the four series + the fixture tag",
          _fx.data_source == "fixture" and _fx.as_of is None
          and all(getattr(_fx, _k) is not None
                  for _k in ("sofr", "on_rrp", "tga", "reserves")))

    # (ii) SNAPSHOT EXCLUSION — the load-bearing guard. Liquidity must stay OFF the
    # snapshot/regime path. MUTATION (any one): add a `liquidity`/`sofr` field to
    # MacroDataResult, OR call fetch_liquidity inside fetch_all_macro, OR write a
    # liquidity field into write_daily_snapshot's _meta → the matching check goes RED.
    _LIQ_FIELDS = {"sofr", "on_rrp", "tga", "reserves", "liquidity"}
    _mdr_fields = {_f.name for _f in _dcL.fields(_mdL.MacroDataResult)}
    check("L.4 MacroDataResult excludes every liquidity field (off the snapshot/regime path)",
          _mdr_fields.isdisjoint(_LIQ_FIELDS), f"fields={sorted(_mdr_fields)}")

    _FAM_SRC = _inspL.getsource(_mdL.fetch_all_macro)
    check("L.5 fetch_all_macro does NOT call fetch_liquidity (display-only stays on demand)",
          "fetch_liquidity" not in _FAM_SRC and "LiquidityResult" not in _FAM_SRC,
          "fetch_all_macro references the liquidity group")

    _WDS_SRC = _inspL.getsource(_orrL.write_daily_snapshot)
    check("L.6 write_daily_snapshot source references no liquidity field",
          all(_tok not in _WDS_SRC for _tok in
              ("fetch_liquidity", "LiquidityResult", "on_rrp", "RRPONTSYD")),
          "write_daily_snapshot references liquidity")

    # Drive the REAL write_daily_snapshot and assert the persisted _meta header carries
    # NONE of the liquidity series (even though the Dashboard fetches them for display).
    _tmpL = _PathL(_tfL.mkdtemp())
    _fragL = {"fragility_level": "normal", "good_news_sold": 0, "earnings_evaluated": 3}
    _pathL = _orrL.write_daily_snapshot([], macro_regime="risk_on", fragility=_fragL,
                                        date_str="2026-06-10", base_dir=_tmpL)
    _metaL = (_jsonL.loads(_PathL(_pathL).read_text(encoding="utf-8").splitlines()[0])
              if _pathL else {})
    _metaL_blob = _jsonL.dumps(_metaL)
    check("L.7 the persisted snapshot _meta excludes ALL liquidity series (never persisted)",
          bool(_metaL) and all(_k not in _metaL for _k in _LIQ_FIELDS)
          and "RRPONTSYD" not in _metaL_blob and "on_rrp" not in _metaL_blob,
          f"meta_keys={sorted(_metaL)}")

    # (iii) no fredapi / new client — fetch_liquidity reuses _fred_observations.
    _FL_SRC = _inspL.getsource(_mdL.fetch_liquidity)
    check("L.8 fetch_liquidity uses _fred_observations (no fredapi / new client)",
          "_fred_observations" in _FL_SRC
          and "fredapi" not in _FL_SRC and "Fred(" not in _FL_SRC)
except Exception as _eL:  # noqa: BLE001
    FAIL += 1
    import traceback as _tbL
    _failures.append(f"FAIL  L.x liquidity fetcher / snapshot-exclusion check: "
                     f"{_eL} :: {_tbL.format_exc()[-300:]}")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
print("============================================================")
print(f"Phase 5O Macro Dashboard Test Results: {PASS} passed, {FAIL} failed")
print("============================================================")
if _failures:
    for f in _failures:
        print(f)

sys.exit(0 if FAIL == 0 else 1)
