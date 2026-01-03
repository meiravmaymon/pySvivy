# -*- coding: utf-8 -*-
"""
OCR Package for Svivy Municipal System
חבילת OCR למערכת סביבי

This package provides modular OCR functionality for extracting
data from Hebrew municipal protocol PDFs.

Modules:
- text_utils: Text manipulation utilities (reverse, normalize, fix numbers)
- date_extractor: Date extraction from Hebrew text
- budget_extractor: Budget and funding source extraction
- vote_extractor: Vote count and result extraction
- pdf_processor: PDF to text conversion
- section_detector: Protocol section detection
- formats: Municipality-specific format handlers
- llm_router: LLM routing (Regex → Ollama → Gemini)
- gemini_client: Google Gemini Flash client

Usage:
    from ocr import extract_protocol_data, detect_sections
    from ocr.formats import detect_format
    from ocr.llm_router import LLMRouter

    # Detect sections in protocol
    result = detect_sections(ocr_text)

    # Get format for municipality
    fmt = detect_format(ocr_text)

    # Use LLM router for extraction
    router = LLMRouter()
    vote = router.extract(text, ExtractionType.VOTE)
"""

# Import main functions for convenience
from ocr.text_utils import (
    reverse_hebrew_text,
    normalize_final_letters,
    fix_reversed_numbers,
    fix_reversed_short_numbers,
    normalize_hebrew_text,
    detect_reversed_text,
    fix_common_ocr_errors,
    extract_hebrew_words,
    is_valid_hebrew_name,
    similarity_score,
)

from ocr.date_extractor import (
    extract_meeting_date,
    extract_meeting_number,
    parse_israeli_date
)

from ocr.budget_extractor import (
    extract_budget_amount,
    extract_funding_sources
)

from ocr.section_detector import (
    SectionType,
    SectionInfo,
    DetectionResult,
    SectionDetector,
    detect_sections,
    get_section,
)

__all__ = [
    # Text utilities
    'reverse_hebrew_text',
    'normalize_final_letters',
    'fix_reversed_numbers',
    'fix_reversed_short_numbers',
    'normalize_hebrew_text',
    'detect_reversed_text',
    'fix_common_ocr_errors',
    'extract_hebrew_words',
    'is_valid_hebrew_name',
    'similarity_score',

    # Date extraction
    'extract_meeting_date',
    'extract_meeting_number',
    'parse_israeli_date',

    # Budget extraction
    'extract_budget_amount',
    'extract_funding_sources',

    # Section detection
    'SectionType',
    'SectionInfo',
    'DetectionResult',
    'SectionDetector',
    'detect_sections',
    'get_section',
]

__version__ = '2.1.0'
