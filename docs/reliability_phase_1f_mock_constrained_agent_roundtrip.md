# Phase 1F: Mock Constrained Agent Roundtrip

**Date**: 2026-05-21
**Status**: Planning / Implementation
**Author**: Reliability Refactor — Phase 1F
**Depends on**: Phase 1E (`docs/reliability_phase_1e_prompt_contract.md`)

---

## A. Purpose

Phase 1F demonstrates the **complete constrained-agent loop using mock
responses** — without calling any LLM API and without changing any live code.

Its goal is to prove that:

1. The evidence packet and prompt contract built in Phase 1E are sufficient to
   describe a complete analysis task to a future constrained agent.
2. A mock AgentResult JSON response that follows the contract passes
   `parse_agent_result_json()` and `validate_agent_result()` with zero issues.
3. Responses that violate the contract (fabricated IDs, unsupported numeric
   claims, wrong binding metadata) are reliably caught by the existing
   validator and produce the correct issue codes.
4. The repair prompt template (`build_repair_prompt()`) can be generated from
   validation errors without calling any LLM.

### What Phase 1F does

- Creates `scripts/test_reliability_mock_agent_roundtrip.py` — a fully
  isolated, deterministic test script covering 13 roundtrip scenarios (A–M).
- Creates `examples/reliability/mock_constrained_agent_roundtrip.md` — an
  annotated reference showing valid and invalid mock responses with their
  corresponding `ValidationReport` outputs.
- Documents the complete non-live pipeline and its future integration path.

### What Phase 1F does NOT do

- Does **not** call the Claude API or any external LLM.
- Does **not** modify `lib/llm_orchestrator.py`.
- Does **not** modify any live prompt file.
- Does **not** modify `.claude/agents/*`.
- Does **not** change any Streamlit page.
- Does **not** change the main research workflow.

---

## B. Target Mock Roundtrip Pipeline

```
Synthetic ToolResults (valuation / technical / scanner)
  │
  ▼
EvidenceStore.add_tool_result()
  │  persists to tool_results.jsonl, evidence_manifest.json
  │  returns deterministic evidence_id for each result
  ▼
build_evidence_packet(run_id, target_name, tool_results)
  │  compact evidence summary with evidence_ids, output_keys, notable_field_paths
  │  no raw payload — only path hints
  ▼
build_agent_result_prompt(agent_name, run_id, target, task, packet)
  │  deterministic prompt string embedding hard rules + evidence packet + schema
  │  does NOT call any LLM
  ▼
[MOCK] AgentResult-compatible JSON response
  │  hand-crafted in the test script to simulate a compliant LLM output
  │  must use only evidence_ids from the packet
  ▼
parse_agent_result_json(raw)
  │  schema validation only — raises ValueError on malformed / schema-invalid JSON
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
  ├── passed=True  → findings are evidence-backed ✓
  └── passed=False → [OPTIONAL] build_repair_prompt(errors, original_prompt)
                        │  repair prompt instructs future LLM to fix JSON
                        │  does NOT call LLM in this phase
                        ▼
                     repair prompt string (for future use)
```

---

## C. Why This Matters

| Layer | Role |
|---|---|
| **Deterministic ToolResults** | The only authorised source of financial metrics, scores, and indicators. Code computes; LLM interprets. |
| **Evidence packet** | Tells the future agent exactly which evidence IDs it may cite and which field paths exist. Prevents citation of non-existent evidence. |
| **Prompt contract** | Encodes 11 hard rules that prohibit fabrication, require JSON-only output, and demand EvidenceRef for every numeric claim. |
| **AgentResult parser** | Enforces schema (`extra="forbid"`). Rejects malformed JSON and unknown fields immediately. |
| **Validator** | Checks that every cited `evidence_id` exists in the store, and that numeric claims carry valid binding metadata. |
| **ValidationReport** | Makes hallucination risk auditable. `passed=False` means the response contains fabricated evidence or unsupported numeric claims. |
| **Repair prompt** | When validation fails, provides a future retry path that does not introduce new evidence or fabricated IDs. |

Without this pipeline, an LLM could silently invent fair values, RSI readings,
or scanner scores, and no automated check would catch them. Phase 1F proves
the full check chain works before any live LLM integration begins.

---

## D. Mock Response Categories

Phase 1F tests cover all 10 defined failure and success modes:

| Test | Mock response category | Expected outcome |
|---|---|---|
| A | Valid response — all findings fully evidenced | `passed=True`, zero issues |
| B | Prompt contract content verification | All 11 hard rules present in prompt string |
| C | Unsupported numeric claim (no evidence refs) | `UNSUPPORTED_NUMERIC_CLAIM` error, `passed=False` |
| D | Fabricated `evidence_id` not in store | `INVALID_EVIDENCE_ID` error, `passed=False` |
| E | Weak binding (evidence_id only, no metadata) | `WEAK_NUMERIC_EVIDENCE_BINDING` warning, `passed=True` |
| F | Mismatched `tool_name` | `INVALID_EVIDENCE_TOOL_BINDING` + `WEAK_NUMERIC_EVIDENCE_BINDING` warnings, `passed=True` |
| G | Invalid `metric` not in outputs | `INVALID_EVIDENCE_METRIC_BINDING` + `WEAK_NUMERIC_EVIDENCE_BINDING` warnings, `passed=True` |
| H | Invalid `field_path` that does not resolve | `INVALID_EVIDENCE_FIELD_PATH_BINDING` + `WEAK_NUMERIC_EVIDENCE_BINDING` warnings, `passed=True` |
| I | Malformed JSON string | `ValueError` from `parse_agent_result_json()` |
| J | Schema-invalid JSON (missing required field) | `ValueError` from `parse_agent_result_json()` |
| K | Repair prompt generation | Repair prompt string contains errors, prohibits fabrication, demands JSON |
| L | `ValidationReport` JSON serialisation | Report serialises with `run_id`, `target_name`, `passed`, `issues` |
| M | Artifact persistence | `tool_results.jsonl` and `evidence_manifest.json` written to disk |

---

## E. Repair Prompt Boundaries

When `validate_agent_result()` returns `passed=False`, the caller may use
`build_repair_prompt(invalid_output, validation_errors, original_prompt)` to
produce a repair instruction for a future LLM.

The repair prompt enforces strict boundaries:

| Constraint | Rule |
|---|---|
| No new evidence | Repair prompt must not introduce evidence IDs beyond those in the original packet |
| No fabrication | Explicitly prohibits inventing `evidence_id` values |
| JSON-only output | Demands the repaired response is a single JSON object with no prose |
| Error-targeted | Instructs the LLM to fix only the listed validation errors |
| No claim inflation | If a claim cannot be evidenced, remove or soften it rather than fabricating a reference |
| run_id / agent_name invariant | These fields must not change during repair |

**In Phase 1F, `build_repair_prompt()` is called but the resulting string is
never sent to any LLM.**  It is tested only for correct content.

---

## F. Future Integration Path (Not Phase 1F)

Phase 1F is a non-live proof-of-concept.  Future phases will wire this loop
into the live workflow:

| Future Phase | Scope |
|---|---|
| **Phase 2A** | Adapt `lib/llm_orchestrator.py` to use `build_evidence_packet()` and `build_agent_result_prompt()` behind a feature flag. LLM output parsed through `parse_agent_result_json()` and validated. |
| **Phase 2B** | Wire adapter calls into `lib/workflow_state.py` for the Scanner and Sector pages. ToolResults flow automatically into evidence packets per research run. |
| **Phase 2C** | Add a bounded retry loop: if `validate_agent_result()` fails, generate a repair prompt and retry the LLM call (max 1–2 retries). |
| **Phase 3** | Surface `ValidationReport` in Streamlit as an evidence trace panel on the Financial, Scanner, and Sector pages. |
| **Phase 4** | Add per-agent-type prompt snapshots (non-live) so each agent's contract can be reviewed and audited independently. |

---

## G. Non-Goals for Phase 1F

| Category | Out-of-scope items |
|---|---|
| **Claude API** | No live API calls; no `anthropic` SDK usage |
| **llm_orchestrator.py** | No modifications; no imports from it |
| **Live prompts** | No changes to existing prompt files or `.claude/agents/*` |
| **Streamlit** | No page changes, no UI panels, no session state modifications |
| **App workflow** | No changes to `app.py`, `lib/workflow_state.py`, or existing workflow |
| **Computation** | No changes to `lib/rotation.py`, `lib/technical.py`, `lib/valuation.py`, `lib/data_fetcher.py` |
| **Semantic validation** | Structural binding checks only — no interpretation of claim correctness |
| **Debate / critique layer** | No agent-vs-agent checking |
| **Memory layer** | No long-term agent memory or cross-run learning |
| **Investment cockpit** | Reliability stays in the research workflow only |
| **Live repair loop** | `build_repair_prompt()` output is not sent to any LLM in this phase |

---

## Appendix: Issue Code Reference

| Code | Severity | Trigger |
|---|---|---|
| `MISSING_EVIDENCE` | warning | Finding has no evidence refs at all |
| `UNSUPPORTED_NUMERIC_CLAIM` | **error** | Numeric/metric claim, zero evidence refs |
| `INVALID_EVIDENCE_ID` | **error** | `evidence_id` not found in store |
| `INVALID_RISK_EVIDENCE_ID` | **error** | Risk `evidence_id` not found in store |
| `WEAK_NUMERIC_EVIDENCE_BINDING` | warning | Numeric claim, evidence refs exist but none has a valid binding |
| `INVALID_EVIDENCE_TOOL_BINDING` | warning | `EvidenceRef.tool_name` ≠ `ToolResult.tool_name` |
| `INVALID_EVIDENCE_METRIC_BINDING` | warning | `EvidenceRef.metric` not resolvable in `ToolResult.outputs` |
| `INVALID_EVIDENCE_FIELD_PATH_BINDING` | warning | `EvidenceRef.field_path` traversal fails |
| `RISK_NUMERIC_NO_EVIDENCE` | warning | Risk description contains numeric claim with zero evidence refs |

`passed=True` ↔ zero `error`-severity issues in `ValidationReport.issues`.
