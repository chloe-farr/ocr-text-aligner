import subprocess
import sys
import tempfile
from pathlib import Path

import gradio as gr

SRC_DIR = Path(__file__).parent / "src"
sys.path.insert(0, str(SRC_DIR))

import tesseract_ocr as tess

PSM_OPTIONS = [
    "3 — Auto (no OSD)",
    "4 — Single column (default)",
    "6 — Uniform block of text",
    "11 — Sparse text",
    "12 — Sparse text with OSD",
]
_PSM_MAP = {"3": 3, "4": 4, "6": 6, "11": 11, "12": 12}


def _path(f):
    if f is None:
        return None
    if isinstance(f, str):
        return Path(f)
    if isinstance(f, dict):
        return Path(f.get("path") or f.get("name") or "")
    if hasattr(f, "name"):
        return Path(f.name)
    return None


def _psm_int(choice: str) -> int:
    return _PSM_MAP.get(choice.split("—")[0].strip(), 4)


def _page_outputs(out_dir: Path, page_n: int, num_pages: int):
    """Return (alto_path, hocr_path, txt_path, plain_text) for a given page."""
    alto_dir = out_dir / "alto"
    hocr_dir = out_dir / "hocr"
    alto_files = sorted(alto_dir.glob("*.xml")) if alto_dir.is_dir() else []
    hocr_files = sorted(hocr_dir.glob("*.hocr.html")) if hocr_dir.is_dir() else []

    idx = page_n - 1
    alto = str(alto_files[idx]) if idx < len(alto_files) else None
    hocr = str(hocr_files[idx]) if idx < len(hocr_files) else None

    page_txt = out_dir / f"page-{page_n}.txt"
    plain = page_txt.read_text(encoding="utf-8").strip() if page_txt.is_file() else ""

    return alto, hocr, plain


def _ocr_error(msg):
    return None, None, None, "", "", msg, "", 1, 1, gr.update(visible=False), "—"


def run_ocr(file_obj, lang, psm_choice):
    if file_obj is None:
        return _ocr_error("Upload a file first.")

    input_path = _path(file_obj)
    if not input_path or not input_path.is_file():
        return _ocr_error("File not found.")

    lang = (lang or "eng").strip()
    psm = _psm_int(psm_choice)
    out_dir = Path(tempfile.mkdtemp(prefix="ocr_space_"))

    try:
        tess.ocr_input(input_path, out_dir, lang=lang, psm=psm)
    except Exception as e:
        return _ocr_error(f"OCR failed: {e}")

    alto_dir = out_dir / "alto"
    alto_files = sorted(alto_dir.glob("*.xml")) if alto_dir.is_dir() else []
    num_pages = len(alto_files)
    multi_page = num_pages > 1

    alto, hocr, plain = _page_outputs(out_dir, 1, num_pages)

    combined_txt = out_dir / f"{input_path.stem}.txt"
    txt_out = str(combined_txt) if combined_txt.is_file() else None

    status = f"Done — {num_pages} page(s) processed."
    if multi_page:
        status += " Use the page buttons to browse. ALTO/hOCR downloads follow the current page."

    # returns: alto, hocr, txt, plain×2, status, out_dir, page, num_pages, nav_visible, page_label
    return (alto, hocr, txt_out, plain, plain, status,
            str(out_dir), 1, num_pages, gr.update(visible=multi_page), f"1 / {num_pages}")


def change_page(out_dir_str, current_page, num_pages, direction):
    if not out_dir_str:
        return None, None, "", "", current_page
    new_page = max(1, min(num_pages, current_page + direction))
    out_dir = Path(out_dir_str)
    alto, hocr, plain = _page_outputs(out_dir, new_page, num_pages)
    return alto, hocr, plain, plain, new_page


def run_align(ocr_file, text_source, clean_file, clean_textbox):
    if ocr_file is None:
        return None, "Upload an OCR file (ALTO XML or hOCR)."

    ocr_path = _path(ocr_file)
    if not ocr_path or not ocr_path.is_file():
        return None, "OCR file not found."

    if text_source == "Upload file":
        if clean_file is None:
            return None, "Upload a clean text file."
        clean_path = _path(clean_file)
        if not clean_path or not clean_path.is_file():
            return None, "Clean text file not found."
    else:
        text = (clean_textbox or "").strip()
        if not text:
            return None, "Enter or paste clean text."
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
        tmp.write(text)
        tmp.close()
        clean_path = Path(tmp.name)

    is_alto = ocr_path.suffix.lower() == ".xml"
    out_dir = Path(tempfile.mkdtemp(prefix="align_space_"))
    out_file = out_dir / ("aligned.xml" if is_alto else "aligned.hocr.html")

    cmd = [sys.executable, str(SRC_DIR / "map_up_text.py"), "--clean-text", str(clean_path)]
    if is_alto:
        cmd += ["--xml-file", str(ocr_path), "--output-xml", str(out_file)]
    else:
        cmd += ["--hocr-file", str(ocr_path), "--output-hocr", str(out_file)]

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(SRC_DIR.parent))

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "Unknown error").strip()
        return None, f"Alignment failed:\n{err[:600]}"

    if not out_file.is_file():
        return None, "Alignment ran but output file not found."

    return str(out_file), "Alignment complete."



with gr.Blocks(title="OCR Text Aligner") as demo:
    ocr_dir_state = gr.State("")
    ocr_page_state = gr.State(1)
    ocr_num_pages_state = gr.State(1)

    gr.Markdown(
        "# OCR Text Aligner\n"
        "Map corrected text back onto Tesseract ALTO/hOCR — word by word, preserving spatial coordinates. "
        "[[GitHub](https://github.com/chloe-farr/ocr-text-aligner)]"
    )

    with gr.Tabs():
        # ── Tab 1: OCR ──────────────────────────────────────────────────────
        with gr.Tab("1 · OCR"):
            gr.Markdown(
                "Run Tesseract on your document. Edit the plain text output below, "
                "then align it in Tab 2."
            )
            ocr_file_in = gr.File(
                label="Document (PDF, PNG, JPG, TIFF)",
                file_types=[".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"],
            )
            with gr.Row():
                lang_in = gr.Textbox(
                    label="Language",
                    value="eng",
                    placeholder="eng, fra, eng+fra, …",
                    info="[Language codes](https://tesseract-ocr.github.io/tessdoc/Data-Files-in-different-versions.html)",
                )
                psm_in = gr.Dropdown(
                    label="Page segmentation (PSM)",
                    choices=PSM_OPTIONS,
                    value="4 — Single column (default)",
                )
            ocr_btn = gr.Button("Run OCR", variant="primary")
            ocr_status = gr.Textbox(label="Status", interactive=False, lines=1)
            with gr.Row():
                dl_alto = gr.File(label="ALTO XML")
                dl_hocr = gr.File(label="hOCR")
                dl_txt = gr.File(label="Plain text (all pages)")
            with gr.Row(visible=False) as page_nav:
                prev_btn = gr.Button("← Prev page", size="sm")
                page_label = gr.Textbox(label="Page", value="1", interactive=False, scale=0, min_width=80)
                next_btn = gr.Button("Next page →", size="sm")
            ocr_text = gr.Textbox(
                label="Plain text — edit here, then use in Align tab",
                lines=16,
                interactive=True,
            )

        # ── Tab 2: Align ─────────────────────────────────────────────────────
        with gr.Tab("2 · Align"):
            gr.Markdown(
                "Align corrected text back onto OCR spatial coordinates. "
                "Upload the ALTO XML or hOCR from Tab 1, and provide clean text.\n\n"
                "> **LLM cleaning is not included.** "
                "Pass your OCR plain text through any LLM (GPT-4o, Claude, Gemini, a local model, …), "
                "then paste the result below."
            )
            align_ocr_in = gr.File(
                label="OCR file (ALTO XML or hOCR)",
                file_types=[".xml", ".html", ".hocr"],
            )
            text_source = gr.Radio(
                choices=["Paste / edit text", "Upload file"],
                value="Paste / edit text",
                label="Clean text source",
            )
            clean_text_in = gr.Textbox(
                label="Clean text",
                lines=12,
                interactive=True,
                placeholder="Paste LLM-corrected or manually edited text here.",
            )
            clean_file_in = gr.File(
                label="Clean text file (.txt or .md)",
                file_types=[".txt", ".md"],
                visible=False,
            )
            align_btn = gr.Button("Align", variant="primary")
            align_status = gr.Textbox(label="Status", interactive=False, lines=1)
            dl_aligned = gr.File(label="Aligned output")


    # ── Events ────────────────────────────────────────────────────────────────
    ocr_btn.click(
        fn=run_ocr,
        inputs=[ocr_file_in, lang_in, psm_in],
        outputs=[dl_alto, dl_hocr, dl_txt, ocr_text, clean_text_in, ocr_status,
                 ocr_dir_state, ocr_page_state, ocr_num_pages_state, page_nav, page_label],
        api_name=False,
    )

    def _prev(out_dir, page, total):
        alto, hocr, plain, plain2, new_page = change_page(out_dir, page, total, -1)
        return alto, hocr, plain, plain2, new_page, f"{new_page} / {total}"

    def _next(out_dir, page, total):
        alto, hocr, plain, plain2, new_page = change_page(out_dir, page, total, +1)
        return alto, hocr, plain, plain2, new_page, f"{new_page} / {total}"

    _nav_inputs = [ocr_dir_state, ocr_page_state, ocr_num_pages_state]
    _nav_outputs = [dl_alto, dl_hocr, ocr_text, clean_text_in, ocr_page_state, page_label]
    prev_btn.click(fn=_prev, inputs=_nav_inputs, outputs=_nav_outputs, api_name=False)
    next_btn.click(fn=_next, inputs=_nav_inputs, outputs=_nav_outputs, api_name=False)

    ocr_text.change(fn=lambda t: t, inputs=[ocr_text], outputs=[clean_text_in], api_name=False)

    def _toggle(choice):
        is_paste = choice == "Paste / edit text"
        return gr.update(visible=is_paste), gr.update(visible=not is_paste)

    text_source.change(fn=_toggle, inputs=[text_source], outputs=[clean_text_in, clean_file_in], api_name=False)

    align_btn.click(
        fn=run_align,
        inputs=[align_ocr_in, text_source, clean_file_in, clean_text_in],
        outputs=[dl_aligned, align_status],
        api_name=False,
    )


if __name__ == "__main__":
    demo.launch()
