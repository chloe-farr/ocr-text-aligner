# ocr-text-aligner

**What this does:** Maps LLM-cleaned (or otherwise corrected) text back onto ALTO XML from OCR—word by word—using fuzzy matching, context, and layout. You get aligned ALTO and optional searchable PDFs.
**Quickstart (align only, no OCR or LLM):**
```bash
pip install -r requirements.txt
python3 run_pipeline.py align --xml-file examples/sample_page/page-1.xml --clean-text examples/sample_page/page-1_cleantext.txt --output-xml
```
Or using IA-friendly hOCR as input/output:
```bash
python3 run_pipeline.py align --hocr-file examples/sample_page/page-1.hocr.html --clean-text examples/sample_page/page-1_cleantext.txt --output-hocr
```
See examples/README.md for details.

Designed by Chloë Farr. Co-scripted by Chloë Farr and Cursor Agent.

Start date of coding: November 21, 2025
Last updated: April 4, 2026

## ⚠️ GPU / CUDA vs this repository
This aligner is CPU-only. pip install -r requirements.txt does not install PyTorch or CUDA.

If you are running the full workflow (PDF → layout models → Chandra / vLLM → clean text → then this tool), the vision and LLM servers may expect a NVIDIA GPU. On a laptop or server without CUDA, you can still run map_up_text.py; you must configure the upstream pipeline for CPU, smaller batches, or a remote inference host.

Read the full guide: FULL_PIPELINE_AND_CUDA.md (what runs where, nvidia-smi, CPU expectations, Apple Silicon, hyphen-friendly upstream chunking).

Using the pipeline (digital humanities)
Run OCR → LLM clean → align (or any step alone). You need: an ALTO XML file and a clean text file for alignment; for the full pipeline, a PDF or image and Ollama for the clean step. See Setup and Unified pipeline below.

## Extending the algorithms (ML / research)
The alignment pipeline is modular. For a high-level flow and file/function pointers (fuzzy → context → hyphen/merges → linking → proximity), see ALGORITHM.md. Known gaps and analysis (paragraph boundaries, duplicate words) are in docs/PENDING_ANALYSIS.md. Planned backlog items (e.g. Unicode/i18n normalization for matching) are in docs/OUTSTANDING_FEATURES.md. The logic in tagged_span_matcher.py is experimental and not yet correct—see Limitations below.

## Setup

### Prerequisites

- Python 3.8 or higher (tested with 3.8+)
- Tesseract (CLI) — e.g. `brew install tesseract`
- For PDF input: pdftoppm (poppler) — e.g. `brew install poppler`
- For LLM clean step: `Ollama`
- For alignment only (skip OCR): an ALTO XML file and a clean text file
- Optional — custom OCR script: Set TESSERACT_EXPERIMENT_DIR to the directory containing your ocr_pdf.sh to use it instead of the built-in Tesseract pipeline. You can also use a config file: copy pipeline_config.example.json to pipeline_config.json and set tesseract_experiment_dir to that path. The repo does not commit pipeline_config.json (it may contain machine-specific paths).
- Optional: For upstream VLM/layout work, see FULL_PIPELINE_AND_CUDA.md—not required for alignment only.

### Installation
Create a virtual environment:
```bash
python3 -m venv venv
```
Activate the virtual environment:
```bash
source venv/bin/activate
Install required packages:

pip install -r requirements.txt
```
## Current State

- **OCR** — Built-in in this repo (`tesseract_ocr.py`): run Tesseract on a PDF or image → ALTO XML + plain text. No separate project needed. Optionally, set `TESSERACT_EXPERIMENT_DIR` to use your own OCR script instead.
- **LLM clean text** — Implemented in `llm_cleaning/` (Ollama-based refinement). Run via the pipeline or standalone.
- **Alignment** — Implemented in `map_up_text.py` (ALTO or hOCR + cleantext → aligned ALTO or hOCR and visualizations).

### Unified pipeline (single workflow)

Everything is in this repo. One entry point: OCR → LLM clean → align (or run any step alone).

1. **Run the full pipeline** (built-in OCR → clean → align):
   ```bash
   python3 run_pipeline.py all --input /path/to/document.pdf
   ```
   Or with a single image:
   ```bash
   python3 run_pipeline.py all --input /path/to/page.png
   ```
   Output: `pipeline_work/<base>_cleantext.txt`, `pipeline_work/<base>_aligned.xml`, and OCR output under `pipeline_work/ocr_output/<base>/`.

2. **Run steps separately:**
   - **OCR only** (built-in Tesseract; writes `<base>.txt` and `alto/*.xml`):
     ```bash
     python3 run_pipeline.py ocr --input /path/to/document.pdf --output-dir pipeline_work/ocr_output/mydoc
     ```
   - **Clean only** (LLM refinement):
     ```bash
     python3 run_pipeline.py clean --input-plaintext path/to/plain.txt --output-cleantext path/to/cleantext.txt
     ```
   - **Align only** (ALTO + cleantext → aligned ALTO):
     ```bash
     python3 run_pipeline.py align --xml-file path/to.alto.xml --clean-text path/to/cleantext.txt --output-xml
     ```
  - **Align only** (hOCR + cleantext → aligned hOCR):
    ```bash
    python3 run_pipeline.py align --hocr-file path/to.hocr.html --clean-text path/to/cleantext.txt --output-hocr
    ```

3. **Use existing OCR output** (skip OCR step):
   ```bash
   python3 run_pipeline.py all --ocr-output-dir /path/to/dir/with/base.txt/and/alto/
   ```

4. **Use your own OCR script** instead of built-in: set `TESSERACT_EXPERIMENT_DIR` to the directory containing `ocr_pdf.sh`, then run as above. The pipeline will call that script when `--tesseract-dir` (or the env) is set.

OCR output layout (built-in or expected from external): a directory with `<base>.txt` and `alto/*.xml` (one ALTO per page). Built-in OCR also writes `page-1.txt`, `page-2.txt`, … for each page.

**Multi-page (e.g. non-newspaper)**: When you run the full pipeline on a multi-page PDF (or have per-page ALTO + plain text), the pipeline runs **page-by-page**:
- **Clean**: Each page’s plain text (`page-1.txt`, …) is refined with `--page-mode` (one chunk = entire page). Use `--page-mode` when running the clean step alone for a single-page or page-by-page workflow.
- **Align**: Each page’s ALTO is aligned with that page’s cleantext, then all aligned pages are merged into one `*_aligned.xml` file.

A future GUI can call these same steps (ocr / clean / align / all) with settings for tagging and other options.

### Current workflow (alignment only)

See [PIPELINE_EXPLANATION.md](PIPELINE_EXPLANATION.md) for the logic behind the alignment step.

**Assumptions (when running alignment alone):**
1. An ALTO XML file already exists (e.g., from your Tesseract pipeline).
2. Clean text already exists (from the LLM step or elsewhere).

**Important:**
- Pass the ALTO XML file with `--xml-file` and the clean text file with `--clean-text` (both are required).
- To write a new ALTO XML with aligned content, use the `--output-xml` flag (see **Usage** below).

## Usage

1. **Ensure you have an ALTO XML file** and a **clean text file** (LLM-cleaned).

2. **Run the alignment pipeline** (both `--xml-file` and `--clean-text` are required):
   ```bash
   python3 map_up_text.py --xml-file "path/to/your.alto.xml" --clean-text "path/to/cleantext.txt"
   ```
   To also write a new ALTO XML with aligned content:
   ```bash
   python3 map_up_text.py --xml-file "path/to/your.alto.xml" --clean-text "path/to/cleantext.txt" --output-xml
   ```

   **Flags**
   - `--show-table` - bool: Display the full LLM token mapping table in terminal (default: show only summary)
   ```bash
   python3 map_up_text.py --show-table
   ```
   - `--show-ocr-accuracy` - bool: Display OCR accuracy analysis at the beginning
   ```bash
   python3 map_up_text.py --show-ocr-accuracy
   ```
   - `--track-word` - str: Display pipeline flowchart for a specific word
   ```bash
   python3 map_up_text.py --track-word "dams"
   ```
   - `--clean-text` - str: Path to clean text file to use for the pipeline
   ```bash
   python3 map_up_text.py --clean-text "inputs/1972_10_12_p1/1972_10_12_p1_Maclear_Gaglardi_cleantext.txt"
   ```
   - `--xml-file` - str: Path to ALTO XML file to use for the pipeline
   ```bash
   python3 map_up_text.py --xml-file "inputs/1972_10_12_p1/1972_10_12_p1_Tesseract_XML_minus-separatists-kissinger.xml"
   ```
   - `--output-xml` - optional path: Write a new ALTO XML file with CONTENT updated to the aligned (cleaned) text. If the flag is given with no path, the file is written to `outputs/<pagename>/<pagename>_aligned.xml`, where *pagename* is derived from the XML path: if the path starts with `input/`, it is the next segment (e.g. `input/1972_10_12_p1/file.xml` → `1972_10_12_p1`); otherwise it is the XML filename without extension (e.g. `page-1alto-Maclear.xml` → `page-1alto-Maclear`). If a path is given after the flag, that path is used. Handles splits (1→3 words), same-line merges (N→1 with merged bounds), and cross-line merges (first word gets merged text, rest empty).
   ```bash
   python3 map_up_text.py --xml-file "inputs/.../file.xml" --clean-text "inputs/.../cleantext.txt" --output-xml
   python3 map_up_text.py --xml-file "inputs/.../file.xml" --clean-text "inputs/.../cleantext.txt" --output-xml "outputs/my_aligned.xml"
   ```

3. **Create a cleaned PDF** from the original PDF or a single PNG and the aligned ALTO (optional). Requires Pillow and reportlab; for PDF input, `pdftoppm` (poppler) as well.
   ```bash
   python3 make_cleaned_pdf.py --pdf path/to/original.pdf --aligned-xml path/to/doc_aligned.xml --output path/to/cleaned.pdf
   python3 make_cleaned_pdf.py --image path/to/page-1.png --aligned-xml path/to/page-1_aligned.xml --output path/to/cleaned.pdf
   ```
   With `--pdf`: renders each page to an image, draws cleaned text over it, writes a new PDF (if ALTO has fewer pages, only the first N are used). With `--image`: uses the PNG as the single page; ALTO must have exactly one page. The output has a **searchable text layer** from the aligned (cleaned) ALTO.  
   **Note:** Tesseract’s own `tesseract image out pdf` creates a searchable PDF by running OCR; it does *not* accept existing ALTO as input. To use Tesseract’s PDF path (raw OCR, no cleaned ALTO), run:
   ```bash
   python3 make_cleaned_pdf.py --image path/to/page.png --output path/to/out.pdf --tesseract-pdf
   ```

   **Combine flags to display all above**
   ```bash
   python3 map_up_text.py --show-table --show-ocr-accuracy --track-word "dams"
   ```

The script will:
- Load the ALTO XML file (via `--xml-file`) and clean text (via `--clean-text`)
- Process the clean text and perform fuzzy matching and context analysis
- Handle hyphenated words, merges, and splits
- Generate visualizations of the matching process
   - outputs a PNG file with a visualization recreation of the text in place
- Display the final results as a table
   - displayed in the terminal with flag `--show-table`
   - outputs a PDF file with the table
- **With `--output-xml`:** write a new ALTO XML file whose String CONTENT reflects the aligned (cleaned) text; layout and structure are preserved; word IDs are renumbered per line where splits or same-line merges occur.

## Limitations / Known issues

- Alignment works best when the LLM-cleaned (or corrected) text is close to the OCR content and OCR quality is moderate. Heavy rewrites or very poor OCR can leave words unmatched.
- Tested so far mainly on single-article or manually prepared full-page material. Full-page and complex multi-column layouts may need manual prep or future improvements.
- **Tagged span → ALTO block matching:** The logic in `tagged_span_matcher.py` (chunk–block scoring, anchor chain) is experimental and not yet correct; it needs to be written/fixed (e.g. coherence within a span, short-block handling, ordering constraints). For algorithm notes and known issues (paragraph boundaries, duplicate-word resolution), see [ALGORITHM.md](ALGORITHM.md) and [docs/PENDING_ANALYSIS.md](docs/PENDING_ANALYSIS.md). Design notes and plans are in `docs/`.

## Project Structure

- `run_pipeline.py` - **Unified pipeline**: OCR → clean → align; run any step or all. Single entry point for CLI and future GUI.
- `tesseract_ocr.py` - **Built-in OCR**: PDF or image → Tesseract → ALTO XML + plain text (no external script required).
- `pipeline_config.json` - Optional: copy from `pipeline_config.example.json`, then set `tesseract_experiment_dir` to use your own OCR script instead of built-in.
- `map_up_text.py` - Main alignment pipeline module
- `xml_obj.py` - ALTO XML parsing and object model
- `write_aligned_alto.py` - Writes a new ALTO XML file from the alignment result (invoked with `--output-xml`)
- `make_cleaned_pdf.py` - Builds a new PDF from original PDF + aligned ALTO (renders pages, draws cleaned text, outputs PDF)
- `proximity_scoring.py` - Geometric proximity analysis for word matching
- `visualize_matching.py` - Visualization tools for debugging and analysis
- `llm_cleaning/` - LLM-based OCR refinement (Ollama)
- `requirements.txt` - Python package dependencies

## Dependencies

Listed in `requirements.txt`: Pillow, reportlab, rapidfuzz, matplotlib, rich, requests. Python 3.8+ and these dependencies are sufficient for the alignment pipeline; OCR and PDF steps need Tesseract and (for PDF) poppler as well.

## Future Development

Planned features:
- **Unicode-aware matching normalization** — `normalize_for_matching` currently keeps only ASCII letters, so German (ä, ö, ü, ß) and other scripts fail before RapidFuzz runs. See [docs/OUTSTANDING_FEATURES.md](docs/OUTSTANDING_FEATURES.md) for problem statement, file pointers, and a **copy-paste implementer prompt**.
- **GUI** — Run any pipeline step (OCR, clean, align) with settings (e.g. tagging, model, tolerances) from a single app.
- Image pre-processing pipeline (or continue using your existing Tesseract preprocessing).
- Batch processing support.
- Generate a new searchable PDF with the aligned results.

## License

MIT License - See LICENSE file for details.

