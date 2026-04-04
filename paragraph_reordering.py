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
            missing_left = True
    
    # Check if right neighbor is missing or incorrect
    missing_right = False
    if hyp.chosen_LLM_token.w_after is not None:
        if hyp.right_matched is None:
            missing_right = True
        elif (hyp.right_matched.chosen_LLM_token is None or
              hyp.right_matched.chosen_LLM_token != hyp.chosen_LLM_token.w_after):
            missing_right = True
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


def _build_swap_graph(
    hypothesis_list: List[TokenHypotheses],
    max_search_distance: int = MAX_COMBINATORIAL_SEARCH_DISTANCE
) -> Dict[int, List[Tuple[TokenHypotheses, int, str]]]:
    """
    Build a graph of potential swaps between PENDING words.
    
    Each node (PENDING word) has edges to other PENDING words that it expects as neighbors.
    This graph is used to find chains of swaps that would resolve multiple PENDING words.
    
    Args:
        hypothesis_list: List of all hypotheses
        max_search_distance: Maximum index distance to search (default: 200)
        
    Returns:
        Dictionary mapping id(PENDING word) to list of (target_word, target_idx, direction) tuples
        where direction is 'left' or 'right' (from the source word's perspective)
    """
    import text_utils
    
    # Find all PENDING words with their indices
    pending_words: List[Tuple[TokenHypotheses, int]] = []
    for idx, hyp in enumerate(hypothesis_list):
        if is_pending_word(hyp):
            pending_words.append((hyp, idx))
    
    if len(pending_words) < 2:
        return {}
    
    # Build graph: for each PENDING word, find other PENDING words it expects as neighbors
    # Use id(hyp) as key since TokenHypotheses objects are not hashable
    swap_graph: Dict[int, List[Tuple[TokenHypotheses, int, str]]] = {}
    
    for hyp_A, idx_A in pending_words:
        swap_graph[id(hyp_A)] = []
        
        # Check what neighbors hyp_A expects
        expected_left = hyp_A.chosen_LLM_token.w_before if hyp_A.chosen_LLM_token else None
        expected_right = hyp_A.chosen_LLM_token.w_after if hyp_A.chosen_LLM_token else None
        
        # Search other PENDING words to see if any match what hyp_A expects
        for hyp_B, idx_B in pending_words:
            if hyp_A == hyp_B:
                continue
            
            # Check distance
            distance = abs(idx_B - idx_A)
            if distance > max_search_distance:
                continue
            
            # Check if hyp_B has the LLM token that hyp_A expects
            if hyp_B.chosen_LLM_token is None:
                continue
            
            # Check if hyp_A expects hyp_B on its left
            if expected_left is not None:
                if (expected_left == hyp_B.chosen_LLM_token or
                    expected_left.word_normalized == hyp_B.chosen_LLM_token.word_normalized):
                    # Also check if hyp_B expects hyp_A on its right (bidirectional)
                    if (hyp_B.chosen_LLM_token.w_after is not None and
                        (hyp_B.chosen_LLM_token.w_after == hyp_A.chosen_LLM_token or
                         hyp_B.chosen_LLM_token.w_after.word_normalized == hyp_A.chosen_LLM_token.word_normalized)):
                        swap_graph[id(hyp_A)].append((hyp_B, idx_B, 'left'))
            
            # Check if hyp_A expects hyp_B on its right
            if expected_right is not None:
                if (expected_right == hyp_B.chosen_LLM_token or
                    expected_right.word_normalized == hyp_B.chosen_LLM_token.word_normalized):
                    # Also check if hyp_B expects hyp_A on its left (bidirectional)
                    if (hyp_B.chosen_LLM_token.w_before is not None and
                        (hyp_B.chosen_LLM_token.w_before == hyp_A.chosen_LLM_token or
                         hyp_B.chosen_LLM_token.w_before.word_normalized == hyp_A.chosen_LLM_token.word_normalized)):
                        swap_graph[id(hyp_A)].append((hyp_B, idx_B, 'right'))
    
    return swap_graph


def _find_swap_chains(
    swap_graph: Dict[int, List[Tuple[TokenHypotheses, int, str]]],
    hypothesis_list: List[TokenHypotheses]
) -> List[List[Tuple[TokenHypotheses, TokenHypotheses, str]]]:
    """
    Find chains of swaps that would resolve multiple PENDING words.
    
    A chain is a sequence of swaps where:
    - Swap 1: word A <-> word B (resolves A and B)
    - Swap 2: word B <-> word C (resolves B and C, but B was already resolved by swap 1)
    - etc.
    
    We look for cycles and paths in the swap graph that maximize the number of PENDING words resolved.
    
    Args:
        swap_graph: Graph of potential swaps (keyed by id(hyp))
        hypothesis_list: List of all hypotheses (for indexing)
        
    Returns:
        List of swap chains, where each chain is a list of (word_A, word_B, direction) tuples
    """
    import text_utils
    
    # Create reverse lookup: id -> TokenHypotheses for graph traversal
    id_to_hyp: Dict[int, TokenHypotheses] = {}
    for hyp in hypothesis_list:
        if is_pending_word(hyp):
            id_to_hyp[id(hyp)] = hyp
    
    # Find all bidirectional pairs (simple swaps)
    swap_pairs: List[Tuple[TokenHypotheses, TokenHypotheses, str]] = []
    processed_pairs = set()
    
    for hyp_A_id, edges in swap_graph.items():
        hyp_A = id_to_hyp[hyp_A_id]
        for hyp_B, idx_B, direction in edges:
            # Check if this is a bidirectional pair (both words expect each other)
            pair_key = (hyp_A_id, id(hyp_B))
            if pair_key in processed_pairs:
                continue
            
            # Check if hyp_B also has hyp_A in its edges
            hyp_B_id = id(hyp_B)
            if hyp_B_id in swap_graph:
                for hyp_B_target, idx_A, reverse_direction in swap_graph[hyp_B_id]:
                    if id(hyp_B_target) == hyp_A_id:
                        # Found bidirectional pair
                        swap_pairs.append((hyp_A, hyp_B, direction))
                        processed_pairs.add(pair_key)
                        processed_pairs.add((hyp_B_id, hyp_A_id))
                        break
    
    # Group swaps into chains
    # A chain is a sequence where swaps share words (A<->B, B<->C, C<->D)
    chains: List[List[Tuple[TokenHypotheses, TokenHypotheses, str]]] = []
    used_words = set()
    
    # Start with swaps that resolve the most PENDING words
    # Sort by distance (prefer swaps that are far apart, indicating cross-boundary)
    def get_swap_score(swap: Tuple[TokenHypotheses, TokenHypotheses, str]) -> int:
        hyp_A, hyp_B, _ = swap
        idx_A = hypothesis_list.index(hyp_A)
        idx_B = hypothesis_list.index(hyp_B)
        return abs(idx_B - idx_A)  # Prefer larger distances (cross-boundary)
    
    swap_pairs.sort(key=get_swap_score, reverse=True)
    
    # Build chains greedily: start with best swaps, then find connected swaps
    for swap in swap_pairs:
        hyp_A, hyp_B, direction = swap
        if id(hyp_A) in used_words or id(hyp_B) in used_words:
            # Already part of a chain, skip
            continue
        
        # Start a new chain with this swap
        chain = [swap]
        used_words.add(id(hyp_A))
        used_words.add(id(hyp_B))
        
        # Try to extend the chain by finding swaps that share words with current chain
        # Look for swaps where one word is already in the chain
        extended = True
        while extended:
            extended = False
            for other_swap in swap_pairs:
                other_A, other_B, other_dir = other_swap
                if id(other_A) in used_words and id(other_B) in used_words:
                    continue  # Both already used
                
                # Check if this swap shares a word with the chain
                chain_words = {id(hyp) for swap_item in chain for hyp in (swap_item[0], swap_item[1])}
                if id(other_A) in chain_words or id(other_B) in chain_words:
                    # This swap extends the chain
                    chain.append(other_swap)
                    used_words.add(id(other_A))
                    used_words.add(id(other_B))
                    extended = True
                    break
        
        if chain:
            chains.append(chain)
    
    return chains


def find_cross_boundary_neighbor_matches(
    hypothesis_list: List[TokenHypotheses],
    max_search_distance: int = MAX_COMBINATORIAL_SEARCH_DISTANCE
) -> List[Tuple[TokenHypotheses, TokenHypotheses, str]]:
    """
    Find cross-boundary neighbor matches using chain detection.
    
    Builds a graph of potential swaps and finds chains where multiple swaps
    would resolve multiple PENDING words. Returns all swaps from all chains.
    
    Args:
        hypothesis_list: List of all hypotheses
        max_search_distance: Maximum index distance to search (default: 200)
        
    Returns:
        List of (word_A, word_B, direction) tuples from all detected chains
    """
    import text_utils
    
    # Build swap graph
    swap_graph = _build_swap_graph(hypothesis_list, max_search_distance)
    
    if not swap_graph:
        return []
    
    # Find chains of swaps
    chains = _find_swap_chains(swap_graph, hypothesis_list)
    
    # Flatten chains into list of swaps
    all_swaps: List[Tuple[TokenHypotheses, TokenHypotheses, str]] = []
    for chain in chains:
        all_swaps.extend(chain)
    
    # Debug output
    print(f"\n[Cross-Boundary Matching] Found {len(chains)} swap chain(s) with {len(all_swaps)} total swaps:")
    for i, chain in enumerate(chains[:5]):  # Show first 5 chains
        print(f"  Chain {i+1}: {len(chain)} swap(s)")
        for j, (hyp_A, hyp_B, direction) in enumerate(chain[:3]):  # Show first 3 swaps per chain
            word_A = text_utils.decode_html_entities(hyp_A.anchor.content)
            word_B = text_utils.decode_html_entities(hyp_B.anchor.content)
            idx_A = hypothesis_list.index(hyp_A)
            idx_B = hypothesis_list.index(hyp_B)
            print(f"    Swap {j+1}: Hyp[{idx_A}] '{word_A}' ←→ Hyp[{idx_B}] '{word_B}' [{direction}]")
        if len(chain) > 3:
            print(f"    ... and {len(chain) - 3} more swaps in this chain")
    if len(chains) > 5:
        print(f"  ... and {len(chains) - 5} more chains")
    
    return all_swaps


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
    hypothesis_list: List[TokenHypotheses],
    cross_boundary_matches: Optional[List[Tuple[TokenHypotheses, TokenHypotheses, str]]] = None
) -> List[TokenHypotheses]:
    """
    Link cross-boundary neighbors found through combinatorial matching.
    
    This creates links between words that should be neighbors but are separated
    by layout boundaries. These links can then be used to detect reordering needs.
    
    Args:
        hypothesis_list: List of all hypotheses
        cross_boundary_matches: Optional pre-computed matches (will find if None)
        
    Returns:
        Updated hypothesis_list with cross-boundary links established
    """
    if cross_boundary_matches is None:
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
    page,
    max_iterations: int = 10
) -> List[TokenHypotheses]:
    """
    Main entry point: detect and handle cross-boundary neighbor issues using chain detection.
    
    Uses combinatorial approach to find chains of swaps where swapping one pair enables
    other pairs to match. Iteratively applies swaps until no more improvements.
    
    Args:
        hypothesis_list: List of all hypotheses
        llm_elements: List of LLM tokens (unused for now)
        page: Page object (unused for now)
        max_iterations: Maximum number of iterations (default: 10)
        
    Returns:
        Updated hypothesis_list with cross-boundary links established
    """
    print("\n[Cross-Boundary Matching] Starting cross-boundary neighbor reconciliation...")
    
    # Iteratively find and apply swaps until no more improvements
    prev_pending_count = sum(1 for h in hypothesis_list if is_pending_word(h))
    
    for iteration in range(max_iterations):
        # Find cross-boundary matches (chains of swaps)
        cross_boundary_matches = find_cross_boundary_neighbor_matches(hypothesis_list)
        
        if not cross_boundary_matches:
            if iteration == 0:
                print(f"[Cross-Boundary Matching] No swaps found")
            else:
                print(f"[Cross-Boundary Matching] No more swaps found after {iteration} iterations")
            break
        
        # Apply all swaps from chains (pass pre-computed matches to avoid redundant search)
        hypothesis_list = link_cross_boundary_neighbors(hypothesis_list, cross_boundary_matches)
        
        # Re-link after swaps to update neighbor relationships
        hypothesis_list = map_up_text.link_hypothesis_objects_by_context(hypothesis_list)
        
        # Check if we made progress
        current_pending_count = sum(1 for h in hypothesis_list if is_pending_word(h))
        
        if current_pending_count == prev_pending_count:
            print(f"[Cross-Boundary Matching] Converged after {iteration + 1} iterations (no change in PENDING count)")
            break
        
        print(f"[Cross-Boundary Matching] Iteration {iteration + 1}: PENDING words: {prev_pending_count} → {current_pending_count} ({current_pending_count - prev_pending_count:+d})")
        prev_pending_count = current_pending_count
    
    return hypothesis_list
