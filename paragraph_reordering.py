"""
Cross-boundary neighbor matching module for text boundary mapping.

This module handles PENDING words that have chosen_LLM_token but missing neighbors
due to layout blocks being in opposite order. It uses a combinatorial approach to
test unmatched words against each other to find cross-boundary connections.

Similar to hyphen linking - tests combinations to find pairs that should be neighbors.
"""

from typing import List, Optional, Dict, Tuple, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from map_up_text import LLMToken, TokenHypotheses
    import xml_obj as XMLOBJ
else:
    LLMToken = None
    TokenHypotheses = None
    XMLOBJ = None

import text_utils
import map_up_text

# Configuration
MAX_COMBINATORIAL_SEARCH_DISTANCE = 200  # Maximum indices to search for cross-boundary matches


def is_pending_word(hyp: TokenHypotheses) -> bool:
    """
    Check if a word is PENDING.
    
    A word is PENDING if it has a chosen_LLM_token but is missing required
    left_matched or right_matched links, or if the linked neighbors don't have
    the correct LLM tokens.
    
    Args:
        hyp: TokenHypotheses to check
        
    Returns:
        True if the word is PENDING, False otherwise
    """
    # Must have a chosen LLM token to be PENDING (words without chosen_LLM_token are ERROR or NO CAND)
    if hyp.chosen_LLM_token is None:
        return False
    
    # Check if left neighbor is missing or incorrect
    missing_left = False
    if hyp.chosen_LLM_token.w_before is not None:
        if hyp.left_matched is None:
            missing_left = True
        elif (hyp.left_matched.chosen_LLM_token is None or
              hyp.left_matched.chosen_LLM_token != hyp.chosen_LLM_token.w_before):
            missing_left = True
    
    # Check if right neighbor is missing or incorrect
    missing_right = False
    if hyp.chosen_LLM_token.w_after is not None:
        if hyp.right_matched is None:
            missing_right = True
        elif (hyp.right_matched.chosen_LLM_token is None or
              hyp.right_matched.chosen_LLM_token != hyp.chosen_LLM_token.w_after):
            missing_right = True
    
    # PENDING if either neighbor is missing or incorrect
    return missing_left or missing_right


def find_words_with_missing_neighbors(
    hypothesis_list: List[TokenHypotheses]
) -> List[Tuple[TokenHypotheses, int, Optional[LLMToken], str]]:
    """
    Find PENDING words with chosen_LLM_token but missing expected neighbors.
    
    Only processes words that are flagged as PENDING (have chosen_LLM_token but
    missing or incorrect neighbor links).
    
    Returns list of (hypothesis, index, expected_neighbor_token, direction) tuples
    where direction is 'left' or 'right'.
    
    Args:
        hypothesis_list: List of all hypotheses
        
    Returns:
        List of (hyp, idx, expected_token, 'left'|'right') tuples for PENDING words only
    """
    unmatched_neighbors = []
    
    for idx, hyp in enumerate(hypothesis_list):
        # Only process PENDING words
        if not is_pending_word(hyp):
            continue
            
        # Check left neighbor
        if hyp.chosen_LLM_token.w_before is not None:
            missing_left = False
            if hyp.left_matched is None:
                missing_left = True
            elif (hyp.left_matched.chosen_LLM_token is None or
                  hyp.left_matched.chosen_LLM_token != hyp.chosen_LLM_token.w_before):
                missing_left = True
                
            if missing_left:
                unmatched_neighbors.append((hyp, idx, hyp.chosen_LLM_token.w_before, 'left'))
        
        # Check right neighbor
        if hyp.chosen_LLM_token.w_after is not None:
            missing_right = False
            if hyp.right_matched is None:
                missing_right = True
            elif (hyp.right_matched.chosen_LLM_token is None or
                  hyp.right_matched.chosen_LLM_token != hyp.chosen_LLM_token.w_after):
                missing_right = True
                
            if missing_right:
                unmatched_neighbors.append((hyp, idx, hyp.chosen_LLM_token.w_after, 'right'))
    
    return unmatched_neighbors


def find_cross_boundary_neighbor_matches(
    hypothesis_list: List[TokenHypotheses],
    max_search_distance: int = MAX_COMBINATORIAL_SEARCH_DISTANCE
) -> List[Tuple[TokenHypotheses, TokenHypotheses, str]]:
    """
    Test combinatorials between PENDING words to find cross-boundary neighbor pairs.
    
    Only tests PENDING words against other PENDING words, focusing on triplets:
    - Words missing a LEFT neighbor paired with words missing a RIGHT neighbor
    - Checks if they should be neighbors (bidirectional expectation)
    
    Args:
        hypothesis_list: List of all hypotheses
        max_search_distance: Maximum index distance to search (default: 200)
        
    Returns:
        List of (word_A, word_B, direction) tuples where:
        - word_A and word_B are both PENDING
        - word_A expects word_B as neighbor
        - direction is 'left' or 'right' (from word_A's perspective)
    """
    import text_utils
    
    # Find all PENDING words
    pending_words: List[Tuple[TokenHypotheses, int]] = []
    for idx, hyp in enumerate(hypothesis_list):
        if is_pending_word(hyp):
            pending_words.append((hyp, idx))
    
    if len(pending_words) < 2:
        return []
    
    # Separate PENDING words into those missing left neighbor and those missing right neighbor
    missing_left: List[Tuple[TokenHypotheses, int, LLMToken]] = []
    missing_right: List[Tuple[TokenHypotheses, int, LLMToken]] = []
    
    for hyp, idx in pending_words:
        # Check if missing left neighbor
        if hyp.chosen_LLM_token and hyp.chosen_LLM_token.w_before is not None:
            missing_left_neighbor = False
            if hyp.left_matched is None:
                missing_left_neighbor = True
            elif (hyp.left_matched.chosen_LLM_token is None or
                  hyp.left_matched.chosen_LLM_token != hyp.chosen_LLM_token.w_before):
                missing_left_neighbor = True
            
            if missing_left_neighbor:
                missing_left.append((hyp, idx, hyp.chosen_LLM_token.w_before))
        
        # Check if missing right neighbor
        if hyp.chosen_LLM_token and hyp.chosen_LLM_token.w_after is not None:
            missing_right_neighbor = False
            if hyp.right_matched is None:
                missing_right_neighbor = True
            elif (hyp.right_matched.chosen_LLM_token is None or
                  hyp.right_matched.chosen_LLM_token != hyp.chosen_LLM_token.w_after):
                missing_right_neighbor = True
            
            if missing_right_neighbor:
                missing_right.append((hyp, idx, hyp.chosen_LLM_token.w_after))
    
    if not missing_left or not missing_right:
        return []
    
    # Debug: Show what we're looking for
    print(f"\n[Cross-Boundary Matching] Testing combinatorials between PENDING words:")
    print(f"  - {len(missing_left)} PENDING words missing LEFT neighbor")
    print(f"  - {len(missing_right)} PENDING words missing RIGHT neighbor")
    print(f"  - Testing {len(missing_left)} × {len(missing_right)} = {len(missing_left) * len(missing_right)} combinations")
    
    cross_boundary_matches = []
    matches_found = 0
    
    # Test combinatorials: each word missing left neighbor against each word missing right neighbor
    for hyp_left_missing, idx_left, expected_left_token in missing_left:
        for hyp_right_missing, idx_right, expected_right_token in missing_right:
            # Skip if it's the same word
            if hyp_left_missing == hyp_right_missing:
                continue
            
            # Check distance first - respect max_search_distance limit
            distance = abs(idx_right - idx_left)
            if distance > max_search_distance:
                continue
            
            # Check if they're already linked
            if hyp_left_missing.left_matched == hyp_right_missing:
                continue
            if hyp_right_missing.right_matched == hyp_left_missing:
                continue
            
            # Check if this is a bidirectional match:
            # - hyp_left_missing expects hyp_right_missing on its LEFT
            # - hyp_right_missing expects hyp_left_missing on its RIGHT
            left_expects_right = False
            right_expects_left = False
            
            # Check if left_missing word expects right_missing word on its left
            if (hyp_left_missing.chosen_LLM_token and 
                hyp_left_missing.chosen_LLM_token.w_before is not None):
                if (expected_left_token == hyp_right_missing.chosen_LLM_token or
                    expected_left_token.word_normalized == hyp_right_missing.chosen_LLM_token.word_normalized):
                    left_expects_right = True
            
            # Check if right_missing word expects left_missing word on its right
            if (hyp_right_missing.chosen_LLM_token and
                hyp_right_missing.chosen_LLM_token.w_after is not None):
                if (expected_right_token == hyp_left_missing.chosen_LLM_token or
                    expected_right_token.word_normalized == hyp_left_missing.chosen_LLM_token.word_normalized):
                    right_expects_left = True
            
            # Only link if bidirectional expectation (both words expect each other)
            if left_expects_right and right_expects_left:
                # Only link if they're far apart (cross-boundary indicator) or exact token match
                # Note: "far apart" means > 3 positions, indicating cross-boundary
                # We already checked distance <= max_search_distance above
                is_exact_token_match = (
                    expected_left_token == hyp_right_missing.chosen_LLM_token and
                    expected_right_token == hyp_left_missing.chosen_LLM_token
                )
                
                # Match if exact token match OR if distance > 3 (cross-boundary indicator)
                if is_exact_token_match or distance > 3:
                    cross_boundary_matches.append((hyp_left_missing, hyp_right_missing, 'left'))
                    matches_found += 1
                    
                    # Debug: Show match
                    if matches_found <= 10:  # Only show first 10
                        word_left = text_utils.decode_html_entities(hyp_left_missing.anchor.content)
                        word_right = text_utils.decode_html_entities(hyp_right_missing.anchor.content)
                        llm_left = hyp_left_missing.chosen_LLM_token.word if hyp_left_missing.chosen_LLM_token else "N/A"
                        llm_right = hyp_right_missing.chosen_LLM_token.word if hyp_right_missing.chosen_LLM_token else "N/A"
                        reason = "exact_token" if is_exact_token_match else f"distance_{distance}"
                        print(f"    [MATCH {matches_found}] Hyp[{idx_left}] '{word_left}' ({llm_left}) ←→ Hyp[{idx_right}] '{word_right}' ({llm_right}) [bidirectional, {reason}]")
    
    if matches_found > 10:
        print(f"    ... and {matches_found - 10} more matches")
    print(f"  Total bidirectional matches found: {matches_found}")
    
    return cross_boundary_matches


def detect_layout_block_reordering_needed(
    hypothesis_list: List[TokenHypotheses]
) -> List[Tuple[TokenHypotheses, TokenHypotheses, str]]:
    """
    Detect when layout blocks need reordering by finding cross-boundary neighbor pairs.
    
    Uses combinatorial approach: tests unmatched words against each other to find
    pairs that should be neighbors but are separated by layout boundaries.
    
    Args:
        hypothesis_list: List of all hypotheses
        
    Returns:
        List of (word_A, word_B, direction) tuples indicating cross-boundary connections
    """
    cross_boundary_matches = find_cross_boundary_neighbor_matches(hypothesis_list)
    
    # Group matches by layout boundary areas
    # For now, just return all matches - the caller can decide how to handle them
    return cross_boundary_matches


def link_cross_boundary_neighbors(
    hypothesis_list: List[TokenHypotheses]
) -> List[TokenHypotheses]:
    """
    Link cross-boundary neighbors found through combinatorial matching.
    
    This creates links between words that should be neighbors but are separated
    by layout boundaries. These links can then be used to detect reordering needs.
    
    Args:
        hypothesis_list: List of all hypotheses
        
    Returns:
        Updated hypothesis_list with cross-boundary links established
    """
    cross_boundary_matches = find_cross_boundary_neighbor_matches(hypothesis_list)
    
    if cross_boundary_matches:
        import text_utils
        print(f"\n[Cross-Boundary Matching] Linking {len(cross_boundary_matches)} cross-boundary neighbor pairs:")
        for hyp_A, hyp_B, direction in cross_boundary_matches[:10]:  # Show first 10
            word_A = text_utils.decode_html_entities(hyp_A.anchor.content)
            word_B = text_utils.decode_html_entities(hyp_B.anchor.content)
            llm_A = hyp_A.chosen_LLM_token.word if hyp_A.chosen_LLM_token else "N/A"
            llm_B = hyp_B.chosen_LLM_token.word if hyp_B.chosen_LLM_token else "N/A"
            idx_A = hypothesis_list.index(hyp_A)
            idx_B = hypothesis_list.index(hyp_B)
            print(f"  Linking: Hyp[{idx_A}] '{word_A}' ({llm_A}) ←→ Hyp[{idx_B}] '{word_B}' ({llm_B}) [{direction}]")
        if len(cross_boundary_matches) > 10:
            print(f"  ... and {len(cross_boundary_matches) - 10} more")
    else:
        print("\n[Cross-Boundary Matching] No cross-boundary matches found")
    
    for hyp_A, hyp_B, direction in cross_boundary_matches:
        if direction == 'left':
            # hyp_A expects hyp_B on its left
            # Verify the match before linking
            if (hyp_A.chosen_LLM_token and hyp_A.chosen_LLM_token.w_before and
                hyp_B.chosen_LLM_token and
                (hyp_A.chosen_LLM_token.w_before == hyp_B.chosen_LLM_token or
                 hyp_A.chosen_LLM_token.w_before.word_normalized == hyp_B.chosen_LLM_token.word_normalized)):
                # Set bidirectional link
                map_up_text._set_bidirectional_link(hyp_A, hyp_B, is_left_to_right=True)
                # Update logical neighbors (anchor_left/anchor_right) to reflect cross-boundary connection
                hyp_A.anchor_left = hyp_B.anchor  # hyp_A's logical left neighbor is hyp_B
                hyp_B.anchor_right = hyp_A.anchor  # hyp_B's logical right neighbor is hyp_A
        elif direction == 'right':
            # hyp_A expects hyp_B on its right
            # Verify the match before linking
            if (hyp_A.chosen_LLM_token and hyp_A.chosen_LLM_token.w_after and
                hyp_B.chosen_LLM_token and
                (hyp_A.chosen_LLM_token.w_after == hyp_B.chosen_LLM_token or
                 hyp_A.chosen_LLM_token.w_after.word_normalized == hyp_B.chosen_LLM_token.word_normalized)):
                # Set bidirectional link
                map_up_text._set_bidirectional_link(hyp_A, hyp_B, is_left_to_right=False)
                # Update logical neighbors (anchor_left/anchor_right) to reflect cross-boundary connection
                hyp_A.anchor_right = hyp_B.anchor  # hyp_A's logical right neighbor is hyp_B
                hyp_B.anchor_left = hyp_A.anchor  # hyp_B's logical left neighbor is hyp_A
    
    # Verify links were established
    links_verified = 0
    for hyp_A, hyp_B, direction in cross_boundary_matches:
        if direction == 'left':
            if hyp_A.left_matched == hyp_B and hyp_B.right_matched == hyp_A:
                links_verified += 1
        elif direction == 'right':
            if hyp_A.right_matched == hyp_B and hyp_B.left_matched == hyp_A:
                links_verified += 1
    
    if links_verified > 0:
        import text_utils
        print(f"  ✓ Verified {links_verified}/{len(cross_boundary_matches)} links established successfully")
    
    return hypothesis_list


def reorder_paragraphs(
    hypothesis_list: List[TokenHypotheses],
    llm_elements: List[LLMToken],
    page
) -> List[TokenHypotheses]:
    """
    Main entry point: detect and handle cross-boundary neighbor issues.
    
    Uses combinatorial approach to find unmatched words that should be neighbors.
    Tests combinations of words with missing neighbors against all other words to find
    cross-boundary matches (similar to hyphen linking).
    
    Args:
        hypothesis_list: List of all hypotheses
        llm_elements: List of LLM tokens (unused for now)
        page: Page object (unused for now)
        
    Returns:
        Updated hypothesis_list with cross-boundary links established
    """
    print("\n[Cross-Boundary Matching] Starting cross-boundary neighbor reconciliation...")
    
    # Find and link cross-boundary neighbors using combinatorial matching
    hypothesis_list = link_cross_boundary_neighbors(hypothesis_list)
    
    return hypothesis_list
