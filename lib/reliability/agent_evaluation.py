"""
lib/reliability/agent_evaluation.py - Phase 4M-G: Agent Evaluation.

Standalone, deterministic, offline/mock-only schema and helper layer for
evaluating agent/module performance from accepted memory artifacts and
human feedback. No persistence, no DB, no vector store, no broker/order
behavior, no prompt/model/agent-definition mutation, no Streamlit UI.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lib.reliability.adapters import make_evidence_id, stable_hash_payload
from lib.reliability.schemas import ToolResult

_DETERMINISTIC_TIMESTAMP_DEFAULT: str = "1970-01-01T00:00:00Z"
_AGENT_EVALUATION_TOOL_NAME: str = "agent_evaluation_report"
_AGENT_EVALUATION_METRIC_GROUP: str = "agent_evaluation_report"
_CALCULATION_VERSION: str = "agent_evaluation_v1"

# ----------------------------------------------------------------------------
# Literal type aliases
# ----------------------------------------------------------------------------

AgentEvaluationStatus = Literal[
    "unknown",
    "evaluated",
    "needs_review",
    "incomplete",
    "archived",
    "blocked",
]

EvaluatedAgentType = Literal[
    "macro_agent",
    "horizon_synthesis",
    "debate_agent",
    "decision_packet",
    "human_review",
    "review_loop",
    "event_intelligence",
    "trade_plan",
    "allocation_agent",
    "option_expression",
    "research_memory",
    "thesis_memory",
    "event_memory",
    "allocation_memory",
    "option_trade_memory",
    "human_feedback",
    "integration_boundary",
    "unknown",
]

AgentEvaluationOutcome = Literal[
    "unknown",
    "correct",
    "incorrect",
    "partially_correct",
    "inconclusive",
    "false_positive",
    "false_negative",
    "avoided_loss",
    "missed_gain",
    "prevented_bad_action",
    "caused_bad_action",
]

AgentEvaluationSignalType = Literal[
    "thesis_direction",
    "confidence",
    "risk_warning",
    "catalyst_call",
    "news_impact",
    "earnings_view",
    "estimate_revision",
    "trade_plan",
    "allocation_decision",
    "option_expression",
    "no_trade_call",
    "review_trigger",
    "human_override",
    "unknown",
]

AgentEvaluationHorizon = Literal[
    "short",
    "medium",
    "long",
    "multi_horizon",
    "unknown",
]

AgentEvaluationGrade = Literal[
    "excellent",
    "good",
    "mixed",
    "poor",
    "unknown",
]

AgentEvaluationEventType = Literal[
    "evaluation_recorded",
    "outcome_updated",
    "lesson_added",
    "calibration_updated",
    "human_feedback_linked",
    "archived",
    "unknown",
]

AgentEvaluationActor = Literal[
    "system",
    "user",
    "reviewer",
    "agent",
    "unknown",
]

# Outcomes that count as "correct-leaning" for accuracy.
_CORRECT_OUTCOMES = {"correct", "avoided_loss", "prevented_bad_action"}
# Outcomes that count as "incorrect-leaning" for accuracy.
_INCORRECT_OUTCOMES = {
    "incorrect",
    "false_positive",
    "false_negative",
    "caused_bad_action",
    "missed_gain",
}
_PARTIAL_OUTCOMES = {"partially_correct"}
_INCONCLUSIVE_OUTCOMES = {"inconclusive", "unknown"}

# ----------------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------------


def _dedup_source_refs(refs):
    seen = set()
    result = []
    for ref in refs:
        if ref.source_id not in seen:
            seen.add(ref.source_id)
            result.append(ref)
    return result


def _dedup_list(items):
    seen = set()
    result = []
    for item in items:
        if item is None:
            continue
        s = str(item)
        if not s.strip():
            continue
        if s not in seen:
            seen.add(s)
            result.append(s)
    return result


# ----------------------------------------------------------------------------
# Pydantic Models
# ----------------------------------------------------------------------------


class AgentEvaluationSourceRef(BaseModel):
    """A pointer to upstream evidence/memory/artifact that backs an evaluation."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    source_type: str = "unknown"
    artifact_id: Optional[str] = None
    evidence_id: Optional[str] = None
    field_path: Optional[str] = None
    label: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_source_id(self):
        if not self.source_id.strip():
            raise ValueError(
                f"'source_id' must not be whitespace-only; got {self.source_id!r}."
            )
        return self


class AgentEvaluationTargetRef(BaseModel):
    """A pointer to the agent/module output being evaluated."""

    model_config = ConfigDict(extra="forbid")

    target_ref_id: str = Field(min_length=1)
    agent_type: EvaluatedAgentType = "unknown"
    artifact_id: str = Field(min_length=1)
    run_id: Optional[str] = None
    memory_id: Optional[str] = None
    thesis_id: Optional[str] = None
    report_id: Optional[str] = None
    field_path: Optional[str] = None
    horizon: Optional[AgentEvaluationHorizon] = None
    signal_type: Optional[AgentEvaluationSignalType] = None
    source_refs: list[AgentEvaluationSourceRef] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_ids(self):
        for fn in ("target_ref_id", "artifact_id"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(
                    f"'{fn}' must not be whitespace-only; got {v!r}."
                )
        return self


class AgentEvaluationSignal(BaseModel):
    """One evaluated agent signal/claim (direction, confidence, risk, etc.)."""

    model_config = ConfigDict(extra="forbid")

    signal_id: str = Field(min_length=1)
    signal_type: AgentEvaluationSignalType = "unknown"
    agent_type: EvaluatedAgentType = "unknown"
    horizon: AgentEvaluationHorizon = "unknown"
    original_claim: Optional[str] = None
    original_direction: Optional[str] = None
    original_confidence: Optional[float] = None
    evaluated_outcome: AgentEvaluationOutcome = "unknown"
    evaluation_grade: AgentEvaluationGrade = "unknown"
    rationale: str = Field(min_length=1)
    source_refs: list[AgentEvaluationSourceRef] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _validate_signal(self):
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 4M-G. "
                "This layer does not authorize execution."
            )
        for fn in ("signal_id", "rationale"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(
                    f"'{fn}' must not be whitespace-only; got {v!r}."
                )
        if self.original_confidence is not None and not (
            0.0 <= self.original_confidence <= 1.0
        ):
            raise ValueError(
                f"'original_confidence' must be between 0 and 1 when present; "
                f"got {self.original_confidence!r}."
            )
        return self


class AgentEvaluationCalibration(BaseModel):
    """Calibration metrics across a sample of evaluated agent signals."""

    model_config = ConfigDict(extra="forbid")

    calibration_id: str = Field(min_length=1)
    agent_type: EvaluatedAgentType = "unknown"
    sample_count: int = 0
    correct_count: int = 0
    incorrect_count: int = 0
    partial_count: int = 0
    inconclusive_count: int = 0
    false_positive_count: int = 0
    false_negative_count: int = 0
    override_count: int = 0
    rejection_count: int = 0
    acceptance_rate: Optional[float] = None
    override_rate: Optional[float] = None
    rejection_rate: Optional[float] = None
    accuracy_rate: Optional[float] = None
    false_positive_rate: Optional[float] = None
    false_negative_rate: Optional[float] = None
    average_confidence: Optional[float] = None
    calibration_gap: Optional[float] = None
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_counts_and_rates(self):
        for fn in (
            "sample_count",
            "correct_count",
            "incorrect_count",
            "partial_count",
            "inconclusive_count",
            "false_positive_count",
            "false_negative_count",
            "override_count",
            "rejection_count",
        ):
            v = getattr(self, fn)
            if v < 0:
                raise ValueError(
                    f"'{fn}' must be non-negative; got {v!r}."
                )
        for fn in (
            "acceptance_rate",
            "override_rate",
            "rejection_rate",
            "accuracy_rate",
            "false_positive_rate",
            "false_negative_rate",
            "average_confidence",
        ):
            v = getattr(self, fn)
            if v is not None and not (0.0 <= v <= 1.0):
                raise ValueError(
                    f"'{fn}' must be between 0 and 1 when present; got {v!r}."
                )
        # calibration_gap is signed: accuracy_rate - average_confidence, range [-1, 1]
        if self.calibration_gap is not None and not (-1.0 <= self.calibration_gap <= 1.0):
            raise ValueError(
                f"'calibration_gap' must be between -1 and 1 when present; "
                f"got {self.calibration_gap!r}."
            )
        if not self.calibration_id.strip():
            raise ValueError(
                f"'calibration_id' must not be whitespace-only; got {self.calibration_id!r}."
            )
        return self


class AgentEvaluationLogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1)
    event_type: AgentEvaluationEventType = "unknown"
    created_at: str = Field(min_length=1)
    actor: AgentEvaluationActor = "system"
    description: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_whitespace(self):
        for fn in ("event_id", "created_at", "description"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(
                    f"'{fn}' must not be whitespace-only; got {v!r}."
                )
        return self


class AgentEvaluationRecord(BaseModel):
    """A complete agent evaluation record."""

    model_config = ConfigDict(extra="forbid")

    evaluation_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    run_id: Optional[str] = None
    memory_id: Optional[str] = None
    agent_type: EvaluatedAgentType = "unknown"
    status: AgentEvaluationStatus = "unknown"
    target_ref: AgentEvaluationTargetRef
    signals: list[AgentEvaluationSignal] = Field(default_factory=list)
    overall_outcome: AgentEvaluationOutcome = "unknown"
    overall_grade: AgentEvaluationGrade = "unknown"
    calibration: Optional[AgentEvaluationCalibration] = None
    human_feedback_memory_id: Optional[str] = None
    lesson: Optional[str] = None
    review_required: bool = False
    recorded_at: str = Field(min_length=1)
    reviewed_at: Optional[str] = None
    source_refs: list[AgentEvaluationSourceRef] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    event_log: list[AgentEvaluationLogEntry] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _check_fields(self):
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 4M-G. "
                "This layer does not authorize execution."
            )
        for fn in ("evaluation_id", "target", "recorded_at"):
            v = getattr(self, fn)
            if not v.strip():
                raise ValueError(
                    f"'{fn}' must not be whitespace-only; got {v!r}."
                )
        if not self.signals:
            raise ValueError(
                "'signals' must not be empty; at least one signal is required."
            )
        return self


class AgentEvaluationInputBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    target: str = Field(min_length=1)
    run_id: Optional[str] = None
    memory_id: Optional[str] = None
    as_of: Optional[str] = None
    research_run_memory_record: Optional[Any] = None
    thesis_memory_report: Optional[Any] = None
    event_memory_report: Optional[Any] = None
    allocation_memory_report: Optional[Any] = None
    option_trade_memory_report: Optional[Any] = None
    human_feedback_memory_report: Optional[Any] = None
    review_loop_report: Optional[Any] = None
    decision_packet: Optional[Any] = None
    source_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_whitespace(self):
        if not self.target.strip():
            raise ValueError("'target' must not be whitespace-only.")
        return self


class AgentEvaluationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str = Field(min_length=1)
    status: AgentEvaluationStatus = "unknown"
    record_count: int = 0
    signal_count: int = 0
    agent_counts: dict[str, int] = Field(default_factory=dict)
    outcome_counts: dict[str, int] = Field(default_factory=dict)
    grade_counts: dict[str, int] = Field(default_factory=dict)
    horizon_counts: dict[str, int] = Field(default_factory=dict)
    correct_count: int = 0
    incorrect_count: int = 0
    partial_count: int = 0
    inconclusive_count: int = 0
    false_positive_count: int = 0
    false_negative_count: int = 0
    override_count: int = 0
    rejection_count: int = 0
    review_required_count: int = 0
    rejection_rate: Optional[float] = None
    top_warnings: list[str] = Field(default_factory=list)
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _validate_summary(self):
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 4M-G. "
                "This layer does not authorize execution."
            )
        for fn in (
            "record_count",
            "signal_count",
            "correct_count",
            "incorrect_count",
            "partial_count",
            "inconclusive_count",
            "false_positive_count",
            "false_negative_count",
            "override_count",
            "rejection_count",
            "review_required_count",
        ):
            v = getattr(self, fn)
            if v < 0:
                raise ValueError(
                    f"'{fn}' must be non-negative; got {v!r}."
                )
        if self.rejection_rate is not None and not (
            0.0 <= self.rejection_rate <= 1.0
        ):
            raise ValueError(
                f"'rejection_rate' must be between 0 and 1 when present; "
                f"got {self.rejection_rate!r}."
            )
        return self


class AgentEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    run_id: Optional[str] = None
    status: AgentEvaluationStatus = "unknown"
    records: list[AgentEvaluationRecord] = Field(default_factory=list)
    summary: AgentEvaluationSummary
    source_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    calculation_version: str = _CALCULATION_VERSION
    approved_for_execution: bool = False

    @model_validator(mode="after")
    def _execution_always_forbidden(self):
        if self.approved_for_execution:
            raise ValueError(
                "approved_for_execution must always be False in Phase 4M-G. "
                "This layer does not authorize execution."
            )
        return self


# ----------------------------------------------------------------------------
# ID factories (content-sensitive, deterministic)
# ----------------------------------------------------------------------------


def make_agent_evaluation_record_id(
    target_id,
    agent_type,
    signal_ids,
    outcomes,
    grades,
    lesson=None,
    human_feedback_memory_id=None,
    run_id=None,
    as_of=None,
):
    payload = {
        "target_id": target_id,
        "agent_type": agent_type,
        "signal_ids": list(signal_ids),
        "outcomes": list(outcomes),
        "grades": list(grades),
        "lesson": lesson or "",
        "human_feedback_memory_id": human_feedback_memory_id or "",
        "run_id": run_id or "",
        "as_of": as_of or _DETERMINISTIC_TIMESTAMP_DEFAULT,
    }
    return f"aev_{stable_hash_payload(payload, length=12)}"


def make_agent_evaluation_log_entry_id(evaluation_id, event_type, created_at):
    payload = {
        "evaluation_id": evaluation_id,
        "event_type": event_type,
        "created_at": created_at,
    }
    return f"aevev_{stable_hash_payload(payload, length=12)}"


def make_agent_evaluation_report_id(target, as_of, run_id=None):
    payload = {
        "target": target,
        "as_of": as_of,
        "run_id": run_id or "",
        "tool": _AGENT_EVALUATION_TOOL_NAME,
    }
    return f"aevrpt_{stable_hash_payload(payload, length=12)}"


# ----------------------------------------------------------------------------
# Builders
# ----------------------------------------------------------------------------


def build_agent_evaluation_target_ref(
    artifact_id,
    agent_type="unknown",
    run_id=None,
    memory_id=None,
    thesis_id=None,
    report_id=None,
    field_path=None,
    horizon=None,
    signal_type=None,
    source_refs=None,
    evidence_ids=None,
    artifact_refs=None,
    metadata=None,
    warnings=None,
    as_of=None,
):
    _source_refs = _dedup_source_refs(list(source_refs or []))
    _evidence_ids = _dedup_list(list(evidence_ids or []))
    _artifact_refs = _dedup_list(list(artifact_refs or []))
    ref_payload = {
        "artifact_id": artifact_id,
        "agent_type": agent_type,
        "run_id": run_id or "",
        "memory_id": memory_id or "",
        "field_path": field_path or "",
        "as_of": as_of or _DETERMINISTIC_TIMESTAMP_DEFAULT,
    }
    target_ref_id = f"aevtref_{stable_hash_payload(ref_payload, length=12)}"
    return AgentEvaluationTargetRef(
        target_ref_id=target_ref_id,
        agent_type=agent_type,
        artifact_id=artifact_id,
        run_id=run_id,
        memory_id=memory_id,
        thesis_id=thesis_id,
        report_id=report_id,
        field_path=field_path,
        horizon=horizon,
        signal_type=signal_type,
        source_refs=_source_refs,
        evidence_ids=_evidence_ids,
        artifact_refs=_artifact_refs,
        metadata=dict(metadata or {}),
        warnings=list(warnings or []),
    )


def build_agent_evaluation_signal(
    signal_id,
    rationale,
    signal_type="unknown",
    agent_type="unknown",
    horizon="unknown",
    original_claim=None,
    original_direction=None,
    original_confidence=None,
    evaluated_outcome="unknown",
    evaluation_grade="unknown",
    source_refs=None,
    evidence_ids=None,
    artifact_refs=None,
    metadata=None,
    warnings=None,
):
    _source_refs = _dedup_source_refs(list(source_refs or []))
    _evidence_ids = _dedup_list(list(evidence_ids or []))
    _artifact_refs = _dedup_list(list(artifact_refs or []))
    return AgentEvaluationSignal(
        signal_id=signal_id,
        signal_type=signal_type,
        agent_type=agent_type,
        horizon=horizon,
        original_claim=original_claim,
        original_direction=original_direction,
        original_confidence=original_confidence,
        evaluated_outcome=evaluated_outcome,
        evaluation_grade=evaluation_grade,
        rationale=rationale,
        source_refs=_source_refs,
        evidence_ids=_evidence_ids,
        artifact_refs=_artifact_refs,
        metadata=dict(metadata or {}),
        warnings=list(warnings or []),
        approved_for_execution=False,
    )


def _safe_rate(num, denom):
    if denom is None or denom <= 0:
        return None
    return float(num) / float(denom)


def build_agent_evaluation_calibration(
    calibration_id,
    agent_type="unknown",
    sample_count=0,
    correct_count=0,
    incorrect_count=0,
    partial_count=0,
    inconclusive_count=0,
    false_positive_count=0,
    false_negative_count=0,
    override_count=0,
    rejection_count=0,
    average_confidence=None,
    acceptance_rate=None,
    warnings=None,
):
    accuracy_rate = _safe_rate(correct_count, sample_count)
    fp_rate = _safe_rate(false_positive_count, sample_count)
    fn_rate = _safe_rate(false_negative_count, sample_count)
    override_rate = _safe_rate(override_count, sample_count)
    rejection_rate = _safe_rate(rejection_count, sample_count)
    # signed calibration_gap = accuracy_rate - average_confidence
    if accuracy_rate is not None and average_confidence is not None:
        calibration_gap = accuracy_rate - average_confidence
    else:
        calibration_gap = None
    return AgentEvaluationCalibration(
        calibration_id=calibration_id,
        agent_type=agent_type,
        sample_count=sample_count,
        correct_count=correct_count,
        incorrect_count=incorrect_count,
        partial_count=partial_count,
        inconclusive_count=inconclusive_count,
        false_positive_count=false_positive_count,
        false_negative_count=false_negative_count,
        override_count=override_count,
        rejection_count=rejection_count,
        acceptance_rate=acceptance_rate,
        override_rate=override_rate,
        rejection_rate=rejection_rate,
        accuracy_rate=accuracy_rate,
        false_positive_rate=fp_rate,
        false_negative_rate=fn_rate,
        average_confidence=average_confidence,
        calibration_gap=calibration_gap,
        warnings=list(warnings or []),
    )


def build_agent_evaluation_log_entry(
    event_type,
    description,
    evaluation_id,
    created_at=None,
    actor="system",
    source_ids=None,
    evidence_ids=None,
    metadata=None,
    warnings=None,
):
    ts = created_at or _DETERMINISTIC_TIMESTAMP_DEFAULT
    event_id = make_agent_evaluation_log_entry_id(
        evaluation_id=evaluation_id,
        event_type=event_type,
        created_at=ts,
    )
    return AgentEvaluationLogEntry(
        event_id=event_id,
        event_type=event_type,
        created_at=ts,
        actor=actor,
        description=description,
        source_ids=list(source_ids or []),
        evidence_ids=list(evidence_ids or []),
        metadata=dict(metadata or {}),
        warnings=list(warnings or []),
    )


def _derive_overall_outcome(signals):
    outcomes = [s.evaluated_outcome for s in signals]
    if not outcomes:
        return "unknown"
    # Precedence: caused_bad_action > prevented_bad_action > false_positive > false_negative
    # > incorrect > missed_gain > avoided_loss > correct > partially_correct
    # > inconclusive > unknown
    priority = [
        "caused_bad_action",
        "prevented_bad_action",
        "false_positive",
        "false_negative",
        "incorrect",
        "missed_gain",
        "avoided_loss",
        "correct",
        "partially_correct",
        "inconclusive",
        "unknown",
    ]
    # If multiple distinct correct-ish outcomes present and any incorrect-ish: pick incorrect
    has_incorrect = any(o in _INCORRECT_OUTCOMES for o in outcomes)
    has_correct = any(o in _CORRECT_OUTCOMES for o in outcomes)
    has_partial = any(o in _PARTIAL_OUTCOMES for o in outcomes)
    if has_incorrect and has_correct:
        # mixed result
        return "partially_correct"
    if has_partial and not has_incorrect:
        return "partially_correct"
    # Otherwise return the highest priority outcome present
    for o in priority:
        if o in outcomes:
            return o
    return "unknown"


def _derive_overall_grade(signals):
    grades = [s.evaluation_grade for s in signals]
    if not grades:
        return "unknown"
    if any(g == "poor" for g in grades) and any(
        g in ("excellent", "good") for g in grades
    ):
        return "mixed"
    if all(g == "excellent" for g in grades):
        return "excellent"
    if all(g in ("excellent", "good") for g in grades):
        return "good"
    if any(g == "poor" for g in grades):
        return "poor"
    if any(g == "mixed" for g in grades):
        return "mixed"
    if any(g == "good" for g in grades):
        return "good"
    if any(g == "excellent" for g in grades):
        return "excellent"
    return "unknown"


def _derive_record_status(
    signals,
    review_required,
    initial_status,
    hfm_blocked,
    missing_important_upstream,
):
    """Derive record-level status following the precedence:

        blocked > needs_review > incomplete > evaluated > archived > unknown

    ``initial_status`` is an optional caller-supplied label. It is NOT a free
    override: stronger conditions (``hfm_blocked``, ``review_required``,
    ``missing_important_upstream``) always outrank weaker initial labels such
    as ``evaluated`` or ``archived``. ``initial_status`` may, however, raise
    the status to a stronger label than the derivation would otherwise pick.
    """
    # 1. Blocked outranks everything (including initial_status of weaker labels)
    if hfm_blocked or initial_status == "blocked":
        return "blocked"
    # 2. Needs-review outranks incomplete/evaluated/archived/unknown
    if review_required or initial_status == "needs_review":
        return "needs_review"
    # 3. Incomplete outranks evaluated/archived/unknown
    if missing_important_upstream or initial_status == "incomplete":
        return "incomplete"
    # If any signal outcome is purely unknown -> incomplete
    outcomes = [s.evaluated_outcome for s in signals]
    if all(o == "unknown" for o in outcomes):
        return "incomplete"
    # 4. Safe initial_status applies only after stronger conditions cleared
    if initial_status in ("evaluated", "archived", "unknown"):
        return initial_status
    return "evaluated"


def build_agent_evaluation_record(
    target,
    target_ref,
    signals,
    agent_type=None,
    run_id=None,
    memory_id=None,
    overall_outcome=None,
    overall_grade=None,
    calibration=None,
    human_feedback_memory_id=None,
    lesson=None,
    review_required=False,
    initial_status=None,
    hfm_blocked=False,
    missing_important_upstream=False,
    recorded_at=None,
    reviewed_at=None,
    source_refs=None,
    evidence_ids=None,
    artifact_refs=None,
    warnings=None,
    as_of=None,
):
    ts = recorded_at or as_of or _DETERMINISTIC_TIMESTAMP_DEFAULT
    _signals = list(signals)
    if not _signals:
        raise ValueError(
            "'signals' must not be empty; at least one signal is required."
        )
    _agent_type = agent_type or target_ref.agent_type or "unknown"
    derived_outcome = overall_outcome or _derive_overall_outcome(_signals)
    derived_grade = overall_grade or _derive_overall_grade(_signals)
    status = _derive_record_status(
        signals=_signals,
        review_required=review_required,
        initial_status=initial_status,
        hfm_blocked=hfm_blocked,
        missing_important_upstream=missing_important_upstream,
    )
    all_warnings = list(warnings or [])
    _source_refs = _dedup_source_refs(list(source_refs or []))
    _evidence_ids = _dedup_list(list(evidence_ids or []))
    _artifact_refs = _dedup_list(list(artifact_refs or []))
    signal_ids = [s.signal_id for s in _signals]
    outcomes = [s.evaluated_outcome for s in _signals]
    grades = [s.evaluation_grade for s in _signals]
    evaluation_id = make_agent_evaluation_record_id(
        target_id=target_ref.artifact_id,
        agent_type=_agent_type,
        signal_ids=signal_ids,
        outcomes=outcomes,
        grades=grades,
        lesson=lesson,
        human_feedback_memory_id=human_feedback_memory_id,
        run_id=run_id,
        as_of=ts,
    )
    event_log = []
    event_log.append(
        build_agent_evaluation_log_entry(
            event_type="evaluation_recorded",
            description=(
                f"Agent evaluation recorded for {target!r} "
                f"(agent_type={_agent_type!r}, signals={signal_ids!r})."
            ),
            evaluation_id=evaluation_id,
            created_at=ts,
            actor="system",
            metadata={
                "agent_type": _agent_type,
                "signal_count": len(_signals),
                "outcomes": outcomes,
            },
        )
    )
    if calibration is not None:
        event_log.append(
            build_agent_evaluation_log_entry(
                event_type="calibration_updated",
                description=(
                    f"Calibration recorded: accuracy_rate="
                    f"{calibration.accuracy_rate!r}, sample_count="
                    f"{calibration.sample_count!r}."
                ),
                evaluation_id=evaluation_id,
                created_at=ts,
                actor="system",
                metadata={
                    "accuracy_rate": calibration.accuracy_rate,
                    "sample_count": calibration.sample_count,
                },
            )
        )
    if human_feedback_memory_id:
        event_log.append(
            build_agent_evaluation_log_entry(
                event_type="human_feedback_linked",
                description=(
                    f"Human feedback memory linked: "
                    f"{human_feedback_memory_id!r}."
                ),
                evaluation_id=evaluation_id,
                created_at=ts,
                actor="system",
                metadata={
                    "human_feedback_memory_id": human_feedback_memory_id
                },
            )
        )
    if lesson:
        event_log.append(
            build_agent_evaluation_log_entry(
                event_type="lesson_added",
                description=f"Lesson recorded: {lesson!r}.",
                evaluation_id=evaluation_id,
                created_at=ts,
                actor="system",
                metadata={"lesson": lesson},
            )
        )
    if derived_outcome not in ("unknown",):
        event_log.append(
            build_agent_evaluation_log_entry(
                event_type="outcome_updated",
                description=(
                    f"Overall outcome derived: {derived_outcome!r} "
                    f"(grade={derived_grade!r})."
                ),
                evaluation_id=evaluation_id,
                created_at=ts,
                actor="system",
                metadata={
                    "overall_outcome": derived_outcome,
                    "overall_grade": derived_grade,
                },
            )
        )
    return AgentEvaluationRecord(
        evaluation_id=evaluation_id,
        target=target,
        run_id=run_id,
        memory_id=memory_id,
        agent_type=_agent_type,
        status=status,
        target_ref=target_ref,
        signals=_signals,
        overall_outcome=derived_outcome,
        overall_grade=derived_grade,
        calibration=calibration,
        human_feedback_memory_id=human_feedback_memory_id,
        lesson=lesson,
        review_required=review_required,
        recorded_at=ts,
        reviewed_at=reviewed_at,
        source_refs=_source_refs,
        evidence_ids=_evidence_ids,
        artifact_refs=_artifact_refs,
        event_log=event_log,
        warnings=all_warnings,
        approved_for_execution=False,
    )


# ----------------------------------------------------------------------------
# Status determination
# ----------------------------------------------------------------------------


def determine_agent_evaluation_status(records, input_bundle=None):
    warnings = []
    hfm = (
        getattr(input_bundle, "human_feedback_memory_report", None)
        if input_bundle
        else None
    )
    rlr = (
        getattr(input_bundle, "review_loop_report", None)
        if input_bundle
        else None
    )
    if hfm is not None:
        hf_status = str(getattr(hfm, "status", "unknown"))
        if hf_status == "blocked":
            warnings.append(
                "Human feedback memory report is blocked -- agent evaluation "
                "report status set to blocked."
            )
            return "blocked", warnings
    if rlr is not None:
        rl_status = str(getattr(rlr, "status", "unknown"))
        if rl_status in ("block", "blocked"):
            warnings.append(
                "Review loop report is blocked -- agent evaluation report "
                "status set to blocked."
            )
            return "blocked", warnings
    if not records:
        warnings.append(
            "No agent evaluation records provided -- report status is unknown."
        )
        return "unknown", warnings
    statuses = [r.status for r in records]
    if "blocked" in statuses:
        n = statuses.count("blocked")
        warnings.append(f"{n} agent evaluation record(s) are blocked.")
        return "blocked", warnings
    if "needs_review" in statuses:
        n = statuses.count("needs_review")
        warnings.append(
            f"{n} agent evaluation record(s) require review."
        )
        return "needs_review", warnings
    if "incomplete" in statuses:
        n = statuses.count("incomplete")
        warnings.append(f"{n} agent evaluation record(s) are incomplete.")
        return "incomplete", warnings
    non_terminal = [s for s in statuses if s not in ("archived", "unknown")]
    if not non_terminal:
        if all(s == "archived" for s in statuses):
            return "archived", warnings
        return "unknown", warnings
    if all(s == "evaluated" for s in non_terminal):
        return "evaluated", warnings
    if any(s == "evaluated" for s in non_terminal):
        return "evaluated", warnings
    return "unknown", warnings


# ----------------------------------------------------------------------------
# Collection helpers (dedup, first-occurrence-wins)
# ----------------------------------------------------------------------------


_UPSTREAM_ATTRS = (
    "research_run_memory_record",
    "thesis_memory_report",
    "event_memory_report",
    "allocation_memory_report",
    "option_trade_memory_report",
    "human_feedback_memory_report",
    "review_loop_report",
    "decision_packet",
)


def collect_agent_evaluation_source_ids(input_bundle, records=None):
    seen = set()
    result = []

    def _add(sid):
        if sid is None:
            return
        s = str(sid)
        if s and s.strip() and s not in seen:
            seen.add(s)
            result.append(s)

    for sid in input_bundle.source_ids:
        _add(sid)
    for attr in _UPSTREAM_ATTRS:
        artifact = getattr(input_bundle, attr, None)
        if artifact is None:
            continue
        for sid in (getattr(artifact, "source_ids", []) or []):
            _add(sid)
        artifact_id = (
            getattr(artifact, "report_id", None)
            or getattr(artifact, "result_id", None)
            or getattr(artifact, "packet_id", None)
            or getattr(artifact, "memory_id", None)
        )
        if artifact_id:
            _add(artifact_id)
    if records:
        for record in records:
            for ref in record.source_refs:
                _add(ref.source_id)
            for ref in record.target_ref.source_refs:
                _add(ref.source_id)
            for signal in record.signals:
                for ref in signal.source_refs:
                    _add(ref.source_id)
    return result


def collect_agent_evaluation_evidence_ids(input_bundle, records=None):
    seen = set()
    result = []

    def _add(eid):
        if eid is None:
            return
        s = str(eid)
        if s and s.strip() and s not in seen:
            seen.add(s)
            result.append(s)

    for eid in input_bundle.evidence_ids:
        _add(eid)
    for attr in _UPSTREAM_ATTRS:
        artifact = getattr(input_bundle, attr, None)
        if artifact is None:
            continue
        for eid in (getattr(artifact, "evidence_ids", None) or []):
            _add(eid)
        artifact_eid = getattr(artifact, "evidence_id", None)
        if artifact_eid:
            _add(artifact_eid)
    if records:
        for record in records:
            for eid in record.evidence_ids:
                _add(eid)
            for ref in record.source_refs:
                if ref.evidence_id:
                    _add(ref.evidence_id)
            for eid in record.target_ref.evidence_ids:
                _add(eid)
            for ref in record.target_ref.source_refs:
                if ref.evidence_id:
                    _add(ref.evidence_id)
            for signal in record.signals:
                for eid in signal.evidence_ids:
                    _add(eid)
                for ref in signal.source_refs:
                    if ref.evidence_id:
                        _add(ref.evidence_id)
    return result


def collect_agent_evaluation_artifact_refs(input_bundle, records=None):
    seen = set()
    result = []

    def _add(ref):
        if ref is None:
            return
        s = str(ref)
        if s and s.strip() and s not in seen:
            seen.add(s)
            result.append(s)

    for ref in input_bundle.artifact_refs:
        _add(ref)
    if records:
        for record in records:
            for ref in record.artifact_refs:
                _add(ref)
            for ref in record.target_ref.artifact_refs:
                _add(ref)
            for signal in record.signals:
                for ref in signal.artifact_refs:
                    _add(ref)
    return result


# ----------------------------------------------------------------------------
# Summary + Report builder
# ----------------------------------------------------------------------------


def summarize_agent_evaluation(target, status, records, warnings):
    rc = len(records)
    sc = sum(len(r.signals) for r in records)
    agent_counts: dict[str, int] = {}
    outcome_counts: dict[str, int] = {}
    grade_counts: dict[str, int] = {}
    horizon_counts: dict[str, int] = {}
    correct_count = 0
    incorrect_count = 0
    partial_count = 0
    inconclusive_count = 0
    fp_count = 0
    fn_count = 0
    override_count = 0
    rejection_count = 0
    review_required_count = sum(1 for r in records if r.review_required)
    for record in records:
        agent_counts[record.agent_type] = (
            agent_counts.get(record.agent_type, 0) + 1
        )
        for signal in record.signals:
            outcome_counts[signal.evaluated_outcome] = (
                outcome_counts.get(signal.evaluated_outcome, 0) + 1
            )
            grade_counts[signal.evaluation_grade] = (
                grade_counts.get(signal.evaluation_grade, 0) + 1
            )
            horizon_counts[signal.horizon] = (
                horizon_counts.get(signal.horizon, 0) + 1
            )
            if signal.evaluated_outcome in _CORRECT_OUTCOMES:
                correct_count += 1
            if signal.evaluated_outcome in _INCORRECT_OUTCOMES:
                incorrect_count += 1
            if signal.evaluated_outcome in _PARTIAL_OUTCOMES:
                partial_count += 1
            if signal.evaluated_outcome in _INCONCLUSIVE_OUTCOMES:
                inconclusive_count += 1
            if signal.evaluated_outcome == "false_positive":
                fp_count += 1
            if signal.evaluated_outcome == "false_negative":
                fn_count += 1
            if signal.signal_type == "human_override":
                override_count += 1
        # also count record-level calibration override + rejection counts
        if record.calibration is not None:
            override_count += record.calibration.override_count
            rejection_count += record.calibration.rejection_count
    # Rejection rate derived only from signal_count to keep it deterministic
    # and bounded; None if there are no signals.
    rejection_rate = (
        float(rejection_count) / float(sc) if sc > 0 else None
    )
    if rejection_rate is not None and rejection_rate > 1.0:
        # Cap caller-supplied counts so the rate stays within [0, 1] bounds.
        rejection_rate = 1.0
    return AgentEvaluationSummary(
        target=target,
        status=status,
        record_count=rc,
        signal_count=sc,
        agent_counts=agent_counts,
        outcome_counts=outcome_counts,
        grade_counts=grade_counts,
        horizon_counts=horizon_counts,
        correct_count=correct_count,
        incorrect_count=incorrect_count,
        partial_count=partial_count,
        inconclusive_count=inconclusive_count,
        false_positive_count=fp_count,
        false_negative_count=fn_count,
        override_count=override_count,
        rejection_count=rejection_count,
        review_required_count=review_required_count,
        rejection_rate=rejection_rate,
        top_warnings=list(warnings[:5]) if warnings else [],
        approved_for_execution=False,
    )


_IMPORTANT_UPSTREAM_ATTRS_FOR_REPORT = (
    "research_run_memory_record",
    "human_feedback_memory_report",
    "review_loop_report",
    "decision_packet",
)


def build_agent_evaluation_report(
    input_bundle,
    records=None,
    created_at=None,
    updated_at=None,
):
    ts = created_at or input_bundle.as_of or _DETERMINISTIC_TIMESTAMP_DEFAULT
    updated = updated_at or ts
    as_of = input_bundle.as_of or ts
    run_id = input_bundle.run_id
    report_id = make_agent_evaluation_report_id(
        target=input_bundle.target, as_of=as_of, run_id=run_id
    )
    _records = list(records or [])
    status, status_warnings = determine_agent_evaluation_status(
        records=_records, input_bundle=input_bundle
    )
    missing_warnings = []
    for attr in _IMPORTANT_UPSTREAM_ATTRS_FOR_REPORT:
        if getattr(input_bundle, attr, None) is None:
            missing_warnings.append(
                f"Missing optional upstream artifact: {attr}."
            )
    all_warnings = (
        list(input_bundle.warnings) + status_warnings + missing_warnings
    )
    source_ids = collect_agent_evaluation_source_ids(input_bundle, _records)
    evidence_ids = collect_agent_evaluation_evidence_ids(
        input_bundle, _records
    )
    artifact_refs = collect_agent_evaluation_artifact_refs(
        input_bundle, _records
    )
    summary = summarize_agent_evaluation(
        target=input_bundle.target,
        status=status,
        records=_records,
        warnings=all_warnings,
    )
    return AgentEvaluationReport(
        report_id=report_id,
        target=input_bundle.target,
        run_id=run_id,
        status=status,
        records=_records,
        summary=summary,
        source_ids=source_ids,
        evidence_ids=evidence_ids,
        artifact_refs=artifact_refs,
        warnings=all_warnings,
        created_at=ts,
        updated_at=updated,
        calculation_version=_CALCULATION_VERSION,
        approved_for_execution=False,
    )


# ----------------------------------------------------------------------------
# ToolResult adapter
# ----------------------------------------------------------------------------


def agent_evaluation_tool_result_from_report(report, run_id=None):
    _run_id = run_id or report.run_id or report.target
    outputs = {
        "report_id": report.report_id,
        "target": report.target,
        "status": report.status,
        "report": report.model_dump(),
        "summary": report.summary.model_dump(),
        "record_count": report.summary.record_count,
        "signal_count": report.summary.signal_count,
        "correct_count": report.summary.correct_count,
        "incorrect_count": report.summary.incorrect_count,
        "false_positive_count": report.summary.false_positive_count,
        "false_negative_count": report.summary.false_negative_count,
        "override_count": report.summary.override_count,
        "rejection_count": report.summary.rejection_count,
        "rejection_rate": report.summary.rejection_rate,
        "review_required_count": report.summary.review_required_count,
        "calculation_version": report.calculation_version,
        "approved_for_execution": False,
    }
    evidence_id = make_evidence_id(
        run_id=_run_id,
        tool_name=_AGENT_EVALUATION_TOOL_NAME,
        target=report.target,
        metric_group=_AGENT_EVALUATION_METRIC_GROUP,
        payload=outputs,
    )
    return ToolResult(
        tool_name=_AGENT_EVALUATION_TOOL_NAME,
        run_id=_run_id,
        ticker=report.target if report.target else None,
        evidence_id=evidence_id,
        inputs={"target": report.target, "report_id": report.report_id},
        outputs=outputs,
        description=(
            f"AgentEvaluationReport for {report.target} "
            f"(report_id={report.report_id!r}, status={report.status!r}, "
            f"records={report.summary.record_count}, "
            f"signals={report.summary.signal_count}, "
            f"correct={report.summary.correct_count}, "
            f"incorrect={report.summary.incorrect_count}, "
            f"false_positive={report.summary.false_positive_count}, "
            f"false_negative={report.summary.false_negative_count}, "
            f"override={report.summary.override_count}, "
            f"rejection={report.summary.rejection_count})."
        ),
    )


__all__ = [
    # Literal type aliases
    "AgentEvaluationStatus",
    "EvaluatedAgentType",
    "AgentEvaluationOutcome",
    "AgentEvaluationSignalType",
    "AgentEvaluationHorizon",
    "AgentEvaluationGrade",
    "AgentEvaluationEventType",
    "AgentEvaluationActor",
    # Pydantic models
    "AgentEvaluationSourceRef",
    "AgentEvaluationTargetRef",
    "AgentEvaluationSignal",
    "AgentEvaluationCalibration",
    "AgentEvaluationLogEntry",
    "AgentEvaluationRecord",
    "AgentEvaluationInputBundle",
    "AgentEvaluationSummary",
    "AgentEvaluationReport",
    # ID factories
    "make_agent_evaluation_record_id",
    "make_agent_evaluation_log_entry_id",
    "make_agent_evaluation_report_id",
    # Builders
    "build_agent_evaluation_target_ref",
    "build_agent_evaluation_signal",
    "build_agent_evaluation_calibration",
    "build_agent_evaluation_log_entry",
    "build_agent_evaluation_record",
    "build_agent_evaluation_report",
    # Status, collection, summary
    "determine_agent_evaluation_status",
    "collect_agent_evaluation_source_ids",
    "collect_agent_evaluation_evidence_ids",
    "collect_agent_evaluation_artifact_refs",
    "summarize_agent_evaluation",
    # ToolResult adapter
    "agent_evaluation_tool_result_from_report",
]
