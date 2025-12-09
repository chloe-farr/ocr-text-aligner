"""
Main entry point for OCR pipeline.

Supports GUI, CLI, and batch processing modes.
"""

import argparse
import sys
import os
from typing import Dict, Any

# Import interfaces
from cli_interface import run_cli_pipeline
from batch_processor import process_batch
from pipeline_controller import PipelineController, PipelineStage


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='OCR Text Aligner - Map LLM-cleaned text to OCR coordinates',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # GUI mode
  python main.py --gui
  
  # CLI mode with image
  python main.py --cli --image path/to/image.png
  
  # Batch processing
  python main.py --batch path/to/folder --output outputs/
  
  # Start at specific stage
  python main.py --cli --image image.png --xml existing.xml --clean-text cleaned.txt
        """
    )
    
    # Mode selection
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--gui', action='store_true',
                           help='Launch GUI mode')
    mode_group.add_argument('--cli', action='store_true',
                           help='Launch CLI mode')
    mode_group.add_argument('--batch', type=str, metavar='FOLDER',
                           help='Batch processing mode (process all images/PDFs in folder)')
    
    # Input files
    parser.add_argument('--image', type=str,
                       help='Path to input image file')
    parser.add_argument('--xml', type=str,
                       help='Path to existing XML file (skip OCR stage)')
    parser.add_argument('--clean-text', type=str,
                       help='Path to existing clean text file (skip LLM stage)')
    
    # Stage selection
    parser.add_argument('--stage', type=str,
                       choices=['image_prep', 'ocr', 'llm_clean', 'mapping', 'pdf_gen'],
                       help='Start at specific stage')
    
    # OCR settings
    parser.add_argument('--ocr-language', type=str, default='eng',
                       help='Tesseract language code (default: eng)')
    parser.add_argument('--ocr-config', type=str,
                       help='Tesseract config options (comma-separated key=value pairs)')
    
    # LLM settings
    parser.add_argument('--llm-model', type=str, default='qwen2.5',
                       help='LLM model name (default: qwen2.5)')
    parser.add_argument('--llm-context', type=str,
                       help='Additional context for LLM (e.g., "1972 newspaper from New York")')
    parser.add_argument('--ollama-url', type=str, default='http://localhost:11434',
                       help='Ollama API base URL (default: http://localhost:11434)')
    
    # Output settings
    parser.add_argument('--output', type=str, default='outputs',
                       help='Output directory (default: outputs)')
    parser.add_argument('--pdf-output', type=str,
                       help='Output path for PDF (default: auto-generated)')
    
    # Batch processing options
    parser.add_argument('--no-llm', action='store_true',
                       help='Skip LLM cleaning in batch mode')
    parser.add_argument('--no-pdf', action='store_true',
                       help='Skip PDF generation in batch mode')
    parser.add_argument('--no-csv', action='store_true',
                       help='Skip CSV export in batch mode')
    parser.add_argument('--show-ocr-accuracy', action='store_true',
                       help='Show OCR accuracy analysis')
    
    args = parser.parse_args()
    
    # Build config dictionary
    config = {
        'output_dir': args.output,
        'ocr_language': args.ocr_language,
        'llm_model': args.llm_model,
        'llm_context': args.llm_context,
        'ollama_base_url': args.ollama_url,
        'show_ocr_accuracy': args.show_ocr_accuracy,
        'generate_pdf': not args.no_pdf,
        'export_csv': not args.no_csv,
        'run_llm_cleaning': not args.no_llm,
    }
    
    # Parse OCR config if provided
    if args.ocr_config:
        ocr_config = {}
        for pair in args.ocr_config.split(','):
            if '=' in pair:
                key, value = pair.split('=', 1)
                ocr_config[key.strip()] = value.strip()
        config['ocr_config'] = ocr_config
    else:
        config['ocr_config'] = {}
    
    # Handle PDF output path
    if args.pdf_output:
        config['pdf_output_path'] = args.pdf_output
    
    # GUI mode
    if args.gui:
        try:
            from PyQt6.QtWidgets import QApplication
            from gui.main_window import MainWindow
            from gui.stage_widgets import (
                ImagePrepWidget, OCRReviewWidget, LLMCleaningWidget,
                MappingReviewWidget, PDFGenerationWidget
            )
            from gui.error_highlighter import ErrorHighlighter
            
            app = QApplication(sys.argv)
            window = MainWindow()
            
            # Connect stage widgets (simplified - full integration would be more complex)
            # This is a basic setup - full GUI integration would require more work
            
            window.show()
            sys.exit(app.exec())
        
        except ImportError as e:
            print(f"Error: PyQt6 not installed. Install with: pip install PyQt6")
            sys.exit(1)
    
    # CLI mode
    elif args.cli:
        # Add input files to config
        if args.image:
            config['image_path'] = args.image
        if args.xml:
            config['ocr_xml_path'] = args.xml
        if args.clean_text:
            config['clean_text_path'] = args.clean_text
        
        # Determine starting stage
        if args.stage:
            stage_map = {
                'image_prep': PipelineStage.IMAGE_PREP,
                'ocr': PipelineStage.OCR,
                'llm_clean': PipelineStage.LLM_CLEAN,
                'mapping': PipelineStage.MAPPING,
                'pdf_gen': PipelineStage.PDF_GEN
            }
            config['start_stage'] = stage_map[args.stage]
        
        run_cli_pipeline(config)
    
    # Batch mode
    elif args.batch:
        if not os.path.isdir(args.batch):
            print(f"Error: Input folder does not exist: {args.batch}")
            sys.exit(1)
        
        print(f"Batch processing: {args.batch}")
        print(f"Output folder: {args.output}")
        print()
        
        results = process_batch(args.batch, args.output, config)
        
        # Print summary
        print("\n" + "="*70)
        print("BATCH PROCESSING SUMMARY")
        print("="*70)
        
        successful = sum(1 for r in results if r['success'])
        failed = len(results) - successful
        
        print(f"Total files: {len(results)}")
        print(f"Successful: {successful}")
        print(f"Failed: {failed}")
        
        if successful > 0:
            total_matched = sum(r.get('matched_count', 0) for r in results if r['success'])
            total_errors = sum(r.get('error_count', 0) for r in results if r['success'])
            total_words = sum(r.get('total_count', 0) for r in results if r['success'])
            
            print(f"\nTotal words matched: {total_matched}/{total_words}")
            print(f"Total errors: {total_errors}")
        
        if failed > 0:
            print("\nFailed files:")
            for r in results:
                if not r['success']:
                    print(f"  - {r['image_path']}: {r.get('error', 'Unknown error')}")


if __name__ == '__main__':
    main()

