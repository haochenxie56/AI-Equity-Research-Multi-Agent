#!/usr/bin/env python3
"""
scripts/test_reliability_phase_6c_v2_entry_strategy.py

Phase 6C-A v2 — Entry Strategy v3 test suite (mock-only / offline).

Runs entirely WITHOUT real API calls: ANTHROPIC_API_KEY / FINNHUB_API_KEY are
forced empty, and the yfinance / technical / valuation-anchor fetches are patched
so every computation exercises the deterministic / fail-closed branches.

It verifies the horizon-native, scenario-aware entry strategy in
``lib/order_advisor.py`` (SHORT = EMA10+EMA20, MID = SMA50, LONG = SMA200 +
fair_value_anchor), the SHORT-never-average-down rule, the MID/LONG average-down
rules, the fundamental gate, stop-vs-zone sanity, the ``FairValueAnchor`` contract,
and the SHORT time stop in ``lib/thesis_monitor.py``. ``approved_for_execution`` is
asserted to be ``False`` everywhere.

Usage:
    python3 -B scripts/test_reliability_phase_6c_v2_entry_strategy.py
"""

from __future__ import annotations

import dataclasses
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ["FINNHUB_API_KEY"] = ""

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pandas as pd  # noqa: E402

import lib.order_advisor as oa  # noqa: E402
import lib.valuation_anchor as va  # noqa: E402
import lib.thesis_monitor as tm  # noqa: E402
import lib.holdings as holds  # noqa: E402


PASS = 0
FAIL = 0
_failures: list = []


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        d = f"  [{detail}]" if detail else ""
        _failures.append(f"FAIL  {label}{d}")


def _read(path: str) -> str:
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Mock helpers — a controlled snapshot + dummy OHLCV + fixed fair-value anchor.
# ---------------------------------------------------------------------------

def _dummy_df(n: int = 40) -> pd.DataFrame:
    rows = []
    for i in range(n):
        c = 100.0 + (i % 5)
        rows.append([c * 0.99, c * 1.02, c * 0.97, c, 1_000_000.0])
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"])


def _snap(price, *, ema10=None, ema20=None, sma50=None, sma200=None, rsi=None,
          adx=None, vol_ratio=None, nearest_support=None, nearest_resistance=None,
          candle="none", atr=None):
    return {
        "price": price, "EMA_10": ema10, "EMA_20": ema20, "SMA_50": sma50,
        "SMA_200": sma200, "RSI_14": rsi, "ADX": adx,
        "ATR_14": atr if atr is not None else round(price * 0.03, 2),
        "Vol_ratio_20d": vol_ratio,
        "above_SMA200": bool(price > (sma200 or 0)),
        "pct_from_52w_high": -5.0,
        "nearest_support": nearest_support,
        "nearest_resistance": nearest_resistance,
        "candlestick_pattern": candle,
    }


@contextmanager
def _patched(snap: dict, fva: float = 85.0):
    fva_obj = va.FairValueAnchor(ticker="MU", fair_value_anchor=fva,
                                 data_sources=["mock"], data_source="fixture")
    with mock.patch("ui_utils.load_ohlcv", return_value=_dummy_df()), \
            mock.patch("lib.technical.snapshot", return_value=snap), \
            mock.patch("lib.valuation_anchor.compute_fair_value_anchor",
                       return_value=fva_obj):
        yield


class _H:
    """Minimal holding stand-in (shares > 0 => 'add' scenario)."""

    def __init__(self, cost_basis, horizon, shares=10.0):
        self.ticker = "MU"
        self.cost_basis = cost_basis
        self.horizon = horizon
        self.shares = shares


# ---------------------------------------------------------------------------
# Section 1 — PriceLevelResult / FairValueAnchor field contracts
# ---------------------------------------------------------------------------

_PLR_NEW_FIELDS = (
    "ticker", "scenario", "horizon", "current_price", "cost_basis", "ema10",
    "ema20", "sma50", "sma200", "atr_14", "nearest_support", "nearest_resistance",
    "fair_value_anchor", "action", "entry_zone_low", "entry_zone_high",
    "stop_loss_level", "position_sizing", "reason", "missing_conditions",
    "next_trigger", "risk_note", "entry_status", "risk_reward_ratio",
    "data_source", "approved_for_execution",
)
PLR = oa.PriceLevelResult
present = {f.name for f in dataclasses.fields(PLR)}
for fld in _PLR_NEW_FIELDS:
    check(f"1.1 PriceLevelResult has field {fld!r}", fld in present, detail=str(sorted(present)))

_FVA_FIELDS = (
    "ticker", "analyst_target", "analyst_anchor", "relative_anchor",
    "valuation_anchor", "fair_value_anchor", "data_sources", "data_source",
)
present_fva = {f.name for f in dataclasses.fields(va.FairValueAnchor)}
for fld in _FVA_FIELDS:
    check(f"1.2 FairValueAnchor has field {fld!r}", fld in present_fva,
          detail=str(sorted(present_fva)))


# ---------------------------------------------------------------------------
# Section 2 — SHORT initiate (EMA10 + EMA20 + volume gate)
# ---------------------------------------------------------------------------

# 2.1 blocked when EMA10 < EMA20
with _patched(_snap(100.0, ema10=98.0, ema20=100.0, rsi=55.0, vol_ratio=1.5)):
    r = oa.compute_price_levels("MU", None, horizon="short")
check("2.1 SHORT initiate blocked when EMA10<EMA20 (action=wait)", r.action == "wait",
      detail=r.action)
check("2.2 SHORT initiate blocked => entry_zone None", r.entry_zone_low is None,
      detail=str(r.entry_zone_low))
check("2.3 SHORT initiate blocked => missing_conditions populated",
      len(r.missing_conditions) > 0, detail=str(r.missing_conditions))

# 2.4 allowed (enter_or_add_small) when fully confirmed and near support
with _patched(_snap(100.0, ema10=100.0, ema20=99.0, rsi=55.0, vol_ratio=1.5,
                    nearest_support=99.0)):
    r = oa.compute_price_levels("MU", None, horizon="short")
check("2.4 SHORT initiate confirmed => enter_or_add_small",
      r.action == "enter_or_add_small", detail=r.action)
check("2.5 SHORT initiate confirmed => entry_zone present", r.entry_zone_low is not None,
      detail=str(r.entry_zone_low))


# ---------------------------------------------------------------------------
# Section 3 — SHORT add (never average down a loser; no chasing)
# ---------------------------------------------------------------------------

with _patched(_snap(100.0, ema10=100.0, ema20=99.0, rsi=55.0, vol_ratio=1.5,
                    nearest_support=99.0)):
    r = oa.compute_price_levels("MU", _H(110.0, "short"), horizon="short")
check("3.1 SHORT add blocked when price<cost (wait_or_cut)", r.action == "wait_or_cut",
      detail=r.action)
check("3.1b SHORT add scenario detected", r.scenario == "add", detail=r.scenario)

with _patched(_snap(100.0, ema10=100.0, ema20=99.0, rsi=55.0, vol_ratio=1.5,
                    nearest_support=99.0)):
    r = oa.compute_price_levels("MU", _H(80.0, "short"), horizon="short")
check("3.2 SHORT add blocked when price>cost*1.15 (wait)", r.action == "wait",
      detail=r.action)


# ---------------------------------------------------------------------------
# Section 4 — MID initiate (SMA50 + volume state)
# ---------------------------------------------------------------------------

with _patched(_snap(100.0, sma50=96.0, sma200=80.0, rsi=55.0, vol_ratio=1.5)):
    r = oa.compute_price_levels("MU", None, horizon="mid")
check("4.1 MID initiate healthy volume => enter_partial_now",
      r.action == "enter_partial_now", detail=r.action)
check("4.2 MID stop_loss_level < entry_zone_low",
      r.entry_zone_low is not None and r.stop_loss_level < r.entry_zone_low,
      detail=f"stop={r.stop_loss_level} low={r.entry_zone_low}")

with _patched(_snap(100.0, sma50=96.0, sma200=80.0, rsi=82.0, vol_ratio=0.5)):
    r = oa.compute_price_levels("MU", None, horizon="mid")
check("4.3 MID initiate unhealthy volume => wait_for_pullback",
      r.action == "wait_for_pullback", detail=r.action)


# ---------------------------------------------------------------------------
# Section 5 — MID add (average_down_small) + LONG add (average_down / wait)
# ---------------------------------------------------------------------------

with _patched(_snap(100.0, sma50=96.0, sma200=80.0, rsi=55.0, vol_ratio=0.8)):
    r = oa.compute_price_levels("MU", _H(110.0, "mid"), horizon="mid",
                                thesis_status="intact",
                                eps_revision_direction="improving")
check("5.1 MID add average_down_small (price<cost, intact, eps not deteriorating)",
      r.action == "average_down_small", detail=r.action)

with _patched(_snap(100.0, sma200=80.0, rsi=50.0, vol_ratio=0.8)):
    r = oa.compute_price_levels("MU", _H(120.0, "long"), horizon="long",
                                thesis_status="intact")
check("5.2 LONG add average_down (price<cost, thesis intact)",
      r.action == "average_down", detail=r.action)

with _patched(_snap(100.0, sma200=80.0, rsi=50.0, vol_ratio=0.8)):
    r = oa.compute_price_levels("MU", _H(120.0, "long"), horizon="long",
                                thesis_status="weakening")
check("5.3 LONG add wait when thesis_status != intact", r.action == "wait",
      detail=r.action)


# ---------------------------------------------------------------------------
# Section 6 — fundamental gate / stop sanity / risk-reward / approved flag
# ---------------------------------------------------------------------------

with _patched(_snap(100.0, sma50=96.0, sma200=80.0, rsi=55.0, vol_ratio=1.5)):
    r_gate = oa.compute_price_levels("MU", None, horizon="mid",
                                     eps_revision_direction="deteriorating")
check("6.1 fundamental gate (deteriorating EPS) => action wait", r_gate.action == "wait",
      detail=r_gate.action)
check("6.2 fundamental gate => entry_zone None", r_gate.entry_zone_low is None)
check("6.3 risk_reward_ratio == 0.0 when entry_zone None",
      r_gate.risk_reward_ratio == 0.0, detail=str(r_gate.risk_reward_ratio))

with _patched(_snap(100.0, sma50=96.0, sma200=80.0, rsi=55.0, vol_ratio=1.5)):
    r_val = oa.compute_price_levels("MU", None, horizon="mid", valuation_percentile=0.85)
check("6.4 fundamental gate (valuation >= 0.70) => wait + entry None",
      r_val.action == "wait" and r_val.entry_zone_low is None, detail=r_val.action)

# stop_loss < entry_zone_low always (or entry None) across a sweep of results.
_sweep_ok = True
_cases = [
    _snap(100.0, sma50=96.0, sma200=80.0, rsi=55.0, vol_ratio=1.5),     # mid healthy
    _snap(100.0, sma50=96.0, sma200=80.0, rsi=60.0, vol_ratio=0.95),    # mid neutral
    _snap(100.0, ema10=100.0, ema20=99.0, rsi=55.0, vol_ratio=1.5, nearest_support=99.0),  # short
    _snap(100.0, sma200=80.0, rsi=50.0, vol_ratio=1.5),                 # long initiate
]
for i, s in enumerate(_cases):
    for hz in ("short", "mid", "long"):
        with _patched(s):
            rr = oa.compute_price_levels("MU", None, horizon=hz)
        if rr.entry_zone_low is not None and rr.stop_loss_level is not None:
            if not (rr.stop_loss_level < rr.entry_zone_low):
                _sweep_ok = False
check("6.5 stop_loss_level < entry_zone_low whenever a zone exists", _sweep_ok)

# approved_for_execution is ALWAYS False on every produced result.
_approved_ok = True
for s in _cases:
    for hz in ("short", "mid", "long"):
        with _patched(s):
            rr = oa.compute_price_levels("MU", _H(100.0, hz), horizon=hz)
            rr2 = oa.compute_price_levels("MU", None, horizon=hz)
        if rr.approved_for_execution or rr2.approved_for_execution:
            _approved_ok = False
check("6.6 approved_for_execution always False on PriceLevelResult", _approved_ok)


# ---------------------------------------------------------------------------
# Section 7 — FairValueAnchor compute (fail-closed, > 0)
# ---------------------------------------------------------------------------

fva = va.compute_fair_value_anchor("MU", 100.0, 0.5)
check("7.1 compute_fair_value_anchor returns FairValueAnchor",
      isinstance(fva, va.FairValueAnchor))
check("7.2 compute_fair_value_anchor fair_value_anchor > 0", fva.fair_value_anchor > 0,
      detail=str(fva.fair_value_anchor))
# Fallback math: all anchors None => current_price * 0.85.
check("7.3 valuation fallback discounts current price",
      fva.fair_value_anchor <= 100.0, detail=str(fva.fair_value_anchor))


# ---------------------------------------------------------------------------
# Section 8 — thesis_monitor SHORT time stop
# ---------------------------------------------------------------------------

_short_hold = holds.HoldingRecord(ticker="MU", shares=10, cost_basis=100.0,
                                  horizon="short", entry_date="2020-01-01")
ts = tm.short_time_stop_signal(_short_hold, 100.0)
check("8.1 SHORT time stop fires after 5+ days without momentum (price<=cost*1.02)",
      ts["flag"] is True, detail=str(ts))
ts_mom = tm.short_time_stop_signal(_short_hold, 130.0)
check("8.2 SHORT time stop does NOT fire when price has momentum", ts_mom["flag"] is False,
      detail=str(ts_mom))
ts_mid = tm.short_time_stop_signal(
    holds.HoldingRecord(ticker="MU", shares=10, cost_basis=100.0, horizon="mid",
                        entry_date="2020-01-01"), 100.0)
check("8.3 time stop only applies to SHORT horizon", ts_mid["flag"] is False,
      detail=str(ts_mid))

# Integration: check_holding sets technical_breakdown + 'time_stop' reason + broken.
import lib.signal_engine as _se  # noqa: E402
with mock.patch.object(tm, "news_signal",
                       return_value={"news_sentiment": "neutral", "thesis_relevant": False,
                                     "key_development": ""}), \
        mock.patch.object(tm, "eps_signal", return_value="improving"), \
        mock.patch.object(_se, "_technical_snapshot",
                          return_value={"price": 100.0, "SMA_200": 90.0, "RSI_14": 45.0,
                                        "ADX": 15.0, "above_SMA200": True}):
    res = tm.check_holding(_short_hold, macro_result={"regime": "risk_on"})
check("8.4 check_holding flags time_stop reason for stalled SHORT",
      "time_stop" in res.technical_breakdown_reasons, detail=str(res.technical_breakdown_reasons))
check("8.5 check_holding technical_breakdown True via time stop",
      res.technical_breakdown is True)
check("8.6 stalled SHORT thesis_status == broken", res.thesis_status == "broken",
      detail=res.thesis_status)


# ---------------------------------------------------------------------------
# Section 9 — guardrails: no approved_for_execution=True in source
# ---------------------------------------------------------------------------

_SRCS = {
    "lib/order_advisor.py": _read(os.path.join(_REPO_ROOT, "lib", "order_advisor.py")),
    "lib/valuation_anchor.py": _read(os.path.join(_REPO_ROOT, "lib", "valuation_anchor.py")),
    "lib/thesis_monitor.py": _read(os.path.join(_REPO_ROOT, "lib", "thesis_monitor.py")),
    "lib/technical.py": _read(os.path.join(_REPO_ROOT, "lib", "technical.py")),
    "pages/9_Trading_Desk.py": _read(os.path.join(_REPO_ROOT, "pages", "9_Trading_Desk.py")),
}
for name, src in _SRCS.items():
    bad = ("approved_for_execution=True" in src.replace(" ", "")
           or "approved_for_execution = True" in src)
    check(f"9.1 no approved_for_execution=True in {name}", not bad)

_FORBIDDEN = ("place_order", "submit_order", "execute_order", "execute_trade",
              "broker_payload", "order_ticket", "order_payload", "time_in_force",
              "place_trade", "send_order", "route_order")
for name, src in _SRCS.items():
    low = src.lower()
    hits = [tok for tok in _FORBIDDEN if tok in low]
    check(f"9.2 no execution-capability tokens in {name}", not hits, detail=str(hits))

# valuation_anchor uses yfinance (free) only — no paid API / DB / vector store.
_va_src = _SRCS["lib/valuation_anchor.py"].lower()
check("9.3 valuation_anchor references yfinance (free source)", "yfinance" in _va_src)
for name, src in _SRCS.items():
    low = src.lower()
    bad = any(tok in low for tok in ("sqlite", "psycopg", "chromadb", "pinecone",
                                     "faiss", "import sqlalchemy"))
    check(f"9.4 no DB / vector store in {name}", not bad)


# ---------------------------------------------------------------------------
# Section 10 — Trading Desk five-fix follow-up
# ---------------------------------------------------------------------------

# 10.1 MID add gap band [cost, cost*1.05): in-the-money below the add band now
# yields an actionable enter_on_pullback zone (NVDA-style: $214 vs $212 cost).
with _patched(_snap(214.0, sma50=210.0, sma200=190.0, rsi=55.0, vol_ratio=1.2)):
    r_gap = oa.compute_price_levels("NVDA", _H(212.0, "mid"), horizon="mid",
                                    thesis_status="intact",
                                    eps_revision_direction="improving")
check("10.1 MID add [cost,cost*1.05) => enter_on_pullback (not bare hold)",
      r_gap.action == "enter_on_pullback", detail=r_gap.action)
check("10.2 MID add gap band produces an entry zone", r_gap.entry_zone_low is not None,
      detail=str(r_gap.entry_zone_low))

# 10.3 OrderNarrative carries bilingual {field}_en / {field}_zh fields.
_on_fields = {f.name for f in dataclasses.fields(oa.OrderNarrative)}
for _f in ("action_reasoning_en", "action_reasoning_zh", "entry_note_en",
           "entry_note_zh", "stop_note_en", "stop_note_zh", "target_note_en",
           "target_note_zh", "risk_warning_en", "risk_warning_zh",
           "next_trigger_note_en", "next_trigger_note_zh"):
    check(f"10.3 OrderNarrative has bilingual field {_f!r}", _f in _on_fields,
          detail=str(sorted(_on_fields)))

# 10.4 cash position persists to data/holdings.json alongside holdings.
with tempfile.TemporaryDirectory() as _td:
    _p = Path(_td) / "holdings.json"
    with mock.patch.object(holds, "HOLDINGS_PATH", _p), \
            mock.patch.object(holds, "_DATA_DIR", Path(_td)):
        check("10.4 load_cash_position default 0.0 when absent",
              holds.load_cash_position() == 0.0)
        check("10.5 save_cash_position returns True", holds.save_cash_position(5000.0) is True)
        check("10.6 load_cash_position round-trips", holds.load_cash_position() == 5000.0,
              detail=str(holds.load_cash_position()))
        holds.add_holding(holds.HoldingRecord(ticker="MU", shares=5, cost_basis=100.0))
        check("10.7 cash preserved across add_holding", holds.load_cash_position() == 5000.0,
              detail=str(holds.load_cash_position()))
        ok = (holds.save_cash_position(7000.0) is True
              and len(holds.load_holdings()) == 1
              and holds.load_cash_position() == 7000.0)
        check("10.8 holdings preserved across save_cash_position", ok)
        # Legacy bare-list file is read as holdings with cash 0.0 (backward compat).
        import json as _json
        with open(_p, "w", encoding="utf-8") as _fh:
            _json.dump([{"ticker": "NVDA", "shares": 1, "cost_basis": 100.0}], _fh)
        check("10.9 legacy list format still loads holdings",
              len(holds.load_holdings()) == 1 and holds.load_cash_position() == 0.0)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n".join(_failures))
total = PASS + FAIL
print(f"\nPhase 6C-A v2 Entry Strategy — {PASS}/{total} checks passed.")
if FAIL:
    print(f"{FAIL} FAILED.")
    sys.exit(1)
print("ALL PASSED.")
