"""
Markdown report generation utilities.
Writes research reports to the research/ directory following project naming conventions.
"""

import textwrap
from datetime import datetime
from pathlib import Path

RESEARCH_DIR = Path(__file__).parent.parent / "research"


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _date_prefix() -> str:
    return datetime.now().strftime("%Y%m%d")


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def sector_report_path(sector_name: str) -> Path:
    slug = sector_name.lower().replace(" ", "_")
    return RESEARCH_DIR / "sector" / f"{_date_prefix()}_sector_{slug}.md"


def equity_report_path(ticker: str, report_type: str = "equity") -> Path:
    return RESEARCH_DIR / "stock" / f"{_date_prefix()}_{ticker.upper()}_{report_type}.md"


def scan_report_path(strategy: str) -> Path:
    slug = strategy.lower().replace(" ", "_")
    return RESEARCH_DIR / "scans" / f"{_date_prefix()}_scan_{slug}.md"


# ---------------------------------------------------------------------------
# Standard report header
# ---------------------------------------------------------------------------

def make_header(
    title: str,
    ticker_or_sector: str,
    agent_name: str,
    extra_fields: dict = None,
    lang: str = "en",
) -> str:
    _date_lbl    = "Date"           if lang == "en" else "日期"
    _ticker_lbl  = "Ticker / Sector" if lang == "en" else "代码 / 板块"
    _analyst_lbl = "Analyst Agent"  if lang == "en" else "分析师 Agent"
    lines = [
        f"# {title}",
        "",
        f"**{_date_lbl}**: {_today()}",
        f"**{_ticker_lbl}**: {ticker_or_sector}",
        f"**{_analyst_lbl}**: {agent_name}",
    ]
    if extra_fields:
        for k, v in extra_fields.items():
            lines.append(f"**{k}**: {v}")
    lines += ["", "---", ""]
    return "\n".join(lines)


def make_risk_footer(lang: str = "en") -> str:
    if lang == "en":
        return "\n\n---\n\n> **Disclaimer**: This report is for research purposes only and does not constitute investment advice. Markets involve risk; invest with caution.\n"
    return "\n\n---\n\n> **风险提示**：本报告仅供研究参考，不构成投资建议。市场有风险，投资须谨慎。\n"


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def write_report(path: Path, content: str) -> Path:
    """Write report content to path, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def write_equity_report(
    ticker: str,
    sections: dict[str, str],
    report_type: str = "equity",
    agent_name: str = "equity-research",
    extra_fields: dict = None,
    lang: str = "en",
) -> Path:
    """
    Build and write a standard equity report.

    sections: ordered dict of {section_title: section_body}
    lang: "en" or "zh" — controls report title and header labels
    Returns the written file path.
    """
    # Language-aware report type labels
    _type_labels = {
        "equity":         ("Equity Research",    "个股研究报告"),
        "financial":      ("Financial Analysis",  "财务分析报告"),
        "sector":         ("Sector Research",     "行业研究报告"),
        "price_volume":   ("Price & Volume",      "量价分析报告"),
        "overview":       ("Research Overview",   "综合研究报告"),
        "scan":           ("Stock Scan",          "选股扫描"),
    }
    _en_lbl, _zh_lbl = _type_labels.get(report_type, (report_type.replace("_", " ").title(), report_type))
    type_label = _en_lbl if lang == "en" else _zh_lbl

    company_name = sections.pop("company_name", ticker)
    title = f"{type_label}: {ticker.upper()} — {company_name}"

    parts = [make_header(title, ticker.upper(), agent_name, extra_fields, lang=lang)]
    for heading, body in sections.items():
        parts.append(f"## {heading}\n\n{body}\n")
    parts.append(make_risk_footer())

    content = "\n".join(parts)
    path = equity_report_path(ticker, report_type)
    return write_report(path, content)


# ---------------------------------------------------------------------------
# DataFrame → Markdown table
# ---------------------------------------------------------------------------

def df_to_md_table(df, float_fmt: str = "{:.2f}") -> str:
    """Convert a pandas DataFrame to a GitHub-flavored Markdown table."""
    import pandas as pd

    def fmt(v):
        if isinstance(v, float):
            return float_fmt.format(v)
        return str(v)

    header = "| " + " | ".join(str(c) for c in df.columns) + " |"
    sep = "| " + " | ".join("---" for _ in df.columns) + " |"
    rows = []
    for _, row in df.iterrows():
        rows.append("| " + " | ".join(fmt(v) for v in row) + " |")
    return "\n".join([header, sep] + rows)
