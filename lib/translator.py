"""Bilingual translation helpers using deep-translator (Google Translate).

After each LLM analysis call, invoke add_bilingual() to store both EN and ZH
versions of every text field.  Rendering code reads the appropriate language
with:

    from ui_utils import bi
    text = bi(llm_result, "reasoning", _lang)   # _lang = "en" | "zh"

Which expands to: llm.get(f"reasoning_{_lang}") or llm.get("reasoning") or ""
"""

import re

_LANG_CODE: dict[str, str] = {"en": "en", "zh": "zh-CN"}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    """Strip markdown code fences, stray backticks, and extra whitespace."""
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```", "", text)
    return text.strip()


def _translate_batch(texts: list[str], target_lang: str) -> list[str]:
    """
    Batch-translate a list of strings to target_lang ("en" or "zh").
    Returns the originals on any failure (graceful degradation).
    """
    if not texts:
        return texts
    code = _LANG_CODE.get(target_lang, "en")
    try:
        from deep_translator import GoogleTranslator
        results = GoogleTranslator(source="auto", target=code).translate_batch(texts)
        # translate_batch may return None for empty/unchanged strings
        return [r if isinstance(r, str) and r.strip() else t
                for r, t in zip(results, texts)]
    except Exception:
        return texts


# ── Public API ────────────────────────────────────────────────────────────────

def add_bilingual(result: dict, source_lang: str, text_fields: list[str]) -> dict:
    """
    Add {field}_en and {field}_zh for every field in text_fields.

    source_lang: language of the current values ("en" or "zh").
    The OTHER language is generated via Google Translate in one batch call.
    Returns a shallow copy of result with the extra *_en / *_zh keys appended.

    Non-string, empty, or "N/A" values are skipped.
    """
    if source_lang not in ("en", "zh"):
        return result

    target_lang = "zh" if source_lang == "en" else "en"

    originals: list[str] = []
    keys:      list[str] = []
    for f in text_fields:
        v = result.get(f)
        if isinstance(v, str) and v.strip() and v not in ("N/A", ""):
            originals.append(_clean(v))
            keys.append(f)

    translated = _translate_batch(originals, target_lang)

    updated = dict(result)
    for f, orig, trans in zip(keys, originals, translated):
        updated[f"{f}_{source_lang}"] = orig
        updated[f"{f}_{target_lang}"] = trans
    return updated


def add_bilingual_list(items: list[dict], source_lang: str,
                       text_fields: list[str]) -> list[dict]:
    """
    Like add_bilingual() but operates on a list of dicts (e.g. selected stocks).
    Translates all specified text fields across all items in one batch call.
    """
    if source_lang not in ("en", "zh") or not items:
        return items

    target_lang = "zh" if source_lang == "en" else "en"

    all_texts:   list[str]        = []
    all_indices: list[tuple]      = []   # (item_idx, field)

    for i, item in enumerate(items):
        for f in text_fields:
            v = item.get(f)
            if isinstance(v, str) and v.strip() and v not in ("N/A", ""):
                all_texts.append(_clean(v))
                all_indices.append((i, f))

    if not all_texts:
        return items

    translated = _translate_batch(all_texts, target_lang)

    result = [dict(item) for item in items]
    for (i, f), orig, trans in zip(all_indices, all_texts, translated):
        result[i][f"{f}_{source_lang}"] = orig
        result[i][f"{f}_{target_lang}"] = trans
    return result


def translate_str_list(texts: list[str], source_lang: str) -> dict[str, list[str]]:
    """
    Translate a list of strings from source_lang to the other language.
    Returns {"en": [...], "zh": [...]} with both language versions.
    """
    if source_lang not in ("en", "zh") or not texts:
        return {"en": texts, "zh": texts}

    target_lang = "zh" if source_lang == "en" else "en"
    clean_texts = [_clean(t) for t in texts]
    translated  = _translate_batch(clean_texts, target_lang)

    return {
        source_lang: clean_texts,
        target_lang: translated,
    }
