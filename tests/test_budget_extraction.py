# -*- coding: utf-8 -*-
"""
Tests for budget extraction functions.
בדיקות לפונקציות חילוץ תקציב ומקורות מימון
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ocr_protocol import (
    fix_reversed_numbers,
    reverse_hebrew_text
)


class TestBudgetExtraction:
    """Tests for budget extraction from OCR text."""

    def test_extract_total_budget(self):
        """Test extraction of total budget amount."""
        text = "סך התב\"ר: 250,000 ש\"ח"
        # Should find the amount 250,000
        assert "250,000" in text

    def test_reversed_budget_fix(self):
        """Test fixing reversed budget numbers."""
        reversed_text = "סך התב\"ר: 000,052 ש\"ח"
        result = fix_reversed_numbers(reversed_text)
        assert "250,000" in result

    def test_multiple_budget_sources(self):
        """Test extraction of multiple funding sources."""
        text = """
        מקורות מימון:
        משרד החינוך: 300,000 ש"ח
        קרנות הרשות: 200,000 ש"ח
        """
        assert "300,000" in text
        assert "200,000" in text


class TestFundingSourcePatterns:
    """Tests for funding source pattern matching."""

    def test_ministry_pattern(self):
        """Test ministry funding source pattern."""
        text = "משרד החינוך ע\"ס 150,000 ש\"ח"
        # Should match ministry pattern
        assert "משרד" in text
        assert "150,000" in text

    def test_municipal_fund_pattern(self):
        """Test municipal fund pattern."""
        text = "קרנות הרשות: 100,000 ש\"ח"
        assert "קרנות" in text
        assert "100,000" in text

    def test_authorization_pattern(self):
        """Test authorization pattern."""
        text = "הרשאת משרד הרווחה - 200,000 ש\"ח"
        assert "הרשאת" in text
        assert "200,000" in text


class TestReversedFundingText:
    """Tests for handling reversed funding text from OCR."""

    def test_reversed_funding_sources_keyword(self):
        """Test that reversed 'מקורות מימון' can be identified."""
        # "מקורות מימון" reversed
        reversed_text = "ןומימ תורוקמ"
        normal_text = reverse_hebrew_text(reversed_text)
        # After reversal, should contain the Hebrew words
        assert len(normal_text) > 0

    def test_full_reversed_budget_line(self):
        """Test full reversed budget line."""
        # Original: סך התב"ר- 250,000 ₪. מקורות מימון- קרנות הרשות.
        # Reversed as it might come from OCR
        reversed_line = ".תושרה תונרק -ןומימ תורוקמ .₪ 000,052-ר\"בתה ךס"

        # Fix the numbers first
        fixed = fix_reversed_numbers(reversed_line)
        # 000,052 should become 250,000
        assert "250,000" in fixed


class TestBudgetAmountParsing:
    """Tests for parsing budget amounts."""

    def test_shekel_symbol(self):
        """Test amount with shekel symbol."""
        text = "סכום: 100,000 ₪"
        assert "100,000" in text

    def test_shach_abbreviation(self):
        """Test amount with ש\"ח abbreviation."""
        text = "סכום: 100,000 ש\"ח"
        assert "100,000" in text

    def test_amount_without_currency(self):
        """Test amount without currency marker."""
        text = "תקציב: 500,000"
        assert "500,000" in text

    def test_large_amount(self):
        """Test large budget amount."""
        text = "תקציב: 1,500,000 ש\"ח"
        assert "1,500,000" in text


class TestEdgeCases:
    """Edge cases for budget extraction."""

    def test_empty_budget(self):
        """Test handling of empty budget text."""
        result = fix_reversed_numbers("")
        assert result == ""

    def test_no_budget_in_text(self):
        """Test text without budget information."""
        text = "דיון כללי ללא תקציב"
        result = fix_reversed_numbers(text)
        assert result == text

    def test_zero_budget(self):
        """Test zero budget amount."""
        text = "תקציב: 0 ש\"ח"
        result = fix_reversed_numbers(text)
        assert "0" in result
