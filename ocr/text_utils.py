# -*- coding: utf-8 -*-
"""
Text manipulation utilities for Hebrew OCR processing.
פונקציות עזר לעיבוד טקסט עברי מ-OCR

Functions:
- reverse_hebrew_text: Reverse RTL text that was read as LTR
- normalize_final_letters: Fix final letter positions
- fix_reversed_numbers: Fix numbers that appear reversed
- normalize_hebrew_text: Full normalization pipeline
- detect_reversed_text: Detect if text is reversed with confidence score
- fix_common_ocr_errors: Fix common OCR mistakes in Hebrew
"""
import re
from typing import Tuple, List, Optional


def normalize_final_letters(text):
    """
    נרמול אותיות סופיות לאחר היפוך טקסט.
    כשמהפכים טקסט עברי, האותיות הסופיות עוברות למקום הלא נכון.
    פונקציה זו מתקנת: ם→מ (באמצע), מ→ם (בסוף)

    Args:
        text: Text to normalize

    Returns:
        Text with correct final letter positions
    """
    if not text:
        return text

    # מיפוי אותיות רגילות לסופיות ולהפך
    final_to_regular = {'ם': 'מ', 'ן': 'נ', 'ף': 'פ', 'ץ': 'צ', 'ך': 'כ'}
    regular_to_final = {'מ': 'ם', 'נ': 'ן', 'פ': 'ף', 'צ': 'ץ', 'כ': 'ך'}

    words = text.split()
    result = []

    for word in words:
        if not word:
            result.append(word)
            continue

        # עבור על כל תו במילה
        new_word = list(word)
        for i, char in enumerate(word):
            is_last = (i == len(word) - 1)

            if is_last:
                # תו אחרון - צריך להיות סופית אם רלוונטי
                if char in regular_to_final:
                    new_word[i] = regular_to_final[char]
            else:
                # לא אחרון - לא יכול להיות סופית
                if char in final_to_regular:
                    new_word[i] = final_to_regular[char]

        result.append(''.join(new_word))

    return ' '.join(result)


def fix_reversed_numbers(text):
    """
    תיקון מספרים הפוכים בטקסט עברי.
    OCR של עברית לפעמים קורא מספרים משמאל לימין במקום מימין לשמאל.

    Examples:
        - "000,052" → "250,000"
        - "000,09" → "90,000"
        - "000,003" → "300,000"

    Args:
        text: Text containing potentially reversed numbers

    Returns:
        Text with corrected numbers
    """
    if not text:
        return text

    def reverse_number(match):
        num_str = match.group(0)

        # הסר פסיקים
        digits_only = num_str.replace(',', '')

        # בדוק אם מתחיל ב-0 ולא כולו אפסים
        if digits_only.startswith('0') and not all(c == '0' for c in digits_only):
            # הפוך את הספרות
            reversed_digits = digits_only[::-1]

            # הסר אפסים מובילים
            reversed_digits = reversed_digits.lstrip('0') or '0'

            # הוסף פסיקים כל 3 ספרות מימין
            result = ''
            for i, digit in enumerate(reversed(reversed_digits)):
                if i > 0 and i % 3 == 0:
                    result = ',' + result
                result = digit + result

            return result

        return num_str

    # מצא מספרים עם פסיקים (פורמט: 000,XXX או XXX,000 וכו')
    # מספר הפוך נראה כמו: 000,012 (מתחיל ב-000,)
    pattern = r'\b0{1,3},\d{1,3}(?:,\d{3})*\b'

    result = re.sub(pattern, reverse_number, text)

    return result


def fix_reversed_short_numbers(text, context='budget'):
    """
    תיקון מספרים קצרים (2-3 ספרות) הפוכים בהקשר תקציבי.

    Args:
        text: הטקסט לתיקון
        context: 'budget' לתקציב (כביש 46, ש"ח), 'vote' להצבעה

    Returns:
        טקסט מתוקן עם מספרים הפוכים שתוקנו
    """
    if not text:
        return text

    # מילון מספרים ידועים שצריכים היפוך (הקשר תקציבי/גאוגרפי)
    known_reversed_numbers = {
        '64': '46',   # כביש 46
        '56': '65',   # כביש 65
        '04': '40',   # כביש 40
        '06': '60',   # כביש 60
    }

    result = text

    if context == 'budget':
        # תיקון בהקשר של כביש
        for reversed_num, correct_num in known_reversed_numbers.items():
            patterns = [
                (rf'כביש\s+{reversed_num}\b', f'כביש {correct_num}'),
                (rf'דרך\s+{reversed_num}\b', f'דרך {correct_num}'),
                (rf"כביש\s+מס['׳]\s*{reversed_num}\b", f"כביש מס' {correct_num}"),
            ]
            for pattern, replacement in patterns:
                result = re.sub(pattern, replacement, result)

    return result


def reverse_hebrew_text(text):
    """
    Reverse Hebrew text that was stored in reversed order (RTL as LTR).
    Uses multiple heuristics to detect reversed Hebrew text.

    Args:
        text: Potentially reversed Hebrew text

    Returns:
        Correctly ordered Hebrew text
    """
    if not text:
        return ""

    text_stripped = text.strip()
    if len(text_stripped) < 2:
        return text

    # Final letters (סופיות) - מופיעות רק בסוף מילים בעברית תקינה
    final_letters = ['ם', 'ן', 'ף', 'ץ', 'ך']

    # Extract Hebrew words
    hebrew_words = re.findall(r'[א-תךםןףץ]+', text_stripped)

    if not hebrew_words:
        return text

    # === HEURISTIC 1: Final letters at word START ===
    for word in hebrew_words:
        if len(word) > 1 and word[0] in final_letters:
            return normalize_final_letters(text[::-1])

    # === HEURISTIC 2: Final letters in MIDDLE of words ===
    for word in hebrew_words:
        if len(word) > 2:
            middle = word[1:-1]
            for final in final_letters:
                if final in middle:
                    return normalize_final_letters(text[::-1])

    # === HEURISTIC 3: Common reversed name patterns ===
    reversed_patterns = [
        # שמות פרטיים הפוכים
        'ןורש', 'ןנור', 'ןועמש', 'ןרהא', 'ןתנוי', 'ןד', 'ןור', 'ןב',
        'הרש', 'ריאמ', 'יול', 'יגח', 'לאינד', 'לכימ', 'ילא', 'הלא',
        # שמות משפחה נפוצים הפוכים
        'ןהכ', 'ןומימ', 'ןמטור', 'רלימ', 'דעס', 'קינזר', 'ירשוב',
        'רקניפ', 'סילקמ', 'ןמנירג', 'ץרפ', 'ןמדירפ', 'ןמרבליז',
        # תפקידים הפוכים
        'ל"כנמ', 'לכנמ', 'רבזג', 'ש"מעוי', 'רקבמ', 'סדנהמ', 'להנמ',
        # מילים כלליות הפוכות
        'יפסכה', 'רושיא', 'הטלחה', 'תנשל', 'הייריעה', 'הצעומה',
    ]
    if any(pattern in text_stripped for pattern in reversed_patterns):
        return normalize_final_letters(text[::-1])

    # === HEURISTIC 4: Word ending patterns ===
    common_end_letters = ['ה', 'ת', 'י']
    reversed_word_count = 0
    for word in hebrew_words:
        if len(word) > 2:
            if word[0] in common_end_letters:
                reversed_word_count += 1

    multi_letter_words = [w for w in hebrew_words if len(w) > 2]
    if multi_letter_words and reversed_word_count >= len(multi_letter_words) * 0.5:
        return normalize_final_letters(text[::-1])

    # === HEURISTIC 5: Word beginning patterns ===
    common_start_letters = ['ה', 'ב', 'ו', 'ל', 'מ', 'ש', 'כ']
    wrong_ending_count = 0
    for word in hebrew_words:
        if len(word) > 2:
            if word[-1] in common_start_letters:
                wrong_ending_count += 1

    if multi_letter_words and wrong_ending_count >= len(multi_letter_words) * 0.6:
        return normalize_final_letters(text[::-1])

    return text


def clean_ocr_text(text):
    """
    Clean OCR text by removing common artifacts.

    Args:
        text: Raw OCR text

    Returns:
        Cleaned text
    """
    if not text:
        return text

    # Remove page markers
    text = re.sub(r'---\s*Page\s*\d+\s*---', '\n', text)

    # Remove excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)

    # Remove common OCR artifacts
    text = re.sub(r'[|]', '', text)

    return text.strip()


# =============================================================================
# New Enhanced Functions
# =============================================================================

# Common OCR character confusions in Hebrew
OCR_CONFUSIONS = {
    # Similar-looking Hebrew letters
    'ד': ['ר'],  # dalet ↔ resh
    'ר': ['ד'],
    'ו': ['ן'],  # vav ↔ final nun (in some fonts)
    'ת': ['ח'],  # tav ↔ chet
    'ח': ['ת'],
    'ב': ['כ'],  # bet ↔ kaf
    'כ': ['ב'],
    'ה': ['ח'],  # he ↔ chet
    'ע': ['צ'],  # ayin ↔ tsade
    'צ': ['ע'],
    'ס': ['ם'],  # samekh ↔ final mem
    'ם': ['ס'],
}

# Common Hebrew name patterns (for validation)
COMMON_FIRST_NAMES = [
    'אברהם', 'יצחק', 'יעקב', 'משה', 'דוד', 'שלמה', 'יוסף', 'בנימין',
    'שרה', 'רבקה', 'רחל', 'לאה', 'מרים', 'חנה', 'דבורה', 'אסתר',
    'יוני', 'דני', 'רוני', 'שרון', 'אילן', 'גיל', 'עמית', 'שי',
    'מאיר', 'חיים', 'אהרון', 'שמעון', 'ראובן', 'יהודה', 'נפתלי',
    'מיכל', 'נעמה', 'טלי', 'ליאת', 'אורית', 'גלית', 'עינת', 'נטלי',
]

COMMON_LAST_NAMES = [
    'כהן', 'לוי', 'מזרחי', 'פרץ', 'ביטון', 'דהן', 'אברהם', 'פרידמן',
    'שרון', 'גולן', 'בן דוד', 'אוחיון', 'חדד', 'עמר', 'אזולאי',
    'גרינברג', 'רוזנברג', 'גולדברג', 'שוורץ', 'קליין', 'וייס',
    'מימון', 'סעד', 'בושרי', 'מקליס', 'פינקר', 'רוטמן',
]


def detect_reversed_text(text: str) -> Tuple[bool, float]:
    """
    Detect if Hebrew text is reversed with a confidence score.

    Uses multiple indicators:
    - Final letters in wrong positions
    - Known reversed word patterns
    - Known normal word patterns (negative indicator)

    Args:
        text: Text to analyze

    Returns:
        Tuple of (is_reversed, confidence) where confidence is 0.0-1.0
    """
    if not text or len(text.strip()) < 2:
        return False, 0.0

    text_stripped = text.strip()

    # Extract Hebrew words
    hebrew_words = re.findall(r'[א-תךםןףץ]+', text_stripped)
    if not hebrew_words:
        return False, 0.0

    # Final letters that shouldn't appear at start or middle
    final_letters = set('םןףץך')

    # Count indicators
    reversed_indicators = 0
    normal_indicators = 0

    # Check 1: Final letters at word start (strong reversed indicator)
    final_at_start = sum(1 for word in hebrew_words
                         if len(word) > 1 and word[0] in final_letters)
    if final_at_start > 0:
        ratio = final_at_start / len(hebrew_words)
        if ratio > 0.1:  # More than 10% of words
            reversed_indicators += 3
        elif ratio > 0.02:  # More than 2%
            reversed_indicators += 1

    # Check 2: Final letters in middle (count as one indicator, not per-word)
    final_in_middle = sum(1 for word in hebrew_words
                          if len(word) > 2 and any(c in final_letters for c in word[1:-1]))
    if final_in_middle > 0:
        ratio = final_in_middle / len([w for w in hebrew_words if len(w) > 2])
        if ratio > 0.1:
            reversed_indicators += 2
        elif ratio > 0.02:
            reversed_indicators += 1

    # Check 3: Known reversed patterns
    reversed_patterns = [
        'ןהכ', 'יול', 'ןומימ', 'ריאמ', 'ןד',  # Common reversed names
        'לוקוטורפ', 'הבישי', 'הצעומ', 'הייריע',  # Common reversed words
    ]
    for pattern in reversed_patterns:
        if pattern in text_stripped:
            reversed_indicators += 1

    # Check 4: Known NORMAL patterns (negative indicator - text is NOT reversed)
    normal_patterns = [
        'פרוטוקול', 'ישיבה', 'מועצה', 'עירייה',  # Common words
        'החלטה', 'הצבעה', 'אושר', 'נגד', 'בעד',  # Decision words
        'משתתפים', 'נוכחים', 'חסרים', 'סגל',  # Attendance
        'ראש העיר', 'חבר מועצה', 'סגן',  # Roles
        'סעיף', 'דיון', 'תקציב',  # Meeting terms
    ]
    for pattern in normal_patterns:
        if pattern in text_stripped:
            normal_indicators += 1

    # Calculate final result
    total_indicators = reversed_indicators + normal_indicators

    if total_indicators == 0:
        return False, 0.0

    # If normal patterns found, bias heavily toward normal
    if normal_indicators > 0:
        if reversed_indicators == 0:
            return False, 0.0
        # Need strong reversed evidence to override normal patterns
        if reversed_indicators < normal_indicators * 2:
            return False, min(reversed_indicators / (normal_indicators * 2), 0.3)

    # Pure reversed detection
    if reversed_indicators >= 3:
        confidence = min(reversed_indicators / 5, 1.0)
        return True, confidence
    elif reversed_indicators >= 1:
        # Weak signal - could be OCR errors
        return False, reversed_indicators * 0.2

    return False, 0.0


def fix_common_ocr_errors(text: str) -> str:
    """
    Fix common OCR errors in Hebrew text.

    This function applies known corrections for common OCR mistakes.

    Args:
        text: Text with potential OCR errors

    Returns:
        Text with common errors fixed
    """
    if not text:
        return text

    result = text

    # Fix common word errors (known corrections)
    corrections = {
        # Reversed common words (if not caught by reverse detection)
        'לוקוטורפ': 'פרוטוקול',
        'הבישי': 'ישיבה',
        'הצעומ': 'מועצה',
        'הייריע': 'עירייה',
        # Common OCR mistakes
        'ארשו': 'אושר',
        'רשוא': 'אושר',
        'העבצה': 'הצבעה',
        'הטלחה': 'החלטה',
    }

    for wrong, correct in corrections.items():
        result = result.replace(wrong, correct)

    return result


def normalize_hebrew_text(text: str, fix_reversed: bool = True) -> str:
    """
    Full normalization pipeline for Hebrew OCR text.

    Applies all available fixes in the correct order:
    1. Clean OCR artifacts
    2. Detect and fix reversed text
    3. Normalize final letters
    4. Fix reversed numbers
    5. Fix common OCR errors

    Args:
        text: Raw OCR text
        fix_reversed: Whether to auto-detect and fix reversed text

    Returns:
        Fully normalized text
    """
    if not text:
        return text

    # Step 1: Clean OCR artifacts
    result = clean_ocr_text(text)

    # Step 2: Detect and fix reversed text
    if fix_reversed:
        is_reversed, confidence = detect_reversed_text(result)
        if is_reversed and confidence > 0.4:
            result = result[::-1]
            result = normalize_final_letters(result)

    # Step 3: Fix reversed numbers
    result = fix_reversed_numbers(result)
    result = fix_reversed_short_numbers(result)

    # Step 4: Fix common OCR errors
    result = fix_common_ocr_errors(result)

    return result


def extract_hebrew_words(text: str) -> List[str]:
    """
    Extract all Hebrew words from text.

    Args:
        text: Text to extract from

    Returns:
        List of Hebrew words
    """
    if not text:
        return []

    return re.findall(r'[א-תךםןףץ]+', text)


def is_valid_hebrew_name(name: str) -> bool:
    """
    Check if a string looks like a valid Hebrew name.

    Args:
        name: Potential name string

    Returns:
        True if it looks like a valid name
    """
    if not name or len(name) < 2:
        return False

    # Must contain Hebrew letters
    hebrew_chars = re.findall(r'[א-תךםןףץ]', name)
    if len(hebrew_chars) < 2:
        return False

    # Check for final letters in wrong positions
    final_letters = set('םןףץך')
    words = name.split()

    for word in words:
        hebrew_only = re.sub(r'[^א-תךםןףץ]', '', word)
        if len(hebrew_only) > 1:
            # Final letter at start = reversed
            if hebrew_only[0] in final_letters:
                return False
            # Final letter in middle = reversed
            if any(c in final_letters for c in hebrew_only[1:-1]):
                return False

    return True


def similarity_score(str1: str, str2: str) -> float:
    """
    Calculate similarity between two Hebrew strings.

    Uses Levenshtein-like distance but also considers
    common OCR confusions.

    Args:
        str1: First string
        str2: Second string

    Returns:
        Similarity score 0.0-1.0
    """
    if not str1 or not str2:
        return 0.0

    if str1 == str2:
        return 1.0

    # Normalize both strings
    s1 = str1.strip().lower()
    s2 = str2.strip().lower()

    if s1 == s2:
        return 1.0

    # Check if one is reversed version of other
    if s1 == s2[::-1] or normalize_final_letters(s1) == normalize_final_letters(s2[::-1]):
        return 0.9

    # Simple character-based similarity
    len1, len2 = len(s1), len(s2)
    max_len = max(len1, len2)

    if max_len == 0:
        return 1.0

    # Count matching characters
    matches = sum(1 for c1, c2 in zip(s1, s2) if c1 == c2)

    # Account for OCR confusions
    for i, (c1, c2) in enumerate(zip(s1, s2)):
        if c1 != c2:
            if c2 in OCR_CONFUSIONS.get(c1, []):
                matches += 0.5

    return matches / max_len
