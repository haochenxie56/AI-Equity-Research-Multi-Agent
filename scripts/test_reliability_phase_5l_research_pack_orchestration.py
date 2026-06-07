#!/usr/bin/env python3
"""
scripts/test_reliability_phase_5l_research_pack_orchestration.py

Phase 5L — Auto Research Pack Orchestration Boundary — test suite.

Phase 5L converts Phase 5K opportunity-queue candidates into structured
research-pack requests and research-pack bundles. It is an orchestration
boundary only: it does NOT run company research, financial analysis,
price-volume analysis, news fetches, catalyst/earnings, macro/theme/sector/
scanner analysis, LLM calls, or external APIs. Module requests are descriptive
placeholders; module result refs are placeholders (no fabricated analysis).

This test verifies:
  - The default research pack bundle builds from the Phase 5K default queue.
  - Short-term candidate module selection (technical/news/catalyst/risk/evidence).
  - Mid-term candidate module selection (company/financial/technical/catalyst/
    risk/evidence).
  - Long-term candidate module selection (macro/theme/company/financial/risk/
    evidence).
  - Research_more candidate maps evidence gaps to required modules.
  - Wait_for_pullback / too_extended requires price_volume_analysis + risk_review.
  - No_trade / avoid does not generate an executable research-to-trade pack.
  - Empty queue returns a safe empty pack.
  - Degraded pack returns warnings (missing module refs handled safely).
  - Module requests are descriptive and do not call live modules.
  - No forbidden imports (app.py / pages/* / Streamlit / lib/workflow_state.py /
    lib/llm_orchestrator.py / external APIs / broker / order modules).
  - No approved_for_execution=True is positively authorized; no order-ticket
    fields are introduced.
  - Serialization is deterministic.
  - Package exports are wired; documentation is present.

It does NOT spin up Streamlit and does NOT call any external API or LLM.

Usage:
    python3 scripts/test_reliability_phase_5l_research_pack_orchestration.py
"""

from __future__ import annotations

import json
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


def _raises(fn) -> bool:
    try:
        fn()
        return False
    except Exception:
        return True


# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

from lib.reliability.phase5_research_pack import (  # noqa: E402
    AutoResearchPackOrchestrationBoundary,
    RESEARCH_PACK_SOURCE_MODULES,
    RESEARCH_PACK_STATUSES,
    ResearchModuleRequest,
    ResearchModuleResultRef,
    ResearchPackBundle,
    ResearchPackEvidenceGap,
    ResearchPackHorizonCoverage,
    ResearchPackPlan,
    ResearchPackRequest,
    ResearchPackSafetyBanner,
    ResearchPackValidationSummary,
    ResearchPackWarning,
    build_auto_research_pack_orchestration_boundary,
    build_default_research_pack_bundle,
    build_degraded_research_pack_bundle,
    build_empty_research_pack_bundle,
    build_research_module_requests,
    build_research_pack_bundle_from_fixture,
    build_research_pack_evidence_gaps,
    build_research_pack_plan,
    build_research_pack_request_from_opportunity_candidate,
    determine_research_pack_status,
    make_research_pack_request_id,
)
from lib.reliability.phase5_opportunity_queue import (  # noqa: E402
    build_long_term_candidate_view,
    build_mid_term_candidate_view,
    build_short_term_candidate_view,
)
from lib.reliability.phase5_theme_intelligence import (  # noqa: E402
    FundamentalConfirmationSignal,
    ThemeCandidateTicker,
    ThemeEvidenceSummary,
    ThemeHeatSignal,
    ThemeRecord,
    build_theme_heat_score,
)

import lib.reliability as reliability_pkg  # noqa: E402

MODULE_PATH = os.path.join(
    _REPO_ROOT, "lib", "reliability", "phase5_research_pack.py"
)
DOC_PATH = os.path.join(
    _REPO_ROOT,
    "docs",
    "reliability_phase_5l_auto_research_pack_orchestration_boundary.md",
)


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


# Helper builders for synthetic candidates / themes (clean horizon decisions).
def _theme(candidate, *, lifecycle="accelerating", confirm="confirming",
           strength="strong", price="strong", complete_heat=True) -> ThemeRecord:
    fund = (
        [FundamentalConfirmationSignal(confirmation_type="revenue",
                                       confirmation_direction=confirm,
                                       strength=strength)]
        if confirm != "none"
        else []
    )
    heat = build_theme_heat_score(
        price_momentum_component=0.9, volume_component=0.85,
        breadth_component=0.7, narrative_component=0.9,
        fundamental_confirmation_component=0.8, freshness_component=0.85,
    )
    return ThemeRecord(
        theme_id="theme_syn", name="Synthetic", lifecycle_stage=lifecycle,
        heat_score=heat,
        source_signals=[ThemeHeatSignal(signal_type="price_momentum",
                                        source_type="scanner", strength=price)],
        fundamental_confirmation_signals=fund,
        candidate_tickers=[candidate],
    )


def _cand(ticker, *, role="leader", crowding="moderate", coverage="complete",
          hc=0.9, refs=("e1",)) -> ThemeCandidateTicker:
    return ThemeCandidateTicker(
        ticker=ticker, theme_id="theme_syn", role=role, heat_contribution=hc,
        crowding_level=crowding,
        evidence=ThemeEvidenceSummary(coverage_status=coverage,
                                      evidence_refs=list(refs)),
    )


# ---------------------------------------------------------------------------
# Section 1 — Default research pack bundle builds from default queue
# ---------------------------------------------------------------------------

b = build_default_research_pack_bundle()
check("1.1 default boundary is AutoResearchPackOrchestrationBoundary",
      isinstance(b, AutoResearchPackOrchestrationBoundary))
check("1.2 default boundary has an id", bool(b.boundary_id))
check("1.3 default boundary references source queue id", bool(b.source_queue_id))
check("1.4 default boundary references source theme snapshot id",
      bool(b.source_theme_snapshot_id))
check("1.5 default boundary has pack requests", len(b.pack_requests) >= 1)
check("1.6 requests and bundles are 1:1",
      len(b.pack_requests) == len(b.pack_bundles))
check("1.7 default boundary has a validation summary",
      isinstance(b.validation_summary, ResearchPackValidationSummary))
check("1.8 default boundary is not safe-empty",
      b.validation_summary is not None and not b.validation_summary.is_safe_empty)
check("1.9 default boundary status is planned (nothing executed)",
      b.status == "planned")
check("1.10 schema_version set", b.schema_version == "phase5_research_pack_v1")
check("1.11 every bundle is a ResearchPackBundle",
      all(isinstance(x, ResearchPackBundle) for x in b.pack_bundles))
check("1.12 every request is a ResearchPackRequest",
      all(isinstance(x, ResearchPackRequest) for x in b.pack_requests))
# Deterministic across builds.
d1 = build_default_research_pack_bundle().model_dump(mode="json")
d2 = build_default_research_pack_bundle().model_dump(mode="json")
check("1.13 two default builds dump-equal", d1 == d2)
check("1.14 eleven canonical source modules", len(RESEARCH_PACK_SOURCE_MODULES) == 11)
check("1.15 make_research_pack_request_id deterministic",
      make_research_pack_request_id("AAA", "theme_x", "short_term", "trade_now")
      == make_research_pack_request_id("AAA", "theme_x", "short_term", "trade_now"))


def _by(boundary, ticker, horizon):
    for r in boundary.pack_requests:
        if r.ticker == ticker and r.horizon == horizon:
            return r
    return None


# ---------------------------------------------------------------------------
# Section 2 — Short-term candidate module selection
# ---------------------------------------------------------------------------

# A clean short-term momentum candidate (low crowding, complete evidence) ->
# trade_now, exercising the base short-term required module set.
c_short = _cand("STX", crowding="low", coverage="complete", hc=0.9)
v_short = build_short_term_candidate_view(c_short, _theme(c_short))
req_short = build_research_pack_request_from_opportunity_candidate(v_short)
short_required = {m.module for m in req_short.required_modules}
check("2.1 short-term decision is short-native (trade_now expected)",
      str(v_short.decision_label) == "trade_now", detail=str(v_short.decision_label))
check("2.2 short-term requires price_volume_analysis",
      "price_volume_analysis" in short_required)
check("2.3 short-term requires news_sentiment", "news_sentiment" in short_required)
check("2.4 short-term requires catalyst_earnings",
      "catalyst_earnings" in short_required)
check("2.5 short-term requires risk_review", "risk_review" in short_required)
check("2.6 short-term requires evidence_validation",
      "evidence_validation" in short_required)
check("2.7 short-term horizon == short_term", req_short.horizon == "short_term")
check("2.8 short-term carries short_term_timing trigger",
      "short_term_timing" in req_short.trigger_reasons)


# ---------------------------------------------------------------------------
# Section 3 — Mid-term candidate module selection
# ---------------------------------------------------------------------------

c_mid = _cand("MDX", crowding="moderate", coverage="complete", hc=0.7)
v_mid = build_mid_term_candidate_view(c_mid, _theme(c_mid))
req_mid = build_research_pack_request_from_opportunity_candidate(v_mid)
mid_required = {m.module for m in req_mid.required_modules}
check("3.1 mid-term decision is mid-native (not no_trade)",
      str(v_mid.decision_label) != "no_trade", detail=str(v_mid.decision_label))
for mod in ("company_research", "financial_analysis", "price_volume_analysis",
            "catalyst_earnings", "risk_review", "evidence_validation"):
    check(f"3.2 mid-term requires {mod}", mod in mid_required)
check("3.3 mid-term horizon == mid_term", req_mid.horizon == "mid_term")
check("3.4 mid-term carries mid_term_position_building trigger",
      "mid_term_position_building" in req_mid.trigger_reasons)


# ---------------------------------------------------------------------------
# Section 4 — Long-term candidate module selection
# ---------------------------------------------------------------------------

c_long = _cand("LGX", crowding="low", coverage="complete", hc=0.6)
v_long = build_long_term_candidate_view(c_long, _theme(c_long, lifecycle="consensus"))
req_long = build_research_pack_request_from_opportunity_candidate(v_long)
long_required = {m.module for m in req_long.required_modules}
check("4.1 long-term decision is long-native (not no_trade)",
      str(v_long.decision_label) != "no_trade", detail=str(v_long.decision_label))
for mod in ("macro_context", "theme_context", "company_research",
            "financial_analysis", "risk_review", "evidence_validation"):
    check(f"4.2 long-term requires {mod}", mod in long_required)
check("4.3 long-term horizon == long_term", req_long.horizon == "long_term")
check("4.4 long-term carries long_term_durability trigger",
      "long_term_durability" in req_long.trigger_reasons)
check("4.5 long-term required modules include macro_context with macro trigger",
      any(m.module == "macro_context" and "macro_validation" in m.trigger_reasons
          for m in req_long.required_modules))


# ---------------------------------------------------------------------------
# Section 5 — Research_more candidate maps evidence gaps to required modules
# ---------------------------------------------------------------------------

# FIXSPEC short-term in the default queue is research_more with no/partial
# evidence -> gap-closing modules must be promoted into the required set.
fixspec_short = _by(b, "FIXSPEC", "short_term")
check("5.1 FIXSPEC short request present", fixspec_short is not None)
check("5.2 FIXSPEC short decision is research_more",
      fixspec_short is not None and str(fixspec_short.decision_label) == "research_more")
check("5.3 FIXSPEC short has evidence gaps",
      fixspec_short is not None and len(fixspec_short.evidence_gaps) >= 1)
if fixspec_short is not None:
    fs_required = {m.module for m in fixspec_short.required_modules}
    # Every gap's addressing modules are promoted into required.
    all_gap_modules = set()
    for g in fixspec_short.evidence_gaps:
        all_gap_modules.update(g.addressed_by_modules)
    check("5.4 all gap-addressing modules are in required",
          all_gap_modules.issubset(fs_required),
          detail=str(sorted(all_gap_modules - fs_required)))
    # company_research + financial_analysis are NOT base short-required; they
    # appear only because gaps promoted them.
    check("5.5 gap-driven company_research promoted to required (beyond base)",
          "company_research" in fs_required)
    check("5.6 gap-driven financial_analysis promoted to required (beyond base)",
          "financial_analysis" in fs_required)
    check("5.7 at least one required module addresses a gap",
          any(m.addresses_gaps for m in fixspec_short.required_modules))
    check("5.8 a gap-addressing module carries evidence_gap trigger + high priority",
          any(m.addresses_gaps and "evidence_gap" in m.trigger_reasons
              and m.priority == "high" for m in fixspec_short.required_modules))

# Direct builder check on evidence gaps from a partial-evidence candidate.
c_gap = _cand("GAP", crowding="moderate", coverage="partial", hc=0.5)
v_gap = build_mid_term_candidate_view(c_gap, _theme(c_gap, confirm="mixed",
                                                     strength="moderate"))
gaps = build_research_pack_evidence_gaps(v_gap)
check("5.9 build_research_pack_evidence_gaps returns gaps for partial evidence",
      len(gaps) >= 1 and all(isinstance(g, ResearchPackEvidenceGap) for g in gaps))
check("5.10 incomplete_evidence gap detected for partial coverage",
      any(g.gap_type == "incomplete_evidence" for g in gaps))


# ---------------------------------------------------------------------------
# Section 6 — Wait_for_pullback / too_extended require pv + risk_review
# ---------------------------------------------------------------------------

# NVDA short in default is wait_for_pullback (elevated crowding downgrade).
nvda_short = _by(b, "NVDA", "short_term")
check("6.1 NVDA short request present", nvda_short is not None)
check("6.2 NVDA short decision is wait_for_pullback",
      nvda_short is not None and str(nvda_short.decision_label) == "wait_for_pullback")
if nvda_short is not None:
    nvda_req = {m.module for m in nvda_short.required_modules}
    check("6.3 wait_for_pullback requires price_volume_analysis",
          "price_volume_analysis" in nvda_req)
    check("6.4 wait_for_pullback requires risk_review", "risk_review" in nvda_req)
    check("6.5 wait_for_pullback carries entry_quality_check trigger",
          "entry_quality_check" in nvda_short.trigger_reasons)
    check("6.6 wait_for_pullback carries crowding_risk_check trigger",
          "crowding_risk_check" in nvda_short.trigger_reasons)

# too_extended (high crowding + red-hot heat).
c_te = _cand("TE", crowding="high", coverage="complete")
v_te = build_short_term_candidate_view(c_te, _theme(c_te))
req_te = build_research_pack_request_from_opportunity_candidate(v_te)
te_required = {m.module for m in req_te.required_modules}
check("6.7 synthetic candidate decision is too_extended",
      str(v_te.decision_label) == "too_extended", detail=str(v_te.decision_label))
check("6.8 too_extended requires price_volume_analysis",
      "price_volume_analysis" in te_required)
check("6.9 too_extended requires risk_review", "risk_review" in te_required)
check("6.10 too_extended is not review-only", req_te.is_review_only is False)


# ---------------------------------------------------------------------------
# Section 7 — No_trade / avoid does not generate an executable pack
# ---------------------------------------------------------------------------

# disconfirming fundamentals -> no_trade.
c_nt = _cand("NT", crowding="moderate", coverage="complete")
v_nt = build_short_term_candidate_view(
    c_nt, _theme(c_nt, lifecycle="fading", confirm="disconfirming"))
check("7.1 disconfirming candidate decision is no_trade",
      str(v_nt.decision_label) == "no_trade", detail=str(v_nt.decision_label))
req_nt = build_research_pack_request_from_opportunity_candidate(v_nt)
nt_required = {m.module for m in req_nt.required_modules}
check("7.2 no_trade request is review-only", req_nt.is_review_only is True)
check("7.3 no_trade required modules are exactly risk_review + evidence_validation",
      nt_required == {"risk_review", "evidence_validation"}, detail=str(nt_required))
check("7.4 no_trade has no optional (trade-enabling) modules",
      len(req_nt.optional_modules) == 0)
check("7.5 no_trade does NOT require company/financial/price_volume modules",
      not ({"company_research", "financial_analysis", "price_volume_analysis"}
           & nt_required))
check("7.6 no_trade carries no_trade_review_only trigger",
      "no_trade_review_only" in req_nt.trigger_reasons)
nt_bundle = build_research_pack_bundle_from_fixture(req_nt)
check("7.7 no_trade bundle still has no executable order field in dump",
      '"order_type"' not in json.dumps(nt_bundle.model_dump(mode="json")).lower())
# extreme crowding -> avoid_too_crowded is also review-only.
c_ext = _cand("EX", crowding="extreme", coverage="complete")
v_ext = build_short_term_candidate_view(c_ext, _theme(c_ext))
req_ext = build_research_pack_request_from_opportunity_candidate(v_ext)
check("7.8 avoid_too_crowded is review-only",
      str(v_ext.decision_label) == "avoid_too_crowded" and req_ext.is_review_only)


# ---------------------------------------------------------------------------
# Section 8 — Empty queue returns a safe empty pack
# ---------------------------------------------------------------------------

emp = build_empty_research_pack_bundle()
check("8.1 empty boundary builds",
      isinstance(emp, AutoResearchPackOrchestrationBoundary))
check("8.2 empty boundary has no requests / bundles",
      len(emp.pack_requests) == 0 and len(emp.pack_bundles) == 0)
check("8.3 empty boundary is safe-empty",
      emp.validation_summary is not None and emp.validation_summary.is_safe_empty)
check("8.4 empty boundary status is skipped", emp.status == "skipped")
check("8.5 empty boundary carries safety + empty warnings", len(emp.warnings) >= 1)
check("8.6 empty boundary carries an empty_queue warning",
      any(w.warning_type == "empty_queue" for w in emp.warnings))


# ---------------------------------------------------------------------------
# Section 9 — Degraded pack returns warnings (missing module refs safe)
# ---------------------------------------------------------------------------

deg = build_degraded_research_pack_bundle()
check("9.1 degraded boundary builds",
      isinstance(deg, AutoResearchPackOrchestrationBoundary))
check("9.2 degraded boundary has bundles", len(deg.pack_bundles) >= 1)
check("9.3 degraded boundary carries warnings", len(deg.warnings) >= 1)
check("9.4 degraded boundary status is blocked", deg.status == "blocked")
deg_bundle = deg.pack_bundles[0]
check("9.5 degraded bundle module results are blocked placeholders",
      all(r.status == "blocked" for r in deg_bundle.module_results)
      and len(deg_bundle.module_results) >= 1)
check("9.6 degraded module result refs are None (no fabricated analysis)",
      all(r.result_ref is None for r in deg_bundle.module_results))
check("9.7 degraded module results carry no evidence refs (not fabricated)",
      all(r.evidence_refs == [] for r in deg_bundle.module_results))
check("9.8 degraded bundle carries degraded_upstream / missing_module_ref warnings",
      any(w.warning_type == "degraded_upstream" for w in deg_bundle.warnings)
      and any(w.warning_type == "missing_module_ref" for w in deg_bundle.warnings))


# ---------------------------------------------------------------------------
# Section 10 — Module requests are descriptive, not runtime calls
# ---------------------------------------------------------------------------

all_module_reqs: list[ResearchModuleRequest] = []
all_module_results: list[ResearchModuleResultRef] = []
for bundle in b.pack_bundles:
    all_module_reqs.extend(bundle.request.required_modules)
    all_module_reqs.extend(bundle.request.optional_modules)
    all_module_results.extend(bundle.module_results)
check("10.1 every module request is_runtime_call is False",
      all(m.is_runtime_call is False for m in all_module_reqs))
check("10.2 every module request has a conceptual source description",
      all(bool(m.conceptual_source) for m in all_module_reqs))
check("10.3 every module result ref is a placeholder",
      all(r.is_placeholder is True for r in all_module_results))
check("10.4 every module result ref is_runtime_call is False",
      all(r.is_runtime_call is False for r in all_module_results))
check("10.5 module requests select only known source modules",
      all(m.module in RESEARCH_PACK_SOURCE_MODULES for m in all_module_reqs))
check("10.6 ResearchModuleRequest rejects is_runtime_call=True",
      _raises(lambda: ResearchModuleRequest(module="risk_review",
                                            is_runtime_call=True)))
check("10.7 ResearchModuleResultRef rejects is_placeholder=False",
      _raises(lambda: ResearchModuleResultRef(module="risk_review",
                                              is_placeholder=False)))
check("10.8 determine_research_pack_status of empty list is skipped",
      determine_research_pack_status([]) == "skipped")
check("10.9 every status is a known ResearchPackStatus",
      all(bundle.status in RESEARCH_PACK_STATUSES for bundle in b.pack_bundles))


# ---------------------------------------------------------------------------
# Section 11 — No forbidden imports / determinism in module source
# ---------------------------------------------------------------------------

module_src = _read_text(MODULE_PATH)
FORBIDDEN_IMPORT_SUBSTRINGS = [
    "import streamlit", "import anthropic", "import openai", "from app",
    "import app\n", "lib.workflow_state", "lib.llm_orchestrator",
    "lib.data_fetcher", "from pages", "import requests", "import httpx",
    "import urllib", "yfinance", "polygon", "finnhub",
]
for sub in FORBIDDEN_IMPORT_SUBSTRINGS:
    check(f"11.1 module does not reference {sub!r}", sub not in module_src, detail=sub)
check("11.2 module does not read research/.workflow_state.json",
      ".workflow_state.json" not in module_src)
check("11.3 module does not open files for persistence",
      "open(" not in module_src and "Path(" not in module_src)
check("11.4 module does not use wall-clock time / randomness",
      "datetime.now" not in module_src and "time.time(" not in module_src
      and "import random" not in module_src)


# ---------------------------------------------------------------------------
# Section 12 — No approved_for_execution / order-ticket / buy-sell fields
# ---------------------------------------------------------------------------

ALL_MODELS = [
    ResearchPackSafetyBanner, ResearchPackWarning, ResearchPackEvidenceGap,
    ResearchModuleRequest, ResearchModuleResultRef, ResearchPackHorizonCoverage,
    ResearchPackRequest, ResearchPackPlan, ResearchPackValidationSummary,
    ResearchPackBundle, AutoResearchPackOrchestrationBoundary,
]
FORBIDDEN_FIELDS = {
    "approved_for_execution", "order_type", "order_id", "time_in_force",
    "broker_route", "broker_payload", "account_id", "execution_id",
    "quantity_to_execute", "limit_price", "stop_price", "fill_price",
    "buy", "sell", "buy_now", "sell_now",
}
for m in ALL_MODELS:
    bad = set(m.model_fields.keys()) & FORBIDDEN_FIELDS
    check(f"12.1 {m.__name__} declares no forbidden field", not bad, detail=str(bad))

check("12.2 boundary rejects approved_for_execution kwarg (extra=forbid)",
      _raises(lambda: AutoResearchPackOrchestrationBoundary(
          boundary_id="x", approved_for_execution=True)))
check("12.3 request rejects approved_for_execution kwarg (extra=forbid)",
      _raises(lambda: ResearchPackRequest(
          pack_request_id="x", ticker="AAA", theme_id="t", horizon="short_term",
          decision_label="trade_now", approved_for_execution=True)))

dump_str = json.dumps(d1).lower()
check("12.4 serialized default boundary does not authorize approved_for_execution",
      '"approved_for_execution": true' not in dump_str
      and '"approved_for_execution":true' not in dump_str
      and '"approved_for_execution":' not in dump_str)
check("12.5 serialized default boundary has no order-ticket fields",
      '"order_type"' not in dump_str and '"broker_route"' not in dump_str
      and '"account_id"' not in dump_str and '"time_in_force"' not in dump_str)
check("12.6 validation summary asserts execution-safety invariants",
      b.validation_summary is not None
      and b.validation_summary.no_executable_order_fields
      and b.validation_summary.approved_for_execution_absent
      and b.validation_summary.no_live_module_calls
      and b.validation_summary.no_final_recommendation
      and b.validation_summary.all_modules_descriptive)
check("12.7 safety banner asserts no_execution_authorized + no_orders",
      b.safety_banner.no_execution_authorized is True
      and b.safety_banner.no_orders is True
      and b.safety_banner.no_final_recommendation is True)


# ---------------------------------------------------------------------------
# Section 13 — Serialization deterministic + round-trip
# ---------------------------------------------------------------------------

j1 = json.dumps(d1, sort_keys=True)
j2 = json.dumps(build_default_research_pack_bundle().model_dump(mode="json"),
                sort_keys=True)
check("13.1 JSON serialization deterministic across builds", j1 == j2)
rt = AutoResearchPackOrchestrationBoundary.model_validate(d1)
check("13.2 round-trip re-validates",
      isinstance(rt, AutoResearchPackOrchestrationBoundary))
check("13.3 round-trip dump-equal", rt.model_dump(mode="json") == d1)
# Plan derivation deterministic.
plan = build_research_pack_plan(req_short)
check("13.4 plan module_requests == required + optional",
      isinstance(plan, ResearchPackPlan)
      and len(plan.module_requests)
      == len(req_short.required_modules) + len(req_short.optional_modules))
check("13.5 plan horizon coverage matches request horizon",
      plan.horizon_coverage.horizon == req_short.horizon)
check("13.6 build_research_module_requests deterministic",
      [m.module for m in build_research_module_requests(
          horizon="short_term", decision_label="trade_now", evidence_gaps=[],
          is_review_only=False)[0]]
      == [m.module for m in build_research_module_requests(
          horizon="short_term", decision_label="trade_now", evidence_gaps=[],
          is_review_only=False)[0]])


# ---------------------------------------------------------------------------
# Section 14 — Package exports wired
# ---------------------------------------------------------------------------

EXPECTED_EXPORTS = [
    "AutoResearchPackOrchestrationBoundary",
    "ResearchPackRequest",
    "ResearchPackPlan",
    "ResearchPackBundle",
    "ResearchModuleRequest",
    "ResearchModuleResultRef",
    "ResearchModuleStatus",
    "ResearchPackStatus",
    "ResearchPackPriority",
    "ResearchPackTriggerReason",
    "ResearchPackEvidenceGap",
    "ResearchPackSourceModule",
    "ResearchPackHorizonCoverage",
    "ResearchPackValidationSummary",
    "ResearchPackSafetyBanner",
    "ResearchPackWarning",
    "RESEARCH_PACK_SOURCE_MODULES",
    "build_auto_research_pack_orchestration_boundary",
    "build_research_pack_request_from_opportunity_candidate",
    "build_research_pack_plan",
    "build_research_module_requests",
    "build_research_pack_bundle_from_fixture",
    "build_research_pack_validation_summary",
    "build_research_pack_evidence_gaps",
    "build_default_research_pack_bundle",
    "build_degraded_research_pack_bundle",
    "build_empty_research_pack_bundle",
]
for name in EXPECTED_EXPORTS:
    check(f"14.1 lib.reliability exports {name!r}", hasattr(reliability_pkg, name))
    check(f"14.2 {name!r} in lib.reliability.__all__", name in reliability_pkg.__all__)


# ---------------------------------------------------------------------------
# Section 15 — Documentation present with required sections
# ---------------------------------------------------------------------------

check("15.1 Phase 5L doc exists", os.path.isfile(DOC_PATH), detail=DOC_PATH)
doc = _read_text(DOC_PATH) if os.path.isfile(DOC_PATH) else ""
dlc = doc.lower()
REQUIRED_DOC_TOPICS = [
    "Purpose", "Phase 5I", "Phase 5J", "Phase 5K", "orchestration boundary",
    "source module", "macro_context", "theme_context", "company_research",
    "financial_analysis", "price_volume_analysis", "news_sentiment",
    "catalyst_earnings", "risk_review", "evidence_validation",
    "short", "mid", "long", "evidence gap", "research_more",
    "wait_for_pullback", "too_extended", "no_trade", "Fixture", "degraded",
    "Non-goals", "Guardrails", "Acceptance criteria", "Phase 5M",
]
for topic in REQUIRED_DOC_TOPICS:
    check(f"15.2 Phase 5L doc covers {topic!r}", topic in doc or topic.lower() in dlc)
check("15.3 doc keeps approved_for_execution False/absent",
      "approved_for_execution" in doc and ("false" in dlc or "absent" in dlc))
check("15.4 doc keeps Phase 5M as a future dependency, not started",
      "phase 5m" in dlc and ("future" in dlc or "not started" in dlc
                             or "later" in dlc or "next" in dlc))


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
print("=" * 70)
print("Phase 5L — Auto Research Pack Orchestration Boundary — test results")
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
    print("RESULT: PASS — Phase 5L auto research pack orchestration boundary verified.")
    sys.exit(0)
else:
    print("RESULT: FAIL — see failures above.")
    sys.exit(1)
