---
name: reliability-refactor
description: Use this skill when implementing or modifying the evidence-first reliability foundation, ToolResult/AgentResult schemas, evidence binding, validators, deterministic tool wrappers, or LLM agent result validation.
paths:
  - "lib/reliability/**"
  - "lib/valuation.py"
  - "lib/technical.py"
  - "lib/rotation.py"
  - "lib/data_fetcher.py"
  - "lib/llm_orchestrator.py"
  - "scripts/test_reliability_foundation.py"
---

## Mission

Implement the evidence-first reliability foundation for the AI Investment Agent project.

The goal is **not** to make LLM agents more autonomous. The goal is to make the existing deterministic workflow more auditable while preparing for constrained multi-agent collaboration.

---

## Non-Negotiable Principles

- Code computes facts.
- Tools produce `ToolResult`.
- Agents produce `AgentResult`.
- Findings must reference `EvidenceRef` wherever a numeric or metric claim is made.
- Numeric claims require evidence IDs.
- Validators must detect unsupported numeric or metric-related claims.
- Preserve reproducibility and auditability.
- Do not modify the Streamlit UI unless explicitly requested.
- Do not replace deterministic workflow logic with free-form LLM reasoning.

---

## Phase 0: Reliability Foundation

Phase 0 creates a standalone evidence and validation layer. It must not change the existing Streamlit UI or current workflow logic.

### Package to create: `lib/reliability/`

| File | Responsibility |
|------|---------------|
| `__init__.py` | Package init; re-export key symbols |
| `schemas.py` | All Pydantic models |
| `run_context.py` | `RunContext` dataclass and `create_run_context()` factory |
| `evidence_store.py` | `EvidenceStore`: in-memory + file persistence |
| `validators.py` | `validate_agent_result()` |
| `serialization.py` | `save_json_model()`, `save_json()` |

### Schemas to define (all in `schemas.py`)

```
DataSnapshot       — raw data artifact with source/timestamp
ToolResult         — output of one deterministic tool call
EvidenceRef        — pointer from a finding to a ToolResult
Finding            — one analytical claim, optionally with evidence
Assumption         — named assumption with rationale
Risk               — named risk with optional evidence refs
AgentConfidence    — confidence level with rationale
AgentResult        — structured LLM output: findings + assumptions + risks + confidence
ValidationIssue    — one detected problem (severity + message + location)
ValidationReport   — full validator output: passed flag + list of issues
```

### RunContext

- Dataclass fields: `run_id`, `ticker`, `task`, `run_dir`, `created_at`
- `run_id` format: `TICKER_YYYYMMDD_HHMMSS_shortuuid`
- `run_dir` is created under `research/runs/<run_id>/` on construction
- Factory: `create_run_context(ticker=None, task=None, base_dir="research/runs")`

### EvidenceStore

```python
add_tool_result(result: ToolResult) -> str   # returns evidence_id
get(evidence_id: str) -> ToolResult | None
all() -> list[ToolResult]
evidence_ids() -> set[str]
save_manifest()                              # writes evidence_manifest.json + tool_results.jsonl
```

- `tool_results.jsonl`: one JSON line per `ToolResult`
- `evidence_manifest.json`: summary mapping `evidence_id -> {tool_name, created_at, ...}`

### Validator

`validate_agent_result(agent_result: AgentResult, evidence_store: EvidenceStore) -> ValidationReport`

Must detect:

| Issue | Description |
|-------|-------------|
| `finding_no_evidence` | Finding has no `EvidenceRef` attached |
| `invalid_evidence_id` | `EvidenceRef` points to an ID not in the store |
| `numeric_claim_no_evidence` | Finding text contains a number or metric keyword but has no evidence |
| `risk_invalid_evidence` | Risk references an evidence ID not in the store |

---

## Standard Data Flow

```
Deterministic tool
  -> ToolResult
  -> EvidenceStore.add_tool_result()
  -> AgentResult (findings reference evidence_ids)
  -> validate_agent_result()
  -> ValidationReport
  -> Report / Memory / UI
```

---

## Test Script: `scripts/test_reliability_foundation.py`

The script must:

1. Create a `RunContext` for ticker `ORCL`.
2. Create an `EvidenceStore` bound to the run directory.
3. Add a sample valuation `ToolResult`.
4. Create a `FinancialAgent` `AgentResult` with at least one finding referencing the evidence.
5. Call `validate_agent_result()`.
6. Print validation passed/failed status.
7. Print the `ValidationReport` as JSON.

**Test command:**

```bash
python scripts/test_reliability_foundation.py
```

**Expected output:**
- Validation passes.
- `research/runs/<run_id>/` directory exists.
- `tool_results.jsonl` is persisted.
- `evidence_manifest.json` is persisted.

---

## Validation Requirements (detail)

- A finding is numeric if its text matches digits, percentages, currency values, or financial metric keywords (e.g. `P/E`, `EV/EBITDA`, `WACC`, `DCF`, `FCF`, `ROE`, `CAGR`, `margin`, `yield`, `ratio`).
- Severity levels: `error` (invalid/missing evidence ID), `warning` (finding with no evidence, numeric claim without evidence).
- `ValidationReport.passed` is `True` only when there are zero `error`-level issues.

---

## Implementation Style

- Use **Pydantic v2** for all schemas (`BaseModel`, `model_validator`, `field_validator`).
- Use full type hints throughout.
- Keep functions small and single-purpose.
- Keep `lib/reliability/` fully standalone — no imports from `lib/valuation.py`, `lib/technical.py`, etc. at Phase 0.
- Do not modify existing app or workflow code during Phase 0.
- Do not modify Streamlit pages.

---

## After Each Change

1. Run `python scripts/test_reliability_foundation.py` and report the result.
2. Report which files were created or modified.
3. Confirm that no existing deterministic logic was altered.
4. Note any import or typing warnings.
