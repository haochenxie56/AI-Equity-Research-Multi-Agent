# Mock Constrained Agent Roundtrip — Examples

**Phase**: 1F — Mock Constrained Agent Roundtrip
**Status**: Documentation only — not live LLM behavior
**Date**: 2026-05-21

> **Important**: All examples are synthetic illustrations using the helper
> functions defined in `lib/reliability/`.  No live Claude API calls are made.
> These do not represent or affect any current LLM prompt or workflow behavior.

---

## 1. Synthetic Evidence Packet

Produced by `build_evidence_packet()` from three ToolResults:
- `valuation_tool_result()` — `tool_name="valuation_model"`
- `technical_tool_result()` — `tool_name="technical_indicator_engine"`
- `scanner_tool_result()` — `tool_name="stock_scanner"`

```json
{
  "run_id": "ORCL_20260521_phase1f_abcd1234",
  "target_name": "ORCL",
  "evidence_count": 3,
  "available_evidence": [
    {
      "evidence_id": "ORCL_20260521_phase1f_abcd1234:valuation_model:ORCL:dcf:<val_hash>",
      "tool_name": "valuation_model",
      "output_keys": ["assumptions", "current_price", "dcf", "fair_value", "upside_pct"],
      "notable_field_paths": [
        "assumptions.terminal_growth",
        "assumptions.wacc",
        "current_price",
        "dcf.base_case.fair_value",
        "fair_value",
        "upside_pct"
      ],
      "description": "Phase 1F synthetic valuation evidence"
    },
    {
      "evidence_id": "ORCL_20260521_phase1f_abcd1234:technical_indicator_engine:ORCL:rsi_macd:<tech_hash>",
      "tool_name": "technical_indicator_engine",
      "output_keys": ["levels", "macd_histogram", "moving_averages", "rsi"],
      "notable_field_paths": [
        "levels.resistance",
        "levels.support",
        "macd_histogram",
        "moving_averages.sma_50",
        "rsi"
      ],
      "description": "Phase 1F synthetic technical evidence"
    },
    {
      "evidence_id": "ORCL_20260521_phase1f_abcd1234:stock_scanner:market:stock_scanner:<scan_hash>",
      "tool_name": "stock_scanner",
      "output_keys": ["candidates", "selected_tickers"],
      "notable_field_paths": [
        "candidates.ORCL.candidate_rank",
        "candidates.ORCL.composite_score",
        "candidates.ORCL.strategy_breakdown.quality_growth_score",
        "selected_tickers"
      ],
      "description": "Phase 1F synthetic scanner evidence"
    }
  ]
}
```

The packet tells the future agent:
- Exactly **which evidence IDs** it may cite (any other ID is fabricated).
- **What field paths** are available (so it can write valid `field_path` refs).
- **Which tool** produced each result (for valid `tool_name` binding).

---

## 2. Generated Prompt Excerpt

Produced by `build_agent_result_prompt()`.  *(Abbreviated for readability.)*

```
You are integrated_agent — a constrained financial analysis agent operating
under strict evidence-first rules.

ARCHITECTURE PRINCIPLE
Deterministic computation, agentic interpretation, auditable synthesis.
Code computes facts. You interpret, critique, and synthesise. You do not
compute new financial metrics.

HARD RULES — YOU MUST FOLLOW ALL OF THEM
1.  Output ONLY a single valid JSON object that matches the AgentResult schema.
    No markdown. No code fences. No prose before or after the JSON.
2.  Every numeric or metric claim in findings[].text or risks[].description
    MUST cite at least one EvidenceRef with evidence_id from this packet.
3.  EvidenceRef.evidence_id MUST appear in AVAILABLE EVIDENCE below.
    NEVER fabricate an evidence_id. NEVER use an evidence_id not in this packet.
...
10. Use run_id = "ORCL_20260521_phase1f_abcd1234" exactly as provided.
11. Use agent_name = "integrated_agent" exactly as provided.

TASK
Analyse ORCL valuation, RSI momentum, and scanner ranking.
Cite all numeric values from the evidence packet.

AVAILABLE EVIDENCE (evidence packet)
{ ... evidence packet JSON ... }

AGENTRESULT SCHEMA SUMMARY
{ ... schema summary JSON ... }

OUTPUT INSTRUCTION
Return a single JSON object. It must start with { and end with }.
Do not include any text, markdown, explanation, or comments outside the JSON object.
```

---

## 3. Valid Mock AgentResult JSON Response

A future constrained LLM, having received the prompt above, should produce
something like this.  This response **passes** `parse_agent_result_json()`
and `validate_agent_result()` with zero issues.

```json
{
  "agent_name": "integrated_agent",
  "run_id": "ORCL_20260521_phase1f_abcd1234",
  "ticker": "ORCL",
  "findings": [
    {
      "text": "DCF fair value is $200.",
      "confidence": 0.85,
      "evidence": [
        {
          "evidence_id": "ORCL_20260521_phase1f_abcd1234:valuation_model:ORCL:dcf:<val_hash>",
          "tool_name": "valuation_model",
          "metric": "fair_value",
          "description": "Base case DCF fair value from valuation model"
        }
      ]
    },
    {
      "text": "RSI is 62.5, indicating building momentum.",
      "confidence": 0.80,
      "evidence": [
        {
          "evidence_id": "ORCL_20260521_phase1f_abcd1234:technical_indicator_engine:ORCL:rsi_macd:<tech_hash>",
          "tool_name": "technical_indicator_engine",
          "field_path": "rsi",
          "description": "RSI from technical indicator engine"
        }
      ]
    },
    {
      "text": "ORCL composite scanner score is 91.2.",
      "confidence": 0.75,
      "evidence": [
        {
          "evidence_id": "ORCL_20260521_phase1f_abcd1234:stock_scanner:market:stock_scanner:<scan_hash>",
          "tool_name": "stock_scanner",
          "field_path": "candidates.ORCL.composite_score",
          "description": "Composite score from stock scanner"
        }
      ]
    }
  ],
  "assumptions": [
    {
      "name": "WACC",
      "rationale": "9.5% WACC from valuation model.",
      "value": "0.095",
      "source": "tool",
      "sensitivity": "high"
    }
  ],
  "risks": [
    {
      "name": "Support break risk",
      "description": "Downside risk increases if price breaks support at $175.",
      "severity": "medium",
      "evidence": [
        {
          "evidence_id": "ORCL_20260521_phase1f_abcd1234:technical_indicator_engine:ORCL:rsi_macd:<tech_hash>",
          "tool_name": "technical_indicator_engine",
          "field_path": "levels.support",
          "description": "Support level from technical engine"
        }
      ]
    }
  ],
  "confidence": {
    "level": "medium",
    "rationale": "Evidence-backed valuation, momentum, and scanner signals.",
    "score": 0.78
  }
}
```

### Corresponding ValidationReport (passing)

```json
{
  "passed": true,
  "schema_version": "0.1",
  "run_id": "ORCL_20260521_phase1f_abcd1234",
  "target_name": "ORCL",
  "issues": [],
  "created_at": "2026-05-21T..."
}
```

---

## 4. Invalid Mock AgentResult JSON — Fabricated Evidence ID

```json
{
  "agent_name": "integrated_agent",
  "run_id": "ORCL_20260521_phase1f_abcd1234",
  "findings": [
    {
      "text": "DCF fair value is $200.",
      "evidence": [
        {
          "evidence_id": "hallucinated_eid_not_in_store_xyz",
          "tool_name": "valuation_model",
          "metric": "fair_value"
        }
      ]
    }
  ]
}
```

**Validator result**: `INVALID_EVIDENCE_ID` (error) → `passed=False`

### Corresponding ValidationReport

```json
{
  "passed": false,
  "run_id": "ORCL_20260521_phase1f_abcd1234",
  "target_name": "ORCL",
  "issues": [
    {
      "severity": "error",
      "code": "INVALID_EVIDENCE_ID",
      "message": "Evidence ID 'hallucinated_eid_not_in_store_xyz' not found in store.",
      "location": "findings[0].evidence[0]"
    }
  ]
}
```

---

## 5. Invalid Mock AgentResult JSON — Unsupported Numeric Claim

```json
{
  "agent_name": "integrated_agent",
  "run_id": "ORCL_20260521_phase1f_abcd1234",
  "findings": [
    {
      "text": "The intrinsic value is $215 based on my analysis.",
      "evidence": []
    }
  ]
}
```

**Validator result**: `UNSUPPORTED_NUMERIC_CLAIM` (error) → `passed=False`

The LLM invented `$215` without providing any evidence reference.

### Corresponding ValidationReport

```json
{
  "passed": false,
  "run_id": "ORCL_20260521_phase1f_abcd1234",
  "target_name": "ORCL",
  "issues": [
    {
      "severity": "error",
      "code": "UNSUPPORTED_NUMERIC_CLAIM",
      "message": "Numeric claim in finding[0] has no evidence refs.",
      "location": "findings[0]"
    }
  ]
}
```

---

## 6. Invalid Mock AgentResult JSON — Weak Binding (Warning Only)

```json
{
  "agent_name": "integrated_agent",
  "run_id": "ORCL_20260521_phase1f_abcd1234",
  "findings": [
    {
      "text": "DCF fair value is $200.",
      "evidence": [
        {
          "evidence_id": "ORCL_20260521_phase1f_abcd1234:valuation_model:ORCL:dcf:<val_hash>"
        }
      ]
    }
  ]
}
```

**Validator result**: `WEAK_NUMERIC_EVIDENCE_BINDING` (warning) → `passed=True`

The `evidence_id` exists in the store, but the ref has no binding metadata
(`tool_name`, `metric`, or `field_path`).  The validator cannot confirm that
this evidence supports the `$200` claim.  The report passes but flags the
weakness for review.

### Corresponding ValidationReport

```json
{
  "passed": true,
  "run_id": "ORCL_20260521_phase1f_abcd1234",
  "target_name": "ORCL",
  "issues": [
    {
      "severity": "warning",
      "code": "WEAK_NUMERIC_EVIDENCE_BINDING",
      "message": "Numeric claim in finding[0] has no valid binding metadata.",
      "location": "findings[0]"
    }
  ]
}
```

---

## 7. Repair Prompt (for failed response — not sent to any LLM in Phase 1F)

When `passed=False`, `build_repair_prompt()` produces a string like this:

```
The following output from a constrained financial analysis agent failed validation.
Your task is to repair it so it passes the AgentResult schema and evidence validation.

REPAIR RULES — YOU MUST FOLLOW ALL OF THEM
1.  Return ONLY a single valid JSON object. No markdown. No prose outside JSON.
2.  Fix ONLY the structural/schema issues listed in VALIDATION ERRORS below.
3.  Do NOT invent new evidence_id values. Use only the evidence_ids from the
    original evidence packet (see ORIGINAL PROMPT).
4.  Do NOT add numeric/metric claims not backed by the original evidence.
5.  Do NOT change the run_id or agent_name fields.
6.  If a claim cannot be properly evidenced, remove or soften it rather than
    fabricating an evidence reference.
7.  The repaired JSON must satisfy all HARD RULES from the original prompt.

VALIDATION ERRORS
  - Evidence ID 'hallucinated_eid_not_in_store_xyz' not found in store.

INVALID OUTPUT TO REPAIR
{ ... invalid mock response JSON ... }

ORIGINAL PROMPT (for context — do not add evidence not present there)
{ ... original constrained prompt ... }

OUTPUT INSTRUCTION
Return a single repaired JSON object. Begin with { and end with }.
Do not include any text or explanation outside the JSON.
```

**In Phase 1F, this repair prompt string is tested for correct content but
never sent to any LLM.**

---

## 8. Note on Usage

All examples above are generated by the test script
`scripts/test_reliability_mock_agent_roundtrip.py` using synthetic fixtures.
They prove the complete non-live loop:

```
synthetic ToolResults → EvidenceStore → evidence packet → constrained prompt
→ [mock] AgentResult JSON → parser → validator → ValidationReport
→ [optional] repair prompt
```

**Nothing in this file represents live prompt behavior.**  The complete
integration of this pipeline into `lib/llm_orchestrator.py` is deferred to
Phase 2A.
