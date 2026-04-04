# Algorithm overview: OCR text alignment

This document describes the high-level flow of the alignment pipeline and points to the files and functions that implement each stage. It is aimed at researchers and developers who want to understand or modify the algorithm.

## Pipeline flow

1. **Load ALTO and clean text** → build OCR word list and LLM token list.
2. **Fuzzy matching** → assign possible clean-text candidates to each OCR word.
3. **Context matching** → score and narrow candidates using left/right neighbors; link hypotheses by context.
4. **Iterative refinement** (hyphen linking, word merges, context re-runs) until stable.
5. **Proximity / weak fuzzy** → resolve remaining unmatched words using geometry and neighbor strength.
6. **Output** → aligned ALTO (and optional visualizations).

Detailed prose explanation: [PIPELINE_EXPLANATION.md](PIPELINE_EXPLANATION.md).

---

## Stage 1: Load and tokenize

| What | Where |
|------|--------|
| Load ALTO XML, get `Page` and word list | `xml_obj.load_first_page()`, `xml_obj.load_pages_from_file()` in [xml_obj.py](xml_obj.py) |
| Parse clean text into LLM tokens (with optional layout tags) | `prepare_llm_elements()` in [llm_tokens.py](llm_tokens.py); layout tags parsed in [layout_tags.py](layout_tags.py) |

---

## Stage 2: Fuzzy matching

| What | Where |
|------|--------|
| Build hypothesis list: each ALTO word → list of possible clean-word candidates (by string similarity) | `create_hypothesis_list()` in [map_up_text.py](map_up_text.py) |
| Fuzzy match implementation (RapidFuzz) | `fuzzy_match_rapid()`, `best_fuzzy_match_rapid()` in [fuzzy_matching.py](fuzzy_matching.py) |
| Normalization for matching | `normalize_for_matching()` in [text_utils.py](text_utils.py) |

---

## Stage 3: Context matching and linking

| What | Where |
|------|--------|
| Assign LLM candidates to hypotheses by fuzzy match only | `assign_llm_candidates_to_all_token_hypotheses_by_fuzzy_matching()` in [context_matching.py](context_matching.py) |
| Per-hypothesis context scoring (triplet: before, word, after) | `assign_llm_candidates_to_all_token_hypotheses_by_context()`, `calculate_context_scores()`, `find_best_candidates_by_context()` in [context_matching.py](context_matching.py) |
| Narrow candidates by context | `narrow_hypothesis_token_candidates_by_context()` in [context_matching.py](context_matching.py) |
| Choose best candidate per hypothesis and link neighbors | `find_best_candidates_for_all_hypothesis_objects()`, `link_hypothesis_objects_by_context()` in [context_matching.py](context_matching.py) |
| Initial pipeline run (fuzzy + context + link) | `run_candidate_pipeline()` in [map_up_text.py](map_up_text.py) |

---

## Stage 4: Iterative refinement (hyphen, merges, context)

| What | Where |
|------|--------|
| One iteration: split hyphenated triplets, link hyphen pairs, word merges, reference updates, context re-run | `run_one_iteration()` in [map_up_text.py](map_up_text.py) |
| Split hyphenated triplets (e.g. one ALTO word → "word", "-", "continuation") | `split_hyphenated_triplets()` in [hyphen_linking.py](hyphen_linking.py) |
| Link hyphen pairs (line-wrap and similar) | `link_hyphen_pairs()` in [hyphen_linking.py](hyphen_linking.py) |
| Search for word merges (N ALTO words → 1 clean word, or 1 ALTO → N clean) | `search_for_word_merges()` in [word_merges.py](word_merges.py) |
| Re-run context matching after structure changes | `_rerun_context_matching_pipeline()` in [context_matching.py](context_matching.py) |
| Run iterations until stable or max iterations | `run_iterative_pipeline()` in [map_up_text.py](map_up_text.py) |

---

## Stage 5: Proximity and weak fuzzy (unmatched words)

| What | Where |
|------|--------|
| Resolve still-unmatched words using geometry and neighbor strength | `match_weak_fuzzy_words()` in [weak_fuzzy_matching.py](weak_fuzzy_matching.py) |
| Reading-order distance, column awareness | `calculate_reading_order_distance()`, `detect_column_boundaries()` in [proximity_scoring.py](proximity_scoring.py) |
| Proximity score for choosing among multiple matches | `calculate_proximity_score()`, `assess_proximity_for_multiple_matches()` in [proximity_scoring.py](proximity_scoring.py) |

---

## Stage 6: Paragraph reordering and output

| What | Where |
|------|--------|
| Pending-word detection, cross-boundary linking | `is_pending_word()`, `link_cross_boundary_neighbors()` in [paragraph_reordering.py](paragraph_reordering.py) |
| Write aligned ALTO (CONTENT updated, layout preserved) | `write_aligned_alto()` in [write_aligned_alto.py](write_aligned_alto.py) |
| Visualizations (cleaned text overlay, mapping table) | `visualize_cleaned_text_positions()`, `visualize_llm_token_mapping_table()` in [visualize_matching.py](visualize_matching.py) |

---

## Main entry point

The alignment pipeline is invoked from [map_up_text.py](map_up_text.py): load page and words, `prepare_llm_elements()` for clean text, `create_hypothesis_list()`, `run_candidate_pipeline()`, `run_iterative_pipeline()`, then weak-fuzzy and paragraph-reorder steps, then output and optional `write_aligned_alto()`.

---

## Known limitations (for researchers)

- **Paragraph/column boundaries:** Linking uses ALTO spatial neighbors (`before_word` / `after_word`). When clean-text order differs from ALTO spatial order (e.g. across columns or paragraphs), some words stay PENDING. See [docs/PENDING_ANALYSIS.md](docs/PENDING_ANALYSIS.md) for analysis and proposed fixes.
- **Duplicate words:** Multiple instances of the same word in clean text can cause token-instance mismatches; linking correctly rejects wrong instances but those words remain PENDING.
- **Tagged span → ALTO block matching:** [tagged_span_matcher.py](tagged_span_matcher.py) is experimental: chunk–block scoring and anchor-chain logic are not yet correct. Intended for mapping layout-tagged spans to ALTO blocks; to be fixed or rewritten later.
- **ASCII-only normalization:** [text_utils.normalize_for_matching](text_utils.py) strips non-ASCII letters, so languages like German (umlauts, ß) need a Unicode-aware normalization pass; RapidFuzz itself is not English-specific. Backlog item with implementer prompt: [docs/OUTSTANDING_FEATURES.md](docs/OUTSTANDING_FEATURES.md).
