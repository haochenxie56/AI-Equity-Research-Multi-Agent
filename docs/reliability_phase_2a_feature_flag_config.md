# Phase 2A: Feature Flag Config Foundation

**Date**: 2026-05-21
**Status**: Implemented
**Author**: Reliability Refactor — Phase 2A
**Depends on**: Phase 1G (`docs/reliability_phase_1g_feature_flagged_orchestration_design.md`)

---

## A. Purpose

Phase 2A creates a **safe, deterministic configuration layer** for the
reliability feature flags — the first concrete step toward integrating the
reliability orchestration layer into the live research workflow.

Its goal is to answer the following operational questions:

1. How does an operator enable or disable the reliability layer safely?
2. How are flags communicated to the running process (environment variables)?
3. How can the config be inspected and audited at startup?
4. How do we guarantee that a missing or empty environment leaves the app
   completely unchanged?

### What Phase 2A does

- Creates `lib/reliability/config.py` with pure, side-effect-free helpers:
  - `parse_bool()` — strict, explicit boolean parser for env strings.
  - `load_reliability_flags_from_mapping()` — load flags from any mapping.
  - `load_reliability_flags_from_env()` — load flags from `os.environ`.
  - `reliability_flags_to_env_dict()` — serialise flags back to env strings.
  - `describe_reliability_config()` — human-readable flag summary.
- Updates `lib/reliability/__init__.py` to export all new helpers.
- Updates `.env.example` with commented, default-off reliability env vars.
- Creates `scripts/test_reliability_config.py` — isolated, zero-API test suite.
- Creates this design document.

### What Phase 2A does NOT do

- Does **not** modify `app.py`, `pages/*`, `lib/llm_orchestrator.py`, or any
  workflow module.
- Does **not** call the Claude API.
- Does **not** modify any live prompt.
- Does **not** wire reliability into any Streamlit page.
- Does **not** change any computation logic.
- Does **not** activate any reliability code path in the running app.

---

## B. Safe Default-Off Philosophy

Every config helper returns the same safe defaults when called with an empty
mapping or an environment that contains no `RELIABILITY_*` variables:

| Flag | Default | Safe because |
|---|---|---|
| `reliability_enabled` | `False` | Master switch — entire layer inactive |
| `dry_run` | `True` | Even when enabled, output never altered |
| `block_on_validation_error` | `False` | Workflow never blocked by default |
| `show_ui_trace` | `False` | No UI elements ever added by default |
| `use_constrained_prompts` | `False` | Existing prompts unchanged |
| `enable_repair_prompt` | `False` | No LLM retries by default |

An operator must **explicitly set** `RELIABILITY_ENABLED=true` to begin
activating any part of the reliability layer.  A typo, a missing `.env` file,
or a deployment that never sets these variables will always produce the
fully-inert default configuration.

---

## C. Supported Environment Variables

| Variable | Flag | Default |
|---|---|---|
| `RELIABILITY_ENABLED` | `reliability_enabled` | `false` |
| `RELIABILITY_DRY_RUN` | `dry_run` | `true` |
| `RELIABILITY_BLOCK_ON_VALIDATION_ERROR` | `block_on_validation_error` | `false` |
| `RELIABILITY_SHOW_UI_TRACE` | `show_ui_trace` | `false` |
| `RELIABILITY_USE_CONSTRAINED_PROMPTS` | `use_constrained_prompts` | `false` |
| `RELIABILITY_ENABLE_REPAIR_PROMPT` | `enable_repair_prompt` | `false` |

All variables are optional.  Missing variables fall back to their safe defaults.
Unknown variables are silently ignored.

### Setting flags in `.env`

```bash
# Enable dry-run mode (artifacts collected, output unchanged)
RELIABILITY_ENABLED=true
RELIABILITY_DRY_RUN=true
```

**Never enable `RELIABILITY_ENABLED=true` in production until Phase 2B dry-run
monitoring has been validated.**

---

## D. Boolean Parsing Rules

The `parse_bool()` function accepts the following values (case-insensitive,
leading/trailing whitespace stripped):

| Input | Result |
|---|---|
| `True` (Python bool) | `True` |
| `False` (Python bool) | `False` |
| `"1"`, `"true"`, `"yes"`, `"y"`, `"on"` | `True` |
| `"0"`, `"false"`, `"no"`, `"n"`, `"off"` | `False` |
| Any other string | `ValueError` |
| Non-bool, non-str type | `ValueError` |

This design is intentional.  Env vars are string-typed, and many env-loading
libraries silently coerce unexpected values to `False`.  Raising `ValueError`
on unrecognised strings prevents silent misconfiguration.

```python
from lib.reliability.config import parse_bool

parse_bool("true")    # → True
parse_bool("  NO  ")  # → False
parse_bool("maybe")   # → ValueError: Cannot parse value='maybe' as bool. ...
parse_bool(1)         # → ValueError: expected bool or str, got 'int'.
```

---

## E. How Mapping and Environment Loading Works

### `load_reliability_flags_from_mapping(mapping)`

Accepts any `Mapping[str, Any]`.  Unknown keys are ignored.  Each recognised
key is parsed with `parse_bool()`.  Missing keys fall back to safe defaults.
The input mapping is never mutated.

```python
from lib.reliability.config import load_reliability_flags_from_mapping

# All defaults — completely safe
flags = load_reliability_flags_from_mapping({})
assert flags.reliability_enabled is False

# Dry-run mode
flags = load_reliability_flags_from_mapping({
    "RELIABILITY_ENABLED": "true",
    "RELIABILITY_DRY_RUN": "true",
})
assert flags.reliability_enabled is True
assert flags.dry_run is True
```

### `load_reliability_flags_from_env(env=None)`

Reads from `os.environ` when `env=None`, or from a provided mapping (for
testing).  Delegates to `load_reliability_flags_from_mapping()`.

```python
from lib.reliability.config import load_reliability_flags_from_env

# Live process environment
flags = load_reliability_flags_from_env()

# Testable override
flags = load_reliability_flags_from_env({"RELIABILITY_ENABLED": "false"})
assert flags.reliability_enabled is False
```

### `reliability_flags_to_env_dict(flags)`

Serialises a `ReliabilityFeatureFlags` instance into a `dict[str, str]` with
lowercase `"true"` / `"false"` values.  Useful for:
- Logging the current config at process startup.
- Round-tripping flags through env-var injection in tests.
- Generating a `.env` snapshot from a known configuration.

```python
from lib.reliability.config import reliability_flags_to_env_dict
from lib.reliability.orchestration_plan import get_default_reliability_flags

d = reliability_flags_to_env_dict(get_default_reliability_flags())
# {
#   "RELIABILITY_ENABLED": "false",
#   "RELIABILITY_DRY_RUN": "true",
#   "RELIABILITY_BLOCK_ON_VALIDATION_ERROR": "false",
#   "RELIABILITY_SHOW_UI_TRACE": "false",
#   "RELIABILITY_USE_CONSTRAINED_PROMPTS": "false",
#   "RELIABILITY_ENABLE_REPAIR_PROMPT": "false",
# }
```

### `describe_reliability_config(flags)`

Returns a multi-line human-readable string describing all flag states,
contextual annotations (e.g., "overridden by dry_run"), and any warnings
from `validate_flag_combination()`.  Intended for startup logging.

```python
from lib.reliability.config import describe_reliability_config, load_reliability_flags_from_env

flags = load_reliability_flags_from_env()
print(describe_reliability_config(flags))
```

---

## F. Why This Phase Does Not Change App Behavior

`lib/reliability/config.py` follows the same constraints as all Phase 1
modules:

- No Streamlit imports.
- No imports from `lib/llm_orchestrator.py`, `app.py`, or any workflow module.
- No file I/O (beyond what callers do with the returned flags).
- No API calls.
- No side effects on the global interpreter state.

The config helpers return a `ReliabilityFeatureFlags` dataclass.  That
dataclass is currently **not read by any live workflow code**.  The config
layer can be imported and called anywhere without risk of altering app
behaviour.

The live workflow will only begin to read flags in **Phase 2B**, when dry-run
ToolResult collection is wired into one isolated step behind an explicit
`if flags.reliability_enabled:` guard.

---

## G. Relationship to Future Phases

| Phase | Description | Config flag used |
|---|---|---|
| **Phase 2A (this)** | Config helpers; env loading; no behavior change | — |
| **Phase 2B** | Dry-run ToolResult collection for Financial Analysis | `RELIABILITY_ENABLED=true`, `RELIABILITY_DRY_RUN=true` |
| **Phase 2C** | Dry-run ValidationReport persistence for all steps | same |
| **Phase 2D** | Constrained prompt behind flag | + `RELIABILITY_USE_CONSTRAINED_PROMPTS=true` |
| **Phase 2E** | Repair/retry loop | + `RELIABILITY_ENABLE_REPAIR_PROMPT=true` |
| **Phase 2F** | UI evidence trace panel | + `RELIABILITY_SHOW_UI_TRACE=true` |
| **Phase 3** | Critic/debate layer | to be defined |

Each phase gated behind an explicit flag means operators can enable exactly as
much reliability as they have validated, with no risk of accidentally activating
future phases.

---

## H. Flag Safety Invariants (preserved from Phase 1G)

These invariants are enforced by `validate_flag_combination()` and by the
design of `load_reliability_flags_from_mapping()`:

1. **`reliability_enabled=False` (the default)** — guarantees the app behaves
   identically to before Phase 0.
2. **`dry_run=True`** — guarantees user-facing output is never altered, even
   when reliability is enabled.  `block_on_error` is always `False` in dry-run.
3. **`block_on_validation_error=False`** — default prevents any workflow step
   from being blocked by the reliability layer.
4. **`show_ui_trace=False`** — no UI panels appear unless explicitly opted in.
5. **`use_constrained_prompts=False`** — existing prompts remain unchanged.

Risky flag combinations (auto-detected by `validate_flag_combination()`):

| Combination | Risk |
|---|---|
| `block_on_validation_error=True` while `reliability_enabled=False` | No effect; potential confusion |
| `show_ui_trace=True` while `reliability_enabled=False` | No effect |
| `use_constrained_prompts=True` while `reliability_enabled=False` | No effect |
| `enable_repair_prompt=True` without `use_constrained_prompts=True` | Limited effect |
| `dry_run=False` with `block_on_validation_error=True` | Strict mode — may block output |

---

## Appendix: Exported Symbols

```python
from lib.reliability.config import (
    parse_bool,
    load_reliability_flags_from_mapping,
    load_reliability_flags_from_env,
    reliability_flags_to_env_dict,
    describe_reliability_config,
)

# Also available via the package shorthand:
from lib.reliability import (
    parse_bool,
    load_reliability_flags_from_mapping,
    load_reliability_flags_from_env,
    reliability_flags_to_env_dict,
    describe_reliability_config,
)
```

## Appendix: Test Script

```bash
python3 scripts/test_reliability_config.py
```

98 assertions across groups A–P:
- A–F: `parse_bool` coverage (bool passthrough, truthy/falsy strings,
  whitespace/case, invalid string rejection, unsupported type rejection)
- G: Empty mapping → safe defaults
- H: Dry-run enabled mapping
- I: Strict mode mapping
- J: Invalid value raises `ValueError` with descriptive message
- K: Input mapping not mutated
- L: `load_reliability_flags_from_env` with injected mapping
- M: `reliability_flags_to_env_dict` roundtrip (default, dry-run, strict)
- N: `describe_reliability_config` content checks
- O: Integration with `orchestration_plan` helpers
- P: Default / env / mapping all produce fully-inert step plans
