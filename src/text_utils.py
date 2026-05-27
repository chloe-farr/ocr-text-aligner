"""
Text processing utilities for OCR text alignment.
"""

import re
import html
import unicodedata
import xml_obj as XMLOBJ

HY_PHENS = ("-", "-", "—", "--")  # plain hyphen + common variants

def decode_html_entities(text: str) -> str:
    """
    Decode HTML entities in text to Unicode characters.
    This is needed because ALTO XML may contain HTML entities (e.g., &amp;, &quot;)
    while the clean text has Unicode characters.
    
    Args:
        text (str): Text that may contain HTML entities
        
    Returns:
        str: Text with HTML entities decoded to Unicode
        
    Example:
        >>> decode_html_entities("&amp;")
        '&'
        >>> decode_html_entities("&quot;hello&quot;")
        '"hello"'
    """
    return html.unescape(text)

def normalize_for_matching(word: str) -> str:
    """
    Strips a string of all characters aside from Unicode letters, digits, and hyphens.
    Preserves hyphens (including trailing hyphens) to maintain word-wrapping information.
    Works for any language/script — ä, é, ñ, ü, etc. are preserved.

    Args:
        word (str): word to clean.

    Returns:
        word (str): word without special characters other than hyphens.

    Example:
    >>> normalize_for_matching("unco-")
    'unco-'

    >>> normalize_for_matching("unconscious.")
    'unconscious'

    >>> normalize_for_matching("unco--nscious")
    'unco--nscious'

    >>> normalize_for_matching("unconscious:")
    'unconscious'

    >>> normalize_for_matching("anti-aircraft")
    'antiaircraft'

    >>> normalize_for_matching("Ärger")
    'ärger'

    >>> normalize_for_matching("naïve.")
    'naïve'
    """
    s = word.lower()
    s = "".join(c for c in s if unicodedata.category(c).startswith(("L", "N")) or c in "-–—")
    return s.strip()

def is_hyphenish(word: XMLOBJ.StringWord) -> bool:
    """
    Determines if a given string contains a hyphen or hyphen-variant.
    
    Args:
        word (str): word to assess.

    Returns:
        bool: True if contains hyphen, False if no hyphen.

    Example:
    >>> is_hyphenish("unco-")
    True

    >>> is_hyphenish("unconscious")
    False

    >>> is_hyphenish("unco--")
    True

    >>> is_hyphenish("unco—")
    True
    """
    # Decode HTML entities before checking for hyphens
    decoded_content = decode_html_entities(word.content)
    return decoded_content.rstrip().endswith(HY_PHENS)

