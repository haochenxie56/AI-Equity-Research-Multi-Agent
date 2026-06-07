"""lib/macro_state.py — Phase 6C-B macro-regime session-state boundary.

`lib/macro_regime.py` (the `MacroRegimeResult` dataclass + `classify_regime`) is a
frozen module that must not be modified. This call-layer helper sits *after*
`classify_regime(fetch_all_macro())` and is the SINGLE boundary for putting the
regime into / reading it out of ``st.session_state``.

The regime is always stored as a **plain dict** (never the dataclass) so it
survives cross-page Streamlit session reuse consistently (a dataclass object can
behave inconsistently across page modules / reruns). Every reader uses plain
``dict.get()`` access via :func:`get_regime_field`.

All functions are fail-closed: a missing Streamlit runtime, a malformed regime,
or any unexpected shape never raises.
"""

from __future__ import annotations

from typing import Optional

SESSION_KEY = "macro_regime_result"

# Canonical field set surfaced to consumers (Cockpit Section A, Scanner, Trading
# Desk, thesis monitor). Mirrors MacroRegimeResult without importing it.
_FIELDS = (
    "regime", "confidence", "horizon_bias", "key_signals",
    "opportunity_posture", "data_coverage", "signals",
)


def serialize_regime(regime) -> dict:
    """Convert a ``MacroRegimeResult`` (or an already-dict regime) to a pure dict.

    Fail-closed: missing fields fall back to safe defaults; list/dict fields are
    defensively copied so the stored dict shares no mutable state with the source.
    """
    if isinstance(regime, dict):
        src = regime.get
    else:
        src = lambda k, d=None: getattr(regime, k, d)  # noqa: E731
    try:
        return {
            "regime": src("regime", "unknown") or "unknown",
            "confidence": src("confidence", "") or "",
            "horizon_bias": dict(src("horizon_bias", {}) or {}),
            "key_signals": list(src("key_signals", []) or []),
            "opportunity_posture": src("opportunity_posture", "") or "",
            "data_coverage": src("data_coverage", 0.0),
            "signals": list(src("signals", []) or []),
        }
    except Exception:  # noqa: BLE001 — fail-closed
        return {"regime": "unknown", "confidence": "", "horizon_bias": {},
                "key_signals": [], "opportunity_posture": "", "data_coverage": 0.0,
                "signals": []}


def deserialize_regime(d) -> dict:
    """Return a normalized regime dict from a stored value (no dataclass rebuild).

    Accepts a dict (normalized) or a dataclass / any object exposing the regime
    fields (serialized). Returns a safe-empty dict on ``None`` / unexpected input.
    Compat: a legacy ``MacroRegimeResult`` write (has ``__dataclass_fields__``) is
    auto-serialized so every reader gets a plain dict.
    """
    if d is None:
        return {}
    if isinstance(d, dict):
        # Normalize so every canonical field is present.
        return serialize_regime(d)
    # A stray dataclass / object (e.g. a legacy write) — serialize it to a dict.
    return serialize_regime(d)


def save_regime_to_state(regime) -> None:
    """Write the regime to ``st.session_state[SESSION_KEY]`` as a dict (fail-closed)."""
    try:
        import streamlit as st

        st.session_state[SESSION_KEY] = serialize_regime(regime)
    except Exception:  # noqa: BLE001 — fail-closed (no Streamlit runtime)
        return


def get_regime_dict() -> dict:
    """Return the stored regime as a normalized dict (``{}`` when absent)."""
    try:
        import streamlit as st

        return deserialize_regime(st.session_state.get(SESSION_KEY))
    except Exception:  # noqa: BLE001 — fail-closed
        return {}


def get_regime_field(field: str, default=None):
    """Safely read a single regime field from session_state (fail-closed).

    Reads through :func:`get_regime_dict` so a dict OR a legacy dataclass write is
    normalized to a plain dict before the lookup.
    """
    d = get_regime_dict()
    if not d:
        return default
    return d.get(field, default)


def get_regime_str(default: str = "unknown") -> str:
    """Convenience: the regime label as a string (fail-closed)."""
    val = get_regime_field("regime", default)
    return str(val or default)
