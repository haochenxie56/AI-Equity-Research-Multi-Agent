# Feature-Flagged Reliability Orchestration Flow — Examples

**Phase**: 1G — Feature-Flagged Reliability Orchestration Design
**Status**: Documentation only — not wired into the app yet
**Date**: 2026-05-21

> **Important**: All examples below illustrate the PLANNED behavior of the
> reliability orchestration layer.  None of these code paths are active in
> the live application.  The helpers shown exist in
> `lib/reliability/orchestration_plan.py` as pure planning functions only.

---

## 1. Default-Off Flag Example

The default flag set guarantees zero impact on the existing app.

```python
from lib.reliability.orchestration_plan import (
    get_default_reliability_flags,
    reliability_mode_description,
    build_orchestration_step_plan,
)

flags = get_default_reliability_flags()

# All flags are at their safe defaults
assert flags.reliability_enabled is False
assert flags.dry_run is True
assert flags.block_on_validation_error is False
assert flags.show_ui_trace is False
assert flags.use_constrained_prompts is False
assert flags.enable_repair_prompt is False

# Mode description confirms nothing is active
desc = reliability_mode_description(flags)
# {
#   "reliability_active": False,
#   "dry_run_active": False,
#   "alters_app_output": False,
#   "blocks_on_error": False,
#   "shows_ui_trace": False,
#   "uses_constrained_prompts": False,
#   "repair_prompt_enabled": False,
#   "summary": "Reliability layer inactive. Existing app behavior is completely unchanged."
# }

# Any step plan is fully inert
plan = build_orchestration_step_plan("financial_analysis", flags)
# {
#   "step_name": "financial_analysis",
#   "collect_tool_results": False,
#   "build_evidence_packet": False,
#   "use_constrained_prompt": False,
#   "parse_agent_result": False,
#   "validate_agent_result": False,
#   "persist_validation_report": False,
#   "block_on_error": False,
#   "show_trace": False,
#   "fallback_behavior": "existing_workflow_unchanged"
# }
```

The existing Financial Analysis page behavior is 100% unaffected.

---

## 2. Dry-Run Flag Example

Enable reliability in dry-run mode: collect artifacts without altering output.

```python
from lib.reliability.orchestration_plan import ReliabilityFeatureFlags

flags = ReliabilityFeatureFlags(
    reliability_enabled=True,
    dry_run=True,
    # All other flags remain at their safe defaults
)

desc = reliability_mode_description(flags)
# {
#   "reliability_active": True,
#   "dry_run_active": True,
#   "alters_app_output": False,   ← output unchanged
#   "blocks_on_error": False,     ← never blocks in dry-run
#   "shows_ui_trace": False,
#   "uses_constrained_prompts": False,
#   "repair_prompt_enabled": False,
#   "summary": "Reliability layer active; dry-run (artifacts only, output unchanged)."
# }

plan = build_orchestration_step_plan("financial_analysis", flags)
# {
#   "step_name": "financial_analysis",
#   "collect_tool_results": True,       ← ToolResults collected in background
#   "build_evidence_packet": True,      ← evidence packet built
#   "use_constrained_prompt": False,    ← existing prompt unchanged
#   "parse_agent_result": False,        ← no constrained output to parse
#   "validate_agent_result": True,      ← validation runs for inspection
#   "persist_validation_report": True,  ← report written to disk
#   "block_on_error": False,            ← NEVER blocks in dry-run
#   "show_trace": False,
#   "fallback_behavior": "dry_run_artifacts_only"
# }
```

In dry-run mode:
- The existing LLM call and displayed output are **completely unchanged**.
- ToolResults are written to `research/runs/<run_id>/tool_results.jsonl`.
- ValidationReports are written for offline inspection.
- Operators can review artifacts without any user-visible impact.

---

## 3. Strict Mode Future Example

**Not recommended until reliability is proven stable via dry-run monitoring.**

```python
from lib.reliability.orchestration_plan import (
    ReliabilityFeatureFlags,
    validate_flag_combination,
)

flags = ReliabilityFeatureFlags(
    reliability_enabled=True,
    dry_run=False,                      # strict mode
    block_on_validation_error=True,     # validation errors block output
    show_ui_trace=True,                 # evidence trace in UI
    use_constrained_prompts=True,       # constrained AgentResult prompt
    enable_repair_prompt=True,          # retry on failure
)

# validate_flag_combination warns about strict mode
warnings = validate_flag_combination(flags)
# [
#   "dry_run=False with block_on_validation_error=True enables strict mode. "
#   "Validation errors will block workflow output. ..."
# ]

plan = build_orchestration_step_plan("financial_analysis", flags)
# {
#   "step_name": "financial_analysis",
#   "collect_tool_results": True,
#   "build_evidence_packet": True,
#   "use_constrained_prompt": True,     ← constrained prompt used
#   "parse_agent_result": True,         ← AgentResult JSON parsed
#   "validate_agent_result": True,
#   "persist_validation_report": True,
#   "block_on_error": True,             ← blocks on validation failure
#   "show_trace": True,                 ← UI trace shown
#   "fallback_behavior": "reliability_enforced"
# }
```

Strict mode is only appropriate after Phase 2E+ validation.  The warning from
`validate_flag_combination()` is intentional — it requires an explicit
override, not an accidental config.

---

## 4. Per-Step Plan Example: `financial_analysis`

Showing how the same flags produce different plans for different steps.
*(All with the same dry-run flags from Example 2.)*

```python
flags = ReliabilityFeatureFlags(
    reliability_enabled=True,
    dry_run=True,
    use_constrained_prompts=False,
    show_ui_trace=False,
)

steps = [
    "financial_analysis",
    "price_volume_analysis",
    "sector_analysis",
    "stock_scanner",
    "equity_research",
    "synthesis",
]

for step in steps:
    plan = build_orchestration_step_plan(step, flags)
    print(f"{step}: collect={plan['collect_tool_results']}, "
          f"block={plan['block_on_error']}, "
          f"fallback={plan['fallback_behavior']}")

# financial_analysis:    collect=True, block=False, fallback=dry_run_artifacts_only
# price_volume_analysis: collect=True, block=False, fallback=dry_run_artifacts_only
# sector_analysis:       collect=True, block=False, fallback=dry_run_artifacts_only
# stock_scanner:         collect=True, block=False, fallback=dry_run_artifacts_only
# equity_research:       collect=True, block=False, fallback=dry_run_artifacts_only
# synthesis:             collect=True, block=False, fallback=dry_run_artifacts_only
```

With default-off flags the same loop produces all False for every field.

---

## 5. Risky Combination Detection Example

```python
from lib.reliability.orchestration_plan import (
    ReliabilityFeatureFlags,
    validate_flag_combination,
)

# Inconsistent: blocking without reliability enabled
flags = ReliabilityFeatureFlags(
    reliability_enabled=False,
    block_on_validation_error=True,  # has no effect while disabled
    show_ui_trace=True,              # has no effect while disabled
)
warnings = validate_flag_combination(flags)
# [
#   "block_on_validation_error=True has no effect while reliability_enabled=False...",
#   "show_ui_trace=True has no effect while reliability_enabled=False..."
# ]

# Inconsistent: repair prompt without constrained prompts
flags2 = ReliabilityFeatureFlags(
    reliability_enabled=True,
    dry_run=True,
    use_constrained_prompts=False,
    enable_repair_prompt=True,      # only useful with constrained prompts
)
warnings2 = validate_flag_combination(flags2)
# [
#   "enable_repair_prompt=True has limited effect while use_constrained_prompts=False..."
# ]

# Clean config — no warnings
flags3 = ReliabilityFeatureFlags(
    reliability_enabled=True,
    dry_run=True,
)
warnings3 = validate_flag_combination(flags3)
# []  ← no warnings
```

---

## 6. This Is Not Wired Into the App

All examples above use `lib/reliability/orchestration_plan.py` as a
**planning and configuration helper only**.  The helper functions:

- Do NOT read or write any Streamlit session state.
- Do NOT call `lib/llm_orchestrator.py` or any LLM API.
- Do NOT modify `lib/valuation.py`, `lib/technical.py`, `lib/rotation.py`,
  or `lib/data_fetcher.py`.
- Do NOT change any live prompt or `.claude/agents/*` file.
- Do NOT alter any existing `app.py` or `pages/*` behavior.

The planning helpers simply describe what WILL happen when a future phase
wires the feature flag into the live workflow.  Until that wiring is done
(Phase 2A+), the live application is completely unchanged.
