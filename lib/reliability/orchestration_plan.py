"""
lib/reliability/orchestration_plan.py

Pure planning and configuration helpers for a future feature-flagged
reliability orchestration layer.

Design principles:
  - Pure functions and dataclasses only.
  - No Streamlit imports.
  - No imports from lib/llm_orchestrator.py, app.py, or any workflow module.
  - No file I/O.
  - No API calls.
  - No side effects.
  - All helpers are deterministic for the same inputs.
  - Default flags are safe and non-invasive: reliability_enabled=False by default.

This module defines HOW reliability orchestration will eventually work.
It does NOT wire anything into the live app or workflow.

See docs/reliability_phase_1g_feature_flagged_orchestration_design.md for the
full design rationale and rollout sequence.
"""

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Feature flag dataclass
# ---------------------------------------------------------------------------

@dataclass
class ReliabilityFeatureFlags:
    """
    Feature flags governing the reliability orchestration layer.

    All flags default to the safe, non-invasive state that leaves the existing
    application behavior completely unchanged.

    Fields:
        reliability_enabled:
            Master switch.  When False (the default), the reliability layer is
            entirely inactive — no ToolResults are collected, no evidence
            packets are built, no validation is performed.  All other flags are
            meaningless while this is False.

        dry_run:
            When True (the default, for future use), reliability artifacts
            (ToolResults, ValidationReports) are generated and persisted in
            the background, but the user-facing LLM output is NOT altered.
            Dry-run never blocks the workflow even if validation fails.

        block_on_validation_error:
            When True, a failed ValidationReport (passed=False) will block the
            workflow step and prevent the LLM output from being shown.
            Defaults to False — must remain False during dry-run phase.

        show_ui_trace:
            When True, the Streamlit UI will display evidence trace panels
            (ValidationReport details, ToolResult summaries).
            Defaults to False.

        use_constrained_prompts:
            When True, the LLM is given a constrained prompt contract
            (built by build_agent_result_prompt()) instead of the existing
            free-form prompt.  The response is expected to be AgentResult JSON.
            Defaults to False.

        enable_repair_prompt:
            When True and a validation error occurs, a repair prompt is
            generated and the LLM is given a bounded retry.
            Requires use_constrained_prompts=True to be meaningful.
            Defaults to False.
    """

    reliability_enabled: bool = False
    dry_run: bool = True
    block_on_validation_error: bool = False
    show_ui_trace: bool = False
    use_constrained_prompts: bool = False
    enable_repair_prompt: bool = False


# ---------------------------------------------------------------------------
# Default flag factory
# ---------------------------------------------------------------------------

def get_default_reliability_flags() -> ReliabilityFeatureFlags:
    """
    Return default-safe reliability feature flags.

    The defaults guarantee that:
      - No reliability code path runs in the live app.
      - No user-facing output is altered.
      - No workflow step is blocked.
      - No UI elements are added.

    Returns:
        ``ReliabilityFeatureFlags`` with all flags at their safe defaults.

    Examples::

        flags = get_default_reliability_flags()
        assert flags.reliability_enabled is False
        assert flags.dry_run is True
        assert flags.block_on_validation_error is False
    """
    return ReliabilityFeatureFlags()


# ---------------------------------------------------------------------------
# Mode description
# ---------------------------------------------------------------------------

def reliability_mode_description(flags: ReliabilityFeatureFlags) -> dict:
    """
    Return a deterministic dict describing what the given flags will do.

    This is a pure function intended for debugging, config validation, and
    documentation of the current reliability mode.  It does not perform any
    reliability operations itself.

    When ``reliability_enabled=False``:
      - ``reliability_active``   = False
      - ``alters_app_output``    = False
      - ``blocks_on_error``      = False
      - ``shows_ui_trace``       = False
      - ``uses_constrained_prompts`` = False
      - ``repair_prompt_enabled`` = False

    Args:
        flags: A ``ReliabilityFeatureFlags`` instance.

    Returns:
        A dict with the following keys:

        - ``reliability_active`` (bool): True iff reliability_enabled is True.
        - ``dry_run_active`` (bool): True iff enabled and dry_run is True.
        - ``alters_app_output`` (bool): True iff enabled and NOT dry-run mode;
          when enabled in strict mode (dry_run=False) the constrained prompt
          or blocking behaviour may alter what the user sees.
        - ``blocks_on_error`` (bool): True iff enabled and block_on_validation_error.
        - ``shows_ui_trace`` (bool): True iff enabled and show_ui_trace.
        - ``uses_constrained_prompts`` (bool): True iff enabled and use_constrained_prompts.
        - ``repair_prompt_enabled`` (bool): True iff enabled and enable_repair_prompt.
        - ``summary`` (str): A human-readable one-line description.

    Examples::

        flags = get_default_reliability_flags()
        desc = reliability_mode_description(flags)
        assert desc["reliability_active"] is False
        assert desc["alters_app_output"] is False
    """
    enabled = flags.reliability_enabled

    if not enabled:
        return {
            "reliability_active": False,
            "dry_run_active": False,
            "alters_app_output": False,
            "blocks_on_error": False,
            "shows_ui_trace": False,
            "uses_constrained_prompts": False,
            "repair_prompt_enabled": False,
            "summary": (
                "Reliability layer inactive. "
                "Existing app behavior is completely unchanged."
            ),
        }

    dry_run = flags.dry_run
    # In strict mode (not dry_run) with constrained prompts, output is altered.
    alters_output = not dry_run

    # blocks_on_error mirrors the same invariant enforced in build_orchestration_step_plan:
    # dry_run=True always prevents blocking, even when block_on_validation_error=True.
    blocks_on_error = flags.block_on_validation_error and not dry_run

    summary_parts = ["Reliability layer active"]
    if dry_run:
        summary_parts.append("dry-run (artifacts only, output unchanged)")
    else:
        summary_parts.append("strict mode (output may be altered)")
    if blocks_on_error:
        summary_parts.append("blocking on validation error")
    if flags.show_ui_trace:
        summary_parts.append("UI trace enabled")
    if flags.use_constrained_prompts:
        summary_parts.append("constrained prompts active")

    return {
        "reliability_active": True,
        "dry_run_active": dry_run,
        "alters_app_output": alters_output,
        "blocks_on_error": blocks_on_error,
        "shows_ui_trace": flags.show_ui_trace,
        "uses_constrained_prompts": flags.use_constrained_prompts,
        "repair_prompt_enabled": flags.enable_repair_prompt,
        "summary": "; ".join(summary_parts) + ".",
    }


# ---------------------------------------------------------------------------
# Per-step orchestration plan
# ---------------------------------------------------------------------------

def build_orchestration_step_plan(
    step_name: str,
    flags: ReliabilityFeatureFlags,
) -> dict:
    """
    Return a deterministic plan dict describing what the reliability layer
    will do for a named future workflow step.

    This is a pure planning function.  It does NOT execute any step, create
    any file, or call any LLM.  The returned dict describes the INTENDED
    future behavior given the provided flags — it is a specification, not an
    execution.

    Args:
        step_name: Name of the future workflow step, e.g. ``"financial_analysis"``.
        flags:     ``ReliabilityFeatureFlags`` controlling orchestration.

    Returns:
        A dict with the following keys:

        - ``step_name`` (str): The input step name, echoed back.
        - ``collect_tool_results`` (bool): Whether deterministic outputs should
          be wrapped into ToolResults for this step.
        - ``build_evidence_packet`` (bool): Whether an evidence packet should
          be constructed for the prompt contract.
        - ``use_constrained_prompt`` (bool): Whether the LLM should receive a
          constrained AgentResult prompt instead of the existing free-form prompt.
        - ``parse_agent_result`` (bool): Whether the LLM response should be
          parsed as AgentResult JSON.  Only meaningful when use_constrained_prompt
          is True.
        - ``validate_agent_result`` (bool): Whether validate_agent_result()
          should be called on the parsed response.
        - ``persist_validation_report`` (bool): Whether the ValidationReport
          should be persisted to disk.
        - ``block_on_error`` (bool): Whether a failed ValidationReport should
          block the workflow step.  Always False in dry-run mode.
        - ``show_trace`` (bool): Whether a UI evidence trace should be shown.
        - ``fallback_behavior`` (str): What happens to the existing workflow
          when reliability is active.

    Reliability disabled (``reliability_enabled=False``):
        All active behaviours are False.  ``fallback_behavior`` =
        ``"existing_workflow_unchanged"``.

    Dry-run (``reliability_enabled=True``, ``dry_run=True``):
        Collection and validation run in the background.  ``block_on_error``
        is always False.  ``fallback_behavior`` = ``"dry_run_artifacts_only"``.

    Strict mode (``reliability_enabled=True``, ``dry_run=False``):
        All flags take effect.  ``block_on_error`` mirrors
        ``block_on_validation_error``.  ``fallback_behavior`` =
        ``"reliability_enforced"``.

    Examples::

        flags = get_default_reliability_flags()
        plan = build_orchestration_step_plan("financial_analysis", flags)
        assert plan["collect_tool_results"] is False
        assert plan["fallback_behavior"] == "existing_workflow_unchanged"
    """
    if not isinstance(step_name, str) or not step_name.strip():
        raise ValueError(
            f"'step_name' must be a non-empty, non-blank string; got {step_name!r}."
        )

    if not flags.reliability_enabled:
        return {
            "step_name": step_name,
            "collect_tool_results": False,
            "build_evidence_packet": False,
            "use_constrained_prompt": False,
            "parse_agent_result": False,
            "validate_agent_result": False,
            "persist_validation_report": False,
            "block_on_error": False,
            "show_trace": False,
            "fallback_behavior": "existing_workflow_unchanged",
        }

    dry_run = flags.dry_run
    use_constrained = flags.use_constrained_prompts

    # block_on_error: only in strict mode (not dry_run) AND if flag is set
    block_on_error = flags.block_on_validation_error and not dry_run

    # parse_agent_result only makes sense if constrained prompts generate AgentResult JSON
    parse_agent_result = use_constrained

    if dry_run:
        fallback = "dry_run_artifacts_only"
    else:
        fallback = "reliability_enforced"

    return {
        "step_name": step_name,
        "collect_tool_results": True,
        "build_evidence_packet": True,
        "use_constrained_prompt": use_constrained,
        "parse_agent_result": parse_agent_result,
        "validate_agent_result": True,
        "persist_validation_report": True,
        "block_on_error": block_on_error,
        "show_trace": flags.show_ui_trace,
        "fallback_behavior": fallback,
    }


# ---------------------------------------------------------------------------
# Flag combination validator
# ---------------------------------------------------------------------------

def validate_flag_combination(flags: ReliabilityFeatureFlags) -> list[str]:
    """
    Return a list of warning strings for risky or inconsistent flag combinations.

    This function does NOT raise exceptions.  It returns an empty list for
    clean configurations and a non-empty list for combinations that are
    potentially dangerous or ineffective.

    Checked conditions:

    +------------------------------------------------------------+----------------------------------------------------------+
    | Condition                                                  | Warning                                                  |
    +============================================================+==========================================================+
    | ``block_on_validation_error=True`` while disabled          | Flag has no effect                                       |
    +------------------------------------------------------------+----------------------------------------------------------+
    | ``show_ui_trace=True`` while disabled                      | Flag has no effect                                       |
    +------------------------------------------------------------+----------------------------------------------------------+
    | ``use_constrained_prompts=True`` while disabled            | Flag has no effect                                       |
    +------------------------------------------------------------+----------------------------------------------------------+
    | ``enable_repair_prompt=True`` without constrained prompts  | Repair has limited effect without constrained prompts    |
    +------------------------------------------------------------+----------------------------------------------------------+
    | ``dry_run=False`` with ``block_on_validation_error=True``  | Strict mode — validation errors will block output        |
    +------------------------------------------------------------+----------------------------------------------------------+

    Args:
        flags: ``ReliabilityFeatureFlags`` to validate.

    Returns:
        List of warning strings (may be empty).

    Examples::

        flags = ReliabilityFeatureFlags(
            reliability_enabled=False,
            block_on_validation_error=True,
        )
        warnings = validate_flag_combination(flags)
        assert len(warnings) >= 1
        assert any("block_on_validation_error" in w for w in warnings)
    """
    warnings: list[str] = []

    if not flags.reliability_enabled:
        if flags.block_on_validation_error:
            warnings.append(
                "block_on_validation_error=True has no effect while "
                "reliability_enabled=False. Set reliability_enabled=True to activate."
            )
        if flags.show_ui_trace:
            warnings.append(
                "show_ui_trace=True has no effect while "
                "reliability_enabled=False. Set reliability_enabled=True to activate."
            )
        if flags.use_constrained_prompts:
            warnings.append(
                "use_constrained_prompts=True has no effect while "
                "reliability_enabled=False. Set reliability_enabled=True to activate."
            )

    if flags.enable_repair_prompt and not flags.use_constrained_prompts:
        warnings.append(
            "enable_repair_prompt=True has limited effect while "
            "use_constrained_prompts=False. Repair prompts are only useful when "
            "constrained prompts generate AgentResult-compatible JSON."
        )

    if not flags.dry_run and flags.block_on_validation_error:
        warnings.append(
            "dry_run=False with block_on_validation_error=True enables strict mode. "
            "Validation errors will block workflow output. "
            "Ensure reliability is stable before enabling strict mode in production."
        )

    return warnings


# ---------------------------------------------------------------------------
# Supported future steps
# ---------------------------------------------------------------------------

def list_supported_future_steps() -> list[str]:
    """
    Return the list of future workflow steps that the reliability layer is
    planned to support.

    This list is documentation of the intended integration scope.  None of
    these steps are currently wired to reliability.  Each step maps to one
    or more adapter functions and agent types.

    Returns:
        A list of step name strings.

    Step → planned adapter mapping:

    +------------------------+----------------------------------------+
    | Step                   | Planned adapters                       |
    +========================+========================================+
    | sector_analysis        | sector_rotation_tool_result()          |
    +------------------------+----------------------------------------+
    | stock_scanner          | scanner_tool_result()                  |
    +------------------------+----------------------------------------+
    | equity_research        | (future) equity_research_tool_result() |
    +------------------------+----------------------------------------+
    | financial_analysis     | valuation_tool_result()                |
    +------------------------+----------------------------------------+
    | price_volume_analysis  | technical_tool_result()                |
    +------------------------+----------------------------------------+
    | synthesis              | (consumes multiple ValidationReports)  |
    +------------------------+----------------------------------------+
    """
    return [
        "sector_analysis",
        "stock_scanner",
        "equity_research",
        "financial_analysis",
        "price_volume_analysis",
        "synthesis",
    ]
