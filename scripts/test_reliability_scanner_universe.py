#!/usr/bin/env python3
"""
scripts/test_reliability_scanner_universe.py

Mock-only test suite for the Scanner universe integration (Phase 6B v2):
the configurable :class:`lib.candidate_generator.UniverseConfig` dataclass,
:func:`lib.candidate_generator.build_universe`, the theme-aware
``generate_candidates`` signature, and the "Universe Configuration" expander
wired into ``pages/3_Scanner.py``.

This test runs **entirely offline** — it never fetches market data, never calls
an LLM, and never hits a paid API. ``build_universe`` is a pure set-union over
hardcoded lists + (mock) ``st.session_state``, so it can be exercised directly.

Usage:
    python3 -B scripts/test_reliability_scanner_universe.py
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import os
import sys

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


# ── Mock streamlit session_state ─────────────────────────────────────────────
# A minimal stand-in so build_universe's session_state reads are deterministic.

class _FakeSessionState(dict):
    pass


class _FakeSt:
    def __init__(self) -> None:
        self.session_state = _FakeSessionState()


# ---------------------------------------------------------------------------
# Section 1 — Module imports
# ---------------------------------------------------------------------------

cg = None
try:
    cg = importlib.import_module("lib.candidate_generator")
    check("1.1 lib.candidate_generator importable", True)
except Exception as exc:  # noqa: BLE001
    check("1.1 lib.candidate_generator importable", False, repr(exc))

tb = None
try:
    tb = importlib.import_module("lib.theme_baskets")
    check("1.2 lib.theme_baskets importable", True)
except Exception as exc:  # noqa: BLE001
    check("1.2 lib.theme_baskets importable", False, repr(exc))


# ---------------------------------------------------------------------------
# Section 2 — UniverseConfig dataclass exists with required fields
# ---------------------------------------------------------------------------

_REQUIRED_CONFIG_FIELDS = {
    "include_sp500_top100", "selected_themes", "manual_tickers", "max_size",
}

if cg is not None:
    check("2.1 UniverseConfig exists", hasattr(cg, "UniverseConfig"))
    if hasattr(cg, "UniverseConfig"):
        UC = cg.UniverseConfig
        check("2.2 UniverseConfig is a dataclass", dataclasses.is_dataclass(UC))
        field_names = {f.name for f in dataclasses.fields(UC)}
        missing = _REQUIRED_CONFIG_FIELDS - field_names
        check("2.3 UniverseConfig has all required fields", not missing,
              f"missing {missing}")
        # Defaults match the contract.
        default = UC()
        check("2.4 include_sp500_top100 defaults True",
              default.include_sp500_top100 is True)
        check("2.5 selected_themes defaults to empty list",
              default.selected_themes == [])
        check("2.6 manual_tickers defaults to empty list",
              default.manual_tickers == [])
        check("2.7 max_size defaults to 150", default.max_size == 150)


# ---------------------------------------------------------------------------
# Section 3 — build_universe behavior (offline; mock session_state)
# ---------------------------------------------------------------------------

if cg is not None and hasattr(cg, "build_universe") and hasattr(cg, "UniverseConfig"):
    UC = cg.UniverseConfig
    _orig_st = cg.st
    try:
        cg.st = _FakeSt()  # empty session_state by default

        check("3.1 build_universe is callable", callable(cg.build_universe))

        # Default config -> S&P 500 anchor, deduped, capped.
        uni_default = cg.build_universe(UC())
        check("3.2 build_universe returns list[str]",
              isinstance(uni_default, list)
              and all(isinstance(s, str) for s in uni_default))
        check("3.3 default universe non-empty (S&P 500 anchor)", len(uni_default) > 0)
        check("3.4 build_universe deduplicates (no duplicate tickers)",
              len(uni_default) == len(set(uni_default)),
              f"{len(uni_default)} vs {len(set(uni_default))}")

        # max_size cap respected.
        uni_capped = cg.build_universe(UC(max_size=50))
        check("3.5 build_universe respects max_size cap (<=50)",
              len(uni_capped) <= 50, str(len(uni_capped)))
        check("3.6 build_universe fills to the cap when oversupplied",
              len(uni_capped) == 50, str(len(uni_capped)))

        # Theme constituents included when selected_themes is non-empty.
        # 'ai_chips' constituents include ARM / ALAB / MCHP / NXPI, which are NOT
        # in SP500_TOP_100 — isolate by turning the S&P anchor off.
        theme_key = "ai_chips"
        theme_constituents = list(tb.THEME_BASKETS[theme_key]["constituents"])
        uni_theme = cg.build_universe(
            UC(include_sp500_top100=False, selected_themes=[theme_key])
        )
        check("3.7 build_universe includes theme constituents",
              all(c.upper() in uni_theme for c in theme_constituents),
              f"theme={theme_constituents} got={uni_theme}")
        check("3.8 theme-only universe excludes S&P anchor when sp500 off",
              "JPM" not in uni_theme, str(uni_theme[:5]))

        # Manual tickers included.
        uni_manual = cg.build_universe(
            UC(include_sp500_top100=False, manual_tickers=["zzzz", "WxYz"])
        )
        check("3.9 build_universe includes manual_tickers (upper-cased)",
              "ZZZZ" in uni_manual and "WXYZ" in uni_manual, str(uni_manual))

        # Deduplication across duplicated manual entries + anchor.
        uni_dup = cg.build_universe(
            UC(manual_tickers=["AAPL", "AAPL", "NVDA", "nvda"])
        )
        check("3.10 duplicate manual + anchor entries deduplicated",
              uni_dup.count("AAPL") == 1 and uni_dup.count("NVDA") == 1,
              f"AAPL={uni_dup.count('AAPL')} NVDA={uni_dup.count('NVDA')}")

        # theme_universe from session_state is included if set.
        cg.st.session_state["theme_universe"] = ["FAKE1", "FAKE2"]
        uni_session = cg.build_universe(UC(include_sp500_top100=False))
        check("3.11 theme_universe session_state tickers are included",
              "FAKE1" in uni_session and "FAKE2" in uni_session, str(uni_session))
        cg.st.session_state.pop("theme_universe", None)
    finally:
        cg.st = _orig_st


# ---------------------------------------------------------------------------
# Section 4 — generate_candidates accepts a UniverseConfig argument
# ---------------------------------------------------------------------------

if cg is not None and hasattr(cg, "generate_candidates"):
    sig = inspect.signature(cg.generate_candidates)
    check("4.1 generate_candidates accepts a 'config' parameter",
          "config" in sig.parameters, str(list(sig.parameters)))
    if "config" in sig.parameters:
        check("4.2 config parameter defaults to None",
              sig.parameters["config"].default is None,
              repr(sig.parameters["config"].default))


# ---------------------------------------------------------------------------
# Section 5 — Scanner page wiring (Universe Configuration expander)
# ---------------------------------------------------------------------------

_SCANNER_SRC = _read(os.path.join(_REPO_ROOT, "pages", "3_Scanner.py"))

check("5.1 Scanner imports UniverseConfig + build_universe",
      "UniverseConfig" in _SCANNER_SRC and "build_universe" in _SCANNER_SRC)
check("5.2 Scanner renders a Universe Configuration expander",
      'st.expander(t("scn_uni_title")' in _SCANNER_SRC)
check("5.3 Scanner has the Include S&P 500 checkbox",
      "scn_uni_sp500" in _SCANNER_SRC and "st.checkbox(" in _SCANNER_SRC)
check("5.4 Scanner has the theme multiselect",
      "scn_uni_themes" in _SCANNER_SRC and "st.multiselect(" in _SCANNER_SRC)
check("5.5 Scanner has the manual-ticker text input",
      "scn_uni_manual" in _SCANNER_SRC and "st.text_input(" in _SCANNER_SRC)
check("5.6 Scanner has the max-size slider (50..300 step 25)",
      "scn_uni_max" in _SCANNER_SRC
      and "min_value=50" in _SCANNER_SRC and "max_value=300" in _SCANNER_SRC
      and "step=25" in _SCANNER_SRC)
check("5.7 Scanner shows live universe size",
      "scn_uni_current" in _SCANNER_SRC and "build_universe(" in _SCANNER_SRC)
check("5.8 Scanner shows the theme pre-load banner + Clear",
      "scn_uni_preloaded" in _SCANNER_SRC and "scn_uni_clear_btn" in _SCANNER_SRC
      and "theme_universe" in _SCANNER_SRC)
check("5.9 Scanner passes a UniverseConfig to generate_candidates",
      "config=_uni_config" in _SCANNER_SRC
      and "UniverseConfig(" in _SCANNER_SRC)


# ---------------------------------------------------------------------------
# Section 6 — ui_utils carries the new universe-config t() keys (EN + ZH)
# ---------------------------------------------------------------------------

_UI_SRC = _read(os.path.join(_REPO_ROOT, "ui_utils.py"))
_NEW_KEYS = [
    "scn_uni_title", "scn_uni_sp500", "scn_uni_themes", "scn_uni_manual",
    "scn_uni_max", "scn_uni_current", "scn_uni_preloaded", "scn_uni_clear_btn",
]
for key in _NEW_KEYS:
    check(f"6.x ui_utils defines {key!r} in both EN and ZH",
          _UI_SRC.count(f'"{key}"') >= 2, detail=str(_UI_SRC.count(f'"{key}"')))


# ---------------------------------------------------------------------------
# Section 7 — No execution authorization in any modified file
# ---------------------------------------------------------------------------

_MODIFIED_FILES = [
    os.path.join(_REPO_ROOT, "lib", "candidate_generator.py"),
    os.path.join(_REPO_ROOT, "pages", "3_Scanner.py"),
    os.path.join(_REPO_ROOT, "ui_utils.py"),
]
_POSITIVE_AUTH_FORMS = [
    "approved_for_execution=true",
    'approved_for_execution":true',
    "approved_for_execution:true",
]
for path in _MODIFIED_FILES:
    src = _read(path)
    low = src.replace(" ", "").lower()
    bad = any(form in low for form in _POSITIVE_AUTH_FORMS)
    check(f"7.x no approved_for_execution=True in {os.path.basename(path)}", not bad)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
for f in _failures:
    print(f)
print()
print(f"{'='*60}")
print(f"  Scanner universe test:  {PASS} passed, {FAIL} failed")
print(f"{'='*60}")
sys.exit(1 if FAIL else 0)
