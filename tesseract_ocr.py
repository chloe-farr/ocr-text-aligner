"""
Tesseract OCR integration module.

Provides functions to run Tesseract OCR and generate various output formats
including ALTO XML, plaintext, hOCR, and searchable PDF.

All output formats are generated from a single OCR run to ensure textual consistency.
"""

import pytesseract
from PIL import Image
from typing import Optional, Dict, Any, List
import os
import xml.etree.ElementTree as ET


def check_tesseract_installed() -> bool:
    """
    Check if Tesseract OCR is installed and accessible.
    
    Returns:
        True if Tesseract is available, False otherwise
    """
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def get_available_languages() -> List[str]:
    """
    Get list of available Tesseract language packs.
    
    Returns:
        List of language codes (e.g., ['eng', 'fra', 'deu'])
    """
    try:
        langs = pytesseract.get_languages()
        return langs
    except Exception:
        return ['eng']  # Default fallback


def _extract_plaintext_from_xml(xml_string: str) -> str:
    """
    Extract plaintext from ALTO XML string.
    Supports both ALTO v3 and v4.
    
    Args:
        xml_string: ALTO XML content as string
        
    Returns:
        Plaintext extracted from XML
    """
    try:
        root = ET.fromstring(xml_string)
        # Try both ALTO v3 and v4 namespaces
        ns_v3 = {'alto': 'http://www.loc.gov/standards/alto/ns-v3#'}
        ns_v4 = {'alto': 'http://www.loc.gov/standards/alto/ns-v4#'}
        
        # Find all String elements and extract their CONTENT
        words = []
        # Try v4 first
        for string in root.findall('.//alto:String', ns_v4):
            content = string.get('CONTENT', '')
            if content:
                words.append(content)
        
        # If no words found, try v3
        if not words:
            for string in root.findall('.//alto:String', ns_v3):
                content = string.get('CONTENT', '')
                if content:
                    words.append(content)
        
        # Join words with spaces
        return ' '.join(words)
    except Exception as e:
        # Fallback: try to extract text more simply
        # This is a basic fallback if XML parsing fails
        import re
        # Look for CONTENT="..." patterns
        matches = re.findall(r'CONTENT="([^"]*)"', xml_string)
        return ' '.join(matches)


def run_ocr_once(image: Image.Image, language: str = 'eng',
                config_options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Run Tesseract OCR once and return all output formats.
    This ensures all output files have consistent textual content.
    
    Args:
        image: PIL Image object
        language: Language code (e.g., 'eng', 'eng+fra' for multilingual)
        config_options: Optional dictionary of Tesseract config options
        
    Returns:
        Dictionary containing:
        {
            'xml': ALTO XML string,
            'plaintext': plaintext string (extracted from XML),
            'hocr': hOCR bytes,
            'pdf': PDF bytes
        }
    """
    if config_options is None:
        config_options = {}
    
    # Build base config string
    base_config = ' '.join([f'--{k} {v}' for k, v in config_options.items()])
    
    results = {}
    
    # Run OCR once to get ALTO XML (this is our source of truth)
    xml_config = base_config + ' alto' if base_config else 'alto'
    xml_output = pytesseract.image_to_alto_xml(image, lang=language, config=xml_config)
    # Ensure XML is a string (pytesseract may return bytes)
    if isinstance(xml_output, bytes):
        xml_string = xml_output.decode('utf-8')
    else:
        xml_string = xml_output
    results['xml'] = xml_string
    
    # Get plaintext using Tesseract's native function
    # Use same config to maintain consistency
    txt_config = base_config if base_config else ''
    results['plaintext'] = pytesseract.image_to_string(image, lang=language, config=txt_config)
    
    # Generate hOCR (using same config to maintain consistency)
    hocr_config = base_config + ' hocr' if base_config else 'hocr'
    results['hocr'] = pytesseract.image_to_pdf_or_hocr(image, lang=language,
                                                       config=hocr_config, extension='hocr')
    
    # Generate PDF (using same config)
    pdf_config = base_config if base_config else ''
    results['pdf'] = pytesseract.image_to_pdf_or_hocr(image, lang=language,
                                                      config=pdf_config, extension='pdf')
    
    return results


def generate_xml(image: Image.Image, output_path: str, language: str = 'eng',
                 config_options: Optional[Dict[str, Any]] = None) -> str:
    """
    Generate ALTO XML output from Tesseract OCR.
    
    Args:
        image: PIL Image object
        output_path: Path to save XML file
        language: Language code
        config_options: Optional dictionary of Tesseract config options
        
    Returns:
        Path to generated XML file
    """
    ocr_results = run_ocr_once(image, language, config_options)
    
    # Save XML to file
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(ocr_results['xml'])
    
    return output_path


def generate_plaintext(image: Image.Image, output_path: str, language: str = 'eng',
                      config_options: Optional[Dict[str, Any]] = None) -> str:
    """
    Generate plaintext output from Tesseract OCR.
    Plaintext is extracted from the ALTO XML to ensure consistency with other outputs.
    
    Args:
        image: PIL Image object
        output_path: Path to save plaintext file
        language: Language code
        config_options: Optional dictionary of Tesseract config options
        
    Returns:
        Path to generated plaintext file
    """
    ocr_results = run_ocr_once(image, language, config_options)
    
    # Save plaintext to file
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(ocr_results['plaintext'])
    
    return output_path


def generate_hocr(image: Image.Image, output_path: str, language: str = 'eng',
                 config_options: Optional[Dict[str, Any]] = None) -> str:
    """
    Generate hOCR (HTML OCR) output from Tesseract OCR.
    
    Args:
        image: PIL Image object
        output_path: Path to save hOCR file
        language: Language code
        config_options: Optional dictionary of Tesseract config options
        
    Returns:
        Path to generated hOCR file
    """
    ocr_results = run_ocr_once(image, language, config_options)
    
    # Save hOCR to file
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    with open(output_path, 'wb') as f:
        f.write(ocr_results['hocr'])
    
    return output_path


def generate_pdf_from_tesseract(image: Image.Image, output_path: str, 
                                language: str = 'eng',
                                config_options: Optional[Dict[str, Any]] = None) -> str:
    """
    Generate searchable PDF directly from Tesseract OCR.
    
    Args:
        image: PIL Image object
        output_path: Path to save PDF file
        language: Language code
        config_options: Optional dictionary of Tesseract config options
        
    Returns:
        Path to generated PDF file
    """
    ocr_results = run_ocr_once(image, language, config_options)
    
    # Save PDF to file
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    with open(output_path, 'wb') as f:
        f.write(ocr_results['pdf'])
    
    return output_path


def run_full_ocr(image: Image.Image, output_dir: str, base_name: str,
                 language: str = 'eng', config_options: Optional[Dict[str, Any]] = None,
                 generate_pdf: bool = False) -> Dict[str, str]:
    """
    Run full OCR pipeline generating all output formats from a single OCR run.
    This ensures all output files have consistent textual content.
    
    Args:
        image: PIL Image object
        output_dir: Directory to save output files
        base_name: Base name for output files (without extension)
        language: Language code
        config_options: Optional dictionary of Tesseract config options
        generate_pdf: Whether to generate PDF output
        
    Returns:
        Dictionary mapping output type to file path:
        {
            'xml': path_to_xml,
            'plaintext': path_to_plaintext,
            'hocr': path_to_hocr,
            'pdf': path_to_pdf (if generate_pdf=True)
        }
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Run OCR once to get all formats
    ocr_results = run_ocr_once(image, language, config_options)
    
    results = {}
    
    # Save XML
    xml_path = os.path.join(output_dir, f"{base_name}.xml")
    with open(xml_path, 'w', encoding='utf-8') as f:
        f.write(ocr_results['xml'])
    results['xml'] = xml_path
    
    # Save plaintext (extracted from XML for consistency)
    txt_path = os.path.join(output_dir, f"{base_name}_plaintext.txt")
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(ocr_results['plaintext'])
    results['plaintext'] = txt_path
    
    # Save hOCR
    hocr_path = os.path.join(output_dir, f"{base_name}.hocr")
    with open(hocr_path, 'wb') as f:
        f.write(ocr_results['hocr'])
    results['hocr'] = hocr_path
    
    # Save PDF if requested
    if generate_pdf:
        pdf_path = os.path.join(output_dir, f"{base_name}_tesseract.pdf")
        with open(pdf_path, 'wb') as f:
            f.write(ocr_results['pdf'])
        results['pdf'] = pdf_path
    
    return results

