"""
PDF generation module for creating searchable PDFs with corrected text.

Generates PDFs with invisible text overlay at OCR coordinates, making them
searchable while preserving the original image appearance.
"""

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image
from typing import List, Optional, Tuple
import os

# Import types from map_up_text
from map_up_text import TokenHypotheses
import xml_obj as XMLOBJ


def create_searchable_pdf(image_path: str, hypothesis_list: List[TokenHypotheses],
                         page: XMLOBJ.Page, output_path: str,
                         page_size: Optional[Tuple[float, float]] = None) -> str:
    """
    Create a searchable PDF with corrected text overlaid invisibly on the image.
    
    The text is positioned at the original OCR coordinates but rendered invisibly,
    making the PDF searchable while preserving the visual appearance of the image.
    
    Args:
        image_path: Path to the original image file
        hypothesis_list: List of TokenHypotheses with corrected text mappings
        page: Page object with dimensions
        output_path: Path to save the PDF
        page_size: Optional (width, height) tuple in points. If None, uses image dimensions.
        
    Returns:
        Path to generated PDF file
    """
    # Load image to get dimensions
    img = Image.open(image_path)
    img_width, img_height = img.size
    
    # Determine page size
    if page_size is None:
        # Use image dimensions, converting pixels to points (1 inch = 72 points)
        # Assume 300 DPI for conversion
        dpi = 300
        page_width = (img_width / dpi) * 72
        page_height = (img_height / dpi) * 72
    else:
        page_width, page_height = page_size
    
    # Create PDF canvas
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    c = canvas.Canvas(output_path, pagesize=(page_width, page_height))
    
    # Draw the image (scaled to fit page)
    c.drawImage(image_path, 0, 0, width=page_width, height=page_height, preserveAspectRatio=True)
    
    # Calculate scaling factors
    scale_x = page_width / page.width if page.width > 0 else 1.0
    scale_y = page_height / page.height if page.height > 0 else 1.0
    
    # Overlay invisible text at OCR coordinates
    for hyp in hypothesis_list:
        if hyp.chosen_LLM_token is None:
            continue
        
        # Get corrected text
        corrected_text = hyp.chosen_LLM_token.word
        
        # Get OCR coordinates from anchor
        anchor = hyp.anchor
        x = anchor.hpos * scale_x
        y = page_height - (anchor.vpos + anchor.height) * scale_y  # Flip Y coordinate
        
        # Calculate font size based on OCR word height
        font_size = anchor.height * scale_y * 0.8  # Slightly smaller than bounding box
        
        # Set text rendering mode to invisible (text is there but not visible)
        # For searchable PDFs, we need text in the PDF text layer but invisible
        # Use text rendering mode 3 (invisible) - this makes text searchable but not visible
        c.saveState()
        
        # Set text rendering mode to invisible (mode 3)
        # Mode 0 = fill, 1 = stroke, 2 = fill+stroke, 3 = invisible
        # Invisible mode makes text searchable but not visible
        # Use low-level PDF command for text rendering mode
        c._code.append('3 Tr')  # Set text rendering mode to invisible
        
        # Set text color (won't be visible but needed for text layer)
        c.setFillColorRGB(1, 1, 1)  # White (won't show due to rendering mode)
        
        # Set font and size
        c.setFont("Helvetica", font_size)
        
        # Position and draw text
        c.drawString(x, y, corrected_text)
        
        # Reset text rendering mode to normal (mode 0 = fill)
        c._code.append('0 Tr')
        
        c.restoreState()
    
    # Save PDF
    c.save()
    
    return output_path


def overlay_text_on_pdf(image: Image.Image, word_positions: List[Tuple[float, float, float, float, str]],
                       output_path: str, page_size: Optional[Tuple[float, float]] = None) -> str:
    """
    Overlay text on PDF at specified positions.
    
    This is a lower-level function for more control over text positioning.
    
    Args:
        image: PIL Image object
        word_positions: List of tuples (x, y, width, height, text) in image coordinates
        output_path: Path to save PDF
        page_size: Optional (width, height) tuple in points
        
    Returns:
        Path to generated PDF file
    """
    img_width, img_height = image.size
    
    if page_size is None:
        dpi = 300
        page_width = (img_width / dpi) * 72
        page_height = (img_height / dpi) * 72
    else:
        page_width, page_height = page_size
    
    # Save image temporarily if needed
    temp_image_path = None
    if not hasattr(image, 'filename') or image.filename is None:
        import tempfile
        temp_image_path = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        image.save(temp_image_path.name)
        image_path = temp_image_path.name
    else:
        image_path = image.filename
    
    # Create PDF
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    c = canvas.Canvas(output_path, pagesize=(page_width, page_height))
    
    # Draw image
    c.drawImage(image_path, 0, 0, width=page_width, height=page_height, preserveAspectRatio=True)
    
    # Calculate scaling
    scale_x = page_width / img_width if img_width > 0 else 1.0
    scale_y = page_height / img_height if img_height > 0 else 1.0
    
    # Overlay text
    for x, y, width, height, text in word_positions:
        pdf_x = x * scale_x
        pdf_y = page_height - (y + height) * scale_y  # Flip Y
        font_size = height * scale_y * 0.8
        
        c.saveState()
        # Set text rendering mode to invisible (mode 3) for searchable but invisible text
        c._code.append('3 Tr')  # Invisible text rendering mode
        c.setFillColorRGB(1, 1, 1)  # White (won't show)
        c.setFont("Helvetica", font_size)
        c.drawString(pdf_x, pdf_y, text)
        c._code.append('0 Tr')  # Reset to normal
        c.restoreState()
    
    c.save()
    
    # Clean up temp file if created
    if temp_image_path:
        os.unlink(temp_image_path.name)
    
    return output_path

