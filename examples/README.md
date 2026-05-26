# Examples

## Align only (no OCR, no LLM)

Use the Daily Colonist page to run the alignment step with no external services.

From the **project root**:

```bash
# Install dependencies first (if not already)
pip install -r requirements.txt

# Align cleantext to ALTO and write aligned XML
python3 run_pipeline.py align \
  --xml-file examples/daily_colonist_1972_10_12/page_0000/page_0000.xml \
  --clean-text examples/daily_colonist_1972_10_12/page_0000/page_0000_cleantext.md \
  --output-xml
```

Output: aligned ALTO is written by default to `outputs/page_0000/page_0000_aligned.xml` (or pass a path after `--output-xml` to choose a location). You will also see a pipeline summary in the terminal and visualizations under `outputs/`.

### Align cleantext to hOCR and write aligned hOCR

```bash
python3 run_pipeline.py align \
  --hocr-file examples/daily_colonist_1972_10_12/page_0000/page_0000.hocr \
  --clean-text examples/daily_colonist_1972_10_12/page_0000/page_0000_cleantext.md \
  --output-hocr
```

Output: aligned hOCR is written by default to `outputs/page_0000/page_0000_aligned_hocr.html`.

Same via `map_up_text.py` directly:

```bash
python3 map_up_text.py \
  --xml-file examples/daily_colonist_1972_10_12/page_0000/page_0000.xml \
  --clean-text examples/daily_colonist_1972_10_12/page_0000/page_0000_cleantext.md \
  --output-xml
```

## Full pipeline (OCR → clean → align)

For a full run you need:

- A PDF or image file
- [Ollama](https://ollama.ai) running locally (for the LLM clean step)

Example (from project root):

```bash
python3 run_pipeline.py all --input /path/to/your/document.pdf
```

Outputs go to `pipeline_work/` by default. See the main [README](../README.md) for options (e.g. `--work-dir`, `--model`, `--ocr-output-dir` to skip OCR).

## Sample data

- **examples/daily_colonist_1972_10_12/** — Front page of the *Victoria Daily Colonist*, Oct. 12 1972, with Tesseract ALTO XML + hOCR and a manually ordered clean text. See the [dataset README](daily_colonist_1972_10_12/README.md) for notes on clean-text preparation and expected alignment quality.
