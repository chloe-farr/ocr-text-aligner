#!/usr/bin/env python3
"""
Built-in OCR: run Tesseract on a PDF or image to produce ALTO XML and plain text.
Output layout matches what run_pipeline expects: <out_dir>/<base>.txt and <out_dir>/alto/*.xml.
Requires: tesseract (CLI), and for PDFs: pdftoppm (poppler-utils).
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional


def _check_tesseract() -> bool:
    return shutil.which("tesseract") is not None


def _check_pdftoppm() -> bool:
    return shutil.which("pdftoppm") is not None


def pdf_to_images(pdf_path: Path, work_dir: Path, dpi: int = 300) -> list[Path]:
    """Render PDF pages to PNGs. Returns list of image paths in order."""
    # pdftoppm -png -r 300 input.pdf output_base  → output_base-1.png, output_base-2.png, ...
    base = work_dir / "page"
    result = subprocess.run(
        ["pdftoppm", "-png", "-r", str(dpi), str(pdf_path), str(base)],
        cwd=str(work_dir),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pdftoppm failed: {result.stderr or result.stdout}")
    # pdftoppm names output base-1.png, base-2.png, ...
    images = sorted(work_dir.glob("page-*.png"), key=lambda p: (len(p.stem), p.stem))
    return images


def run_tesseract_alto(image_path: Path, output_base: Path, lang: str = "eng", psm: int = 4) -> Path:
    """Run tesseract with ALTO output. Returns path to the .xml file (tesseract adds .xml)."""
    subprocess.run(
        ["tesseract", str(image_path), str(output_base), "-l", lang, "--psm", str(psm), "alto"],
        check=True,
        capture_output=True,
    )
    xml_path = Path(str(output_base) + ".xml")
    return xml_path if xml_path.is_file() else output_base.with_suffix(".xml")


def run_tesseract_txt(image_path: Path, output_base: Path, lang: str = "eng", psm: int = 4) -> Path:
    """Run tesseract with plain text output. Returns path to .txt file."""
    subprocess.run(
        ["tesseract", str(image_path), str(output_base), "-l", lang, "--psm", str(psm)],
        check=True,
        capture_output=True,
    )
    txt_path = Path(str(output_base) + ".txt")
    return txt_path if txt_path.is_file() else output_base.with_suffix(".txt")


def ocr_image(
    image_path: Path,
    out_dir: Path,
    page_name: str = "page-1",
    lang: str = "eng",
    psm: int = 4,
) -> tuple[Path, Path]:
    """Run Tesseract on one image. Writes out_dir/alto/<page_name>.xml and returns (alto_path, txt_path).
    Does not write a combined .txt; caller can concatenate for multi-page."""
    out_dir = Path(out_dir).resolve()
    alto_dir = out_dir / "alto"
    alto_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "_work" / page_name
    work.mkdir(parents=True, exist_ok=True)
    base = work / "out"
    alto_path = run_tesseract_alto(image_path, base, lang=lang, psm=psm)
    txt_path = run_tesseract_txt(image_path, base, lang=lang, psm=psm)
    # Move to final location
    dest_alto = alto_dir / f"{page_name}.xml"
    dest_txt = out_dir / f"{page_name}.txt"
    shutil.copy2(alto_path, dest_alto)
    shutil.copy2(txt_path, dest_txt)
    return dest_alto, dest_txt


def ocr_pdf(
    pdf_path: Path,
    out_dir: Path,
    base_name: Optional[str] = None,
    dpi: int = 300,
    lang: str = "eng",
    psm: int = 4,
    save_pages: bool = False,
) -> Path:
    """
    OCR a PDF: render pages to images, run Tesseract on each, write ALTO and plain text.
    Creates:
      out_dir/<base_name>.txt   (concatenated plain text)
      out_dir/page-1.txt, page-2.txt, ...
      out_dir/alto/page-1.xml, page-2.xml, ...
      If save_pages: out_dir/page-1.png, page-2.png, ... (for VLLM or other use)
    Returns out_dir.
    """
    pdf_path = Path(pdf_path).resolve()
    out_dir = Path(out_dir).resolve()
    base_name = base_name or pdf_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ocr_") as tmp:
        work = Path(tmp)
        images = pdf_to_images(pdf_path, work, dpi=dpi)
        if not images:
            raise RuntimeError(f"No pages produced from {pdf_path}")
        alto_dir = out_dir / "alto"
        alto_dir.mkdir(parents=True, exist_ok=True)
        all_txt = []
        for i, img in enumerate(images, start=1):
            page_name = f"page-{i}"
            if save_pages:
                shutil.copy2(img, out_dir / f"{page_name}.png")
            page_work = work / page_name
            page_work.mkdir(parents=True, exist_ok=True)
            base = page_work / "out"
            alto_path = run_tesseract_alto(img, base, lang=lang, psm=psm)
            txt_path = run_tesseract_txt(img, base, lang=lang, psm=psm)
            dest_alto = alto_dir / f"{page_name}.xml"
            shutil.copy2(alto_path, dest_alto)
            with open(txt_path, encoding="utf-8") as f:
                all_txt.append(f.read())
        # Per-page plain text (for page-by-page LLM cleaning)
        for i, text in enumerate(all_txt, start=1):
            (out_dir / f"page-{i}.txt").write_text(text, encoding="utf-8")
        combined_txt = out_dir / f"{base_name}.txt"
        with open(combined_txt, "w", encoding="utf-8") as f:
            f.write("\n\n".join(all_txt))
    return out_dir


def ocr_input(
    input_path: Path,
    out_dir: Path,
    base_name: Optional[str] = None,
    dpi: int = 300,
    lang: str = "eng",
    psm: int = 4,
    save_pages: bool = False,
) -> Path:
    """OCR a PDF or image. Dispatches to ocr_pdf or ocr_image. Returns out_dir."""
    input_path = Path(input_path).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    out_dir = Path(out_dir).resolve()
    base_name = base_name or input_path.stem
    suf = input_path.suffix.lower()
    if suf == ".pdf":
        if not _check_pdftoppm():
            raise RuntimeError("PDF input requires pdftoppm (poppler). Install e.g. brew install poppler")
        return ocr_pdf(input_path, out_dir, base_name=base_name, dpi=dpi, lang=lang, psm=psm, save_pages=save_pages)
    if suf in (".png", ".jpg", ".jpeg", ".tif", ".tiff"):
        out_dir.mkdir(parents=True, exist_ok=True)
        ocr_image(input_path, out_dir, page_name="page-1", lang=lang, psm=psm)
        # Single page: copy page-1.txt to <base_name>.txt
        p1_txt = out_dir / "page-1.txt"
        if p1_txt.is_file():
            combined = out_dir / f"{base_name}.txt"
            shutil.copy2(p1_txt, combined)
        return out_dir
    raise ValueError(f"Unsupported input type: {input_path.suffix}. Use .pdf, .png, .jpg, .tif")


def main():
    parser = argparse.ArgumentParser(description="Run Tesseract OCR on a PDF or image. Output: ALTO XML + plain text.")
    parser.add_argument("input", type=Path, help="PDF or image (png, jpg, tiff)")
    parser.add_argument("--output-dir", "-o", type=Path, required=True, help="Output directory (<base>.txt and alto/*.xml)")
    parser.add_argument("--save-pages", action="store_true", help="Save page PNGs to output dir (page-1.png, page-2.png, ...) for VLLM etc.")
    parser.add_argument("--dpi", type=int, default=300, help="DPI for PDF rendering (default 300)")
    parser.add_argument("--lang", default="eng", help="Tesseract language (default eng)")
    parser.add_argument("--psm", type=int, default=4, help="Tesseract PSM (default 4)")
    args = parser.parse_args()
    if not _check_tesseract():
        print("Error: tesseract not found. Install it (e.g. brew install tesseract).", file=sys.stderr)
        return 1
    try:
        out = ocr_input(args.input, args.output_dir, dpi=args.dpi, lang=args.lang, psm=args.psm, save_pages=args.save_pages)
        print("OCR output directory:", out)
        base = args.input.stem
        txt = out / f"{base}.txt"
        if txt.is_file():
            print("  Plain text:", txt)
        alto_dir = out / "alto"
        if alto_dir.is_dir():
            for f in sorted(alto_dir.glob("*.xml")):
                print("  ALTO:", f)
        if args.save_pages:
            for f in sorted(out.glob("page-*.png"), key=lambda p: (len(p.stem), p.stem)):
                print("  Page image:", f)
        return 0
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
