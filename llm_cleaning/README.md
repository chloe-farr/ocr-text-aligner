# LLM-based OCR Text Cleaning

This module provides chunked, iterative refinement of OCR text using local Ollama models. It processes OCR text in chunks, iteratively refines each chunk until stable, and validates outputs to prevent hallucination.

## Installation

### Prerequisites

- Python 3.10+
- Ollama running locally (default: `http://localhost:11434`)
- Models available: `qwen2.5:14b`, `mistral:7b` (or other compatible models)

### Dependencies

Install required packages:

```bash
pip install requests rapidfuzz
```

Or install from the project root:

```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

```bash
python -m llm_cleaning.ocr_refiner --in input.txt --out output.txt
```

### With Custom Model

```bash
python -m llm_cleaning.ocr_refiner --in input.txt --out output.txt --model mistral:7b
```

### With Document Metadata

```bash
python -m llm_cleaning.ocr_refiner \
  --in input.txt \
  --out output.txt \
  --year 1972 \
  --month 10 \
  --location "Victoria, Canada" \
  --document_type "Newspaper"
```

python3 -m llm_cleaning.ocr_refiner --in llm_cleaning/1862_04_21_small.txt --out "llm_cleaning/1862_04_21_cleantext_small.txt" --year 1862 --month 4 --location "Victoria, Canada" --document_type "Newspaper" --debug

### With Custom Parameters

```bash
python -m llm_cleaning.ocr_refiner \
  --in input.txt \
  --out output.txt \
  --max-iters 8 \
  --wc-tol 0.20 \
  --cc-tol 0.20 \
  --novel-tok-ratio 0.15 \
  --min-tokens 200 \
  --max-tokens 700 \
  --overlap-lines 3
```

### Debug Mode

```bash
python -m llm_cleaning.ocr_refiner \
  --in input.txt \
  --out output.txt \
  --debug
```

## Command-Line Options

### Input/Output
- `--in`: Input OCR text file (required)
- `--out`: Output refined text file (required)

### Model
- `--model`: Ollama model name (default: `qwen2.5:14b`)

### Refinement Parameters
- `--max-iters`: Maximum refinement iterations per chunk (default: 6)
- `--wc-tol`: Word count tolerance, e.g., 0.15 = ±15% (default: 0.15)
- `--cc-tol`: Character count tolerance, e.g., 0.15 = ±15% (default: 0.15)
- `--novel-tok-ratio`: Maximum novel token ratio (default: 0.12)

### Chunking Parameters
- `--min-tokens`: Minimum word count per chunk (default: 150)
- `--max-tokens`: Maximum word count per chunk (default: 600)
- `--overlap-lines`: Number of lines to overlap between chunks (default: 2)

### Document Metadata (Optional)
- `--year`: Document year
- `--month`: Document month
- `--location`: Publication location

### Debugging
- `--debug`: Enable debug logging

## How It Works

### 1. Chunking

The OCR text is split into chunks with:
- **Sentence-aware boundaries**: Chunks break at likely sentence endings when minimum token count is reached
- **Overlap**: Each chunk includes overlap lines from the previous chunk to maintain context
- **Token limits**: Chunks respect min/max token counts

### 2. Iterative Refinement

For each chunk:
1. **Initial state**: Start with raw OCR text
2. **Iteration loop**:
   - Send OCR chunk and current refined text to LLM
   - Parse response (DECISION: STOP|CONTINUE, TEXT: ...)
   - Validate output (length ratios, novel tokens, fuzzy similarity)
   - If validation fails: retry once with stricter settings
   - If validation passes: accept as new current state
   - Stop if: DECISION is STOP, or output stabilizes (no change), or max iterations reached

### 3. Validation Gates

Outputs are validated using:
- **Length ratios**: Word and character counts must stay within tolerance of OCR
- **Novel token ratio**: New words not in OCR must be below threshold (stopwords excluded)
- **Fuzzy similarity**: Optional check to catch catastrophic rewrites

### 4. Stitching

Refined chunks are stitched together:
- Overlap is removed using line-based or fuzzy matching
- Chunks are joined with double newlines

## Tuning Guide

### When to Loosen Tolerances

**Increase `--wc-tol` and `--cc-tol` (e.g., 0.20-0.25)** when:
- OCR has many formatting issues (extra spaces, line breaks)
- Document has complex layout (tables, columns)
- OCR quality is very poor (many character errors)

**Increase `--novel-tok-ratio` (e.g., 0.15-0.20)** when:
- OCR has many character-level errors that require word reconstruction
- Document uses domain-specific terminology that OCR misreads
- OCR consistently misreads certain character patterns

### When to Tighten Tolerances

**Decrease `--wc-tol` and `--cc-tol` (e.g., 0.10-0.12)** when:
- OCR quality is good and you want strict preservation
- Document has precise formatting requirements
- You want to catch any hallucination early

**Decrease `--novel-tok-ratio` (e.g., 0.08-0.10)** when:
- You want to prevent any creative interpretation
- OCR is mostly accurate with minor errors
- Document requires exact preservation

### Chunking Tuning

**Increase `--min-tokens` (e.g., 200-250)** when:
- Document has long sentences
- You want fewer, larger chunks (faster, but may hit context limits)

**Decrease `--min-tokens` (e.g., 100-120)** when:
- Document has many short sentences
- You want more granular refinement

**Increase `--max-tokens` (e.g., 700-800)** when:
- Using models with larger context windows
- Document has long paragraphs

**Decrease `--max-tokens` (e.g., 400-500)** when:
- Using smaller models
- Want more frequent sentence-boundary breaks

**Increase `--overlap-lines` (e.g., 3-4)** when:
- Document has complex context dependencies
- Chunks may break mid-sentence

**Decrease `--overlap-lines` (e.g., 1)** when:
- Document has clear paragraph boundaries
- Want to minimize redundant processing

### Iteration Tuning

**Increase `--max-iters` (e.g., 8-10)** when:
- OCR quality is very poor
- Document requires multiple refinement passes
- Model tends to make incremental improvements

**Decrease `--max-iters` (e.g., 4-5)** when:
- OCR quality is good
- Model tends to stabilize quickly
- Want faster processing

## Example Workflow

```bash
# 1. Basic refinement
python -m llm_cleaning.ocr_refiner \
  --in inputs/1972_10_12_p1/1972_10_12_p1_plaintext.txt \
  --out outputs/1972_10_12_p1/1972_10_12_p1_cleantext.txt \
  --year 1972 \
  --month 10 \
  --location "Vancouver"

# 2. Use refined text with mapping pipeline
python map_up_text.py \
  --xml-file inputs/1972_10_12_p1/1972_10_12_p1_Tesseract_XML_Maclear.xml \
  --clean-text outputs/1972_10_12_p1/1972_10_12_p1_cleantext.txt
```

## Architecture

### Module Structure

- `chunker.py`: Chunking logic with sentence-aware boundaries
- `prompts.py`: System and user prompt templates
- `validators.py`: Validation gates (length, novel tokens, fuzzy)
- `ocr_refiner.py`: Main refinement loop, Ollama client, CLI

### Key Design Decisions

1. **Order-insensitive validation**: Validates length and tokens without requiring exact word order (handles OCR layout chaos)
2. **Iterative refinement**: Fixed-point iteration per chunk until stable
3. **Retry mechanism**: Single retry with stricter settings on validation failure
4. **Chunk overlap**: Maintains context across chunk boundaries
5. **Strict output format**: Requires DECISION and TEXT markers for parsing

## Limitations

- Requires Ollama running locally
- No support for preserving OCR word IDs (separate alignment task)
- No GUI (CLI only)
- No external web calls (local models only)
- Chunking is line-based (may not handle complex layouts perfectly)

## Troubleshooting

### "Connection refused" or API errors
- Ensure Ollama is running: `ollama serve`
- Check model is available: `ollama list`
- Verify model name matches exactly

### Validation failures
- Check `--debug` output for specific failure reasons
- Consider loosening tolerances if OCR quality is poor
- Verify model is following output format (DECISION/TEXT)

### Slow processing
- Reduce `--max-iters`
- Increase `--max-tokens` to process fewer chunks
- Use smaller model (e.g., `mistral:7b` instead of `qwen2.5:14b`)

### Output quality issues
- Tighten tolerances to prevent hallucination
- Increase `--max-iters` for more refinement passes
- Provide document metadata (`--year`, `--location`) for better context

