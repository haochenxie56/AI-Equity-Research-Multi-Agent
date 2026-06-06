"""LLM Orchestrator — Claude-driven analysis for each workflow step.

Each function:
  1. Formats quantitative data into a structured prompt
  2. Calls Claude API (claude-sonnet-4-6, one call per step)
  3. Parses the JSON response
  4. Falls back gracefully on any failure

All functions accept `lang` ("en" | "zh") for bilingual support.
"""

import os
import json
import logging
import re

_MODEL = "claude-sonnet-4-6"

_log = logging.getLogger("llm_orchestrator")

# Valid GICS sector names used by compute_sector_scores()
_GICS_SECTORS = [
    "Information Technology", "Health Care", "Financials", "Energy",
    "Industrials", "Consumer Discretionary", "Consumer Staples",
    "Materials", "Real Estate", "Utilities", "Communication Services",
]

# Valid subsector names from THEME_ETF_CONFIG and CUSTOM_THEME_CONFIG
_SUBSECTORS_BY_SECTOR: dict[str, list[str]] = {
    "Information Technology": [
        "Semiconductors", "Cloud Computing", "Cybersecurity",
        "AI & Robotics", "Data Centers", "Optical Networking",
    ],
    "Health Care":   ["Biotech", "Genomics"],
    "Financials":    ["Fintech"],
    "Energy":        ["Nuclear Energy", "Clean Energy", "Solar", "Nuclear Power Developers"],
    "Real Estate":   ["Data Center REITs"],
    "Materials":     ["Global X Copper"],
}


# ── Client factory ─────────────────────────────────────────────────────────────

def _get_client():
    import anthropic
    api_key = None
    try:
        import streamlit as st
        api_key = st.secrets.get("ANTHROPIC_API_KEY")
    except Exception:
        pass
    if not api_key:
        api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured")
    return anthropic.Anthropic(api_key=api_key)


# ── JSON parser ────────────────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    """Remove markdown code fences (```json ... ```) from LLM output."""
    # Remove opening fence (with optional language tag)
    text = re.sub(r"```(?:json)?\s*", "", text)
    # Remove closing fence
    text = re.sub(r"```", "", text)
    return text.strip()


def _parse_json(text: str) -> dict:
    """Extract a JSON object from an LLM response with multiple fallback strategies.

    Uses json.JSONDecoder.raw_decode() which correctly handles:
    - Preamble prose before the JSON object
    - Trailing text / notes after the closing brace
    - Markdown code fences (stripped first)

    The old greedy-regex approach (r"\\{[\\s\\S]+\\}") was unreliable when the
    text after the JSON also contained curly braces.
    """
    decoder = json.JSONDecoder()

    def _first_obj(src: str) -> dict | None:
        """Scan src left-to-right for the first decodable JSON object."""
        for i, ch in enumerate(src):
            if ch == "{":
                try:
                    obj, _ = decoder.raw_decode(src, i)
                    if isinstance(obj, dict):
                        return obj
                except Exception:
                    pass
        return None

    # Strategy 1: strip code fences, then find first JSON object
    clean = _strip_fences(text)
    result = _first_obj(clean)
    if result is not None:
        return result

    # Strategy 2: try on the original text (in case fence stripping corrupted it)
    result = _first_obj(text)
    if result is not None:
        return result

    # Fallback: return structured error (never expose raw JSON/text in reasoning)
    return {
        "decision": "N/A",
        "reasoning": "AI analysis unavailable (response could not be parsed).",
        "summary":   "AI analysis unavailable.",
        "key_metrics": {},
    }


def _fallback(step: str, err: Exception) -> dict:
    return {
        "decision": "N/A",
        "reasoning": f"AI analysis unavailable ({step}): {err}",
        "summary": "AI analysis unavailable",
        "key_metrics": {},
        "error": str(err),
    }


# ── Bilingual normaliser (LLM emits *_en + *_zh directly; no deep-translator) ──

def _bilingualize(result: dict, text_fields: list) -> dict:
    """Normalise an LLM result so every prose field has ``{f}_en`` / ``{f}_zh``.

    The prompts now ask the model to emit BOTH ``{f}_en`` (English original) and
    ``{f}_zh`` (professional-finance Chinese) in ONE call, so no Google-Translate
    round-trip is needed. Fail-closed fallback per field: a missing/blank ``_zh``
    falls back to ``_en``; a missing/blank ``_en`` falls back to the plain ``{f}``
    value (older/degraded responses); if all are blank the field is left as "".
    The plain ``{f}`` is also set to the English canonical so any legacy consumer
    (e.g. ``synthesize_sector_analysis``) keeps working. Pure in-process; never
    raises.
    """
    if not isinstance(result, dict):
        return result
    out = dict(result)

    def _s(v):
        return v if isinstance(v, str) and v.strip() and v != "N/A" else None

    for f in text_fields:
        en = _s(out.get(f"{f}_en"))
        zh = _s(out.get(f"{f}_zh"))
        base = _s(out.get(f))
        canonical_en = en or base or ""
        canonical_zh = zh or en or base or ""
        out[f"{f}_en"] = canonical_en
        out[f"{f}_zh"] = canonical_zh
        if canonical_en:
            out[f] = canonical_en
    return out


def _bilingualize_list(items, text_fields: list) -> list:
    """Apply :func:`_bilingualize` to each dict in a list (e.g. selected stocks)."""
    if not isinstance(items, list):
        return items
    return [_bilingualize(it, text_fields) if isinstance(it, dict) else it
            for it in items]


def _llm_json_call(client, max_tokens: int, system: str, user: str) -> dict:
    """Call the LLM and parse the JSON object from the response.

    Centralises all API calls so _parse_json is always used consistently.
    _parse_json uses JSONDecoder.raw_decode() to find the first valid JSON
    object in the response, handling any preamble prose or markdown fences
    Claude may add around the JSON.
    """
    resp = client.messages.create(
        model=_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return _parse_json(resp.content[0].text)


# ── Step 1: Sector Analysis (comprehensive 6-dimension version) ──────────────

def analyze_sector_full(data: dict, lang: str = "en") -> dict:
    """
    One-call comprehensive sector analysis across 6 dimensions.

    data keys:
      macro, phase, scores_3m, scores_1m, scores_6m,
      volume_recent, etf_returns, subsector_scores,
      sector_etf, tentative_sector

    Returns dict with keys:
      macro, rotation, momentum, etf_trend, volume_flow, subsector,
      decision, subsector_decision, reasoning, summary
    """
    try:
        client = _get_client()

        macro_data       = data.get("macro") or {}
        phase            = data.get("phase") or {}
        scores_3m        = data.get("scores_3m")
        scores_1m        = data.get("scores_1m")
        scores_6m        = data.get("scores_6m")
        volume_recent    = data.get("volume_recent") or {}
        etf_returns      = data.get("etf_returns") or {}
        sub_df           = data.get("subsector_scores")
        sector_etf       = data.get("sector_etf", "")
        tentative_sector = data.get("tentative_sector", "")

        # ── Macro ─────────────────────────────────────────────────────────────
        macro_lines = []
        for key, d in macro_data.items():
            if d.get("current") is not None:
                macro_lines.append(
                    f"  {key}: {d['current']:.2f}  (5D: {d.get('change5d', 0):+.2f})"
                )
        macro_text = "\n".join(macro_lines) or "  N/A"

        # ── Rotation phase ────────────────────────────────────────────────────
        phase_text = (
            f"  phase: {phase.get('phase', 'N/A')}\n"
            f"  offensive_score: {phase.get('offensive_score', 'N/A')}\n"
            f"  defensive_score: {phase.get('defensive_score', 'N/A')}\n"
            f"  top3: {', '.join(phase.get('top3_sectors', []))}\n"
            f"  accelerating: {', '.join(phase.get('accelerating', []) or ['none'])}"
        )

        # ── Momentum comparison (3 windows) ───────────────────────────────────
        def _fmt_scores(df, label):
            try:
                if df is None or df.empty:
                    return f"  {label}: N/A"
            except Exception:
                return f"  {label}: N/A"
            lines = [f"  {label}:"]
            for _, r in df.head(6).iterrows():
                lines.append(
                    f"    {r.get('sector','?')}: score={r.get('score',0):.1f}  "
                    f"excess={r.get('primary_excess', r.get('1m_excess', 0)):+.1f}%  "
                    f"accel={r.get('momentum_accel', 0):+.1f}"
                )
            return "\n".join(lines)

        momentum_text = (
            _fmt_scores(scores_1m, "1M window") + "\n" +
            _fmt_scores(scores_3m, "3M window") + "\n" +
            _fmt_scores(scores_6m, "6M window")
        )

        # ── ETF trend vs SPY ──────────────────────────────────────────────────
        if etf_returns:
            etf_lines = [f"  Sector ETF: {sector_etf} ({tentative_sector})"]
            for period, vals in etf_returns.items():
                etf_lines.append(
                    f"  {period}: ETF={vals.get('etf','N/A'):+.1f}%  "
                    f"SPY={vals.get('spy','N/A'):+.1f}%  "
                    f"Excess={vals.get('excess','N/A'):+.1f}%"
                )
            etf_text = "\n".join(etf_lines)
        else:
            etf_text = "  N/A"

        # ── Volume flow ───────────────────────────────────────────────────────
        if volume_recent:
            vol_sorted  = sorted(volume_recent.items(), key=lambda x: x[1], reverse=True)
            vol_lines   = [f"  {s}: {v:.2f}x" for s, v in vol_sorted[:8]]
            volume_text = "  Last-5D avg vol ratio:\n" + "\n".join(vol_lines)
        else:
            volume_text = "  N/A"

        # ── Subsector scores ──────────────────────────────────────────────────
        try:
            sub_empty = sub_df is None or sub_df.empty
        except Exception:
            sub_empty = True

        if not sub_empty:
            sub_lines = [f"  Subsectors of {tentative_sector}:"]
            for _, r in sub_df.head(6).iterrows():
                sub_lines.append(
                    f"    {r.get('name','?')} ({r.get('etf','?')}): "
                    f"score={r.get('score',0):.1f}  "
                    f"3m_ret={r.get('3m_ret',0):+.1f}%  "
                    f"3m_excess={r.get('3m_excess',0):+.1f}%  "
                    f"rsi={r.get('rsi',0):.1f}"
                )
            subsector_text = "\n".join(sub_lines)
        else:
            subsector_text = f"  No subsector data for {tentative_sector}"

        sub_hint = "; ".join(
            f"{s}: [{', '.join(v)}]" for s, v in _SUBSECTORS_BY_SECTOR.items() if v
        )

        # Single bilingual call: the model emits BOTH languages per prose field.
        system = (
            "You are a US equity sector rotation expert. Below are 6 dimensions of "
            "quantitative data. Produce a structured analysis with 6 sub-sections "
            "(2-3 sentences each), then give a sector selection decision.\n"
            "Output pure JSON (no markdown). For EVERY prose field you MUST output "
            "BOTH an English version ('<field>_en') and a Chinese version "
            "('<field>_zh'). The Chinese MUST use professional finance / investment "
            "research terminology — NOT a literal machine translation. Fields:\n"
            '  "macro_en"/"macro_zh":             macro environment (2-3 sentences),\n'
            '  "rotation_en"/"rotation_zh":       rotation signal (2-3 sentences),\n'
            '  "momentum_en"/"momentum_zh":       sector momentum comparison (2-3 sentences),\n'
            '  "etf_trend_en"/"etf_trend_zh":     ETF trend vs SPY (2-3 sentences),\n'
            '  "volume_flow_en"/"volume_flow_zh": volume flow signal (2-3 sentences),\n'
            '  "subsector_en"/"subsector_zh":     subsector analysis (2-3 sentences),\n'
            '  "reasoning_en"/"reasoning_zh":     one-sentence combined rationale,\n'
            '  "summary_en"/"summary_zh":         one-line summary,\n'
            '  "decision":           selected GICS sector (English; must be from valid list),\n'
            '  "subsector_decision": selected subsector (English; from hint list; null if none)'
        )
        user = (
            f"[Macro indicators]\n{macro_text}\n\n"
            f"[Rotation phase]\n{phase_text}\n\n"
            f"[Sector momentum — 3 windows]\n{momentum_text}\n\n"
            f"[ETF returns vs SPY]\n{etf_text}\n\n"
            f"[Volume flow — last 5D avg vol ratio]\n{volume_text}\n\n"
            f"[Subsector scores]\n{subsector_text}\n\n"
            f"Valid GICS sectors: {_GICS_SECTORS}\n"
            f"Available subsectors: {sub_hint}\n\n"
            "Generate the 6-dimension bilingual analysis report and output JSON."
        )

        result = _llm_json_call(client, 3000, system, user)
        return _bilingualize(result, [
            "macro", "rotation", "momentum", "etf_trend",
            "volume_flow", "subsector", "reasoning", "summary",
        ])

    except Exception as e:
        return _fallback("sector_full", e)


# ── Cross-GICS Theme Basket interpretation ───────────────────────────────────

def analyze_theme_basket(theme_key: str, momentum_result, macro_regime,
                         lang: str = "en") -> dict:
    """LLM interpretation of one cross-GICS theme basket.

    Mirrors analyze_sector_full(): deterministic momentum numbers are computed
    by lib/theme_baskets.py; this call only *interprets* them. It never invents
    returns or prices.

    Args:
      theme_key:        THEME_BASKETS key (e.g. "model_training").
      momentum_result:  ThemeMomentumResult dataclass OR a dict with the same
                        fields (label_en/label_zh, etf, constituents,
                        return_1m/return_3m/return_6m, momentum_score,
                        data_source).
      macro_regime:     current macro regime — a str, or a MacroRegimeResult /
                        dict (regime/confidence/horizon_bias/...).
      lang:             "en" | "zh".

    Returns dict with keys:
      macro_alignment, narrative_stage ("early"|"growing"|"mature"|"cooling"),
      key_catalysts, risk_factors, horizon_bias, summary.
    Falls back gracefully on any failure.
    """
    try:
        client = _get_client()

        def _g(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        label_en   = _g(momentum_result, "label_en", theme_key)
        label_zh   = _g(momentum_result, "label_zh", label_en)
        label      = label_zh if lang == "zh" else label_en
        etf        = _g(momentum_result, "etf")
        consts     = _g(momentum_result, "constituents", []) or []
        r1m        = _g(momentum_result, "return_1m")
        r3m        = _g(momentum_result, "return_3m")
        r6m        = _g(momentum_result, "return_6m")
        mscore     = _g(momentum_result, "momentum_score")
        data_src   = _g(momentum_result, "data_source", "fixture")

        # Normalise the macro regime into a short readable string.
        if isinstance(macro_regime, str):
            regime_text = macro_regime
        else:
            _reg  = _g(macro_regime, "regime", "unknown")
            _conf = _g(macro_regime, "confidence")
            _bias = _g(macro_regime, "horizon_bias")
            regime_text = str(_reg)
            if _conf is not None:
                regime_text += f" (confidence={_conf}"
                regime_text += f", horizon_bias={_bias})" if _bias else ")"

        def _ret(v):
            return f"{v:+.1f}%" if isinstance(v, (int, float)) else "N/A"

        mscore_text = f"{mscore:.2f}" if isinstance(mscore, (int, float)) else "N/A"

        src_label = {
            "etf": f"ETF {etf} price returns",
            "equal_weight": "equal-weight average of constituents",
            "fixture": "fixture fallback (no live data)",
        }.get(data_src, data_src)

        basket_text = (
            f"  Theme: {label}\n"
            f"  ETF proxy: {etf or 'none (equal-weight basket)'}\n"
            f"  Constituents: {', '.join(consts) if consts else 'N/A'}\n"
            f"  1M return: {_ret(r1m)}\n"
            f"  3M return: {_ret(r3m)}\n"
            f"  6M return: {_ret(r6m)}\n"
            f"  Momentum score (0-1 percentile): {mscore_text}\n"
            f"  Data source: {src_label}"
        )

        # Single bilingual call: the model emits BOTH languages per prose field.
        system = (
            "You are a US equity thematic strategy expert. Below is quantitative "
            "momentum data for one cross-GICS investment theme plus the current "
            "macro environment. Produce a structured thematic assessment.\n"
            "Output pure JSON (no markdown). For EVERY prose field you MUST output "
            "BOTH an English version ('<field>_en') and a Chinese version "
            "('<field>_zh'). The Chinese MUST use professional finance / investment "
            "research terminology — NOT a literal machine translation. Fields:\n"
            '  "macro_alignment_en"/"macro_alignment_zh": how this theme fits the current macro regime (2-3 sentences),\n'
            '  "narrative_stage": one of "early"|"growing"|"mature"|"cooling" (English enum, single value),\n'
            '  "key_catalysts_en"/"key_catalysts_zh":   what is driving this theme right now (2-3 sentences),\n'
            '  "risk_factors_en"/"risk_factors_zh":     what could derail this theme (2-3 sentences),\n'
            '  "horizon_bias_en"/"horizon_bias_zh":     short/mid/long horizon suitability with rationale,\n'
            '  "summary_en"/"summary_zh":               one-line summary'
        )
        user = (
            f"[Theme momentum data]\n{basket_text}\n\n"
            f"[Current macro regime]\n  {regime_text}\n\n"
            "Generate the bilingual thematic assessment and output JSON."
        )

        result = _llm_json_call(client, 1500, system, user)
        return _bilingualize(result, [
            "macro_alignment", "key_catalysts", "risk_factors",
            "horizon_bias", "summary",
        ])

    except Exception as e:
        return _fallback("theme_basket", e)


# ── Step 1: Sector Analysis (legacy fallback version) ────────────────────────

def analyze_sector(scores_df, macro_data: dict, lang: str = "en") -> dict:
    """Pick the most promising GICS sector + subsector from quantitative data."""
    try:
        client = _get_client()

        # Format sector rows
        rows = []
        for _, r in scores_df.iterrows():
            rows.append(
                f"  {r['sector']}: score={r.get('score', 0):.1f}, "
                f"3m_excess={r.get('3m_excess', 0):+.1f}%, "
                f"1m_excess={r.get('1m_excess', 0):+.1f}%, "
                f"RSI={r.get('rsi', 0):.1f}, "
                f"52W_high_dist={r.get('from_52w_high', 0):.1f}%, "
                f"vol_ratio={r.get('vol_ratio', 0):.2f}x, "
                f"momentum_accel={r.get('momentum_accel', 0):+.1f}"
            )
        sector_text = "\n".join(rows)

        # Format macro
        macro_lines = []
        for key, d in macro_data.items():
            if d.get("current") is not None:
                macro_lines.append(
                    f"  {key}: {d['current']:.2f}  (5D: {d.get('change5d', 0):+.2f})"
                )
        macro_text = "\n".join(macro_lines) or "  N/A"

        # Build subsector hint for each sector
        sub_hint = "; ".join(
            f"{s}: [{', '.join(v)}]"
            for s, v in _SUBSECTORS_BY_SECTOR.items()
            if v
        )

        if lang == "zh":
            system = (
                "你是美股行业配置专家。根据量化数据分析当前板块轮动机会，"
                "选出最值得关注的GICS板块及子方向。\n"
                "输出纯JSON（不含markdown），字段：\n"
                '  "decision": 选定板块名称（必须是给定列表之一），\n'
                '  "subsector": 子板块（可选，从提示列表选；无合适子板块则为null），\n'
                '  "reasoning": 2-3句决策理由（中文），\n'
                '  "summary": 一句话摘要（中文），\n'
                '  "key_metrics": 支持决策的3-5个关键数据点dict'
            )
            user = (
                f"宏观指标：\n{macro_text}\n\n"
                f"板块量化评分（按score降序）：\n{sector_text}\n\n"
                f"有效板块名称（decision必须从此列表选）：\n  {_GICS_SECTORS}\n\n"
                f"可选子板块（按板块分组）：\n  {sub_hint}\n\n"
                "请选出当前最值得关注的板块，输出JSON。"
            )
        else:
            system = (
                "You are a US equity sector rotation expert. Analyze quantitative data to "
                "identify the most promising GICS sector and subsector.\n"
                "Output pure JSON (no markdown), fields:\n"
                '  "decision": selected sector name (must be from the given list),\n'
                '  "subsector": subsector direction (optional, pick from hint list; null if none fits),\n'
                '  "reasoning": 2-3 sentence rationale,\n'
                '  "summary": one-line summary,\n'
                '  "key_metrics": 3-5 key data points as dict'
            )
            user = (
                f"Macro indicators:\n{macro_text}\n\n"
                f"Sector quantitative scores (sorted by score desc):\n{sector_text}\n\n"
                f"Valid sector names (decision must be one of):\n  {_GICS_SECTORS}\n\n"
                f"Available subsectors (grouped by sector):\n  {sub_hint}\n\n"
                "Select the most promising sector and output JSON."
            )

        return _llm_json_call(client, 600, system, user)

    except Exception as e:
        return _fallback("sector", e)


# ── Step 2: Multi-strategy scanner selection ──────────────────────────────────

def analyze_scanner_multi(strategy_results: dict, sector_ctx: dict,
                           lang: str = "en") -> dict:
    """
    Cross-strategy stock selection from multi-strategy scan results.

    strategy_results: {strategy_name: [hit_dict, ...], ...}
    Each hit_dict has: ticker, name, rsi, adx, 3m_ret, 1m_ret,
                       vol_ratio, above_sma200, mkt_cap_b, fwd_pe

    Returns dict with keys:
      selected  — list of {ticker, strategy, confidence, reasoning}
      decision  — top-pick ticker
      runner_up — second-pick ticker
      reasoning — one-paragraph rationale
      summary   — one-line summary
    """
    try:
        client = _get_client()

        # sector_ctx is results["sector"] — actual LLM text lives inside "llm"
        _sec_llm      = sector_ctx.get("llm") or {}
        sector_name   = (_sec_llm.get("decision")
                         or sector_ctx.get("top_sector")
                         or sector_ctx.get("decision", ""))
        # Use English reasoning regardless of workflow run language
        sector_reason = (_sec_llm.get("reasoning_en")
                         or _sec_llm.get("reasoning", ""))

        # Format each strategy's hits
        strat_sections = []
        total_hits = 0
        for strat, hits in strategy_results.items():
            if not hits:
                strat_sections.append(f"  [{strat}]: no hits")
                continue
            total_hits += len(hits)
            lines = [f"  [{strat}] ({len(hits)} hits):"]
            for h in hits[:8]:
                lines.append(
                    f"    {h.get('ticker','?')} ({h.get('name','?')[:20]}): "
                    f"RSI={h.get('rsi') or 'N/A'}  "
                    f"ADX={h.get('adx') or 'N/A'}  "
                    f"3M={h.get('3m_ret') or 'N/A'}%  "
                    f"VolR={h.get('vol_ratio') or 'N/A'}x  "
                    f"Cap={h.get('mkt_cap_b') or 'N/A'}B  "
                    f"FwdPE={h.get('fwd_pe') or 'N/A'}"
                )
            strat_sections.append("\n".join(lines))
        scan_text = "\n".join(strat_sections) or "  No hits across all strategies"

        # Single bilingual call: the model emits BOTH languages per prose field
        # (including each selected stock's reasoning).
        system = (
            "You are a US equity stock selection expert. Below are candidates from "
            "four different strategies. Select 1-5 best stocks across strategies.\n"
            "Evaluation criteria: technical strength, fundamental quality, "
            "strategy confirmation (bonus for multi-strategy hits), market cap / "
            "liquidity, sector fit.\n"
            "Output pure JSON. For EVERY prose field you MUST output BOTH an English "
            "version ('<field>_en') and a Chinese version ('<field>_zh'). The Chinese "
            "MUST use professional finance / investment research terminology — NOT a "
            "literal machine translation. Fields:\n"
            '  "selected": [\n'
            '    {"ticker":"NVDA","strategy":"Momentum","confidence":"High",\n'
            '     "reasoning_en":"...","reasoning_zh":"..."}\n'
            '    ... (up to 5 stocks; ticker/strategy/confidence stay English)\n'
            '  ],\n'
            '  "decision":  top pick ticker (uppercase English, used as deep-dive input),\n'
            '  "runner_up": second-choice ticker (uppercase English; empty string if none),\n'
            '  "reasoning_en"/"reasoning_zh": one-paragraph cross-strategy rationale,\n'
            '  "summary_en"/"summary_zh":     one-line summary (include count and top pick)'
        )
        user = (
            f"Sector context: {sector_name} — {sector_reason}\n\n"
            f"Four-strategy scan results:\n{scan_text}\n\n"
            f"Total hits: {total_hits}. Select best 1-5 stocks and output bilingual JSON."
        )

        result = _llm_json_call(client, 3000, system, user)
        result = _bilingualize(result, ["reasoning", "summary"])
        selected = result.get("selected") or []
        if selected:
            result["selected"] = _bilingualize_list(selected, ["reasoning"])
        return result

    except Exception as e:
        return _fallback("scanner_multi", e)


# ── Step 2: Stock Scanner (legacy single-strategy version) ────────────────────

def analyze_scanner(ranked_df, sector_ctx: dict, lang: str = "en") -> dict:
    """Pick the best ticker from ranked sector constituents."""
    try:
        client = _get_client()

        rows = []
        for _, r in ranked_df.head(25).iterrows():
            rows.append(
                f"  {r.get('ticker','?')} ({r.get('name','?')}): "
                f"tier={r.get('tier','?')}, "
                f"3m_ret={r.get('3m_ret', 0):+.1f}%, "
                f"RSI={r.get('rsi', 0):.1f}, "
                f"SMA200={'Y' if r.get('above_sma200') else 'N'}, "
                f"fwd_pe={r.get('fwd_pe') or 'N/A'}, "
                f"mkt_cap_B={round(r.get('mkt_cap', 0) / 1e9, 1)}"
            )
        stocks_text = "\n".join(rows) or "  No data"

        sector_name     = sector_ctx.get("decision", "")
        sector_reason   = sector_ctx.get("reasoning", "")
        sector_summary  = sector_ctx.get("summary", "")

        if lang == "zh":
            system = (
                "你是美股个股选择专家。根据板块分析结论和成分股评分，"
                "选出最值得深度研究的标的。\n"
                "输出纯JSON，字段：\n"
                '  "decision": 选定ticker代码（大写），\n'
                '  "runner_up": 次选ticker，\n'
                '  "reasoning": 2-3句选股理由（中文），\n'
                '  "summary": 一句话摘要（中文），\n'
                '  "key_metrics": 支持决策的3-5个关键数据点dict'
            )
            user = (
                f"板块背景：{sector_summary}（{sector_name}）\n"
                f"板块逻辑：{sector_reason}\n\n"
                f"成分股评分（按市值排序，含tier分类）：\n{stocks_text}\n\n"
                "请选出最值得深度研究的个股，输出JSON。"
            )
        else:
            system = (
                "You are a US equity stock selection expert. Based on sector analysis "
                "and constituent rankings, select the best candidate for deep-dive research.\n"
                "Output pure JSON, fields:\n"
                '  "decision": selected ticker (uppercase),\n'
                '  "runner_up": second-choice ticker,\n'
                '  "reasoning": 2-3 sentence rationale,\n'
                '  "summary": one-line summary,\n'
                '  "key_metrics": 3-5 key data points as dict'
            )
            user = (
                f"Sector context: {sector_summary} ({sector_name})\n"
                f"Sector rationale: {sector_reason}\n\n"
                f"Constituent stock rankings (sorted by mkt cap, with tier):\n{stocks_text}\n\n"
                "Select the best candidate for deep-dive research and output JSON."
            )

        result = _llm_json_call(client, 600, system, user)
        try:
            from translator import add_bilingual
            result = add_bilingual(result, lang, ["reasoning", "summary"])
        except Exception:
            pass
        return result

    except Exception as e:
        return _fallback("scanner", e)


# ── Step 3: Equity Research ────────────────────────────────────────────────────

def analyze_equity(info: dict, snap: dict, earnings: dict,
                   sector_ctx: dict, scan_ctx: dict, lang: str = "en") -> dict:
    """Comprehensive individual stock analysis."""
    try:
        client = _get_client()

        ticker = info.get("symbol", "?")
        name   = info.get("longName", info.get("shortName", ticker))
        biz    = (info.get("longBusinessSummary") or "")[:500]

        metrics = {
            "price":        info.get("currentPrice") or info.get("regularMarketPrice"),
            "mkt_cap_B":    round((info.get("marketCap") or 0) / 1e9, 1),
            "trailing_pe":  info.get("trailingPE"),
            "forward_pe":   info.get("forwardPE"),
            "gross_margin": f"{(info.get('grossMargins') or 0)*100:.1f}%",
            "op_margin":    f"{(info.get('operatingMargins') or 0)*100:.1f}%",
            "roe":          f"{(info.get('returnOnEquity') or 0)*100:.1f}%",
            "analyst":      info.get("recommendationKey", "N/A"),
            "num_analysts": info.get("numberOfAnalystOpinions"),
            "target_price": info.get("targetMeanPrice"),
            "rsi_14":       snap.get("RSI_14"),
            "adx":          snap.get("ADX"),
            "above_sma200": snap.get("above_SMA200"),
            "from_52w_high":snap.get("pct_from_52w_high"),
            "vol_ratio":    snap.get("Vol_ratio_20d"),
        }
        if earnings and earnings.get("next_earnings_date"):
            metrics["next_earnings"] = str(earnings["next_earnings_date"])[:10]
            metrics["days_to_earnings"] = earnings.get("days_to_earnings")

        metrics_text = "\n".join(f"  {k}: {v}" for k, v in metrics.items() if v is not None)

        sector_reason = sector_ctx.get("reasoning", "")
        scan_reason   = scan_ctx.get("reasoning", "")

        if lang == "zh":
            system = (
                "你是美股个股研究分析师。综合公司基本面、竞争优势、分析师评级和技术面，"
                "给出全面的个股研究结论。\n"
                "输出纯JSON，字段：\n"
                '  "decision": 整体判断（如"积极配置"/"观察等待"/"谨慎回避"），\n'
                '  "reasoning": 2-3句核心逻辑（中文），\n'
                '  "summary": 一句话摘要（中文），\n'
                '  "key_metrics": 护城河、估值、技术面等3-5个判断dict'
            )
            user = (
                f"标的：{ticker} — {name}\n\n"
                f"业务简介：{biz}\n\n"
                f"关键指标：\n{metrics_text}\n\n"
                f"板块逻辑：{sector_reason}\n"
                f"选股逻辑：{scan_reason}\n\n"
                "请给出个股研究结论，输出JSON。"
            )
        else:
            system = (
                "You are a US equity research analyst. Synthesize fundamentals, "
                "competitive advantages, analyst ratings, and technicals to provide "
                "comprehensive equity research conclusions.\n"
                "Output pure JSON, fields:\n"
                '  "decision": overall judgment (e.g. "Buy"/"Hold"/"Watch"/"Avoid"),\n'
                '  "reasoning": 2-3 sentences of core logic,\n'
                '  "summary": one-line summary,\n'
                '  "key_metrics": moat, valuation, technicals — 3-5 judgments as dict'
            )
            user = (
                f"Stock: {ticker} — {name}\n\n"
                f"Business: {biz}\n\n"
                f"Key metrics:\n{metrics_text}\n\n"
                f"Sector context: {sector_reason}\n"
                f"Selection rationale: {scan_reason}\n\n"
                "Provide equity research conclusions and output JSON."
            )

        result = _llm_json_call(client, 700, system, user)
        try:
            from translator import add_bilingual
            result = add_bilingual(result, lang, ["reasoning", "summary", "decision"])
        except Exception:
            pass
        return result

    except Exception as e:
        return _fallback("equity", e)


# ── Step 4: Financial Analysis ─────────────────────────────────────────────────

def analyze_financials(fin_data: dict, equity_ctx: dict, lang: str = "en") -> dict:
    """Assess 3-statement financial health."""
    try:
        client = _get_client()

        equity_reason = equity_ctx.get("reasoning", "")
        fin_text = "\n".join(f"  {k}: {v}" for k, v in fin_data.items() if v is not None)

        if lang == "zh":
            system = (
                "你是财务分析师。根据三张报表关键数据，结合个股研究背景，"
                "评估财务健康度，识别核心亮点和风险。\n"
                "输出纯JSON，字段：\n"
                '  "decision": 财务评级（"优秀"/"良好"/"一般"/"警示"），\n'
                '  "reasoning": 2-3句核心财务逻辑（中文），\n'
                '  "summary": 一句话摘要（中文），\n'
                '  "key_metrics": 增长、利润率、现金流质量等3-5个指标dict'
            )
            user = (
                f"关键财务数据（TTM）：\n{fin_text}\n\n"
                f"个股研究背景：{equity_reason}\n\n"
                "请评估财务健康状况，输出JSON。"
            )
        else:
            system = (
                "You are a financial analyst. Based on key 3-statement data and equity "
                "research context, assess financial health and identify strengths and risks.\n"
                "Output pure JSON, fields:\n"
                '  "decision": financial rating ("Excellent"/"Good"/"Fair"/"Caution"),\n'
                '  "reasoning": 2-3 sentences of core financial logic,\n'
                '  "summary": one-line summary,\n'
                '  "key_metrics": growth, margins, cash flow quality — 3-5 metrics as dict'
            )
            user = (
                f"Key financial data (TTM):\n{fin_text}\n\n"
                f"Equity research context: {equity_reason}\n\n"
                "Assess financial health and output JSON."
            )

        result = _llm_json_call(client, 600, system, user)
        try:
            from translator import add_bilingual
            result = add_bilingual(result, lang, ["reasoning", "summary", "decision"])
        except Exception:
            pass
        return result

    except Exception as e:
        return _fallback("financial", e)


# ── Step 5: Price & Volume Analysis ───────────────────────────────────────────

def analyze_pv(snap: dict, equity_ctx: dict, lang: str = "en") -> dict:
    """Interpret technical indicators and chart structure."""
    try:
        client = _get_client()

        equity_reason = equity_ctx.get("reasoning", "")
        tech = {
            "price":            snap.get("price"),
            "RSI_14":           snap.get("RSI_14"),
            "ADX":              snap.get("ADX"),
            "above_SMA200":     snap.get("above_SMA200"),
            "SMA_20":           snap.get("SMA_20"),
            "SMA_50":           snap.get("SMA_50"),
            "SMA_200":          snap.get("SMA_200"),
            "pct_from_52w_high":snap.get("pct_from_52w_high"),
            "Vol_ratio_20d":    snap.get("Vol_ratio_20d"),
            "MACD":             snap.get("MACD"),
            "MACD_signal":      snap.get("MACD_signal"),
        }
        tech_text = "\n".join(f"  {k}: {v}" for k, v in tech.items() if v is not None)

        if lang == "zh":
            system = (
                "你是技术分析师。根据技术指标数据，结合个股研究背景，"
                "判断当前技术形态、趋势强弱和关键价位，给出技术面结论。\n"
                "输出纯JSON，字段：\n"
                '  "decision": 技术形态（"强势"/"中性"/"弱势"/"超买"/"超卖"），\n'
                '  "reasoning": 2-3句技术逻辑（中文），\n'
                '  "summary": 一句话摘要（中文），\n'
                '  "key_metrics": 趋势、动能、支撑阻力等3-5个技术判断dict'
            )
            user = (
                f"技术指标数据：\n{tech_text}\n\n"
                f"个股研究背景：{equity_reason}\n\n"
                "请给出技术面分析结论，输出JSON。"
            )
        else:
            system = (
                "You are a technical analyst. Based on indicator data and equity "
                "research context, assess chart pattern, trend strength, and key levels.\n"
                "Output pure JSON, fields:\n"
                '  "decision": technical pattern ("Bullish"/"Neutral"/"Bearish"/"Overbought"/"Oversold"),\n'
                '  "reasoning": 2-3 sentences of technical logic,\n'
                '  "summary": one-line summary,\n'
                '  "key_metrics": trend, momentum, support/resistance — 3-5 judgments as dict'
            )
            user = (
                f"Technical indicator data:\n{tech_text}\n\n"
                f"Equity research context: {equity_reason}\n\n"
                "Provide technical analysis conclusions and output JSON."
            )

        result = _llm_json_call(client, 600, system, user)
        try:
            from translator import add_bilingual
            result = add_bilingual(result, lang, ["reasoning", "summary", "decision"])
        except Exception:
            pass
        return result

    except Exception as e:
        return _fallback("pv", e)


# ── Sector Page: Synthesis of 6 sub-sections ─────────────────────────────────

def synthesize_sector_analysis(sec_llm: dict, lang: str = "en") -> dict:
    """
    Synthesise the 6 sector sub-section paragraphs into one comprehensive
    conclusion paragraph.  Returns {"conclusion": "..."}
    """
    try:
        client = _get_client()

        fields = ["macro", "rotation", "momentum", "etf_trend", "volume_flow", "subsector"]
        labels_zh = ["宏观环境", "轮动信号", "板块动量", "ETF走势", "资金流入", "子板块"]
        labels_en = ["Macro", "Rotation", "Momentum", "ETF Trend", "Volume Flow", "Subsector"]

        parts = []
        for field, lbl_zh, lbl_en in zip(fields, labels_zh, labels_en):
            text = sec_llm.get(field, "")
            if text and "unavailable" not in text.lower():
                lbl = lbl_zh if lang == "zh" else lbl_en
                parts.append(f"[{lbl}] {text}")

        if not parts:
            return {"conclusion": ""}

        context = "\n".join(parts)

        if lang == "zh":
            system = (
                "你是资深美股行业研究分析师。根据以下六个维度的板块分析，"
                "撰写一段150字左右的综合研究结论，要求：\n"
                "- 覆盖宏观背景、轮动信号、动量对比、资金流向和子板块选择\n"
                "- 语言流畅、专业，给出明确的配置建议方向\n"
                "- 输出纯JSON：{\"conclusion\": \"...\"}"
            )
            user = f"六维度分析：\n{context}\n\n请生成综合研究结论，输出JSON。"
        else:
            system = (
                "You are a senior US equity sector analyst. Synthesise the following "
                "six-dimension sector analysis into a ~150-word comprehensive conclusion.\n"
                "Requirements:\n"
                "- Cover macro backdrop, rotation signal, momentum, volume flow, subsector\n"
                "- Professional tone with a clear allocation direction\n"
                "- Output pure JSON: {\"conclusion\": \"...\"}"
            )
            user = f"Six-dimension analysis:\n{context}\n\nGenerate the comprehensive conclusion as JSON."

        result = _llm_json_call(client, 600, system, user)
        try:
            from translator import add_bilingual
            result = add_bilingual(result, lang, ["conclusion"])
        except Exception:
            pass
        return result

    except Exception as e:
        return _fallback("sector_synthesis", e)


# ── Synthesis: Comprehensive Conclusion ───────────────────────────────────────

def synthesize_report(state: dict, lang: str = "en") -> dict:
    """Generate a comprehensive conclusion synthesising all 5 step results.

    Returns JSON: {recommendation, conclusion, risks (list)}
    """
    try:
        client = _get_client()

        sector  = state.get("sector", "N/A")
        ticker  = state.get("ticker", "N/A")
        results = state.get("results", {})

        def _ctx(step: str) -> str:
            llm = (results.get(step) or {}).get("llm", {})
            dec = llm.get("decision", "N/A")
            rea = llm.get("reasoning", "")
            return f"{dec}: {rea}" if rea else dec

        context = (
            f"Sector Analysis — {_ctx('sector')}\n"
            f"Stock Selection — {_ctx('scan')}\n"
            f"Equity Research — {_ctx('equity')}\n"
            f"Financial Analysis — {_ctx('financial')}\n"
            f"Price & Volume — {_ctx('pv')}"
        )

        if lang == "zh":
            system = (
                "你是资深投资研究报告撰写专家。根据五步分析结论，撰写综合投资结论段落。\n"
                "要求：覆盖板块逻辑、个股选择理由、财务健康度和技术面；"
                "给出明确整体建议；列出2-3个主要风险。约150-200字，专业易读。\n"
                "输出纯JSON，字段：\n"
                '  "recommendation": "积极配置"|"观察等待"|"谨慎回避",\n'
                '  "conclusion": 综合结论段落（中文），\n'
                '  "risks": ["风险1","风险2",...]'
            )
            user = (
                f"研究标的：{sector} / {ticker}\n\n"
                f"五步分析结论：\n{context}\n\n"
                "请生成综合投资结论，输出JSON。"
            )
        else:
            system = (
                "You are a senior investment research writer. Synthesise five-step analysis "
                "into a comprehensive investment conclusion.\n"
                "Requirements: cover sector logic, stock selection, financial health, technicals; "
                "give a clear recommendation; list 2-3 key risks. ~150-200 words, professional.\n"
                "Output pure JSON, fields:\n"
                '  "recommendation": "Buy"|"Hold"|"Watch"|"Avoid",\n'
                '  "conclusion": comprehensive conclusion paragraph,\n'
                '  "risks": ["risk 1","risk 2",...]'
            )
            user = (
                f"Research target: {sector} / {ticker}\n\n"
                f"Five-step analysis:\n{context}\n\n"
                "Generate comprehensive investment conclusion and output JSON."
            )

        result = _llm_json_call(client, 900, system, user)
        try:
            from translator import add_bilingual, translate_str_list
            result = add_bilingual(result, lang, ["recommendation", "conclusion"])
            risks = result.get("risks")
            if isinstance(risks, list) and risks:
                both = translate_str_list(risks, lang)
                result["risks_en"] = both.get("en", risks)
                result["risks_zh"] = both.get("zh", risks)
        except Exception:
            pass
        return result

    except Exception as e:
        return _fallback("synthesis", e)


# ── REMOVED: translate_research_fields() ─────────────────────────────────────
# Bilingual support is now handled at generation time by translator.py.
# Each LLM analysis function calls add_bilingual() immediately after parsing.
# Rendering reads {field}_{lang} via the bi() helper in ui_utils.py.

# translate_research_fields() has been removed.
# Use translator.add_bilingual() / translator.add_bilingual_list() instead.


# ── Phase 6C-B: Equity fair-value bull/bear/risk debate ──────────────────────

_DEBATE_TEXT_FIELDS = ("bull_case", "bear_case", "risk_factors", "synthesis")
_DEBATE_ACTIONS = ("buy", "hold", "avoid", "wait")


def _debate_fallback(low: float, high: float, reason: str = "") -> dict:
    """Deterministic, code-only fallback (no LLM). Endorses the app low/high band.

    ``reason`` is surfaced (both languages) so the page can tell the user WHY the
    debate did not run instead of showing blank prose. The result carries
    ``debate_status="fallback"`` and ``debate_error=<reason>``.
    """
    why = (reason or "AI debate unavailable").strip()
    msg_en = (
        f"AI debate did not run ({why}). Showing the app-computed fair value "
        "range only — not an AI-endorsed view."
    )
    msg_zh = (
        f"AI 辩论未运行（{why}）。仅展示应用计算的合理估值区间，非 AI 认可结论。"
    )
    out = {}
    for f in _DEBATE_TEXT_FIELDS:
        out[f"{f}_en"] = msg_en
        out[f"{f}_zh"] = msg_zh
    out["endorsed_fair_value_low"] = round(float(low), 2)
    out["endorsed_fair_value_high"] = round(float(high), 2)
    out["analyst_action"] = "hold"
    out["debate_status"] = "fallback"
    out["debate_error"] = why
    return out


def _extract_debate_fields(text: str):
    """Last-resort field-by-field regex extraction from a possibly truncated /
    malformed debate JSON string. Returns a dict if at least ``bull_case_en`` is
    found, else ``None`` (survives a missing closing brace / output truncation)."""
    if not text:
        return None
    out: dict = {}

    def _grab(key: str):
        m = re.search(r'"%s"\s*:\s*"((?:[^"\\]|\\.)*)"' % re.escape(key), text, re.S)
        if not m:
            return None
        val = (m.group(1)
               .replace('\\"', '"').replace("\\n", " ")
               .replace("\\t", " ").replace("\\\\", "\\"))
        return val.strip()

    for f in _DEBATE_TEXT_FIELDS:
        en = _grab(f"{f}_en")
        zh = _grab(f"{f}_zh")
        if en:
            out[f"{f}_en"] = en
        if zh:
            out[f"{f}_zh"] = zh
    for key in ("endorsed_fair_value_low", "endorsed_fair_value_high"):
        m = re.search(r'"%s"\s*:\s*(-?\d+(?:\.\d+)?)' % key, text)
        if m:
            try:
                out[key] = float(m.group(1))
            except ValueError:
                pass
    m = re.search(r'"analyst_action"\s*:\s*"(\w+)"', text)
    if m:
        out["analyst_action"] = m.group(1)
    return out if out.get("bull_case_en") else None


def _parse_debate_response(text: str):
    """Lenient debate-JSON parser. Strategy chain: (1) the standard parser
    (markdown-fence strip + first decodable object), (2) the first ``{...}`` block,
    (3) field-by-field regex extraction. Returns a dict with ``bull_case_en`` or
    ``None``."""
    if not text:
        return None
    parsed = _parse_json(text)  # strips fences, scans for first JSON object
    if isinstance(parsed, dict) and parsed.get("bull_case_en"):
        return parsed
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict) and obj.get("bull_case_en"):
                return obj
        except Exception:  # noqa: BLE001 — fall through to regex extraction
            pass
    return _extract_debate_fields(text)


def analyze_equity_fair_value_debate(
    ticker: str,
    app_fair_value,
    thesis_text: str = "",
    macro_regime: str = "unknown",
    lang: str = "en",
) -> dict:
    """One LLM call: a bull / bear / risk debate over an app-computed fair value.

    Input is the full :class:`lib.equity_valuation.AppFairValue` plus the current
    macro regime and an optional thesis. The LLM acts as a bull/bear/risk panel
    and endorses a fair-value range + a recommended action. Output JSON is
    bilingual (``*_en`` / ``*_zh``) for every prose field. Cached TTL=7200 keyed
    on ``(ticker, confidence, macro_regime, lang)``. Fail-closed: on any failure
    the endorsed range mirrors the app ``fair_value_low`` / ``fair_value_high``
    and the action defaults to ``hold``. The LLM never alters the computed
    numbers — it only argues over them.
    """
    tk = (ticker or "").upper().strip()
    lang = lang if lang in ("en", "zh") else "en"
    regime = (macro_regime or "unknown").strip().lower() or "unknown"
    low = float(getattr(app_fair_value, "fair_value_low", 0.0) or 0.0)
    mid = float(getattr(app_fair_value, "fair_value_mid", 0.0) or 0.0)
    high = float(getattr(app_fair_value, "fair_value_high", 0.0) or 0.0)
    confidence = str(getattr(app_fair_value, "confidence", "low") or "low")
    upside = float(getattr(app_fair_value, "upside_pct", 0.0) or 0.0)
    dcf = getattr(app_fair_value, "dcf_value", None)
    rel = getattr(app_fair_value, "relative_value", None)
    ana = getattr(app_fair_value, "analyst_target", None)
    methodology = str(getattr(app_fair_value, "methodology", "") or "")
    try:
        return _equity_debate_cached(
            tk, confidence, regime, lang, round(low, 2), round(mid, 2), round(high, 2),
            round(upside, 4), dcf, rel, ana, methodology, (thesis_text or "")[:600],
        )
    except Exception as exc:  # noqa: BLE001 — fail-closed
        _reason = f"{type(exc).__name__}: {exc}"
        _log.warning(
            "analyze_equity_fair_value_debate(%s): failed (%s); returning fallback",
            tk, _reason,
        )
        return _debate_fallback(low, high, _reason)


def _equity_debate_cached(ticker: str, confidence: str, macro_regime: str, lang: str,
                          low: float, mid: float, high: float, upside: float,
                          dcf, rel, ana, methodology: str, thesis_text: str) -> dict:
    """Cached LLM debate (fail-closed)."""
    if not _has_llm_api_key():
        _reason = "ANTHROPIC_API_KEY not configured"
        _log.warning(
            "analyze_equity_fair_value_debate(%s): %s; returning deterministic "
            "fallback (endorsed = app low/high, action=hold).", ticker, _reason,
        )
        return _debate_fallback(low, high, _reason)
    try:
        client = _get_client()
        facts = (
            f"ticker: {ticker}\n"
            f"app_fair_value_low: {low}\n"
            f"app_fair_value_mid: {mid}\n"
            f"app_fair_value_high: {high}\n"
            f"upside_pct (mid vs current): {upside:.2%}\n"
            f"confidence: {confidence}\n"
            f"dcf_value: {dcf}\n"
            f"relative_value: {rel}\n"
            f"analyst_target: {ana}\n"
            f"methodology: {methodology}\n"
            f"macro_regime: {macro_regime}\n"
            f"thesis: {thesis_text or '(none given)'}"
        )
        # Concise prompt — field names + a one-line description each — so the
        # bilingual JSON has plenty of token room and does not truncate.
        system = (
            "You are an equity research debate panel (bull/bear/risk). The "
            "fair-value range was computed by code; do NOT change the numbers, "
            "only argue over them. Reply with PURE JSON ONLY (no markdown, no "
            "prose), every text field in BOTH English (_en) and "
            "professional-finance Chinese (_zh). Keep each field to 2-3 short "
            "sentences. Fields:\n"
            "bull_case_en / bull_case_zh: why fair_value_high is reachable.\n"
            "bear_case_en / bear_case_zh: why fair_value_low or below is the risk.\n"
            "risk_factors_en / risk_factors_zh: what could invalidate the valuation.\n"
            "synthesis_en / synthesis_zh: recommended stance + endorsed range.\n"
            "endorsed_fair_value_low / endorsed_fair_value_high: numbers near the band.\n"
            'analyst_action: one of "buy"|"hold"|"avoid"|"wait".'
        )
        user = (
            "Return the JSON object ONLY for this app-computed fair value.\n\n"
            f"{facts}"
        )
        # max_tokens generous (>=1500) so the bilingual JSON never truncates.
        resp = client.messages.create(
            model=_MODEL, max_tokens=1600, system=system,
            messages=[{"role": "user", "content": user}],
        )
        raw_text = resp.content[0].text if (resp and resp.content) else ""
        parsed = _parse_debate_response(raw_text)
        if not isinstance(parsed, dict) or not parsed.get("bull_case_en"):
            _reason = (
                f"LLM response was not parseable JSON ({len(raw_text)} chars; "
                f"head: {raw_text[:120]!r})"
            )
            _log.warning("analyze_equity_fair_value_debate(%s): %s", ticker, _reason)
            return _debate_fallback(low, high, _reason)

        def _pair(field: str) -> tuple:
            en = str(parsed.get(f"{field}_en", "") or parsed.get(field, "") or "")[:1200]
            zh = str(parsed.get(f"{field}_zh", "") or "")[:1200]
            return en, (zh or en)

        out: dict = {}
        for f in _DEBATE_TEXT_FIELDS:
            en, zh = _pair(f)
            out[f"{f}_en"], out[f"{f}_zh"] = en, zh

        def _num(key: str, default: float) -> float:
            v = parsed.get(key)
            try:
                fv = float(v)
                return fv if fv == fv else default  # reject NaN
            except (TypeError, ValueError):
                return default

        out["endorsed_fair_value_low"] = round(_num("endorsed_fair_value_low", low), 2)
        out["endorsed_fair_value_high"] = round(_num("endorsed_fair_value_high", high), 2)
        action = parsed.get("analyst_action")
        out["analyst_action"] = action if action in _DEBATE_ACTIONS else "hold"
        out["debate_status"] = "ok"
        out["debate_error"] = ""
        return out
    except Exception as exc:  # noqa: BLE001 — fail-closed
        _reason = f"{type(exc).__name__}: {exc}"
        _log.warning(
            "analyze_equity_fair_value_debate(%s): LLM call failed (%s); "
            "returning fallback.", ticker, _reason,
        )
        return _debate_fallback(low, high, _reason)


# Decorate the cached debate worker with st.cache_data when Streamlit is available.
try:  # pragma: no cover - cache decoration is environment dependent
    import streamlit as _st_dbg

    _equity_debate_cached = _st_dbg.cache_data(ttl=7200, show_spinner=False)(
        _equity_debate_cached
    )
except Exception:  # noqa: BLE001
    pass


def _has_llm_api_key() -> bool:
    """True if an LLM API key is configured (without importing the SDK)."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    try:
        import streamlit as st

        return bool(st.secrets.get("ANTHROPIC_API_KEY"))
    except Exception:  # noqa: BLE001
        return False
