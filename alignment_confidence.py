"""
Alignment-derived confidence for written OCR outputs (ALTO / hOCR).

Combines Tesseract word confidence (WC, 0–100 on StringWord) with mapping status:
matched + neighbor-consistent, matched-but-pending (weak neighbor graph), or unmatched/error.

This is independent of visualization color rules; consumers can use ALIGNCONF / alignconf
for filtering or QA without changing WC (which remains the engine's OCR confidence).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from map_up_text import TokenHypotheses


def alignment_confidence(hyp: "TokenHypotheses") -> int:
    """
    Return an integer 0–100: higher means more trust in the aligned token and neighborhood.

    Heuristic (documented for downstream users):
    - Unmatched / error: scale WC down strongly (text is still wrong or unresolved).
    - Unmatched but has fuzzy candidates: medium-low (ambiguous).
    - Matched but PENDING (neighbor links inconsistent with chosen LLM token): scale WC by ~0.6.
    - Matched and not pending: use WC as-is (OCR confidence plus successful local alignment).
    """
    wc = getattr(hyp.anchor, "wc", 0) or 0
    wc = max(0, min(100, int(wc)))

    if hyp.chosen_LLM_token is None:
        if hyp.flagged_for_error:
            return max(0, int(round(wc * 0.25)))
        if hyp.candidates:
            return max(0, int(round(wc * 0.45)))
        return max(0, int(round(wc * 0.20)))

    import paragraph_reordering as _pr

    if _pr.is_pending_word(hyp):
        return max(0, int(round(wc * 0.60)))

    return wc
