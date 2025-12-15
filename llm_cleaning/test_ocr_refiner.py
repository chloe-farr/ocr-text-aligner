"""
Minimal tests for OCR refinement pipeline.
"""

import re
from llm_cleaning.chunker import make_chunks, Chunk, estimate_word_count
from llm_cleaning.ocr_refiner import parse_llm_response
from llm_cleaning.validators import (
    validate_length_ratios,
    validate_novel_tokens,
    normalize_counts,
    count_words,
    count_chars
)


# Test data
SAMPLE_OCR = """This is a sample OCR text. It has some errors.
For example, "rn" might be "m" in context. The text continues here.
Another sentence follows. This is the end."""


def test_chunker_respects_max_tokens():
    """Test that chunker respects max_tokens limit."""
    chunks = make_chunks(SAMPLE_OCR, min_tokens=10, max_tokens=20, overlap_lines=0)
    
    for chunk in chunks:
        word_count = estimate_word_count(chunk.text)
        assert word_count <= 20, f"Chunk {chunk.id} exceeds max_tokens: {word_count}"
    
    print("✓ Chunker respects max_tokens")


def test_chunker_overlap():
    """Test that chunks include overlap."""
    chunks = make_chunks(SAMPLE_OCR, min_tokens=10, max_tokens=30, overlap_lines=2)
    
    if len(chunks) > 1:
        # Check that second chunk has overlap_prefix
        assert chunks[1].overlap_prefix, "Second chunk should have overlap_prefix"
        print("✓ Chunker includes overlap")
    else:
        print("✓ Chunker overlap test skipped (single chunk)")


def test_parse_llm_response():
    """Test parsing of LLM response format."""
    # Test standard format
    response1 = "DECISION: STOP\nTEXT:\nThis is the refined text."
    decision1, text1 = parse_llm_response(response1)
    assert decision1 == "STOP"
    assert "refined text" in text1
    
    # Test CONTINUE
    response2 = "DECISION: CONTINUE\nTEXT:\nSome text here."
    decision2, text2 = parse_llm_response(response2)
    assert decision2 == "CONTINUE"
    assert "Some text" in text2
    
    # Test without explicit DECISION (should default to CONTINUE)
    response3 = "TEXT:\nJust text here."
    decision3, text3 = parse_llm_response(response3)
    assert decision3 == "CONTINUE"
    assert "Just text" in text3
    
    print("✓ LLM response parser works correctly")


def test_validators_length_drift():
    """Test that validators flag length drift."""
    ocr_text = "This is a test sentence with exactly ten words here."
    # Output with significant drift (800 vs 1200 words equivalent)
    output_text = "This is a test sentence with exactly ten words here. " * 15  # Much longer
    
    result = validate_length_ratios(output_text, ocr_text, wc_tolerance=0.15, cc_tolerance=0.15)
    
    assert not result.ok, "Should flag length drift"
    assert len(result.reasons) > 0, "Should have failure reasons"
    
    print("✓ Validators flag length drift")


def test_validators_novel_tokens():
    """Test that validators flag high novel token ratio."""
    ocr_text = "The quick brown fox jumps over the lazy dog."
    # Output with many novel tokens
    output_text = "The quick brown fox jumps over the lazy dog. Completely new words here that were never in original text."
    
    result = validate_novel_tokens(output_text, ocr_text, max_novel_token_ratio=0.12)
    
    assert not result.ok, "Should flag high novel token ratio"
    assert len(result.reasons) > 0, "Should have failure reasons"
    
    print("✓ Validators flag high novel token ratio")


def test_validators_accepts_good_output():
    """Test that validators accept output within tolerances."""
    ocr_text = "The quick brown fox jumps over the lazy dog."
    # Output with minor corrections, similar length
    output_text = "The quick brown fox jumps over the lazy dog."
    
    result = validate_length_ratios(output_text, ocr_text, wc_tolerance=0.15, cc_tolerance=0.15)
    
    assert result.ok, "Should accept output within tolerance"
    
    print("✓ Validators accept good output")


def test_normalize_counts():
    """Test text normalization."""
    text1 = "  This   has  \r\n  multiple  \t  spaces  "
    normalized = normalize_counts(text1)
    
    # Should collapse whitespace
    assert "  " not in normalized, "Should collapse multiple spaces"
    assert "\r" not in normalized, "Should normalize newlines"
    assert "\t" not in normalized, "Should normalize tabs"
    
    print("✓ Text normalization works")


def test_count_functions():
    """Test word and character counting."""
    text = "Hello world! This has 5 words."
    
    word_count = count_words(text)
    assert word_count == 5, f"Expected 5 words, got {word_count}"
    
    char_count = count_chars(text)
    assert char_count > 0, "Should count characters"
    
    print("✓ Counting functions work")


def test_refinement_stops_on_stop():
    """Test that refinement loop stops on STOP decision."""
    # This is a conceptual test - actual implementation would require mocking Ollama
    # For now, we test the parse function which is used in the loop
    response = "DECISION: STOP\nTEXT:\nFinal text."
    decision, _ = parse_llm_response(response)
    assert decision == "STOP", "Should parse STOP decision"
    
    print("✓ Refinement stops on STOP (parser test)")


def test_refinement_stops_when_stable():
    """Test that refinement detects stability."""
    # Test normalization for stability check
    text1 = "  Hello world  "
    text2 = "Hello world"
    
    norm1 = normalize_counts(text1)
    norm2 = normalize_counts(text2)
    
    assert norm1 == norm2, "Normalized texts should be equal for stability check"
    
    print("✓ Stability detection works (normalization test)")


def run_all_tests():
    """Run all tests."""
    print("\nRunning OCR refinement tests...\n")
    
    try:
        test_chunker_respects_max_tokens()
        test_chunker_overlap()
        test_parse_llm_response()
        test_validators_length_drift()
        test_validators_novel_tokens()
        test_validators_accepts_good_output()
        test_normalize_counts()
        test_count_functions()
        test_refinement_stops_on_stop()
        test_refinement_stops_when_stable()
        
        print("\n✓ All tests passed!\n")
        return True
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}\n")
        return False
    except Exception as e:
        print(f"\n✗ Test error: {e}\n")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)

