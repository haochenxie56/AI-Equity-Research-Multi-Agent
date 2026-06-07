"""
lib/reliability/review_loop.py

Phase 3G: Offline Review Loop / Reliability Run Report Skeleton.

Design principles:
  - Standalone, deterministic, offline.
  - No live LLM calls, no live data fetching, no app integration.
  - Composes accepted Phase 3A–3F artifacts into a single auditable
    research/review package.
  - All logic is rule-based; no free-form LLM reasoning.
  - Does NOT import from app.py, pages/*, lib/llm_orchestrator.py, or any
    live workflow module.
  - Does NOT produce investment advice, buy/sell/order instructions, or
    individual security recommendations.
  - Does NOT authorize execution. approved_for_execution is always False.
  - Does NOT connect to live data feeds, brokers, or order systems.
  - Mock/dry-run only; all outputs are explicitly evidence-aware.

Phase 3G input bundle:
  - orchestration artifact (Phase 3A)
  - horizon-aware synthesis artifact (Phase 3B)
  - macro context artifact (Phase 3C)
  - debate-by-horizon artifact (Phase 3D)
  - decision packet artifact (Phase 3E)
  - human review artifact (Phase 3F)
  - validation aggregate, staleness report, critic result, tool results

Status logic (precedence: block > needs_revision > failed > complete > unknown):
  - blocked        if human review blocked (critical feedback) OR decision packet blocked.
  - needs_revision if human review has changes_requested; beats decision packet "fail".
  - failed         if decision packet status is "fail" and no HR block or revision above.
  - complete       if human review approved_for_research_only with no blockers.
  - unknown        otherwise or if human review report is absent.

approved_for_execution is ALWAYS False — this layer does not authorize execution.

See docs/reliability_phase_3g_review_loop_skeleton.md for design.

Disclaimer: All outputs are for research and educational purposes only.
They do not constitute investment advice. Markets involve risk.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lib.reliability.adapters import make_evidence_id, stable_hash_payload
from lib.reliability.critic import CriticResult
from lib.reliability.human_review import HumanReviewReport
from lib.reliability.schemas import ToolResult
from lib.reliability.staleness import StalenessReport
from lib.reliability.validation_aggregator import ValidationAggregate


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Literal type aliases (enums)
# ---------------------------------------------------------------------------

ReliabilityRunStatus = Literal[
    "unknown",
    "complete",
    "needs_revision",
    "blocked",
    "failed",
]


# ---------------------------------------------------------------------------
# Private constants
# ---------------------------------------------------------------------------

_REVIEW_LOOP_TOOL_NAME: str = "reliability_run_report"
_REVIEW_LOOP_METRIC_GROUP: str = "reliability_run_report"
_CALCULATION_VERSION: str = "reliability_run_report_v1"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class ReliabilityRunInputBundle(BaseModel):
    """
    Input bundle for a Phase 3G offline review loop run.

    Accepts all Phase 3A–3F artifacts so the review loop can compose
    a single auditable research/review package.

    Phase 3A–3F artifacts (orchestration, horizon synthesis, macro agent,
    debate, decision packet) are duck-typed via Any to avoid hard cross-module
    dependencies at import time.  ValidationAggregate, StalenessReport,
    CriticResult, and HumanReviewReport are typed for structured access.

    Optional artifacts that are None produce warnings rather than errors.
    """

    model_config = ConfigDict(extra="forbid")

    bundle_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    as_of: str = Field(min_length=1)
    ticker: Optional[str] = None

    # Phase 3A
    orchestration_report: Optional[Any] = None
    # Phase 3B
    horizon_synthesis_report: Optional[Any] = None
    # Phase 3C
    macro_agent_result: Optional[Any] = None
    # Phase 3D
    debate_report: Optional[Any] = None
    # Phase 3E
    decision_packet: Optional[Any] = None
    # Phase 3F
    human_review_report: Optional[HumanReviewReport] = None

    # Cross-phase supporting artifacts
    validation_aggregate: Optional[ValidationAggregate] = None
    staleness_report: Optional[StalenessReport] = None
    critic_result: Optional[CriticResult] = None
    tool_results: list[ToolResult] = Field(default_factory=list)

    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace(self) -> "ReliabilityRunInputBundle":
        for fn in ("bundle_id", "run_id", "as_of"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self


class ReliabilityRunSummary(BaseModel):
    """
    Deterministic summary of one reliability run.

    Computed from the input bundle and resolved status.
    approved_for_execution is always False.
    """

    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    status: ReliabilityRunStatus = "unknown"
    decision_summary: Optional[str] = None
    review_status: Optional[str] = None
    blocking_reasons: list[str] = Field(default_factory=list)
    revision_reasons: list[str] = Field(default_factory=list)
    horizon_count: int = 0
    debate_count: int = 0
    evidence_count: int = 0
    validation_issue_count: int = 0
    staleness_issue_count: int = 0
    critic_issue_count: int = 0
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "ReliabilityRunSummary":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 3G. "
                "This layer does not authorize execution."
            )
        return self


class ReliabilityRunReport(BaseModel):
    """
    Full offline reliability run report for one review loop pass.

    Composes Phase 3A–3F artifacts into a single auditable package.

    approved_for_execution is ALWAYS False.  This report is a research
    artifact only and does not constitute investment advice or authorize
    any form of execution.
    """

    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    schema_version: str = "1.0"
    target: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    as_of: str = Field(min_length=1)
    status: ReliabilityRunStatus = "unknown"
    summary: ReliabilityRunSummary
    source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: str = Field(min_length=1)
    calculation_version: str = _CALCULATION_VERSION
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _check_whitespace(self) -> "ReliabilityRunReport":
        for fn in ("report_id", "target", "run_id", "as_of", "created_at"):
            v = getattr(self, fn)
            if v is not None and not v.strip():
                raise ValueError(f"'{fn}' must not be whitespace-only; got {v!r}.")
        return self

    @model_validator(mode="after")
    def _execution_always_forbidden(self) -> "ReliabilityRunReport":
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 3G. "
                "This layer does not authorize execution."
            )
        return self


# ---------------------------------------------------------------------------
# Helper: deterministic ID generator
# ---------------------------------------------------------------------------

def make_reliability_run_report_id(
    run_id: str,
    target: str,
    as_of: str,
) -> str:
    """Return a deterministic stable hash ID for a ReliabilityRunReport."""
    payload = {"run_id": run_id, "target": target, "as_of": as_of}
    h = stable_hash_payload(payload, length=16)
    return f"rlr_{h}"


# ---------------------------------------------------------------------------
# Helper: status determination
# ---------------------------------------------------------------------------

def determine_reliability_run_status(
    input_bundle: ReliabilityRunInputBundle,
) -> tuple[ReliabilityRunStatus, list[str], list[str]]:
    """
    Derive the ReliabilityRunStatus from available input artifacts.

    Returns (status, blocking_reasons, revision_reasons).

    Priority (highest wins):
      blocked        — human review blocked (critical feedback) OR decision packet blocked.
      needs_revision — human review has changes_requested (revision required).
      failed         — decision packet status is "fail" and no HR revision request / block.
      complete       — human review approved for research only, no blockers.
      unknown        — human review absent or any other state.

    Decision packet "fail" does NOT override a human-review revision request.
    approved_for_execution is never implied by any status value.
    """
    blocking_reasons: list[str] = []
    revision_reasons: list[str] = []

    hrr = input_bundle.human_review_report
    dp = input_bundle.decision_packet

    # Determine human review state
    hr_status: Optional[str] = None
    hr_blocked: bool = False
    hr_revision: bool = False
    hr_approved_research: bool = False

    if hrr is not None:
        hr_status = hrr.status

        if hr_status == "blocked":
            hr_blocked = True
            # Collect blocking reasons from feedback
            for fb in hrr.feedback_items:
                if fb.severity == "critical":
                    blocking_reasons.append(fb.message)
            if hrr.outcome is not None and hrr.outcome.blocked:
                if hrr.outcome.rationale not in blocking_reasons:
                    blocking_reasons.append(hrr.outcome.rationale)
            if not blocking_reasons:
                blocking_reasons.append(
                    "Human review report is blocked — critical feedback detected."
                )
        elif hr_status == "changes_requested":
            hr_revision = True
            for rr in hrr.revision_requests:
                revision_reasons.append(rr.reason)
            if not revision_reasons:
                revision_reasons.append(
                    "Human review report requires changes before proceeding."
                )
        elif hr_status == "approved_for_research_only":
            hr_approved_research = True

    # Determine decision packet state
    dp_failed: bool = False
    dp_status: Optional[str] = None
    if dp is not None:
        dp_status = str(getattr(dp, "status", "unknown"))
        if dp_status in ("fail", "blocked"):
            dp_failed = True
            if dp_status == "blocked":
                blocking_reasons.append(
                    f"Decision packet status is '{dp_status}' — blocked at decision layer."
                )
            else:
                revision_reasons.append(
                    f"Decision packet status is '{dp_status}' — requires review before proceeding."
                )

    # Resolve final status — precedence: block > hr_revision > dp_fail > complete > unknown
    if hr_blocked:
        status: ReliabilityRunStatus = "blocked"
    elif dp_failed and dp_status == "blocked":
        status = "blocked"
    elif hr_revision:
        # HR changes_requested beats DP fail — the human reviewer's intent dominates.
        status = "needs_revision"
    elif dp_failed:
        status = "failed"
    elif hr_approved_research:
        status = "complete"
    elif hrr is None:
        status = "unknown"
    else:
        status = "unknown"

    # Deduplicate reasons preserving order
    seen_b: set[str] = set()
    blocking_reasons = [
        r for r in blocking_reasons if not (r in seen_b or seen_b.add(r))  # type: ignore[func-returns-value]
    ]
    seen_r: set[str] = set()
    revision_reasons = [
        r for r in revision_reasons if not (r in seen_r or seen_r.add(r))  # type: ignore[func-returns-value]
    ]

    return status, blocking_reasons, revision_reasons


# ---------------------------------------------------------------------------
# Helper: source ID collection
# ---------------------------------------------------------------------------

def collect_reliability_run_source_ids(
    input_bundle: ReliabilityRunInputBundle,
) -> list[str]:
    """
    Collect all source/evidence IDs from the input bundle deterministically.

    Deterministic order:
      1. ToolResult evidence IDs (direct evidence chain).
      2. Orchestration report artifact ID.
      3. Horizon synthesis report artifact ID and card evidence IDs.
      4. Macro agent result artifact ID.
      5. Debate report artifact ID.
      6. Decision packet artifact ID.
      7. Human review report artifact ID.
      8. ValidationAggregate aggregate ID.
      9. StalenessReport report ID.
      10. CriticResult critic ID.

    Deduplicates preserving first-occurrence order.
    Does not mutate inputs.
    """
    seen: set[str] = set()
    ids: list[str] = []

    def _add(eid: str) -> None:
        if eid and eid not in seen:
            seen.add(eid)
            ids.append(eid)

    # 1. ToolResult evidence IDs
    for tr in input_bundle.tool_results:
        _add(tr.evidence_id)

    # 2. Orchestration report
    orch = input_bundle.orchestration_report
    if orch is not None:
        oid = (
            getattr(orch, "orchestration_id", None)
            or getattr(orch, "report_id", None)
        )
        if oid:
            _add(str(oid))

    # 3. Horizon synthesis
    hsr = input_bundle.horizon_synthesis_report
    if hsr is not None:
        hid = (
            getattr(hsr, "synthesis_id", None)
            or getattr(hsr, "report_id", None)
        )
        if hid:
            _add(str(hid))
        # Card evidence IDs
        for card in getattr(hsr, "cards", []) or []:
            esummary = getattr(card, "evidence_summary", None)
            eids = (
                getattr(esummary, "supporting_evidence_ids", None)
                or getattr(card, "evidence_ids", None)
                or []
            )
            for eid in eids:
                _add(str(eid))

    # 4. Macro agent
    mar = input_bundle.macro_agent_result
    if mar is not None:
        mid = (
            getattr(mar, "macro_agent_id", None)
            or getattr(mar, "agent_id", None)
        )
        if mid:
            _add(str(mid))
        # Regime evidence IDs
        regime = getattr(mar, "regime_assessment", None)
        if regime is not None:
            for eid in getattr(regime, "supporting_evidence_ids", []) or []:
                _add(str(eid))

    # 5. Debate report
    dr = input_bundle.debate_report
    if dr is not None:
        did = (
            getattr(dr, "debate_id", None)
            or getattr(dr, "report_id", None)
        )
        if did:
            _add(str(did))

    # 6. Decision packet
    dp = input_bundle.decision_packet
    if dp is not None:
        dpid = getattr(dp, "decision_packet_id", None)
        if dpid:
            _add(str(dpid))
        # Source IDs from the packet
        for v in (getattr(dp, "source_ids", None) or {}).values():
            if v:
                _add(str(v))

    # 7. Human review report
    hrr = input_bundle.human_review_report
    if hrr is not None:
        hrid = getattr(hrr, "review_report_id", None)
        if hrid:
            _add(str(hrid))

    # 8. ValidationAggregate
    va = input_bundle.validation_aggregate
    if va is not None:
        vaid = getattr(va, "aggregate_id", None)
        if vaid:
            _add(str(vaid))

    # 9. StalenessReport
    sr = input_bundle.staleness_report
    if sr is not None:
        srid = getattr(sr, "report_id", None)
        if srid:
            _add(str(srid))

    # 10. CriticResult
    cr = input_bundle.critic_result
    if cr is not None:
        crid = getattr(cr, "critic_id", None)
        if crid:
            _add(str(crid))

    return ids


# ---------------------------------------------------------------------------
# Helper: warning generator
# ---------------------------------------------------------------------------

def _generate_run_warnings(input_bundle: ReliabilityRunInputBundle) -> list[str]:
    """
    Generate warnings for missing optional artifacts in the input bundle.

    Missing artifacts produce warnings, not errors.
    Required fields (bundle_id, run_id, as_of) are enforced by Pydantic.
    """
    warnings: list[str] = []
    if input_bundle.orchestration_report is None:
        warnings.append(
            "orchestration_report is absent; Phase 3A artifact was not provided."
        )
    if input_bundle.horizon_synthesis_report is None:
        warnings.append(
            "horizon_synthesis_report is absent; Phase 3B artifact was not provided."
        )
    if input_bundle.macro_agent_result is None:
        warnings.append(
            "macro_agent_result is absent; Phase 3C artifact was not provided."
        )
    if input_bundle.debate_report is None:
        warnings.append(
            "debate_report is absent; Phase 3D artifact was not provided."
        )
    if input_bundle.decision_packet is None:
        warnings.append(
            "decision_packet is absent; Phase 3E artifact was not provided."
        )
    if input_bundle.human_review_report is None:
        warnings.append(
            "human_review_report is absent; Phase 3F artifact was not provided. "
            "Run status will be 'unknown'."
        )
    if input_bundle.validation_aggregate is None:
        warnings.append("validation_aggregate is absent.")
    if input_bundle.staleness_report is None:
        warnings.append("staleness_report is absent.")
    if input_bundle.critic_result is None:
        warnings.append("critic_result is absent.")
    return warnings


# ---------------------------------------------------------------------------
# Helper: summary builder
# ---------------------------------------------------------------------------

def summarize_reliability_run(
    input_bundle: ReliabilityRunInputBundle,
    status: ReliabilityRunStatus,
    source_ids: list[str],
    blocking_reasons: list[str],
    revision_reasons: list[str],
) -> ReliabilityRunSummary:
    """
    Build a deterministic ReliabilityRunSummary from the input bundle and status.

    Does not mutate inputs.
    approved_for_execution is always False.
    """
    target = input_bundle.ticker or input_bundle.run_id

    # Decision summary from decision_packet
    decision_summary: Optional[str] = None
    dp = input_bundle.decision_packet
    if dp is not None:
        dp_status = str(getattr(dp, "status", "unknown"))
        dp_rec = str(getattr(dp, "recommendation", "unknown"))
        dp_ticker = getattr(dp, "ticker", None) or target
        decision_summary = (
            f"DecisionPacket for {dp_ticker}: status={dp_status}, "
            f"recommendation={dp_rec}. Research artifact only."
        )

    # Review status from human_review_report
    review_status: Optional[str] = None
    hrr = input_bundle.human_review_report
    if hrr is not None:
        review_status = hrr.status

    # Horizon count
    horizon_count = 0
    hsr = input_bundle.horizon_synthesis_report
    if hsr is not None:
        cards = getattr(hsr, "cards", None) or []
        horizon_count = len(cards)

    # Debate count (number of rounds)
    debate_count = 0
    dr = input_bundle.debate_report
    if dr is not None:
        rounds = getattr(dr, "rounds", None) or []
        debate_count = len(rounds)

    # Validation issue count
    validation_issue_count = 0
    va = input_bundle.validation_aggregate
    if va is not None:
        validation_issue_count = len(va.items)

    # Staleness issue count
    staleness_issue_count = 0
    sr = input_bundle.staleness_report
    if sr is not None:
        staleness_issue_count = len(sr.findings)

    # Critic issue count
    critic_issue_count = 0
    cr = input_bundle.critic_result
    if cr is not None:
        critic_issue_count = len(cr.issues)

    return ReliabilityRunSummary(
        target=target,
        run_id=input_bundle.run_id,
        status=status,
        decision_summary=decision_summary,
        review_status=review_status,
        blocking_reasons=list(blocking_reasons),
        revision_reasons=list(revision_reasons),
        horizon_count=horizon_count,
        debate_count=debate_count,
        evidence_count=len(source_ids),
        validation_issue_count=validation_issue_count,
        staleness_issue_count=staleness_issue_count,
        critic_issue_count=critic_issue_count,
        approved_for_execution=False,
    )


# ---------------------------------------------------------------------------
# Helper: main report builder
# ---------------------------------------------------------------------------

def build_reliability_run_report(
    input_bundle: ReliabilityRunInputBundle,
    created_at: Optional[str] = None,
) -> ReliabilityRunReport:
    """
    Build a complete offline reliability run report from the input bundle.

    Steps:
      1. Generate warnings for missing artifacts (no crash on missing optional).
      2. Collect source IDs deterministically.
      3. Determine run status and reasons.
      4. Build summary.
      5. Build report with stable deterministic report_id.

    Deterministic: identical inputs → identical outputs.
    No network calls. No LLM calls. No mutation of inputs.
    Does not constitute investment advice.
    approved_for_execution is always False.
    """
    target = input_bundle.ticker or input_bundle.run_id

    # 1. Warnings
    warnings = _generate_run_warnings(input_bundle)

    # 2. Source IDs
    source_ids = collect_reliability_run_source_ids(input_bundle)

    # 3. Status
    status, blocking_reasons, revision_reasons = determine_reliability_run_status(
        input_bundle
    )

    # 4. Summary
    summary = summarize_reliability_run(
        input_bundle=input_bundle,
        status=status,
        source_ids=source_ids,
        blocking_reasons=blocking_reasons,
        revision_reasons=revision_reasons,
    )

    # 5. Report ID
    report_id = make_reliability_run_report_id(
        run_id=input_bundle.run_id,
        target=target,
        as_of=input_bundle.as_of,
    )

    _created_at = created_at or _utcnow()

    return ReliabilityRunReport(
        report_id=report_id,
        target=target,
        run_id=input_bundle.run_id,
        as_of=input_bundle.as_of,
        status=status,
        summary=summary,
        source_ids=source_ids,
        warnings=warnings,
        created_at=_created_at,
        calculation_version=_CALCULATION_VERSION,
        approved_for_execution=False,
    )


# ---------------------------------------------------------------------------
# Helper: ToolResult adapter
# ---------------------------------------------------------------------------

def reliability_run_tool_result_from_report(
    run_id: str,
    report: ReliabilityRunReport,
    target: Optional[str] = None,
    calculation_version: str = _CALCULATION_VERSION,
) -> ToolResult:
    """
    Wrap a ReliabilityRunReport as a ToolResult for evidence-aware pipelines.

    - tool_name is stable: "reliability_run_report".
    - target defaults to report.target.
    - outputs includes the full report (serialized), summary, and
      calculation_version.
    - evidence_id is deterministic and content-sensitive.
    - Does not mutate report.
    - approved_for_execution is always False in the payload.
    - No live execution implication.
    """
    _target: str = target or report.target

    _report_dict = report.model_dump()
    _summary_dict: dict[str, Any] = {
        "report_id": report.report_id,
        "target": report.target,
        "run_id": report.run_id,
        "status": report.status,
        "horizon_count": report.summary.horizon_count,
        "debate_count": report.summary.debate_count,
        "evidence_count": report.summary.evidence_count,
        "validation_issue_count": report.summary.validation_issue_count,
        "staleness_issue_count": report.summary.staleness_issue_count,
        "critic_issue_count": report.summary.critic_issue_count,
        "blocking_reason_count": len(report.summary.blocking_reasons),
        "revision_reason_count": len(report.summary.revision_reasons),
        "warning_count": len(report.warnings),
        "source_id_count": len(report.source_ids),
        "approved_for_execution": False,  # Always False
    }

    outputs: dict[str, Any] = {
        "report": _report_dict,
        "summary": _summary_dict,
        "calculation_version": calculation_version,
    }

    evidence_id = make_evidence_id(
        run_id=run_id,
        tool_name=_REVIEW_LOOP_TOOL_NAME,
        target=_target,
        metric_group=_REVIEW_LOOP_METRIC_GROUP,
        payload=outputs,
    )

    return ToolResult(
        evidence_id=evidence_id,
        tool_name=_REVIEW_LOOP_TOOL_NAME,
        run_id=run_id,
        ticker=report.target if report.target != report.run_id else None,
        inputs={"as_of": report.as_of, "target": _target},
        outputs=outputs,
        description=(
            f"ReliabilityRunReport for {report.target}: "
            f"status={report.status}, "
            f"source_ids={len(report.source_ids)}, "
            f"warnings={len(report.warnings)}."
        ),
    )
