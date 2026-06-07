"""
lib/reliability/staleness.py

Standalone staleness/freshness checking layer for reliability artifacts
and Phase 2 snapshots.

Design principles:
  - Pure Pydantic v2 models; no Streamlit, no LLM calls, no file I/O.
  - Evaluates freshness of timestamps in reliability artifacts without
    fetching new data.
  - Does NOT wire into live app, live workflow, or live LLM calls.
  - Does NOT fetch real data.
  - Integrates with ValidationAggregate via staleness_findings_to_validation_items().
  - All check_* functions accept domain objects via duck typing so that
    TYPE_CHECKING imports are not needed at runtime.

See docs/reliability_phase_2i_staleness_checker.md for full design.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from lib.reliability.adapters import make_evidence_id, stable_hash_payload
from lib.reliability.schemas import ToolResult
from lib.reliability.validation_aggregator import (
    AggregatedValidationItem,
    ValidationDomain,
    ValidationItemType,
    ValidationSeverity,
    make_validation_item_id,
)


# ---------------------------------------------------------------------------
# Literal type aliases
# ---------------------------------------------------------------------------

StalenessStatus = Literal["fresh", "near_stale", "stale", "expired", "unknown"]

StalenessDomain = Literal[
    "tool_result",
    "macro",
    "allocation",
    "option",
    "news",
    "catalyst",
    "earnings",
    "estimate_revision",
    "validation",
    "generic",
    "unknown",
]

StalenessSeverity = Literal["info", "warning", "critical"]

TimestampRole = Literal[
    "as_of",
    "generated_at",
    "published_at",
    "event_date",
    "expiration",
    "revision_date",
    "report_date",
    "unknown",
]


# ---------------------------------------------------------------------------
# Private constants
# ---------------------------------------------------------------------------

_STALENESS_TOOL_NAME: str = "staleness_report"
_STALENESS_METRIC_GROUP: str = "staleness_report"

_DEFAULT_MAX_AGE_DAYS: dict[str, float] = {
    "news": 7.0,
    "macro": 30.0,
    "option": 1.0,
    "allocation": 7.0,
    "catalyst": 30.0,
    "earnings": 30.0,
    "estimate_revision": 30.0,
    "tool_result": 14.0,
    "validation": 7.0,
    "generic": 14.0,
    "unknown": 14.0,
}

# Maps StalenessDomain → ValidationDomain for conversion helpers.
# "validation", "generic", "unknown" → "unknown" (no exact match in ValidationDomain).
_STALENESS_TO_VALIDATION_DOMAIN: dict[str, str] = {
    "tool_result": "tool_result",
    "macro": "macro",
    "allocation": "allocation",
    "option": "option",
    "news": "news",
    "catalyst": "catalyst",
    "earnings": "earnings",
    "estimate_revision": "estimate_revision",
    "validation": "unknown",
    "generic": "unknown",
    "unknown": "unknown",
}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class StalenessPolicy(BaseModel):
    """
    Staleness evaluation policy for a specific domain.

    Fields:
        policy_id:             Non-empty unique identifier for this policy.
        domain:                Domain this policy applies to.
        max_age_days:          Days before data is considered stale (gt=0 if provided).
                               None means no age-based staleness threshold is enforced.
        near_stale_ratio:      Fraction of max_age_days for the near_stale threshold (0–1).
        expiration_grace_days: Days of grace after expiration before marking as expired.
                               0.0 means any past expiration is immediately expired.
        allow_unknown:         When True, missing/unparseable timestamps produce
                               ``"warning"`` severity; when False, ``"critical"``.
        near_stale_severity:   Severity for near_stale findings (default ``"info"``).
        stale_severity:        Severity for stale findings (default ``"warning"``).
        expired_severity:      Severity for expired findings (default ``"critical"``).
        metadata:              Arbitrary key/value metadata.
    """

    model_config = ConfigDict(extra="forbid")

    policy_id: str = Field(min_length=1)
    domain: StalenessDomain = "generic"
    max_age_days: Optional[float] = Field(default=None, gt=0)
    near_stale_ratio: float = Field(default=0.8, ge=0.0, le=1.0)
    expiration_grace_days: float = Field(default=0.0, ge=0.0)
    allow_unknown: bool = True
    near_stale_severity: StalenessSeverity = "info"
    stale_severity: StalenessSeverity = "warning"
    expired_severity: StalenessSeverity = "critical"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace_fields(self) -> "StalenessPolicy":
        if not self.policy_id.strip():
            raise ValueError("policy_id must not be whitespace-only.")
        return self

    @property
    def unknown_severity(self) -> StalenessSeverity:
        """Severity for unknown/missing timestamps, derived from allow_unknown."""
        return "warning" if self.allow_unknown else "critical"


class StalenessFinding(BaseModel):
    """
    One staleness finding for a single timestamp in a reliability artifact.

    Fields:
        finding_id:      Deterministic unique identifier.
        domain:          Staleness domain this finding belongs to.
        status:          Freshness status of the evaluated timestamp.
        severity:        Severity level derived from status and policy.
        message:         Human-readable description (non-empty).
        timestamp_value: Raw timestamp string that was evaluated (may be None).
        timestamp_role:  Role of the timestamp being evaluated (default ``"unknown"``).
        as_of:           Reference date used for comparison.
        age_days:        Days from timestamp to reference (>= 0 if provided; None = unknown).
        max_age_days:    Stale threshold used for this finding (> 0 if provided;
                         None for expiration checks or when no age limit applies).
        object_id:       Optional ID of the source object.
        field_path:      Optional field path in the source artifact (dot-notation).
        evidence_id:     Optional evidence_id from an associated ToolResult.
        source_name:     Optional source name (snapshot_id, tool_name, etc.).
        metadata:        Arbitrary key/value metadata.
    """

    model_config = ConfigDict(extra="forbid")

    finding_id: str = Field(min_length=1)
    domain: StalenessDomain
    status: StalenessStatus
    severity: StalenessSeverity
    message: str = Field(min_length=1)
    timestamp_value: Optional[str] = None
    timestamp_role: TimestampRole = "unknown"
    as_of: str = Field(min_length=1)
    age_days: Optional[float] = None
    max_age_days: Optional[float] = None
    object_id: Optional[str] = None
    field_path: Optional[str] = None
    evidence_id: Optional[str] = None
    source_name: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace_fields(self) -> "StalenessFinding":
        for field_name in ("finding_id", "message", "as_of"):
            value = getattr(self, field_name)
            if value is not None and not value.strip():
                raise ValueError(
                    f"'{field_name}' must not be whitespace-only; got {value!r}."
                )
        return self

    @model_validator(mode="after")
    def _check_numeric_constraints(self) -> "StalenessFinding":
        if self.age_days is not None and self.age_days < 0:
            raise ValueError(
                f"age_days must be >= 0 if provided; got {self.age_days!r}."
            )
        if self.max_age_days is not None and self.max_age_days <= 0:
            raise ValueError(
                f"max_age_days must be > 0 if provided; got {self.max_age_days!r}."
            )
        return self


class StalenessReport(BaseModel):
    """
    Aggregated staleness report for one or more domain checks.

    Fields:
        report_id:        Non-empty unique identifier.
        schema_version:   Schema version string.
        as_of:            Reference date for all staleness evaluations.
        target:           Optional research target (ticker, domain, etc.).
        status:           Overall staleness status (auto-normalised from findings).
                          Priority: expired > stale > near_stale > unknown > fresh.
        findings:         All staleness findings (de-duplicated by finding_id).
        domains_present:  Sorted unique domains from findings (auto-normalised).
        fresh_count:      Count of fresh findings (auto-normalised).
        near_stale_count: Count of near_stale findings (auto-normalised).
        stale_count:      Count of stale findings (auto-normalised).
        expired_count:    Count of expired findings (auto-normalised).
        unknown_count:    Count of unknown findings (auto-normalised).
        critical_count:   Count of critical severity findings (auto-normalised).
        warning_count:    Count of warning severity findings (auto-normalised).
        info_count:       Count of info severity findings (auto-normalised).
        metadata:         Arbitrary key/value metadata.

    Normalisation:
        After construction, all derived fields are recomputed from findings.
        Empty findings list normalises to status ``"fresh"``, all counts 0.
    """

    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(min_length=1)
    schema_version: str = "1.0"
    as_of: str = Field(min_length=1)
    target: Optional[str] = None
    status: StalenessStatus = "fresh"
    findings: list[StalenessFinding] = Field(default_factory=list)
    domains_present: list[StalenessDomain] = Field(default_factory=list)
    fresh_count: int = Field(default=0, ge=0)
    near_stale_count: int = Field(default=0, ge=0)
    stale_count: int = Field(default=0, ge=0)
    expired_count: int = Field(default=0, ge=0)
    unknown_count: int = Field(default=0, ge=0)
    critical_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    info_count: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_whitespace_fields(self) -> "StalenessReport":
        for field_name in ("report_id", "as_of"):
            value = getattr(self, field_name)
            if value is not None and not value.strip():
                raise ValueError(
                    f"'{field_name}' must not be whitespace-only; got {value!r}."
                )
        return self

    @model_validator(mode="after")
    def _normalize_derived_fields(self) -> "StalenessReport":
        """Recompute all derived fields from findings to guarantee consistency."""
        findings = self.findings
        self.fresh_count = sum(1 for f in findings if f.status == "fresh")
        self.near_stale_count = sum(1 for f in findings if f.status == "near_stale")
        self.stale_count = sum(1 for f in findings if f.status == "stale")
        self.expired_count = sum(1 for f in findings if f.status == "expired")
        self.unknown_count = sum(1 for f in findings if f.status == "unknown")
        self.critical_count = sum(1 for f in findings if f.severity == "critical")
        self.warning_count = sum(1 for f in findings if f.severity == "warning")
        self.info_count = sum(1 for f in findings if f.severity == "info")
        self.domains_present = sorted(  # type: ignore[assignment]
            set(f.domain for f in findings)
        )
        # Status priority: expired > stale > near_stale > unknown > fresh
        if self.expired_count > 0:
            self.status = "expired"
        elif self.stale_count > 0:
            self.status = "stale"
        elif self.near_stale_count > 0:
            self.status = "near_stale"
        elif self.unknown_count > 0:
            self.status = "unknown"
        else:
            self.status = "fresh"  # all fresh findings, or no findings at all
        return self


# ---------------------------------------------------------------------------
# Helper 1: parse_iso_like_datetime
# ---------------------------------------------------------------------------

def parse_iso_like_datetime(ts: str) -> datetime:
    """
    Parse an ISO-like date or datetime string into a timezone-aware datetime.

    Accepted formats:
        - ``"YYYY-MM-DD"`` — assumed midnight UTC.
        - ``"YYYY-MM-DDTHH:MM:SS"`` — naive, assumed UTC.
        - ``"YYYY-MM-DDTHH:MM:SSZ"`` — UTC (Z suffix).
        - ``"YYYY-MM-DDTHH:MM:SS+HH:MM"`` — offset-aware.

    Args:
        ts: The timestamp string to parse.

    Returns:
        A timezone-aware datetime object (UTC if no offset is specified).

    Raises:
        ValueError: If the string cannot be parsed.

    Examples::

        dt = parse_iso_like_datetime("2026-05-22")
        assert dt.tzinfo is not None
    """
    ts = ts.strip()
    # Date-only: exactly "YYYY-MM-DD"
    if len(ts) == 10 and ts[4] == "-" and ts[7] == "-":
        try:
            d = date.fromisoformat(ts)
            return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        except ValueError:
            pass
    # Normalize 'Z' suffix for fromisoformat compatibility (Python <3.11)
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        raise ValueError(f"Cannot parse datetime string: {ts!r}")


# ---------------------------------------------------------------------------
# Helper 2: days_between
# ---------------------------------------------------------------------------

def days_between(earlier: str, later: str) -> float:
    """
    Compute float days from ``earlier`` to ``later``.

    Positive = ``later`` is after ``earlier``; negative = ``later`` is before.
    Both strings are parsed with :func:`parse_iso_like_datetime`.

    Args:
        earlier: The earlier timestamp string.
        later:   The later timestamp string.

    Returns:
        Float number of days from earlier to later.

    Raises:
        ValueError: If either string cannot be parsed.

    Examples::

        d = days_between("2026-05-15", "2026-05-22")
        assert abs(d - 7.0) < 0.001
    """
    dt_a = parse_iso_like_datetime(earlier)
    dt_b = parse_iso_like_datetime(later)
    delta = dt_b - dt_a
    return delta.total_seconds() / 86400.0


# ---------------------------------------------------------------------------
# Helper 3: make_staleness_finding_id
# ---------------------------------------------------------------------------

def make_staleness_finding_id(
    domain: StalenessDomain,
    timestamp_role: TimestampRole,
    timestamp_value: Optional[str],
    as_of: str,
    source_name: Optional[str] = None,
    object_id: Optional[str] = None,
    field_path: Optional[str] = None,
) -> str:
    """
    Build a deterministic, stable finding_id for a StalenessFinding.

    Uses SHA-256 hashing of key fields. Same inputs → same ID.

    Args:
        domain:          Staleness domain.
        timestamp_role:  Role of the timestamp being evaluated.
        timestamp_value: The raw timestamp string (may be None).
        as_of:           The reference date used for comparison.
        source_name:     Optional source name.
        object_id:       Optional object identifier.
        field_path:      Optional field path in the source artifact.

    Returns:
        A deterministic string prefixed by ``{domain}:{timestamp_role}:``.

    Examples::

        fid = make_staleness_finding_id("news", "as_of", "2026-05-15", "2026-05-22")
        assert fid.startswith("news:as_of:")
    """
    payload = {
        "domain": domain,
        "timestamp_role": timestamp_role,
        "timestamp_value": timestamp_value or "",
        "as_of": as_of,
        "source_name": source_name or "",
        "object_id": object_id or "",
        "field_path": field_path or "",
    }
    hash_suffix = stable_hash_payload(payload, length=16)
    return f"{domain}:{timestamp_role}:{hash_suffix}"


# ---------------------------------------------------------------------------
# Helper 4: evaluate_timestamp_staleness
# ---------------------------------------------------------------------------

def evaluate_timestamp_staleness(
    timestamp: Optional[str],
    as_of: str,
    policy: StalenessPolicy,
    field_path: Optional[str] = None,
    evidence_id: Optional[str] = None,
) -> tuple[StalenessStatus, Optional[float], StalenessSeverity]:
    """
    Evaluate the staleness of a single timestamp against a policy.

    Thresholds (when ``max_age_days`` is set):
        - near_stale: ``age >= max_age_days * near_stale_ratio``
        - stale:      ``age >= max_age_days``
        - fresh:      ``age < near_stale threshold`` (includes future timestamps)

    When ``policy.max_age_days`` is None, the timestamp is always ``"fresh"``.

    Unknown severity is controlled by ``policy.allow_unknown``:
        - ``True``  → ``"warning"``
        - ``False`` → ``"critical"``

    Args:
        timestamp:  Timestamp string to evaluate (may be None → unknown).
        as_of:      Reference date string for comparison.
        policy:     StalenessPolicy defining thresholds and severities.
        field_path: Optional field path (informational, not used for thresholds).
        evidence_id: Optional evidence_id (informational).

    Returns:
        Tuple of ``(StalenessStatus, age_days_or_None, StalenessSeverity)``.
        ``age_days`` is a non-negative float when the timestamp is not newer
        than the reference; None for unknown or future timestamps.

    Examples::

        pol = StalenessPolicy(policy_id="p", domain="news", max_age_days=7.0)
        status, age, sev = evaluate_timestamp_staleness("2026-05-15", "2026-05-22", pol)
        assert status == "stale"
    """
    unknown_sev: StalenessSeverity = policy.unknown_severity

    if timestamp is None:
        return "unknown", None, unknown_sev

    try:
        age = days_between(timestamp, as_of)
    except ValueError:
        return "unknown", None, unknown_sev

    # If no age limit is defined, the timestamp is always fresh
    if policy.max_age_days is None:
        return "fresh", max(0.0, age) if age >= 0 else None, "info"

    near_stale_threshold = policy.max_age_days * policy.near_stale_ratio

    if age >= policy.max_age_days:
        return "stale", age, policy.stale_severity
    elif age >= near_stale_threshold:
        return "near_stale", age, policy.near_stale_severity
    else:
        # Fresh: store non-negative age or None for future timestamps
        return "fresh", max(0.0, age) if age >= 0 else None, "info"


# ---------------------------------------------------------------------------
# Helper 5: evaluate_expiration_status
# ---------------------------------------------------------------------------

def evaluate_expiration_status(
    expiration_value: Optional[str],
    as_of: str,
    policy: Optional[StalenessPolicy] = None,
    domain: StalenessDomain = "generic",
    object_id: Optional[str] = None,
    field_path: Optional[str] = None,
) -> StalenessFinding:
    """
    Evaluate whether a contract expiration date has passed, with grace period support.

    Behavior:
        - Missing or unparseable expiration:
          status ``"unknown"``; severity ``"warning"`` if ``allow_unknown=True``
          else ``"critical"``.
        - Expiration date >= as_of (not yet expired):
          status ``"fresh"``; severity ``"info"``.
        - Expiration date < as_of and days past expiry <= grace_days:
          status ``"near_stale"``; severity ``"warning"`` (within grace window).
        - Expiration date < as_of and days past expiry > grace_days:
          status ``"expired"``; severity ``"critical"``.

    Used specifically for option contract expirations.

    Args:
        expiration_value: Expiration date string (may be None → unknown).
        as_of:            Reference date string for comparison.
        policy:           Optional policy for severity/grace configuration.
        domain:           Staleness domain for the returned finding.
        object_id:        Optional source object identifier.
        field_path:       Optional field path in the source artifact.

    Returns:
        A StalenessFinding with all provenance fields populated.

    Examples::

        finding = evaluate_expiration_status("2026-05-01", "2026-05-22")
        assert finding.status == "expired"
    """
    grace_days = policy.expiration_grace_days if policy is not None else 0.0
    allow_unknown = policy.allow_unknown if policy is not None else True
    expired_sev: StalenessSeverity = (
        policy.expired_severity if policy is not None else "critical"
    )
    unknown_sev: StalenessSeverity = "warning" if allow_unknown else "critical"

    ts_value: Optional[str] = expiration_value
    age_days: Optional[float] = None
    expiry_metadata: dict[str, Any] = {"expiration_grace_days": grace_days}

    if not expiration_value:
        status: StalenessStatus = "unknown"
        severity: StalenessSeverity = unknown_sev
        msg = "Expiration value is missing."
    else:
        try:
            # positive = as_of is after expiration = expired
            days_past = days_between(expiration_value, as_of)
        except ValueError:
            status = "unknown"
            severity = unknown_sev
            msg = f"Expiration value {expiration_value!r} cannot be parsed."
        else:
            if days_past <= 0:
                # Not yet expired; days_until = -days_past
                status = "fresh"
                severity = "info"
                days_until = -days_past
                msg = (
                    f"Expiration '{expiration_value}' is active "
                    f"({days_until:.1f}d until expiry)."
                )
                age_days = None
            elif days_past <= grace_days:
                # Within grace window
                status = "near_stale"
                severity = "warning"
                age_days = days_past
                msg = (
                    f"Expiration '{expiration_value}' is within grace period "
                    f"({days_past:.1f}d past expiry, grace={grace_days:.1f}d)."
                )
                expiry_metadata["days_past_expiration"] = days_past
            else:
                # Truly expired
                status = "expired"
                severity = expired_sev
                age_days = days_past
                msg = (
                    f"Expiration '{expiration_value}' has expired "
                    f"({days_past:.1f}d past expiry)."
                )
                expiry_metadata["days_past_expiration"] = days_past

    finding_id = make_staleness_finding_id(
        domain=domain,
        timestamp_role="expiration",
        timestamp_value=ts_value,
        as_of=as_of,
        object_id=object_id,
        field_path=field_path,
    )
    return StalenessFinding(
        finding_id=finding_id,
        domain=domain,
        status=status,
        severity=severity,
        timestamp_role="expiration",
        timestamp_value=ts_value,
        as_of=as_of,
        age_days=age_days,
        max_age_days=None,
        message=msg,
        object_id=object_id,
        field_path=field_path,
        metadata=expiry_metadata,
    )


# ---------------------------------------------------------------------------
# Helper 6: aggregate_staleness_findings
# ---------------------------------------------------------------------------

def aggregate_staleness_findings(
    report_id: str,
    as_of: str,
    findings: list[StalenessFinding],
    target: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> StalenessReport:
    """
    Aggregate a list of StalenessFinding objects into a StalenessReport.

    Deduplicates findings by ``finding_id`` (first occurrence wins).
    Auto-normalization computes all derived fields from the de-duplicated list.
    Does not mutate the input findings list.

    Args:
        report_id: Non-empty unique identifier for the report.
        as_of:     Non-empty reference date string.
        findings:  List of StalenessFinding to aggregate.
        target:    Optional research target (ticker, domain, etc.).
        metadata:  Optional metadata dict (shallow-copied, not mutated).

    Returns:
        A new StalenessReport.

    Examples::

        report = aggregate_staleness_findings("rep_001", "2026-05-22", [f1, f2])
        assert report.status in ("fresh", "near_stale", "stale", "expired", "unknown")
    """
    # Deduplicate by finding_id, preserving first-occurrence order
    seen_ids: set[str] = set()
    deduped: list[StalenessFinding] = []
    for f in findings:
        if f.finding_id not in seen_ids:
            seen_ids.add(f.finding_id)
            deduped.append(f)

    return StalenessReport(
        report_id=report_id,
        as_of=as_of,
        target=target,
        findings=deduped,
        metadata=dict(metadata) if metadata is not None else {},
    )


# ---------------------------------------------------------------------------
# Helper 7: default_staleness_policy_for_domain
# ---------------------------------------------------------------------------

def default_staleness_policy_for_domain(domain: StalenessDomain) -> StalenessPolicy:
    """
    Return the default StalenessPolicy for a given domain.

    Default max_age_days:
        - ``news``: 7 days
        - ``option``: 1 day
        - ``allocation``: 7 days
        - ``validation``: 7 days
        - ``macro`` / ``catalyst`` / ``earnings`` / ``estimate_revision``: 30 days
        - ``tool_result`` / ``generic`` / ``unknown``: 14 days

    All domains use ``near_stale_ratio=0.8``, ``expiration_grace_days=0.0``,
    and ``allow_unknown=True`` by default.

    Args:
        domain: Staleness domain.

    Returns:
        A StalenessPolicy with default thresholds for the domain.

    Examples::

        pol = default_staleness_policy_for_domain("news")
        assert pol.max_age_days == 7.0
        assert pol.near_stale_ratio == 0.8
        assert pol.policy_id == "default_news_staleness_policy"
    """
    max_age = _DEFAULT_MAX_AGE_DAYS.get(domain, 14.0)
    return StalenessPolicy(
        policy_id=f"default_{domain}_staleness_policy",
        domain=domain,
        max_age_days=max_age,
        near_stale_ratio=0.8,
        expiration_grace_days=0.0,
        allow_unknown=True,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _make_report_id(
    domain: StalenessDomain, object_id: Optional[str], as_of: str
) -> str:
    payload = {
        "domain": domain,
        "object_id": object_id or "",
        "as_of": as_of,
    }
    return f"staleness:{domain}:{stable_hash_payload(payload, length=16)}"


def _fmt_age(age: Optional[float]) -> str:
    return f"{age:.1f}d" if age is not None else "unknown"


def _make_age_msg(
    label: str,
    role: str,
    status: str,
    age: Optional[float],
    max_age: Optional[float],
) -> str:
    max_part = f", max={max_age:.1f}d" if max_age is not None else ""
    return f"{label} {role} is {status} (age={_fmt_age(age)}{max_part})."


def _make_finding(
    domain: StalenessDomain,
    timestamp_value: Optional[str],
    as_of: str,
    status: StalenessStatus,
    severity: StalenessSeverity,
    timestamp_role: TimestampRole,
    age_days: Optional[float],
    max_age_days: Optional[float],
    message: str,
    source_name: Optional[str] = None,
    object_id: Optional[str] = None,
    field_path: Optional[str] = None,
    evidence_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> StalenessFinding:
    # Normalise age_days: negative values mean future timestamps; store None
    normalized_age: Optional[float] = (
        age_days if (age_days is not None and age_days >= 0) else None
    )
    finding_id = make_staleness_finding_id(
        domain=domain,
        timestamp_role=timestamp_role,
        timestamp_value=timestamp_value,
        as_of=as_of,
        source_name=source_name,
        object_id=object_id,
        field_path=field_path,
    )
    return StalenessFinding(
        finding_id=finding_id,
        domain=domain,
        status=status,
        severity=severity,
        timestamp_role=timestamp_role,
        timestamp_value=timestamp_value,
        as_of=as_of,
        age_days=normalized_age,
        max_age_days=max_age_days,
        message=message,
        source_name=source_name,
        object_id=object_id,
        field_path=field_path,
        evidence_id=evidence_id,
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# Helper 8: check_tool_result_staleness
# ---------------------------------------------------------------------------

def check_tool_result_staleness(
    tool_result: ToolResult,
    as_of: str,
    policy: Optional[StalenessPolicy] = None,
    report_id: Optional[str] = None,
) -> StalenessReport:
    """
    Check the staleness of a ToolResult artifact.

    Checks:
        - ``created_at`` (TimestampRole ``generated_at``, field_path ``"created_at"``)
        - ``outputs["as_of"]`` if present (TimestampRole ``as_of``,
          field_path ``"outputs.as_of"``)

    Args:
        tool_result: ToolResult artifact to evaluate.
        as_of:       Reference date string for comparison.
        policy:      Optional policy; defaults to ``tool_result`` domain policy.
        report_id:   Optional report ID; auto-generated if not provided.

    Returns:
        A StalenessReport.
    """
    if policy is None:
        policy = default_staleness_policy_for_domain("tool_result")
    findings: list[StalenessFinding] = []

    # Check created_at
    status, age, severity = evaluate_timestamp_staleness(
        tool_result.created_at, as_of, policy
    )
    findings.append(_make_finding(
        domain="tool_result",
        timestamp_value=tool_result.created_at,
        as_of=as_of,
        status=status,
        severity=severity,
        timestamp_role="generated_at",
        age_days=age,
        max_age_days=policy.max_age_days,
        message=_make_age_msg(
            f"ToolResult '{tool_result.tool_name}'", "generated_at",
            status, age, policy.max_age_days,
        ),
        source_name=tool_result.tool_name,
        object_id=tool_result.evidence_id,
        field_path="created_at",
        evidence_id=tool_result.evidence_id,
    ))

    # Check outputs.as_of if present
    outputs_as_of = tool_result.outputs.get("as_of")
    if isinstance(outputs_as_of, str) and outputs_as_of.strip():
        status2, age2, severity2 = evaluate_timestamp_staleness(
            outputs_as_of, as_of, policy
        )
        findings.append(_make_finding(
            domain="tool_result",
            timestamp_value=outputs_as_of,
            as_of=as_of,
            status=status2,
            severity=severity2,
            timestamp_role="as_of",
            age_days=age2,
            max_age_days=policy.max_age_days,
            message=_make_age_msg(
                f"ToolResult '{tool_result.tool_name}' outputs", "as_of",
                status2, age2, policy.max_age_days,
            ),
            source_name=tool_result.tool_name,
            object_id=tool_result.evidence_id,
            field_path="outputs.as_of",
            evidence_id=tool_result.evidence_id,
        ))

    actual_report_id = report_id or _make_report_id(
        "tool_result", tool_result.evidence_id, as_of
    )
    return aggregate_staleness_findings(
        actual_report_id, as_of, findings,
        target=tool_result.tool_name,
    )


# ---------------------------------------------------------------------------
# Helper 9: check_news_snapshot_staleness
# ---------------------------------------------------------------------------

def check_news_snapshot_staleness(
    snapshot: Any,
    as_of: str,
    policy: Optional[StalenessPolicy] = None,
    report_id: Optional[str] = None,
) -> StalenessReport:
    """
    Check the staleness of a NewsSnapshot artifact.

    Checks:
        - ``snapshot.as_of`` (field_path ``"as_of"``)
        - Each ``event.published_at`` (field_path ``"events.{i}.published_at"``)

    Args:
        snapshot:  NewsSnapshot object (duck-typed).
        as_of:     Reference date string for comparison.
        policy:    Optional policy; defaults to ``news`` domain policy (7d).
        report_id: Optional report ID; auto-generated if not provided.

    Returns:
        A StalenessReport.
    """
    if policy is None:
        policy = default_staleness_policy_for_domain("news")
    findings: list[StalenessFinding] = []
    snap_id = getattr(snapshot, "snapshot_id", None) or "unknown"

    # Check snapshot.as_of
    snap_as_of = getattr(snapshot, "as_of", None)
    status, age, severity = evaluate_timestamp_staleness(snap_as_of, as_of, policy)
    findings.append(_make_finding(
        domain="news",
        timestamp_value=snap_as_of,
        as_of=as_of,
        status=status,
        severity=severity,
        timestamp_role="as_of",
        age_days=age,
        max_age_days=policy.max_age_days,
        message=_make_age_msg(
            f"NewsSnapshot '{snap_id}'", "as_of", status, age, policy.max_age_days,
        ),
        source_name="news_snapshot",
        object_id=snap_id,
        field_path="as_of",
    ))

    # Check each event's published_at with indexed field_path
    events = getattr(snapshot, "events", None) or []
    for i, event in enumerate(events):
        pub_at = getattr(event, "published_at", None)
        ev_id = getattr(event, "event_id", None) or "unknown"
        ev_status, ev_age, ev_severity = evaluate_timestamp_staleness(
            pub_at, as_of, policy
        )
        findings.append(_make_finding(
            domain="news",
            timestamp_value=pub_at,
            as_of=as_of,
            status=ev_status,
            severity=ev_severity,
            timestamp_role="published_at",
            age_days=ev_age,
            max_age_days=policy.max_age_days,
            message=_make_age_msg(
                f"NewsEvent '{ev_id}'", "published_at", ev_status, ev_age, policy.max_age_days,
            ),
            source_name="news_event",
            object_id=ev_id,
            field_path=f"events.{i}.published_at",
        ))

    actual_report_id = report_id or _make_report_id("news", snap_id, as_of)
    return aggregate_staleness_findings(
        actual_report_id, as_of, findings, target=snap_id,
    )


# ---------------------------------------------------------------------------
# Helper 10: check_option_decision_set_staleness
# ---------------------------------------------------------------------------

def check_option_decision_set_staleness(
    decision_set: Any,
    as_of: str,
    policy: Optional[StalenessPolicy] = None,
    report_id: Optional[str] = None,
) -> StalenessReport:
    """
    Check the staleness of an OptionStrategyDecisionSet artifact.

    Checks:
        - ``decision_set.as_of`` (field_path ``"as_of"``)
        - ``chain_snapshot.as_of`` if present (field_path ``"chain_snapshot.as_of"``)
        - Each ``chain_snapshot.contracts[i].expiration`` via
          :func:`evaluate_expiration_status`
          (field_path ``"chain_snapshot.contracts.{i}.expiration"``)

    If ``chain_snapshot.contracts`` is empty, falls back to checking
    ``chain_snapshot.expirations`` (list of strings).

    Args:
        decision_set: OptionStrategyDecisionSet object (duck-typed).
        as_of:        Reference date string.
        policy:       Optional policy; defaults to ``option`` domain policy (1d).
        report_id:    Optional report ID; auto-generated if not provided.

    Returns:
        A StalenessReport.
    """
    if policy is None:
        policy = default_staleness_policy_for_domain("option")
    findings: list[StalenessFinding] = []
    ticker = getattr(decision_set, "ticker", None) or "unknown"

    # Check decision_set.as_of
    ds_as_of = getattr(decision_set, "as_of", None)
    status, age, severity = evaluate_timestamp_staleness(ds_as_of, as_of, policy)
    findings.append(_make_finding(
        domain="option",
        timestamp_value=ds_as_of,
        as_of=as_of,
        status=status,
        severity=severity,
        timestamp_role="as_of",
        age_days=age,
        max_age_days=policy.max_age_days,
        message=_make_age_msg(
            f"OptionStrategyDecisionSet '{ticker}'", "as_of",
            status, age, policy.max_age_days,
        ),
        source_name="option_decision_set",
        object_id=ticker,
        field_path="as_of",
    ))

    # Check chain_snapshot
    chain = getattr(decision_set, "chain_snapshot", None)
    if chain is not None:
        chain_as_of = getattr(chain, "as_of", None)
        status2, age2, severity2 = evaluate_timestamp_staleness(
            chain_as_of, as_of, policy
        )
        findings.append(_make_finding(
            domain="option",
            timestamp_value=chain_as_of,
            as_of=as_of,
            status=status2,
            severity=severity2,
            timestamp_role="as_of",
            age_days=age2,
            max_age_days=policy.max_age_days,
            message=_make_age_msg(
                "OptionChainSnapshot", "as_of", status2, age2, policy.max_age_days,
            ),
            source_name="option_chain_snapshot",
            object_id=ticker,
            field_path="chain_snapshot.as_of",
        ))

        # Prefer contracts list (has structured expiration per contract)
        contracts = getattr(chain, "contracts", None) or []
        if contracts:
            for i, contract in enumerate(contracts):
                expiry_str = getattr(contract, "expiration", None)
                fp = f"chain_snapshot.contracts.{i}.expiration"
                exp_finding = evaluate_expiration_status(
                    expiry_str, as_of, policy,
                    domain="option",
                    object_id=expiry_str,
                    field_path=fp,
                )
                findings.append(exp_finding)
        else:
            # Fallback: iterate expirations list (strings)
            expirations = getattr(chain, "expirations", None) or []
            for i, expiry_str in enumerate(expirations):
                fp = f"chain_snapshot.expirations.{i}"
                exp_finding = evaluate_expiration_status(
                    expiry_str, as_of, policy,
                    domain="option",
                    object_id=expiry_str,
                    field_path=fp,
                )
                findings.append(exp_finding)

    actual_report_id = report_id or _make_report_id("option", ticker, as_of)
    return aggregate_staleness_findings(
        actual_report_id, as_of, findings, target=ticker,
    )


# ---------------------------------------------------------------------------
# Helper 11: check_catalyst_snapshot_staleness
# ---------------------------------------------------------------------------

def check_catalyst_snapshot_staleness(
    snapshot: Any,
    as_of: str,
    policy: Optional[StalenessPolicy] = None,
    report_id: Optional[str] = None,
) -> StalenessReport:
    """
    Check the staleness of a CatalystSnapshot artifact.

    Checks:
        - ``snapshot.as_of`` (field_path ``"as_of"``, catalyst policy)
        - Each ``catalyst.event_date`` (field_path ``"catalysts.{i}.event_date"``,
          catalyst policy)
        - Each ``earnings_event.report_date`` (field_path
          ``"earnings_events.{i}.report_date"``, earnings policy)
        - Each ``estimate_revision.revision_date`` (field_path
          ``"estimate_revisions.{i}.revision_date"``, estimate_revision policy)

    Args:
        snapshot:  CatalystSnapshot object (duck-typed).
        as_of:     Reference date string.
        policy:    Optional policy; defaults to ``catalyst`` domain policy (30d).
        report_id: Optional report ID; auto-generated if not provided.

    Returns:
        A StalenessReport.
    """
    if policy is None:
        policy = default_staleness_policy_for_domain("catalyst")
    er_policy = default_staleness_policy_for_domain("estimate_revision")
    earnings_policy = default_staleness_policy_for_domain("earnings")
    findings: list[StalenessFinding] = []
    snap_id = getattr(snapshot, "snapshot_id", None) or "unknown"

    # Check snapshot.as_of
    snap_as_of = getattr(snapshot, "as_of", None)
    status, age, severity = evaluate_timestamp_staleness(snap_as_of, as_of, policy)
    findings.append(_make_finding(
        domain="catalyst",
        timestamp_value=snap_as_of,
        as_of=as_of,
        status=status,
        severity=severity,
        timestamp_role="as_of",
        age_days=age,
        max_age_days=policy.max_age_days,
        message=_make_age_msg(
            f"CatalystSnapshot '{snap_id}'", "as_of", status, age, policy.max_age_days,
        ),
        source_name="catalyst_snapshot",
        object_id=snap_id,
        field_path="as_of",
    ))

    # Check each catalyst.event_date
    catalysts = getattr(snapshot, "catalysts", None) or []
    for i, catalyst in enumerate(catalysts):
        ev_date = getattr(catalyst, "event_date", None)
        cat_id = getattr(catalyst, "catalyst_id", None) or "unknown"
        cat_status, cat_age, cat_severity = evaluate_timestamp_staleness(
            ev_date, as_of, policy
        )
        findings.append(_make_finding(
            domain="catalyst",
            timestamp_value=ev_date,
            as_of=as_of,
            status=cat_status,
            severity=cat_severity,
            timestamp_role="event_date",
            age_days=cat_age,
            max_age_days=policy.max_age_days,
            message=_make_age_msg(
                f"CatalystEvent '{cat_id}'", "event_date",
                cat_status, cat_age, policy.max_age_days,
            ),
            source_name="catalyst_event",
            object_id=cat_id,
            field_path=f"catalysts.{i}.event_date",
        ))

    # Check earnings_events.report_date
    earnings_events = getattr(snapshot, "earnings_events", None) or []
    for i, earnings in enumerate(earnings_events):
        report_date = getattr(earnings, "report_date", None)
        earn_id = getattr(earnings, "earnings_id", None) or "unknown"
        earn_status, earn_age, earn_severity = evaluate_timestamp_staleness(
            report_date, as_of, earnings_policy
        )
        findings.append(_make_finding(
            domain="earnings",
            timestamp_value=report_date,
            as_of=as_of,
            status=earn_status,
            severity=earn_severity,
            timestamp_role="report_date",
            age_days=earn_age,
            max_age_days=earnings_policy.max_age_days,
            message=_make_age_msg(
                f"EarningsEvent '{earn_id}'", "report_date",
                earn_status, earn_age, earnings_policy.max_age_days,
            ),
            source_name="earnings_event",
            object_id=earn_id,
            field_path=f"earnings_events.{i}.report_date",
        ))

    # Check estimate_revisions.revision_date
    revisions = getattr(snapshot, "estimate_revisions", None) or []
    for i, revision in enumerate(revisions):
        rev_date = getattr(revision, "revision_date", None)
        rev_id = getattr(revision, "revision_id", None) or "unknown"
        rev_status, rev_age, rev_severity = evaluate_timestamp_staleness(
            rev_date, as_of, er_policy
        )
        findings.append(_make_finding(
            domain="estimate_revision",
            timestamp_value=rev_date,
            as_of=as_of,
            status=rev_status,
            severity=rev_severity,
            timestamp_role="revision_date",
            age_days=rev_age,
            max_age_days=er_policy.max_age_days,
            message=_make_age_msg(
                f"EstimateRevision '{rev_id}'", "revision_date",
                rev_status, rev_age, er_policy.max_age_days,
            ),
            source_name="estimate_revision",
            object_id=rev_id,
            field_path=f"estimate_revisions.{i}.revision_date",
        ))

    actual_report_id = report_id or _make_report_id("catalyst", snap_id, as_of)
    return aggregate_staleness_findings(
        actual_report_id, as_of, findings, target=snap_id,
    )


# ---------------------------------------------------------------------------
# Helper 12: check_allocation_decision_set_staleness
# ---------------------------------------------------------------------------

def check_allocation_decision_set_staleness(
    decision_set: Any,
    as_of: str,
    policy: Optional[StalenessPolicy] = None,
    report_id: Optional[str] = None,
) -> StalenessReport:
    """
    Check the staleness of an AllocationDecisionSet artifact.

    Checks:
        - ``decision_set.as_of`` if present (field_path ``"as_of"``)
        - ``decision_set.portfolio.as_of`` or ``decision_set.portfolio_snapshot.as_of``
          if either attribute exists (field_path ``"portfolio.as_of"`` or
          ``"portfolio_snapshot.as_of"``)
        - Each position's ``as_of`` within the portfolio if present
          (field_path ``"portfolio.positions.{i}.as_of"``)

    Args:
        decision_set: AllocationDecisionSet object (duck-typed).
        as_of:        Reference date string.
        policy:       Optional policy; defaults to ``allocation`` domain policy (7d).
        report_id:    Optional report ID; auto-generated if not provided.

    Returns:
        A StalenessReport.
    """
    if policy is None:
        policy = default_staleness_policy_for_domain("allocation")
    findings: list[StalenessFinding] = []
    portfolio_id = getattr(decision_set, "portfolio_id", None) or "unknown"

    # Check decision_set.as_of
    ds_as_of = getattr(decision_set, "as_of", None)
    if ds_as_of is not None:
        status, age, severity = evaluate_timestamp_staleness(ds_as_of, as_of, policy)
        findings.append(_make_finding(
            domain="allocation",
            timestamp_value=ds_as_of,
            as_of=as_of,
            status=status,
            severity=severity,
            timestamp_role="as_of",
            age_days=age,
            max_age_days=policy.max_age_days,
            message=_make_age_msg(
                f"AllocationDecisionSet '{portfolio_id}'", "as_of",
                status, age, policy.max_age_days,
            ),
            source_name="allocation_decision_set",
            object_id=portfolio_id,
            field_path="as_of",
        ))

    # Check portfolio / portfolio_snapshot if present (duck typing)
    portfolio = getattr(decision_set, "portfolio", None) or getattr(
        decision_set, "portfolio_snapshot", None
    )
    portfolio_field = (
        "portfolio" if hasattr(decision_set, "portfolio") else "portfolio_snapshot"
    )
    if portfolio is not None:
        port_as_of = getattr(portfolio, "as_of", None)
        if port_as_of is not None:
            port_id = getattr(portfolio, "portfolio_id", None) or portfolio_field
            p_status, p_age, p_severity = evaluate_timestamp_staleness(
                port_as_of, as_of, policy
            )
            findings.append(_make_finding(
                domain="allocation",
                timestamp_value=port_as_of,
                as_of=as_of,
                status=p_status,
                severity=p_severity,
                timestamp_role="as_of",
                age_days=p_age,
                max_age_days=policy.max_age_days,
                message=_make_age_msg(
                    f"PortfolioSnapshot '{port_id}'", "as_of",
                    p_status, p_age, policy.max_age_days,
                ),
                source_name="portfolio_snapshot",
                object_id=port_id,
                field_path=f"{portfolio_field}.as_of",
            ))

        # Check each position's as_of
        positions = getattr(portfolio, "positions", None) or []
        for i, position in enumerate(positions):
            pos_as_of = getattr(position, "as_of", None)
            pos_ticker = getattr(position, "ticker", None) or f"pos_{i}"
            if pos_as_of is None:
                continue
            pos_status, pos_age, pos_severity = evaluate_timestamp_staleness(
                pos_as_of, as_of, policy
            )
            findings.append(_make_finding(
                domain="allocation",
                timestamp_value=pos_as_of,
                as_of=as_of,
                status=pos_status,
                severity=pos_severity,
                timestamp_role="as_of",
                age_days=pos_age,
                max_age_days=policy.max_age_days,
                message=_make_age_msg(
                    f"PositionSnapshot '{pos_ticker}'", "as_of",
                    pos_status, pos_age, policy.max_age_days,
                ),
                source_name="position_snapshot",
                object_id=pos_ticker,
                field_path=f"{portfolio_field}.positions.{i}.as_of",
            ))

    actual_report_id = report_id or _make_report_id("allocation", portfolio_id, as_of)
    return aggregate_staleness_findings(
        actual_report_id, as_of, findings, target=portfolio_id,
    )


# ---------------------------------------------------------------------------
# Helper 13: check_macro_snapshot_staleness
# ---------------------------------------------------------------------------

def check_macro_snapshot_staleness(
    snapshot: Any,
    as_of: str,
    policy: Optional[StalenessPolicy] = None,
    report_id: Optional[str] = None,
) -> StalenessReport:
    """
    Check the staleness of a MacroSnapshot artifact.

    Checks:
        - ``snapshot.as_of`` if present (field_path ``"as_of"``)
        - Each ``indicator.as_of`` if non-empty
          (field_path ``"indicators.{i}.as_of"``)

    Gracefully handles minimal or unsupported objects — if ``as_of`` is
    absent or unparseable, an unknown finding is produced rather than
    raising an exception.

    Args:
        snapshot:  MacroSnapshot object (duck-typed).
        as_of:     Reference date string.
        policy:    Optional policy; defaults to ``macro`` domain policy (30d).
        report_id: Optional report ID; auto-generated if not provided.

    Returns:
        A StalenessReport.
    """
    if policy is None:
        policy = default_staleness_policy_for_domain("macro")
    findings: list[StalenessFinding] = []
    snap_id: Optional[str] = None
    try:
        snap_id = getattr(snapshot, "snapshot_id", None) or "unknown"
    except Exception:
        snap_id = "unknown"

    # Check snapshot.as_of — safely via getattr
    snap_as_of: Optional[str] = None
    try:
        snap_as_of = getattr(snapshot, "as_of", None)
    except Exception:
        pass

    status, age, severity = evaluate_timestamp_staleness(snap_as_of, as_of, policy)
    findings.append(_make_finding(
        domain="macro",
        timestamp_value=snap_as_of,
        as_of=as_of,
        status=status,
        severity=severity,
        timestamp_role="as_of",
        age_days=age,
        max_age_days=policy.max_age_days,
        message=_make_age_msg(
            f"MacroSnapshot '{snap_id}'", "as_of", status, age, policy.max_age_days,
        ),
        source_name="macro_snapshot",
        object_id=snap_id,
        field_path="as_of",
    ))

    # Check each indicator's as_of — safely
    indicators: list[Any] = []
    try:
        indicators = getattr(snapshot, "indicators", None) or []
    except Exception:
        pass

    for i, indicator in enumerate(indicators):
        try:
            ind_as_of = getattr(indicator, "as_of", None)
            if not ind_as_of:
                continue
            ind_name = getattr(indicator, "name", None) or f"indicator_{i}"
            ind_status, ind_age, ind_severity = evaluate_timestamp_staleness(
                ind_as_of, as_of, policy
            )
            findings.append(_make_finding(
                domain="macro",
                timestamp_value=ind_as_of,
                as_of=as_of,
                status=ind_status,
                severity=ind_severity,
                timestamp_role="as_of",
                age_days=ind_age,
                max_age_days=policy.max_age_days,
                message=_make_age_msg(
                    f"MacroIndicator '{ind_name}'", "as_of",
                    ind_status, ind_age, policy.max_age_days,
                ),
                source_name="macro_indicator",
                object_id=ind_name,
                field_path=f"indicators.{i}.as_of",
            ))
        except Exception:
            continue

    actual_report_id = report_id or _make_report_id("macro", snap_id, as_of)
    return aggregate_staleness_findings(
        actual_report_id, as_of, findings, target=snap_id,
    )


# ---------------------------------------------------------------------------
# Helper 14: staleness_findings_to_validation_items
# ---------------------------------------------------------------------------

def staleness_findings_to_validation_items(
    findings: list[StalenessFinding],
) -> list[AggregatedValidationItem]:
    """
    Convert StalenessFinding objects to AggregatedValidationItem objects.

    Conversion rules:
        - ``fresh``      → skipped.
        - ``near_stale`` / ``stale`` / ``expired`` → ``item_type="stale_data"``.
        - ``unknown`` (missing/unparseable timestamp) → ``item_type="provenance"``.

    Provenance fields are preserved:
        - ``finding.field_path`` → ``item.field_path``
        - ``finding.evidence_id`` → ``item.evidence_id``
        - ``finding.object_id`` → ``item.object_id``
        - ``finding.source_name`` → ``item.source_name``

    ``blocking`` is set to ``True`` for ``"critical"`` severity items.

    StalenessDomain → ValidationDomain mapping:
        - ``tool_result``         → ``"tool_result"``
        - ``macro``               → ``"macro"``
        - ``allocation``          → ``"allocation"``
        - ``option``              → ``"option"``
        - ``news``                → ``"news"``
        - ``catalyst``            → ``"catalyst"``
        - ``earnings``            → ``"earnings"``
        - ``estimate_revision``   → ``"estimate_revision"``
        - ``validation`` / ``generic`` / ``unknown`` → ``"unknown"``

    Args:
        findings: List of StalenessFinding to convert.

    Returns:
        List of AggregatedValidationItem (fresh findings excluded).

    Examples::

        items = staleness_findings_to_validation_items(findings)
        assert all(it.item_type in ("stale_data", "provenance") for it in items)
    """
    items: list[AggregatedValidationItem] = []
    for finding in findings:
        if finding.status == "fresh":
            continue

        v_domain: ValidationDomain = _STALENESS_TO_VALIDATION_DOMAIN.get(  # type: ignore[assignment]
            finding.domain, "unknown"
        )
        v_severity: ValidationSeverity = finding.severity  # "info"/"warning"/"critical" match exactly

        # unknown = missing/unparseable timestamp → provenance issue
        # near_stale/stale/expired → stale_data
        v_item_type: ValidationItemType = (
            "provenance" if finding.status == "unknown" else "stale_data"
        )

        item_id = make_validation_item_id(
            domain=v_domain,
            message=finding.message,
            source_name=finding.source_name,
            object_id=finding.object_id,
            field_path=finding.field_path,
        )
        items.append(AggregatedValidationItem(
            item_id=item_id,
            domain=v_domain,
            severity=v_severity,
            item_type=v_item_type,
            message=finding.message,
            source_name=finding.source_name,
            object_id=finding.object_id,
            field_path=finding.field_path,
            evidence_id=finding.evidence_id,
            blocking=v_severity == "critical",
            metadata={
                "staleness_status": finding.status,
                "timestamp_value": finding.timestamp_value,
                "timestamp_role": finding.timestamp_role,
                "age_days": finding.age_days,
                "max_age_days": finding.max_age_days,
            },
        ))
    return items


# ---------------------------------------------------------------------------
# Helper 15: staleness_report_tool_result_from_report
# ---------------------------------------------------------------------------

def staleness_report_tool_result_from_report(
    run_id: str,
    report: StalenessReport,
    target: str = "staleness",
    calculation_version: str = "staleness_checker_v1",
) -> ToolResult:
    """
    Wrap a StalenessReport into the existing ToolResult model.

    The resulting ToolResult is suitable for submission to
    EvidenceStore.add_tool_result().  The caller is responsible for
    persisting it — this function does not write to disk.

    Args:
        run_id:              Run context ID (from create_run_context).
        report:              StalenessReport to wrap.
        target:              Research target string; defaults to ``"staleness"``.
        calculation_version: Schema/version tag embedded in outputs.

    Returns:
        A ToolResult with:
        - ``tool_name = "staleness_report"`` (stable)
        - Deterministic ``evidence_id``
        - ``outputs`` — full serialised report dict plus ``calculation_version``
        - ``inputs`` — ``{report_id, as_of, target, calculation_version}``

    Examples::

        tr = staleness_report_tool_result_from_report("run_001", report)
        assert tr.tool_name == "staleness_report"
    """
    report_dict = report.model_dump()
    outputs: dict[str, Any] = {
        **report_dict,
        "calculation_version": calculation_version,
    }

    evidence_id = make_evidence_id(
        run_id=run_id,
        tool_name=_STALENESS_TOOL_NAME,
        target=target,
        metric_group=_STALENESS_METRIC_GROUP,
        payload=outputs,
    )

    description = (
        f"StalenessReport {report.report_id!r}"
        f" as_of={report.as_of!r}"
        f" status={report.status!r}"
        f" (stale={report.stale_count}"
        f" expired={report.expired_count}"
        f" near_stale={report.near_stale_count})"
    )

    return ToolResult(
        evidence_id=evidence_id,
        tool_name=_STALENESS_TOOL_NAME,
        run_id=run_id,
        inputs={
            "report_id": report.report_id,
            "as_of": report.as_of,
            "target": target,
            "calculation_version": calculation_version,
        },
        outputs=outputs,
        description=description,
    )


# ---------------------------------------------------------------------------
# Helper 16: summarize_staleness_report
# ---------------------------------------------------------------------------

def summarize_staleness_report(report: StalenessReport) -> dict[str, Any]:
    """
    Return a concise dict summary of a StalenessReport.

    Returns:
        Dict with keys:
            - ``report_id``
            - ``status``
            - ``total_findings``
            - ``fresh_count``
            - ``near_stale_count``
            - ``stale_count``
            - ``expired_count``
            - ``unknown_count``
            - ``critical_count``
            - ``warning_count``
            - ``info_count``
            - ``domains_present``
            - ``top_messages`` — up to 10 message strings from findings
            - ``metadata_keys`` — list of metadata keys (only if non-empty)

    Examples::

        summary = summarize_staleness_report(report)
        assert "status" in summary
        assert "top_messages" in summary
    """
    top_messages = [f.message for f in report.findings[:10]]
    summary: dict[str, Any] = {
        "report_id": report.report_id,
        "status": report.status,
        "total_findings": len(report.findings),
        "fresh_count": report.fresh_count,
        "near_stale_count": report.near_stale_count,
        "stale_count": report.stale_count,
        "expired_count": report.expired_count,
        "unknown_count": report.unknown_count,
        "critical_count": report.critical_count,
        "warning_count": report.warning_count,
        "info_count": report.info_count,
        "domains_present": list(report.domains_present),
        "top_messages": top_messages,
    }
    if report.metadata:
        summary["metadata_keys"] = sorted(report.metadata.keys())
    return summary
