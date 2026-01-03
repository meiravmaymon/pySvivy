# -*- coding: utf-8 -*-
"""
Protocol Format Definitions Package.
חבילת הגדרות פורמטים לפרוטוקולים עירוניים

This package provides format definitions for different municipalities.
Each municipality may have slightly different protocol formats.

Usage:
    from ocr.formats import detect_format, get_format

    # Auto-detect format from text
    fmt = detect_format(ocr_text)

    # Get specific format
    fmt = get_format('yehud')

    # Extract data using format
    header = fmt.extract_header(text)
    attendees = fmt.extract_attendees(text)
"""

from ocr.formats.base_format import (
    ProtocolFormat,
    HeaderInfo,
    AttendeeInfo,
    DiscussionInfo,
    VoteInfo,
    DecisionInfo,
)
from ocr.formats.format_detector import detect_format, get_format
from ocr.formats.yehud_format import YehudFormat
from ocr.formats.generic_format import GenericFormat

__all__ = [
    # Base classes
    'ProtocolFormat',
    'HeaderInfo',
    'AttendeeInfo',
    'DiscussionInfo',
    'VoteInfo',
    'DecisionInfo',
    # Format classes
    'YehudFormat',
    'GenericFormat',
    # Functions
    'detect_format',
    'get_format',
]

__version__ = '1.0.0'
