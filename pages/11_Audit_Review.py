"""Page 11 — Audit Review (Phase 7D Block A).

A read-only review of the daily opportunity snapshot audit trail
(``data/snapshots/opportunities_YYYYMMDD.jsonl``). It surfaces snapshot coverage,
the fragility-level history, a per-ticker status timeline, and an early
follow-through analysis of "Actionable Now" signals.

ISOLATION: this page touches ONLY ``lib.audit_query`` + ``ui_utils``. Through
``lib.audit_query`` it reuses the two existing snapshot READ helpers
(``load_ticker_series`` / ``read_recent_meta``) and nothing else — it never calls
the live signal engine, the ranker's scoring path, regime classification, or any
network/data-vendor SDK. It performs no writes. The audit track (snapshot reads)
and the live track (rolling recomputation) stay separate here by construction.

Note on history depth: with only a handful of snapshot days, the follow-through
numbers are structural previews, not statistically meaningful rates. The page
says so loudly rather than implying precision it does not have.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "lib"))

import altair as alt
import pandas as pd
import streamlit as st

from ui_utils import apply_theme, init_session, render_sidebar

from lib.audit_query import (
    DEFAULT_SNAPSHOT_DIR,
    compute_actionable_follow_through,
    compute_fragility_series,
    load_all_meta,
    load_all_opportunities,
    query_status_transitions,
)

st.set_page_config(page_title="Audit Review", page_icon="🔍", layout="wide")
apply_theme()
init_session()
render_sidebar()

# Follow-through analysis parameters (Block A spec).
_WINDOW_DAYS = 5
_SCORE_THRESHOLD = 0.05
_MEANINGFUL_DAYS = 30        # signal analysis becomes meaningful at 30+ days
_BANNER_DAYS = 14            # below this, show the "early data" banner

# Fragility-level → color (normal=green, elevated=yellow, high=red).
_FRAG_COLORS = {"normal": "#2e7d32", "elevated": "#f9a825", "high": "#c62828"}

# ── Display label maps (de-jargonized, language-aware) ────────────────────────
# Raw tokens that flow up from the snapshot records are mapped to readable labels
# before rendering. Every map is bilingual, keyed by the same "language" toggle
# that drives t() / _tx() ("en" / "zh"). Value maps are applied with
# .map(...).fillna(original) so any unknown/future token falls back to its raw
# string rather than vanishing.

# Market fragility level.
FRAGILITY_LABEL = {
    "zh": {"normal": "正常", "elevated": "偏高", "high": "高"},
    "en": {"normal": "Normal", "elevated": "Elevated", "high": "High"},
}

# Macro regime classification.
REGIME_LABEL = {
    "zh": {
        "risk_on": "风险偏好", "risk_off": "风险规避",
        "transition": "过渡期", "bull_early": "牛市早期",
        "bull_late": "牛市晚期", "recession": "衰退期",
        "stagflation": "滞胀期", "recovery": "复苏期",
    },
    "en": {
        "risk_on": "Risk On", "risk_off": "Risk Off",
        "transition": "Transition", "bull_early": "Bull Early",
        "bull_late": "Bull Late", "recession": "Recession",
        "stagflation": "Stagflation", "recovery": "Recovery",
    },
}

# Opportunity status (per-horizon and flat).
STATUS_LABEL = {
    "zh": {
        "Actionable Now": "可立即操作",
        "Avoid Chasing": "避免追涨",
        "Research Required": "需进一步研究",
        "Wait for Breakout": "等待突破",
        "Wait for Pullback": "等待回调",
    },
    "en": {
        "Actionable Now": "Actionable Now",
        "Avoid Chasing": "Avoid Chasing",
        "Research Required": "Research Required",
        "Wait for Breakout": "Wait for Breakout",
        "Wait for Pullback": "Wait for Pullback",
    },
}

# Horizon → human label (replaces the internal "horizon=short/mid/long" jargon).
HORIZON_LABEL = {
    "zh": {
        "short": "短线（1–4 周）",
        "mid": "中线（1–3 月）",
        "long": "长线（6–18 月）",
    },
    "en": {
        "short": "Short-Term (1–4 wks)",
        "mid": "Mid-Term (1–3 mo)",
        "long": "Long-Term (6–18 mo)",
    },
}

# Column-header rename maps (one per table), language-aware.
COL_META = {
    "zh": {"date": "日期", "n_tickers": "候选标的数", "macro_regime": "宏观环境",
           "fragility_level": "市场脆弱度", "fragility_points": "脆弱度分值"},
    "en": {"date": "Date", "n_tickers": "Candidates", "macro_regime": "Macro Regime",
           "fragility_level": "Fragility Level", "fragility_points": "Fragility Pts"},
}

COL_TICKER = {
    "zh": {"date": "日期", "status_short": "短线状态", "status_mid": "中线状态",
           "status_long": "长线状态", "short_score": "短线评分", "mid_score": "中线评分",
           "long_score": "长线评分", "macro_regime": "宏观环境",
           "fragility_level": "市场脆弱度"},
    "en": {"date": "Date", "status_short": "Short Status", "status_mid": "Mid Status",
           "status_long": "Long Status", "short_score": "Short Score",
           "mid_score": "Mid Score", "long_score": "Long Score",
           "macro_regime": "Macro Regime", "fragility_level": "Fragility Level"},
}

COL_CASES = {
    "zh": {"ticker": "标的", "signal_date": "信号日期", "initial_score": "初始评分",
           "best_score": "窗口内最高评分", "delta": "评分变化", "follow_through": "是否兑现"},
    "en": {"ticker": "Ticker", "signal_date": "Signal Date",
           "initial_score": "Initial Score", "best_score": "Best Score (Window)",
           "delta": "Score Delta", "follow_through": "Follow Through"},
}

COL_AUDIT = {
    "zh": {"file": "快照文件", "missing_fields": "缺失字段"},
    "en": {"file": "Snapshot File", "missing_fields": "Missing Fields"},
}


def _zh() -> bool:
    return st.session_state.get("language", "en") == "zh"


def _tx(en: str, zh: str) -> str:
    """Tiny local bilingual literal helper (page-only chrome strings)."""
    return zh if _zh() else en


# Current language ("en" / "zh") — the whole script reruns on a toggle, so a
# single resolution at module scope is consistent across every section below.
_LANG = "zh" if _zh() else "en"


# ── Cached loaders (re-reading the trail on every widget tick is wasteful) ─────
# The snapshot trail changes at most once per refresh day; a 5-minute TTL keeps
# the page responsive without ever showing data older than one refresh cycle.

@st.cache_data(ttl=300, show_spinner=False)
def _cached_meta(snapshot_dir: str) -> list[dict]:
    """All ``_meta`` records as plain dicts (cache-friendly), ascending by date."""
    return [m.raw for m in load_all_meta(snapshot_dir)]


@st.cache_data(ttl=300, show_spinner=False)
def _cached_opportunities(snapshot_dir: str) -> list[dict]:
    """All per-ticker records as plain dicts, sorted by (date, ticker)."""
    return [o.raw for o in load_all_opportunities(snapshot_dir)]


_SNAPSHOT_DIR = DEFAULT_SNAPSHOT_DIR

st.title("🔍 " + _tx("Audit Review", "审计回顾"))
st.caption(_tx(
    "Read-only review of the daily opportunity snapshot audit trail. "
    "No live signals are recomputed here.",
    "对每日机会快照审计轨迹的只读回顾。本页不重算任何实时信号。"))

_meta_dicts = _cached_meta(_SNAPSHOT_DIR)
_opp_dicts = _cached_opportunities(_SNAPSHOT_DIR)
_n_days = len(_meta_dicts)

if _n_days == 0:
    st.warning(_tx(
        "No snapshot history found under "
        f"`{_SNAPSHOT_DIR}`. Run a Cockpit refresh to produce the first snapshot.",
        f"在 `{_SNAPSHOT_DIR}` 下未找到任何快照历史。请先在 Cockpit 执行一次刷新以生成首个快照。"))
    st.stop()


# ===========================================================================
# Section A — Snapshot Coverage
# ===========================================================================
st.subheader(_tx("A · Snapshot Coverage", "A · 快照覆盖"))

if _n_days < _BANNER_DAYS:
    st.info(_tx(
        f"Note: {_n_days} days of snapshot history available. Signal analysis "
        f"becomes meaningful at {_MEANINGFUL_DAYS}+ days. Current view shows data "
        "structure and early trends.",
        f"提示：当前有 {_n_days} 天的快照历史。信号分析在 {_MEANINGFUL_DAYS} 天以上才具有"
        "统计意义。当前视图展示数据结构与早期趋势。"))

# Count tickers per day from the opportunity records.
_tickers_per_day: dict[str, int] = {}
for _o in _opp_dicts:
    _d = _o.get("date", "")
    _tickers_per_day[_d] = _tickers_per_day.get(_d, 0) + 1

_coverage_rows = [{
    "date": m.get("date", ""),
    "n_tickers": _tickers_per_day.get(m.get("date", ""), 0),
    "macro_regime": m.get("macro_regime", ""),
    "fragility_level": m.get("fragility_level", ""),
    "fragility_points": m.get("fragility_points", 0),
} for m in _meta_dicts]
# Resolve the language-specific maps once for this section.
_frag_map = FRAGILITY_LABEL[_LANG]
_regime_map = REGIME_LABEL[_LANG]

_coverage_df = pd.DataFrame(_coverage_rows)
# Map raw tokens → current language (unknown values fall back to the original).
_coverage_df["fragility_level"] = (
    _coverage_df["fragility_level"].map(_frag_map).fillna(_coverage_df["fragility_level"]))
_coverage_df["macro_regime"] = (
    _coverage_df["macro_regime"].map(_regime_map).fillna(_coverage_df["macro_regime"]))
_coverage_df = _coverage_df.rename(columns=COL_META[_LANG])
st.dataframe(_coverage_df, use_container_width=True, hide_index=True)


# ===========================================================================
# Section B — Fragility History
# ===========================================================================
st.subheader(_tx("B · Fragility History", "B · 脆弱度历史"))

_frag_series = compute_fragility_series(_SNAPSHOT_DIR)
if _frag_series:
    _b_frag_map = FRAGILITY_LABEL[_LANG]
    # Language-aware column names so the tooltip field labels follow the toggle too.
    _frag_col = COL_META[_LANG]["fragility_level"]
    _pts_col = COL_META[_LANG]["fragility_points"]
    _frag_df = pd.DataFrame([{
        "date": e["date"],
        # Map values BEFORE Altair: the data values become the legend labels.
        _frag_col: _b_frag_map.get(e["fragility_level"], e["fragility_level"]),
        _pts_col: e["fragility_points"],
    } for e in _frag_series])
    # Color domain resolved from the current language (正常/偏高/高 or Normal/…).
    _frag_order = list(_b_frag_map.values())
    _chart = (
        alt.Chart(_frag_df)
        .mark_bar()
        .encode(
            x=alt.X(field="date", type="ordinal",
                    title=_tx("Snapshot date", "快照日期")),
            y=alt.Y(field=_pts_col, type="quantitative",
                    title=_tx("Fragility points", "脆弱度分值")),
            color=alt.Color(
                field=_frag_col, type="nominal",
                scale=alt.Scale(domain=_frag_order,
                                range=[_FRAG_COLORS[l] for l in _FRAG_COLORS]),
                legend=alt.Legend(title=_tx("Level", "等级")),
            ),
            tooltip=["date", _frag_col, _pts_col],
        )
        .properties(height=280)
    )
    st.altair_chart(_chart, use_container_width=True)
else:
    st.caption(_tx("No fragility history to chart.", "暂无可绘制的脆弱度历史。"))


# ===========================================================================
# Section C — Ticker Status History
# ===========================================================================
st.subheader(_tx("C · Ticker Status History", "C · 个股状态历史"))

_all_tickers = sorted({_o.get("ticker", "") for _o in _opp_dicts if _o.get("ticker")})
if _all_tickers:
    _sel = st.selectbox(_tx("Select a ticker", "选择标的"), _all_tickers, index=0)
    _rows = query_status_transitions(_sel, snapshot_dir=_SNAPSHOT_DIR)
    if _rows:
        _hist_df = pd.DataFrame([{
            "date": r["date"],
            "status_short": r["status_short"],
            "status_mid": r["status_mid"],
            "status_long": r["status_long"],
            "short_score": round(r["short_score"], 4),
            "mid_score": round(r["mid_score"], 4),
            "long_score": round(r["long_score"], 4),
            "macro_regime": r["macro_regime"],
            "fragility_level": r["fragility_level"],
        } for r in _rows])
        # Resolve language-specific value maps once for this table.
        _c_status_map = STATUS_LABEL[_LANG]
        _c_frag_map = FRAGILITY_LABEL[_LANG]
        _c_regime_map = REGIME_LABEL[_LANG]
        # Map status / fragility / regime tokens (fallback to original on unknown).
        for _col in ("status_short", "status_mid", "status_long"):
            _hist_df[_col] = _hist_df[_col].map(_c_status_map).fillna(_hist_df[_col])
        _hist_df["fragility_level"] = (
            _hist_df["fragility_level"].map(_c_frag_map).fillna(_hist_df["fragility_level"]))
        _hist_df["macro_regime"] = (
            _hist_df["macro_regime"].map(_c_regime_map).fillna(_hist_df["macro_regime"]))
        _hist_df = _hist_df.rename(columns=COL_TICKER[_LANG])
        st.dataframe(_hist_df, use_container_width=True, hide_index=True)
    else:
        st.caption(_tx(f"No snapshot history for {_sel}.", f"{_sel} 暂无快照历史。"))
else:
    st.caption(_tx("No tickers found in the snapshot trail.", "快照轨迹中未发现任何标的。"))


# ===========================================================================
# Section D — Follow-Through Analysis
# ===========================================================================
st.subheader(_tx("D · Follow-Through Analysis", "D · 跟进表现分析"))
st.caption(_tx(
    'For each horizon: of the "Actionable Now" signals, how many saw their score '
    f"rise by ≥ {_SCORE_THRESHOLD:.2f} within the next {_WINDOW_DAYS} snapshot days.",
    f'各时间框架下："立即可操作"信号中，有多少在随后 {_WINDOW_DAYS} 个快照日内分值'
    f"上升 ≥ {_SCORE_THRESHOLD:.2f}。"))

# Language-resolved horizon labels for headings + chrome messages.
_horizon_map = HORIZON_LABEL[_LANG]
_actionable_lbl = STATUS_LABEL[_LANG]["Actionable Now"]

for _hz in ("short", "mid", "long"):
    _res = compute_actionable_follow_through(
        horizon=_hz, status_from="Actionable Now",
        window_days=_WINDOW_DAYS, score_improvement_threshold=_SCORE_THRESHOLD,
        snapshot_dir=_SNAPSHOT_DIR)
    # De-jargonized horizon heading (no "horizon=short/mid/long").
    st.markdown(f"**{_horizon_map[_hz]}**")

    _c1, _c2, _c3 = st.columns(3)
    _c1.metric(_tx("Total signals", "信号总数"), _res["total_signals"])
    _c2.metric(_tx("Follow-through", "跟进达标"), _res["follow_through_count"])
    _c3.metric(_tx("Rate", "达标率"), f"{_res['follow_through_rate']:.0%}")

    if _res["insufficient_history"]:
        st.info(_tx(
            f"Insufficient data for {_horizon_map[_hz]} (need "
            f"{_WINDOW_DAYS}+ snapshot days after the signal). Results will "
            "populate as snapshot history grows.",
            f"{_horizon_map[_hz]}数据不足（需信号后 {_WINDOW_DAYS}+ 个快照日）。"
            "随着快照历史增长，结果将逐步充实。"))

    if _res["cases"]:
        _cases_df = pd.DataFrame([{
            "ticker": c["ticker"],
            "signal_date": c["signal_date"],
            "initial_score": round(c["initial_score"], 4),
            "best_score": round(c["best_score_in_window"], 4),
            "delta": round(c["score_delta"], 4),
            # Boolean follow-through rendered as a glyph instead of True/False.
            "follow_through": "✅" if c["follow_through"] else "❌",
        } for c in _res["cases"]])
        _cases_df = _cases_df.rename(columns=COL_CASES[_LANG])
        st.dataframe(_cases_df, use_container_width=True, hide_index=True)
    else:
        st.caption(_tx(
            f'No "Actionable Now" signals on {_horizon_map[_hz]} yet.',
            f'{_horizon_map[_hz]}暂无"{_actionable_lbl}"信号。'))


# ===========================================================================
# Section E — Audit Trail Integrity (developer view)
# ===========================================================================
st.subheader(_tx("E · Audit Trail Integrity", "E · 审计轨迹完整性"))
st.caption(_tx(
    "Developer diagnostics — not an end-user view. Schema drift across the file "
    "history is expected (additive only) and handled by safe-default readers.",
    "开发者诊断视图，非终端用户视图。文件历史中的字段漂移属预期（仅新增），"
    "由带安全默认值的读取器处理。"))

# File-level facts straight from disk (read-only listing; no parsing of records).
_base = Path(_SNAPSHOT_DIR)
_files = sorted(_base.glob("opportunities_*.jsonl")) if _base.exists() else []
_dates = [m.get("date", "") for m in _meta_dicts]
_date_range = f"{_dates[0]} → {_dates[-1]}" if _dates else "—"

_i1, _i2, _i3 = st.columns(3)
_i1.metric(_tx("Snapshot files", "快照文件数"), len(_files))
_i2.metric(_tx("Total records", "记录总数"), len(_opp_dicts))
_i3.metric(_tx("Date range", "日期范围"), _date_range)

# Schema-drift summary: which optional fields are absent in which files. Computed
# live from the actual files so it never goes stale against the trail on disk.
_DRIFT_FIELDS_RECORD = ("anchor", "rs_stale")
_DRIFT_FIELDS_META = ("earnings_skipped",)

# Human-readable description leading the technical field path (kept in parens for
# developer traceability), language-aware.
_FIELD_PATH_LABEL = {
    "zh": {
        "record.anchor": "个股估值锚（record.anchor）",
        "record.rs_stale": "个股RS过期标志（record.rs_stale）",
        "_meta.earnings_skipped": "元数据财报跳过列表（_meta.earnings_skipped）",
    },
    "en": {
        "record.anchor": "Valuation Anchor (record.anchor)",
        "record.rs_stale": "RS Stale Flag (record.rs_stale)",
        "_meta.earnings_skipped": "Earnings Skipped List (_meta.earnings_skipped)",
    },
}
_field_path_map = _FIELD_PATH_LABEL[_LANG]
_no_missing_lbl = _tx("None", "无缺失")
_drift_rows: list[dict] = []
for _fp in _files:
    try:
        _lines = _fp.read_text(encoding="utf-8").splitlines()
    except OSError:
        continue
    _meta = {}
    _recs: list[dict] = []
    for _ln in _lines:
        _ln = _ln.strip()
        if not _ln:
            continue
        try:
            _obj = json.loads(_ln)
        except json.JSONDecodeError:
            continue
        if isinstance(_obj, dict) and _obj.get("_meta"):
            _meta = _obj
        elif isinstance(_obj, dict):
            _recs.append(_obj)
    _missing = []
    for _f in _DRIFT_FIELDS_META:
        if _f not in _meta:
            _missing.append(f"_meta.{_f}")
    for _f in _DRIFT_FIELDS_RECORD:
        if _recs and any(_f not in _r for _r in _recs):
            _missing.append(f"record.{_f}")
    # Lead with the human description; placeholder when the file has every field.
    _missing_display = [_field_path_map.get(_p, _p) for _p in _missing]
    _sep = "，" if _LANG == "zh" else ", "
    _drift_rows.append({
        "file": _fp.name,
        "missing_fields": _sep.join(_missing_display) if _missing_display else _no_missing_lbl,
    })

if _drift_rows:
    _drift_df = pd.DataFrame(_drift_rows).rename(columns=COL_AUDIT[_LANG])
    st.dataframe(_drift_df, use_container_width=True, hide_index=True)

# Plain-Chinese explanation (no raw field-path literals inline); the exact paths
# live in the developer "技术详情" expander below for traceability.
st.caption(_tx(
    "Expected drift: the individual-stock valuation anchor is absent in the 3 "
    "earliest files; the RS-stale flag and the earnings-skipped list are absent in "
    "the earliest file. All are handled by safe-default readers.",
    "预期漂移：个股估值锚在最早的 3 个文件中缺失；RS 过期标志与财报跳过列表在最早的"
    "文件中缺失。以上均由带安全默认值的读取器处理，不影响查询。"))
with st.expander(_tx("Technical details", "技术详情")):
    st.markdown(
        "- `record.anchor` — " + _tx("absent in the 3 earliest files",
                                      "最早的 3 个文件中缺失") + "\n"
        "- `record.rs_stale` — " + _tx("absent in the earliest file",
                                       "最早的文件中缺失") + "\n"
        "- `_meta.earnings_skipped` — " + _tx("absent in the earliest file",
                                              "最早的文件中缺失"))
