#!/usr/bin/env python3
"""
scripts/test_reliability_phase_5q_human_feedback_ui.py

Phase 5Q — Human Feedback UI v0.1 test suite.

Phase 5Q adds a controlled, **session-only / non-persistent / non-executable**
human-feedback review surface to the Investment Cockpit
(``pages/7_Investment_Cockpit.py`` Feedback / Review tab), backed by the new
``lib/reliability/phase5_human_feedback_ui.py`` UI/session contracts.

This test is **static + import-safe + AppTest-backed**: it does NOT launch a
Streamlit server socket, does NOT call any external API or LLM, and does NOT
import the page module at top level (importing the page would call
``st.set_page_config`` outside a Streamlit runtime). It asserts source-level
invariants, validates the session contracts, and renders the page through
Streamlit's in-process ``AppTest`` harness in both EN and ZH.

Usage:
    python3 scripts/test_reliability_phase_5q_human_feedback_ui.py
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
MODULE_PATH = os.path.join(
    _REPO_ROOT, "lib", "reliability", "phase5_human_feedback_ui.py"
)
PHASE_5Q_DOC = os.path.join(
    _REPO_ROOT, "docs", "reliability_phase_5q_human_feedback_ui_v01.md"
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
    "lib/workflow_state.py",
    "lib/data_fetcher.py",
    "lib/reliability/integration_boundary.py",
]


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Section 1 — Page + module exist; existing pages preserved
# ---------------------------------------------------------------------------

check("1.1 cockpit page exists", os.path.isfile(PAGE_PATH))
check("1.2 Phase 5Q feedback-UI module exists", os.path.isfile(MODULE_PATH))

for rel in FORBIDDEN_LIVE_RUNTIME_PATHS:
    check(
        f"1.x forbidden live runtime path still exists: {rel}",
        os.path.exists(os.path.join(_REPO_ROOT, rel)),
    )

# Existing live pages (and app.py) must not reference Phase 5Q markers.
_PHASE_5Q_MARKERS = (
    "phase5_human_feedback_ui",
    "phase5q_feedback_session",
    "build_human_feedback_ui_state",
)
for rel in EXISTING_LIVE_PAGES:
    abs_path = os.path.join(_REPO_ROOT, rel)
    if not os.path.exists(abs_path):
        continue
    src = _read_text(abs_path)
    for marker in _PHASE_5Q_MARKERS:
        check(
            f"1.y existing page {rel} not modified to reference marker: {marker}",
            marker not in src,
        )


# ---------------------------------------------------------------------------
# Section 2 — Page + module parse cleanly (import-safe)
# ---------------------------------------------------------------------------

_PAGE_SRC = _read_text(PAGE_PATH) if os.path.isfile(PAGE_PATH) else ""
_MODULE_SRC = _read_text(MODULE_PATH) if os.path.isfile(MODULE_PATH) else ""

check("2.1 page source non-empty", bool(_PAGE_SRC))
try:
    _PAGE_AST = ast.parse(_PAGE_SRC, filename=PAGE_PATH)
    _PAGE_PARSED_OK = True
except SyntaxError as e:
    _PAGE_AST = None
    _PAGE_PARSED_OK = False
    _failures.append(f"FAIL  2.1 SyntaxError in page: {e}")
check("2.2 page AST built", _PAGE_PARSED_OK)

try:
    ast.parse(_MODULE_SRC, filename=MODULE_PATH)
    _MODULE_PARSED_OK = True
except SyntaxError as e:
    _MODULE_PARSED_OK = False
    _failures.append(f"FAIL  2.3 SyntaxError in module: {e}")
check("2.3 module AST built", _MODULE_PARSED_OK)

_imported_module_names: set[str] = set()
if _PAGE_AST is not None:
    for node in ast.walk(_PAGE_AST):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _imported_module_names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                _imported_module_names.add(node.module.split(".")[0])

check("2.4 page imports streamlit", "streamlit" in _imported_module_names)


# ---------------------------------------------------------------------------
# Section 3 — Page imports Phase 5Q feedback-UI contracts; no forbidden imports
# ---------------------------------------------------------------------------

check(
    "3.1 page imports lib.reliability.phase5_human_feedback_ui",
    "from lib.reliability.phase5_human_feedback_ui" in _PAGE_SRC,
)
for sym in (
    "HumanFeedbackUIState",
    "build_human_feedback_ui_state",
    "build_human_feedback_session_record",
):
    check(f"3.2 page references Phase 5Q symbol: {sym}", sym in _PAGE_SRC)

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
        f"3.3 page does NOT import forbidden module: {mod}",
        f"import {mod}" not in _PAGE_SRC and f"from {mod}" not in _PAGE_SRC,
    )
    check(
        f"3.4 Phase 5Q module does NOT import forbidden module: {mod}",
        f"import {mod}" not in _MODULE_SRC and f"from {mod}" not in _MODULE_SRC,
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
        f"4.a page does NOT contain external/broker token: {tok}",
        tok not in _PAGE_SRC,
    )
    check(
        f"4.b module does NOT contain external/broker token: {tok}",
        tok not in _MODULE_SRC,
    )


# ---------------------------------------------------------------------------
# Section 5 — Session-only / non-persistent (no file/DB/vector/workflow writes)
# ---------------------------------------------------------------------------

# Page uses st.session_state for transient UI state.
check("5.1 page uses st.session_state", "st.session_state" in _PAGE_SRC)
check(
    "5.2 page declares a transient session key",
    "_HF_SESSION_KEY" in _PAGE_SRC and "phase5q_feedback_session" in _PAGE_SRC,
)

# No persistence / DB / vector store / file-open patterns in page OR module.
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
for tok in _FORBIDDEN_PERSISTENCE_TOKENS:
    check(f"5.3 page does NOT contain persistence token: {tok!r}", tok not in _PAGE_SRC)
    check(
        f"5.4 module does NOT contain persistence token: {tok!r}",
        tok not in _MODULE_SRC,
    )

# No workflow-state read/write CALL patterns. (A bare path mention in safety
# negation copy / docstrings is allowed, mirroring the Phase 5N test — only
# actual open/read/write call sites against the file are forbidden.)
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
for pat in _WORKFLOW_STATE_CALL_PATTERNS:
    check(
        f"5.5 page does NOT read/write workflow-state via: {pat!r}",
        pat not in _PAGE_SRC,
    )
    check(
        f"5.6 module does NOT read/write workflow-state via: {pat!r}",
        pat not in _MODULE_SRC,
    )


# ---------------------------------------------------------------------------
# Section 6 — No order-ticket-like fields
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
# The boolean safety flag ``no_order_ticket_fields`` legitimately *asserts the
# absence* of order-ticket fields; strip it before scanning so it does not
# false-positive on the ``order_ticket`` substring.
_MODULE_SCAN = _MODULE_SRC.replace("no_order_ticket_fields", "")
for tok in _FORBIDDEN_ORDER_TICKET_TOKENS:
    check(f"6.a page has no order-ticket token: {tok!r}", tok not in _PAGE_SRC)
    check(f"6.b module has no order-ticket token: {tok!r}", tok not in _MODULE_SCAN)


# ---------------------------------------------------------------------------
# Section 7 — approved_for_execution never positively authorized
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
    check(f"7.a page does NOT positively authorize: {form!r}", form not in _PAGE_SRC)
    check(f"7.b module does NOT positively authorize: {form!r}", form not in _MODULE_SRC)


# ---------------------------------------------------------------------------
# Section 8 — Import ui_utils.TRANSLATIONS + Phase 5Q chrome keys exist EN/ZH
# ---------------------------------------------------------------------------

try:
    from ui_utils import TRANSLATIONS as _UI_TRANSLATIONS
except Exception as _ti_exc:  # noqa: BLE001
    _UI_TRANSLATIONS = {"en": {}, "zh": {}}
    _failures.append(f"FAIL  8.0 could not import ui_utils.TRANSLATIONS: {_ti_exc}")

_EN = _UI_TRANSLATIONS.get("en", {})
_ZH = _UI_TRANSLATIONS.get("zh", {})

# Feedback / Review tab still present.
check("8.1 page references cockpit_tab_review", "cockpit_tab_review" in _PAGE_SRC)
check("8.2 EN cockpit_tab_review == 'Feedback / Review'", _EN.get("cockpit_tab_review") == "Feedback / Review")
check("8.3 ZH cockpit_tab_review non-empty", _ZH.get("cockpit_tab_review", "").strip() != "")

_REQUIRED_HF_CHROME_KEYS = [
    "cockpit_review_hf_safety_headline",
    "cockpit_review_hf_safety_b1",
    "cockpit_review_hf_safety_b2",
    "cockpit_review_hf_safety_b3",
    "cockpit_review_hf_safety_b4",
    "cockpit_review_hf_safety_b5",
    "cockpit_review_hf_form_header",
    "cockpit_review_hf_no_targets",
    "cockpit_review_hf_kind_label",
    "cockpit_review_hf_target_label",
    "cockpit_review_hf_target_help",
    "cockpit_review_hf_action_label",
    "cockpit_review_hf_note_label",
    "cockpit_review_hf_note_ph",
    "cockpit_review_hf_non_exec_note",
    "cockpit_review_hf_add_button",
    "cockpit_review_hf_clear_button",
    "cockpit_review_hf_preview_header",
    "cockpit_review_hf_preview_note",
    "cockpit_review_hf_preview_empty",
    "cockpit_review_hf_preview_count",
    "cockpit_review_hf_col_kind",
    "cockpit_review_hf_col_target",
    "cockpit_review_hf_col_action",
    "cockpit_review_hf_col_note",
    "cockpit_review_hf_bind_kind",
    "cockpit_review_hf_bind_ticker",
    "cockpit_review_hf_bind_horizon",
    "cockpit_review_hf_fixture_header",
]
for key in _REQUIRED_HF_CHROME_KEYS:
    check(f"8.a EN chrome key {key!r} non-empty", _EN.get(key, "").strip() != "")
    check(f"8.b ZH chrome key {key!r} non-empty", _ZH.get(key, "").strip() != "")
    check(f"8.c page references chrome key {key!r}", key in _PAGE_SRC)

# Action-label keys for all nine review actions.
_REQUIRED_ACTIONS = [
    "accept_for_watchlist",
    "reject",
    "modify_thesis",
    "request_more_research",
    "wait_for_pullback",
    "manually_executed_outside_system",
    "skip",
    "review_later",
    "no_trade_confirmed",
]
for action in _REQUIRED_ACTIONS:
    key = f"cockpit_review_action_{action}"
    check(f"8.d EN action label {key!r} non-empty", _EN.get(key, "").strip() != "")
    check(f"8.e ZH action label {key!r} non-empty", _ZH.get(key, "").strip() != "")

# Safety headline must state session-only / not persisted semantics.
_en_head = _EN.get("cockpit_review_hf_safety_headline", "").lower()
check(
    "8.f EN safety headline states session-only + not persisted",
    "session-only" in _en_head and ("not persisted" in _en_head or "persist" in _en_head),
)
# Preview-count format string must accept {n}.
check(
    "8.g EN preview-count is a format string with {n}",
    "{n}" in _EN.get("cockpit_review_hf_preview_count", ""),
)
check(
    "8.h ZH preview-count is a format string with {n}",
    "{n}" in _ZH.get("cockpit_review_hf_preview_count", ""),
)


# ---------------------------------------------------------------------------
# Section 9 — Phase 5Q session contracts build with safety invariants
# ---------------------------------------------------------------------------

try:
    from lib.reliability.phase5_human_feedback_ui import (  # noqa: E402
        HUMAN_FEEDBACK_ACTIONS,
        HumanFeedbackActionView,
        HumanFeedbackFormState,
        HumanFeedbackReviewTarget,
        HumanFeedbackSafetyBanner,
        HumanFeedbackSessionRecord,
        HumanFeedbackUIState,
        HumanFeedbackValidationSummary,
        build_default_human_feedback_ui_state,
        build_human_feedback_action_views,
        build_human_feedback_session_record,
        build_human_feedback_ui_state,
    )

    # Action vocabulary — all nine required actions, in canonical order.
    check(
        "9.1 HUMAN_FEEDBACK_ACTIONS has all nine required actions",
        list(HUMAN_FEEDBACK_ACTIONS) == _REQUIRED_ACTIONS,
        detail=str(list(HUMAN_FEEDBACK_ACTIONS)),
    )
    _actions = build_human_feedback_action_views()
    check("9.2 nine action views built", len(_actions) == 9)
    check(
        "9.3 every action view is non-executable",
        all(a.is_executable is False for a in _actions),
    )
    check(
        "9.4 action translation keys are cockpit_review_action_*",
        all(a.translation_key == f"cockpit_review_action_{a.action}" for a in _actions),
    )

    _state = build_default_human_feedback_ui_state()
    check("9.5 default UI state builds", isinstance(_state, HumanFeedbackUIState))
    check("9.6 UI state is session-only", _state.is_session_only is True)
    check("9.7 UI state is not persisted", _state.is_persisted is False)

    _banner = _state.safety_banner
    check("9.8 banner session-only", _banner.is_session_only is True)
    check("9.9 banner not persisted", _banner.is_persisted is False)
    check("9.10 banner non-executable", _banner.is_non_executable is True)
    check("9.11 banner requires human review", _banner.requires_human_review is True)
    check("9.12 banner no broker/order", _banner.no_broker_or_order is True)
    check("9.13 banner no llm/external api", _banner.no_llm_or_external_api is True)

    # Review targets cover the required kinds + carry visible connections.
    _targets = _state.review_targets
    check("9.14 UI state has review targets", len(_targets) >= 1)
    _kinds = {tg.target_kind for tg in _targets}
    for required_kind in (
        "opportunity_candidate",
        "decision_workspace",
        "trade_allocation_plan",
        "option_overlay",
    ):
        check(f"9.15 review targets include kind {required_kind!r}", required_kind in _kinds)
    check("9.16 some target carries a horizon", any(tg.horizon for tg in _targets))
    check(
        "9.17 some target carries decision-workspace consensus/conflicts",
        any(
            tg.target_kind == "decision_workspace"
            and (tg.consensus_level is not None or tg.conflict_count is not None)
            for tg in _targets
        ),
    )
    check(
        "9.18 some target carries an option-overlay state",
        any(tg.target_kind == "option_overlay" and tg.option_state for tg in _targets),
    )
    check(
        "9.19 some target carries a trade-plan review state",
        any(
            tg.target_kind == "trade_allocation_plan"
            and tg.trade_review_needed is not None
            for tg in _targets
        ),
    )

    # Validation summary invariants.
    _vs = _state.validation_summary
    check("9.20 validation summary present", _vs is not None)
    check("9.21 vs session-only", _vs.is_session_only is True)
    check("9.22 vs not persisted", _vs.is_persisted is False)
    check("9.23 vs no execution authorized", _vs.no_execution_authorized is True)
    check("9.24 vs no broker/order", _vs.no_broker_or_order is True)
    check("9.25 vs no order-ticket fields", _vs.no_order_ticket_fields is True)
    check("9.26 vs approved_for_execution_absent", _vs.approved_for_execution_absent is True)
    check("9.27 vs has no issues", _vs.issues == [], detail=str(_vs.issues))
    check("9.28 vs action_count == 9", _vs.action_count == 9)

    # Session record built from a target — session-only / non-executable.
    _rec = build_human_feedback_session_record(
        target=_targets[0], action="accept_for_watchlist", note="demo review note"
    )
    check("9.29 session record session-only", _rec.is_session_only is True)
    check("9.30 session record not persisted", _rec.is_persisted is False)
    check("9.31 session record non-executable", _rec.is_executable is False)
    check("9.32 session record requires human review", _rec.requires_human_review is True)
    check("9.33 session record deterministic id", _rec.record_id.startswith("hfu_"))

    # approved_for_execution absent on EVERY Phase 5Q model (never declared).
    _PHASE_5Q_MODELS = [
        HumanFeedbackSafetyBanner,
        HumanFeedbackActionView,
        HumanFeedbackReviewTarget,
        HumanFeedbackFormState,
        HumanFeedbackSessionRecord,
        HumanFeedbackValidationSummary,
        HumanFeedbackUIState,
    ]
    for model_cls in _PHASE_5Q_MODELS:
        check(
            f"9.34 {model_cls.__name__} does not declare approved_for_execution",
            "approved_for_execution" not in model_cls.model_fields,
        )
        # No order-ticket-like field on any model.
        _bad_fields = {
            "order_type",
            "order_ticket",
            "broker_route",
            "broker_payload",
            "account_id",
            "time_in_force",
            "execution_id",
            "quantity_to_execute",
            "fill_price",
        }
        check(
            f"9.35 {model_cls.__name__} declares no order-ticket field",
            not (_bad_fields & set(model_cls.model_fields.keys())),
        )

    # Persisted/executable session records must be rejected at construction.
    _rejected_persist = False
    try:
        HumanFeedbackSessionRecord(
            record_id="x", target=_targets[0], action="reject", is_persisted=True
        )
    except Exception:  # noqa: BLE001
        _rejected_persist = True
    check("9.36 persisted session record rejected", _rejected_persist)

    _rejected_exec = False
    try:
        HumanFeedbackSessionRecord(
            record_id="x", target=_targets[0], action="reject", is_executable=True
        )
    except Exception:  # noqa: BLE001
        _rejected_exec = True
    check("9.37 executable session record rejected", _rejected_exec)

    # Empty-input UI state is safe.
    _empty_state = build_human_feedback_ui_state()
    check("9.38 empty UI state has zero targets", len(_empty_state.review_targets) == 0)
    check(
        "9.39 empty UI state still has nine actions + safe banner",
        len(_empty_state.available_actions) == 9
        and _empty_state.safety_banner.is_session_only is True,
    )
except Exception as e:  # noqa: BLE001
    FAIL += 1
    _failures.append(f"FAIL  9.x Phase 5Q contract import/build failed: {e}")


# ---------------------------------------------------------------------------
# Section 10 — Shared upstream fixtures (5K/5M/5G) still build (regression)
# ---------------------------------------------------------------------------

try:
    from lib.reliability.phase5_agent_debate import (  # noqa: E402
        build_default_agent_debate_workspace,
    )
    from lib.reliability.phase5_opportunity_queue import (  # noqa: E402
        build_default_opportunity_queue_view,
    )

    _ws = build_default_agent_debate_workspace()
    _q = build_default_opportunity_queue_view()
    check("10.1 Phase 5M workspace still builds", len(_ws.workspace_views) >= 1)
    check("10.2 Phase 5K queue still builds", _q is not None)
    check(
        "10.3 Phase 5M workspace views remain non-executable",
        all(v.is_executable_decision is False for v in _ws.workspace_views),
    )
except Exception as e:  # noqa: BLE001
    FAIL += 1
    _failures.append(f"FAIL  10.x upstream fixture regression failed: {e}")


# ---------------------------------------------------------------------------
# Section 11 — Phase 5Q design doc exists with required sections
# ---------------------------------------------------------------------------

check("11.1 Phase 5Q design doc exists", os.path.isfile(PHASE_5Q_DOC))
if os.path.isfile(PHASE_5Q_DOC):
    _doc = _read_text(PHASE_5Q_DOC)
    for heading in (
        "Purpose",
        "Phase 4M-F",
        "Phase 5I",
        "Phase 5M",
        "Phase 5N",
        "session-only",
        "Supported feedback actions",
        "Review target",
        "Non-persistence",
        "Non-execution",
        "Bilingual",
        "Non-goals",
        "Guardrails",
        "Acceptance criteria",
        "Phase 5R",
    ):
        check(f"11.x Phase 5Q doc mentions: {heading!r}", heading in _doc)


# ---------------------------------------------------------------------------
# Section 12 — AppTest render in EN and ZH (+ degraded scenario)
# ---------------------------------------------------------------------------

_APPTEST_AVAILABLE = False
try:
    from streamlit.testing.v1 import AppTest  # type: ignore
    _APPTEST_AVAILABLE = True
except Exception as _at_imp_exc:  # noqa: BLE001
    _failures.append(f"FAIL  12.0 AppTest import failed: {_at_imp_exc}")


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

    try:
        for lang, tag in (("en", "EN"), ("zh", "ZH")):
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
                f"12.{tag}.1 AppTest {tag} render completed without exception",
                ran_ok,
                detail=exc_info or "",
            )
            if not ran_ok or at is None:
                continue

            rendered = _collect_rendered_text(at)
            lang_map = _UI_TRANSLATIONS.get(lang, {})
            # Phase 5Q feedback safety headline + form header render.
            for key in (
                "cockpit_review_hf_safety_headline",
                "cockpit_review_hf_form_header",
                "cockpit_review_hf_preview_empty",
            ):
                expected = lang_map.get(key, "\x00")
                check(
                    f"12.{tag}.2 {tag} render contains {key!r}",
                    expected in rendered,
                )
            # Feedback / Review tab label renders.
            check(
                f"12.{tag}.3 {tag} render contains Feedback/Review tab label",
                lang_map.get("cockpit_tab_review", "\x00") in rendered,
            )
            # No positive approved_for_execution authorization in rendered text.
            for form in _POSITIVE_AUTH_FORMS:
                check(
                    f"12.{tag}.4 {tag} render has no positive auth: {form!r}",
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
            "12.DEGRADED.1 degraded scenario renders without exception",
            ran_ok2,
            detail=exc_info2 or "",
        )
    finally:
        _ui_utils_mod.render_sidebar = _orig_render_sidebar  # type: ignore[assignment]
        _ui_utils_mod.apply_theme = _orig_apply_theme  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
print("============================================================")
print(f"Phase 5Q Human Feedback UI Test Results: {PASS} passed, {FAIL} failed")
print("============================================================")
if _failures:
    for f in _failures:
        print(f)

sys.exit(0 if FAIL == 0 else 1)
