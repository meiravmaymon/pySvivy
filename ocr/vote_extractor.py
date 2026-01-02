# -*- coding: utf-8 -*-
"""
Vote extraction utilities for Hebrew OCR processing.
פונקציות לחילוץ הצבעות מטקסט עברי

Functions:
- extract_vote_counts: Extract yes/no/abstain counts
- extract_vote_type: Determine vote type (unanimous, majority, etc.)
"""
import re


def extract_vote_counts(text):
    """
    Extract vote counts (yes, no, abstain) from text.

    Args:
        text: Text to search for vote counts

    Returns:
        dict with 'yes', 'no', 'abstain' counts
    """
    if not text:
        return {'yes': 0, 'no': 0, 'abstain': 0}

    votes = {'yes': 0, 'no': 0, 'abstain': 0}

    # Yes vote patterns (בעד)
    yes_patterns = [
        r'בעד[\s:-]+(\d+)',
        r'(\d+)\s+בעד',
        r'3va[\s\u200f]*-\s*(\d+)',  # OCR misread of בעד
    ]

    for pattern in yes_patterns:
        match = re.search(pattern, text)
        if match:
            votes['yes'] = int(match.group(1))
            break

    # No vote patterns (נגד)
    no_patterns = [
        r'נגד[\s:-]+(\d+)',
        r'(\d+)\s+נגד',
    ]

    for pattern in no_patterns:
        match = re.search(pattern, text)
        if match:
            votes['no'] = int(match.group(1))
            break

    # Abstain vote patterns (נמנע/נמנעים)
    abstain_patterns = [
        r'(?:נמנע|נמנעים)[\s:-]+(\d+)',
        r'(\d+)\s+(?:נמנע|נמנעים)',
        r'גמנצים[\s:-]+(\d+)',  # OCR misread of נמנעים
    ]

    for pattern in abstain_patterns:
        match = re.search(pattern, text)
        if match:
            votes['abstain'] = int(match.group(1))
            break

    return votes


def extract_vote_type(text, vote_counts=None):
    """
    Determine the type of vote (unanimous, majority, etc.).

    Args:
        text: Text to analyze
        vote_counts: Optional pre-extracted vote counts

    Returns:
        Vote type string: 'unanimous', 'majority', 'rejected', or None
    """
    if not text:
        return None

    text_lower = text.lower()

    # Check for unanimous vote (פה אחד)
    unanimous_patterns = [
        r'פה\s+אח[דר]',
        r'פא\s+אחד',
        r'דחא\s+הפ',  # reversed
    ]
    for pattern in unanimous_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return 'unanimous'

    # Check for majority vote (ברוב קולות)
    if re.search(r'ברוב\s+(?:קולות|קולה)', text, re.IGNORECASE):
        return 'majority'

    # Check for rejection
    if re.search(r'נדח[הת]|לא\s+אושר', text, re.IGNORECASE):
        return 'rejected'

    # Infer from vote counts
    if vote_counts:
        yes = vote_counts.get('yes', 0)
        no = vote_counts.get('no', 0)
        abstain = vote_counts.get('abstain', 0)

        if yes > 0 and no == 0 and abstain == 0:
            return 'unanimous'
        elif yes > no:
            return 'majority'
        elif no > yes:
            return 'rejected'

    return None


def extract_decision_status(text):
    """
    Extract the decision status from text.

    Args:
        text: Text to analyze

    Returns:
        Decision status string
    """
    if not text:
        return None

    # Check for specific statuses
    status_patterns = [
        (r'אושר\s+פה\s+אחד', 'אושר פה אחד'),
        (r'פה\s+אחד', 'אושר פה אחד'),
        (r'אושר\s+ברוב', 'אושר'),
        (r'אושר', 'אושר'),
        (r'מאושר', 'אושר'),
        (r'נדח[הת]', 'נדחה'),
        (r'לא\s+אושר', 'נדחה'),
        (r'ירד\s+(?:מ)?סדר', 'ירד מסדר היום'),
        (r'הורד\s+(?:מ)?סדר', 'ירד מסדר היום'),
        (r'הועבר\s+לדיון', 'הועבר לדיון'),
        (r'דיווח\s+ועדכון', 'דיווח ועדכון'),
        (r'לידיעה', 'לידיעה'),
    ]

    for pattern, status in status_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return status

    return None


def format_vote_result(vote_counts, vote_type=None):
    """
    Format vote counts into a readable string.

    Args:
        vote_counts: dict with 'yes', 'no', 'abstain'
        vote_type: Optional vote type

    Returns:
        Formatted string like "בעד: 12, נגד: 0, נמנעים: 1"
    """
    if not vote_counts:
        return ""

    parts = []
    if vote_counts.get('yes', 0) > 0:
        parts.append(f"בעד: {vote_counts['yes']}")
    if vote_counts.get('no', 0) > 0:
        parts.append(f"נגד: {vote_counts['no']}")
    if vote_counts.get('abstain', 0) > 0:
        parts.append(f"נמנעים: {vote_counts['abstain']}")

    if vote_type == 'unanimous':
        parts.append("(פה אחד)")

    return ', '.join(parts)
