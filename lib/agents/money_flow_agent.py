"""
lib/agents/money_flow_agent.py

Phase 8B — MoneyFlowAgent, production implementation.

The second PRODUCTION agent on the Phase 8A framework. It turns two
deterministic money-flow signals — dealer GEX/DEX positioning
(``lib.gex_dex.compute_gex_dex`` over a Massive Options chain) and dark-pool
net flow (``lib.quiver_fetcher.compute_dark_pool_signal``) — into a
horizon-aware, evidence-backed ``AgentOutput`` for the PM layer:

  options chain  ->  compute_gex_dex (deterministic dealer positioning)
  dark pool      ->  compute_dark_pool_signal (deterministic net flow)
                 ->  deterministic confidence metrics (short / mid / long)
                 ->  THREE ToolResults into the EvidenceStore (numeric firewall)
                 ->  constrained Claude prompt -> validated AgentResult
                 ->  AgentOutput (JSONL).

Reliability rules honoured here (mirrors MacroRegimeAgent):
  * Every NUMBER the LLM may cite is computed in code and persisted as evidence
    BEFORE the LLM runs. The three confidence metrics, the GEX/DEX signals, and
    the dark-pool signal are all deterministic — the LLM never invents them.
  * Fully fail-closed: ``run_llm_agent`` already returns a rule-based fallback on
    any Claude/parse error; an OUTER guard here guarantees that nothing
    (fetch faults, validation errors, unexpected exceptions) ever propagates to
    the Cockpit caller.

IMPORT DISCIPLINE: NO ``lib.reliability`` AND NO ``lib.agent_framework`` import
at module-load time. Every such helper (``create_run_context``,
``run_llm_agent``, ``processed_signals_to_tool_result``,
``_fallback_agent_output``) and every data helper (``fetch_options_chain``,
``compute_gex_dex``, ``gex_dex_to_signals``, ``compute_dark_pool_signal``) is
imported lazily inside the function that needs it. Only stdlib is imported at
module level. This keeps the module eager-import-cheap and lets tests patch any
dependency at its source module.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # annotations only — never imported at runtime here
    from lib.agent_framework.agent_output import AgentOutput
    from lib.gex_dex import GexDexResult


_log = logging.getLogger("agents.money_flow_agent")

# Dark-pool signal strength -> mid-horizon confidence. The dark-pool aggregator
# is a multi-day net-flow read, so it anchors the 1-4 week (mid) confidence.
_STRENGTH_MAP = {"strong": 1.0, "moderate": 0.6, "weak": 0.3, "none": 0.0}

# Directional tokens that count as a usable, non-neutral read.
_GEX_DEX_DIRECTIONAL = frozenset({"positive", "negative"})
_DARK_POOL_DIRECTIONAL = frozenset({"bullish", "bearish"})

# Long-horizon rationale (recorded in the confidence ToolResult description and
# emitted in the TR3 payload). GEX/DEX and dark pool are intraday-to-3-week
# signals; they carry no long-horizon information.
_LONG_RATIONALE = (
    "GEX/DEX and dark pool are intraday-to-3-week signals; "
    "not meaningful beyond 1 month"
)

# Every field that must be present in a stored record's supporting_data before
# _load_prior_gex_dex_result will trust it enough to reconstruct a prior
# GexDexResult. A record missing ANY of these is rejected (return None) rather
# than silently defaulting a fabricated prior state into compute_gex_dex().
_REQUIRED_PRIOR_FIELDS = frozenset({
    "ticker", "gex_total", "dex_total", "gex_sign", "dex_sign",
    "call_wall", "put_wall", "squeeze_probability", "squeeze_direction",
    "contracts_used", "degraded",
})


def end_of_today_iso() -> str:
    """Return today's date at 23:59:59 UTC as an ISO datetime string.

    Mirrors ``macro_regime_agent.end_of_today_iso``; defined locally so this
    module pulls in no ``lib.agent_framework`` dependency at import time.
    """
    now = datetime.now(timezone.utc)
    return now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# prior_result loading (fail-closed; never raises)
# ---------------------------------------------------------------------------

def _load_prior_gex_dex_result(
    agent_output_dir: str,
    ticker: str,
) -> "Optional[GexDexResult]":
    """Reconstruct the most-recent prior ``GexDexResult`` for *ticker*.

    Reads the most recent ``MoneyFlowAgent`` AgentOutput JSONL under
    ``<agent_output_dir>/MoneyFlowAgent/<YYYY-MM-DD>.jsonl`` and rebuilds a
    ``GexDexResult`` from the ``supporting_data`` fields that
    ``run_money_flow_agent`` persists (``gex_total``, ``dex_total``,
    ``gex_sign``, ``dex_sign``, ``call_wall``, ``put_wall``,
    ``squeeze_probability``, ``squeeze_direction``, ``contracts_used``,
    ``degraded``). Only ``dex_total`` is functionally consumed downstream
    (``compute_gex_dex`` squeeze condition C); the remaining required dataclass
    fields are filled with neutral defaults.

    Returns ``None`` if no prior output exists, the most recent record for
    *ticker* is missing ANY required field, or any file is unreadable /
    unparseable. An unreadable or invalid-JSON file fails CLOSED (return None
    immediately) rather than falling through to an older — and therefore stale —
    file. Fail-closed — NEVER raises.
    """
    try:
        from lib.gex_dex import GexDexResult

        out_dir = os.path.join(agent_output_dir, "MoneyFlowAgent")
        if not os.path.isdir(out_dir):
            return None

        # Newest date-stamped file first; within a file the last line is newest.
        try:
            files = sorted(
                (f for f in os.listdir(out_dir) if f.endswith(".jsonl")),
                reverse=True,
            )
        except OSError:
            return None

        for fname in files:
            path = os.path.join(out_dir, fname)
            # An unreadable file OR any line that is not valid JSON makes this
            # file untrustworthy: fail closed (return None) instead of skipping
            # to an older file and silently using stale prior state.
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    lines = [ln.strip() for ln in fh if ln.strip()]
                for raw in reversed(lines):
                    rec = json.loads(raw)  # invalid JSON -> raises -> None
                    sd = rec.get("supporting_data") or {}
                    if str(sd.get("ticker", "")) != str(ticker):
                        continue
                    # Most-recent record for this ticker found. EVERY required
                    # field must be present — a missing key would otherwise be
                    # silently defaulted into a fabricated prior state.
                    if not _REQUIRED_PRIOR_FIELDS.issubset(sd.keys()):
                        return None
                    return _reconstruct_gex_dex(GexDexResult, sd, ticker)
            except Exception:  # noqa: BLE001 — unreadable/unparseable -> fail closed
                return None
        return None
    except Exception as exc:  # noqa: BLE001 — never raise from a prior-state read
        _log.warning("_load_prior_gex_dex_result failed: %s", exc)
        return None


def _reconstruct_gex_dex(gex_cls, sd: dict, ticker: str):
    """Rebuild a ``GexDexResult`` from a validated supporting_data dict.

    Caller guarantees every key in ``_REQUIRED_PRIOR_FIELDS`` is present. Only
    ``dex_total`` is functionally consumed downstream (squeeze condition C); the
    remaining required dataclass fields not stored on output are neutral.
    """
    return gex_cls(
        ticker=str(sd.get("ticker", ticker)),
        as_of="",
        underlying_price=0.0,
        gex_total=float(sd.get("gex_total", 0.0) or 0.0),
        gex_sign=str(sd.get("gex_sign", "neutral")),
        gex_call=0.0,
        gex_put=0.0,
        dex_total=float(sd.get("dex_total", 0.0) or 0.0),
        dex_sign=str(sd.get("dex_sign", "neutral")),
        dex_call=0.0,
        dex_put=0.0,
        call_wall=sd.get("call_wall"),
        put_wall=sd.get("put_wall"),
        squeeze_probability=str(sd.get("squeeze_probability", "unknown")),
        squeeze_direction=sd.get("squeeze_direction"),
        contracts_used=int(sd.get("contracts_used", 0) or 0),
        degraded=bool(sd.get("degraded", False)),
    )


# ---------------------------------------------------------------------------
# Deterministic confidence calculations (no LLM)
# ---------------------------------------------------------------------------

def _short_signal_count(gex_result, dark_pool_signal: dict) -> int:
    """Count how many of the three money-flow signals carry a usable direction.

    signal_1: ``gex_sign`` is directional AND the GEX/DEX read is not degraded.
    signal_2: ``dex_sign`` is directional AND the GEX/DEX read is not degraded.
    signal_3: dark-pool ``net_direction`` is bullish/bearish AND not degraded.

    Range: 0 .. 3.
    """
    gex_degraded = bool(getattr(gex_result, "degraded", False))
    signal_1 = (
        getattr(gex_result, "gex_sign", None) in _GEX_DEX_DIRECTIONAL
        and not gex_degraded
    )
    signal_2 = (
        getattr(gex_result, "dex_sign", None) in _GEX_DEX_DIRECTIONAL
        and not gex_degraded
    )
    signal_3 = (
        dark_pool_signal.get("net_direction") in _DARK_POOL_DIRECTIONAL
        and not bool(dark_pool_signal.get("degraded", False))
    )
    return int(signal_1) + int(signal_2) + int(signal_3)


def _compute_short_confidence(gex_result, dark_pool_signal: dict) -> float:
    """Fraction of the three money-flow signals that carry a usable direction.

    ``short_confidence = signals_agree_count / 3``. The short horizon trusts the
    breadth of the live read: how many independent flow signals point somewhere
    rather than collapsing to neutral / degraded.

    Fully degraded (all three neutral / degraded) -> 0.0.

    Range: 0.0 .. 1.0 (rounded to 6 dp).
    """
    return round(_short_signal_count(gex_result, dark_pool_signal) / 3.0, 6)


def _compute_mid_confidence(dark_pool_signal: dict) -> float:
    """Mid-horizon confidence from dark-pool flow strength and direction clarity.

    ``mid_confidence = strength_map[signal_strength]`` when the net direction is
    decisive (bullish / bearish) and the read is not degraded; otherwise 0.0.
    The dark-pool aggregator is a multi-day net-flow read, so it anchors the
    1-4 week horizon.

    ``degraded == True`` OR ``net_direction in ("neutral", "insufficient_data")``
    -> 0.0.

    Range: 0.0 .. 1.0 (rounded to 6 dp).
    """
    if bool(dark_pool_signal.get("degraded", False)):
        return 0.0
    direction_valid = (
        dark_pool_signal.get("net_direction") in _DARK_POOL_DIRECTIONAL
    )
    if not direction_valid:
        return 0.0
    strength = dark_pool_signal.get("signal_strength", "none")
    return round(_STRENGTH_MAP.get(strength, 0.0), 6)


def _compute_long_confidence() -> float:
    """Always 0.0 — see ``_LONG_RATIONALE``.

    GEX/DEX and dark pool are intraday-to-3-week signals; they carry no
    long-horizon information, so the long confidence is structurally zero.
    """
    return 0.0


# ---------------------------------------------------------------------------
# task_instruction builder
# ---------------------------------------------------------------------------

def _build_task_instruction(signals: dict, dark_pool: dict) -> str:
    """Build the dynamic, horizon-aware MoneyFlowAgent task instruction.

    All interpolated context is QUALITATIVE (signs, probability bands,
    directions) — never numeric — so the model is never handed a number to
    echo. The REQUIRED OUTPUT FORMAT block uses 4-space indentation (NOT
    triple-backtick fences, which confuse the JSON extractor in agent_runner).
    """
    gex_sign = signals.get("gex_sign", "neutral")
    dex_sign = signals.get("dex_sign", "neutral")
    squeeze_prob = signals.get("squeeze_probability", "unknown")
    squeeze_dir = signals.get("squeeze_direction") or "none"
    dp_dir = dark_pool.get("net_direction", "neutral")
    dp_strength = dark_pool.get("signal_strength", "none")

    return (
        "You are MoneyFlowAgent. Synthesize dealer GEX/DEX positioning and "
        "dark-pool net flow into actionable trading implications.\n\n"
        f"Current GEX environment: {gex_sign}. DEX direction: {dex_sign}. "
        f"Gamma squeeze probability: {squeeze_prob} (direction: {squeeze_dir}). "
        f"Dark-pool net flow: {dp_dir} (strength: {dp_strength}).\n\n"
        "Based on the evidence packet, provide THREE findings:\n"
        "1. SHORT-TERM (intraday-2 weeks): one-sentence actionable judgment for "
        "ShortTermPM. Cover the GEX environment (positive dampens volatility, "
        "negative amplifies it, neutral pins) and its volatility implication; "
        "the DEX direction and whether dealers add buy- or sell-side support; "
        "agreement or divergence with the dark-pool direction; and the gamma "
        "squeeze status and its direction if probability is mid or high. State "
        "a SPECIFIC actionable implication that NAMES the strategy type (for "
        "example directional long, directional short, sell put spread, sell "
        "call spread, or iron condor) and references the relevant key level "
        "(the call wall or the put wall) from the evidence. A neutral GEX "
        "environment MUST still produce an options-structure strategy (such as "
        "an iron condor or a credit spread between the walls) — never "
        "\"wait and see\".\n"
        "2. MID-TERM (1-4 weeks): one-sentence judgment for MidTermPM. Cover the "
        "dark-pool multi-day flow direction and its strength, and whether the "
        "GEX structure supports or contradicts that flow, with the implication "
        "for 1-4 week positioning.\n"
        "3. LONG-TERM (6-18 months): one-sentence judgment for LongTermPM. "
        "ALWAYS state that money-flow signals are not meaningful beyond one "
        "month and that long-horizon context should defer to MacroRegimeAgent.\n\n"
        "Each finding must cite at least one evidence_id from the packet. No "
        "numeric values in finding text. No dollar signs, percentages, or "
        "metric tokens. Specific strategy names, key-level references, and "
        "directions required — no vague statements.\n\n"
        # REQUIRED OUTPUT FORMAT — concrete fill-in example so the model nests
        # finding-level fields inside findings[] and emits confidence as an
        # object (not a top-level {text, evidence, confidence:float}). Plain
        # (NON-f) string literals: the braces below are literal, never
        # .format() fields. 4-space indentation, NOT triple-backtick fences
        # (fences confuse the JSON extractor in agent_runner).
        "REQUIRED OUTPUT FORMAT — you must respond with ONLY valid JSON\n"
        "matching this exact structure. No prose, no markdown fences.\n\n"
        "    {\n"
        "      \"agent_name\": \"MoneyFlowAgent\",\n"
        "      \"run_id\": \"<use the run_id from the evidence packet header>\",\n"
        "      \"findings\": [\n"
        "        {\n"
        "          \"text\": \"<SHORT-TERM one-sentence judgment — no numbers>\",\n"
        "          \"evidence\": [{\"evidence_id\": \"<id from packet>\", \"excerpt\": \"<brief>\"}]\n"
        "        },\n"
        "        {\n"
        "          \"text\": \"<MID-TERM one-sentence judgment — no numbers>\",\n"
        "          \"evidence\": [{\"evidence_id\": \"<id from packet>\", \"excerpt\": \"<brief>\"}]\n"
        "        },\n"
        "        {\n"
        "          \"text\": \"<LONG-TERM one-sentence judgment — no numbers>\",\n"
        "          \"evidence\": [{\"evidence_id\": \"<id from packet>\", \"excerpt\": \"<brief>\"}]\n"
        "        }\n"
        "      ],\n"
        "      \"confidence\": {\n"
        "        \"level\": \"<high|medium|low>\",\n"
        "        \"rationale\": \"<one sentence explaining confidence level>\",\n"
        "        \"score\": <float between 0.0 and 1.0>\n"
        "      }\n"
        "    }\n\n"
        "Rules:\n"
        "- agent_name must be exactly \"MoneyFlowAgent\"\n"
        "- run_id must be copied verbatim from the evidence packet\n"
        "- findings must be a list, never a flat object\n"
        "- each finding must have \"text\" and \"evidence\" keys\n"
        "- confidence must be an object with level/rationale/score, never a float\n"
        "- evidence_id must be an id from the provided evidence packet\n"
        "- no numeric values in any finding text field"
    )


# ---------------------------------------------------------------------------
# Main production function
# ---------------------------------------------------------------------------

def run_money_flow_agent(
    ticker: str = "SPY",
    *,
    expiry_filter: str = "this_week",
    agent_output_dir: str = "data/agent_outputs",
    snapshot_dir: str = "data/snapshots",
) -> "AgentOutput":
    """Production MoneyFlowAgent — see the module docstring for the pipeline.

    Fetches a Massive Options chain and the Quiver dark-pool signal, computes
    dealer GEX/DEX (chaining last run's snapshot as ``prior_result`` for the
    DEX-trend squeeze condition), derives three deterministic confidences, and
    persists three evidence-backed ToolResults BEFORE the constrained LLM call.

    The entire body is wrapped in an outer fail-closed guard: a fetch fault, a
    Claude failure, or any unexpected error yields a rule-based fallback
    AgentOutput, never a raised exception.
    """
    # supporting_data is referenced by the outer fallback if we fail early.
    supporting_data: dict = {"ticker": ticker}
    run_id: str | None = None

    try:
        # 1. Fetch the options chain (fail-closed inside the fetcher).
        from lib.massive_options_fetcher import fetch_options_chain

        chain = fetch_options_chain(ticker, expiry_filter)

        # 2. Load the prior GexDexResult for the DEX-trend squeeze condition.
        prior_gex_dex = _load_prior_gex_dex_result(agent_output_dir, ticker)

        # 3. Deterministic dealer positioning (chains the prior snapshot).
        from lib.gex_dex import compute_gex_dex, gex_dex_to_signals

        gex_result = compute_gex_dex(
            chain, expiry_filter, prior_result=prior_gex_dex
        )

        # 4. Deterministic dark-pool net flow.
        from lib.quiver_fetcher import compute_dark_pool_signal

        dark_pool = compute_dark_pool_signal(ticker)

        # 5. Deterministic confidences (computed BEFORE any LLM call).
        signals_agree_count = _short_signal_count(gex_result, dark_pool)
        short_conf = _compute_short_confidence(gex_result, dark_pool)
        mid_conf = _compute_mid_confidence(dark_pool)
        long_conf = _compute_long_confidence()
        direction_valid = (
            dark_pool.get("net_direction") in _DARK_POOL_DIRECTIONAL
        )
        strength_used = dark_pool.get("signal_strength", "none")

        # 6. Mint one run_id and reuse it everywhere (store + packet + runner).
        from lib.reliability.run_context import create_run_context

        ctx = create_run_context(ticker=ticker, task="money_flow_agent")
        run_id = ctx.run_id

        # 7. Build THREE evidence-backed ToolResults.
        from lib.agent_framework.world_adapter import (
            processed_signals_to_tool_result,
        )

        gex_signals = gex_dex_to_signals(gex_result)
        tr_gex = processed_signals_to_tool_result(
            gex_signals,
            run_id=run_id,
            tool_name="gex_dex_signals",
            target=ticker,
            metric_group="gex_dex",
            description="GEX/DEX dealer positioning signals",
        )
        tr_dark_pool = processed_signals_to_tool_result(
            dark_pool,
            run_id=run_id,
            tool_name="dark_pool_signal",
            target=ticker,
            metric_group="dark_pool",
            description="Dark pool net flow direction and strength",
        )
        confidence_payload = {
            "short_confidence": short_conf,
            "mid_confidence": mid_conf,
            "long_confidence": long_conf,
            "signals_agree_count": signals_agree_count,
            "direction_valid": direction_valid,
            "strength_used": strength_used,
            "long_rationale": _LONG_RATIONALE,
        }
        tr_confidence = processed_signals_to_tool_result(
            confidence_payload,
            run_id=run_id,
            tool_name="money_flow_confidence",
            target=ticker,
            metric_group="confidence",
            description=(
                "Deterministic confidence scores (computed before LLM). "
                + _LONG_RATIONALE
            ),
        )

        # 8. Dynamic, horizon-aware task instruction.
        task_instruction = _build_task_instruction(gex_signals, dark_pool)

        # 9. supporting_data carried on the AgentOutput. Stores the GexDexResult
        #    fields needed to reconstruct prior_result on the NEXT run.
        supporting_data = {
            "ticker": ticker,
            "gex_total": gex_result.gex_total,
            "dex_total": gex_result.dex_total,
            "gex_sign": gex_result.gex_sign,
            "dex_sign": gex_result.dex_sign,
            "call_wall": gex_result.call_wall,
            "put_wall": gex_result.put_wall,
            "squeeze_probability": gex_result.squeeze_probability,
            "squeeze_direction": gex_result.squeeze_direction,
            "contracts_used": gex_result.contracts_used,
            "degraded": gex_result.degraded,
            "dark_pool_direction": dark_pool["net_direction"],
            "dark_pool_strength": dark_pool["signal_strength"],
            "short_confidence": short_conf,
            "mid_confidence": mid_conf,
            "long_confidence": long_conf,
            "signals_agree_count": signals_agree_count,
        }

        # 10. Run the constrained agent (cross-horizon synthesis; EOD validity).
        from lib.agent_framework.agent_runner import run_llm_agent

        return run_llm_agent(
            agent_id="MoneyFlowAgent",
            horizon="cross",
            task_instruction=task_instruction,
            tool_results=[tr_gex, tr_dark_pool, tr_confidence],
            supporting_data=supporting_data,
            requires_human_confirmation=True,
            judgment_source="llm_proposed",
            valid_until=end_of_today_iso(),
            ticker=ticker,
            max_tokens=1024,
            run_id=run_id,
        )
    except Exception as exc:  # noqa: BLE001 — outer fail-closed guard
        # run_llm_agent is itself fail-closed; this guards everything else
        # (fetch faults, evidence plumbing, unexpected errors) so a failure here
        # NEVER aborts the Cockpit refresh.
        _log.warning("run_money_flow_agent failed; returning fallback: %s", exc)
        from lib.agent_framework.agent_runner import _fallback_agent_output

        return _fallback_agent_output(
            "MoneyFlowAgent",
            "cross",
            supporting_data,
            exc,
            valid_until=end_of_today_iso(),
            run_id=run_id,
            target=ticker,
            ticker=ticker,
        )
