from __future__ import annotations

import gzip
from pathlib import Path
from typing import Iterable, List

try:
    from lxml import html as lxml_html  # type: ignore[import-not-found]
except Exception:  # pragma: no cover
    lxml_html = None


def _read_bytes(path: Path) -> bytes:
    if str(path).lower().endswith(".gz"):
        with gzip.open(path, "rb") as f:
            return f.read()
    return path.read_bytes()


def combine_hocr_files(input_paths: Iterable[Path], output_path: Path) -> None:
    """
    Combine per-page word-level hOCR HTML files into a single IA-style hOCR HTML
    containing multiple `.ocr_page` elements.

    This mirrors the shape IA commonly serves as `*_hocr.html` while letting the
    pipeline operate page-by-page internally.
    """
    if lxml_html is None:
        raise RuntimeError("hOCR combining requires lxml. Install it (pip install lxml) and retry.")

    input_paths = [Path(p).resolve() for p in input_paths]
    if not input_paths:
        raise ValueError("No input hOCR files provided to combine.")

    pages = []
    head_el = None
    for p in input_paths:
        doc = lxml_html.fromstring(_read_bytes(p))
        if head_el is None:
            maybe_head = doc.find(".//head")
            if maybe_head is not None:
                head_el = maybe_head
        for el in doc.iter():
            cls = el.get("class") or ""
            if "ocr_page" in cls.split():
                pages.append(el)

    if not pages:
        raise ValueError("No .ocr_page elements found across input hOCR files.")

    # Build a minimal combined document
    root = lxml_html.fromstring(b"<html><head></head><body></body></html>")
    if head_el is not None:
        head = root.find(".//head")
        if head is not None:
            for c in list(head):
                head.remove(c)
            for c in list(head_el):
                head.append(c)
    body = root.find(".//body")
    if body is None:
        raise RuntimeError("Failed to construct combined hOCR document (no <body>).")

    for p in pages:
        body.append(p)

    out = lxml_html.tostring(root, encoding="unicode", method="html")
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(out, encoding="utf-8")

