"""
Batch processing module for automated OCR pipeline execution.

Processes multiple images or PDF pages without user intervention.
"""

import os
import glob
from typing import List, Dict, Any, Optional
from pathlib import Path

from pipeline_controller import PipelineController
import image_preprocessing


def extract_pdf_pages(pdf_path: str, output_folder: str) -> List[str]:
    """
    Extract pages from PDF as images.
    
    Args:
        pdf_path: Path to PDF file
        output_folder: Folder to save extracted page images
        
    Returns:
        List of paths to extracted image files
    """
    try:
        from pdf2image import convert_from_path
    except ImportError:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError("Please install pdf2image or PyMuPDF for PDF page extraction")
    
    os.makedirs(output_folder, exist_ok=True)
    
    image_paths = []
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    
    try:
        # Try pdf2image first
        from pdf2image import convert_from_path
        images = convert_from_path(pdf_path, dpi=300)
        
        for i, img in enumerate(images, 1):
            output_path = os.path.join(output_folder, f"{base_name}_page_{i:03d}.png")
            img.save(output_path, 'PNG')
            image_paths.append(output_path)
    
    except ImportError:
        # Fall back to PyMuPDF
        import fitz
        doc = fitz.open(pdf_path)
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))  # 300 DPI
            output_path = os.path.join(output_folder, f"{base_name}_page_{page_num+1:03d}.png")
            pix.save(output_path)
            image_paths.append(output_path)
        
        doc.close()
    
    return image_paths


def get_image_files(folder: str) -> List[str]:
    """
    Get all image files from a folder.
    
    Args:
        folder: Folder path
        
    Returns:
        List of image file paths
    """
    extensions = ['*.png', '*.jpg', '*.jpeg', '*.tiff', '*.tif', '*.bmp']
    image_files = []
    
    for ext in extensions:
        pattern = os.path.join(folder, ext)
        image_files.extend(glob.glob(pattern))
        # Also check uppercase
        pattern = os.path.join(folder, ext.upper())
        image_files.extend(glob.glob(pattern))
    
    return sorted(image_files)


def get_pdf_files(folder: str) -> List[str]:
    """
    Get all PDF files from a folder.
    
    Args:
        folder: Folder path
        
    Returns:
        List of PDF file paths
    """
    pattern = os.path.join(folder, '*.pdf')
    pdf_files = glob.glob(pattern)
    pattern = os.path.join(folder, '*.PDF')
    pdf_files.extend(glob.glob(pattern))
    return sorted(pdf_files)


def run_automated_pipeline(image_path: str, config: Dict[str, Any],
                          output_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Run full pipeline automatically without user prompts.
    
    Args:
        image_path: Path to input image
        config: Configuration dictionary with pipeline settings
        output_dir: Optional output directory (uses config if not provided)
        
    Returns:
        Dictionary with results and output paths
    """
    if output_dir is None:
        output_dir = config.get('output_dir', 'outputs')
    
    controller = PipelineController(output_dir)
    
    results = {
        'image_path': image_path,
        'success': False,
        'error': None,
        'outputs': {}
    }
    
    try:
        # Stage 1: Image prep
        prep_config = config.get('image_prep_config', {})
        controller.set_image(image_path, prep_config)
        
        # Stage 2: OCR
        ocr_results = controller.run_ocr(
            config.get('ocr_language', 'eng'),
            config.get('ocr_config', {}),
            config.get('generate_tesseract_pdf', False)
        )
        results['outputs']['ocr'] = ocr_results
        
        # Stage 3: LLM cleaning
        if config.get('run_llm_cleaning', True):
            clean_path = controller.run_llm_cleaning(
                config.get('llm_model', 'qwen2.5:14b'),
                config.get('llm_context'),
                config.get('llm_system_prompt'),
                config.get('ollama_base_url', 'http://localhost:11434')
            )
            results['outputs']['clean_text'] = clean_path
        
        # Stage 4: Mapping
        hypothesis_list, page = controller.run_mapping(
            show_ocr_accuracy=config.get('show_ocr_accuracy', False)
        )
        results['outputs']['mapping_dir'] = controller.state.mapping_output_dir
        
        # Export CSV
        if config.get('export_csv', True) and controller.state.mapping_output_dir:
            import visualize_matching
            from map_up_text import create_LLM_element_list
            
            llm_elements = create_LLM_element_list(controller.state.clean_text)
            csv_path = os.path.join(
                controller.state.mapping_output_dir,
                f"{os.path.splitext(os.path.basename(image_path))[0]}_mapping.csv"
            )
            visualize_matching.export_llm_token_mapping_to_csv(
                hypothesis_list,
                llm_elements,
                csv_path
            )
            results['outputs']['csv'] = csv_path
        
        # Stage 5: PDF generation
        if config.get('generate_pdf', True):
            pdf_path = controller.generate_pdf()
            results['outputs']['pdf'] = pdf_path
        
        results['success'] = True
        results['matched_count'] = sum(1 for h in hypothesis_list if h.chosen_LLM_token is not None)
        results['error_count'] = sum(1 for h in hypothesis_list if h.flagged_for_error)
        results['total_count'] = len(hypothesis_list)
        
    except Exception as e:
        results['error'] = str(e)
        results['success'] = False
    
    return results


def process_batch(input_folder: str, output_folder: str, config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Process all images and PDFs in a folder.
    
    Args:
        input_folder: Folder containing input images/PDFs
        output_folder: Base folder for outputs
        config: Configuration dictionary
        
    Returns:
        List of result dictionaries for each processed file
    """
    results = []
    
    # Get all image files
    image_files = get_image_files(input_folder)
    
    # Get all PDF files and extract pages
    pdf_files = get_pdf_files(input_folder)
    for pdf_file in pdf_files:
        # Extract pages to temp folder
        temp_folder = os.path.join(output_folder, 'temp_pdf_pages', 
                                  os.path.splitext(os.path.basename(pdf_file))[0])
        os.makedirs(temp_folder, exist_ok=True)
        
        try:
            page_images = extract_pdf_pages(pdf_file, temp_folder)
            image_files.extend(page_images)
        except Exception as e:
            print(f"Warning: Failed to extract pages from {pdf_file}: {e}")
    
    # Process each image
    total = len(image_files)
    for i, image_path in enumerate(image_files, 1):
        print(f"\nProcessing {i}/{total}: {os.path.basename(image_path)}")
        
        # Create output directory for this image
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        image_output_dir = os.path.join(output_folder, base_name)
        
        # Update config with image-specific output dir
        image_config = config.copy()
        image_config['output_dir'] = image_output_dir
        
        # Run pipeline
        result = run_automated_pipeline(image_path, image_config, image_output_dir)
        result['file_number'] = i
        result['total_files'] = total
        results.append(result)
        
        if result['success']:
            print(f"  ✓ Success: {result.get('matched_count', 0)}/{result.get('total_count', 0)} matched, "
                  f"{result.get('error_count', 0)} errors")
        else:
            print(f"  ✗ Failed: {result.get('error', 'Unknown error')}")
    
    return results


def run_tesseract_batch(output_folder: str, config: Dict[str, Any]) -> None:
    """
    Run Tesseract OCR on all image files in output folder.
    
    This is a helper function for batch processing that runs OCR
    on all images found in the output folder structure.
    
    Args:
        output_folder: Folder containing images to process
        config: Configuration with OCR settings
    """
    image_files = get_image_files(output_folder)
    
    for image_path in image_files:
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        image_output_dir = os.path.join(output_folder, base_name)
        os.makedirs(image_output_dir, exist_ok=True)
        
        # Load and prepare image
        img = image_preprocessing.prepare_image(image_path, config.get('image_prep_config', {}))
        
        # Run OCR
        import tesseract_ocr
        tesseract_ocr.run_full_ocr(
            img,
            image_output_dir,
            base_name,
            config.get('ocr_language', 'eng'),
            config.get('ocr_config', {}),
            config.get('generate_tesseract_pdf', False)
        )


def generate_clean_text_files(output_folder: str, config: Dict[str, Any]) -> None:
    """
    Run LLM cleaning on all plaintext files in output folder.
    
    Args:
        output_folder: Folder containing OCR plaintext files
        config: Configuration with LLM settings
    """
    import llm_cleaning
    
    # Find all plaintext files
    pattern = os.path.join(output_folder, '**', '*_plaintext.txt')
    plaintext_files = glob.glob(pattern, recursive=True)
    
    for plaintext_path in plaintext_files:
        base_name = os.path.splitext(os.path.basename(plaintext_path))[0]
        base_name = base_name.replace('_plaintext', '')
        output_dir = os.path.dirname(plaintext_path)
        clean_text_path = os.path.join(output_dir, f"{base_name}_cleantext.txt")
        
        try:
            llm_cleaning.clean_text_file(
                plaintext_path,
                clean_text_path,
                config.get('llm_model', 'qwen2.5:14b'),
                config.get('llm_system_prompt'),
                config.get('llm_context'),
                config.get('ollama_base_url', 'http://localhost:11434')
            )
            print(f"Cleaned: {clean_text_path}")
        except Exception as e:
            print(f"Failed to clean {plaintext_path}: {e}")


def map_texts(output_folder: str, config: Dict[str, Any]) -> None:
    """
    Run mapping on all XML and clean text file pairs in output folder.
    
    Args:
        output_folder: Folder containing XML and clean text files
        config: Configuration with mapping settings
    """
    # Find all XML files
    pattern = os.path.join(output_folder, '**', '*.xml')
    xml_files = glob.glob(pattern, recursive=True)
    
    for xml_path in xml_files:
        # Find corresponding clean text file
        base_name = os.path.splitext(os.path.basename(xml_path))[0]
        base_name = base_name.replace('_plaintext', '').replace('_Tesseract_XML', '')
        
        # Look for clean text in same directory
        clean_text_pattern = os.path.join(os.path.dirname(xml_path), f"{base_name}*cleantext.txt")
        clean_text_files = glob.glob(clean_text_pattern)
        
        if not clean_text_files:
            print(f"No clean text found for {xml_path}")
            continue
        
        clean_text_path = clean_text_files[0]
        
        try:
            # Create controller and run mapping
            controller = PipelineController(os.path.dirname(xml_path))
            controller.state.ocr_xml_path = xml_path
            
            with open(clean_text_path, 'r', encoding='utf-8') as f:
                controller.state.clean_text = f.read()
            controller.state.clean_text_path = clean_text_path
            
            controller.run_mapping(show_ocr_accuracy=config.get('show_ocr_accuracy', False))
            
            print(f"Mapped: {xml_path}")
        except Exception as e:
            print(f"Failed to map {xml_path}: {e}")

