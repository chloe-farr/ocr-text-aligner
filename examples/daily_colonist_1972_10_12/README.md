# Daily Colonist — October 12, 1972

Two pages from the Victoria *Daily Colonist*, digitized at the UVic Library (Kula: Library Futures Academy). Tesseract OCR output (ALTO XML + hOCR) is provided alongside a VLM-cleaned plain text prepared with `prepare_cleantext.py` (see the project's Nextcloud prep folder — not tracked in this repo).

| Page | Content | Words (clean) | Words (Tesseract) |
|------|---------|--------------|-------------------|
| `page_0003` | Editorial page: "Facts Expose Fallacies" (Trudeau economic policy), Philippines martial law, Uruguay Tupamaros, "I Beg to Differ" column, "Today in History" | ~2 250 | ~3 200 |
| `page_0014` | Local news: IWA labor vote, UVic student election, Davis/Indigenous fishing rights, fire hydrant photo essay, jaywalking crackdown | ~1 230 | ~1 630 |

---

## Run alignment — ALTO XML input

```bash
# From project root
python3 run_pipeline.py align \
  --xml-file examples/daily_colonist_1972_10_12/page_0003/page_0003.xml \
  --clean-text examples/daily_colonist_1972_10_12/page_0003/page_0003_cleantext.txt \
  --output-xml
```

```bash
python3 run_pipeline.py align \
  --xml-file examples/daily_colonist_1972_10_12/page_0014/page_0014.xml \
  --clean-text examples/daily_colonist_1972_10_12/page_0014/page_0014_cleantext.txt \
  --output-xml
```

## Run alignment — hOCR input

```bash
python3 run_pipeline.py align \
  --hocr-file examples/daily_colonist_1972_10_12/page_0003/page_0003.hocr \
  --clean-text examples/daily_colonist_1972_10_12/page_0003/page_0003_cleantext.txt \
  --output-hocr
```

```bash
python3 run_pipeline.py align \
  --hocr-file examples/daily_colonist_1972_10_12/page_0014/page_0014.hocr \
  --clean-text examples/daily_colonist_1972_10_12/page_0014/page_0014_cleantext.txt \
  --output-hocr
```

Output goes to `outputs/` by default. Add `--visualize` for an alignment overlay PDF.

---

## About the clean text

The plain-text files were produced by stripping markdown/HTML block markers from the VLM (Chandra/InternVL) per-block outputs, applying spatial column-sort (left→right, top→bottom), and rejoining soft hyphens. The prep script filters `figure`, `figure_caption`, `abandon`, and `gap_fill` element-type blocks entirely, then strips remaining image descriptions by matching common VLM phrasing patterns (`_IMG_STARTS`).

**Known limitation — VLM confabulation.** InternVL/Chandra sometimes generates plausible-sounding but entirely fabricated text, particularly when a block crop includes a photo near text content. These hallucinations don't begin with the typical "A black-and-white photograph…" pattern and pass through the current filter. In these files: page_0003 has one clearly hallucinated passage near the Philippines article (a cabinet-resignations dateline that doesn't exist in the original newspaper). The aligner is robust to this: confabulated words that don't appear in the Tesseract output simply remain unaligned (low confidence), rather than corrupting neighbouring alignments. Use the confidence scores in the aligned XML/hOCR output to identify these regions.
