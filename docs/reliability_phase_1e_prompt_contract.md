# Phase 1E: Prompt Contract Drafting / Constrained Agent Interface

**Date**: 2026-05-21
**Status**: Planning / Implementation
**Author**: Reliability Refactor — Phase 1E
**Depends on**: Phase 1D (`docs/reliability_phase_1d_agent_result_contract.md`)

---

## A. Purpose

Phase 1E defines the **constrained-agent prompt contract** — a specification
and set of pure helper functions that describe _how_ a future LLM agent will be
instructed to produce `AgentResult`-compatible JSON using only provided,
deterministic `ToolResult` evidence.

### What Phase 1E does

- Defines the evidence packet format that will be provided to a future
  constrained agent.
- Defines the prompt contract principles that prevent fabrication of financial
  metrics, evidence IDs, or unsupported numeric claims.
- Implements pure helper functions in `lib/reliability/prompt_contracts.py`:
  - `extract_field_paths()` — deterministic path extraction from ToolResult
    outputs.
  - `build_evidence_packet()` — compact, prompt-embeddable evidence summary.
  - `build_schema_summary()` — concise AgentResult schema reference.
  - `build_agent_result_prompt()` — deterministic constrained prompt string.
  - `build_repair_prompt()` — future retry/repair prompt template.
- Creates a fully isolated test script
  `scripts/test_reliability_prompt_contracts.py` with no live API calls.

### What Phase 1E does NOT do

- Does **not** modify any live prompt file.
- Does **not** modify `.claude/agents/*`.
- Does **not** modify `lib/llm_orchestrator.py`.
- Does **not** call the Claude API or make any HTTP request.
- Does **not** change any Streamlit page.
- Does **not** change the main research workflow.
- Does **not** integrate reliability into the Streamlit app.

---

## B. Target Future Pipeline

The full pipeline below is the **target state for Phase 1F and beyond**.
Phase 1E only creates the building blocks (evidence packet + prompt contract);
it does not execute the LLM step.

```
EvidenceStore (populated by Phase 1A-1C adapters)
  │
  │  store.get(evidence_id) for each relevant ToolResult
  ▼
build_evidence_packet(run_id, target_name, tool_results)
  │  compact, prompt-embeddable evidence summary
  │  no raw payload volume — only keys, field paths, and IDs
  ▼
build_agent_result_prompt(agent_name, run_id, target_name, task, packet)
  │  deterministic prompt string
  │  embeds architecture principle, hard rules, evidence packet, schema
  ▼
[FUTURE] LLM receives constrained prompt
  │  Claude / any LLM that supports structured output
  │  LLM must use only evidence_ids from packet
  ▼
[FUTURE] LLM returns AgentResult-compatible JSON string
  │
  ▼
parse_agent_result_json(raw_output)
  │  schema validation only — raises ValueError on malformed JSON
  ▼
AgentResult (in-memory)
  │
  ▼
validate_agent_result(agent_result, evidence_store)
  │  checks evidence IDs exist in store
  │  checks numeric claims carry valid binding metadata
  ▼
ValidationReport
  │
  ├── passed=True  → proceed with findings
  └── passed=False → [FUTURE] build_repair_prompt() → retry
```

---

## C. Core Prompt Contract Principles

The prompt built by `build_agent_result_prompt()` enforces the following hard
rules that a future constrained LLM agent must follow:

| # | Rule |
|---|------|
| 1 | Output **only** a single valid JSON object.  No markdown.  No code fences.  No prose before or after the JSON. |
| 2 | Every numeric or metric claim in `findings[].text` or `risks[].description` **must** cite at least one `EvidenceRef` with an `evidence_id` from the packet. |
| 3 | `EvidenceRef.evidence_id` **must** appear in the provided evidence packet.  **Never fabricate** an `evidence_id`. |
| 4 | `EvidenceRef` should include at least one binding field: `tool_name`, `metric`, or `field_path`.  Unbound refs will be flagged `WEAK` by the validator. |
| 5 | Do **not** invent financial numbers, valuations, technical indicators, scanner scores, risk metrics, or any market data.  Only interpret values present in the evidence packet. |
| 6 | If evidence is insufficient for a numeric claim, express uncertainty in the finding text rather than making an unsupported numeric assertion. |
| 7 | Do **not** cite evidence not present in the packet. |
| 8 | `Assumption.source` must be one of: `tool`, `user`, `agent`, `default`.  `Assumption.sensitivity` must be one of: `low`, `medium`, `high`. |
| 9 | `AgentConfidence.score` must be a float within `[0.0, 1.0]`. |
| 10 | Use the provided `run_id` exactly as given. |
| 11 | Use the provided `agent_name` exactly as given. |

These rules directly correspond to the issues raised by
`validate_agent_result()`:

| Rule violation | Validator issue code |
|---|---|
| Numeric claim with zero evidence refs | `UNSUPPORTED_NUMERIC_CLAIM` (error) |
| `evidence_id` not in store | `INVALID_EVIDENCE_ID` (error) |
| `tool_name` mismatch | `INVALID_EVIDENCE_TOOL_BINDING` (warning) |
| `metric` not in outputs | `INVALID_EVIDENCE_METRIC_BINDING` (warning) |
| `field_path` does not resolve | `INVALID_EVIDENCE_FIELD_PATH_BINDING` (warning) |
| Evidence ref with no binding metadata | `WEAK_NUMERIC_EVIDENCE_BINDING` (warning) |

---

## D. Evidence Packet Structure

`build_evidence_packet()` produces a compact dict safe for embedding in a
prompt string.  It summarises available deterministic evidence without exposing
excessive raw payload content.

```python
{
  "run_id": "ORCL_20260521_abcd1234",
  "target_name": "ORCL",
  "evidence_count": 2,
  "available_evidence": [
    {
      "evidence_id": "ORCL_20260521_abcd1234:valuation_model:ORCL:dcf:ed6660d9582e",
      "tool_name": "valuation_model",
      "output_keys": ["assumptions", "current_price", "dcf", "fair_value", "upside_pct"],
      "notable_field_paths": [
        "assumptions.terminal_growth",
        "assumptions.wacc",
        "current_price",
        "dcf.base_case.fair_value",
        "dcf.bear_case.fair_value",
        "dcf.bull_case.fair_value",
        "fair_value",
        "upside_pct"
      ],
      "description": "DCF valuation model output for ORCL"
    },
    {
      "evidence_id": "ORCL_20260521_abcd1234:technical_indicator_engine:ORCL:rsi_macd:de2456370211",
      "tool_name": "technical_indicator_engine",
      "output_keys": ["macd", "macd_histogram", "macd_signal", "moving_averages", "rsi"],
      "notable_field_paths": [
        "macd",
        "macd_histogram",
        "macd_signal",
        "moving_averages.ema_20",
        "moving_averages.sma_200",
        "moving_averages.sma_50",
        "rsi"
      ],
      "description": "Technical indicator engine output for ORCL"
    }
  ]
}
```

### Field descriptions

| Field | Purpose |
|---|---|
| `run_id` | Links the evidence packet to a specific research run |
| `target_name` | Ticker, sector, or analysis target |
| `evidence_count` | Number of ToolResults in the packet |
| `available_evidence[].evidence_id` | Exact ID the LLM must cite in `EvidenceRef.evidence_id` |
| `available_evidence[].tool_name` | Tool identifier for `EvidenceRef.tool_name` binding |
| `available_evidence[].output_keys` | Top-level keys in `ToolResult.outputs` (sorted) |
| `available_evidence[].notable_field_paths` | Dot-paths to scalar/list leaves within `outputs` |
| `available_evidence[].description` | Human-readable summary of what this result contains |

The LLM is expected to use `notable_field_paths` to select valid `field_path`
values for `EvidenceRef` binding.  Paths are derived deterministically from the
actual `ToolResult.outputs` using `extract_field_paths()`.

---

## E. AgentResult Output Contract

The LLM must return a JSON object conforming to the `AgentResult` schema
(defined in `lib/reliability/schemas.py`).  All models use
`ConfigDict(extra="forbid")` — unknown fields cause a parse error.

### Required fields

| Field | Type | Constraint |
|---|---|---|
| `agent_name` | `str` | Non-empty; must match the agent_name in the prompt |
| `run_id` | `str` | Non-empty; must match the run_id from the evidence packet |

### Optional fields

| Field | Type | Default |
|---|---|---|
| `ticker` | `str \| null` | `null` |
| `findings` | `list[Finding]` | `[]` |
| `assumptions` | `list[Assumption]` | `[]` |
| `risks` | `list[Risk]` | `[]` |
| `confidence` | `AgentConfidence \| null` | `null` |

### Schema-compatible example output

```json
{
  "agent_name": "valuation_agent",
  "run_id": "ORCL_20260521_abcd1234",
  "ticker": "ORCL",
  "findings": [
    {
      "text": "DCF fair value is $200, implying 11.1% upside from the current price of $180.",
      "confidence": 0.85,
      "evidence": [
        {
          "evidence_id": "ORCL_20260521_abcd1234:valuation_model:ORCL:dcf:ed6660d9582e",
          "tool_name": "valuation_model",
          "metric": "fair_value",
          "description": "Base DCF fair value output"
        }
      ]
    },
    {
      "text": "RSI at 62.5 signals building momentum without overbought conditions.",
      "confidence": 0.78,
      "evidence": [
        {
          "evidence_id": "ORCL_20260521_abcd1234:technical_indicator_engine:ORCL:rsi_macd:de2456370211",
          "tool_name": "technical_indicator_engine",
          "field_path": "rsi",
          "description": "RSI from technical indicator engine"
        }
      ]
    }
  ],
  "assumptions": [
    {
      "name": "WACC",
      "rationale": "Weighted average cost of capital as derived by valuation model.",
      "value": "0.095",
      "source": "tool",
      "sensitivity": "high"
    }
  ],
  "risks": [
    {
      "name": "Rate sensitivity",
      "description": "WACC of 9.5% narrows upside if interest rates rise further.",
      "severity": "high",
      "evidence": [
        {
          "evidence_id": "ORCL_20260521_abcd1234:valuation_model:ORCL:dcf:ed6660d9582e",
          "tool_name": "valuation_model",
          "field_path": "assumptions.wacc",
          "description": "WACC assumption from valuation model"
        }
      ]
    }
  ],
  "confidence": {
    "level": "medium",
    "rationale": "High evidence quality; moderate uncertainty from macro risk.",
    "score": 0.78
  }
}
```

---

## F. Refusal / Insufficiency Behaviour

The prompt contract requires the following behaviour when evidence is absent or
insufficient:

| Situation | Required behaviour |
|---|---|
| No evidence supports a numeric claim | Do not make the numeric claim.  Express uncertainty instead: _"Evidence is insufficient to determine fair value."_ |
| Evidence is partial | State that the conclusion is uncertain and which inputs are missing. |
| Asked for a field not in the schema | Do not return that field — `extra="forbid"` will reject it anyway. |
| No evidence_id available for a claim | Do not fabricate one.  Omit the numeric claim or make it qualitative. |
| Evidence packet is empty | Return a minimal AgentResult with a finding that evidence is unavailable for this run. |

### Why these rules matter

Fabricated evidence IDs produce `INVALID_EVIDENCE_ID` errors that fail
`ValidationReport.passed`.  Unsupported numeric claims produce
`UNSUPPORTED_NUMERIC_CLAIM` errors that also fail validation.  The validator
is the backstop — but the prompt contract is the first line of defence.

---

## G. Future Integration Path (Not Phase 1E)

Phase 1E is **contract drafting and validation only**.  Future phases will wire
this contract into the live research workflow:

| Future Phase | Scope |
|---|---|
| **Phase 1F** | Mock prompt → mock response → parser/validator roundtrip with a simulated (not live) LLM response. Prove the full contract loop without calling Claude API. |
| **Phase 2A** | Adapt `lib/llm_orchestrator.py` prompts to emit `AgentResult`-compatible JSON using this contract.  Wire `build_evidence_packet()` and `build_agent_result_prompt()` into the orchestrator. |
| **Phase 2B** | Wire adapter calls into `lib/workflow_state.py` for the Scanner and Sector pages so that ToolResults flow automatically into evidence packets. |
| **Phase 2C** | Add JSON repair loop: if `parse_agent_result_json()` or `validate_agent_result()` fails, call `build_repair_prompt()` and retry (bounded retries). |
| **Phase 3** | Surface `ValidationReport` in Streamlit as an evidence trace panel on the Financial, Scanner, and Sector pages. |

None of the Phase 2+ integration should happen in Phase 1E.

---

## H. Non-Goals for Phase 1E

| Category | Out-of-scope items |
|---|---|
| **Live prompts** | No changes to existing prompt files or `.claude/agents/*` |
| **llm_orchestrator.py** | No modifications; no imports from it |
| **Claude API** | No live API calls; no `anthropic` SDK usage |
| **Streamlit** | No page changes, no UI panels, no session state modifications |
| **App workflow** | No changes to `app.py`, `lib/workflow_state.py`, or existing workflow |
| **Computation** | No changes to `lib/rotation.py`, `lib/technical.py`, `lib/valuation.py`, `lib/data_fetcher.py` |
| **Semantic validation** | Structural binding checks only — no interpretation of claim correctness |
| **Debate / critique layer** | No agent-vs-agent checking |
| **Memory layer** | No long-term agent memory or cross-run learning |
| **Investment cockpit** | Reliability stays in the research workflow only |
| **JSON repair execution** | `build_repair_prompt()` is defined but not invoked in live code |

---

## Appendix: Public API Summary

```python
from lib.reliability.prompt_contracts import (
    extract_field_paths,          # dict → list[str]   (dot-paths to leaves)
    build_evidence_packet,        # run_id, target, list[ToolResult] → dict
    build_schema_summary,         # () → dict
    build_agent_result_prompt,    # agent_name, run_id, target, task, packet → str
    build_repair_prompt,          # invalid_output, errors, original_prompt → str
)

# Also re-exported from lib.reliability:
from lib.reliability import (
    extract_field_paths,
    build_evidence_packet,
    build_schema_summary,
    build_agent_result_prompt,
    build_repair_prompt,
)
```

## Appendix: Tool Name Registry (complete as of Phase 1E)

| Source module | `tool_name` | Adapter function |
|---|---|---|
| `lib/valuation.py` | `valuation_model` | `valuation_tool_result()` |
| `lib/technical.py` | `technical_indicator_engine` | `technical_tool_result()` |
| `lib/rotation.py` (sector) | `sector_rotation_model` | `sector_rotation_tool_result()` |
| `lib/rotation.py` (scanner) | `stock_scanner` | `scanner_tool_result()` |
| `lib/data_fetcher.py` (price) | `price_volume_snapshot` | *(future)* |
| `lib/data_fetcher.py` (financials) | `financial_statement_fetcher` | *(future)* |
| `lib/data_fetcher.py` (ratings) | `analyst_rating_fetcher` | *(future)* |
| `lib/data_fetcher.py` (metadata) | `market_data_fetcher` | *(future)* |
