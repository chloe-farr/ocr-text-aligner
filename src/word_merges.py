"""
Word merge/split functions for OCR text alignment.

Handles cases where OCR incorrectly merged multiple words into one,
or where words need to be split based on special characters.
"""

import re
from typing import List, Optional, Dict, Tuple, TYPE_CHECKING
import text_utils
import fuzzy_matching
import context_matching
import hyphen_linking
import xml_obj as XMLOBJ

if TYPE_CHECKING:
    from map_up_text import TokenHypotheses, TokenCandidate, LLMToken
else:
    # Import at runtime to avoid circular imports
    TokenHypotheses = None
    TokenCandidate = None
    LLMToken = None

# Split on spaces, commas, exclamation marks, and common OCR error characters (*, ~, etc.)
ADVANCED_SPLIT_RE = re.compile(r"[ ,!*~]+")


def _create_split_hypotheses(
    anchor: XMLOBJ.StringWord,
    split_words: List[str],
    clean_vocab: set[str],
    fuzzy_cutoff: float = 90.0
) -> List['TokenHypotheses']:
    """
    Create TokenHypotheses objects for split words.
    
    Args:
        anchor: Original ALTO word anchor
        split_words: List of split word strings
        clean_vocab: Set of normalized vocabulary words
        fuzzy_cutoff: Cutoff for fuzzy matching (default: 90.0)
    
    Returns:
        List of TokenHypotheses for each split word
    """
    # Import at runtime to avoid circular imports
    from map_up_text import TokenHypotheses, TokenCandidate
    
    split_hypotheses_objects: List[TokenHypotheses] = []
    
    # Filter out empty strings from split_words (can happen if content starts/ends with separators)
    split_words = [w for w in split_words if w]
    
    if not split_words:
        # No valid words after splitting, return empty list
        return split_hypotheses_objects
    
    # Calculate total character length of all split words combined
    # This gives us a baseline for proportional width distribution
    total_chars = sum(len(word) for word in split_words)
    
    if total_chars == 0:
        # Edge case: all empty words
        return split_hypotheses_objects
    
    # Calculate proportional widths and positions for each split word
    # Use character length as a proxy for visual width
    # Reserve space for gaps between words (small fixed gap)
    num_words = len(split_words)
    gap_size = max(2, int(anchor.width * 0.01))  # 1% of width, minimum 2 pixels
    
    # Calculate total space needed for gaps
    total_gap_space = gap_size * (num_words - 1) if num_words > 1 else 0
    
    # Available width after reserving space for gaps
    available_width = max(1, anchor.width - total_gap_space)
    
    # Calculate widths for all words proportionally
    word_widths = []
    cumulative_width = 0
    
    for i, word in enumerate(split_words):
        if i == num_words - 1:
            # Last word gets remaining width to avoid rounding errors
            word_width = available_width - cumulative_width
        else:
            # Proportional width based on character length
            word_width = int((len(word) / total_chars) * available_width)
            cumulative_width += word_width
        word_widths.append(max(1, word_width))  # Ensure at least 1 pixel
    
    # Now create hypotheses with calculated widths and positions
    current_hpos = anchor.hpos
    
    for i, word in enumerate(split_words):
        # Normalize the split word for matching
        normalized_word = text_utils.normalize_for_matching(word)
        
        word_width = word_widths[i]
        
        # Create hypothesis object for this split word with adjusted bounds
        split_anchor = XMLOBJ.StringWord(
            id=anchor.id, 
            width=word_width,
            height=anchor.height, 
            hpos=current_hpos, 
            vpos=anchor.vpos, 
            content=word, 
            wc=anchor.wc
        )
        # Initialize logical neighbors from anchor's spatial neighbors
        split_hypothesis = TokenHypotheses(
            anchor=split_anchor,
            anchor_left=split_anchor.before_word if i == 0 else None,  # First split word gets original's left neighbor
            anchor_right=split_anchor.after_word if i == len(split_words) - 1 else None  # Last split word gets original's right neighbor
        )
        
        # Update position for next word (current position + width + gap)
        current_hpos += word_width
        if i < num_words - 1:
            current_hpos += gap_size  # Add gap before next word
        
        # Create candidates for this split word (similar to create_hypothesis_list)
        # First check for exact match in normalized vocab
        if normalized_word in clean_vocab:
            split_hypothesis.candidates.append(
                TokenCandidate(clean_form=normalized_word, kind="word", alto_words=[split_anchor], fuzzy_score=100.0)
            )
        else:
            # If no exact match, try fuzzy matching
            token_candidates = fuzzy_matching.fuzzy_match_rapid(normalized_word, clean_vocab, cutoff=fuzzy_cutoff, limit=None)
            for token_candidate in token_candidates:
                split_hypothesis.candidates.append(
                    TokenCandidate(clean_form=token_candidate[0], kind="word", alto_words=[split_anchor], fuzzy_score=token_candidate[1])
                )
        
        split_hypotheses_objects.append(split_hypothesis)
    
    return split_hypotheses_objects


def search_for_word_merges(
    hypothesis_list: List['TokenHypotheses'], 
    llm_elements: List['LLMToken'],
    fuzzy_cutoff: float = 90.0
) -> List['TokenHypotheses']:
    """
    Handle word merges in the hypothesis list.
    
    Args:
        hypothesis_list: List of TokenHypotheses objects
        llm_elements: List of LLMToken objects
        fuzzy_cutoff: Cutoff for fuzzy matching (default: 90.0)
    
    Returns: List[TokenHypotheses] with updated left_matched and right_matched set.
    """
    # Import at runtime to avoid circular imports
    from map_up_text import TokenHypotheses, TokenCandidate
    
    # Import helper functions from hyphen_linking
    _setup_split_triplets = hyphen_linking._setup_split_triplets
    _create_candidate_fuzzy_lookups = hyphen_linking._create_candidate_fuzzy_lookups
    
    # Build new list instead of modifying in place (more efficient)
    new_hypothesis_list: List[TokenHypotheses] = []
    
    for hypothesis_object in hypothesis_list:
        if not hypothesis_object.flagged_for_error:
            # Not flagged, keep as is
            new_hypothesis_list.append(hypothesis_object)
            continue
            
        # test fuzzy matching on words that might be 2 actual words merged into one. Split by special characters.
        # Decode HTML entities before splitting
        decoded_anchor_content = text_utils.decode_html_entities(hypothesis_object.anchor.content)
        split_words = ADVANCED_SPLIT_RE.split(decoded_anchor_content)
        
        if len(split_words) <= 1:
            # Can't split, keep original
            new_hypothesis_list.append(hypothesis_object)
            continue
            
        # Create list of hypothesis objects for split words
        anchor = hypothesis_object.anchor
        
        # Get clean vocab for fuzzy matching
        clean_vocab = set(e.word_normalized for e in llm_elements)
        
        # Create split hypotheses using helper function
        split_hypotheses_objects = _create_split_hypotheses(anchor, split_words, clean_vocab, fuzzy_cutoff)
        
        # Assign possible llm elements based on fuzzy matching
        split_hypotheses_objects = context_matching.assign_llm_candidates_to_all_token_hypotheses_by_fuzzy_matching(
            split_hypotheses_objects, llm_elements
        )
        
        # Run context matching pipeline on split hypotheses to get full matches
        # Set word triplets for split hypotheses using helper function
        _setup_split_triplets(split_hypotheses_objects, anchor)
        
        # First pass: Process each split hypothesis for context matching (using raw ALTO content)
        for split_hyp in split_hypotheses_objects:
            context_matching.assign_llm_candidates_to_all_token_hypotheses_by_context(split_hyp)
        
        # Narrow down and find best candidates
        split_hypotheses_objects = context_matching.narrow_hypothesis_token_candidates_by_context(split_hypotheses_objects)
        split_hypotheses_objects = context_matching.find_best_candidates_for_all_hypothesis_objects(split_hypotheses_objects, llm_elements)
        
        # Second pass: Re-run context matching with lookup to use chosen_LLM_token from adjacent splits
        # This gives better context scores when adjacent splits have been resolved
        # Use object IDs as keys since StringWord objects aren't hashable
        split_hypothesis_lookup: Dict[int, TokenHypotheses] = {
            id(split_hyp.anchor): split_hyp for split_hyp in split_hypotheses_objects
        }
        
        # Re-run context matching with lookup to get improved scores
        for split_hyp in split_hypotheses_objects:
            # Clear existing context matches and re-compute with better context
            for candidate in split_hyp.candidates:
                candidate.possible_llm_elements_by_context.clear()
            context_matching.assign_llm_candidates_to_all_token_hypotheses_by_context(split_hyp, split_hypothesis_lookup)
        
        # Re-narrow and re-select with improved context scores
        split_hypotheses_objects = context_matching.narrow_hypothesis_token_candidates_by_context(split_hypotheses_objects)
        split_hypotheses_objects = context_matching.find_best_candidates_for_all_hypothesis_objects(split_hypotheses_objects, llm_elements)
        
        # Optimize: Create lookup dictionaries for O(1) membership testing
        # Use helper function to create lookups
        candidate_fuzzy_lookups = _create_candidate_fuzzy_lookups(split_hypotheses_objects)
        
        # Now do the linking with optimized lookups
        for i, split_hypothesis_object in enumerate(split_hypotheses_objects):
            if len(split_hypothesis_object.candidates) == 0:
                continue
                
            candidate = split_hypothesis_object.candidates[0]
            next_lookup = candidate_fuzzy_lookups[i + 1] if i + 1 < len(candidate_fuzzy_lookups) else {}
            prev_lookup = candidate_fuzzy_lookups[i - 1] if i - 1 >= 0 else {}
            current_lookup = candidate_fuzzy_lookups[i]
            
            # Create a list to track what we've already processed to avoid duplicates
            processed_next = set()
            processed_prev = set()
            
            for llm_element in candidate.possible_llm_elements_by_fuzzy_match:
                # Check if next element's w_after matches any element in next candidate's list
                if (i + 1 < len(split_hypotheses_objects) and 
                    llm_element.w_after is not None and
                    id(llm_element.w_after) in next_lookup):
                    # Add cross-references (avoid duplicates)
                    elem_id = id(llm_element)
                    if elem_id not in processed_next:
                        if elem_id not in current_lookup:
                            candidate.possible_llm_elements_by_fuzzy_match.append(llm_element)
                            current_lookup[elem_id] = llm_element
                        if len(split_hypotheses_objects[i+1].candidates) > 0:
                            after_id = id(llm_element.w_after)
                            if after_id not in candidate_fuzzy_lookups[i + 1]:
                                split_hypotheses_objects[i+1].candidates[0].possible_llm_elements_by_fuzzy_match.append(llm_element.w_after)
                                candidate_fuzzy_lookups[i + 1][after_id] = llm_element.w_after
                        processed_next.add(elem_id)

                # Check if previous element's w_before matches any element in prev candidate's list
                if (i - 1 >= 0 and 
                    llm_element.w_before is not None and
                    id(llm_element.w_before) in prev_lookup):
                    # Add cross-references (avoid duplicates)
                    elem_id = id(llm_element)
                    if elem_id not in processed_prev:
                        if elem_id not in current_lookup:
                            candidate.possible_llm_elements_by_fuzzy_match.append(llm_element)
                            current_lookup[elem_id] = llm_element
                        if len(split_hypotheses_objects[i-1].candidates) > 0:
                            before_id = id(llm_element.w_before)
                            if before_id not in candidate_fuzzy_lookups[i - 1]:
                                split_hypotheses_objects[i-1].candidates[0].possible_llm_elements_by_fuzzy_match.append(llm_element.w_before)
                                candidate_fuzzy_lookups[i - 1][before_id] = llm_element.w_before
                        processed_prev.add(elem_id)
                        break  # Only process first match
        
        # Add all split hypotheses to the new list
        new_hypothesis_list.extend(split_hypotheses_objects)
    
    return new_hypothesis_list

