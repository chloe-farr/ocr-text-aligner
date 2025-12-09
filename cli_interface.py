"""
CLI interface module for terminal-based pipeline interaction.

Provides prompts for stage approvals, file editing, and pipeline execution.
"""

import os
import sys
import subprocess
from typing import Optional, Dict, Any
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.text import Text

from pipeline_controller import PipelineController, PipelineStage

console = Console()


def prompt_stage_approval(stage_name: str, output_preview: Optional[str] = None,
                         output_files: Optional[list] = None) -> str:
    """
    Prompt user to approve, reject, or edit output from a pipeline stage.
    
    Args:
        stage_name: Name of the stage (e.g., "OCR", "LLM Cleaning")
        output_preview: Optional preview text to display
        output_files: Optional list of output file paths that can be edited
        
    Returns:
        User choice: "approve", "reject", or "edit"
    """
    console.print(f"\n[bold cyan]{'='*70}[/bold cyan]")
    console.print(f"[bold cyan]Stage: {stage_name}[/bold cyan]")
    console.print(f"[bold cyan]{'='*70}[/bold cyan]\n")
    
    if output_preview:
        # Show preview (truncate if too long)
        preview_text = output_preview
        if len(preview_text) > 1000:
            preview_text = preview_text[:1000] + "\n... (truncated)"
        
        console.print(Panel(preview_text, title="Output Preview", border_style="blue"))
        console.print()
    
    if output_files:
        console.print("[yellow]Output files:[/yellow]")
        for file_path in output_files:
            console.print(f"  - {file_path}")
        console.print()
    
    while True:
        choice = Prompt.ask(
            "[bold]What would you like to do?[/bold]",
            choices=["approve", "reject", "edit"],
            default="approve"
        )
        
        if choice == "edit" and output_files:
            # Allow editing
            edit_choice = Prompt.ask(
                "Which file would you like to edit?",
                choices=[str(i) for i in range(len(output_files))] + ["all", "cancel"],
                default="0"
            )
            
            if edit_choice == "cancel":
                continue
            elif edit_choice == "all":
                for file_path in output_files:
                    prompt_file_edit(file_path)
            else:
                idx = int(edit_choice)
                prompt_file_edit(output_files[idx])
            
            # After editing, ask again
            continue
        
        return choice


def prompt_file_edit(file_path: str) -> bool:
    """
    Open a file in the user's default editor and wait for save.
    
    Args:
        file_path: Path to file to edit
        
    Returns:
        True if file was edited, False otherwise
    """
    if not os.path.exists(file_path):
        console.print(f"[red]File not found: {file_path}[/red]")
        return False
    
    console.print(f"\n[yellow]Opening file in editor: {file_path}[/yellow]")
    console.print("[dim]Press Enter when you're done editing...[/dim]")
    
    # Try to determine default editor
    editor = os.environ.get('EDITOR', None)
    if editor is None:
        # Try common editors
        if sys.platform == 'darwin':  # macOS
            editor = 'open -e'  # TextEdit
        elif sys.platform.startswith('linux'):
            editor = 'nano'
        elif sys.platform == 'win32':
            editor = 'notepad'
        else:
            editor = 'nano'
    
    try:
        # Open file in editor
        if 'open -e' in editor:
            subprocess.run(['open', '-e', file_path])
        else:
            subprocess.run([editor, file_path])
        
        # Wait for user confirmation
        input()
        return True
    except Exception as e:
        console.print(f"[red]Failed to open editor: {e}[/red]")
        console.print(f"[yellow]Please edit the file manually: {file_path}[/yellow]")
        input("Press Enter when done...")
        return True


def run_cli_pipeline(config: Dict[str, Any]) -> None:
    """
    Run the pipeline with CLI prompts for approvals.
    
    Args:
        config: Configuration dictionary with pipeline settings
    """
    controller = PipelineController(config.get('output_dir', 'outputs'))
    
    console.print("[bold green]OCR Pipeline - CLI Mode[/bold green]\n")
    
    # Stage 1: Image Preparation
    if 'image_path' not in config:
        image_path = Prompt.ask("Enter path to input image")
        config['image_path'] = image_path
    
    console.print(f"\n[bold]Loading image: {config['image_path']}[/bold]")
    controller.set_image(config['image_path'], config.get('image_prep_config'))
    
    approval = prompt_stage_approval(
        "Image Preparation",
        output_preview=f"Image loaded: {controller.state.image.size if controller.state.image else 'N/A'}"
    )
    
    if approval == "reject":
        console.print("[red]Pipeline cancelled by user.[/red]")
        return
    
    # Stage 2: OCR
    console.print("\n[bold]Running Tesseract OCR...[/bold]")
    ocr_language = config.get('ocr_language', Prompt.ask("Tesseract language", default="eng"))
    
    try:
        ocr_results = controller.run_ocr(
            ocr_language,
            config.get('ocr_config'),
            config.get('generate_tesseract_pdf', False)
        )
        
        # Read plaintext preview
        plaintext_preview = None
        if controller.state.ocr_plaintext_path and os.path.exists(controller.state.ocr_plaintext_path):
            with open(controller.state.ocr_plaintext_path, 'r', encoding='utf-8') as f:
                content = f.read()
                plaintext_preview = content[:500] + "..." if len(content) > 500 else content
        
        output_files = [
            controller.state.ocr_plaintext_path,
            controller.state.ocr_xml_path,
            controller.state.ocr_hocr_path
        ]
        output_files = [f for f in output_files if f and os.path.exists(f)]
        
        approval = prompt_stage_approval(
            "OCR",
            output_preview=plaintext_preview,
            output_files=output_files
        )
        
        if approval == "reject":
            console.print("[red]Pipeline cancelled by user.[/red]")
            return
        
    except Exception as e:
        console.print(f"[red]OCR failed: {e}[/red]")
        return
    
    # Stage 3: LLM Cleaning
    console.print("\n[bold]LLM Text Cleaning[/bold]")
    
    # Check Ollama availability
    import llm_cleaning
    if not llm_cleaning.check_ollama_available(config.get('ollama_base_url', 'http://localhost:11434')):
        console.print("[red]Ollama is not running or not accessible.[/red]")
        console.print("[yellow]Please start Ollama and ensure the model is installed.[/yellow]")
        return
    
    # Get model
    available_models = llm_cleaning.get_available_models(config.get('ollama_base_url', 'http://localhost:11434'))
    if available_models:
        console.print(f"[green]Available models: {', '.join(available_models)}[/green]")
    
    model = config.get('llm_model', Prompt.ask("LLM model", default="qwen2.5"))
    
    # Get context
    context = config.get('llm_context')
    if context is None:
        context = Prompt.ask(
            "Additional context (optional, e.g., '1972 newspaper from New York')",
            default=""
        )
        if not context:
            context = None
    
    if not Confirm.ask("Run LLM cleaning?", default=True):
        console.print("[yellow]Skipping LLM cleaning.[/yellow]")
    else:
        try:
            console.print("\n[bold]Running LLM cleaning (this may take a while)...[/bold]")
            clean_text_path = controller.run_llm_cleaning(
                model,
                context,
                config.get('llm_system_prompt'),
                config.get('ollama_base_url', 'http://localhost:11434')
            )
            
            # Read cleaned text preview
            cleaned_preview = None
            if os.path.exists(clean_text_path):
                with open(clean_text_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    cleaned_preview = content[:500] + "..." if len(content) > 500 else content
            
            approval = prompt_stage_approval(
                "LLM Cleaning",
                output_preview=cleaned_preview,
                output_files=[clean_text_path]
            )
            
            if approval == "reject":
                console.print("[red]Pipeline cancelled by user.[/red]")
                return
            
            # Allow re-running
            while approval == "edit":
                if Confirm.ask("Re-run LLM cleaning with same settings?", default=False):
                    console.print("\n[bold]Re-running LLM cleaning...[/bold]")
                    clean_text_path = controller.run_llm_cleaning(
                        model,
                        context,
                        config.get('llm_system_prompt'),
                        config.get('ollama_base_url', 'http://localhost:11434')
                    )
                    
                    with open(clean_text_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        cleaned_preview = content[:500] + "..." if len(content) > 500 else content
                    
                    approval = prompt_stage_approval(
                        "LLM Cleaning",
                        output_preview=cleaned_preview,
                        output_files=[clean_text_path]
                    )
                else:
                    approval = "approve"
        
        except Exception as e:
            console.print(f"[red]LLM cleaning failed: {e}[/red]")
            return
    
    # Stage 4: Mapping
    console.print("\n[bold]Running text mapping...[/bold]")
    try:
        hypothesis_list, page = controller.run_mapping(
            show_ocr_accuracy=config.get('show_ocr_accuracy', False)
        )
        
        # Count errors
        error_count = sum(1 for h in hypothesis_list if h.flagged_for_error)
        matched_count = sum(1 for h in hypothesis_list if h.chosen_LLM_token is not None)
        total_count = len(hypothesis_list)
        
        console.print(f"\n[green]Mapping complete:[/green]")
        console.print(f"  Matched: {matched_count}/{total_count}")
        console.print(f"  Errors: {error_count}")
        
        approval = prompt_stage_approval(
            "Mapping",
            output_preview=f"Matched {matched_count}/{total_count} words. {error_count} errors flagged."
        )
        
        if approval == "reject":
            console.print("[red]Pipeline cancelled by user.[/red]")
            return
    
    except Exception as e:
        console.print(f"[red]Mapping failed: {e}[/red]")
        import traceback
        traceback.print_exc()
        return
    
    # Stage 5: PDF Generation
    if Confirm.ask("\nGenerate searchable PDF?", default=True):
        try:
            console.print("\n[bold]Generating PDF...[/bold]")
            pdf_path = controller.generate_pdf(config.get('pdf_output_path'))
            console.print(f"[green]PDF generated: {pdf_path}[/green]")
        except Exception as e:
            console.print(f"[red]PDF generation failed: {e}[/red]")
    
    console.print("\n[bold green]Pipeline complete![/bold green]")

