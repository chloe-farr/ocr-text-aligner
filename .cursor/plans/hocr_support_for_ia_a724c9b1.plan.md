---
name: HOCR support for IA
overview: "Add Internet Archive–friendly hOCR I/O to the pipeline: accept hOCR as an OCR-input format for alignment (in addition to ALTO) and emit a minimal IA-compatible `*_hocr.html` derivative as output."
todos:
  - id: hocr-parse
    content: Add `hocr_obj.py` to parse word-level hOCR into existing `XMLOBJ.Page/StringWord` model (bbox + confidence).
    status: completed
  - id: hocr-write
    content: Add `write_aligned_hocr.py` to update/emit a minimal IA-compatible `*_hocr.html` from alignment results.
    status: completed
  - id: cli-pipeline
    content: Extend `map_up_text.py` and `run_pipeline.py` to accept hOCR inputs and support `--output-hocr` alongside existing ALTO paths.
    status: completed
  - id: tests-docs
    content: Add hOCR example fixture + smoke test; document new hOCR usage in `README.md` and `examples/README.md`.
    status: completed
isProject: false
---

# Integrate hOCR (IA-friendly)

## Goals

- Accept **hOCR input** (IA-favored) as a first-class OCR format for the aligner.
- Continue supporting existing **ALTO input/output**.
- Emit a **minimal IA-compatible** word-level hOCR derivative (`*_hocr.html`) from alignment results (your chosen scope).

## Grounding in current code

- **OCR currently produces ALTO** via Tesseract (`[tesseract_ocr.py](/Users/cfarr/Documents/GitHub/ocr-text-aligner/tesseract_ocr.py)`), and the pipeline expects `out_dir/alto/*.xml` (`[run_pipeline.py](/Users/cfarr/Documents/GitHub/ocr-text-aligner/run_pipeline.py)`).
- Alignment consumes `XMLOBJ.Page/StringWord` from ALTO parsing (`[xml_obj.py](/Users/cfarr/Documents/GitHub/ocr-text-aligner/xml_obj.py)`), and writes aligned ALTO via `[write_aligned_alto.py](/Users/cfarr/Documents/GitHub/ocr-text-aligner/write_aligned_alto.py)`.
- IA’s ecosystem centers around **word-level hOCR** and streaming utilities (see archive-hocr-tools docs: `https://archive-hocr-tools.readthedocs.io/en/latest/`). Your repo already contains IA metadata showing common derivative naming (`*_hocr.html`, etc.) in `[llm_cleaning/dailycolonist349uvic/dailycolonist349uvic_files.xml](/Users/cfarr/Documents/GitHub/ocr-text-aligner/llm_cleaning/dailycolonist349uvic/dailycolonist349uvic_files.xml)`.

## Design

### 1) Introduce an OCR-format abstraction (minimal refactor)

- Keep `XMLOBJ.Page/TextBlock/TextLine/StringWord` as the **internal canonical layout model**.
- Add a single loader function that returns `list[XMLOBJ.Page]` from either format:
  - **ALTO**: call existing `xml_obj.load_pages_from_file()`
  - **hOCR**: new `hocr_obj.load_pages_from_file()` that parses hOCR into the same `XMLOBJ.`* objects
- Add a lightweight format detector:
  - `--ocr-format {alto,hocr}` explicit flag (preferred)
  - or auto-detect by extension (`.xml`→ALTO, `.html/.htm/.gz`→hOCR), but still allow override.

### 2) hOCR parsing into the existing layout model

Create `[hocr_obj.py](/Users/cfarr/Documents/GitHub/ocr-text-aligner/hocr_obj.py)` that:

- Parses hOCR pages (`.ocr_page`) and extracts:
  - **page bbox** → `Page.width/height` (from `bbox x0 y0 x1 y1` in `title`)
  - **word nodes** (`.ocrx_word`) → `StringWord(content, bbox→hpos/vpos/width/height, x_wconf→wc)`
- Builds a conservative block/line structure:
  - Prefer `ocr_carea`→`TextBlock`, `ocr_line`→`TextLine` when present
  - Fallback: single block + line per page if some hierarchy is missing
- Preserves reading order by document order within the hOCR DOM.

**Dependency choice**

- Add `lxml` (recommended) to `[requirements.txt](/Users/cfarr/Documents/GitHub/ocr-text-aligner/requirements.txt)` for robust HTML parsing; alternatively `beautifulsoup4` if you prefer.

### 3) hOCR writer for aligned output (minimal IA derivative)

Create `[write_aligned_hocr.py](/Users/cfarr/Documents/GitHub/ocr-text-aligner/write_aligned_hocr.py)` analogous to `write_aligned_alto.py`:

- Input: original hOCR path + `page` + `hypothesis_list`.
- Update only the **word text content** while keeping layout/IDs/bboxes stable.
- Preserve IA-friendly attributes:
  - keep `title` with `bbox` and `x_wconf` if already present
  - keep/produce `class="ocr_page"`, `ocr_carea`, `ocr_par`, `ocr_line`, `ocrx_word` structure
- Output: a single **word-level** `*_hocr.html` file (your chosen minimal bundle).

### 4) Wire hOCR into the CLI and pipeline

- Update `[map_up_text.py](/Users/cfarr/Documents/GitHub/ocr-text-aligner/map_up_text.py)` to accept either:
  - `--xml-file` (ALTO) **or** `--hocr-file` (hOCR), OR
  - replace with `--ocr-file` and `--ocr-format` (cleaner long-term)
- Extend output options:
  - keep `--output-xml` for ALTO
  - add `--output-hocr` for hOCR
- Update `[run_pipeline.py](/Users/cfarr/Documents/GitHub/ocr-text-aligner/run_pipeline.py)` so `cmd_all` can:
  - use `out_dir/alto/*.xml` when format=ALTO
  - use `out_dir/hocr/*.html` (or a single combined file) when format=hOCR
  - (for now) focus on **align-only** from existing hOCR directories/files; adding Tesseract hOCR generation can be a follow-up.

### 5) Tests + examples

- Add a tiny hOCR fixture under `[examples/sample_page/](/Users/cfarr/Documents/GitHub/ocr-text-aligner/examples/sample_page)` (single page) mirroring the existing ALTO fixture.
- Extend `[tests/test_align_smoke.py](/Users/cfarr/Documents/GitHub/ocr-text-aligner/tests/test_align_smoke.py)`:
  - new test: run alignment from hOCR input and assert `--output-hocr` produces HTML with at least one `.ocrx_word` and updated text.
  - keep existing ALTO smoke test unchanged.

### 6) Documentation

- Update `[README.md](/Users/cfarr/Documents/GitHub/ocr-text-aligner/README.md)` and `[examples/README.md](/Users/cfarr/Documents/GitHub/ocr-text-aligner/examples/README.md)`:
  - show how to run align from hOCR
  - explain the minimal IA derivative produced (`*_hocr.html`) and how it aligns with IA’s hOCR tooling ecosystem (reference archive-hocr-tools docs).

## Non-goals (for this iteration)

- Generating IA’s full derivative bundle (`*_chocr.html.gz`, `*_hocr_pageindex.json.gz`, `*_hocr_searchtext.txt.gz`). (You selected “minimal”.)
- Re-running OCR to produce hOCR directly from Tesseract in this project (can be added later as `tesseract ... hocr`).

