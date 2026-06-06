# AgentResult Prompt Contract — Examples

**Phase**: 1E — Prompt Contract Drafting
**Status**: Documentation only — not live prompt behavior
**Date**: 2026-05-21

> **Important**: All examples below are synthetic illustrations of the prompt
> contract defined in `docs/reliability_phase_1e_prompt_contract.md`.  They
> are produced by `lib/reliability/prompt_contracts.py` helper functions using
> synthetic ToolResult fixtures.  **No live Claude API calls are made.**
> These examples do not affect any live LLM prompt or workflow behavior.

---

## 1. Example Evidence Packet

This packet is produced by `build_evidence_packet()` given two synthetic
ToolResults: one from `valuation_tool_result()` and one from
`technical_tool_result()`.

```json
{
  "available_evidence": [
    {
      "description": "DCF valuation model output for ORCL",
      "evidence_id": "ORCL_20260521_phase1e_abcd1234:valuation_model:ORCL:dcf:<hash>",
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
      "output_keys": [
        "assumptions",
        "current_price",
        "dcf",
        "fair_value",
        "upside_pct"
      ],
      "tool_name": "valuation_model"
    },
    {
      "description": "Technical indicator engine output for ORCL",
      "evidence_id": "ORCL_20260521_phase1e_abcd1234:technical_indicator_engine:ORCL:rsi_macd:<hash>",
      "notable_field_paths": [
        "adx",
        "atr",
        "bollinger.lower",
        "bollinger.middle",
        "bollinger.upper",
        "levels.resistance",
        "levels.support",
        "macd",
        "macd_histogram",
        "macd_signal",
        "moving_averages.ema_20",
        "moving_averages.sma_200",
        "moving_averages.sma_20",
        "moving_averages.sma_50",
        "rsi",
        "volume_ratio"
      ],
      "output_keys": [
        "adx",
        "atr",
        "bollinger",
        "levels",
        "macd",
        "macd_histogram",
        "macd_signal",
        "moving_averages",
        "rsi",
        "volume_ratio"
      ],
      "tool_name": "technical_indicator_engine"
    }
  ],
  "evidence_count": 2,
  "run_id": "ORCL_20260521_phase1e_abcd1234",
  "target_name": "ORCL"
}
```

The evidence packet tells the future LLM:
- **Exactly which evidence IDs it may cite** — any other ID is fabricated.
- **What field paths are available** — so it can write valid `field_path` refs.
- **What tool produced each result** — so it can write valid `tool_name` refs.

---

## 2. Example Prompt (produced by `build_agent_result_prompt()`)

```
You are valuation_agent — a constrained financial analysis agent operating under
strict evidence-first rules.

ARCHITECTURE PRINCIPLE
Deterministic computation, agentic interpretation, auditable synthesis.
Code computes facts. You interpret, critique, and synthesise. You do not compute
new financial metrics.

HARD RULES — YOU MUST FOLLOW ALL OF THEM
1.  Output ONLY a single valid JSON object that matches the AgentResult schema.
    No markdown. No code fences. No prose before or after the JSON.
2.  Every numeric or metric claim in findings[].text or risks[].description
    MUST cite at least one EvidenceRef with evidence_id from this packet.
3.  EvidenceRef.evidence_id MUST appear in AVAILABLE EVIDENCE below.
    NEVER fabricate an evidence_id. NEVER use an evidence_id not in this packet.
4.  EvidenceRef SHOULD include at least one binding field: tool_name, metric,
    or field_path.  Unbound refs will be flagged WEAK by the validator.
5.  Do NOT invent financial numbers, valuations, technical indicators, scanner
    scores, risk metrics, or any market data. Only interpret values present
    in the evidence packet.
6.  If evidence is insufficient for a numeric claim, express uncertainty
    in the finding text instead of making the claim.
    (Prefer: 'Evidence is insufficient to determine X.' over an unsupported
    numeric assertion.)
7.  Do NOT cite evidence not present in this packet.
8.  Assumptions MUST declare source (tool/user/agent/default) and
    sensitivity (low/medium/high) explicitly.
9.  AgentConfidence.score MUST be a float within [0.0, 1.0].
10. Use run_id = "ORCL_20260521_phase1e_abcd1234" exactly as provided.
11. Use agent_name = "valuation_agent" exactly as provided.

TASK
Analyse the DCF valuation and RSI momentum for ORCL. Summarise key findings,
assumptions, and risks. Cite all numeric values from the evidence packet.

RUN CONTEXT
  agent_name  : valuation_agent
  run_id      : ORCL_20260521_phase1e_abcd1234
  target_name : ORCL

AVAILABLE EVIDENCE (evidence packet)
Use ONLY the evidence_ids listed in this packet. Do not use any evidence_id not listed here.
{ ... evidence packet JSON ... }

AGENTRESULT SCHEMA SUMMARY
{ ... schema summary JSON ... }

OUTPUT INSTRUCTION
Return a single JSON object. It must start with { and end with }.
Do not include any text, markdown, explanation, or comments outside the JSON object.
The JSON must be parseable by Python json.loads().
```

---

## 3. Example Valid AgentResult-Compatible JSON Response

A future constrained LLM, having received the prompt above, should return
something like the following.  This response would **pass** `parse_agent_result_json()`
and `validate_agent_result()`.

```json
{
  "agent_name": "valuation_agent",
  "run_id": "ORCL_20260521_phase1e_abcd1234",
  "ticker": "ORCL",
  "findings": [
    {
      "text": "DCF fair value is $200.0, implying approximately 11.1% upside from the current price.",
      "confidence": 0.85,
      "evidence": [
        {
          "evidence_id": "ORCL_20260521_phase1e_abcd1234:valuation_model:ORCL:dcf:<hash>",
          "tool_name": "valuation_model",
          "metric": "fair_value",
          "description": "Base case DCF fair value"
        }
      ]
    },
    {
      "text": "RSI at 62.5 indicates building momentum, not yet in overbought territory (>70).",
      "confidence": 0.80,
      "evidence": [
        {
          "evidence_id": "ORCL_20260521_phase1e_abcd1234:technical_indicator_engine:ORCL:rsi_macd:<hash>",
          "tool_name": "technical_indicator_engine",
          "field_path": "rsi",
          "description": "RSI value from technical indicator engine"
        }
      ]
    },
    {
      "text": "The 50-day SMA at $176.50 and 200-day SMA at $154.00 show the stock is trending above both moving averages.",
      "confidence": 0.90,
      "evidence": [
        {
          "evidence_id": "ORCL_20260521_phase1e_abcd1234:technical_indicator_engine:ORCL:rsi_macd:<hash>",
          "tool_name": "technical_indicator_engine",
          "field_path": "moving_averages.sma_50",
          "description": "50-day SMA from technical engine"
        }
      ]
    }
  ],
  "assumptions": [
    {
      "name": "WACC",
      "rationale": "Weighted average cost of capital used in DCF model.",
      "value": "0.095",
      "source": "tool",
      "sensitivity": "high"
    },
    {
      "name": "Terminal growth rate",
      "rationale": "Long-run perpetuity growth rate applied in DCF terminal value.",
      "value": "0.025",
      "source": "tool",
      "sensitivity": "medium"
    }
  ],
  "risks": [
    {
      "name": "Rate sensitivity",
      "description": "WACC of 9.5% — upside narrows significantly if interest rates rise 50bps.",
      "severity": "high",
      "evidence": [
        {
          "evidence_id": "ORCL_20260521_phase1e_abcd1234:valuation_model:ORCL:dcf:<hash>",
          "tool_name": "valuation_model",
          "field_path": "assumptions.wacc",
          "description": "WACC assumption from valuation model"
        }
      ]
    },
    {
      "name": "Momentum reversal",
      "description": "RSI at 62.5 is approaching overbought territory; a reversal at 70+ would invalidate the momentum thesis.",
      "severity": "medium",
      "evidence": [
        {
          "evidence_id": "ORCL_20260521_phase1e_abcd1234:technical_indicator_engine:ORCL:rsi_macd:<hash>",
          "tool_name": "technical_indicator_engine",
          "field_path": "rsi",
          "description": "RSI from technical engine"
        }
      ]
    }
  ],
  "confidence": {
    "level": "medium",
    "rationale": "Evidence from both valuation model and technical engine; macro uncertainty limits high confidence.",
    "score": 0.78
  }
}
```

### Why this response passes validation

- Every numeric/metric claim (`$200.0`, `11.1%`, `62.5`, `$176.50`, `$154.00`,
  `9.5%`) cites a real `evidence_id` from the packet.
- `tool_name` values match the actual `ToolResult.tool_name`.
- `field_path` values (`rsi`, `moving_averages.sma_50`, `assumptions.wacc`) all
  resolve within the respective `ToolResult.outputs`.
- `Assumption.source` and `Assumption.sensitivity` use valid enum values.
- `AgentConfidence.score` is within `[0.0, 1.0]`.
- No extra fields — all models use `extra="forbid"`.

---

## 4. Example Invalid Response — Why the Validator Rejects It

### Invalid response A: fabricated evidence_id

```json
{
  "agent_name": "valuation_agent",
  "run_id": "ORCL_20260521_phase1e_abcd1234",
  "findings": [
    {
      "text": "DCF fair value is $200.",
      "evidence": [
        {
          "evidence_id": "made_up_evidence_id_that_doesnt_exist"
        }
      ]
    }
  ]
}
```

**Validator result**: `INVALID_EVIDENCE_ID` (error) → `passed=False`

The fabricated `evidence_id` is not present in the `EvidenceStore`.  This is
exactly the hallucination the contract prevents.

### Invalid response B: numeric claim with no evidence

```json
{
  "agent_name": "valuation_agent",
  "run_id": "ORCL_20260521_phase1e_abcd1234",
  "findings": [
    {
      "text": "The intrinsic value is $215 based on my analysis.",
      "evidence": []
    }
  ]
}
```

**Validator result**: `UNSUPPORTED_NUMERIC_CLAIM` (error) → `passed=False`

The LLM invented `$215` without providing any evidence reference.  This is the
primary anti-hallucination check.

### Invalid response C: wrong tool_name + no valid binding

```json
{
  "agent_name": "valuation_agent",
  "run_id": "ORCL_20260521_phase1e_abcd1234",
  "findings": [
    {
      "text": "The DCF fair value is $200.",
      "evidence": [
        {
          "evidence_id": "ORCL_20260521_phase1e_abcd1234:valuation_model:ORCL:dcf:<hash>",
          "tool_name": "technical_indicator_engine"
        }
      ]
    }
  ]
}
```

**Validator result**: `INVALID_EVIDENCE_TOOL_BINDING` (warning) +
`WEAK_NUMERIC_EVIDENCE_BINDING` (warning) → `passed=True` (warnings only)

The `evidence_id` exists, but `tool_name` does not match the actual
`ToolResult.tool_name` (`"valuation_model"`).  No valid binding metadata
means the claim is weakly bound.  This passes but is flagged for review.

### Invalid response D: extra field (schema violation)

```json
{
  "agent_name": "valuation_agent",
  "run_id": "ORCL_20260521_phase1e_abcd1234",
  "findings": [],
  "undocumented_field": "this will cause a parse error"
}
```

**Parser result**: `ValueError` — `parse_agent_result_json()` raises immediately
because `AgentResult` uses `ConfigDict(extra="forbid")`.

---

## 5. Note on Usage

All examples above are generated offline using synthetic ToolResult fixtures
from `lib/reliability/` helpers.  They are intended to:

1. Document the expected behavior of `build_agent_result_prompt()`.
2. Illustrate what a compliant future LLM response looks like.
3. Show which responses would fail validation and why.

**Nothing in this file represents live prompt behavior.**  The Phase 1E prompt
contract helpers are pure Python functions with no side effects.
