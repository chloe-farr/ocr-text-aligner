"""
Weak fuzzy matching module for text boundary mapping.

This module handles words with very weak fuzzy scores (no LLM candidates) by using
physical bounding box size and strong neighbor context. It fills in the blank:
finds ALTO words where before/after neighbors strongly match an unmatched LLM token's
before/after neighbors, then verifies physical size fit.

Non-intrusive: only matches words with NO existing candidates.
"""

from typing import List, Optional, Dict, Tuple, TYPE_CHECKING
from rapidfuzz import fuzz

if TYPE_CHECKING:
    from map_up_text import LLMToken, TokenHypotheses, TokenCandidate
    import xml_obj as XMLOBJ
else:
    LLMToken = None
    TokenHypotheses = None
    TokenCandidate = None
    XMLOBJ = None

import text_utils
import map_up_text

# Configuration
NEIGHBOR_STRENGTH_THRESHOLD = 90.0  # Minimum fuzzy match score for neighbors
BOUNDING_BOX_TOLERANCE = 0.35  # ±35% tolerance for width matching
MIN_FIT_SCORE = 75.0  # Minimum fit score to create a match
MIN_WORD_FUZZY_SCORE = 50.0  # Minimum fuzzy match score for the word itself


def find_unmatched_llm_tokens(
    llm_elements: List[LLMToken],
    hypothesis_list: List[TokenHypotheses]
) -> List[LLMToken]:
    """
    Find LLM tokens that are not yet matched.
    
    Args:
        llm_elements: List of all LLM tokens
        hypothesis_list: List of all hypotheses
    
    Returns:
        List of unmatched LLM tokens
    """
    matched_token_ids = {
        id(hyp.chosen_LLM_token)
        for hyp in hypothesis_list
        if hyp.chosen_LLM_token is not None
    }
    return [token for token in llm_elements if id(token) not in matched_token_ids]


def has_llm_candidates(hypothesis: TokenHypotheses) -> bool:
    """
    Check if hypothesis has any candidates with LLM matches.
    
    Args:
        hypothesis: Hypothesis to check
    
    Returns:
        True if has LLM candidates, False otherwise
    """
    if not hypothesis.candidates:
        return False
    for candidate in hypothesis.candidates:
        if (candidate.possible_llm_elements_by_fuzzy_match or
            candidate.possible_llm_elements_by_context):
            return True
    return False


def find_matching_llm_tokens_for_flagged_alto(
    flagged_hyp: TokenHypotheses,
    unmatched_llm_tokens: List[LLMToken],
    hypothesis_list: List[TokenHypotheses],
    threshold: float = NEIGHBOR_STRENGTH_THRESHOLD
) -> List[Tuple[LLMToken, float, float, float]]:
    """
    Find unmatched LLM tokens where neighbors strongly match the flagged ALTO word's neighbors.
    
    Approach:
    1. Get the ALTO (hypothesis) neighbors of the flagged word
    2. Search unmatched LLM tokens for one where:
       - llm_token.w_before strongly fuzzy matches left neighbor
       - llm_token.w_after strongly fuzzy matches right neighbor
       - llm_token.word itself has at least 50% fuzzy match with flagged ALTO word
    3. Return candidates that fit in the middle
    
    Args:
        flagged_hyp: Flagged ALTO hypothesis to find matches for
        unmatched_llm_tokens: List of unmatched LLM tokens
        hypothesis_list: List of all hypotheses
        threshold: Minimum fuzzy match score for neighbors (default: 90.0)
    
    Returns:
        List of (llm_token, left_score, right_score, word_fuzzy_score) tuples
    """
    candidates = []
    
    # Get the flagged ALTO word's neighbors (hypothesis objects)
    left_neighbor_hyp = None
    right_neighbor_hyp = None
    
    if flagged_hyp.anchor.before_word:
        for h in hypothesis_list:
            if h.anchor == flagged_hyp.anchor.before_word:
                left_neighbor_hyp = h
                break
            # Check if before_word is in any candidate's alto_words (merged case)
            for candidate in h.candidates:
                if flagged_hyp.anchor.before_word in candidate.alto_words:
                    left_neighbor_hyp = h
                    break
            if left_neighbor_hyp:
                break
    
    if flagged_hyp.anchor.after_word:
        for h in hypothesis_list:
            if h.anchor == flagged_hyp.anchor.after_word:
                right_neighbor_hyp = h
                break
            # Check if after_word is in any candidate's alto_words (merged case)
            for candidate in h.candidates:
                if flagged_hyp.anchor.after_word in candidate.alto_words:
                    right_neighbor_hyp = h
                    break
            if right_neighbor_hyp:
                break
    
    # Need at least one neighbor to proceed
    if not left_neighbor_hyp and not right_neighbor_hyp:
        return candidates
    
    # Get neighbor content for matching - prefer chosen_LLM_token.word if available (handles merged words)
    # Otherwise fall back to ALTO content
    left_neighbor_text = None
    right_neighbor_text = None
    
    if left_neighbor_hyp:
        if left_neighbor_hyp.chosen_LLM_token:
            # Use the matched LLM token word (handles merged/hyphenated words like "resi- + dence" → "residence")
            left_neighbor_text = text_utils.normalize_for_matching(left_neighbor_hyp.chosen_LLM_token.word)
        else:
            # Fall back to ALTO content if not matched
            left_alto_decoded = text_utils.decode_html_entities(left_neighbor_hyp.anchor.content)
            left_neighbor_text = text_utils.normalize_for_matching(left_alto_decoded)
    
    if right_neighbor_hyp:
        if right_neighbor_hyp.chosen_LLM_token:
            # Use the matched LLM token word (handles merged/hyphenated words)
            right_neighbor_text = text_utils.normalize_for_matching(right_neighbor_hyp.chosen_LLM_token.word)
        else:
            # Fall back to ALTO content if not matched
            right_alto_decoded = text_utils.decode_html_entities(right_neighbor_hyp.anchor.content)
            right_neighbor_text = text_utils.normalize_for_matching(right_alto_decoded)
    
    # Get normalized ALTO content for word fuzzy matching
    # Strip leading/trailing hyphens from ALTO word (handles hyphenated word fragments)
    flagged_alto_decoded = text_utils.decode_html_entities(flagged_hyp.anchor.content)
    flagged_alto_normalized = text_utils.normalize_for_matching(flagged_alto_decoded)
    # Remove leading hyphens (second half of hyphenated word) and trailing hyphens (first half)
    flagged_alto_normalized = flagged_alto_normalized.lstrip('-–—').rstrip('-–—')
    
    # Debug: track best matches to understand why candidates are rejected
    best_matches = []
    
    # Search unmatched LLM tokens: find ones where w_before matches left neighbor and w_after matches right neighbor
    for llm_token in unmatched_llm_tokens:
        left_score = 0.0
        right_score = 0.0
        
        # Check if llm_token.w_before matches left neighbor (prefer chosen_LLM_token, fall back to ALTO)
        if llm_token.w_before:
            llm_before_text = text_utils.normalize_for_matching(llm_token.w_before.word)
            if left_neighbor_text:
                # Both have text - compare them
                left_score = fuzz.ratio(left_neighbor_text, llm_before_text)
            else:
                # Left neighbor normalized to empty (e.g., '@' → ''), check if LLM also normalizes to empty
                if not llm_before_text:
                    # Both normalize to empty - perfect match (e.g., '@' matches '@')
                    left_score = 100.0
                else:
                    # Left is empty but LLM has text - no match
                    left_score = 0.0
        else:
            # LLM token has no w_before
            if not left_neighbor_text:
                # Both are at start/empty - perfect match
                left_score = 100.0
            else:
                # LLM has no w_before but ALTO has left neighbor - no match
                left_score = 0.0
        
        # Check if llm_token.w_after matches right neighbor (prefer chosen_LLM_token, fall back to ALTO)
        if llm_token.w_after:
            llm_after_text = text_utils.normalize_for_matching(llm_token.w_after.word)
            if right_neighbor_text:
                # Both have text - compare them
                right_score = fuzz.ratio(right_neighbor_text, llm_after_text)
            else:
                # Right neighbor normalized to empty (e.g., '@' → ''), check if LLM also normalizes to empty
                if not llm_after_text:
                    # Both normalize to empty - perfect match (e.g., '@' matches '@')
                    right_score = 100.0
                else:
                    # Right is empty but LLM has text - no match
                    right_score = 0.0
        else:
            # LLM token has no w_after
            if not right_neighbor_text:
                # Both are at end/empty - perfect match
                right_score = 100.0
            else:
                # LLM has no w_after but ALTO has right neighbor - no match
                right_score = 0.0
        
        # Also check fuzzy match of the word itself
        llm_word_normalized = text_utils.normalize_for_matching(llm_token.word)
        word_fuzzy_score = fuzz.ratio(flagged_alto_normalized, llm_word_normalized)
        
        # Track best matches for debugging (keep top 5)
        if left_score >= threshold or right_score >= threshold or word_fuzzy_score >= MIN_WORD_FUZZY_SCORE:
            best_matches.append((llm_token.word, left_score, right_score, word_fuzzy_score, 
                                llm_token.w_before.word if llm_token.w_before else None,
                                llm_token.w_after.word if llm_token.w_after else None))
            best_matches.sort(key=lambda x: max(x[1], x[2], x[3]), reverse=True)
            if len(best_matches) > 5:
                best_matches.pop()
        
        # Need both neighbors to match strongly (or be at boundaries) AND word itself to be at least 50% match
        if left_score >= threshold and right_score >= threshold and word_fuzzy_score >= MIN_WORD_FUZZY_SCORE:
            candidates.append((llm_token, left_score, right_score, word_fuzzy_score))
    
    # Debug output if no candidates found
    if not candidates and best_matches:
        print(f"      Debug: Top matches that didn't meet all requirements:")
        for word, l_score, r_score, w_fuzzy, w_before, w_after in best_matches[:3]:
            print(f"        '{word}' (L:{l_score:.1f}, R:{r_score:.1f}, word_fuzzy:{w_fuzzy:.1f}, "
                  f"w_before='{w_before}', w_after='{w_after}')")
    
    return candidates


def get_paragraph_words(
    hypothesis: TokenHypotheses,
    hypothesis_list: List[TokenHypotheses],
    page
) -> List[TokenHypotheses]:
    """
    Find all words in same paragraph/area as hypothesis.
    
    Args:
        hypothesis: Hypothesis to find neighbors for
        hypothesis_list: List of all hypotheses
        page: Page object for spatial information
    
    Returns:
        List of nearby hypotheses with matches
    """
    if page is None:
        return []
    
    # Use vpos similarity to find words on same/similar lines
    target_vpos = hypothesis.anchor.vpos
    vpos_tolerance = 50  # pixels
    
    paragraph_words = []
    for hyp in hypothesis_list:
        if hyp.chosen_LLM_token is None:
            continue
        vpos_diff = abs(hyp.anchor.vpos - target_vpos)
        if vpos_diff <= vpos_tolerance:
            paragraph_words.append(hyp)
    
    return paragraph_words


def calculate_average_character_size(
    paragraph_words: List[TokenHypotheses]
) -> float:
    """
    Calculate average character size from matched words in paragraph.
    
    Args:
        paragraph_words: List of matched hypotheses in same paragraph
    
    Returns:
        Average pixels per character
    """
    if not paragraph_words:
        return 0.0
    
    total_width = 0.0
    total_chars = 0
    
    for hyp in paragraph_words:
        if hyp.chosen_LLM_token:
            word_text = hyp.chosen_LLM_token.word
            decoded_content = text_utils.decode_html_entities(hyp.anchor.content)
            # Use actual ALTO width and LLM word length
            total_width += hyp.anchor.width
            total_chars += len(word_text)
    
    if total_chars == 0:
        return 0.0
    
    return total_width / total_chars


def estimate_word_width(
    word_text: str,
    avg_char_size: float
) -> float:
    """
    Estimate physical width for given word text.
    
    Args:
        word_text: Word text to estimate
        avg_char_size: Average pixels per character
    
    Returns:
        Estimated width in pixels
    """
    return len(word_text) * avg_char_size


def calculate_bounding_box_fit_score(
    alto_word,
    estimated_width: float,
    tolerance: float = BOUNDING_BOX_TOLERANCE
) -> float:
    """
    Compare ALTO word width to estimated LLM word width.
    
    Args:
        alto_word: ALTO word object
        estimated_width: Estimated width for LLM word
        tolerance: Allowed deviation (default: 0.2 = ±20%)
    
    Returns:
        Fit score (0.0-100.0)
    """
    actual_width = alto_word.width
    if actual_width == 0:
        return 0.0
    
    ratio = estimated_width / actual_width
    if ratio < (1.0 - tolerance) or ratio > (1.0 + tolerance):
        # Outside tolerance - calculate penalty
        deviation = abs(ratio - 1.0)
        return max(0.0, 100.0 - (deviation * 200.0))
    
    # Within tolerance - perfect score
    return 100.0


def _score_candidate_by_fit(
    hyp: TokenHypotheses,
    llm_token: LLMToken,
    left_score: float,
    right_score: float,
    word_fuzzy_score: float,
    hypothesis_list: List[TokenHypotheses],
    page
) -> Optional[Tuple[float, float]]:
    """
    Score a candidate hypothesis by bounding box fit.
    
    Args:
        hyp: Hypothesis to score
        llm_token: LLM token candidate
        left_score: Neighbor match score (left)
        right_score: Neighbor match score (right)
        word_fuzzy_score: Fuzzy match score of the word itself
        hypothesis_list: List of all hypotheses
        page: Page object for spatial information
    
    Returns:
        Tuple of (total_score, fit_score) or None
    """
    alto_content = text_utils.decode_html_entities(hyp.anchor.content)
    llm_word = llm_token.word
    
    paragraph_words = get_paragraph_words(hyp, hypothesis_list, page)
    print(f"        Paragraph words found: {len(paragraph_words)}")
    if not paragraph_words:
        print(f"        No paragraph words found for '{alto_content}'")
        return None
    
    avg_char_size = calculate_average_character_size(paragraph_words)
    print(f"        Average char size: {avg_char_size:.2f} pixels/char")
    if avg_char_size == 0.0:
        print(f"        Average char size is 0 - cannot estimate width")
        return None
    
    estimated_width = estimate_word_width(llm_token.word, avg_char_size)
    actual_width = hyp.anchor.width
    fit_score = calculate_bounding_box_fit_score(
        hyp.anchor, estimated_width, BOUNDING_BOX_TOLERANCE
    )
    
    print(f"        Width: actual={actual_width:.1f}, estimated={estimated_width:.1f} (for '{llm_word}')")
    print(f"        Fit score: {fit_score:.1f} (tolerance={BOUNDING_BOX_TOLERANCE*100}%)")
    print(f"        Word fuzzy score: {word_fuzzy_score:.1f}")
    
    neighbor_avg = (left_score + right_score) / 2.0
    # Weighted combination: neighbor context (40%), word fuzzy match (30%), fit score (30%)
    total_score = (neighbor_avg * 0.4) + (word_fuzzy_score * 0.3) + (fit_score * 0.3)
    
    print(f"        Total score: {total_score:.1f} = (neighbor_avg {neighbor_avg:.1f} * 0.4) + (word_fuzzy {word_fuzzy_score:.1f} * 0.3) + (fit {fit_score:.1f} * 0.3)")
    
    return (total_score, fit_score)


def _create_match_for_hypothesis(
    hyp: TokenHypotheses,
    llm_token: LLMToken,
    total_score: float,
    left_neighbor_hyp: Optional[TokenHypotheses] = None,
    right_neighbor_hyp: Optional[TokenHypotheses] = None
) -> None:
    """
    Create a match candidate for a hypothesis and link it to neighbors.
    Marks all 3 LLM tokens as matched and links all 3 hypotheses.
    
    Args:
        hyp: Hypothesis to match (middle word)
        llm_token: LLM token to match to (middle word)
        total_score: Score for the match
        left_neighbor_hyp: Left neighbor hypothesis (if available)
        right_neighbor_hyp: Right neighbor hypothesis (if available)
    """
    # Create candidate for middle word
    candidate = map_up_text.TokenCandidate(
        clean_form=text_utils.normalize_for_matching(llm_token.word),
        kind="word",
        alto_words=[hyp.anchor],
        fuzzy_score=total_score
    )
    candidate.possible_llm_elements_by_fuzzy_match = [llm_token]
    hyp.candidates.append(candidate)
    hyp.chosen_LLM_token = llm_token
    hyp.chosen_index = len(hyp.candidates) - 1
    hyp.flagged_for_error = False
    
    # Mark middle LLM token as matched
    llm_token.matched = True
    
    # Set StringWord matched and best_clean_content for middle word
    hyp.anchor.matched = True
    hyp.anchor.best_clean_content = llm_token.word
    
    # Handle left neighbor - always link, but only fully match if it has both neighbors
    if left_neighbor_hyp and llm_token.w_before:
        # Mark left LLM token as matched
        llm_token.w_before.matched = True
        
        # Always link hypotheses (even if left neighbor isn't fully matched)
        hyp.left_matched = left_neighbor_hyp
        left_neighbor_hyp.right_matched = hyp
        
        # Only fully match left neighbor if it doesn't have a match yet AND it has both neighbors
        # (i.e., it's at the start OR it already has a left_matched)
        if not left_neighbor_hyp.chosen_LLM_token:
            # Check if left neighbor is at start (no before_word) or has a left_matched
            is_at_start = left_neighbor_hyp.anchor.before_word is None
            has_left_matched = left_neighbor_hyp.left_matched is not None
            
            # Only fully match if it has both neighbors (at start OR has left_matched)
            if is_at_start or has_left_matched:
                left_candidate = map_up_text.TokenCandidate(
                    clean_form=text_utils.normalize_for_matching(llm_token.w_before.word),
                    kind="word",
                    alto_words=[left_neighbor_hyp.anchor],
                    fuzzy_score=100.0
                )
                left_candidate.possible_llm_elements_by_fuzzy_match = [llm_token.w_before]
                left_neighbor_hyp.candidates.append(left_candidate)
                left_neighbor_hyp.chosen_LLM_token = llm_token.w_before
                left_neighbor_hyp.chosen_index = len(left_neighbor_hyp.candidates) - 1
                left_neighbor_hyp.flagged_for_error = False
                left_neighbor_hyp.anchor.matched = True
                left_neighbor_hyp.anchor.best_clean_content = llm_token.w_before.word
            # Otherwise, don't fully match - just link (left neighbor remains pending)
    
    # Handle right neighbor - always link and fully match if it doesn't have a match yet
    if right_neighbor_hyp and llm_token.w_after:
        # Mark right LLM token as matched
        llm_token.w_after.matched = True
        
        # Always link hypotheses
        hyp.right_matched = right_neighbor_hyp
        right_neighbor_hyp.left_matched = hyp
        
        # If right neighbor doesn't have a match yet, fully match it
        # (Right neighbor should be fully matched since it now has both neighbors: left=hyp, right=its after_word)
        if not right_neighbor_hyp.chosen_LLM_token:
            right_candidate = map_up_text.TokenCandidate(
                clean_form=text_utils.normalize_for_matching(llm_token.w_after.word),
                kind="word",
                alto_words=[right_neighbor_hyp.anchor],
                fuzzy_score=100.0
            )
            right_candidate.possible_llm_elements_by_fuzzy_match = [llm_token.w_after]
            right_neighbor_hyp.candidates.append(right_candidate)
            right_neighbor_hyp.chosen_LLM_token = llm_token.w_after
            right_neighbor_hyp.chosen_index = len(right_neighbor_hyp.candidates) - 1
            right_neighbor_hyp.flagged_for_error = False
            right_neighbor_hyp.anchor.matched = True
            right_neighbor_hyp.anchor.best_clean_content = llm_token.w_after.word


def match_weak_fuzzy_words(
    hypothesis_list: List[TokenHypotheses],
    llm_elements: List[LLMToken],
    page
) -> List[TokenHypotheses]:
    """
    Main entry point: match flagged ALTO words using neighbor context and size.
    
    Non-intrusive: only processes words flagged_for_error.
    
    Args:
        hypothesis_list: List of all hypotheses
        llm_elements: List of all LLM tokens
        page: Page object for spatial information
    
    Returns:
        Updated hypothesis_list (only adds matches, never removes)
    """
    # Find all flagged ALTO words that are still unmatched (actual errors)
    # ERROR = flagged_for_error AND no chosen_LLM_token
    flagged_hyps = [hyp for hyp in hypothesis_list if hyp.flagged_for_error and hyp.chosen_LLM_token is None]
    print(f"\n[WEAK FUZZY MATCHING] Found {len(flagged_hyps)} flagged ALTO words (ERROR status)")
    
    # Find all unmatched LLM tokens
    unmatched_tokens = find_unmatched_llm_tokens(llm_elements, hypothesis_list)
    print(f"[WEAK FUZZY MATCHING] Found {len(unmatched_tokens)} unmatched LLM tokens")
    print(f"  (Note: This includes LLM tokens that don't correspond to any ALTO word)")
    print(f"  (Only ~14 should be relevant: 10 PENDING + 4 ERROR)")
    
    processed_count = 0
    for flagged_hyp in flagged_hyps:
        alto_content = text_utils.decode_html_entities(flagged_hyp.anchor.content)
        
        # Get the ALTO (hypothesis) neighbors
        left_neighbor_hyp = None
        right_neighbor_hyp = None
        
        if flagged_hyp.anchor.before_word:
            for h in hypothesis_list:
                if h.anchor == flagged_hyp.anchor.before_word:
                    left_neighbor_hyp = h
                    break
                for candidate in h.candidates:
                    if flagged_hyp.anchor.before_word in candidate.alto_words:
                        left_neighbor_hyp = h
                        break
                if left_neighbor_hyp:
                    break
        
        if flagged_hyp.anchor.after_word:
            for h in hypothesis_list:
                if h.anchor == flagged_hyp.anchor.after_word:
                    right_neighbor_hyp = h
                    break
                for candidate in h.candidates:
                    if flagged_hyp.anchor.after_word in candidate.alto_words:
                        right_neighbor_hyp = h
                        break
                if right_neighbor_hyp:
                    break
        
        print(f"\n[WEAK FUZZY] Checking flagged ALTO: '{alto_content}'")
        if left_neighbor_hyp:
            left_display = left_neighbor_hyp.chosen_LLM_token.word if left_neighbor_hyp.chosen_LLM_token else left_neighbor_hyp.anchor.content
            print(f"  Left neighbor: '{left_neighbor_hyp.anchor.content}' -> '{left_display}'")
        else:
            print(f"  Left neighbor: None")
        if right_neighbor_hyp:
            right_display = right_neighbor_hyp.chosen_LLM_token.word if right_neighbor_hyp.chosen_LLM_token else right_neighbor_hyp.anchor.content
            print(f"  Right neighbor: '{right_neighbor_hyp.anchor.content}' -> '{right_display}'")
        else:
            print(f"  Right neighbor: None")
        
        # Need at least one neighbor to proceed
        if not left_neighbor_hyp and not right_neighbor_hyp:
            print(f"  ✗ Skipping: No neighbors found")
            continue
        
        # Find unmatched LLM tokens with matching neighbors
        candidates = find_matching_llm_tokens_for_flagged_alto(
            flagged_hyp, unmatched_tokens, hypothesis_list, NEIGHBOR_STRENGTH_THRESHOLD
        )
        
        if not candidates:
            # Debug: show why no candidates were found
            flagged_alto_decoded = text_utils.decode_html_entities(flagged_hyp.anchor.content)
            flagged_alto_normalized = text_utils.normalize_for_matching(flagged_alto_decoded)
            print(f"  ✗ No LLM token candidates found with matching neighbors")
            print(f"    Requirements: L>={NEIGHBOR_STRENGTH_THRESHOLD}, R>={NEIGHBOR_STRENGTH_THRESHOLD}, word_fuzzy>={MIN_WORD_FUZZY_SCORE}")
            print(f"    Checking {len(unmatched_tokens)} unmatched LLM tokens")
            # Show a few examples of what we're looking for
            if left_neighbor_hyp:
                left_text = left_neighbor_hyp.chosen_LLM_token.word if left_neighbor_hyp.chosen_LLM_token else left_neighbor_hyp.anchor.content
                print(f"    Looking for LLM tokens where w_before matches: '{left_text}'")
            if right_neighbor_hyp:
                right_text = right_neighbor_hyp.chosen_LLM_token.word if right_neighbor_hyp.chosen_LLM_token else right_neighbor_hyp.anchor.content
                print(f"    Looking for LLM tokens where w_after matches: '{right_text}'")
            print(f"    And word itself matches: '{flagged_alto_normalized}'")
            continue
        
        processed_count += 1
        print(f"\n[WEAK FUZZY] Processing flagged ALTO #{processed_count}: '{alto_content}'")
        print(f"  Found {len(candidates)} LLM token candidates with matching neighbors")
        
        for llm_token, left_score, right_score, word_fuzzy_score in candidates:
            print(f"    - LLM: '{llm_token.word}' (L:{left_score:.1f}, R:{right_score:.1f}, word_fuzzy:{word_fuzzy_score:.1f})")
            print(f"      LLM neighbors: before='{llm_token.w_before.word if llm_token.w_before else None}', "
                  f"after='{llm_token.w_after.word if llm_token.w_after else None}'")
        
        # Calculate size and score candidates
        scored_candidates = []
        for llm_token, left_score, right_score, word_fuzzy_score in candidates:
            # Calculate bounding box fit score
            score_result = _score_candidate_by_fit(
                flagged_hyp, llm_token, left_score, right_score, word_fuzzy_score, hypothesis_list, page
            )
            if score_result:
                total_score, fit_score = score_result
                scored_candidates.append((llm_token, total_score, fit_score, left_score, right_score, word_fuzzy_score))
                print(f"    Scored: '{llm_token.word}' -> total={total_score:.1f}, fit={fit_score:.1f}")
            else:
                print(f"    Failed to score: '{llm_token.word}' (no paragraph words or avg_char_size=0)")
        
        if not scored_candidates:
            print(f"  No scored candidates - skipping")
            continue
        
        # Sort by total score and select best
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        best_llm_token, best_total, best_fit, best_left, best_right, best_word_fuzzy = scored_candidates[0]
        
        print(f"  Best candidate: '{best_llm_token.word}' (total={best_total:.1f}, fit={best_fit:.1f}, L:{best_left:.1f}, R:{best_right:.1f}, word_fuzzy:{best_word_fuzzy:.1f})")
        
        if best_fit >= MIN_FIT_SCORE:
            _create_match_for_hypothesis(flagged_hyp, best_llm_token, best_total, left_neighbor_hyp, right_neighbor_hyp)
            print(f"  ✓ MATCHED: '{alto_content}' -> '{best_llm_token.word}'")
        else:
            print(f"  ✗ REJECTED: fit score {best_fit:.1f} < minimum {MIN_FIT_SCORE}")
    
    print(f"\n[WEAK FUZZY MATCHING] Processed {processed_count} flagged ALTO words with matching neighbors")
    return hypothesis_list

