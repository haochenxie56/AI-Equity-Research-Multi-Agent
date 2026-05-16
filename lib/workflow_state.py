"""Global research workflow state management.

State schema:
  status:       "idle" | "running" | "completed"
  current_step: "sector" | "scan" | "equity" | None
  sector:       str | None   — sector currently under research
  ticker:       str | None   — ticker currently under research
  fork:         bool         — True when user has forked from the workflow
  results:      dict         — keyed by step name, stores agent output
"""

import streamlit as st

_DEFAULTS: dict = {
    "status":       "idle",
    "current_step": None,
    "sector":       None,
    "ticker":       None,
    "fork":         False,
    "results":      {"sector": None, "scan": None, "equity": None},
}


def init_research_state() -> None:
    """Ensure research_state exists in session_state."""
    if "research_state" not in st.session_state:
        state = {k: v for k, v in _DEFAULTS.items()}
        state["results"] = dict(_DEFAULTS["results"])
        st.session_state["research_state"] = state


def get_state() -> dict:
    init_research_state()
    return st.session_state["research_state"]


def update_state(**kwargs) -> None:
    """Update one or more top-level fields.

    For 'results', pass a dict — its keys are merged (not replaced).
    """
    init_research_state()
    state = st.session_state["research_state"]
    for k, v in kwargs.items():
        if k == "results" and isinstance(v, dict):
            state["results"].update(v)
        else:
            state[k] = v


def reset_state() -> None:
    """Reset workflow to idle."""
    state = get_state()
    state.update({k: v for k, v in _DEFAULTS.items() if k != "results"})
    state["results"] = dict(_DEFAULTS["results"])
