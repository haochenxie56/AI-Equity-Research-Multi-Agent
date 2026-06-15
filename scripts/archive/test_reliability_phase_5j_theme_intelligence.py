#!/usr/bin/env python3
"""
scripts/test_reliability_phase_5j_theme_intelligence.py

Phase 5J — Theme Intelligence / Market Heat Schema — test suite.

Phase 5J defines evidence-first schema / contracts for detecting market themes,
measuring market heat, decomposing industry chains, and representing theme
candidate tickers. It is the upstream input layer for the future Phase 5K
Horizon-aware Opportunity Queue ViewModel. Phase 5J is schema / contract /
helper / fixture only: it does not decide buy/sell, does not generate a final
opportunity queue, does not compute entry quality, and does not implement any
live data retrieval.

This test verifies:
  - The default theme intelligence snapshot builds (with validation summary).
  - The AI theme includes required subthemes / chain nodes.
  - The Space theme includes required subthemes / chain nodes.
  - The degraded / emerging theme handles partial evidence + unknown state.
  - A ThemeCandidateTicker can map to multiple subthemes / chain nodes.
  - ThemeHeatScore supports complete / partial / unknown status.
  - CrowdingSignal is separate from ThemeHeatScore.
  - A high heat score does NOT create buy/trade decision fields.
  - The empty snapshot is safe.
  - Serialization is deterministic.
  - No approved_for_execution=True is positively authorized.
  - No order-ticket-like fields are introduced.
  - No imports of app.py / pages/* / Streamlit / lib/workflow_state.py /
    lib/llm_orchestrator.py / external APIs / broker / order modules.
  - Phase 5I doc/state assertions pass.

It does NOT spin up Streamlit and does NOT call any external API or LLM.

Usage:
    python3 scripts/test_reliability_phase_5j_theme_intelligence.py
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


# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

from lib.reliability.phase5_theme_intelligence import (  # noqa: E402
    CrowdingSignal,
    EntryQualityScorePlaceholder,
    IndustryChainNode,
    SubthemeRecord,
    THEME_CANDIDATE_ROLES,
    ThemeCandidateTicker,
    ThemeHeatScore,
    ThemeIntelligenceSnapshot,
    ThemeIntelligenceValidationSummary,
    ThemeRecord,
    ThemeUniverseSnapshot,
    build_ai_theme_fixture,
    build_default_theme_intelligence_snapshot,
    build_degraded_theme_fixture,
    build_empty_theme_intelligence_snapshot,
    build_space_theme_fixture,
    build_theme_heat_score,
    derive_heat_score_status,
    make_theme_id,
    validate_theme_intelligence_snapshot,
)

# Re-import via package to confirm exports are wired.
import lib.reliability as reliability_pkg  # noqa: E402

MODULE_PATH = os.path.join(
    _REPO_ROOT, "lib", "reliability", "phase5_theme_intelligence.py"
)
TEST_PATH = os.path.abspath(__file__)
DOC_PATH = os.path.join(
    _REPO_ROOT,
    "docs",
    "reliability_phase_5j_theme_intelligence_market_heat_schema.md",
)
PHASE_5I_DOC = os.path.join(
    _REPO_ROOT,
    "docs",
    "reliability_phase_5i_investment_cockpit_product_logic_reconciliation.md",
)
PROJECT_STATE = os.path.join(_REPO_ROOT, "docs", "ai_dev_state", "PROJECT_STATE.md")
CURRENT_TASK = os.path.join(_REPO_ROOT, "docs", "ai_dev_state", "CURRENT_TASK.md")


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Section 1 — Default snapshot builds with validation summary
# ---------------------------------------------------------------------------

snap = build_default_theme_intelligence_snapshot()
check("1.1 default snapshot is a ThemeIntelligenceSnapshot",
      isinstance(snap, ThemeIntelligenceSnapshot))
check("1.2 default snapshot has a non-empty universe",
      len(snap.universe.themes) >= 3)
check("1.3 default snapshot has a validation summary",
      isinstance(snap.validation_summary, ThemeIntelligenceValidationSummary))
check("1.4 default snapshot validation summary not safe-empty",
      snap.validation_summary is not None and not snap.validation_summary.is_safe_empty)
check("1.5 default snapshot validation has no dangling chain-node refs",
      snap.validation_summary is not None
      and snap.validation_summary.dangling_chain_node_ref_count == 0,
      detail=str(snap.validation_summary.issues if snap.validation_summary else None))
check("1.6 default snapshot is marked a fixture", snap.is_fixture is True)

themes_by_name = {t.name: t for t in snap.universe.themes}


# ---------------------------------------------------------------------------
# Section 2 — AI theme: required subthemes / chain nodes
# ---------------------------------------------------------------------------

ai = build_ai_theme_fixture()
check("2.1 AI theme is a ThemeRecord", isinstance(ai, ThemeRecord))
check("2.2 AI theme id is deterministic", ai.theme_id == make_theme_id("Artificial Intelligence"))

ai_node_roles = {n.role_in_chain for n in ai.industry_chain_nodes}
REQUIRED_AI_NODES = {
    "compute",
    "memory",
    "optical",
    "dc_power",
    "cloud",
    "enterprise_sw",
    "applications",
    "edge_robotics",
}
for r in REQUIRED_AI_NODES:
    check(f"2.3 AI theme has chain node role {r!r}", r in ai_node_roles)

ai_node_names = " | ".join(n.name for n in ai.industry_chain_nodes).lower()
for token in ["compute", "memory", "hbm", "optical", "power", "cooling",
              "cloud", "platform", "enterprise software", "applications",
              "edge", "robotics"]:
    check(f"2.4 AI chain-node names mention {token!r}", token in ai_node_names)

check("2.5 AI theme has >= 3 subthemes", len(ai.subthemes) >= 3)
ai_sub_names = {s.name for s in ai.subthemes}
check("2.6 AI subtheme set includes a memory/HBM subtheme",
      any("memory" in s.lower() or "hbm" in s.lower() for s in ai_sub_names))
check("2.7 AI subtheme set includes a power/cooling subtheme",
      any("power" in s.lower() or "cooling" in s.lower() for s in ai_sub_names))
check("2.8 AI theme heat score is complete", ai.heat_score.score_status == "complete")
check("2.9 AI theme has multiple candidate roles",
      len({c.role for c in ai.candidate_tickers}) >= 4)
check("2.10 AI theme candidate roles include leader/laggard/supplier/speculative/platform",
      {"leader", "laggard", "supplier", "speculative", "platform"}.issubset(
          {c.role for c in ai.candidate_tickers}))


# ---------------------------------------------------------------------------
# Section 3 — Space theme: required subthemes / chain nodes
# ---------------------------------------------------------------------------

space = build_space_theme_fixture()
check("3.1 Space theme is a ThemeRecord", isinstance(space, ThemeRecord))
space_node_roles = {n.role_in_chain for n in space.industry_chain_nodes}
REQUIRED_SPACE_NODES = {
    "launch",
    "sat_mfg",
    "satcom",
    "eo",
    "defense_space",
    "components",
    "ground",
}
for r in REQUIRED_SPACE_NODES:
    check(f"3.2 Space theme has chain node role {r!r}", r in space_node_roles)

space_node_names = " | ".join(n.name for n in space.industry_chain_nodes).lower()
for token in ["launch", "satellite manufacturing", "satellite communications",
              "earth observation", "defense space", "components", "ground"]:
    check(f"3.3 Space chain-node names mention {token!r}", token in space_node_names)

check("3.4 Space theme has >= 3 subthemes", len(space.subthemes) >= 3)


# ---------------------------------------------------------------------------
# Section 4 — Degraded / emerging theme: partial evidence + unknown state
# ---------------------------------------------------------------------------

deg = build_degraded_theme_fixture()
check("4.1 degraded theme lifecycle is unknown", deg.lifecycle_stage == "unknown")
check("4.2 degraded theme heat score status is unknown",
      deg.heat_score.score_status in ("unknown",)
      or derive_heat_score_status(deg.heat_score) == "unknown")
check("4.3 degraded theme evidence coverage is none/partial",
      deg.evidence.coverage_status in ("none", "partial", "unknown"))
check("4.4 degraded theme carries a missing-evidence/narrative-only warning",
      any(w.warning_type in ("missing_evidence", "narrative_only") for w in deg.warnings))
check("4.5 degraded theme has at least one subtheme with unknown lifecycle",
      any(s.lifecycle_stage == "unknown" for s in deg.subthemes))
check("4.6 degraded theme candidate has no fundamental confirmation (none coverage)",
      any(c.evidence.coverage_status == "none" for c in deg.candidate_tickers))


# ---------------------------------------------------------------------------
# Section 5 — Candidate maps to multiple subthemes / chain nodes
# ---------------------------------------------------------------------------

multi_sub = [c for c in ai.candidate_tickers if len(c.subtheme_ids) >= 2]
multi_node = [c for c in ai.candidate_tickers if len(c.chain_node_ids) >= 2]
check("5.1 at least one AI candidate maps to >= 2 subthemes", len(multi_sub) >= 1)
check("5.2 at least one AI candidate maps to >= 2 chain nodes", len(multi_node) >= 1)

# Construct one directly to assert the contract supports many-to-many mapping.
cand = ThemeCandidateTicker(
    ticker="MULTI",
    theme_id="theme_x",
    subtheme_ids=["s1", "s2", "s3"],
    chain_node_ids=["n1", "n2"],
    role="second_derivative_beneficiary",
)
check("5.3 ThemeCandidateTicker accepts multiple subtheme ids", len(cand.subtheme_ids) == 3)
check("5.4 ThemeCandidateTicker accepts multiple chain-node ids", len(cand.chain_node_ids) == 2)
check("5.5 'unknown' is a valid candidate role", "unknown" in THEME_CANDIDATE_ROLES)


# ---------------------------------------------------------------------------
# Section 6 — ThemeHeatScore supports complete / partial / unknown
# ---------------------------------------------------------------------------

complete = build_theme_heat_score(
    price_momentum_component=0.5,
    volume_component=0.5,
    breadth_component=0.5,
    narrative_component=0.5,
    fundamental_confirmation_component=0.5,
    freshness_component=0.5,
)
partial = build_theme_heat_score(price_momentum_component=0.5, volume_component=0.4)
unknown = build_theme_heat_score()

check("6.1 complete heat score status == complete", complete.score_status == "complete")
check("6.2 complete heat score has a total_score", complete.total_score is not None)
check("6.3 partial heat score status == partial", partial.score_status == "partial")
check("6.4 partial heat score does not fabricate a total", partial.total_score is None)
check("6.5 unknown heat score status == unknown", unknown.score_status == "unknown")
check("6.6 unknown heat score has no total", unknown.total_score is None)
check("6.7 derive_heat_score_status agrees for complete",
      derive_heat_score_status(complete) == "complete")
check("6.8 derive_heat_score_status agrees for partial",
      derive_heat_score_status(partial) == "partial")

# Validation summary tallies all three statuses across the default snapshot.
vs = snap.validation_summary
check("6.9 validation summary tallies complete heat scores", vs is not None and vs.complete_heat_score_count >= 1)
check("6.10 validation summary tallies partial heat scores", vs is not None and vs.partial_heat_score_count >= 1)
check("6.11 validation summary tallies unknown heat scores", vs is not None and vs.unknown_heat_score_count >= 1)


# ---------------------------------------------------------------------------
# Section 7 — CrowdingSignal separate from ThemeHeatScore; heat != buy signal
# ---------------------------------------------------------------------------

heat_fields = set(ThemeHeatScore.model_fields.keys())
crowd_fields = set(CrowdingSignal.model_fields.keys())

check("7.1 ThemeHeatScore has no crowding_level field (kept on CrowdingSignal)",
      "crowding_level" not in heat_fields)
check("7.2 CrowdingSignal has crowding_level field", "crowding_level" in crowd_fields)
check("7.3 CrowdingSignal is a distinct model from ThemeHeatScore",
      CrowdingSignal is not ThemeHeatScore)

# heat score must not contain buy/trade decision fields
FORBIDDEN_DECISION_FIELDS = {
    "buy", "sell", "trade_now", "buy_now", "actionable",
    "approved_for_execution", "recommendation", "decision",
    "order_type", "time_in_force", "broker_route", "account_id",
    "quantity", "quantity_to_execute", "order_id", "execution_id",
}
check("7.4 ThemeHeatScore declares no buy/trade decision field",
      not (heat_fields & FORBIDDEN_DECISION_FIELDS),
      detail=str(heat_fields & FORBIDDEN_DECISION_FIELDS))
check("7.5 ThemeHeatScore has an explicit is_buy_signal == False marker",
      "is_buy_signal" in heat_fields and complete.is_buy_signal is False)

# is_buy_signal is Literal[False]: setting True must raise.
try:
    ThemeHeatScore(is_buy_signal=True)
    _raised = False
except Exception:
    _raised = True
check("7.6 ThemeHeatScore rejects is_buy_signal=True", _raised)


# ---------------------------------------------------------------------------
# Section 8 — Empty snapshot is safe
# ---------------------------------------------------------------------------

empty = build_empty_theme_intelligence_snapshot()
check("8.1 empty snapshot builds", isinstance(empty, ThemeIntelligenceSnapshot))
check("8.2 empty snapshot has zero themes", len(empty.universe.themes) == 0)
check("8.3 empty snapshot validation is_safe_empty",
      empty.validation_summary is not None and empty.validation_summary.is_safe_empty)
check("8.4 empty snapshot theme_count == 0",
      empty.validation_summary is not None and empty.validation_summary.theme_count == 0)

# A directly-constructed bare snapshot validates safely too.
bare = ThemeIntelligenceSnapshot(
    snapshot_id="themeintel_bare", universe=ThemeUniverseSnapshot()
)
bare_vs = validate_theme_intelligence_snapshot(bare)
check("8.5 bare snapshot validates as safe empty", bare_vs.is_safe_empty)


# ---------------------------------------------------------------------------
# Section 9 — Serialization is deterministic
# ---------------------------------------------------------------------------

s1 = build_default_theme_intelligence_snapshot().model_dump(mode="json")
s2 = build_default_theme_intelligence_snapshot().model_dump(mode="json")
check("9.1 two builds dump-equal", s1 == s2)
j1 = json.dumps(s1, sort_keys=True)
j2 = json.dumps(s2, sort_keys=True)
check("9.2 JSON serialization deterministic across builds", j1 == j2)
# Round-trip
rt = ThemeIntelligenceSnapshot.model_validate(s1)
check("9.3 round-trip re-validates", isinstance(rt, ThemeIntelligenceSnapshot))
check("9.4 round-trip dump-equal", rt.model_dump(mode="json") == s1)
check("9.5 theme ids deterministic across builds",
      [t.theme_id for t in build_default_theme_intelligence_snapshot().universe.themes]
      == [t.theme_id for t in build_default_theme_intelligence_snapshot().universe.themes])


# ---------------------------------------------------------------------------
# Section 10 — No approved_for_execution anywhere; no order-ticket fields
# ---------------------------------------------------------------------------

ALL_MODELS = [
    ThemeIntelligenceSnapshot,
    ThemeUniverseSnapshot,
    ThemeRecord,
    SubthemeRecord,
    IndustryChainNode,
    ThemeCandidateTicker,
    ThemeHeatScore,
    CrowdingSignal,
    ThemeIntelligenceValidationSummary,
    EntryQualityScorePlaceholder,
]
ORDER_TICKET_FIELDS = {
    "approved_for_execution",
    "order_type",
    "order_id",
    "time_in_force",
    "broker_route",
    "broker_payload",
    "account_id",
    "execution_id",
    "quantity_to_execute",
    "limit_price",
    "stop_price",
    "fill_price",
}
for m in ALL_MODELS:
    fields = set(m.model_fields.keys())
    bad = fields & ORDER_TICKET_FIELDS
    check(f"10.1 {m.__name__} declares no order-ticket field", not bad, detail=str(bad))

# extra="forbid": cannot smuggle approved_for_execution into the snapshot.
try:
    ThemeIntelligenceSnapshot(
        snapshot_id="x", universe=ThemeUniverseSnapshot(), approved_for_execution=True
    )
    _afe_raised = False
except Exception:
    _afe_raised = True
check("10.2 snapshot rejects approved_for_execution kwarg (extra=forbid)", _afe_raised)

# Serialized default snapshot contains no positive approved_for_execution=true.
# (The safety flag `approved_for_execution_absent` is allowed; an actual
#  `approved_for_execution` field set true is not.)
dump_str = json.dumps(s1).lower()
check("10.3 serialized snapshot does not authorize approved_for_execution",
      '"approved_for_execution": true' not in dump_str
      and '"approved_for_execution":true' not in dump_str
      and '"approved_for_execution":' not in dump_str)
check("10.4 validation summary asserts execution safety invariants",
      vs is not None and vs.no_executable_order_fields and vs.approved_for_execution_absent
      and vs.no_buy_signal_fields)


# ---------------------------------------------------------------------------
# Section 11 — Module source forbidden-import / forbidden-content checks
# ---------------------------------------------------------------------------

module_src = _read_text(MODULE_PATH)
FORBIDDEN_IMPORT_SUBSTRINGS = [
    "import streamlit",
    "import anthropic",
    "import openai",
    "from app",
    "import app\n",
    "lib.workflow_state",
    "lib.llm_orchestrator",
    "lib.data_fetcher",
    "from pages",
    "import requests",
    "import httpx",
    "import urllib",
    "yfinance",
    "polygon",
    "finnhub",
]
for sub in FORBIDDEN_IMPORT_SUBSTRINGS:
    check(f"11.1 module does not reference {sub!r}", sub not in module_src,
          detail=sub)

# Module must not read the live workflow state file.
check("11.2 module does not read research/.workflow_state.json",
      ".workflow_state.json" not in module_src)
# No file-open / persistence in the schema module.
check("11.3 module does not open files for persistence",
      "open(" not in module_src and "Path(" not in module_src)
# Deterministic: no wall-clock time / randomness in the schema module.
check("11.4 module does not use datetime.now / time.time / random",
      "datetime.now" not in module_src
      and "time.time(" not in module_src
      and "import random" not in module_src)


# ---------------------------------------------------------------------------
# Section 12 — Package exports wired
# ---------------------------------------------------------------------------

EXPECTED_EXPORTS = [
    "ThemeIntelligenceSnapshot",
    "ThemeRecord",
    "SubthemeRecord",
    "IndustryChainNode",
    "ThemeCandidateTicker",
    "ThemeHeatScore",
    "CrowdingSignal",
    "NarrativeSignal",
    "FundamentalConfirmationSignal",
    "ThemeHeatSignal",
    "ThemeLifecycleStage",
    "ThemeEvidenceSummary",
    "ThemeRiskWarning",
    "ThemeDiscoverySource",
    "ThemeUniverseSnapshot",
    "ThemeIntelligenceValidationSummary",
    "EntryQualityScorePlaceholder",
    "build_default_theme_intelligence_snapshot",
    "build_ai_theme_fixture",
    "build_space_theme_fixture",
    "build_degraded_theme_fixture",
    "validate_theme_intelligence_snapshot",
]
for name in EXPECTED_EXPORTS:
    check(f"12.1 lib.reliability exports {name!r}", hasattr(reliability_pkg, name))
    check(f"12.2 {name!r} is in lib.reliability.__all__", name in reliability_pkg.__all__)


# ---------------------------------------------------------------------------
# Section 13 — Documentation present with required sections
# ---------------------------------------------------------------------------

check("13.1 Phase 5J doc exists", os.path.isfile(DOC_PATH), detail=DOC_PATH)
doc = _read_text(DOC_PATH) if os.path.isfile(DOC_PATH) else ""
dlc = doc.lower()
REQUIRED_DOC_TOPICS = [
    "Purpose",
    "Phase 5I",
    "Roadmap v4",
    "sector",
    "Theme Intelligence",
    "Market Heat",
    "industry-chain",
    "Candidate ticker roles",
    "Narrative signals",
    "Fundamental confirmation",
    "Crowding signals",
    "Theme lifecycle",
    "Heat score",
    "not a buy signal",
    "AI",
    "Space",
    "Non-goals",
    "Guardrails",
    "Acceptance criteria",
    "Phase 5K",
]
for topic in REQUIRED_DOC_TOPICS:
    check(f"13.2 Phase 5J doc covers {topic!r}", topic in doc or topic.lower() in dlc)

check("13.3 Phase 5J doc states heat score is not a buy signal",
      "not a buy signal" in dlc)
check("13.4 Phase 5J doc explains why sector/ETF heatmaps are insufficient",
      ("etf" in dlc or "heatmap" in dlc) and "insufficient" in dlc)
check("13.5 Phase 5J doc states approved_for_execution stays False/absent",
      "approved_for_execution" in doc
      and ("false" in dlc or "absent" in dlc))
check("13.6 Phase 5J doc keeps Phase 5K as a future dependency, not started",
      "phase 5k" in dlc and ("future" in dlc or "not started" in dlc or "next" in dlc))


# ---------------------------------------------------------------------------
# Section 14 — Phase 5I doc/state assertions
# ---------------------------------------------------------------------------

state_text = _read_text(PROJECT_STATE) if os.path.isfile(PROJECT_STATE) else ""
task_text = _read_text(CURRENT_TASK) if os.path.isfile(CURRENT_TASK) else ""
state_lc = state_text.lower()
task_lc = task_text.lower()

check("14.1 PROJECT_STATE marks Phase 5I accepted",
      "phase 5i" in state_lc and "accepted" in state_lc)
check("14.2 PROJECT_STATE references Phase 5J implemented / awaiting review",
      "phase 5j" in state_lc
      and ("awaiting" in state_lc or "implemented" in state_lc))
check("14.3 PROJECT_STATE does not claim Phase 5J accepted as completed roadmap row",
      "phase 5j — theme intelligence / market heat schema — accepted" not in state_lc
      and "phase 5j theme intelligence / market heat schema — accepted" not in state_lc)
check("14.4 PROJECT_STATE does not claim Phase 5K has started",
      "phase 5k has started" not in state_lc and "phase 5k started" not in state_lc)
check("14.5 CURRENT_TASK marks Phase 5I accepted",
      "phase 5i" in task_lc and "accepted" in task_lc)
check("14.6 CURRENT_TASK sets current task to Phase 5J",
      "phase 5j" in task_lc)
check("14.7 CURRENT_TASK recommends Phase 5K next after acceptance",
      "phase 5k" in task_lc and "opportunity queue" in task_lc)
check("14.8 CURRENT_TASK does not claim Phase 5K started",
      "phase 5k has started" not in task_lc and "phase 5k started" not in task_lc)
check("14.9 Phase 5I doc still present (not removed)", os.path.isfile(PHASE_5I_DOC))


# ---------------------------------------------------------------------------
# Section 15 — Theme/heat semantics: high heat alone does not actionize
# ---------------------------------------------------------------------------

# The hottest theme in the default universe still carries a crowding warning
# and no buy/trade field — high heat is a reason to research, not to buy.
hot = max(
    (t for t in snap.universe.themes if t.heat_score.score_status == "complete"),
    key=lambda t: (t.heat_score.total_score or 0.0),
)
check("15.1 hottest complete theme has a total score", hot.heat_score.total_score is not None)
check("15.2 hottest theme carries a crowding/risk warning (heat != entry)",
      len(hot.warnings) >= 1)
check("15.3 hottest theme exposes no buy/trade/decision field on the record",
      not (set(ThemeRecord.model_fields.keys()) & FORBIDDEN_DECISION_FIELDS))
check("15.4 EntryQualityScorePlaceholder is explicitly not computed",
      EntryQualityScorePlaceholder().computed is False)
check("15.5 EntryQualityScorePlaceholder deferred to Phase 5K",
      "5k" in EntryQualityScorePlaceholder().deferred_to_phase.lower())


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
print("=" * 70)
print("Phase 5J — Theme Intelligence / Market Heat Schema — test results")
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
    print("RESULT: PASS — Phase 5J theme intelligence schema verified.")
    sys.exit(0)
else:
    print("RESULT: FAIL — see failures above.")
    sys.exit(1)
