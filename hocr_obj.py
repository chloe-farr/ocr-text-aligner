from __future__ import annotations

import gzip
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional

import xml_obj as XMLOBJ

try:
    from lxml import html as lxml_html  # type: ignore[import-not-found]
except Exception as e:  # pragma: no cover
    lxml_html = None


_BBOX_RE = re.compile(r"\bbbox\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\b")
_WCONF_RE = re.compile(r"\bx_wconf\s+(\d+)\b")


def _read_bytes(path: Path) -> bytes:
    if str(path).lower().endswith(".gz"):
        with gzip.open(path, "rb") as f:
            return f.read()
    return path.read_bytes()


def _parse_title_bbox(title: str) -> Optional[tuple[int, int, int, int]]:
    if not title:
        return None
    m = _BBOX_RE.search(title)
    if not m:
        return None
    x0, y0, x1, y1 = (int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)))
    return (x0, y0, x1, y1)


def _parse_title_wconf(title: str) -> Optional[int]:
    if not title:
        return None
    m = _WCONF_RE.search(title)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _has_class(el, cls: str) -> bool:
    c = el.get("class") or ""
    parts = {p for p in c.split() if p}
    return cls in parts


def _iter_by_class(root, cls: str) -> Iterator:
    # Keep in DOM order
    for el in root.iter():
        if _has_class(el, cls):
            yield el


def _first_by_class(root, cls: str):
    for el in _iter_by_class(root, cls):
        return el
    return None


def _all_by_class(root, cls: str) -> list:
    return list(_iter_by_class(root, cls))


def _text_of(el) -> str:
    # lxml html elements support text_content(); fall back to joining itertext()
    if hasattr(el, "text_content"):
        txt = el.text_content()
    else:  # pragma: no cover
        txt = "".join(el.itertext())
    return " ".join((txt or "").split())


def load_pages_from_file(path: str) -> list[XMLOBJ.Page]:
    """
    Parse an hOCR HTML/HTML.GZ and return a list of Page objects compatible with xml_obj's model.

    IA-friendly assumption: word-level hOCR contains .ocr_page, .ocr_line, .ocrx_word with bbox and x_wconf in @title.
    """
    if lxml_html is None:
        raise RuntimeError("hOCR parsing requires lxml. Install it (pip install lxml) and retry.")

    p = Path(path).resolve()
    raw = _read_bytes(p)
    doc = lxml_html.fromstring(raw)

    page_els = _all_by_class(doc, "ocr_page")
    if not page_els:
        # Some hOCR has a single page without explicit class; be forgiving.
        maybe = _first_by_class(doc, "ocrx_word")
        if maybe is None:
            raise ValueError("No hOCR pages/words found (missing .ocr_page/.ocrx_word).")
        page_els = [doc]

    pages: list[XMLOBJ.Page] = []
    for page_idx, page_el in enumerate(page_els, start=1):
        page_title = page_el.get("title") or ""
        pb = _parse_title_bbox(page_title) or (0, 0, 0, 0)
        _, _, x1, y1 = pb
        page = XMLOBJ.Page(
            id=f"PAGE_{page_idx:03d}",
            width=int(x1),
            height=int(y1),
            physical_img_nr=page_idx,
            content_elements=[],
        )

        careas = _all_by_class(page_el, "ocr_carea")
        if not careas:
            careas = [page_el]

        block_num = 0
        for carea in careas:
            block_num += 1
            carea_title = carea.get("title") or ""
            cb = _parse_title_bbox(carea_title) or (0, 0, 0, 0)
            x0, y0, x1b, y1b = cb
            block = XMLOBJ.TextBlock(
                id=f"BLOCK_{block_num:03d}",
                width=max(0, int(x1b - x0)),
                height=max(0, int(y1b - y0)),
                hpos=int(x0),
                vpos=int(y0),
                content_elements=[],
            )

            lines = _all_by_class(carea, "ocr_line")
            if not lines:
                lines = [carea]

            line_num = 0
            for line_el in lines:
                line_num += 1
                line_title = line_el.get("title") or ""
                lb = _parse_title_bbox(line_title) or (0, 0, 0, 0)
                lx0, ly0, lx1, ly1 = lb
                line = XMLOBJ.TextLine(
                    id=f"LINE_{block_num:03d}_{line_num:03d}",
                    width=max(0, int(lx1 - lx0)),
                    height=max(0, int(ly1 - ly0)),
                    hpos=int(lx0),
                    vpos=int(ly0),
                    content_elements=[],
                )

                words = _all_by_class(line_el, "ocrx_word")
                if not words and line_el is carea:
                    # Fallback: if we used the carea as a line, pull words from it.
                    words = _all_by_class(carea, "ocrx_word")

                word_num = 0
                for w_el in words:
                    word_num += 1
                    w_title = w_el.get("title") or ""
                    wb = _parse_title_bbox(w_title)
                    if wb is None:
                        continue
                    wx0, wy0, wx1, wy1 = wb
                    wc = _parse_title_wconf(w_title)
                    text = _text_of(w_el)
                    if text == "":
                        continue

                    word = XMLOBJ.StringWord(
                        id=f"WORD_{block_num:03d}_{line_num:03d}_{word_num:03d}",
                        width=max(0, int(wx1 - wx0)),
                        height=max(0, int(wy1 - wy0)),
                        hpos=int(wx0),
                        vpos=int(wy0),
                        content=text,
                        wc=int(wc) if wc is not None else 0,
                    )
                    line.content_elements.append(word)

                if line.content_elements:
                    block.content_elements.append(line)

            if block.content_elements:
                page.content_elements.append(block)

        pages.append(page)

    return pages


def load_first_page(path: str) -> XMLOBJ.Page:
    pages = load_pages_from_file(path)
    if not pages:
        raise ValueError("No <Page> found in hOCR file.")
    return pages[0]

