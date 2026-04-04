"""
Fuzzy matching utilities for OCR text alignment.

Provides functions for fuzzy string matching using RapidFuzz library.
"""

from rapidfuzz import fuzz, process
from typing import List, Tuple, Optional, Dict, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from map_up_text import TokenCandidate, LLMToken
else:
    # Import at runtime to avoid circular imports
    # These will be imported when the function is called
    TokenCandidate = None


def fuzzy_match_rapid(word: str, vocab: set[str], cutoff: float = 90.0, limit: Optional[int] = None) -> List[Tuple[str, float]]:
    """
    Use a dedicated fuzzy library to find best word matches
    cutoff is in [0, 100]
    
    Returns:
    all strong matches, sorted by score
    """
    # process.extract returns (match, score, index); we return (match, score) only
    raw = process.extract(query=word, choices=vocab, scorer=fuzz.ratio, score_cutoff=cutoff, limit=limit)
    return [(m, s) for m, s, _ in raw]


def best_fuzzy_match_rapid(word: str, vocab: set[str], cutoff: float = 90.0) -> Union['TokenCandidate', None]:
    """
    Use a dedicated fuzzy library to find best word matches
    cutoff is in [0, 100]
    
    Returns:
    best_match, score or None if no match found
    """
    # Import at runtime to avoid circular imports
    from map_up_text import TokenCandidate
    
    # process.extractOne returns (match, score, index)
    result = process.extractOne(
        query=word,
        choices=vocab,
        scorer=fuzz.ratio,
        score_cutoff=cutoff
    )

    if result is None:
        return None

    match, score, index = result
    # Note: This function creates TokenCandidate with string instead of StringWord - may need redesign
    # For now, using empty list as alto_words requires List[XMLOBJ.StringWord]
    return TokenCandidate(clean_form=match, kind="word", alto_words=[], fuzzy_score=float(score))  # type: ignore[reportUnknownReturnType]


def create_llm_word_lookup(llm_elements: List['LLMToken']) -> Dict[str, List['LLMToken']]:
    """
    Create a lookup dictionary mapping normalized words to LLMToken lists.
    
    Args:
        llm_elements: List of LLMToken objects
    
    Returns:
        Dictionary: normalized_word -> List[LLMToken]
    """
    llm_word_lookup: Dict[str, List['LLMToken']] = {}
    for llm_element in llm_elements:
        if llm_element.word_normalized not in llm_word_lookup:
            llm_word_lookup[llm_element.word_normalized] = []
        llm_word_lookup[llm_element.word_normalized].append(llm_element)
    return llm_word_lookup


def check_individual_word_match(
    normalized_word: str,
    clean_vocab: set[str],
    cutoff: float = 85.0
) -> Optional[Tuple[str, float]]:
    """
    Check if a word matches individually in the vocabulary.
    
    Args:
        normalized_word: Normalized word to check
        clean_vocab: Set of normalized vocabulary words
        cutoff: Minimum fuzzy match score (default: 85.0)
    
    Returns:
        Tuple of (matched_word, score) if match found, None otherwise
    """
    if normalized_word:
        if normalized_word in clean_vocab:
            return (normalized_word, 100.0)
        else:
            candidate = best_fuzzy_match_rapid(normalized_word, clean_vocab, cutoff=cutoff)
            if candidate:
                return (candidate.clean_form, candidate.fuzzy_score)
    return None


def validate_context_scores(
    before_score: float,
    after_score: float,
    avg_score: float,
    threshold: float = 70.0
) -> bool:
    """
    Check if context scores meet minimum requirements.
    
    Args:
        before_score: Context score for before word
        after_score: Context score for after word
        avg_score: Average context score
        threshold: Minimum score threshold (default: 70.0)
    
    Returns:
        True if scores are acceptable, False otherwise
    """
    return (avg_score > threshold) or (before_score > threshold) or (after_score > threshold)


def should_combine_words(
    individual_w1_score: float,
    individual_w2_score: float,
    combined_score: float,
    individual_threshold: float = 85.0,
    improvement_threshold: float = 5.0,
    w1_length: Optional[int] = None,
    w2_length: Optional[int] = None
) -> bool:
    """
    Determine if two words should be combined based on score comparison.
    
    Args:
        individual_w1_score: Score for first word individually
        individual_w2_score: Score for second word individually
        combined_score: Score for combined words
        individual_threshold: Threshold below which individual matches are poor (default: 85.0)
        improvement_threshold: Minimum improvement required for combination (default: 5.0)
        w1_length: Length of first word (optional, used to penalize combining short words)
        w2_length: Length of second word (optional, used to penalize combining short words)
    
    Returns:
        True if words should be combined, False otherwise
    """
    best_individual_score = max(individual_w1_score, individual_w2_score)
    worst_individual_score = min(individual_w1_score, individual_w2_score)
    
    # Penalize combining short words that have reasonable individual matches
    # Short words (≤2 chars) with decent matches (≥75%) should not be combined
    if w1_length is not None and w1_length <= 2:
        if individual_w1_score >= 75.0:
            # Short word has reasonable match - don't combine unless combined is MUCH better
            if combined_score < individual_w1_score + 15.0:  # Need 15% improvement, not just 5%
                return False
    if w2_length is not None and w2_length <= 2:
        if individual_w2_score >= 75.0:
            # Short word has reasonable match - don't combine unless combined is MUCH better
            if combined_score < individual_w2_score + 15.0:  # Need 15% improvement, not just 5%
                return False
    
    if best_individual_score < individual_threshold:
        # Individual words don't match well, combining is reasonable
        return True
    elif combined_score >= best_individual_score + improvement_threshold:
        # Combined match is significantly better (at least improvement_threshold better)
        return True
    
    return False

