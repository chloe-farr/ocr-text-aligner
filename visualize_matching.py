"""
Visualization tools for understanding the text matching and hyphen linking process.
Generated entirely by Cursor Agent with minimal instruction.
"""
import os
import glob
from typing import List, Dict, Optional, Tuple

try:
    import matplotlib.pyplot as plt  # type: ignore
    import matplotlib.patches as patches  # type: ignore
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    plt = None  # type: ignore
    patches = None  # type: ignore

try:
    from rich.console import Console  # type: ignore
    from rich.table import Table  # type: ignore
    from rich.panel import Panel  # type: ignore
    from rich.tree import Tree  # type: ignore
    from rich.text import Text  # type: ignore
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    # Fallback to basic print
    class Console:
        def print(self, *args, **kwargs):
            print(*args)

try:
    from reportlab.lib import colors  # type: ignore
    from reportlab.lib.pagesizes import letter, A4  # type: ignore
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle  # type: ignore
    from reportlab.lib.units import inch  # type: ignore
    from reportlab.platypus import SimpleDocTemplate, Table as PDFTable, TableStyle, Paragraph, Spacer, PageBreak  # type: ignore
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT  # type: ignore
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

import xml_obj as XMLOBJ
import text_utils
from map_up_text import TokenCandidate, TokenHypotheses, LLMToken

console = Console() if RICH_AVAILABLE else Console()


def visualize_original_ocr_text(
    hypothesis_list: List[TokenHypotheses],
    page: XMLOBJ.Page,
    xml_filename: str,
    output_dir: str = "outputs"
):
    """
    Create a visualization of the original OCR text before any cleaning.
    Words that don't fuzzy match are shown in red font.
    
    Args:
        hypothesis_list: List of TokenHypotheses objects (from create_hypothesis_list, before any processing)
        page: The page object for dimensions
        xml_filename: The XML filename (e.g., "page-1alto-Maclear.xml")
        output_dir: Directory to save the PNG file (default: "outputs")
    
    Returns:
        The output file path that was used
    """
    if not MATPLOTLIB_AVAILABLE:
        console.print("[yellow]matplotlib not available. Install with: pip install matplotlib[/yellow]")
        return None
    
    # Extract base filename from XML filename (remove extension)
    xml_base = os.path.splitext(os.path.basename(xml_filename))[0]
    
    # Create base output filename
    base_filename = f"original-ocr-text_{xml_base}.png"
    
    # Check for existing files with this pattern
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    
    # Pattern to match: original-ocr-text_{xml_base}_v*.png
    pattern = os.path.join(output_dir, f"original-ocr-text_{xml_base}_v*.png")
    existing_files = glob.glob(pattern)
    
    # Also check for the base filename (v0, no version suffix)
    base_path = os.path.join(output_dir, base_filename)
    if os.path.exists(base_path):
        existing_files.append(base_path)
    
    # Count existing versions and determine next version number
    version = len(existing_files)
    
    # Generate output path with version suffix
    if version == 0:
        # First version - no suffix
        output_path = base_path
    else:
        # Add version suffix
        output_path = os.path.join(output_dir, f"original-ocr-text_{xml_base}_v{version}.png")
    
    fig, ax = plt.subplots(1, 1, figsize=(12, 16))
    
    # Set up the plot with page dimensions
    ax.set_xlim(0, page.width)
    ax.set_ylim(page.height, 0)  # Invert y-axis for image coordinates
    ax.set_aspect('equal')
    ax.axis('off')  # Remove axes for cleaner visualization
    
    # Process each hypothesis
    for hypothesis in hypothesis_list:
        anchor = hypothesis.anchor
        # Get original OCR text
        text = text_utils.decode_html_entities(anchor.content)
        
        # Determine if word fuzzy matches (has candidates)
        has_fuzzy_match = len(hypothesis.candidates) > 0
        
        # Calculate font size to fit within the bounding box
        height_scale = 0.20
        height_based_size = anchor.height * height_scale
        
        if len(text) > 0:
            char_width_ratio = 0.6
            width_based_size = (anchor.width * 0.85) / (char_width_ratio * len(text))
        else:
            width_based_size = height_based_size
        
        font_size = min(height_based_size, width_based_size)
        font_size = max(4, min(font_size, 12))
        
        # Position text at center of bounding box
        text_x = anchor.hpos + anchor.width / 2
        text_y = anchor.vpos + anchor.height / 2
        
        # Color: red if no fuzzy match, black otherwise
        text_color = 'red' if not has_fuzzy_match else 'black'
        
        # Add text to the plot
        ax.text(
            text_x,
            text_y,
            text,
            fontsize=font_size,
            ha='center',
            va='center',
            weight='normal',
            color=text_color,
            family='sans-serif'
        )
    
    plt.tight_layout()
    
    # Save the figure
    fig.savefig(output_path, dpi=150, bbox_inches='tight', pad_inches=0.1)
    console.print(f"[green]Saved original OCR text visualization to: {output_path}[/green]")
    
    return fig


def visualize_cleaned_text_positions(
    hypothesis_list: List[TokenHypotheses],
    page: XMLOBJ.Page,
    xml_filename: str,
    output_dir: str = "outputs",
    original_alto_content_by_id: Optional[Dict[int, str]] = None
):
    """
    Create a visualization of cleaned text positioned using TokenHypotheses.
    Uses the anchor's hpos, vpos, width, height and the chosen_LLM_token's word value.
    
    Color coding:
    - Green: Words that were corrected from the original XML
    - Red: Words that are errors (flagged_for_error and no chosen_LLM_token)
    - Dark orange: Words that are pending (has candidates but not matched, or context links missing / wrong token instance)
    - Black: Matched words that were not corrected

    Exported ALTO/hOCR also carries a numeric ALIGNCONF (ALTO attribute) / alignconf (hOCR title) from
    alignment_confidence.py for QA without changing this color logic.
    
    Args:
        hypothesis_list: List of TokenHypotheses objects
        page: The page object for dimensions
        xml_filename: The XML filename (e.g., "page-1alto-Maclear.xml")
        output_dir: Directory to save the PNG file (default: "outputs")
        original_alto_content_by_id: Optional mapping of anchor ID to original ALTO content
    
    Returns:
        The output file path that was used
    """
    if not MATPLOTLIB_AVAILABLE:
        console.print("[yellow]matplotlib not available. Install with: pip install matplotlib[/yellow]")
        return None
    
    # Extract base filename from XML filename (remove extension)
    xml_base = os.path.splitext(os.path.basename(xml_filename))[0]
    
    # Create base output filename
    base_filename = f"visual-recreation_{xml_base}.png"
    
    # Check for existing files with this pattern
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    
    # Pattern to match: visual-recreation_{xml_base}_v*.png
    pattern = os.path.join(output_dir, f"visual-recreation_{xml_base}_v*.png")
    existing_files = glob.glob(pattern)
    
    # Also check for the base filename (v0, no version suffix)
    base_path = os.path.join(output_dir, base_filename)
    if os.path.exists(base_path):
        existing_files.append(base_path)
    
    # Count existing versions and determine next version number
    version = len(existing_files)
    
    # Generate output path with version suffix
    if version == 0:
        # First version - no suffix
        output_path = base_path
    else:
        # Add version suffix
        output_path = os.path.join(output_dir, f"visual-recreation_{xml_base}_v{version}.png")
    
    fig, ax = plt.subplots(1, 1, figsize=(12, 16))
    
    # Set up the plot with page dimensions
    ax.set_xlim(0, page.width)
    ax.set_ylim(page.height, 0)  # Invert y-axis for image coordinates
    ax.set_aspect('equal')
    ax.axis('off')  # Remove axes for cleaner visualization
    
    # Process each hypothesis
    for hypothesis in hypothesis_list:
        anchor = hypothesis.anchor
        
        # Determine text and color based on status
        if hypothesis.chosen_LLM_token:
            text = hypothesis.chosen_LLM_token.word
            
            # Check if word was corrected from original XML
            # A word is corrected if the chosen LLM token differs from the original ALTO content(s)
            is_corrected = False
            if original_alto_content_by_id:
                original_contents = []
                # Get all original ALTO words (may be merged)
                if hypothesis.chosen and hypothesis.chosen.alto_words:
                    # Use chosen candidate's ALTO words (handles merged words)
                    for alto_word in hypothesis.chosen.alto_words:
                        alto_id = id(alto_word)
                        if alto_id in original_alto_content_by_id:
                            original_contents.append(original_alto_content_by_id[alto_id])
                        else:
                            # Fallback to current content if original not found
                            original_contents.append(text_utils.decode_html_entities(alto_word.content))
                else:
                    # Fallback: use anchor's original content
                    anchor_id = id(anchor)
                    if anchor_id in original_alto_content_by_id:
                        original_contents.append(original_alto_content_by_id[anchor_id])
                    else:
                        original_contents.append(text_utils.decode_html_entities(anchor.content))
                
                # Combine original contents and normalize for comparison
                # For merged words like "dams" + "aged" = "damaged", compare "damsaged" vs "damaged"
                original_combined = "".join(original_contents)
                original_normalized = text_utils.normalize_for_matching(original_combined)
                current_normalized = text_utils.normalize_for_matching(text)
                # Consider corrected if normalized forms differ
                is_corrected = (original_normalized != current_normalized)
            
            # PENDING: requires context-linked neighbors to match the *exact* expected LLM tokens.
            # (ALTO spatial before/after is a poor proxy at line/column boundaries — strict linking
            # misses some repeats but avoids false PENDING on every line start/end.)
            missing_left = False
            if hypothesis.chosen_LLM_token.w_before is not None:
                if hypothesis.left_matched is None:
                    missing_left = True
                elif (hypothesis.left_matched.chosen_LLM_token is None or
                      hypothesis.left_matched.chosen_LLM_token != hypothesis.chosen_LLM_token.w_before):
                    missing_left = True

            missing_right = False
            if hypothesis.chosen_LLM_token.w_after is not None:
                if hypothesis.right_matched is None:
                    missing_right = True
                elif (hypothesis.right_matched.chosen_LLM_token is None or
                      hypothesis.right_matched.chosen_LLM_token != hypothesis.chosen_LLM_token.w_after):
                    missing_right = True
            
            if is_corrected:
                # Green: corrected from XML
                text_color = 'green'
            elif missing_left or missing_right:
                # Dark orange: pending (missing neighbors or neighbors have wrong LLM tokens)
                text_color = '#CC6600'  # Dark orange
            else:
                # Black: matched but not corrected
                text_color = 'black'
        else:
            # No chosen LLM token
            if hypothesis.flagged_for_error:
                # Red: error
                text = text_utils.decode_html_entities(anchor.content)
                text_color = 'red'
            elif hypothesis.candidates:
                # Dark orange: pending (has candidates but not matched)
                text = text_utils.decode_html_entities(anchor.content)
                text_color = '#CC6600'  # Dark orange
            else:
                # Red: no candidates (error)
                text = text_utils.decode_html_entities(anchor.content)
                text_color = 'red'

        # Calculate font size to fit within the bounding box
        height_scale = 0.20
        height_based_size = anchor.height * height_scale
        
        if len(text) > 0:
            char_width_ratio = 0.6
            width_based_size = (anchor.width * 0.85) / (char_width_ratio * len(text))
        else:
            width_based_size = height_based_size
        
        font_size = min(height_based_size, width_based_size)
        font_size = max(4, min(font_size, 12))
        
        # Position text at center of bounding box
        text_x = anchor.hpos + anchor.width / 2
        text_y = anchor.vpos + anchor.height / 2
        
        # Add text to the plot
        ax.text(
            text_x,
            text_y,
            text,
            fontsize=font_size,
            ha='center',
            va='center',
            weight='normal',
            color=text_color,
            family='sans-serif'
        )
    
    plt.tight_layout()
    
    # Save the figure
    fig.savefig(output_path, dpi=150, bbox_inches='tight', pad_inches=0.1)
    console.print(f"[green]Saved cleaned text visualization to: {output_path}[/green]")
    
    return fig


def visualize_word_pipeline_flowchart(
    word_content: str,
    pipeline_states: Dict[str, List[TokenHypotheses]],
    llm_elements: List[LLMToken],
    stage_names: List[str]
):
    """
    Visualize the complete journey of ONE word through the pipeline as a flowchart.
    Shows the processing steps, decisions, and transformations at each stage.
    
    Args:
        word_content: The ALTO word content to track
        pipeline_states: Dictionary mapping stage names to hypothesis lists at that stage
        llm_elements: List of all LLM tokens
        stage_names: Ordered list of stage names to display
    """
    import text_utils
    
    console.print(f"\n[bold cyan]{'='*100}[/bold cyan]")
    console.print(f"[bold cyan]PIPELINE FLOWCHART: Tracking '{word_content}'[/bold cyan]")
    console.print(f"[bold cyan]{'='*100}[/bold cyan]\n")
    
    # Find the word in each stage
    tracked_hypotheses = {}
    for stage_name in stage_names:
        if stage_name not in pipeline_states:
            continue
        hypothesis_list = pipeline_states[stage_name]
        
        # Find the PRIMARY hypothesis for this word at this stage
        primary_hyp = None
        
        # Try exact match first
        for hyp in hypothesis_list:
            decoded = text_utils.decode_html_entities(hyp.anchor.content)
            if word_content.lower() == decoded.lower():
                primary_hyp = hyp
                break
        
        # Check merged candidates
        if not primary_hyp:
            for hyp in hypothesis_list:
                if hyp.candidates:
                    for cand in hyp.candidates:
                        for alto_w in cand.alto_words:
                            alto_decoded = text_utils.decode_html_entities(alto_w.content)
                            if word_content.lower() == alto_decoded.lower():
                                primary_hyp = hyp
                                break
                        if primary_hyp:
                            break
                    if primary_hyp:
                        break
        
        # Partial match
        if not primary_hyp:
            for hyp in hypothesis_list:
                decoded = text_utils.decode_html_entities(hyp.anchor.content)
                if word_content.lower() in decoded.lower() or decoded.lower() in word_content.lower():
                    primary_hyp = hyp
                    break
        
        if primary_hyp:
            tracked_hypotheses[stage_name] = primary_hyp
    
    if not tracked_hypotheses:
        console.print(f"[yellow]Word '{word_content}' not found in any pipeline stage[/yellow]")
        return
    
    # FLOWCHART STYLE VISUALIZATION
    # Step 1: Initial State
    console.print(f"\n[bold green]┌─────────────────────────────────────────────────────────┐[/bold green]")
    console.print(f"[bold green]│ STEP 1: INITIAL STATE                                  │[/bold green]")
    console.print(f"[bold green]└─────────────────────────────────────────────────────────┘[/bold green]")
    
    initial_hyp = tracked_hypotheses.get("after_fuzzy_matching")
    if initial_hyp:
        alto_word = initial_hyp.anchor
        decoded = text_utils.decode_html_entities(alto_word.content)
        console.print(f"  ALTO Word: [red]{alto_word.content}[/red] → [blue]{decoded}[/blue]")
        console.print(f"  Position: ({alto_word.hpos}, {alto_word.vpos})")
    
    console.print(f"\n  [bold]↓[/bold]")
    console.print(f"  [dim]Processing...[/dim]")
    console.print(f"  [bold]↓[/bold]")
    
    # Step 2: Fuzzy Matching
    console.print(f"\n[bold yellow]┌─────────────────────────────────────────────────────────┐[/bold yellow]")
    console.print(f"[bold yellow]│ STEP 2: FUZZY MATCHING                                 │[/bold yellow]")
    console.print(f"[bold yellow]└─────────────────────────────────────────────────────────┘[/bold yellow]")
    
    if initial_hyp:
        console.print(f"  [bold]Action:[/bold] Match normalized word against LLM vocabulary")
        normalized = text_utils.normalize_for_matching(decoded)
        console.print(f"  Normalized: [cyan]{normalized}[/cyan]")
        console.print(f"  [dim]Threshold: ≥80% fuzzy match required[/dim]")
        
        if initial_hyp.candidates:
            console.print(f"\n  [bold]Results:[/bold] Found {len(initial_hyp.candidates)} candidate form(s)")
            for i, cand in enumerate(initial_hyp.candidates[:5], 1):
                console.print(f"    [{i}] Candidate form: [cyan]'{cand.clean_form}'[/cyan] (fuzzy score: {cand.fuzzy_score:.1f}%)")
                if cand.possible_llm_elements_by_fuzzy_match:
                    # Count instances by word
                    word_counts = {}
                    for token in cand.possible_llm_elements_by_fuzzy_match:
                        word = token.word
                        if word not in word_counts:
                            word_counts[word] = []
                        word_counts[word].append(token)
                    
                    console.print(f"        → Total LLM token instances matching this form: {len(cand.possible_llm_elements_by_fuzzy_match)}")
                    for word, tokens in word_counts.items():
                        console.print(f"        → '{word}': {len(tokens)} instance(s) in LLM text")
                        # Show unique neighbor contexts for this word
                        neighbor_contexts = set()
                        for token in tokens:
                            before = token.w_before.word if token.w_before else "(start)"
                            after = token.w_after.word if token.w_after else "(end)"
                            neighbor_contexts.add(f"'{before}' ... '{after}'")
                        if len(neighbor_contexts) <= 5:
                            for ctx in sorted(neighbor_contexts):
                                console.print(f"          • Context: {ctx}")
                        elif len(neighbor_contexts) > 5:
                            for ctx in sorted(list(neighbor_contexts))[:5]:
                                console.print(f"          • Context: {ctx}")
                            console.print(f"          • ... and {len(neighbor_contexts) - 5} more unique neighbor contexts")
        else:
            console.print(f"  [red]✗ No candidates found[/red]")
            console.print(f"  [yellow]→ Flagged for error (no fuzzy match ≥80%)[/yellow]")
    
    console.print(f"\n  [bold]↓[/bold]")
    console.print(f"  [dim]Processing...[/dim]")
    console.print(f"  [bold]↓[/bold]")
    
    # Step 3: Context Matching
    console.print(f"\n[bold yellow]┌─────────────────────────────────────────────────────────┐[/bold yellow]")
    console.print(f"[bold yellow]│ STEP 3: CONTEXT MATCHING                               │[/bold yellow]")
    console.print(f"[bold yellow]└─────────────────────────────────────────────────────────┘[/bold yellow]")
    
    context_hyp = tracked_hypotheses.get("after_context_matching")
    if context_hyp:
        console.print(f"  [bold]Action:[/bold] Check neighbors (before/after words)")
        before_word = text_utils.decode_html_entities(context_hyp.anchor.before_word.content) if context_hyp.anchor.before_word else "N/A"
        after_word = text_utils.decode_html_entities(context_hyp.anchor.after_word.content) if context_hyp.anchor.after_word else "N/A"
        console.print(f"  Context: ... '{before_word}' → '{decoded}' → '{after_word}' ...")
        
        has_context_matches = False
        all_context_matches = []
        
        for cand in context_hyp.candidates:
            if cand.possible_llm_elements_by_context:
                has_context_matches = True
                # Deduplicate by LLM token ID to get unique instances
                seen_token_ids = set()
                for llm_elem, before_score, after_score in cand.possible_llm_elements_by_context:
                    token_id = id(llm_elem)
                    if token_id not in seen_token_ids:
                        seen_token_ids.add(token_id)
                        all_context_matches.append((llm_elem, before_score, after_score, cand))
        
        if has_context_matches:
            console.print(f"\n  [bold]Results:[/bold] Found {len(all_context_matches)} unique context match(es)")
            console.print(f"  [dim]Testing each LLM token instance with its unique neighbors...[/dim]")
            console.print(f"  [dim]Threshold: ≥90% context score required[/dim]")
            
            # Show all unique matches (each represents a different LLM token instance with different neighbors)
            for idx, (llm_elem, before_score, after_score, cand) in enumerate(all_context_matches, 1):
                before_llm = llm_elem.w_before.word if llm_elem.w_before else "N/A"
                after_llm = llm_elem.w_after.word if llm_elem.w_after else "N/A"
                avg_score = (before_score + after_score) / 2.0
                
                console.print(f"\n    [{idx}] Testing LLM token instance:")
                console.print(f"        Word: [cyan]'{llm_elem.word}'[/cyan]")
                console.print(f"        LLM context: ... '{before_llm}' → '{llm_elem.word}' → '{after_llm}' ...")
                console.print(f"        Context scores:")
                console.print(f"          • Before: ALTO '{before_word}' ↔ LLM '{before_llm}' = {before_score:.1f}%")
                console.print(f"          • After:  ALTO '{after_word}' ↔ LLM '{after_llm}' = {after_score:.1f}%")
                console.print(f"        Average context score: {avg_score:.1f}%")
                if avg_score >= 90.0:
                    console.print(f"        [green]✓ PASS[/green] (≥90%)")
                elif avg_score >= 70.0:
                    console.print(f"        [yellow]⚠ WEAK[/yellow] (70-90%)")
                else:
                    console.print(f"        [red]✗ FAIL[/red] (<70%)")
        else:
            console.print(f"\n  [yellow]⚠ No context matches found[/yellow]")
            console.print(f"  [dim]Checked all {len(context_hyp.candidates)} candidate(s) for context matches[/dim]")
            console.print(f"  [dim]Threshold: ≥90% context score required on at least one side[/dim]")
            if context_hyp.flagged_for_error:
                console.print(f"  [red]→ Flagged for error (no context match found)[/red]")
    
    console.print(f"\n  [bold]↓[/bold]")
    console.print(f"  [dim]Processing...[/dim]")
    console.print(f"  [bold]↓[/bold]")
    
    # Step 4: Hyphen Linking
    console.print(f"\n[bold yellow]┌─────────────────────────────────────────────────────────┐[/bold yellow]")
    console.print(f"[bold yellow]│ STEP 4: HYPHEN LINKING                                 │[/bold yellow]")
    console.print(f"[bold yellow]└─────────────────────────────────────────────────────────┘[/bold yellow]")
    
    hyphen_hyp = tracked_hypotheses.get("after_hyphen_linking")
    context_hyp = tracked_hypotheses.get("after_context_matching")  # Get previous stage for comparison
    
    if hyphen_hyp:
        decoded_hyphen = text_utils.decode_html_entities(hyphen_hyp.anchor.content)
        is_literal_hyphen = text_utils.is_hyphenish(hyphen_hyp.anchor)
        console.print(f"  [bold]Action:[/bold] Check if word should be combined with neighbors")
        console.print(f"  [bold]Is literal hyphen?[/bold] {is_literal_hyphen}")
        if is_literal_hyphen:
            console.print(f"  Content: [cyan]{decoded_hyphen}[/cyan] (ends with hyphen)")
        
        # Get the previous stage to see what the word was before hyphen linking
        if context_hyp:
            prev_decoded = text_utils.decode_html_entities(context_hyp.anchor.content)
            prev_after_word = context_hyp.anchor.after_word
            console.print(f"  [dim]Previous state: '{prev_decoded}' → after_word: {text_utils.decode_html_entities(prev_after_word.content) if prev_after_word else 'N/A'}[/dim]")
        
        # Check if word was merged
        was_merged = False
        merged_parts = []
        merged_candidate = None
        for cand in hyphen_hyp.candidates:
            if len(cand.alto_words) > 1:
                was_merged = True
                merged_parts = [text_utils.decode_html_entities(w.content) for w in cand.alto_words]
                merged_candidate = cand
                break
        
        if was_merged and merged_candidate:
            console.print(f"\n  [bold green]✓ MERGED[/bold green]")
            console.print(f"  Combined ALTO words: [cyan]{' + '.join(merged_parts)}[/cyan]")
            
            # Show the combined form and scores
            combined_form = merged_candidate.clean_form
            fuzzy_score = merged_candidate.fuzzy_score
            console.print(f"  Combined form: [green]'{combined_form}'[/green]")
            console.print(f"  Fuzzy match score: {fuzzy_score:.1f}%")
            
            # Show what LLM word it matched against
            if merged_candidate.possible_llm_elements_by_fuzzy_match:
                matched_llm_words = [t.word for t in merged_candidate.possible_llm_elements_by_fuzzy_match]
                word_list = ', '.join(f"'{w}'" for w in matched_llm_words[:3])
                console.print(f"  Matched to LLM word(s): {word_list}")
                if len(matched_llm_words) > 3:
                    console.print(f"    ... and {len(matched_llm_words) - 3} more")
            elif hyphen_hyp.chosen_LLM_token:
                console.print(f"  Matched to LLM token: [green]'{hyphen_hyp.chosen_LLM_token.word}'[/green]")
            
            # Show context scores if available
            if merged_candidate.possible_llm_elements_by_context:
                best_context = merged_candidate.possible_llm_elements_by_context[0]
                llm_elem, before_score, after_score = best_context
                avg_context = (before_score + after_score) / 2.0
                console.print(f"  Context score: {avg_context:.1f}% (before: {before_score:.1f}%, after: {after_score:.1f}%)")
            
            if hyphen_hyp.chosen_LLM_token and hyphen_hyp.chosen_LLM_token not in (merged_candidate.possible_llm_elements_by_fuzzy_match or []):
                console.print(f"  → Final chosen LLM token: [green]'{hyphen_hyp.chosen_LLM_token.word}'[/green]")
            
            # Show what was tested - the immediate after_word is prioritized
            if context_hyp:
                console.print(f"\n  [bold]Combination Testing Process:[/bold]")
                
                # Show the prioritized after_word
                if context_hyp.anchor.after_word:
                    after_word_text = text_utils.decode_html_entities(context_hyp.anchor.after_word.content)
                    console.print(f"    [1] [bold]PRIORITIZED[/bold] '{decoded_hyphen}' + '{after_word_text}'")
                    console.print(f"        → [green]✓ SELECTED[/green] (Immediate after_word has highest priority)")
                    
                    # Show what was attempted
                    base1 = decoded_hyphen.rstrip("-–—") if is_literal_hyphen else decoded_hyphen
                    attempted_merge = base1 + after_word_text
                    attempted_with_hyphen = base1 + "-" + after_word_text if is_literal_hyphen else None
                    
                    console.print(f"        Combined: '{attempted_merge}'" + (f" or '{attempted_with_hyphen}'" if attempted_with_hyphen else ""))
                    console.print(f"        Fuzzy score: {fuzzy_score:.1f}%")
                
                # Find nearby words in the same stage that might have been tested
                # Only show words that were eligible (flagged or no good matches)
                if "after_context_matching" in pipeline_states:
                    context_stage_hypotheses = pipeline_states["after_context_matching"]
                    
                    # Find the index of our word in the context stage
                    word_idx = None
                    for idx, hyp in enumerate(context_stage_hypotheses):
                        if id(hyp.anchor) == id(context_hyp.anchor):
                            word_idx = idx
                            break
                    
                    if word_idx is not None:
                        # Show eligible nearby words (flagged or no good matches)
                        # Words with good matches shouldn't be tested as partners
                        eligible_words = []
                        ineligible_words = []
                        
                        for offset in range(1, 6):  # Check nearby positions
                            for check_idx in [word_idx + offset, word_idx - offset]:
                                if 0 <= check_idx < len(context_stage_hypotheses):
                                    other_hyp = context_stage_hypotheses[check_idx]
                                    other_word = text_utils.decode_html_entities(other_hyp.anchor.content)
                                    
                                    if other_word == after_word_text:  # Skip the selected one
                                        continue
                                    
                                    # Check if this word was eligible (should have been tested)
                                    has_good_match = False
                                    if other_hyp.candidates:
                                        for cand in other_hyp.candidates:
                                            if cand.fuzzy_score >= 85.0 or len(cand.possible_llm_elements_by_fuzzy_match) > 0:
                                                has_good_match = True
                                                break
                                    
                                    is_eligible = other_hyp.flagged_for_error or not has_good_match
                                    
                                    if is_eligible and len(eligible_words) < 3:
                                        eligible_words.append((offset if check_idx > word_idx else -offset, other_word, other_hyp))
                                    elif not is_eligible and len(ineligible_words) < 2:
                                        ineligible_words.append((offset if check_idx > word_idx else -offset, other_word))
                            
                            if len(eligible_words) >= 3:
                                break
                        
                        if eligible_words:
                            console.print(f"\n    [2+] Other eligible words tested (spatially sorted):")
                            for offset, other_word, other_hyp in eligible_words:
                                direction = "after" if offset > 0 else "before"
                                reason = "flagged" if other_hyp.flagged_for_error else "no good match"
                                console.print(f"        [{abs(offset)} {direction}] '{decoded_hyphen}' + '{other_word}' ({reason}) → [dim]tested[/dim]")
                        
                        if ineligible_words:
                            console.print(f"\n    [dim]Nearby words NOT tested (already have good matches):[/dim]")
                            for offset, other_word in ineligible_words:
                                direction = "after" if offset > 0 else "before"
                                console.print(f"        [{abs(offset)} {direction}] '{other_word}' → [dim]skipped (has good match)[/dim]")
                        
                        console.print(f"\n    [dim]Search strategy:[/dim]")
                        console.print(f"        • Only tests words with no candidates OR bad context scores")
                        console.print(f"        • Pass 1: Spatially-close eligible words (reading order distance)")
                        console.print(f"        • Pass 2: All remaining eligible words for exact vocabulary matches")
                        console.print(f"        • Priority: Exact matches (100%) > Fuzzy matches (≥80%)")
                        console.print(f"        • Context validation: ≥70% required")
        else:
            # Show what was tested
            console.print(f"\n  [bold]Not merged[/bold]")
            console.print(f"  [bold]Combination Testing Process:[/bold]")
            
            if context_hyp and context_hyp.anchor.after_word:
                after_word_text = text_utils.decode_html_entities(context_hyp.anchor.after_word.content)
                console.print(f"    [1] [bold]PRIORITIZED[/bold] '{decoded_hyphen}' + '{after_word_text}'")
                
                # Try to show why it failed
                base1 = decoded_hyphen.rstrip("-–—") if is_literal_hyphen else decoded_hyphen
                attempted_merge = base1 + after_word_text
                attempted_with_hyphen = base1 + "-" + after_word_text if is_literal_hyphen else None
                
                console.print(f"        Combined: '{attempted_merge}'" + (f" or '{attempted_with_hyphen}'" if attempted_with_hyphen else ""))
                console.print(f"        → [red]✗ FAILED[/red]")
                console.print(f"        Reason: [dim]No fuzzy match ≥80% found in LLM vocabulary, or context validation <70%[/dim]")
                
                # Show nearby words that were also tested
                if "after_context_matching" in pipeline_states:
                    context_stage_hypotheses = pipeline_states["after_context_matching"]
                    word_idx = None
                    for idx, hyp in enumerate(context_stage_hypotheses):
                        if id(hyp.anchor) == id(context_hyp.anchor):
                            word_idx = idx
                            break
                    
                    if word_idx is not None:
                        # Show eligible nearby words (flagged or no good matches)
                        eligible_words = []
                        ineligible_words = []
                        
                        for offset in range(1, 6):  # Check nearby positions
                            for check_idx in [word_idx + offset, word_idx - offset]:
                                if 0 <= check_idx < len(context_stage_hypotheses):
                                    other_hyp = context_stage_hypotheses[check_idx]
                                    other_word = text_utils.decode_html_entities(other_hyp.anchor.content)
                                    
                                    if other_word == after_word_text:  # Skip the prioritized one
                                        continue
                                    
                                    # Check if this word was eligible (should have been tested)
                                    has_good_match = False
                                    if other_hyp.candidates:
                                        for cand in other_hyp.candidates:
                                            if cand.fuzzy_score >= 85.0 or len(cand.possible_llm_elements_by_fuzzy_match) > 0:
                                                has_good_match = True
                                                break
                                    
                                    is_eligible = other_hyp.flagged_for_error or not has_good_match
                                    actual_offset = check_idx - word_idx
                                    
                                    if is_eligible and len(eligible_words) < 3:
                                        eligible_words.append((actual_offset, other_word, other_hyp))
                                    elif not is_eligible and len(ineligible_words) < 2:
                                        ineligible_words.append((actual_offset, other_word))
                            
                            if len(eligible_words) >= 3:
                                break
                        
                        if eligible_words:
                            console.print(f"\n    [2+] Other eligible words tested:")
                            for offset, other_word, other_hyp in eligible_words:
                                direction = "after" if offset > 0 else "before"
                                reason = "flagged" if other_hyp.flagged_for_error else "no good match"
                                console.print(f"        [{abs(offset)} {direction}] '{decoded_hyphen}' + '{other_word}' ({reason}) → [dim]✗ No match[/dim]")
                        
                        if ineligible_words:
                            console.print(f"\n    [dim]Nearby words NOT tested (already have good matches):[/dim]")
                            for offset, other_word in ineligible_words:
                                direction = "after" if offset > 0 else "before"
                                console.print(f"        [{abs(offset)} {direction}] '{other_word}' → [dim]skipped (has good match)[/dim]")
            
            console.print(f"\n    [dim]Search strategy:[/dim]")
            console.print(f"        • Only tests words with no candidates OR bad context scores")
            console.print(f"        • Tested spatially-close eligible words (reading order distance)")
            console.print(f"        • Also tested all eligible words for exact vocabulary matches (handles reordering)")
            console.print(f"        → [dim]No suitable partner found[/dim]")
            console.print(f"  [dim]Reason: Individual match is better, or no valid combination with ≥80% fuzzy + ≥70% context[/dim]")
            if hyphen_hyp.flagged_for_error:
                console.print(f"  [yellow]→ Still flagged for error (may need long-distance matching or paragraph reordering)[/yellow]")
    
    console.print(f"\n  [bold]↓[/bold]")
    console.print(f"  [dim]Processing...[/dim]")
    console.print(f"  [bold]↓[/bold]")
    
    # Step 5: Word Merges/Splits
    console.print(f"\n[bold yellow]┌─────────────────────────────────────────────────────────┐[/bold yellow]")
    console.print(f"[bold yellow]│ STEP 5: WORD MERGES/SPLITS                             │[/bold yellow]")
    console.print(f"[bold yellow]└─────────────────────────────────────────────────────────┘[/bold yellow]")
    
    merge_hyp = tracked_hypotheses.get("after_word_merges")
    if merge_hyp:
        console.print(f"  [bold]Check:[/bold] Is this word a merge that should be split?")
        
        # Check if word was split
        was_split = False
        split_parts = []
        # Compare with previous stage to see if it was split
        if "after_hyphen_linking" in tracked_hypotheses:
            prev_hyp = tracked_hypotheses["after_hyphen_linking"]
            prev_decoded = text_utils.decode_html_entities(prev_hyp.anchor.content)
            curr_decoded = text_utils.decode_html_entities(merge_hyp.anchor.content)
            
            # If current is different/shorter, might have been split
            if curr_decoded != prev_decoded and word_content.lower() in prev_decoded.lower():
                was_split = True
                split_parts = [curr_decoded]
        
        if was_split:
            console.print(f"  [bold green]✓ SPLIT[/bold green]")
            console.print(f"  Split into: [cyan]{' + '.join(split_parts)}[/cyan]")
        else:
            console.print(f"  [dim]→ Not split (word is correct as-is)[/dim]")
    
    console.print(f"\n  [bold]↓[/bold]")
    console.print(f"  [dim]Processing...[/dim]")
    console.print(f"  [bold]↓[/bold]")
    
    # Step 6: Weak Fuzzy Matching
    console.print(f"\n[bold yellow]┌─────────────────────────────────────────────────────────┐[/bold yellow]")
    console.print(f"[bold yellow]│ STEP 6: WEAK FUZZY MATCHING                            │[/bold yellow]")
    console.print(f"[bold yellow]└─────────────────────────────────────────────────────────┘[/bold yellow]")
    
    weak_hyp = tracked_hypotheses.get("after_weak_fuzzy")
    if weak_hyp:
        console.print(f"  [bold]Check:[/bold] Still unmatched? Use neighbor context + size")
        
        if weak_hyp.chosen_LLM_token:
            console.print(f"  [bold green]✓ MATCHED via weak fuzzy[/bold green]")
            console.print(f"  Method: Neighbor context + bounding box size")
            console.print(f"  → Matched to: [green]'{weak_hyp.chosen_LLM_token.word}'[/green]")
        else:
            console.print(f"  [dim]→ No weak fuzzy match (already matched or no suitable neighbors)[/dim]")
    
    console.print(f"\n  [bold]↓[/bold]")
    console.print(f"  [dim]Processing...[/dim]")
    console.print(f"  [bold]↓[/bold]")
    
    # Final State
    console.print(f"\n[bold green]┌─────────────────────────────────────────────────────────┐[/bold green]")
    console.print(f"[bold green]│ FINAL STATE                                             │[/bold green]")
    console.print(f"[bold green]└─────────────────────────────────────────────────────────┘[/bold green]")
    
    final_hyp = tracked_hypotheses.get("final")
    if final_hyp:
        if final_hyp.chosen_LLM_token:
            llm_idx = None
            for idx, llm in enumerate(llm_elements):
                if llm == final_hyp.chosen_LLM_token:
                    llm_idx = idx
                    break
            
            console.print(f"  [bold green]✓ SUCCESSFULLY MATCHED[/bold green]")
            console.print(f"  ALTO: [red]{decoded}[/red]")
            console.print(f"  → LLM: [green]'{final_hyp.chosen_LLM_token.word}'[/green] (index: {llm_idx})")
            
            if final_hyp.chosen:
                console.print(f"  Candidate form: '{final_hyp.chosen.clean_form}' (fuzzy: {final_hyp.chosen.fuzzy_score:.1f}%)")
            
            # Show links with details
            console.print(f"\n  [bold]Bidirectional Links:[/bold]")
            if final_hyp.left_matched:
                left_word = text_utils.decode_html_entities(final_hyp.left_matched.anchor.content)
                left_llm = final_hyp.left_matched.chosen_LLM_token.word if final_hyp.left_matched.chosen_LLM_token else "N/A"
                console.print(f"    Left: [green]✓[/green] '{left_word}' → LLM: '{left_llm}'")
                # Verify bidirectional
                if final_hyp.left_matched.right_matched == final_hyp:
                    console.print(f"        [dim]✓ Reciprocal link confirmed[/dim]")
                else:
                    console.print(f"        [red]✗ Missing reciprocal link![/red]")
            else:
                expected_left = final_hyp.chosen_LLM_token.w_before.word if final_hyp.chosen_LLM_token.w_before else None
                if expected_left:
                    console.print(f"    Left: [red]✗[/red] Expected LLM: '{expected_left}' (not linked)")
                else:
                    console.print(f"    Left: [dim]N/A (at start)[/dim]")
            
            if final_hyp.right_matched:
                right_word = text_utils.decode_html_entities(final_hyp.right_matched.anchor.content)
                right_llm = final_hyp.right_matched.chosen_LLM_token.word if final_hyp.right_matched.chosen_LLM_token else "N/A"
                console.print(f"    Right: [green]✓[/green] '{right_word}' → LLM: '{right_llm}'")
                # Verify bidirectional
                if final_hyp.right_matched.left_matched == final_hyp:
                    console.print(f"        [dim]✓ Reciprocal link confirmed[/dim]")
                else:
                    console.print(f"        [red]✗ Missing reciprocal link![/red]")
            else:
                expected_right = final_hyp.chosen_LLM_token.w_after.word if final_hyp.chosen_LLM_token.w_after else None
                if expected_right:
                    console.print(f"    Right: [red]✗[/red] Expected LLM: '{expected_right}' (not linked)")
                else:
                    console.print(f"    Right: [dim]N/A (at end)[/dim]")
        else:
            console.print(f"  [bold red]✗ NOT MATCHED[/bold red]")
            console.print(f"  [bold]Status:[/bold] ", end="")
            if final_hyp.flagged_for_error:
                console.print(f"[red]ERROR[/red]")
                # Show why it failed
                if final_hyp.candidates:
                    console.print(f"  [dim]Has {len(final_hyp.candidates)} candidate(s) but none selected[/dim]")
                else:
                    console.print(f"  [dim]No candidates available[/dim]")
            else:
                console.print(f"[yellow]PENDING[/yellow]")
                if final_hyp.candidates:
                    console.print(f"  [dim]Has {len(final_hyp.candidates)} candidate(s) - awaiting better context or proximity matching[/dim]")


def visualize_llm_token_mapping_table(hypothesis_list: List[TokenHypotheses], llm_elements: List[LLMToken], max_display: int = 100, show_table: bool = True):
    """
    Show a comprehensive table mapping LLM tokens to TokenHypotheses objects.
    This helps verify that mappings are correct and identify conflicts.
    
    Args:
        hypothesis_list: List of all TokenHypotheses
        llm_elements: List of all LLM tokens
        max_display: Maximum number of rows to display (if show_table=True, use None to show all)
        show_table: If True, display the full table. If False, only show the summary.
    """
    if show_table:
        console.print(f"\n[bold cyan]{'='*100}[/bold cyan]")
        console.print(f"[bold cyan]LLM TOKEN ↔ TOKENHYPOTHESES MAPPING TABLE[/bold cyan]")
        console.print(f"[bold cyan]{'='*100}[/bold cyan]\n")
    else:
        console.print(f"\n{'='*70}")
        console.print(f"LLM TOKEN MAPPING SUMMARY")
        console.print(f"{'='*70}\n")
    
    # Build mapping from LLM tokens to hypotheses (using id() since LLMToken is not hashable)
    llm_to_hypotheses: Dict[int, List[TokenHypotheses]] = {}
    llm_id_to_token: Dict[int, LLMToken] = {}  # Map id to token for lookup
    for hyp in hypothesis_list:
        if hyp.chosen_LLM_token:
            llm_id = id(hyp.chosen_LLM_token)
            if llm_id not in llm_to_hypotheses:
                llm_to_hypotheses[llm_id] = []
                llm_id_to_token[llm_id] = hyp.chosen_LLM_token
            llm_to_hypotheses[llm_id].append(hyp)
    
    # Create main mapping table
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=5)
    table.add_column("Hypothesis Index", style="dim", width=12)
    table.add_column("ALTO Word(s)", style="red", width=30)
    table.add_column("→", style="dim", width=3, justify="center")
    table.add_column("LLM Token", style="green", width=30)
    table.add_column("LLM Index", style="dim", width=10)
    table.add_column("Status", width=12)
    table.add_column("Conflict?", width=10, justify="center")
    
    # Track conflicts (using id() for set membership)
    conflicts = []
    matched_llm_token_ids = set()
    pending_details_list = []  # Store details for PENDING words with chosen_LLM_token
    
    # If showing table, use max_display (None = all). If not showing table, iterate all for summary.
    if show_table:
        display_limit = max_display if max_display else len(hypothesis_list)
    else:
        display_limit = len(hypothesis_list)  # Always process all for accurate summary
    
    for display_idx, hypothesis in enumerate(hypothesis_list[:display_limit], 1):
        # Get the actual index in the full hypothesis_list
        hyp_idx = display_idx - 1  # Since enumerate starts at 1, subtract 1 for 0-based index
        # Get ALTO word(s)
        alto_words_str = ""
        if hypothesis.candidates and hypothesis.candidates[0].alto_words:
            alto_words = [text_utils.decode_html_entities(w.content) for w in hypothesis.candidates[0].alto_words]
            alto_words_str = " + ".join(alto_words) if len(alto_words) > 1 else alto_words[0]
        else:
            alto_words_str = text_utils.decode_html_entities(hypothesis.anchor.content)
        
        # Get LLM token info
        if hypothesis.chosen_LLM_token:
            llm_token = hypothesis.chosen_LLM_token
            llm_token_str = llm_token.word
            # Find LLM token index
            llm_index = None
            for idx, llm in enumerate(llm_elements):
                if llm == llm_token:
                    llm_index = idx
                    break
            llm_index_str = str(llm_index) if llm_index is not None else "?"
            
            # Check for conflicts (same LLM token mapped to multiple hypotheses)
            llm_id = id(llm_token)
            if llm_id in matched_llm_token_ids:
                # Already seen this token - check if it's a conflict
                if len(llm_to_hypotheses.get(llm_id, [])) > 1:
                    conflict_str = "[bold red]⚠ YES[/bold red]"
                    conflicts.append((hypothesis, llm_token, llm_to_hypotheses[llm_id]))
                else:
                    conflict_str = "[dim]No[/dim]"
            else:
                matched_llm_token_ids.add(llm_id)
                if len(llm_to_hypotheses.get(llm_id, [])) > 1:
                    conflict_str = "[bold red]⚠ YES[/bold red]"
                    conflicts.append((hypothesis, llm_token, llm_to_hypotheses[llm_id]))
                else:
                    conflict_str = "[dim]No[/dim]"
            
            # Check if required neighbors are linked AND have the correct LLM tokens
            missing_left = False
            if hypothesis.chosen_LLM_token.w_before is not None:
                if hypothesis.left_matched is None:
                    missing_left = True
                elif (hypothesis.left_matched.chosen_LLM_token is None or
                      hypothesis.left_matched.chosen_LLM_token != hypothesis.chosen_LLM_token.w_before):
                    # Has link but neighbor doesn't have the correct LLM token
                    missing_left = True
            
            missing_right = False
            if hypothesis.chosen_LLM_token.w_after is not None:
                if hypothesis.right_matched is None:
                    missing_right = True
                elif (hypothesis.right_matched.chosen_LLM_token is None or
                      hypothesis.right_matched.chosen_LLM_token != hypothesis.chosen_LLM_token.w_after):
                    # Has link but neighbor doesn't have the correct LLM token
                    missing_right = True
            
            if missing_left or missing_right:
                # Has chosen_LLM_token but missing required neighbors or neighbors have wrong LLM tokens - mark as PENDING
                status = "[yellow]⚠ PENDING[/yellow]"
            else:
                status = "[bold green]✓ MATCHED[/bold green]"
        else:
            llm_token_str = "[dim]N/A[/dim]"
            llm_index_str = "[dim]N/A[/dim]"
            conflict_str = "[dim]N/A[/dim]"
            missing_left = False
            missing_right = False
            if hypothesis.flagged_for_error:
                status = "[bold red]✗ ERROR[/bold red]"
            elif hypothesis.candidates:
                status = "[yellow]⚠ PENDING[/yellow]"
            else:
                status = "[red]✗ NO CAND[/red]"
        
        # Only add to table if showing table
        if show_table:
            table.add_row(
                str(display_idx),
                f"Hyp[{hyp_idx}]",
                alto_words_str,
                "→",
                llm_token_str,
                llm_index_str,
                status,
                conflict_str
            )
        
        # Store PENDING details for debugging output (words with chosen_LLM_token that are still PENDING)
        if hypothesis.chosen_LLM_token and (missing_left or missing_right):
            # Find spatial neighbors via ALTO structure
            spatial_left_alto = None
            spatial_right_alto = None
            if hypothesis.anchor.before_word:
                spatial_left_alto = text_utils.decode_html_entities(hypothesis.anchor.before_word.content)
            if hypothesis.anchor.after_word:
                spatial_right_alto = text_utils.decode_html_entities(hypothesis.anchor.after_word.content)
            
            pending_details = {
                'hyp_idx': hyp_idx,
                'alto_word': alto_words_str,
                'llm_token': hypothesis.chosen_LLM_token.word,
                'missing_left': missing_left,
                'missing_right': missing_right,
                'expected_left_token': hypothesis.chosen_LLM_token.w_before,
                'expected_left': hypothesis.chosen_LLM_token.w_before.word if hypothesis.chosen_LLM_token.w_before else None,
                'expected_right_token': hypothesis.chosen_LLM_token.w_after,
                'expected_right': hypothesis.chosen_LLM_token.w_after.word if hypothesis.chosen_LLM_token.w_after else None,
                'actual_left_token': None,
                'actual_left': None,
                'actual_right_token': None,
                'actual_right': None,
                'left_matched_word': None,
                'right_matched_word': None,
                'spatial_left_alto': spatial_left_alto,
                'spatial_right_alto': spatial_right_alto
            }
            
            if hypothesis.left_matched:
                pending_details['left_matched_word'] = text_utils.decode_html_entities(hypothesis.left_matched.anchor.content)
                if hypothesis.left_matched.chosen_LLM_token:
                    pending_details['actual_left_token'] = hypothesis.left_matched.chosen_LLM_token
                    pending_details['actual_left'] = hypothesis.left_matched.chosen_LLM_token.word
            
            if hypothesis.right_matched:
                pending_details['right_matched_word'] = text_utils.decode_html_entities(hypothesis.right_matched.anchor.content)
                if hypothesis.right_matched.chosen_LLM_token:
                    pending_details['actual_right_token'] = hypothesis.right_matched.chosen_LLM_token
                    pending_details['actual_right'] = hypothesis.right_matched.chosen_LLM_token.word
            
            # Store in a list for later display
            pending_details_list.append(pending_details)
    
    if show_table:
        console.print(table)
    
    # Show conflicts summary
    if conflicts:
        console.print(f"\n[bold red]⚠ CONFLICTS DETECTED:[/bold red]")
        unique_conflicts = {}  # Use id as key
        for hyp, llm_token, hyp_list in conflicts:
            llm_id = id(llm_token)
            if llm_id not in unique_conflicts:
                unique_conflicts[llm_id] = (llm_token, hyp_list)
        
        for llm_id, (llm_token, hyp_list) in unique_conflicts.items():
            console.print(f"\n  [red]LLM Token '{llm_token.word}' is mapped to {len(hyp_list)} hypotheses:[/red]")
            for hyp in hyp_list:
                alto_str = text_utils.decode_html_entities(hyp.anchor.content)
                console.print(f"    - Hyp[{hypothesis_list.index(hyp)}]: '{alto_str}'")
    else:
        console.print(f"\n[bold green]✓ No conflicts detected - all LLM tokens map to unique hypotheses[/bold green]")
    
    # Show detailed debugging for PENDING words with chosen_LLM_token
    if pending_details_list:
        console.print(f"\n[bold yellow]⚠ PENDING WORDS ANALYSIS (with chosen_LLM_token):[/bold yellow]")
        console.print(f"  These words have a chosen LLM token but neighbors don't match correctly.")
        console.print(f"  [dim]Note: Cross-boundary matching should have attempted to link these by searching for expected neighbors across layout boundaries. Check console output above for '[Cross-Boundary Matching]' messages.[/dim]\n")
        
        for details in pending_details_list[:20]:  # Show first 20
            console.print(f"  [bold]Hyp[{details['hyp_idx']}]:[/bold] '{details['alto_word']}' → LLM: '{details['llm_token']}'")
            
            if details['missing_left']:
                console.print(f"    [red]Left neighbor:[/red]")
                if details['expected_left']:
                    console.print(f"      Expected LLM token: [green]'{details['expected_left']}'[/green]")
                else:
                    console.print(f"      Expected: [dim]N/A (at start)[/dim]")
                
                if details['left_matched_word']:
                    console.print(f"      Linked to ALTO: [yellow]'{details['left_matched_word']}'[/yellow]")
                    if details['actual_left_token']:
                        console.print(f"      Which has LLM token: [yellow]'{details['actual_left']}'[/yellow]")
                        # Check if token objects match (not just word strings)
                        if details['expected_left_token']:
                            if details['actual_left_token'] != details['expected_left_token']:
                                if details['expected_left'] == details['actual_left']:
                                    # Words match but different token instances = duplicate words in text
                                    console.print(f"      [yellow]⚠ WORD MATCHES but wrong instance:[/yellow] '{details['actual_left']}'")
                                    console.print(f"         The neighbor matched to a different instance of the same word in the clean text.")
                                    console.print(f"         This indicates duplicate words or incorrect sequence matching.")
                                else:
                                    # Different words entirely
                                    console.print(f"      [red]✗ MISMATCH: Expected '{details['expected_left']}' but got '{details['actual_left']}'[/red]")
                            else:
                                console.print(f"      [green]✓ Token objects match correctly![/green]")
                    else:
                        console.print(f"      Which has LLM token: [red]NONE (PENDING)[/red]")
                else:
                    console.print(f"      [red]✗ No link established[/red]")
                    # Show spatial neighbor info to help debug
                    if details['spatial_left_alto']:
                        console.print(f"      Spatial ALTO neighbor: [dim]'{details['spatial_left_alto']}'[/dim]")
                        # Try to find this neighbor in hypothesis list
                        spatial_neighbor_hyp = None
                        for hyp in hypothesis_list:
                            if text_utils.decode_html_entities(hyp.anchor.content) == details['spatial_left_alto']:
                                spatial_neighbor_hyp = hyp
                                break
                        if spatial_neighbor_hyp:
                            neighbor_idx = hypothesis_list.index(spatial_neighbor_hyp)
                            if spatial_neighbor_hyp.chosen_LLM_token:
                                console.print(f"        → Found as Hyp[{neighbor_idx}] with LLM: '{spatial_neighbor_hyp.chosen_LLM_token.word}'")
                                if spatial_neighbor_hyp.chosen_LLM_token.word == details['expected_left']:
                                    console.print(f"        [yellow]⚠ Word matches but link not established - likely token object mismatch[/yellow]")
                                else:
                                    console.print(f"        [yellow]⚠ Has different LLM token than expected[/yellow]")
                            else:
                                console.print(f"        → Found as Hyp[{neighbor_idx}] but [red]PENDING (no chosen_LLM_token)[/red]")
                        else:
                            console.print(f"        → [red]Not found in hypothesis list[/red]")
                    else:
                        console.print(f"      [dim]No spatial ALTO neighbor defined (anchor.before_word is None)[/dim]")
            
            if details['missing_right']:
                console.print(f"    [red]Right neighbor:[/red]")
                if details['expected_right']:
                    console.print(f"      Expected LLM token: [green]'{details['expected_right']}'[/green]")
                else:
                    console.print(f"      Expected: [dim]N/A (at end)[/dim]")
                
                if details['right_matched_word']:
                    console.print(f"      Linked to ALTO: [yellow]'{details['right_matched_word']}'[/yellow]")
                    if details['actual_right_token']:
                        console.print(f"      Which has LLM token: [yellow]'{details['actual_right']}'[/yellow]")
                        # Check if token objects match (not just word strings)
                        if details['expected_right_token']:
                            if details['actual_right_token'] != details['expected_right_token']:
                                if details['expected_right'] == details['actual_right']:
                                    # Words match but different token instances = duplicate words in text
                                    console.print(f"      [yellow]⚠ WORD MATCHES but wrong instance:[/yellow] '{details['actual_right']}'")
                                    console.print(f"         The neighbor matched to a different instance of the same word in the clean text.")
                                    console.print(f"         This indicates duplicate words or incorrect sequence matching.")
                                else:
                                    # Different words entirely
                                    console.print(f"      [red]✗ MISMATCH: Expected '{details['expected_right']}' but got '{details['actual_right']}'[/red]")
                            else:
                                console.print(f"      [green]✓ Token objects match correctly![/green]")
                    else:
                        console.print(f"      Which has LLM token: [red]NONE (PENDING)[/red]")
                else:
                    console.print(f"      [red]✗ No link established[/red]")
            
            console.print()  # Blank line between entries
        
        if len(pending_details_list) > 20:
            console.print(f"    ... and {len(pending_details_list) - 20} more PENDING words\n")
    
    # Show unmatched items
    unmatched_llm = [llm for llm in llm_elements if id(llm) not in matched_llm_token_ids]
    unmatched_hyp = [hyp for hyp in hypothesis_list if not hyp.chosen_LLM_token]
    
    console.print(f"\n[bold]Summary:[/bold]")
    console.print(f"  Total Hypotheses: {len(hypothesis_list)}")
    console.print(f"  Total LLM Tokens: {len(llm_elements)}")
    console.print(f"  Matched Hypotheses: [green]{len(matched_llm_token_ids)}[/green]")
    console.print(f"  Unmatched Hypotheses: [yellow]{len(unmatched_hyp)}[/yellow]")
    console.print(f"  Unmatched LLM Tokens: [yellow]{len(unmatched_llm)}[/yellow]")
    
    if unmatched_llm and len(unmatched_llm) <= 20:
        console.print(f"\n[bold yellow]Unmatched LLM Tokens:[/bold yellow]")
        for llm in unmatched_llm[:20]:
            idx = llm_elements.index(llm) if llm in llm_elements else "?"
            console.print(f"  [{idx}] '{llm.word}'")
    
    if unmatched_hyp and len(unmatched_hyp) <= 20:
        console.print(f"\n[bold yellow]Unmatched Hypotheses:[/bold yellow]")
        for hyp in unmatched_hyp[:20]:
            alto_str = text_utils.decode_html_entities(hyp.anchor.content)
            idx = hypothesis_list.index(hyp)
            status = "ERROR" if hyp.flagged_for_error else ("PENDING" if hyp.candidates else "NO CAND")
            console.print(f"  Hyp[{idx}]: '{alto_str}' ({status})")


def create_pdf_table_from_data(
    headers: List[str],
    rows: List[List[str]],
    title: Optional[str] = None,
    max_width: float = 7.5 * inch,
    font_size: int = 9,
    header_font_size: int = 10
) -> List:
    """
    Create PDF table elements from extracted table data.
    Handles text wrapping and returns a list of PDF elements.
    
    Args:
        headers: List of header strings
        rows: List of row data (each row is a list of strings)
        title: Optional title for the table
        max_width: Maximum width for the table
        font_size: Font size for table cells
        header_font_size: Font size for headers
        
    Returns:
        List of PDF elements (Paragraphs, Tables, Spacers)
    """
    if not REPORTLAB_AVAILABLE:
        console.print("[yellow]reportlab not available. Install with: pip install reportlab[/yellow]")
        return []
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Add title if provided
    if title:
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=14,
            textColor=colors.HexColor('#1f77b4'),
            spaceAfter=12,
            alignment=TA_CENTER
        )
        elements.append(Paragraph(title, title_style))
        elements.append(Spacer(1, 0.2 * inch))
    
    if not headers or not rows:
        return elements
    
    # Calculate column widths
    # Distribute available width evenly, but allow for content-based adjustment
    num_cols = len(headers)
    base_col_width = max_width / num_cols
    
    # Adjust column widths based on content
    col_widths = []
    for i in range(num_cols):
        # Find max content width for this column
        max_content = max(
            len(str(headers[i])) if i < len(headers) else 0,
            max((len(str(row[i])) if i < len(row) else 0) for row in rows[:50])  # Sample first 50 rows
        )
        # Use base width but ensure minimum readability
        col_width = max(base_col_width * 0.8, min(base_col_width * 1.5, max_content * 0.1 * inch))
        col_widths.append(col_width)
    
    # Normalize widths to fit max_width
    total_width = sum(col_widths)
    if total_width > max_width:
        col_widths = [w * (max_width / total_width) for w in col_widths]
    else:
        # Distribute remaining space
        remaining = max_width - total_width
        col_widths = [w + (remaining / num_cols) for w in col_widths]
    
    # Create cell style for wrapping text
    cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontSize=font_size,
        leading=font_size * 1.2,
        alignment=TA_LEFT
    )
    
    header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontSize=header_font_size,
        leading=header_font_size * 1.2,
        textColor=colors.HexColor('#1f77b4'),
        alignment=TA_LEFT,
        fontName='Helvetica-Bold'
    )
    
    # Prepare table data with wrapped text
    table_data = []
    
    # Add headers
    header_row = []
    for header in headers:
        header_para = Paragraph(str(header), header_style)
        header_row.append(header_para)
    table_data.append(header_row)
    
    # Add rows with text wrapping
    for row in rows:
        row_data = []
        for i, cell in enumerate(row):
            # Wrap text in Paragraph for proper rendering
            cell_para = Paragraph(str(cell), cell_style)
            row_data.append(cell_para)
        table_data.append(row_data)
    
    # Create PDF table
    pdf_table = PDFTable(table_data, colWidths=col_widths, repeatRows=1)
    
    # Style the table
    table_style = TableStyle([
        # Header styling
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8f4f8')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#1f77b4')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), header_font_size),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('TOPPADDING', (0, 0), (-1, 0), 12),
        
        # Cell styling
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), font_size),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        
        # Alternating row colors
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')]),
    ])
    
    pdf_table.setStyle(table_style)
    elements.append(pdf_table)
    elements.append(Spacer(1, 0.3 * inch))
    
    return elements


def export_llm_token_mapping_to_pdf(
    hypothesis_list: List[TokenHypotheses],
    llm_elements: List[LLMToken],
    output_path: str,
    max_display: int = 100,
    original_alto_content_by_id: Optional[Dict[int, str]] = None
):
    """
    Export the LLM token mapping table to PDF.
    
    Args:
        hypothesis_list: List of all TokenHypotheses
        llm_elements: List of all LLM tokens
        output_path: Path to save the PDF file
        max_display: Maximum number of rows to display
        original_alto_content_by_id: Optional mapping of anchor ID to original ALTO content
    """
    import text_utils
    
    # Build mapping from LLM tokens to hypotheses
    llm_to_hypotheses: Dict[int, List[TokenHypotheses]] = {}
    llm_id_to_token: Dict[int, LLMToken] = {}
    for hyp in hypothesis_list:
        if hyp.chosen_LLM_token:
            llm_id = id(hyp.chosen_LLM_token)
            if llm_id not in llm_to_hypotheses:
                llm_to_hypotheses[llm_id] = []
                llm_id_to_token[llm_id] = hyp.chosen_LLM_token
            llm_to_hypotheses[llm_id].append(hyp)
    
    # Build table data directly
    headers = ["#", "Hypothesis Index", "Original ALTO Word", "ALTO Word(s)", "→", "LLM Token", "LLM Index", "Status", "Links", "Conflict?"]
    rows = []
    
    # Track conflicts
    conflicts = []
    matched_llm_token_ids = set()
    
    for display_idx, hypothesis in enumerate(hypothesis_list[:max_display], 1):
        hyp_idx = display_idx - 1
        
        # Get original ALTO word(s) (before any splits/merges)
        # For merged words, show all original words that were merged
        original_alto_str = ""
        if hypothesis.candidates and hypothesis.candidates[0].alto_words and len(hypothesis.candidates[0].alto_words) > 1:
            # Merged word - get original content for each ALTO word
            original_parts = []
            for alto_word in hypothesis.candidates[0].alto_words:
                if original_alto_content_by_id:
                    alto_id = id(alto_word)
                    if alto_id in original_alto_content_by_id:
                        original_parts.append(original_alto_content_by_id[alto_id])
                    else:
                        original_parts.append(text_utils.decode_html_entities(alto_word.content))
                else:
                    original_parts.append(text_utils.decode_html_entities(alto_word.content))
            original_alto_str = " + ".join(original_parts)
        elif original_alto_content_by_id:
            # Single word - check if it was split
            anchor_id = id(hypothesis.anchor)
            if anchor_id in original_alto_content_by_id:
                original_content = original_alto_content_by_id[anchor_id]
                current_content = text_utils.decode_html_entities(hypothesis.anchor.content)
                # Only show if different (was split)
                if original_content != current_content:
                    original_alto_str = original_content
        if not original_alto_str:
            # No original or same as current - show current
            original_alto_str = text_utils.decode_html_entities(hypothesis.anchor.content)
        
        # Get ALTO word(s) - current state (may be merged)
        alto_words_str = ""
        if hypothesis.candidates and hypothesis.candidates[0].alto_words:
            alto_words = [text_utils.decode_html_entities(w.content) for w in hypothesis.candidates[0].alto_words]
            alto_words_str = " + ".join(alto_words) if len(alto_words) > 1 else alto_words[0]
        else:
            alto_words_str = text_utils.decode_html_entities(hypothesis.anchor.content)
        
        # Get LLM token info
        if hypothesis.chosen_LLM_token:
            llm_token = hypothesis.chosen_LLM_token
            llm_token_str = llm_token.word
            # Find LLM token index
            llm_index = None
            for idx, llm in enumerate(llm_elements):
                if llm == llm_token:
                    llm_index = idx
                    break
            llm_index_str = str(llm_index) if llm_index is not None else "?"
            
            # Check for conflicts
            llm_id = id(llm_token)
            if llm_id in matched_llm_token_ids:
                if len(llm_to_hypotheses.get(llm_id, [])) > 1:
                    conflict_str = "⚠ YES"
                    conflicts.append((hypothesis, llm_token, llm_to_hypotheses[llm_id]))
                else:
                    conflict_str = "No"
            else:
                matched_llm_token_ids.add(llm_id)
                if len(llm_to_hypotheses.get(llm_id, [])) > 1:
                    conflict_str = "⚠ YES"
                    conflicts.append((hypothesis, llm_token, llm_to_hypotheses[llm_id]))
                else:
                    conflict_str = "No"
            
            # Check status - verify neighbors are linked AND have correct LLM tokens
            missing_left = False
            if hypothesis.chosen_LLM_token.w_before is not None:
                if hypothesis.left_matched is None:
                    missing_left = True
                elif (hypothesis.left_matched.chosen_LLM_token is None or
                      hypothesis.left_matched.chosen_LLM_token != hypothesis.chosen_LLM_token.w_before):
                    missing_left = True
            
            missing_right = False
            if hypothesis.chosen_LLM_token.w_after is not None:
                if hypothesis.right_matched is None:
                    missing_right = True
                elif (hypothesis.right_matched.chosen_LLM_token is None or
                      hypothesis.right_matched.chosen_LLM_token != hypothesis.chosen_LLM_token.w_after):
                    missing_right = True
            
            if missing_left or missing_right:
                status = "⚠ PENDING"
            else:
                status = "✓ MATCHED"
        else:
            llm_token_str = "N/A"
            llm_index_str = "N/A"
            conflict_str = "N/A"
            if hypothesis.flagged_for_error:
                status = "✗ ERROR"
            elif hypothesis.candidates:
                status = "⚠ PENDING"
            else:
                status = "✗ NO CAND"
        
        # Get linking status
        left_link = "✓" if hypothesis.left_matched else "✗"
        right_link = "✓" if hypothesis.right_matched else "✗"
        links_str = f"L:{left_link} R:{right_link}"
        
        rows.append([
            str(display_idx),
            f"Hyp[{hyp_idx}]",
            original_alto_str,
            alto_words_str,
            "→",
            llm_token_str,
            llm_index_str,
            status,
            links_str,
            conflict_str
        ])
    
    # Export to PDF directly
    if not REPORTLAB_AVAILABLE:
        console.print("[yellow]reportlab not available. Install with: pip install reportlab[/yellow]")
        return
    
    # Create PDF document
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch
    )
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Add document title
    title_style = ParagraphStyle(
        'DocumentTitle',
        parent=styles['Title'],
        fontSize=18,
        textColor=colors.HexColor('#1f77b4'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    elements.append(Paragraph("LLM Token ↔ TokenHypotheses Mapping", title_style))
    elements.append(Spacer(1, 0.3 * inch))
    
    # Create PDF table elements
    table_elements = create_pdf_table_from_data(
        headers, rows, None, 7.5 * inch, 9, 10
    )
    elements.extend(table_elements)
    
    # Build PDF
    doc.build(elements)
    console.print(f"[green]PDF exported successfully to: {output_path}[/green]")


if __name__ == "__main__":
    # Example usage
    console.print("[bold]Visualization Module Loaded[/bold]")
    console.print("Import this module and use the visualization functions in your main script.")

