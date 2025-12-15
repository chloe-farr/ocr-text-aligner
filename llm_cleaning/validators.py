"""
Validation gates for OCR refinement output.
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Set, Optional

from rapidfuzz import fuzz


# Common stopwords that are allowed as novel tokens (glue words)
STOPWORD_ALLOWLIST = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
    "been", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "must", "can", "this", "that",
    "these", "those", "i", "you", "he", "she", "it", "we", "they"
}


@dataclass
class ValidationResult:
    """Result of validation check."""
    ok: bool
    reasons: List[str]
    stats: Dict[str, float | int]


def normalize_counts(text: str) -> str:
    """
    Normalize text for counting purposes.
    
    Args:
        text: Input text
    
    Returns:
        Normalized text
    """
    # Normalize newlines
    text = re.sub(r'\r\n|\r', '\n', text)
    # Collapse multiple whitespace to single space
    text = re.sub(r'[ \t]+', ' ', text)
    # Strip leading/trailing whitespace
    text = text.strip()
    return text


def count_words(text: str) -> int:
    """Count words using regex."""
    words = re.findall(r"\b[\w']+\b", text)
    return len(words)


def count_chars(text: str) -> int:
    """Count characters (excluding only newlines for normalization)."""
    return len(text.replace('\n', ' '))


def tokenize_lowercase(text: str) -> Set[str]:
    """
    Tokenize text into lowercase word tokens.
    
    Args:
        text: Input text
    
    Returns:
        Set of lowercase word tokens
    """
    tokens = re.findall(r'\b\w+\b', text.lower())
    return set(tokens)


def validate_length_ratios(
    output_text: str,
    ocr_text: str,
    wc_tolerance: float = 0.15,
    cc_tolerance: float = 0.15
) -> ValidationResult:
    """
    Validate that output length ratios are within tolerance.
    
    Args:
        output_text: Refined output text
        ocr_text: Original OCR text
        wc_tolerance: Word count tolerance (e.g., 0.15 = ±15%)
        cc_tolerance: Character count tolerance (e.g., 0.15 = ±15%)
    
    Returns:
        ValidationResult
    """
    reasons = []
    stats = {}
    
    # Normalize both texts
    norm_output = normalize_counts(output_text)
    norm_ocr = normalize_counts(ocr_text)
    
    # Count words and characters
    wc_output = count_words(norm_output)
    wc_ocr = count_words(norm_ocr)
    cc_output = count_chars(norm_output)
    cc_ocr = count_chars(norm_ocr)
    
    stats['word_count_output'] = wc_output
    stats['word_count_ocr'] = wc_ocr
    stats['char_count_output'] = cc_output
    stats['char_count_ocr'] = cc_ocr
    
    # Calculate ratios
    if wc_ocr > 0:
        wc_ratio = wc_output / wc_ocr
        stats['word_count_ratio'] = wc_ratio
        if wc_ratio < (1 - wc_tolerance) or wc_ratio > (1 + wc_tolerance):
            reasons.append(
                f"Word count ratio {wc_ratio:.3f} outside tolerance "
                f"[{1 - wc_tolerance:.3f}, {1 + wc_tolerance:.3f}]"
            )
    else:
        stats['word_count_ratio'] = 0.0
        if wc_output > 0:
            reasons.append("OCR has 0 words but output has words")
    
    if cc_ocr > 0:
        cc_ratio = cc_output / cc_ocr
        stats['char_count_ratio'] = cc_ratio
        if cc_ratio < (1 - cc_tolerance) or cc_ratio > (1 + cc_tolerance):
            reasons.append(
                f"Character count ratio {cc_ratio:.3f} outside tolerance "
                f"[{1 - cc_tolerance:.3f}, {1 + cc_tolerance:.3f}]"
            )
    else:
        stats['char_count_ratio'] = 0.0
        if cc_output > 0:
            reasons.append("OCR has 0 characters but output has characters")
    
    ok = len(reasons) == 0
    return ValidationResult(ok=ok, reasons=reasons, stats=stats)


def validate_novel_tokens(
    output_text: str,
    ocr_text: str,
    max_novel_token_ratio: float = 0.12,
    stopword_allowlist: Optional[Set[str]] = None
) -> ValidationResult:
    """
    Validate that novel token ratio is within limits.
    
    Args:
        output_text: Refined output text
        ocr_text: Original OCR text
        max_novel_token_ratio: Maximum allowed ratio of novel tokens
        stopword_allowlist: Set of stopwords to exclude from novel token check
    
    Returns:
        ValidationResult
    """
    reasons = []
    stats = {}
    
    if stopword_allowlist is None:
        stopword_allowlist = STOPWORD_ALLOWLIST
    
    # Tokenize both texts
    output_tokens = tokenize_lowercase(output_text)
    ocr_tokens = tokenize_lowercase(ocr_text)
    
    stats['output_token_count'] = len(output_tokens)
    stats['ocr_token_count'] = len(ocr_tokens)
    
    # Find novel tokens (in output but not in OCR)
    novel_tokens = output_tokens - ocr_tokens
    
    # Filter out stopwords and purely numeric tokens
    filtered_novel = {
        token for token in novel_tokens
        if token not in stopword_allowlist and not token.isdigit()
    }
    
    stats['novel_token_count'] = len(novel_tokens)
    stats['filtered_novel_token_count'] = len(filtered_novel)
    
    # Calculate ratio
    if len(output_tokens) > 0:
        novel_ratio = len(filtered_novel) / len(output_tokens)
        stats['novel_token_ratio'] = novel_ratio
        
        if novel_ratio > max_novel_token_ratio:
            reasons.append(
                f"Novel token ratio {novel_ratio:.3f} exceeds maximum "
                f"{max_novel_token_ratio:.3f}"
            )
            # Include some example novel tokens for debugging
            example_novels = list(filtered_novel)[:5]
            if example_novels:
                reasons.append(f"Example novel tokens: {', '.join(example_novels)}")
    else:
        stats['novel_token_ratio'] = 0.0
    
    ok = len(reasons) == 0
    return ValidationResult(ok=ok, reasons=reasons, stats=stats)


def validate_fuzzy_similarity(
    output_text: str,
    previous_text: str,
    min_fuzzy_ratio: float = 50.0
) -> ValidationResult:
    """
    Optional fuzzy similarity check to catch catastrophic rewrites.
    
    Args:
        output_text: Current output text
        previous_text: Previous accepted output text
        min_fuzzy_ratio: Minimum fuzzy ratio (0-100)
    
    Returns:
        ValidationResult
    """
    reasons = []
    stats = {}
    
    norm_output = normalize_counts(output_text)
    norm_previous = normalize_counts(previous_text)
    
    # Calculate fuzzy ratio
    ratio = fuzz.ratio(norm_output, norm_previous)
    stats['fuzzy_ratio'] = ratio
    
    if ratio < min_fuzzy_ratio:
        reasons.append(
            f"Fuzzy similarity {ratio:.1f} below minimum {min_fuzzy_ratio:.1f}"
        )
    
    ok = len(reasons) == 0
    return ValidationResult(ok=ok, reasons=reasons, stats=stats)


def validate_all(
    output_text: str,
    ocr_text: str,
    wc_tolerance: float = 0.15,
    cc_tolerance: float = 0.15,
    max_novel_token_ratio: float = 0.12,
    previous_text: Optional[str] = None,
    min_fuzzy_ratio: Optional[float] = None,
    stopword_allowlist: Optional[Set[str]] = None
) -> ValidationResult:
    """
    Run all validation gates.
    
    Args:
        output_text: Refined output text
        ocr_text: Original OCR text
        wc_tolerance: Word count tolerance
        cc_tolerance: Character count tolerance
        max_novel_token_ratio: Maximum novel token ratio
        previous_text: Previous accepted text (for fuzzy check)
        min_fuzzy_ratio: Minimum fuzzy ratio (None to skip)
        stopword_allowlist: Stopwords to exclude from novel token check
    
    Returns:
        Combined ValidationResult
    """
    all_reasons = []
    all_stats = {}
    
    # Length validation
    length_result = validate_length_ratios(
        output_text, ocr_text, wc_tolerance, cc_tolerance
    )
    all_reasons.extend(length_result.reasons)
    all_stats.update(length_result.stats)
    
    # Novel token validation
    novel_result = validate_novel_tokens(
        output_text, ocr_text, max_novel_token_ratio, stopword_allowlist
    )
    all_reasons.extend(novel_result.reasons)
    all_stats.update(novel_result.stats)
    
    # Optional fuzzy validation
    if previous_text is not None and min_fuzzy_ratio is not None:
        fuzzy_result = validate_fuzzy_similarity(
            output_text, previous_text, min_fuzzy_ratio
        )
        all_reasons.extend(fuzzy_result.reasons)
        all_stats.update(fuzzy_result.stats)
    
    ok = len(all_reasons) == 0
    return ValidationResult(ok=ok, reasons=all_reasons, stats=all_stats)

