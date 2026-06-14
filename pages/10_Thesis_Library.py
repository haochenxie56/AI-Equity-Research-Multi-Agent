"""Page 10 — Thesis Library.

A library of manually-curated external research articles / interviews, extracted
into structured thesis cards (one LLM call per argument), stored as local JSON,
and browsed here. Two modes: **Library** (browse / manage cards) and **Ingest**
(upload → preview → extract → review → save).

ISOLATION: this page touches ONLY ``lib.thesis_ingestion`` + ``ui_utils``. It
imports nothing from the scoring / ranking / snapshot / anchor systems, and
nothing in those systems imports it. No paid API; no broker / order / execution
path; no execution-authorization flag is ever set.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "lib") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "lib"))

# Default backup folder: a sibling of the project root, e.g. for
# /home/u/projects/investment-agents → /home/u/projects/thesis_backup.
_DEFAULT_BACKUP_FOLDER = str(_REPO_ROOT.parent / "thesis_backup")

import streamlit as st

from ui_utils import apply_theme, bi, init_session, render_sidebar

from lib.thesis_ingestion import store, validator
from lib.thesis_ingestion.extractor import (
    ExtractionError,
    UnsupportedFormatError,
    extract_card,
    get_llm_client,
    get_theme_names,
    is_image_ext,
    preview_article,
    read_document,
)

st.set_page_config(page_title="Thesis Library", page_icon="📚", layout="wide")
apply_theme()
init_session()
render_sidebar()

_LANG = st.session_state.get("language", "en")


def _zh() -> bool:
    return st.session_state.get("language", "en") == "zh"


def _tx(en: str, zh: str) -> str:
    """Tiny local bilingual literal helper (page-only chrome strings)."""
    return zh if _zh() else en


# ── Badge helpers ─────────────────────────────────────────────────────────────
def _badge(text: str, color: str) -> str:
    return (
        f'<span style="display:inline-block;padding:2px 9px;border-radius:10px;'
        f'background:{color}22;color:{color};border:1px solid {color}55;'
        f'font-size:0.72rem;font-weight:600;margin-right:6px">{text}</span>'
    )


_HORIZON_COLOR = {"short": "#388bfd", "mid": "#d29922", "long": "#3fb950"}
_TIER_COLOR = {
    "fresh": "#3fb950", "aging": "#d29922", "expired": "#f85149",
    "not_applicable": "#8b949e",
}
_STATUS_COLOR = {"active": "#3fb950", "silenced": "#8b949e", "unavailable": "#f85149"}


# ── Categorisation (deterministic, no LLM) ────────────────────────────────────
def _card_tickers(card: dict) -> list[str]:
    tickers: list[str] = []
    for cc in card.get("core_claims") or []:
        tickers.extend(cc.get("related_tickers") or [])
    for sc in card.get("scenarios") or []:
        tickers.extend(sc.get("affected_tickers") or [])
    return sorted({str(t).upper() for t in tickers if str(t).strip()})


def _card_themes(card: dict) -> list[str]:
    themes: list[str] = []
    for cc in card.get("core_claims") or []:
        themes.extend(cc.get("related_themes") or [])
    for sc in card.get("scenarios") or []:
        themes.extend(sc.get("affected_themes") or [])
    return sorted({str(t) for t in themes if str(t).strip()})


def _theme_maps_to_gics(themes: list[str]) -> bool:
    """A theme 'maps to a GICS sector' if it is a recognised theme-basket name.

    (The curated theme baskets are the project's single sector/theme taxonomy.)
    """
    known = set(get_theme_names())
    return any(t in known for t in themes)


def categorize_card(card: dict) -> set[str]:
    """Return the set of category tabs a card belongs to.

    A card may appear in more than one tab when it has both tickers and themes.
    Falls back to 'macro' only when it qualifies for nothing else.
    """
    cats: set[str] = set()
    tickers = _card_tickers(card)
    themes = _card_themes(card)
    if tickers:
        cats.add("stock")
    if themes:
        cats.add("theme")
    if (card.get("source") or {}).get("doc_type") == "research_report" and _theme_maps_to_gics(themes):
        cats.add("sector")
    if not cats:
        cats.add("macro")
    return cats


# ── Backup folder helpers ─────────────────────────────────────────────────────
def _ensure_backup_folder(folder: str) -> None:
    """Create the backup folder if missing (show a one-time success message).

    The folder is auto-created rather than erroring, so a missing path is never a
    failure state.
    """
    if not folder:
        return
    p = Path(folder)
    if p.exists():
        return
    try:
        p.mkdir(parents=True, exist_ok=True)
        st.success(_tx("Backup folder created.", "已创建备份文件夹"))
    except Exception as exc:  # noqa: BLE001
        st.warning(_tx(f"Could not create backup folder: {exc}",
                       f"无法创建备份文件夹：{exc}"))


def _open_folder(folder: str) -> None:
    if not folder:
        return
    # The folder is auto-created during setup, but mkdir defensively so "open"
    # always targets an existing directory (no "folder does not exist" error).
    try:
        Path(folder).mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass
    try:
        import shutil
        import subprocess

        if sys.platform == "win32":
            os.startfile(folder)  # type: ignore[attr-defined]
        elif shutil.which("explorer.exe"):
            # WSL environment — open via Windows Explorer (always present in WSL2).
            subprocess.Popen(["explorer.exe", folder])
        elif shutil.which("xdg-open"):
            # Native Linux desktop environment.
            subprocess.Popen(["xdg-open", folder])
        else:
            st.info(
                f"无法自动打开文件夹，请手动访问：{folder}\n"
                f"WSL 路径对应 Windows 路径：\\\\wsl.localhost\\Ubuntu{folder}"
            )
    except Exception as exc:  # noqa: BLE001
        st.warning(_tx(f"Could not open folder: {exc}", f"无法打开文件夹：{exc}"))


def _write_backup(file_bytes: bytes, filename: str, doc_hash: str, folder: str) -> str:
    """Copy the uploaded file into the backup folder; return its absolute path.

    The original filename is preserved. On a name collision a ``doc_hash[:8]``
    suffix is appended to avoid clobbering an existing file. The folder is
    auto-created if missing. Returns "" if no folder is configured / on error.
    """
    if not folder:
        return ""
    p = Path(folder)
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # noqa: BLE001
        st.warning(_tx(f"Could not create backup folder: {exc}",
                       f"无法创建备份文件夹：{exc}"))
        return ""
    base = os.path.basename(filename or "doc") or "doc"
    dest = p / base
    if dest.exists():
        stem, suffix = os.path.splitext(base)
        dest = p / f"{stem}_{doc_hash[:8]}{suffix}"
    try:
        with open(dest, "wb") as fh:
            fh.write(file_bytes)
        return str(dest.resolve())
    except Exception as exc:  # noqa: BLE001
        st.warning(_tx(f"Backup write failed: {exc}", f"备份写入失败：{exc}"))
        return ""


# ═══════════════════════════════════════════════════════════════════════════════
# Header + mode selector
# ═══════════════════════════════════════════════════════════════════════════════
st.title("📚 " + _tx("Thesis Library", "研报论点库"))
st.caption(_tx(
    "Curated external research → structured thesis cards. Research-only; not investment advice.",
    "外部研报手动整理 → 结构化论点卡片。仅供研究，不构成投资建议。",
))

# ── Query-param deep links (e.g. from the Cockpit theme / signal cards) ──
# Pre-apply a ticker / theme filter, force Library mode, then clear the URL so it
# stays clean during later interactions. Done BEFORE the mode radio + filter
# widgets are instantiated so we never mutate a widget-bound key after creation.
_qp_ticker = (st.query_params.get("ticker", "") or "").upper().strip()
_qp_theme = (st.query_params.get("theme", "") or "").strip()
_qp_category = (st.query_params.get("category", "") or "").strip().lower()
if _qp_ticker or _qp_theme or _qp_category:
    st.session_state["thesis_force_mode"] = "library"
    if _qp_ticker:
        st.session_state["f_ticker"] = _qp_ticker
    if _qp_theme:
        st.session_state["f_theme"] = _qp_theme
    if _qp_category in ("macro", "sector", "theme", "stock"):
        # Consumed by the Library tab ordering so the requested category leads.
        st.session_state["thesis_active_category"] = _qp_category
    st.query_params.clear()

# A programmatic mode switch (e.g. Re-extract, or a query-param deep link) is
# applied here, BEFORE the radio widget is instantiated, so we never mutate a
# widget-bound key after creation.
if "thesis_force_mode" in st.session_state:
    st.session_state["thesis_mode"] = st.session_state.pop("thesis_force_mode")

_mode = st.radio(
    _tx("Mode", "模式"),
    options=["library", "ingest"],
    format_func=lambda m: _tx("Library", "卡片库") if m == "library" else _tx("Ingest", "录入"),
    horizontal=True,
    key="thesis_mode",
)


# ═══════════════════════════════════════════════════════════════════════════════
# LIBRARY MODE
# ═══════════════════════════════════════════════════════════════════════════════
def _render_card(card: dict, ctx: str = "") -> None:
    # ``ctx`` (the category tab) makes widget keys unique when one card appears
    # in more than one tab (e.g. it has both tickers and themes).
    cid = card.get("card_id", "")
    kp = f"{ctx}_{cid}"  # key prefix
    src = card.get("source") or {}
    status = card.get("card_status", "active")
    staleness = store.compute_staleness(card)
    active = store.compute_is_active(card, staleness)

    muted = status in ("silenced", "unavailable")
    border = "#30363d" if muted else "#3fb950" if active else "#8b949e"
    with st.container(border=True):
        # Header line
        title = src.get("title") or cid
        hdr = f"**{title}**" if not muted else f"_{title}_"
        st.markdown(hdr)

        badges = (
            _badge(_tx("horizon: ", "周期：") + card.get("horizon_type", "?"),
                   _HORIZON_COLOR.get(card.get("horizon_type"), "#8b949e"))
            + _badge(staleness["tier"], _TIER_COLOR.get(staleness["tier"], "#8b949e"))
            + _badge(status, _STATUS_COLOR.get(status, "#8b949e"))
            + _badge(_tx("active", "生效") if active else _tx("inactive", "未生效"),
                     "#3fb950" if active else "#8b949e")
        )
        st.markdown(badges, unsafe_allow_html=True)

        if staleness.get("show_aging_warning"):
            st.markdown(
                f"<span style='color:#d29922'>⚠ "
                + _tx("Aging — re-verify before relying on this thesis.",
                      "论点逐渐过期 —— 依赖前请重新验证。")
                + "</span>",
                unsafe_allow_html=True,
            )

        meta_bits = []
        if src.get("author") and src.get("author") != "unknown":
            meta_bits.append(src["author"])
        if src.get("publication_date"):
            meta_bits.append(_tx("published ", "发布 ") + str(src["publication_date"]))
        if src.get("ingested_at"):
            meta_bits.append(_tx("ingested ", "录入 ") + str(src["ingested_at"])[:10])
        if meta_bits:
            st.caption(" · ".join(meta_bits))

        # First core claim summary
        claims = card.get("core_claims") or []
        if claims:
            summary = bi(claims[0], "claim_text") or claims[0].get("claim_text_en", "")
            if summary:
                st.markdown(summary)

        tickers = _card_tickers(card)
        themes = _card_themes(card)
        tag_line = []
        if tickers:
            tag_line.append("🎯 " + ", ".join(tickers))
        if themes:
            tag_line.append("🏷 " + ", ".join(themes))
        if tag_line:
            st.caption(" | ".join(tag_line))

        with st.expander(_tx("Details", "详情")):
            if card.get("numeric_claims"):
                st.markdown("**" + _tx("Numeric claims", "数值论点") + "**")
                for nc in card["numeric_claims"]:
                    st.caption(
                        f"• {nc.get('metric','?')} = {nc.get('value')} {nc.get('unit','')} "
                        f"({nc.get('provenance','?')}) — {nc.get('source_quote','')}"
                    )
            if card.get("unspecified_numerics"):
                st.markdown("**" + _tx("Directional (no number)", "方向性（无数值）") + "**")
                for un in card["unspecified_numerics"]:
                    st.caption(f"• {un.get('metric','?')}: {un.get('direction','?')} — {un.get('note','')}")
            if card.get("assumptions"):
                st.markdown("**" + _tx("Assumptions", "关键假设") + "**")
                for a in card["assumptions"]:
                    st.caption(f"• {a}")
            for sc in card.get("scenarios") or []:
                _eoh = bi(sc, "event_or_hypothesis")
                if _eoh:
                    st.markdown("**" + _tx("Scenario", "情景") + f"**: {_eoh}")
                for stp in sc.get("transmission_chain") or []:
                    st.caption(
                        f"  ↳ {stp.get('from_node','')} → {stp.get('to_node','')}: "
                        f"{bi(stp, 'mechanism')} ({stp.get('provenance','')})"
                    )
                for cond in sc.get("confirmation_conditions") or []:
                    _ct = bi(cond, "condition_text")
                    if _ct:
                        st.caption(f"  ✓ {_ct} ({cond.get('observable','')}/{cond.get('provenance','')})")
                for cond in sc.get("falsification_conditions") or []:
                    _ct = bi(cond, "condition_text")
                    if _ct:
                        st.caption(f"  ✗ {_ct} ({cond.get('observable','')}/{cond.get('provenance','')})")
                _snotes = bi(sc, "notes")
                if _snotes:
                    st.caption(f"  — {_snotes}")

        # Action buttons
        cols = st.columns(3)
        if status == "silenced":
            if cols[0].button(_tx("Unsilence", "取消屏蔽"), key=f"unsil_{kp}"):
                store.update_card_status(cid, "active")
                st.rerun()
        elif status == "active":
            if cols[0].button(_tx("Silence", "屏蔽"), key=f"sil_{kp}"):
                store.update_card_status(cid, "silenced")
                st.rerun()
        if status == "unavailable":
            if cols[1].button("🗑 " + _tx("Delete", "删除"), key=f"del_{kp}", type="secondary"):
                store.delete_card(cid)
                st.rerun()
        if cols[2].button(_tx("Re-extract", "重新提取"), key=f"reext_{kp}"):
            st.session_state["thesis_reextract_path"] = src.get("doc_path", "")
            st.session_state["thesis_force_mode"] = "ingest"
            st.rerun()


if _mode == "library":
    cards = store.list_cards()

    # On load: flip any newly-unavailable cards (doc_path missing) to unavailable.
    for cid in store.scan_unavailable(cards):
        c = next((x for x in cards if x.get("card_id") == cid), None)
        if c and c.get("card_status") != "unavailable":
            store.update_card_status(cid, "unavailable")
            c["card_status"] = "unavailable"

    if not cards:
        st.info(_tx("No thesis cards yet. Switch to Ingest to add one.",
                    "暂无论点卡片。切换到“录入”以添加。"))
    else:
        # Filter bar
        fcols = st.columns([2, 2, 1])
        f_ticker = fcols[0].text_input(_tx("Filter by ticker", "按代码筛选"), key="f_ticker").upper().strip()
        all_themes = sorted({t for c in cards for t in _card_themes(c)})
        # Include any pre-applied theme (e.g. from a ?theme= deep link) in the
        # options even if no card references it yet, so the stored f_theme value
        # is always a valid selectbox option (otherwise Streamlit raises).
        _active_theme = st.session_state.get("f_theme", "(all)")
        _theme_opts = ["(all)"] + sorted(
            set(all_themes) | ({_active_theme} if _active_theme not in ("(all)", "") else set())
        )
        f_theme = fcols[1].selectbox(
            _tx("Filter by theme", "按主题筛选"),
            options=_theme_opts, key="f_theme",
        )
        f_status = fcols[2].selectbox(
            _tx("Status", "状态"),
            options=["active_only", "all"],
            format_func=lambda s: _tx("active only", "仅生效") if s == "active_only" else _tx("all", "全部"),
            key="f_status",
        )

        def _passes(card: dict) -> bool:
            if f_ticker and f_ticker not in _card_tickers(card):
                return False
            if f_theme != "(all)" and f_theme not in _card_themes(card):
                return False
            if f_status == "active_only":
                stale = store.compute_staleness(card)
                if not store.compute_is_active(card, stale):
                    return False
            return True

        shown = [c for c in cards if _passes(c)]

        # Streamlit has no API to programmatically select a tab, so a deep-linked
        # category (e.g. ?category=macro) is honoured by ordering that tab first
        # (the first tab is the default-active one).
        _cat_defs = [
            ("macro", _tx("Macro", "宏观")), ("sector", _tx("Sector", "行业")),
            ("theme", _tx("Theme", "主题")), ("stock", _tx("Stock", "个股")),
        ]
        _active_cat = st.session_state.get("thesis_active_category", "")
        if _active_cat in {k for k, _ in _cat_defs}:
            _cat_defs = sorted(_cat_defs, key=lambda kv: 0 if kv[0] == _active_cat else 1)
        tabs = st.tabs([lbl for _, lbl in _cat_defs])
        for tab, (key, _lbl) in zip(tabs, _cat_defs):
            with tab:
                bucket = [c for c in shown if key in categorize_card(c)]
                if not bucket:
                    st.caption(_tx("No cards in this category.", "该分类暂无卡片。"))
                for c in bucket:
                    _render_card(c, ctx=key)


# ═══════════════════════════════════════════════════════════════════════════════
# INGEST MODE
# ═══════════════════════════════════════════════════════════════════════════════
def _reset_ingest_state() -> None:
    for k in ("thesis_ing_filebytes", "thesis_ing_filename", "thesis_ing_hash",
              "thesis_ing_text", "thesis_ing_preview", "thesis_ing_extracted",
              "thesis_ing_doc_path", "thesis_ing_overwrite", "thesis_overwrite_pending"):
        st.session_state.pop(k, None)


if _mode == "ingest":
    st.subheader(_tx("Step 1 — Source file & backup", "步骤一 — 源文件与备份"))

    # Backup folder config (session_state mirror of persisted config.json).
    # First load: if nothing is configured yet, fall back to the default
    # (sibling of the project root), persist it immediately, and auto-create it.
    if "thesis_backup_folder" not in st.session_state:
        _saved = store.get_backup_folder()
        if not _saved:
            _saved = _DEFAULT_BACKUP_FOLDER
            store.set_backup_folder(_saved)
        st.session_state["thesis_backup_folder"] = _saved
        _ensure_backup_folder(_saved)

    bcols = st.columns([4, 1])
    folder = bcols[0].text_input(
        _tx("Backup folder (local copies of source docs)", "备份文件夹（源文档本地副本）"),
        value=st.session_state.get("thesis_backup_folder", ""),
        key="thesis_backup_folder_input",
    )
    if folder != st.session_state.get("thesis_backup_folder", ""):
        # User confirmed a (possibly new) path → persist and auto-create it.
        st.session_state["thesis_backup_folder"] = folder
        store.set_backup_folder(folder)
        _ensure_backup_folder(folder)
    _folder_set = bool((st.session_state.get("thesis_backup_folder", "") or "").strip())
    if bcols[1].button("📂 " + _tx("Open folder", "打开文件夹"),
                       disabled=not _folder_set):
        _open_folder(st.session_state.get("thesis_backup_folder", ""))

    reext = st.session_state.get("thesis_reextract_path")
    if reext:
        st.info(_tx(f"Re-extracting from backup: {reext}", f"从备份重新提取：{reext}"))
        if os.path.isfile(reext) and st.button(_tx("Load backup file", "加载备份文件")):
            with open(reext, "rb") as fh:
                fb = fh.read()
            st.session_state["thesis_ing_filebytes"] = fb
            st.session_state["thesis_ing_filename"] = os.path.basename(reext)
            st.session_state["thesis_ing_hash"] = store.compute_doc_hash(fb)
            st.session_state["thesis_ing_doc_path"] = reext
            st.session_state.pop("thesis_reextract_path", None)
            st.rerun()

    uploaded = st.file_uploader(
        _tx("Upload document", "上传文档"),
        type=["pdf", "txt", "md", "docx", "pptx"],
        key="thesis_uploader",
    )
    if uploaded is not None:
        if is_image_ext(uploaded.name):
            # Friendly, non-fatal message — never a raw exception for images.
            st.error(_tx(
                "Image formats are not supported. Please provide a text document "
                "(PDF, Word, TXT, etc.).",
                "图片格式暂不支持，请提供文字版文档（PDF、Word、TXT 等）",
            ))
        else:
            fb = uploaded.getvalue()
            _dh = store.compute_doc_hash(fb)
            # Only (re)process + auto-backup when a genuinely NEW file is uploaded
            # (by content hash), so reruns don't write duplicate backup copies.
            if st.session_state.get("thesis_ing_hash") != _dh:
                st.session_state["thesis_ing_filebytes"] = fb
                st.session_state["thesis_ing_filename"] = uploaded.name
                st.session_state["thesis_ing_hash"] = _dh
                # Auto-save the upload to the configured backup folder immediately.
                _folder = st.session_state.get("thesis_backup_folder", "")
                _saved_path = _write_backup(fb, uploaded.name, _dh, _folder)
                st.session_state["thesis_ing_doc_path"] = _saved_path or ""
                st.session_state.pop("thesis_ing_text", None)
                st.session_state.pop("thesis_ing_preview", None)
                st.session_state.pop("thesis_ing_extracted", None)

    file_bytes = st.session_state.get("thesis_ing_filebytes")
    filename = st.session_state.get("thesis_ing_filename", "")
    doc_hash = st.session_state.get("thesis_ing_hash", "")

    if file_bytes:
        existing = store.check_existing_by_hash(doc_hash)
        proceed = True
        if existing and not st.session_state.get("thesis_ing_overwrite"):
            st.warning(_tx(
                f"This document has already been ingested (card ID: {existing.get('card_id')}). "
                "Do you want to re-extract and overwrite?",
                f"该文档已被录入（卡片 ID：{existing.get('card_id')}）。是否重新提取并覆盖？",
            ))
            wc = st.columns(2)
            if wc[0].button(_tx("Confirm overwrite", "确认覆盖"), key="ow_confirm"):
                st.session_state["thesis_ing_overwrite"] = True
                st.rerun()
            if wc[1].button(_tx("Cancel", "取消"), key="ow_cancel"):
                _reset_ingest_state()
                st.rerun()
            proceed = False

        if proceed:
            st.caption(f"`{filename}` · sha256 `{doc_hash[:16]}…`")

            # Read text (cache in session).
            if "thesis_ing_text" not in st.session_state:
                try:
                    st.session_state["thesis_ing_text"] = read_document(file_bytes, filename)
                except UnsupportedFormatError as exc:
                    st.error(str(exc))
                    st.session_state["thesis_ing_text"] = ""
                except Exception as exc:  # noqa: BLE001 — show a clean message, not a traceback
                    st.error(_tx(f"Could not read the document: {exc}",
                                 f"无法读取文档：{exc}"))
                    st.session_state["thesis_ing_text"] = ""
            file_text = st.session_state.get("thesis_ing_text", "")

            st.subheader(_tx("Step 2 — Preview arguments", "步骤二 — 预览论点"))
            if file_text and st.button(_tx("Analyze arguments", "分析论点"), key="do_preview"):
                try:
                    with st.spinner(_tx("Calling LLM…", "调用 LLM…")):
                        st.session_state["thesis_ing_preview"] = preview_article(
                            file_text, get_llm_client()
                        )
                except (ExtractionError, Exception) as exc:  # noqa: BLE001
                    st.error(_tx(f"Preview failed: {exc}", f"预览失败：{exc}"))

            preview = st.session_state.get("thesis_ing_preview")
            if preview:
                args = preview.get("arguments") or []
                title_en = preview.get("article_title_en", "")
                title_zh = preview.get("article_title_zh", "")
                language = preview.get("article_language", "en")
                st.caption(_tx(f"Title: {title_en}", f"标题：{title_zh or title_en}")
                           + f" · lang={language}")

                selections = []
                for arg in args:
                    idx = arg.get("index")
                    with st.container(border=True):
                        c = st.columns([0.5, 4, 1.5])
                        chosen = c[0].checkbox("", value=True, key=f"arg_sel_{idx}")
                        headline = bi(arg, "headline") or arg.get("headline_en", "")
                        c[1].markdown(f"**#{idx}** {headline}")
                        tk = ", ".join(arg.get("primary_tickers") or [])
                        th = ", ".join(arg.get("primary_themes") or [])
                        if tk or th:
                            c[1].caption((f"🎯 {tk}  " if tk else "") + (f"🏷 {th}" if th else ""))
                        sugg = arg.get("suggested_horizon", "mid")
                        opts = ["short", "mid", "long"]
                        hz = c[2].selectbox(
                            _tx("horizon", "周期"), options=opts,
                            index=opts.index(sugg) if sugg in opts else 1,
                            key=f"arg_hz_{idx}",
                        )
                        if chosen:
                            selections.append((arg, hz))

                if selections and st.button(_tx("Extract selected", "提取所选"), key="do_extract"):
                    folder = st.session_state.get("thesis_backup_folder", "")
                    doc_path = st.session_state.get("thesis_ing_doc_path") or _write_backup(
                        file_bytes, filename, doc_hash, folder
                    )
                    # extraction_seq: 1 unless overwriting an existing doc_hash.
                    seq = 1
                    doc_meta = {
                        "doc_hash": doc_hash,
                        "doc_path": doc_path,
                        "doc_type": "research_report" if language == "en" else "article",
                        "author": "unknown",
                        "author_affiliation": "unknown",
                        "publication_date": None,
                        "publication_date_provenance": "unspecified",
                        "language": language if language in ("zh", "en", "mixed") else "en",
                        "title": title_en or filename,
                    }
                    extracted = []
                    client = None
                    try:
                        client = get_llm_client()
                    except Exception as exc:  # noqa: BLE001
                        st.error(_tx(f"LLM client error: {exc}", f"LLM 客户端错误：{exc}"))
                    if client is not None:
                        with st.spinner(_tx("Extracting cards…", "提取卡片中…")):
                            for arg, hz in selections:
                                try:
                                    card = extract_card(
                                        file_text, arg.get("index"),
                                        arg.get("headline_en", ""), hz, doc_meta,
                                        client, extraction_seq=seq,
                                    )
                                    extracted.append(card)
                                    seq += 1
                                except Exception as exc:  # noqa: BLE001
                                    st.error(_tx(
                                        f"Argument #{arg.get('index')} failed: {exc}",
                                        f"论点 #{arg.get('index')} 提取失败：{exc}",
                                    ))
                        st.session_state["thesis_ing_extracted"] = extracted

            # ── Step 3 — review & confirm ──
            extracted = st.session_state.get("thesis_ing_extracted")
            if extracted:
                st.subheader(_tx("Step 3 — Review & save", "步骤三 — 审阅与保存"))
                for i, card in enumerate(extracted):
                    is_valid, errs = validator.validate_card(card)
                    with st.container(border=True):
                        st.markdown(f"**{card.get('card_id')}** · "
                                    f"{card.get('horizon_type')} · "
                                    f"{len(card.get('core_claims') or [])} "
                                    + _tx("claims", "论点"))
                        for cc in card.get("core_claims") or []:
                            st.markdown("• " + (bi(cc, "claim_text") or cc.get("claim_text_en", "")))
                        if card.get("numeric_claims"):
                            for nc in card["numeric_claims"]:
                                st.caption(f"📊 {nc.get('metric')} = {nc.get('value')} "
                                           f"{nc.get('unit','')} ({nc.get('provenance')})")
                        if not is_valid:
                            st.error(_tx("Validation errors — cannot save:", "校验错误 —— 无法保存："))
                            for e in errs:
                                st.markdown(f"  - `{e}`")
                        else:
                            cid = card.get("card_id")
                            overwrite = bool(st.session_state.get("thesis_ing_overwrite"))
                            pending = st.session_state.get("thesis_overwrite_pending") == cid
                            if st.button(_tx("Confirm & Save", "确认并保存"),
                                         key=f"save_{i}_{cid}"):
                                try:
                                    store.save_card(card, overwrite=overwrite)
                                    store.append_ingest_log({
                                        "doc_hash": card["source"]["doc_hash"],
                                        "card_id": cid,
                                        "timestamp": datetime.now().isoformat(timespec="seconds"),
                                        "action": "overwritten" if overwrite else "created",
                                    })
                                    st.session_state.pop("thesis_overwrite_pending", None)
                                    # Reset so the next upload of the same document
                                    # shows the warning again (not a silent overwrite).
                                    st.session_state["thesis_ing_overwrite"] = False
                                    st.success(_tx(
                                        f"Saved {cid} ({'overwritten' if overwrite else 'created'}).",
                                        f"已保存 {cid}（{'overwritten' if overwrite else 'created'}）。",
                                    ))
                                except store.CardExistsError:
                                    # No silent overwrite — flag and require a second,
                                    # separate explicit confirmation from the user.
                                    st.session_state["thesis_overwrite_pending"] = cid
                                    st.rerun()
                            if pending:
                                st.warning(_tx(
                                    f"A card for this document already exists (card ID: {cid}). "
                                    "Click 'Confirm Overwrite' to replace it.",
                                    f"该文档的卡片已存在（卡片 ID：{cid}）。点击“确认覆盖”以替换。",
                                ))
                                if st.button(_tx("Confirm Overwrite", "确认覆盖"),
                                             key=f"ow_save_{i}_{cid}"):
                                    store.save_card(card, overwrite=True)
                                    store.append_ingest_log({
                                        "doc_hash": card["source"]["doc_hash"],
                                        "card_id": cid,
                                        "timestamp": datetime.now().isoformat(timespec="seconds"),
                                        "action": "overwritten",
                                    })
                                    st.session_state.pop("thesis_overwrite_pending", None)
                                    # Reset so the next upload of the same document
                                    # shows the warning again (not a silent overwrite).
                                    st.session_state["thesis_ing_overwrite"] = False
                                    st.success(_tx(f"Overwrote {cid}.", f"已覆盖 {cid}。"))

    if file_bytes and st.button(_tx("Reset ingest", "重置录入"), key="reset_ingest"):
        _reset_ingest_state()
        st.session_state.pop("thesis_reextract_path", None)
        st.rerun()
