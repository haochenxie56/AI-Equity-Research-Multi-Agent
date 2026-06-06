"""
lib/reliability/config.py

Configuration helpers for the reliability feature-flag layer.

This module provides safe, deterministic helpers for loading
``ReliabilityFeatureFlags`` from environment variables or arbitrary
mappings.  All functions are pure (no side effects) except
``load_reliability_flags_from_env``, which reads ``os.environ`` when no
explicit mapping is supplied.

Design principles:
  - Reliability is always **off by default**.  A missing or empty
    environment mapping returns the safe all-off flags.
  - Boolean parsing is strict and explicit: only well-known tokens are
    accepted.  Unknown strings raise ``ValueError`` rather than silently
    defaulting.
  - No Streamlit imports.
  - No imports from ``lib/llm_orchestrator.py``, ``app.py``, or any
    workflow module.
  - No file I/O.
  - No API calls.
  - No side effects on the global interpreter state.

Supported environment variable names
-------------------------------------
  RELIABILITY_ENABLED                  → ``reliability_enabled``
  RELIABILITY_DRY_RUN                  → ``dry_run``
  RELIABILITY_BLOCK_ON_VALIDATION_ERROR → ``block_on_validation_error``
  RELIABILITY_SHOW_UI_TRACE            → ``show_ui_trace``
  RELIABILITY_USE_CONSTRAINED_PROMPTS  → ``use_constrained_prompts``
  RELIABILITY_ENABLE_REPAIR_PROMPT     → ``enable_repair_prompt``

Safe defaults
-------------
  reliability_enabled           = False
  dry_run                       = True
  block_on_validation_error     = False
  show_ui_trace                 = False
  use_constrained_prompts       = False
  enable_repair_prompt          = False

See docs/reliability_phase_2a_feature_flag_config.md for the full design
rationale and rollout sequence.
"""

from __future__ import annotations

import os
from typing import Any, Mapping

from lib.reliability.orchestration_plan import (
    ReliabilityFeatureFlags,
    get_default_reliability_flags,
    validate_flag_combination,
)


# ---------------------------------------------------------------------------
# Environment variable key constants
# ---------------------------------------------------------------------------

_ENV_RELIABILITY_ENABLED = "RELIABILITY_ENABLED"
_ENV_DRY_RUN = "RELIABILITY_DRY_RUN"
_ENV_BLOCK_ON_VALIDATION_ERROR = "RELIABILITY_BLOCK_ON_VALIDATION_ERROR"
_ENV_SHOW_UI_TRACE = "RELIABILITY_SHOW_UI_TRACE"
_ENV_USE_CONSTRAINED_PROMPTS = "RELIABILITY_USE_CONSTRAINED_PROMPTS"
_ENV_ENABLE_REPAIR_PROMPT = "RELIABILITY_ENABLE_REPAIR_PROMPT"

# Ordered mapping: env-var key → (flag field name, safe default)
_FLAG_SPECS: tuple[tuple[str, str, bool], ...] = (
    (_ENV_RELIABILITY_ENABLED, "reliability_enabled", False),
    (_ENV_DRY_RUN, "dry_run", True),
    (_ENV_BLOCK_ON_VALIDATION_ERROR, "block_on_validation_error", False),
    (_ENV_SHOW_UI_TRACE, "show_ui_trace", False),
    (_ENV_USE_CONSTRAINED_PROMPTS, "use_constrained_prompts", False),
    (_ENV_ENABLE_REPAIR_PROMPT, "enable_repair_prompt", False),
)

_TRUTHY_STRINGS: frozenset[str] = frozenset({"1", "true", "yes", "y", "on"})
_FALSY_STRINGS: frozenset[str] = frozenset({"0", "false", "no", "n", "off"})


# ---------------------------------------------------------------------------
# Boolean parser
# ---------------------------------------------------------------------------

def parse_bool(value: Any, name: str = "value") -> bool:
    """
    Parse *value* into a ``bool`` using explicit, safe rules.

    Accepted inputs
    ~~~~~~~~~~~~~~~
    - Actual ``bool``: returned as-is.
    - Strings (stripped, lower-cased):

      +-----------+---------+
      | String    | Result  |
      +===========+=========+
      | ``"1"``   | ``True``|
      | ``"true"``| ``True``|
      | ``"yes"`` | ``True``|
      | ``"y"``   | ``True``|
      | ``"on"``  | ``True``|
      +-----------+---------+
      | ``"0"``   | ``False``|
      | ``"false"``|``False``|
      | ``"no"``  | ``False``|
      | ``"n"``   | ``False``|
      | ``"off"`` | ``False``|
      +-----------+---------+

    All other strings (including empty strings and unrecognised tokens)
    raise ``ValueError``.  Types other than ``bool`` and ``str`` also
    raise ``ValueError``.

    Args:
        value: The value to parse.
        name:  Human-readable label included in error messages.

    Returns:
        ``True`` or ``False``.

    Raises:
        ValueError: If *value* cannot be parsed.

    Examples::

        >>> parse_bool(True)
        True
        >>> parse_bool("yes")
        True
        >>> parse_bool("  FALSE  ")
        False
        >>> parse_bool("maybe", name="dry_run")
        ValueError: Cannot parse dry_run='maybe' as bool. ...
    """
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        normalised = value.strip().lower()
        if normalised in _TRUTHY_STRINGS:
            return True
        if normalised in _FALSY_STRINGS:
            return False
        raise ValueError(
            f"Cannot parse {name}={value!r} as bool. "
            f"Accepted truthy strings: {sorted(_TRUTHY_STRINGS)}. "
            f"Accepted falsy strings: {sorted(_FALSY_STRINGS)}."
        )

    raise ValueError(
        f"Cannot parse {name}={value!r} as bool: "
        f"expected bool or str, got {type(value).__name__!r}."
    )


# ---------------------------------------------------------------------------
# Mapping loader
# ---------------------------------------------------------------------------

def load_reliability_flags_from_mapping(
    mapping: Mapping[str, Any],
) -> ReliabilityFeatureFlags:
    """
    Load ``ReliabilityFeatureFlags`` from a key→value mapping.

    Missing keys fall back to safe defaults.  Values are parsed with
    :func:`parse_bool`.  Unknown keys in *mapping* are silently ignored.
    The input mapping is never mutated.

    Args:
        mapping: A ``Mapping`` keyed by environment variable names (see
                 module docstring).  Values may be ``bool`` or ``str``.

    Returns:
        A ``ReliabilityFeatureFlags`` instance.

    Raises:
        ValueError: If any recognised key has an unparseable bool value.

    Examples::

        flags = load_reliability_flags_from_mapping({})
        assert flags.reliability_enabled is False   # safe default

        flags = load_reliability_flags_from_mapping(
            {"RELIABILITY_ENABLED": "true", "RELIABILITY_DRY_RUN": "true"}
        )
        assert flags.reliability_enabled is True
        assert flags.dry_run is True
    """
    kwargs: dict[str, bool] = {}
    for env_key, field_name, default in _FLAG_SPECS:
        if env_key in mapping:
            # Key is present — parse it; None and invalid values raise ValueError.
            kwargs[field_name] = parse_bool(mapping[env_key], name=env_key)
        else:
            # Key is absent — fall back to safe default.
            kwargs[field_name] = default
    return ReliabilityFeatureFlags(**kwargs)


# ---------------------------------------------------------------------------
# Environment loader
# ---------------------------------------------------------------------------

def load_reliability_flags_from_env(
    env: Mapping[str, str] | None = None,
) -> ReliabilityFeatureFlags:
    """
    Load ``ReliabilityFeatureFlags`` from environment variables.

    If *env* is ``None``, the function reads from ``os.environ``.
    Otherwise it reads from the provided mapping (useful for testing).

    This function never mutates *env*.

    Args:
        env: Optional mapping to read from.  Defaults to ``os.environ``.

    Returns:
        A ``ReliabilityFeatureFlags`` instance.

    Raises:
        ValueError: If any reliability env var contains an unparseable
                    bool string.

    Examples::

        # Reads live process environment
        flags = load_reliability_flags_from_env()

        # Unit-testable override
        flags = load_reliability_flags_from_env(
            {"RELIABILITY_ENABLED": "false"}
        )
        assert flags.reliability_enabled is False
    """
    source: Mapping[str, str] = os.environ if env is None else env
    return load_reliability_flags_from_mapping(source)


# ---------------------------------------------------------------------------
# Env-dict serialiser
# ---------------------------------------------------------------------------

def reliability_flags_to_env_dict(flags: ReliabilityFeatureFlags) -> dict[str, str]:
    """
    Serialise *flags* into a ``dict`` of environment variable strings.

    The returned dict uses the canonical ``RELIABILITY_*`` key names and
    lowercase ``"true"`` / ``"false"`` values.  The result can be round-
    tripped back through :func:`load_reliability_flags_from_mapping`.

    Args:
        flags: A ``ReliabilityFeatureFlags`` instance.

    Returns:
        ``dict[str, str]`` with six entries — one per flag.

    Examples::

        flags = get_default_reliability_flags()
        d = reliability_flags_to_env_dict(flags)
        assert d["RELIABILITY_ENABLED"] == "false"
        assert d["RELIABILITY_DRY_RUN"] == "true"

        # Roundtrip
        restored = load_reliability_flags_from_mapping(d)
        assert restored == flags
    """
    return {
        _ENV_RELIABILITY_ENABLED: str(flags.reliability_enabled).lower(),
        _ENV_DRY_RUN: str(flags.dry_run).lower(),
        _ENV_BLOCK_ON_VALIDATION_ERROR: str(flags.block_on_validation_error).lower(),
        _ENV_SHOW_UI_TRACE: str(flags.show_ui_trace).lower(),
        _ENV_USE_CONSTRAINED_PROMPTS: str(flags.use_constrained_prompts).lower(),
        _ENV_ENABLE_REPAIR_PROMPT: str(flags.enable_repair_prompt).lower(),
    }


# ---------------------------------------------------------------------------
# Human-readable summary
# ---------------------------------------------------------------------------

def describe_reliability_config(flags: ReliabilityFeatureFlags) -> str:
    """
    Return a short human-readable description of the given flag set.

    The description is intended for logging, debug output, and
    documentation.  It does not imply that the live app has changed —
    the reliability layer must be explicitly wired into the workflow
    (Phase 2B+) before any app behaviour changes.

    Args:
        flags: A ``ReliabilityFeatureFlags`` instance.

    Returns:
        A multi-line string summarising the flag states and any
        warnings from :func:`validate_flag_combination`.

    Examples::

        flags = get_default_reliability_flags()
        print(describe_reliability_config(flags))
        # Reliability config summary
        # --------------------------
        # reliability_enabled       : False  (master switch — layer inactive)
        # ...
    """
    enabled = flags.reliability_enabled
    enabled_label = "True  (layer active)" if enabled else "False (master switch — layer inactive)"

    dry_run_label: str
    if not enabled:
        dry_run_label = f"{flags.dry_run}  (no effect while disabled)"
    elif flags.dry_run:
        dry_run_label = "True  (artifacts only — user-facing output unchanged)"
    else:
        dry_run_label = "False (strict mode — output may be altered)"

    block_label: str
    if not enabled:
        block_label = f"{flags.block_on_validation_error}  (no effect while disabled)"
    elif flags.dry_run:
        block_label = f"{flags.block_on_validation_error}  (overridden by dry_run — never blocks)"
    else:
        block_label = str(flags.block_on_validation_error)

    constrained_label: str
    if not enabled:
        constrained_label = f"{flags.use_constrained_prompts}  (no effect while disabled)"
    else:
        constrained_label = str(flags.use_constrained_prompts)

    repair_label: str
    if not enabled:
        repair_label = f"{flags.enable_repair_prompt}  (no effect while disabled)"
    elif not flags.use_constrained_prompts:
        repair_label = f"{flags.enable_repair_prompt}  (limited effect without constrained prompts)"
    else:
        repair_label = str(flags.enable_repair_prompt)

    ui_trace_label: str
    if not enabled:
        ui_trace_label = f"{flags.show_ui_trace}  (no effect while disabled)"
    else:
        ui_trace_label = str(flags.show_ui_trace)

    lines = [
        "Reliability config summary",
        "-" * 42,
        f"  reliability_enabled          : {enabled_label}",
        f"  dry_run                      : {dry_run_label}",
        f"  block_on_validation_error    : {block_label}",
        f"  use_constrained_prompts      : {constrained_label}",
        f"  enable_repair_prompt         : {repair_label}",
        f"  show_ui_trace                : {ui_trace_label}",
    ]

    warnings = validate_flag_combination(flags)
    if warnings:
        lines.append("")
        lines.append("  Warnings:")
        for w in warnings:
            lines.append(f"    ! {w}")
    else:
        lines.append("")
        lines.append("  No flag combination warnings.")

    lines.append("")
    if not enabled:
        lines.append(
            "  Note: Reliability layer is inactive. "
            "Live app behavior is completely unchanged."
        )
    else:
        lines.append(
            "  Note: Reliability flags are configured but the layer is not yet wired "
            "into the live workflow (Phase 2B+). Live app behavior is unchanged."
        )

    return "\n".join(lines)
