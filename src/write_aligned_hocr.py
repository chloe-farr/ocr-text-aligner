from __future__ import annotations

import gzip
import re
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set

import alignment_confidence
import text_utils

try:
    from lxml import html as lxml_html  # type: ignore[import-not-found]
except Exception:  # pragma: no cover
    lxml_html = None


_BBOX_RE = re.compile(r"\bbbox\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\b")


def _read_bytes(path: Path) -> bytes:
    if str(path).lower().endswith(".gz"):
        with gzip.open(path, "rb") as f:
            return f.read()
    return path.read_bytes()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _has_class(el, cls: str) -> bool:
    c = el.get("class") or ""
    parts = {p for p in c.split() if p}
    return cls in parts


def _iter_by_class(root, cls: str) -> Iterator:
    for el in root.iter():
        if _has_class(el, cls):
            yield el


def _all_by_class(root, cls: str) -> list:
    return list(_iter_by_class(root, cls))


def _parse_bbox(title: str) -> Optional[tuple[int, int, int, int]]:
    if not title:
        return None
    m = _BBOX_RE.search(title)
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))


def _iter_word_elements_in_page_order(doc) -> Iterator:
    """
    Yield .ocrx_word elements in a stable reading/DOM order that matches hocr_obj's ID assignment:
      ocr_page -> (ocr_carea*) -> (ocr_line*) -> (ocrx_word*)
    """
    pages = _all_by_class(doc, "ocr_page")
    if not pages:
        pages = [doc]

    for page_el in pages:
        careas = _all_by_class(page_el, "ocr_carea") or [page_el]
        for carea in careas:
            lines = _all_by_class(carea, "ocr_line") or [carea]
            for line_el in lines:
                words = _all_by_class(line_el, "ocrx_word")
                if not words and line_el is carea:
                    words = _all_by_class(carea, "ocrx_word")
                for w in words:
                    yield w


def _id_to_hypothesis_lists(hypothesis_list: List[Any]) -> Dict[str, List[Any]]:
    """
    Map OCR word id -> hypotheses sharing that id.

    Each hypothesis is appended once per word id even when anchor id equals the single
    alto_word id (1:1 match); otherwise the writer treats it as a split and doubles text.
    """
    id_to_hyps: Dict[str, List[Any]] = {}
    for hyp in hypothesis_list:
        seen_ids: Set[str] = set()
        word_ids: List[str] = [hyp.anchor.id]
        if hyp.chosen and getattr(hyp.chosen, "alto_words", None):
            word_ids.extend(w.id for w in hyp.chosen.alto_words)
        for wid in word_ids:
            if wid in seen_ids:
                continue
            seen_ids.add(wid)
            id_to_hyps.setdefault(wid, []).append(hyp)
    return id_to_hyps


def _build_id_to_content(hypothesis_list: List[Any]) -> Dict[str, str]:
    """
    Map each original word id -> output content.

    - For normal 1:1, use chosen LLM token if present.
    - For merges (candidate spans multiple words), place merged token on the first word id in that span and blank the rest.
    - For split cases (multiple hypotheses share the same anchor id), join chosen tokens with spaces onto that anchor.
    """
    id_to_hyps = _id_to_hypothesis_lists(hypothesis_list)

    id_to_content: Dict[str, str] = {}

    # First handle explicit merges: chosen.alto_words spans > 1
    for hyp in hypothesis_list:
        if not hyp.chosen or not getattr(hyp.chosen, "alto_words", None):
            continue
        words = hyp.chosen.alto_words
        if len(words) < 2:
            continue

        merged = hyp.chosen_LLM_token.word if hyp.chosen_LLM_token else text_utils.decode_html_entities(words[0].content)
        first_id = words[0].id
        id_to_content[first_id] = merged
        for w in words[1:]:
            id_to_content[w.id] = ""

    # Then fill everything else
    for wid, hyps in id_to_hyps.items():
        if wid in id_to_content:
            continue
        if len(hyps) == 1:
            hyp = hyps[0]
            id_to_content[wid] = hyp.chosen_LLM_token.word if hyp.chosen_LLM_token else text_utils.decode_html_entities(hyp.anchor.content)
        else:
            # Multiple hyps mapped to same id (e.g. split). Preserve text even if geometry can't represent it.
            parts: List[str] = []
            for hyp in hyps:
                if hyp.chosen_LLM_token and hyp.chosen_LLM_token.word:
                    parts.append(hyp.chosen_LLM_token.word)
            if parts:
                id_to_content[wid] = " ".join(parts)
            else:
                id_to_content[wid] = text_utils.decode_html_entities(hyps[0].anchor.content)

    return id_to_content


def _build_id_to_clean_para(hypothesis_list: List[Any]) -> Dict[str, int]:
    """Map each original word id -> clean-text paragraph index (0-based), when matched."""
    id_to_hyps = _id_to_hypothesis_lists(hypothesis_list)

    id_to_para: Dict[str, int] = {}
    for wid, hyps in id_to_hyps.items():
        if not hyps:
            continue
        tok = hyps[0].chosen_LLM_token
        if tok is not None and tok.clean_para_id is not None:
            id_to_para[wid] = int(tok.clean_para_id)
    return id_to_para


def _build_id_to_align_conf(hypothesis_list: List[Any]) -> Dict[str, int]:
    """Map each original word id -> alignment confidence (0–100)."""
    id_to_hyps = _id_to_hypothesis_lists(hypothesis_list)

    id_to_conf: Dict[str, int] = {}
    for wid, hyps in id_to_hyps.items():
        if not hyps:
            continue
        id_to_conf[wid] = alignment_confidence.alignment_confidence(hyps[0])
    return id_to_conf


def _append_cleanpara_to_title(title: Optional[str], clean_para_id: int) -> str:
    """Append `cleanpara N` to hOCR title; avoid duplicating if already present."""
    t = (title or "").strip()
    low = t.lower()
    if "cleanpara" in low:
        return t
    suffix = f"cleanpara {int(clean_para_id)}"
    if t:
        return f"{t}; {suffix}"
    return suffix


def _append_alignconf_to_title(title: Optional[str], align_conf: int) -> str:
    """Append `alignconf N` to hOCR title; avoid duplicating if already present."""
    t = (title or "").strip()
    low = t.lower()
    if "alignconf" in low:
        return t
    suffix = f"alignconf {max(0, min(100, int(align_conf)))}"
    if t:
        return f"{t}; {suffix}"
    return suffix


def write_aligned_hocr(
    hocr_path: str,
    page: Any,
    hypothesis_list: List[Any],
    output_path: str,
) -> None:
    """
    Update a word-level hOCR file by rewriting the text inside .ocrx_word spans.

    Minimal IA-friendly output: keeps existing bbox/title metadata intact and only changes word text.
    """
    if lxml_html is None:
        raise RuntimeError("hOCR writing requires lxml. Install it (pip install lxml) and retry.")

    src = Path(hocr_path).resolve()
    raw = _read_bytes(src)
    doc = lxml_html.fromstring(raw)

    id_to_content = _build_id_to_content(hypothesis_list)
    id_to_align_conf = _build_id_to_align_conf(hypothesis_list)
    id_to_clean_para = _build_id_to_clean_para(hypothesis_list)
    words_in_model = page.all_strings()
    words_in_html = list(_iter_word_elements_in_page_order(doc))

    # Update by index to avoid needing stable element IDs in the input.
    n = min(len(words_in_model), len(words_in_html))
    for i in range(n):
        w_model = words_in_model[i]
        w_el = words_in_html[i]
        new_text = id_to_content.get(w_model.id, text_utils.decode_html_entities(w_model.content))
        ac = id_to_align_conf.get(
            w_model.id,
            max(0, min(100, int(round(getattr(w_model, "wc", 0) * 0.35)))),
        )
        prev_title = w_el.get("title")
        t = _append_alignconf_to_title(prev_title, ac)
        cpid = id_to_clean_para.get(w_model.id)
        if cpid is not None:
            t = _append_cleanpara_to_title(t, cpid)
        w_el.set("title", t)
        # Ensure the span is plain text; drop any child nodes
        for child in list(w_el):
            w_el.remove(child)
        w_el.text = new_text

    out = lxml_html.tostring(doc, encoding="unicode", method="html")
    _write_text(Path(output_path).resolve(), out)

