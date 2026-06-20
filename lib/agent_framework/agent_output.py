"""
lib/agent_framework/agent_output.py

Phase 8A — Agent Framework Foundation: the unified AgentOutput contract.

AgentOutput wraps a validated World 2 ``AgentResult`` and adds agent-level
metadata that the World 2 schemas do not carry (horizon, judgment,
valid_until, human-confirmation flag, judgment source). It is a plain
dataclass — NOT a Pydantic subclass — that *embeds* the validated
AgentResult rather than reimplementing it.

IMPORT DISCIPLINE (enforced by §8A.10):
  This module performs NO ``lib.reliability`` imports at module-load time.
  ``AgentResult`` / ``EvidenceRef`` / ``DebateReport`` are referenced only
  in TYPE_CHECKING annotations (stringified via ``from __future__ import
  annotations``). Every runtime use of a reliability class is a lazy import
  inside the function that needs it. Importing this module must not trigger
  the heavy ``lib.reliability`` package __init__.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # annotations only — never imported at runtime here
    from lib.reliability.schemas import AgentResult, EvidenceRef
    from lib.reliability.debate import DebateReport


_log = logging.getLogger("agent_framework.agent_output")


# ---------------------------------------------------------------------------
# Judgment constraint
# ---------------------------------------------------------------------------

_JUDGMENT_MAX_LEN = 200

# Metric-name tokens that would trip validate_agent_result's _is_numeric_claim
# regex when present in findings[0].text (the judgment). Numeric specifics
# belong in supporting_data + evidence_refs, never in the prose judgment.
_JUDGMENT_METRIC_TOKENS = (
    "revenue", "margin", "fcf", "wacc", "rsi", "eps", "dcf", "roe",
    "pe", "ev", "ebitda", "vix", "ppi", "cpi",
)

_JUDGMENT_METRIC_RE = re.compile(
    r"\b(?:" + "|".join(_JUDGMENT_METRIC_TOKENS) + r")\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# AgentOutput dataclass
# ---------------------------------------------------------------------------

@dataclass
class AgentOutput:
    """
    The unified output contract for all agents in the AI Fund pipeline.
    Wraps a validated World 2 AgentResult and adds agent-level metadata
    that World 2 schemas do not carry.

    evidence_refs is flattened from agent_result.findings[].evidence +
    agent_result.risks[].evidence for fast consumer access.

    INVARIANT: evidence_refs must never be empty. If the agent runner
    cannot produce evidence, the output must not be created.
    """

    agent_id: str                              # maps to AgentResult.agent_name
    timestamp: str                             # ISO UTC, maps to AgentResult.created_at
    horizon: str                               # "short" | "mid" | "long" | "cross"
    judgment: str                              # one-sentence actionable conclusion;
                                               # MUST NOT contain numeric values,
                                               # %, $, or metric names (see below)
    confidence: float                          # 0.0-1.0
    evidence_refs: "list[EvidenceRef]"         # flattened from agent_result
    supporting_data: dict                      # agent-specific structured data
    requires_human_confirmation: bool
    judgment_source: str                       # "llm_proposed"|"rule_based"|"human"
    valid_until: str                           # ISO datetime; short=EOD, long=EOP quarter
    agent_result: "Optional[AgentResult]" = None      # embedded validated World 2 object
    debate_report: "Optional[DebateReport]" = None    # populated in Phase 8B only

    @staticmethod
    def validate_judgment(text: str) -> list[str]:
        """
        Return a list of human-readable violation descriptions for *text*
        as a judgment string. An empty list means the judgment is clean.

        A clean judgment is a single sentence of <= 200 characters that
        contains no digits, no '%' / '$', and no metric-name tokens that
        would trigger validate_agent_result's numeric-claim detector.
        """
        violations: list[str] = []
        if not isinstance(text, str) or not text.strip():
            violations.append("judgment is empty or not a string")
            return violations

        if len(text) > _JUDGMENT_MAX_LEN:
            violations.append(
                f"judgment exceeds {_JUDGMENT_MAX_LEN} chars (len={len(text)})"
            )
        if re.search(r"\d", text):
            violations.append("judgment contains numeric digits")
        if "%" in text:
            violations.append("judgment contains a percent sign ('%')")
        if "$" in text:
            violations.append("judgment contains a dollar sign ('$')")

        metric_hits = sorted({m.group(0).lower() for m in _JUDGMENT_METRIC_RE.finditer(text)})
        if metric_hits:
            violations.append(
                "judgment contains metric-name token(s): " + ", ".join(metric_hits)
            )
        return violations


# ---------------------------------------------------------------------------
# Mapper: AgentResult -> AgentOutput
# ---------------------------------------------------------------------------

def agent_result_to_agent_output(
    agent_result: "AgentResult",
    *,
    horizon: str,
    judgment: str,
    requires_human_confirmation: bool,
    judgment_source: str,
    valid_until: str,
    supporting_data: dict | None = None,
) -> AgentOutput:
    """
    Derive an AgentOutput from a validated AgentResult.

    evidence_refs is flattened from all findings and risks.
    confidence is taken from agent_result.confidence.score if present,
    else defaults to 0.5 with a logging.warning.

    Raises ValueError if evidence_refs would be empty.
    """
    evidence_refs: list = []
    for finding in agent_result.findings:
        evidence_refs.extend(finding.evidence)
    for risk in agent_result.risks:
        evidence_refs.extend(risk.evidence)

    if not evidence_refs:
        raise ValueError(
            f"agent_result_to_agent_output: AgentResult "
            f"{agent_result.agent_name!r} produced no evidence references; "
            "AgentOutput.evidence_refs must never be empty."
        )

    if agent_result.confidence is not None:
        confidence = float(agent_result.confidence.score)
    else:
        confidence = 0.5
        _log.warning(
            "agent_result_to_agent_output: AgentResult %r has no confidence; "
            "defaulting AgentOutput.confidence to 0.5.",
            agent_result.agent_name,
        )

    violations = AgentOutput.validate_judgment(judgment)
    if violations:
        _log.warning(
            "agent_result_to_agent_output: judgment for %r has constraint "
            "violations: %s",
            agent_result.agent_name,
            "; ".join(violations),
        )

    return AgentOutput(
        agent_id=agent_result.agent_name,
        timestamp=agent_result.created_at,
        horizon=horizon,
        judgment=judgment,
        confidence=confidence,
        evidence_refs=evidence_refs,
        supporting_data=supporting_data or {},
        requires_human_confirmation=requires_human_confirmation,
        judgment_source=judgment_source,
        valid_until=valid_until,
        agent_result=agent_result,
        debate_report=None,
    )


# ---------------------------------------------------------------------------
# JSONL serialization
# ---------------------------------------------------------------------------

def agent_output_to_dict(ao: AgentOutput) -> dict:
    """
    Serialize AgentOutput to a JSON-safe dict.

    Flat fields are copied directly. Pydantic members are dumped via
    ``.model_dump(mode="json")``: each EvidenceRef in ``evidence_refs``,
    the embedded ``agent_result`` (if any), and ``debate_report`` (if any).
    """
    return {
        "agent_id": ao.agent_id,
        "timestamp": ao.timestamp,
        "horizon": ao.horizon,
        "judgment": ao.judgment,
        "confidence": ao.confidence,
        "evidence_refs": [ref.model_dump(mode="json") for ref in ao.evidence_refs],
        "supporting_data": ao.supporting_data,
        "requires_human_confirmation": ao.requires_human_confirmation,
        "judgment_source": ao.judgment_source,
        "valid_until": ao.valid_until,
        "agent_result": (
            ao.agent_result.model_dump(mode="json")
            if ao.agent_result is not None else None
        ),
        "debate_report": (
            ao.debate_report.model_dump(mode="json")
            if ao.debate_report is not None else None
        ),
    }


def agent_output_from_dict(d: dict) -> AgentOutput:
    """
    Deserialize from a dict (e.g. loaded from JSONL).

    Reconstructs each EvidenceRef via ``EvidenceRef(**ref_dict)`` and the
    embedded AgentResult via ``AgentResult(**result_dict)`` when present.
    ``debate_report`` is left as None (reconstruction is Phase 8B).
    """
    # Lazy import — keeps lib.reliability out of the module-load chain.
    from lib.reliability.schemas import AgentResult, EvidenceRef

    evidence_refs = [EvidenceRef(**ref) for ref in d.get("evidence_refs", [])]

    agent_result = None
    result_dict = d.get("agent_result")
    if result_dict is not None:
        agent_result = AgentResult(**result_dict)

    return AgentOutput(
        agent_id=d["agent_id"],
        timestamp=d["timestamp"],
        horizon=d["horizon"],
        judgment=d["judgment"],
        confidence=float(d["confidence"]),
        evidence_refs=evidence_refs,
        supporting_data=d.get("supporting_data") or {},
        requires_human_confirmation=bool(d["requires_human_confirmation"]),
        judgment_source=d["judgment_source"],
        valid_until=d["valid_until"],
        agent_result=agent_result,
        debate_report=None,
    )


def append_agent_output(ao: AgentOutput, base_dir: str = "data/agent_outputs") -> str:
    """
    Append ao to ``<base_dir>/<agent_id>/<YYYY-MM-DD>.jsonl``.

    Creates directories if needed. The date component is ``ao.timestamp[:10]``
    (the ISO date prefix). One JSON object per line, append mode.

    Fail-closed: on any IOError/OSError, logs and returns "" — never raises.
    Returns the file path written to on success.
    """
    try:
        date_stem = (ao.timestamp or "")[:10] or "unknown-date"
        out_dir = os.path.join(base_dir, ao.agent_id)
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"{date_stem}.jsonl")
        line = json.dumps(agent_output_to_dict(ao), ensure_ascii=False)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        return path
    except OSError as exc:
        _log.warning(
            "append_agent_output: failed to persist output for %r: %s",
            getattr(ao, "agent_id", "?"), exc,
        )
        return ""


def _normalize_date_stem(date: str) -> str:
    """Accept either ``YYYYMMDD`` or ``YYYY-MM-DD`` and return the dashed stem."""
    if len(date) == 8 and date.isdigit():
        return f"{date[:4]}-{date[4:6]}-{date[6:]}"
    return date


def load_agent_outputs(
    agent_id: str,
    base_dir: str = "data/agent_outputs",
    date: str | None = None,
) -> list[AgentOutput]:
    """
    Load all AgentOutput records for ``agent_id``.

    If ``date`` is given (``YYYYMMDD`` or ``YYYY-MM-DD``) only that day's
    file is read; otherwise every ``*.jsonl`` under
    ``<base_dir>/<agent_id>/`` is read. Malformed lines are skipped with a
    logging.warning. Never raises. Returns records sorted ascending by
    ``timestamp``.
    """
    out_dir = os.path.join(base_dir, agent_id)
    results: list[AgentOutput] = []

    if not os.path.isdir(out_dir):
        return results

    if date is not None:
        stem = _normalize_date_stem(date)
        files = [os.path.join(out_dir, f"{stem}.jsonl")]
    else:
        try:
            files = sorted(
                os.path.join(out_dir, name)
                for name in os.listdir(out_dir)
                if name.endswith(".jsonl")
            )
        except OSError as exc:
            _log.warning("load_agent_outputs: cannot list %r: %s", out_dir, exc)
            return results

    for path in files:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line_no, raw in enumerate(fh, 1):
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        results.append(agent_output_from_dict(json.loads(raw)))
                    except (ValueError, KeyError, TypeError) as exc:
                        _log.warning(
                            "load_agent_outputs: skipping malformed line "
                            "%d in %r: %s", line_no, path, exc,
                        )
        except OSError as exc:
            _log.warning("load_agent_outputs: cannot read %r: %s", path, exc)

    results.sort(key=lambda ao: ao.timestamp)
    return results
