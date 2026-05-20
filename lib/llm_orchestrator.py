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
import re

_MODEL = "claude-sonnet-4-6"

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
    """Extract JSON from LLM response with multiple fallback strategies."""
    # Pre-process: strip code fences so subsequent strategies work on clean text
    clean = _strip_fences(text)

    # Strategy 1: direct parse of cleaned text
    try:
        return json.loads(clean)
    except Exception:
        pass
    # Strategy 2: first {...} block in cleaned text
    m = re.search(r"\{[\s\S]+\}", clean)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    # Strategy 3: original text, first {...} block (in case fence stripping broke it)
    m = re.search(r"\{[\s\S]+\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
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


def _llm_json_call(client, max_tokens: int, system: str, user: str) -> dict:
    """
    Call the LLM and parse a JSON object response.

    Uses assistant-turn prefill ``{`` so Claude is forced to output raw JSON
    immediately, without any preamble text, markdown code fences, or
    explanatory prose.  The opening brace is prepended back before parsing.
    """
    resp = client.messages.create(
        model=_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[
            {"role": "user",      "content": user},
            {"role": "assistant", "content": "{"},   # prefill — forces JSON start
        ],
    )
    return _parse_json("{" + resp.content[0].text)


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

        if lang == "zh":
            system = (
                "你是美股行业配置专家。以下是六个维度的量化数据，"
                "请按六个子章节结构输出深度分析，每个子章节2-3句，最后给出板块选择决策。\n"
                "输出纯JSON（不含markdown），字段：\n"
                '  "macro":              宏观环境分析（2-3句中文），\n'
                '  "rotation":           轮动信号分析（2-3句中文），\n'
                '  "momentum":           板块动量对比（2-3句中文），\n'
                '  "etf_trend":          ETF走势对比（2-3句中文），\n'
                '  "volume_flow":        资金流入信号（2-3句中文），\n'
                '  "subsector":          子板块分析（2-3句中文），\n'
                '  "decision":           选定GICS板块（必须在有效列表中），\n'
                '  "subsector_decision": 选定子板块（从提示列表选；无则null），\n'
                '  "reasoning":          综合决策逻辑（1句），\n'
                '  "summary":            一句话摘要'
            )
            user = (
                f"【宏观指标】\n{macro_text}\n\n"
                f"【轮动阶段】\n{phase_text}\n\n"
                f"【板块动量对比（三窗口）】\n{momentum_text}\n\n"
                f"【ETF走势 vs SPY】\n{etf_text}\n\n"
                f"【近5日资金量比】\n{volume_text}\n\n"
                f"【子板块评分】\n{subsector_text}\n\n"
                f"有效GICS板块：{_GICS_SECTORS}\n"
                f"可选子板块：{sub_hint}\n\n"
                "请生成六维度分析报告并输出JSON。"
            )
        else:
            system = (
                "You are a US equity sector rotation expert. Below are 6 dimensions of "
                "quantitative data. Produce a structured analysis with 6 sub-sections "
                "(2-3 sentences each), then give a sector selection decision.\n"
                "Output pure JSON (no markdown), fields:\n"
                '  "macro":              macro environment (2-3 sentences),\n'
                '  "rotation":           rotation signal (2-3 sentences),\n'
                '  "momentum":           sector momentum comparison (2-3 sentences),\n'
                '  "etf_trend":          ETF trend vs SPY (2-3 sentences),\n'
                '  "volume_flow":        volume flow signal (2-3 sentences),\n'
                '  "subsector":          subsector analysis (2-3 sentences),\n'
                '  "decision":           selected GICS sector (must be from valid list),\n'
                '  "subsector_decision": selected subsector (from hint list; null if none),\n'
                '  "reasoning":          one-sentence combined rationale,\n'
                '  "summary":            one-line summary'
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
                "Generate the 6-dimension analysis report and output JSON."
            )

        result = _llm_json_call(client, 2000, system, user)
        try:
            from translator import add_bilingual
            result = add_bilingual(result, lang, [
                "macro", "rotation", "momentum", "etf_trend",
                "volume_flow", "subsector", "reasoning", "summary",
            ])
        except Exception:
            pass
        return result

    except Exception as e:
        return _fallback("sector_full", e)


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

        if lang == "zh":
            system = (
                "你是美股选股专家。以下是四种策略各自筛出的候选股，"
                "请跨策略综合评估，选出1-5支最优标的。\n"
                "评估维度：技术面强度、基本面质量、策略确认度（多策略同时命中加分）、"
                "市值流动性、板块匹配度。\n"
                "输出纯JSON，字段：\n"
                '  "selected": [\n'
                '    {"ticker":"NVDA","strategy":"Momentum","confidence":"High","reasoning":"..."}\n'
                '    ... (最多5支)\n'
                '  ],\n'
                '  "decision":  最强1支ticker（大写，作为下一步深度研究输入），\n'
                '  "runner_up": 次选ticker（可为空字符串），\n'
                '  "reasoning": 综合选股逻辑（1-2句，中文），\n'
                '  "summary":   一句话摘要（含入选股数量和最强标的，中文）'
            )
            user = (
                f"板块背景：{sector_name} — {sector_reason}\n\n"
                f"四策略扫描结果：\n{scan_text}\n\n"
                f"总命中：{total_hits}支。请选出最优1-5支，输出JSON。"
            )
        else:
            system = (
                "You are a US equity stock selection expert. Below are candidates from "
                "four different strategies. Select 1-5 best stocks across strategies.\n"
                "Evaluation criteria: technical strength, fundamental quality, "
                "strategy confirmation (bonus for multi-strategy hits), market cap / "
                "liquidity, sector fit.\n"
                "Output pure JSON, fields:\n"
                '  "selected": [\n'
                '    {"ticker":"NVDA","strategy":"Momentum","confidence":"High","reasoning":"..."}\n'
                '    ... (up to 5 stocks)\n'
                '  ],\n'
                '  "decision":  top pick ticker (uppercase, used as deep-dive input),\n'
                '  "runner_up": second-choice ticker (empty string if none),\n'
                '  "reasoning": one-paragraph cross-strategy rationale,\n'
                '  "summary":   one-line summary (include count and top pick)'
            )
            user = (
                f"Sector context: {sector_name} — {sector_reason}\n\n"
                f"Four-strategy scan results:\n{scan_text}\n\n"
                f"Total hits: {total_hits}. Select best 1-5 stocks and output JSON."
            )

        result = _llm_json_call(client, 2000, system, user)
        try:
            from translator import add_bilingual, add_bilingual_list
            result = add_bilingual(result, lang, ["reasoning", "summary"])
            selected = result.get("selected") or []
            if selected:
                result["selected"] = add_bilingual_list(selected, lang, ["reasoning"])
        except Exception:
            pass
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
