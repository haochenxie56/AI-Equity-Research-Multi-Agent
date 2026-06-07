# Phase 1G: Feature-Flagged Reliability Orchestration Design

**Date**: 2026-05-21
**Status**: Design / Dry-Run Scaffolding
**Author**: Reliability Refactor — Phase 1G
**Depends on**: Phase 1F (`docs/reliability_phase_1f_mock_constrained_agent_roundtrip.md`)

---

## A. Purpose

Phase 1G defines a **safe, feature-flagged path for integrating the reliability
layer into the live research workflow** — without changing any current app
behavior.

Its goal is to answer the following design questions:

1. Where will reliability orchestration eventually sit in the workflow?
2. How will existing deterministic outputs become `ToolResult` evidence?
3. How will prompt contracts, `AgentResult` parsing, validation, and repair fit
   together in production?
4. How will this be enabled behind a feature flag to guarantee zero impact on
   current users until explicitly switched on?
5. How do we guarantee default app behavior remains unchanged?

### What Phase 1G does

- Creates `lib/reliability/orchestration_plan.py` with pure planning helpers:
  - `ReliabilityFeatureFlags` — dataclass with safe defaults.
  - `get_default_reliability_flags()` — factory returning all-off defaults.
  - `reliability_mode_description()` — describes what a given flag set will do.
  - `build_orchestration_step_plan()` — per-step plan dict from flags.
  - `validate_flag_combination()` — warns about risky flag combinations.
  - `list_supported_future_steps()` — lists planned integration points.
- Creates `scripts/test_reliability_orchestration_plan.py` — isolated, zero-API test suite.
- Creates `examples/reliability/feature_flagged_orchestration_flow.md` — annotated examples.

### What Phase 1G does NOT do

- Does **not** modify `app.py`, `pages/*`, `lib/llm_orchestrator.py`, or any workflow module.
- Does **not** call the Claude API.
- Does **not** modify any live prompt.
- Does **not** wire reliability into any Streamlit page.
- Does **not** change any computation logic (`valuation.py`, `technical.py`, `rotation.py`, `data_fetcher.py`).
- Does **not** activate any reliability code path in the running app.

---

## B. Future Target Architecture

The full pipeline below is the **target state for Phase 2+**.  Phase 1G only
defines the flag contract and step plan structure; it does not execute any step.

```
Existing deterministic workflow step
  │  (e.g. Financial Analysis: valuation.py computes DCF, WACC, fair value)
  │
  │  [FUTURE: reliability_enabled=True]
  ▼
Adapter wrapper (e.g. valuation_tool_result())
  │  wraps already-computed outputs into a ToolResult
  │  deterministic evidence_id based on content hash
  ▼
EvidenceStore.add_tool_result()
  │  appends to tool_results.jsonl
  │  returns evidence_id
  ▼
build_evidence_packet(run_id, target, tool_results)
  │  compact evidence summary with IDs, output_keys, notable_field_paths
  ▼
build_agent_result_prompt(agent_name, run_id, target, task, packet)
  │  [only if use_constrained_prompts=True]
  │  deterministic constrained prompt with 11 hard rules
  ▼
LLM call (via future constrained interface — not live in Phase 1G)
  │  LLM must output AgentResult-compatible JSON
  │  LLM must cite only evidence_ids from the packet
  ▼
parse_agent_result_json(raw_output)
  │  schema validation — raises ValueError on malformed JSON
  ▼
validate_agent_result(agent_result, evidence_store)
  │  evidence existence + numeric binding checks
  ▼
ValidationReport
  │
  ├── passed=True  → accept findings, persist report
  │
  └── passed=False → [if enable_repair_prompt=True]
                       build_repair_prompt(errors, original_prompt)
                       → bounded LLM retry
                       → [if still fails] fallback to existing behavior
  ▼
[if block_on_validation_error=True and dry_run=False]
  Block workflow step and surface error
[else (default / dry_run=True)]
  Log ValidationReport for offline inspection
  Continue with existing app output unchanged
```

---

## C. Feature Flag Strategy

All flags are defined in `ReliabilityFeatureFlags` in `lib/reliability/orchestration_plan.py`.

| Flag | Default | Meaning |
|---|---|---|
| `reliability_enabled` | `False` | Master switch — when False, zero reliability code runs |
| `dry_run` | `True` | Collect artifacts without altering user-facing output |
| `block_on_validation_error` | `False` | Block workflow on failed validation (strict mode) |
| `show_ui_trace` | `False` | Show evidence trace panels in Streamlit |
| `use_constrained_prompts` | `False` | Use constrained AgentResult prompt contract |
| `enable_repair_prompt` | `False` | Retry with repair prompt on validation failure |

### Flag safety invariants

1. **`reliability_enabled=False`** (the default) must guarantee that the app
   behaves identically to today.  No ToolResults are collected, no validation
   runs, no UI is modified.
2. **`dry_run=True`** must guarantee that user-facing output is never altered,
   even when reliability is enabled.  Artifacts are written to disk for
   offline inspection only.
3. **`block_on_validation_error`** must default to `False` and must be
   overridden manually, never automatically.
4. **`show_ui_trace`** must default to `False`.  UI panels must never appear
   unless explicitly enabled.
5. **`use_constrained_prompts`** must default to `False`.  Existing prompts
   must remain unchanged unless explicitly opted in.

### Risky combinations (auto-detected by `validate_flag_combination()`)

| Combination | Risk |
|---|---|
| `block_on_validation_error=True` while `reliability_enabled=False` | Flag has no effect; potential confusion |
| `show_ui_trace=True` while `reliability_enabled=False` | Flag has no effect |
| `use_constrained_prompts=True` while `reliability_enabled=False` | Flag has no effect |
| `enable_repair_prompt=True` with `use_constrained_prompts=False` | Repair prompts require constrained output |
| `dry_run=False` with `block_on_validation_error=True` | Strict mode — may block user-facing output |

---

## D. Proposed Orchestration Boundaries

### Deterministic adapter layer (Phase 1A–1C, already implemented)

These adapters wrap already-computed Python dicts into `ToolResult` evidence.
They are pure functions with no side effects.

| Workflow step | Adapter function | `tool_name` |
|---|---|---|
| Financial analysis | `valuation_tool_result()` | `"valuation_model"` |
| Price/volume analysis | `technical_tool_result()` | `"technical_indicator_engine"` |
| Sector analysis | `sector_rotation_tool_result()` | `"sector_rotation_model"` |
| Stock scanner | `scanner_tool_result()` | `"stock_scanner"` |

### Evidence layer (Phase 0–0.2, already implemented)

| Component | Module |
|---|---|
| `RunContext` | `lib/reliability/run_context.py` |
| `EvidenceStore` | `lib/reliability/evidence_store.py` |
| `tool_results.jsonl` | Appended by `EvidenceStore.add_tool_result()` |
| `evidence_manifest.json` | Written by `EvidenceStore.save_manifest()` |

### Prompt contract layer (Phase 1E, already implemented)

| Function | Purpose |
|---|---|
| `build_evidence_packet()` | Compact evidence summary for prompt embedding |
| `build_agent_result_prompt()` | Constrained prompt with 11 hard rules |
| `build_repair_prompt()` | Future repair/retry prompt |

### Agent output layer (Phase 1D, already implemented)

| Function | Purpose |
|---|---|
| `parse_agent_result_json()` | Schema-only parse, raises `ValueError` on violation |
| `parse_and_validate_agent_result()` | Parse + evidence validation in one call |
| `agent_result_to_json()` | Lossless serialisation |

### Validation layer (Phase 0, already implemented)

| Component | Purpose |
|---|---|
| `validate_agent_result()` | Evidence existence + numeric binding checks |
| `ValidationReport` | Serialisable pass/fail with issue list |

---

## E. Proposed Future Integration Points

These are documentation of INTENDED future changes.  **None of these have been
implemented yet.**  Each entry is a proposal for a future phase.

### Financial analysis step (future Phase 2A)

```python
# Future: inside lib/workflow_state.py or lib/llm_orchestrator.py
# (gated behind RELIABILITY_ENABLED feature flag)

# 1. Existing computation runs unchanged
val_outputs = run_dcf_model(ticker, ...)       # valuation.py — not modified

# 2. Wrap into ToolResult (new, gated)
if flags.collect_tool_results:
    tr = valuation_tool_result(run_id, ticker, "dcf", val_outputs)
    evidence_store.add_tool_result(tr)

# 3. Build constrained prompt (new, gated)
if flags.use_constrained_prompts:
    packet = build_evidence_packet(run_id, ticker, [tr])
    prompt = build_agent_result_prompt("financial_agent", run_id, ticker, task, packet)
    raw = call_llm(prompt)                     # future constrained call
    ar, report = parse_and_validate_agent_result(raw, evidence_store)
else:
    # Existing prompt and LLM call — unchanged
    raw = existing_llm_call(...)

# 4. Handle validation result (new, gated)
if flags.validate_agent_result and report is not None:
    if not report.passed and flags.block_on_validation_error and not flags.dry_run:
        raise ValidationBlockedError(report)
    persist_validation_report(report)
```

### Price/volume analysis step (future Phase 2B)

Same pattern but using `technical_tool_result()` and `"price_volume_analyst"`.

### Sector analysis step (future Phase 2B)

Same pattern but using `sector_rotation_tool_result()` and `"sector_agent"`.

### Stock scanner step (future Phase 2B)

Same pattern but using `scanner_tool_result()` and `"scanner_agent"`.

### Synthesis step (future Phase 2C)

Consume multiple `ValidationReport` objects from prior steps.  Produce a
final auditable recommendation with cross-step evidence coherence check.

---

## F. Dry-Run Behavior

When `reliability_enabled=True` and `dry_run=True`:

| Aspect | Behavior |
|---|---|
| Existing workflow | Runs as-is, unmodified |
| ToolResult collection | Runs in parallel — does not replace existing computation |
| EvidenceStore | Populated in the background |
| Constrained prompts | NOT used (dry-run does not alter LLM input) |
| AgentResult parsing | NOT used (no constrained output to parse) |
| Validation | Runs against any existing LLM output IF it can be parsed (for research/debug) |
| ValidationReport | Persisted to `research/runs/<run_id>/` for offline inspection |
| User-facing output | **Unchanged** — dry-run output never replaces live display |
| Workflow blocking | **Never** — dry-run never blocks |
| UI trace | Only if `show_ui_trace=True` |

Dry-run mode is the safe onramp.  Operators can monitor ValidationReports
without risking any regression in user-visible output.

---

## G. Error-Handling Strategy

| Error condition | Dry-run behavior | Strict mode behavior |
|---|---|---|
| Schema parse failure | Log, continue with existing output | Log + raise if blocking enabled |
| Malformed LLM JSON | Log, continue | Log + trigger repair prompt if enabled |
| `INVALID_EVIDENCE_ID` | Log in ValidationReport | Block if `block_on_validation_error=True` |
| `UNSUPPORTED_NUMERIC_CLAIM` | Log in ValidationReport | Block if `block_on_validation_error=True` |
| `WEAK_NUMERIC_EVIDENCE_BINDING` | Log warning (not blocking) | Log warning (not blocking) |
| `INVALID_EVIDENCE_TOOL_BINDING` | Log warning | Log warning |
| `INVALID_EVIDENCE_METRIC_BINDING` | Log warning | Log warning |
| `INVALID_EVIDENCE_FIELD_PATH_BINDING` | Log warning | Log warning |
| Repair prompt generated | Not sent to LLM in dry-run | Sent to LLM if `enable_repair_prompt=True` |
| Repair still fails | Fallback to existing output | Fallback to existing output or hard block |

**Invariant**: Never silently accept invalid evidence in strict mode.  If
`block_on_validation_error=True` and `dry_run=False`, a failed
`ValidationReport` must surface as an error — it must never be swallowed.

---

## H. Rollout Sequence

| Phase | Description | Prerequisite |
|---|---|---|
| **Phase 2A** | Add `ReliabilityFeatureFlags` config to a config file or env vars.  Default all flags off.  No behavior change. | Phase 1G accepted |
| **Phase 2B** | Dry-run ToolResult collection for one isolated step (e.g. Financial Analysis).  Persists artifacts without altering output. | Phase 2A |
| **Phase 2C** | Dry-run `ValidationReport` persistence and logging for all four analysis steps. | Phase 2B |
| **Phase 2D** | Constrained prompt behind `use_constrained_prompts` flag for one agent.  Output not yet shown to users. | Phase 2C |
| **Phase 2E** | Repair/retry loop behind `enable_repair_prompt` flag.  Bounded retries (max 2). | Phase 2D |
| **Phase 2F** | UI evidence trace panel in Streamlit behind `show_ui_trace` flag.  Initially debug-only. | Phase 2E |
| **Phase 3** | Critic / debate layer — multiple agents cross-check each other's findings. | Phase 2F |

---

## I. Non-Goals for Phase 1G

| Category | Out-of-scope items |
|---|---|
| **Streamlit** | No page changes, no UI panels, no session state modifications |
| **App workflow** | No changes to `app.py`, `lib/workflow_state.py`, or existing workflow |
| **llm_orchestrator.py** | No modifications; no imports from it |
| **Live prompts** | No changes to existing prompt files or `.claude/agents/*` |
| **Claude API** | No live API calls; no `anthropic` SDK usage |
| **Computation** | No changes to `lib/rotation.py`, `lib/technical.py`, `lib/valuation.py`, `lib/data_fetcher.py` |
| **Blocking validation** | No validation blocks any step in Phase 1G |
| **UI evidence trace** | No Streamlit evidence panels added |
| **Semantic validation** | Structural checks only — no interpretation of claim correctness |
| **Debate / critique layer** | No agent-vs-agent checking |
| **Memory layer** | No long-term agent memory or cross-run learning |
| **Investment cockpit** | Reliability stays in the research workflow only |

---

## Appendix: Flag Defaults Table

| Flag | Default | Activation phase |
|---|---|---|
| `reliability_enabled` | `False` | Phase 2A |
| `dry_run` | `True` | Phase 2B |
| `block_on_validation_error` | `False` | Phase 2E (opt-in) |
| `show_ui_trace` | `False` | Phase 2F (opt-in) |
| `use_constrained_prompts` | `False` | Phase 2D (opt-in) |
| `enable_repair_prompt` | `False` | Phase 2E (opt-in) |

## Appendix: Supported Future Steps

| Step name | Agent type | Primary adapter |
|---|---|---|
| `sector_analysis` | Sector Research | `sector_rotation_tool_result()` |
| `stock_scanner` | Stock Scanner | `scanner_tool_result()` |
| `equity_research` | Equity Research | *(future adapter)* |
| `financial_analysis` | Financial Analyst | `valuation_tool_result()` |
| `price_volume_analysis` | Price & Volume | `technical_tool_result()` |
| `synthesis` | Orchestrator | *(consumes ValidationReports)* |
