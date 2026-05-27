# Algorithm overview: OCR text alignment

This document describes the high-level flow of the alignment pipeline and points to the files and functions that implement each stage. It is aimed at researchers and developers who want to understand or modify the algorithm.

## Pipeline flow

1. **Load ALTO and clean text** → build OCR word list and LLM token list.
2. **Fuzzy matching** → assign possible clean-text candidates to each OCR word (threshold: `--fuzzy-cutoff`, default 60).
3. **Context matching** → score and narrow candidates using left/right neighbors; link hypotheses by context.
4. **Iterative refinement** (hyphen linking, word merges, context re-runs) until stable.
5. **Proximity / weak fuzzy** → resolve remaining unmatched words using geometry and neighbor strength.
6. **Cross-boundary reconciliation** → link PENDING words whose LLM neighbors live in different ALTO TextBlocks (multi-column / multi-article layouts).
7. **Token stealing** → reassign LLM tokens from low-confidence holders to flagged words with stronger fuzzy scores.
8. **Error-gap fill** → match remaining flagged words with no candidates using neighbor + character-size evidence alone.
9. **Output** → aligned ALTO/hOCR with per-word ALIGNCONF score, and optional visualizations.

Detailed prose explanation: [PIPELINE_EXPLANATION.md](PIPELINE_EXPLANATION.md).

---

## Stage 1: Load and tokenize

| What | Where |
|------|--------|
| Load ALTO XML, get `Page` and word list (stamps `text_block_id` on each word) | `xml_obj.load_first_page()`, `xml_obj.load_pages_from_file()` in [src/xml_obj.py](src/xml_obj.py) |
| Parse clean text into LLM tokens (with optional layout tags) | `prepare_llm_elements()` in [src/llm_tokens.py](src/llm_tokens.py); layout tags parsed in [src/layout_tags.py](src/layout_tags.py) |

---

## Stage 2: Fuzzy matching

| What | Where |
|------|--------|
| Build hypothesis list: each ALTO word → list of possible clean-word candidates (by string similarity above `fuzzy_cutoff`) | `create_hypothesis_list()` in [src/map_up_text.py](src/map_up_text.py) |
| Fuzzy match implementation (RapidFuzz) | `fuzzy_match_rapid()`, `best_fuzzy_match_rapid()` in [src/fuzzy_matching.py](src/fuzzy_matching.py) |
| Normalization for matching | `normalize_for_matching()` in [src/text_utils.py](src/text_utils.py) |

---

## Stage 3: Context matching and linking

| What | Where |
|------|--------|
| Assign LLM candidates to hypotheses by fuzzy match only | `assign_llm_candidates_to_all_token_hypotheses_by_fuzzy_matching()` in [src/context_matching.py](src/context_matching.py) |
| Per-hypothesis context scoring (triplet: before, word, after) | `assign_llm_candidates_to_all_token_hypotheses_by_context()`, `calculate_context_scores()`, `find_best_candidates_by_context()` in [src/context_matching.py](src/context_matching.py) |
| Narrow candidates by context | `narrow_hypothesis_token_candidates_by_context()` in [src/context_matching.py](src/context_matching.py) |
| Choose best candidate per hypothesis and link neighbors | `find_best_candidates_for_all_hypothesis_objects()`, `link_hypothesis_objects_by_context()` in [src/context_matching.py](src/context_matching.py) |
| Cross-block boundary detection (prevents false error-flagging at TextBlock edges) | inline in `assign_llm_candidates_to_all_token_hypotheses_by_context()` using `text_block_id` and vpos fallback |
| Initial pipeline run (fuzzy + context + link) | `run_candidate_pipeline()` in [src/map_up_text.py](src/map_up_text.py) |

---

## Stage 4: Iterative refinement (hyphen, merges, context)

| What | Where |
|------|--------|
| One iteration: split hyphenated triplets, link hyphen pairs, word merges, reference updates, context re-run | `run_one_iteration()` in [src/map_up_text.py](src/map_up_text.py) |
| Split hyphenated triplets (e.g. one ALTO word → "word", "-", "continuation") | `split_hyphenated_triplets()` in [src/hyphen_linking.py](src/hyphen_linking.py) |
| Link hyphen pairs (line-wrap and similar) | `link_hyphen_pairs()` in [src/hyphen_linking.py](src/hyphen_linking.py) |
| Search for word merges (N ALTO words → 1 clean word, or 1 ALTO → N clean) | `search_for_word_merges()` in [src/word_merges.py](src/word_merges.py) |
| Re-run context matching after structure changes | `_rerun_context_matching_pipeline()` in [src/context_matching.py](src/context_matching.py) |
| Run iterations until stable or max iterations | `run_iterative_pipeline()` in [src/map_up_text.py](src/map_up_text.py) |

---

## Stage 5: Proximity and weak fuzzy (unmatched words)

| What | Where |
|------|--------|
| Resolve still-unmatched words using geometry and neighbor strength | `match_weak_fuzzy_words()` in [src/weak_fuzzy_matching.py](src/weak_fuzzy_matching.py) |
| Reading-order distance, column awareness | `calculate_reading_order_distance()`, `detect_column_boundaries()` in [src/proximity_scoring.py](src/proximity_scoring.py) |
| Proximity score for choosing among multiple matches | `calculate_proximity_score()`, `assess_proximity_for_multiple_matches()` in [src/proximity_scoring.py](src/proximity_scoring.py) |

---

## Stage 6: Cross-boundary reconciliation, token stealing, error-gap fill, and output

| What | Where |
|------|--------|
| PENDING-word detection (matched token but neighbor chain broken) | `is_pending_word()` in [src/paragraph_reordering.py](src/paragraph_reordering.py) |
| Cross-boundary linking: swap neighbor assignments across ALTO TextBlock edges to resolve PENDING words | `link_cross_boundary_neighbors()`, `reorder_paragraphs()` in [src/paragraph_reordering.py](src/paragraph_reordering.py) |
| Token stealing: reassign LLM tokens from lower-fuzzy-score holders to flagged words (≥90 score, ≥3 pt gain, ≤15 candidates) | `_apply_token_stealing_pass()` in [src/map_up_text.py](src/map_up_text.py) |
| Error-gap fill: match flagged words with no candidates using neighbor + character-size evidence | final hard-matching loop in [src/map_up_text.py](src/map_up_text.py) |
| Per-word alignment confidence score (0–100), written to ALTO `ALIGNCONF` / hOCR `alignconf` attributes | `alignment_confidence()` in [src/alignment_confidence.py](src/alignment_confidence.py) |
| Write aligned ALTO (CONTENT updated, layout preserved) | `write_aligned_alto()` in [src/write_aligned_alto.py](src/write_aligned_alto.py) |
| Write aligned hOCR | `write_aligned_hocr()` in [src/write_aligned_hocr.py](src/write_aligned_hocr.py) |
| Visualization: ALIGNCONF-based black→red gradient overlay (black = confident, red = uncertain) | `visualize_cleaned_text_positions()` in [src/visualize_matching.py](src/visualize_matching.py) |

---

## Main entry point

The alignment pipeline is invoked from [src/map_up_text.py](src/map_up_text.py): load page and words, `prepare_llm_elements()` for clean text, `create_hypothesis_list()`, `run_candidate_pipeline()`, `run_iterative_pipeline()`, then weak-fuzzy, cross-boundary reconciliation, token stealing, error-gap fill, then output and optional `write_aligned_alto()` / `write_aligned_hocr()`.

---

## Known limitations (for researchers)

- **Multi-column / multi-article layout:** When clean-text reading order differs from ALTO spatial order (e.g. across newspaper columns), some words remain PENDING after cross-boundary reconciliation. This is structural: the aligner can't recover article membership without layout segmentation. Words are marked PENDING (lower ALIGNCONF) rather than ERROR. Single-column documents are largely unaffected.
- **Duplicate words:** Multiple instances of the same word in clean text can cause token-instance mismatches; linking correctly rejects wrong instances but those words may remain PENDING.
- **Unicode normalization:** `normalize_for_matching()` in [src/text_utils.py](src/text_utils.py) is Unicode-aware for basic Latin but non-Latin scripts (e.g. Arabic, CJK) are not tested. RapidFuzz itself is not English-specific.
