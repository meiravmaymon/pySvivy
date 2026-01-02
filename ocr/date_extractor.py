# -*- coding: utf-8 -*-
"""
Date extraction utilities for Hebrew OCR processing.
פונקציות לחילוץ תאריכים מטקסט עברי

Functions:
- extract_meeting_date: Extract date from protocol text
- extract_meeting_number: Extract meeting number
- parse_israeli_date: Parse DD/MM/YYYY format
"""
import re
from datetime import datetime


# Hebrew month names mapping
HEBREW_MONTHS = {
    'ינואר': 1, 'פברואר': 2, 'מרץ': 3, 'אפריל': 4,
    'מאי': 5, 'יוני': 6, 'יולי': 7, 'אוגוסט': 8,
    'ספטמבר': 9, 'אוקטובר': 10, 'נובמבר': 11, 'דצמבר': 12,
    # Alternative spellings
    'מרס': 3, 'מארס': 3,
    'ינו': 1, 'פבר': 2, 'מרצ': 3, 'אפר': 4,
    'יונ': 6, 'יול': 7, 'אוג': 8, 'ספט': 9,
    'אוק': 10, 'נוב': 11, 'דצמ': 12,
}


def parse_israeli_date(date_str):
    """
    Parse date in Israeli format (DD/MM/YYYY or DD.MM.YYYY).

    Args:
        date_str: Date string like "15/03/2023" or "15.03.2023"

    Returns:
        datetime object or None if parsing fails
    """
    if not date_str:
        return None

    # Clean the string
    date_str = date_str.strip()

    # Try DD/MM/YYYY format
    patterns = [
        r'(\d{1,2})[/.](\d{1,2})[/.](\d{4})',  # DD/MM/YYYY or DD.MM.YYYY
        r'(\d{1,2})[/.](\d{1,2})[/.](\d{2})',   # DD/MM/YY or DD.MM.YY
    ]

    for pattern in patterns:
        match = re.search(pattern, date_str)
        if match:
            day = int(match.group(1))
            month = int(match.group(2))
            year = int(match.group(3))

            # Handle 2-digit year
            if year < 100:
                year += 2000 if year < 50 else 1900

            try:
                return datetime(year, month, day)
            except ValueError:
                continue

    return None


def extract_meeting_date(text):
    """
    Extract meeting date from protocol text.

    Args:
        text: Protocol text to search

    Returns:
        Date string in YYYY-MM-DD format, or None
    """
    if not text:
        return None

    # Look for date patterns
    date_patterns = [
        # מיום DD/MM/YYYY
        r'מיום\s+(\d{1,2}[/.]\d{1,2}[/.]\d{2,4})',
        # בתאריך DD/MM/YYYY
        r'בתאריך\s+(\d{1,2}[/.]\d{1,2}[/.]\d{2,4})',
        # תאריך: DD/MM/YYYY
        r'תאריך[:\s]+(\d{1,2}[/.]\d{1,2}[/.]\d{2,4})',
        # נערכה ביום DD/MM/YYYY
        r'נערכה?\s+ביום\s+(\d{1,2}[/.]\d{1,2}[/.]\d{2,4})',
        # DD/MM/YYYY alone (less specific)
        r'(\d{1,2}[/.]\d{1,2}[/.]\d{4})',
    ]

    for pattern in date_patterns:
        match = re.search(pattern, text[:1000])  # Search in first 1000 chars
        if match:
            date = parse_israeli_date(match.group(1))
            if date:
                return date.strftime('%Y-%m-%d')

    # Try Hebrew date format: D ב[חודש] YYYY
    hebrew_pattern = r'(\d{1,2})\s+ב?(' + '|'.join(HEBREW_MONTHS.keys()) + r')\s+(\d{4})'
    match = re.search(hebrew_pattern, text[:1000])
    if match:
        day = int(match.group(1))
        month_name = match.group(2)
        year = int(match.group(3))
        month = HEBREW_MONTHS.get(month_name, 0)
        if month:
            try:
                date = datetime(year, month, day)
                return date.strftime('%Y-%m-%d')
            except ValueError:
                pass

    return None


def extract_meeting_number(text):
    """
    Extract meeting number from protocol text.

    Args:
        text: Protocol text to search

    Returns:
        Meeting number as integer, or None
    """
    if not text:
        return None

    # Meeting number patterns
    patterns = [
        # ישיבה מס' 82
        r"ישיבה\s+מס['\"]?\s*(\d+)",
        # ישיבה מספר 82
        r'ישיבה\s+מספר\s+(\d+)',
        # פרוטוקול מס' 82
        r"פרוטוקול\s+מס['\"]?\s*(\d+)",
        # ישיבה 82
        r'ישיבה\s+(\d+)',
        # מס' ישיבה: 82
        r"מס['\"]?\s*ישיבה[:\s]+(\d+)",
        # Reversed: 82 'סמ הבישי
        r"(\d+)\s*['\"]?\s*(?:סמ|םס)\s+הבישי",
    ]

    for pattern in patterns:
        match = re.search(pattern, text[:500])  # Search in first 500 chars
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                continue

    return None


def extract_meeting_type(text):
    """
    Extract the type of meeting (regular, special, urgent).

    Args:
        text: Protocol text to search

    Returns:
        Meeting type string, or 'רגילה' (regular) as default
    """
    if not text:
        return 'רגילה'

    # Check for special meeting types
    if re.search(r'ישיבה\s+(?:מן\s+המניין|מהמניין|רגילה)', text[:500]):
        return 'רגילה'
    if re.search(r'ישיבה\s+(?:שלא\s+מן\s+המניין|מיוחדת)', text[:500]):
        return 'מיוחדת'
    if re.search(r'ישיבה\s+(?:דחופה|חירום)', text[:500]):
        return 'דחופה'

    return 'רגילה'
