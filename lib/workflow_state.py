"""Global research workflow state management.

State schema:
  status:       "idle" | "running" | "completed"
  current_step: "sector" | "scan" | "equity" | "financial" | "pv" | None
  sector:       str | None   — sector currently under research
  ticker:       str | None   — ticker currently under research
  fork:         bool         — True when user has forked from the workflow
  results:      dict         — keyed by step name, stores step output
  steps:        dict         — per-step {status, summary}
"""

import json
from pathlib import Path
import streamlit as st

_STATE_FILE = Path(__file__).parent.parent / "research" / ".workflow_state.json"

_STEP_NAMES = ["sector", "scan", "equity", "financial", "pv"]


def _default_steps() -> dict:
    return {k: {"status": "pending", "summary": None} for k in _STEP_NAMES}


_DEFAULTS: dict = {
    "status":       "idle",
    "current_step": None,
    "sector":       None,
    "ticker":       None,
    "fork":         False,
    "results":      {k: None for k in _STEP_NAMES},
    "steps":        None,   # filled dynamically
}


def save_state() -> None:
    """Persist current workflow state to JSON file."""
    state = st.session_state.get("research_state", {})
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(json.dumps(state, default=str, indent=2), encoding="utf-8")
    except Exception:
        pass


def load_persisted_state() -> dict | None:
    """Load workflow state from JSON file. Returns None if not found or invalid."""
    try:
        if _STATE_FILE.exists():
            raw = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and "status" in raw:
                return raw
    except Exception:
        pass
    return None


def init_research_state() -> None:
    """Ensure research_state exists in session_state. Loads from file on first call."""
    if "research_state" not in st.session_state:
        persisted = load_persisted_state()
        if persisted:
            # Merge persisted data with current defaults (handles schema evolution)
            state: dict = {
                "status":       persisted.get("status", "idle"),
                "current_step": persisted.get("current_step"),
                "sector":       persisted.get("sector"),
                "ticker":       persisted.get("ticker"),
                "fork":         persisted.get("fork", False),
                "results":      {k: None for k in _STEP_NAMES},
                "steps":        _default_steps(),
            }
            if isinstance(persisted.get("results"), dict):
                state["results"].update(persisted["results"])
            if isinstance(persisted.get("steps"), dict):
                state["steps"].update(persisted["steps"])
        else:
            state = {
                "status":       "idle",
                "current_step": None,
                "sector":       None,
                "ticker":       None,
                "fork":         False,
                "results":      {k: None for k in _STEP_NAMES},
                "steps":        _default_steps(),
            }
        st.session_state["research_state"] = state


def get_state() -> dict:
    init_research_state()
    return st.session_state["research_state"]


def update_state(**kwargs) -> None:
    """Update one or more top-level fields.

    For 'results' and 'steps', pass a dict — its keys are merged (not replaced).
    """
    init_research_state()
    state = st.session_state["research_state"]
    for k, v in kwargs.items():
        if k in ("results", "steps") and isinstance(v, dict):
            state[k].update(v)
        else:
            state[k] = v
    save_state()


def update_step(step: str, status: str, summary: str | None = None) -> None:
    """Update a specific step's status and summary, then persist."""
    init_research_state()
    state = st.session_state["research_state"]
    state["steps"][step] = {"status": status, "summary": summary}
    save_state()


def reset_state() -> None:
    """Reset workflow to idle and clear persisted state."""
    state = get_state()
    state["status"]       = "idle"
    state["current_step"] = None
    state["sector"]       = None
    state["ticker"]       = None
    state["fork"]         = False
    state["results"]      = {k: None for k in _STEP_NAMES}
    state["steps"]        = _default_steps()
    save_state()
