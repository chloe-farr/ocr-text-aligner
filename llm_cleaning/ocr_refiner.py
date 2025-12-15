"""
Main OCR refinement module with iterative refinement loop and CLI.
"""

import argparse
import json
import logging
import re
import sys
from typing import Dict, List, Optional, Tuple

import requests

from .chunker import Chunk, make_chunks, split_chunks_for_tables
from .prompts import get_system_prompt, get_user_prompt, get_retry_user_prompt_suffix
from .validators import normalize_counts, validate_all

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def is_probable_table(text: str) -> bool:
    """
    Heuristic to detect table/list-like chunks.
    - Many short lines
    - Frequent digits/punctuation
    """
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 5:
        return False

    short_lines = sum(1 for line in lines if len(line.strip()) <= 35)
    digit_lines = sum(1 for line in lines if re.search(r"\d", line))
    punct_lines = sum(1 for line in lines if re.search(r"[|,.;:/]", line))

    return (short_lines / len(lines) >= 0.6) and ((digit_lines + punct_lines) / len(lines) >= 0.4)


def call_ollama_chat(
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    timeout: int = 120
) -> str:
    """
    Call Ollama chat API.
    
    Args:
        model: Model name (e.g., "qwen2.5:14b")
        system_prompt: System prompt
        user_prompt: User prompt
        temperature: Temperature for generation
        timeout: Request timeout in seconds
    
    Returns:
        Response text from model
    
    Raises:
        requests.RequestException: If API call fails
    """
    url = "http://localhost:11434/api/chat"
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "options": {
            "temperature": temperature
        },
        "stream": False
    }
    
    try:
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        return data.get("message", {}).get("content", "")
    except requests.exceptions.RequestException as e:
        logger.error(f"Ollama API call failed: {e}")
        raise


def parse_llm_response(response_text: str) -> Tuple[str, str]:
    """
    Parse LLM response to extract DECISION and TEXT.
    
    Args:
        response_text: Raw response from LLM
    
    Returns:
        Tuple of (decision, text) where decision is "STOP" or "CONTINUE"
    
    Raises:
        ValueError: If response format is invalid
    """
    # Normalize whitespace
    response_text = response_text.strip()
    
    # Try to find DECISION
    decision_match = re.search(r'DECISION:\s*(STOP|CONTINUE)', response_text, re.IGNORECASE)
    if not decision_match:
        # Try without colon
        decision_match = re.search(r'DECISION\s+(STOP|CONTINUE)', response_text, re.IGNORECASE)
    
    decision = "CONTINUE"  # Default
    if decision_match:
        decision = decision_match.group(1).upper()
    
    # Try to find TEXT section
    text_match = re.search(r'TEXT:\s*\n?(.*)', response_text, re.IGNORECASE | re.DOTALL)
    if text_match:
        text = text_match.group(1).strip()
    else:
        # If no TEXT: marker, try to extract everything after DECISION
        if decision_match:
            text = response_text[decision_match.end():].strip()
            # Remove leading "TEXT:" if present
            text = re.sub(r'^TEXT:\s*', '', text, flags=re.IGNORECASE)
        else:
            # Last resort: use entire response
            text = response_text
    
    return decision, text


def refine_chunk(
    model: str,
    ocr_chunk: str,
    max_iters: int = 6,
    wc_tolerance: float = 0.15,
    cc_tolerance: float = 0.15,
    max_novel_token_ratio: float = 0.12,
    temperature: float = 0.2,
    retry_temperature: float = 0.0,
    year: Optional[int] = None,
    month: Optional[int] = None,
    location: Optional[str] = None,
    is_table: Optional[bool] = None,
    debug: bool = False
) -> str:
    """
    Iteratively refine a single OCR chunk.
    
    Args:
        model: Ollama model name
        ocr_chunk: Original OCR text chunk
        max_iters: Maximum iterations
        wc_tolerance: Word count tolerance
        cc_tolerance: Character count tolerance
        max_novel_token_ratio: Maximum novel token ratio
        temperature: Generation temperature
        retry_temperature: Temperature for retry attempts
        year: Document year (optional)
        month: Document month (optional)
        location: Publication location (optional)
        debug: Enable debug logging
    
    Returns:
        Refined text
    """
    current = ocr_chunk
    last_good = ocr_chunk
    system_prompt = get_system_prompt()
    
    is_table_chunk = is_table if is_table is not None else is_probable_table(ocr_chunk)

    # Count OCR stats
    from .validators import count_words, count_chars
    word_count_ocr = count_words(ocr_chunk)
    char_count_ocr = count_chars(ocr_chunk)
    
    if debug:
        logger.info(f"Starting refinement: {word_count_ocr} words, {char_count_ocr} chars:\n{ocr_chunk}\n")
    
    for iteration in range(max_iters):
        if debug:
            logger.info(f"Iteration {iteration + 1}/{max_iters}")
        
        # Build user prompt
        user_prompt = get_user_prompt(
            ocr_chunk=ocr_chunk,
            current_text=current,
            word_count_ocr=word_count_ocr,
            char_count_ocr=char_count_ocr,
            wc_tolerance=wc_tolerance,
            cc_tolerance=cc_tolerance,
            year=year,
            month=month,
            location=location,
            is_table=is_table_chunk
        )
        
        # Call Ollama
        try:
            response_text = call_ollama_chat(
                model=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"API call failed on iteration {iteration + 1}: {e}")
            return last_good
        
        # Parse response
        try:
            decision, refined_text = parse_llm_response(response_text)
        except ValueError as e:
            logger.warning(f"Failed to parse response on iteration {iteration + 1}: {e}")
            if debug:
                logger.debug(f"Response was: {response_text[:200]}...")
            continue
        
        if debug:
            logger.info(f"Decision: {decision}\nRefined text: {refined_text}\n")
        
        # Validate output
        validation = validate_all(
            output_text=refined_text,
            ocr_text=ocr_chunk,
            wc_tolerance=wc_tolerance,
            cc_tolerance=cc_tolerance,
            max_novel_token_ratio=max_novel_token_ratio,
            previous_text=current if iteration > 0 else None,
            min_fuzzy_ratio=50.0 if iteration > 0 else None
        )
        
        if not validation.ok:
            if debug:
                logger.warning(f"Validation failed: {', '.join(validation.reasons)}")
            
            # Retry once with stricter settings
            if debug:
                logger.info("Retrying with stricter settings...")
            
            retry_user_prompt = user_prompt + get_retry_user_prompt_suffix()
            try:
                retry_response = call_ollama_chat(
                    model=model,
                    system_prompt=system_prompt,
                    user_prompt=retry_user_prompt,
                    temperature=retry_temperature
                )
                retry_decision, retry_text = parse_llm_response(retry_response)
                
                retry_validation = validate_all(
                    output_text=retry_text,
                    ocr_text=ocr_chunk,
                    wc_tolerance=wc_tolerance,
                    cc_tolerance=cc_tolerance,
                    max_novel_token_ratio=max_novel_token_ratio,
                    previous_text=current if iteration > 0 else None,
                    min_fuzzy_ratio=50.0 if iteration > 0 else None
                )
                
                if retry_validation.ok:
                    refined_text = retry_text
                    decision = retry_decision
                    validation = retry_validation
                    if debug:
                        logger.info("Retry validation passed")
                else:
                    if debug:
                        logger.warning(f"Retry validation failed: {', '.join(retry_validation.reasons)}")
                    return last_good
            except Exception as e:
                logger.error(f"Retry failed: {e}")
                return last_good
        
        # Check for stability (normalized text unchanged)
        norm_current = normalize_counts(current)
        norm_refined = normalize_counts(refined_text)
        
        if norm_current == norm_refined:
            if debug:
                logger.info("Output stabilized (no change)")
            return refined_text
        
        # Update current and last_good
        current = refined_text
        last_good = refined_text
        
        if debug:
            logger.info(f"Accepted output (stats: {validation.stats})")
        
        # Stop if decision is STOP
        if decision == "STOP":
            if debug:
                logger.info("Model returned STOP")
            return refined_text
    
    if debug:
        logger.info(f"Reached max iterations ({max_iters})")
    return last_good


def stitch_chunks(
    refined_chunks: List[str],
    chunks: List[Chunk],
    overlap_strategy: str = "drop_overlap"
) -> str:
    """
    Stitch refined chunks together, handling overlap.
    
    Args:
        refined_chunks: List of refined text for each chunk
        chunks: List of Chunk objects with overlap information
        overlap_strategy: Strategy for handling overlap ("drop_overlap" or "simple")
    
    Returns:
        Stitched document text
    """
    if overlap_strategy == "simple":
        # Simple join with double newlines
        return "\n\n".join(refined_chunks)
    
    elif overlap_strategy == "drop_overlap":
        if not chunks or len(chunks) == 1:
            return refined_chunks[0] if refined_chunks else ""
        
        stitched = [refined_chunks[0]]  # First chunk as-is
        
        for i in range(1, len(refined_chunks)):
            chunk = chunks[i]
            refined = refined_chunks[i]

            # Count-based overlap removal to avoid duplicate lines if content changed by cleaning
            overlap_count = 0
            if chunk.overlap_prefix:
                overlap_count = max(0, len([l for l in chunk.overlap_prefix.split('\n') if l.strip()]))

            refined_lines = refined.split('\n')

            # Drop the first overlap_count lines; if that empties the chunk, fall back to full
            if overlap_count > 0 and overlap_count < len(refined_lines):
                non_overlap_lines = refined_lines[overlap_count:]
                non_overlap = '\n'.join(non_overlap_lines)
                if non_overlap.strip():
                    stitched.append(non_overlap)
                else:
                    stitched.append(refined)
            else:
                stitched.append(refined)
        
        return "\n\n".join(stitched)
    
    else:
        raise ValueError(f"Unknown overlap_strategy: {overlap_strategy}")


def refine_document(
    ocr_text: str,
    model: str = "qwen2.5:14b",
    chunk_params: Optional[Dict] = None,
    refinement_params: Optional[Dict] = None,
    overlap_strategy: str = "drop_overlap",
    debug: bool = False
) -> str:
    """
    Refine entire OCR document chunk by chunk.
    
    Args:
        ocr_text: Full OCR text
        model: Ollama model name
        chunk_params: Parameters for chunking (min_tokens, max_tokens, overlap_lines)
        refinement_params: Parameters for refinement (max_iters, tolerances, etc.)
        overlap_strategy: Strategy for stitching chunks
        debug: Enable debug logging
    
    Returns:
        Refined document text
    """
    if chunk_params is None:
        chunk_params = {}
    if refinement_params is None:
        refinement_params = {}
    
    # Create chunks
    chunks = make_chunks(ocr_text, **chunk_params)

    # Split mixed chunks that contain table-like runs into separate table/non-table chunks
    chunks = split_chunks_for_tables(chunks)
    
    if debug:
        logger.info(f"Created {len(chunks)} chunks")
    
    # Refine each chunk
    refined_chunks = []
    for i, chunk in enumerate(chunks):
        if debug:
            logger.info(f"Processing chunk {i + 1}/{len(chunks)} (lines {chunk.start_line}-{chunk.end_line})")
        
        try:
            refined = refine_chunk(
                model=model,
                ocr_chunk=chunk.text,
                is_table=chunk.is_table,
                debug=debug,
                **refinement_params
            )
            if not refined or len(refined.strip()) == 0:
                logger.warning(f"Chunk {i + 1} returned empty, using original text")
                refined = chunk.text
            refined_chunks.append(refined)
            if debug:
                logger.info(f"Chunk {i + 1} completed: {len(refined)} chars")
        except Exception as e:
            logger.error(f"Error processing chunk {i + 1}: {e}", exc_info=debug)
            # Use original chunk text as fallback
            refined_chunks.append(chunk.text)
    
    # Stitch chunks together
    if debug:
        logger.info(f"Refined {len(refined_chunks)} chunks:")
        for i, (chunk, refined) in enumerate(zip(chunks, refined_chunks)):
            logger.info(f"  Chunk {i}: {len(refined)} chars (original: {len(chunk.text)} chars)")
    
    result = stitch_chunks(refined_chunks, chunks, overlap_strategy=overlap_strategy)
    
    if debug:
        logger.info(f"Final stitched result: {len(result)} chars")
    
    # Strip separator lines (`---`) that may appear from prompt framing
    cleaned_result = "\n".join(line for line in result.splitlines() if line.strip() != "---")

    return cleaned_result


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Refine OCR text using iterative LLM correction"
    )
    parser.add_argument(
        "--in", dest="input_file",
        required=True,
        help="Input OCR text file"
    )
    parser.add_argument(
        "--out", dest="output_file",
        required=True,
        help="Output refined text file"
    )
    parser.add_argument(
        "--model",
        default="qwen2.5:14b",
        help="Ollama model name (default: qwen2.5:14b)"
    )
    parser.add_argument(
        "--max-iters",
        type=int,
        default=6,
        help="Maximum refinement iterations per chunk (default: 6)"
    )
    parser.add_argument(
        "--wc-tol",
        type=float,
        default=0.15,
        help="Word count tolerance (default: 0.15)"
    )
    parser.add_argument(
        "--cc-tol",
        type=float,
        default=0.15,
        help="Character count tolerance (default: 0.15)"
    )
    parser.add_argument(
        "--novel-tok-ratio",
        type=float,
        default=0.12,
        help="Maximum novel token ratio (default: 0.12)"
    )
    parser.add_argument(
        "--min-tokens",
        type=int,
        default=150,
        help="Minimum tokens per chunk (default: 150)"
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=600,
        help="Maximum tokens per chunk (default: 600)"
    )
    parser.add_argument(
        "--overlap-lines",
        type=int,
        default=2,
        help="Overlap lines between chunks (default: 2)"
    )
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Document year (optional)"
    )
    parser.add_argument(
        "--month",
        type=int,
        default=None,
        help="Document month (optional)"
    )
    parser.add_argument(
        "--location",
        type=str,
        default=None,
        help="Publication location (optional)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
    
    # Read input file
    try:
        with open(args.input_file, 'r', encoding='utf-8') as f:
            ocr_text = f.read()
    except FileNotFoundError:
        logger.error(f"Input file not found: {args.input_file}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error reading input file: {e}")
        sys.exit(1)
    
    # Prepare parameters
    chunk_params = {
        "min_tokens": args.min_tokens,
        "max_tokens": args.max_tokens,
        "overlap_lines": args.overlap_lines
    }
    
    refinement_params = {
        "max_iters": args.max_iters,
        "wc_tolerance": args.wc_tol,
        "cc_tolerance": args.cc_tol,
        "max_novel_token_ratio": args.novel_tok_ratio,
        "year": args.year,
        "month": args.month,
        "location": args.location
    }
    
    # Refine document
    logger.info("Starting OCR refinement...")
    try:
        refined_text = refine_document(
            ocr_text=ocr_text,
            model=args.model,
            chunk_params=chunk_params,
            refinement_params=refinement_params,
            debug=args.debug
        )
    except Exception as e:
        logger.error(f"Refinement failed: {e}", exc_info=args.debug)
        sys.exit(1)
    
    # Write output file
    try:
        with open(args.output_file, 'w', encoding='utf-8') as f:
            f.write(refined_text)
        logger.info(f"Refined text written to {args.output_file}")
    except Exception as e:
        logger.error(f"Error writing output file: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

