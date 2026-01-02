# -*- coding: utf-8 -*-
"""
PDF processing utilities for OCR.
פונקציות לעיבוד PDF ל-OCR

Functions:
- extract_text_from_pdf: Convert PDF to text using Tesseract OCR
- pdf_to_images: Convert PDF pages to images
"""
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Configure Tesseract paths
TESSERACT_PATH = os.environ.get(
    'TESSERACT_PATH',
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)
TESSDATA_PREFIX = os.environ.get(
    'TESSDATA_PREFIX',
    str(Path(__file__).parent.parent / "tessdata")
)


def setup_tesseract():
    """Configure Tesseract OCR paths."""
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
        os.environ['TESSDATA_PREFIX'] = TESSDATA_PREFIX
        return True
    except ImportError:
        logger.error("pytesseract not installed")
        return False


def pdf_to_images(pdf_path, dpi=300):
    """
    Convert PDF pages to images.

    Args:
        pdf_path: Path to PDF file
        dpi: Resolution for conversion (default 300)

    Returns:
        List of PIL Image objects, one per page
    """
    try:
        from pdf2image import convert_from_path
        images = convert_from_path(pdf_path, dpi=dpi)
        return images
    except Exception as e:
        logger.error(f"Failed to convert PDF to images: {e}")
        return []


def extract_text_from_image(image):
    """
    Extract text from a single image using Tesseract.

    Args:
        image: PIL Image object

    Returns:
        Extracted text string
    """
    try:
        import pytesseract
        setup_tesseract()

        # Use Hebrew language for OCR
        text = pytesseract.image_to_string(
            image,
            lang='heb+eng',
            config='--psm 6'  # Assume uniform block of text
        )
        return text
    except Exception as e:
        logger.error(f"Failed to extract text from image: {e}")
        return ""


def extract_text_from_pdf(pdf_path, dpi=300):
    """
    Extract text from PDF using OCR.

    Args:
        pdf_path: Path to PDF file
        dpi: Resolution for OCR (default 300)

    Returns:
        Full extracted text from all pages
    """
    if not os.path.exists(pdf_path):
        logger.error(f"PDF file not found: {pdf_path}")
        return ""

    logger.info(f"Processing PDF: {pdf_path}")

    # Convert PDF to images
    images = pdf_to_images(pdf_path, dpi=dpi)
    if not images:
        logger.error("No images extracted from PDF")
        return ""

    logger.info(f"Converted {len(images)} pages to images")

    # Extract text from each page
    full_text = []
    for i, image in enumerate(images, 1):
        logger.debug(f"Processing page {i}/{len(images)}")
        text = extract_text_from_image(image)
        if text:
            full_text.append(f"--- Page {i} ---\n{text}")

    result = "\n\n".join(full_text)
    logger.info(f"Extracted {len(result)} characters from PDF")

    return result


def extract_text_with_pdfplumber(pdf_path):
    """
    Extract text from PDF using pdfplumber (for non-scanned PDFs).

    Args:
        pdf_path: Path to PDF file

    Returns:
        Extracted text, or empty string if failed
    """
    try:
        import pdfplumber

        text_parts = []
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, 1):
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(f"--- Page {i} ---\n{page_text}")

        return "\n\n".join(text_parts)
    except Exception as e:
        logger.warning(f"pdfplumber extraction failed: {e}")
        return ""


def smart_extract_text(pdf_path):
    """
    Smart text extraction - try pdfplumber first, fall back to OCR.

    Args:
        pdf_path: Path to PDF file

    Returns:
        Extracted text
    """
    # Try pdfplumber first (faster for text-based PDFs)
    text = extract_text_with_pdfplumber(pdf_path)

    # If text is too short, probably a scanned PDF - use OCR
    if len(text.strip()) < 100:
        logger.info("PDF appears to be scanned, using OCR")
        text = extract_text_from_pdf(pdf_path)

    return text
