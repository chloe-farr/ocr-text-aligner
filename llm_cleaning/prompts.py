"""
Prompt templates for OCR refinement.
"""

from typing import Optional


def get_system_prompt() -> str:
    """Get the system prompt for OCR correction."""
    return """You are an OCR correction engine. Your task is to refine OCR text while preserving its original meaning and structure.

Rules:
- Use the OCR_CHUNK as evidence; do not invent missing content.
- Reordering is allowed (e.g., fixing paragraph order), but paraphrasing is not.
- If uncertain about a word or phrase, keep the OCR token or mark it as [[unclear]].
- Preserve the original vocabulary and terminology.
- Correct obvious OCR errors (e.g., "rn" -> "m", "0" -> "O" in context).
- Fix spacing and punctuation issues. Do not update punctuation if it seems merely out of style.
- Do not make stylistic or grammatical changes that are not suggested by the OCR text. For example, do not change `it  now  making` to `is now being made` unless the OCR text suggests it.
- Do not add content that is not suggested by the OCR text.
- Do not include any commentary, notes, or explanations in the output—only the corrected text.
- If the chunk is just loose words (e.g., OCR word soup), do not try to create grammatical sentences; only fix obvious OCR errors and keep the word-level sequence.

Output format (strict):
DECISION: STOP|CONTINUE
TEXT:
<your corrected text here>

DECISION indicates whether you believe further refinement is needed:
- STOP: The text is correct or cannot be improved without guessing.
- CONTINUE: You can make additional improvements in the next iteration."""


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
    prompt_parts.append("- Refine the text to correct OCR errors while staying within the tolerance limits.")
    prompt_parts.append("- Your output word count must be within the specified tolerance of the OCR word count.")
    prompt_parts.append("- If you cannot improve the text without guessing or exceeding tolerances, return DECISION: STOP.")
    prompt_parts.append("- Do not add content that is not present in the OCR text.")
    prompt_parts.append("- Do not include commentary, rationale, or notes—only the corrected text.")
    prompt_parts.append("- The OCR is from scanned newspaper microfiche. You may clean any stray special characters, such as asterisks, unmatched quotes, etc. that are likely to be transcription errors due to smudges, bleed, etc.")
    prompt_parts.append("- Make your best guess at where currency symbols belong. If the text says 'per anunum, ... 010 00' or 'per anunum, ... S10 00' then it is likely to actually be 'per anunum, ... $10.00'.")
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

