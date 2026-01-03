# -*- coding: utf-8 -*-
"""
Generic Protocol Format.
פורמט גנרי לפרוטוקולים עירוניים

This module provides a generic format that works with most
Israeli municipal protocol documents. Used as a fallback when
no specific format is detected.
"""

import re
from typing import List, Optional
from ocr.formats.base_format import (
    ProtocolFormat,
    HeaderInfo,
    AttendeeInfo,
    DiscussionInfo,
    VoteInfo,
    DecisionInfo,
    DialogueEntry,
    BudgetInfo,
    DecisionStatus,
    VoteType,
)
from ocr.text_utils import reverse_hebrew_text, normalize_final_letters


class GenericFormat(ProtocolFormat):
    """
    Generic protocol format for Israeli municipalities.

    This format uses common patterns found across different
    municipalities and serves as a fallback when no specific
    format is detected.
    """

    municipality_code = "generic"
    municipality_name = "Generic"
    municipality_name_he = "כללי"

    # Common roles across municipalities
    COMMON_ROLES = [
        "ראש המועצה",
        "ראש העיר",
        "ראש הרשות",
        "סגן ראש המועצה",
        "סגן ראש העיר",
        "חבר מועצה",
        "חברת מועצה",
        'מנכ"ל',
        "מנהל כללי",
        "גזבר",
        "גזברית",
        "יועץ משפטי",
        "יועצת משפטית",
        "מהנדס",
        "מהנדסת",
        "מזכיר",
        "מזכירה",
        "מבקר",
        "מבקרת",
    ]

    # Common committee names
    COMMON_COMMITTEES = [
        "מליאת המועצה",
        "מועצת העיר",
        "מועצה מקומית",
        "ועדת הנהלה",
        "ועדת כספים",
        "ועדת תכנון ובניה",
        "ועדה מקומית לתכנון ובניה",
        "ועדת חינוך",
        "ועדת רווחה",
        "ועדה לאיכות הסביבה",
    ]

    def extract_header(self, text: str) -> HeaderInfo:
        """Extract header using generic patterns."""
        header = HeaderInfo(raw_text=text[:500] if text else "")

        if not text:
            return header

        # Try to find municipality name
        municipality_patterns = [
            r'עיריית\s+([א-ת\-\s]+)',
            r'מועצה\s+(מקומית|אזורית)\s+([א-ת\-\s]+)',
            r'רשות\s+מקומית\s+([א-ת\-\s]+)',
        ]

        for pattern in municipality_patterns:
            match = re.search(pattern, text)
            if match:
                # Get the last captured group (the name)
                groups = match.groups()
                header.municipality = groups[-1].strip() if groups else ""
                break

        # Extract committee name
        for committee in self.COMMON_COMMITTEES:
            if committee in text:
                header.committee_name = committee
                break

        if not header.committee_name:
            committee_pattern = r'(ועד[הת]\s+[א-ת\s]+|מליאת?\s+ה?מועצה)'
            match = re.search(committee_pattern, text)
            if match:
                header.committee_name = match.group(1).strip()

        # Extract meeting number
        number_patterns = [
            r'ישיבה\s*(מס[\'׳]?|מספר|#)?\s*[:\-]?\s*(\d+)',
            r'פרוטוקול\s*(מס[\'׳]?|מספר|#)?\s*[:\-]?\s*(\d+)',
            r'ישיבה\s+מספר\s+(\d+)',
        ]

        for pattern in number_patterns:
            match = re.search(pattern, text)
            if match:
                groups = match.groups()
                for g in reversed(groups):
                    if g and g.isdigit():
                        header.meeting_number = int(g)
                        break
                if header.meeting_number:
                    break

        # Extract date (multiple formats)
        date_patterns = [
            r'(\d{1,2})[/\.\-](\d{1,2})[/\.\-](20\d{2}|\d{2})',
            r'(\d{1,2})\s+ב?(ינואר|פברואר|מרץ|אפריל|מאי|יוני|יולי|אוגוסט|ספטמבר|אוקטובר|נובמבר|דצמבר)\s+(20\d{2})',
        ]

        month_map = {
            'ינואר': '01', 'פברואר': '02', 'מרץ': '03', 'אפריל': '04',
            'מאי': '05', 'יוני': '06', 'יולי': '07', 'אוגוסט': '08',
            'ספטמבר': '09', 'אוקטובר': '10', 'נובמבר': '11', 'דצמבר': '12'
        }

        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                groups = match.groups()
                if len(groups) == 3:
                    day = groups[0]
                    if groups[1].isdigit():
                        month = groups[1]
                    else:
                        month = month_map.get(groups[1], '01')
                    year = groups[2]
                    if len(year) == 2:
                        year = f"20{year}"
                    header.meeting_date = f"{day}/{month}/{year}"
                    break

        # Meeting type
        if 'שלא מן המניין' in text:
            header.meeting_type = 'שלא מן המניין'
        elif 'מיוחדת' in text:
            header.meeting_type = 'מיוחדת'
        else:
            header.meeting_type = 'רגילה'

        # Calculate confidence
        confidence = 0.3  # Base for generic
        if header.municipality:
            confidence += 0.2
        if header.meeting_number:
            confidence += 0.2
        if header.meeting_date:
            confidence += 0.2
        if header.committee_name:
            confidence += 0.1

        header.confidence = confidence

        return header

    def extract_attendees(self, text: str) -> List[AttendeeInfo]:
        """Extract present attendees using generic patterns."""
        return self._extract_people_generic(text, "present")

    def extract_absent(self, text: str) -> List[AttendeeInfo]:
        """Extract absent members using generic patterns."""
        return self._extract_people_generic(text, "absent")

    def extract_staff(self, text: str) -> List[AttendeeInfo]:
        """Extract staff using generic patterns."""
        return self._extract_people_generic(text, "staff")

    def _extract_people_generic(
        self,
        text: str,
        attendance_type: str
    ) -> List[AttendeeInfo]:
        """
        Generic extraction of people from text.

        Args:
            text: Section text
            attendance_type: 'present', 'absent', or 'staff'

        Returns:
            List of AttendeeInfo
        """
        if not text:
            return []

        attendees = []
        lines = text.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line or len(line) < 3:
                continue

            # Skip header/label lines
            skip_keywords = [
                'נוכחים', 'חסרים', 'נעדרים', 'סגל',
                'משתתפים', 'השתתפו', 'נכחו',
            ]
            if any(kw in line for kw in skip_keywords):
                continue

            attendee = self._parse_generic_attendee_line(line, attendance_type)
            if attendee:
                attendees.append(attendee)

        return attendees

    def _parse_generic_attendee_line(
        self,
        line: str,
        attendance_type: str
    ) -> Optional[AttendeeInfo]:
        """Parse a single attendee line with generic patterns."""
        if not line or len(line) < 3:
            return None

        # Check for reversed text
        is_reversed = self._check_reversed(line)
        if is_reversed:
            line = reverse_hebrew_text(line)

        attendee = AttendeeInfo(
            name="",
            role="",
            attendance_type=attendance_type,
            is_reversed=is_reversed,
            raw_text=line
        )

        # Try different separators
        separators = [' - ', ' – ', ': ', ', ', ' / ']
        parts = None

        for sep in separators:
            if sep in line:
                parts = line.split(sep, 1)
                break

        if parts and len(parts) == 2:
            part1, part2 = [p.strip() for p in parts]

            # Determine which is name and which is role
            if self._is_role_generic(part1):
                attendee.role = part1
                attendee.name = part2
            elif self._is_role_generic(part2):
                attendee.name = part1
                attendee.role = part2
            else:
                # Assume first is name
                attendee.name = part1
                attendee.role = part2
        else:
            # No separator - try to find role in line
            for role in self.COMMON_ROLES:
                if role in line:
                    attendee.role = role
                    attendee.name = line.replace(role, '').strip(' -,/')
                    break

            if not attendee.name:
                attendee.name = line

        # Clean up
        attendee.name = self._clean_name_generic(attendee.name)

        if not attendee.name or len(attendee.name) < 2:
            return None

        attendee.confidence = 0.6 if attendee.role else 0.4

        return attendee

    def _check_reversed(self, text: str) -> bool:
        """Check if text appears reversed."""
        if not text:
            return False

        final_letters = ['ם', 'ן', 'ף', 'ץ', 'ך']
        words = text.split()

        for word in words:
            if len(word) > 1:
                # Final letter at start
                if word[0] in final_letters:
                    return True
                # Final letter in middle
                if any(fl in word[1:-1] for fl in final_letters if len(word) > 2):
                    return True

        return False

    def _is_role_generic(self, text: str) -> bool:
        """Check if text matches a known role."""
        text = text.strip()
        for role in self.COMMON_ROLES:
            if role in text or text in role:
                return True

        # Also check for role-like patterns
        role_patterns = [
            r'ראש\s+ה',
            r'סגן',
            r'חבר\s+מועצה',
            r'גזבר',
            r'יועץ',
            r'מהנדס',
            r'מנכ"ל',
        ]
        return any(re.search(p, text) for p in role_patterns)

    def _clean_name_generic(self, name: str) -> str:
        """Clean up extracted name."""
        if not name:
            return ""

        # Remove titles
        name = re.sub(r'^(מר|גב[\'׳]?|ד"ר|עו"ד|רו"ח|פרופ[\'׳]?)\s*', '', name)

        # Remove numbering
        name = re.sub(r'^\d+\s*[\.\)]\s*', '', name)

        # Remove trailing punctuation
        name = re.sub(r'\s*[-,;:]\s*$', '', name)

        # Normalize whitespace
        name = ' '.join(name.split())

        return name.strip()

    def extract_discussions(self, text: str) -> List[DiscussionInfo]:
        """Extract discussions using generic patterns."""
        if not text:
            return []

        discussions = []

        # Try multiple patterns
        item_patterns = [
            r'סעיף\s*(מס[\'׳]?|מספר)?\s*[:\-]?\s*(\d+)',
            r'נושא\s*(מס[\'׳]?|מספר)?\s*[:\-]?\s*(\d+)',
            r'^(\d+)\s*[\.:\-]\s+',
        ]

        # Find all matches and their positions
        all_matches = []
        for pattern in item_patterns:
            for match in re.finditer(pattern, text, re.MULTILINE):
                # Extract item number
                groups = match.groups()
                item_num = next((g for g in groups if g and g.isdigit()), "")
                if item_num:
                    all_matches.append((match.start(), match.end(), item_num))

        # Sort by position
        all_matches.sort(key=lambda x: x[0])

        # Remove duplicates that are too close
        filtered_matches = []
        for start, end, num in all_matches:
            if not filtered_matches or start - filtered_matches[-1][1] > 20:
                filtered_matches.append((start, end, num))

        # Extract each discussion
        for i, (start, end, item_num) in enumerate(filtered_matches):
            # Get text until next item or end
            if i + 1 < len(filtered_matches):
                item_text = text[end:filtered_matches[i + 1][0]]
            else:
                item_text = text[end:end + 3000]  # Limit length

            discussion = self._parse_generic_discussion(item_num, item_text)
            if discussion:
                discussions.append(discussion)

        return discussions

    def _parse_generic_discussion(
        self,
        item_number: str,
        text: str
    ) -> Optional[DiscussionInfo]:
        """Parse a discussion with generic patterns."""
        if not text:
            return None

        discussion = DiscussionInfo(
            item_number=item_number,
            raw_text=text[:1000]
        )

        # Title is usually the first non-empty line
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if lines:
            discussion.title = lines[0][:200]

        # Extract vote
        discussion.vote = self.extract_vote(text)

        # Extract decision
        discussion.decision = self.extract_decision(text)

        # Basic confidence
        confidence = 0.4
        if discussion.title:
            confidence += 0.2
        if discussion.vote:
            confidence += 0.2
        if discussion.decision:
            confidence += 0.2

        discussion.confidence = confidence

        return discussion
