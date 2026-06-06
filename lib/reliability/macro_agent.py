"""
lib/reliability/macro_agent.py

Phase 3C: Macro Agent v0.1 Skeleton.

Design principles:
  - Standalone, deterministic, offline.
  - No live LLM calls, no live data fetching, no app integration.
  - Consumes macro ToolResults / MacroSnapshot artifacts (Phase 2C) and
    validation/staleness/critic artifacts (Phase 2H–2J) to produce
    structured macro regime, risk appetite, sector bias, horizon impact,
    and macro agent result outputs.
  - Does NOT import from app.py, pages/*, lib/llm_orchestrator.py, or any
    live workflow module.
  - Does NOT produce investment advice, buy/sell recommendations, or
    individual security recommendations.
  - Mock/dry-run only; all outputs are explicitly evidence-aware.
  - All rule-based inference is conservative; unknown/mixed is acceptable.

See docs/reliability_phase_3c_macro_agent_v0_1_skeleton.md for design.

Disclaimer: All outputs are for research and educational purposes only.
They do not constitute investment advice. Markets involve risk.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lib.reliability.adapters import make_evidence_id, stable_hash_payload
from lib.reliability.critic import CriticIssue, CriticResult
from lib.reliability.schemas import (
    AgentConfidence,
    AgentResult,
    Assumption,
    EvidenceRef,
    Finding,
    Risk,
    ToolResult,
)
from lib.reliability.staleness import StalenessFinding, StalenessReport
from lib.reliability.validation_aggregator import (
    AggregatedValidationItem,
    ValidationAggregate,
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Literal type aliases (enums)
# ---------------------------------------------------------------------------

MacroRegimeType = Literal[
    "risk_on",
    "risk_off",
    "neutral",
    "late_cycle",
    "early_cycle",
    "recessionary",
    "inflationary",
    "disinflationary",
    "liquidity_tightening",
    "liquidity_easing",
    "mixed",
    "insufficient_evidence",
    "unknown",
]

MacroRiskAppetite = Literal[
    "high",
    "moderate",
    "low",
    "defensive",
    "insufficient_evidence",
    "unknown",
]

MacroSectorBiasDirection = Literal[
    "overweight",
    "underweight",
    "neutral",
    "avoid",
    "insufficient_evidence",
    "unknown",
]

MacroHorizonImpactDirection = Literal[
    "supportive",
    "headwind",
    "neutral",
    "mixed",
    "insufficient_evidence",
    "unknown",
]

MacroAgentStatus = Literal[
    "pass",
    "pass_with_warnings",
    "fail",
    "insufficient_evidence",
    "unknown",
]

MacroAgentRecommendation = Literal[
    "proceed_to_horizon_synthesis",
    "revise",
    "reject",
    "needs_more_evidence",
    "no_action",
    "unknown",
]

MacroAgentIssueType = Literal[
    "missing_macro_evidence",
    "stale_macro_evidence",
    "conflicting_macro_signal",
    "unsupported_macro_claim",
    "validation_issue",
    "critic_issue",
    "horizon_mismatch",
    "missing_assumption",
    "overconfidence",
    "other",
]

MacroSignalDomain = Literal[
    "rates",
    "inflation",
    "growth",
    "liquidity",
    "credit",
    "breadth",
    "volatility",
    "currency",
    "commodities",
    "employment",
    "policy",
    "unknown",
]

MacroIssueSeverity = Literal["critical", "warning", "info"]


# ---------------------------------------------------------------------------
# Private constants
# ---------------------------------------------------------------------------

_MACRO_AGENT_TOOL_NAME: str = "macro_agent_result"
_MACRO_AGENT_METRIC_GROUP: str = "macro_agent_result"

# Keywords for signal domain inference (checked in order)
_DOMAIN_KEYWORDS: dict[MacroSignalDomain, list[str]] = {
    "rates": ["rate", "rates", "yield", "fed", "funds", "treasury", "bond", "fomc_rate"],
    "inflation": ["cpi", "inflation", "pce", "deflat", "price_level", "core_cpi", "core_pce"],
    "growth": ["gdp", "growth", "pmi", "ism", "manufacturing", "services", "output", "expansion", "contraction"],
    "liquidity": ["liquidity", "m2", "qt", "qe", "reserve", "balance_sheet", "money_supply"],
    "credit": ["credit", "spread", "hy", "ig", "high_yield", "investment_grade", "default", "cds"],
    "breadth": ["breadth", "advance_decline", "new_highs", "new_lows", "market_breadth", "ad_line"],
    "volatility": ["vix", "volatility", "vol", "realized_vol", "implied_vol"],
    "currency": ["dollar", "dxy", "fx", "currency", "eur", "usd", "exchange_rate"],
    "commodities": ["oil", "commodity", "commodities", "gold", "energy", "metals", "wti", "brent"],
    "employment": ["payroll", "unemployment", "jobs", "nfp", "labor", "hire", "jobless", "claims"],
    "policy": ["policy", "fomc", "fiscal", "stimulus", "budget", "deficit", "congress", "fed_policy"],
}

# Macro ToolResult tool_name keywords that identify macro evidence
_MACRO_TOOL_KEYWORDS: list[str] = [
    "macro", "rates", "inflation", "growth", "liquidity", "credit_spread",
    "volatility", "market_breadth", "yield_curve", "macro_regime", "macro_snapshot",
]

# ValidationItemType → MacroAgentIssueType
_VALIDATION_TYPE_MAP: dict[str, MacroAgentIssueType] = {
    "stale_data": "stale_macro_evidence",
    "missing_data": "missing_macro_evidence",
    "evidence_binding": "unsupported_macro_claim",
    "unsupported": "unsupported_macro_claim",
    "risk_limit": "validation_issue",
    "safety": "validation_issue",
    "schema": "validation_issue",
    "mismatch": "conflicting_macro_signal",
    "duplicate_data": "other",
    "calculation": "validation_issue",
    "provenance": "missing_macro_evidence",
    "other": "other",
}

# CriticIssueType → MacroAgentIssueType
_CRITIC_TYPE_MAP: dict[str, MacroAgentIssueType] = {
    "overconfidence": "overconfidence",
    "missing_risk": "missing_assumption",
    "missing_assumption": "missing_assumption",
    "conflicting_evidence": "conflicting_macro_signal",
    "stale_evidence": "stale_macro_evidence",
    "unsupported_claim": "unsupported_macro_claim",
    "weak_evidence": "missing_macro_evidence",
    "validation_failure": "validation_issue",
    "numeric_claim_issue": "unsupported_macro_claim",
    "scope_violation": "other",
    "safety_concern": "other",
    "other": "other",
}

# StalenessStatus → MacroAgentIssueType
_STALENESS_STATUS_MAP: dict[str, MacroAgentIssueType] = {
    "stale": "stale_macro_evidence",
    "expired": "stale_macro_evidence",
    "near_stale": "stale_macro_evidence",
    "unknown": "missing_macro_evidence",
    "fresh": "other",
}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class MacroAgentIssue(BaseModel):
    """One structured issue raised by the Macro Agent."""

    model_config = ConfigDict(extra="forbid")

    issue_id: str = Field(min_length=1)
    issue_type: MacroAgentIssueType
    severity: MacroIssueSeverity = "warning"
    message: str = Field(min_length=1)
    domain: MacroSignalDomain = "unknown"
    related_id: Optional[str] = None
    evidence_id: Optional[str] = None
    field_path: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "MacroAgentIssue":
        for fn in ("issue_id", "message"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


class MacroSignalSummary(BaseModel):
    """Summary of macro signals within one domain."""

    model_config = ConfigDict(extra="forbid")

    domain: MacroSignalDomain
    direction: MacroHorizonImpactDirection = "unknown"
    strength: str = "unknown"
    evidence_ids: list[str] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)
    stale: bool = False
    contested: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class MacroRegimeAssessment(BaseModel):
    """Macro regime assessment derived from signal summaries."""

    model_config = ConfigDict(extra="forbid")

    regime: MacroRegimeType = "unknown"
    confidence: str = "unknown"
    risk_appetite: MacroRiskAppetite = "unknown"
    signal_summaries: list[MacroSignalSummary] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    issues: list[MacroAgentIssue] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MacroSectorBias(BaseModel):
    """Broad sector bias based on macro regime (not individual security recommendation)."""

    model_config = ConfigDict(extra="forbid")

    sector: str = Field(min_length=1)
    bias: MacroSectorBiasDirection = "unknown"
    rationale: Optional[str] = None
    supporting_domains: list[MacroSignalDomain] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    issues: list[MacroAgentIssue] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MacroHorizonImpact(BaseModel):
    """Macro impact assessment for a specific investment horizon."""

    model_config = ConfigDict(extra="forbid")

    horizon: str = Field(min_length=1)
    impact: MacroHorizonImpactDirection = "unknown"
    confidence: str = "unknown"
    rationale: Optional[str] = None
    evidence_ids: list[str] = Field(default_factory=list)
    issues: list[MacroAgentIssue] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MacroAgentResult(BaseModel):
    """
    Full result from the Macro Agent v0.1 skeleton.

    Status and recommendation are auto-normalised from issues.

    Normalisation:
      - fail if any critical issues exist.
      - pass_with_warnings if any warning issues exist (no criticals).
      - insufficient_evidence if no regime assessment or key evidence missing.
      - pass otherwise.
      - recommendation follows status.
    """

    model_config = ConfigDict(extra="forbid")

    macro_agent_id: str = Field(min_length=1)
    schema_version: str = "1.0"
    as_of: str = Field(min_length=1)
    ticker: Optional[str] = None
    status: MacroAgentStatus = "unknown"
    recommendation: MacroAgentRecommendation = "unknown"
    regime_assessment: Optional[MacroRegimeAssessment] = None
    sector_biases: list[MacroSectorBias] = Field(default_factory=list)
    horizon_impacts: list[MacroHorizonImpact] = Field(default_factory=list)
    issues: list[MacroAgentIssue] = Field(default_factory=list)
    validation_aggregate: Optional[ValidationAggregate] = None
    staleness_report: Optional[StalenessReport] = None
    critic_result: Optional[CriticResult] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "MacroAgentResult":
        for fn in ("macro_agent_id", "as_of"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _normalize_status_recommendation(self) -> "MacroAgentResult":
        issues = self.issues
        critical_count = sum(1 for i in issues if i.severity == "critical")
        warning_count = sum(1 for i in issues if i.severity == "warning")

        missing_evidence = any(
            i.issue_type == "missing_macro_evidence" for i in issues
        )
        no_regime = (
            self.regime_assessment is None
            or self.regime_assessment.regime in ("insufficient_evidence", "unknown")
        )

        if critical_count > 0:
            self.status = "fail"
            self.recommendation = "reject"
        elif warning_count > 0 and not (missing_evidence and no_regime):
            self.status = "pass_with_warnings"
            self.recommendation = "revise"
        elif missing_evidence and no_regime:
            self.status = "insufficient_evidence"
            self.recommendation = "needs_more_evidence"
        elif warning_count > 0:
            self.status = "pass_with_warnings"
            self.recommendation = "revise"
        else:
            self.status = "pass"
            self.recommendation = "proceed_to_horizon_synthesis"
        return self


class MacroAgentInputBundle(BaseModel):
    """Input bundle for the Macro Agent v0.1 skeleton."""

    model_config = ConfigDict(extra="forbid")

    bundle_id: str = Field(min_length=1)
    as_of: str = Field(min_length=1)
    ticker: Optional[str] = None
    macro_snapshot: Optional[Any] = None
    tool_results: list[ToolResult] = Field(default_factory=list)
    validation_aggregate: Optional[ValidationAggregate] = None
    staleness_report: Optional[StalenessReport] = None
    critic_result: Optional[CriticResult] = None
    horizon_synthesis_report: Optional[Any] = None
    orchestration_report: Optional[Any] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "MacroAgentInputBundle":
        for fn in ("bundle_id", "as_of"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def make_macro_agent_issue_id(
    issue_type: str,
    message: str,
    domain: str = "unknown",
    related_id: Optional[str] = None,
    evidence_id: Optional[str] = None,
    field_path: Optional[str] = None,
) -> str:
    """
    Build a deterministic, stable issue_id for a MacroAgentIssue.

    Same inputs always produce the same ID.
    Different issue_type / message / domain / related_id / evidence_id / field_path
    produce a different ID.
    """
    payload = {
        "issue_type": issue_type,
        "message": message,
        "domain": domain,
        "related_id": related_id or "",
        "evidence_id": evidence_id or "",
        "field_path": field_path or "",
    }
    hash_suffix = stable_hash_payload(payload, length=16)
    return f"macro_issue:{issue_type}:{hash_suffix}"


def make_macro_agent_id(
    bundle_id: str,
    as_of: str,
    ticker: Optional[str] = None,
) -> str:
    """Build a deterministic, stable macro_agent_id."""
    payload = {
        "bundle_id": bundle_id,
        "as_of": as_of,
        "ticker": ticker or "",
    }
    hash_suffix = stable_hash_payload(payload, length=16)
    ticker_part = f":{ticker}" if ticker else ""
    return f"macro_agent:{bundle_id}{ticker_part}:{hash_suffix}"


def infer_macro_signal_domain_from_path(
    field_path_or_name: Optional[str],
) -> MacroSignalDomain:
    """
    Deterministically map a field path or name to a MacroSignalDomain.

    Uses keyword matching in order of specificity.
    Returns 'unknown' if no keywords match.
    """
    if not field_path_or_name:
        return "unknown"
    lower = field_path_or_name.lower()
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return domain
    return "unknown"


def _is_macro_tool_result(tr: ToolResult) -> bool:
    """Return True if this ToolResult looks like macro evidence."""
    tool_lower = tr.tool_name.lower()
    return any(kw in tool_lower for kw in _MACRO_TOOL_KEYWORDS)


def extract_macro_evidence_ids(
    macro_snapshot: Optional[Any] = None,
    tool_results: Optional[list[ToolResult]] = None,
) -> list[str]:
    """
    Collect evidence IDs from macro ToolResults and macro snapshot metadata.

    Deterministic order: snapshot-derived IDs first, then ToolResult IDs.
    Does not fabricate evidence. Does not mutate inputs.
    """
    ids: list[str] = []
    seen: set[str] = set()

    # Extract from macro snapshot metadata if it has an evidence_id attribute
    if macro_snapshot is not None:
        snap_eid = getattr(macro_snapshot, "evidence_id", None)
        if snap_eid and snap_eid not in seen:
            ids.append(snap_eid)
            seen.add(snap_eid)

    # Extract from ToolResults that appear to be macro-related
    if tool_results:
        for tr in tool_results:
            if _is_macro_tool_result(tr):
                eid = tr.evidence_id
                if eid and eid not in seen:
                    ids.append(eid)
                    seen.add(eid)

    return ids


def summarize_macro_signals(
    macro_snapshot: Optional[Any] = None,
    tool_results: Optional[list[ToolResult]] = None,
    staleness_report: Optional[StalenessReport] = None,
    validation_aggregate: Optional[ValidationAggregate] = None,
    critic_result: Optional[CriticResult] = None,
) -> list[MacroSignalSummary]:
    """
    Deterministically summarize macro signals from available evidence.

    Returns [] if no macro evidence exists. No data fetching. No LLM.
    Marks stale=True if staleness findings relate to macro.
    Marks contested=True if critic/validation issues relate to macro.
    """
    # Collect macro ToolResults
    macro_trs: list[ToolResult] = []
    if tool_results:
        for tr in tool_results:
            if _is_macro_tool_result(tr):
                macro_trs.append(tr)

    # Also include snapshot indicators if available
    snapshot_indicators: list[Any] = []
    if macro_snapshot is not None:
        snapshot_indicators = getattr(macro_snapshot, "indicators", []) or []

    if not macro_trs and not snapshot_indicators:
        return []

    # Build domain → evidence_ids mapping
    domain_evidence: dict[str, list[str]] = {}
    domain_key_points: dict[str, list[str]] = {}

    for tr in macro_trs:
        # Infer domain from tool_name
        domain = infer_macro_signal_domain_from_path(tr.tool_name)
        if domain not in domain_evidence:
            domain_evidence[domain] = []
            domain_key_points[domain] = []
        if tr.evidence_id not in domain_evidence[domain]:
            domain_evidence[domain].append(tr.evidence_id)
        domain_key_points[domain].append(
            f"tool_result: {tr.tool_name} (evidence_id={tr.evidence_id[:16]}...)"
        )

    # Include snapshot indicators
    for ind in snapshot_indicators:
        cat = getattr(ind, "category", None) or ""
        # Map macro category → signal domain
        domain = infer_macro_signal_domain_from_path(cat)
        if domain not in domain_evidence:
            domain_evidence[domain] = []
            domain_key_points[domain] = []
        name = getattr(ind, "name", "")
        value = getattr(ind, "value", "")
        as_of = getattr(ind, "as_of", "")
        domain_key_points[domain].append(
            f"indicator: {name}={value} (as_of={as_of})"
        )

    # Determine stale/contested flags from staleness and validation
    macro_stale_domains: set[str] = set()
    if staleness_report:
        for finding in staleness_report.findings:
            if finding.domain == "macro" and finding.status in ("stale", "expired", "near_stale"):
                # Try to infer which signal domain is stale
                d = infer_macro_signal_domain_from_path(finding.field_path)
                macro_stale_domains.add(d)
                macro_stale_domains.add("unknown")  # flag globally

    macro_contested_domains: set[str] = set()
    if validation_aggregate:
        for item in validation_aggregate.items:
            if item.domain == "macro":
                d = infer_macro_signal_domain_from_path(item.field_path)
                macro_contested_domains.add(d)
    if critic_result:
        for issue in critic_result.issues:
            d = infer_macro_signal_domain_from_path(issue.field_path)
            if d != "unknown":
                macro_contested_domains.add(d)

    summaries: list[MacroSignalSummary] = []
    for domain, eids in domain_evidence.items():
        stale = (domain in macro_stale_domains) or ("unknown" in macro_stale_domains and macro_stale_domains)
        contested = domain in macro_contested_domains
        summaries.append(MacroSignalSummary(
            domain=domain,  # type: ignore[arg-type]
            direction="unknown",
            strength="unknown",
            evidence_ids=list(eids),
            key_points=list(domain_key_points.get(domain, [])),
            stale=stale,
            contested=contested,
        ))

    return summaries


def infer_macro_regime(
    signal_summaries: list[MacroSignalSummary],
    validation_aggregate: Optional[ValidationAggregate] = None,
    staleness_report: Optional[StalenessReport] = None,
    critic_result: Optional[CriticResult] = None,
) -> MacroRegimeAssessment:
    """
    Deterministic, conservative, rule-based macro regime inference.

    No LLM. No data fetching. Returns insufficient_evidence / unknown
    when evidence is incomplete.
    """
    issues: list[MacroAgentIssue] = []
    all_evidence_ids: list[str] = []
    for s in signal_summaries:
        all_evidence_ids.extend(s.evidence_ids)

    # No signals → insufficient evidence
    if not signal_summaries:
        eid = make_macro_agent_issue_id(
            "missing_macro_evidence",
            "No macro signal summaries available. Cannot infer regime.",
        )
        issues.append(MacroAgentIssue(
            issue_id=eid,
            issue_type="missing_macro_evidence",
            severity="warning",
            message="No macro signal summaries available. Regime cannot be determined.",
            domain="unknown",
        ))
        return MacroRegimeAssessment(
            regime="insufficient_evidence",
            confidence="insufficient_evidence",
            risk_appetite="insufficient_evidence",
            signal_summaries=[],
            supporting_evidence_ids=[],
            issues=issues,
        )

    # Count stale and contested signals
    stale_count = sum(1 for s in signal_summaries if s.stale)
    contested_count = sum(1 for s in signal_summaries if s.contested)
    total = len(signal_summaries)

    if stale_count > 0:
        sid = make_macro_agent_issue_id(
            "stale_macro_evidence",
            f"{stale_count}/{total} macro signal domains are stale.",
        )
        issues.append(MacroAgentIssue(
            issue_id=sid,
            issue_type="stale_macro_evidence",
            severity="warning",
            message=f"{stale_count}/{total} macro signal domain(s) have stale evidence. Regime confidence reduced.",
        ))

    if contested_count > 0:
        cid = make_macro_agent_issue_id(
            "conflicting_macro_signal",
            f"{contested_count}/{total} macro signal domains are contested.",
        )
        issues.append(MacroAgentIssue(
            issue_id=cid,
            issue_type="conflicting_macro_signal",
            severity="warning",
            message=f"{contested_count}/{total} macro signal domain(s) are contested by validation/critic.",
        ))

    # Extract domains present
    domains_present: set[str] = {s.domain for s in signal_summaries}

    # If most signals are stale or contested, fall back to mixed/low confidence
    high_uncertainty = (stale_count + contested_count) >= max(1, total * 0.5)

    # Derive regime from heuristic domain rules
    # These are conservative rules only; unknown/mixed is acceptable when evidence is incomplete.
    regime: MacroRegimeType = "unknown"
    risk_appetite: MacroRiskAppetite = "unknown"
    confidence: str = "low"

    has_liquidity = "liquidity" in domains_present
    has_breadth = "breadth" in domains_present
    has_volatility = "volatility" in domains_present
    has_credit = "credit" in domains_present
    has_inflation = "inflation" in domains_present
    has_growth = "growth" in domains_present
    has_rates = "rates" in domains_present

    if high_uncertainty:
        regime = "mixed"
        risk_appetite = "unknown"
        confidence = "low"
    elif has_liquidity and has_breadth and has_volatility:
        # Simplified heuristic: presence of these domains without explicit signal values
        # → assume moderate/neutral regime since we don't have actual data values
        regime = "neutral"
        risk_appetite = "moderate"
        confidence = "low"
    elif has_credit and has_growth:
        # Credit + growth stress signals → potentially risk_off
        regime = "risk_off"
        risk_appetite = "defensive"
        confidence = "low"
    elif has_inflation and has_rates:
        # Inflation + rates → inflationary tightening regime
        regime = "inflationary"
        risk_appetite = "low"
        confidence = "low"
    elif has_growth:
        # Only growth data
        regime = "neutral"
        risk_appetite = "moderate"
        confidence = "low"
    elif len(domains_present) >= 3:
        regime = "mixed"
        risk_appetite = "unknown"
        confidence = "low"
    else:
        regime = "insufficient_evidence"
        risk_appetite = "insufficient_evidence"
        confidence = "insufficient_evidence"
        eid = make_macro_agent_issue_id(
            "missing_macro_evidence",
            "Insufficient macro signal domains to determine regime.",
        )
        issues.append(MacroAgentIssue(
            issue_id=eid,
            issue_type="missing_macro_evidence",
            severity="warning",
            message="Insufficient macro signal domains to determine regime. More evidence needed.",
        ))

    return MacroRegimeAssessment(
        regime=regime,
        confidence=confidence,
        risk_appetite=risk_appetite,
        signal_summaries=list(signal_summaries),
        supporting_evidence_ids=list(dict.fromkeys(all_evidence_ids)),
        issues=issues,
    )


def derive_macro_sector_biases(
    regime_assessment: MacroRegimeAssessment,
    signal_summaries: list[MacroSignalSummary],
) -> list[MacroSectorBias]:
    """
    Deterministic mock sector bias mapping based on regime.

    Returns broad sector bias only — not individual security recommendations.
    No investment advice. No buy/sell language.
    If insufficient evidence, returns biases with insufficient_evidence direction.
    """
    regime = regime_assessment.regime
    evidence_ids: list[str] = list(dict.fromkeys(regime_assessment.supporting_evidence_ids))

    if regime in ("insufficient_evidence", "unknown"):
        insufficient_issue = MacroAgentIssue(
            issue_id=make_macro_agent_issue_id(
                "missing_macro_evidence",
                "Sector bias cannot be derived: insufficient macro regime evidence.",
            ),
            issue_type="missing_macro_evidence",
            severity="warning",
            message="Sector bias cannot be derived without a determined macro regime.",
        )
        return [
            MacroSectorBias(
                sector="all_sectors",
                bias="insufficient_evidence",
                rationale="Macro regime is undetermined; sector bias cannot be assessed.",
                evidence_ids=evidence_ids,
                issues=[insufficient_issue],
            )
        ]

    biases: list[MacroSectorBias] = []

    if regime in ("risk_on", "liquidity_easing", "early_cycle"):
        biases.extend([
            MacroSectorBias(
                sector="growth_equities",
                bias="neutral",
                rationale=(
                    "Mock assessment: risk_on / liquidity_easing conditions are broadly "
                    "consistent with neutral-to-positive macro backdrop for growth sectors. "
                    "Not an investment recommendation."
                ),
                supporting_domains=["liquidity", "breadth"],
                evidence_ids=evidence_ids,
            ),
            MacroSectorBias(
                sector="cyclicals",
                bias="neutral",
                rationale=(
                    "Mock assessment: early-cycle / risk_on regimes historically align with "
                    "cyclical sector participation. Not an investment recommendation."
                ),
                supporting_domains=["growth", "breadth"],
                evidence_ids=evidence_ids,
            ),
            MacroSectorBias(
                sector="defensives",
                bias="underweight",
                rationale=(
                    "Mock assessment: risk_on conditions reduce relative macro tailwinds "
                    "for defensive sectors. Not an investment recommendation."
                ),
                supporting_domains=["volatility", "breadth"],
                evidence_ids=evidence_ids,
            ),
        ])

    elif regime in ("risk_off", "recessionary", "liquidity_tightening", "late_cycle"):
        biases.extend([
            MacroSectorBias(
                sector="defensives",
                bias="neutral",
                rationale=(
                    "Mock assessment: risk_off / recessionary conditions are broadly "
                    "consistent with neutral-to-supportive macro backdrop for defensive sectors. "
                    "Not an investment recommendation."
                ),
                supporting_domains=["volatility", "credit"],
                evidence_ids=evidence_ids,
            ),
            MacroSectorBias(
                sector="cyclicals",
                bias="underweight",
                rationale=(
                    "Mock assessment: recessionary / risk_off conditions reduce macro "
                    "tailwinds for cyclicals. Not an investment recommendation."
                ),
                supporting_domains=["growth", "credit"],
                evidence_ids=evidence_ids,
            ),
            MacroSectorBias(
                sector="growth_equities",
                bias="underweight",
                rationale=(
                    "Mock assessment: liquidity tightening reduces macro tailwinds for "
                    "long-duration growth equities. Not an investment recommendation."
                ),
                supporting_domains=["rates", "liquidity"],
                evidence_ids=evidence_ids,
            ),
        ])

    elif regime in ("inflationary", "disinflationary"):
        biases.extend([
            MacroSectorBias(
                sector="energy_materials",
                bias="neutral",
                rationale=(
                    "Mock assessment: inflationary conditions are broadly consistent with "
                    "neutral-to-positive macro backdrop for energy/materials sectors. "
                    "Not an investment recommendation."
                ),
                supporting_domains=["inflation", "commodities"],
                evidence_ids=evidence_ids,
            ),
            MacroSectorBias(
                sector="long_duration_growth",
                bias="underweight",
                rationale=(
                    "Mock assessment: inflation / rate tightening reduces macro tailwinds "
                    "for long-duration growth equities. Not an investment recommendation."
                ),
                supporting_domains=["rates", "inflation"],
                evidence_ids=evidence_ids,
            ),
        ])

    else:
        # neutral / mixed / other
        biases.append(MacroSectorBias(
            sector="all_sectors",
            bias="neutral",
            rationale=(
                f"Mock assessment: regime={regime!r} yields neutral macro sector bias. "
                "Insufficient signal differentiation for sector-specific assessment. "
                "Not an investment recommendation."
            ),
            evidence_ids=evidence_ids,
        ))

    return biases


def derive_macro_horizon_impacts(
    regime_assessment: MacroRegimeAssessment,
    signal_summaries: list[MacroSignalSummary],
) -> list[MacroHorizonImpact]:
    """
    Derive macro impact assessments for short_term, medium_term, long_term horizons.

    Always produces three horizon impact records.
    If insufficient evidence, all horizons indicate insufficient_evidence.
    No investment advice.
    """
    regime = regime_assessment.regime
    evidence_ids: list[str] = list(dict.fromkeys(regime_assessment.supporting_evidence_ids))
    domains: set[str] = {s.domain for s in signal_summaries}
    issues_ref = list(regime_assessment.issues)

    if regime in ("insufficient_evidence", "unknown"):
        return [
            MacroHorizonImpact(
                horizon=h,
                impact="insufficient_evidence",
                confidence="insufficient_evidence",
                rationale="Macro regime is undetermined; horizon impact cannot be assessed.",
                evidence_ids=evidence_ids,
            )
            for h in ("short_term", "medium_term", "long_term")
        ]

    # Short-term: most sensitive to volatility / breadth / liquidity
    short_sensitive_domains = {"volatility", "breadth", "liquidity", "credit"}
    short_coverage = len(short_sensitive_domains & domains)
    if regime in ("risk_off", "recessionary", "liquidity_tightening"):
        short_impact: MacroHorizonImpactDirection = "headwind"
        short_conf = "low"
    elif regime in ("risk_on", "liquidity_easing", "early_cycle"):
        short_impact = "supportive"
        short_conf = "low"
    else:
        short_impact = "mixed" if short_coverage > 0 else "insufficient_evidence"
        short_conf = "low"

    # Medium-term: most sensitive to growth / inflation / rates
    medium_sensitive_domains = {"growth", "inflation", "rates", "credit"}
    medium_coverage = len(medium_sensitive_domains & domains)
    if regime in ("recessionary", "risk_off"):
        medium_impact: MacroHorizonImpactDirection = "headwind"
        medium_conf = "low"
    elif regime in ("inflationary",):
        medium_impact = "mixed"
        medium_conf = "low"
    elif regime in ("risk_on", "early_cycle", "liquidity_easing"):
        medium_impact = "supportive"
        medium_conf = "low"
    else:
        medium_impact = "mixed" if medium_coverage > 0 else "insufficient_evidence"
        medium_conf = "low"

    # Long-term: most sensitive to structural growth / policy / liquidity regime
    long_sensitive_domains = {"policy", "growth", "liquidity", "rates"}
    long_coverage = len(long_sensitive_domains & domains)
    if regime in ("recessionary",):
        long_impact: MacroHorizonImpactDirection = "headwind"
        long_conf = "low"
    elif regime in ("liquidity_easing", "early_cycle"):
        long_impact = "supportive"
        long_conf = "low"
    elif regime in ("liquidity_tightening", "inflationary"):
        long_impact = "mixed"
        long_conf = "low"
    else:
        long_impact = "mixed" if long_coverage > 0 else "insufficient_evidence"
        long_conf = "low"

    return [
        MacroHorizonImpact(
            horizon="short_term",
            impact=short_impact,
            confidence=short_conf,
            rationale=(
                f"Short-term macro impact ({regime!r}): "
                "sensitive to volatility, breadth, and liquidity signals. "
                "Not an investment recommendation."
            ),
            evidence_ids=evidence_ids,
        ),
        MacroHorizonImpact(
            horizon="medium_term",
            impact=medium_impact,
            confidence=medium_conf,
            rationale=(
                f"Medium-term macro impact ({regime!r}): "
                "sensitive to growth, inflation, and rates signals. "
                "Not an investment recommendation."
            ),
            evidence_ids=evidence_ids,
        ),
        MacroHorizonImpact(
            horizon="long_term",
            impact=long_impact,
            confidence=long_conf,
            rationale=(
                f"Long-term macro impact ({regime!r}): "
                "sensitive to structural growth, policy, and liquidity regime. "
                "Not an investment recommendation."
            ),
            evidence_ids=evidence_ids,
        ),
    ]


def issue_from_validation_item_for_macro(
    item: AggregatedValidationItem,
) -> MacroAgentIssue:
    """
    Convert an AggregatedValidationItem into a MacroAgentIssue.

    Preserves evidence_id, field_path, object_id/related_id.
    Infers domain from field_path/message.
    """
    issue_type: MacroAgentIssueType = _VALIDATION_TYPE_MAP.get(
        item.item_type, "other"
    )
    domain = infer_macro_signal_domain_from_path(
        item.field_path or item.message
    )
    severity: MacroIssueSeverity
    if item.severity == "critical":
        severity = "critical"
    elif item.severity == "info":
        severity = "info"
    else:
        severity = "warning"

    issue_id = make_macro_agent_issue_id(
        issue_type=issue_type,
        message=item.message,
        domain=domain,
        related_id=item.object_id,
        evidence_id=item.evidence_id,
        field_path=item.field_path,
    )
    return MacroAgentIssue(
        issue_id=issue_id,
        issue_type=issue_type,
        severity=severity,
        message=item.message,
        domain=domain,
        related_id=item.object_id,
        evidence_id=item.evidence_id,
        field_path=item.field_path,
    )


def issue_from_staleness_finding_for_macro(
    finding: StalenessFinding,
) -> MacroAgentIssue:
    """
    Convert a StalenessFinding into a MacroAgentIssue.

    Preserves evidence_id, field_path, object_id.
    Maps stale/expired/unknown → stale_macro_evidence or missing_macro_evidence.
    """
    issue_type: MacroAgentIssueType = _STALENESS_STATUS_MAP.get(
        finding.status, "other"
    )
    domain = infer_macro_signal_domain_from_path(
        finding.field_path or finding.source_name or finding.message
    )
    severity: MacroIssueSeverity
    if finding.severity == "critical":
        severity = "critical"
    elif finding.severity == "info":
        severity = "info"
    else:
        severity = "warning"

    issue_id = make_macro_agent_issue_id(
        issue_type=issue_type,
        message=finding.message,
        domain=domain,
        related_id=finding.object_id,
        evidence_id=finding.evidence_id,
        field_path=finding.field_path,
    )
    return MacroAgentIssue(
        issue_id=issue_id,
        issue_type=issue_type,
        severity=severity,
        message=finding.message,
        domain=domain,
        related_id=finding.object_id,
        evidence_id=finding.evidence_id,
        field_path=finding.field_path,
    )


def issue_from_critic_issue_for_macro(
    issue: CriticIssue,
) -> MacroAgentIssue:
    """
    Convert a CriticIssue into a MacroAgentIssue.

    Preserves evidence_id, field_path, related target_id.
    Maps critic issue types to macro issue types.
    """
    issue_type: MacroAgentIssueType = _CRITIC_TYPE_MAP.get(
        issue.issue_type, "other"
    )
    domain = infer_macro_signal_domain_from_path(
        issue.field_path or issue.message
    )
    severity: MacroIssueSeverity
    if issue.severity == "critical":
        severity = "critical"
    elif issue.severity == "info":
        severity = "info"
    else:
        severity = "warning"

    issue_id = make_macro_agent_issue_id(
        issue_type=issue_type,
        message=issue.message,
        domain=domain,
        related_id=issue.target_id,
        evidence_id=issue.evidence_id,
        field_path=issue.field_path,
    )
    return MacroAgentIssue(
        issue_id=issue_id,
        issue_type=issue_type,
        severity=severity,
        message=issue.message,
        domain=domain,
        related_id=issue.target_id,
        evidence_id=issue.evidence_id,
        field_path=issue.field_path,
    )


def build_macro_agent_result(
    macro_agent_id: str,
    as_of: str,
    ticker: Optional[str] = None,
    regime_assessment: Optional[MacroRegimeAssessment] = None,
    sector_biases: Optional[list[MacroSectorBias]] = None,
    horizon_impacts: Optional[list[MacroHorizonImpact]] = None,
    validation_aggregate: Optional[ValidationAggregate] = None,
    staleness_report: Optional[StalenessReport] = None,
    critic_result: Optional[CriticResult] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> MacroAgentResult:
    """
    Aggregate issues from nested artifacts and build a MacroAgentResult.

    Status and recommendation are auto-normalised by the model validator.
    Does not mutate inputs.
    """
    all_issues: list[MacroAgentIssue] = []

    # Collect issues from regime assessment
    if regime_assessment:
        all_issues.extend(regime_assessment.issues)

    # Collect issues from sector biases
    for sb in (sector_biases or []):
        all_issues.extend(sb.issues)

    # Collect issues from horizon impacts
    for hi in (horizon_impacts or []):
        all_issues.extend(hi.issues)

    # Convert validation aggregate items to macro issues
    if validation_aggregate:
        for item in validation_aggregate.items:
            all_issues.append(issue_from_validation_item_for_macro(item))

    # Convert staleness findings to macro issues
    if staleness_report:
        for finding in staleness_report.findings:
            if finding.domain == "macro" or finding.domain == "unknown":
                all_issues.append(issue_from_staleness_finding_for_macro(finding))

    # Convert critic issues to macro issues
    if critic_result:
        for critic_issue in critic_result.issues:
            all_issues.append(issue_from_critic_issue_for_macro(critic_issue))

    # De-duplicate by issue_id (first wins)
    seen: set[str] = set()
    deduped: list[MacroAgentIssue] = []
    for issue in all_issues:
        if issue.issue_id not in seen:
            seen.add(issue.issue_id)
            deduped.append(issue)

    return MacroAgentResult(
        macro_agent_id=macro_agent_id,
        as_of=as_of,
        ticker=ticker,
        regime_assessment=regime_assessment,
        sector_biases=list(sector_biases) if sector_biases is not None else [],
        horizon_impacts=list(horizon_impacts) if horizon_impacts is not None else [],
        issues=deduped,
        validation_aggregate=validation_aggregate,
        staleness_report=staleness_report,
        critic_result=critic_result,
        metadata=dict(metadata) if metadata is not None else {},
    )


def run_macro_agent_v0(
    input_bundle: MacroAgentInputBundle,
) -> MacroAgentResult:
    """
    Run the Macro Agent v0.1 skeleton on an input bundle.

    Deterministic. Offline. No LLM. No APIs. No mutation of input bundle.

    Steps:
      1. Extract macro evidence IDs.
      2. Summarize macro signals.
      3. Infer macro regime.
      4. Derive sector biases.
      5. Derive horizon impacts.
      6. Build result.
    """
    macro_agent_id = make_macro_agent_id(
        bundle_id=input_bundle.bundle_id,
        as_of=input_bundle.as_of,
        ticker=input_bundle.ticker,
    )

    signal_summaries = summarize_macro_signals(
        macro_snapshot=input_bundle.macro_snapshot,
        tool_results=list(input_bundle.tool_results),
        staleness_report=input_bundle.staleness_report,
        validation_aggregate=input_bundle.validation_aggregate,
        critic_result=input_bundle.critic_result,
    )

    regime_assessment = infer_macro_regime(
        signal_summaries=signal_summaries,
        validation_aggregate=input_bundle.validation_aggregate,
        staleness_report=input_bundle.staleness_report,
        critic_result=input_bundle.critic_result,
    )

    sector_biases = derive_macro_sector_biases(
        regime_assessment=regime_assessment,
        signal_summaries=signal_summaries,
    )

    horizon_impacts = derive_macro_horizon_impacts(
        regime_assessment=regime_assessment,
        signal_summaries=signal_summaries,
    )

    return build_macro_agent_result(
        macro_agent_id=macro_agent_id,
        as_of=input_bundle.as_of,
        ticker=input_bundle.ticker,
        regime_assessment=regime_assessment,
        sector_biases=sector_biases,
        horizon_impacts=horizon_impacts,
        validation_aggregate=input_bundle.validation_aggregate,
        staleness_report=input_bundle.staleness_report,
        critic_result=input_bundle.critic_result,
        metadata={"bundle_id": input_bundle.bundle_id},
    )


def macro_agent_result_to_agent_result(
    result: MacroAgentResult,
    tool_results: Optional[list[ToolResult]] = None,
) -> AgentResult:
    """
    Bridge MacroAgentResult into the existing constrained AgentResult contract.

    This is mock/dry-run output. Does not invent evidence. Does not generate
    trade recommendations. Does not use buy/sell language.
    If no evidence is available, findings are weak/needs_more_evidence.
    """
    evidence_ids = extract_macro_evidence_ids(
        macro_snapshot=None,
        tool_results=tool_results,
    )
    if result.regime_assessment:
        evidence_ids = list(dict.fromkeys(
            evidence_ids + result.regime_assessment.supporting_evidence_ids
        ))

    # Build findings
    findings: list[Finding] = []

    # Regime finding
    regime = "unknown"
    risk_appetite = "unknown"
    if result.regime_assessment:
        regime = result.regime_assessment.regime
        risk_appetite = result.regime_assessment.risk_appetite

    regime_evidence: list[EvidenceRef] = []
    if evidence_ids:
        for eid in evidence_ids[:3]:
            regime_evidence.append(EvidenceRef(
                evidence_id=eid,
                excerpt=f"Macro evidence supporting regime assessment: {eid[:32]}",
                description="macro_agent_result (dry-run)",
            ))

    findings.append(Finding(
        text=(
            f"[MOCK DRY-RUN] Macro Agent v0.1 regime assessment: regime={regime!r}, "
            f"risk_appetite={risk_appetite!r}, status={result.status!r}. "
            "This is a dry-run skeleton output. Not investment advice."
        ),
        evidence=regime_evidence,
        confidence=0.3 if not evidence_ids else 0.5,
    ))

    # Sector bias finding
    if result.sector_biases:
        bias_summary = "; ".join(
            f"{sb.sector}={sb.bias}" for sb in result.sector_biases[:5]
        )
        findings.append(Finding(
            text=(
                f"[MOCK DRY-RUN] Macro-derived sector bias assessment: {bias_summary}. "
                "These are broad macro-level observations only, not individual security recommendations."
            ),
            evidence=regime_evidence[:1],
            confidence=0.3,
        ))

    # Horizon impact finding
    if result.horizon_impacts:
        horizon_summary = "; ".join(
            f"{hi.horizon}={hi.impact}" for hi in result.horizon_impacts
        )
        findings.append(Finding(
            text=(
                f"[MOCK DRY-RUN] Macro horizon impact: {horizon_summary}. "
                "Not an investment recommendation."
            ),
            evidence=regime_evidence[:1],
            confidence=0.3,
        ))

    # Risks from issues
    risks: list[Risk] = []
    critical_issues = [i for i in result.issues if i.severity == "critical"]
    warning_issues = [i for i in result.issues if i.severity == "warning"][:5]

    for issue in critical_issues[:3]:
        risks.append(Risk(
            name=f"MacroRisk:{issue.issue_type}",
            description=issue.message,
            severity="high",
            evidence=[EvidenceRef(evidence_id=issue.evidence_id, excerpt=issue.message[:100])
                      ] if issue.evidence_id else [],
        ))

    for issue in warning_issues[:3]:
        risks.append(Risk(
            name=f"MacroWarning:{issue.issue_type}",
            description=issue.message,
            severity="medium",
        ))

    # Assumptions
    assumptions: list[Assumption] = [
        Assumption(
            name="macro_agent_dry_run",
            rationale=(
                "This output is produced by the Macro Agent v0.1 skeleton "
                "(mock/dry-run). No live LLM calls, no live data fetching, "
                "no live app integration. Rule-based inference only."
            ),
            value="dry_run",
            source="agent",
            sensitivity="low",
        ),
        Assumption(
            name="regime_inference_method",
            rationale="Regime inferred from deterministic keyword-based rules. Conservative: unknown/mixed acceptable.",
            value="rule_based_v0",
            source="agent",
            sensitivity="medium",
        ),
    ]

    # Confidence
    conf_level: str
    if not evidence_ids:
        conf_level = "low"
        conf_score = 0.2
    elif result.status == "pass":
        conf_level = "medium"
        conf_score = 0.5
    else:
        conf_level = "low"
        conf_score = 0.3

    confidence = AgentConfidence(
        level=conf_level,  # type: ignore[arg-type]
        rationale=(
            f"Macro Agent v0.1 (dry-run): regime={regime!r} "
            f"status={result.status!r} "
            f"evidence_count={len(evidence_ids)}. "
            "Low confidence expected for mock skeleton output."
        ),
        score=conf_score,
    )

    run_id = result.metadata.get("bundle_id", result.macro_agent_id)

    return AgentResult(
        agent_name="macro_agent_v0_skeleton",
        ticker=result.ticker,
        run_id=run_id,
        findings=findings,
        assumptions=assumptions,
        risks=risks,
        confidence=confidence,
    )


def summarize_macro_agent_result(result: MacroAgentResult) -> dict[str, Any]:
    """Return a concise summary dict for a MacroAgentResult."""
    issues = result.issues
    critical_count = sum(1 for i in issues if i.severity == "critical")
    warning_count = sum(1 for i in issues if i.severity == "warning")
    info_count = sum(1 for i in issues if i.severity == "info")
    top_messages = [i.message for i in issues[:10]]

    regime = "unknown"
    risk_appetite = "unknown"
    if result.regime_assessment:
        regime = result.regime_assessment.regime
        risk_appetite = result.regime_assessment.risk_appetite

    return {
        "macro_agent_id": result.macro_agent_id,
        "ticker": result.ticker,
        "status": result.status,
        "recommendation": result.recommendation,
        "regime": regime,
        "risk_appetite": risk_appetite,
        "sector_bias_count": len(result.sector_biases),
        "horizon_impact_count": len(result.horizon_impacts),
        "issue_count": len(issues),
        "critical_count": critical_count,
        "warning_count": warning_count,
        "info_count": info_count,
        "top_messages": top_messages,
    }


def macro_agent_tool_result_from_result(
    run_id: str,
    result: MacroAgentResult,
    target: Optional[str] = None,
    calculation_version: str = "macro_agent_v0_1_skeleton",
) -> ToolResult:
    """
    Wrap a MacroAgentResult into the existing ToolResult model.

    tool_name is stable: "macro_agent_result".
    target defaults to result.ticker if present, else "macro_agent".
    evidence_id is content-sensitive: built from full payload before hashing.
    Does not mutate result.
    """
    effective_target = target or result.ticker or "macro_agent"

    # Build full payload before hashing (content-sensitive evidence_id)
    result_dict = result.model_dump(mode="json")
    summary = summarize_macro_agent_result(result)
    payload: dict[str, Any] = {
        "result": result_dict,
        "summary": summary,
        "calculation_version": calculation_version,
    }

    evidence_id = make_evidence_id(
        run_id=run_id,
        tool_name=_MACRO_AGENT_TOOL_NAME,
        target=effective_target,
        metric_group=_MACRO_AGENT_METRIC_GROUP,
        payload=payload,
    )

    description = (
        f"MacroAgentResult {result.macro_agent_id!r}"
        f" as_of={result.as_of!r}"
        f" status={result.status!r}"
        f" recommendation={result.recommendation!r}"
        f" regime={summary.get('regime', 'unknown')!r}"
    )

    return ToolResult(
        evidence_id=evidence_id,
        tool_name=_MACRO_AGENT_TOOL_NAME,
        run_id=run_id,
        ticker=result.ticker,
        inputs={
            "macro_agent_id": result.macro_agent_id,
            "as_of": result.as_of,
            "target": effective_target,
            "calculation_version": calculation_version,
        },
        outputs=payload,
        description=description,
    )
