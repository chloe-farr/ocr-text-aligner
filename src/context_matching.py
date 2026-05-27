"""
Context matching functions for OCR text alignment.

Provides functions for matching OCR words to LLM tokens based on context
(neighboring words) rather than just fuzzy string matching.
"""

from rapidfuzz import fuzz
from typing import List, Optional, Dict, Tuple, TYPE_CHECKING
import text_utils
import proximity_scoring
import xml_obj as XMLOBJ

if TYPE_CHECKING:
    from map_up_text import TokenHypotheses, TokenCandidate, LLMToken
else:
    # Import at runtime to avoid circular imports
    TokenHypotheses = None
    TokenCandidate = None
    LLMToken = None


def calculate_context_scores(
    before_alto: Optional[XMLOBJ.StringWord],
    after_alto: Optional[XMLOBJ.StringWord],
    llm_token: 'LLMToken',
    hypothesis_lookup: Optional[Dict[int, 'TokenHypotheses']] = None,
    context_score_threshold: float = 90.0
) -> Tuple[float, float]:
    """
    Calculate before and after context scores for a match.
    
    Args:
        before_alto: ALTO word before the candidate (or None)
        after_alto: ALTO word after the candidate (or None)
        llm_token: LLM token to match against
        hypothesis_lookup: Optional lookup for resolved hypotheses
        context_score_threshold: Minimum score to consider a match (default: 90.0)
    
    Returns:
        Tuple of (before_score, after_score) where scores are 0.0-100.0
    """
    # Get the text to compare for before word
    before_fuzzy_match_score = 0.0
    if before_alto is None and llm_token.w_before is None:
        # Both are at the start - perfect match
        before_fuzzy_match_score = 100.0
    elif before_alto is not None and llm_token.w_before is not None:
        # Both have before words - compare them
        before_text_to_compare = None
        if hypothesis_lookup and id(before_alto) in hypothesis_lookup:
            before_hyp = hypothesis_lookup[id(before_alto)]
            if before_hyp.chosen_LLM_token:
                before_text_to_compare = before_hyp.chosen_LLM_token.word
            else:
                # Use the best candidate's clean_form if available
                if before_hyp.candidates:
                    before_text_to_compare = before_hyp.candidates[0].clean_form
        
        if before_text_to_compare is None:
            # Fall back to ALTO content
            before_alto_content = text_utils.decode_html_entities(before_alto.content)
            before_text_to_compare = before_alto_content
        
        # Normalize for comparison
        before_alto_normalized = text_utils.normalize_for_matching(before_text_to_compare)
        before_llm_normalized = text_utils.normalize_for_matching(llm_token.w_before.word)
        
        # Compare normalized forms for accurate matching
        before_fuzzy_match_score = fuzz.ratio(before_alto_normalized, before_llm_normalized)
    # If one is None and the other isn't, score remains 0.0 (not a match)
    
    # Get the text to compare for after word
    after_fuzzy_match_score = 0.0
    if after_alto is None and llm_token.w_after is None:
        # Both are at the end - perfect match
        after_fuzzy_match_score = 100.0
    elif after_alto is not None and llm_token.w_after is not None:
        # Both have after words - compare them
        after_text_to_compare = None
        if hypothesis_lookup and id(after_alto) in hypothesis_lookup:
            after_hyp = hypothesis_lookup[id(after_alto)]
            if after_hyp.chosen_LLM_token:
                after_text_to_compare = after_hyp.chosen_LLM_token.word
            else:
                # Use the best candidate's clean_form if available
                if after_hyp.candidates:
                    after_text_to_compare = after_hyp.candidates[0].clean_form
        
        if after_text_to_compare is None:
            # Fall back to ALTO content
            after_alto_content = text_utils.decode_html_entities(after_alto.content)
            after_text_to_compare = after_alto_content
        
        # Normalize for comparison
        after_alto_normalized = text_utils.normalize_for_matching(after_text_to_compare)
        after_llm_normalized = text_utils.normalize_for_matching(llm_token.w_after.word)
        
        # Compare normalized forms for accurate matching
        after_fuzzy_match_score = fuzz.ratio(after_alto_normalized, after_llm_normalized)
    # If one is None and the other isn't, score remains 0.0 (not a match)
    
    return before_fuzzy_match_score, after_fuzzy_match_score


def find_best_candidates_by_context(hypothesis_object: 'TokenHypotheses') -> List['TokenCandidate']:
    """
    Find the best candidate based on the context scores.
    Returns: TokenCandidate with the best context score.
    """
    best_candidates_by_context = []
    perfect_matches = []  # Track perfect matches separately
    
    for candidate in hypothesis_object.candidates:

        if not candidate.possible_llm_elements_by_context:  # Check if list is empty
            continue

        for llm_element, before_score, after_score in candidate.possible_llm_elements_by_context:
            if before_score == 100 and after_score == 100:
                # Perfect match - prioritize these
                perfect_matches.append((candidate, llm_element, before_score, after_score))
            elif len(best_candidates_by_context) == 0 and len(perfect_matches) == 0:
                # First non-perfect match (only if no perfect matches exist)
                best_candidates_by_context.append((candidate, llm_element, before_score, after_score))
            elif len(perfect_matches) == 0:  # Only consider non-perfect matches if no perfect ones exist
                # if the element doesn't have a perfect context score, and there are no perfect scores in the list so far
                if all(best_before < 100 and best_after < 100 
                        for _, _, best_before, best_after in best_candidates_by_context):
                    if (before_score >= max(best_before for _, _, best_before, _ in best_candidates_by_context) or 
                        after_score >= max(best_after for _, _, _, best_after in best_candidates_by_context)):
                        best_candidates_by_context.append((candidate, llm_element, before_score, after_score))

    # Prioritize perfect matches
    if perfect_matches:
        if len(perfect_matches) == 1:
            # Single perfect match - select it immediately
            hypothesis_object.best_candidates_by_context = perfect_matches
            # Also set the chosen token if not already set and the LLM token is not already matched
            if hypothesis_object.chosen_LLM_token is None:
                llm_token = perfect_matches[0][1]
                if not llm_token.matched:
                    hypothesis_object.chosen_LLM_token = llm_token
                    # Mark as matched immediately to prevent conflicts
                    llm_token.matched = True
                    # Set chosen_index
                    if perfect_matches[0][0] in hypothesis_object.candidates:
                        hypothesis_object.chosen_index = hypothesis_object.candidates.index(perfect_matches[0][0])
                    # Unflag since it's been resolved
                    hypothesis_object.flagged_for_error = False
                # If LLM token is already matched, leave as PENDING (don't set chosen_LLM_token)
        else:
            # Multiple perfect matches - requires proximity assessment (not yet implemented)
            # Store all perfect matches for later proximity-based selection
            hypothesis_object.best_candidates_by_context = perfect_matches
            # Do not select a match yet - will be handled by proximity assessment
    elif len(best_candidates_by_context) == 1:
        hypothesis_object.best_candidates_by_context = best_candidates_by_context

    return best_candidates_by_context if not perfect_matches else perfect_matches


def narrow_hypothesis_token_candidates_by_context(hypothesis_list: List['TokenHypotheses']) -> List['TokenHypotheses']:
    """
    Narrow down the list of token candidates by context based on the before and after alto words.
    Returns: List[TokenHypotheses] with updated possible_llm_elements_by_context set.
    """
    for token_hypothesis in hypothesis_list:
        likely_candidate = None

        # Check if this is a literal hyphen word (ends with hyphen)
        is_literal_hyphen = text_utils.is_hyphenish(token_hypothesis.anchor)
        
        #if all candidates of the hypothesis has no candidates where the possible_llm_elements_by_context is not None, and possible_llm_elements_by_fuzzy_match is not None, remove all candidates and flag it for error
        if all((candidate.possible_llm_elements_by_context is not None and len(candidate.possible_llm_elements_by_context) == 0 and len(candidate.possible_llm_elements_by_fuzzy_match) == 0) for candidate in token_hypothesis.candidates):
            token_hypothesis.flagged_for_error = True
            continue
        
        # For literal hyphen words: if they have 0 context matches, flag for error even if they have fuzzy matches
        # This indicates the word is incomplete and needs to be combined with its after_word
        if is_literal_hyphen:
            if all((candidate.possible_llm_elements_by_context is not None and len(candidate.possible_llm_elements_by_context) == 0) for candidate in token_hypothesis.candidates):
                token_hypothesis.flagged_for_error = True
                continue

        # Check for perfect context matches (100/100) and set chosen token immediately
        perfect_matches = []
        for candidate in token_hypothesis.candidates:
            for llm_element, before_score, after_score in candidate.possible_llm_elements_by_context:
                if before_score == 100 and after_score == 100:
                    perfect_matches.append((candidate, llm_element, before_score, after_score))
        
        # If there is only one perfect match, select it immediately
        if len(perfect_matches) == 1:
            candidate, llm_element, _, _ = perfect_matches[0]
            # Only set chosen_LLM_token if the LLM token is not already matched to another word
            if not llm_element.matched:
                token_hypothesis.chosen_LLM_token = llm_element
                # Mark as matched immediately to prevent conflicts
                llm_element.matched = True
                # Set the chosen_index to the candidate's position
                if candidate in token_hypothesis.candidates:
                    token_hypothesis.chosen_index = token_hypothesis.candidates.index(candidate)
                # Unflag since it's been resolved
                token_hypothesis.flagged_for_error = False
            # If LLM token is already matched, leave as PENDING (don't set chosen_LLM_token)
            continue  # Skip the rest of the processing for this hypothesis
        elif len(perfect_matches) > 1:
            # Multiple perfect matches - requires proximity assessment (not yet implemented)
            # Store all perfect matches for later proximity-based selection
            token_hypothesis.best_candidates_by_context = perfect_matches
            # Do not select a match yet - will be handled by proximity assessment
            continue  # Skip the rest of the processing for this hypothesis
        
        # Check for candidates with 0 context score on one side (when both sides should have matches)
        # This indicates potential hyphenation, merging, or ordering issues
        # BUT: Don't flag if the 0 score is because the LLM token is at a boundary (w_before=None or w_after=None)
        # This is valid for paragraph boundaries where OCR and LLM text may differ
        has_zero_context_on_one_side = False
        anchor = token_hypothesis.anchor
        # Only flag if both before and after words exist (meaning there should be context on both sides)
        if anchor.before_word is not None and anchor.after_word is not None:
            # Detect cross-block neighbors: in multi-column newspaper layout the ALTO
            # before_word / after_word may belong to a DIFFERENT TextBlock (a different
            # article entirely).  A zero context score on that side is expected — the
            # mismatch is structural, not a content error.
            # Primary check: TextBlock ID mismatch (stamped by iter_words in xml_obj.py).
            # Fallback: vpos jump > 50 px — catches column wraps and cases where Tesseract
            # has merged multiple articles into one TextBlock (so IDs match but context doesn't).
            _CROSS_BLOCK_VPOS_FALLBACK = 50  # px
            before_cross_block = (
                (getattr(anchor, 'text_block_id', None) is not None and
                 getattr(anchor.before_word, 'text_block_id', None) is not None and
                 anchor.text_block_id != anchor.before_word.text_block_id)
                or
                (hasattr(anchor, 'vpos') and hasattr(anchor.before_word, 'vpos') and
                 abs(anchor.vpos - anchor.before_word.vpos) > _CROSS_BLOCK_VPOS_FALLBACK)
            )
            after_cross_block = (
                (getattr(anchor, 'text_block_id', None) is not None and
                 getattr(anchor.after_word, 'text_block_id', None) is not None and
                 anchor.text_block_id != anchor.after_word.text_block_id)
                or
                (hasattr(anchor, 'vpos') and hasattr(anchor.after_word, 'vpos') and
                 abs(anchor.after_word.vpos - anchor.vpos) > _CROSS_BLOCK_VPOS_FALLBACK)
            )

            for candidate in token_hypothesis.candidates:
                for llm_element, before_score, after_score in candidate.possible_llm_elements_by_context:
                    # If one side is 0 and the other is > 0, this indicates a problem
                    # (e.g., "day" with before="Wednes-" doesn't match LLM "day"'s before_word)
                    # BUT: skip if the zero side is a cross-block ALTO neighbor — the mismatch
                    # is structural (article boundary), not a content error.
                    if (before_score == 0.0 and after_score > 0.0):
                        if llm_element.w_before is not None and not before_cross_block:
                            has_zero_context_on_one_side = True
                            break
                    elif (before_score > 0.0 and after_score == 0.0):
                        if llm_element.w_after is not None and not after_cross_block:
                            has_zero_context_on_one_side = True
                            break
                if has_zero_context_on_one_side:
                    break

        if has_zero_context_on_one_side:
            # Flag for reassessment - might need hyphenation, merging, or incorrect ordering
            token_hypothesis.flagged_for_error = True
            # Don't continue - still process candidates, but flag indicates need for later reassessment

        #find the likely candidate based on the context scores
        # Collect candidates to remove (can't modify list while iterating)
        candidates_to_remove = []
        for candidate in token_hypothesis.candidates:
            for element in candidate.possible_llm_elements_by_context:
                if likely_candidate is None:
                    likely_candidate = element
                elif element[1] > likely_candidate[1] or element[2] > likely_candidate[2]:
                    likely_candidate = element

            # Sort context matches by score for later use (proximity assessment will use these)
            if len(candidate.possible_llm_elements_by_context) > 0:
                candidate.possible_llm_elements_by_context.sort(key=lambda x: x[1]+x[2], reverse=True)
                # Keep the candidate - don't eliminate based on context quality
                # Even imperfect context matches (e.g., 100/50) should be kept for proximity assessment
            elif len(candidate.possible_llm_elements_by_fuzzy_match) == 0:
                # Only mark for deletion if it has neither context matches nor fuzzy matches
                # Keep candidates with fuzzy matches even if context matching failed (e.g., first/last words)
                # Keep candidates with context matches even if imperfect - let proximity assessment decide
                candidates_to_remove.append(candidate)
        
        # Remove candidates marked for deletion
        for candidate in candidates_to_remove:
            token_hypothesis.candidates.remove(candidate)
        
        # Also check best_candidates_by_context if it was already set (for backward compatibility)
        if (token_hypothesis.best_candidates_by_context is not None and 
            len(token_hypothesis.best_candidates_by_context) == 1 and 
            token_hypothesis.best_candidates_by_context[0][2] == 100 and 
            token_hypothesis.best_candidates_by_context[0][3] == 100):
            llm_token = token_hypothesis.best_candidates_by_context[0][1]
            # Only set chosen_LLM_token if the LLM token is not already matched to another word
            if not llm_token.matched:
                token_hypothesis.chosen_LLM_token = llm_token
                # Mark as matched immediately to prevent conflicts
                llm_token.matched = True
                # Unflag since it's been resolved
                token_hypothesis.flagged_for_error = False
            # If LLM token is already matched, leave as PENDING (don't set chosen_LLM_token)

    return hypothesis_list


def find_best_candidates_for_all_hypothesis_objects(hypothesis_list: List['TokenHypotheses'], llm_elements: List['LLMToken'] = None) -> List['TokenHypotheses']:
    """
    Find the best candidates for all hypothesis objects.
    If llm_elements is provided, uses proximity assessment for multiple perfect matches.
    Returns: List[TokenHypotheses] with updated chosen_llm_token set.
    """

    for hypothesis_object in hypothesis_list:
        find_best_candidates_by_context(hypothesis_object)
        
        # If there are multiple perfect matches and llm_elements, use proximity assessment
        if (hypothesis_object.best_candidates_by_context and 
            len(hypothesis_object.best_candidates_by_context) > 1 and 
            llm_elements is not None):
            best_llm_token = proximity_scoring.assess_proximity_for_multiple_matches(
                hypothesis_object, llm_elements, hypothesis_list
            )
            if best_llm_token:
                # Only assign if LLM token is not already matched to another hypothesis
                if not best_llm_token.matched:
                    hypothesis_object.chosen_LLM_token = best_llm_token
                    # Mark as matched immediately to prevent conflicts
                    best_llm_token.matched = True
                    # Find and set the chosen_index
                    for i, candidate in enumerate(hypothesis_object.candidates):
                        for llm_elem, _, _ in candidate.possible_llm_elements_by_context:
                            if llm_elem == best_llm_token:
                                hypothesis_object.chosen_index = i
                                break
                        if hypothesis_object.chosen_index is not None:
                            break
                    # Unflag since it's been resolved
                    hypothesis_object.flagged_for_error = False
                # If already matched, leave as PENDING (don't set chosen_LLM_token)
        
        # Mark as matched if chosen (for backward compatibility with code that sets it elsewhere)
        if hypothesis_object.chosen_LLM_token is not None and not hypothesis_object.chosen_LLM_token.matched:
            hypothesis_object.chosen_LLM_token.matched = True
    return hypothesis_list


def _set_bidirectional_link(left_hyp: 'TokenHypotheses', right_hyp: 'TokenHypotheses', is_left_to_right: bool) -> None:
    """
    Set a bidirectional link between two hypotheses, cleaning up any existing conflicting links.
    
    Args:
        left_hyp: The hypothesis on the left (or the one setting left_matched)
        right_hyp: The hypothesis on the right (or the one setting right_matched)
        is_left_to_right: True if setting left_hyp.left_matched = right_hyp,
                         False if setting left_hyp.right_matched = right_hyp
    """
    if is_left_to_right:
        # Setting left_hyp.left_matched = right_hyp (and right_hyp.right_matched = left_hyp)
        # Clean up left_hyp's old left link
        if left_hyp.left_matched is not None:
            old_left = left_hyp.left_matched
            if old_left.right_matched == left_hyp:
                old_left.right_matched = None
        
        # Clean up right_hyp's old right link
        if right_hyp.right_matched is not None:
            old_right = right_hyp.right_matched
            if old_right.left_matched == right_hyp:
                old_right.left_matched = None
        
        # Set the new bidirectional link
        left_hyp.left_matched = right_hyp
        right_hyp.right_matched = left_hyp
    else:
        # Setting left_hyp.right_matched = right_hyp (and right_hyp.left_matched = left_hyp)
        # Clean up left_hyp's old right link
        if left_hyp.right_matched is not None:
            old_right = left_hyp.right_matched
            if old_right.left_matched == left_hyp:
                old_right.left_matched = None
        
        # Clean up right_hyp's old left link
        if right_hyp.left_matched is not None:
            old_left = right_hyp.left_matched
            if old_left.right_matched == right_hyp:
                old_left.right_matched = None
        
        # Set the new bidirectional link
        left_hyp.right_matched = right_hyp
        right_hyp.left_matched = left_hyp


def link_hypothesis_objects_by_context(hypothesis_list: List['TokenHypotheses']) -> List['TokenHypotheses']:
    """
    Link hypothesis objects by context based on ALTO spatial order and LLM token sequence.
    
    CRITICAL: Only links spatially adjacent words (using ALTO before_word/after_word).
    This ensures we don't skip over PENDING words and respects document order.
    
    For each matched word:
    1. Check its ALTO before_word (spatial left neighbor)
    2. If that neighbor has the matching LLM token, link them
    3. Check its ALTO after_word (spatial right neighbor)  
    4. If that neighbor has the matching LLM token, link them
    
    Also links PENDING words if they have candidates matching the expected LLM token.
    Returns: List[TokenHypotheses] with updated left_matched and right_matched set.
    
    Ensures bidirectional consistency: if X.left_matched = Y, then Y.right_matched = X (and vice versa).
    """
    # Create a lookup: anchor -> hypothesis for fast spatial neighbor lookup
    anchor_to_hypothesis: Dict[int, 'TokenHypotheses'] = {}
    for hyp in hypothesis_list:
        anchor_to_hypothesis[id(hyp.anchor)] = hyp
    
    for hypothesis_object in hypothesis_list:
        if hypothesis_object.chosen_LLM_token is None:
            continue
        
        # Find the hypothesis to the LEFT (spatially adjacent via ALTO before_word)
        # Only check the immediate spatial neighbor, not all hypotheses
        if hypothesis_object.chosen_LLM_token.w_before is not None:
            # Check the ALTO spatial left neighbor
            if hypothesis_object.anchor.before_word is not None:
                before_word_id = id(hypothesis_object.anchor.before_word)
                if before_word_id in anchor_to_hypothesis:
                    spatial_left_neighbor = anchor_to_hypothesis[before_word_id]
                    
                    # Check if spatial neighbor has matching LLM token (exact LLMToken instance)
                    if (spatial_left_neighbor.chosen_LLM_token is not None and
                        spatial_left_neighbor.chosen_LLM_token == hypothesis_object.chosen_LLM_token.w_before):
                        # Perfect match - link them
                        _set_bidirectional_link(hypothesis_object, spatial_left_neighbor, is_left_to_right=True)
                    # Also check if PENDING neighbor has the LLM token in candidates
                    elif spatial_left_neighbor.candidates:
                        for candidate in spatial_left_neighbor.candidates:
                            # Check fuzzy matches
                            for llm_token in candidate.possible_llm_elements_by_fuzzy_match:
                                if llm_token == hypothesis_object.chosen_LLM_token.w_before:
                                    _set_bidirectional_link(hypothesis_object, spatial_left_neighbor, is_left_to_right=True)
                                    break
                            if hypothesis_object.left_matched:
                                break
                            # Check context matches
                            for llm_elem, _, _ in candidate.possible_llm_elements_by_context:
                                if llm_elem == hypothesis_object.chosen_LLM_token.w_before:
                                    _set_bidirectional_link(hypothesis_object, spatial_left_neighbor, is_left_to_right=True)
                                    break
                            if hypothesis_object.left_matched:
                                break
        
        # Find the hypothesis to the RIGHT (spatially adjacent via ALTO after_word)
        # Only check the immediate spatial neighbor, not all hypotheses
        if hypothesis_object.chosen_LLM_token.w_after is not None:
            # Check the ALTO spatial right neighbor
            if hypothesis_object.anchor.after_word is not None:
                after_word_id = id(hypothesis_object.anchor.after_word)
                if after_word_id in anchor_to_hypothesis:
                    spatial_right_neighbor = anchor_to_hypothesis[after_word_id]
                    
                    # Check if spatial neighbor has matching LLM token (exact LLMToken instance)
                    if (spatial_right_neighbor.chosen_LLM_token is not None and
                        spatial_right_neighbor.chosen_LLM_token == hypothesis_object.chosen_LLM_token.w_after):
                        # Perfect match - link them
                        _set_bidirectional_link(hypothesis_object, spatial_right_neighbor, is_left_to_right=False)
                    # Also check if PENDING neighbor has the LLM token in candidates
                    elif spatial_right_neighbor.candidates:
                        for candidate in spatial_right_neighbor.candidates:
                            # Check fuzzy matches
                            for llm_token in candidate.possible_llm_elements_by_fuzzy_match:
                                if llm_token == hypothesis_object.chosen_LLM_token.w_after:
                                    _set_bidirectional_link(hypothesis_object, spatial_right_neighbor, is_left_to_right=False)
                                    break
                            if hypothesis_object.right_matched:
                                break
                            # Check context matches
                            for llm_elem, _, _ in candidate.possible_llm_elements_by_context:
                                if llm_elem == hypothesis_object.chosen_LLM_token.w_after:
                                    _set_bidirectional_link(hypothesis_object, spatial_right_neighbor, is_left_to_right=False)
                                    break
                            if hypothesis_object.right_matched:
                                break
    
    return hypothesis_list


def assign_llm_candidates_to_all_token_hypotheses_by_context(
    token_hypothesis: 'TokenHypotheses', 
    hypothesis_lookup: Optional[Dict[int, 'TokenHypotheses']] = None,
    context_score_threshold: float = 90.0
) -> 'TokenHypotheses':
    """
    Assess each token candidate by context based on the before and after alto words.
    If the before or after fuzzy match score is above threshold, add the llm element to the possible_llm_elements_by_context list.
        - This allows for the possibility that the triplet on one side is a match, but not the other side.
    If hypothesis_lookup is provided, uses chosen_LLM_token from adjacent hypotheses when available (for split words).
    
    Args:
        token_hypothesis: TokenHypotheses to process
        hypothesis_lookup: Optional lookup for resolved hypotheses
        context_score_threshold: Minimum context score threshold (default: 90.0)
    
    Returns: TokenCandidate with updated possible_llm_elements_by_context set.
    """
    for token_candidate in token_hypothesis.candidates:
        if len(token_candidate.alto_words) == 0:
            continue
        
        # Prefer linked neighbors over ALTO before_word/after_word for context matching
        # Linked neighbors represent the actual resolved sequence, which is more accurate
        if token_hypothesis.left_matched and token_hypothesis.left_matched.chosen_LLM_token:
            # Use linked left neighbor's chosen token for context
            before_alto_object = None  # Will use linked neighbor instead
            before_linked_token = token_hypothesis.left_matched.chosen_LLM_token
        else:
            before_alto_object = token_candidate.alto_words[0].before_word
            before_linked_token = None
        
        if token_hypothesis.right_matched and token_hypothesis.right_matched.chosen_LLM_token:
            # Use linked right neighbor's chosen token for context
            after_alto_object = None  # Will use linked neighbor instead
            after_linked_token = token_hypothesis.right_matched.chosen_LLM_token
        else:
            after_alto_object = token_candidate.alto_words[0].after_word if len(token_candidate.alto_words) == 1 else token_candidate.alto_words[-1].after_word #handles hyphens and splits
            after_linked_token = None

        # Skip only if context matching is not possible (both sides missing)
        # If one side is missing, context matching is still possible on the other side
        if before_alto_object is None and after_alto_object is None and before_linked_token is None and after_linked_token is None:
            continue

        for element in token_candidate.possible_llm_elements_by_fuzzy_match:
            # Check if context matching is possible (at least one side available)
            # If both ALTO and LLM have None for a side, that's a perfect match (both at start/end)
            can_match_before = (before_alto_object is not None or before_linked_token is not None) or (element.w_before is None)
            can_match_after = (after_alto_object is not None or after_linked_token is not None) or (element.w_after is None)
            
            if not (can_match_before or can_match_after):
                continue
            
            # Calculate context scores - use linked tokens if available, otherwise use ALTO objects
            if before_linked_token:
                # Use linked neighbor for before context
                before_text = text_utils.normalize_for_matching(before_linked_token.word)
                before_llm_text = text_utils.normalize_for_matching(element.w_before.word) if element.w_before else None
                if before_llm_text:
                    before_fuzzy_match_score = fuzz.ratio(before_text, before_llm_text)
                elif element.w_before is None:
                    before_fuzzy_match_score = 100.0  # Both None - perfect match
                else:
                    before_fuzzy_match_score = 0.0
            else:
                before_fuzzy_match_score, _ = calculate_context_scores(
                    before_alto_object, None, element, hypothesis_lookup, context_score_threshold
                )
            
            if after_linked_token:
                # Use linked neighbor for after context
                after_text = text_utils.normalize_for_matching(after_linked_token.word)
                after_llm_text = text_utils.normalize_for_matching(element.w_after.word) if element.w_after else None
                if after_llm_text:
                    after_fuzzy_match_score = fuzz.ratio(after_text, after_llm_text)
                elif element.w_after is None:
                    after_fuzzy_match_score = 100.0  # Both None - perfect match
                else:
                    after_fuzzy_match_score = 0.0
            else:
                _, after_fuzzy_match_score = calculate_context_scores(
                    None, after_alto_object, element, hypothesis_lookup, context_score_threshold
                )

            # If the words match, and both before or after fuzzy match scores are above threshold, add the llm element to the possible_llm_elements_by_context list
            # But only if this LLM token isn't already in the list (deduplicate by token ID)
            if before_fuzzy_match_score > context_score_threshold or after_fuzzy_match_score > context_score_threshold:
                # Check if this LLM token is already in the list (same token instance)
                element_id = id(element)
                already_added = any(id(existing_elem) == element_id for existing_elem, _, _ in token_candidate.possible_llm_elements_by_context)
                if not already_added:
                    token_candidate.possible_llm_elements_by_context.append((element, float(before_fuzzy_match_score), float(after_fuzzy_match_score)))

    return token_hypothesis


def assign_llm_candidates_to_all_token_hypotheses_by_fuzzy_matching(hypothesis_list: List['TokenHypotheses'], llm_elements: List['LLMToken']) -> List['TokenHypotheses']:
    """
    for each hypothesis object (one per alto word), assign possible llm elements to each token candidate based on the clean form and llm word for all possible fuzzy matches
    Returns: List[TokenHypotheses] with possible_llm_elements_by_fuzzy_match set.
    """
    # Import at runtime to avoid circular imports
    from fuzzy_matching import create_llm_word_lookup
    
    # Create a lookup dictionary for O(1) access instead of O(n) search
    llm_word_lookup = create_llm_word_lookup(llm_elements)
    
    # Now iterate through candidates and look up matches efficiently
    for token_hypothesis in hypothesis_list:
        for candidate in token_hypothesis.candidates:
            # O(1) lookup instead of O(n) iteration through all llm_elements
            # candidate.clean_form is normalized, so match against normalized LLM words
            if candidate.clean_form in llm_word_lookup:
                candidate.possible_llm_elements_by_fuzzy_match.extend(llm_word_lookup[candidate.clean_form])

    return hypothesis_list


def _create_alto_to_hypothesis_lookup(hypothesis_list: List['TokenHypotheses']) -> Dict[int, 'TokenHypotheses']:
    """
    Create lookup dictionary mapping ALTO word IDs to their hypotheses.
    
    Args:
        hypothesis_list: List of all hypotheses
        
    Returns:
        Dictionary mapping id(alto_word) -> TokenHypotheses
    """
    alto_to_hypothesis_lookup: Dict[int, 'TokenHypotheses'] = {}
    for hyp in hypothesis_list:
        alto_to_hypothesis_lookup[id(hyp.anchor)] = hyp
        for candidate in hyp.candidates:
            for alto_word in candidate.alto_words:
                alto_to_hypothesis_lookup[id(alto_word)] = hyp
    return alto_to_hypothesis_lookup


def _rerun_context_matching_pipeline(
    hypothesis_list: List['TokenHypotheses'],
    llm_elements: List['LLMToken'],
    alto_to_hypothesis_lookup: Optional[Dict[int, 'TokenHypotheses']] = None
) -> List['TokenHypotheses']:
    """
    Helper function to re-run the full context matching pipeline.
    
    This consolidates the repeated pattern of:
    1. Creating lookup
    2. Clearing context matches
    3. Re-running context matching
    4. Narrowing candidates
    5. Finding best candidates
    6. Linking by context
    
    Args:
        hypothesis_list: List of hypotheses to process
        llm_elements: List of LLM tokens
        alto_to_hypothesis_lookup: Optional pre-created lookup (will create if None)
        
    Returns:
        Updated hypothesis_list
    """
    if alto_to_hypothesis_lookup is None:
        alto_to_hypothesis_lookup = _create_alto_to_hypothesis_lookup(hypothesis_list)
    
    # Clear and re-run context matching
    for hypothesis in hypothesis_list:
        if hypothesis.candidates:
            for candidate in hypothesis.candidates:
                candidate.possible_llm_elements_by_context.clear()
            assign_llm_candidates_to_all_token_hypotheses_by_context(
                hypothesis, alto_to_hypothesis_lookup
            )
    
    # Narrow, find best, and link
    hypothesis_list = narrow_hypothesis_token_candidates_by_context(hypothesis_list)
    hypothesis_list = find_best_candidates_for_all_hypothesis_objects(hypothesis_list, llm_elements)
    hypothesis_list = link_hypothesis_objects_by_context(hypothesis_list)
    
    return hypothesis_list

