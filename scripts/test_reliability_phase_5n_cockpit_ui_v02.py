#!/usr/bin/env python3
"""
scripts/test_reliability_phase_5n_cockpit_ui_v02.py

Phase 5N — Cockpit UI v0.2 Opportunity-first Redesign test suite.

Phase 5N redesigns the single additive Streamlit page
``pages/7_Investment_Cockpit.py`` from a company/ticker-first research
display (Phase 5H/5H.1) into an opportunity-first, macro/theme-aware,
horizon-aware decision cockpit. The page now consumes — in addition to the
Phase 5G fixture demo pack — the Phase 5J Theme Intelligence, Phase 5K
Opportunity Queue, Phase 5L Research Pack, and Phase 5M Agent Debate /
Decision Workspace deterministic fixture builders.

This test is **static + import-safe + AppTest-backed**: it does NOT launch a
Streamlit server socket, does NOT call any external API, does NOT call any
LLM, and does NOT import the page module at top level (importing the page
would call ``st.set_page_config`` outside a Streamlit runtime). It asserts
source-level invariants, validates the fixture contracts the page consumes,
and renders the page through Streamlit's in-process ``AppTest`` harness in
both EN and ZH.

Usage:
    python3 scripts/test_reliability_phase_5n_cockpit_ui_v02.py
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
PHASE_5N_DOC = os.path.join(
    _REPO_ROOT,
    "docs",
    "reliability_phase_5n_cockpit_ui_v02_opportunity_first_redesign.md",
)

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
# Section 1 — Page exists + compiles; existing pages preserved
# ---------------------------------------------------------------------------

check("1.1 cockpit page exists", os.path.isfile(PAGE_PATH))

for rel in FORBIDDEN_LIVE_RUNTIME_PATHS:
    check(
        f"1.x forbidden live runtime path still exists: {rel}",
        os.path.exists(os.path.join(_REPO_ROOT, rel)),
    )

# Existing live pages must not be modified to reference Phase 5N / cockpit
# marker strings.
_PHASE_5N_MARKERS = (
    "phase5_demo_pack",
    "phase5_theme_intelligence",
    "phase5_opportunity_queue",
    "phase5_research_pack",
    "phase5_agent_debate",
    "Investment Cockpit",
)
for rel in EXISTING_LIVE_PAGES:
    abs_path = os.path.join(_REPO_ROOT, rel)
    if not os.path.exists(abs_path):
        continue
    src = _read_text(abs_path)
    for marker in _PHASE_5N_MARKERS:
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


# ---------------------------------------------------------------------------
# Section 3 — Page consumes Phase 5G demo pack + Phase 5J/5K/5L/5M fixtures
# ---------------------------------------------------------------------------

# Phase 5G demo pack still imported / used.
check(
    "3.1 page imports lib.reliability.phase5_demo_pack",
    "from lib.reliability.phase5_demo_pack" in _PAGE_SRC,
)
for sym in (
    "build_default_cockpit_demo_pack",
    "CockpitDemoPack",
    "CockpitDemoScenario",
    "DEMO_SCENARIO_ORDER",
):
    check(f"3.2 page references Phase 5G symbol: {sym}", sym in _PAGE_SRC)

# Phase 5J/5K/5L/5M modules imported.
for mod in (
    "lib.reliability.phase5_theme_intelligence",
    "lib.reliability.phase5_opportunity_queue",
    "lib.reliability.phase5_research_pack",
    "lib.reliability.phase5_agent_debate",
):
    check(f"3.3 page imports module: {mod}", f"from {mod}" in _PAGE_SRC)

# Phase 5J/5K/5L/5M fixture builders + top view models referenced.
_PHASE_5JKLM_SYMBOLS = (
    # Phase 5J
    "build_default_theme_intelligence_snapshot",
    "ThemeIntelligenceSnapshot",
    # Phase 5K
    "build_default_opportunity_queue_view",
    "build_degraded_opportunity_queue_view",
    "HorizonAwareOpportunityQueueView",
    # Phase 5L
    "build_default_research_pack_bundle",
    "build_degraded_research_pack_bundle",
    "AutoResearchPackOrchestrationBoundary",
    # Phase 5M
    "build_default_agent_debate_workspace",
    "build_degraded_agent_debate_workspace",
    "AgentDebateWorkspace",
    "DecisionWorkspaceView",
)
for sym in _PHASE_5JKLM_SYMBOLS:
    check(f"3.4 page references Phase 5J/5K/5L/5M symbol: {sym}", sym in _PAGE_SRC)

# Phase 5B/5C/5D views still referenced (Research Snapshot / Trade / Option).
for sym in ("CompanyResearchHubView", "ThesisTrackerView", "PortfolioCockpitView"):
    check(f"3.5 page references Phase 5B/5C/5D view: {sym}", sym in _PAGE_SRC)

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

# No live workflow-state read (literal allowed in negation copy only).
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
# Section 4 — No external API / broker / order routing call sites
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
for tok in _FORBIDDEN_EXTERNAL_API_TOKENS:
    check(
        f"4.x page does NOT contain external/broker token: {tok}",
        tok not in _PAGE_SRC,
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
# Section 6 — v0.2 tab structure
# ---------------------------------------------------------------------------

_V02_TAB_KEY_TO_EN = {
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

for key, expected_en in _V02_TAB_KEY_TO_EN.items():
    check(
        f"6.a EN tab key {key!r} == {expected_en!r}",
        _EN.get(key) == expected_en,
        detail=repr(_EN.get(key)),
    )
    check(
        f"6.b ZH tab key {key!r} non-empty",
        _ZH.get(key, "").strip() != "",
        detail=repr(_ZH.get(key)),
    )
    check(f"6.c page references tab key {key!r}", key in _PAGE_SRC)

# Market Themes + Opportunity Queue must appear BEFORE Research Snapshot in
# the page's tab order (opportunity-first).
_pos_themes = _PAGE_SRC.find('t("cockpit_tab_themes")')
_pos_opp = _PAGE_SRC.find('t("cockpit_tab_opportunity")')
_pos_research = _PAGE_SRC.find('t("cockpit_tab_research")')
check(
    "6.d Market Themes tab declared before Research Snapshot tab",
    -1 < _pos_themes < _pos_research,
)
check(
    "6.e Opportunity Queue tab declared before Research Snapshot tab",
    -1 < _pos_opp < _pos_research,
)

# Company Research Hub is no longer presented as a primary early tab — the
# page must not wire ``cockpit_tab_company`` as a tab. The key still exists in
# TRANSLATIONS (additive policy) and is repositioned to "Research Snapshot".
check(
    "6.f page no longer references cockpit_tab_company as a tab",
    "cockpit_tab_company" not in _PAGE_SRC,
)
check(
    "6.g Research Snapshot label is 'Research Snapshot'",
    _EN.get("cockpit_tab_research") == "Research Snapshot",
)
check(
    "6.h old 'Company Research Hub' label not in v0.2 tab values",
    "Company Research Hub" not in set(_V02_TAB_KEY_TO_EN.values()),
)

# Page still registers in the global sidebar as nav_p7.
check("6.i EN nav_p7 non-empty", _EN.get("nav_p7", "").strip() != "")
check("6.j ZH nav_p7 non-empty", _ZH.get("nav_p7", "").strip() != "")
try:
    _UI_UTILS_SRC = _read_text(os.path.join(_REPO_ROOT, "ui_utils.py"))
except Exception as _uu_exc:  # noqa: BLE001
    _UI_UTILS_SRC = ""
    _failures.append(f"FAIL  6.k could not read ui_utils.py: {_uu_exc}")
check(
    "6.k ui_utils.render_sidebar registers pages/7_Investment_Cockpit.py",
    "pages/7_Investment_Cockpit.py" in _UI_UTILS_SRC
    and 'label=t("nav_p7")' in _UI_UTILS_SRC,
)


# ---------------------------------------------------------------------------
# Section 7 — New chrome translation keys exist in EN + ZH
# ---------------------------------------------------------------------------

_REQUIRED_NEW_CHROME_KEYS = [
    # Overview v0.2
    "cockpit_overview_v02_preview",
    "cockpit_overview_flow",
    "cockpit_overview_flow_header",
    # Market Themes
    "cockpit_themes_caption",
    "cockpit_themes_heat_not_buy",
    "cockpit_themes_lifecycle",
    "cockpit_themes_chain_decomposition",
    "cockpit_themes_candidate_tickers",
    "cockpit_themes_no_themes",
    # Opportunity Queue
    "cockpit_opportunity_caption",
    "cockpit_opportunity_heat_not_trade",
    "cockpit_opportunity_short_term",
    "cockpit_opportunity_mid_term",
    "cockpit_opportunity_long_term",
    "cockpit_opportunity_watch_wait",
    "cockpit_opportunity_research_more",
    "cockpit_opportunity_no_trade",
    "cockpit_opportunity_cross_horizon",
    # Decision Workspace
    "cockpit_decision_caption",
    "cockpit_decision_review_only",
    "cockpit_decision_recommendation_state",
    "cockpit_decision_consensus",
    "cockpit_decision_conflicts",
    "cockpit_decision_evidence_coverage",
    # Research Snapshot
    "cockpit_research_caption",
    "cockpit_research_thesis_header",
    "cockpit_research_pack_header",
    # Agent Debate
    "cockpit_debate_caption",
    "cockpit_debate_participants",
    "cockpit_debate_critic",
    "cockpit_debate_alloc_non_exec",
    "cockpit_debate_option_non_exec",
    "cockpit_debate_conflicts",
    # Trade / Allocation Plan
    "cockpit_trade_caption",
    "cockpit_trade_boundary",
    # Option Overlay
    "cockpit_option_caption_v02",
    # Feedback / Review
    "cockpit_review_caption",
    "cockpit_review_actions",
    # Provenance / Diagnostics
    "cockpit_provenance_no_api",
    "cockpit_provenance_intel_validation",
]
for key in _REQUIRED_NEW_CHROME_KEYS:
    check(f"7.a EN chrome key {key!r} non-empty", _EN.get(key, "").strip() != "")
    check(f"7.b ZH chrome key {key!r} non-empty", _ZH.get(key, "").strip() != "")
    check(f"7.c page references chrome key {key!r}", key in _PAGE_SRC)

# The Trade boundary statement must say it is review-only / not an order ticket.
check(
    "7.d EN trade boundary is review-only / not an order ticket",
    "review-only" in _EN.get("cockpit_trade_boundary", "").lower()
    and "order ticket" in _EN.get("cockpit_trade_boundary", "").lower(),
)


# ---------------------------------------------------------------------------
# Section 8 — No order-ticket-like fields exposed in the page
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
    # NOTE: the field-form ``broker_payload`` is forbidden above. The lowercase
    # space phrase "broker payload(s)" is intentionally NOT forbidden because it
    # appears legitimately in the page's safety negation copy ("No orders, order
    # tickets, broker payloads, or executable instructions."), mirroring how the
    # Phase 5H test allows "order tickets" in negation copy.
    "Broker payload",
]
for tok in _FORBIDDEN_ORDER_TICKET_TOKENS:
    check(
        f"8.x page does NOT contain order-ticket token: {tok!r}",
        tok not in _PAGE_SRC,
    )


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
    check(
        f"9.x page does NOT positively authorize: {form!r}",
        form not in _PAGE_SRC,
    )


# ---------------------------------------------------------------------------
# Section 10 — Phase 5J/5K/5L/5M fixture builders build with safety invariants
# ---------------------------------------------------------------------------

try:
    from lib.reliability.phase5_theme_intelligence import (  # noqa: E402
        build_default_theme_intelligence_snapshot,
        build_empty_theme_intelligence_snapshot,
    )

    _theme = build_default_theme_intelligence_snapshot()
    _theme_vs = _theme.validation_summary
    check("10.1 theme snapshot has themes", len(_theme.universe.themes) >= 2)
    check("10.2 theme vs no_buy_signal_fields", _theme_vs.no_buy_signal_fields is True)
    check(
        "10.3 theme vs no_executable_order_fields",
        _theme_vs.no_executable_order_fields is True,
    )
    check(
        "10.4 theme vs approved_for_execution_absent",
        _theme_vs.approved_for_execution_absent is True,
    )
    check(
        "10.5 theme entry_quality not computed (heat != entry quality)",
        _theme.entry_quality_placeholder.computed is False,
    )
    check(
        "10.6 every theme heat_score.is_buy_signal is False",
        all(th.heat_score.is_buy_signal is False for th in _theme.universe.themes),
    )
    # AI + Space industry-chain decomposition present.
    _theme_names = {th.name for th in _theme.universe.themes}
    check("10.7 AI theme present", "Artificial Intelligence" in _theme_names)
    check("10.8 Space theme present", "Space Economy" in _theme_names)
    _ai = next(th for th in _theme.universe.themes if th.name == "Artificial Intelligence")
    _space = next(th for th in _theme.universe.themes if th.name == "Space Economy")
    check("10.9 AI theme has industry-chain nodes", len(_ai.industry_chain_nodes) >= 6)
    check(
        "10.10 Space theme has industry-chain nodes",
        len(_space.industry_chain_nodes) >= 6,
    )
    _ai_roles = {n.role_in_chain for n in _ai.industry_chain_nodes}
    for role in ("compute", "memory", "optical", "cloud"):
        check(f"10.11 AI chain has role {role!r}", role in _ai_roles)
    # Empty snapshot is safe.
    _empty_theme = build_empty_theme_intelligence_snapshot()
    check(
        "10.12 empty theme snapshot is safe empty",
        _empty_theme.validation_summary.is_safe_empty is True,
    )
    check(
        "10.13 theme models do not declare approved_for_execution",
        "approved_for_execution" not in type(_theme).model_fields,
    )
except Exception as e:  # noqa: BLE001
    FAIL += 1
    _failures.append(f"FAIL  10.x theme intelligence import/build failed: {e}")


try:
    from lib.reliability.phase5_opportunity_queue import (  # noqa: E402
        build_default_opportunity_queue_view,
        build_degraded_opportunity_queue_view,
    )

    _q = build_default_opportunity_queue_view()
    _q_vs = _q.validation_summary
    check(
        "10.20 queue has six sections",
        all(
            getattr(_q, name) is not None
            for name in (
                "short_term",
                "mid_term",
                "long_term",
                "watch_wait",
                "research_more",
                "no_trade_avoid",
            )
        ),
    )
    check("10.21 queue vs no_unsafe_trade_now", _q_vs.no_unsafe_trade_now is True)
    check(
        "10.22 queue vs no_executable_order_fields",
        _q_vs.no_executable_order_fields is True,
    )
    check(
        "10.23 queue vs approved_for_execution_absent",
        _q_vs.approved_for_execution_absent is True,
    )
    check("10.24 queue vs no_buy_signal_fields", _q_vs.no_buy_signal_fields is True)
    check(
        "10.25 same ticker appears across horizons",
        _q_vs.multi_horizon_ticker_count >= 1,
    )
    # Heat does not imply trade_now: any trade_now candidate is not crowded.
    _all_cands = []
    for qq in (_q.short_term, _q.mid_term, _q.long_term):
        _all_cands.extend(qq.candidates)
    _trade_now = [c for c in _all_cands if c.decision_label == "trade_now"]
    check(
        "10.26 trade_now candidates are not elevated-crowding",
        all(c.crowding_risk.is_elevated is False for c in _trade_now),
    )
    check(
        "10.27 every candidate theme_heat.is_buy_signal False",
        all(c.theme_heat.is_buy_signal is False for c in _all_cands),
    )
    _qd = build_degraded_opportunity_queue_view()
    check(
        "10.28 degraded queue has research_more or warnings",
        _qd.research_more.count >= 1 or len(_qd.warnings) >= 1,
    )
    check(
        "10.29 queue models do not declare approved_for_execution",
        "approved_for_execution" not in type(_q).model_fields,
    )
except Exception as e:  # noqa: BLE001
    FAIL += 1
    _failures.append(f"FAIL  10.2x opportunity queue import/build failed: {e}")


try:
    from lib.reliability.phase5_research_pack import (  # noqa: E402
        build_default_research_pack_bundle,
        build_degraded_research_pack_bundle,
    )

    _rp = build_default_research_pack_bundle()
    _rp_vs = _rp.validation_summary
    check("10.40 research pack has requests", len(_rp.pack_requests) >= 1)
    check("10.41 research banner no_execution_authorized", _rp.safety_banner.no_execution_authorized is True)
    check("10.42 research banner no_orders", _rp.safety_banner.no_orders is True)
    check("10.43 research vs no_live_module_calls", _rp_vs.no_live_module_calls is True)
    check("10.44 research vs no_final_recommendation", _rp_vs.no_final_recommendation is True)
    check("10.45 research vs all_modules_descriptive", _rp_vs.all_modules_descriptive is True)
    check(
        "10.46 research vs approved_for_execution_absent",
        _rp_vs.approved_for_execution_absent is True,
    )
    # Module requests are descriptive (no runtime call).
    _all_modreq = []
    for req in _rp.pack_requests:
        _all_modreq.extend(req.required_modules)
        _all_modreq.extend(req.optional_modules)
    check(
        "10.47 all module requests is_runtime_call False",
        all(m.is_runtime_call is False for m in _all_modreq),
    )
    # Module result refs are placeholders.
    _all_results = []
    for b in _rp.pack_bundles:
        _all_results.extend(b.module_results)
    check(
        "10.48 all module result refs are placeholders",
        all(r.is_placeholder is True and r.result_ref is None for r in _all_results),
    )
    _rpd = build_degraded_research_pack_bundle()
    check("10.49 degraded research pack has warnings", len(_rpd.warnings) >= 1)
    check(
        "10.50 research models do not declare approved_for_execution",
        "approved_for_execution" not in type(_rp).model_fields,
    )
except Exception as e:  # noqa: BLE001
    FAIL += 1
    _failures.append(f"FAIL  10.4x research pack import/build failed: {e}")


try:
    from lib.reliability.phase5_agent_debate import (  # noqa: E402
        build_default_agent_debate_workspace,
        build_degraded_agent_debate_workspace,
        build_empty_agent_debate_workspace,
    )

    _ws = build_default_agent_debate_workspace()
    _ws_vs = _ws.validation_summary
    check("10.60 workspace has sessions", len(_ws.sessions) >= 1)
    check("10.61 workspace has views", len(_ws.workspace_views) >= 1)
    check(
        "10.62 banner no_execution_authorized",
        _ws.safety_banner.no_execution_authorized is True,
    )
    check("10.63 banner requires_human_review", _ws.safety_banner.requires_human_review is True)
    check("10.64 vs no_live_agent_calls", _ws_vs.no_live_agent_calls is True)
    check("10.65 vs no_final_recommendation", _ws_vs.no_final_recommendation is True)
    check(
        "10.66 vs approved_for_execution_absent",
        _ws_vs.approved_for_execution_absent is True,
    )
    check("10.67 vs critic_hides_no_conflict", _ws_vs.critic_hides_no_conflict is True)
    # Every decision-workspace view is review-only / non-executable.
    check(
        "10.68 every workspace view is_executable_decision False",
        all(v.is_executable_decision is False for v in _ws.workspace_views),
    )
    check(
        "10.69 every workspace view requires_human_review True",
        all(v.requires_human_review is True for v in _ws.workspace_views),
    )
    # Participants / stances are not live.
    for s in _ws.sessions:
        check(
            f"10.70 session {s.session_id} participants not live",
            all(p.is_live_agent is False for p in s.participants),
        )
        check(
            f"10.71 session {s.session_id} stances not live output",
            all(st.is_live_agent_output is False for st in s.stances),
        )
        # Bull/bear/risk/critic/allocation/option perspectives present.
        check(
            f"10.72 session {s.session_id} has all six perspectives",
            all(
                getattr(s, name) is not None
                for name in (
                    "bull_case",
                    "bear_case",
                    "risk_case",
                    "critic_review",
                    "allocation_perspective",
                    "option_perspective",
                )
            ),
        )
        # Allocation + option clearly non-executable.
        check(
            f"10.73 session {s.session_id} allocation non-executable",
            s.allocation_perspective.is_executable_allocation is False,
        )
        check(
            f"10.74 session {s.session_id} option non-executable",
            s.option_perspective.is_executable_order is False,
        )
        # Critic never hides an unresolved conflict.
        check(
            f"10.75 session {s.session_id} critic hides_unresolved_conflict False",
            s.critic_review.hides_unresolved_conflict is False,
        )
    # Degraded → research_more / insufficient evidence (or warnings).
    _wsd = build_degraded_agent_debate_workspace()
    check(
        "10.76 degraded workspace surfaces warnings or research_more",
        len(_wsd.warnings) >= 1
        or any(v.status == "research_more" for v in _wsd.workspace_views),
    )
    # Empty → safe empty.
    _wse = build_empty_agent_debate_workspace()
    check(
        "10.77 empty workspace is safe empty",
        _wse.validation_summary.is_safe_empty is True,
    )
    check(
        "10.78 debate models do not declare approved_for_execution",
        "approved_for_execution" not in type(_ws).model_fields
        and "approved_for_execution" not in type(_ws.workspace_views[0]).model_fields,
    )
except Exception as e:  # noqa: BLE001
    FAIL += 1
    _failures.append(f"FAIL  10.6x agent debate import/build failed: {e}")


# ---------------------------------------------------------------------------
# Section 11 — Phase 5G demo pack still builds with invariants
# ---------------------------------------------------------------------------

try:
    from lib.reliability.phase5_demo_pack import (  # noqa: E402
        CockpitDemoPack as _CockpitDemoPack,
        build_default_cockpit_demo_pack as _build_pack,
    )

    _pack = _build_pack()
    check("11.1 demo pack builds", isinstance(_pack, _CockpitDemoPack))
    check(
        "11.2 demo pack approved_for_execution invariant",
        _pack.validation_summary.all_approved_for_execution_false,
    )
    check(
        "11.3 demo pack no-executable-order-fields invariant",
        _pack.validation_summary.no_executable_order_fields,
    )
    check(
        "11.4 demo pack has no validation errors",
        not _pack.validation_summary.errors,
        detail=str(_pack.validation_summary.errors),
    )
except Exception as e:  # noqa: BLE001
    FAIL += 1
    _failures.append(f"FAIL  11.x demo pack import/build failed: {e}")


# ---------------------------------------------------------------------------
# Section 12 — Phase 5N design doc exists with required sections
# ---------------------------------------------------------------------------

check("12.1 Phase 5N design doc exists", os.path.isfile(PHASE_5N_DOC))
if os.path.isfile(PHASE_5N_DOC):
    _doc = _read_text(PHASE_5N_DOC)
    for heading in (
        "Purpose",
        "Phase 5I",
        "Phase 5J",
        "Phase 5K",
        "Phase 5L",
        "Phase 5M",
        "Phase 5H",
        "opportunity-first",
        "Market Themes",
        "Opportunity Queue",
        "Decision Workspace",
        "Research Snapshot",
        "Agent Debate",
        "Trade",
        "Option Overlay",
        "Bilingual",
        "Fixture-only",
        "Non-goals",
        "Guardrails",
        "Acceptance criteria",
        "Phase 5O",
    ):
        check(f"12.x Phase 5N doc mentions: {heading!r}", heading in _doc)


# ---------------------------------------------------------------------------
# Section 13 — No persistence / DB / vector store / file-open
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
        f"13.x page does NOT contain persistence token: {tok!r}",
        tok not in _PAGE_SRC,
    )


# ---------------------------------------------------------------------------
# Section 14 — Fail-closed branch (no LLM/API fallback)
# ---------------------------------------------------------------------------

check(
    "14.1 page has a fail-closed branch",
    "Fail-closed" in _PAGE_SRC or "fail closed" in _PAGE_SRC.lower(),
)
check(
    "14.2 page asserts no live fallback",
    "no fallback to live" in _PAGE_SRC.lower(),
)


# ---------------------------------------------------------------------------
# Section 15 — AppTest render in EN and ZH
# ---------------------------------------------------------------------------

_APPTEST_AVAILABLE = False
try:
    from streamlit.testing.v1 import AppTest  # type: ignore
    _APPTEST_AVAILABLE = True
except Exception as _at_imp_exc:  # noqa: BLE001
    _failures.append(f"FAIL  15.0 AppTest import failed: {_at_imp_exc}")


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
    _EN_TAB_LABELS = tuple(_V02_TAB_KEY_TO_EN.values())
    _ZH_TAB_LABELS = tuple(_ZH.get(k, "") for k in _V02_TAB_KEY_TO_EN)

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
                f"15.{tag}.1 AppTest {tag} render completed without exception",
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
                    f"15.{tag}.2 {tag} render contains tab label: {label!r}",
                    label in rendered,
                )

            # Safety banner still appears.
            check(
                f"15.{tag}.3 {tag} render contains safety headline",
                _UI_TRANSLATIONS.get(lang, {}).get("cockpit_safety_headline", "X")
                in rendered,
            )

            # No positive approved_for_execution authorization in rendered text.
            for form in _POSITIVE_AUTH_FORMS:
                check(
                    f"15.{tag}.4 {tag} render has no positive auth: {form!r}",
                    form not in rendered,
                )

        # Degraded scenario also renders without exception.
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
            "15.DEGRADED.1 degraded scenario renders without exception",
            ran_ok2,
            detail=exc_info2 or "",
        )
    finally:
        _ui_utils_mod.render_sidebar = _orig_render_sidebar  # type: ignore[assignment]
        _ui_utils_mod.apply_theme = _orig_apply_theme  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Section 16 — Trade / Allocation tab bilingual chrome (inactive-tab static scan)
# ---------------------------------------------------------------------------
#
# The AppTest section (15) asserts that every tab LABEL renders and that no
# positive authorization appears, but it does NOT assert the *absence* of
# untranslated English-literal chrome inside a tab body. Because Streamlit tab
# bodies all execute during a single AppTest run, an English literal inside a
# non-open tab (e.g. the Trade / Allocation tab) is easy to miss when the only
# AppTest assertions are tab-label presence checks. This static source scan
# catches untranslated chrome in ANY tab regardless of which tab AppTest would
# render as "open" — it is the inactive-tab guard that blocked the first
# Phase 5N review.

# 16.a — known English chrome literals must NOT appear as direct UI strings
# anywhere in the page source. These are the exact Trade / Allocation labels
# flagged by review; they must route through ui_utils.t() and live only in
# ui_utils.TRANSLATIONS (which this scan does not inspect).
_FORBIDDEN_TRADE_CHROME_LITERALS = [
    "Max risk budget %",
    "Max portfolio loss %",
    "High / medium / low / unknown risk counts",
    "Total cash impact",
    "Min projected cash %",
    "Max projected cash %",
]
for lit in _FORBIDDEN_TRADE_CHROME_LITERALS:
    check(
        f"16.a page has no untranslated chrome literal: {lit!r}",
        lit not in _PAGE_SRC,
    )


def _source_slice(src: str, start_marker: str, end_marker: str) -> str:
    i = src.find(start_marker)
    if i < 0:
        return ""
    j = src.find(end_marker, i + len(start_marker))
    return src[i:j] if j > i else src[i:]


# 16.b — the Trade / Allocation render functions must not hardcode visible
# table column headers as raw English dict-key strings; they must route
# through t(...) keys. Scope the scan to the Trade / Allocation source slice so
# it does not false-positive on intentional schema identifiers in other tabs.
_TRADE_SRC = _source_slice(
    _PAGE_SRC, "def _render_trade_plan(", "def _render_option_overlay_one("
)
check("16.b0 Trade/Allocation source slice located", bool(_TRADE_SRC))

_FORBIDDEN_TRADE_COLUMN_LITERALS = [
    '"target":',
    '"horizon":',
    '"status":',
    '"action":',
    '"kind":',
    '"label":',
    '"note":',
    '"target_alloc_pct":',
    '"actual_alloc_pct":',
    '"review_needed":',
]
for lit in _FORBIDDEN_TRADE_COLUMN_LITERALS:
    check(
        f"16.b Trade source has no raw column-key chrome: {lit!r}",
        lit not in _TRADE_SRC,
    )

# The Trade / Allocation execution-safety banner caption must route its flag
# labels through t() rather than hardcoding the raw ``field=value`` form. (The
# raw ``is_executable_*=`` / ``requires_human_review=`` schema-flag form is
# intentionally retained as non-executability evidence in the Decision
# Workspace and Agent Debate tabs, so this check is scoped to the Trade slice.)
for lit in ("is_non_executable=", "requires_human_review="):
    check(
        f"16.b2 Trade banner caption does not hardcode flag label: {lit!r}",
        lit not in _TRADE_SRC,
    )

# 16.c — the new Trade / Allocation chrome translation keys exist in EN + ZH
# and are actually referenced by the page.
_NEW_TRADE_CHROME_KEYS = [
    "cockpit_trade_non_executable",
    "cockpit_trade_requires_review",
    "cockpit_trade_max_risk_budget",
    "cockpit_trade_max_portfolio_loss",
    "cockpit_trade_risk_counts",
    "cockpit_trade_total_cash_impact",
    "cockpit_trade_min_cash",
    "cockpit_trade_max_cash",
    "cockpit_trade_col_target",
    "cockpit_trade_col_horizon",
    "cockpit_trade_col_action",
    "cockpit_trade_col_status",
    "cockpit_trade_col_target_alloc",
    "cockpit_trade_col_actual_alloc",
    "cockpit_trade_col_review_needed",
    "cockpit_trade_col_kind",
    "cockpit_trade_col_label",
    "cockpit_trade_col_pct",
    "cockpit_trade_col_value",
    "cockpit_trade_col_note",
]
for key in _NEW_TRADE_CHROME_KEYS:
    check(f"16.c EN trade chrome key {key!r} non-empty", _EN.get(key, "").strip() != "")
    check(f"16.d ZH trade chrome key {key!r} non-empty", _ZH.get(key, "").strip() != "")
    check(f"16.e page references trade chrome key {key!r}", key in _PAGE_SRC)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
print("============================================================")
print(f"Phase 5N Cockpit UI v0.2 Test Results: {PASS} passed, {FAIL} failed")
print("============================================================")
if _failures:
    for f in _failures:
        print(f)

sys.exit(0 if FAIL == 0 else 1)
