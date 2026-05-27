#!/usr/bin/env python3
"""
Build a new PDF from the original PDF or a single PNG and aligned ALTO XML.

Compiles like Tesseract's pdf output: raw page image + invisible text layer
(PDF text render mode 3). No drawing on the image; no visible text. Requires:
pdftoppm (for --pdf), Pillow, reportlab; for --tesseract-pdf, tesseract.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

try:
    import xml_obj
except ImportError:
    xml_obj = None  # type: ignore

try:
    import hocr_obj
except ImportError:
    hocr_obj = None  # type: ignore

try:
    from PIL import Image
except ImportError:
    Image = None  # type: ignore

try:
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
except ImportError:
    canvas = ImageReader = None  # type: ignore


def _check_pdftoppm() -> bool:
    return shutil.which("pdftoppm") is not None


def _check_tesseract() -> bool:
    return shutil.which("tesseract") is not None


def pdf_to_images(pdf_path: Path, work_dir: Path, dpi: int = 300) -> List[Path]:
    """Render PDF pages to PNGs. Returns list of image paths in order."""
    base = work_dir / "page"
    result = subprocess.run(
        ["pdftoppm", "-png", "-r", str(dpi), str(pdf_path), str(base)],
        cwd=str(work_dir),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftoppm failed: {result.stderr or result.stdout}")
    images = sorted(work_dir.glob("page-*.png"), key=lambda p: (len(p.stem), p.stem))
    return images


def build_pdf_tesseract(image_path: Path, output_path: Path, lang: str = "eng") -> None:
    """Use Tesseract's native PDF output: image + searchable text layer from OCR. Does not use ALTO."""
    if not _check_tesseract():
        raise RuntimeError("tesseract not found. Install it (e.g. brew install tesseract).")
    image_path = Path(image_path).resolve()
    output_path = Path(output_path).resolve()
    if not image_path.is_file():
        raise FileNotFoundError(f"Image not found: {image_path}")
    with tempfile.TemporaryDirectory(prefix="make_cleaned_pdf_") as tmp:
        work = Path(tmp)
        base = work / "out"
        result = subprocess.run(
            ["tesseract", str(image_path), str(base), "-l", lang, "pdf"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"tesseract pdf failed: {result.stderr or result.stdout}")
        pdf_from_tesseract = work / "out.pdf"
        if not pdf_from_tesseract.is_file():
            raise RuntimeError("tesseract did not produce out.pdf")
        shutil.copy2(pdf_from_tesseract, output_path)


def build_pdf(
    aligned_xml_path: Path,
    output_path: Path,
    pdf_path: Optional[Path] = None,
    image_path: Optional[Path] = None,
    dpi: int = 300,
    font_path: Optional[str] = None,
) -> None:
    """Build PDF like Tesseract: raw page image + invisible text layer (render mode 3)."""
    if xml_obj is None:
        raise RuntimeError("xml_obj not available. Run from repo root: python make_cleaned_pdf.py ...")
    if canvas is None or ImageReader is None:
        raise RuntimeError("reportlab is required. Install with: pip install reportlab")
    if pdf_path is None and image_path is None:
        raise ValueError("Provide either --pdf or --image.")
    if pdf_path is not None and image_path is not None:
        raise ValueError("Provide only one of --pdf or --image.")

    aligned_xml_path = Path(aligned_xml_path).resolve()
    output_path = Path(output_path).resolve()
    if not aligned_xml_path.is_file():
        raise FileNotFoundError(f"Aligned ALTO not found: {aligned_xml_path}")

    pages = xml_obj.load_pages_from_file(str(aligned_xml_path))
    if not pages:
        raise ValueError("No pages found in aligned ALTO file.")

    page_data: List[tuple] = []  # (PIL Image, xml_obj.Page)

    if image_path is not None:
        image_path = Path(image_path).resolve()
        if not image_path.is_file():
            raise FileNotFoundError(f"Image not found: {image_path}")
        if len(pages) != 1:
            raise ValueError("When using --image, aligned ALTO must have exactly one page.")
        if Image is None:
            raise RuntimeError("Pillow is required. Install with: pip install Pillow")
        raw = Image.open(image_path).convert("RGB")
        page_data.append((raw, pages[0]))
    else:
        pdf_path = Path(pdf_path).resolve()  # type: ignore[assignment]
        if not pdf_path.is_file():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        if not _check_pdftoppm():
            raise RuntimeError("pdftoppm not found. Install poppler (e.g. brew install poppler).")
        with tempfile.TemporaryDirectory(prefix="make_cleaned_pdf_") as tmp:
            work = Path(tmp)
            all_images = pdf_to_images(pdf_path, work, dpi=dpi)
            if len(all_images) < len(pages):
                raise ValueError(
                    f"PDF has fewer pages ({len(all_images)}) than ALTO ({len(pages)}). "
                    "Use a PDF with at least as many pages as the aligned ALTO."
                )
            for img_path, page in zip(all_images[: len(pages)], pages):
                if Image is None:
                    raise RuntimeError("Pillow is required. Install with: pip install Pillow")
                raw = Image.open(img_path).convert("RGB")
                page_data.append((raw, page))

    # Compile like Tesseract: image then invisible text layer (render mode 3)
    c = canvas.Canvas(str(output_path))
    for pil_img, page in page_data:
        w_px, h_px = pil_img.size
        w_pt = w_px * 72 / dpi
        h_pt = h_px * 72 / dpi
        c.setPageSize((w_pt, h_pt))
        c.drawImage(ImageReader(pil_img), 0, 0, width=w_pt, height=h_pt)
        t = c.beginText()
        t.setTextRenderMode(3)  # invisible, same as Tesseract pdf output
        for w in page.all_strings():
            if not w.content or w.height <= 0:
                continue
            x_pt = w.hpos * 72 / dpi
            font_size_pt = max(6, min((w.height * 72 / dpi) * 0.85, 72))
            y_baseline_pt = (h_px - w.vpos - w.height * 0.85) * 72 / dpi
            t.setFont("Helvetica", font_size_pt)
            t.setTextOrigin(x_pt, y_baseline_pt)
            t.textOut(w.content)
        c.drawText(t)
        c.showPage()
    c.save()


def build_pdf_from_hocr(
    aligned_hocr_path: Path,
    output_path: Path,
    pdf_path: Optional[Path] = None,
    image_path: Optional[Path] = None,
    dpi: int = 300,
    font_path: Optional[str] = None,
) -> None:
    """Build PDF like Tesseract: raw page image + invisible text layer from word-level hOCR."""
    if hocr_obj is None:
        raise RuntimeError("hocr_obj not available. Run from repo root: python make_cleaned_pdf.py ...")
    if canvas is None or ImageReader is None:
        raise RuntimeError("reportlab is required. Install with: pip install reportlab")
    if pdf_path is None and image_path is None:
        raise ValueError("Provide either --pdf or --image.")
    if pdf_path is not None and image_path is not None:
        raise ValueError("Provide only one of --pdf or --image.")

    aligned_hocr_path = Path(aligned_hocr_path).resolve()
    output_path = Path(output_path).resolve()
    if not aligned_hocr_path.is_file():
        raise FileNotFoundError(f"Aligned hOCR not found: {aligned_hocr_path}")

    pages = hocr_obj.load_pages_from_file(str(aligned_hocr_path))
    if not pages:
        raise ValueError("No pages found in aligned hOCR file.")

    page_data: List[tuple] = []  # (PIL Image, page)
    if image_path is not None:
        image_path = Path(image_path).resolve()
        if not image_path.is_file():
            raise FileNotFoundError(f"Image not found: {image_path}")
        if len(pages) != 1:
            raise ValueError("When using --image, aligned hOCR must have exactly one page.")
        if Image is None:
            raise RuntimeError("Pillow is required. Install with: pip install Pillow")
        raw = Image.open(image_path).convert("RGB")
        page_data.append((raw, pages[0]))
    else:
        pdf_path = Path(pdf_path).resolve()  # type: ignore[assignment]
        if not pdf_path.is_file():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        if not _check_pdftoppm():
            raise RuntimeError("pdftoppm not found. Install poppler (e.g. brew install poppler).")
        with tempfile.TemporaryDirectory(prefix="make_cleaned_pdf_") as tmp:
            work = Path(tmp)
            all_images = pdf_to_images(pdf_path, work, dpi=dpi)
            if len(all_images) < len(pages):
                raise ValueError(
                    f"PDF has fewer pages ({len(all_images)}) than hOCR ({len(pages)}). "
                    "Use a PDF with at least as many pages as the aligned hOCR."
                )
            for img_path, page in zip(all_images[: len(pages)], pages):
                if Image is None:
                    raise RuntimeError("Pillow is required. Install with: pip install Pillow")
                raw = Image.open(img_path).convert("RGB")
                page_data.append((raw, page))

    c = canvas.Canvas(str(output_path))
    for pil_img, page in page_data:
        w_px, h_px = pil_img.size
        w_pt = w_px * 72 / dpi
        h_pt = h_px * 72 / dpi
        c.setPageSize((w_pt, h_pt))
        c.drawImage(ImageReader(pil_img), 0, 0, width=w_pt, height=h_pt)
        t = c.beginText()
        t.setTextRenderMode(3)
        for w in page.all_strings():
            if not w.content or w.height <= 0:
                continue
            x_pt = w.hpos * 72 / dpi
            font_size_pt = max(6, min((w.height * 72 / dpi) * 0.85, 72))
            y_baseline_pt = (h_px - w.vpos - w.height * 0.85) * 72 / dpi
            t.setFont("Helvetica", font_size_pt)
            t.setTextOrigin(x_pt, y_baseline_pt)
            t.textOut(w.content)
        c.drawText(t)
        c.showPage()
    c.save()


def build_pdf_from_hocr_dir(
    aligned_hocr_dir: Path,
    output_path: Path,
    pdf_path: Optional[Path] = None,
    dpi: int = 300,
    font_path: Optional[str] = None,
) -> None:
    """Build a multi-page PDF using per-page hOCR files (page-by-page pipeline output)."""
    if hocr_obj is None:
        raise RuntimeError("hocr_obj not available. Run from repo root: python make_cleaned_pdf.py ...")
    if canvas is None or ImageReader is None:
        raise RuntimeError("reportlab is required. Install with: pip install reportlab")
    if pdf_path is None:
        raise ValueError("Provide --pdf when using --aligned-hocr-dir.")

    aligned_hocr_dir = Path(aligned_hocr_dir).resolve()
    output_path = Path(output_path).resolve()
    if not aligned_hocr_dir.is_dir():
        raise FileNotFoundError(f"hOCR directory not found: {aligned_hocr_dir}")
    pdf_path = Path(pdf_path).resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if not _check_pdftoppm():
        raise RuntimeError("pdftoppm not found. Install poppler (e.g. brew install poppler).")

    page_files = sorted(aligned_hocr_dir.glob("page-*_aligned_hocr.html"), key=lambda p: (len(p.stem), p.stem))
    if not page_files:
        page_files = sorted(aligned_hocr_dir.glob("page-*.html*"), key=lambda p: (len(p.stem), p.stem))
    if not page_files:
        raise ValueError("No per-page hOCR files found in directory.")

    pages = [hocr_obj.load_first_page(str(p)) for p in page_files]
    with tempfile.TemporaryDirectory(prefix="make_cleaned_pdf_") as tmp:
        work = Path(tmp)
        all_images = pdf_to_images(pdf_path, work, dpi=dpi)
        if len(all_images) < len(pages):
            raise ValueError(
                f"PDF has fewer pages ({len(all_images)}) than hOCR pages ({len(pages)}). "
                "Use a PDF with at least as many pages as the aligned hOCR."
            )

        c = canvas.Canvas(str(output_path))
        for img_path, page in zip(all_images[: len(pages)], pages):
            if Image is None:
                raise RuntimeError("Pillow is required. Install with: pip install Pillow")
            pil_img = Image.open(img_path).convert("RGB")
            w_px, h_px = pil_img.size
            w_pt = w_px * 72 / dpi
            h_pt = h_px * 72 / dpi
            c.setPageSize((w_pt, h_pt))
            c.drawImage(ImageReader(pil_img), 0, 0, width=w_pt, height=h_pt)
            t = c.beginText()
            t.setTextRenderMode(3)
            for w in page.all_strings():
                if not w.content or w.height <= 0:
                    continue
                x_pt = w.hpos * 72 / dpi
                font_size_pt = max(6, min((w.height * 72 / dpi) * 0.85, 72))
                y_baseline_pt = (h_px - w.vpos - w.height * 0.85) * 72 / dpi
                t.setFont("Helvetica", font_size_pt)
                t.setTextOrigin(x_pt, y_baseline_pt)
                t.textOut(w.content)
            c.drawText(t)
            c.showPage()
        c.save()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a searchable PDF from PDF or PNG and aligned ALTO (Tesseract-style: image + invisible text)."
    )
    parser.add_argument("--pdf", "-p", help="Path to original PDF (use this or --image)")
    parser.add_argument("--image", "-i", help="Path to single page image (PNG, etc.); ALTO must have one page")
    parser.add_argument("--aligned-xml", "-x", help="Path to aligned ALTO XML (-aligned.xml); required unless --tesseract-pdf")
    parser.add_argument("--aligned-hocr", help="Path to aligned hOCR HTML/HTML.GZ; required unless --tesseract-pdf")
    parser.add_argument("--aligned-hocr-dir", help="Directory of per-page aligned hOCR (page-*_aligned_hocr.html); requires --pdf")
    parser.add_argument("--output", "-o", required=True, help="Path to output PDF")
    parser.add_argument("--dpi", type=int, default=300, help="DPI for PDF rendering (default 300)")
    parser.add_argument("--font", "-f", default=None, help="Path to TTF font (optional)")
    parser.add_argument("--tesseract-pdf", action="store_true", help="Use Tesseract's pdf output (image only; raw OCR, no ALTO)")
    parser.add_argument("--lang", "-l", default="eng", help="Tesseract language for --tesseract-pdf (default eng)")
    args = parser.parse_args()

    if args.tesseract_pdf:
        if not args.image:
            parser.error("--tesseract-pdf requires --image.")
        try:
            build_pdf_tesseract(Path(args.image), Path(args.output), lang=args.lang)
            print(f"Wrote (Tesseract PDF): {args.output}")
            return 0
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    if not args.pdf and not args.image:
        parser.error("Provide either --pdf or --image.")
    if args.pdf and args.image:
        parser.error("Provide only one of --pdf or --image.")
    if sum(bool(x) for x in (args.aligned_xml, args.aligned_hocr, args.aligned_hocr_dir)) > 1:
        parser.error("Provide only one of --aligned-xml, --aligned-hocr, or --aligned-hocr-dir.")
    if not args.aligned_xml and not args.aligned_hocr and not args.aligned_hocr_dir:
        parser.error("One of --aligned-xml, --aligned-hocr, or --aligned-hocr-dir is required unless using --tesseract-pdf.")

    try:
        if args.aligned_hocr_dir:
            build_pdf_from_hocr_dir(
                Path(args.aligned_hocr_dir),
                Path(args.output),
                pdf_path=Path(args.pdf) if args.pdf else None,
                dpi=args.dpi,
                font_path=args.font,
            )
        elif args.aligned_hocr:
            build_pdf_from_hocr(
                Path(args.aligned_hocr),
                Path(args.output),
                pdf_path=Path(args.pdf) if args.pdf else None,
                image_path=Path(args.image) if args.image else None,
                dpi=args.dpi,
                font_path=args.font,
            )
        else:
            build_pdf(
                Path(args.aligned_xml),
                Path(args.output),
                pdf_path=Path(args.pdf) if args.pdf else None,
                image_path=Path(args.image) if args.image else None,
                dpi=args.dpi,
                font_path=args.font,
            )
        print(f"Wrote: {args.output}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
