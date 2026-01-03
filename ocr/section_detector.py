# -*- coding: utf-8 -*-
"""
Section Detection for Municipal Protocol OCR.
זיהוי סקציות בפרוטוקולים עירוניים

This module detects section boundaries in protocol documents:
- Header (כותרת) - Municipality, committee, date
- Attendees (נוכחים) - Present council members
- Absent (נעדרים/חסרים) - Absent members
- Staff (סגל) - Municipal staff
- Agenda (סדר יום) - Agenda overview
- Discussions (סעיפים) - Individual discussion items

The detector handles both normal and reversed Hebrew text from OCR.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum


class SectionType(Enum):
    """Types of sections in a protocol document."""
    HEADER = "header"
    ATTENDEES = "attendees"
    ABSENT = "absent"
    STAFF = "staff"
    AGENDA = "agenda"
    DISCUSSIONS = "discussions"
    UNKNOWN = "unknown"


@dataclass
class SectionInfo:
    """Information about a detected section."""
    section_type: SectionType
    start_pos: int
    end_pos: int
    text: str
    confidence: float
    is_reversed: bool = False
    anchor_found: str = ""


@dataclass
class DetectionResult:
    """Result of section detection on a document."""
    sections: Dict[SectionType, SectionInfo] = field(default_factory=dict)
    document_reversed: bool = False
    overall_confidence: float = 0.0
    raw_text: str = ""

    def get_section(self, section_type: SectionType) -> Optional[SectionInfo]:
        """Get a specific section if detected."""
        return self.sections.get(section_type)

    def has_section(self, section_type: SectionType) -> bool:
        """Check if a section was detected."""
        return section_type in self.sections


class SectionDetector:
    """
    Detects section boundaries in Hebrew municipal protocol documents.

    The detector uses anchor patterns (both normal and reversed) to identify
    where each section begins, then calculates section boundaries based on
    the relative order of detected anchors.
    """

    # Section anchors - normal Hebrew text
    ANCHORS_NORMAL = {
        SectionType.HEADER: [
            r'פרוטוקול',
            r'ישיבת\s*(מועצה|ועדה)',
            r'מועצת\s*(העיר|המקומית)',
            r'עיריית',
            r'מועצה\s*מקומית',
        ],
        SectionType.ATTENDEES: [
            r'נוכחים',
            r'משתתפים',
            r'חברי\s*(המועצה|הועדה)\s*הנוכחים',
            r'נכחו',
            r'השתתפו',
        ],
        SectionType.ABSENT: [
            r'נעדרים',
            r'חסרים',
            r'לא\s*נכחו',
            r'חברים\s*שנעדרו',
        ],
        SectionType.STAFF: [
            r'סגל',
            r'אנשי\s*מקצוע',
            r'נוכחים\s*נוספים',
            r'משתתפים\s*נוספים',
            r'עובדי\s*(העירייה|הרשות)',
        ],
        SectionType.AGENDA: [
            r'סדר\s*היום',
            r'על\s*סדר\s*היום',
            r'נושאים\s*לדיון',
        ],
        SectionType.DISCUSSIONS: [
            r'סעיף\s*(מס[\'׳]?|מספר)?\s*\d+',
            r'סעיף\s+[א-ת]',
            r'נושא\s*(מס[\'׳]?|מספר)?\s*\d+',
        ],
    }

    # Section anchors - reversed Hebrew text (common OCR issue)
    ANCHORS_REVERSED = {
        SectionType.HEADER: [
            r'לוקוטורפ',
            r'תבשי',
            r'תייריע',
            r'הצעומ',
        ],
        SectionType.ATTENDEES: [
            r'םיחכונ',
            r'םיפתתשמ',
            r'וחכנ',
        ],
        SectionType.ABSENT: [
            r'םירדענ',
            r'םירסח',
        ],
        SectionType.STAFF: [
            r'לגס',
            r'םיפסונ\s*םיחכונ',
        ],
        SectionType.AGENDA: [
            r'םויה\s*רדס',
            r'ןויד[ל]?\s*םיאשונ',
        ],
        SectionType.DISCUSSIONS: [
            r'\d+\s*[\'׳]?סמ\s*ףיעס',
            r'ףיעס',
        ],
    }

    def __init__(self):
        """Initialize the section detector."""
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for efficiency."""
        self._patterns_normal = {}
        self._patterns_reversed = {}

        for section_type, patterns in self.ANCHORS_NORMAL.items():
            self._patterns_normal[section_type] = [
                re.compile(p, re.IGNORECASE | re.MULTILINE)
                for p in patterns
            ]

        for section_type, patterns in self.ANCHORS_REVERSED.items():
            self._patterns_reversed[section_type] = [
                re.compile(p, re.IGNORECASE | re.MULTILINE)
                for p in patterns
            ]

    def detect_document_direction(self, text: str) -> Tuple[bool, float]:
        """
        Detect if the document text is reversed.

        Returns:
            Tuple of (is_reversed, confidence)
        """
        # Count matches for normal vs reversed anchors
        normal_matches = 0
        reversed_matches = 0

        # Check header patterns (most reliable)
        for pattern in self._patterns_normal.get(SectionType.HEADER, []):
            if pattern.search(text):
                normal_matches += 2  # Header is weighted more

        for pattern in self._patterns_reversed.get(SectionType.HEADER, []):
            if pattern.search(text):
                reversed_matches += 2

        # Check attendees patterns
        for pattern in self._patterns_normal.get(SectionType.ATTENDEES, []):
            if pattern.search(text):
                normal_matches += 1

        for pattern in self._patterns_reversed.get(SectionType.ATTENDEES, []):
            if pattern.search(text):
                reversed_matches += 1

        # Check discussions patterns
        for pattern in self._patterns_normal.get(SectionType.DISCUSSIONS, []):
            if pattern.search(text):
                normal_matches += 1

        for pattern in self._patterns_reversed.get(SectionType.DISCUSSIONS, []):
            if pattern.search(text):
                reversed_matches += 1

        total = normal_matches + reversed_matches
        if total == 0:
            return False, 0.0

        is_reversed = reversed_matches > normal_matches
        confidence = abs(normal_matches - reversed_matches) / total

        return is_reversed, confidence

    def _find_anchor_positions(
        self,
        text: str,
        use_reversed: bool = False
    ) -> Dict[SectionType, List[Tuple[int, str, float]]]:
        """
        Find all anchor positions in the text.

        Returns:
            Dict mapping section type to list of (position, anchor_text, confidence)
        """
        patterns = self._patterns_reversed if use_reversed else self._patterns_normal
        results = {}

        for section_type, pattern_list in patterns.items():
            matches = []
            for i, pattern in enumerate(pattern_list):
                for match in pattern.finditer(text):
                    # Earlier patterns in the list are more specific/confident
                    confidence = 1.0 - (i * 0.1)
                    matches.append((match.start(), match.group(), confidence))

            if matches:
                # Sort by position
                matches.sort(key=lambda x: x[0])
                results[section_type] = matches

        return results

    def _calculate_section_boundaries(
        self,
        text: str,
        anchor_positions: Dict[SectionType, List[Tuple[int, str, float]]]
    ) -> Dict[SectionType, SectionInfo]:
        """
        Calculate section boundaries based on anchor positions.

        Uses the expected order of sections and detected anchors to
        determine where each section starts and ends.
        """
        # Expected section order in a typical protocol
        expected_order = [
            SectionType.HEADER,
            SectionType.ATTENDEES,
            SectionType.ABSENT,
            SectionType.STAFF,
            SectionType.AGENDA,
            SectionType.DISCUSSIONS,
        ]

        # Get first anchor position for each section type
        first_positions = {}
        for section_type, matches in anchor_positions.items():
            if matches:
                first_positions[section_type] = matches[0]

        # Sort sections by their detected position
        sorted_sections = sorted(
            first_positions.items(),
            key=lambda x: x[1][0]
        )

        sections = {}
        text_len = len(text)

        for i, (section_type, (start_pos, anchor_text, confidence)) in enumerate(sorted_sections):
            # End position is the start of the next section, or end of text
            if i + 1 < len(sorted_sections):
                end_pos = sorted_sections[i + 1][1][0]
            else:
                end_pos = text_len

            section_text = text[start_pos:end_pos].strip()

            sections[section_type] = SectionInfo(
                section_type=section_type,
                start_pos=start_pos,
                end_pos=end_pos,
                text=section_text,
                confidence=confidence,
                is_reversed=False,  # Will be set by caller
                anchor_found=anchor_text
            )

        return sections

    def detect(self, text: str) -> DetectionResult:
        """
        Detect sections in a protocol document.

        Args:
            text: The OCR text from the protocol PDF

        Returns:
            DetectionResult with all detected sections
        """
        if not text or not text.strip():
            return DetectionResult(raw_text=text)

        # Detect document direction
        is_reversed, direction_confidence = self.detect_document_direction(text)

        # Find anchor positions
        anchor_positions = self._find_anchor_positions(text, use_reversed=is_reversed)

        # If no anchors found, try the other direction
        if not anchor_positions:
            is_reversed = not is_reversed
            anchor_positions = self._find_anchor_positions(text, use_reversed=is_reversed)

        # Calculate section boundaries
        sections = self._calculate_section_boundaries(text, anchor_positions)

        # Mark sections as reversed if document is reversed
        if is_reversed:
            for section_info in sections.values():
                section_info.is_reversed = True

        # Calculate overall confidence
        if sections:
            overall_confidence = sum(s.confidence for s in sections.values()) / len(sections)
        else:
            overall_confidence = 0.0

        return DetectionResult(
            sections=sections,
            document_reversed=is_reversed,
            overall_confidence=overall_confidence,
            raw_text=text
        )

    def get_section_text(
        self,
        text: str,
        section_type: SectionType
    ) -> Optional[str]:
        """
        Extract text for a specific section.

        Args:
            text: Full document text
            section_type: The section to extract

        Returns:
            Section text if found, None otherwise
        """
        result = self.detect(text)
        section = result.get_section(section_type)

        if section:
            return section.text
        return None

    def get_all_discussion_positions(self, text: str) -> List[Tuple[int, str]]:
        """
        Find all discussion/agenda item positions in the document.

        This is useful for splitting the discussions section into
        individual agenda items.

        Returns:
            List of (position, item_number_or_title)
        """
        # Detect direction first
        is_reversed, _ = self.detect_document_direction(text)

        # Patterns for discussion items
        if is_reversed:
            patterns = [
                r'(\d+)\s*[\'׳]?סמ\s*ףיעס',
                r'(\d+)\s*אשונ',
            ]
        else:
            patterns = [
                r'סעיף\s*(מס[\'׳]?|מספר)?\s*(\d+)',
                r'נושא\s*(מס[\'׳]?|מספר)?\s*(\d+)',
                r'(\d+)\s*[\.:\-]\s*',  # Just number followed by punctuation
            ]

        positions = []
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.MULTILINE):
                # Extract the item number from the match
                groups = match.groups()
                item_num = next((g for g in groups if g and g.isdigit()), "")
                positions.append((match.start(), item_num))

        # Sort by position and remove duplicates
        positions.sort(key=lambda x: x[0])

        # Remove duplicates that are too close together
        filtered = []
        for pos, num in positions:
            if not filtered or pos - filtered[-1][0] > 50:  # At least 50 chars apart
                filtered.append((pos, num))

        return filtered


def detect_sections(text: str) -> DetectionResult:
    """
    Convenience function to detect sections in a protocol document.

    Args:
        text: The OCR text from the protocol PDF

    Returns:
        DetectionResult with all detected sections
    """
    detector = SectionDetector()
    return detector.detect(text)


def get_section(text: str, section_type: SectionType) -> Optional[str]:
    """
    Convenience function to extract a specific section.

    Args:
        text: Full document text
        section_type: The section to extract

    Returns:
        Section text if found, None otherwise
    """
    detector = SectionDetector()
    return detector.get_section_text(text, section_type)


# Export for convenience
__all__ = [
    'SectionType',
    'SectionInfo',
    'DetectionResult',
    'SectionDetector',
    'detect_sections',
    'get_section',
]
