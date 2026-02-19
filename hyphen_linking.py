"""
Hyphen linking functions for OCR text alignment.

Handles detection and linking of hyphenated words, including:
- Internal hyphens (e.g., "assignment-his" → "assignment" "-" "his")
- Word-wrap hyphens (e.g., "Wednes-" + "day" → "Wednesday")
- Non-literal hyphen splits (e.g., "dams" + "aged" → "damaged")
"""

from rapidfuzz import fuzz
from typing import List, Optional, Dict, Tuple, TYPE_CHECKING
import text_utils
import proximity_scoring
import xml_obj as XMLOBJ
import fuzzy_matching
import context_matching

if TYPE_CHECKING:
    from map_up_text import TokenHypotheses, TokenCandidate, LLMToken
else:
    # Import at runtime to avoid circular imports
    TokenHypotheses = None
    TokenCandidate = None
    LLMToken = None


def _has_internal_hyphen(word: XMLOBJ.StringWord) -> bool:
    """
    Check if a word has an internal hyphen (not just trailing or leading).
    
    Args:
        word: ALTO StringWord to check
        
    Returns:
        True if word contains hyphen in the middle (e.g., "assignment-his"), False otherwise
    """
    decoded = text_utils.decode_html_entities(word.content)
    stripped = decoded.strip()
    
    # Check if any hyphen variant exists and is not just at the edges
    for hyphen in text_utils.HY_PHENS:
        if hyphen in stripped:
            # Check if hyphen is at the very start
            if stripped.startswith(hyphen):
                continue  # Leading hyphen, not internal
            # Check if hyphen is at the very end (trailing hyphen for word wrap)
            if stripped.endswith(hyphen):
                continue  # Trailing hyphen, not internal
            # Hyphen exists and is not at edges - it's internal
            return True
    return False


def _detect_hyphenated_triplet_pattern(
    alto_word: XMLOBJ.StringWord,
    llm_elements: List['LLMToken']
) -> Optional[Tuple[str, str, str, 'LLMToken', 'LLMToken', 'LLMToken']]:
    """
    Detect if an ALTO word with internal hyphen should be split into a triplet
    matching clean text pattern: word1 - word2
    
    Args:
        alto_word: ALTO word with internal hyphen (e.g., "assignment-his")
        llm_elements: List of all LLM tokens from clean text
        
    Returns:
        Tuple of (word1, hyphen_char, word2, llm_word1, llm_hyphen, llm_word2) if detected,
        None otherwise
    """
    decoded = text_utils.decode_html_entities(alto_word.content)
    
    # Split on hyphen variants to get parts
    # Try each hyphen type to find the actual separator
    for hyphen_char in text_utils.HY_PHENS:
        if hyphen_char in decoded:
            parts = decoded.split(hyphen_char, 1)  # Split only on first occurrence
            if len(parts) == 2:
                word1_alto = parts[0].strip()
                word2_alto = parts[1].strip()
                
                if not word1_alto or not word2_alto:
                    continue  # Invalid split, try next hyphen
                
                # Normalize parts for matching
                word1_normalized = text_utils.normalize_for_matching(word1_alto)
                word2_normalized = text_utils.normalize_for_matching(word2_alto)
                
                # Search LLM elements for the triplet pattern: word1, hyphen, word2
                for i in range(len(llm_elements) - 2):
                    llm_word1 = llm_elements[i]
                    llm_hyphen = llm_elements[i + 1]
                    llm_word2 = llm_elements[i + 2]
                    
                    # Check if word1 matches
                    word1_match = False
                    if llm_word1.word_normalized == word1_normalized:
                        word1_match = True
                    else:
                        # Try fuzzy match
                        word1_fuzzy = fuzz.ratio(word1_normalized, llm_word1.word_normalized)
                        if word1_fuzzy >= 85.0:
                            word1_match = True
                    
                    if not word1_match:
                        continue
                    
                    # Check if middle token is a hyphen
                    hyphen_match = False
                    hyphen_text = text_utils.decode_html_entities(llm_hyphen.word)
                    # Normalize hyphen - it should match the hyphen character or variants
                    hyphen_normalized = text_utils.normalize_for_matching(hyphen_text)
                    
                    # Check if it's a hyphen character (normalized might be empty, so check original)
                    if hyphen_text.strip() in text_utils.HY_PHENS or hyphen_text.strip() == hyphen_char:
                        hyphen_match = True
                    elif not hyphen_normalized and hyphen_text.strip() in text_utils.HY_PHENS:
                        # Hyphen normalizes to empty string
                        hyphen_match = True
                    
                    if not hyphen_match:
                        continue
                    
                    # Check if word2 matches
                    word2_match = False
                    if llm_word2.word_normalized == word2_normalized:
                        word2_match = True
                    else:
                        # Try fuzzy match
                        word2_fuzzy = fuzz.ratio(word2_normalized, llm_word2.word_normalized)
                        if word2_fuzzy >= 85.0:
                            word2_match = True
                    
                    if word2_match:
                        # Found the triplet pattern!
                        return (word1_alto, hyphen_char, word2_alto, llm_word1, llm_hyphen, llm_word2)
    
    return None


def _setup_split_triplets(
    split_hypotheses: List['TokenHypotheses'],
    original_anchor: XMLOBJ.StringWord
) -> None:
    """
    Set up before_word/after_word triplets for split hypotheses.
    Modifies split_hypotheses in place.
    
    Args:
        split_hypotheses: List of split hypotheses to set up
        original_anchor: Original anchor word before splitting
    """
    for i, split_hyp in enumerate(split_hypotheses):
        if i == 0:
            # First split
            split_hyp.anchor.before_word = original_anchor.before_word
            if len(split_hypotheses) > 1:
                split_hyp.anchor.after_word = split_hypotheses[1].anchor
            else:
                split_hyp.anchor.after_word = original_anchor.after_word
        elif i == len(split_hypotheses) - 1:
            # Last split
            split_hyp.anchor.before_word = split_hypotheses[i-1].anchor
            split_hyp.anchor.after_word = original_anchor.after_word
        else:
            # Middle split
            split_hyp.anchor.before_word = split_hypotheses[i-1].anchor
            split_hyp.anchor.after_word = split_hypotheses[i+1].anchor


def _create_candidate_fuzzy_lookups(
    split_hypotheses: List['TokenHypotheses']
) -> List[Dict[int, 'LLMToken']]:
    """
    Create optimized lookup dictionaries for fast token matching.
    
    Args:
        split_hypotheses: List of split hypotheses
    
    Returns:
        List of lookup dictionaries, one per split hypothesis
    """
    candidate_fuzzy_lookups: List[Dict[int, 'LLMToken']] = []
    for split_hyp in split_hypotheses:
        lookup = {}
        if len(split_hyp.candidates) > 0:
            # Build a dict mapping id(token) -> token for fast lookups
            for token in split_hyp.candidates[0].possible_llm_elements_by_fuzzy_match:
                lookup[id(token)] = token
        candidate_fuzzy_lookups.append(lookup)
    return candidate_fuzzy_lookups


def _search_all_words_for_exact_match(
    hyp1: 'TokenHypotheses',
    i: int,
    all_other_indices: List[int],
    hypothesis_list: List['TokenHypotheses'],
    processed_indices: set,
    search_indices_pass1: List[int],
    is_literal_hyphen: bool,
    base1: str,
    decoded_w1: str,
    clean_vocab: set[str],
    llm_word_lookup: Dict[str, List['LLMToken']]
) -> Optional[Tuple[str, float, int, 'LLMToken', float]]:
    """
    Search all remaining words for exact vocabulary matches (handles paragraph reordering).
    
    Args:
        hyp1: First hypothesis
        i: Current index in hypothesis_list
        all_other_indices: List of indices not in prioritized_indices
        hypothesis_list: List of all hypotheses
        processed_indices: Set of already processed indices
        search_indices_pass1: Indices already searched in pass 1
        is_literal_hyphen: Whether hyp1 ends with a literal hyphen
        base1: Base word without trailing hyphens (if literal hyphen)
        decoded_w1: Decoded content of hyp1
        clean_vocab: Set of normalized vocabulary words
        llm_word_lookup: Lookup dictionary for LLM tokens
    
    Returns:
        Tuple of (best_match, best_match_score, best_partner_idx, best_llm_token, best_context_score)
        or None if no match found
    """
    for j in all_other_indices:
        if j in processed_indices or j in search_indices_pass1:
            continue  # Skip if already processed in pass 1
        
        hyp2 = hypothesis_list[j]
        
        # Decode and normalize second word
        decoded_w2 = text_utils.decode_html_entities(hyp2.anchor.content)
        normalized_w2 = text_utils.normalize_for_matching(decoded_w2)
        
        # Try combining: base1 + w2 (for literal hyphens) or w1 + w2 (for non-hyphen splits)
        if is_literal_hyphen:
            merged = base1 + decoded_w2
            # Also try with hyphen inserted (for words like "anti-aircraft")
            merged_with_hyphen = base1 + "-" + decoded_w2
        else:
            merged = decoded_w1 + decoded_w2
            merged_with_hyphen = None
        
        merged_normalized = text_utils.normalize_for_matching(merged)
        
        if not merged_normalized:
            continue
        
        # Check for exact match in vocab (try both with and without hyphen)
        candidates_to_check = [merged_normalized]
        if merged_with_hyphen is not None:
            candidates_to_check.append(text_utils.normalize_for_matching(merged_with_hyphen))
        
        # First try exact matches
        for candidate_normalized in candidates_to_check:
            if candidate_normalized in clean_vocab:
                # Found exact match - this is a valid combination despite distance
                matching_llm_tokens = llm_word_lookup.get(candidate_normalized, [])
                if matching_llm_tokens:
                    # When multiple LLM tokens match, select the one with best context
                    best_llm_token = matching_llm_tokens[0]
                    best_context_score = 0.0
                    for llm_token in matching_llm_tokens:
                        before_score, after_score = context_matching.calculate_context_scores(
                            hyp1.anchor.before_word, hyp2.anchor.after_word, llm_token, None
                        )
                        context_score = (before_score + after_score) / 2.0
                        if context_score > best_context_score:
                            best_context_score = context_score
                            best_llm_token = llm_token
                    return (
                        candidate_normalized,
                        100.0,
                        j,
                        best_llm_token,
                        best_context_score
                    )
        
        # If no exact match, try fuzzy matching
        best_fuzzy_match = None
        best_fuzzy_score = 0.0
        for candidate_normalized in candidates_to_check:
            fuzzy_matches = fuzzy_matching.fuzzy_match_rapid(candidate_normalized, clean_vocab, cutoff=80.0, limit=1)
            if fuzzy_matches:
                match_tuple = fuzzy_matches[0]
                match_word = match_tuple[0]
                match_score = match_tuple[1]
                if match_score > best_fuzzy_score:
                    best_fuzzy_score = match_score
                    best_fuzzy_match = match_word
        
        # Use fuzzy match if score is high enough
        if best_fuzzy_match and best_fuzzy_score >= 80.0:
            matching_llm_tokens = llm_word_lookup.get(best_fuzzy_match, [])
            if matching_llm_tokens:
                # When multiple LLM tokens match, select the one with best context
                best_llm_token = matching_llm_tokens[0]
                best_context_score = 0.0
                for llm_token in matching_llm_tokens:
                    before_score, after_score = context_matching.calculate_context_scores(
                        hyp1.anchor.before_word, hyp2.anchor.after_word, llm_token, None
                    )
                    context_score = (before_score + after_score) / 2.0
                    if context_score > best_context_score:
                        best_context_score = context_score
                        best_llm_token = llm_token
                return (
                    best_fuzzy_match,
                    best_fuzzy_score,
                    j,
                    best_llm_token,
                    best_context_score
                )
    
    return None


def _create_combined_hypothesis(
    hyp1: 'TokenHypotheses',
    hyp2: 'TokenHypotheses',
    best_match: str,
    best_match_score: float,
    best_llm_token: 'LLMToken'
) -> 'TokenHypotheses':
    """
    Create a combined TokenHypotheses from two hypotheses.
    
    Args:
        hyp1: First hypothesis
        hyp2: Second hypothesis (partner)
        best_match: Best matched word form
        best_match_score: Score of the match
        best_llm_token: Best matching LLM token
    
    Returns:
        Combined TokenHypotheses object
    """
    # Import at runtime to avoid circular imports
    from map_up_text import TokenHypotheses, TokenCandidate
    
    # Calculate actual context scores using helper function
    before_score, after_score = context_matching.calculate_context_scores(
        hyp1.anchor.before_word,
        hyp2.anchor.after_word,
        best_llm_token,
        None
    )
    
    # Create combined TokenHypotheses
    # Use hyp1's anchor as base, but combine both words
    combined_anchor = hyp1.anchor
    combined_hypothesis = TokenHypotheses(
        anchor=combined_anchor,
        anchor_left=hyp1.anchor.before_word,  # Combined word gets hyp1's left neighbor
        anchor_right=hyp2.anchor.after_word   # Combined word gets hyp2's right neighbor
    )
    
    # Create candidate with both ALTO words
    combined_candidate = TokenCandidate(
        clean_form=best_match,
        kind="word",
        alto_words=[hyp1.anchor, hyp2.anchor],
        fuzzy_score=best_match_score
    )
    combined_candidate.possible_llm_elements_by_fuzzy_match = [best_llm_token]
    combined_candidate.possible_llm_elements_by_context = [(best_llm_token, before_score, after_score)]
    combined_hypothesis.candidates.append(combined_candidate)
    # Only assign if LLM token is not already matched to another hypothesis
    # If already matched, leave as PENDING - it will be resolved later
    if not best_llm_token.matched:
        combined_hypothesis.chosen_LLM_token = best_llm_token
        combined_hypothesis.chosen_index = 0
        combined_hypothesis.flagged_for_error = False
        # Mark as matched immediately to prevent conflicts
        best_llm_token.matched = True
    # If already matched, leave as PENDING (will be resolved later)
    
    # Set context: before word from hyp1, after word from hyp2
    combined_hypothesis.anchor.before_word = hyp1.anchor.before_word
    combined_hypothesis.anchor.after_word = hyp2.anchor.after_word
    
    return combined_hypothesis


def _check_after_word_match(
    hyp1: 'TokenHypotheses',
    after_word_idx: int,
    hypothesis_list: List['TokenHypotheses'],
    is_literal_hyphen: bool,
    base1: str,
    decoded_w1: str,
    clean_vocab: set[str],
    llm_word_lookup: Dict[str, List['LLMToken']]
) -> Optional[Tuple[str, float, int, 'LLMToken', float]]:
    """
    Check if hyp1's after_word creates a valid match when combined.
    
    Note: This function uses exact vocabulary matches only, so no thresholds needed.
    
    Args:
        hyp1: First hypothesis
        after_word_idx: Index of after_word in hypothesis_list
        hypothesis_list: List of all hypotheses
        is_literal_hyphen: Whether hyp1 ends with a literal hyphen
        base1: Base word without trailing hyphens (if literal hyphen)
        decoded_w1: Decoded content of hyp1
        clean_vocab: Set of normalized vocabulary words
        llm_word_lookup: Lookup dictionary for LLM tokens
    
    Returns:
        Tuple of (best_match, best_match_score, best_partner_idx, best_llm_token, best_context_score)
        or None if no match found
    """
    if after_word_idx is None or after_word_idx >= len(hypothesis_list):
        return None
    
    hyp2_after = hypothesis_list[after_word_idx]
    decoded_w2_after = text_utils.decode_html_entities(hyp2_after.anchor.content)
    normalized_w2_after = text_utils.normalize_for_matching(decoded_w2_after)
    
    # Try combining with after_word
    if is_literal_hyphen:
        merged_after = base1 + decoded_w2_after
        # Also try with hyphen inserted (for words like "anti-aircraft")
        merged_after_with_hyphen = base1 + "-" + decoded_w2_after
    else:
        merged_after = decoded_w1 + decoded_w2_after
        merged_after_with_hyphen = None
    
    merged_normalized_after = text_utils.normalize_for_matching(merged_after)
    
    # Check if combined form matches vocab (try both with and without hyphen)
    candidates_to_check = [merged_normalized_after]
    if merged_after_with_hyphen is not None:
        candidates_to_check.append(text_utils.normalize_for_matching(merged_after_with_hyphen))
    
    # First try exact matches
    for candidate_normalized in candidates_to_check:
        if candidate_normalized in clean_vocab:
            # Found exact match with after_word - use it immediately (hard match)
            matching_llm_tokens_after = llm_word_lookup.get(candidate_normalized, [])
            if matching_llm_tokens_after:
                # When multiple LLM tokens match, select the one with best context
                best_llm_token = matching_llm_tokens_after[0]
                best_context_score = 0.0
                for llm_token in matching_llm_tokens_after:
                    before_score, after_score = context_matching.calculate_context_scores(
                        hyp1.anchor.before_word, hyp2_after.anchor.after_word, llm_token, None
                    )
                    context_score = (before_score + after_score) / 2.0
                    if context_score > best_context_score:
                        best_context_score = context_score
                        best_llm_token = llm_token
                return (
                    candidate_normalized,
                    100.0,
                    after_word_idx,
                    best_llm_token,
                    best_context_score
                )
    
    # If no exact match, try fuzzy matching (for cases like "damsaged" → "damaged")
    best_fuzzy_match = None
    best_fuzzy_score = 0.0
    for candidate_normalized in candidates_to_check:
        fuzzy_matches = fuzzy_matching.fuzzy_match_rapid(candidate_normalized, clean_vocab, cutoff=80.0, limit=1)
        if fuzzy_matches:
            match_tuple = fuzzy_matches[0]
            match_word = match_tuple[0]
            match_score = match_tuple[1]
            if match_score > best_fuzzy_score:
                best_fuzzy_score = match_score
                best_fuzzy_match = match_word
    
    # Use fuzzy match if score is high enough
    if best_fuzzy_match and best_fuzzy_score >= 80.0:
        matching_llm_tokens_after = llm_word_lookup.get(best_fuzzy_match, [])
        if matching_llm_tokens_after:
            # When multiple LLM tokens match, select the one with best context
            best_llm_token = matching_llm_tokens_after[0]
            best_context_score = 0.0
            for llm_token in matching_llm_tokens_after:
                before_score, after_score = context_matching.calculate_context_scores(
                    hyp1.anchor.before_word, hyp2_after.anchor.after_word, llm_token, None
                )
                context_score = (before_score + after_score) / 2.0
                if context_score > best_context_score:
                    best_context_score = context_score
                    best_llm_token = llm_token
            return (
                best_fuzzy_match,
                best_fuzzy_score,
                after_word_idx,
                best_llm_token,
                best_context_score
            )
    
    return None


def _evaluate_word_combination(
    hyp1: 'TokenHypotheses',
    hyp2: 'TokenHypotheses',
    is_literal_hyphen: bool,
    base1: str,
    decoded_w1: str,
    decoded_w2: str,
    clean_vocab: set[str],
    llm_word_lookup: Dict[str, List['LLMToken']],
    hyp1_before_word: XMLOBJ.StringWord,
    hyp2_after_word: XMLOBJ.StringWord,
    individual_w1_match: Optional[Tuple[str, float]],
    individual_w2_match: Optional[Tuple[str, float]],
    fuzzy_cutoff_combined: float,
    context_validation_threshold: float,
    individual_score_threshold: float,
    combination_improvement_threshold: float
) -> Optional[Tuple[str, float, 'LLMToken', float]]:
    """
    Evaluate if two words should be combined and return match details if valid.
    
    Returns:
        Tuple of (merged_normalized, combined_score, selected_llm_token, context_score) or None
    """
    # Try combining: base1 + w2 (for literal hyphens) or w1 + w2 (for non-hyphen splits)
    if is_literal_hyphen:
        merged = base1 + decoded_w2
        merged_with_hyphen = base1 + "-" + decoded_w2
    else:
        merged = decoded_w1 + decoded_w2
        merged_with_hyphen = None
    
    merged_normalized = text_utils.normalize_for_matching(merged)
    if not merged_normalized:
        return None
    
    # Check for exact match in vocab (try both with and without hyphen)
    candidates_to_check = [merged_normalized]
    if merged_with_hyphen is not None:
        candidates_to_check.append(text_utils.normalize_for_matching(merged_with_hyphen))
    
    merged_normalized_to_use = None
    best_fuzzy_match = None
    best_fuzzy_score = 0.0
    
    # First try exact matches
    for candidate in candidates_to_check:
        if candidate in clean_vocab:
            merged_normalized_to_use = candidate
            break
    
    # If no exact match, try fuzzy matching
    if merged_normalized_to_use is None:
        for candidate in candidates_to_check:
            fuzzy_matches = fuzzy_matching.fuzzy_match_rapid(candidate, clean_vocab, cutoff=fuzzy_cutoff_combined, limit=1)
            if fuzzy_matches:
                match_tuple = fuzzy_matches[0]
                match_word = match_tuple[0]
                match_score = match_tuple[1]
                if match_score > best_fuzzy_score:
                    best_fuzzy_score = match_score
                    best_fuzzy_match = match_word
        
        if best_fuzzy_match and best_fuzzy_score >= fuzzy_cutoff_combined:
            merged_normalized_to_use = best_fuzzy_match
    
    if not merged_normalized_to_use:
        return None
    
    # Found match - check context
    matching_llm_tokens = llm_word_lookup.get(merged_normalized_to_use, [])
    
    candidate_context_match = None
    candidate_context_score = 0.0
    selected_before_score = 0.0
    selected_after_score = 0.0
    
    for llm_token in matching_llm_tokens:
        # CRITICAL: For non-hyphen merges, verify that the LLM token's w_before matches hyp1's expected match
        # This prevents incorrect merges like "T'm" + "delighted,"" → "delighted,"" when "delighted,"" should have "I'm" before it
        if not is_literal_hyphen:
            # Check if hyp1 has a chosen_LLM_token or candidates that suggest what should come before the merged word
            hyp1_expected_before = None
            if hyp1.chosen_LLM_token:
                hyp1_expected_before = hyp1.chosen_LLM_token
            elif hyp1.candidates:
                # Check if hyp1 has candidates that suggest a specific LLM token
                for cand in hyp1.candidates:
                    if cand.possible_llm_elements_by_fuzzy_match:
                        hyp1_expected_before = cand.possible_llm_elements_by_fuzzy_match[0]
                        break
                    elif cand.possible_llm_elements_by_context:
                        hyp1_expected_before = cand.possible_llm_elements_by_context[0][0]
                        break
            
            # If we have an expected before token, verify the LLM token's w_before matches it
            if hyp1_expected_before and llm_token.w_before:
                if llm_token.w_before != hyp1_expected_before:
                    # The merged word's before doesn't match what hyp1 should be - this is an incorrect merge
                    continue
        
        # Don't skip tokens at boundaries - they might still be valid matches
        # Calculate context scores for all tokens to find the best match
        before_score, after_score = context_matching.calculate_context_scores(
            hyp1_before_word, hyp2_after_word, llm_token, None
        )
        
        context_score = (before_score + after_score) / 2.0
        if context_score > candidate_context_score:
            candidate_context_score = context_score
            candidate_context_match = llm_token
            selected_before_score = before_score
            selected_after_score = after_score
    
    # Only use fallback if we truly have no matches with any context
    selected_llm = candidate_context_match if candidate_context_match else (matching_llm_tokens[0] if matching_llm_tokens else None)
    if not selected_llm:
        return None
    
    # Require minimum context scores
    # For non-literal hyphen merges, require stronger neighbor validation to prevent incorrect merges
    # Non-literal hyphens (like "af" + "the" → "after") need both neighbors to match well
    if not is_literal_hyphen:
        # For non-literal merges, require at least one neighbor to match very well (≥85%) 
        # and the average to be reasonable (≥75%)
        # This prevents incorrect merges when neighbors don't match
        neighbor_avg = (selected_before_score + selected_after_score) / 2.0
        max_neighbor = max(selected_before_score, selected_after_score)
        if max_neighbor < 85.0 or neighbor_avg < 75.0:
            # Neighbors don't match well enough - this is likely an incorrect merge
            return None
    
    # Standard context validation (applies to all merges)
    if not fuzzy_matching.validate_context_scores(selected_before_score, selected_after_score, candidate_context_score, threshold=context_validation_threshold):
        return None
    
    # Check if individual words have better matches - only combine if combined is significantly better
    individual_w1_score = individual_w1_match[1] if individual_w1_match else 0.0
    individual_w2_score = individual_w2_match[1] if individual_w2_match else 0.0
    
    combined_score = best_fuzzy_score if best_fuzzy_match else 100.0
    
    # Get word lengths to prevent combining short words with good matches
    w1_len = len(base1 if is_literal_hyphen else decoded_w1)
    w2_len = len(decoded_w2)
    
    should_combine = fuzzy_matching.should_combine_words(
        individual_w1_score,
        individual_w2_score,
        combined_score,
        individual_threshold=individual_score_threshold,
        improvement_threshold=combination_improvement_threshold,
        w1_length=w1_len,
        w2_length=w2_len
    )
    
    if should_combine:
        return (merged_normalized_to_use, combined_score, selected_llm, candidate_context_score)
    
    return None


def _should_prefer_match(
    current_match: Optional[Tuple[str, float, int, 'LLMToken', float]],
    new_match: Tuple[str, float, 'LLMToken', float],
    new_partner_idx: int,
    is_literal_hyphen: bool,
    is_after_word: bool,
    after_word_is_exact: bool,
    hypothesis_list: List['TokenHypotheses'],
    hyp1: 'TokenHypotheses'
) -> bool:
    """
    Determine if new_match should replace current_match based on priority rules.
    
    Priority:
    1. Literal hyphen words (ending with -) over non-literal hyphen words
    2. Exact matches over fuzzy matches
    3. after_word exact matches
    4. Better context scores
    """
    new_merged, new_score, new_llm, new_context = new_match
    
    if current_match is None:
        return True
    
    _, current_score, current_partner_idx, _, current_context = current_match
    
    # Priority 1: Literal hyphen words over non-literal hyphen words
    # Check if current partner is a literal hyphen word
    current_partner_is_literal_hyphen = False
    if current_partner_idx is not None:
        current_partner = hypothesis_list[current_partner_idx]
        current_partner_is_literal_hyphen = text_utils.is_hyphenish(current_partner.anchor)
    
    new_partner = hypothesis_list[new_partner_idx]
    new_partner_is_literal_hyphen = text_utils.is_hyphenish(new_partner.anchor)
    
    # If new is literal hyphen and current is not, prefer new
    if is_literal_hyphen and not current_partner_is_literal_hyphen:
        return True
    # If current is literal hyphen and new is not, don't replace
    if current_partner_is_literal_hyphen and not is_literal_hyphen:
        return False
    
    # Priority 2: Exact matches over fuzzy
    if new_score == 100.0 and current_score < 100.0:
        return True
    if new_score < 100.0 and current_score == 100.0:
        return False
    
    # Priority 3: after_word exact matches
    if is_after_word and after_word_is_exact:
        if current_score < 100.0:
            return True
        elif current_score == 100.0:
            return new_context > current_context
    
    # Priority 4: Better context scores (for same match type)
    if new_score == current_score:
        return new_context > current_context
    
    # For fuzzy matches, prefer higher score
    if new_score < 100.0 and current_score < 100.0:
        return new_score > current_score or (new_score == current_score and new_context > current_context)
    
    return False


def _search_spatially_close_partners(
    hyp1: 'TokenHypotheses',
    hyp1_idx: int,
    hypothesis_list: List['TokenHypotheses'],
    processed_indices: set,
    prioritized_indices: List[int],
    other_indices: List[int],
    is_literal_hyphen: bool,
    base1: str,
    decoded_w1: str,
    normalized_w1: str,
    individual_w1_match: Optional[Tuple[str, float]],
    clean_vocab: set[str],
    llm_word_lookup: Dict[str, List['LLMToken']],
    page: XMLOBJ.Page,
    column_boundaries: List[float],
    fuzzy_cutoff_individual: float,
    fuzzy_cutoff_combined: float,
    context_validation_threshold: float,
    individual_score_threshold: float,
    combination_improvement_threshold: float,
    after_word_result: Optional[Tuple[str, float, int, 'LLMToken', float]],
    after_word_is_exact: bool
) -> Optional[Tuple[str, float, int, 'LLMToken', float]]:
    """
    Search for partners in spatially close words (Pass 1).
    Returns best match tuple or None.
    """
    best_match = None
    best_match_score = 0.0
    best_partner_idx = None
    best_llm_token = None
    best_context_score = -1.0
    
    search_indices = prioritized_indices + other_indices
    
    for j in search_indices:
        if j in processed_indices:
            continue
        
        hyp2 = hypothesis_list[j]
        
        # Skip words that are too far away (unless it's the after_word)
        is_after_word = (hyp1.anchor.after_word is not None and hyp2.anchor == hyp1.anchor.after_word)
        if not is_after_word:
            are_adjacent_columns = proximity_scoring.are_words_in_adjacent_columns(hyp1.anchor, hyp2.anchor, column_boundaries)
            if not are_adjacent_columns:
                reading_dist = proximity_scoring.calculate_reading_order_distance(hyp1.anchor, hyp2.anchor, page, column_boundaries)
                column_aware_threshold = proximity_scoring.calculate_column_aware_threshold(page, column_boundaries)
                if reading_dist > column_aware_threshold:
                    continue
        
        decoded_w2 = text_utils.decode_html_entities(hyp2.anchor.content)
        normalized_w2 = text_utils.normalize_for_matching(decoded_w2)
        individual_w2_match = fuzzy_matching.check_individual_word_match(normalized_w2, clean_vocab, cutoff=fuzzy_cutoff_individual)
        
        # Evaluate combination
        result = _evaluate_word_combination(
            hyp1, hyp2, is_literal_hyphen, base1, decoded_w1, decoded_w2,
            clean_vocab, llm_word_lookup,
            hyp1.anchor.before_word, hyp2.anchor.after_word,
            individual_w1_match, individual_w2_match,
            fuzzy_cutoff_combined, context_validation_threshold,
            individual_score_threshold, combination_improvement_threshold
        )
        
        if result:
            merged_normalized, combined_score, selected_llm, candidate_context_score = result
            
            current_match = (best_match, best_match_score, best_partner_idx, best_llm_token, best_context_score) if best_match else None
            new_match = (merged_normalized, combined_score, selected_llm, candidate_context_score)
            
            if _should_prefer_match(current_match, new_match, j, is_literal_hyphen, is_after_word, after_word_is_exact, hypothesis_list, hyp1):
                best_match = merged_normalized
                best_match_score = combined_score
                best_partner_idx = j
                best_llm_token = selected_llm
                best_context_score = candidate_context_score
                
                if is_after_word:
                    break
    
    if best_match:
        return (best_match, best_match_score, best_partner_idx, best_llm_token, best_context_score)
    return None



def _collect_indices_to_process(
    hypothesis_list: List['TokenHypotheses'],
    fuzzy_cutoff_individual: float
) -> Tuple[List[int], List[int], set]:
    """
    Collect indices of hypotheses that need processing for hyphen linking.
    
    Args:
        hypothesis_list: List of all TokenHypotheses
        fuzzy_cutoff_individual: Cutoff for individual word matching
        
    Returns:
        Tuple of (literal_hyphen_indices, other_indices_to_process, skip_indices)
    """
    literal_hyphen_indices = []
    other_indices_to_process = []
    skip_indices = set()
    
    for i, hyp1 in enumerate(hypothesis_list):
        # Skip if already combined (has candidates with multiple alto_words)
        is_already_combined = False
        for cand in hyp1.candidates:
            if len(cand.alto_words) > 1:
                is_already_combined = True
                break
        if is_already_combined:
            skip_indices.add(i)
            continue
        
        decoded_w1 = text_utils.decode_html_entities(hyp1.anchor.content)
        is_literal_hyphen = text_utils.is_hyphenish(hyp1.anchor)
        
        if not hyp1.flagged_for_error and not is_literal_hyphen:
            skip_indices.add(i)
            continue
        
        has_good_match = False
        if len(hyp1.candidates) > 0:
            for cand in hyp1.candidates:
                if cand.fuzzy_score >= fuzzy_cutoff_individual or len(cand.possible_llm_elements_by_fuzzy_match) > 0:
                    has_good_match = True
                    break
        
        if has_good_match and not (is_literal_hyphen and hyp1.flagged_for_error):
            skip_indices.add(i)
            continue
        
        if is_literal_hyphen:
            literal_hyphen_indices.append(i)
        else:
            other_indices_to_process.append(i)
    
    return literal_hyphen_indices, other_indices_to_process, skip_indices


def _check_short_word_neighbor_match(
    hyp1: 'TokenHypotheses',
    hypothesis_list: List['TokenHypotheses'],
    llm_elements: List['LLMToken'],
    decoded_w1: str,
    is_literal_hyphen: bool
) -> bool:
    """
    Check if a short word can be matched based solely on neighbors.
    This prevents incorrect merges when short words should match individually.
    
    Args:
        hyp1: Hypothesis to check
        hypothesis_list: List of all hypotheses
        llm_elements: List of LLM tokens
        decoded_w1: Decoded content of hyp1
        is_literal_hyphen: Whether hyp1 is a literal hyphen word
        
    Returns:
        True if a neighbor-based match was found and added to hyp1.candidates
    """
    # Import at runtime to avoid circular imports
    from map_up_text import TokenCandidate
    
    normalized_w1 = text_utils.normalize_for_matching(decoded_w1)
    # Strip leading hyphens for length calculation (leading hyphens are OCR artifacts)
    w1_length = len(normalized_w1.lstrip("-–—"))
    is_short_word = w1_length <= 3
    
    # Only do this pre-check for short words that are NOT literal hyphens
    if not (is_short_word and not is_literal_hyphen and (hyp1.anchor.before_word is not None or hyp1.anchor.after_word is not None)):
        return False
    
    # Get neighbors
    left_neighbor_hyp = None
    right_neighbor_hyp = None
    
    if hyp1.anchor.before_word:
        for h in hypothesis_list:
            if h.anchor == hyp1.anchor.before_word:
                left_neighbor_hyp = h
                break
            for candidate in h.candidates:
                if hyp1.anchor.before_word in candidate.alto_words:
                    left_neighbor_hyp = h
                    break
            if left_neighbor_hyp:
                break
    
    if hyp1.anchor.after_word:
        for h in hypothesis_list:
            if h.anchor == hyp1.anchor.after_word:
                right_neighbor_hyp = h
                break
            for candidate in h.candidates:
                if hyp1.anchor.after_word in candidate.alto_words:
                    right_neighbor_hyp = h
                    break
            if right_neighbor_hyp:
                break
    
    # Get neighbor texts - use chosen_LLM_token if available, otherwise use best candidate,
    # or fall back to ALTO content (surface form) if not matched yet
    left_neighbor_text = None
    right_neighbor_text = None
    
    if left_neighbor_hyp:
        if left_neighbor_hyp.chosen_LLM_token:
            left_neighbor_text = text_utils.normalize_for_matching(left_neighbor_hyp.chosen_LLM_token.word)
        elif left_neighbor_hyp.candidates:
            best_candidate = max(left_neighbor_hyp.candidates, key=lambda c: c.fuzzy_score, default=None)
            if best_candidate and best_candidate.possible_llm_elements_by_fuzzy_match:
                left_neighbor_text = text_utils.normalize_for_matching(best_candidate.possible_llm_elements_by_fuzzy_match[0].word)
        else:
            left_alto_decoded = text_utils.decode_html_entities(left_neighbor_hyp.anchor.content)
            left_neighbor_text = text_utils.normalize_for_matching(left_alto_decoded)
    
    if right_neighbor_hyp:
        if right_neighbor_hyp.chosen_LLM_token:
            right_neighbor_text = text_utils.normalize_for_matching(right_neighbor_hyp.chosen_LLM_token.word)
        elif right_neighbor_hyp.candidates:
            best_candidate = max(right_neighbor_hyp.candidates, key=lambda c: c.fuzzy_score, default=None)
            if best_candidate and best_candidate.possible_llm_elements_by_fuzzy_match:
                right_neighbor_text = text_utils.normalize_for_matching(best_candidate.possible_llm_elements_by_fuzzy_match[0].word)
        else:
            right_alto_decoded = text_utils.decode_html_entities(right_neighbor_hyp.anchor.content)
            right_neighbor_text = text_utils.normalize_for_matching(right_alto_decoded)
    
    # Check if we have at least one neighbor with text
    if not (left_neighbor_text or right_neighbor_text):
        return False
    
    # Get unmatched LLM tokens
    matched_token_ids = {id(h.chosen_LLM_token) for h in hypothesis_list if h.chosen_LLM_token}
    unmatched_tokens = [token for token in llm_elements if id(token) not in matched_token_ids]
    
    if not unmatched_tokens:
        return False
    
    # Check if any unmatched LLM token matches based on neighbors
    for llm_token in unmatched_tokens:
        left_score = 0.0
        right_score = 0.0
        
        if llm_token.w_before and left_neighbor_text:
            left_score = fuzz.ratio(left_neighbor_text, text_utils.normalize_for_matching(llm_token.w_before.word))
        elif not llm_token.w_before and not left_neighbor_text:
            left_score = 100.0
        
        if llm_token.w_after and right_neighbor_text:
            right_score = fuzz.ratio(right_neighbor_text, text_utils.normalize_for_matching(llm_token.w_after.word))
        elif not llm_token.w_after and not right_neighbor_text:
            right_score = 100.0
        
        # For short words, be more lenient - accept if:
        # - Both neighbors ≥90% (very strong)
        # - One neighbor ≥90% and other ≥80% (strong with reasonable support)
        # - For very short words (≤2 chars), even one neighbor ≥90% is enough
        neighbor_match_ok = False
        if w1_length <= 2:
            # Very short words (1-2 chars): one strong neighbor (≥90%) is enough
            neighbor_match_ok = (max(left_score, right_score) >= 90.0)
        else:
            # 3-char words: need both ≥90% OR one ≥90% and other ≥80%
            neighbor_match_ok = (
                (left_score >= 90.0 and right_score >= 90.0) or
                (max(left_score, right_score) >= 90.0 and min(left_score, right_score) >= 80.0)
            )
        
        if neighbor_match_ok:
            # Found a strong neighbor-based match - create candidate
            candidate = TokenCandidate(
                clean_form=text_utils.normalize_for_matching(llm_token.word),
                kind="word",
                alto_words=[hyp1.anchor],
                fuzzy_score=50.0  # Low fuzzy score since we're matching by neighbors, not word similarity
            )
            candidate.possible_llm_elements_by_fuzzy_match = [llm_token]
            candidate.possible_llm_elements_by_context = [(llm_token, left_score, right_score)]
            hyp1.candidates.append(candidate)
            return True
    
    return False


def _find_best_partner_match(
    hyp1: 'TokenHypotheses',
    hyp1_idx: int,
    hypothesis_list: List['TokenHypotheses'],
    processed_indices: set,
    is_literal_hyphen: bool,
    base1: str,
    decoded_w1: str,
    normalized_w1: str,
    individual_w1_match: Optional[Tuple[str, float]],
    clean_vocab: set[str],
    llm_word_lookup: Dict[str, List['LLMToken']],
    page: XMLOBJ.Page,
    column_boundaries: List[float],
    prioritized_indices: List[int],
    other_indices: List[int],
    after_word_result: Optional[Tuple[str, float, int, 'LLMToken', float]],
    after_word_is_exact: bool,
    fuzzy_cutoff_individual: float,
    fuzzy_cutoff_combined: float,
    context_validation_threshold: float,
    individual_score_threshold: float,
    combination_improvement_threshold: float
) -> Optional[Tuple[str, float, int, 'LLMToken', float]]:
    """
    Find the best partner match for hyp1 using two-pass approach.
    
    Returns:
        Tuple of (best_match, best_match_score, best_partner_idx, best_llm_token, best_context_score) or None
    """
    best_match = None
    best_match_score = 0.0
    best_partner_idx = None
    best_llm_token = None
    best_context_score = -1.0
    
    # If after_word exists and is exact match, use it immediately
    if after_word_result is not None and after_word_is_exact:
        return after_word_result
    
    # Two-pass approach to handle paragraph reordering:
    # Pass 1: Check spatially close words (normal case)
    # Pass 2: Check all remaining words for exact vocabulary matches (handles reordering)
    
    # Pass 1: Search spatially close words using helper function
    pass1_result = _search_spatially_close_partners(
        hyp1, hyp1_idx, hypothesis_list, processed_indices,
        prioritized_indices, other_indices,
        is_literal_hyphen, base1, decoded_w1, normalized_w1,
        individual_w1_match, clean_vocab, llm_word_lookup,
        page, column_boundaries,
        fuzzy_cutoff_individual, fuzzy_cutoff_combined,
        context_validation_threshold, individual_score_threshold,
        combination_improvement_threshold,
        after_word_result, after_word_is_exact
    )
    
    if pass1_result:
        best_match, best_match_score, best_partner_idx, best_llm_token, best_context_score = pass1_result
    
    # Pass 2: Check all remaining words for exact vocabulary matches
    # This handles cases where paragraph reordering makes words far apart spatially
    # but they should still be combined (e.g., "sor-" + "ties" = "sorties")
    # ALWAYS check pass 2 for literal hyphens to find exact matches, even if Pass 1 found a fuzzy match
    # For non-literal hyphens, only check if we don't have an exact match yet
    has_exact_match = (pass1_result and best_match_score == 100.0) or (after_word_result is not None and after_word_is_exact)
    should_run_pass2 = is_literal_hyphen or not has_exact_match
    
    if should_run_pass2:
        # For Pass 2, we want to check ALL words that weren't successfully matched in Pass 1
        all_other_indices = [j for j in range(hyp1_idx + 1, len(hypothesis_list)) if j not in prioritized_indices]
        
        pass2_best_match = None
        pass2_best_score = 0.0
        pass2_best_partner = None
        pass2_best_llm = None
        pass2_best_context = -1.0
        
        # Track which indices were actually evaluated in Pass 1
        evaluated_in_pass1 = set()
        if pass1_result:
            evaluated_in_pass1 = set(other_indices)
        
        # Check all words in all_other_indices that weren't evaluated in Pass 1
        for j in all_other_indices:
            if j in processed_indices or j in evaluated_in_pass1:
                continue
            
            hyp2 = hypothesis_list[j]
            decoded_w2 = text_utils.decode_html_entities(hyp2.anchor.content)
            normalized_w2 = text_utils.normalize_for_matching(decoded_w2)
            individual_w2_match = fuzzy_matching.check_individual_word_match(normalized_w2, clean_vocab, cutoff=fuzzy_cutoff_individual)
            
            # Use the same evaluation logic as Pass 1
            result = _evaluate_word_combination(
                hyp1, hyp2, is_literal_hyphen, base1, decoded_w1, decoded_w2,
                clean_vocab, llm_word_lookup,
                hyp1.anchor.before_word, hyp2.anchor.after_word,
                individual_w1_match, individual_w2_match,
                fuzzy_cutoff_combined, context_validation_threshold,
                individual_score_threshold, combination_improvement_threshold
            )
            
            if result:
                merged_normalized, combined_score, selected_llm, candidate_context_score = result
                # Prefer better matches (higher score or better context for same score)
                if (combined_score > pass2_best_score or 
                    (combined_score == pass2_best_score and candidate_context_score > pass2_best_context)):
                    pass2_best_match = merged_normalized
                    pass2_best_score = combined_score
                    pass2_best_partner = j
                    pass2_best_llm = selected_llm
                    pass2_best_context = candidate_context_score
        
        # If Pass 2 found a match, compare it with Pass 1 results
        if pass2_best_match and pass2_best_partner is not None:
            pass2_result = (pass2_best_match, pass2_best_score, pass2_best_partner, pass2_best_llm, pass2_best_context)
            # Prefer exact match from pass 2 over fuzzy match from Pass 1 or after_word
            if pass2_best_score == 100.0:
                if not pass1_result or best_match_score < 100.0:
                    # Pass 2 found exact match, current is fuzzy or no match - always use exact
                    return pass2_result
                elif best_match_score == 100.0:
                    # Both exact - prefer better context
                    if pass2_best_context > best_context_score:
                        return pass2_result
            elif pass2_best_score > best_match_score:
                # Pass 2 found a better fuzzy match than Pass 1
                return pass2_result
            elif pass2_best_score == best_match_score and pass2_best_context > best_context_score:
                # Same score but better context
                return pass2_result
    
    if best_match:
        return (best_match, best_match_score, best_partner_idx, best_llm_token, best_context_score)
    return None


def _build_output_list(
    hypothesis_list: List['TokenHypotheses'],
    combinations: Dict[int, Tuple['TokenHypotheses', int]],
    processed_indices: set,
    skip_indices: set
) -> List['TokenHypotheses']:
    """
    Build the output list in original order, including combined hypotheses.
    
    Args:
        hypothesis_list: Original list of hypotheses
        combinations: Dictionary mapping index -> (combined_hypothesis, partner_idx)
        processed_indices: Set of indices that were processed
        skip_indices: Set of indices to skip (already handled)
        
    Returns:
        New list of hypotheses with combinations applied
    """
    # Import at runtime to avoid circular imports
    from map_up_text import TokenHypotheses
    
    new_hypothesis_list: List[TokenHypotheses] = []
    for i, hyp1 in enumerate(hypothesis_list):
        if i in processed_indices:
            # Check if this is part of a combination
            if i in combinations:
                # This is the first word of a combination - add the combined hypothesis
                combined_hypothesis, partner_idx = combinations[i]
                new_hypothesis_list.append(combined_hypothesis)
            # If it's the partner (second word), skip it (already included in combination)
            elif any(partner_idx == i for _, partner_idx in combinations.values()):
                continue
            else:
                # Shouldn't happen, but add original if somehow processed but not combined
                new_hypothesis_list.append(hyp1)
        elif i in skip_indices:
            # Not flagged, not literal hyphen - add as is
            new_hypothesis_list.append(hyp1)
        else:
            # Shouldn't happen, but add original
            new_hypothesis_list.append(hyp1)
    
    return new_hypothesis_list


def split_hyphenated_triplets(
    hypothesis_list: List['TokenHypotheses'],
    llm_elements: List['LLMToken'],
    fuzzy_cutoff: float = 85.0
) -> List['TokenHypotheses']:
    """
    Split ALTO words with internal hyphens that match clean text triplet pattern.
    
    Handles cases where ALTO has "assignment-his" but clean text has "assignment" "-" "his".
    Creates three separate hypotheses for word1, hyphen, and word2.
    
    Args:
        hypothesis_list: List of TokenHypotheses objects
        llm_elements: List of LLM tokens from clean text
        fuzzy_cutoff: Cutoff for fuzzy matching (default: 85.0)
    
    Returns:
        List of TokenHypotheses with triplet splits applied
    """
    # Import at runtime to avoid circular imports
    from map_up_text import TokenHypotheses, TokenCandidate
    
    new_hypothesis_list: List[TokenHypotheses] = []
    clean_vocab = set(e.word_normalized for e in llm_elements)
    
    # Create lookup for hyphen tokens in clean text
    hyphen_llm_tokens = []
    for llm_token in llm_elements:
        hyphen_text = text_utils.decode_html_entities(llm_token.word)
        if hyphen_text.strip() in text_utils.HY_PHENS:
            hyphen_llm_tokens.append(llm_token)
    
    for hyp in hypothesis_list:
        # Skip if already processed or combined
        is_already_combined = False
        for cand in hyp.candidates:
            if len(cand.alto_words) > 1:
                is_already_combined = True
                break
        if is_already_combined:
            new_hypothesis_list.append(hyp)
            continue
        
        # Check if word has internal hyphen
        if not _has_internal_hyphen(hyp.anchor):
            new_hypothesis_list.append(hyp)
            continue
        
        # Try to detect triplet pattern
        triplet_result = _detect_hyphenated_triplet_pattern(hyp.anchor, llm_elements)
        
        if triplet_result is None:
            # No triplet pattern found, keep original
            new_hypothesis_list.append(hyp)
            continue
        
        # Found triplet pattern! Split into 3 parts
        word1_alto, hyphen_char, word2_alto, llm_word1, llm_hyphen, llm_word2 = triplet_result
        
        # Create split parts: [word1, hyphen, word2]
        split_parts = [word1_alto, hyphen_char, word2_alto]
        
        # Calculate widths - hyphen should be narrow
        total_chars = len(word1_alto) + len(word2_alto) + 1  # +1 for hyphen
        gap_size = max(2, int(hyp.anchor.width * 0.01))
        total_gap_space = gap_size * 2  # Two gaps between 3 parts
        available_width = max(1, hyp.anchor.width - total_gap_space)
        
        # Allocate widths: word1 and word2 proportional, hyphen gets minimal width
        word1_width = int((len(word1_alto) / total_chars) * available_width) if total_chars > 0 else available_width // 3
        word2_width = int((len(word2_alto) / total_chars) * available_width) if total_chars > 0 else available_width // 3
        hyphen_width = max(5, available_width - word1_width - word2_width)  # Hyphen gets at least 5px
        
        # Create three split hypotheses
        current_hpos = hyp.anchor.hpos
        
        # Create all three anchors first, then create TokenHypotheses objects
        # Part 1: First word anchor
        word1_anchor = XMLOBJ.StringWord(
            id=hyp.anchor.id,
            width=word1_width,
            height=hyp.anchor.height,
            hpos=current_hpos,
            vpos=hyp.anchor.vpos,
            content=word1_alto,
            wc=hyp.anchor.wc,
            before_word=hyp.anchor.before_word,
            after_word=None,  # Will be set to hyphen anchor
            page_id=getattr(hyp.anchor, "page_id", None),
        )
        current_hpos += word1_width + gap_size
        
        # Part 2: Hyphen anchor
        hyphen_anchor = XMLOBJ.StringWord(
            id=hyp.anchor.id,
            width=hyphen_width,
            height=hyp.anchor.height,
            hpos=current_hpos,
            vpos=hyp.anchor.vpos,
            content=hyphen_char,
            wc=hyp.anchor.wc,
            before_word=word1_anchor,
            after_word=None,  # Will be set to word2 anchor
            page_id=getattr(hyp.anchor, "page_id", None),
        )
        word1_anchor.after_word = hyphen_anchor
        current_hpos += hyphen_width + gap_size
        
        # Part 3: Second word anchor
        word2_anchor = XMLOBJ.StringWord(
            id=hyp.anchor.id,
            width=word2_width,
            height=hyp.anchor.height,
            hpos=current_hpos,
            vpos=hyp.anchor.vpos,
            content=word2_alto,
            wc=hyp.anchor.wc,
            before_word=hyphen_anchor,
            after_word=hyp.anchor.after_word,
            page_id=getattr(hyp.anchor, "page_id", None),
        )
        hyphen_anchor.after_word = word2_anchor
        
        # Now create TokenHypotheses objects with all anchors already created
        word1_normalized = text_utils.normalize_for_matching(word1_alto)
        word1_hyp = TokenHypotheses(
            anchor=word1_anchor,
            anchor_left=hyp.anchor.before_word,  # First word gets original's left neighbor
            anchor_right=hyphen_anchor  # First word's right is the hyphen
        )
        
        # Create candidate for word1
        word1_candidate = None
        if word1_normalized in clean_vocab:
            word1_candidate = TokenCandidate(clean_form=word1_normalized, kind="word", alto_words=[word1_anchor], fuzzy_score=100.0)
        else:
            token_candidates = fuzzy_matching.fuzzy_match_rapid(word1_normalized, clean_vocab, cutoff=fuzzy_cutoff, limit=None)
            if token_candidates:
                word1_candidate = TokenCandidate(clean_form=token_candidates[0][0], kind="word", alto_words=[word1_anchor], fuzzy_score=token_candidates[0][1])
        
        if word1_candidate:
            # Add the matched LLM token to the candidate's fuzzy match list
            if llm_word1:
                word1_candidate.possible_llm_elements_by_fuzzy_match.append(llm_word1)
            word1_hyp.candidates.append(word1_candidate)
            word1_hyp.chosen_index = 0
        
        # Assign the matched LLM token
        if llm_word1:
            word1_hyp.chosen_LLM_token = llm_word1
        
        hyphen_hyp = TokenHypotheses(
            anchor=hyphen_anchor,
            anchor_left=word1_anchor,  # Hyphen's left is word1
            anchor_right=word2_anchor  # Hyphen's right is word2
        )
        # Hyphen matches directly to hyphen token
        hyphen_normalized = text_utils.normalize_for_matching(hyphen_char)
        hyphen_candidate = TokenCandidate(clean_form=hyphen_normalized, kind="word", alto_words=[hyphen_anchor], fuzzy_score=100.0)
        # Add the matched LLM token to the candidate's fuzzy match list
        if llm_hyphen:
            hyphen_candidate.possible_llm_elements_by_fuzzy_match.append(llm_hyphen)
        hyphen_hyp.candidates.append(hyphen_candidate)
        if llm_hyphen:
            hyphen_hyp.chosen_LLM_token = llm_hyphen
            hyphen_hyp.chosen_index = 0
        
        word2_normalized = text_utils.normalize_for_matching(word2_alto)
        word2_hyp = TokenHypotheses(
            anchor=word2_anchor,
            anchor_left=hyphen_anchor,  # Second word's left is the hyphen
            anchor_right=hyp.anchor.after_word  # Second word gets original's right neighbor
        )
        
        # Create candidate for word2
        word2_candidate = None
        if word2_normalized in clean_vocab:
            word2_candidate = TokenCandidate(clean_form=word2_normalized, kind="word", alto_words=[word2_anchor], fuzzy_score=100.0)
        else:
            token_candidates = fuzzy_matching.fuzzy_match_rapid(word2_normalized, clean_vocab, cutoff=fuzzy_cutoff, limit=None)
            if token_candidates:
                word2_candidate = TokenCandidate(clean_form=token_candidates[0][0], kind="word", alto_words=[word2_anchor], fuzzy_score=token_candidates[0][1])
        
        if word2_candidate:
            # Add the matched LLM token to the candidate's fuzzy match list
            if llm_word2:
                word2_candidate.possible_llm_elements_by_fuzzy_match.append(llm_word2)
            word2_hyp.candidates.append(word2_candidate)
            word2_hyp.chosen_index = 0
        
        # Assign the matched LLM token
        if llm_word2:
            word2_hyp.chosen_LLM_token = llm_word2
        
        # Add all three to the list
        new_hypothesis_list.append(word1_hyp)
        new_hypothesis_list.append(hyphen_hyp)
        new_hypothesis_list.append(word2_hyp)
    
    return new_hypothesis_list




def link_hyphen_pairs(
    hypothesis_list: List['TokenHypotheses'], 
    llm_elements: List['LLMToken'], 
    page: XMLOBJ.Page = None,
    fuzzy_cutoff_individual: float = 85.0,
    fuzzy_cutoff_combined: float = 80.0,
    context_validation_threshold: float = 70.0,
    individual_score_threshold: float = 85.0,
    combination_improvement_threshold: float = 5.0
) -> List['TokenHypotheses']:
    """
    Links corresponding halves of hyphenated words (or words that should be combined).
    Works with flagged TokenHypotheses objects and uses LLM tokens for matching.
    Handles both literal hyphens and cases where OCR split words incorrectly (e.g., "dams" + "aged" = "damaged").
    
    Args:
        hypothesis_list: List of TokenHypotheses objects (some may be flagged)
        llm_elements: List of LLMToken objects from clean text
        page: Optional page object for column boundary detection
        fuzzy_cutoff_individual: Cutoff for individual word fuzzy matching (default: 85.0)
        fuzzy_cutoff_combined: Cutoff for combined word fuzzy matching (default: 80.0)
        context_validation_threshold: Minimum context score threshold (default: 70.0)
        individual_score_threshold: Threshold for individual word scores (default: 85.0)
        combination_improvement_threshold: Minimum improvement for combination (default: 5.0)
        
    Returns:
        List[TokenHypotheses] with hyphen pairs linked and combined
    """
    # Import at runtime to avoid circular imports
    from map_up_text import TokenHypotheses, TokenCandidate
    
    # Create vocab from LLM elements for matching
    clean_vocab = set(e.word_normalized for e in llm_elements)
    
    # Create lookup: normalized word -> list of LLMTokens
    llm_word_lookup = fuzzy_matching.create_llm_word_lookup(llm_elements)
    
    # First, determine all combinations (processing literal hyphen words first for priority)
    # But maintain original order in output
    combinations = {}  # Map: (i, j) -> (combined_hypothesis, best_match, best_match_score, best_llm_token)
    processed_indices = set()
    
    # Collect indices to process, prioritizing literal hyphen words
    literal_hyphen_indices, other_indices_to_process, skip_indices = _collect_indices_to_process(
        hypothesis_list, fuzzy_cutoff_individual
    )
    
    # Process literal hyphen words first to determine combinations (ensures they claim partners)
    all_indices_to_process = literal_hyphen_indices + other_indices_to_process
    
    for i in all_indices_to_process:
        hyp1 = hypothesis_list[i]
        if i in processed_indices:
            continue
        
        # Skip if already combined (has candidates with multiple alto_words)
        is_already_combined = False
        for cand in hyp1.candidates:
            if len(cand.alto_words) > 1:
                is_already_combined = True
                break
        if is_already_combined:
            continue
        
        # Process flagged words and words ending with hyphens (potential first half of hyphenated word)
        decoded_w1 = text_utils.decode_html_entities(hyp1.anchor.content)
        is_literal_hyphen = text_utils.is_hyphenish(hyp1.anchor)
        
        if not hyp1.flagged_for_error and not is_literal_hyphen:
            # Not flagged and not a hyphen-ending word, skip (will be added in output building)
            continue
        
        # CRITICAL PRE-CHECK: Before trying to merge, check if SHORT words can be matched based solely on neighbors
        # This prevents incorrect merges when short words should match individually based on context
        found_neighbor_match = _check_short_word_neighbor_match(
            hyp1, hypothesis_list, llm_elements, decoded_w1, is_literal_hyphen
        )
        
        # If we found a neighbor-based match, skip merging for this word
        if found_neighbor_match:
            # Found neighbor-based match - don't try merging
            # Mark as processed so it gets added to the list at the end
            skip_indices.add(i)
            continue
        
        # Check if individual word has a good fuzzy match before trying to combine
        normalized_w1 = text_utils.normalize_for_matching(decoded_w1)
        individual_w1_match = fuzzy_matching.check_individual_word_match(normalized_w1, clean_vocab, cutoff=fuzzy_cutoff_individual)
        base1 = decoded_w1.rstrip("-–—") if is_literal_hyphen else decoded_w1
        
        # Find prioritized indices (after_word) and other potential partners
        prioritized_indices = []
        after_word_idx = None
        if hyp1.anchor.after_word is not None:
            for j in range(i + 1, len(hypothesis_list)):
                if hypothesis_list[j].anchor == hyp1.anchor.after_word:
                    prioritized_indices.append(j)
                    after_word_idx = j
                    break
        
        other_indices = [j for j in range(i + 1, len(hypothesis_list)) if j not in prioritized_indices]
        column_boundaries = proximity_scoring.detect_column_boundaries(page)
        other_indices.sort(key=lambda idx: proximity_scoring.calculate_reading_order_distance(
            hyp1.anchor, hypothesis_list[idx].anchor, page, column_boundaries
        ))
        
        # Check after_word first
        after_word_result = None
        after_word_is_exact = False
        if after_word_idx is not None and after_word_idx not in processed_indices:
            after_word_result = _check_after_word_match(
                hyp1, after_word_idx, hypothesis_list, is_literal_hyphen,
                base1, decoded_w1, clean_vocab, llm_word_lookup
            )
            if after_word_result is not None:
                after_word_is_exact = (after_word_result[1] == 100.0)
        
        # Find best partner match using two-pass approach
        best_match_result = _find_best_partner_match(
            hyp1, i, hypothesis_list, processed_indices,
            is_literal_hyphen, base1, decoded_w1, normalized_w1,
            individual_w1_match, clean_vocab, llm_word_lookup,
            page, column_boundaries,
            prioritized_indices, other_indices,
            after_word_result, after_word_is_exact,
            fuzzy_cutoff_individual, fuzzy_cutoff_combined,
            context_validation_threshold, individual_score_threshold,
            combination_improvement_threshold
        )
        
        if best_match_result:
            best_match, best_match_score, best_partner_idx, best_llm_token, best_context_score = best_match_result
        else:
            best_match = None
            best_partner_idx = None
        
        # If match found, store the combination (don't add to list yet - preserve order)
        if best_match and best_partner_idx is not None:
            # Check if partner is already part of another combination
            if best_partner_idx in processed_indices:
                # Partner already combined - skip this combination
                continue
            
            hyp2 = hypothesis_list[best_partner_idx]
            # Check if hyp2 is already combined (has multiple alto_words in candidates)
            is_hyp2_combined = False
            for cand in hyp2.candidates:
                if len(cand.alto_words) > 1:
                    is_hyp2_combined = True
                    break
            if is_hyp2_combined:
                # Partner already combined - skip this combination
                continue
            
            combined_hypothesis = _create_combined_hypothesis(
                hyp1, hyp2, best_match, best_match_score, best_llm_token
            )
            # Store combination at the position of the first word (i)
            combinations[i] = (combined_hypothesis, best_partner_idx)
            processed_indices.add(i)
            processed_indices.add(best_partner_idx)
    
    # Build output list in original order
    return _build_output_list(hypothesis_list, combinations, processed_indices, skip_indices)

