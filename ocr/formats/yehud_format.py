# -*- coding: utf-8 -*-
"""
Yehud-Monosson Protocol Format.
פורמט פרוטוקולים עיריית יהוד-מונוסון

This module defines the specific format patterns and extraction logic
for Yehud-Monosson municipal protocols.
"""

import re
from typing import List, Optional, Tuple
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


class YehudFormat(ProtocolFormat):
    """
    Protocol format for Yehud-Monosson municipality.

    Yehud-Monosson protocols typically follow this structure:
    - Header with municipality name, committee, date, meeting number
    - List of present council members (נוכחים)
    - List of absent members (נעדרים/חסרים)
    - List of staff (סגל)
    - Agenda items (סעיפים)
    """

    municipality_code = "yehud"
    municipality_name = "Yehud-Monosson"
    municipality_name_he = "יהוד-מונוסון"

    # Known committee names in Yehud
    COMMITTEES = [
        "מליאת המועצה",
        "מועצת העיר",
        "ועדת הנהלה",
        "ועדת כספים",
        "ועדת תכנון ובניה",
        "ועדת חינוך",
        "ועדת רווחה",
        "ועדת איכות הסביבה",
    ]

    # Known roles in Yehud
    ROLES = [
        "ראש העיר",
        "סגן ראש העיר",
        "חבר מועצה",
        "חברת מועצה",
        'מנכ"ל',
        "מנכל",
        "גזבר",
        "יועץ משפטי",
        "יועמ\"ש",
        "מהנדס העיר",
        "מזכיר העירייה",
        "מבקר העירייה",
    ]

    # Header patterns specific to Yehud
    _header_patterns = [
        r'עיריית\s+יהוד[\s\-]*מונוסון',
        r'ןוסונומ[\s\-]*דוהי\s*תייריע',  # Reversed
        r'מועצת\s+העיר\s+יהוד',
        r'פרוטוקול\s+ישיבה?\s*(מס[\'׳]?|מספר)?\s*(\d+)',
    ]

    # Meeting type patterns
    _meeting_type_patterns = [
        (r'ישיבה\s+רגילה', 'רגילה'),
        (r'ישיבה\s+שלא\s+מן\s+המניין', 'שלא מן המניין'),
        (r'ישיבה\s+מיוחדת', 'מיוחדת'),
        (r'ישיבה\s+חגיגית', 'חגיגית'),
    ]

    def extract_header(self, text: str) -> HeaderInfo:
        """Extract header information from Yehud protocol."""
        header = HeaderInfo(raw_text=text[:500] if text else "")

        if not text:
            return header

        # Municipality is known
        header.municipality = self.municipality_name_he

        # Extract committee name
        for committee in self.COMMITTEES:
            if committee in text:
                header.committee_name = committee
                break

        # If not found, try to extract from text
        if not header.committee_name:
            committee_pattern = r'(ועד[הת]\s+\S+|מליאת?\s+ה?מועצה|מועצת\s+העיר)'
            match = re.search(committee_pattern, text)
            if match:
                header.committee_name = match.group(1)

        # Extract meeting number
        number_patterns = [
            r'ישיבה\s*(מס[\'׳]?|מספר)?\s*[:\-]?\s*(\d+)',
            r'פרוטוקול\s*(מס[\'׳]?|מספר)?\s*[:\-]?\s*(\d+)',
            r'(\d+)\s*\'?סמ\s*(הבישי|לוקוטורפ)',  # Reversed
        ]

        for pattern in number_patterns:
            match = re.search(pattern, text)
            if match:
                # Get the last group that contains digits
                groups = match.groups()
                for g in reversed(groups):
                    if g and g.isdigit():
                        header.meeting_number = int(g)
                        break
                if header.meeting_number:
                    break

        # Extract date
        date_patterns = [
            r'(\d{1,2})[/\.\-](\d{1,2})[/\.\-](20\d{2}|\d{2})',
            r'(\d{1,2})\s+(לינואר|לפברואר|למרץ|לאפריל|למאי|ליוני|ליולי|לאוגוסט|לספטמבר|לאוקטובר|לנובמבר|לדצמבר)\s+(20\d{2})',
        ]

        for pattern in date_patterns:
            match = re.search(pattern, text)
            if match:
                groups = match.groups()
                if len(groups) == 3:
                    # Numeric date
                    day, month, year = groups
                    if len(year) == 2:
                        year = f"20{year}"
                    header.meeting_date = f"{day}/{month}/{year}"
                    break

        # Extract meeting type
        header.meeting_type = "רגילה"  # Default
        for pattern, meeting_type in self._meeting_type_patterns:
            if re.search(pattern, text):
                header.meeting_type = meeting_type
                break

        # Calculate confidence
        confidence_score = 0
        if header.municipality:
            confidence_score += 0.3
        if header.meeting_number:
            confidence_score += 0.3
        if header.meeting_date:
            confidence_score += 0.3
        if header.committee_name:
            confidence_score += 0.1

        header.confidence = confidence_score

        return header

    def extract_attendees(self, text: str) -> List[AttendeeInfo]:
        """Extract present attendees from Yehud protocol."""
        return self._extract_people(text, "present")

    def extract_absent(self, text: str) -> List[AttendeeInfo]:
        """Extract absent members from Yehud protocol."""
        return self._extract_people(text, "absent")

    def extract_staff(self, text: str) -> List[AttendeeInfo]:
        """Extract staff from Yehud protocol."""
        return self._extract_people(text, "staff")

    def _extract_people(
        self,
        text: str,
        attendance_type: str
    ) -> List[AttendeeInfo]:
        """
        Extract people (attendees, absent, or staff) from text.

        Args:
            text: Section text
            attendance_type: 'present', 'absent', or 'staff'

        Returns:
            List of AttendeeInfo
        """
        if not text:
            return []

        attendees = []

        # Split into lines and process each
        lines = text.strip().split('\n')

        for line in lines:
            line = line.strip()
            if not line or len(line) < 3:
                continue

            # Skip header lines
            if any(skip in line for skip in ['נוכחים', 'חסרים', 'נעדרים', 'סגל', ':']):
                continue

            # Try to extract name and role
            attendee = self._parse_attendee_line(line)
            if attendee:
                attendee.attendance_type = attendance_type
                attendees.append(attendee)

        return attendees

    def _parse_attendee_line(self, line: str) -> Optional[AttendeeInfo]:
        """
        Parse a single line to extract attendee information.

        Handles formats like:
        - "שם פרטי משפחה - תפקיד"
        - "שם פרטי משפחה, תפקיד"
        - "תפקיד: שם פרטי משפחה"
        """
        if not line or len(line) < 3:
            return None

        # Check if text is reversed
        is_reversed = self._is_reversed_text(line)
        if is_reversed:
            line = reverse_hebrew_text(line)

        attendee = AttendeeInfo(
            name="",
            role="",
            is_reversed=is_reversed,
            raw_text=line
        )

        # Pattern: "Role: Name" or "Role - Name"
        role_first_pattern = r'^([^:\-]+)[:\-]\s*(.+)$'
        match = re.match(role_first_pattern, line)

        if match:
            part1, part2 = match.groups()
            part1 = part1.strip()
            part2 = part2.strip()

            # Check which part is the role
            if self._is_role(part1):
                attendee.role = part1
                attendee.name = part2
            elif self._is_role(part2):
                attendee.name = part1
                attendee.role = part2
            else:
                # Assume "Name - Role" format
                attendee.name = part1
                attendee.role = part2
        else:
            # No separator, try to find role in text
            for role in self.ROLES:
                if role in line:
                    attendee.role = role
                    attendee.name = line.replace(role, '').strip(' -,')
                    break

            if not attendee.name:
                # Just use the whole line as name
                attendee.name = line

        # Clean up name
        attendee.name = self._clean_name(attendee.name)

        if not attendee.name or len(attendee.name) < 2:
            return None

        attendee.confidence = 0.7 if attendee.role else 0.5

        return attendee

    def _is_reversed_text(self, text: str) -> bool:
        """Check if text appears to be reversed Hebrew."""
        if not text:
            return False

        # Final letters at start indicate reversed text
        final_letters = ['ם', 'ן', 'ף', 'ץ', 'ך']
        words = text.split()

        for word in words:
            if len(word) > 1 and word[0] in final_letters:
                return True

        # Check for known reversed patterns
        reversed_patterns = ['ןהכ', 'יול', 'ןומימ', 'ריאמ', 'ןד']
        return any(p in text for p in reversed_patterns)

    def _is_role(self, text: str) -> bool:
        """Check if text is a known role."""
        text_lower = text.strip()
        for role in self.ROLES:
            if role in text_lower or text_lower in role:
                return True
        return False

    def _clean_name(self, name: str) -> str:
        """Clean up extracted name."""
        if not name:
            return ""

        # Remove common prefixes/suffixes
        name = re.sub(r'^(מר|גב[\'׳]?|ד"ר|עו"ד|רו"ח)\s*', '', name)
        name = re.sub(r'\s*[-,]\s*$', '', name)

        # Remove extra whitespace
        name = ' '.join(name.split())

        return name.strip()

    def extract_discussions(self, text: str) -> List[DiscussionInfo]:
        """Extract all discussion items from Yehud protocol."""
        if not text:
            return []

        discussions = []

        # Find all discussion item markers
        item_pattern = r'סעיף\s*(מס[\'׳]?|מספר)?\s*[:\-]?\s*(\d+|[א-ת])'

        # Split text into items
        parts = re.split(item_pattern, text)

        # Process each part
        i = 0
        while i < len(parts):
            # Find the item number
            if i + 2 < len(parts) and parts[i + 2]:
                item_number = parts[i + 2].strip()
                item_text = parts[i + 3] if i + 3 < len(parts) else ""

                discussion = self._parse_discussion(item_number, item_text)
                if discussion:
                    discussions.append(discussion)

                i += 3
            else:
                i += 1

        # If no structured items found, try alternative parsing
        if not discussions:
            discussions = self._parse_discussions_alternative(text)

        return discussions

    def _parse_discussion(
        self,
        item_number: str,
        text: str
    ) -> Optional[DiscussionInfo]:
        """Parse a single discussion item."""
        if not text:
            return None

        discussion = DiscussionInfo(
            item_number=item_number,
            raw_text=text
        )

        # Extract title (usually first line or before "דברי הסבר")
        lines = text.strip().split('\n')
        if lines:
            discussion.title = lines[0].strip()[:200]  # Limit title length

        # Extract description/expert opinion
        opinion_pattern = r'דברי\s*הסבר[:\s]*(.+?)(?=הצבעה|החלטה|פה\s*אחד|\Z)'
        match = re.search(opinion_pattern, text, re.DOTALL)
        if match:
            discussion.expert_opinion = match.group(1).strip()[:1000]

        # Extract vote
        discussion.vote = self.extract_vote(text)

        # Extract decision
        discussion.decision = self.extract_decision(text)

        # Extract budget if mentioned
        discussion.budget = self._extract_budget(text)

        # Extract dialogue
        discussion.dialogue = self._extract_dialogue(text)

        # Calculate confidence
        confidence = 0.5
        if discussion.title:
            confidence += 0.2
        if discussion.vote:
            confidence += 0.15
        if discussion.decision:
            confidence += 0.15

        discussion.confidence = confidence

        return discussion

    def _parse_discussions_alternative(self, text: str) -> List[DiscussionInfo]:
        """Alternative parsing when standard markers aren't found."""
        discussions = []

        # Try to find numbered sections
        number_pattern = r'(\d+)\s*[\.:\-]\s*(.+?)(?=\d+\s*[\.:\-]|\Z)'
        matches = re.findall(number_pattern, text, re.DOTALL)

        for num, content in matches:
            discussion = DiscussionInfo(
                item_number=num,
                raw_text=content[:500]
            )

            lines = content.strip().split('\n')
            if lines:
                discussion.title = lines[0].strip()[:200]

            discussion.vote = self.extract_vote(content)
            discussion.decision = self.extract_decision(content)
            discussion.confidence = 0.4

            discussions.append(discussion)

        return discussions

    def _extract_budget(self, text: str) -> Optional[BudgetInfo]:
        """Extract budget information from discussion text."""
        if not text:
            return None

        # Look for amounts in ILS
        amount_pattern = r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*(?:ש"ח|שקל|₪)'
        matches = re.findall(amount_pattern, text)

        if not matches:
            return None

        budget = BudgetInfo(raw_text=text[:500])

        # Find the largest amount (usually the total)
        amounts = []
        for match in matches:
            amount_str = match.replace(',', '')
            try:
                amounts.append(float(amount_str))
            except ValueError:
                pass

        if amounts:
            budget.total_amount = max(amounts)
            budget.confidence = 0.6

        return budget

    def _extract_dialogue(self, text: str) -> List[DialogueEntry]:
        """Extract dialogue from discussion text."""
        if not text:
            return []

        dialogue = []

        # Pattern for speaker: "Speaker Name: content"
        speaker_pattern = r'([^:\n]{3,30}):\s*([^\n]+)'
        matches = re.findall(speaker_pattern, text)

        for speaker, content in matches:
            speaker = speaker.strip()
            content = content.strip()

            # Skip if speaker looks like a label
            if any(skip in speaker for skip in ['נושא', 'סעיף', 'החלטה', 'הצבעה']):
                continue

            entry = DialogueEntry(
                speaker=speaker,
                content=content,
                is_question='?' in content
            )

            # Try to identify speaker role
            for role in self.ROLES:
                if role in speaker:
                    entry.speaker_role = role
                    entry.speaker = speaker.replace(role, '').strip(' -,')
                    break

            dialogue.append(entry)

        return dialogue

    def extract_vote(self, text: str) -> Optional[VoteInfo]:
        """Extract vote information specific to Yehud format."""
        if not text:
            return None

        vote = VoteInfo(raw_text=text[:300] if len(text) > 300 else text)

        # Check for unanimous first
        unanimous_patterns = [
            r'אושר\s+פה\s*אחד',
            r'פה\s*אחד',
            r'ללא\s+מתנגדים',
            r'אושר\s+ללא\s+הצבעה',
        ]

        for pattern in unanimous_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                vote.vote_type = VoteType.UNANIMOUS
                vote.confidence = 0.9
                return vote

        # Look for specific vote counts
        count_patterns = [
            r'בעד[:\s]*(\d+)',
            r'נגד[:\s]*(\d+)',
            r'נמנע(?:ים)?[:\s]*(\d+)',
        ]

        found_counts = False
        for i, pattern in enumerate(count_patterns):
            match = re.search(pattern, text)
            if match:
                count = int(match.group(1))
                found_counts = True
                if i == 0:
                    vote.yes_count = count
                elif i == 1:
                    vote.no_count = count
                else:
                    vote.abstain_count = count

        if found_counts:
            vote.vote_type = VoteType.COUNTED
            vote.total_voters = vote.yes_count + vote.no_count + vote.abstain_count
            vote.confidence = 0.85
            return vote

        # Use base class implementation as fallback
        return super().extract_vote(text)

    def extract_decision(self, text: str) -> Optional[DecisionInfo]:
        """Extract decision information specific to Yehud format."""
        if not text:
            return None

        decision = DecisionInfo(raw_text=text[:500] if len(text) > 500 else text)

        # Yehud-specific decision patterns
        yehud_patterns = [
            (r'מועצת\s+העיר\s+מחליטה\s+לאשר', DecisionStatus.APPROVED),
            (r'המועצה\s+מאשרת', DecisionStatus.APPROVED),
            (r'הועדה\s+מאשרת', DecisionStatus.APPROVED),
            (r'הוחלט\s+לאשר', DecisionStatus.APPROVED),
            (r'אושר', DecisionStatus.APPROVED),
            (r'לא\s+אושר', DecisionStatus.REJECTED),
            (r'נדחה', DecisionStatus.REJECTED),
            (r'ירד\s+מסדר\s+היום', DecisionStatus.REMOVED),
            (r'לידיעה', DecisionStatus.INFO),
        ]

        for pattern, status in yehud_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                decision.status = status
                decision.confidence = 0.8

                # Try to extract decision text
                decision_text_patterns = [
                    r'החלטה[:\s]+(.+?)(?=\n\n|סעיף|\Z)',
                    r'הוחלט[:\s]+(.+?)(?=\n\n|סעיף|\Z)',
                    r'מחליטה[:\s]+(.+?)(?=\n\n|סעיף|\Z)',
                ]

                for dt_pattern in decision_text_patterns:
                    match = re.search(dt_pattern, text, re.DOTALL)
                    if match:
                        decision.text = match.group(1).strip()[:500]
                        decision.confidence = 0.85
                        break

                return decision

        # Use base class implementation as fallback
        return super().extract_decision(text)
