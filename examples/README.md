# Examples

## Align only (no OCR, no LLM)

Use one of the Daily Colonist pages to run the alignment step with no external services.

From the **project root**:

```bash
# Install dependencies first (if not already)
pip install -r requirements.txt

# Align cleantext to ALTO and write aligned XML
python3 run_pipeline.py align \
  --xml-file examples/daily_colonist_1972_10_12/page_0014/page_0014.xml \
  --clean-text examples/daily_colonist_1972_10_12/page_0014/page_0014_cleantext.txt \
  --output-xml
```

Output: aligned ALTO is written by default to `outputs/page_0014/page_0014_aligned.xml` (or pass a path after `--output-xml` to choose a location). You will also see a pipeline summary in the terminal and, by default, visualizations under `outputs/`.

### Align cleantext to hOCR (IA-friendly) and write aligned hOCR

```bash
python3 run_pipeline.py align \
  --hocr-file examples/daily_colonist_1972_10_12/page_0014/page_0014.hocr \
  --clean-text examples/daily_colonist_1972_10_12/page_0014/page_0014_cleantext.txt \
  --output-hocr
```

Output: aligned hOCR is written by default to `outputs/page_0014/page_0014_aligned_hocr.html` (or pass a path after `--output-hocr` to choose a location).

Same via `map_up_text.py` directly:

```bash
python3 map_up_text.py \
  --xml-file examples/daily_colonist_1972_10_12/page_0014/page_0014.xml \
  --clean-text examples/daily_colonist_1972_10_12/page_0014/page_0014_cleantext.txt \
  --output-xml
```

And for hOCR:

```bash
python3 map_up_text.py \
  --hocr-file examples/daily_colonist_1972_10_12/page_0014/page_0014.hocr \
  --clean-text examples/daily_colonist_1972_10_12/page_0014/page_0014_cleantext.txt \
  --output-hocr
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

- **examples/daily_colonist_1972_10_12/** — Two pages from the *Victoria Daily Colonist*, Oct. 12 1972, with Tesseract ALTO XML + hOCR and VLM-prepared clean text. `page_0003` is the editorial/opinion page (international news); `page_0014` is a local news page. See the [dataset README](daily_colonist_1972_10_12/README.md) for full run commands and notes on the clean-text quality.
