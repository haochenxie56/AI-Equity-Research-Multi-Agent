"""
lib/reliability/validation_aggregator.py

Standalone validation aggregation layer for Phase 2 reliability foundations.

Design principles:
  - Pure Pydantic v2 models; no Streamlit, no LLM calls, no file I/O.
  - Converts warning strings from Phase 2 module validators into structured
    AggregatedValidationItem objects.
  - Converts existing ValidationReport / ValidationIssue objects from
    validate_agent_result() into aggregate items without modifying that
    validator's behaviour.
  - Aggregates items from multiple domains into a single ValidationAggregate.
  - All functions are deterministic and pure — they do not fetch real data.
  - Does NOT replace or modify validate_agent_result().
  - Does NOT wire into the live Streamlit app, live workflow, or live LLM calls.
  - No Critic Agent, Cockpit, or Debate Layer is implemented in this phase.

See docs/reliability_phase_2h_validation_aggregator.md for full design
rationale and rollout context.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lib.reliability.adapters import make_evidence_id, stable_hash_payload
from lib.reliability.schemas import ToolResult, ValidationReport


# ---------------------------------------------------------------------------
# Literal type aliases
# ---------------------------------------------------------------------------

ValidationDomain = Literal[
    "agent_result",
    "horizon",
    "macro",
    "allocation",
    "option",
    "news",
    "catalyst",
    "earnings",
    "estimate_revision",
    "tool_result",
    "evidence",
    "system",
    "unknown",
]

ValidationSeverity = Literal[
    "critical",
    "warning",
    "info",
]

ValidationStatus = Literal[
    "pass",
    "pass_with_warnings",
    "fail",
    "unknown",
]

ValidationItemType = Literal[
    "schema",
    "evidence_binding",
    "missing_data",
    "stale_data",
    "duplicate_data",
    "mismatch",
    "risk_limit",
    "unsupported",
    "calculation",
    "provenance",
    "safety",
    "other",
]


# ---------------------------------------------------------------------------
# Private constants
# ---------------------------------------------------------------------------

_AGG_TOOL_NAME: str = "validation_aggregate"
_AGG_METRIC_GROUP: str = "validation_aggregate"

# Map ValidationIssue.code → ValidationItemType
_CODE_TO_ITEM_TYPE: dict[str, ValidationItemType] = {
    "MISSING_EVIDENCE": "missing_data",
    "INVALID_EVIDENCE_ID": "evidence_binding",
    "UNSUPPORTED_NUMERIC_CLAIM": "unsupported",
    "WEAK_NUMERIC_EVIDENCE_BINDING": "evidence_binding",
    "RISK_NUMERIC_NO_EVIDENCE": "evidence_binding",
    "INVALID_RISK_EVIDENCE_ID": "evidence_binding",
    "INVALID_EVIDENCE_TOOL_BINDING": "evidence_binding",
    "INVALID_EVIDENCE_METRIC_BINDING": "evidence_binding",
    "INVALID_EVIDENCE_FIELD_PATH_BINDING": "evidence_binding",
}

# Map ValidationIssue.severity → ValidationSeverity
_ISSUE_SEVERITY_MAP: dict[str, ValidationSeverity] = {
    "error": "critical",
    "critical": "critical",
    "fail": "critical",
    "warning": "warning",
    "info": "info",
}


# ---------------------------------------------------------------------------
# 1. AggregatedValidationItem
# ---------------------------------------------------------------------------

class AggregatedValidationItem(BaseModel):
    """
    One structured validation item produced by the aggregation layer.

    Fields:
        item_id:     Non-empty deterministic identifier for this item.
        domain:      Validation domain this item originated from.
        severity:    Severity level; defaults to ``"warning"``.
        item_type:   Classification of the validation condition.
        message:     Non-empty human-readable description of the issue.
        source_name: Optional source name (module, tool, snapshot id, etc.).
        object_id:   Optional ID of the source object (snapshot_id, agent_name, etc.).
        evidence_id: Optional evidence_id that triggered this item.
        field_path:  Optional field path that triggered this item.
        blocking:    True if this item should block downstream processing.
        metadata:    Arbitrary key/value metadata.
    """

    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(min_length=1)
    domain: ValidationDomain
    severity: ValidationSeverity = "warning"
    item_type: ValidationItemType = "other"
    message: str = Field(min_length=1)
    source_name: Optional[str] = None
    object_id: Optional[str] = None
    evidence_id: Optional[str] = None
    field_path: Optional[str] = None
    blocking: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace_fields(self) -> "AggregatedValidationItem":
        for field_name in ("item_id", "message"):
            value = getattr(self, field_name)
            if value is not None and not value.strip():
                raise ValueError(
                    f"'{field_name}' must not be whitespace-only; got {value!r}."
                )
        return self


# ---------------------------------------------------------------------------
# 2. ValidationAggregate
# ---------------------------------------------------------------------------

class ValidationAggregate(BaseModel):
    """
    Aggregated validation summary for one or more Phase 2 module outputs.

    Fields:
        aggregate_id:    Non-empty unique identifier for this aggregate.
        schema_version:  Version of this schema contract.
        as_of:           Non-empty snapshot date/datetime string.
        status:          Overall validation status (auto-normalised from items).
        items:           All aggregated validation items.
        source_domains:  Unique, sorted domains present in items (auto-normalised).
        critical_count:  Number of critical severity items (auto-normalised from items).
        warning_count:   Number of warning severity items (auto-normalised from items).
        info_count:      Number of info severity items (auto-normalised from items).
        blocking_count:  Number of blocking items (auto-normalised from items).
        metadata:        Arbitrary key/value metadata.

    Normalisation:
        After construction, derived fields (counts, status, source_domains) are
        always recomputed from the ``items`` list so that manually constructed
        instances cannot be internally inconsistent.  Caller-supplied values for
        these fields are accepted by the field validator (``ge=0`` still rejects
        negative counts) but are then replaced by the normalised values.

        Normalisation rules:
          - ``critical_count``  = items with severity == ``"critical"``
          - ``warning_count``   = items with severity == ``"warning"``
          - ``info_count``      = items with severity == ``"info"``
          - ``blocking_count``  = items with blocking == ``True``
          - ``source_domains``  = sorted unique ``item.domain`` values
          - ``status``          = ``"fail"`` if critical_count > 0 or blocking_count > 0;
                                  ``"pass_with_warnings"`` if warning_count > 0;
                                  ``"pass"`` otherwise
          - Empty items list normalises to status ``"pass"``, all counts 0,
            source_domains ``[]``.
    """

    model_config = ConfigDict(extra="forbid")

    aggregate_id: str = Field(min_length=1)
    schema_version: str = "1.0"
    as_of: str = Field(min_length=1)
    status: ValidationStatus = "unknown"
    items: list[AggregatedValidationItem] = Field(default_factory=list)
    source_domains: list[ValidationDomain] = Field(default_factory=list)
    critical_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    info_count: int = Field(default=0, ge=0)
    blocking_count: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace_fields(self) -> "ValidationAggregate":
        for field_name in ("aggregate_id", "as_of"):
            value = getattr(self, field_name)
            if value is not None and not value.strip():
                raise ValueError(
                    f"'{field_name}' must not be whitespace-only; got {value!r}."
                )
        return self

    @model_validator(mode="after")
    def _normalize_derived_fields(self) -> "ValidationAggregate":
        """Recompute all derived fields from items to guarantee consistency."""
        items = self.items
        self.critical_count = sum(1 for it in items if it.severity == "critical")
        self.warning_count = sum(1 for it in items if it.severity == "warning")
        self.info_count = sum(1 for it in items if it.severity == "info")
        self.blocking_count = sum(1 for it in items if it.blocking)
        self.source_domains = sorted(  # type: ignore[assignment]
            set(it.domain for it in items)
        )
        if self.critical_count > 0 or self.blocking_count > 0:
            self.status = "fail"
        elif self.warning_count > 0:
            self.status = "pass_with_warnings"
        else:
            self.status = "pass"
        return self


# ---------------------------------------------------------------------------
# Helper 1: make_validation_item_id
# ---------------------------------------------------------------------------

def make_validation_item_id(
    domain: ValidationDomain,
    message: str,
    source_name: Optional[str] = None,
    object_id: Optional[str] = None,
    field_path: Optional[str] = None,
) -> str:
    """
    Build a deterministic, stable item_id for an AggregatedValidationItem.

    Uses stable SHA-256 hashing of the key fields.
    Same inputs always produce the same ID.
    Different domain, message, source_name, object_id, or field_path
    produce a different ID.

    Args:
        domain:      Validation domain string.
        message:     Validation message string.
        source_name: Optional source name.
        object_id:   Optional object identifier.
        field_path:  Optional field path string.

    Returns:
        A short, deterministic hex string prefixed by the domain.

    Examples::

        make_validation_item_id("news", "No events.")  # → "news:3a9f..."
        make_validation_item_id("news", "No events.")  # → same ID
    """
    payload = {
        "domain": domain,
        "message": message,
        "source_name": source_name or "",
        "object_id": object_id or "",
        "field_path": field_path or "",
    }
    hash_suffix = stable_hash_payload(payload, length=16)
    return f"{domain}:{hash_suffix}"


# ---------------------------------------------------------------------------
# Helper 2: warning_to_validation_item
# ---------------------------------------------------------------------------

def warning_to_validation_item(
    warning: str,
    domain: ValidationDomain,
    source_name: Optional[str] = None,
    object_id: Optional[str] = None,
    severity: ValidationSeverity = "warning",
    item_type: ValidationItemType = "other",
    field_path: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> AggregatedValidationItem:
    """
    Convert a warning string into a structured AggregatedValidationItem.

    The item_id is deterministic based on domain, message, source_name,
    object_id, and field_path.  The blocking flag is automatically set to
    True when severity is ``"critical"``.

    Does not mutate the metadata dict.

    Args:
        warning:     Non-empty warning message string.
        domain:      Validation domain this warning came from.
        source_name: Optional source name (module, snapshot_id, etc.).
        object_id:   Optional ID of the source object.
        severity:    Severity level; defaults to ``"warning"``.
        item_type:   Classification; defaults to ``"other"``.
        field_path:  Optional field path string.
        metadata:    Optional metadata dict (shallow-copied, not mutated).

    Returns:
        A new AggregatedValidationItem.

    Examples::

        item = warning_to_validation_item(
            "No events in snapshot.", "news", source_name="news_module"
        )
        assert item.severity == "warning"
        assert not item.blocking
    """
    item_id = make_validation_item_id(
        domain=domain,
        message=warning,
        source_name=source_name,
        object_id=object_id,
        field_path=field_path,
    )
    return AggregatedValidationItem(
        item_id=item_id,
        domain=domain,
        severity=severity,
        item_type=item_type,
        message=warning,
        source_name=source_name,
        object_id=object_id,
        field_path=field_path,
        blocking=severity == "critical",
        metadata=dict(metadata) if metadata is not None else {},
    )


# ---------------------------------------------------------------------------
# Helper 3: validation_report_to_items
# ---------------------------------------------------------------------------

def validation_report_to_items(
    report: ValidationReport,
) -> list[AggregatedValidationItem]:
    """
    Convert an existing AgentResult ValidationReport into AggregatedValidationItems.

    This function does NOT change or call validate_agent_result().  It only
    converts already-produced ValidationReport objects.

    Severity mapping from ValidationIssue.severity:
        - ``"error"`` / ``"critical"`` / ``"fail"`` → ``"critical"``
        - ``"warning"`` → ``"warning"``
        - ``"info"`` → ``"info"``
        - anything else → ``"warning"``

    Item type mapping from ValidationIssue.code:
        - ``MISSING_EVIDENCE`` → ``"missing_data"``
        - ``INVALID_EVIDENCE_ID``, ``INVALID_RISK_EVIDENCE_ID``,
          ``WEAK_NUMERIC_EVIDENCE_BINDING``, ``RISK_NUMERIC_NO_EVIDENCE``,
          ``INVALID_EVIDENCE_TOOL_BINDING``, ``INVALID_EVIDENCE_METRIC_BINDING``,
          ``INVALID_EVIDENCE_FIELD_PATH_BINDING`` → ``"evidence_binding"``
        - ``UNSUPPORTED_NUMERIC_CLAIM`` → ``"unsupported"``
        - others → ``"other"``

    Domain is always ``"agent_result"`` unless issue metadata indicates otherwise.

    Does not modify ValidationReport or ValidationIssue.

    Args:
        report: An existing ValidationReport from validate_agent_result().

    Returns:
        A list of AggregatedValidationItem (may be empty for a clean report).

    Examples::

        report = validate_agent_result(agent_result, store)
        items = validation_report_to_items(report)
    """
    result: list[AggregatedValidationItem] = []

    for issue in report.issues:
        severity: ValidationSeverity = _ISSUE_SEVERITY_MAP.get(
            issue.severity.lower(), "warning"
        )
        item_type: ValidationItemType = _CODE_TO_ITEM_TYPE.get(
            issue.code, "other"
        )
        item = warning_to_validation_item(
            warning=issue.message,
            domain="agent_result",
            source_name=report.target_name,
            object_id=issue.location or None,
            severity=severity,
            item_type=item_type,
        )
        result.append(item)

    return result


# ---------------------------------------------------------------------------
# Helper 4: aggregate_validation_items
# ---------------------------------------------------------------------------

def aggregate_validation_items(
    aggregate_id: str,
    as_of: str,
    items: list[AggregatedValidationItem],
    metadata: Optional[dict[str, Any]] = None,
) -> ValidationAggregate:
    """
    Aggregate a list of AggregatedValidationItem objects into a ValidationAggregate.

    Behavior:
        - De-duplicates items with identical item_ids (first occurrence wins).
        - Counts critical/warning/info/blocking items.
        - Builds a deterministic, sorted source_domains list.
        - Status logic:
          - ``"fail"`` if any item has severity ``"critical"`` or blocking is True.
          - ``"pass_with_warnings"`` if any item has severity ``"warning"``.
          - ``"pass"`` if only info items or no items.
        - Does not mutate the input items list or metadata dict.

    Args:
        aggregate_id: Non-empty unique identifier for the resulting aggregate.
        as_of:        Non-empty date/datetime string.
        items:        List of AggregatedValidationItem to aggregate.
        metadata:     Optional metadata dict (shallow-copied, not mutated).

    Returns:
        A new ValidationAggregate.

    Examples::

        agg = aggregate_validation_items("agg_001", "2026-05-22", [item1, item2])
        assert agg.status in ("pass", "pass_with_warnings", "fail")
    """
    # De-duplicate by item_id (first occurrence wins)
    seen_ids: set[str] = set()
    deduped: list[AggregatedValidationItem] = []
    for item in items:
        if item.item_id not in seen_ids:
            seen_ids.add(item.item_id)
            deduped.append(item)

    critical_count = sum(1 for it in deduped if it.severity == "critical")
    warning_count = sum(1 for it in deduped if it.severity == "warning")
    info_count = sum(1 for it in deduped if it.severity == "info")
    blocking_count = sum(1 for it in deduped if it.blocking)

    # De-duplicated, sorted domains
    source_domains: list[ValidationDomain] = sorted(  # type: ignore[assignment]
        set(it.domain for it in deduped)
    )

    # Status logic
    if critical_count > 0 or blocking_count > 0:
        status: ValidationStatus = "fail"
    elif warning_count > 0:
        status = "pass_with_warnings"
    else:
        status = "pass"

    return ValidationAggregate(
        aggregate_id=aggregate_id,
        as_of=as_of,
        status=status,
        items=deduped,
        source_domains=source_domains,
        critical_count=critical_count,
        warning_count=warning_count,
        info_count=info_count,
        blocking_count=blocking_count,
        metadata=dict(metadata) if metadata is not None else {},
    )


# ---------------------------------------------------------------------------
# Helper 5: aggregate_warning_groups
# ---------------------------------------------------------------------------

def aggregate_warning_groups(
    aggregate_id: str,
    as_of: str,
    warning_groups: dict[ValidationDomain, list[str]],
    source_name_by_domain: Optional[dict[ValidationDomain, str]] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> ValidationAggregate:
    """
    Convert domain-keyed warning string groups into a ValidationAggregate.

    Behavior:
        - Converts each warning string into an AggregatedValidationItem
          via warning_to_validation_item().
        - Uses severity ``"warning"`` for all items.
        - Aggregates with aggregate_validation_items().
        - Empty warning groups produce a ``"pass"`` status aggregate.
        - Does not mutate inputs.

    Args:
        aggregate_id:         Non-empty unique identifier.
        as_of:                Non-empty date/datetime string.
        warning_groups:       Dict of domain → list of warning strings.
        source_name_by_domain: Optional dict of domain → source name hint.
        metadata:             Optional metadata dict.

    Returns:
        A ValidationAggregate.

    Examples::

        agg = aggregate_warning_groups(
            "agg_002", "2026-05-22",
            {"news": ["No events in snapshot."], "catalyst": []}
        )
        assert agg.status == "pass_with_warnings"
    """
    items: list[AggregatedValidationItem] = []
    sn_map = source_name_by_domain or {}

    for domain, warnings in warning_groups.items():
        source_name = sn_map.get(domain)
        for warning in warnings:
            item = warning_to_validation_item(
                warning=warning,
                domain=domain,
                source_name=source_name,
                severity="warning",
            )
            items.append(item)

    return aggregate_validation_items(
        aggregate_id=aggregate_id,
        as_of=as_of,
        items=items,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Helper 6: merge_validation_aggregates
# ---------------------------------------------------------------------------

def merge_validation_aggregates(
    aggregate_id: str,
    as_of: str,
    aggregates: list[ValidationAggregate],
    metadata: Optional[dict[str, Any]] = None,
) -> ValidationAggregate:
    """
    Merge items from multiple ValidationAggregate objects into one.

    Behavior:
        - Collects all items from every aggregate.
        - De-duplicates by item_id (first occurrence wins, preserving order
          across aggregates in list order).
        - Recomputes counts, status, and source_domains.
        - Does not mutate input aggregates or their item lists.

    Args:
        aggregate_id: Non-empty unique identifier for the merged aggregate.
        as_of:        Non-empty date/datetime string.
        aggregates:   List of ValidationAggregate to merge.
        metadata:     Optional metadata dict (shallow-copied, not mutated).

    Returns:
        A new ValidationAggregate.

    Examples::

        merged = merge_validation_aggregates("merged_001", "2026-05-22", [agg1, agg2])
        assert merged.critical_count == agg1.critical_count + agg2.critical_count
    """
    all_items: list[AggregatedValidationItem] = []
    for agg in aggregates:
        all_items.extend(agg.items)

    return aggregate_validation_items(
        aggregate_id=aggregate_id,
        as_of=as_of,
        items=all_items,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Helper 7: summarize_validation_aggregate
# ---------------------------------------------------------------------------

def summarize_validation_aggregate(aggregate: ValidationAggregate) -> dict[str, Any]:
    """
    Return a concise dict summary of a ValidationAggregate.

    Returns:
        Dict with keys:
            - ``aggregate_id``
            - ``status``
            - ``total_items``
            - ``critical_count``
            - ``warning_count``
            - ``info_count``
            - ``blocking_count``
            - ``source_domains``
            - ``top_messages`` — up to 10 message strings from items
            - ``metadata_keys`` — list of metadata keys (if non-empty)

    Examples::

        summary = summarize_validation_aggregate(agg)
        assert "status" in summary
        assert "top_messages" in summary
    """
    top_messages = [it.message for it in aggregate.items[:10]]
    summary: dict[str, Any] = {
        "aggregate_id": aggregate.aggregate_id,
        "status": aggregate.status,
        "total_items": len(aggregate.items),
        "critical_count": aggregate.critical_count,
        "warning_count": aggregate.warning_count,
        "info_count": aggregate.info_count,
        "blocking_count": aggregate.blocking_count,
        "source_domains": list(aggregate.source_domains),
        "top_messages": top_messages,
    }
    if aggregate.metadata:
        summary["metadata_keys"] = sorted(aggregate.metadata.keys())
    return summary


# ---------------------------------------------------------------------------
# Helper 8: collect_phase2_validation_warnings
# ---------------------------------------------------------------------------

def collect_phase2_validation_warnings(
    horizon_result=None,
    macro_snapshot=None,
    allocation_decision_set=None,
    option_decision_set=None,
    news_snapshot=None,
    catalyst_snapshot=None,
) -> dict[ValidationDomain, list[str]]:
    """
    Convenience helper that collects validation warnings from Phase 2 modules.

    Calls existing validation helpers only when the corresponding object is
    provided.  Does not fetch data, does not import live app modules, does
    not call LLMs.

    If a module or helper is unavailable (ImportError), a fallback warning
    string is recorded under the originating domain (e.g., ``"news"``,
    ``"catalyst"``) rather than crashing.  It is never placed under
    ``"system"`` unless the implementation explicitly does so.

    Args:
        horizon_result:         Optional HorizonDecisionSet.
        macro_snapshot:         Optional MacroSnapshot.
        allocation_decision_set: Optional AllocationDecisionSet.
        option_decision_set:    Optional OptionStrategyDecisionSet.
        news_snapshot:          Optional NewsSnapshot.
        catalyst_snapshot:      Optional CatalystSnapshot.

    Returns:
        Dict of ValidationDomain → list of warning strings.
        Only domains with non-None input are present in the result.

    Examples::

        groups = collect_phase2_validation_warnings(news_snapshot=snap)
        assert "news" in groups
    """
    groups: dict[ValidationDomain, list[str]] = {}

    if horizon_result is not None:
        try:
            from lib.reliability.horizon import validate_horizon_decision_set
            groups["horizon"] = validate_horizon_decision_set(horizon_result)
        except ImportError:
            groups["horizon"] = [
                "validate_horizon_decision_set unavailable: lib.reliability.horizon could not be imported."
            ]
        except Exception as exc:
            groups["horizon"] = [f"horizon validation error: {exc}"]

    if macro_snapshot is not None:
        try:
            from lib.reliability.macro import validate_macro_snapshot
            groups["macro"] = validate_macro_snapshot(macro_snapshot)
        except ImportError:
            groups["macro"] = [
                "validate_macro_snapshot unavailable: lib.reliability.macro could not be imported."
            ]
        except Exception as exc:
            groups["macro"] = [f"macro validation error: {exc}"]

    if allocation_decision_set is not None:
        try:
            from lib.reliability.allocation import validate_allocation_decision_set
            groups["allocation"] = validate_allocation_decision_set(allocation_decision_set)
        except ImportError:
            groups["allocation"] = [
                "validate_allocation_decision_set unavailable: lib.reliability.allocation could not be imported."
            ]
        except Exception as exc:
            groups["allocation"] = [f"allocation validation error: {exc}"]

    if option_decision_set is not None:
        try:
            from lib.reliability.options import validate_option_strategy_decision_set
            groups["option"] = validate_option_strategy_decision_set(option_decision_set)
        except ImportError:
            groups["option"] = [
                "validate_option_strategy_decision_set unavailable: lib.reliability.options could not be imported."
            ]
        except Exception as exc:
            groups["option"] = [f"option validation error: {exc}"]

    if news_snapshot is not None:
        try:
            from lib.reliability.news import validate_news_snapshot
            groups["news"] = validate_news_snapshot(news_snapshot)
        except ImportError:
            groups["news"] = [
                "validate_news_snapshot unavailable: lib.reliability.news could not be imported."
            ]
        except Exception as exc:
            groups["news"] = [f"news validation error: {exc}"]

    if catalyst_snapshot is not None:
        try:
            from lib.reliability.catalysts import validate_catalyst_snapshot
            groups["catalyst"] = validate_catalyst_snapshot(catalyst_snapshot)
        except ImportError:
            groups["catalyst"] = [
                "validate_catalyst_snapshot unavailable: lib.reliability.catalysts could not be imported."
            ]
        except Exception as exc:
            groups["catalyst"] = [f"catalyst validation error: {exc}"]

    return groups


# ---------------------------------------------------------------------------
# Helper 9: validation_aggregate_tool_result_from_aggregate
# ---------------------------------------------------------------------------

def validation_aggregate_tool_result_from_aggregate(
    run_id: str,
    aggregate: ValidationAggregate,
    target: str = "validation",
    calculation_version: str = "validation_aggregator_v1",
) -> ToolResult:
    """
    Wrap a ValidationAggregate into the existing ToolResult model.

    The resulting ToolResult is suitable for submission to
    EvidenceStore.add_tool_result().  The caller is responsible for
    persisting it — this function does not write to disk.

    Args:
        run_id:              Run context ID (from create_run_context).
        aggregate:           ValidationAggregate to wrap.
        target:              Research target string; defaults to ``"validation"``.
        calculation_version: Schema/version tag embedded in outputs.

    Returns:
        A ToolResult with:
        - ``tool_name = "validation_aggregate"`` (stable)
        - ``evidence_id`` — deterministic hash of outputs.
        - ``outputs`` — full serialised aggregate dict plus
          ``calculation_version``.
        - ``inputs`` — ``{aggregate_id, as_of, target, calculation_version}``.
        - ``description`` — includes aggregate_id, status, and counts.

    Determinism guarantee:
        Calling this function twice with the same ``run_id`` and ``aggregate``
        (identical field values) produces the same ``evidence_id``.

    Examples::

        tr = validation_aggregate_tool_result_from_aggregate("run_001", agg)
        assert tr.tool_name == "validation_aggregate"
    """
    agg_dict = aggregate.model_dump()
    outputs: dict[str, Any] = {
        **agg_dict,
        "calculation_version": calculation_version,
    }

    evidence_id = make_evidence_id(
        run_id=run_id,
        tool_name=_AGG_TOOL_NAME,
        target=target,
        metric_group=_AGG_METRIC_GROUP,
        payload=outputs,
    )

    description = (
        f"ValidationAggregate {aggregate.aggregate_id!r}"
        f" as_of={aggregate.as_of!r}"
        f" status={aggregate.status!r}"
        f" (critical={aggregate.critical_count}"
        f" warning={aggregate.warning_count}"
        f" info={aggregate.info_count}"
        f" blocking={aggregate.blocking_count})"
    )

    return ToolResult(
        evidence_id=evidence_id,
        tool_name=_AGG_TOOL_NAME,
        run_id=run_id,
        inputs={
            "aggregate_id": aggregate.aggregate_id,
            "as_of": aggregate.as_of,
            "target": target,
            "calculation_version": calculation_version,
        },
        outputs=outputs,
        description=description,
    )
