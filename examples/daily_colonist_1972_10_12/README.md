# Daily Colonist — October 12, 1972

Front page of the Victoria *Daily Colonist*, digitized at the UVic Library (Kula: Library Futures Academy). Tesseract OCR output (ALTO XML + hOCR) is provided alongside a manually ordered clean text prepared from VLM (Chandra/InternVL) per-block outputs.

| Page | Content | Words (clean) | Words (Tesseract) |
|------|---------|--------------|-------------------|
| `page_0000` | Front page: Hanoi bombing witness report (Michael Maclear/CTV), Bennett opposition seat, Gaglardi reaction, industry power costs, food prices, hostage-taking, Quebec election, U.S. bombing mission | ~2 100 | ~2 450 |

---

## Run alignment — ALTO XML input

```bash
# From project root
python3 run_pipeline.py align \
  --xml-file examples/daily_colonist_1972_10_12/page_0000/page_0000.xml \
  --clean-text examples/daily_colonist_1972_10_12/page_0000/page_0000_cleantext.md \
  --output-xml
```

## Run alignment — hOCR input

```bash
python3 run_pipeline.py align \
  --hocr-file examples/daily_colonist_1972_10_12/page_0000/page_0000.hocr \
  --clean-text examples/daily_colonist_1972_10_12/page_0000/page_0000_cleantext.md \
  --output-hocr
```

Output goes to `outputs/` by default.

---

## About the clean text

`page_0000_cleantext.md` is a manually ordered plain-text transcription of the page. VLM per-block outputs were arranged into article-reading order and lightly edited to remove OCR artefacts. The manual ordering is important: the aligner's context-matching pass uses token neighbors to resolve ambiguous matches, so article-ordered text yields significantly fewer PENDING words than spatially-sorted block output.

**Known limitation — multi-column layout.** Newspaper front pages pack multiple articles into narrow columns. The aligner assigns each Tesseract word to its best LLM token match, but context verification (neighbor links) can still fail at article boundaries where ALTO spatial order diverges from article reading order. These words are marked PENDING (lower ALIGNCONF) rather than ERROR. With a manually ordered clean text, this page achieves ~3.8% error rate and ~80% confirmed matches.
