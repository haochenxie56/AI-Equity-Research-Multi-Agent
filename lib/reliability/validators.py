import re
from typing import Any, Optional

from lib.reliability.evidence_store import EvidenceStore
from lib.reliability.schemas import (
    AgentResult,
    EvidenceRef,
    ToolResult,
    ValidationIssue,
    ValidationReport,
)

# ---------------------------------------------------------------------------
# Numeric / metric claim detection
# Matches: bare integers, comma-separated numbers, percentages, dollar amounts,
# x-multiples, P/E, EV/EBITDA, EV/Sales, FY20xx fiscal-year forms,
# and a broad list of financial metric keywords.
# ---------------------------------------------------------------------------

_NUMERIC_RE = re.compile(
    r"""
    -?\d{1,3}(?:,\d{3})*(?:\.\d+)?    # comma-separated / decimal numbers, negatives
    | -?\d+\.?\d*\s*%                  # percentage
    | \$\s*-?\d+                       # dollar amount
    | \d+\.?\d*[xX]\b                 # x-multiples (10.5x, 3x)
    | \bP/E\b                          # P/E ratio
    | \bEV/(?:EBITDA|Sales|Revenue)\b  # EV multiples
    | \bFY\d{2,4}\b                    # fiscal year (FY26, FY2026)
    | \b(?:
        revenue | margin | fcf | wacc | rsi | macd | ebitda | eps | sales |
        growth | multiple | valuation | dcf | cagr | roe | roa | yield |
        ratio | earnings | cash\s*flow | debt | equity | book\s*value |
        net\s*income | ebit | interest | dividend | price | asset
      )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _is_numeric_claim(text: str) -> bool:
    return bool(_NUMERIC_RE.search(text))


# ---------------------------------------------------------------------------
# Binding validation helpers
# ---------------------------------------------------------------------------

def _resolve_field_path(data: dict, path: str) -> bool:
    """
    Resolve a dot-separated key/index path inside a nested dict or list.
    Returns True if every segment exists and is reachable.

    Supported segment types:

    * **dict key** — if the current node is a ``dict``, the segment must be
      a key present in that dict.
    * **list index** — if the current node is a ``list``, the segment must be
      a non-negative integer string (plain digits only).  Negative indices,
      floating-point strings, and arbitrary words are rejected.  The index
      must be within bounds.

    Explicitly **not** supported: bracket notation, negative indices,
    wildcards, slices, ``eval``, or any other dynamic access.  Only plain
    dot-separated dict keys and non-negative integer list indices are allowed.

    Preserves existing behaviour for dict-only paths.

    Examples::

        _resolve_field_path(
            {"valuation": {"dcf": {"fair_value": 200}}},
            "valuation.dcf.fair_value",
        )
        # → True  (unchanged dict-only behaviour)

        _resolve_field_path(
            {"events": [{"headline": "AAPL beats EPS"}]},
            "events.0.headline",
        )
        # → True

        _resolve_field_path({"events": []}, "events.0.headline")
        # → False  (index out of bounds)

        _resolve_field_path(
            {"events": [{"headline": "AAPL beats EPS"}]},
            "events.foo.headline",
        )
        # → False  (non-integer index against a list)

        _resolve_field_path(
            {"events": [{"headline": "AAPL beats EPS"}]},
            "events.-1.headline",
        )
        # → False  (negative index rejected by isdigit())
    """
    current: Any = data
    for segment in path.split("."):
        if isinstance(current, dict):
            if segment not in current:
                return False
            current = current[segment]
        elif isinstance(current, list):
            # isdigit() accepts "0", "1", … and rejects "-1", "foo", "1.0"
            if not segment.isdigit():
                return False
            idx = int(segment)
            if idx >= len(current):
                return False
            current = current[idx]
        else:
            # Scalar (str, int, float, bool, None): cannot traverse further.
            return False
    return True


def _validate_ref_binding(
    ref: EvidenceRef,
    tool_result: ToolResult,
    location: str,
) -> tuple[bool, list[ValidationIssue]]:
    """
    Validate the binding metadata of a single EvidenceRef against its ToolResult.

    Checks tool_name, metric, and field_path independently.  Returns:
        (has_valid_binding, issues)

    has_valid_binding is True if at least one metadata field is present AND
    resolves correctly against the ToolResult.  Each invalid metadata field
    produces its own warning issue.
    """
    issues: list[ValidationIssue] = []
    any_valid = False

    if ref.tool_name is not None:
        if ref.tool_name == tool_result.tool_name:
            any_valid = True
        else:
            issues.append(ValidationIssue(
                severity="warning",
                code="INVALID_EVIDENCE_TOOL_BINDING",
                message=(
                    f"EvidenceRef.tool_name {ref.tool_name!r} does not match "
                    f"ToolResult.tool_name {tool_result.tool_name!r}."
                ),
                location=location,
            ))

    if ref.metric is not None:
        outputs = tool_result.outputs
        if ref.metric in outputs or _resolve_field_path(outputs, ref.metric):
            any_valid = True
        else:
            issues.append(ValidationIssue(
                severity="warning",
                code="INVALID_EVIDENCE_METRIC_BINDING",
                message=(
                    f"EvidenceRef.metric {ref.metric!r} not found "
                    f"in ToolResult.outputs."
                ),
                location=location,
            ))

    if ref.field_path is not None:
        if _resolve_field_path(tool_result.outputs, ref.field_path):
            any_valid = True
        else:
            issues.append(ValidationIssue(
                severity="warning",
                code="INVALID_EVIDENCE_FIELD_PATH_BINDING",
                message=(
                    f"EvidenceRef.field_path {ref.field_path!r} does not resolve "
                    f"in ToolResult.outputs."
                ),
                location=location,
            ))

    return any_valid, issues


# ---------------------------------------------------------------------------
# Main validator
# ---------------------------------------------------------------------------

def validate_agent_result(
    agent_result: AgentResult,
    evidence_store: EvidenceStore,
    *,
    run_id: Optional[str] = None,
    target_name: Optional[str] = None,
) -> ValidationReport:
    """
    Validate an AgentResult against an EvidenceStore.

    run_id / target_name kwargs override the values derived from agent_result
    (useful when the caller manages run context directly).
    """
    issues: list[ValidationIssue] = []
    known_ids = evidence_store.evidence_ids()

    # --- Findings -----------------------------------------------------------
    for i, finding in enumerate(agent_result.findings):
        loc = f"findings[{i}]"
        is_numeric = _is_numeric_claim(finding.text)

        if not finding.evidence:
            issues.append(ValidationIssue(
                severity="warning",
                code="MISSING_EVIDENCE",
                message="Finding has no evidence references.",
                location=loc,
            ))
            if is_numeric:
                issues.append(ValidationIssue(
                    severity="error",
                    code="UNSUPPORTED_NUMERIC_CLAIM",
                    message="Numeric or metric-related claim has no supporting evidence.",
                    location=loc,
                ))
        else:
            # Phase 1: check that every referenced evidence_id exists,
            # and collect (index, ref, tool_result) for valid refs.
            valid_refs: list[tuple[int, EvidenceRef, ToolResult]] = []
            for ref_idx, ref in enumerate(finding.evidence):
                if ref.evidence_id not in known_ids:
                    issues.append(ValidationIssue(
                        severity="error",
                        code="INVALID_EVIDENCE_ID",
                        message=f"Evidence ID {ref.evidence_id!r} not found in store.",
                        location=f"{loc}.evidence[{ref_idx}]",
                    ))
                else:
                    tool_result = evidence_store.get(ref.evidence_id)
                    if tool_result is not None:   # guard: get() can theoretically return None
                        valid_refs.append((ref_idx, ref, tool_result))

            # Phase 2 (numeric claims only): validate binding metadata and
            # flag WEAK_NUMERIC_EVIDENCE_BINDING if no ref has valid binding.
            if is_numeric:
                any_valid_binding = False
                for ref_idx, ref, tool_result in valid_refs:
                    ref_loc = f"{loc}.evidence[{ref_idx}]"
                    has_valid, binding_issues = _validate_ref_binding(
                        ref, tool_result, ref_loc
                    )
                    issues.extend(binding_issues)
                    if has_valid:
                        any_valid_binding = True

                if not any_valid_binding:
                    issues.append(ValidationIssue(
                        severity="warning",
                        code="WEAK_NUMERIC_EVIDENCE_BINDING",
                        message=(
                            "Numeric or metric-related finding has evidence, but no "
                            "EvidenceRef provides valid binding metadata "
                            "(tool_name, metric, or field_path matched against the ToolResult)."
                        ),
                        location=loc,
                    ))

    # --- Risks --------------------------------------------------------------
    for j, risk in enumerate(agent_result.risks):
        loc_r = f"risks[{j}]"
        risk_text = f"{risk.name} {risk.description}"
        is_numeric_risk = _is_numeric_claim(risk_text)

        if not risk.evidence:
            if is_numeric_risk:
                issues.append(ValidationIssue(
                    severity="warning",
                    code="RISK_NUMERIC_NO_EVIDENCE",
                    message=(
                        "Risk contains numeric or metric content "
                        "but has no supporting evidence."
                    ),
                    location=loc_r,
                ))
        else:
            # Phase 1: check evidence IDs exist, collect valid refs.
            valid_risk_refs: list[tuple[int, EvidenceRef, ToolResult]] = []
            for ref_idx, ref in enumerate(risk.evidence):
                if ref.evidence_id not in known_ids:
                    issues.append(ValidationIssue(
                        severity="error",
                        code="INVALID_RISK_EVIDENCE_ID",
                        message=f"Risk evidence ID {ref.evidence_id!r} not found in store.",
                        location=f"{loc_r}.evidence[{ref_idx}]",
                    ))
                else:
                    tool_result = evidence_store.get(ref.evidence_id)
                    if tool_result is not None:
                        valid_risk_refs.append((ref_idx, ref, tool_result))

            # Phase 2 (numeric risks only): validate binding metadata and
            # flag WEAK_NUMERIC_EVIDENCE_BINDING if no ref has valid binding.
            if is_numeric_risk:
                any_valid_binding = False
                for ref_idx, ref, tool_result in valid_risk_refs:
                    ref_loc = f"{loc_r}.evidence[{ref_idx}]"
                    has_valid, binding_issues = _validate_ref_binding(
                        ref, tool_result, ref_loc
                    )
                    issues.extend(binding_issues)
                    if has_valid:
                        any_valid_binding = True

                if not any_valid_binding:
                    issues.append(ValidationIssue(
                        severity="warning",
                        code="WEAK_NUMERIC_EVIDENCE_BINDING",
                        message=(
                            "Numeric or metric-related risk has evidence, but no "
                            "EvidenceRef provides valid binding metadata "
                            "(tool_name, metric, or field_path matched against the ToolResult)."
                        ),
                        location=loc_r,
                    ))

    # --- Build report -------------------------------------------------------
    passed = not any(iss.severity == "error" for iss in issues)
    effective_run_id = run_id or agent_result.run_id
    # target_name falls back: explicit kwarg → ticker → agent_name (always non-empty)
    effective_target = target_name or agent_result.ticker or agent_result.agent_name
    return ValidationReport(
        passed=passed,
        issues=issues,
        run_id=effective_run_id,
        target_name=effective_target,
    )
