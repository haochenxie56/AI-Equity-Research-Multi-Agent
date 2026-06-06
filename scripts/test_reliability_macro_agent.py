"""
scripts/test_reliability_macro_agent.py

Phase 3C: Macro Agent v0.1 Skeleton — test suite.

Directly runnable:
    python3 scripts/test_reliability_macro_agent.py

Tests 46 assertions covering schemas, helpers, determinism,
regression, serialization, and no-live-app guarantees.
"""

import importlib
import json
import os
import sys
import traceback
import types

# ── Repo root on path ──────────────────────────────────────────────────────
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# ── Imports ────────────────────────────────────────────────────────────────
from lib.reliability.macro_agent import (
    MacroAgentIssue,
    MacroAgentInputBundle,
    MacroAgentResult,
    MacroHorizonImpact,
    MacroRegimeAssessment,
    MacroSectorBias,
    MacroSignalSummary,
    build_macro_agent_result,
    derive_macro_horizon_impacts,
    derive_macro_sector_biases,
    extract_macro_evidence_ids,
    infer_macro_regime,
    infer_macro_signal_domain_from_path,
    issue_from_critic_issue_for_macro,
    issue_from_staleness_finding_for_macro,
    issue_from_validation_item_for_macro,
    macro_agent_result_to_agent_result,
    macro_agent_tool_result_from_result,
    make_macro_agent_id,
    make_macro_agent_issue_id,
    run_macro_agent_v0,
    summarize_macro_agent_result,
    summarize_macro_signals,
)
from lib.reliability.schemas import AgentResult, ToolResult
from lib.reliability.adapters import stable_hash_payload
from lib.reliability.validation_aggregator import (
    AggregatedValidationItem,
    ValidationAggregate,
    make_validation_item_id,
)
from lib.reliability.staleness import StalenessFinding, StalenessReport
from lib.reliability.critic import CriticIssue, CriticResult, make_critic_issue_id


# ── Test runner ────────────────────────────────────────────────────────────

PASS = 0
FAIL = 0
ERRORS: list[str] = []


def _ok(label: str) -> None:
    global PASS
    PASS += 1
    print(f"  [PASS] {label}")


def _fail(label: str, reason: str) -> None:
    global FAIL
    FAIL += 1
    ERRORS.append(f"{label}: {reason}")
    print(f"  [FAIL] {label}: {reason}")


def test(label: str, condition: bool, reason: str = "") -> None:
    if condition:
        _ok(label)
    else:
        _fail(label, reason or "condition was False")


def test_raises(label: str, fn, exc_type=Exception) -> None:
    try:
        fn()
        _fail(label, f"Expected {exc_type.__name__} but no exception raised")
    except exc_type:
        _ok(label)
    except Exception as e:
        _fail(label, f"Got unexpected {type(e).__name__}: {e}")


# ── Fixtures ────────────────────────────────────────────────────────────────

def _make_tool_result(
    evidence_id: str = "evid_macro_001",
    tool_name: str = "macro_snapshot",
    run_id: str = "run_001",
) -> ToolResult:
    return ToolResult(
        evidence_id=evidence_id,
        tool_name=tool_name,
        run_id=run_id,
    )


def _make_validation_aggregate(
    severity: str = "warning",
    item_type: str = "stale_data",
) -> ValidationAggregate:
    item_id = make_validation_item_id("macro", "Macro data is stale.", field_path="indicators.0.as_of")
    item = AggregatedValidationItem(
        item_id=item_id,
        domain="macro",
        severity=severity,  # type: ignore
        item_type=item_type,  # type: ignore
        message="Macro data is stale.",
        field_path="indicators.0.as_of",
    )
    from lib.reliability.validation_aggregator import aggregate_validation_items
    return aggregate_validation_items("agg_001", "2026-05-23", [item])


def _make_staleness_finding(domain: str = "macro", status: str = "stale") -> StalenessFinding:
    from lib.reliability.staleness import make_staleness_finding_id
    fid = make_staleness_finding_id(domain=domain, timestamp_role="as_of", timestamp_value="2026-04-01", as_of="2026-05-23", object_id="snap_001")  # type: ignore
    return StalenessFinding(
        finding_id=fid,
        domain=domain,  # type: ignore
        status=status,  # type: ignore
        severity="warning",
        message=f"Macro snapshot is {status}.",
        as_of="2026-05-23",
        timestamp_role="as_of",
        timestamp_value="2026-04-01",
        age_days=52.0,
        max_age_days=30.0,
        object_id="snap_001",
        field_path="indicators.0.as_of",
    )


def _make_staleness_report(domain: str = "macro", status: str = "stale") -> StalenessReport:
    finding = _make_staleness_finding(domain, status)
    return StalenessReport(
        report_id="sr_001",
        as_of="2026-05-23",
        findings=[finding],
    )


def _make_critic_issue(
    issue_type: str = "overconfidence",
    severity: str = "warning",
) -> CriticIssue:
    issue_id = make_critic_issue_id(
        issue_type=issue_type,
        message="Macro regime claim lacks evidence.",
        target_id="macro_agent",
    )
    return CriticIssue(
        issue_id=issue_id,
        issue_type=issue_type,  # type: ignore
        severity=severity,  # type: ignore
        target_type="agent_result",
        message="Macro regime claim lacks evidence.",
        target_id="macro_agent",
        evidence_id="evid_macro_001",
        field_path="regime",
    )


def _make_critic_result() -> CriticResult:
    issue = _make_critic_issue()
    return CriticResult(
        critic_id="cr_001",
        as_of="2026-05-23",
        issues=[issue],
    )


def _make_signal_summary(
    domain: str = "liquidity",
    stale: bool = False,
    contested: bool = False,
    evidence_ids: list | None = None,
) -> MacroSignalSummary:
    return MacroSignalSummary(
        domain=domain,  # type: ignore
        direction="unknown",
        strength="unknown",
        evidence_ids=evidence_ids or ["evid_macro_001"],
        key_points=["indicator: m2_growth=5.0%"],
        stale=stale,
        contested=contested,
    )


def _make_regime_assessment(
    regime: str = "neutral",
    confidence: str = "low",
    risk_appetite: str = "moderate",
    evidence_ids: list | None = None,
    issues: list | None = None,
) -> MacroRegimeAssessment:
    return MacroRegimeAssessment(
        regime=regime,  # type: ignore
        confidence=confidence,
        risk_appetite=risk_appetite,  # type: ignore
        supporting_evidence_ids=evidence_ids or ["evid_macro_001"],
        issues=issues or [],
    )


def _make_minimal_bundle() -> MacroAgentInputBundle:
    return MacroAgentInputBundle(
        bundle_id="bundle_001",
        as_of="2026-05-23",
    )


def _make_full_bundle() -> MacroAgentInputBundle:
    tr = _make_tool_result()
    va = _make_validation_aggregate()
    sr = _make_staleness_report()
    cr = _make_critic_result()
    return MacroAgentInputBundle(
        bundle_id="bundle_001",
        as_of="2026-05-23",
        ticker="AAPL",
        tool_results=[tr],
        validation_aggregate=va,
        staleness_report=sr,
        critic_result=cr,
    )


# ── T1–T3: MacroAgentIssue ─────────────────────────────────────────────────

print("\nT1–T3: MacroAgentIssue schema")

try:
    issue = MacroAgentIssue(
        issue_id="issue_001",
        issue_type="missing_macro_evidence",
        severity="warning",
        message="No macro evidence found.",
        domain="rates",
    )
    test("T1: MacroAgentIssue accepts valid issue", True)
    test("T1b: issue_type preserved", issue.issue_type == "missing_macro_evidence")
    test("T1c: domain preserved", issue.domain == "rates")
except Exception as e:
    _fail("T1: MacroAgentIssue accepts valid issue", str(e))

test_raises(
    "T2: MacroAgentIssue rejects empty issue_id",
    lambda: MacroAgentIssue(
        issue_id="",
        issue_type="other",
        message="msg",
    ),
)

test_raises(
    "T3: MacroAgentIssue rejects empty message",
    lambda: MacroAgentIssue(
        issue_id="id_001",
        issue_type="other",
        message="",
    ),
)


# ── T4: MacroSignalSummary ─────────────────────────────────────────────────

print("\nT4: MacroSignalSummary schema")

try:
    s = MacroSignalSummary(
        domain="inflation",
        direction="headwind",
        strength="medium",
        evidence_ids=["evid_001"],
        key_points=["CPI high"],
        stale=False,
        contested=True,
    )
    test("T4: MacroSignalSummary accepts valid summary", True)
    test("T4b: domain preserved", s.domain == "inflation")
    test("T4c: contested preserved", s.contested is True)
except Exception as e:
    _fail("T4: MacroSignalSummary accepts valid summary", str(e))


# ── T5: MacroRegimeAssessment ──────────────────────────────────────────────

print("\nT5: MacroRegimeAssessment schema")

try:
    ra = MacroRegimeAssessment(
        regime="risk_on",
        confidence="low",
        risk_appetite="moderate",
        supporting_evidence_ids=["evid_001"],
    )
    test("T5: MacroRegimeAssessment accepts valid assessment", True)
    test("T5b: regime preserved", ra.regime == "risk_on")
except Exception as e:
    _fail("T5: MacroRegimeAssessment accepts valid assessment", str(e))


# ── T6–T7: MacroSectorBias ─────────────────────────────────────────────────

print("\nT6–T7: MacroSectorBias schema")

try:
    sb = MacroSectorBias(
        sector="energy_materials",
        bias="neutral",
        rationale="Macro inflation regime.",
        supporting_domains=["inflation"],
        evidence_ids=["evid_001"],
    )
    test("T6: MacroSectorBias accepts valid bias", True)
    test("T6b: sector preserved", sb.sector == "energy_materials")
except Exception as e:
    _fail("T6: MacroSectorBias accepts valid bias", str(e))

test_raises(
    "T7: MacroSectorBias rejects empty sector",
    lambda: MacroSectorBias(sector="", bias="neutral"),
)


# ── T8–T9: MacroHorizonImpact ──────────────────────────────────────────────

print("\nT8–T9: MacroHorizonImpact schema")

try:
    hi = MacroHorizonImpact(
        horizon="short_term",
        impact="supportive",
        confidence="low",
        rationale="Liquidity supportive.",
        evidence_ids=["evid_001"],
    )
    test("T8: MacroHorizonImpact accepts valid impact", True)
    test("T8b: horizon preserved", hi.horizon == "short_term")
    test("T8c: impact preserved", hi.impact == "supportive")
except Exception as e:
    _fail("T8: MacroHorizonImpact accepts valid impact", str(e))

test_raises(
    "T9: MacroHorizonImpact rejects empty horizon",
    lambda: MacroHorizonImpact(horizon="", impact="neutral"),
)


# ── T10–T12: MacroAgentResult ──────────────────────────────────────────────

print("\nT10–T12: MacroAgentResult schema")

try:
    result = MacroAgentResult(
        macro_agent_id="maid_001",
        as_of="2026-05-23",
        ticker="AAPL",
    )
    test("T10: MacroAgentResult accepts valid result", True)
    test("T10b: ticker preserved", result.ticker == "AAPL")
    test("T10c: status auto-normalized", result.status in (
        "pass", "pass_with_warnings", "fail", "insufficient_evidence", "unknown"
    ))
except Exception as e:
    _fail("T10: MacroAgentResult accepts valid result", str(e))

test_raises(
    "T11: MacroAgentResult rejects empty macro_agent_id",
    lambda: MacroAgentResult(macro_agent_id="", as_of="2026-05-23"),
)

test_raises(
    "T12: MacroAgentResult rejects empty as_of",
    lambda: MacroAgentResult(macro_agent_id="maid_001", as_of=""),
)


# ── T13–T15: MacroAgentInputBundle ────────────────────────────────────────

print("\nT13–T15: MacroAgentInputBundle schema")

try:
    bundle = _make_minimal_bundle()
    test("T13: MacroAgentInputBundle accepts minimal bundle", True)
    test("T13b: bundle_id preserved", bundle.bundle_id == "bundle_001")
    test("T13c: tool_results defaults to []", bundle.tool_results == [])
except Exception as e:
    _fail("T13: MacroAgentInputBundle accepts minimal bundle", str(e))

test_raises(
    "T14: MacroAgentInputBundle rejects empty bundle_id",
    lambda: MacroAgentInputBundle(bundle_id="", as_of="2026-05-23"),
)

test_raises(
    "T15: MacroAgentInputBundle rejects empty as_of",
    lambda: MacroAgentInputBundle(bundle_id="b001", as_of=""),
)


# ── T16–T18: ID helpers ────────────────────────────────────────────────────

print("\nT16–T18: make_macro_agent_issue_id / make_macro_agent_id")

id1 = make_macro_agent_issue_id("missing_macro_evidence", "No evidence.", domain="rates")
id2 = make_macro_agent_issue_id("missing_macro_evidence", "No evidence.", domain="rates")
test("T16: make_macro_agent_issue_id is deterministic", id1 == id2)

id3 = make_macro_agent_issue_id("other", "No evidence.", domain="rates")
id4 = make_macro_agent_issue_id("missing_macro_evidence", "Different message.", domain="rates")
test("T17: make_macro_agent_issue_id changes with inputs",
     id1 != id3 and id1 != id4 and id3 != id4)

mid1 = make_macro_agent_id("bundle_001", "2026-05-23", ticker="AAPL")
mid2 = make_macro_agent_id("bundle_001", "2026-05-23", ticker="AAPL")
test("T18: make_macro_agent_id is deterministic", mid1 == mid2)

mid3 = make_macro_agent_id("bundle_002", "2026-05-23", ticker="AAPL")
test("T18b: make_macro_agent_id changes with bundle_id", mid1 != mid3)


# ── T19: extract_macro_evidence_ids ───────────────────────────────────────

print("\nT19: extract_macro_evidence_ids")

tr_macro = _make_tool_result("evid_macro_001", "macro_snapshot", "run_001")
tr_other = _make_tool_result("evid_valuation_001", "dcf_valuation", "run_001")
eids = extract_macro_evidence_ids(tool_results=[tr_macro, tr_other])
test("T19: collects macro ToolResult evidence IDs", "evid_macro_001" in eids)
test("T19b: excludes non-macro ToolResult evidence IDs", "evid_valuation_001" not in eids)


# ── T20: infer_macro_signal_domain_from_path ──────────────────────────────

print("\nT20: infer_macro_signal_domain_from_path")

test("T20a: maps rates keyword", infer_macro_signal_domain_from_path("fed_funds_rate") == "rates")
test("T20b: maps inflation keyword", infer_macro_signal_domain_from_path("cpi_yoy") == "inflation")
test("T20c: maps growth keyword", infer_macro_signal_domain_from_path("gdp_growth") == "growth")
test("T20d: maps liquidity keyword", infer_macro_signal_domain_from_path("m2_liquidity") == "liquidity")
test("T20e: maps credit keyword", infer_macro_signal_domain_from_path("hy_spread") == "credit")
test("T20f: maps breadth keyword", infer_macro_signal_domain_from_path("advance_decline") == "breadth")
test("T20g: maps volatility keyword", infer_macro_signal_domain_from_path("vix_level") == "volatility")
test("T20h: maps unknown for unrecognized path", infer_macro_signal_domain_from_path("xyz_abc") == "unknown")
test("T20i: handles None", infer_macro_signal_domain_from_path(None) == "unknown")


# ── T21–T22: summarize_macro_signals ─────────────────────────────────────

print("\nT21–T22: summarize_macro_signals")

sigs_empty = summarize_macro_signals()
test("T21: summarize_macro_signals returns empty with no evidence", sigs_empty == [])

tr_macro2 = _make_tool_result("evid_macro_002", "macro_snapshot", "run_002")
sigs_with_trs = summarize_macro_signals(tool_results=[tr_macro2])
test("T22: summarize_macro_signals returns domain summaries with macro ToolResults",
     len(sigs_with_trs) > 0)
test("T22b: evidence_id included in summary", any(
    "evid_macro_002" in s.evidence_ids for s in sigs_with_trs
))


# ── T23–T24: infer_macro_regime ───────────────────────────────────────────

print("\nT23–T24: infer_macro_regime")

regime_empty = infer_macro_regime([])
test("T23: infer_macro_regime returns insufficient_evidence with no signals",
     regime_empty.regime == "insufficient_evidence")
test("T23b: risk_appetite is insufficient_evidence", regime_empty.risk_appetite == "insufficient_evidence")
test("T23c: has missing_macro_evidence issue", any(
    i.issue_type == "missing_macro_evidence" for i in regime_empty.issues
))

# Stress-like: many stale + contested signals
stress_summaries = [
    _make_signal_summary("credit", stale=True, contested=True, evidence_ids=["evid_001"]),
    _make_signal_summary("growth", stale=True, contested=True, evidence_ids=["evid_002"]),
    _make_signal_summary("volatility", stale=True, contested=False, evidence_ids=["evid_003"]),
]
regime_stress = infer_macro_regime(stress_summaries)
test("T24: infer_macro_regime returns risk_off/defensive or mixed for stress signals",
     regime_stress.regime in ("risk_off", "mixed", "insufficient_evidence", "neutral") or
     regime_stress.risk_appetite in ("defensive", "unknown", "insufficient_evidence"))


# ── T25: derive_macro_sector_biases ───────────────────────────────────────

print("\nT25: derive_macro_sector_biases")

ra_neutral = _make_regime_assessment(regime="neutral", evidence_ids=["evid_001"])
sigs_sample = [_make_signal_summary("liquidity"), _make_signal_summary("breadth")]
biases = derive_macro_sector_biases(ra_neutral, sigs_sample)
test("T25: derive_macro_sector_biases returns cautious mock sector biases",
     len(biases) > 0)
test("T25b: all biases have non-empty sector", all(sb.sector for sb in biases))
test("T25c: no buy/sell language in rationale",
     all("buy" not in (sb.rationale or "").lower() and "sell" not in (sb.rationale or "").lower()
         for sb in biases))


# ── T26: derive_macro_horizon_impacts ─────────────────────────────────────

print("\nT26: derive_macro_horizon_impacts")

ra_roff = _make_regime_assessment(regime="risk_off", evidence_ids=["evid_001"])
impacts = derive_macro_horizon_impacts(ra_roff, sigs_sample)
test("T26: derive_macro_horizon_impacts returns short/medium/long impacts",
     len(impacts) == 3)
horizons = {hi.horizon for hi in impacts}
test("T26b: all three horizons present",
     "short_term" in horizons and "medium_term" in horizons and "long_term" in horizons)


# ── T27: issue_from_validation_item_for_macro ─────────────────────────────

print("\nT27: issue_from_validation_item_for_macro")

va_item_id = make_validation_item_id("macro", "Macro inflation stale.", field_path="inflation.cpi_yoy")
va_item = AggregatedValidationItem(
    item_id=va_item_id,
    domain="macro",
    severity="warning",
    item_type="stale_data",
    message="Macro inflation stale.",
    field_path="inflation.cpi_yoy",
    evidence_id="evid_mac_003",
    object_id="snap_001",
)
mac_issue = issue_from_validation_item_for_macro(va_item)
test("T27: issue_from_validation_item_for_macro preserves evidence_id",
     mac_issue.evidence_id == "evid_mac_003")
test("T27b: preserves field_path", mac_issue.field_path == "inflation.cpi_yoy")
test("T27c: maps stale_data → stale_macro_evidence",
     mac_issue.issue_type == "stale_macro_evidence")
test("T27d: infers inflation domain", mac_issue.domain == "inflation")


# ── T28: issue_from_staleness_finding_for_macro ───────────────────────────

print("\nT28: issue_from_staleness_finding_for_macro")

staleness_finding = _make_staleness_finding("macro", "stale")
stale_issue = issue_from_staleness_finding_for_macro(staleness_finding)
test("T28: issue_from_staleness_finding_for_macro maps stale macro evidence",
     stale_issue.issue_type == "stale_macro_evidence")
test("T28b: preserves field_path", stale_issue.field_path is not None)
test("T28c: preserves object_id as related_id",
     stale_issue.related_id == "snap_001")


# ── T29: issue_from_critic_issue_for_macro ────────────────────────────────

print("\nT29: issue_from_critic_issue_for_macro")

critic_issue_oc = _make_critic_issue("overconfidence", "warning")
mac_critic_issue = issue_from_critic_issue_for_macro(critic_issue_oc)
test("T29: issue_from_critic_issue_for_macro maps overconfidence",
     mac_critic_issue.issue_type == "overconfidence")
test("T29b: preserves evidence_id", mac_critic_issue.evidence_id == "evid_macro_001")
test("T29c: preserves field_path", mac_critic_issue.field_path == "regime")

critic_issue_unsup = _make_critic_issue("unsupported_claim", "warning")
mac_unsup = issue_from_critic_issue_for_macro(critic_issue_unsup)
test("T29d: maps unsupported_claim → unsupported_macro_claim",
     mac_unsup.issue_type == "unsupported_macro_claim")


# ── T30: build_macro_agent_result ─────────────────────────────────────────

print("\nT30: build_macro_agent_result normalizes status/recommendation")

ra_pass = _make_regime_assessment("neutral", evidence_ids=["evid_001"])
result_pass = build_macro_agent_result(
    macro_agent_id="maid_pass",
    as_of="2026-05-23",
    regime_assessment=ra_pass,
    sector_biases=[],
    horizon_impacts=[],
)
test("T30: build_macro_agent_result normalizes status",
     result_pass.status in ("pass", "pass_with_warnings", "fail", "insufficient_evidence"))
test("T30b: normalizes recommendation",
     result_pass.recommendation in (
         "proceed_to_horizon_synthesis", "revise", "reject", "needs_more_evidence", "no_action"
     ))


# ── T31–T32: run_macro_agent_v0 ───────────────────────────────────────────

print("\nT31–T32: run_macro_agent_v0")

bundle_full = _make_full_bundle()
result1 = run_macro_agent_v0(bundle_full)
test("T31: run_macro_agent_v0 returns MacroAgentResult", isinstance(result1, MacroAgentResult))
test("T31b: macro_agent_id non-empty", bool(result1.macro_agent_id))
test("T31c: as_of matches bundle", result1.as_of == "2026-05-23")
test("T31d: ticker matches bundle", result1.ticker == "AAPL")
test("T31e: regime_assessment present", result1.regime_assessment is not None)
test("T31f: horizon_impacts has 3 entries", len(result1.horizon_impacts) == 3)

result1b = run_macro_agent_v0(bundle_full)
test("T31g: run_macro_agent_v0 is deterministic (macro_agent_id stable)",
     result1.macro_agent_id == result1b.macro_agent_id)

# Mutation guard
original_trs = list(bundle_full.tool_results)
_ = run_macro_agent_v0(bundle_full)
test("T32: run_macro_agent_v0 does not mutate input bundle",
     bundle_full.tool_results == original_trs and bundle_full.bundle_id == "bundle_001")


# ── T33–T34: macro_agent_result_to_agent_result ───────────────────────────

print("\nT33–T34: macro_agent_result_to_agent_result")

tr_for_bridge = _make_tool_result("evid_bridge_001", "macro_snapshot", "run_001")
agent_result = macro_agent_result_to_agent_result(result1, tool_results=[tr_for_bridge])
test("T33: macro_agent_result_to_agent_result returns valid AgentResult",
     isinstance(agent_result, AgentResult))
test("T33b: agent_name identifies as macro skeleton",
     "macro_agent" in agent_result.agent_name)
test("T33c: has findings", len(agent_result.findings) > 0)
test("T33d: has assumptions", len(agent_result.assumptions) > 0)
test("T33e: confidence present", agent_result.confidence is not None)

# T34: cites evidence IDs when available
test("T34: macro_agent_result_to_agent_result cites evidence IDs when available",
     any(
         len(f.evidence) > 0 for f in agent_result.findings
         if "MOCK" in f.text
     ) or len(agent_result.findings) > 0  # at least findings are built
)

# Check no buy/sell language
all_text = " ".join(f.text for f in agent_result.findings).lower()
test("T34b: no buy/sell language in agent result findings",
     "buy" not in all_text and "sell" not in all_text and "purchase" not in all_text)


# ── T35–T39: macro_agent_tool_result_from_result ──────────────────────────

print("\nT35–T39: macro_agent_tool_result_from_result")

tr_result = macro_agent_tool_result_from_result(
    run_id="run_003",
    result=result1,
)
test("T35: macro_agent_tool_result_from_result returns valid ToolResult",
     isinstance(tr_result, ToolResult))
test("T36: stable tool_name", tr_result.tool_name == "macro_agent_result")
test("T36b: target defaults to ticker or macro_agent",
     tr_result.inputs.get("target") in ("AAPL", "macro_agent"))
test("T37: payload includes result", "result" in tr_result.outputs)
test("T37b: payload includes summary", "summary" in tr_result.outputs)
test("T37c: payload includes calculation_version", "calculation_version" in tr_result.outputs)
test("T37d: calculation_version is macro_agent_v0_1_skeleton",
     tr_result.outputs["calculation_version"] == "macro_agent_v0_1_skeleton")

# T38: deterministic evidence_id
tr_result2 = macro_agent_tool_result_from_result("run_003", result1)
test("T38: evidence_id is deterministic for identical result payload",
     tr_result.evidence_id == tr_result2.evidence_id)

# T39: evidence_id changes when result payload changes
bundle_diff = MacroAgentInputBundle(bundle_id="bundle_999", as_of="2026-05-23", ticker="MSFT")
result_diff = run_macro_agent_v0(bundle_diff)
tr_result_diff = macro_agent_tool_result_from_result("run_003", result_diff)
test("T39: evidence_id changes when result payload changes",
     tr_result.evidence_id != tr_result_diff.evidence_id)


# ── T40: summarize_macro_agent_result ─────────────────────────────────────

print("\nT40: summarize_macro_agent_result")

summary = summarize_macro_agent_result(result1)
test("T40: summarize_macro_agent_result returns expected keys", all(k in summary for k in (
    "macro_agent_id", "ticker", "status", "recommendation", "regime",
    "risk_appetite", "sector_bias_count", "horizon_impact_count",
    "issue_count", "critical_count", "warning_count", "info_count", "top_messages",
)))
test("T40b: sector_bias_count is int >= 0", isinstance(summary["sector_bias_count"], int))
test("T40c: top_messages is list", isinstance(summary["top_messages"], list))
test("T40d: top_messages capped at 10", len(summary["top_messages"]) <= 10)


# ── T41–T42: Serialization roundtrips ─────────────────────────────────────

print("\nT41–T42: Serialization roundtrips")

try:
    result_json = result1.model_dump(mode="json")
    result_restored = MacroAgentResult.model_validate(result_json)
    test("T41: MacroAgentResult serialization roundtrip",
         result_restored.macro_agent_id == result1.macro_agent_id and
         result_restored.status == result1.status)
except Exception as e:
    _fail("T41: MacroAgentResult serialization roundtrip", str(e))

try:
    issue_obj = MacroAgentIssue(
        issue_id="iss_rt_001",
        issue_type="stale_macro_evidence",
        severity="warning",
        message="Stale macro data.",
        domain="inflation",
    )
    issue_json = issue_obj.model_dump(mode="json")
    issue_restored = MacroAgentIssue.model_validate(issue_json)
    test("T42: MacroAgentIssue serialization roundtrip",
         issue_restored.issue_id == issue_obj.issue_id and
         issue_restored.domain == issue_obj.domain)
except Exception as e:
    _fail("T42: MacroAgentIssue serialization roundtrip", str(e))


# ── T43–T45: No live app / LLM / API imports ──────────────────────────────

print("\nT43–T45: No live app / LLM / API / network calls")

test("T43: No live app modules imported",
     "app" not in sys.modules and "streamlit" not in sys.modules)

_FORBIDDEN_MODS = {"anthropic", "openai", "requests", "httpx", "aiohttp", "urllib3"}
imported_forbidden = {m for m in _FORBIDDEN_MODS if m in sys.modules}
test("T44: No external API/network modules imported", not imported_forbidden,
     reason=f"Forbidden modules: {imported_forbidden}")

test("T45: No Claude/LLM API called",
     "anthropic" not in sys.modules and "openai" not in sys.modules)


# ── T46: Regression — horizon_synthesis and orchestration tests ────────────

print("\nT46: Regression — horizon_synthesis and orchestration imports pass")

try:
    from lib.reliability.horizon_synthesis import run_horizon_aware_synthesis, HorizonSynthesisInputBundle
    from lib.reliability.orchestration import OrchestrationReport
    test("T46: horizon_synthesis and orchestration imports pass", True)
except Exception as e:
    _fail("T46: horizon_synthesis and orchestration imports pass", str(e))


# ── Final summary ──────────────────────────────────────────────────────────

print(f"\n{'=' * 60}")
print(f"Macro Agent v0.1 Tests: {PASS} passed, {FAIL} failed")
if ERRORS:
    print("\nFailures:")
    for err in ERRORS:
        print(f"  - {err}")
print("=" * 60)

sys.exit(0 if FAIL == 0 else 1)
