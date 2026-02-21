"""
LLM token type and creation from clean text.

Builds lists of LLMToken from plain or tagged clean text. When the LLM adds
layout tags (e.g. [ARTICLE 1 TITLE]), they are stripped for mapping and
attached per-token so the aligned ALTO can carry LAYOUT on each String.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import layout_tags
import text_utils


@dataclass
class LLMToken:
    """
    A token (actually a word) from the clean text produced by the LLM.
    """
    word: str = ""
    word_normalized: str = ""
    matched: bool = False
    article_name: Optional[str] = None
    page_number: Optional[int] = None
    w_before: Optional["LLMToken"] = None
    w_after: Optional["LLMToken"] = None
    layout_tag: Optional[str] = None  # e.g. "article_1_title" for ALTO LAYOUT attribute


def create_LLM_element_list(plain_text: str) -> List[LLMToken]:
    """
    Create a list of LLMTokens from plain text (no tag parsing).
    Sets word, word_normalized, w_before, w_after for each token.
    Tokenization matches layout_tags (split on whitespace).
    """
    tokens = plain_text.split()
    llm_elements: List[LLMToken] = []

    i = 0
    while i < len(tokens):
        word = tokens[i]
        word_normalized = text_utils.normalize_for_matching(word)
        llm_element_before = llm_elements[i - 1] if i - 1 >= 0 and len(llm_elements) > 0 else None

        llm_element = LLMToken(word=word, word_normalized=word_normalized, w_before=llm_element_before)
        llm_elements.append(llm_element)
        if i > 0 and len(llm_elements) > 1:
            llm_elements[i - 1].w_after = llm_element
        i += 1

    if len(llm_elements) > 0:
        llm_elements[-1].w_after = None

    return llm_elements


def prepare_llm_elements(raw_clean_text: str) -> Tuple[str, List[LLMToken]]:
    """
    Parse layout tags from raw clean text, tokenize, and attach layout_tag to each LLMToken.

    Use the returned plain_text for vocab and the returned llm_elements for the mapping pipeline.
    When the LLM output has no tags, layout_tag is None for every token.
    """
    plain_text, layout_tags_by_index = layout_tags.parse_layout_tags(raw_clean_text)
    llm_elements = create_LLM_element_list(plain_text)
    for i, tag in enumerate(layout_tags_by_index):
        if i < len(llm_elements):
            llm_elements[i].layout_tag = tag
    return (plain_text, llm_elements)
