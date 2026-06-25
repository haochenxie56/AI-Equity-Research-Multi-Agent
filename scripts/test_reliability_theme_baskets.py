#!/usr/bin/env python3
"""
scripts/test_reliability_theme_baskets.py

Mock-only test suite for the cross-GICS Market Themes extension
(lib/theme_baskets.py + analyze_theme_basket in lib/llm_orchestrator.py +
the Market Themes tab in pages/2_Sector.py).

This test runs **entirely without real network / API calls**: yfinance is
patched with a deterministic fake price source, so every computation exercises
the live (non-fixture) code paths deterministically. No paid APIs, no broker /
order / execution, no LLM call.

Usage:
    python3 -B scripts/test_reliability_theme_baskets.py
"""

from __future__ import annotations

import dataclasses
import importlib
import os
import sys

import pandas as pd

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


# ── Deterministic fake yfinance ──────────────────────────────────────────────

class _FakeTicker:
    def __init__(self, symbol: str):
        self.symbol = symbol

    def history(self, period: str = "1y"):
        # Per-ticker deterministic upward series so 1M/3M/6M returns are all
        # computable and vary between tickers (drives distinct percentiles).
        seed = sum(ord(c) for c in self.symbol) % 50
        n = 200
        start, end = 100.0, 100.0 * (1.0 + (seed + 1) / 100.0)
        closes = [start + (end - start) * i / (n - 1) for i in range(n)]
        return pd.DataFrame({"Close": closes})


class _FakeYF:
    @staticmethod
    def Ticker(symbol: str):
        return _FakeTicker(symbol)


# ---------------------------------------------------------------------------
# Section 1 — Module imports
# ---------------------------------------------------------------------------

tb = None
try:
    tb = importlib.import_module("lib.theme_baskets")
    check("1.1 lib.theme_baskets importable", True)
except Exception as exc:  # noqa: BLE001
    check("1.1 lib.theme_baskets importable", False, repr(exc))

llm = None
try:
    llm = importlib.import_module("lib.llm_orchestrator")
    check("1.2 lib.llm_orchestrator importable", True)
except Exception as exc:  # noqa: BLE001
    check("1.2 lib.llm_orchestrator importable", False, repr(exc))

# Patch the fake price source for all subsequent live-path computations.
if tb is not None:
    tb.yf = _FakeYF


# ---------------------------------------------------------------------------
# Section 2 — THEME_BASKETS structure (12 themes, required fields)
# ---------------------------------------------------------------------------

_EXPECTED_KEYS = [
    "ai_chips", "semiconductor_mfg", "hbm_memory", "networking_optical",
    "ai_servers_infra", "datacenter_power", "cloud_hyperscaler",
    "data_infrastructure", "ai_software", "cybersecurity", "edge_ai_devices",
    "robotics_autonomous",
]
_REQUIRED_THEME_FIELDS = [
    "label_en", "label_zh", "etf", "constituents",
    "description_en", "description_zh",
]

if tb is not None:
    baskets = tb.THEME_BASKETS
    check("2.1 THEME_BASKETS has exactly 12 themes", len(baskets) == 12,
          f"got {len(baskets)}")
    for k in _EXPECTED_KEYS:
        check(f"2.2 theme key present: {k}", k in baskets)
    for k, cfg in baskets.items():
        for fld in _REQUIRED_THEME_FIELDS:
            check(f"2.3 {k} has field {fld}", fld in cfg)
        check(f"2.4 {k}.constituents non-empty list",
              isinstance(cfg.get("constituents"), list) and len(cfg["constituents"]) > 0)


# ---------------------------------------------------------------------------
# Section 3 — ThemeMomentumResult dataclass required fields
# ---------------------------------------------------------------------------

_REQUIRED_RESULT_FIELDS = {
    "theme_key", "label_en", "label_zh", "constituents", "etf",
    "return_1m", "return_3m", "return_6m", "momentum_score", "data_source",
}

if tb is not None:
    check("3.1 ThemeMomentumResult is a dataclass",
          dataclasses.is_dataclass(tb.ThemeMomentumResult))
    field_names = {f.name for f in dataclasses.fields(tb.ThemeMomentumResult)}
    missing = _REQUIRED_RESULT_FIELDS - field_names
    check("3.2 ThemeMomentumResult has all required fields", not missing,
          f"missing {missing}")


# ---------------------------------------------------------------------------
# Section 4 — compute_theme_momentum callable (mocked yfinance)
# ---------------------------------------------------------------------------

if tb is not None:
    check("4.1 compute_theme_momentum is callable", callable(tb.compute_theme_momentum))

    # ETF-less theme -> equal_weight
    r_eqw = tb.compute_theme_momentum("ai_chips")
    check("4.2 ETF-less theme returns a ThemeMomentumResult",
          isinstance(r_eqw, tb.ThemeMomentumResult))
    check("4.3 ETF-less theme data_source == equal_weight",
          r_eqw.data_source == "equal_weight", r_eqw.data_source)
    check("4.4 ETF-less theme has a numeric 3M return",
          isinstance(r_eqw.return_3m, (int, float)))

    # ETF theme -> etf
    r_etf = tb.compute_theme_momentum("semiconductor_mfg")
    check("4.5 ETF theme data_source == etf",
          r_etf.data_source == "etf", r_etf.data_source)
    check("4.6 ETF theme carries its etf symbol", r_etf.etf == "SOXX", str(r_etf.etf))


# ---------------------------------------------------------------------------
# Section 5 — compute_all_themes: sorted desc, scores in [0,1], data sources
# ---------------------------------------------------------------------------

all_results = []
if tb is not None:
    all_results = tb.compute_all_themes("3mo")
    check("5.1 compute_all_themes returns a list", isinstance(all_results, list))
    check("5.2 compute_all_themes returns all 12 themes", len(all_results) == 12,
          f"got {len(all_results)}")

    scores = [r.momentum_score for r in all_results]
    check("5.3 momentum_score sorted descending",
          all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1)),
          str(scores))
    check("5.4 every momentum_score in [0.0, 1.0]",
          all(0.0 <= s <= 1.0 for s in scores), str(scores))

    by_key = {r.theme_key: r for r in all_results}
    # Themes with etf=None must use equal_weight; themes with etf set must use etf.
    for k, cfg in tb.THEME_BASKETS.items():
        r = by_key.get(k)
        if r is None:
            check(f"5.5 {k} present in compute_all_themes", False)
            continue
        if cfg["etf"] is None:
            check(f"5.5 {k} (etf=None) uses equal_weight", r.data_source == "equal_weight",
                  r.data_source)
        else:
            check(f"5.6 {k} (etf set) uses etf", r.data_source == "etf", r.data_source)


# ---------------------------------------------------------------------------
# Section 6 — Scanner hand-off sets session_state["theme_universe"] (mock st)
# ---------------------------------------------------------------------------

if tb is not None and all_results:
    fake_session: dict = {}
    top = tb.send_top_theme_to_scanner(all_results, fake_session, "en")
    check("6.1 send_top_theme returns the top theme", top is all_results[0])
    check("6.2 theme_universe set after Send top theme",
          "theme_universe" in fake_session and isinstance(fake_session["theme_universe"], list)
          and len(fake_session["theme_universe"]) > 0)
    check("6.3 theme_universe_label set after Send top theme",
          bool(fake_session.get("theme_universe_label")))
    check("6.4 theme_universe equals top theme constituents (deduped)",
          fake_session["theme_universe"] == list(dict.fromkeys(top.constituents)))

    fake_session2: dict = {}
    all_tickers = tb.send_all_themes_to_scanner(all_results, fake_session2, "en")
    check("6.5 send_all_themes sets theme_universe", "theme_universe" in fake_session2)
    check("6.6 send_all_themes returns deduplicated union (no duplicates)",
          len(all_tickers) == len(set(all_tickers)) and len(all_tickers) > 0)
    # The union must cover every theme's constituents.
    union_expected = set()
    for r in all_results:
        union_expected.update(r.constituents)
    check("6.7 send_all_themes covers all constituents",
          set(all_tickers) == union_expected)


# ---------------------------------------------------------------------------
# Section 7 — analyze_theme_basket exists in llm_orchestrator
# ---------------------------------------------------------------------------

if llm is not None:
    check("7.1 analyze_theme_basket exists", hasattr(llm, "analyze_theme_basket"))
    check("7.2 analyze_theme_basket is callable",
          callable(getattr(llm, "analyze_theme_basket", None)))
    # Calling it with no API key must fail-closed (never raise) and return a dict.
    if hasattr(llm, "analyze_theme_basket") and tb is not None and all_results:
        os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            out = llm.analyze_theme_basket("model_training", all_results[0], "risk_on", "en")
            check("7.3 analyze_theme_basket fail-closed returns dict", isinstance(out, dict))
        except Exception as exc:  # noqa: BLE001
            check("7.3 analyze_theme_basket fail-closed returns dict", False, repr(exc))


# ---------------------------------------------------------------------------
# Section 8 — No execution authorization in any modified file
# ---------------------------------------------------------------------------

# Production / page files touched by this task. The test file itself is excluded
# because it necessarily contains the forbidden literal in its detector strings.
_MODIFIED_FILES = [
    os.path.join(_REPO_ROOT, "lib", "theme_baskets.py"),
    os.path.join(_REPO_ROOT, "lib", "llm_orchestrator.py"),
    os.path.join(_REPO_ROOT, "pages", "2_Sector.py"),
    os.path.join(_REPO_ROOT, "ui_utils.py"),
]
for path in _MODIFIED_FILES:
    src = _read(path)
    low = src.replace(" ", "")
    bad = ("approved_for_execution=True" in low) or ('"approved_for_execution":true' in low.lower())
    check(f"8.x no approved_for_execution=True in {os.path.basename(path)}", not bad)


# ---------------------------------------------------------------------------
# Section 9 — Page wiring sanity (Market Themes tab + hand-off keys)
# ---------------------------------------------------------------------------

_page_src = _read(os.path.join(_REPO_ROOT, "pages", "2_Sector.py"))
check("9.1 page adds a Market Themes tab", 'st.tabs([t("p2_tab_sector"), t("theme_tab")])' in _page_src)
check("9.2 page renders the themes tab", "_render_market_themes(_lang, _dark)" in _page_src)
check("9.3 page wires theme_universe hand-off", 'theme_universe' in _page_src or 'send_top_theme_to_scanner' in _page_src)
check("9.4 existing sector content preserved (rotation signal)", 'classify_rotation_phase' in _page_src)
check("9.5 existing sector content preserved (send to scanner)", 'scanner_pool' in _page_src)

_ui_src = _read(os.path.join(_REPO_ROOT, "ui_utils.py"))
for key in ("theme_tab", "p2_tab_sector", "theme_send_top_btn", "theme_col_score"):
    check(f"9.6 ui_utils has key {key} (EN)", f'"{key}":' in _ui_src)


# ---------------------------------------------------------------------------
# Section TB-CR — per-constituent constituent_rs + label lift
# ---------------------------------------------------------------------------
# Helpers: a deterministic Close Series per symbol (same shape _history_close
# returns) and a benchmark window map, so we can drive compute_theme_momentum's
# enrichment path directly with controlled loaders (NO real network).

def _fake_series(symbol: str):
    """A 200-row deterministic Close Series for ``symbol`` (DataFrame -> Close)."""
    return _FakeTicker(symbol).history()["Close"]


if tb is not None:
    _bench_map = {"QQQ": tb._window_returns(_fake_series("QQQ"))}

    # §TB-CR1 — constituent_rs is populated for at least one theme when
    # compute_all_themes runs with the fake loader (every constituent resolves).
    _cr_any = False
    for _r in (all_results or []):
        _crs = getattr(_r, "constituent_rs", None)
        if isinstance(_crs, dict) and _crs:
            for _tkr, _wd in _crs.items():
                if isinstance(_wd, dict) and ({"1m", "3m", "active"} & set(_wd)):
                    _cr_any = True
                    break
        if _cr_any:
            break
    check("TB-CR1 constituent_rs populated for >=1 theme with 1m/3m/active",
          _cr_any)

    # §TB-CR2 — keys are ticker strings; values are dicts with >=1 of
    # 1m/3m/active as FLOATS; no None values are ever stored.
    _cr2_ok = True
    _cr2_detail = ""
    for _r in (all_results or []):
        _crs = getattr(_r, "constituent_rs", {}) or {}
        for _tkr, _wd in _crs.items():
            if not isinstance(_tkr, str) or not isinstance(_wd, dict):
                _cr2_ok = False
                _cr2_detail = f"{_r.theme_key}:{_tkr!r}"
                break
            if not ({"1m", "3m", "active"} & set(_wd)):
                _cr2_ok = False
                _cr2_detail = f"{_r.theme_key}:{_tkr} no window keys"
                break
            for _wk, _wv in _wd.items():
                if _wv is None or not isinstance(_wv, float):
                    _cr2_ok = False
                    _cr2_detail = f"{_r.theme_key}:{_tkr}:{_wk}={_wv!r}"
                    break
            if not _cr2_ok:
                break
        if not _cr2_ok:
            break
    check("TB-CR2 constituent_rs structure: str keys, float window values, no None",
          _cr2_ok, _cr2_detail)

    # §TB-CR3 — selective-inclusion probe (DISCRIMINATING): drive enrichment with a
    # loader where ONE constituent (NVDA) has a valid close and the rest (incl.
    # INTC) return None. A valid close MUST produce a constituent_rs entry; a None
    # close MUST be excluded. Asserting that EXACTLY the valid ticker appears proves
    # per-ticker filtering and the positive population path — not just an all-empty
    # result (the prior CR3 was empty-in/empty-out and merely duplicated CR4).
    def _loader_nvda_valid_intc_none(sym):
        # ai_chips constituents: NVDA valid; everything else (incl. INTC) -> None.
        return _fake_series("NVDA") if sym == "NVDA" else None

    _r_cr3 = tb.compute_theme_momentum(
        "ai_chips", bench_returns_map=_bench_map,
        close_loader=_loader_nvda_valid_intc_none, active_window="1m")
    _cr3 = _r_cr3.constituent_rs
    check("TB-CR3 valid-close constituent (NVDA) produces an entry",
          isinstance(_cr3, dict) and "NVDA" in _cr3, repr(_cr3))
    check("TB-CR3 None-close constituent (INTC) is excluded",
          isinstance(_cr3, dict) and "INTC" not in _cr3, repr(_cr3))
    check("TB-CR3 NVDA entry has >=1 of 1m/3m/active as float",
          isinstance(_cr3.get("NVDA"), dict)
          and any(isinstance(_cr3["NVDA"].get(_w), float)
                  for _w in ("1m", "3m", "active")),
          repr(_cr3.get("NVDA")))

    # §TB-CR4 — fixture themes (data_source='fixture') never reach enrichment, so
    # constituent_rs stays at its {} default. An ETF-less theme whose loader
    # returns None for ALL constituents takes the used==0 fixture early-return.
    def _loader_all_none(sym):
        return None

    _r_cr4 = tb.compute_theme_momentum(
        "ai_chips", bench_returns_map=_bench_map,
        close_loader=_loader_all_none, active_window="1m")
    check("TB-CR4 total-miss ETF-less theme is fixture",
          _r_cr4.data_source == "fixture", _r_cr4.data_source)
    check("TB-CR4 fixture theme -> constituent_rs == {} (enrichment not reached)",
          _r_cr4.constituent_rs == {}, repr(_r_cr4.constituent_rs))

    # §TB-CR5 — label lift: CLUSTER_LABELS (8) + ROLE_LABELS (7) now live in
    # lib.theme_transmission with {en, zh} on every value.
    try:
        _tt = importlib.import_module("lib.theme_transmission")
        _cl = getattr(_tt, "CLUSTER_LABELS", None)
        _rl = getattr(_tt, "ROLE_LABELS", None)
        check("TB-CR5 CLUSTER_LABELS importable, 8 keys",
              isinstance(_cl, dict) and len(_cl) == 8,
              f"len={len(_cl) if isinstance(_cl, dict) else 'n/a'}")
        check("TB-CR5 ROLE_LABELS importable, 7 keys",
              isinstance(_rl, dict) and len(_rl) == 7,
              f"len={len(_rl) if isinstance(_rl, dict) else 'n/a'}")
        check("TB-CR5 every CLUSTER_LABELS value has en+zh",
              isinstance(_cl, dict) and all(
                  isinstance(v, dict) and "en" in v and "zh" in v
                  for v in _cl.values()))
        check("TB-CR5 every ROLE_LABELS value has en+zh",
              isinstance(_rl, dict) and all(
                  isinstance(v, dict) and "en" in v and "zh" in v
                  for v in _rl.values()))
    except Exception as exc:  # noqa: BLE001
        check("TB-CR5 label lift importable", False, repr(exc))


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
for f in _failures:
    print(f)
print()
print(f"{'='*60}")
print(f"  Theme Baskets test:  {PASS} passed, {FAIL} failed")
print(f"{'='*60}")
sys.exit(1 if FAIL else 0)
