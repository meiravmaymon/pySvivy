# -*- coding: utf-8 -*-
"""
Discussion/Agenda Item Extractor.
חילוץ סעיפי דיון מפרוטוקולים עירוניים

This module provides enhanced extraction of discussion items from
municipal protocol documents, including:
- Item number and title
- Description and expert opinion
- Dialogue between participants
- Vote information
- Decision status and text
- Budget information

Uses LLM routing for improved accuracy on problematic sections.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

logger = logging.getLogger(__name__)


class VoteType(Enum):
    """Types of votes."""
    COUNTED = "counted"
    UNANIMOUS = "unanimous"
    MAJORITY = "majority"
    UNKNOWN = "unknown"


class DecisionStatus(Enum):
    """Decision status options."""
    APPROVED = "אושר"
    REJECTED = "לא אושר"
    REMOVED = "ירד מסדר היום"
    INFO = "לידיעה"
    DEFERRED = "נדחה"
    UNKNOWN = "לא ידוע"


@dataclass
class VoteResult:
    """Extracted vote information."""
    vote_type: VoteType = VoteType.UNKNOWN
    yes_count: int = 0
    no_count: int = 0
    abstain_count: int = 0
    total_voters: int = 0
    named_votes: List[Dict[str, str]] = field(default_factory=list)
    raw_text: str = ""
    confidence: float = 0.0
    extraction_method: str = "regex"


@dataclass
class DecisionResult:
    """Extracted decision information."""
    status: DecisionStatus = DecisionStatus.UNKNOWN
    text: str = ""
    conditions: List[str] = field(default_factory=list)
    raw_text: str = ""
    confidence: float = 0.0
    extraction_method: str = "regex"


@dataclass
class DialogueEntry:
    """A single dialogue entry."""
    speaker: str
    content: str
    speaker_role: str = ""
    is_question: bool = False


@dataclass
class BudgetInfo:
    """Budget information."""
    total_amount: float = 0.0
    sources: List[Dict[str, Any]] = field(default_factory=list)
    raw_text: str = ""
    confidence: float = 0.0


@dataclass
class DiscussionItem:
    """Fully extracted discussion item."""
    item_number: str
    title: str = ""
    description: str = ""
    expert_opinion: str = ""
    dialogue: List[DialogueEntry] = field(default_factory=list)
    vote: Optional[VoteResult] = None
    decision: Optional[DecisionResult] = None
    budget: Optional[BudgetInfo] = None
    categories: List[str] = field(default_factory=list)
    raw_text: str = ""
    start_pos: int = 0
    end_pos: int = 0
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for compatibility."""
        result = {
            'issue_no': self.item_number,
            'title': self.title,
            'description': self.description,
            'expert_opinion': self.expert_opinion,
            'raw_text': self.raw_text,
            'confidence': self.confidence,
        }

        if self.vote:
            result['vote'] = {
                'type': self.vote.vote_type.value,
                'yes': self.vote.yes_count,
                'no': self.vote.no_count,
                'abstain': self.vote.abstain_count,
                'total': self.vote.total_voters,
                'method': self.vote.extraction_method,
            }

        if self.decision:
            result['decision'] = {
                'status': self.decision.status.value,
                'text': self.decision.text,
                'method': self.decision.extraction_method,
            }

        if self.budget:
            result['budget'] = {
                'total': self.budget.total_amount,
                'sources': self.budget.sources,
            }

        if self.dialogue:
            result['dialogue'] = [
                {'speaker': d.speaker, 'content': d.content, 'role': d.speaker_role}
                for d in self.dialogue
            ]

        return result


class DiscussionExtractor:
    """
    Extract discussion items from protocol text.

    Uses a multi-stage approach:
    1. Find item boundaries
    2. Extract structured data using regex
    3. Fall back to LLM for low-confidence extractions
    """

    # Item number patterns
    ITEM_PATTERNS = [
        r'סעיף\s*(מס[\'׳]?|מספר)?\s*[:\-]?\s*(\d+)',
        r'נושא\s*(מס[\'׳]?|מספר)?\s*[:\-]?\s*(\d+)',
        r'^(\d+)\s*[\.:\-]\s+',
    ]

    # Vote patterns
    VOTE_PATTERNS = {
        'unanimous': [
            r'פה\s*אחד',
            r'ללא\s+מתנגדים',
            r'אושר\s+פה\s*אחד',
            r'ללא\s+הצבעה',
        ],
        'counted': [
            r'(\d+)\s*בעד',
            r'(\d+)\s*נגד',
            r'(\d+)\s*נמנע(?:ים)?',
        ],
    }

    # Decision patterns
    DECISION_PATTERNS = {
        DecisionStatus.APPROVED: [
            r'אושר',
            r'התקבל',
            r'מאושר',
            r'מועצת\s+העיר\s+מאשרת',
            r'הוחלט\s+לאשר',
        ],
        DecisionStatus.REJECTED: [
            r'נדחה',
            r'לא\s+אושר',
            r'לא\s+התקבל',
        ],
        DecisionStatus.REMOVED: [
            r'ירד\s+מסדר\s+היום',
            r'הוסר',
            r'הורד',
        ],
        DecisionStatus.INFO: [
            r'לידיעה',
            r'להידיעה',
        ],
        DecisionStatus.DEFERRED: [
            r'נדחה\s+לישיבה',
            r'הועבר\s+לדיון',
        ],
    }

    def __init__(self, use_llm: bool = True):
        """
        Initialize the extractor.

        Args:
            use_llm: Whether to use LLM for fallback extraction
        """
        self.use_llm = use_llm
        self._llm_router = None

    def _get_llm_router(self):
        """Get LLM router (lazy initialization)."""
        if self._llm_router is None and self.use_llm:
            try:
                from ocr.llm_router import get_router
                self._llm_router = get_router()
            except ImportError:
                pass
        return self._llm_router

    def find_item_boundaries(self, text: str) -> List[Tuple[int, int, str]]:
        """
        Find all discussion item boundaries in text.

        Returns:
            List of (start_pos, end_pos, item_number)
        """
        if not text:
            return []

        # Find all item markers
        markers = []
        for pattern in self.ITEM_PATTERNS:
            for match in re.finditer(pattern, text, re.MULTILINE):
                # Extract item number from match
                groups = match.groups()
                item_num = next((g for g in groups if g and g.isdigit()), "")
                if item_num:
                    markers.append((match.start(), item_num))

        # Sort by position
        markers.sort(key=lambda x: x[0])

        # Remove duplicates that are too close
        filtered = []
        for pos, num in markers:
            if not filtered or pos - filtered[-1][0] > 50:
                filtered.append((pos, num))

        # Calculate boundaries
        boundaries = []
        text_len = len(text)

        for i, (start, num) in enumerate(filtered):
            if i + 1 < len(filtered):
                end = filtered[i + 1][0]
            else:
                end = min(start + 5000, text_len)  # Limit item length

            boundaries.append((start, end, num))

        return boundaries

    def extract_vote(self, text: str) -> VoteResult:
        """
        Extract vote information from text.

        Args:
            text: Text containing vote information

        Returns:
            VoteResult with extracted data
        """
        result = VoteResult(raw_text=text[:300] if len(text) > 300 else text)

        if not text:
            return result

        # Check for unanimous first
        for pattern in self.VOTE_PATTERNS['unanimous']:
            if re.search(pattern, text, re.IGNORECASE):
                result.vote_type = VoteType.UNANIMOUS
                result.confidence = 0.9
                result.extraction_method = "regex"
                return result

        # Look for counted votes
        found_votes = False
        for pattern in self.VOTE_PATTERNS['counted']:
            match = re.search(pattern, text)
            if match:
                count = int(match.group(1))
                found_votes = True

                if 'בעד' in pattern:
                    result.yes_count = count
                elif 'נגד' in pattern:
                    result.no_count = count
                elif 'נמנע' in pattern:
                    result.abstain_count = count

        if found_votes:
            result.vote_type = VoteType.COUNTED
            result.total_voters = result.yes_count + result.no_count + result.abstain_count
            result.confidence = 0.8
            result.extraction_method = "regex"
            return result

        # If regex didn't find anything, try LLM
        router = self._get_llm_router()
        if router and self.use_llm:
            try:
                from ocr.llm_router import ExtractionType
                llm_result = router.extract(text, ExtractionType.VOTE)

                if llm_result.success and llm_result.data:
                    data = llm_result.data
                    if data.get('type') == 'unanimous':
                        result.vote_type = VoteType.UNANIMOUS
                    else:
                        result.vote_type = VoteType.COUNTED
                        result.yes_count = data.get('yes', 0)
                        result.no_count = data.get('no', 0)
                        result.abstain_count = data.get('abstain', 0)
                        result.total_voters = result.yes_count + result.no_count + result.abstain_count

                    result.confidence = llm_result.confidence
                    result.extraction_method = llm_result.method.value

            except Exception as e:
                logger.debug(f"LLM vote extraction error: {e}")

        return result

    def extract_decision(self, text: str) -> DecisionResult:
        """
        Extract decision information from text.

        Args:
            text: Text containing decision information

        Returns:
            DecisionResult with extracted data
        """
        result = DecisionResult(raw_text=text[:500] if len(text) > 500 else text)

        if not text:
            return result

        # Check each decision status
        for status, patterns in self.DECISION_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    result.status = status
                    result.confidence = 0.7
                    result.extraction_method = "regex"

                    # Try to extract decision text
                    decision_text_patterns = [
                        r'החלטה[:\s]+(.+?)(?=\n\n|סעיף|\Z)',
                        r'הוחלט[:\s]+(.+?)(?=\n\n|סעיף|\Z)',
                        r'מחליטה[:\s]+(.+?)(?=\n\n|סעיף|\Z)',
                    ]

                    for dt_pattern in decision_text_patterns:
                        match = re.search(dt_pattern, text, re.DOTALL)
                        if match:
                            result.text = match.group(1).strip()[:500]
                            result.confidence = 0.8
                            break

                    return result

        # If regex didn't find anything, try LLM
        router = self._get_llm_router()
        if router and self.use_llm:
            try:
                from ocr.llm_router import ExtractionType
                llm_result = router.extract(text, ExtractionType.DECISION)

                if llm_result.success and llm_result.data:
                    data = llm_result.data
                    status_map = {
                        'אושר': DecisionStatus.APPROVED,
                        'נדחה': DecisionStatus.REJECTED,
                        'לידיעה': DecisionStatus.INFO,
                    }
                    result.status = status_map.get(
                        data.get('status', ''),
                        DecisionStatus.UNKNOWN
                    )
                    result.text = data.get('text', '')
                    result.confidence = llm_result.confidence
                    result.extraction_method = llm_result.method.value

            except Exception as e:
                logger.debug(f"LLM decision extraction error: {e}")

        return result

    def extract_dialogue(self, text: str) -> List[DialogueEntry]:
        """
        Extract dialogue from discussion text.

        Args:
            text: Discussion text

        Returns:
            List of DialogueEntry
        """
        if not text:
            return []

        dialogue = []

        # Pattern: "Speaker Name: content"
        speaker_pattern = r'([^:\n]{3,40}):\s*([^\n]+)'
        matches = re.findall(speaker_pattern, text)

        skip_words = ['נושא', 'סעיף', 'החלטה', 'הצבעה', 'תאריך', 'מספר']

        for speaker, content in matches:
            speaker = speaker.strip()
            content = content.strip()

            # Skip if speaker looks like a label
            if any(skip in speaker for skip in skip_words):
                continue

            if len(speaker) < 2 or len(content) < 3:
                continue

            entry = DialogueEntry(
                speaker=speaker,
                content=content,
                is_question='?' in content
            )

            dialogue.append(entry)

        return dialogue

    def extract_budget(self, text: str) -> Optional[BudgetInfo]:
        """
        Extract budget information from text.

        Args:
            text: Text containing budget information

        Returns:
            BudgetInfo if budget found, None otherwise
        """
        if not text:
            return None

        # Look for amounts
        amount_pattern = r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*(?:ש"ח|שקל|₪)'
        matches = re.findall(amount_pattern, text)

        if not matches:
            return None

        budget = BudgetInfo(raw_text=text[:500])

        # Parse amounts
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

    def extract_item(self, text: str, item_number: str) -> DiscussionItem:
        """
        Extract all information for a single discussion item.

        Args:
            text: The item text
            item_number: The item number

        Returns:
            DiscussionItem with all extracted data
        """
        item = DiscussionItem(
            item_number=item_number,
            raw_text=text
        )

        if not text:
            return item

        # Extract title (first line or first sentence)
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if lines:
            # Skip the item number line if it's just the marker
            first_line = lines[0]
            if re.match(r'^סעיף\s*\d+\s*$', first_line) and len(lines) > 1:
                first_line = lines[1]
            item.title = first_line[:200]

        # Extract expert opinion
        opinion_pattern = r'דברי\s*הסבר[:\s]*(.+?)(?=הצבעה|החלטה|פה\s*אחד|\Z)'
        match = re.search(opinion_pattern, text, re.DOTALL)
        if match:
            item.expert_opinion = match.group(1).strip()[:1000]

        # Extract vote
        vote = self.extract_vote(text)
        if vote.vote_type != VoteType.UNKNOWN or vote.confidence > 0:
            item.vote = vote

        # Extract decision
        decision = self.extract_decision(text)
        if decision.status != DecisionStatus.UNKNOWN or decision.confidence > 0:
            item.decision = decision

        # Extract budget
        budget = self.extract_budget(text)
        if budget:
            item.budget = budget

        # Extract dialogue
        item.dialogue = self.extract_dialogue(text)

        # Calculate overall confidence
        confidence_scores = [0.5]  # Base
        if item.title:
            confidence_scores.append(0.7)
        if item.vote and item.vote.confidence > 0:
            confidence_scores.append(item.vote.confidence)
        if item.decision and item.decision.confidence > 0:
            confidence_scores.append(item.decision.confidence)

        item.confidence = sum(confidence_scores) / len(confidence_scores)

        return item

    def extract_all(self, text: str) -> List[DiscussionItem]:
        """
        Extract all discussion items from text.

        Args:
            text: Full discussions section text

        Returns:
            List of DiscussionItem
        """
        if not text:
            return []

        # Find item boundaries
        boundaries = self.find_item_boundaries(text)

        # Extract each item
        items = []
        for start, end, item_num in boundaries:
            item_text = text[start:end]
            item = self.extract_item(item_text, item_num)
            item.start_pos = start
            item.end_pos = end
            items.append(item)

        return items


# Convenience functions
def extract_discussions(text: str, use_llm: bool = True) -> List[DiscussionItem]:
    """Extract all discussions from text."""
    extractor = DiscussionExtractor(use_llm=use_llm)
    return extractor.extract_all(text)


def extract_vote(text: str, use_llm: bool = True) -> VoteResult:
    """Extract vote from text."""
    extractor = DiscussionExtractor(use_llm=use_llm)
    return extractor.extract_vote(text)


def extract_decision(text: str, use_llm: bool = True) -> DecisionResult:
    """Extract decision from text."""
    extractor = DiscussionExtractor(use_llm=use_llm)
    return extractor.extract_decision(text)


__all__ = [
    'VoteType',
    'DecisionStatus',
    'VoteResult',
    'DecisionResult',
    'DialogueEntry',
    'BudgetInfo',
    'DiscussionItem',
    'DiscussionExtractor',
    'extract_discussions',
    'extract_vote',
    'extract_decision',
]
