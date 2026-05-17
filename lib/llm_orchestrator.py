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

def _parse_json(text: str) -> dict:
    """Extract JSON from LLM response with multiple fallback strategies."""
    # Strategy 1: code-fenced JSON block
    m = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except Exception:
            pass
    # Strategy 2: first {...} block
    m = re.search(r"\{[\s\S]+\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            pass
    # Strategy 3: raw parse
    try:
        return json.loads(text.strip())
    except Exception:
        pass
    # Fallback: wrap raw text
    return {
        "decision": "N/A",
        "reasoning": text[:400],
        "summary": text[:150],
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


# ── Step 1: Sector Analysis ────────────────────────────────────────────────────

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

        resp = client.messages.create(
            model=_MODEL,
            max_tokens=600,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return _parse_json(resp.content[0].text)

    except Exception as e:
        return _fallback("sector", e)


# ── Step 2: Stock Scanner ──────────────────────────────────────────────────────

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

        resp = client.messages.create(
            model=_MODEL,
            max_tokens=600,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return _parse_json(resp.content[0].text)

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

        resp = client.messages.create(
            model=_MODEL,
            max_tokens=700,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return _parse_json(resp.content[0].text)

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

        resp = client.messages.create(
            model=_MODEL,
            max_tokens=600,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return _parse_json(resp.content[0].text)

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

        resp = client.messages.create(
            model=_MODEL,
            max_tokens=600,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return _parse_json(resp.content[0].text)

    except Exception as e:
        return _fallback("pv", e)


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

        resp = client.messages.create(
            model=_MODEL,
            max_tokens=900,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return _parse_json(resp.content[0].text)

    except Exception as e:
        return _fallback("synthesis", e)
