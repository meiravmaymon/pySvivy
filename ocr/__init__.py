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
- discussion_extractor: Discussion/agenda item extraction
- vote_extractor: Vote count and result extraction
- pdf_processor: PDF to text conversion
- protocol_parser: Main orchestration and parsing

Usage:
    from ocr import extract_protocol_data, extract_text_from_pdf

    # Extract text from PDF
    text = extract_text_from_pdf('protocol.pdf')

    # Parse protocol data
    data = extract_protocol_data('protocol.pdf')
"""

# Import main functions for convenience
from ocr.text_utils import (
    reverse_hebrew_text,
    normalize_final_letters,
    fix_reversed_numbers,
    fix_reversed_short_numbers
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

__all__ = [
    # Text utilities
    'reverse_hebrew_text',
    'normalize_final_letters',
    'fix_reversed_numbers',
    'fix_reversed_short_numbers',

    # Date extraction
    'extract_meeting_date',
    'extract_meeting_number',
    'parse_israeli_date',

    # Budget extraction
    'extract_budget_amount',
    'extract_funding_sources',
]

__version__ = '2.0.0'
