"""
Prompt templates for OCR refinement.
"""

from typing import Optional


def get_system_prompt() -> str:
    """Get the system prompt for OCR correction."""
    return """You are an OCR correction engine. Clean the text. Do not paraphrase. Remove line-break hyphens (join words broken across lines into one word).

What to do:
- Actively correct every clear OCR error. Do not leave obviously wrong text unchanged.
- Fix character-level errors: e.g. "rn" -> "m", "0" -> "O", "l" -> "I", "S10" -> "$10", "teh" -> "the", "Cyhemehics" -> "Cybernetics", "Prryt83" -> "Progress", "Sysfas" -> "Systems", garbled letters in titles/headers (e.g. "VI76 ta" -> "Vol 76 to" when context is journal/series).
- Remove hyphens that are only from line breaks: join the two parts into one word (e.g. "re-\nsearch" -> "research"). Keep hyphens that are part of compound words (e.g. "well-known").
- Fix spacing: collapse multiple spaces, fix missing space after punctuation.
- Fix stray scan artifacts: odd symbols (¥, |), asterisks, unmatched quotes, that are clearly not part of the intended text.
- Preserve meaning, vocabulary, and structure. Reordering lines/paragraphs is allowed if the OCR order is wrong; do not paraphrase.
- If a word is clearly wrong from context but you are unsure of the exact correction, use your best guess or mark [[unclear]] only when you truly cannot infer it.

Constraints:
- Do not invent content that is not in or strongly suggested by the OCR text.
- Do not add sentences, change meaning, or make purely stylistic/grammatical edits (e.g. do not change "it now making" to "is now being made" unless the OCR suggests it).
- Output only the corrected text—no commentary or notes.
- If the chunk is loose words (OCR word soup), fix obvious errors and keep the word sequence; do not invent grammar.

Output format (strict):
DECISION: STOP|CONTINUE
TEXT:
<your corrected text here>

DECISION: Use STOP when the text is correct or further change would be guesswork. Use CONTINUE when you can still fix clear OCR errors."""


def get_user_prompt(
    ocr_chunk: str,
    current_text: str,
    word_count_ocr: int,
    char_count_ocr: int,
    wc_tolerance: float = 0.15,
    cc_tolerance: float = 0.15,
    year: Optional[int] = None,
    month: Optional[int] = None,
    location: Optional[str] = None,
    document_type: Optional[str] = None,
    is_table: bool = False
    ) -> str:
    """
    Generate user prompt for OCR refinement iteration.
    
    Args:
        ocr_chunk: Original OCR text chunk
        current_text: Current refined text (for iterative refinement)
        word_count_ocr: Word count of OCR chunk
        char_count_ocr: Character count of OCR chunk
        wc_tolerance: Word count tolerance (e.g., 0.15 = ±15%)
        cc_tolerance: Character count tolerance (e.g., 0.15 = ±15%)
        year: Year of document (optional)
        month: Month of document (optional)
        location: Location of publication (optional)
        document_type: Type of document (optional)
    Returns:
        Formatted user prompt
    """
    prompt_parts = []
    
    # Document metadata
    if year or month or location or document_type:
        metadata = []
        if year:
            metadata.append(f"Year: {year}")
        if month:
            metadata.append(f"Month: {month}")
        if location:
            metadata.append(f"Location: {location}")
        if document_type:
            metadata.append(f"Document type: {document_type}")
        prompt_parts.append("Document context:\n" + ", ".join(metadata) + "\n")
    
    # OCR chunk info
    prompt_parts.append(f"OCR chunk statistics:")
    prompt_parts.append(f"- Word count: {word_count_ocr}")
    prompt_parts.append(f"- Character count: {char_count_ocr}")
    prompt_parts.append(f"- Word count tolerance: ±{wc_tolerance*100:.0f}%")
    prompt_parts.append(f"- Character count tolerance: ±{cc_tolerance*100:.0f}%")
    prompt_parts.append("")
    
    # Instructions
    prompt_parts.append("Instructions:")
    prompt_parts.append("- Clean the text. Do not paraphrase. Remove line-break hyphens (join words broken across lines into one word).")
    prompt_parts.append("- Correct every clear OCR error. Fix misread words from context, character swaps, stray symbols, and spacing.")
    prompt_parts.append("- Stay within the word and character count tolerances above; small changes in count from corrections are acceptable.")
    prompt_parts.append("- If you cannot improve further without guessing, return DECISION: STOP. Otherwise return DECISION: CONTINUE.")
    prompt_parts.append("- Do not add content that is not in the OCR. Output only the corrected text—no commentary.")
    prompt_parts.append("- The OCR is from scanned documents (e.g. journal articles). Clean stray special characters (asterisks, ¥, |, unmatched quotes) that are scan artifacts.")
    prompt_parts.append("- Fix obvious number/currency misreads (e.g. '010 00' or 'S10 00' in context -> '$10.00').")
    if is_table:
        prompt_parts.append("- This chunk is tabular/list-like. Preserve line breaks and relative spacing; treat each input line as a row.")
        prompt_parts.append("- Do not merge or reorder lines; only fix OCR errors inside each line.")
        prompt_parts.append("- Do not add or drop lines; keep the layout intact.")
    prompt_parts.append("")
    
    # OCR chunk
    prompt_parts.append("OCR_CHUNK:")
    prompt_parts.append("---")
    prompt_parts.append(ocr_chunk)
    prompt_parts.append("---")
    prompt_parts.append("")
    
    # Current text (for iterative refinement)
    prompt_parts.append("CURRENT_TEXT (from previous iteration):")
    prompt_parts.append("---")
    prompt_parts.append(current_text)
    prompt_parts.append("---")
    prompt_parts.append("")
    
    prompt_parts.append("Provide your refined text in the required format:")
    prompt_parts.append("DECISION: STOP|CONTINUE")
    prompt_parts.append("TEXT:")
    prompt_parts.append("<your text>")
    
    return "\n".join(prompt_parts)


def get_retry_user_prompt_suffix() -> str:
    """Get additional prompt text for retry attempts after validation failure."""
    return "\n\nWARNING: Your last output failed validation due to length drift or novel tokens. Be more conservative; do not add content. Stay strictly within the tolerance limits and do not introduce words that are not present in the OCR text."
    