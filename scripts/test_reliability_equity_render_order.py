#!/usr/bin/env python3
"""
scripts/test_reliability_equity_render_order.py

Equity Research page (pages/4_Equity.py) render-order regression test
(mock-only / offline / source-static + runtime call-log via AppTest).

Background — the bug this guards against
----------------------------------------
Streamlit streams element deltas in script-execution order, so a section appears
in the browser only once the line that CREATES it runs. The page must therefore
create EVERY top-level section frame (company header, earnings banner,
key-metrics row, the four analysis tabs, and the AI Valuation Summary) in a
"layout-first" block BEFORE the first blocking call of any kind — load_info,
load_earnings, any yfinance / Finnhub fetch, render_financial_tab /
render_pv_tab, load_news, or compute_app_fair_value. Otherwise, on a cold cache
(first page entry — exactly the acceptance scenario) a frame cannot appear until
the data it sits above has been fetched.

The strong invariant
---------------------
This test runs the page under AppTest with a call log that records BOTH
  * slot creations  — every st.empty() / st.tabs() call, and
  * blocking calls  — every data fetch / heavy render (load_info,
                      load_earnings, load_news, render_financial_tab,
                      render_pv_tab, compute_app_fair_value),
then asserts STRUCTURALLY that the LAST slot creation happens before the FIRST
blocking call:  max(slot_seq) < min(blocking_seq).

Coverage scope (important — no overclaim)
-----------------------------------------
The harness only sees the blocking helpers it explicitly patches. They are
declared in ONE place — the ``_BLOCKING_PATCHES`` registry below — so the set is
easy to read and extend. The structural assertion catches any *registered*
blocking call moved above the layout block, but a brand-new fetch / LLM / heavy
helper introduced on the page is NOT detected until it is added to
``_BLOCKING_PATCHES``. When you add a new blocking helper to pages/4_Equity.py,
add it here too.

Currently registered blocking helpers: load_info, load_earnings, load_news,
translate_to_chinese (Business Description), render_financial_tab, render_pv_tab,
compute_app_fair_value. The Research Report section makes NO blocking call (it is
assembled deterministically from already-fetched data), so only its slot creation
is tracked — its frame appearing before the first blocking call is still asserted.

A cold-cache scenario (st.cache_data cleared before the run) confirms the
creation order is identical when every real cache is empty.

Usage:
    python3 -B scripts/test_reliability_equity_render_order.py
"""

from __future__ import annotations

import os
import sys
import types

os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ["FINNHUB_API_KEY"] = ""

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
if os.path.join(_REPO_ROOT, "lib") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO_ROOT, "lib"))

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


_PAGE_PATH = os.path.join(_REPO_ROOT, "pages", "4_Equity.py")
with open(_PAGE_PATH, "r", encoding="utf-8") as _fh:
    SRC = _fh.read()


# ===========================================================================
# Section 1 — runtime call-log: ALL slot creations precede the FIRST blocking
#             call (the core structural invariant). load_info / load_earnings
#             are tracked, not just the tab-body calls.
# ===========================================================================
def _run_page_and_log(cold_cache: bool) -> tuple[list[tuple[str, str, int]], object]:
    """Run pages/4_Equity.py under AppTest with st.empty/st.tabs and every
    registered blocking helper instrumented. Returns (call_log, app_test).

    call_log entries are (kind, name, seq) where kind is "slot" or "blocking".
    """
    import streamlit
    import ui_utils
    import financial_tab
    import pv_tab
    import lib.equity_valuation as equity_valuation
    from streamlit.testing.v1 import AppTest

    log: list[tuple[str, str, int]] = []
    counter = {"n": 0}

    def _record(kind: str, name: str) -> None:
        counter["n"] += 1
        log.append((kind, name, counter["n"]))

    # ---- slot-creation instrumentation (call the real impl) ----
    _orig_empty = streamlit.empty
    _orig_tabs = streamlit.tabs

    def _empty_wrap(*a, **k):
        _record("slot", "st.empty")
        return _orig_empty(*a, **k)

    def _tabs_wrap(*a, **k):
        _record("slot", "st.tabs")
        return _orig_tabs(*a, **k)

    # ---- blocking-call stubs (never touch the network) ----
    def _info(tk, *a, **k):
        _record("blocking", "load_info")
        # Non-empty business summary so the Business Description fill path runs
        # translate_to_chinese (exercised below via language="zh").
        return {"longName": f"{tk} Inc", "currentPrice": 100.0,
                "regularMarketPreviousClose": 99.0,
                "longBusinessSummary": f"{tk} designs and sells widgets."}

    def _earn(tk, *a, **k):
        _record("blocking", "load_earnings")
        return {}

    def _news(tk, *a, **k):
        _record("blocking", "load_news")
        return []

    def _translate(text, *a, **k):
        _record("blocking", "translate_to_chinese")
        return text

    def _fin(tk, *a, **k):
        _record("blocking", "render_financial_tab")

    def _pv(tk, *a, **k):
        _record("blocking", "render_pv_tab")

    def _fv(tk, price, *a, **k):
        _record("blocking", "compute_app_fair_value")
        # fair_value_mid <= 0 => the expander renders the NA branch only.
        return types.SimpleNamespace(fair_value_mid=0.0)

    # ==== THE single registry of blocking helpers the page may call ==========
    # (module, attribute, stub). This is the ONE place the harness's blocking
    # coverage is defined — to cover a NEW page fetch / LLM / heavy helper, add a
    # row here (and the page must call it through the patched module attribute).
    _BLOCKING_PATCHES = [
        (ui_utils, "load_info", _info),
        (ui_utils, "load_earnings", _earn),
        (ui_utils, "load_news", _news),
        (ui_utils, "translate_to_chinese", _translate),  # Business Description
        (financial_tab, "render_financial_tab", _fin),
        (pv_tab, "render_pv_tab", _pv),
        (equity_valuation, "compute_app_fair_value", _fv),
    ]
    # Chrome no-ops: st.page_link raises inside AppTest (no multi-page context).
    # These are NOT blocking and are NOT logged.
    _CHROME = ["render_sidebar", "apply_theme", "render_workflow_bar", "page_header"]

    _saved: dict = {}
    try:
        streamlit.empty = _empty_wrap
        streamlit.tabs = _tabs_wrap
        for _mod, _attr, _stub in _BLOCKING_PATCHES:
            _saved[(_mod, _attr)] = getattr(_mod, _attr)
            setattr(_mod, _attr, _stub)
        for _attr in _CHROME:
            _saved[(ui_utils, _attr)] = getattr(ui_utils, _attr)
            setattr(ui_utils, _attr, lambda *a, **k: None)

        if cold_cache:
            # Cold cache: drop every memoized value so the very first entry path
            # (the acceptance scenario) is exercised.
            try:
                streamlit.cache_data.clear()
            except Exception:
                pass

        at = AppTest.from_file(_PAGE_PATH, default_timeout=60)
        at.session_state["p4_ticker_input"] = "AAPL"
        # zh exercises the Business Description's translate_to_chinese blocking call.
        at.session_state["language"] = "zh"
        at.run()
        return log, at
    finally:
        streamlit.empty = _orig_empty
        streamlit.tabs = _orig_tabs
        for (_mod, _attr), _val in _saved.items():
            setattr(_mod, _attr, _val)


def _assert_layout_first(prefix: str, log, at) -> None:
    slot_seqs = [seq for (kind, _n, seq) in log if kind == "slot"]
    block_seqs = [seq for (kind, _n, seq) in log if kind == "blocking"]
    names_block = [n for (kind, n, _s) in log if kind == "blocking"]
    n_empty = sum(1 for (k, n, _s) in log if k == "slot" and n == "st.empty")

    check(f"{prefix} page renders without exception", not at.exception,
          str(at.exception))
    check(f"{prefix} at least one section slot created", len(slot_seqs) > 0,
          f"slots={len(slot_seqs)}")
    check(f"{prefix} at least one blocking call recorded", len(block_seqs) > 0,
          f"blocks={len(block_seqs)}")
    # The core invariant: every slot creation precedes the FIRST blocking call.
    last_slot = max(slot_seqs) if slot_seqs else -1
    first_block = min(block_seqs) if block_seqs else 10 ** 9
    check(f"{prefix} ALL section slots created before the FIRST blocking call",
          last_slot < first_block,
          f"last_slot_seq={last_slot} first_block_seq={first_block} order={[ (k,n) for (k,n,_s) in log ]}")
    # The six st.empty section slots — header / earnings / metrics / business
    # description / research report / AI valuation — are all created up front.
    check(f"{prefix} >= 6 st.empty section slots created (incl. biz + report)",
          n_empty >= 6, f"n_empty={n_empty}")
    # Every registered blocking call that actually fired must come after the
    # layout block. (Structural: each first-occurrence seq > last slot seq.)
    for _name in ("load_info", "load_earnings", "translate_to_chinese"):
        _first = min((s for (k, n, s) in log if n == _name), default=None)
        check(f"{prefix} {_name} fired as a blocking call after the layout block",
              _first is not None and _first > last_slot,
              f"first={_first} last_slot={last_slot} names_block={names_block}")


try:
    _log_warm, _at_warm = _run_page_and_log(cold_cache=False)
    _assert_layout_first("1.x [warm]", _log_warm, _at_warm)

    # 1.y — the AI Valuation Summary frame is present in the rendered output.
    _labels = [(e.label or "") for e in _at_warm.get("expander")]
    check("1.y AI Valuation Summary expander present in rendered output",
          any("Valuation" in lbl or "估值" in lbl for lbl in _labels),
          f"labels={_labels[:4]}")

    # 1.z — the two newly slotted sections are present in the rendered output
    # (Business Description expander + Research Report subheader). Labels are
    # taken from the real zh translation table, matching language="zh".
    import ui_utils as _uiu
    _zh = _uiu.TRANSLATIONS["zh"]
    _biz_zh = _zh.get("p4_biz", "")
    _report_zh = _zh.get("p4_report", "")
    _sub_vals = [getattr(s, "value", "") for s in _at_warm.get("subheader")]
    check("1.z1 Business Description expander present in rendered output",
          bool(_biz_zh) and _biz_zh in _labels, f"biz={_biz_zh!r} labels={_labels}")
    check("1.z2 Research Report subheader present in rendered output",
          bool(_report_zh) and _report_zh in _sub_vals,
          f"report={_report_zh!r} subs={_sub_vals}")
except Exception as exc:  # AppTest/runtime failure — report, don't crash suite
    check("1.x runtime render-order harness (warm)", False, repr(exc))

# ===========================================================================
# Section 2 — cold-cache scenario: order unchanged with caches cleared.
# ===========================================================================
try:
    _log_cold, _at_cold = _run_page_and_log(cold_cache=True)
    _assert_layout_first("2.x [cold]", _log_cold, _at_cold)
except Exception as exc:
    check("2.x runtime render-order harness (cold cache)", False, repr(exc))

# ===========================================================================
# Section 3 — no temporary diagnostic logging left behind.
# ===========================================================================
for _tok in ("_diag(", "equity_page_timing", "TEMP DIAGNOSTIC", "_T0 = _time"):
    check(f"3.x no leftover diagnostic token: {_tok}", _tok not in SRC)

# ===========================================================================
# Section 4 — structural source markers for the layout-first pass + fill.
# ===========================================================================
check("4.1 layout-first banner present", "LAYOUT-FIRST PASS" in SRC)
check("4.2 fill-pass banner present", "FILL PASS" in SRC)
check("4.3 header slot reserved", "header_slot = st.empty()" in SRC)
check("4.4 earnings slot reserved", "earnings_slot = st.empty()" in SRC)
check("4.5 metrics slot reserved", "metrics_slot  = st.empty()" in SRC
      or "metrics_slot = st.empty()" in SRC)
check("4.6 valuation slot reserved", "fv_slot = st.empty()" in SRC)
check("4.7 valuation placeholder painted",
      'st.info("📊 AI Valuation summarizing...")' in SRC)
check("4.8 valuation result fills the reserved slot",
      "fv_slot.container().expander(" in SRC)
# Overview sub-section slots (Task 1).
check("4.11 overview top container reserved", "ov_top_slot = st.container()" in SRC)
check("4.12 business-description slot reserved", "biz_slot = st.empty()" in SRC)
check("4.13 research-report slot reserved", "report_slot = st.empty()" in SRC)
check("4.14 business description fills its reserved slot",
      "with biz_slot.container():" in SRC)
check("4.15 research report fills its reserved slot",
      "with report_slot.container():" in SRC)
check("4.16 moat/peers fill the reserved overview container",
      "with ov_top_slot:" in SRC)
# The shared load AND every Overview sub-slot must be reserved BEFORE the first
# blocking call in source order. Use the FILL-PASS load_info as the boundary.
_idx_fv_slot = SRC.find("fv_slot = st.empty()")
_idx_biz_slot = SRC.find("biz_slot = st.empty()")
_idx_report_slot = SRC.find("report_slot = st.empty()")
_idx_load_info = SRC.find("    info  = load_info(ticker)")
_idx_load_earn = SRC.find("    cal   = load_earnings(ticker)")
check("4.9 load_info(ticker) appears AFTER fv_slot reservation in source",
      0 <= _idx_fv_slot < _idx_load_info,
      f"fv_slot={_idx_fv_slot} load_info={_idx_load_info}")
check("4.10 load_earnings(ticker) appears AFTER fv_slot reservation in source",
      0 <= _idx_fv_slot < _idx_load_earn,
      f"fv_slot={_idx_fv_slot} load_earnings={_idx_load_earn}")
check("4.17 biz_slot + report_slot reserved BEFORE the shared load_info",
      0 <= _idx_biz_slot < _idx_load_info
      and 0 <= _idx_report_slot < _idx_load_info,
      f"biz={_idx_biz_slot} report={_idx_report_slot} load_info={_idx_load_info}")

# ===========================================================================
# Section 5 — functionality / session-state keys preserved (render-only).
# ===========================================================================
check("5.1 Run AI Debate button preserved", 'key=f"fv_debate_{ticker}"' in SRC)
check("5.2 Update Valuation button preserved", 'key=f"fv_update_{ticker}"' in SRC)
check("5.3 Send to Desk button preserved", 'key=f"fv_send_{ticker}"' in SRC)
check("5.4 equity_prefill_ticker hand-off preserved",
      'st.session_state.pop("equity_prefill_ticker"' in SRC)
check("5.5 fair-value session key unchanged", 'f"app_fair_value_{ticker}"' in SRC)
check("5.6 debate session key unchanged", 'f"equity_debate_{ticker}"' in SRC)
check("5.7 bilingual header key used", 't("cockpit_fv_header")' in SRC)
check("5.8 LIVE/FIXTURE badge preserved",
      "td_data_live" in SRC and "td_data_fixture" in SRC)
check("5.9 compute + store helpers still imported",
      "compute_app_fair_value" in SRC and "store_equity_research_result" in SRC)
check("5.10 no approved_for_execution=True in the page",
      "approved_for_execution = True" not in SRC
      and '"approved_for_execution": true' not in SRC)


# ===========================================================================
# Summary
# ===========================================================================
print("\n".join(_failures))
print(f"\n{PASS}/{PASS + FAIL} passed")
sys.exit(1 if FAIL else 0)
