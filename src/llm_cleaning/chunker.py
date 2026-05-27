"""
Chunking module for splitting OCR text into processable chunks with overlap.
"""

import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Chunk:
    """Represents a chunk of OCR text."""
    id: int
    text: str
    start_line: int
    end_line: int
    overlap_prefix: str = ""
    is_table: bool = False


# Common abbreviations that should not trigger sentence end detection
ABBREVIATION_DENYLIST = {
    "mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.", "st.", "vs.",
    "u.s.", "u.k.", "e.g.", "i.e.", "jan.", "feb.", "mar.", "apr.",
    "may.", "jun.", "jul.", "aug.", "sep.", "sept.", "oct.", "nov.", "dec.",
    "etc.", "inc.", "ltd.", "corp.", "co.", "no.", "vol.", "pp.", "p.",
    "a.m.", "p.m.", "am.", "pm.", "serv't", "gen.", "col.", "coln."
}


def is_likely_sentence_end(line: str, next_line: Optional[str] = None) -> bool:
    """
    Heuristic to determine if a line likely ends a sentence.
    
    Args:
        line: Current line to check
        next_line: Next line (if available)
    
    Returns:
        True if line likely ends a sentence
    """
    if not line.strip():
        return False
    
    # Check if line ends with sentence-ending punctuation
    line_stripped = line.strip()
    if not re.search(r'[.?!]$', line_stripped):
        return False
    
    # Check for decimal numbers (e.g., "3.14" should not be sentence end)
    if re.search(r'\d+\.\d+$', line_stripped):
        return False
    
    # Check for common abbreviations (case-insensitive)
    line_lower = line_stripped.lower()
    for abbrev in ABBREVIATION_DENYLIST:
        if line_lower.endswith(abbrev):
            return False
    
    # If next line is available, check if it starts with uppercase or quote/paren
    if next_line is not None:
        next_stripped = next_line.strip()
        if next_stripped:
            first_char = next_stripped[0]
            if first_char.isupper() or first_char in ('"', "'", '(', '['):
                return True
    
    # If no next line, assume sentence end if punctuation is present
    return True


def estimate_word_count(text: str) -> int:
    """Estimate word count using regex."""
    words = re.findall(r"\b[\w']+\b", text)
    return len(words)


def is_table_line(line: str) -> bool:
    """Heuristic: short, contains digits/punctuation typical of rows."""
    s = line.strip()
    if not s:
        return False
    if len(s) > 60:
        return False
    has_digit = bool(re.search(r"\d", s))
    has_punct = bool(re.search(r"[|,.;:/]", s))
    many_spaces = s.count("  ") >= 1
    return (has_digit or has_punct or many_spaces)


def split_chunks_for_tables(
    chunks: List[Chunk],
    table_min_lines: int = 3
) -> List[Chunk]:
    """
    Post-process chunks: if a chunk mixes prose and a table-like block,
    split so the table lines live in their own chunk.
    """
    new_chunks: List[Chunk] = []
    next_id = 0

    for chunk in chunks:
        lines = chunk.text.split("\n")
        n = len(lines)
        i = 0
        while i < n:
            if is_table_line(lines[i]):
                start = i
                while i < n and is_table_line(lines[i]):
                    i += 1
                end = i  # exclusive
                run_len = end - start
                if run_len >= table_min_lines:
                    # emit pre-table if any (and non-empty)
                    if start > 0:
                        pre_lines = lines[:start]
                        pre_text = "\n".join(pre_lines).strip()
                        if pre_text:  # Only create chunk if it has content
                            new_chunks.append(
                                Chunk(
                                    id=next_id,
                                    text="\n".join(pre_lines),
                                    start_line=chunk.start_line,
                                    end_line=chunk.start_line + start - 1,
                                    overlap_prefix="",
                                    is_table=False,
                                )
                            )
                            next_id += 1
                    # emit table chunk
                    table_lines = lines[start:end]
                    new_chunks.append(
                        Chunk(
                            id=next_id,
                            text="\n".join(table_lines),
                            start_line=chunk.start_line + start,
                            end_line=chunk.start_line + end - 1,
                            overlap_prefix="",
                            is_table=True,
                        )
                    )
                    next_id += 1
                    # reset lines to post-table
                    lines = lines[end:]
                    n = len(lines)
                    i = 0
                    continue
            i += 1
        # remaining lines (if any) that are not part of a table run
        if lines:
            remaining_text = "\n".join(lines).strip()
            if remaining_text:  # Only create chunk if it has content
                new_chunks.append(
                    Chunk(
                        id=next_id,
                        text="\n".join(lines),
                        start_line=chunk.start_line + (chunk.end_line - len(lines) + 1),
                        end_line=chunk.end_line,
                        overlap_prefix=chunk.overlap_prefix,
                        is_table=False,
                    )
                )
                next_id += 1

    return new_chunks


def make_chunks(
    ocr_text: str,
    min_tokens: int = 150,
    max_tokens: int = 600,
    overlap_lines: int = 2
) -> List[Chunk]:
    """
    Split OCR text into chunks with overlap.
    
    Args:
        ocr_text: Raw OCR text to chunk
        min_tokens: Minimum word count per chunk
        max_tokens: Maximum word count per chunk
        overlap_lines: Number of lines to overlap between chunks
    
    Returns:
        List of Chunk objects
    """
    lines = ocr_text.split('\n')
    chunks = []
    chunk_id = 0
    current_start = 0
    
    while current_start < len(lines):
        # Accumulate lines for current chunk
        current_lines = []
        current_word_count = 0
        i = current_start
        
        while i < len(lines):
            line = lines[i]
            current_lines.append(line)
            line_word_count = estimate_word_count(line)
            current_word_count += line_word_count
            
            # Check if we should break here
            should_break = False
            
            # Break if we exceed max_tokens
            if current_word_count >= max_tokens:
                should_break = True
            # Break if we hit min_tokens AND likely sentence end
            elif current_word_count >= min_tokens:
                next_line = lines[i + 1] if i + 1 < len(lines) else None
                if is_likely_sentence_end(line, next_line):
                    should_break = True
            
            if should_break:
                break
            
            i += 1
        
        # Create chunk text
        chunk_text = '\n'.join(current_lines)
        end_line = current_start + len(current_lines) - 1
        
        # Determine overlap prefix for next chunk
        overlap_prefix = ""
        if overlap_lines > 0 and end_line + 1 < len(lines):
            overlap_start = max(current_start, end_line - overlap_lines + 1)
            overlap_end = end_line
            if overlap_start <= overlap_end:
                overlap_lines_list = lines[overlap_start:overlap_end + 1]
                overlap_prefix = '\n'.join(overlap_lines_list)
        
        chunk = Chunk(
            id=chunk_id,
            text=chunk_text,
            start_line=current_start,
            end_line=end_line,
            overlap_prefix=overlap_prefix,
            is_table=False
        )
        chunks.append(chunk)
        
        # Move to next chunk start (with overlap)
        if overlap_lines > 0 and end_line + 1 < len(lines):
            # Start next chunk from overlap_lines before the end of current chunk
            # This ensures the next chunk includes the overlap
            current_start = max(current_start + 1, end_line - overlap_lines + 1)
        else:
            current_start = end_line + 1
        
        chunk_id += 1
        
        # Safety: prevent infinite loop
        if current_start >= len(lines):
            break
    
    return chunks


def make_single_chunk(ocr_text: str) -> List[Chunk]:
    """Treat the entire text as one chunk (e.g. one page = one chunk for page-by-page processing)."""
    lines = ocr_text.split("\n")
    n = len(lines)
    return [
        Chunk(
            id=0,
            text=ocr_text,
            start_line=0,
            end_line=max(0, n - 1),
            overlap_prefix="",
            is_table=False,
        )
    ]

