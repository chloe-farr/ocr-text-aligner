# Gaines — Control Engineering and Artificial Intelligence (1975)

9-page academic report by B.R. Gaines, digitized at the UVic Library. Tesseract OCR output (ALTO XML + hOCR) and VLM (Chandra/InternVL) per-block clean text are provided.

| Pages | Content | Words (clean) | Words (Tesseract) |
|-------|---------|--------------|-------------------|
| 1–7 | Body text (single-column) | ~400–500 / page | ~450–550 / page |
| 8 | Bibliography | ~185 | ~210 |
| 9 | Short closing section | ~200 | ~220 |

---

## Run alignment — ALTO XML input

```bash
# From project root
python3 src/run_pipeline.py align \
  --xml-file examples/Gaines_CEAI75/CEAI75_tesseract_out/page-1.xml \
  --clean-text examples/Gaines_CEAI75/CEAI75_chandra_out/page-1/page-1/page-1.md \
  --output-xml examples/Gaines_CEAI75/CEAI75_aligned/page-1_aligned.xml
```

## Run alignment — hOCR input

```bash
python3 src/run_pipeline.py align \
  --hocr-file examples/Gaines_CEAI75/CEAI75_tesseract_out/page-1.hocr \
  --clean-text examples/Gaines_CEAI75/CEAI75_chandra_out/page-1/page-1/page-1.md \
  --output-hocr examples/Gaines_CEAI75/CEAI75_aligned/page-1_aligned.hocr
```

Pre-generated aligned XML, hOCR, and visualization PNGs for all 9 pages are in `CEAI75_aligned/`.

---

## About the clean text

Per-page clean text was produced by Chandra (InternVL) with per-block OCR outputs stored under `CEAI75_chandra_out/`. Each page has its own subdirectory containing a `.md` (plain text), `.html`, and `_metadata.json`.

Single-column academic layout means ALTO reading order matches article reading order throughout, so context matching works well. Pages 1–7 achieve ~1–2% error rate; page 8 (bibliography, dense citation formatting) reaches ~3%.

See `fuzzy_cutoff_comparison.md` for results at `--fuzzy-cutoff` values of 80, 70, and 60.
