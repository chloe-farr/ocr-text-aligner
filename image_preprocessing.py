"""
Image preprocessing module for OCR pipeline.

Provides functions to prepare images for Tesseract OCR including cropping,
rotation, contrast adjustment, and resizing.
"""

from PIL import Image, ImageEnhance, ImageOps
from typing import Tuple, Optional, Dict, Any
import numpy as np


def crop_image(image: Image.Image, bbox: Tuple[int, int, int, int]) -> Image.Image:
    """
    Crop image to specified bounding box.
    
    Args:
        image: PIL Image object
        bbox: Tuple of (left, top, right, bottom) coordinates
        
    Returns:
        Cropped PIL Image
    """
    return image.crop(bbox)


def rotate_image(image: Image.Image, angle: float) -> Image.Image:
    """
    Rotate image by specified angle in degrees.
    
    Args:
        image: PIL Image object
        angle: Rotation angle in degrees (positive = counterclockwise)
        
    Returns:
        Rotated PIL Image
    """
    # Expand=True ensures the entire rotated image is visible
    return image.rotate(angle, expand=True, fillcolor='white')


def adjust_contrast(image: Image.Image, factor: float) -> Image.Image:
    """
    Adjust image contrast.
    
    Args:
        image: PIL Image object
        factor: Contrast factor (1.0 = no change, <1.0 = less contrast, >1.0 = more contrast)
                Typically range: 0.0-2.0
        
    Returns:
        Image with adjusted contrast
    """
    enhancer = ImageEnhance.Contrast(image)
    return enhancer.enhance(factor)


def adjust_brightness(image: Image.Image, factor: float) -> Image.Image:
    """
    Adjust image brightness.
    
    Args:
        image: PIL Image object
        factor: Brightness factor (1.0 = no change, <1.0 = darker, >1.0 = brighter)
                Typically range: 0.0-2.0
        
    Returns:
        Image with adjusted brightness
    """
    enhancer = ImageEnhance.Brightness(image)
    return enhancer.enhance(factor)


def resize_image(image: Image.Image, max_dimension: Optional[int] = None, 
                 target_size: Optional[Tuple[int, int]] = None) -> Image.Image:
    """
    Resize image to Tesseract-friendly dimensions.
    
    Tesseract works best with images that are:
    - At least 300 DPI
    - Not too large (max ~4000px on longest side)
    - Maintain aspect ratio
    
    Args:
        image: PIL Image object
        max_dimension: Maximum dimension (width or height) in pixels. If None, no resize.
        target_size: Optional (width, height) tuple. If provided, max_dimension is ignored.
        
    Returns:
        Resized PIL Image
    """
    if target_size:
        return image.resize(target_size, Image.Resampling.LANCZOS)
    
    if max_dimension is None:
        return image
    
    width, height = image.size
    if max(width, height) <= max_dimension:
        return image
    
    # Maintain aspect ratio
    if width > height:
        new_width = max_dimension
        new_height = int(height * (max_dimension / width))
    else:
        new_height = max_dimension
        new_width = int(width * (max_dimension / height))
    
    return image.resize((new_width, new_height), Image.Resampling.LANCZOS)


def convert_to_grayscale(image: Image.Image) -> Image.Image:
    """
    Convert image to grayscale if it's not already.
    
    Args:
        image: PIL Image object
        
    Returns:
        Grayscale PIL Image
    """
    if image.mode == 'L':
        return image
    return image.convert('L')


def enhance_for_ocr(image: Image.Image) -> Image.Image:
    """
    Apply standard OCR-friendly enhancements:
    - Convert to grayscale
    - Apply slight sharpening
    
    Args:
        image: PIL Image object
        
    Returns:
        Enhanced PIL Image
    """
    # Convert to grayscale
    if image.mode != 'L':
        image = convert_to_grayscale(image)
    
    # Apply slight sharpening
    enhancer = ImageEnhance.Sharpness(image)
    image = enhancer.enhance(1.2)
    
    return image


def prepare_image(image_path: str, config: Optional[Dict[str, Any]] = None) -> Image.Image:
    """
    Main function to prepare image for OCR with all preprocessing steps.
    
    Args:
        image_path: Path to input image file
        config: Optional configuration dictionary with keys:
            - crop: Tuple (left, top, right, bottom) or None
            - rotate: Rotation angle in degrees (default: 0)
            - contrast: Contrast factor (default: 1.0)
            - brightness: Brightness factor (default: 1.0)
            - max_dimension: Maximum dimension for resizing (default: 4000)
            - grayscale: Convert to grayscale (default: True)
            - enhance: Apply OCR enhancements (default: True)
        
    Returns:
        Preprocessed PIL Image
    """
    if config is None:
        config = {}
    
    # Load image
    image = Image.open(image_path)
    
    # Crop if specified
    if 'crop' in config and config['crop'] is not None:
        image = crop_image(image, config['crop'])
    
    # Rotate if specified
    if 'rotate' in config and config['rotate'] != 0:
        image = rotate_image(image, config['rotate'])
    
    # Adjust contrast if specified
    if 'contrast' in config and config['contrast'] != 1.0:
        image = adjust_contrast(image, config['contrast'])
    
    # Adjust brightness if specified
    if 'brightness' in config and config['brightness'] != 1.0:
        image = adjust_brightness(image, config['brightness'])
    
    # Resize if specified
    max_dim = config.get('max_dimension', 4000)
    if max_dim:
        image = resize_image(image, max_dimension=max_dim)
    
    # Convert to grayscale if specified (default: True)
    if config.get('grayscale', True):
        image = convert_to_grayscale(image)
    
    # Apply OCR enhancements if specified (default: True)
    if config.get('enhance', True):
        image = enhance_for_ocr(image)
    
    return image


def get_image_info(image: Image.Image) -> Dict[str, Any]:
    """
    Get information about an image.
    
    Args:
        image: PIL Image object
        
    Returns:
        Dictionary with image information (size, mode, etc.)
    """
    return {
        'size': image.size,
        'width': image.width,
        'height': image.height,
        'mode': image.mode,
        'format': getattr(image, 'format', None),
    }

