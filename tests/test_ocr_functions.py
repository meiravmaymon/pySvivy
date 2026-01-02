# -*- coding: utf-8 -*-
"""
Tests for OCR text processing functions.
בדיקות לפונקציות עיבוד טקסט OCR
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Import from the new modular structure
from ocr.text_utils import (
    fix_reversed_numbers,
    reverse_hebrew_text,
    normalize_final_letters
)
from ocr.date_extractor import (
    extract_meeting_date,
    extract_meeting_number
)


class TestFixReversedNumbers:
    """Tests for fix_reversed_numbers function."""

    def test_basic_reversed_number(self):
        """Test basic reversed number correction."""
        # 000,052 should become 250,000
        result = fix_reversed_numbers("סכום: 000,052 ש\"ח")
        assert "250,000" in result

    def test_multiple_reversed_numbers(self):
        """Test multiple reversed numbers in text."""
        text = "תקציב: 000,003 ועוד 000,051"
        result = fix_reversed_numbers(text)
        assert "300,000" in result
        assert "150,000" in result

    def test_normal_number_unchanged(self):
        """Test that normal numbers are not changed."""
        text = "סכום: 123,456 ש\"ח"
        result = fix_reversed_numbers(text)
        assert "123,456" in result

    def test_empty_text(self):
        """Test empty text handling."""
        assert fix_reversed_numbers("") == ""
        assert fix_reversed_numbers(None) is None

    def test_number_starting_with_zeros(self):
        """Test numbers that start with zeros (reversed)."""
        result = fix_reversed_numbers("000,001")
        assert "100,000" in result

    def test_budget_context(self):
        """Test in budget context."""
        text = "סך התב\"ר: 000,005 ש\"ח"
        result = fix_reversed_numbers(text)
        assert "500,000" in result


class TestReverseHebrewText:
    """Tests for reverse_hebrew_text function."""

    def test_basic_reversal(self):
        """Test basic Hebrew text reversal."""
        reversed_text = "םולש"
        result = reverse_hebrew_text(reversed_text)
        assert result == "שלום"

    def test_with_numbers(self):
        """Test reversal with Hebrew that contains numbers."""
        # Test with clearly reversed Hebrew text
        text = "ןהכ"  # כהן reversed
        result = reverse_hebrew_text(text)
        assert "כהן" in result or result == "כהן"

    def test_empty_text(self):
        """Test empty text handling."""
        assert reverse_hebrew_text("") == ""
        assert reverse_hebrew_text(None) == ""


class TestNormalizeFinalLetters:
    """Tests for normalize_final_letters function."""

    def test_final_mem(self):
        """Test final mem normalization."""
        # מ at end should become ם
        result = normalize_final_letters("שלומ")
        assert result.endswith("ם")

    def test_final_nun(self):
        """Test final nun normalization."""
        # נ at end should become ן
        result = normalize_final_letters("דנ")
        assert result.endswith("ן")

    def test_final_tsadi(self):
        """Test final tsadi normalization."""
        # צ at end should become ץ
        result = normalize_final_letters("ארצ")
        assert result.endswith("ץ")

    def test_final_peh(self):
        """Test final peh normalization."""
        # פ at end should become ף
        result = normalize_final_letters("כספ")
        assert result.endswith("ף")

    def test_final_kaf(self):
        """Test final kaf normalization."""
        # כ at end should become ך
        result = normalize_final_letters("מלכ")
        assert result.endswith("ך")

    def test_middle_letters_unchanged(self):
        """Test that middle letters are not changed."""
        result = normalize_final_letters("מלכים")
        # כ in the middle should stay as כ
        assert "כ" in result

    def test_empty_text(self):
        """Test empty text handling."""
        assert normalize_final_letters("") == ""


class TestExtractMeetingDate:
    """Tests for extract_meeting_date function."""

    def test_israeli_date_format(self):
        """Test DD/MM/YYYY format."""
        text = "מיום 15/03/2023"
        result = extract_meeting_date(text)
        assert result is not None
        assert result == "2023-03-15"

    def test_date_with_dots(self):
        """Test DD.MM.YYYY format."""
        text = "בתאריך 15.03.2023"
        result = extract_meeting_date(text)
        assert result == "2023-03-15"

    def test_no_date(self):
        """Test text without date."""
        text = "פרוטוקול ישיבה"
        result = extract_meeting_date(text)
        assert result is None


class TestExtractMeetingNumber:
    """Tests for extract_meeting_number function."""

    def test_meeting_number_format(self):
        """Test meeting number extraction."""
        text = "פרוטוקול ישיבה מס' 82"
        result = extract_meeting_number(text)
        assert result == 82

    def test_meeting_with_quotes(self):
        """Test meeting number with different quote styles."""
        text = "ישיבה מס\" 105"
        result = extract_meeting_number(text)
        assert result == 105

    def test_no_meeting_number(self):
        """Test text without meeting number."""
        text = "פרוטוקול כללי"
        result = extract_meeting_number(text)
        assert result is None
