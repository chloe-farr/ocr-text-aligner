---
title: OCR Text Aligner
emoji: 📄
colorFrom: blue
colorTo: gray
sdk: gradio
sdk_version: 4.44.1
app_file: app.py
pinned: false
---

# ocr-text-aligner

**What this does:** Maps LLM-cleaned (or otherwise corrected) text back onto ALTO XML from OCR—word by word—using fuzzy matching, context, and layout. You get aligned ALTO/hOCR with per-word confidence scores and optional visualizations.

**Quickstart (align only, no OCR or LLM):**
```bash
pip install -r requirements.txt
python3 src/run_pipeline.py align \
  --xml-file examples/daily_colonist_1972_10_12/page_0000/page_0000.xml \
  --clean-text examples/daily_colonist_1972_10_12/page_0000/page_0000_cleantext.md \
  --output-xml
```
Or using hOCR as input/output:
```bash
python3 src/run_pipeline.py align \
  --hocr-file examples/daily_colonist_1972_10_12/page_0000/page_0000.hocr \
  --clean-text examples/daily_colonist_1972_10_12/page_0000/page_0000_cleantext.md \
  --output-hocr
```

Designed by Chloë Farr. Co-scripted by Chloë Farr and Cursor Agent (up to April 2026, then Claude Code).

Start date of coding: November 21, 2025  
Last updated: May 27, 2026

## GPU / CUDA vs this repository
This aligner is CPU-only. `pip install -r requirements.txt` does not install PyTorch or CUDA.

If you are running the full workflow (PDF → layout models → Chandra / vLLM → clean text → then this tool), the vision and LLM servers may expect a NVIDIA GPU. On a laptop or server without CUDA, you can still run `src/map_up_text.py`; you must configure the upstream pipeline for CPU, smaller batches, or a remote inference host.

## Using the pipeline (digital humanities)
Run OCR → LLM clean → align (or any step alone). You need: an ALTO XML file and a clean text file for alignment; for the full pipeline, a PDF or image and Ollama for the clean step. See Setup and Unified pipeline below.

## Extending the algorithms (ML / research)
The alignment pipeline is modular. For a high-level flow and file/function pointers (fuzzy → context → hyphen/merges → linking → proximity → cross-boundary → output), see [ALGORITHM.md](ALGORITHM.md).

## Setup

### Prerequisites

- Python 3.8 or higher (tested with 3.8+)
- Tesseract (CLI) — e.g. `brew install tesseract`
- For PDF input: pdftoppm (poppler) — e.g. `brew install poppler`
- For LLM clean step (optional): [Ollama](https://ollama.ai)
- For alignment only (skip OCR): an ALTO XML file and a clean text file
- Optional — custom OCR script: Set `TESSERACT_EXPERIMENT_DIR` to the directory containing your `ocr_pdf.sh` to use it instead of the built-in Tesseract pipeline. You can also use a config file: copy `pipeline_config.example.json` to `pipeline_config.json` and set `tesseract_experiment_dir` to that path. The repo does not commit `pipeline_config.json` (it may contain machine-specific paths).

### Installation
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Current State

- **OCR** — Built-in in this repo (`src/tesseract_ocr.py`): run Tesseract on a PDF or image → ALTO XML + plain text. No separate project needed. Optionally, set `TESSERACT_EXPERIMENT_DIR` to use your own OCR script instead.
- **LLM clean text** — Implemented in `src/llm_cleaning/` (Ollama-based refinement). Run via the pipeline or standalone. **Note:** this step is unreliable — LLM output should be manually reviewed before passing it to the aligner. For better results, a VLM-OCR tool (e.g. Chandra, GOT-OCR) is recommended instead; save its output as plain text with all comments, image descriptions, and annotations removed.
- **Alignment** — Implemented in `src/map_up_text.py` (ALTO or hOCR + cleantext → aligned ALTO or hOCR with per-word ALIGNCONF scores and visualizations).

### Unified pipeline (single workflow)

Everything is in this repo. OCR → LLM clean → align (or run any step alone).

1. **Run the full pipeline** (built-in OCR → clean → align):
   ```bash
   python3 src/run_pipeline.py all --input /path/to/document.pdf
   ```
   Or with a single image:
   ```bash
   python3 src/run_pipeline.py all --input /path/to/page.png
   ```
   Output: `pipeline_work/<base>_cleantext.txt`, `pipeline_work/<base>_aligned.xml`, and OCR output under `pipeline_work/ocr_output/<base>/`.

2. **Run steps separately:**
   - **OCR only** (built-in Tesseract; writes `<base>.txt` and `alto/*.xml`):
     ```bash
     python3 src/run_pipeline.py ocr --input /path/to/document.pdf --output-dir pipeline_work/ocr_output/mydoc
     ```
   - **Clean only** (LLM refinement):
     ```bash
     python3 src/run_pipeline.py clean --input-plaintext path/to/plain.txt --output-cleantext path/to/cleantext.txt
     ```
   - **Align only** (ALTO + cleantext → aligned ALTO):
     ```bash
     python3 src/run_pipeline.py align --xml-file path/to.alto.xml --clean-text path/to/cleantext.txt --output-xml
     ```
   - **Align only** (hOCR + cleantext → aligned hOCR):
     ```bash
     python3 src/run_pipeline.py align --hocr-file path/to.hocr.html --clean-text path/to/cleantext.txt --output-hocr
     ```

3. **Use existing OCR output** (skip OCR step):
   ```bash
   python3 src/run_pipeline.py all --ocr-output-dir /path/to/dir/with/base.txt/and/alto/
   ```

4. **Use your own OCR script** instead of built-in: set `TESSERACT_EXPERIMENT_DIR` to the directory containing `ocr_pdf.sh`, then run as above.

OCR output layout (built-in or expected from external): a directory with `<base>.txt` and `alto/*.xml` (one ALTO per page).

**Multi-page**: When you run the full pipeline on a multi-page PDF, the pipeline runs page-by-page. Use `--page-mode` when running the clean step alone for a single-page or page-by-page workflow.

A future GUI can call these same steps (ocr / clean / align / all) with settings for tagging and other options.

### Current workflow (alignment only)

See [PIPELINE_EXPLANATION.md](PIPELINE_EXPLANATION.md) for the logic behind the alignment step.

**Assumptions (when running alignment alone):**
1. An ALTO XML file already exists (e.g., from your Tesseract pipeline).
2. Clean text already exists (from the LLM step, a VLM-OCR tool, or manual correction).

## Usage

**Run the alignment pipeline:**
```bash
python3 src/map_up_text.py --xml-file "path/to/your.alto.xml" --clean-text "path/to/cleantext.txt"
```
To write a new ALTO XML with aligned content:
```bash
python3 src/map_up_text.py --xml-file "path/to/your.alto.xml" --clean-text "path/to/cleantext.txt" --output-xml
```

**Flags**

| Flag | Type | Description |
|------|------|-------------|
| `--xml-file` | path | ALTO XML input file |
| `--hocr-file` | path | hOCR HTML input file (alternative to `--xml-file`) |
| `--clean-text` | path | Clean text file (required) |
| `--output-xml` | optional path | Write aligned ALTO XML; if no path given, writes to `outputs/<pagename>/<pagename>_aligned.xml` |
| `--output-hocr` | optional path | Write aligned hOCR HTML; requires `--hocr-file` input |
| `--fuzzy-cutoff` | float (default: 60) | Minimum fuzzy match score (0–100) for candidate generation. Lower values recover more OCR-noisy words at the cost of more ambiguous candidates. |
| `--show-ocr-accuracy` | flag | Display OCR accuracy analysis at the start |
| `--show-pending` | flag | Print analysis for remaining PENDING words after the pipeline |

**Create a cleaned PDF** from the original PDF or PNG and the aligned ALTO (requires Pillow, reportlab, and poppler for PDF input):
```bash
python3 src/make_cleaned_pdf.py --pdf path/to/original.pdf --aligned-xml path/to/doc_aligned.xml --output path/to/cleaned.pdf
python3 src/make_cleaned_pdf.py --image path/to/page-1.png --aligned-xml path/to/page-1_aligned.xml --output path/to/cleaned.pdf
```

The pipeline produces:
- A terminal summary (matched / error / PENDING word counts before and after)
- A PNG visualization: each word rendered at its ALTO bounding-box position, colored by ALIGNCONF — black (confident) → red (uncertain)
- Aligned ALTO / hOCR (with `--output-xml` / `--output-hocr`), with per-word `ALIGNCONF` attribute (0–100)

## Limitations / Known issues

- Alignment works best when the clean text is close to the OCR content (within ~20% character difference). Heavy rewrites or very poor OCR (below ~70% accuracy) can leave words unmatched.
- Multi-column and multi-article layouts (e.g. newspaper front pages) cause elevated PENDING counts because ALTO spatial reading order diverges from article reading order. These words are matched but unconfirmed by context — they are marked PENDING (lower ALIGNCONF) rather than ERROR. Providing a clean text file in article reading order (rather than spatial block order) significantly reduces this.

## Project Structure

```
src/
  run_pipeline.py        Unified pipeline: OCR → clean → align; single CLI entry point
  map_up_text.py         Main alignment pipeline
  alignment_confidence.py  Per-word ALIGNCONF score (0–100)
  context_matching.py    Candidate scoring and neighbor linking
  fuzzy_matching.py      RapidFuzz wrapper
  hyphen_linking.py      Hyphen/line-wrap handling
  word_merges.py         N:1 and 1:N word merge detection
  paragraph_reordering.py  Cross-boundary PENDING resolution
  weak_fuzzy_matching.py   Geometry + neighbor-strength matching for unresolved words
  proximity_scoring.py   Reading-order distance and column detection
  xml_obj.py             ALTO XML parsing and object model
  hocr_obj.py            hOCR parsing
  llm_tokens.py          Clean-text tokenization and LLM token model
  layout_tags.py         Layout tag parsing from clean text
  text_utils.py          Normalization, HTML entity decoding
  write_aligned_alto.py  Write aligned ALTO XML
  write_aligned_hocr.py  Write aligned hOCR HTML
  visualize_matching.py  Visualization tools
  make_cleaned_pdf.py    Build searchable PDF from original + aligned ALTO
  tesseract_ocr.py       Built-in OCR (Tesseract → ALTO + plain text)
  hocr_combine.py        Combine per-page hOCR into multi-page hOCR
  llm_cleaning/          LLM-based OCR refinement (Ollama)

examples/
  daily_colonist_1972_10_12/  Newspaper front page (1 page, multi-column)
  Gaines_CEAI75/              Academic report (9 pages, single-column)

pipeline_config.example.json  Copy to pipeline_config.json to set custom paths
requirements.txt
```

## Dependencies

Listed in `requirements.txt`: Pillow, reportlab, rapidfuzz, matplotlib, rich, requests. Python 3.8+ and these packages are sufficient for the alignment pipeline; OCR and PDF steps need Tesseract and (for PDF) poppler as well.

## Future Development

- **GUI** — Run any pipeline step (OCR, clean, align) with settings from a single app.
- **Batch processing** — multi-document queue.
- **Unicode normalization** — extend `normalize_for_matching` for non-Latin scripts.

## License

MIT License — see [LICENSE](LICENSE) for details.
