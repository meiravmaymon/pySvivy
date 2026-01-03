# -*- coding: utf-8 -*-
"""
Base Protocol Format Definition.
מחלקת בסיס להגדרת פורמט פרוטוקול

This module defines the base class and data structures for protocol formats.
Each municipality can extend this to define their specific patterns.
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum


class DecisionStatus(Enum):
    """Decision status options."""
    APPROVED = "אושר"
    REJECTED = "לא אושר"
    REMOVED = "ירד מסדר היום"
    INFO = "לידיעה"
    DEFERRED = "נדחה"
    UNKNOWN = "לא ידוע"


class VoteType(Enum):
    """Types of votes."""
    COUNTED = "counted"      # With specific counts
    UNANIMOUS = "unanimous"  # פה אחד
    MAJORITY = "majority"    # רוב
    SHOW_HANDS = "show_hands"  # הרמת יד
    ROLL_CALL = "roll_call"  # הצבעה שמית


@dataclass
class HeaderInfo:
    """Extracted header information."""
    municipality: str = ""
    committee_name: str = ""
    meeting_number: Optional[int] = None
    meeting_date: Optional[str] = None
    meeting_type: str = ""  # רגילה, שלא מן המניין, etc.
    location: str = ""
    raw_text: str = ""
    confidence: float = 0.0


@dataclass
class AttendeeInfo:
    """Information about an attendee."""
    name: str
    role: str = ""
    faction: str = ""
    attendance_type: str = "present"  # present, absent, late, left_early
    is_reversed: bool = False
    raw_text: str = ""
    confidence: float = 0.0


@dataclass
class VoteInfo:
    """Vote information for a discussion item."""
    vote_type: VoteType = VoteType.COUNTED
    yes_count: int = 0
    no_count: int = 0
    abstain_count: int = 0
    total_voters: int = 0
    named_votes: List[Dict[str, str]] = field(default_factory=list)  # [{'name': 'x', 'vote': 'נגד'}]
    raw_text: str = ""
    confidence: float = 0.0


@dataclass
class DecisionInfo:
    """Decision information for a discussion item."""
    status: DecisionStatus = DecisionStatus.UNKNOWN
    text: str = ""
    conditions: List[str] = field(default_factory=list)
    raw_text: str = ""
    confidence: float = 0.0


@dataclass
class DialogueEntry:
    """A single dialogue entry in a discussion."""
    speaker: str
    content: str
    speaker_role: str = ""
    is_question: bool = False
    is_reversed: bool = False


@dataclass
class BudgetInfo:
    """Budget information for a discussion item."""
    total_amount: float = 0.0
    currency: str = "ILS"
    sources: List[Dict[str, Any]] = field(default_factory=list)  # [{'name': x, 'amount': y}]
    raw_text: str = ""
    confidence: float = 0.0


@dataclass
class DiscussionInfo:
    """Extracted discussion/agenda item information."""
    item_number: str = ""
    title: str = ""
    description: str = ""
    expert_opinion: str = ""
    dialogue: List[DialogueEntry] = field(default_factory=list)
    vote: Optional[VoteInfo] = None
    decision: Optional[DecisionInfo] = None
    budget: Optional[BudgetInfo] = None
    categories: List[str] = field(default_factory=list)
    raw_text: str = ""
    confidence: float = 0.0


class ProtocolFormat(ABC):
    """
    Abstract base class for protocol format definitions.

    Each municipality may have different protocol formats with
    varying patterns for headers, attendees, discussions, etc.

    Subclasses should implement the extraction methods for their
    specific format.
    """

    # Municipality identifier
    municipality_code: str = ""
    municipality_name: str = ""
    municipality_name_he: str = ""

    # Common patterns that can be overridden
    _header_patterns: List[str] = []
    _attendees_patterns: List[str] = []
    _absent_patterns: List[str] = []
    _staff_patterns: List[str] = []
    _discussion_patterns: List[str] = []
    _vote_patterns: List[str] = []
    _decision_patterns: List[str] = []

    # Decision keywords mapping
    _decision_keywords: Dict[DecisionStatus, List[str]] = {
        DecisionStatus.APPROVED: ['אושר', 'אושרה', 'מאושר', 'התקבל', 'התקבלה'],
        DecisionStatus.REJECTED: ['נדחה', 'נדחתה', 'לא אושר', 'לא אושרה', 'לא התקבל'],
        DecisionStatus.REMOVED: ['ירד מסדר היום', 'הורד', 'נמחק', 'הוסר'],
        DecisionStatus.INFO: ['לידיעה', 'להידיעה', 'לידיעת'],
        DecisionStatus.DEFERRED: ['נדחה לישיבה', 'יידון', 'הועבר לדיון'],
    }

    # Vote keywords
    _vote_keywords: Dict[str, List[str]] = {
        'yes': ['בעד', 'תומך', 'מאשר'],
        'no': ['נגד', 'מתנגד'],
        'abstain': ['נמנע', 'נמנעת'],
        'unanimous': ['פה אחד', 'פה-אחד', 'ללא מתנגדים'],
    }

    def __init__(self):
        """Initialize the format with compiled patterns."""
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for efficiency."""
        self._compiled_patterns = {}

    def get_municipality_patterns(self) -> List[str]:
        """Get patterns to identify this municipality in text."""
        return [self.municipality_name_he, self.municipality_name]

    @abstractmethod
    def extract_header(self, text: str) -> HeaderInfo:
        """
        Extract header information from protocol text.

        Args:
            text: The section of text containing the header

        Returns:
            HeaderInfo with extracted data
        """
        pass

    @abstractmethod
    def extract_attendees(self, text: str) -> List[AttendeeInfo]:
        """
        Extract present attendees from text.

        Args:
            text: The attendees section text

        Returns:
            List of AttendeeInfo for present members
        """
        pass

    @abstractmethod
    def extract_absent(self, text: str) -> List[AttendeeInfo]:
        """
        Extract absent members from text.

        Args:
            text: The absent section text

        Returns:
            List of AttendeeInfo for absent members
        """
        pass

    @abstractmethod
    def extract_staff(self, text: str) -> List[AttendeeInfo]:
        """
        Extract staff members from text.

        Args:
            text: The staff section text

        Returns:
            List of AttendeeInfo for staff
        """
        pass

    @abstractmethod
    def extract_discussions(self, text: str) -> List[DiscussionInfo]:
        """
        Extract all discussion items from text.

        Args:
            text: The discussions section text

        Returns:
            List of DiscussionInfo for each agenda item
        """
        pass

    def extract_vote(self, text: str) -> Optional[VoteInfo]:
        """
        Extract vote information from discussion text.

        Default implementation using common patterns.

        Args:
            text: Text containing vote information

        Returns:
            VoteInfo if vote found, None otherwise
        """
        if not text:
            return None

        vote = VoteInfo()

        # Check for unanimous vote first
        for keyword in self._vote_keywords.get('unanimous', []):
            if keyword in text:
                vote.vote_type = VoteType.UNANIMOUS
                vote.confidence = 0.9
                vote.raw_text = text
                return vote

        # Look for vote counts: "X בעד, Y נגד, Z נמנעים"
        count_pattern = r'(\d+)\s*(בעד|נגד|נמנע)'
        matches = re.findall(count_pattern, text)

        if matches:
            vote.vote_type = VoteType.COUNTED
            for count, vote_type in matches:
                count = int(count)
                if vote_type in self._vote_keywords.get('yes', []) or vote_type == 'בעד':
                    vote.yes_count = count
                elif vote_type in self._vote_keywords.get('no', []) or vote_type == 'נגד':
                    vote.no_count = count
                elif vote_type in self._vote_keywords.get('abstain', []) or vote_type == 'נמנע':
                    vote.abstain_count = count

            vote.total_voters = vote.yes_count + vote.no_count + vote.abstain_count
            vote.confidence = 0.8
            vote.raw_text = text
            return vote

        return None

    def extract_decision(self, text: str) -> Optional[DecisionInfo]:
        """
        Extract decision information from discussion text.

        Default implementation using common patterns.

        Args:
            text: Text containing decision information

        Returns:
            DecisionInfo if decision found, None otherwise
        """
        if not text:
            return None

        decision = DecisionInfo(raw_text=text)

        # Find decision status
        for status, keywords in self._decision_keywords.items():
            for keyword in keywords:
                if keyword in text:
                    decision.status = status
                    decision.confidence = 0.7

                    # Try to extract decision text
                    # Common pattern: "החלטה: ..." or "הוחלט: ..."
                    decision_patterns = [
                        r'החלטה[:\s]+(.+?)(?=\n\n|\Z)',
                        r'הוחלט[:\s]+(.+?)(?=\n\n|\Z)',
                        r'המועצה\s+מחליטה[:\s]+(.+?)(?=\n\n|\Z)',
                    ]

                    for pattern in decision_patterns:
                        match = re.search(pattern, text, re.DOTALL)
                        if match:
                            decision.text = match.group(1).strip()
                            decision.confidence = 0.8
                            break

                    return decision

        return None

    def normalize_text(self, text: str) -> str:
        """
        Normalize text for processing.

        Override this to add format-specific normalization.

        Args:
            text: Raw text

        Returns:
            Normalized text
        """
        if not text:
            return ""

        # Remove multiple spaces
        text = re.sub(r' +', ' ', text)

        # Normalize newlines
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text.strip()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self.municipality_name_he}>"
