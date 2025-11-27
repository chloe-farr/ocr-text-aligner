"""
Paragraph reordering module for text boundary mapping.

This module handles PENDING words that have LLM candidates but poor neighbor matches
due to paragraph reordering. It tests possible paragraph reorderings to match the
LLM text order.

Non-intrusive: only affects words marked as PENDING.
"""

from typing import List, Optional, Dict, Tuple, TYPE_CHECKING
from rapidfuzz import fuzz

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
POOR_NEIGHBOR_THRESHOLD = 85.0  # Below this is considered poor
MAX_REORDERING_DISTANCE = 50  # Maximum words to consider for reordering


def identify_pending_with_poor_neighbors(
    hypothesis_list: List[TokenHypotheses]
) -> List[TokenHypotheses]:
    """
    Find PENDING words with poor neighbor context scores.
    
    Args:
        hypothesis_list: List of all hypotheses
    
    Returns:
        List of hypotheses needing reordering
    """
    pending_words = []
    for hyp in hypothesis_list:
        # Must be PENDING (has candidates but no chosen token)
        if hyp.chosen_LLM_token is not None:
            continue
        if not hyp.candidates:
            continue
        
        # Check if neighbors have poor context scores
        has_poor_neighbor = False
        for candidate in hyp.candidates:
            for llm_elem, before_score, after_score in candidate.possible_llm_elements_by_context:
                if (before_score < POOR_NEIGHBOR_THRESHOLD or
                    after_score < POOR_NEIGHBOR_THRESHOLD):
                    has_poor_neighbor = True
                    break
            if has_poor_neighbor:
                break
        
        if has_poor_neighbor:
            pending_words.append(hyp)
    
    return pending_words


def _is_paragraph_boundary(
    prev_hyp: TokenHypotheses,
    curr_hyp: TokenHypotheses
) -> bool:
    """Check if there's a paragraph boundary between two hypotheses."""
    # Check for indentation (hpos significantly different)
    if prev_hyp.anchor.hpos > 0 and curr_hyp.anchor.hpos > 0:
        hpos_diff = abs(curr_hyp.anchor.hpos - prev_hyp.anchor.hpos)
        if hpos_diff > 100:
            return True
    # Check for capitalization after period
    prev_content = text_utils.decode_html_entities(prev_hyp.anchor.content)
    curr_content = text_utils.decode_html_entities(curr_hyp.anchor.content)
    if prev_content.rstrip().endswith('.') and curr_content and curr_content[0].isupper():
        return True
    # Check for large vertical gap
    vpos_diff = abs(curr_hyp.anchor.vpos - prev_hyp.anchor.vpos)
    if vpos_diff > 100:
        return True
    return False


def detect_paragraph_boundaries(
    hypothesis_list: List[TokenHypotheses],
    page
) -> List[Tuple[int, int]]:
    """
    Identify paragraph starts/ends based on layout patterns.
    
    Args:
        hypothesis_list: List of all hypotheses
        page: Page object for spatial information
    
    Returns:
        List of (start_idx, end_idx) tuples for each paragraph
    """
    if not hypothesis_list:
        return []
    paragraphs = []
    current_start = 0
    for i in range(1, len(hypothesis_list)):
        if _is_paragraph_boundary(hypothesis_list[i - 1], hypothesis_list[i]):
            paragraphs.append((current_start, i - 1))
            current_start = i
    if current_start < len(hypothesis_list):
        paragraphs.append((current_start, len(hypothesis_list) - 1))
    return paragraphs


def find_intervening_paragraphs(
    hypothesis_idx: int,
    paragraph_boundaries: List[Tuple[int, int]]
) -> List[int]:
    """
    Find paragraphs between hypothesis and its expected neighbor.
    
    Args:
        hypothesis_idx: Index of hypothesis
        paragraph_boundaries: List of paragraph ranges
    
    Returns:
        List of paragraph indices that could be reordered
    """
    # Find which paragraph contains this hypothesis
    current_para_idx = None
    for para_idx, (start, end) in enumerate(paragraph_boundaries):
        if start <= hypothesis_idx <= end:
            current_para_idx = para_idx
            break
    
    if current_para_idx is None:
        return []
    
    # Return adjacent paragraphs (limit to prevent explosion)
    intervening = []
    for para_idx in range(max(0, current_para_idx - 2),
                         min(len(paragraph_boundaries), current_para_idx + 3)):
        if para_idx != current_para_idx:
            intervening.append(para_idx)
    
    return intervening


def test_triplet_with_reordering(
    hyp1_idx: int,
    hyp2_idx: int,
    paragraph_indices: List[int],
    hypothesis_list: List[TokenHypotheses],
    llm_elements: List[LLMToken],
    paragraph_boundaries: List[Tuple[int, int]]
) -> Optional[Tuple[float, List[int]]]:
    """
    Test if reordering paragraphs improves triplet context scores.
    
    Args:
        hyp1_idx: Index of first hypothesis
        hyp2_idx: Index of second hypothesis
        paragraph_indices: Paragraphs to test reordering
        hypothesis_list: List of all hypotheses
        llm_elements: List of LLM tokens
        paragraph_boundaries: Current paragraph boundaries
    
    Returns:
        (improved_score, reordered_paragraph_indices) or None
    """
    if hyp1_idx >= len(hypothesis_list) or hyp2_idx >= len(hypothesis_list):
        return None
    
    hyp1 = hypothesis_list[hyp1_idx]
    hyp2 = hypothesis_list[hyp2_idx]
    
    # Get best LLM candidate for hyp1
    best_llm = None
    best_score = 0.0
    for candidate in hyp1.candidates:
        for llm_elem, before_score, after_score in candidate.possible_llm_elements_by_context:
            avg_score = (before_score + after_score) / 2.0
            if avg_score > best_score:
                best_score = avg_score
                best_llm = llm_elem
    
    if not best_llm:
        return None
    
    # Calculate current context score
    current_before, current_after = map_up_text.calculate_context_scores(
        hyp1.anchor.before_word,
        hyp2.anchor.after_word,
        best_llm,
        None
    )
    current_score = (current_before + current_after) / 2.0
    
    # Test reordering (simplified: just check if moving paragraphs improves)
    # For now, return None if improvement is not clear
    # Full implementation would test actual reordering
    
    return None  # Placeholder - full implementation needed


def evaluate_paragraph_reordering(
    hypothesis_list: List[TokenHypotheses],
    paragraph_boundaries: List[Tuple[int, int]],
    llm_elements: List[LLMToken]
) -> List[Tuple[int, int]]:
    """
    Evaluate and select best paragraph reorderings.
    
    Args:
        hypothesis_list: List of all hypotheses
        paragraph_boundaries: Current paragraph boundaries
        llm_elements: List of LLM tokens
    
    Returns:
        List of reordering operations (paragraph_idx, new_position)
    """
    reordering_ops = []
    pending_words = identify_pending_with_poor_neighbors(hypothesis_list)
    
    for hyp in pending_words:
        hyp_idx = hypothesis_list.index(hyp)
        if hyp_idx == -1:
            continue
        
        # Find intervening paragraphs
        intervening = find_intervening_paragraphs(hyp_idx, paragraph_boundaries)
        if not intervening:
            continue
        
        # For each candidate LLM token, test if reordering helps
        for candidate in hyp.candidates:
            for llm_elem, before_score, after_score in candidate.possible_llm_elements_by_context:
                # Check if one neighbor is strong and other is weak
                if (before_score >= POOR_NEIGHBOR_THRESHOLD and
                    after_score < POOR_NEIGHBOR_THRESHOLD):
                    # Right neighbor is poor - might need to move paragraphs after
                    # Simplified: mark for potential reordering
                    pass
                elif (after_score >= POOR_NEIGHBOR_THRESHOLD and
                      before_score < POOR_NEIGHBOR_THRESHOLD):
                    # Left neighbor is poor - might need to move paragraphs before
                    # Simplified: mark for potential reordering
                    pass
    
    return reordering_ops


def apply_paragraph_reordering(
    hypothesis_list: List[TokenHypotheses],
    reordering_operations: List[Tuple[int, int]]
) -> List[TokenHypotheses]:
    """
    Apply paragraph reordering operations to hypothesis_list.
    
    Args:
        hypothesis_list: List of all hypotheses
        reordering_operations: List of (paragraph_idx, new_position) tuples
    
    Returns:
        Reordered hypothesis_list
    """
    # For now, return unchanged (full implementation would reorder)
    # This is a placeholder - actual reordering logic would be complex
    return hypothesis_list


def reorder_paragraphs(
    hypothesis_list: List[TokenHypotheses],
    llm_elements: List[LLMToken],
    page
) -> List[TokenHypotheses]:
    """
    Main entry point: reorder paragraphs to improve PENDING word matches.
    
    Non-intrusive: only affects words marked as PENDING.
    
    Args:
        hypothesis_list: List of all hypotheses
        llm_elements: List of LLM tokens
        page: Page object for spatial information
    
    Returns:
        Updated hypothesis_list
    """
    # Detect paragraph boundaries
    paragraph_boundaries = detect_paragraph_boundaries(hypothesis_list, page)
    
    if not paragraph_boundaries:
        return hypothesis_list
    
    # Evaluate reordering opportunities
    reordering_ops = evaluate_paragraph_reordering(
        hypothesis_list, paragraph_boundaries, llm_elements
    )
    
    if not reordering_ops:
        return hypothesis_list
    
    # Apply reordering
    hypothesis_list = apply_paragraph_reordering(hypothesis_list, reordering_ops)
    
    return hypothesis_list

