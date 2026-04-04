"""
Parse layout tags from LLM-cleaned text.

Tag format (block markers): a line that is only a tag starts a segment.
Everything after it until the next tag line gets that tag.
Example:
  [ARTICLE 1 TITLE]
  Gaglardi 'Delighted' Bennett Plans To Take House Seat

  [ARTICLE 1 AUTHOR]
  By Michael Maclear HANOI (AP)

Tag syntax: [ROLE] or [ARTICLE N ROLE] with ROLE e.g. TITLE, PARAGRAPH, AUTHOR.
Values are normalized to e.g. article_1_title, article_1_author (lowercase, underscores).
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

# Line that is only optional whitespace, [...] , optional whitespace
TAG_LINE_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")


def _normalize_tag(raw: str) -> str:
    """Normalize tag to lowercase with single underscores (e.g. ARTICLE 1 TITLE -> article_1_title)."""
    s = raw.strip().lower()
    s = re.sub(r"\s+", "_", s)
    return s


def parse_layout_tags(raw_clean_text: str) -> Tuple[str, List[Optional[str]]]:
    """
    Parse tagged clean text and return plain text for mapping plus per-token layout tags.

    Tag lines (e.g. [ARTICLE 1 TITLE]) are stripped from the output. Content is
    tokenized with .split() so indices align with create_LLM_element_list(plain_text).

    Returns:
        (plain_text_for_mapping, layout_tags_by_token_index)
        Tokens with no preceding tag get None.
    """
    layout_tags_by_index: List[Optional[str]] = []
    content_lines: List[str] = []
    current_tag: Optional[str] = None

    for line in raw_clean_text.splitlines():
        m = TAG_LINE_RE.match(line)
        if m:
            current_tag = _normalize_tag(m.group(1))
            continue
        content_lines.append(line)
        # Tokenize this line the same way as create_LLM_element_list (split on whitespace)
        tokens = line.split()
        for _ in tokens:
            layout_tags_by_index.append(current_tag)

    plain_text = "\n".join(content_lines)
    return (plain_text, layout_tags_by_index)
