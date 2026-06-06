from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Raw data artifact produced by a deterministic fetch
# ---------------------------------------------------------------------------

class DataSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    schema_version: str = "0.1"
    data: dict[str, Any] = Field(default_factory=dict)
    fetched_at: str = Field(default_factory=_utcnow)
    description: str = ""


# ---------------------------------------------------------------------------
# Deterministic tool output — the primary evidence unit
# ---------------------------------------------------------------------------

class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1)
    tool_name: str = Field(min_length=1)
    run_id: str = Field(min_length=1)         # required — every tool output must be run-linked
    ticker: Optional[str] = None
    schema_version: str = "0.1"
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    data_snapshots: list[DataSnapshot] = Field(default_factory=list)
    created_at: str = Field(default_factory=_utcnow)
    description: str = ""


# ---------------------------------------------------------------------------
# Reference from an LLM finding/risk back to a ToolResult
# ---------------------------------------------------------------------------

class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1)
    excerpt: str = ""
    # Binding metadata — at least one should be set for numeric/metric claims,
    # and each will be validated against the referenced ToolResult.
    tool_name: Optional[str] = None
    metric: Optional[str] = None
    field_path: Optional[str] = None
    snapshot_id: Optional[str] = None
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# LLM agent output building blocks
# ---------------------------------------------------------------------------

class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    evidence: list[EvidenceRef] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class Assumption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    rationale: str
    value: Optional[str] = None
    source: Literal["tool", "user", "agent", "default"] = "agent"
    sensitivity: Literal["low", "medium", "high"] = "medium"


class Risk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    severity: Literal["low", "medium", "high"] = "medium"
    evidence: list[EvidenceRef] = Field(default_factory=list)


class AgentConfidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Literal["high", "medium", "low"]
    rationale: str
    score: float = Field(default=0.5, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Full LLM agent output
# ---------------------------------------------------------------------------

class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_name: str = Field(min_length=1)
    ticker: Optional[str] = None
    run_id: str = Field(min_length=1)         # required — every agent output must be run-linked
    schema_version: str = "0.1"
    findings: list[Finding] = Field(default_factory=list)
    assumptions: list[Assumption] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    confidence: Optional[AgentConfidence] = None
    created_at: str = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Validator output
# ---------------------------------------------------------------------------

class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["info", "warning", "error"]
    code: str = ""
    message: str
    location: str = ""


class ValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passed: bool
    schema_version: str = "0.1"
    run_id: str = Field(min_length=1)         # required — every report must be run-linked
    target_name: str = Field(min_length=1)    # required — ticker, sector, or agent name
    issues: list[ValidationIssue] = Field(default_factory=list)
    created_at: str = Field(default_factory=_utcnow)
