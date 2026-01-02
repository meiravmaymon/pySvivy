# -*- coding: utf-8 -*-
"""
Budget and funding source extraction for Hebrew OCR processing.
פונקציות לחילוץ תקציב ומקורות מימון מטקסט עברי

Functions:
- extract_budget_amount: Extract total budget (תב"ר) amount
- extract_funding_sources: Extract funding sources with amounts
"""
import re
from ocr.text_utils import reverse_hebrew_text, fix_reversed_numbers


def parse_amount(amount_str):
    """
    Parse a monetary amount string to integer.

    Args:
        amount_str: Amount string like "250,000" or "250000"

    Returns:
        Integer amount, or 0 if parsing fails
    """
    if not amount_str:
        return 0

    # Remove currency symbols and whitespace
    cleaned = re.sub(r'[₪ש"ח\s]', '', amount_str)
    # Remove commas
    cleaned = cleaned.replace(',', '')
    # Remove dots (if used as thousands separator)
    if cleaned.count('.') > 1:
        cleaned = cleaned.replace('.', '')

    try:
        return int(float(cleaned))
    except ValueError:
        return 0


def extract_budget_amount(text):
    """
    Extract total budget amount (סך התב"ר) from text.

    Args:
        text: Text to search for budget

    Returns:
        dict with 'amount' (int) and 'raw' (str), or None
    """
    if not text:
        return None

    # First, try to fix reversed text
    search_text = text
    fixed_text = fix_reversed_numbers(reverse_hebrew_text(text))

    # Budget patterns (both normal and reversed Hebrew)
    patterns = [
        # Normal Hebrew: סך התב"ר: 250,000 ש"ח
        r"(?:סך\s+)?(?:ה)?תב[\"'\u05f3]ר[:\s-]+([0-9,\.]+)\s*(?:₪|ש[\"'\u05f3]ח)?",
        # With explicit total: סה"כ תב"ר
        r"סה[\"'\u05f3]כ\s+(?:ה)?תב[\"'\u05f3]ר[:\s-]+([0-9,\.]+)",
        # תקציב: 250,000
        r"תקציב[:\s]+([0-9,\.]+)\s*(?:₪|ש[\"'\u05f3]ח)?",
        # עלות: 250,000
        r"עלות[:\s]+([0-9,\.]+)\s*(?:₪|ש[\"'\u05f3]ח)?",
        # סכום: 250,000
        r"סכום[:\s]+([0-9,\.]+)\s*(?:₪|ש[\"'\u05f3]ח)?",
    ]

    # Search in both original and fixed text
    for search_in in [fixed_text, search_text]:
        for pattern in patterns:
            match = re.search(pattern, search_in, re.IGNORECASE)
            if match:
                raw_amount = match.group(1)
                amount = parse_amount(raw_amount)
                if amount > 0:
                    return {
                        'amount': amount,
                        'raw': raw_amount
                    }

    return None


def extract_funding_sources(text):
    """
    Extract funding sources with their amounts.

    Args:
        text: Text to search for funding sources

    Returns:
        List of dicts with 'name' and 'amount', or empty list
    """
    if not text:
        return []

    sources = []

    # First, reverse and fix the text
    search_text = fix_reversed_numbers(reverse_hebrew_text(text))

    # Also search in original (in case it's not reversed)
    texts_to_search = [search_text, text]

    # Find the "מקורות מימון" section
    section_patterns = [
        r'מקורות?\s+מימון[:\s-]+(.*?)(?=\n\n|דברי\s+הסבר|סעיף\s+מס|הצבעה|$)',
        r'מקור\s+מימון[:\s-]+(.*?)(?=\n\n|דברי\s+הסבר|סעיף|$)',
    ]

    funding_section = None
    for search_in in texts_to_search:
        for pattern in section_patterns:
            match = re.search(pattern, search_in, re.DOTALL | re.IGNORECASE)
            if match:
                funding_section = match.group(1)
                break
        if funding_section:
            break

    # If no section found, search in full text
    search_areas = [funding_section] if funding_section else texts_to_search

    # Patterns for individual funding sources
    source_patterns = [
        # משרד X: סכום ₪
        r'(משרד\s+[א-ת\s]+?)[:\s-]+([0-9,\.]+)\s*(?:₪|ש["\']ח)?',
        # הרשאת משרד X: סכום
        r'(הרשאת\s+משרד\s+[א-ת\s]+?)[:\s-]+([0-9,\.]+)',
        # קרנות הרשות: סכום
        r'(קרנות?\s+(?:ה)?רשות)[:\s-]+([0-9,\.]+)',
        # עירייה: סכום
        r'(עיריי?ה)[:\s-]+([0-9,\.]+)',
        # עצמי: סכום
        r'(מימון\s+עצמי|עצמי)[:\s-]+([0-9,\.]+)',
        # Name amount (generic pattern)
        r'([א-ת]{3,}[א-ת\s]*?)\s+([0-9,]+)\s*(?:₪|ש["\']ח)',
    ]

    seen_sources = set()

    for search_in in search_areas:
        if not search_in:
            continue

        for pattern in source_patterns:
            matches = re.finditer(pattern, search_in, re.IGNORECASE)
            for match in matches:
                name = match.group(1).strip()
                amount_str = match.group(2)
                amount = parse_amount(amount_str)

                # Clean up name
                name = re.sub(r'\s+', ' ', name)

                # Skip if already seen or invalid
                if name.lower() in seen_sources or amount <= 0:
                    continue
                if len(name) < 3:
                    continue

                seen_sources.add(name.lower())
                sources.append({
                    'name': name,
                    'amount': amount,
                    'raw_amount': amount_str
                })

    return sources


def extract_budget_data(text):
    """
    Extract complete budget data including total and sources.

    Args:
        text: Text to analyze

    Returns:
        dict with 'total' and 'sources'
    """
    total = extract_budget_amount(text)
    sources = extract_funding_sources(text)

    return {
        'total': total,
        'sources': sources
    }
