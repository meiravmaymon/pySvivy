# -*- coding: utf-8 -*-
"""
Protocol Format Detection.
זיהוי אוטומטי של פורמט פרוטוקול

This module provides automatic detection of which municipality format
to use for parsing a given protocol document.
"""

import re
from typing import Dict, List, Optional, Type
from ocr.formats.base_format import ProtocolFormat
from ocr.formats.yehud_format import YehudFormat
from ocr.formats.generic_format import GenericFormat


# Registry of available formats
FORMAT_REGISTRY: Dict[str, Type[ProtocolFormat]] = {
    'yehud': YehudFormat,
    'generic': GenericFormat,
}

# Municipality name patterns for detection
MUNICIPALITY_PATTERNS: Dict[str, List[str]] = {
    'yehud': [
        r'יהוד[\s\-]*מונוסון',
        r'ןוסונומ[\s\-]*דוהי',  # Reversed
        r'עיריית\s+יהוד',
        r'דוהי\s*תייריע',  # Reversed
    ],
}


def detect_format(text: str) -> ProtocolFormat:
    """
    Automatically detect the appropriate format for a protocol document.

    The detection works by:
    1. Looking for municipality name patterns in the text
    2. Checking both normal and reversed Hebrew text
    3. Falling back to generic format if no match

    Args:
        text: The OCR text from the protocol document

    Returns:
        An instance of the appropriate ProtocolFormat subclass
    """
    if not text:
        return GenericFormat()

    # Limit search to first part of document (header area)
    search_text = text[:2000]

    # Check each registered municipality
    for municipality_code, patterns in MUNICIPALITY_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, search_text, re.IGNORECASE):
                format_class = FORMAT_REGISTRY.get(municipality_code)
                if format_class:
                    return format_class()

    # No specific format found, use generic
    return GenericFormat()


def get_format(municipality_code: str) -> ProtocolFormat:
    """
    Get a specific format by municipality code.

    Args:
        municipality_code: The code for the municipality (e.g., 'yehud')

    Returns:
        An instance of the appropriate ProtocolFormat subclass

    Raises:
        ValueError: If the municipality code is not found
    """
    format_class = FORMAT_REGISTRY.get(municipality_code.lower())

    if format_class:
        return format_class()

    raise ValueError(
        f"Unknown municipality code: {municipality_code}. "
        f"Available: {list(FORMAT_REGISTRY.keys())}"
    )


def list_formats() -> List[str]:
    """
    List all available format codes.

    Returns:
        List of municipality codes
    """
    return list(FORMAT_REGISTRY.keys())


def register_format(
    municipality_code: str,
    format_class: Type[ProtocolFormat],
    patterns: Optional[List[str]] = None
) -> None:
    """
    Register a new format for a municipality.

    This allows extending the system with new municipality formats
    without modifying this file.

    Args:
        municipality_code: Unique code for the municipality
        format_class: The ProtocolFormat subclass to use
        patterns: Optional list of regex patterns to detect this format

    Example:
        from ocr.formats.format_detector import register_format
        from my_formats import TelAvivFormat

        register_format(
            'tel_aviv',
            TelAvivFormat,
            [r'תל[\\s\\-]*אביב', r'עיריית\\s+תל']
        )
    """
    FORMAT_REGISTRY[municipality_code.lower()] = format_class

    if patterns:
        MUNICIPALITY_PATTERNS[municipality_code.lower()] = patterns


def detect_municipality_name(text: str) -> Optional[str]:
    """
    Detect the municipality name from text without loading a format.

    Useful for quick identification without full parsing.

    Args:
        text: The OCR text

    Returns:
        Municipality name in Hebrew if detected, None otherwise
    """
    if not text:
        return None

    # Common municipality patterns
    patterns = [
        (r'עיריית\s+([א-ת\-\s]{2,20})', 'עירייה'),
        (r'מועצה\s+מקומית\s+([א-ת\-\s]{2,20})', 'מועצה מקומית'),
        (r'מועצה\s+אזורית\s+([א-ת\-\s]{2,20})', 'מועצה אזורית'),
    ]

    search_text = text[:1500]

    for pattern, _ in patterns:
        match = re.search(pattern, search_text)
        if match:
            return match.group(1).strip()

    return None


__all__ = [
    'detect_format',
    'get_format',
    'list_formats',
    'register_format',
    'detect_municipality_name',
    'FORMAT_REGISTRY',
]
