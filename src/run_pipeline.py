#!/usr/bin/env python3
"""
Single-entry pipeline: OCR → LLM clean → align.
OCR is built-in (tesseract_ocr.py); optional external script if TESSERACT_EXPERIMENT_DIR is set.
Run any step alone or the full chain. Designed so a future GUI can call these same steps.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

# src/ directory (where run_pipeline.py lives)
PROJECT_ROOT = Path(__file__).resolve().parent
# Repository root (one level up from src/)
REPO_ROOT = PROJECT_ROOT.parent

CONFIG_FILE = REPO_ROOT / "pipeline_config.json"


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _load_config() -> dict:
    """Load optional pipeline config (for tesseract path, etc.)."""
    if CONFIG_FILE.is_file():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _tesseract_dir(args: argparse.Namespace) -> str:
    """Tesseract experiment dir: CLI > env > config file."""
    return (
        getattr(args, "tesseract_dir", None)
        or _env("TESSERACT_EXPERIMENT_DIR")
        or _load_config().get("tesseract_experiment_dir", "")
        or ""
    )


def cmd_ocr(args: argparse.Namespace) -> int:
    """Run OCR: built-in (default) or external script if --tesseract-dir / TESSERACT_EXPERIMENT_DIR is set."""
    raw = getattr(args, "input", None) or getattr(args, "pdf", None)
    if not raw:
        print("Error: Provide --input or --pdf.", file=sys.stderr)
        return 1
    input_path = Path(raw).resolve()
    if not input_path.is_file():
        print("Error: Input file not found:", input_path, file=sys.stderr)
        return 1
    tesseract_dir = _tesseract_dir(args)
    use_external = bool(Path(tesseract_dir or "").resolve().is_dir() if tesseract_dir else False)

    if use_external:
        # External script (e.g. ocr_pdf.sh)
        script = Path(tesseract_dir).resolve() / "ocr_pdf.sh"
        if not script.is_file():
            print("Error: ocr_pdf.sh not found in", script.parent, file=sys.stderr)
            return 1
        try:
            subprocess.run(["bash", str(script), str(input_path)], cwd=str(script.parent), check=True)
        except subprocess.CalledProcessError as e:
            return e.returncode
        base = input_path.stem
        year = base[:4] if len(base) >= 4 else "unknown"
        out_dir = Path(args.ocr_output_dir).resolve() if getattr(args, "ocr_output_dir", None) else (script.parent / ".." / ".." / "04_datasets" / "TimesColonist_PDFs" / "output" / year / base).resolve()
        if out_dir.is_dir():
            print("OCR output directory:", out_dir)
        return 0

    # Built-in OCR (tesseract_ocr.py)
    out_dir = Path(getattr(args, "output_dir", None) or (REPO_ROOT / "pipeline_work" / "ocr_output" / input_path.stem)).resolve()
    try:
        import tesseract_ocr as ocr
        ocr.ocr_input(input_path, out_dir, dpi=getattr(args, "dpi", 300), lang=getattr(args, "lang", "eng"), psm=getattr(args, "psm", 4), save_pages=getattr(args, "save_pages", False))
        print("OCR output directory:", out_dir)
        return 0
    except Exception as e:
        print("Error:", e, file=sys.stderr)
        return 1


def _resolve_ocr_output(args: argparse.Namespace, base: str, year: str, work_dir: Optional[Path] = None) -> Path:
    """Resolve OCR output dir: explicit --ocr-output-dir, or (external) tesseract script output, or (built-in) work_dir/ocr_output/base."""
    if getattr(args, "ocr_output_dir", None):
        return Path(args.ocr_output_dir).resolve()
    tesseract_dir = _tesseract_dir(args)
    if tesseract_dir and Path(tesseract_dir).resolve().is_dir():
        return (Path(tesseract_dir).resolve() / ".." / ".." / "04_datasets" / "TimesColonist_PDFs" / "output" / year / base).resolve()
    if work_dir is not None:
        return (work_dir / "ocr_output" / base).resolve()
    return (REPO_ROOT / "pipeline_work" / "ocr_output" / base).resolve()


def cmd_clean(args: argparse.Namespace) -> int:
    """Run LLM refinement on plain OCR text."""
    cmd = [
        sys.executable, "-m", "llm_cleaning.ocr_refiner",
        "--in", str(args.input_plaintext),
        "--out", str(args.output_cleantext),
    ]
    if getattr(args, "model", None):
        cmd.extend(["--model", args.model])
    if getattr(args, "ollama_host", None):
        cmd.extend(["--ollama-host", args.ollama_host])
    if getattr(args, "max_iters", None) is not None:
        cmd.extend(["--max-iters", str(args.max_iters)])
    if getattr(args, "wc_tol", None) is not None:
        cmd.extend(["--wc-tol", str(args.wc_tol)])
    if getattr(args, "cc_tol", None) is not None:
        cmd.extend(["--cc-tol", str(args.cc_tol)])
    if getattr(args, "novel_tok_ratio", None) is not None:
        cmd.extend(["--novel-tok-ratio", str(args.novel_tok_ratio)])
    if getattr(args, "min_tokens", None) is not None:
        cmd.extend(["--min-tokens", str(args.min_tokens)])
    if getattr(args, "max_tokens", None) is not None:
        cmd.extend(["--max-tokens", str(args.max_tokens)])
    if getattr(args, "overlap_lines", None) is not None:
        cmd.extend(["--overlap-lines", str(args.overlap_lines)])
    if getattr(args, "year", None) is not None:
        cmd.extend(["--year", str(args.year)])
    if getattr(args, "month", None) is not None:
        cmd.extend(["--month", str(args.month)])
    if getattr(args, "location", None):
        cmd.extend(["--location", args.location])
    if getattr(args, "debug", False):
        cmd.append("--debug")
    if getattr(args, "page_mode", False):
        cmd.append("--page-mode")
    r = subprocess.run(cmd, cwd=str(PROJECT_ROOT))  # cwd=src/ so -m llm_cleaning resolves
    return r.returncode


def cmd_align(args: argparse.Namespace) -> int:
    """Run alignment: OCR (ALTO or hOCR) + clean text → aligned OCR output (and visualizations)."""
    cmd = [
        sys.executable, str(PROJECT_ROOT / "map_up_text.py"),
        "--clean-text", str(args.clean_text),
    ]
    if getattr(args, "xml_file", None):
        cmd.extend(["--xml-file", str(args.xml_file)])
    elif getattr(args, "hocr_file", None):
        cmd.extend(["--hocr-file", str(args.hocr_file)])
    else:
        print("Error: Provide --xml-file or --hocr-file.", file=sys.stderr)
        return 1
    if getattr(args, "output_xml", None) is not None:
        cmd.append("--output-xml")
        if args.output_xml:
            cmd.append(str(args.output_xml))
    if getattr(args, "output_hocr", None) is not None:
        cmd.append("--output-hocr")
        if args.output_hocr:
            cmd.append(str(args.output_hocr))
    if getattr(args, "show_ocr_accuracy", False):
        cmd.append("--show-ocr-accuracy")
    r = subprocess.run(cmd, cwd=str(REPO_ROOT))  # cwd=repo root so outputs/ lands correctly
    return r.returncode


def cmd_all(args: argparse.Namespace) -> int:
    """Run OCR (if requested) → clean → align with derived paths."""
    work_dir = Path(args.work_dir or REPO_ROOT / "pipeline_work").resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    input_path = getattr(args, "input", None) or getattr(args, "pdf", None)
    input_path = Path(input_path).resolve() if input_path else None
    tesseract_dir = _tesseract_dir(args)
    use_external_ocr = bool(tesseract_dir and Path(tesseract_dir).resolve().is_dir())
    ocr_output_dir = getattr(args, "ocr_output_dir", None)
    ocr_output_dir = Path(ocr_output_dir).resolve() if ocr_output_dir else None
    base = (input_path.stem if input_path and input_path.is_file() else None) or getattr(args, "base_name", None) or "document"
    year = (base[:4] if base and len(base) >= 4 else "unknown")

    # Step 1: OCR (optional)
    if ocr_output_dir and ocr_output_dir.is_dir():
        out_dir = ocr_output_dir
        base = base if base != "document" else out_dir.name
    elif input_path and input_path.is_file() and use_external_ocr:
        args_ocr = argparse.Namespace(
            input=str(input_path),
            pdf=str(input_path),
            tesseract_dir=tesseract_dir,
            ocr_output_dir=str(ocr_output_dir) if ocr_output_dir else None,
        )
        if cmd_ocr(args_ocr) != 0:
            return 1
        out_dir = ocr_output_dir or _resolve_ocr_output(args, base, year, work_dir=None)
    elif input_path and input_path.is_file():
        # Built-in OCR
        out_dir = work_dir / "ocr_output" / base
        args_ocr = argparse.Namespace(
            input=str(input_path),
            pdf=str(input_path),
            tesseract_dir=None,
            output_dir=str(out_dir),
            dpi=getattr(args, "dpi", 300),
            lang=getattr(args, "lang", "eng"),
            psm=getattr(args, "psm", 4),
        )
        if cmd_ocr(args_ocr) != 0:
            return 1
    else:
        print("For 'all': provide --input/--pdf to run OCR, or --ocr-output-dir to use existing OCR output.", file=sys.stderr)
        return 1

    plain_path = out_dir / f"{base}.txt"
    alto_dir = out_dir / "alto"
    if not plain_path.is_file():
        print("Error: Plain text not found:", plain_path, file=sys.stderr)
        return 1

    # Collect OCR page files: ALTO (preferred) or hOCR
    input_format: Optional[str] = None
    ocr_page_files: list[Path] = []

    if alto_dir.is_dir():
        alto_files = sorted(alto_dir.glob("*.xml"), key=lambda p: (len(p.stem), p.stem))
        if alto_files:
            input_format = "alto"
            ocr_page_files = alto_files

    if input_format is None:
        hocr_dir = out_dir / "hocr"
        if hocr_dir.is_dir():
            hocr_files = sorted(hocr_dir.glob("*.html*"), key=lambda p: (len(p.stem), p.stem))
            if hocr_files:
                input_format = "hocr"
                ocr_page_files = hocr_files

    if input_format is None:
        # Fallback: look for a single hOCR file in out_dir
        hocr_files = sorted(out_dir.glob("*hocr*.html*"), key=lambda p: (len(p.name), p.name))
        if hocr_files:
            input_format = "hocr"
            ocr_page_files = hocr_files

    if not ocr_page_files:
        print("Error: No OCR page files found (expected alto/*.xml or hocr/*.html).", file=sys.stderr)
        return 1

    num_pages = len(ocr_page_files)
    have_per_page_txt = (out_dir / "page-1.txt").is_file() or (out_dir / "page-01.txt").is_file()
    if num_pages > 1 and not have_per_page_txt:
        print("Error: Multi-page OCR requires per-page plain text (page-1.txt, page-2.txt, ...).", file=sys.stderr)
        return 1
    page_by_page = num_pages > 1 or have_per_page_txt

    # Step 2: Clean (one chunk = whole doc, or one chunk per page)
    if page_by_page and num_pages >= 1:
        # Page-by-page: clean each page-N.txt with --page-mode → page-N_cleantext.txt
        clean_paths = []
        for i in range(1, num_pages + 1):
            page_txt = out_dir / f"page-{i}.txt"
            if not page_txt.is_file():
                page_txt = out_dir / f"page-{i:02d}.txt"
            if not page_txt.is_file():
                print("Error: Per-page plain text not found (e.g. page-1.txt):", out_dir, file=sys.stderr)
                return 1
            out_clean = work_dir / f"{base}_page{i}_cleantext.txt"
            args_clean = argparse.Namespace(
                input_plaintext=str(page_txt),
                output_cleantext=str(out_clean),
                model=getattr(args, "model", "qwen2.5:14b"),
                ollama_host=getattr(args, "ollama_host", None),
                max_iters=getattr(args, "max_iters", 6),
                wc_tol=getattr(args, "wc_tol", 0.15),
                cc_tol=getattr(args, "cc_tol", 0.15),
                novel_tok_ratio=getattr(args, "novel_tok_ratio", 0.12),
                min_tokens=getattr(args, "min_tokens", 150),
                max_tokens=getattr(args, "max_tokens", 600),
                overlap_lines=getattr(args, "overlap_lines", 2),
                year=getattr(args, "year", None),
                month=getattr(args, "month", None),
                location=getattr(args, "location", None),
                debug=getattr(args, "debug", False),
                page_mode=True,
            )
            if cmd_clean(args_clean) != 0:
                return 1
            clean_paths.append(out_clean)
    else:
        # Single doc: one clean run (chunked by token count)
        clean_path = work_dir / f"{base}_cleantext.txt"
        args_clean = argparse.Namespace(
            input_plaintext=str(plain_path),
            output_cleantext=str(clean_path),
            model=getattr(args, "model", "qwen2.5:14b"),
            ollama_host=getattr(args, "ollama_host", None),
            max_iters=getattr(args, "max_iters", 6),
            wc_tol=getattr(args, "wc_tol", 0.15),
            cc_tol=getattr(args, "cc_tol", 0.15),
            novel_tok_ratio=getattr(args, "novel_tok_ratio", 0.12),
            min_tokens=getattr(args, "min_tokens", 150),
            max_tokens=getattr(args, "max_tokens", 600),
            overlap_lines=getattr(args, "overlap_lines", 2),
            year=getattr(args, "year", None),
            month=getattr(args, "month", None),
            location=getattr(args, "location", None),
            debug=getattr(args, "debug", False),
            page_mode=False,
        )
        if cmd_clean(args_clean) != 0:
            return 1
        clean_paths = [clean_path]

    # Step 3: Align (single page or multi-page; ALTO merges, hOCR writes per-page)
    out_xml_path = work_dir / f"{base}_aligned.xml"
    out_hocr_path = work_dir / f"{base}_aligned_hocr.html"
    if len(clean_paths) == 1 and len(ocr_page_files) == 1:
        if input_format == "alto":
            args_align = argparse.Namespace(
                xml_file=str(ocr_page_files[0]),
                hocr_file=None,
                clean_text=str(clean_paths[0]),
                output_xml=str(out_xml_path),
                output_hocr=None,
                show_ocr_accuracy=getattr(args, "show_ocr_accuracy", False),
            )
        else:
            args_align = argparse.Namespace(
                xml_file=None,
                hocr_file=str(ocr_page_files[0]),
                clean_text=str(clean_paths[0]),
                output_xml=None,
                output_hocr=str(out_hocr_path),
                show_ocr_accuracy=getattr(args, "show_ocr_accuracy", False),
            )
        return cmd_align(args_align)
    # Multi-page: align each page, then merge into one ALTO (hOCR: per-page outputs)
    import tempfile
    import write_aligned_alto
    temp_alto_paths = []
    try:
        if input_format == "alto":
            for i, (xml_path, clean_path) in enumerate(zip(ocr_page_files, clean_paths)):
                tmp = tempfile.NamedTemporaryFile(suffix=".xml", delete=False)
                tmp.close()
                temp_alto_paths.append(tmp.name)
                args_align = argparse.Namespace(
                    xml_file=str(xml_path),
                    hocr_file=None,
                    clean_text=str(clean_path),
                    output_xml=tmp.name,
                    output_hocr=None,
                    show_ocr_accuracy=getattr(args, "show_ocr_accuracy", False) and i == 0,
                )
                if cmd_align(args_align) != 0:
                    return 1
            write_aligned_alto.merge_alto_files(temp_alto_paths, str(out_xml_path))
            print(f"Wrote aligned ALTO XML (merged {num_pages} pages) to {out_xml_path}")
        else:
            aligned_dir = work_dir / "aligned_hocr" / base
            aligned_dir.mkdir(parents=True, exist_ok=True)
            for i, (hocr_path, clean_path) in enumerate(zip(ocr_page_files, clean_paths), start=1):
                out_page = aligned_dir / f"page-{i}_aligned_hocr.html"
                args_align = argparse.Namespace(
                    xml_file=None,
                    hocr_file=str(hocr_path),
                    clean_text=str(clean_path),
                    output_xml=None,
                    output_hocr=str(out_page),
                    show_ocr_accuracy=getattr(args, "show_ocr_accuracy", False) and i == 1,
                )
                if cmd_align(args_align) != 0:
                    return 1
            print(f"Wrote aligned hOCR HTML pages to {aligned_dir}")

            # IA-friendly publish artifact: combine per-page aligned hOCR into one multi-page *_hocr.html
            try:
                import hocr_combine

                combined_out = work_dir / f"{base}_aligned_hocr.html"
                page_paths = sorted(aligned_dir.glob("page-*_aligned_hocr.html"), key=lambda p: (len(p.stem), p.stem))
                if page_paths:
                    hocr_combine.combine_hocr_files(page_paths, combined_out)
                    print(f"Wrote combined aligned hOCR HTML to {combined_out}")
            except Exception as e:
                print(f"Warning: failed to combine hOCR pages into one file: {e}", file=sys.stderr)
    finally:
        for p in temp_alto_paths:
            try:
                os.unlink(p)
            except Exception:
                pass
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="OCR → LLM clean → align pipeline. Run one step or all.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", help="Command")

    # --- ocr ---
    p_ocr = sub.add_parser("ocr", help="Run OCR on a PDF or image (built-in Tesseract; or external script if --tesseract-dir set)")
    p_ocr.add_argument("--input", "-i", dest="input", help="Path to PDF or image (png, jpg, tiff)")
    p_ocr.add_argument("--pdf", help="Path to PDF (alias for --input)")
    p_ocr.add_argument("--tesseract-dir", default=_env("TESSERACT_EXPERIMENT_DIR"), help="If set, run external ocr_pdf.sh instead of built-in OCR")
    p_ocr.add_argument("--output-dir", "-o", help="Output directory (default: pipeline_work/ocr_output/<stem> for built-in)")
    p_ocr.add_argument("--ocr-output-dir", help="(External script only) Override OCR output dir")
    p_ocr.add_argument("--save-pages", action="store_true", help="(Built-in) Save page PNGs (page-1.png, ...) for VLLM etc.")
    p_ocr.add_argument("--dpi", type=int, default=300, help="(Built-in) DPI for PDF rendering")
    p_ocr.add_argument("--lang", default="eng", help="(Built-in) Tesseract language")
    p_ocr.add_argument("--psm", type=int, default=4, help="(Built-in) Tesseract PSM")

    # --- clean ---
    p_clean = sub.add_parser("clean", help="LLM-refine plain OCR text → cleantext")
    p_clean.add_argument("--input-plaintext", required=True, help="Plain text from OCR")
    p_clean.add_argument("--output-cleantext", required=True, help="Output cleantext path")
    p_clean.add_argument("--model", default="qwen2.5:14b", help="Ollama model")
    p_clean.add_argument("--ollama-host", default=_env("OLLAMA_HOST", "http://localhost:11434"))
    p_clean.add_argument("--max-iters", type=int, default=6)
    p_clean.add_argument("--wc-tol", type=float, default=0.15, dest="wc_tol")
    p_clean.add_argument("--cc-tol", type=float, default=0.15, dest="cc_tol")
    p_clean.add_argument("--novel-tok-ratio", type=float, default=0.12, dest="novel_tok_ratio")
    p_clean.add_argument("--min-tokens", type=int, default=150)
    p_clean.add_argument("--max-tokens", type=int, default=600)
    p_clean.add_argument("--overlap-lines", type=int, default=2)
    p_clean.add_argument("--year", type=int, default=None)
    p_clean.add_argument("--month", type=int, default=None)
    p_clean.add_argument("--location", type=str, default=None)
    p_clean.add_argument("--debug", action="store_true")
    p_clean.add_argument("--page-mode", action="store_true", dest="page_mode", help="One chunk = entire input (e.g. one page)")

    # --- align ---
    p_align = sub.add_parser("align", help="Align cleantext to OCR (ALTO or hOCR); write aligned output")
    g_align_in = p_align.add_mutually_exclusive_group(required=True)
    g_align_in.add_argument("--xml-file", help="ALTO XML path")
    g_align_in.add_argument("--hocr-file", help="hOCR HTML/HTML.GZ path")
    p_align.add_argument("--clean-text", required=True, help="Cleantext path")
    p_align.add_argument("--output-xml", nargs="?", const="", default=None, help="Write aligned ALTO (optional path)")
    p_align.add_argument("--output-hocr", nargs="?", const="", default=None, help="Write aligned hOCR (optional path)")
    p_align.add_argument("--show-ocr-accuracy", action="store_true")

    # --- all ---
    p_all = sub.add_parser("all", help="Run OCR (built-in or external) then clean then align")
    p_all.add_argument("--input", "-i", dest="input", help="PDF or image to OCR")
    p_all.add_argument("--pdf", help="Alias for --input")
    p_all.add_argument("--tesseract-dir", default=_env("TESSERACT_EXPERIMENT_DIR"), help="If set, use external ocr_pdf.sh instead of built-in OCR")
    p_all.add_argument("--ocr-output-dir", help="Use this OCR output dir (skip OCR step)")
    p_all.add_argument("--base-name", dest="base_name", help="Document base name (default: from input or ocr-output-dir)")
    p_all.add_argument("--work-dir", default=None, help="Working dir for cleantext and aligned XML (default: pipeline_work/)")
    p_all.add_argument("--save-pages", action="store_true", help="(Built-in OCR) Save page PNGs for VLLM etc.")
    p_all.add_argument("--dpi", type=int, default=300, help="(Built-in OCR) DPI for PDF")
    p_all.add_argument("--lang", default="eng", help="(Built-in OCR) Tesseract language")
    p_all.add_argument("--psm", type=int, default=4, help="(Built-in OCR) Tesseract PSM")
    p_all.add_argument("--model", default="qwen2.5:14b")
    p_all.add_argument("--ollama-host", default=_env("OLLAMA_HOST", "http://localhost:11434"))
    p_all.add_argument("--max-iters", type=int, default=6)
    p_all.add_argument("--wc-tol", type=float, default=0.15, dest="wc_tol")
    p_all.add_argument("--cc-tol", type=float, default=0.15, dest="cc_tol")
    p_all.add_argument("--novel-tok-ratio", type=float, default=0.12, dest="novel_tok_ratio")
    p_all.add_argument("--min-tokens", type=int, default=150)
    p_all.add_argument("--max-tokens", type=int, default=600)
    p_all.add_argument("--overlap-lines", type=int, default=2)
    p_all.add_argument("--year", type=int, default=None)
    p_all.add_argument("--month", type=int, default=None)
    p_all.add_argument("--location", type=str, default=None)
    p_all.add_argument("--debug", action="store_true")
    p_all.add_argument("--show-ocr-accuracy", action="store_true")

    parsed = parser.parse_args()
    if not parsed.command:
        parser.print_help()
        return 0

    os.chdir(REPO_ROOT)
    if parsed.command == "ocr":
        return cmd_ocr(parsed)
    if parsed.command == "clean":
        return cmd_clean(parsed)
    if parsed.command == "align":
        return cmd_align(parsed)
    if parsed.command == "all":
        return cmd_all(parsed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
