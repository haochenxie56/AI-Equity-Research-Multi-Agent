#!/usr/bin/env python3
"""
scripts/test_reliability_phase_6c_trading_desk.py

Phase 6C-A — Trading Desk test suite (mock-only / offline).

This test runs **entirely without real API calls**. ANTHROPIC_API_KEY and
FINNHUB_API_KEY are forced empty, the yfinance/technical fetches are patched or
fail-closed, and the news/EPS/order LLM paths are never invoked with a real key —
so every computation exercises the deterministic / fail-closed branches.

It verifies:
  * lib/holdings.py, lib/thesis_monitor.py, lib/order_advisor.py import cleanly.
  * HoldingRecord / ThesisCheckResult / PriceLevelResult / OrderRecommendation
    expose all required fields.
  * thesis_status: broken on technical_breakdown alone; broken on
    news_sentiment="negative" AND thesis_relevant=True; intact with no flags.
  * is_normal_pullback distinguishes a pullback (below cost, above SMA200,
    RSI 35-50) from a thesis break.
  * Kelly-lite position_size_pct is clamped to 2%-10%.
  * risk_reward_ratio is computed correctly from the price levels.
  * load_holdings returns [] when the file is absent (no raise).
  * save_holdings returns False on a write failure (no raise).
  * run_thesis_monitor is callable with mocked dependencies.
  * pages/9_Trading_Desk.py is registered in the ui_utils sidebar.
  * No approved_for_execution=True in any created/modified file.
  * No broker/order/execution CAPABILITY tokens in any created/modified file.
  * data/holdings.json is the persistence path and the page never writes it.

Usage:
    python3 -B scripts/test_reliability_phase_6c_trading_desk.py
"""

from __future__ import annotations

import dataclasses
import importlib
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

# Force a keyless / offline environment BEFORE importing the libs.
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ["FINNHUB_API_KEY"] = ""

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


PASS = 0
FAIL = 0
_failures: list[str] = []


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


HOLDINGS_PATH = os.path.join(_REPO_ROOT, "lib", "holdings.py")
THESIS_PATH = os.path.join(_REPO_ROOT, "lib", "thesis_monitor.py")
ORDER_PATH = os.path.join(_REPO_ROOT, "lib", "order_advisor.py")
PAGE_PATH = os.path.join(_REPO_ROOT, "pages", "9_Trading_Desk.py")
UI_UTILS_PATH = os.path.join(_REPO_ROOT, "ui_utils.py")

_HOLD_SRC = _read(HOLDINGS_PATH)
_THESIS_SRC = _read(THESIS_PATH)
_ORDER_SRC = _read(ORDER_PATH)
_PAGE_SRC = _read(PAGE_PATH)
_UI_SRC = _read(UI_UTILS_PATH)


# ---------------------------------------------------------------------------
# Section 1 — Modules import cleanly
# ---------------------------------------------------------------------------

_hold = _tm = _oa = None
try:
    _hold = importlib.import_module("lib.holdings")
    check("1.1 lib.holdings imports without error", True)
except Exception as exc:  # noqa: BLE001
    check("1.1 lib.holdings imports without error", False, repr(exc))
try:
    _tm = importlib.import_module("lib.thesis_monitor")
    check("1.2 lib.thesis_monitor imports without error", True)
except Exception as exc:  # noqa: BLE001
    check("1.2 lib.thesis_monitor imports without error", False, repr(exc))
try:
    _oa = importlib.import_module("lib.order_advisor")
    check("1.3 lib.order_advisor imports without error", True)
except Exception as exc:  # noqa: BLE001
    check("1.3 lib.order_advisor imports without error", False, repr(exc))


# ---------------------------------------------------------------------------
# Section 2 — Dataclass fields
# ---------------------------------------------------------------------------

_HOLDING_FIELDS = (
    "id", "ticker", "shares", "cost_basis", "entry_date", "horizon",
    "thesis_text", "thesis_source", "thesis_signals", "status", "closed_date",
    "closed_price", "notes",
)
if _hold is not None:
    HR = getattr(_hold, "HoldingRecord", None)
    is_dc = HR is not None and dataclasses.is_dataclass(HR)
    check("2.1 HoldingRecord is a dataclass", is_dc)
    if is_dc:
        present = {f.name for f in dataclasses.fields(HR)}
        for req in _HOLDING_FIELDS:
            check(f"2.2 HoldingRecord has field {req!r}", req in present, detail=str(sorted(present)))

_THESIS_FIELDS = (
    "holding_id", "ticker", "checked_at", "news_sentiment", "thesis_relevant",
    "key_development", "eps_revision_direction", "technical_breakdown",
    "technical_breakdown_reasons", "macro_regime_flag", "macro_regime_note",
    "thesis_status", "price_vs_entry", "is_normal_pullback", "summary",
)
if _tm is not None:
    TCR = getattr(_tm, "ThesisCheckResult", None)
    is_dc = TCR is not None and dataclasses.is_dataclass(TCR)
    check("2.3 ThesisCheckResult is a dataclass", is_dc)
    if is_dc:
        present = {f.name for f in dataclasses.fields(TCR)}
        for req in _THESIS_FIELDS:
            check(f"2.4 ThesisCheckResult has field {req!r}", req in present, detail=str(sorted(present)))

_PRICE_FIELDS = (
    "ticker", "current_price", "entry_zone_low", "entry_zone_high", "stop_loss",
    "target_price", "atr_14", "risk_reward_ratio", "position_size_pct",
    "support_levels", "resistance_levels", "volume_trend", "candlestick_pattern",
    "data_source",
)
if _oa is not None:
    PLR = getattr(_oa, "PriceLevelResult", None)
    is_dc = PLR is not None and dataclasses.is_dataclass(PLR)
    check("2.5 PriceLevelResult is a dataclass", is_dc)
    if is_dc:
        present = {f.name for f in dataclasses.fields(PLR)}
        for req in _PRICE_FIELDS:
            check(f"2.6 PriceLevelResult has field {req!r}", req in present, detail=str(sorted(present)))

    OR = getattr(_oa, "OrderRecommendation", None)
    is_dc = OR is not None and dataclasses.is_dataclass(OR)
    check("2.7 OrderRecommendation is a dataclass", is_dc)
    if is_dc:
        present = {f.name for f in dataclasses.fields(OR)}
        for req in ("holding", "price_levels", "thesis_check", "narrative", "generated_at"):
            check(f"2.8 OrderRecommendation has field {req!r}", req in present, detail=str(sorted(present)))

    ON = getattr(_oa, "OrderNarrative", None)
    check("2.9 OrderNarrative is a dataclass", ON is not None and dataclasses.is_dataclass(ON))


# ---------------------------------------------------------------------------
# Section 3 — thesis_status deterministic rules
# ---------------------------------------------------------------------------

if _tm is not None:
    cts = _tm.compute_thesis_status
    # broken on technical_breakdown alone
    check(
        "3.1 broken when technical_breakdown=True alone",
        cts(news_flag=False, eps_flag=False, technical_breakdown=True,
            macro_regime_flag=False) == "broken",
    )
    # broken on negative + relevant news (no other flags)
    check(
        "3.2 broken when news negative AND thesis_relevant",
        cts(news_flag=True, eps_flag=False, technical_breakdown=False,
            macro_regime_flag=False, news_sentiment="negative",
            thesis_relevant=True) == "broken",
    )
    # intact when no flags
    check(
        "3.3 intact when no flags triggered",
        cts(news_flag=False, eps_flag=False, technical_breakdown=False,
            macro_regime_flag=False) == "intact",
    )
    # watch on exactly 1 (non-decisive) flag
    check(
        "3.4 watch when exactly 1 flag (eps)",
        cts(news_flag=False, eps_flag=True, technical_breakdown=False,
            macro_regime_flag=False) == "watch",
    )
    # weakening on exactly 2 (non-decisive) flags
    check(
        "3.5 weakening when 2 flags (eps + macro)",
        cts(news_flag=False, eps_flag=True, technical_breakdown=False,
            macro_regime_flag=True) == "weakening",
    )


# ---------------------------------------------------------------------------
# Section 4 — technical breakdown vs normal pullback
# ---------------------------------------------------------------------------

if _tm is not None:
    tbs = _tm.technical_breakdown_signal
    # Normal pullback: below cost, above SMA200, RSI 42.
    pull = tbs(
        {"price": 95.0, "SMA_200": 90.0, "RSI_14": 42.0, "ADX": 18.0,
         "above_SMA200": True}, cost_basis=100.0,
    )
    check("4.1 is_normal_pullback True (below cost, above SMA200, RSI 35-50)",
          pull["is_normal_pullback"] is True, detail=str(pull))
    check("4.2 normal pullback is NOT a technical_breakdown",
          pull["technical_breakdown"] is False, detail=str(pull))
    # RSI 38 (still 35-50) → pullback.
    pull2 = tbs({"price": 96.0, "SMA_200": 90.0, "RSI_14": 38.0, "ADX": 12.0,
                 "above_SMA200": True}, cost_basis=100.0)
    check("4.3 is_normal_pullback True at RSI=38", pull2["is_normal_pullback"] is True)
    # Thesis break: below SMA200, oversold RSI.
    brk = tbs({"price": 80.0, "SMA_200": 90.0, "RSI_14": 25.0, "ADX": 35.0,
               "above_SMA200": False}, cost_basis=100.0)
    check("4.4 technical_breakdown True (below SMA200 + RSI<30)",
          brk["technical_breakdown"] is True and not brk["is_normal_pullback"],
          detail=str(brk))
    # price_vs_entry computed.
    check("4.5 price_vs_entry computed (-20% at 80 vs 100)",
          abs(brk["price_vs_entry"] - (-20.0)) < 1e-6, detail=str(brk["price_vs_entry"]))


# ---------------------------------------------------------------------------
# Section 5 — Kelly-lite clamp + risk/reward
# ---------------------------------------------------------------------------

if _oa is not None:
    kelly = _oa.kelly_lite_position_size
    # High R:R → clamps at the 10% ceiling.
    check("5.1 position_size_pct clamped to <= 0.10", kelly(10.0) <= 0.10 + 1e-9,
          detail=str(kelly(10.0)))
    check("5.2 position_size_pct clamped to >= 0.02", kelly(0.3) >= 0.02 - 1e-9,
          detail=str(kelly(0.3)))
    # All sizes within band across a sweep.
    in_band = all(0.02 - 1e-9 <= kelly(rr) <= 0.10 + 1e-9
                  for rr in (-1.0, 0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 50.0))
    check("5.3 position_size_pct always within [0.02, 0.10]", in_band)

    # risk_reward_ratio computed correctly from levels.
    rr = _oa._risk_reward(100.0, 90.0, 130.0)
    check("5.4 risk_reward_ratio = (target-entry)/(entry-stop)", abs(rr - 3.0) < 1e-9,
          detail=str(rr))
    # Non-positive risk → 0.0 (no valid long setup).
    check("5.5 risk_reward_ratio 0.0 when stop >= entry",
          _oa._risk_reward(100.0, 100.0, 130.0) == 0.0)

    # Fixture price levels: rr is internally consistent + size clamped.
    class _H:
        ticker = "MU"
        cost_basis = 100.0
        horizon = "mid"

    with mock.patch("ui_utils.load_ohlcv", return_value=None):
        pl = _oa.compute_price_levels("MU", _H())
    expect_rr = _oa._risk_reward(pl.current_price, pl.stop_loss, pl.target_price)
    check("5.6a compute_price_levels rr matches its own levels",
          abs(pl.risk_reward_ratio - expect_rr) < 1e-6, detail=str(pl))
    check("5.7 compute_price_levels position_size within band",
          0.02 - 1e-9 <= pl.position_size_pct <= 0.10 + 1e-9, detail=str(pl.position_size_pct))
    check("5.8 compute_price_levels fixture fallback when no data",
          pl.data_source == "fixture", detail=pl.data_source)

    # 5.6 — stop_loss is PURELY TECHNICAL (no cost_basis). With the SAME live
    # data (so the same current_price), two DIFFERENT cost bases must produce the
    # SAME stop, and the stop must sit in [0.70, 0.99]×current_price.
    try:
        import pandas as pd
        import numpy as np

        _n = 130
        _idx = pd.date_range("2026-01-01", periods=_n, freq="D")
        _close = pd.Series(np.linspace(80.0, 100.0, _n), index=_idx)
        _df = pd.DataFrame(
            {
                "Open": _close * 0.99,
                "High": _close * 1.02,
                "Low": _close * 0.97,
                "Close": _close,
                "Volume": [1_000_000.0] * _n,
            },
            index=_idx,
        )

        class _H2:
            def __init__(self, cb):
                self.ticker = "MU"
                self.cost_basis = cb
                self.horizon = "mid"

        with mock.patch("ui_utils.load_ohlcv", return_value=_df):
            pl_a = _oa.compute_price_levels("MU", _H2(50.0), thesis_status="intact",
                                            horizon="mid")
            pl_b = _oa.compute_price_levels("MU", _H2(999.0), thesis_status="intact",
                                            horizon="mid")
        check("5.6 stop_loss identical for different cost_basis (no cost_basis dep)",
              abs(pl_a.stop_loss - pl_b.stop_loss) < 1e-9,
              detail=f"{pl_a.stop_loss} vs {pl_b.stop_loss}")
        _cp = pl_a.current_price
        check("5.6b stop_loss within [0.70, 0.99]×current_price",
              _cp * 0.70 - 1e-6 <= pl_a.stop_loss <= _cp * 0.99 + 1e-6,
              detail=f"stop={pl_a.stop_loss} cp={_cp}")
        check("5.6c stop_loss is live (technical) not fixture",
              pl_a.data_source == "live", detail=pl_a.data_source)
    except Exception as exc:  # noqa: BLE001
        check("5.6 stop_loss purely technical", False, repr(exc))


# ---------------------------------------------------------------------------
# Section 6 — Candlestick detection is CODE (no LLM)
# ---------------------------------------------------------------------------

if _oa is not None:
    try:
        import pandas as pd

        def _df(rows):
            return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"])

        # doji: open ≈ close, wide range.
        doji = _df([[10, 11, 9, 10, 100], [10.0, 11.0, 9.0, 10.02, 100]])
        check("6.1 candlestick doji detected", _oa._candlestick_pattern(doji) == "doji",
              detail=_oa._candlestick_pattern(doji))
        # bullish engulfing: prev red, current green engulfs.
        be = _df([[10, 10.2, 9.0, 9.2, 100], [9.0, 11.2, 8.9, 11.0, 100]])
        check("6.2 candlestick bullish_engulfing detected",
              _oa._candlestick_pattern(be) == "bullish_engulfing",
              detail=_oa._candlestick_pattern(be))
        check("6.3 candlestick detection returns a string (no LLM)",
              isinstance(_oa._candlestick_pattern(doji), str))
    except Exception as exc:  # noqa: BLE001
        check("6.1 candlestick detection executes", False, repr(exc))


# ---------------------------------------------------------------------------
# Section 7 — holdings persistence (fail-closed)
# ---------------------------------------------------------------------------

if _hold is not None:
    # load_holdings returns [] when the file is absent (no raise).
    with tempfile.TemporaryDirectory() as td:
        absent = Path(td) / "nope.json"
        with mock.patch.object(_hold, "HOLDINGS_PATH", absent):
            try:
                got = _hold.load_holdings()
                check("7.1 load_holdings returns [] when file absent",
                      got == [], detail=str(got))
            except Exception as exc:  # noqa: BLE001
                check("7.1 load_holdings returns [] when file absent", False, repr(exc))

    # save_holdings returns False on a write failure (no raise).
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "holdings.json"
        with mock.patch.object(_hold, "HOLDINGS_PATH", path), \
                mock.patch.object(_hold, "_DATA_DIR", Path(td)), \
                mock.patch("builtins.open", side_effect=OSError("boom")):
            try:
                ok = _hold.save_holdings([_hold.HoldingRecord(ticker="MU")])
                check("7.2 save_holdings returns False on write failure (no raise)",
                      ok is False, detail=str(ok))
            except Exception as exc:  # noqa: BLE001
                check("7.2 save_holdings returns False on write failure (no raise)", False, repr(exc))

    # Round-trip: add → load → update → close in a temp data dir.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "holdings.json"
        with mock.patch.object(_hold, "HOLDINGS_PATH", path), \
                mock.patch.object(_hold, "_DATA_DIR", Path(td)):
            rec = _hold.HoldingRecord(ticker="MU", shares=10, cost_basis=100.0,
                                      thesis_text="cycle bottom")
            check("7.3 HoldingRecord auto-generates id", bool(rec.id))
            check("7.4 add_holding returns True", _hold.add_holding(rec) is True)
            loaded = _hold.load_holdings()
            check("7.5 load_holdings round-trips the record",
                  len(loaded) == 1 and loaded[0].ticker == "MU", detail=str(loaded))
            check("7.6 get_active_holdings returns the active record",
                  len(_hold.get_active_holdings()) == 1)
            check("7.7 update_holding partial update",
                  _hold.update_holding(rec.id, {"shares": 20}) is True
                  and _hold.load_holdings()[0].shares == 20)
            check("7.8 update_holding unknown id returns False",
                  _hold.update_holding("nope", {"shares": 1}) is False)
            check("7.9 close_holding marks closed",
                  _hold.close_holding(rec.id, 110.0, "2026-06-03") is True
                  and _hold.load_holdings()[0].status == "closed")
            check("7.10 get_active_holdings excludes closed",
                  _hold.get_active_holdings() == [])


# ---------------------------------------------------------------------------
# Section 8 — news_signal + run_thesis_monitor fail-closed / mocked
# ---------------------------------------------------------------------------

if _tm is not None:
    # news_signal fails closed to "unknown" with no Finnhub / LLM key.
    ns = _tm.news_signal("MU", "cycle bottom thesis")
    check("8.1 news_signal fail-closed to unknown (no keys)",
          ns.get("news_sentiment") == "unknown" and ns.get("thesis_relevant") is False,
          detail=str(ns))

    # run_thesis_monitor callable with mocked deps.
    H = _hold.HoldingRecord if _hold is not None else None
    if H is not None:
        holdings = [
            H(ticker="MU", shares=10, cost_basis=100.0, horizon="mid",
              thesis_text="cycle bottom"),
            H(ticker="NVDA", shares=5, cost_basis=120.0, horizon="long",
              thesis_text="AI leader"),
        ]
        import lib.signal_engine as _se
        with mock.patch.object(_tm, "news_signal",
                               return_value={"news_sentiment": "neutral",
                                             "thesis_relevant": False,
                                             "key_development": ""}), \
                mock.patch.object(_se, "_technical_snapshot",
                                  return_value={"price": 95.0, "SMA_200": 90.0,
                                                "RSI_14": 42.0, "ADX": 18.0,
                                                "above_SMA200": True}), \
                mock.patch.object(_se, "fetch_fundamental_signals",
                                  return_value=_se.FundamentalSignals(eps_surprise_trend="improving")):
            try:
                # Clear the in-process result cache so the mock is exercised.
                _tm._RESULT_CACHE.clear()
                results = _tm.run_thesis_monitor(holdings, macro_result={"regime": "risk_on"})
                check("8.2 run_thesis_monitor callable with mocked deps",
                      isinstance(results, list) and len(results) == 2, detail=str(results))
                if results:
                    r0 = results[0]
                    check("8.3 monitor result is a ThesisCheckResult",
                          isinstance(r0, _tm.ThesisCheckResult))
                    check("8.4 mocked pullback → intact + is_normal_pullback",
                          r0.thesis_status == "intact" and r0.is_normal_pullback is True,
                          detail=f"{r0.thesis_status} {r0.is_normal_pullback}")
            except Exception as exc:  # noqa: BLE001
                check("8.2 run_thesis_monitor callable with mocked deps", False, repr(exc))

    # macro regime signal: risk_off flags short/mid, not long.
    check("8.5 macro flags risk_off for mid horizon",
          _tm.macro_regime_signal("risk_off", "mid")["flag"] is True)
    check("8.6 macro does NOT flag long horizon alone",
          _tm.macro_regime_signal("risk_off", "long")["flag"] is False)


# ---------------------------------------------------------------------------
# Section 9 — page registration + translation keys
# ---------------------------------------------------------------------------

check("9.1 pages/9_Trading_Desk.py exists", bool(_PAGE_SRC))
check("9.2 page registered in ui_utils sidebar",
      'st.page_link("pages/9_Trading_Desk.py"' in _UI_SRC)
check("9.3 nav_p9 key present in ui_utils (both languages)",
      _UI_SRC.count('"nav_p9"') >= 2)
check("9.4 td_page_title key present (both languages)",
      _UI_SRC.count('"td_page_title"') >= 2)
# Phase 6C-B restructured the sidebar (Cockpit leads; Trading Desk is the last
# nav entry, after Equity). The original "before Cockpit" expectation is
# superseded; Trading Desk now follows both Equity (nav_p4) and Cockpit (nav_p7).
check("9.5 Trading Desk page registered after Equity (nav_p4) in the sidebar",
      _UI_SRC.find('page_link("pages/9_Trading_Desk.py"')
      > _UI_SRC.find('page_link("pages/4_Equity.py"') > 0)
# Page reads the Scanner hand-off for Section 3.
check("9.6 page consumes cockpit_triple_signals (Section 3)",
      "cockpit_triple_signals" in _PAGE_SRC)
check("9.7 page imports thesis from cockpit_all_signals (Add Position)",
      "cockpit_all_signals" in _PAGE_SRC)


# ---------------------------------------------------------------------------
# Section 10 — guardrails: no execution capability, persistence path
# ---------------------------------------------------------------------------

_ALL_SRCS = {
    "lib/holdings.py": _HOLD_SRC,
    "lib/thesis_monitor.py": _THESIS_SRC,
    "lib/order_advisor.py": _ORDER_SRC,
    "pages/9_Trading_Desk.py": _PAGE_SRC,
}

# No positively-authorized execution flag anywhere.
for name, src in _ALL_SRCS.items():
    bad = ("approved_for_execution=True" in src.replace(" ", "")
           or "approved_for_execution = True" in src)
    check(f"10.1 no approved_for_execution=True in {name}", not bad)

# No broker/order/execution CAPABILITY tokens (executable-order constructs).
# NOTE: the literal word "order" appears legitimately (e.g. "Order
# Recommendations"); the guardrail forbids EXECUTION capability, so we scan for
# the specific constructs that would place / route a real order.
_FORBIDDEN = (
    "place_order", "submit_order", "execute_order", "execute_trade",
    "broker_payload", "order_ticket", "order_payload", "time_in_force",
    "place_trade", "send_order", "route_order",
)
for name, src in _ALL_SRCS.items():
    low = src.lower()
    hits = [tok for tok in _FORBIDDEN if tok in low]
    check(f"10.2 no execution-capability tokens in {name}", not hits, detail=str(hits))

# Persistence is data/holdings.json via lib/holdings.py only.
check("10.3 lib/holdings.py references holdings.json", "holdings.json" in _HOLD_SRC)
check("10.4 lib/holdings.py uses the data/ directory", '"data"' in _HOLD_SRC or "/ \"data\"" in _HOLD_SRC or "parent / \"data\"" in _HOLD_SRC or "_DATA_DIR" in _HOLD_SRC)
check("10.5 page does NOT write holdings.json directly (no file write ops)",
      "json.dump" not in _PAGE_SRC and "HOLDINGS_PATH" not in _PAGE_SRC
      and "open(" not in _PAGE_SRC)
check("10.6 page goes through lib.holdings API (not direct persistence)",
      "from lib.holdings import" in _PAGE_SRC and "save_holdings" not in _PAGE_SRC)
# No DB / vector store.
for name, src in _ALL_SRCS.items():
    low = src.lower()
    bad = any(tok in low for tok in ("sqlite", "psycopg", "chromadb", "pinecone",
                                     "faiss", "import sqlalchemy"))
    check(f"10.7 no DB / vector store in {name}", not bad)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n".join(_failures))
total = PASS + FAIL
print(f"\nPhase 6C-A Trading Desk — {PASS}/{total} checks passed.")
if FAIL:
    print(f"{FAIL} FAILED.")
    sys.exit(1)
print("ALL PASSED.")
