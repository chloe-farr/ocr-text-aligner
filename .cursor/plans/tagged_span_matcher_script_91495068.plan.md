---
name: Tagged span matcher script
overview: Add a single new script that experiments with tagged-span-to-ALTO-block matching (chunk–block fuzzy match, anchor chain) and prints clear, incremental diagnostics to the terminal. No changes to any existing file; the existing pipeline remains untouched.
todos: []
isProject: false
---

# New Script: Tagged Span Matcher (experimental)

## Constraint: no existing code changes

- **Do not modify** [map_up_text.py](map_up_text.py), [write_aligned_alto.py](write_aligned_alto.py), [hyphen_linking.py](hyphen_linking.py), [fuzzy_matching.py](fuzzy_matching.py), [context_matching.py](context_matching.py), [paragraph_reordering.py](paragraph_reordering.py), [llm_tokens.py](llm_tokens.py), [layout_tags.py](layout_tags.py), [xml_obj.py](xml_obj.py), [text_utils.py](text_utils.py), or any other existing module.
- The new script **only imports** from these modules (read-only). Running the existing program (e.g. `map_up_text.py --xml-file ... --clean-text ...`) must work exactly as before.
- All new logic lives in **one new file** at the repo root.

---

## Goal of the new script

Experiment with the strategies we discussed, in isolation:

1. **Tagged spans** — From LLM tagged cleantext, derive spans (each span = one tag + consecutive tokens).
2. **Chunk–block fuzzy match** — For each span, split into chunks (e.g. first N words, next N words). For each chunk, score against each ALTO **block**’s full text (concatenated String CONTENT). Use string fuzzy matching (e.g. RapidFuzz) to find which block(s) best match each chunk.
3. **Anchor chain** — Use the best chunk→block matches to build a candidate “run” of blocks for that span (chunk 1 → block A, chunk 2 → block B, …), without assuming Tesseract block order.
4. **Observable, incremental** — All comparisons, scores, and decisions printed to the terminal in a clear, readable way so you can run it step-by-step and interpret what’s happening.

No integration with the main pipeline; no writing of aligned ALTO. This is a **standalone experiment script** you run separately.

---

## Script name and location

- **File:** `tagged_span_matcher.py` (repo root, next to `map_up_text.py`).

---

## Inputs (CLI)

- `--xml` (required): path to ALTO XML (single page).
- `--clean-text` (required): path to tagged cleantext file (with optional `[TAG]` lines).
- `--chunk-size`: words per chunk (default e.g. 10).
- `--step`: run only up to a given stage (see below).
- `--span`: run only the Nth span (0-based); omit to run all spans.
- `--verbose`: print every chunk×block score; if false, print only best per chunk and summary.

---

## Stages (incremental testing via `--step`)

- **Step 1 — Load and list spans**  
Load ALTO (first page) and tagged cleantext via [llm_tokens.prepare_llm_elements](llm_tokens.py). Group consecutive tokens with the same `layout_tag` into spans. Print a list: span index, tag, token range, word count, and first few words. No matching yet.
- **Step 2 — Chunks per span**  
For each span (or the one selected by `--span`), split into chunks of `--chunk-size` words. Print for each span: chunk index, word range, and the actual chunk text (or first/last word). Still no ALTO comparison.
- **Step 3 — Chunk–block scores**  
For each ALTO block, get “block text” by concatenating all String CONTENT in document order (using [xml_obj](xml_obj.py) Page → TextBlock → TextLine → StringWord). For each chunk (from step 2), score against every block’s text using RapidFuzz (e.g. `fuzz.ratio` or `fuzz.token_sort_ratio` for longer strings). Print: which set (chunk text or chunk summary) is being compared to which block (block ID), and the score. If not `--verbose`, print only the best block per chunk and its score.
- **Step 4 — Anchor chain**  
For each span, build a chain: chunk 0 → best block A, chunk 1 → best block B, … (with optional constraint that B is “after” A in document order, or just report the sequence). Print the resulting candidate block run (e.g. BLOCK_036, BLOCK_037, …) and a short summary (e.g. “Span article_1_headline → blocks 36–37”).

---

## Implementation details

- **Spans from llm_elements:** Walk the list returned by `prepare_llm_elements`; group consecutive tokens that share the same `layout_tag` (including `None`). Each group is one span: `(tag, start_idx, end_idx, list of words)`. Spans with `tag is None` can be skipped or listed as “untagged” depending on desired behavior.
- **ALTO block text:** Iterate `page.content_elements` (TextBlocks); for each block, iterate lines and strings and join `s.content` with a space. Use existing [xml_obj](xml_obj.py) (e.g. `load_first_page`) so block/line order is Tesseract’s document order.
- **Fuzzy scoring:** Use `rapidfuzz.fuzz` (e.g. `fuzz.ratio(chunk_text, block_text)` or `fuzz.token_sort_ratio` for order-robust comparison). The script can import `rapidfuzz` directly; no need to import [fuzzy_matching](fuzzy_matching.py) or [map_up_text](map_up_text.py) for this. Normalize optionally via [text_utils.normalize_for_matching](text_utils.py) for the strings being compared, if you want consistency with the rest of the codebase.
- **Dependencies:** New script imports only: `xml_obj`, `llm_tokens` (for `prepare_llm_elements` and possibly `LLMToken`), `text_utils` (if needed), `rapidfuzz`. No import of `map_up_text`, `hyphen_linking`, `context_matching`, `paragraph_reordering`, or `word_merges`, so the main pipeline is never touched or loaded by this script.

---

## Terminal output (visually clear)

- Use clear **section headers** (e.g. `=== Step 1: Spans ===`, `--- Span 0: article_1_headline ---`).
- For comparisons: short lines like   `Chunk 0 (words 0–10)  vs  BLOCK_036  →  score 87.3`.
- For decisions: a single line like   `Best for chunk 0: BLOCK_036 (87.3)`.
- Use indentation and maybe a fixed width for scores (e.g. `87.3`) so columns line up.
- Keep wording consistent: “chunk”, “block”, “span”, “score”, “best match”, “anchor chain”.

No GUI; all output to stdout so you can run in a terminal and scroll, or redirect to a file.

---

## Scope: keep it simple

- **No** changes to the main mapping pipeline or to how aligned ALTO is produced.
- **No** paragraph reordering, no hyphen linking, no context matching functions should exist inside this script, but can reference respective helper scripts. Those helper scripts may not be modified. 
- **No** writing of ALTO or alignment results; this script only reads ALTO and cleantext and prints diagnostics.
- Optional later: add a “bag match” mode (e.g. for a span, compare word set of chunk to word set of block) for table-like content; for the first version, string fuzzy match is enough.

---

## Summary


| Item           | Detail                                                                            |
| -------------- | --------------------------------------------------------------------------------- |
| New file       | `tagged_span_matcher.py` (repo root)                                              |
| Existing files | Unchanged; script only imports (read-only)                                        |
| Inputs         | `--xml`, `--clean-text`, optional `--chunk-size`, `--step`, `--span`, `--verbose` |
| Steps          | 1=spans, 2=chunks, 3=chunk–block scores, 4=anchor chain                           |
| Fuzzy          | RapidFuzz in script; optional text_utils normalization                            |
| ALTO           | xml_obj.load_first_page; block text = concatenation of String CONTENT per block   |
| Output         | Terminal-only; sections, clear labels, scores, decisions                          |


