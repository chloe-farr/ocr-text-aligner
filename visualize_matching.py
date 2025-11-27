"""
Visualization tools for understanding the text matching and hyphen linking process.
Generated entirely by Cursor Agent with minimal instruction.
"""
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

import xml_obj as XMLOBJ
import text_utils
from map_up_text import TokenCandidate, TokenHypotheses, ALL_HYPOTHESES, LLMToken

console = Console() if RICH_AVAILABLE else Console()


def visualize_word_positions(page: XMLOBJ.Page, highlight_words: Optional[List[XMLOBJ.StringWord]] = None):
    """
    Create a spatial visualization of word positions on the page.
    
    Args:
        page: The page object to visualize
        highlight_words: Optional list of words to highlight (e.g., hyphenated words)
    """
    if not MATPLOTLIB_AVAILABLE:
        console.print("[yellow]matplotlib not available. Install with: pip install matplotlib[/yellow]")
        return None
    
    words = page.all_strings()
    # Use object identity (id) for comparison since StringWord objects aren't hashable
    highlight_ids = {id(w) for w in highlight_words} if highlight_words else set()
    
    fig, ax = plt.subplots(1, 1, figsize=(12, 16))
    
    # Draw all words as rectangles
    for word in words:
        is_highlighted = id(word) in highlight_ids
        color = 'red' if is_highlighted else 'lightblue'
        alpha = 0.7 if is_highlighted else 0.3
        
        rect = patches.Rectangle(
            (word.hpos, word.vpos),
            word.width,
            word.height,
            linewidth=1,
            edgecolor='black' if is_highlighted else 'gray',
            facecolor=color,
            alpha=alpha
        )
        ax.add_patch(rect)
        
        # Add text label (truncated if too long)
        label = word.content[:15] if len(word.content) > 15 else word.content
        ax.text(
            word.hpos + word.width/2,
            word.vpos + word.height/2,
            label,
            fontsize=6,
            ha='center',
            va='center',
            weight='bold' if is_highlighted else 'normal'
        )
    
    ax.set_xlim(0, page.width)
    ax.set_ylim(page.height, 0)  # Invert y-axis for image coordinates
    ax.set_aspect('equal')
    ax.set_xlabel('Horizontal Position (HPOS)')
    ax.set_ylabel('Vertical Position (VPOS)')
    ax.set_title('Word Positions on Page\n(Red = Highlighted, Blue = Normal)')
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    return fig


def print_hyphen_analysis(page: XMLOBJ.Page, vocab: set[str]):
    """
    Print a detailed analysis of hyphenated words and their potential matches.
    """
    from map_up_text import best_fuzzy_match_rapid
    from text_utils import is_hyphenish, normalize_for_matching
    
    words = list(page.all_strings())
    hyphen_words = [w for w in words if is_hyphenish(w)]
    
    if not hyphen_words:
        console.print("[yellow]No hyphenated words found on this page.[/yellow]")
        return
    
    console.print(f"\n[bold cyan]Found {len(hyphen_words)} hyphenated word(s):[/bold cyan]\n")
    
    for i, w1 in enumerate(hyphen_words):
        idx = words.index(w1)
        base1 = w1.content.rstrip("-–—")
        
        # Show context (neighbors)
        prev_word = words[idx - 1] if idx > 0 else None
        next_words = words[idx + 1:idx + 6]  # Look ahead 5 words
        
        # Create a tree structure
        tree = Tree(f"[bold red]{w1.content}[/bold red] (pos: {w1.hpos}, {w1.vpos})")
        
        if prev_word:
            tree.add(f"[dim]Previous:[/dim] {prev_word.content}")
        
        candidates_branch = tree.add("[bold]Potential Partners:[/bold]")
        
        for j, w2 in enumerate(next_words):
            merged = base1 + w2.content
            merged_norm = normalize_for_matching(merged)
            
            if not merged_norm:
                continue
            
            # Check hard match
            is_hard_match = merged_norm in vocab
            fuzzy_match = best_fuzzy_match_rapid(merged_norm, vocab, cutoff=80.0) if not is_hard_match else None
            
            match_status = ""
            if is_hard_match:
                match_status = f"[green]✓ HARD MATCH[/green] → '{merged_norm}'"
            elif fuzzy_match:
                match_status = f"[yellow]~ FUZZY MATCH[/yellow] → '{fuzzy_match.clean_form}' (score: {fuzzy_match.fuzzy_score:.1f}%)"
            else:
                match_status = "[dim]✗ No match[/dim]"
            
            candidates_branch.add(
                f"[{j+1}] {w2.content} → merged: '{merged}' → {match_status}"
            )
        
        console.print(Panel(tree, title=f"Hyphen Word #{i+1}", border_style="cyan"))
        console.print()


def print_matching_table(page: XMLOBJ.Page, vocab: set[str], max_words: int = 20):
    """
    Print a table showing OCR words and their best matches.
    """
    from text_utils import normalize_for_matching
    from map_up_text import best_fuzzy_match_rapid
    
    words = list(page.all_strings())[:max_words]
    
    table = Table(title="OCR Word Matching Analysis", show_header=True, header_style="bold magenta")
    table.add_column("Index", style="dim", width=6)
    table.add_column("OCR Word", style="cyan", width=20)
    table.add_column("Normalized", style="blue", width=20)
    table.add_column("In Vocab?", width=10)
    table.add_column("Best Match", style="green", width=20)
    table.add_column("Score", width=8)
    table.add_column("Position", style="dim", width=15)
    
    for idx, word in enumerate(words):
        norm = normalize_for_matching(word.content)
        in_vocab = "✓" if norm in vocab else "✗"
        
        match = best_fuzzy_match_rapid(norm, vocab, cutoff=80.0) if norm not in vocab else None
        best_match = norm if norm in vocab else (match.clean_form if match else "N/A")
        score = "100%" if norm in vocab else (f"{match.fuzzy_score:.1f}%" if match else "N/A")
        
        pos_str = f"({word.hpos}, {word.vpos})"
        
        table.add_row(
            str(idx),
            word.content,
            norm,
            in_vocab,
            best_match,
            score,
            pos_str
        )
    
    console.print(table)


def visualize_hyphen_linking_process(page: XMLOBJ.Page, vocab: set[str]):
    """
    Show a step-by-step visualization of the hyphen linking process.
    """
    from map_up_text import best_fuzzy_match_rapid
    from text_utils import is_hyphenish, normalize_for_matching
    
    words = list(page.all_strings())
    hyphen_words = [w for w in words if is_hyphenish(w)]
    
    console.print("\n[bold cyan]=" * 60)
    console.print("[bold cyan]HYPHEN LINKING PROCESS VISUALIZATION[/bold cyan]")
    console.print("[bold cyan]=" * 60 + "\n")
    
    for step, w1 in enumerate(hyphen_words, 1):
        idx = words.index(w1)
        base1 = w1.content.rstrip("-–—")
        
        console.print(f"\n[bold yellow]Step {step}: Processing hyphen word[/bold yellow]")
        console.print(f"  Word: [red]{w1.content}[/red]")
        console.print(f"  Base (after stripping hyphen): [blue]{base1}[/blue]")
        console.print(f"  Position in text: word #{idx}")
        console.print(f"  Spatial position: ({w1.hpos}, {w1.vpos})")
        
        # Show candidates
        console.print(f"\n  [bold]Searching for partners (next 5 words):[/bold]")
        
        candidates = []
        for j in range(idx + 1, min(idx + 6, len(words))):
            w2 = words[j]
            merged = base1 + w2.content
            merged_norm = normalize_for_matching(merged)
            
            if not merged_norm:
                continue
            
            is_hard = merged_norm in vocab
            fuzzy = best_fuzzy_match_rapid(merged_norm, vocab, cutoff=80.0) if not is_hard else None
            
            candidates.append({
                'partner': w2,
                'merged': merged,
                'merged_norm': merged_norm,
                'is_hard_match': is_hard,
                'fuzzy_match': fuzzy,
                'distance': j - idx
            })
        
        # Display candidates in a table
        cand_table = Table(show_header=True, header_style="bold")
        cand_table.add_column("Partner", style="cyan")
        cand_table.add_column("Merged", style="blue")
        cand_table.add_column("Normalized", width=20)
        cand_table.add_column("Match Type", width=15)
        cand_table.add_column("Score", width=10)
        cand_table.add_column("Distance", width=8)
        
        for cand in candidates:
            match_type = "[green]HARD[/green]" if cand['is_hard_match'] else (
                "[yellow]FUZZY[/yellow]" if cand['fuzzy_match'] else "[dim]NONE[/dim]"
            )
            score = "100%" if cand['is_hard_match'] else (
                f"{cand['fuzzy_match'].fuzzy_score:.1f}%" if cand['fuzzy_match'] else "N/A"
            )
            
            cand_table.add_row(
                cand['partner'].content,
                cand['merged'],
                cand['merged_norm'],
                match_type,
                score,
                str(cand['distance'])
            )
        
        console.print(cand_table)
        
        # Highlight best candidate
        hard_matches = [c for c in candidates if c['is_hard_match']]
        fuzzy_matches = [c for c in candidates if c['fuzzy_match']]
        
        if hard_matches:
            best = hard_matches[0]
            console.print(f"\n  [bold green]✓ BEST MATCH (HARD):[/bold green] '{best['merged_norm']}'")
            console.print(f"     Partner: {best['partner'].content}")
        elif fuzzy_matches:
            best = max(fuzzy_matches, key=lambda c: c['fuzzy_match'].fuzzy_score)
            console.print(f"\n  [bold yellow]~ BEST MATCH (FUZZY):[/bold yellow] '{best['fuzzy_match'].clean_form}'")
            console.print(f"     Partner: {best['partner'].content}")
            console.print(f"     Score: {best['fuzzy_match'].fuzzy_score:.1f}%")
        else:
            console.print(f"\n  [bold red]✗ NO MATCH FOUND[/bold red]")
        
        console.print("\n" + "-" * 60)


def print_vocab_stats(vocab: set[str], clean_text: str):
    """
    Print statistics about the vocabulary.
    """
    from collections import Counter
    from text_utils import normalize_for_matching
    
    clean_tokens = [normalize_for_matching(t) for t in clean_text.split()]
    clean_freq = Counter(clean_tokens)
    
    console.print("\n[bold cyan]Vocabulary Statistics:[/bold cyan]")
    console.print(f"  Total unique words: {len(vocab)}")
    console.print(f"  Total word tokens: {len(clean_tokens)}")
    console.print(f"  Most common words:")
    
    for word, count in clean_freq.most_common(10):
        console.print(f"    {word}: {count}")


def create_summary_dashboard(page: XMLOBJ.Page, vocab: set[str], clean_text: str):
    """
    Create a comprehensive summary dashboard.
    """
    from text_utils import is_hyphenish, normalize_for_matching
    
    words = list(page.all_strings())
    hyphen_words = [w for w in words if is_hyphenish(w)]
    
    # Count matches
    exact_matches = sum(1 for w in words if normalize_for_matching(w.content) in vocab)
    total_words = len(words)
    
    console.print("\n" + "=" * 70)
    console.print("[bold cyan]TEXT MATCHING DASHBOARD[/bold cyan]")
    console.print("=" * 70)
    
    # Summary stats
    stats_table = Table(show_header=False, box=None)
    stats_table.add_column("Metric", style="bold")
    stats_table.add_column("Value", style="cyan")
    
    stats_table.add_row("Total OCR words", str(total_words))
    stats_table.add_row("Exact vocabulary matches", f"{exact_matches} ({exact_matches/total_words*100:.1f}%)")
    stats_table.add_row("Hyphenated words found", str(len(hyphen_words)))
    stats_table.add_row("Vocabulary size", str(len(vocab)))
    
    console.print(stats_table)
    console.print()


def visualize_pipeline_for_hypothesis(hypothesis: TokenHypotheses, index: int = None):
    """
    Visualize the complete matching pipeline for a single hypothesis:
    ALTO word → TokenCandidate (fuzzy match) → LLM candidates (fuzzy) → LLM candidates (context) → Final selection
    """
    idx_str = f"#{index}" if index is not None else ""
    alto_word = hypothesis.anchor
    decoded_content = text_utils.decode_html_entities(alto_word.content)
    
    console.print(f"\n[bold cyan]{'='*80}[/bold cyan]")
    console.print(f"[bold cyan]HYPOTHESIS {idx_str}: ALTO Word → Pipeline[/bold cyan]")
    console.print(f"[bold cyan]{'='*80}[/bold cyan]\n")
    
    # Step 1: ALTO Word
    console.print(f"[bold yellow]Step 1: ALTO Word[/bold yellow]")
    console.print(f"  Content: [red]{alto_word.content}[/red]")
    console.print(f"  Decoded: [blue]{decoded_content}[/blue]")
    console.print(f"  Position: ({alto_word.hpos}, {alto_word.vpos})")
    console.print(f"  Flagged for error: [{'red' if hypothesis.flagged_for_error else 'green'}]{hypothesis.flagged_for_error}[/]")
    
    if not hypothesis.candidates:
        console.print(f"\n  [bold red]✗ No candidates found[/bold red]")
        return
    
    # Step 2: Token Candidates (fuzzy matches)
    console.print(f"\n[bold yellow]Step 2: Token Candidates (Fuzzy Matches)[/bold yellow]")
    console.print(f"  Found {len(hypothesis.candidates)} candidate(s):\n")
    
    for i, candidate in enumerate(hypothesis.candidates):
        status = "[bold green]✓ SELECTED[/bold green]" if i == hypothesis.chosen_index else ""
        console.print(f"  [bold]Candidate {i+1}:[/bold] {status}")
        console.print(f"    Clean form: [cyan]{candidate.clean_form}[/cyan]")
        console.print(f"    Fuzzy score: [yellow]{candidate.fuzzy_score:.1f}%[/yellow]")
        console.print(f"    Kind: {candidate.kind}")
        console.print(f"    ALTO words: {len(candidate.alto_words)} word(s)")
        
        # Step 3: LLM Candidates by Fuzzy Match
        if candidate.possible_llm_elements_by_fuzzy_match:
            console.print(f"    [dim]→ LLM candidates (fuzzy match): {len(candidate.possible_llm_elements_by_fuzzy_match)}[/dim]")
            for j, llm_elem in enumerate(candidate.possible_llm_elements_by_fuzzy_match[:3]):  # Show first 3
                marker = "[bold green]★[/bold green]" if llm_elem == hypothesis.chosen_LLM_token else ""
                before_word = llm_elem.w_before.word if llm_elem.w_before else "N/A"
                after_word = llm_elem.w_after.word if llm_elem.w_after else "N/A"
                console.print(f"      [{j+1}] {marker} '{llm_elem.word}'; {llm_elem.word_normalized}; {before_word}, {after_word}")
            if len(candidate.possible_llm_elements_by_fuzzy_match) > 3:
                console.print(f"      ... and {len(candidate.possible_llm_elements_by_fuzzy_match) - 3} more")
        
        # Step 4: LLM Candidates by Context (with linguistic context positions)
        if candidate.possible_llm_elements_by_context:
            console.print(f"    [dim]→ LLM candidates (context match): {len(candidate.possible_llm_elements_by_context)}[/dim]")
            for j, (llm_elem, before_score, after_score) in enumerate(candidate.possible_llm_elements_by_context[:3]):  # Show first 3
                marker = "[bold green]★[/bold green]" if llm_elem == hypothesis.chosen_LLM_token else ""
                before_word = llm_elem.w_before.word if llm_elem.w_before else "N/A"
                after_word = llm_elem.w_after.word if llm_elem.w_after else "N/A"
                
                # Get ALTO context words
                before_alto = text_utils.decode_html_entities(candidate.alto_words[0].before_word.content) if candidate.alto_words and candidate.alto_words[0].before_word else "N/A"
                after_alto = text_utils.decode_html_entities(candidate.alto_words[-1].after_word.content) if candidate.alto_words and candidate.alto_words[-1].after_word else "N/A"
                
                console.print(f"      [{j+1}] {marker} '{llm_elem.word}'; {llm_elem.word_normalized}; {before_word}, {after_word}")
                console.print(f"          Context scores:")
                console.print(f"            Before: ALTO '{before_alto}' ↔ LLM '{before_word}' = [yellow]{before_score:.1f}%[/yellow]")
                console.print(f"            After:  ALTO '{after_alto}' ↔ LLM '{after_word}' = [yellow]{after_score:.1f}%[/yellow]")
            if len(candidate.possible_llm_elements_by_context) > 3:
                console.print(f"      ... and {len(candidate.possible_llm_elements_by_context) - 3} more")
    
    # Step 5: Final Selection
    console.print(f"\n[bold yellow]Step 5: Final Selection[/bold yellow]")
    if hypothesis.chosen_LLM_token:
        chosen_candidate = hypothesis.chosen
        console.print(f"  [bold green]✓ MATCHED[/bold green]")
        console.print(f"    Selected candidate: [cyan]{chosen_candidate.clean_form if chosen_candidate else 'N/A'}[/cyan]")
        console.print(f"    Selected LLM token: [green]'{hypothesis.chosen_LLM_token.word}'[/green]")
        console.print(f"    LLM token normalized: {hypothesis.chosen_LLM_token.word_normalized}")
        
        # Show neighbors
        before_alto_neighbor = text_utils.decode_html_entities(hypothesis.anchor.before_word.content) if hypothesis.anchor.before_word else "N/A"
        after_alto_neighbor = text_utils.decode_html_entities(hypothesis.anchor.after_word.content) if hypothesis.anchor.after_word else "N/A"
        before_llm_neighbor = hypothesis.chosen_LLM_token.w_before.word if hypothesis.chosen_LLM_token.w_before else "N/A"
        after_llm_neighbor = hypothesis.chosen_LLM_token.w_after.word if hypothesis.chosen_LLM_token.w_after else "N/A"
        
        console.print(f"\n    [dim]ALTO neighbors: ... '{before_alto_neighbor}' → '{decoded_content}' → '{after_alto_neighbor}' ...[/dim]")
        console.print(f"    [dim]LLM neighbors:  ... '{before_llm_neighbor}' → '{hypothesis.chosen_LLM_token.word}' → '{after_llm_neighbor}' ...[/dim]")
        
        # Show linking status
        left_linked = "✓" if hypothesis.left_matched else "✗"
        right_linked = "✓" if hypothesis.right_matched else "✗"
        console.print(f"    Linking: left={left_linked}, right={right_linked}")
    else:
        console.print(f"  [bold red]✗ NO MATCH SELECTED[/bold red]")
    
    # Show best candidates by context if available
    if hypothesis.best_candidates_by_context:
        console.print(f"\n[bold yellow]Best Candidates by Context:[/bold yellow]")
        if len(hypothesis.best_candidates_by_context) > 1:
            console.print(f"  [yellow]⚠ {len(hypothesis.best_candidates_by_context)} perfect matches found - awaiting proximity assessment[/yellow]")
        for i, (candidate, llm_elem, before_score, after_score) in enumerate(hypothesis.best_candidates_by_context, 1):
            marker = "[bold green]★[/bold green]" if llm_elem == hypothesis.chosen_LLM_token else ""
            console.print(f"  [{i}] {marker} Candidate: '{candidate.clean_form}' → LLM: '{llm_elem.word}'")
            console.print(f"      Full LLM token: '{llm_elem.word}'; {llm_elem.word_normalized}; {llm_elem.w_before.word if llm_elem.w_before else 'N/A'}, {llm_elem.w_after.word if llm_elem.w_after else 'N/A'}")
            console.print(f"      Context scores: before={before_score:.1f}%, after={after_score:.1f}%")
            
            # Show what ALTO words are being compared
            if candidate.alto_words:
                before_alto = text_utils.decode_html_entities(candidate.alto_words[0].before_word.content) if candidate.alto_words[0].before_word else "N/A"
                after_alto = text_utils.decode_html_entities(candidate.alto_words[-1].after_word.content) if candidate.alto_words[-1].after_word else "N/A"
                console.print(f"      ALTO context: '{before_alto}' → '{text_utils.decode_html_entities(hypothesis.anchor.content)}' → '{after_alto}'")
                console.print(f"      LLM context:  '{llm_elem.w_before.word if llm_elem.w_before else 'N/A'}' → '{llm_elem.word}' → '{llm_elem.w_after.word if llm_elem.w_after else 'N/A'}'")


def visualize_hyphenated_words_pipeline(hypothesis_list: List[TokenHypotheses], page: XMLOBJ.Page):
    """
    Visualize the pipeline specifically for hyphenated words, showing fuzzy matching.
    """
    from text_utils import is_hyphenish
    
    alto_words = list(page.all_strings())
    hyphen_words = [w for w in alto_words if is_hyphenish(w)]
    
    if not hyphen_words:
        console.print("[yellow]No hyphenated words found on this page.[/yellow]")
        return
    
    console.print(f"\n[bold cyan]{'='*80}[/bold cyan]")
    console.print(f"[bold cyan]HYPHENATED WORDS PIPELINE VISUALIZATION[/bold cyan]")
    console.print(f"[bold cyan]Found {len(hyphen_words)} hyphenated word(s)[/bold cyan]")
    console.print(f"[bold cyan]{'='*80}[/bold cyan]\n")
    
    for i, hyphen_word in enumerate(hyphen_words, 1):
        # Find corresponding hypothesis
        hypothesis = None
        for hyp in hypothesis_list:
            if hyp.anchor == hyphen_word:
                hypothesis = hyp
                break
        
        if not hypothesis:
            console.print(f"\n[bold red]Hyphen Word #{i}: {hyphen_word.content}[/bold red]")
            console.print(f"  [yellow]No hypothesis found for this word[/yellow]")
            continue
        
        decoded_content = text_utils.decode_html_entities(hyphen_word.content)
        base = decoded_content.rstrip("-–—")
        
        console.print(f"\n[bold yellow]Hyphen Word #{i}:[/bold yellow] [red]{hyphen_word.content}[/red]")
        console.print(f"  Base (stripped): [blue]{base}[/blue]")
        console.print(f"  Position: ({hyphen_word.hpos}, {hyphen_word.vpos})")
        
        # Show candidates with fuzzy matching
        if hypothesis.candidates:
            console.print(f"\n  [bold]Fuzzy Match Candidates:[/bold]")
            for j, candidate in enumerate(hypothesis.candidates[:5]):  # Show top 5
                marker = "[bold green]★[/bold green]" if j == hypothesis.chosen_index else ""
                console.print(f"    [{j+1}] {marker} '{candidate.clean_form}' (score: {candidate.fuzzy_score:.1f}%)")
                
                # Show if this is a merged word (hyphen case)
                if len(candidate.alto_words) > 1:
                    console.print(f"        [dim]→ Merged from {len(candidate.alto_words)} ALTO words[/dim]")
                    for alto_w in candidate.alto_words:
                        console.print(f"          - {text_utils.decode_html_entities(alto_w.content)}")
        else:
            console.print(f"  [red]✗ No candidates found[/red]")
        
        # Show final selection
        if hypothesis.chosen_LLM_token:
            console.print(f"\n  [bold green]✓ Final Selection:[/bold green]")
            console.print(f"    LLM Token: '{hypothesis.chosen_LLM_token.word}'")
            if hypothesis.chosen:
                console.print(f"    Candidate: '{hypothesis.chosen.clean_form}'")
        else:
            console.print(f"\n  [bold red]✗ No final selection[/bold red]")


def visualize_full_pipeline(hypothesis_list: List[TokenHypotheses], max_hypotheses: int = 20):
    """
    Visualize the complete pipeline for multiple hypotheses, showing the flow from
    ALTO elements → fuzzy matching → LLM candidates → context matching → final selection.
    """
    console.print(f"\n[bold cyan]{'='*80}[/bold cyan]")
    console.print(f"[bold cyan]FULL PIPELINE VISUALIZATION[/bold cyan]")
    console.print(f"[bold cyan]Showing first {min(max_hypotheses, len(hypothesis_list))} hypotheses[/bold cyan]")
    console.print(f"[bold cyan]{'='*80}[/bold cyan]\n")
    
    for i, hypothesis in enumerate(hypothesis_list[:max_hypotheses], 1):
        visualize_pipeline_for_hypothesis(hypothesis, index=i)
        if i < min(max_hypotheses, len(hypothesis_list)):
            console.print()  # Add spacing between hypotheses


def visualize_context_matching_details(hypothesis_list: List[TokenHypotheses], max_hypotheses: int = 10):
    """
    Detailed visualization of linguistic context matching with before/after positions.
    """
    console.print(f"\n[bold cyan]{'='*80}[/bold cyan]")
    console.print(f"[bold cyan]LINGUISTIC CONTEXT MATCHING DETAILS[/bold cyan]")
    console.print(f"[bold cyan]{'='*80}[/bold cyan]\n")
    
    shown = 0
    for hypothesis in hypothesis_list:
        if shown >= max_hypotheses:
            break
        
        # Only show hypotheses with context matches
        has_context = any(
            candidate.possible_llm_elements_by_context 
            for candidate in hypothesis.candidates
        )
        
        if not has_context:
            continue
        
        shown += 1
        alto_word = hypothesis.anchor
        decoded_content = text_utils.decode_html_entities(alto_word.content)
        
        console.print(f"\n[bold yellow]Hypothesis #{shown}:[/bold yellow] [red]{decoded_content}[/red]")
        
        for candidate in hypothesis.candidates:
            if not candidate.possible_llm_elements_by_context:
                continue
            
            console.print(f"\n  Candidate: [cyan]{candidate.clean_form}[/cyan]")
            
            # Get ALTO context
            if candidate.alto_words:
                before_alto = text_utils.decode_html_entities(candidate.alto_words[0].before_word.content) if candidate.alto_words[0].before_word else "N/A"
                after_alto = text_utils.decode_html_entities(candidate.alto_words[-1].after_word.content) if candidate.alto_words[-1].after_word else "N/A"
            else:
                before_alto = "N/A"
                after_alto = "N/A"
            
            console.print(f"    ALTO Context: [dim]... '{before_alto}' → '{decoded_content}' → '{after_alto}' ...[/dim]")
            
            # Show LLM context matches
            for llm_elem, before_score, after_score in candidate.possible_llm_elements_by_context[:3]:
                marker = "[bold green]★[/bold green]" if llm_elem == hypothesis.chosen_LLM_token else ""
                before_llm = llm_elem.w_before.word if llm_elem.w_before else "N/A"
                after_llm = llm_elem.w_after.word if llm_elem.w_after else "N/A"
                
                console.print(f"    {marker} LLM Context: [dim]... '{before_llm}' → '{llm_elem.word}' → '{after_llm}' ...[/dim]")
                console.print(f"        Match scores: before=[yellow]{before_score:.1f}%[/yellow], after=[yellow]{after_score:.1f}%[/yellow]")
                
                # Highlight perfect matches
                if before_score == 100 and after_score == 100:
                    console.print(f"        [bold green]✓ Perfect context match![/bold green]")


def visualize_hypothesis_sequence(hypothesis_list: List[TokenHypotheses], max_hypotheses: int = 30):
    """
    Show a sequential list of hypotheses showing the mapping from ALTO words to LLM tokens.
    This helps verify that words are properly mapped in order.
    """
    import text_utils
    
    console.print(f"\n[bold cyan]{'='*80}[/bold cyan]")
    console.print(f"[bold cyan]HYPOTHESIS SEQUENCE MAPPING[/bold cyan]")
    console.print(f"[bold cyan]Showing first {min(max_hypotheses, len(hypothesis_list))} hypotheses[/bold cyan]")
    console.print(f"[bold cyan]{'='*80}[/bold cyan]\n")
    
    # Create a table
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("ALTO Word(s)", style="red", width=25)
    table.add_column("→", style="dim", width=3, justify="center")
    table.add_column("LLM Token", style="green", width=25)
    table.add_column("Status", width=12)
    table.add_column("Links", width=10, justify="center")
    table.add_column("Notes", style="dim", width=20)
    
    for i, hypothesis in enumerate(hypothesis_list[:max_hypotheses], 1):
        # Get ALTO word(s)
        alto_words_str = ""
        if hypothesis.candidates and hypothesis.candidates[0].alto_words:
            alto_words = [text_utils.decode_html_entities(w.content) for w in hypothesis.candidates[0].alto_words]
            alto_words_str = " + ".join(alto_words) if len(alto_words) > 1 else alto_words[0]
        else:
            alto_words_str = text_utils.decode_html_entities(hypothesis.anchor.content)
        
        # Get LLM token
        if hypothesis.chosen_LLM_token:
            llm_token_str = hypothesis.chosen_LLM_token.word
            # Check if required neighbors are linked
            # A neighbor is "required" if the LLM token has w_before/w_after (not None)
            # but the corresponding link is missing
            missing_left = (hypothesis.chosen_LLM_token.w_before is not None and 
                          hypothesis.left_matched is None)
            missing_right = (hypothesis.chosen_LLM_token.w_after is not None and 
                           hypothesis.right_matched is None)
            
            if missing_left or missing_right:
                # Has chosen_LLM_token but missing required neighbors - mark as PENDING
                status = "[yellow]⚠ PENDING[/yellow]"
            else:
                status = "[bold green]✓ MATCHED[/bold green]"
        else:
            llm_token_str = "[dim]N/A[/dim]"
            if hypothesis.flagged_for_error:
                status = "[bold red]✗ ERROR[/bold red]"
            elif hypothesis.candidates:
                status = "[yellow]⚠ PENDING[/yellow]"
            else:
                status = "[red]✗ NO CAND[/red]"
        
        # Get linking status
        left_link = "✓" if hypothesis.left_matched else "✗"
        right_link = "✓" if hypothesis.right_matched else "✗"
        links_str = f"L:{left_link} R:{right_link}"
        
        # Get notes
        notes = []
        if len(hypothesis.candidates) > 0 and hypothesis.candidates[0].alto_words and len(hypothesis.candidates[0].alto_words) > 1:
            notes.append("hyphen")
        if hypothesis.candidates and len(hypothesis.candidates) > 1:
            notes.append(f"{len(hypothesis.candidates)} cands")
        if hypothesis.best_candidates_by_context:
            if len(hypothesis.best_candidates_by_context) > 1:
                notes.append(f"{len(hypothesis.best_candidates_by_context)} perfect")
            else:
                notes.append("1 perfect")
        notes_str = ", ".join(notes) if notes else ""
        
        table.add_row(
            str(i),
            alto_words_str,
            "→",
            llm_token_str,
            status,
            links_str,
            notes_str
        )
    
    console.print(table)
    
    # Show summary stats - count ALL hypotheses, not just displayed ones
    # Error = flagged_for_error AND no chosen_LLM_token (matches display logic)
    matched_count = sum(1 for h in hypothesis_list if h.chosen_LLM_token)
    error_count = sum(1 for h in hypothesis_list if h.flagged_for_error and not h.chosen_LLM_token)
    pending_count = sum(1 for h in hypothesis_list if h.candidates and not h.chosen_LLM_token and not h.flagged_for_error)
    linked_count = sum(1 for h in hypothesis_list if h.left_matched or h.right_matched)
    
    # Count displayed vs total
    displayed_matched = sum(1 for h in hypothesis_list[:max_hypotheses] if h.chosen_LLM_token)
    displayed_errors = sum(1 for h in hypothesis_list[:max_hypotheses] if h.flagged_for_error and not h.chosen_LLM_token)
    displayed_pending = sum(1 for h in hypothesis_list[:max_hypotheses] if h.candidates and not h.chosen_LLM_token and not h.flagged_for_error)
    
    console.print(f"\n[bold]Summary (showing first {max_hypotheses} of {len(hypothesis_list)}):[/bold]")
    console.print(f"  Matched: [green]{matched_count}[/green] ({displayed_matched} shown) | Errors: [red]{error_count}[/red] ({displayed_errors} shown) | Pending: [yellow]{pending_count}[/yellow] ({displayed_pending} shown) | Linked: [cyan]{linked_count}[/cyan]")


def visualize_llm_token_mapping_table(hypothesis_list: List[TokenHypotheses], llm_elements: List[LLMToken], max_display: int = 100):
    """
    Show a comprehensive table mapping LLM tokens to TokenHypotheses objects.
    This helps verify that mappings are correct and identify conflicts.
    
    Args:
        hypothesis_list: List of all TokenHypotheses
        llm_elements: List of all LLM tokens
        max_display: Maximum number of rows to display
    """
    console.print(f"\n[bold cyan]{'='*100}[/bold cyan]")
    console.print(f"[bold cyan]LLM TOKEN ↔ TOKENHYPOTHESES MAPPING TABLE[/bold cyan]")
    console.print(f"[bold cyan]{'='*100}[/bold cyan]\n")
    
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
    
    for display_idx, hypothesis in enumerate(hypothesis_list[:max_display], 1):
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
            
            # Check if required neighbors are linked
            missing_left = (hypothesis.chosen_LLM_token.w_before is not None and 
                          hypothesis.left_matched is None)
            missing_right = (hypothesis.chosen_LLM_token.w_after is not None and 
                           hypothesis.right_matched is None)
            
            if missing_left or missing_right:
                # Has chosen_LLM_token but missing required neighbors - mark as PENDING
                status = "[yellow]⚠ PENDING[/yellow]"
            else:
                status = "[bold green]✓ MATCHED[/bold green]"
        else:
            llm_token_str = "[dim]N/A[/dim]"
            llm_index_str = "[dim]N/A[/dim]"
            conflict_str = "[dim]N/A[/dim]"
            if hypothesis.flagged_for_error:
                status = "[bold red]✗ ERROR[/bold red]"
            elif hypothesis.candidates:
                status = "[yellow]⚠ PENDING[/yellow]"
            else:
                status = "[red]✗ NO CAND[/red]"
        
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


def visualize_word_merges_process(hypothesis_list_before: List[TokenHypotheses], hypothesis_list_after: List[TokenHypotheses]):
    """
    Visualize the word merge splitting process, showing:
    - Which words were flagged for error and split
    - How they were split
    - What candidates were found for each split
    - Linking results between adjacent splits
    - Final outcomes
    """
    import text_utils
    from map_up_text import ADVANCED_SPLIT_RE
    
    # Find hypotheses that were split (flagged in before, but not in after, or new ones)
    # Build a map of original anchor IDs to track splits
    before_anchors = {id(h.anchor): h for h in hypothesis_list_before if h.flagged_for_error}
    
    # Track which original hypotheses were split
    split_originals = []
    split_results = {}  # Map original anchor id -> list of split hypotheses
    
    # Check if any hypotheses were split by comparing counts and content
    for orig_hyp in hypothesis_list_before:
        if not orig_hyp.flagged_for_error:
            continue
        
        decoded_content = text_utils.decode_html_entities(orig_hyp.anchor.content)
        split_words = ADVANCED_SPLIT_RE.split(decoded_content)
        
        if len(split_words) > 1:
            # This one was likely split - find the resulting splits
            split_originals.append(orig_hyp)
            resulting_splits = []
            
            # Find split hypotheses that match the original position and content
            # The split function creates new StringWord objects with same position but different content
            for new_hyp in hypothesis_list_after:
                # Check if this new hypothesis is at the same position as the original
                if (new_hyp.anchor.hpos == orig_hyp.anchor.hpos and 
                    new_hyp.anchor.vpos == orig_hyp.anchor.vpos):
                    # Check if content matches one of the split words
                    new_decoded = text_utils.decode_html_entities(new_hyp.anchor.content)
                    # Also check if anchor ID matches (split function preserves ID)
                    if new_decoded in split_words or (hasattr(new_hyp.anchor, 'id') and 
                                                     hasattr(orig_hyp.anchor, 'id') and
                                                     new_hyp.anchor.id == orig_hyp.anchor.id):
                        if new_hyp not in resulting_splits:
                            resulting_splits.append(new_hyp)
            
            # Sort splits by their order in split_words to maintain sequence
            resulting_splits.sort(key=lambda h: split_words.index(text_utils.decode_html_entities(h.anchor.content)) 
                                  if text_utils.decode_html_entities(h.anchor.content) in split_words else 999)
            
            if resulting_splits:
                split_results[id(orig_hyp.anchor)] = (orig_hyp, resulting_splits)
    
    if not split_results:
        console.print("\n[yellow]No word merges were split in this round.[/yellow]")
        return
    
    console.print(f"\n[bold cyan]{'='*80}[/bold cyan]")
    console.print(f"[bold cyan]WORD MERGE SPLITTING PROCESS[/bold cyan]")
    console.print(f"[bold cyan]Found {len(split_results)} word(s) that were split[/bold cyan]")
    console.print(f"[bold cyan]{'='*80}[/bold cyan]\n")
    
    for orig_id, (original_hyp, split_hypotheses) in split_results.items():
        decoded_original = text_utils.decode_html_entities(original_hyp.anchor.content)
        split_words = ADVANCED_SPLIT_RE.split(decoded_original)
        
        console.print(f"\n[bold yellow]Original Word (Flagged for Error):[/bold yellow]")
        console.print(f"  Content: [red]{original_hyp.anchor.content}[/red]")
        console.print(f"  Decoded: [blue]{decoded_original}[/blue]")
        console.print(f"  Position: ({original_hyp.anchor.hpos}, {original_hyp.anchor.vpos})")
        console.print(f"  Split into: [cyan]{len(split_words)} word(s)[/cyan] → {split_words}")
        
        console.print(f"\n  [bold]Split Results:[/bold]")
        
        for i, split_hyp in enumerate(split_hypotheses):
            split_decoded = text_utils.decode_html_entities(split_hyp.anchor.content)
            console.print(f"\n    [bold]Split #{i+1}:[/bold] [cyan]{split_decoded}[/cyan]")
            
            if not split_hyp.candidates:
                console.print(f"      [red]✗ No candidates found[/red]")
                continue
            
            # Show candidates
            for j, candidate in enumerate(split_hyp.candidates[:3]):  # Show first 3
                marker = "[bold green]★[/bold green]" if j == split_hyp.chosen_index else ""
                console.print(f"      [{j+1}] {marker} Candidate: [cyan]{candidate.clean_form}[/cyan]")
                console.print(f"          Fuzzy score: {candidate.fuzzy_score:.1f}%")
                
                # Show LLM candidates
                if candidate.possible_llm_elements_by_fuzzy_match:
                    llm_count = len(candidate.possible_llm_elements_by_fuzzy_match)
                    console.print(f"          LLM candidates (fuzzy): {llm_count}")
                    for k, llm_elem in enumerate(candidate.possible_llm_elements_by_fuzzy_match[:2]):  # Show first 2
                        selected = "[bold green]★[/bold green]" if llm_elem == split_hyp.chosen_LLM_token else ""
                        console.print(f"            [{k+1}] {selected} '{llm_elem.word}' (normalized: {llm_elem.word_normalized})")
                        if llm_elem.w_before:
                            console.print(f"                Before: '{llm_elem.w_before.word}'")
                        if llm_elem.w_after:
                            console.print(f"                After: '{llm_elem.w_after.word}'")
                    if llm_count > 2:
                        console.print(f"            ... and {llm_count - 2} more")
                
                # Show context matching results
                if candidate.possible_llm_elements_by_context:
                    console.print(f"          LLM candidates (context): {len(candidate.possible_llm_elements_by_context)}")
                    for k, (llm_elem, before_score, after_score) in enumerate(candidate.possible_llm_elements_by_context[:2]):  # Show first 2
                        selected = "[bold green]★[/bold green]" if llm_elem == split_hyp.chosen_LLM_token else ""
                        console.print(f"            [{k+1}] {selected} '{llm_elem.word}'")
                        
                        # Get context words - use resolved values (chosen_LLM_token) when available
                        # This matches what the context matching function actually compares
                        before_alto_obj = candidate.alto_words[0].before_word if candidate.alto_words and candidate.alto_words[0].before_word else None
                        after_alto_obj = candidate.alto_words[-1].after_word if candidate.alto_words and candidate.alto_words[-1].after_word else None
                        
                        # Try to find the resolved value (from hypothesis lookup if this is a split word)
                        # For now, show ALTO content but note if it should be resolved
                        before_alto = text_utils.decode_html_entities(before_alto_obj.content) if before_alto_obj else "N/A"
                        after_alto = text_utils.decode_html_entities(after_alto_obj.content) if after_alto_obj else "N/A"
                        
                        # Check if this is a split word context (before/after might be from other splits)
                        # If so, show what was actually compared (which would be chosen_LLM_token if available)
                        # For visualization, show both the ALTO content and note if it was resolved
                        before_llm = llm_elem.w_before.word if llm_elem.w_before else "N/A"
                        after_llm = llm_elem.w_after.word if llm_elem.w_after else "N/A"
                        
                        console.print(f"                Context scores:")
                        console.print(f"                  Before: '{before_alto}' ↔ '{before_llm}' = [yellow]{before_score:.1f}%[/yellow]")
                        console.print(f"                  After:  '{after_alto}' ↔ '{after_llm}' = [yellow]{after_score:.1f}%[/yellow]")
                        # Note: For split words, the context matching uses chosen_LLM_token from adjacent splits when available
                        
                        if before_score == 100 and after_score == 100:
                            console.print(f"                  [bold green]✓ Perfect context match![/bold green]")
                    if len(candidate.possible_llm_elements_by_context) > 2:
                        console.print(f"            ... and {len(candidate.possible_llm_elements_by_context) - 2} more")
                elif candidate.possible_llm_elements_by_fuzzy_match:
                    console.print(f"          [yellow]⚠ No context matches found (check before/after words)[/yellow]")
            
            # Show final selection
            if split_hyp.chosen_LLM_token:
                console.print(f"      [bold green]✓ FINAL SELECTION:[/bold green] '{split_hyp.chosen_LLM_token.word}'")
            else:
                console.print(f"      [yellow]⚠ No final selection yet[/yellow]")
            
            # Show linking information
            if i > 0:
                prev_hyp = split_hypotheses[i-1]
                if prev_hyp.chosen_LLM_token and split_hyp.chosen_LLM_token:
                    if prev_hyp.chosen_LLM_token.w_after == split_hyp.chosen_LLM_token:
                        console.print(f"      [green]✓ Linked to previous split[/green]")
                    else:
                        console.print(f"      [yellow]⚠ Not linked to previous split[/yellow]")
        
        console.print("\n" + "-" * 80)
    
    # Summary statistics
    total_flagged = len([h for h in hypothesis_list_before if h.flagged_for_error])
    total_splits = sum(len(splits) for _, (_, splits) in split_results.items())
    successful_splits = sum(1 for _, (_, splits) in split_results.items() 
                           for s in splits if s.chosen_LLM_token is not None)
    
    console.print(f"\n[bold cyan]Summary:[/bold cyan]")
    console.print(f"  Total flagged for error: {total_flagged}")
    console.print(f"  Words that were split: {len(split_results)}")
    console.print(f"  Total split pieces created: {total_splits}")
    console.print(f"  Successfully matched splits: {successful_splits}")


def visualize_hyphen_linking_process(hypothesis_list_before: List[TokenHypotheses], hypothesis_list_after: List[TokenHypotheses]):
    """
    Visualize the hyphen linking process, showing which flagged words were combined.
    """
    import text_utils
    
    # Find hypotheses that were combined (flagged in before, not in after, or combined)
    # Track original flagged hypotheses
    before_flagged = {id(h.anchor): h for h in hypothesis_list_before if h.flagged_for_error}
    
    # Find combined hypotheses (have 2+ alto_words)
    combined_hypotheses = [h for h in hypothesis_list_after if len(h.candidates) > 0 and 
                          any(len(c.alto_words) >= 2 for c in h.candidates)]
    
    if not combined_hypotheses:
        console.print("\n[yellow]No hyphen pairs were linked in this round.[/yellow]")
        return
    
    console.print(f"\n[bold cyan]{'='*80}[/bold cyan]")
    console.print(f"[bold cyan]HYPHEN LINKING PROCESS[/bold cyan]")
    console.print(f"[bold cyan]Found {len(combined_hypotheses)} hyphen pair(s) linked[/bold cyan]")
    console.print(f"[bold cyan]{'='*80}[/bold cyan]\n")
    
    for i, combined_hyp in enumerate(combined_hypotheses, 1):
        # Find the candidate with multiple alto_words
        combined_candidate = None
        for candidate in combined_hyp.candidates:
            if len(candidate.alto_words) >= 2:
                combined_candidate = candidate
                break
        
        if not combined_candidate:
            continue
        
        word1 = combined_candidate.alto_words[0]
        word2 = combined_candidate.alto_words[1]
        
        decoded_w1 = text_utils.decode_html_entities(word1.content)
        decoded_w2 = text_utils.decode_html_entities(word2.content)
        is_literal_hyphen = decoded_w1.rstrip().endswith(("-", "-", "—", "--"))
        
        console.print(f"\n[bold yellow]Hyphen Pair #{i}:[/bold yellow]")
        console.print(f"  Word 1: [red]{word1.content}[/red] → [blue]{decoded_w1}[/blue]")
        console.print(f"  Word 2: [red]{word2.content}[/red] → [blue]{decoded_w2}[/blue]")
        console.print(f"  Literal hyphen: {'Yes' if is_literal_hyphen else 'No (OCR split error)'}")
        
        if is_literal_hyphen:
            base1 = decoded_w1.rstrip("-–—")
            merged = base1 + decoded_w2
        else:
            merged = decoded_w1 + decoded_w2
        
        merged_normalized = text_utils.normalize_for_matching(merged)
        console.print(f"  Combined: [cyan]{merged}[/cyan] → normalized: [cyan]{merged_normalized}[/cyan]")
        
        # Show matching results
        if combined_candidate:
            console.print(f"\n  [bold]Matching Results:[/bold]")
            console.print(f"    Clean form: [cyan]{combined_candidate.clean_form}[/cyan]")
            console.print(f"    Fuzzy score: {combined_candidate.fuzzy_score:.1f}%")
            
            if combined_candidate.possible_llm_elements_by_context:
                for llm_elem, before_score, after_score in combined_candidate.possible_llm_elements_by_context:
                    marker = "[bold green]★[/bold green]" if llm_elem == combined_hyp.chosen_LLM_token else ""
                    console.print(f"    {marker} LLM token: '{llm_elem.word}'")
                    
                    # Show context
                    before_alto = word1.before_word.content if word1.before_word else "N/A"
                    after_alto = word2.after_word.content if word2.after_word else "N/A"
                    before_llm = llm_elem.w_before.word if llm_elem.w_before else "N/A"
                    after_llm = llm_elem.w_after.word if llm_elem.w_after else "N/A"
                    
                    console.print(f"      Context scores:")
                    console.print(f"        Before: ALTO '{before_alto}' ↔ LLM '{before_llm}' = [yellow]{before_score:.1f}%[/yellow]")
                    console.print(f"        After:  ALTO '{after_alto}' ↔ LLM '{after_llm}' = [yellow]{after_score:.1f}%[/yellow]")
            
            if combined_hyp.chosen_LLM_token:
                console.print(f"\n  [bold green]✓ FINAL SELECTION:[/bold green] '{combined_hyp.chosen_LLM_token.word}'")
                
                # Show neighbors and linking status
                before_alto_neighbor = text_utils.decode_html_entities(word1.before_word.content) if word1.before_word else "N/A"
                after_alto_neighbor = text_utils.decode_html_entities(word2.after_word.content) if word2.after_word else "N/A"
                before_llm_neighbor = combined_hyp.chosen_LLM_token.w_before.word if combined_hyp.chosen_LLM_token.w_before else "N/A"
                after_llm_neighbor = combined_hyp.chosen_LLM_token.w_after.word if combined_hyp.chosen_LLM_token.w_after else "N/A"
                
                console.print(f"\n  [dim]ALTO neighbors: ... '{before_alto_neighbor}' → '{merged}' → '{after_alto_neighbor}' ...[/dim]")
                console.print(f"  [dim]LLM neighbors:  ... '{before_llm_neighbor}' → '{combined_hyp.chosen_LLM_token.word}' → '{after_llm_neighbor}' ...[/dim]")
                
                # Show linking status
                left_linked = "✓" if combined_hyp.left_matched else "✗"
                right_linked = "✓" if combined_hyp.right_matched else "✗"
                console.print(f"  Linking: left={left_linked}, right={right_linked}")
            else:
                console.print(f"\n  [yellow]⚠ No final selection[/yellow]")
        
        console.print("\n" + "-" * 80)
    
    # Summary
    total_flagged = len(before_flagged)
    total_combined = len(combined_hypotheses)
    successfully_matched = sum(1 for h in combined_hypotheses if h.chosen_LLM_token is not None)
    
    console.print(f"\n[bold cyan]Summary:[/bold cyan]")
    console.print(f"  Total flagged hypotheses: {total_flagged}")
    console.print(f"  Hyphen pairs linked: {total_combined}")
    console.print(f"  Successfully matched: {successfully_matched}")


if __name__ == "__main__":
    # Example usage
    console.print("[bold]Visualization Module Loaded[/bold]")
    console.print("Import this module and use the visualization functions in your main script.")

