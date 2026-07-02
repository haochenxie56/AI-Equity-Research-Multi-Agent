"""Page 12 — Agent Degradation Review (Degradation-Visibility Layer).

A STANDALONE, READ-ONLY, bilingual, zero-network, zero-LLM review of what the
six foundation agents produced on a given day. It is the audit/debug surface
for foundation-agent output: it distinguishes "the agent said this read was
uncertain/neutral" from "the agent did not actually run at all".

ISOLATION: this page touches ONLY ``lib.degradation_view`` (which reads via
``lib.agent_framework.agent_output``) + ``ui_utils``. It NEVER triggers a
Cockpit refresh, adds NO session_state keys, calls NO LLM, makes NO network
call, and performs NO writes. It imports NOTHING that pulls in
``lib.reliability`` at module-load time — the embedded ``EvidenceRef`` /
``AgentResult`` objects are read purely via ``getattr`` / ``.model_dump`` on
already-reconstructed records, never via a top-level schema import.

Structurally the closest existing precedent is ``pages/11_Audit_Review.py``;
this page mirrors its scaffolding and bilingual (`_tx`) convention rather than
inventing new ones.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "lib"))

import pandas as pd
import streamlit as st

from ui_utils import apply_theme, init_session, render_sidebar

from lib.degradation_view import (
    CANONICAL_AGENT_IDS,
    KNOWN_DEFENSIVE_FLAGS,
    list_available_dates,
    load_and_build_all_views,
)

st.set_page_config(page_title="Agent Degradation", page_icon="🩺", layout="wide")
apply_theme()
init_session()
render_sidebar()


def _zh() -> bool:
    return st.session_state.get("language", "en") == "zh"


def _tx(en: str, zh: str) -> str:
    """Tiny local bilingual literal helper (page-only chrome strings)."""
    return zh if _zh() else en


_LANG = "zh" if _zh() else "en"


# ── Display maps (de-jargonized, language-aware) ──────────────────────────────

AGENT_LABEL = {
    "zh": {
        "MacroRegimeAgent": "宏观环境", "MoneyFlowAgent": "资金流",
        "MarketStructureAgent": "市场结构", "SectorRotationAgent": "板块轮动",
        "ThemeIntelligenceAgent": "主题情报", "CandidateScreeningAgent": "候选筛选",
    },
    "en": {
        "MacroRegimeAgent": "Macro Regime", "MoneyFlowAgent": "Money Flow",
        "MarketStructureAgent": "Market Structure", "SectorRotationAgent": "Sector Rotation",
        "ThemeIntelligenceAgent": "Theme Intelligence", "CandidateScreeningAgent": "Candidate Screening",
    },
}

# Normalized basis_state → human label. "other:*" and unknown states fall back
# to the generic "unrecognized" entry so a future token never vanishes.
BASIS_LABEL = {
    "zh": {
        "ok": "有信号", "degraded": "数据不足", "no_winner": "无明确赢家",
        "no_signal": "无信号", "no_leadership": "无明确领涨", "missing": "无输出",
        "other": "未识别",
    },
    "en": {
        "ok": "Signal Present", "degraded": "Degraded", "no_winner": "No Clear Winner",
        "no_signal": "No Signal", "no_leadership": "No Leadership", "missing": "No Output",
        "other": "Unrecognized",
    },
}

SOURCE_LABEL = {
    "zh": {"llm_proposed": "LLM 提议", "rule_based": "规则回退", "human": "人工"},
    "en": {"llm_proposed": "LLM Proposed", "rule_based": "Rule-Based Fallback", "human": "Human"},
}

COL_SUMMARY = {
    "zh": {"agent": "智能体", "theme": "主题", "status": "状态",
           "basis": "信号基础", "coverage": "覆盖度", "n_flags": "标记数"},
    "en": {"agent": "Agent", "theme": "Theme", "status": "Status",
           "basis": "Basis", "coverage": "Coverage", "n_flags": "# Flags"},
}

# Neutral / wait basis states (present data, no directional call — never bearish).
_NEUTRAL = {"no_winner", "no_signal", "no_leadership"}


# ── Small formatting helpers ──────────────────────────────────────────────────

def _basis_label(state: str) -> str:
    labels = BASIS_LABEL[_LANG]
    if state.startswith("other:"):
        return f"{labels['other']} ({state.split(':', 1)[1]})"
    return labels.get(state, state)


def _source_label(src) -> str:
    if not src:
        return "—"
    return SOURCE_LABEL[_LANG].get(src, src)


def _fmt_pct(value) -> str:
    try:
        return f"{float(value):.0%}"
    except (TypeError, ValueError):
        return "—"


def _coverage_str(coverage) -> str:
    """Coverage is a float for five agents, a {short,mid} dict for the sixth."""
    if coverage is None:
        return "—"
    if isinstance(coverage, dict):
        return _tx(
            f"S {_fmt_pct(coverage.get('short'))} / M {_fmt_pct(coverage.get('mid'))}",
            f"短 {_fmt_pct(coverage.get('short'))} / 中 {_fmt_pct(coverage.get('mid'))}")
    return _fmt_pct(coverage)


def _status_badge(view):
    """Four-way status — the 'no output' and 'degraded/bug' buckets are kept
    visually DISTINCT on purpose (they mean different things to a reviewer)."""
    if not view.has_output:
        return "⚫", _tx("No Output", "无输出")
    if view.likely_bug:
        return "⚠️", _tx("Possible Bug", "疑似 BUG")
    if view.basis_state in _NEUTRAL:
        return "⚪", _tx("Neutral · Wait", "中性·观望")
    return "🟢", _tx("OK", "正常")


def _agent_name(agent_id: str) -> str:
    return AGENT_LABEL[_LANG].get(agent_id, agent_id)


def _ref_dict(ref) -> dict:
    """EvidenceRef → plain dict WITHOUT importing the schema at module load."""
    dump = getattr(ref, "model_dump", None)
    if callable(dump):
        try:
            return dump(mode="json")
        except TypeError:
            try:
                return dump()
            except Exception:
                pass
    return {"repr": str(ref)}


# ── Card renderers ────────────────────────────────────────────────────────────

def _render_flags(view) -> None:
    """Degrade flags with an inline note for any KNOWN_DEFENSIVE flag."""
    if not view.degrade_flags:
        return
    st.markdown(f"**{_tx('Degrade flags', '降级标记')}:**")
    for flag in view.degrade_flags:
        if flag in KNOWN_DEFENSIVE_FLAGS:
            st.markdown(
                f"- `{flag}` — *{_tx('known design limitation', '已知设计限制')}*")
        else:
            st.markdown(f"- `{flag}`")


def _render_evidence_expander(src) -> None:
    refs = list(getattr(src, "evidence_refs", []) or [])
    with st.expander(_tx("Evidence", "证据") + f" ({len(refs)})"):
        if not refs:
            st.caption(_tx("No evidence references.", "无证据引用。"))
        else:
            st.json([_ref_dict(r) for r in refs])


def _render_agent_result_expander(src) -> None:
    """Optional bonus: the embedded AgentResult's 3-horizon findings. The page's
    core value must NOT depend on agent_result being present."""
    ar = getattr(src, "agent_result", None)
    if ar is None:
        return
    findings = list(getattr(ar, "findings", []) or [])
    with st.expander(_tx("Agent findings (3-horizon)", "Agent 结论（三周期）")):
        if not findings:
            st.caption(_tx("No findings on the embedded agent_result.",
                           "内嵌 agent_result 无 findings。"))
            return
        for fnd in findings:
            text = getattr(fnd, "text", "") or ""
            conf = getattr(fnd, "confidence", None)
            suffix = f"  _(conf {conf:.0%})_" if isinstance(conf, (int, float)) else ""
            st.markdown(f"- {text}{suffix}")


def _render_single_agent_card(view) -> None:
    if not view.has_output:
        st.info(_tx("No output for this agent on the selected date.",
                    "所选日期下该智能体没有输出。"))
        return

    src = view.source
    # Judgment (qualitative, number-free by contract).
    judgment = getattr(src, "judgment", "") or ""
    if judgment:
        st.markdown(f"**{_tx('Judgment', '判断')}:** {judgment}")

    c1, c2, c3, c4 = st.columns(4)
    conf = getattr(src, "confidence", None)
    c1.metric(_tx("Confidence", "置信度"), _fmt_pct(conf))
    c2.metric(_tx("Source", "判断来源"), _source_label(view.judgment_source))
    c3.metric(_tx("Basis", "信号基础"), _basis_label(view.basis_state))
    c4.metric(_tx("Coverage", "覆盖度"), _coverage_str(view.coverage))

    st.caption(
        f"{_tx('Recorded', '记录时间')}: {getattr(src, 'timestamp', '—')} · "
        f"{_tx('Valid until', '有效期至')}: {getattr(src, 'valid_until', '—')}")

    _render_flags(view)

    # Informational detail (runner_error etc.) — display only, never a flag.
    if view.detail:
        st.markdown(f"**{_tx('Notes', '备注')}:**")
        for key, val in view.detail.items():
            st.markdown(f"- `{key}`: {val}")

    _render_evidence_expander(src)
    with st.expander(_tx("Raw supporting_data", "原始 supporting_data")):
        st.json(getattr(src, "supporting_data", {}) or {})
    _render_agent_result_expander(src)


def _render_theme_card(view) -> None:
    st.markdown(f"#### {view.theme_key}")
    src = view.source

    # Per-horizon basis shown as two labeled values (NOT collapsed to one).
    hb = view.horizon_basis or {}
    st.markdown(
        f"**{_tx('Short', '短线')}** → {_basis_label(hb.get('short', 'missing'))}  |  "
        f"**{_tx('Mid', '中线')}** → {_basis_label(hb.get('mid', 'missing'))}")

    # Coverage is a dict here — show both short and mid.
    cov = view.coverage if isinstance(view.coverage, dict) else {}
    st.markdown(
        f"**{_tx('Coverage', '覆盖度')}:** "
        f"{_tx('short', '短')} {_fmt_pct(cov.get('short'))} / "
        f"{_tx('mid', '中')} {_fmt_pct(cov.get('mid'))}")

    _render_flags(view)

    # no_trade_reason_* — plain informational text, NOT styled as a warning/flag.
    ntr_short = view.detail.get("no_trade_reason_short")
    ntr_mid = view.detail.get("no_trade_reason_mid")
    if ntr_short:
        st.markdown(_tx(f"No-trade reason (short): {ntr_short}",
                        f"未交易原因（短线）：{ntr_short}"))
    if ntr_mid:
        st.markdown(_tx(f"No-trade reason (mid): {ntr_mid}",
                        f"未交易原因（中线）：{ntr_mid}"))
    if view.detail.get("runner_error"):
        st.markdown(f"`runner_error`: {view.detail['runner_error']}")

    judgment = getattr(src, "judgment", "") or ""
    if judgment:
        st.markdown(f"**{_tx('Judgment', '判断')}:** {judgment}")

    _render_evidence_expander(src)

    # First-level "Slate detail" expander → short_slate / mid_slate.
    sd = getattr(src, "supporting_data", {}) or {}
    with st.expander(_tx("Slate detail", "Slate 详情")):
        st.markdown(f"**{_tx('Short slate', '短线 slate')}**")
        st.json(sd.get("short_slate", {}) or {})
        st.markdown(f"**{_tx('Mid slate', '中线 slate')}**")
        st.json(sd.get("mid_slate", {}) or {})
        # SECOND-LEVEL expander NESTED inside — the large comparison_table must
        # stay hidden by default even when Slate detail is open (product req).
        with st.expander(_tx("Comparison table", "对比表")):
            st.json(sd.get("comparison_table", {}) or {})


# ── Page body ─────────────────────────────────────────────────────────────────

st.title("🩺 " + _tx("Agent Degradation Review", "智能体降级回顾"))
st.caption(_tx(
    "Read-only review of what each foundation agent produced on a given day. It "
    "distinguishes an uncertain / neutral read from an agent that did not run at "
    "all. No live signals are recomputed; no network or LLM call is made here.",
    "对各基础智能体在选定日期产出内容的只读回顾。它区分「读数不确定/中性」与"
    "「该智能体根本没有运行」。本页不重算任何实时信号，也不进行任何网络或 LLM 调用。"))

# Date selector: available dates ∪ today, most-recent-first, defaulting to TODAY.
# Defaulting to today (even with no file yet) is an intentional product decision:
# the "today, nothing yet" empty state is itself meaningful and must not be
# papered over by jumping to the last good day.
_today = datetime.date.today().isoformat()
_dates = sorted(set(list_available_dates()) | {_today}, reverse=True)
_date = st.selectbox(
    _tx("Snapshot date", "快照日期"), _dates, index=_dates.index(_today))

_views = load_and_build_all_views(date=_date)

# GLOBAL EMPTY-STATE CHECK — runs BEFORE any per-agent section is rendered.
_all_empty = all(not v.has_output for vs in _views.values() for v in vs)
if _all_empty:
    st.info(_tx("No agent output for this date yet.", "该日期暂无 agent 输出。"))
    st.stop()

# Flatten in canonical roster order (one entry per (agent, theme) view).
_flat = []
for _agent_id in CANONICAL_AGENT_IDS:
    _flat.extend(_views.get(_agent_id, []))


# ── Section 0 — Summary (one row per (agent, theme)) ──────────────────────────
st.subheader(_tx("0 · Summary", "0 · 总览"))

_m1, _m2, _m3 = st.columns(3)
_m1.metric(_tx("Views", "视图数"), len(_flat))
_m2.metric(_tx("Possible bugs", "疑似 BUG"), sum(1 for v in _flat if v.has_output and v.likely_bug))
_m3.metric(_tx("Missing outputs", "缺失输出"), sum(1 for v in _flat if not v.has_output))

_rows = []
for _v in _flat:
    _emoji, _text = _status_badge(_v)
    _rows.append({
        "agent": _agent_name(_v.agent_id),
        "theme": _v.theme_key or "",
        "status": f"{_emoji} {_text}",
        "basis": _basis_label(_v.basis_state),
        "coverage": _coverage_str(_v.coverage),
        "n_flags": len(_v.degrade_flags),
    })
_summary_df = pd.DataFrame(_rows).rename(columns=COL_SUMMARY[_LANG])
st.dataframe(_summary_df, use_container_width=True, hide_index=True)

st.caption(_tx(
    '"Possible Bug" (⚠️) is a fail-closed heuristic, not a verdict: a '
    "degraded/unrecognized basis, a rule-based fallback judgment, or any degrade "
    "flag not on the known-defensive allow-list trips it. Some flags' "
    "defensiveness depends on which optional API keys you have configured.",
    '「疑似 BUG」（⚠️）是一个"失败即暴露"的启发式判断，并非定论：数据不足/未识别的'
    "信号基础、规则回退判断，或任何不在已知防御性白名单上的降级标记都会触发它。"
    "部分标记是否属防御性取决于你配置了哪些可选 API 密钥。"))


# ── Sections 1-6 — one per agent, canonical roster order ──────────────────────
for _agent_id in CANONICAL_AGENT_IDS:
    _vs = _views.get(_agent_id, [])
    st.subheader(f"{_agent_name(_agent_id)}")

    if _agent_id == "CandidateScreeningAgent":
        # One card per theme (2-3 on an active day; a single has_output=False
        # placeholder on a quiet day).
        if len(_vs) == 1 and not _vs[0].has_output:
            st.info(_tx("No output for this agent on the selected date.",
                        "所选日期下该智能体没有输出。"))
        else:
            for _v in _vs:
                with st.container(border=True):
                    _render_theme_card(_v)
    else:
        # Exactly one card for each of the five single-record agents.
        _v = _vs[0]
        with st.container(border=True):
            _render_single_agent_card(_v)
