"""lib/cockpit_hydration.py — Investment Cockpit cold-start hydration.

On app restart the Streamlit ``session_state`` is empty, so the Cockpit (page 7)
renders "not loaded" placeholders until the user clicks *Refresh All*. This module
provides a single, **Streamlit-free** function that re-reads the most recent daily
opportunity snapshot from disk and populates the Section A (macro regime +
fragility) and Section C (opportunity cards) session-state keys so the user sees
the last persisted view immediately, behind a clearly-labelled snapshot banner.

Design constraints (mirrors the project's reliability discipline):

* **Pure reader.** It computes nothing live — it only re-reads the audit snapshot
  via the injected ``load_meta`` / ``load_opportunities`` loaders (defaulting to
  :mod:`lib.audit_query`, itself a no-network snapshot reader).
* **Fail-closed.** Any failure (missing file, parse error, ``KeyError``) silently
  skips hydration and leaves ``session_state`` untouched — the page then renders
  its existing placeholders. No exception ever propagates to the caller.
* **At most once per session.** Hydration runs only when neither
  ``macro_regime_result`` nor the ``cockpit_hydrated_from_snapshot`` flag is
  present, so a later manual refresh (which sets ``macro_regime_result``) and a
  second call within the same session are both no-ops.
* **No Streamlit import.** ``session_state`` is passed in (a ``dict`` in tests,
  ``st.session_state`` in the page) so the logic is unit-testable directly,
  without ``AppTest`` and without a Streamlit runtime.

The banner itself is rendered by the page (it needs ``st.info`` / ``bi``); this
function returns the snapshot date string on success so the caller knows to show
it, or ``None`` when nothing was hydrated.
"""

from __future__ import annotations

from typing import Callable, Optional

# Flat fragility-snapshot keys (mirror lib.market_internals.fragility_snapshot).
# The fragility snapshot is merged flat into each day's ``_meta`` header, so we
# rebuild ``cockpit_fragility`` by lifting exactly these keys back out of
# ``MetaRecord.raw``. Section A's internals line reads a subset of them; carrying
# the full set keeps the hydrated reading faithful to what the refresh wrote.
_FRAGILITY_SNAPSHOT_KEYS = (
    "date",
    "fragility_level",
    "fragility_raw_level",
    "fragility_points",
    "fragility_triggered",
    "fragility_consecutive_raw",
    "fragility_degraded",
    "fragility_adjacency_degraded",
    "earnings_degrade_reason",
    "hysteresis_source",
    "rolling_window",
    "data_vintage",
    "vintage_mismatch",
    "distribution_days_spy",
    "distribution_days_qqq",
    "breadth_above_sma20",
    "breadth_above_sma50",
    "breadth_above_sma20_prev",
    "breadth_slope",
    "leading_theme_breadth_narrowing",
    "leading_theme_volume_shrinking",
    "good_news_sold",
    "earnings_evaluated",
    "earnings_skipped",
    "weak_bounce",
    "offense_defense_direction",
    "offense_defense_magnitude",
)


def _default_load_meta():
    from lib.audit_query import load_all_meta
    return load_all_meta()


def _default_load_opportunities():
    from lib.audit_query import load_all_opportunities
    return load_all_opportunities()


def hydrate_cockpit_from_snapshot(
    session_state,
    load_meta: Optional[Callable[[], list]] = None,
    load_opportunities: Optional[Callable[[], list]] = None,
) -> Optional[str]:
    """Populate Cockpit Sections A & C from the latest daily snapshot.

    Parameters
    ----------
    session_state:
        A mutable mapping (``st.session_state`` in the page, a plain ``dict`` in
        tests). Mutated in place ONLY on a fully successful hydration.
    load_meta:
        Returns the full ``MetaRecord`` history sorted ascending by date.
        Defaults to ``lib.audit_query.load_all_meta``.
    load_opportunities:
        Returns all ``OpportunityRecord`` rows across all days. Defaults to
        ``lib.audit_query.load_all_opportunities``.

    Returns
    -------
    The snapshot date string (``meta.date``) when hydration ran and succeeded —
    the caller shows the snapshot banner for this date. ``None`` when there was no
    snapshot to load, hydration had already run, or any error occurred (in which
    case ``session_state`` is left unchanged).
    """
    try:
        # Cold-start gate: never hydrate over a live refresh result, and run at
        # most once per session (the flag survives even if the user later clears
        # individual keys). Either key present → no-op.
        if "macro_regime_result" in session_state:
            return None
        if "cockpit_hydrated_from_snapshot" in session_state:
            return None

        load_meta = load_meta or _default_load_meta
        load_opportunities = load_opportunities or _default_load_opportunities

        metas = load_meta() or []
        if not metas:
            # No snapshot on disk → nothing to hydrate, no banner, no error.
            return None
        # load_all_meta sorts ascending by date, so the last entry is most recent.
        meta = metas[-1]
        snap_date = meta.date

        # --- Section A: macro regime result ---------------------------------
        # Stored as a plain dict so Section A's get_regime_field() (via the
        # macro_state boundary) reads it consistently. NOTE: deliberately NOT
        # routed through save_regime_to_state() — that serializer strips any
        # non-canonical field, and we keep ``fragility_level`` on the dict for
        # faithful reconstruction. (Section A reads fragility from
        # ``cockpit_fragility`` below, not from here, so the extra key is benign.)
        raw_meta = meta.raw or {}
        macro_regime_result = {
            "regime": meta.macro_regime,
            "confidence": meta.confidence,
            "key_signals": list(meta.key_signals or []),
            "opportunity_posture": meta.opportunity_posture,
            "horizon_bias": dict(raw_meta.get("horizon_bias", {}) or {}),
            "fragility_level": meta.fragility_level,
        }

        # --- Section A: fragility snapshot ----------------------------------
        # Rebuild only when the snapshot actually carried fragility (older files
        # predate it). Lift the flat fragility keys back out of the _meta header.
        cockpit_fragility = None
        if "fragility_level" in raw_meta:
            cockpit_fragility = {
                k: raw_meta[k] for k in _FRAGILITY_SNAPSHOT_KEYS if k in raw_meta
            }

        # --- Section C: opportunity cards for the latest date only ----------
        opps = load_opportunities() or []
        cards: list = []
        for rec in opps:
            if getattr(rec, "date", None) != snap_date:
                continue  # latest date only — never mix older days
            card = dict(getattr(rec, "raw", {}) or {})
            # ``why_now`` is persisted as reason-CODE strings, but Section C
            # iterates it as dicts (``r.get("text_..")``). Drop non-dict elements
            # so the render never raises on a string and NO placeholder text is
            # injected — the card simply shows no why-now line (graceful fallback;
            # the LLM-polished sentence was never persisted either).
            card["why_now"] = [r for r in card.get("why_now", []) if isinstance(r, dict)]
            cards.append(card)

        # --- Commit (atomic): mutate session_state only after all built OK ---
        session_state["macro_regime_result"] = macro_regime_result
        if cockpit_fragility is not None:
            session_state["cockpit_fragility"] = cockpit_fragility
        session_state["cockpit_opportunities"] = cards
        # Flag (also the once-per-session guard) + header timestamp.
        session_state["cockpit_hydrated_from_snapshot"] = snap_date
        session_state["cockpit_last_refresh"] = snap_date
        return snap_date
    except Exception:  # noqa: BLE001 — fail-closed; render placeholders, no banner
        return None
