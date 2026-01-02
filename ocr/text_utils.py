# -*- coding: utf-8 -*-
"""
Text manipulation utilities for Hebrew OCR processing.
פונקציות עזר לעיבוד טקסט עברי מ-OCR

Functions:
- reverse_hebrew_text: Reverse RTL text that was read as LTR
- normalize_final_letters: Fix final letter positions
- fix_reversed_numbers: Fix numbers that appear reversed
"""
import re


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
