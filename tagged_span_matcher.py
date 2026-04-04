"""
Tagged Span Matcher (experimental).

Standalone script to experiment with tagged-span-to-ALTO-block matching:
chunk-block fuzzy match and anchor chain. Reads ALTO + tagged cleantext,
prints diagnostics to the terminal. Does not modify the main pipeline or any
existing module.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import List, Optional, Tuple

try:
    from rapidfuzz import fuzz
except ImportError:
    print(
        "Error: rapidfuzz is not installed. Install project dependencies, e.g.:\n"
        "  python3 -m venv venv && source venv/bin/activate  # or venv\\Scripts\\activate on Windows\n"
        "  pip install -r requirements.txt",
        file=sys.stderr,
    )
    sys.exit(1)

import xml_obj
import llm_tokens
import text_utils


# ---------------------------------------------------------------------------
# Span and block text
# ---------------------------------------------------------------------------


@dataclass
class Span:
    """One tagged span: same layout_tag, consecutive token indices."""
    tag: Optional[str]
    start_idx: int
    end_idx: int
    words: List[str]

    @property
    def word_count(self) -> int:
        return len(self.words)

    def chunk_text(self, start: int, end: int) -> str:
        """Words from start (inclusive) to end (exclusive) within this span."""
        return " ".join(self.words[start:end])


def build_spans(llm_elements: List[llm_tokens.LLMToken]) -> List[Span]:
    """Group consecutive tokens with the same layout_tag into spans."""
    spans: List[Span] = []
    i = 0
    while i < len(llm_elements):
        tag = llm_elements[i].layout_tag
        start = i
        words: List[str] = []
        while i < len(llm_elements) and llm_elements[i].layout_tag == tag:
            words.append(llm_elements[i].word)
            i += 1
        spans.append(Span(tag=tag, start_idx=start, end_idx=i, words=words))
    return spans


def get_block_texts(page: xml_obj.Page) -> List[Tuple[str, str]]:
    """
    Return list of (block_id, block_text) in document order.
    Block text = concatenation of all StringWord.content in that block,
    following Page -> TextBlock -> TextLine -> StringWord (StringWord.id = Block#_line#_String#).
    HTML entities in CONTENT are decoded for comparable scoring.
    """
    result: List[Tuple[str, str]] = []
    for block in page.content_elements:
        parts: List[str] = []
        for line in block.content_elements:
            for s in line.content_elements:
                parts.append(text_utils.decode_html_entities(s.content))
        block_text = " ".join(parts)
        result.append((block.id, block_text))
    return result


# ---------------------------------------------------------------------------
# Chunking and scoring
# ---------------------------------------------------------------------------


def chunk_span(span: Span, chunk_size: int) -> List[Tuple[int, int, str]]:
    """Split span into chunks. Returns list of (start, end, text) in word indices within span."""
    chunks: List[Tuple[int, int, str]] = []
    n = len(span.words)
    start = 0
    while start < n:
        end = min(start + chunk_size, n)
        text = span.chunk_text(start, end)
        chunks.append((start, end, text))
        start = end
    return chunks


# When raw match is below this, we don't apply length penalty (avoid preferring
# a short block with weak match over a long block that actually contains the chunk).
_MIN_RAW_FOR_LENGTH_PENALTY = 75.0

# Position bonus: prefer blocks at "expected" document position for this chunk
# (chunk 0 -> earlier blocks, last chunk -> later blocks) so one long block
# doesn't win every chunk when the span is spread across several blocks.
_POSITION_BONUS_MAX = 12.0  # max points added for block at expected position
_POSITION_SLACK = 8         # bonus decays over this many blocks of distance


def _position_bonus(
    chunk_idx: int, num_chunks: int, block_idx: int, num_blocks: int, use_bonus: bool = True
) -> float:
    """Bonus for block being at the expected position for this chunk (document order)."""
    if not use_bonus or num_chunks <= 1 or num_blocks <= 1:
        return 0.0
    expected = (chunk_idx / (num_chunks - 1)) * (num_blocks - 1)
    distance = abs(block_idx - expected)
    return max(0.0, _POSITION_BONUS_MAX - distance * (_POSITION_BONUS_MAX / _POSITION_SLACK))


def score_chunk_block(chunk_text: str, block_text: str, normalize: bool = True) -> float:
    """
    Fuzzy score 0-100: how well does the chunk belong to this block?
    We always ask: how well does the CHUNK (needle) appear in the BLOCK (haystack).
    So we use partial_ratio(chunk, block) — not (shorter, longer). That way a short
    block like "session." gets a low score for chunk "central area, and probably seven."
    instead of a spurious match. When the match is strong (raw >= 75) and the block
    is much longer than the chunk, we apply a length penalty so one long block
    doesn't win every chunk.
    """
    if normalize:
        chunk_text = " ".join(chunk_text.split()).lower()
        block_text = " ".join(block_text.split()).lower()
    if len(block_text) == 0:
        return 0.0
    # Always: chunk = needle, block = haystack (chunk in block)
    raw = fuzz.partial_ratio(chunk_text, block_text)
    if raw < _MIN_RAW_FOR_LENGTH_PENALTY:
        return raw
    # Among strong matches, prefer blocks closer in size to the chunk
    ratio = len(chunk_text) / len(block_text) if len(block_text) > 0 else 1.0
    length_factor = min(1.0, ratio * 6.0)  # no penalty when block <= 6x chunk
    return raw * length_factor


# ---------------------------------------------------------------------------
# Terminal output (tabular + colour)
# ---------------------------------------------------------------------------

# ANSI (subset that works in most terminals)
_RESET = "\033[0m"
_BOLD = "\033[1m"
_CYAN = "\033[36m"   # chunk text (LLM)
_YELLOW = "\033[33m"  # block text (ALTO)
_GREEN = "\033[32m"   # best row
_DIM = "\033[2m"      # headers / borders

# Column widths for tables
_W_BLOCK_ID = 12
_W_SCORE = 6
_W_TEXT = 52


def _c(s: str, code: str, use_color: bool = True) -> str:
    """Wrap string in ANSI code if use_color else return as-is."""
    if not use_color:
        return s
    return code + s + _RESET


def _cell(s: str, width: int, truncate: bool = True) -> str:
    """One table cell: pad right to width; if truncate, shorten with ..."""
    s = s.replace("\n", " ")
    if truncate and len(s) > width:
        s = s[: width - 3] + "..."
    return s + " " * max(0, width - len(s))


def print_section(title: str, char: str = "=", use_color: bool = True) -> None:
    line = char * 60
    print(f"\n{line}")
    print(f" {title}")
    print(f"{line}\n")


def print_subsection(title: str) -> None:
    print(f"\n--- {title} ---\n")


def _truncate(s: str, max_len: int = 120) -> str:
    """Truncate with ... if over max_len."""
    s = s.replace("\n", " ")
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def run_step1(spans: List[Span], span_filter: Optional[int]) -> None:
    """Step 1: Load and list spans."""
    print_section("Step 1: Spans")
    to_show = [spans[span_filter]] if span_filter is not None else spans
    for idx, span in enumerate(to_show):
        global_idx = span_filter if span_filter is not None else idx
        tag_str = span.tag if span.tag else "(untagged)"
        preview = " ".join(span.words[:8])
        if len(span.words) > 8:
            preview += " ..."
        print(f"  Span {global_idx}: {tag_str}")
        print(f"    token range: {span.start_idx}–{span.end_idx}  word count: {span.word_count}")
        print(f"    preview: {preview}")
        print()


def run_step2(spans: List[Span], chunk_size: int, span_filter: Optional[int]) -> None:
    """Step 2: Chunks per span."""
    print_section("Step 2: Chunks per span", char="-")
    to_show = [spans[span_filter]] if span_filter is not None else spans
    for idx, span in enumerate(to_show):
        global_idx = span_filter if span_filter is not None else idx
        print_subsection(f"Span {global_idx}: {span.tag or '(untagged)'}")
        chunks = chunk_span(span, chunk_size)
        for cidx, (start, end, text) in enumerate(chunks):
            preview = text if len(text) <= 50 else text[:47] + "..."
            print(f"  Chunk {cidx}: words {start}–{end-1}  ({end - start} words)")
            print(f"    \"{preview}\"")
            print()


def run_step3(
    spans: List[Span],
    block_texts: List[Tuple[str, str]],
    chunk_size: int,
    span_filter: Optional[int],
    verbose: bool,
    use_position_bonus: bool = True,
    use_color: bool = True,
) -> None:
    """Step 3: Chunk–block scores. Tabular: Block ID | Score | Chunk text (LLM) | Block text (ALTO)."""
    print_section("Step 3: Chunk–block scores", char="-")
    to_show = [spans[span_filter]] if span_filter is not None else spans
    for idx, span in enumerate(to_show):
        global_idx = span_filter if span_filter is not None else idx
        print_subsection(f"Span {global_idx}: {span.tag or '(untagged)'}")
        chunks = chunk_span(span, chunk_size)
        num_chunks = len(chunks)
        num_blocks = len(block_texts)
        for cidx, (start, end, chunk_text) in enumerate(chunks):
            best_id: Optional[str] = None
            best_score: float = -1.0
            scores: List[Tuple[str, float, str]] = []
            for block_idx, (block_id, block_text) in enumerate(block_texts):
                score = score_chunk_block(chunk_text, block_text) + _position_bonus(
                    cidx, num_chunks, block_idx, num_blocks, use_position_bonus
                )
                scores.append((block_id, score, block_text))
                if score > best_score:
                    best_score = score
                    best_id = block_id
            sorted_scores = sorted(scores, key=lambda x: -x[1])
            n_show = len(sorted_scores) if verbose else 1
            rows = sorted_scores[:n_show] if best_id else []

            # Table header (total width = 4 col widths + 3 internal │)
            _sep_len = _W_BLOCK_ID + _W_SCORE + _W_TEXT * 2 + 3
            sep = _c("─" * _sep_len, _DIM, use_color)
            top = _c("┌", _DIM, use_color) + _c("─" * _W_BLOCK_ID, _DIM, use_color) + _c("┬", _DIM, use_color) + _c("─" * _W_SCORE, _DIM, use_color) + _c("┬", _DIM, use_color) + _c("─" * _W_TEXT, _DIM, use_color) + _c("┬", _DIM, use_color) + _c("─" * _W_TEXT, _DIM, use_color) + _c("┐", _DIM, use_color)
            h_block = _cell("Block ID", _W_BLOCK_ID, truncate=False)
            h_score = _cell("Score", _W_SCORE, truncate=False)
            h_chunk = _cell("Chunk text (LLM)", _W_TEXT, truncate=False)
            h_alto = _cell("Block text (ALTO)", _W_TEXT, truncate=False)
            header = _c("│", _DIM, use_color) + _c(h_block, _BOLD, use_color) + _c("│", _DIM, use_color) + _c(h_score, _BOLD, use_color) + _c("│", _DIM, use_color) + _c(h_chunk, _CYAN, use_color) + _c("│", _DIM, use_color) + _c(h_alto, _YELLOW, use_color) + _c("│", _DIM, use_color)
            mid = _c("├", _DIM, use_color) + sep + _c("┤", _DIM, use_color)
            bot = _c("└", _DIM, use_color) + sep + _c("┘", _DIM, use_color)

            print(f"  Chunk {cidx} (words {start}–{end - 1}):")
            print("  " + top)
            print("  " + header)
            print("  " + mid)
            for bid, sc, btext in rows:
                is_best = bid == best_id
                chunk_cell = _cell(chunk_text, _W_TEXT)
                block_cell = _cell(btext, _W_TEXT)
                row_pre = _c("│", _DIM, use_color)
                if is_best:
                    row_pre += _c(_cell(bid, _W_BLOCK_ID), _GREEN, use_color) + _c("│", _DIM, use_color) + _c(_cell(f"{sc:.1f}", _W_SCORE), _GREEN, use_color) + _c("│", _DIM, use_color) + _c(chunk_cell, _CYAN, use_color) + _c("│", _DIM, use_color) + _c(block_cell, _YELLOW, use_color) + _c("│", _DIM, use_color)
                else:
                    row_pre += _cell(bid, _W_BLOCK_ID) + _c("│", _DIM, use_color) + _cell(f"{sc:.1f}", _W_SCORE) + _c("│", _DIM, use_color) + _c(chunk_cell, _CYAN, use_color) + _c("│", _DIM, use_color) + _c(block_cell, _YELLOW, use_color) + _c("│", _DIM, use_color)
                print("  " + row_pre)
            print("  " + bot)
            print(f"  Best: {best_id} ({best_score:.1f})" if best_id else "  Best: (none)")
            print()
        print()


def run_step4(
    spans: List[Span],
    block_texts: List[Tuple[str, str]],
    chunk_size: int,
    span_filter: Optional[int],
    use_position_bonus: bool = True,
    use_color: bool = True,
) -> None:
    """Step 4: Anchor chain. One table per span: Chunk | Block ID | Score | Chunk text (LLM) | Block text (ALTO)."""
    print_section("Step 4: Anchor chain", char="-")
    to_show = [spans[span_filter]] if span_filter is not None else spans
    _W_CHUNK = 6
    for idx, span in enumerate(to_show):
        global_idx = span_filter if span_filter is not None else idx
        print_subsection(f"Span {global_idx}: {span.tag or '(untagged)'}")
        chunks = chunk_span(span, chunk_size)
        num_chunks = len(chunks)
        num_blocks = len(block_texts)
        chain: List[Tuple[int, str, float, str, str]] = []
        for cidx, (start, end, chunk_text) in enumerate(chunks):
            best_id: Optional[str] = None
            best_score: float = -1.0
            best_block_text: str = ""
            for block_idx, (block_id, block_text) in enumerate(block_texts):
                score = score_chunk_block(chunk_text, block_text) + _position_bonus(
                    cidx, num_chunks, block_idx, num_blocks, use_position_bonus
                )
                if score > best_score:
                    best_score = score
                    best_id = block_id
                    best_block_text = block_text
            if best_id is not None:
                chain.append((cidx, best_id, best_score, chunk_text, best_block_text))
        # One table for the whole span (5 col widths + 4 internal │)
        _sep_len = _W_CHUNK + _W_BLOCK_ID + _W_SCORE + _W_TEXT * 2 + 4
        sep = _c("─" * _sep_len, _DIM, use_color)
        top = _c("┌", _DIM, use_color) + _c("─" * _W_CHUNK, _DIM, use_color) + _c("┬", _DIM, use_color) + _c("─" * _W_BLOCK_ID, _DIM, use_color) + _c("┬", _DIM, use_color) + _c("─" * _W_SCORE, _DIM, use_color) + _c("┬", _DIM, use_color) + _c("─" * _W_TEXT, _DIM, use_color) + _c("┬", _DIM, use_color) + _c("─" * _W_TEXT, _DIM, use_color) + _c("┐", _DIM, use_color)
        h_chunk = _cell("Chunk", _W_CHUNK, truncate=False)
        h_block = _cell("Block ID", _W_BLOCK_ID, truncate=False)
        h_score = _cell("Score", _W_SCORE, truncate=False)
        h_ctext = _cell("Chunk text (LLM)", _W_TEXT, truncate=False)
        h_btext = _cell("Block text (ALTO)", _W_TEXT, truncate=False)
        header = _c("│", _DIM, use_color) + _c(h_chunk, _BOLD, use_color) + _c("│", _DIM, use_color) + _c(h_block, _BOLD, use_color) + _c("│", _DIM, use_color) + _c(h_score, _BOLD, use_color) + _c("│", _DIM, use_color) + _c(h_ctext, _CYAN, use_color) + _c("│", _DIM, use_color) + _c(h_btext, _YELLOW, use_color) + _c("│", _DIM, use_color)
        mid = _c("├", _DIM, use_color) + sep + _c("┤", _DIM, use_color)
        bot = _c("└", _DIM, use_color) + sep + _c("┘", _DIM, use_color)
        print("  " + top)
        print("  " + header)
        print("  " + mid)
        for cidx, bid, sc, ctext, btext in chain:
            row = _c("│", _DIM, use_color) + _cell(str(cidx), _W_CHUNK) + _c("│", _DIM, use_color) + _cell(bid, _W_BLOCK_ID) + _c("│", _DIM, use_color) + _cell(f"{sc:.1f}", _W_SCORE) + _c("│", _DIM, use_color) + _c(_cell(ctext, _W_TEXT), _CYAN, use_color) + _c("│", _DIM, use_color) + _c(_cell(btext, _W_TEXT), _YELLOW, use_color) + _c("│", _DIM, use_color)
            print("  " + row)
        print("  " + bot)
        block_order = []
        seen = set()
        for _, bid, _, _, _ in chain:
            if bid not in seen:
                seen.add(bid)
                block_order.append(bid)
        print(f"  Block run: {', '.join(block_order)}")
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tagged Span Matcher: experiment with chunk–block fuzzy match and anchor chain."
    )
    parser.add_argument("--xml", required=True, help="Path to ALTO XML (single page)")
    parser.add_argument("--clean-text", required=True, help="Path to tagged cleantext file")
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=10,
        help="Words per chunk (default: 10)",
    )
    parser.add_argument(
        "--step",
        type=int,
        default=4,
        choices=(1, 2, 3, 4),
        help="Run only up to this stage (default: 4)",
    )
    parser.add_argument(
        "--span",
        type=int,
        default=None,
        help="Run only the Nth span (0-based); omit to run all spans",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print every chunk×block score; otherwise only best per chunk",
    )
    parser.add_argument(
        "--no-position-bonus",
        action="store_true",
        help="Disable position bonus (chunk 0 → earlier blocks); use content+length only",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colour in table output",
    )
    args = parser.parse_args()
    use_position_bonus = not args.no_position_bonus
    use_color = not args.no_color

    # Load ALTO (first page)
    page = xml_obj.load_first_page(args.xml)
    block_texts = get_block_texts(page)

    # Load tagged cleantext and build spans
    with open(args.clean_text, "r", encoding="utf-8") as f:
        raw_clean_text = f.read()
    _plain_text, llm_elements = llm_tokens.prepare_llm_elements(raw_clean_text)
    spans = build_spans(llm_elements)

    if args.span is not None and (args.span < 0 or args.span >= len(spans)):
        print(f"Error: --span {args.span} is out of range (0–{len(spans) - 1})")
        return

    print_section("Input summary")
    print(f"  ALTO page: {args.xml}")
    print(f"  Blocks: {len(block_texts)}  ({', '.join(bid for bid, _ in block_texts[:5])}{' ...' if len(block_texts) > 5 else ''})")
    print(f"  Spans: {len(spans)}  (tags: {[s.tag for s in spans]})")
    print(f"  Chunk size: {args.chunk_size}  Step: {args.step}  Span filter: {args.span}  Position bonus: {use_position_bonus}")

    if args.step >= 1:
        run_step1(spans, args.span)
    if args.step >= 2:
        run_step2(spans, args.chunk_size, args.span)
    if args.step >= 3:
        run_step3(spans, block_texts, args.chunk_size, args.span, args.verbose, use_position_bonus, use_color)
    if args.step >= 4:
        run_step4(spans, block_texts, args.chunk_size, args.span, use_position_bonus, use_color)

    print_section("Done", char="=")


if __name__ == "__main__":
    main()
