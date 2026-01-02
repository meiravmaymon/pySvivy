"""
OCR-based protocol extraction with Hebrew support
"""
import os
import sys
from pdf2image import convert_from_path
import pytesseract
from PIL import Image
import re
from datetime import datetime
from database import get_session
from models import Meeting, Discussion, Vote, Attendance, Person
import json

# Debug flag - set to True to enable debug output
DEBUG = False

def debug_print(*args, **kwargs):
    """Print only if DEBUG is True"""
    if DEBUG:
        print(*args, **kwargs)

# Import LLM helper for fallback extraction and summary generation
try:
    from llm_helper import (
        OLLAMA_AVAILABLE,
        extract_decision_with_llm,
        extract_budget_with_llm,
        extract_vote_with_llm,
        generate_discussion_summary
    )
except ImportError:
    print("WARNING: llm_helper not available, LLM fallback disabled")
    OLLAMA_AVAILABLE = False
    generate_discussion_summary = None

# Configure Tesseract paths
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSDATA_PREFIX = os.path.join(os.path.dirname(__file__), "tessdata").replace("\\", "/")

pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
os.environ['TESSDATA_PREFIX'] = TESSDATA_PREFIX

# Cache for council member names from database
_council_members_cache = None

def get_council_members():
    """Get list of council member full names from database (cached)"""
    global _council_members_cache
    if _council_members_cache is None:
        try:
            session = get_session()
            people = session.query(Person).all()
            _council_members_cache = [p.full_name for p in people if p.full_name]
            session.close()
        except Exception as e:
            print(f"Warning: Could not load council members from DB: {e}")
            _council_members_cache = []
    return _council_members_cache

def match_partial_name(partial_name):
    """
    Match a partial name (like 'ערן') to a full name from the database.
    Returns the full name if a unique match is found, otherwise returns the partial name.
    """
    if not partial_name or len(partial_name) < 2:
        return partial_name

    council_members = get_council_members()
    if not council_members:
        return partial_name

    # Check if partial name is already a full match
    partial_normalized = partial_name.strip()
    for full_name in council_members:
        if partial_normalized == full_name:
            return full_name

    # Try to match first name only (partial name is first name of a council member)
    matches = []
    for full_name in council_members:
        # Split full name into parts
        name_parts = full_name.split()
        if name_parts and name_parts[0] == partial_normalized:
            matches.append(full_name)

    # If exactly one match, use it
    if len(matches) == 1:
        return matches[0]

    # If multiple matches, return partial (ambiguous)
    return partial_name


def extract_staff_with_roles(text):
    """
    חילוץ אנשי סגל עם תפקידיהם מטקסט הפרוטוקול.

    מחפש בקטעים: "נוכחים", "סגל", "משתתפים" - אנשים עם תפקידי סגל
    (מנכ"ל, גזבר, יועמ"ש, מזכיר וכו')

    Returns:
        list of dict: [{'name': str, 'role': str}, ...]
    """
    staff_list = []

    # תפקידי סגל מוכרים - רשימה בסיסית
    # כולל גם גרסאות הפוכות (OCR לפעמים קורא מימין לשמאל)
    staff_roles = [
        # תפקידים בכירים - רגיל והפוך
        'מנכ"ל', 'מנכל', 'ל"כנמ', 'לכנמ',  # מנכ"ל
        'סמנכ"ל', 'סמנכל',
        'גזבר', 'גזברית', 'גזבר העירייה', 'רבזג',  # גזבר
        'יועמ"ש', 'יועץ משפטי', 'יועצת משפטית', 'ש"מעוי',  # יועמ"ש
        'מבקר', 'מבקרת', 'מבקר העירייה', 'רקבמ',  # מבקר
        'מהנדס', 'מהנדסת', 'מהנדס העירייה', 'סדנהמ',  # מהנדס
        # תפקידי ניהול
        'מנהל אגף', 'מנהלת אגף', 'מנהל מחלקה', 'מנהלת מחלקה',
        'מנהל מח\'', 'מנהלת מח\'',
        'מנהל', 'מנהלת', 'להנמ', 'תלהנמ',  # מנהל
        'ףגא להנמ',  # מנהל אגף הפוך
        # תפקידי מטה
        'עוזר ראש', 'עוזרת ראש', 'עוזר מנכ', 'עוזרת מנכ',
        'דובר', 'דוברת', 'רבוד',  # דובר
        'מזכיר', 'מזכירה', 'מזכירת',
        'רכז', 'רכזת', 'יו"ר',
        # תפקידי מקצוע
        'תובע', 'תובעת', 'תקציבן', 'תקציבנית',
        'קב"ט', 'רו"ח', 'ח"ור',  # רו"ח
        'חשב', 'חשבת',
        'וטרינר', 'וטרינרית', 'וטרינר עירוני',
        'אדריכל', 'לכירדא',  # אדריכל
        'נציג ציבור',
        # מילות מפתח כלליות לסגל
        'סגל מקצועי', 'סגל', 'לגס'  # סגל הפוך
    ]

    # טען תפקידים נוספים מבסיס הנתונים
    try:
        session = get_session()
        from models import Role
        db_roles = session.query(Role).all()
        for role in db_roles:
            if role.name and role.name not in staff_roles:
                # לא להוסיף תפקידים של נבחרים
                if 'חבר מועצה' not in role.name and 'ראש העיר' not in role.name and 'סגן ראש' not in role.name:
                    staff_roles.append(role.name)
        session.close()
    except Exception as e:
        debug_print(f"Warning: Could not load roles from DB: {e}")

    # בניית פטרן לזיהוי תפקידים
    staff_pattern = '|'.join(re.escape(role) for role in staff_roles)

    # גישה חדשה: חפש ישירות שורות עם תפקידי סגל בכל הטקסט
    # הפורמט יכול להיות:
    # 1. "שם - תפקיד" (כמו בפרוטוקול: "שירה דקל כץ - מנכ"ל העירייה")
    # 2. "תפקיד - שם"
    # 3. "תפקיד: שם"

    # קודם ננסה למצוא קטע "סגל:" ספציפי (רגיל או הפוך)
    # הפוך: ": לגס" (נקודתיים לפני)
    staff_section = re.search(
        r'(?:סגל\s*:|:\s*לגס)\s*(.*?)(?=על\s+סדר|םויה\s+רדס|סעיף|ףיעס|משתתפים|נוכחים|חסרים|נעדרים|לוקוטורפ|\n\s*\n\s*\n|$)',
        text[:10000],
        re.DOTALL | re.IGNORECASE
    )
    # בדוק אם מצאנו בגרסה ההפוכה
    # הטקסט יכול להיות ":לגס" או ": לגס" (עם או בלי רווח)
    is_staff_reversed = staff_section and ('לגס' in text[max(0, staff_section.start()-5):staff_section.start()+15] or
                                           'הייריעה' in text[staff_section.start():staff_section.start()+200])

    # גם קטע "נוכחים:" (רגיל או הפוך: םיחכונ)
    officials_section = re.search(
        r'(?:נוכחים|םיחכונ)\s*:\s*(.*?)(?=על\s+סדר|םויה\s+רדס|סעיף|ףיעס|חסרים|םירסח|לגס|סגל|\n\s*\n\s*\n|$)',
        text[:10000],
        re.DOTALL | re.IGNORECASE
    )
    is_officials_reversed = officials_section and 'םיחכונ' in text[max(0, officials_section.start()-5):officials_section.start()+15]

    sections_to_process = []
    section_reversed = []
    if staff_section:
        sections_to_process.append(staff_section.group(1))
        section_reversed.append(is_staff_reversed)
        debug_print(f"DEBUG extract_staff: Found 'סגל/לגס:' section, {len(staff_section.group(1))} chars, reversed={is_staff_reversed}")
    if officials_section:
        sections_to_process.append(officials_section.group(1))
        section_reversed.append(is_officials_reversed)
        debug_print(f"DEBUG extract_staff: Found 'נוכחים/םיחכונ:' section, {len(officials_section.group(1))} chars, reversed={is_officials_reversed}")

    # אם לא מצאנו קטעים ספציפיים, חפש בכל תחילת הטקסט
    if not sections_to_process:
        # בדוק אם כל הטקסט הפוך
        is_text_reversed = ': לגס' in text[:3000] or 'םיחכונ' in text[:3000]
        sections_to_process.append(text[:8000])
        section_reversed.append(is_text_reversed)
        debug_print(f"DEBUG extract_staff: No specific section found, searching in first 8000 chars, reversed={is_text_reversed}")

    def is_line_reversed(line_text):
        """
        בדיקה חכמה אם שורה ספציפית הפוכה.
        משתמש במספר היוריסטיקות:
        1. מילים הפוכות מוכרות (הייריעה, ל"כנמ, רבזג וכו')
        2. אותיות סופיות במקום לא נכון
        3. מבנה השורה (תפקיד-שם vs שם-תפקיד)
        """
        # מילים הפוכות שמעידות על טקסט הפוך
        reversed_indicators = [
            'הייריעה',   # העירייה
            'ל"כנמ', 'לכנמ',  # מנכ"ל
            'רבזג',      # גזבר
            'ש"מעוי',    # יועמ"ש
            'רקבמ',      # מבקר
            'סדנהמ',     # מהנדס
            'להנמ',      # מנהל
            'ריכזמ',     # מזכיר
            'הצעומה',    # המועצה
            'ריעה',      # העיר
            'תיטפשמ',    # משפטית
            'הכשל',      # לשכה
        ]
        if any(ind in line_text for ind in reversed_indicators):
            return True

        # בדיקת אותיות סופיות בתחילת מילים
        words = re.findall(r'[א-תךםןףץ]+', line_text)
        final_letters = ['ם', 'ן', 'ף', 'ץ', 'ך']
        for word in words:
            if len(word) > 1 and word[0] in final_letters:
                return True

        return False

    for section_idx, section_text in enumerate(sections_to_process):
        section_force_reverse = section_reversed[section_idx] if section_idx < len(section_reversed) else False
        lines = section_text.split('\n')
        for line in lines:
            line = line.strip()
            if not line or len(line) < 5:
                continue

            # ניקוי תווי RTL/LTR
            line = re.sub(r'^[^\u0590-\u05FF\s\'"]+', '', line)

            # בדיקה חכמה אם השורה הספציפית הפוכה
            # אם הקטע כולו הפוך או אם השורה עצמה מכילה סימנים להיפוך
            force_reverse = section_force_reverse or is_line_reversed(line)

            # חיפוש תפקיד סגל בשורה
            role_match = re.search(f'({staff_pattern})', line, re.IGNORECASE)
            if not role_match:
                continue

            found_role = role_match.group(1)

            # מציאת השם - לפני או אחרי התפקיד
            # פורמטים אפשריים:
            # "שם פרטי שם משפחה - מנכ"ל"
            # "מנכ"ל - שם פרטי שם משפחה"
            # "מנכ"ל העירייה: שם"

            separator = None
            if '-' in line:
                separator = '-'
            elif ':' in line:
                separator = ':'
            elif '–' in line:  # מקף ארוך
                separator = '–'

            name = None
            role = found_role

            if separator:
                parts = line.split(separator, 1)
                if len(parts) == 2:
                    part0 = parts[0].strip()
                    part1 = parts[1].strip()

                    # בדיקה איזה חלק מכיל את התפקיד
                    if re.search(f'({staff_pattern})', part0, re.IGNORECASE):
                        # התפקיד בחלק הראשון - השם בחלק השני
                        name = part1
                        # נסה לחלץ תפקיד מלא יותר
                        role = part0
                    else:
                        # התפקיד בחלק השני - השם בחלק הראשון
                        name = part0
                        role = part1
            else:
                # אין מפריד - נסה לחלץ שם לפי מיקום התפקיד
                role_start = role_match.start()
                role_end = role_match.end()

                # השם בדרך כלל לפני התפקיד
                before = line[:role_start].strip()
                after = line[role_end:].strip()

                # השם הוא החלק הארוך יותר שמכיל אותיות עבריות
                if before and re.search(r'[א-ת]{2,}', before):
                    name = before
                elif after and re.search(r'[א-ת]{2,}', after):
                    name = after

            if name:
                # ניקוי השם
                # הסרת כינויים
                titles = [r'עו["\'"\']+[דר]\s*', r'מר\s+', r'גב["\']?\s*', r'ד["\'"\']+ר\s*', r'פרופ["\']?\s*']
                for title in titles:
                    name = re.sub(title, '', name, flags=re.IGNORECASE)

                # הסרת תווים שאינם עבריים (חוץ מרווחים וגרשיים)
                name = re.sub(r'[^א-ת\s\'"]', '', name).strip()
                name = re.sub(r'\s+', ' ', name)

                # ניקוי התפקיד
                role = re.sub(r'[^א-ת\s\'"/]', '', role).strip()
                role = re.sub(r'\s+', ' ', role)

                # בדיקת תקינות - שם ותפקיד באורכים סבירים
                # שם: 3-50 תווים, עד 4 מילים
                # תפקיד: 4-40 תווים
                word_count = len(name.split())
                if name and len(name) >= 3 and len(name) <= 50 and word_count <= 4 and len(role) >= 4 and len(role) <= 40:
                    # היפוך טקסט עברי - אם הקטע כולו הפוך, הפוך תמיד ונרמל אותיות סופיות
                    if force_reverse:
                        name = smart_reverse_hebrew(name)
                        role = smart_reverse_hebrew(role)
                    else:
                        name = reverse_hebrew_text(name)
                        role = reverse_hebrew_text(role)

                    # סינון נבחרים - אלה לא סגל (בדוק גם הפוך)
                    elected_keywords = ['ראש העיר', 'סגן ראש', 'חבר מועצה', 'חברת מועצה',
                                       'ריעה שאר', 'שאר ןגס', 'הצעומ רבח', 'הצעומ תרבח']
                    if any(kw in role for kw in elected_keywords):
                        continue

                    # התאמה לשם מלא מבסיס הנתונים
                    name = match_partial_name(name)

                    # מניעת כפילויות
                    if not any(s['name'] == name for s in staff_list):
                        staff_list.append({
                            'name': name,
                            'role': role
                        })

    return staff_list


def extract_sub_discussions(parent_num, section_text):
    """
    Extract sub-discussions from a parent discussion that contains committee protocol approval.
    For example, "סעיף 13 - אישור החלטות ועדת הנצחה" may contain multiple separate votes.

    Returns list of sub-discussions with format:
    [{'number': '13.1', 'title': '...', 'decision': '...', 'yes_votes': N, ...}, ...]
    """
    sub_discussions = []

    # Pattern to find individual votes within the section
    # OCR artifacts: "על" may appear as "by", "Yy", with Unicode RTL/LTR marks around them
    # \u200e = LTR mark, \u200f = RTL mark - these appear around OCR-misread "על"
    # Look for "הצבעה על/בעניין X:" followed by vote counts and decision
    # IMPORTANT: lookahead must match "הצבעה" followed by a word (not just "הצבעה:" alone)
    # This prevents splitting on empty "הצבעה:" which is sometimes OCR artifact within same vote
    vote_pattern = r'הצבעה[\s\u200e\u200f]+(?:על|בעניין|לגבי|בנושא|[\u200e\u200f]*by[\u200e\u200f]*|[\u200e\u200f]*Yy[\u200e\u200f]*|[^\s\n]{0,5})?[\s\u200e\u200f]*([^\n:]{10,150}?)(?::\s*|\n)(.*?)(?=הצבעה[\s\u200e\u200f]+(?:על|בעניין|לגבי|בנושא|[\u200e\u200f]*by|[\u200e\u200f]*Yy|[א-ת])|סעיף\s+מס|$)'

    matches = list(re.finditer(vote_pattern, section_text, re.DOTALL | re.IGNORECASE))

    debug_print(f"DEBUG: extract_sub_discussions - found {len(matches)} vote patterns")

    if not matches:
        return []

    for idx, match in enumerate(matches, start=1):
        sub_title = match.group(1).strip()
        sub_content = match.group(2).strip()

        # Skip if title is too short or looks like garbage
        # Valid vote subjects should be at least 15 chars (e.g., "הנצחת יצחק נבון ז"ל")
        if len(sub_title) < 15:
            debug_print(f"DEBUG: Skipping sub-discussion {idx} - title too short: '{sub_title}'")
            continue

        # Skip if title doesn't contain Hebrew (probably OCR garbage)
        if not re.search(r'[א-ת]', sub_title):
            debug_print(f"DEBUG: Skipping sub-discussion {idx} - no Hebrew in title: '{sub_title}'")
            continue

        # Skip titles that look like speaker names or notes, not vote subjects
        # Valid vote subjects usually contain: "הנצחת", "ז"ל", "ז'ל", names of people/places
        # Invalid: "עו"ד יעלה מקליס", "פה אחד", just speaker attribution
        if re.match(r'^עו"ד\s+', sub_title) or re.match(r'^מר\s+', sub_title) or re.match(r'^גב[\'׳]\s+', sub_title):
            debug_print(f"DEBUG: Skipping sub-discussion {idx} - looks like speaker name: '{sub_title}'")
            continue

        # Skip if it's just "פה אחד" or similar
        if re.match(r'^פה\s+אחד', sub_title, re.IGNORECASE):
            debug_print(f"DEBUG: Skipping sub-discussion {idx} - just vote result: '{sub_title}'")
            continue

        # For committee protocol approval sections, require memorial-related keywords
        # Valid: "הנצחת X ז"ל", "הנצחה של X"
        # Invalid: random person names without context
        if not re.search(r'הנצחת|הנצחה|ז"ל|ז\'ל|זכרון|לזכר', sub_title):
            debug_print(f"DEBUG: Skipping sub-discussion {idx} - no memorial keywords: '{sub_title}'")
            continue

        # Use actual count (not idx) for numbering since some matches are skipped
        actual_num = len(sub_discussions) + 1
        sub_disc = {
            'number': f"{parent_num}.{actual_num}",
            'content': sub_title[:500],
        }

        debug_print(f"DEBUG: Sub-discussion {parent_num}.{idx}: '{sub_title[:60]}...'")

        # Extract vote counts from sub_content (first 500 chars)
        vote_section = sub_content[:500]

        # Pattern: "בעד- N" or "בעד - N" or "3va - N" (OCR for בעד)
        # Note: Unicode RTL mark (0x200f) may appear after 3va, so we use [\s\u200f]* to match it
        yes_match = re.search(r'(?:בעד|3va)[\s\u200f]*-\s*(\d+)', vote_section)
        if yes_match:
            sub_disc['yes_votes'] = int(yes_match.group(1))
            debug_print(f"DEBUG: Found yes votes: {sub_disc['yes_votes']}")

        no_match = re.search(r'נגד\s*-\s*(\d+)', vote_section)
        if no_match:
            sub_disc['no_votes'] = int(no_match.group(1))

        # Pattern: "נמנע- N" or "נמנעים - N" or "גמנצים" (OCR for נמנעים)
        avoid_match = re.search(r'(?:נמנע|נמנעים|גמנצים)\s*-\s*(\d+)', vote_section)
        if avoid_match:
            sub_disc['avoid_votes'] = int(avoid_match.group(1))
            debug_print(f"DEBUG: Found avoid votes: {sub_disc['avoid_votes']}")

        # Check for unanimous vote
        if re.search(r'פה\s+אח[דר]', vote_section, re.IGNORECASE):
            sub_disc['vote_type'] = 'unanimous'
            debug_print(f"DEBUG: Found unanimous vote")

        # Extract decision - look for "החלטה:" pattern
        decision_match = re.search(r'החלטה:\s*([^\n]+(?:\n[^\n]+)?)', sub_content, re.IGNORECASE)
        if decision_match:
            decision_text = decision_match.group(1).strip()
            # Clean decision text
            decision_text = re.sub(r'\s+', ' ', decision_text)
            sub_disc['decision'] = decision_text[:500]
            debug_print(f"DEBUG: Found decision: '{decision_text[:60]}...'")
        elif 'yes_votes' in sub_disc or sub_disc.get('vote_type') == 'unanimous':
            sub_disc['decision'] = 'אושר'

        sub_discussions.append(sub_disc)

    return sub_discussions


def is_committee_protocol_approval(title):
    """Check if a discussion is about approving a committee's protocol/decisions."""
    committee_patterns = [
        r'אישור.*החלטות\s+ועד',
        r'אישור.*פרוטוקול\s+ועד',
        r'החלטות\s+ועדת',
        r'פרוטוקול\s+ועדת',
    ]
    for pattern in committee_patterns:
        if re.search(pattern, title, re.IGNORECASE):
            return True
    return False


def normalize_final_letters(text):
    """
    נרמול אותיות סופיות לאחר היפוך טקסט.
    כשמהפכים טקסט עברי, האותיות הסופיות עוברות למקום הלא נכון.
    פונקציה זו מתקנת: ם→מ (באמצע), מ→ם (בסוף)
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

    דוגמאות:
    - "000,012" → "210,000"
    - "000,09" → "90,000"
    - "000,003" → "300,000"

    זיהוי מספר הפוך:
    - מתחיל ב-0
    - יש פסיק אחרי 3 ספרות מההתחלה (למשל 000,)
    - הספרות אחרי הפסיק אינן כולן 0
    """
    if not text:
        return text

    import re

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

    בעיה: OCR קורא "46" כ-"64" בגלל בעיית RTL/LTR

    Args:
        text: הטקסט לתיקון
        context: 'budget' לתקציב (כביש 46, ש"ח), 'vote' להצבעה

    Returns:
        טקסט מתוקן עם מספרים הפוכים שתוקנו

    דוגמאות בהקשר תקציב:
    - "כביש 64" → "כביש 46" (אם 46 מוכר כדרך)
    - "000,052 ש\"ח" → "250,000 ש\"ח"
    """
    if not text:
        return text

    import re

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
            # כביש XX, דרך XX, כביש מס' XX
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
    Reverse Hebrew text that was stored in reversed order (RTL as LTR)
    Uses multiple heuristics to detect reversed Hebrew text
    """
    if not text:
        return text

    text_stripped = text.strip()
    if len(text_stripped) < 2:
        return text

    # Final letters (סופיות) - מופיעות רק בסוף מילים בעברית תקינה
    final_letters = ['ם', 'ן', 'ף', 'ץ', 'ך']

    # Extract Hebrew words
    import re
    hebrew_words = re.findall(r'[א-תךםןףץ]+', text_stripped)

    if not hebrew_words:
        return text

    # === HEURISTIC 1: Final letters at word START ===
    # This is the STRONGEST indicator - final letters NEVER start words in correct Hebrew
    for word in hebrew_words:
        if len(word) > 1 and word[0] in final_letters:
            return normalize_final_letters(text[::-1])

    # === HEURISTIC 2: Final letters in MIDDLE of words ===
    # In correct Hebrew, final letters appear ONLY at word end
    for word in hebrew_words:
        if len(word) > 2:
            middle = word[1:-1]  # everything except first and last char
            for final in final_letters:
                if final in middle:
                    return normalize_final_letters(text[::-1])

    # === HEURISTIC 3: Common reversed name patterns ===
    # Names that appear frequently in municipal protocols
    reversed_patterns = [
        # שמות פרטיים הפוכים
        'ןורש',    # שרון
        'ןנור',    # רונן
        'ןועמש',   # שמעון
        'ןרהא',    # אהרן
        'ןתנוי',   # יונתן
        'ןד',      # דן (קצר אבל נפוץ)
        'ןור',     # רון
        'ןב',      # בן
        'הרש',     # שרה
        'ריאמ',    # מאיר
        'יול',     # לוי
        'יגח',     # חגי
        'לאינד',   # דניאל
        'לכימ',    # מיכל
        'ילא',     # אלי
        'הלא',     # אלה
        'הואד',    # דאוה (שמות ערביים)

        # שמות משפחה נפוצים הפוכים
        'ןהכ',     # כהן
        'יול',     # לוי
        'ןומימ',   # מימון
        'ןמטור',   # רוטמן
        'רלימ',    # מילר
        'דעס',     # סער
        'קינזר',   # רזניק
        'ירשוב',   # בושרי
        'רקניפ',   # פינקר
        'סילקמ',   # מקליס
        'ןמנירג',  # גרינמן
        'ץרפ',     # פרץ
        'ןמדירפ',  # פרידמן
        'ןמרבליז', # זילברמן
        'גרבנזור', # רוזנברג
        'גרבדלוג', # גולדברג
        'יקסנליו', # וילנסקי
        'יקסבוקי', # יקובסקי

        # תפקידים הפוכים
        'ל"כנמ',   # מנכ"ל
        'לכנמ',    # מנכל
        'רבזג',    # גזבר
        'ש"מעוי',  # יועמ"ש
        'רקבמ',    # מבקר
        'סדנהמ',   # מהנדס
        'להנמ',    # מנהל
        'רבוד',    # דובר
        'לכירדא',  # אדריכל
        'ריכזמ',   # מזכיר

        # מילים כלליות הפוכות
        'יפסכה',   # הכספי
        'רושיא',   # אישור
        'הטלחה',   # החלטה
        'תנשל',    # לשנת
        'הייריעה', # העירייה
        'הצעומה',  # המועצה

        # דפוסים שזוהו מלוג התיקונים
        "ה'זב ןתנ",    # נתן בזיה
        'רנרפואל ןרק', # קרן לאופרנר / קרן לאופר
        'ודאינל לג',   # גל לניאדו
        'שימלח ינור',  # רוני חלמיש
        "ד\"וע",       # עו"ד (הפוך)
        'ןרק',         # קרן
        'לג',          # גל
        'ןתנ',         # נתן
        'ינור',        # רוני
    ]
    if any(pattern in text_stripped for pattern in reversed_patterns):
        return normalize_final_letters(text[::-1])

    # === HEURISTIC 4: Word ending patterns ===
    # In correct Hebrew, words commonly END with: ה, ת, ם, ן, י
    # In reversed Hebrew, words would START with these
    common_end_letters = ['ה', 'ת', 'י']
    reversed_word_count = 0
    for word in hebrew_words:
        if len(word) > 2:
            # Word starts with common ending letter = likely reversed
            if word[0] in common_end_letters:
                reversed_word_count += 1

    # If majority of multi-letter words look reversed
    multi_letter_words = [w for w in hebrew_words if len(w) > 2]
    if multi_letter_words and reversed_word_count >= len(multi_letter_words) * 0.5:
        return normalize_final_letters(text[::-1])

    # === HEURISTIC 5: Word beginning patterns ===
    # Hebrew words commonly START with: ה, ב, ו, ל, מ, ש, כ
    # Check if words END with these instead (reversed indicator)
    common_start_letters = ['ה', 'ב', 'ו', 'ל', 'מ', 'ש', 'כ']
    wrong_ending_count = 0
    for word in hebrew_words:
        if len(word) > 2:
            # Word ends with common starting letter but doesn't start with one
            if word[-1] in common_start_letters and word[0] not in common_start_letters:
                wrong_ending_count += 1

    if multi_letter_words and wrong_ending_count >= len(multi_letter_words) * 0.4:
        return normalize_final_letters(text[::-1])

    return text


def smart_reverse_hebrew(text):
    """
    היפוך חכם של טקסט עברי - מהפך ומנרמל אותיות סופיות.
    פונקציה זו מהפכת תמיד ומתאימה לשימוש כש-force_reverse=True
    """
    if not text:
        return text
    return normalize_final_letters(text[::-1])


def extract_text_from_pdf(pdf_path, lang='heb+eng'):
    """Extract text from PDF using OCR on embedded images"""
    import pdfplumber
    from io import BytesIO

    print(f"Opening PDF and extracting images for OCR...")

    full_text = ""

    with pdfplumber.open(pdf_path) as pdf:
        num_pages = len(pdf.pages)
        print(f"Processing {num_pages} pages...")

        for i, page in enumerate(pdf.pages, 1):
            print(f"  Page {i}/{num_pages}...", end="\r")

            # Try to extract text directly first
            direct_text = page.extract_text()
            if direct_text and len(direct_text.strip()) > 50:
                full_text += f"\n--- Page {i} (Direct) ---\n{direct_text}\n"
                continue

            # If no text, try OCR on page image
            try:
                # Convert page to image
                im = page.to_image(resolution=200)
                pil_image = im.original

                # Run OCR
                page_text = pytesseract.image_to_string(
                    pil_image,
                    lang=lang,
                    config=f'--tessdata-dir {TESSDATA_PREFIX} --psm 6'
                )
                full_text += f"\n--- Page {i} (OCR) ---\n{page_text}\n"
            except Exception as e:
                print(f"\n  Warning: OCR failed on page {i}: {e}")
                full_text += f"\n--- Page {i} (Failed) ---\n"

    print("\nExtraction complete!")
    return full_text

def detect_grouped_vote(text):
    """
    זיהוי דפוס הצבעה מקובצת על מספר סעיפים יחד.

    דפוס נפוץ בפרוטוקולים: ראש העיר מבקש לדון ולהצביע על סעיפים X, Y, Z יחד.
    הסעיפים מוצגים בנפרד אבל הדיון וההצבעה משותפים.

    Args:
        text: טקסט הפרוטוקול

    Returns:
        dict עם:
        - grouped_items: רשימת קבוצות סעיפים (כל קבוצה = רשימת מספרי סעיפים)
        - vote_data: נתוני ההצבעה המשותפת לכל קבוצה
        או None אם לא נמצא דפוס כזה
    """
    if not text:
        return None

    grouped_votes = []

    # דפוסים לזיהוי בקשה לדיון והצבעה משותפים
    patterns = [
        # "לדון ולהצביע על סעיפים 5, 6 ו-7 יחד"
        r'(?:לדון|נדון).*?(?:להצביע|נצביע).*?(?:על\s+)?סעיפים?\s*(\d+)\s*[,،]\s*(\d+)\s*(?:[,،]?\s*ו?[-–]?\s*(\d+))?\s*(?:יחד|ביחד|כאחד)',

        # "סעיפים 5-7 יידונו ויוצבעו יחד"
        r'סעיפים?\s*(\d+)\s*[-–]\s*(\d+)\s*(?:יידונו|נידונו).*?(?:יוצבעו|הוצבעו)\s*(?:יחד|ביחד)',

        # "הצבעה משותפת על סעיפים 5, 6, 7"
        r'הצבעה\s*משותפת.*?סעיפים?\s*(\d+)\s*[,،]\s*(\d+)\s*(?:[,،]?\s*ו?[-–]?\s*(\d+))?',

        # "נצביע על שלושת הסעיפים יחד" (after listing items)
        r'(?:נצביע|להצביע)\s*על\s*(?:שלושת|ארבעת|שני)\s*ה?סעיפים\s*(?:יחד|ביחד|כאחד)',

        # "אני מבקש/ת לאחד את הדיון בסעיפים..."
        r'(?:מבקש|מבקשת)\s*(?:לאחד|לחבר).*?(?:הדיון|ההצבעה).*?סעיפים?\s*(\d+)\s*[,،]\s*(\d+)\s*(?:[,،]?\s*ו?[-–]?\s*(\d+))?',
    ]

    for pattern in patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE | re.DOTALL)
        for match in matches:
            groups = [g for g in match.groups() if g]
            if len(groups) >= 2:
                item_numbers = [int(g) for g in groups if g.isdigit()]
                if len(item_numbers) >= 2:
                    # בדיקה אם זה טווח (5-7) או רשימה (5, 6, 7)
                    if len(item_numbers) == 2 and item_numbers[1] - item_numbers[0] > 1:
                        # זה טווח: 5-7 = [5, 6, 7]
                        item_numbers = list(range(item_numbers[0], item_numbers[1] + 1))

                    grouped_votes.append({
                        'items': item_numbers,
                        'match_text': match.group(0)[:200],
                        'position': match.start()
                    })

    if not grouped_votes:
        return None

    # הסרת כפילויות (אותה קבוצה שנמצאה כמה פעמים)
    unique_groups = []
    seen_items = set()
    for group in grouped_votes:
        items_tuple = tuple(sorted(group['items']))
        if items_tuple not in seen_items:
            seen_items.add(items_tuple)
            unique_groups.append(group)

    return {
        'grouped_items': unique_groups,
        'count': len(unique_groups)
    }


def apply_grouped_vote(discussions, grouped_vote_info, protocol_text):
    """
    החלת הצבעה מקובצת על סעיפים - שכפול נתוני הצבעה והוספת הערה לתקציר.

    Args:
        discussions: רשימת הסעיפים שחולצו
        grouped_vote_info: מידע על הצבעות מקובצות (מ-detect_grouped_vote)
        protocol_text: הטקסט המלא לחילוץ נתוני הצבעה

    Returns:
        רשימת הסעיפים עם נתוני הצבעה מעודכנים
    """
    if not grouped_vote_info or not discussions:
        return discussions

    for group in grouped_vote_info.get('grouped_items', []):
        item_numbers = group['items']
        item_numbers_str = [str(n) for n in item_numbers]

        # מציאת נתוני ההצבעה המשותפת
        # חיפוש בטקסט אחרי הבקשה לדיון משותף
        vote_data = None

        # דפוסים לחילוץ תוצאות הצבעה
        vote_patterns = [
            r'בעד\s*[-:]\s*(\d+)\s*[,،]?\s*נגד\s*[-:]\s*(\d+)\s*[,،]?\s*נמנע\s*[-:]\s*(\d+)',
            r'(\d+)\s*בעד\s*[,،]?\s*(\d+)\s*נגד\s*[,،]?\s*(\d+)\s*נמנע',
            r'פה\s*אחד',  # הצבעה פה אחד
        ]

        # חיפוש ההצבעה באזור אחרי הבקשה לדיון משותף
        start_pos = group.get('position', 0)
        search_text = protocol_text[start_pos:start_pos + 5000]

        for pattern in vote_patterns:
            match = re.search(pattern, search_text, re.IGNORECASE)
            if match:
                if 'פה אחד' in match.group(0):
                    vote_data = {'yes': -1, 'no': 0, 'abstain': 0, 'unanimous': True}
                else:
                    vote_data = {
                        'yes': int(match.group(1)),
                        'no': int(match.group(2)),
                        'abstain': int(match.group(3)),
                        'unanimous': False
                    }
                break

        # עדכון כל הסעיפים בקבוצה
        for disc in discussions:
            disc_num = disc.get('number', '')
            if disc_num in item_numbers_str:
                # הוספת סימון שזו הצבעה מקובצת
                disc['grouped_vote'] = True
                disc['grouped_with'] = item_numbers_str

                # שכפול נתוני ההצבעה
                if vote_data:
                    disc['vote_data'] = vote_data

                # עדכון התקציר עם הערה על דיון משותף
                other_items = [n for n in item_numbers_str if n != disc_num]
                if other_items:
                    grouped_note = f"[הערה: סעיף זה נידון והוצבע יחד עם סעיפים {', '.join(other_items)}]"
                    if 'summary_note' not in disc:
                        disc['summary_note'] = grouped_note
                    else:
                        disc['summary_note'] += ' ' + grouped_note

    return discussions


def parse_protocol_text(text):
    """Parse extracted text to find meeting data"""
    extracted_data = {
        'meeting_info': {},
        'attendances': [],
        'discussions': [],
        'metadata': {'text_length': len(text)}
    }

    # Extract meeting number
    meeting_no_patterns = [
        r'פרוטוקול\s*(?:מס[\'׳]?\s*)?(\d+/\d+)',
        r'ישיבה\s*(?:מספר|מס[\'׳]?)\s*(\d+/\d+)',
        r'(\d{1,2}/\d{2})'
    ]
    for pattern in meeting_no_patterns:
        match = re.search(pattern, text)
        if match:
            extracted_data['meeting_info']['meeting_no'] = match.group(1)
            break

    # Extract date
    date_patterns = [
        r'תאריך[:\s]+(\d{1,2}[./]\d{1,2}[./]\d{2,4})',
        r'מיום[:\s]+(\d{1,2}[./]\d{1,2}[./]\d{2,4})',
        r'(\d{1,2}\.\d{1,2}\.\d{2,4})',
        r'(\d{1,2}/\d{1,2}/\d{2,4})',
    ]
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            date_str = match.group(1)
            # Normalize date format to DD/MM/YYYY
            date_str = date_str.replace('.', '/')
            parts = date_str.split('/')
            if len(parts) == 3:
                day = parts[0].zfill(2)
                month = parts[1].zfill(2)
                year = parts[2]
                # Convert 2-digit year to 4-digit
                if len(year) == 2:
                    year = '20' + year if int(year) < 50 else '19' + year
                date_str = f'{day}/{month}/{year}'
            extracted_data['meeting_info']['date_str'] = date_str
            break

    # Extract title
    title_patterns = [
        r'(ישיבת\s+(?:מועצת\s+)?(?:העיר\s+)?[^\n]+)',
        r'(פרוטוקול\s+[^\n]+)'
    ]
    for pattern in title_patterns:
        match = re.search(pattern, text[:1000])
        if match:
            title = match.group(1).strip()
            # Fix common OCR errors in titles
            title = title.replace('מוצצת', 'מועצת')  # ע misread as צ
            title = title.replace('מועעצת', 'מועצת')  # double ע
            extracted_data['meeting_info']['title'] = title
            break

    # Extract meeting type (מן המניין / שלא מן המניין / אסיפה כללית)
    # Search in first 2000 chars where meeting header typically appears
    header_text = text[:2000]

    # Check for meeting type patterns
    # Priority order matters - check "שלא מן המניין" before "מן המניין"
    if re.search(r'(?:שלא\s+מן\s+המניין|לא\s+מן\s+המניין|מיוחדת)', header_text, re.IGNORECASE):
        extracted_data['meeting_info']['meeting_type'] = 'special'
        extracted_data['meeting_info']['meeting_type_heb'] = 'שלא מן המניין'
    elif re.search(r'אסיפה\s+כללית', header_text, re.IGNORECASE):
        extracted_data['meeting_info']['meeting_type'] = 'general_assembly'
        extracted_data['meeting_info']['meeting_type_heb'] = 'אסיפה כללית'
    elif re.search(r'מן\s+המניין', header_text, re.IGNORECASE):
        extracted_data['meeting_info']['meeting_type'] = 'regular'
        extracted_data['meeting_info']['meeting_type_heb'] = 'מן המניין'
    else:
        # Default to regular if no type found
        extracted_data['meeting_info']['meeting_type'] = 'regular'
        extracted_data['meeting_info']['meeting_type_heb'] = 'מן המניין'

    # Extract attendance
    # Section 1: "משתתפים" = Present council members + officials
    # Try to find explicit "משתתפים" header first (normal or reversed)
    # End markers: חסרים/נעדרים OR "על סדר היום" OR "--- Page" OR multiple empty lines
    present_section = re.search(
        r'(?:משתתפ[א-ת]*|םיפתתשמ)[:\s\W]+(.*?)(?=חפסרים|חסרים|נעדרים|נוכחים|םירסח|םירדענ|םיכוחנ|על\s+סדר\s+היום|---\s+Page|\n\s*\n\s*\n)',
        text,
        re.DOTALL | re.IGNORECASE
    )

    # If not found, look for attendance list starting with name pattern after meeting header
    if not present_section:
        # Look for list starting with lines containing "ראש העיר" or similar (normal or reversed)
        # Can end at "חסרים/נעדרים" OR "סגל:" (some protocols have no absent section)
        present_section = re.search(
            r'(?:נפתחה בשעה|הישיבה נפתחה|העשב החתפנ|החתפנ הבישיה)[^\n]*\n(.*?)(?=חפסרים|חסרים|נעדרים|םירסח|םירדענ|סגל|לגס)',
            text,
            re.DOTALL | re.IGNORECASE
        )

    # Section 2: "חסרים/נעדרים" = Absent council members (normal or reversed)
    # Can be followed by "נוכחים", "סגל", or "על סדר היום"
    absent_section = re.search(
        r'(?:נעדרים|חסרים|חפסרים|םירדענ|םירסח)[:\s]+(.*?)(?=נוכחים|סגל|על.*היום|םיכוחנ|לגס|םויה.*רדס)',
        text,
        re.DOTALL | re.IGNORECASE
    )

    # Section 3: "נוכחים/סגל" = Additional officials (comes AFTER absent members, normal or reversed)
    officials_section = re.search(
        r'(?:נוכחים|סגל|םיכוחנ|לגס)[:\s]+(.*?)(?=על.*היום|םויה.*רדס|$)',
        text,
        re.DOTALL | re.IGNORECASE
    )

    # Process present members (משתתפים)
    if present_section:
        present_text = present_section.group(1)
        lines = present_text.split('\n')
        for line in lines:
            # Skip empty lines
            line_stripped = line.strip()
            if not line_stripped or len(line_stripped) < 5:
                continue

            # Clean line from RTL/LTR marks and other non-Hebrew characters at the beginning
            # This fixes OCR issues like "‎MY‏ מאיר" -> "מאיר"
            line_cleaned = re.sub(r'^[^\u0590-\u05FF\s\'"]+', '', line_stripped)

            # Pattern: "name - role" OR "name . role" where role contains keywords (normal or reversed)
            # Normal: "עו"ד יעלה מקליס - ראש העיר" or "אורי שנהר . חבר מועצה"
            # Reversed: "ריעה שאר - סילקמ הלעי ד"וע" (role BEFORE dash!)
            # Support both dash (-) and period (.) as separators
            separator = None
            if '-' in line_cleaned:
                separator = '-'
            elif '.' in line_cleaned:
                separator = '.'

            if separator and re.search(r'(ראש|סגן|חבר|חברת|מועצה|שאר|ןגס|רבח|תרבח|הצעומ)', line_cleaned):
                parts = line_cleaned.split(separator, 1)
                if len(parts) == 2:
                    part0 = parts[0].strip()
                    part1 = parts[1].strip()

                    # Check which part is the role
                    # Normal: "ראש העיר", "סגן ראש העיר", "חבר מועצה"
                    # Reversed (character-level): "ריעה שאר", "ריעה שאר ןגס", "הצעומ רבח"
                    # IMPORTANT: RTL text is reversed CHARACTER-by-CHARACTER, not word-by-word!
                    # In reversed text, the role comes BEFORE the dash!
                    is_official_part0 = re.search(
                        r'(ראש\s+העיר|סגן\s+ראש|חבר\s+מועצה|חברת\s+מועצה|'
                        r'ריעה\s+שאר|ריעה\s+שאר\s+ןגס|הצעומ\s+רבח|הצעומ\s+תרבח)',
                        part0, re.IGNORECASE
                    )
                    is_official_part1 = re.search(
                        r'(ראש\s+העיר|סגן\s+ראש|חבר\s+מועצה|חברת\s+מועצה|'
                        r'ריעה\s+שאר|ריעה\s+שאר\s+ןגס|הצעומ\s+רבח|הצעומ\s+תרבח)',
                        part1, re.IGNORECASE
                    )

                    # Determine which part is role and which is name
                    if is_official_part0:
                        # Reversed format: "role - name"
                        role_part = part0
                        name_part = part1
                    elif is_official_part1:
                        # Normal format: "name - role"
                        name_part = part0
                        role_part = part1
                    else:
                        # No match
                        continue

                    is_official = is_official_part0 or is_official_part1
                    if is_official:
                        # Filter out staff positions (not elected council members)
                        # Staff keywords: מנכ"ל, גזבר, יועמ"ש, תובע, מבקר, תקציבן, עוזר ראש, דובר, מנהל
                        staff_keywords = [
                            'מנכ', 'גזבר', 'יועמ', 'תובע', 'מבקר', 'תקציבן',
                            'עוזר ראש', 'עוזרת', 'דובר', 'מנהל', 'מנהלת',
                            'עוזר מנכ', 'מזכיר', 'רכז', 'יו"ר'
                        ]
                        is_staff = any(keyword in role_part for keyword in staff_keywords)

                        if not is_staff:
                            # Clean name - remove titles
                            # Common titles: עו"ד, מר, גב', ד"ר, פרופ'
                            # OCR can produce: עו"ד, עו'ד, עו'"ד, עו"'ד, עו'"ר (misread ד as ר), etc.
                            titles_to_remove = [
                                r'עו["\'"\']+[דר]\s+',  # עו"ד, עו'ד, עו'"ד, עו"'ד, עו'"ר (OCR error), etc.
                                r'מר\s+',
                                r'גב["\']?\s+',
                                r'ד["\'"\']+ר\s+',  # ד"ר, ד'ר, etc. - MUST have at least one quote
                                r'פרופ["\']?\s+',
                                r'רב\s+',
                            ]
                            for title_pattern in titles_to_remove:
                                name_part = re.sub(title_pattern, '', name_part, flags=re.IGNORECASE)

                            # Fix common OCR errors in names BEFORE removing non-Hebrew
                            # "13" is often OCR misread of "בן" (especially "בן ציון")
                            name_part = re.sub(r'\b13\b', 'בן', name_part)
                            # "7" is sometimes OCR misread of other letters
                            name_part = re.sub(r'\b7\b', '', name_part)

                            name_part = re.sub(r'[^א-ת\s\'\"]', '', name_part).strip()
                            name_part = re.sub(r'\s+', ' ', name_part)
                            # Allow names as short as 3 Hebrew letters (e.g., "מאיר" after OCR cleanup)
                            if 3 <= len(name_part) <= 50:
                                # Reverse Hebrew text if needed
                                name_part = reverse_hebrew_text(name_part)
                                # Try to match partial names to full names from database
                                name_part = match_partial_name(name_part)
                                extracted_data['attendances'].append({
                                    'name': name_part,
                                    'status': 'present'
                                })

    # Process absent members (חסרים)
    if absent_section:
        absent_text = absent_section.group(1)
        lines = absent_text.split('\n')
        for line in lines:
            # Clean line from RTL/LTR marks and other non-Hebrew characters at the beginning
            line_cleaned = re.sub(r'^[^\u0590-\u05FF\s\'"]+', '', line.strip())

            # Support both dash (-) and period (.) as separators
            separator = None
            if '-' in line_cleaned:
                separator = '-'
            elif '.' in line_cleaned:
                separator = '.'

            if separator and re.search(r'(ראש|סגן|חבר|חברת|מועצה|שאר|ןגס|רבח|תרבח)', line_cleaned):
                parts = line_cleaned.split(separator, 1)
                if len(parts) == 2:
                    # Try part 0 (normal format: "name - role")
                    name_part = parts[0].strip()
                    role_part = parts[1].strip()

                    # If part 0 looks like a role (contains ראש/סגן/חבר), swap
                    if re.search(r'(ראש|סגן|חבר|חברת|שאר|ןגס|רבח|תרבח)', name_part):
                        name_part, role_part = role_part, name_part

                    # Filter out staff positions
                    staff_keywords = [
                        'מנכ', 'גזבר', 'יועמ', 'תובע', 'מבקר', 'תקציבן',
                        'עוזר ראש', 'עוזרת', 'דובר', 'מנהל', 'מנהלת',
                        'עוזר מנכ', 'מזכיר', 'רכז', 'יו"ר'
                    ]
                    is_staff = any(keyword in role_part for keyword in staff_keywords)

                    if not is_staff:
                        # Clean name - remove titles
                        # OCR can produce: עו"ד, עו'ד, עו'"ד, עו"'ד, etc.
                        titles_to_remove = [
                            r'עו["\'"\']+ד\s+',  # עו"ד, עו'ד, עו'"ד, עו"'ד, etc.
                            r'מר\s+',
                            r'גב["\']?\s+',
                            r'ד["\'"\']+ר\s+',  # ד"ר, ד'ר, etc. - MUST have at least one quote
                            r'פרופ["\']?\s+',
                            r'רב\s+',
                        ]
                        for title_pattern in titles_to_remove:
                            name_part = re.sub(title_pattern, '', name_part, flags=re.IGNORECASE)

                        name_part = re.sub(r'[^א-ת\s\'\"]', '', name_part).strip()
                        name_part = re.sub(r'\s+', ' ', name_part)
                        # Reverse Hebrew text if needed
                        name_part = reverse_hebrew_text(name_part)
                        # Try to match partial names to full names from database
                        name_part = match_partial_name(name_part)
                        # Accept 0-3 words (relaxed for OCR errors), minimum 3 letters
                        if 3 <= len(name_part) <= 50 and name_part.count(' ') in [0, 1, 2, 3]:
                            extracted_data['attendances'].append({
                                'name': name_part,
                                'status': 'absent'
                            })

    # Skip additional officials (נוכחים/סגל) - we only want elected officials
    # The officials_section is not processed to exclude staff members

    # Extract discussions from "על סדר היום" (agenda) section
    # According to protocol structure: Part 2 is the agenda with discussion items
    # This section contains: number, title, explanation (דברי הסבר), budget, funding sources
    debug_print("DEBUG: Extracting discussions from agenda section (על סדר היום)")

    # Search in first 25000 chars where agenda typically appears (can span multiple pages)
    text_beginning = text[:25000]

    # Support both normal "על סדר היום" and reversed "לע םויה רדס" / "םויה רדס לע"
    # Agenda section ends when we reach the PROTOCOL section (actual transcript):
    # - "סעיף מס'" (start of discussion transcript) - this is the REAL end of agenda!
    # - "פרוטוקול" as standalone header (not in page header line)
    # NOTE: Agenda can span multiple pages, so:
    # 1. Remove page break markers and page headers
    # 2. Do NOT stop at empty lines (they can appear between agenda pages)

    # Remove page break markers and their header lines (protocol header repeated on each page)
    text_no_breaks = re.sub(r'---\s*Page\s*\d+\s*\(OCR\)\s*---\n[^\n]*\n[^\n]*מיום[^\n]*\n[^\n]*עמוד[^\n]*\n?', '\n', text_beginning)
    text_no_breaks = re.sub(r'---\s*Page\s*\d+\s*\(OCR\)\s*---\n?', '', text_no_breaks)
    # Collapse multiple newlines to single (page breaks often have extra newlines)
    text_no_breaks = re.sub(r'\n{3,}', '\n\n', text_no_breaks)

    # IMPORTANT: Stop at "סעיף מס'" which marks the beginning of the protocol transcript
    # NOTE: "דברי הסבר" appears WITHIN each agenda item (as explanation), so we should NOT stop there!
    # The agenda section contains numbered items with their full explanations, budget, and sources
    # Example: "1. פתיחת תב"ר... דברי הסבר: ... 2. אישור הסכם..." - both 1 and 2 are main items
    agenda_list_section = re.search(
        r'(?:על\s+סדר\s+היום|לע\s+םויה\s+רדס|םויה\s+רדס\s+לע)[:\s]*(.*?)(?=סעיף\s+מס[\'׳י*]?\s*\d|(?:^|\n)פרוטוקול\s*$|\Z)',
        text_no_breaks,
        re.DOTALL | re.IGNORECASE | re.MULTILINE
    )

    if agenda_list_section:
        agenda_text = agenda_list_section.group(1)
        debug_print(f"DEBUG: Found agenda list section, length: {len(agenda_text)}")

        # Pattern 1: Normal LTR: "1 Title..." or "1. Title..." at line start
        # Matches: "1 כותרת הדיון" or "1. כותרת" or "|1 כותרת" or "1. >כותרת" (OCR artifacts)
        # Must start with number followed by space/dot, then optional OCR artifacts, then Hebrew letter
        # Note: OCR sometimes produces artifacts like ">" or other symbols before Hebrew text
        # EXCLUDE lines containing "ךותמ" (reversed "מתוך") or "דומע" (reversed "עמוד") - these are page numbers
        pattern1 = r'(?:^|\n)[\|\s]*(\d{1,2})\.?\s+[>\|\s]*([א-ת][א-ת\s][^\n]{8,300})'
        disc1_raw = re.findall(pattern1, agenda_text, re.MULTILINE)
        # Filter out page number matches
        disc1 = [(num, content) for num, content in disc1_raw
                 if 'ךותמ' not in content and 'דומע' not in content]

        # Pattern 1b: Unnumbered items starting with ". " or "* " (out-of-agenda items)
        # Matches: ". אישור דוחות כספיים..." or "* סעיף מחוץ לסדר היום"
        # These get assigned number "*" or "0" to indicate out-of-agenda
        pattern1b = r'(?:^|\n)[\|\s]*([.*])\s+([א-ת][א-ת\s][^\n]{8,300})'
        disc1b_raw = re.findall(pattern1b, agenda_text, re.MULTILINE)
        # Convert marker to special number (use "*" for these)
        disc1b = [('*', content) for marker, content in disc1b_raw]
        disc1 = disc1 + disc1b

        # Pattern 2: RTL (reversed): ".content .1" or ",content .7" or ".2018 - content .8"
        # Matches reversed text where number comes after content
        # Can start with any character, must contain Hebrew within first 15 chars, ends with .NUMBER
        pattern2 = r'(?:^|\n)(.{0,15}[א-ת][^\n]{10,300})[\s\.]+(\d{1,2})\s*$'
        disc2_raw = re.findall(pattern2, agenda_text, re.MULTILINE)
        disc2 = [(num, content) for content, num in disc2_raw]

        # Pattern 3: Reversed format ".TITLE.NUMBER" - common OCR output for Hebrew
        # Example: ".ריעה שאר רבד .1" (which is "1. דבר ראש העיר." reversed)
        # Line starts with dot, contains content, ends with .NUMBER
        # Using a more flexible pattern that works with multiline
        pattern3 = r'^\s*\.(.+)\.(\d{1,2})\s*$'
        disc3_raw = re.findall(pattern3, agenda_text, re.MULTILINE)
        # Reverse the content back to proper order (the text is reversed)
        disc3 = [(num, content[::-1].strip()) for content, num in disc3_raw]
        debug_print(f"DEBUG: Pattern3 raw matches (reversed .TITLE.NUM): {len(disc3_raw)}")
        if disc3_raw:
            debug_print(f"DEBUG: First pattern3 raw: num={disc3_raw[0][1]}, content_head={disc3_raw[0][0][:30]}")

        # Pattern 4: Line ending with space .NUMBER (no leading dot required)
        # Example: "תשיתפ ר"בת .4"
        pattern4 = r'^\s*([^\.\n][^\n]{5,300}?)\s+\.(\d{1,2})\s*$'
        disc4_raw = re.findall(pattern4, agenda_text, re.MULTILINE)
        disc4 = [(num, content[::-1].strip()) for content, num in disc4_raw]
        debug_print(f"DEBUG: Pattern4 raw matches (TITLE .NUM): {len(disc4_raw)}")

        # Pattern 5: Normal order ".NUMBER TITLE" (for non-reversed text sections)
        # EXCLUDE lines containing page number indicators
        pattern5 = r'\.(\d{1,2})\s+([א-ת][^\n]{5,200})'
        disc5_raw = re.findall(pattern5, agenda_text, re.MULTILINE)
        disc5 = [(num, content.strip()) for num, content in disc5_raw
                 if 'ךותמ' not in content and 'דומע' not in content and 'מתוך' not in content and 'עמוד' not in content]
        debug_print(f"DEBUG: Pattern5 raw matches (.NUM TITLE): {len(disc5_raw)}")

        debug_print(f"DEBUG: Pattern3 (reversed .TITLE.NUM): {len(disc3)}, Pattern4 (.NUM at end): {len(disc4)}, Pattern5 (.NUM TITLE): {len(disc5)}")

        debug_print(f"DEBUG: Agenda - Normal pattern found {len(disc1)}, Reversed pattern found {len(disc2)}")
        # PRIORITY ORDER: Pattern 3 (reversed .TITLE.NUM) is most accurate for reversed Hebrew text
        # Put it first so its matches are kept when removing duplicates
        discussions = disc3 + disc4 + disc5 + disc1 + disc2
        if disc3:
            debug_print(f"DEBUG: First pattern3 match (reversed): {disc3[0]}")
        if disc4:
            debug_print(f"DEBUG: First pattern4 match: {disc4[0]}")
        if disc1:
            debug_print(f"DEBUG: First normal match: {disc1[0]}")
        if disc2:
            debug_print(f"DEBUG: First reversed match: {disc2[0]}")
    else:
        debug_print("DEBUG: Agenda section NOT found with header, searching for numbered items in first 25000 chars")
        # If no clear agenda header, look for numbered items in beginning of text
        # Pattern 1: Normal LTR - number followed by optional dot, then Hebrew text
        pattern1 = r'(?:^|\n)[\|\s]*(\d{1,2})\.?\s+([א-ת][א-ת\s][^\n]{8,250})'
        disc1 = re.findall(pattern1, text_beginning, re.MULTILINE)

        # Pattern 2: RTL
        pattern2 = r'(?:^|\n)([א-ת][^\n]{10,250})[\s\.]+(\d{1,2})\s*[i|\.]*\s*(?:\n|$)'
        disc2_raw = re.findall(pattern2, text_beginning, re.MULTILINE)
        disc2 = [(num, content) for content, num in disc2_raw]

        debug_print(f"DEBUG: No header - Normal pattern found {len(disc1)}, Reversed pattern found {len(disc2)}")
        discussions = disc1 + disc2

    # Filter out invalid numbers (> 20 are likely page numbers or other noise)
    # Note: "*" is valid as it represents out-of-agenda items
    debug_print(f"DEBUG: Before filtering: {len(discussions)} discussions, numbers: {[num for num, _ in discussions[:10]]}")
    discussions = [(num, content) for num, content in discussions if num == '*' or (num.isdigit() and int(num) <= 20)]
    debug_print(f"DEBUG: After number filter (<=20 or '*'): {len(discussions)} discussions")

    # Additional filter: Remove discussions where the number is just part of regular text
    # Check if this looks like a real agenda item - should have substantive content
    def is_likely_real_discussion(num, content):
        """Check if this is likely a real discussion and not just a page number or random match"""
        content_stripped = content.strip()

        # Filter out page numbers and headers (both normal and reversed)
        # Examples: "עמוד 2 מתוך 87" or "87 ךותמ 2 דומע" (reversed)
        page_patterns = [
            r'^עמוד\s+\d',
            r'^דומע\s+\d',  # Reversed "עמוד"
            r'^\d+\s+ךותמ',  # Reversed "מתוך X"
            r'^\d+\s+מתוך',
            r'^פרוטוקול\s+מועצ',
            r'^לוקוטורפ',  # Reversed "פרוטוקול"
            r'^\d{1,2}/\d{2,4}\s+םוימ',  # Date reversed
            r'^\d{1,2}/\d{1,2}/\d{2,4}',  # Just date
            r'^ןינמה\s+ןמ',  # Reversed "מן המניין"
            r'ךותמ\s+\d+\s+דומע',  # "ךותמ X דומע" - page X of Y (reversed)
            r'עמוד\s+\d+\s+מתוך',  # "עמוד X מתוך" - page X of Y
        ]
        for pat in page_patterns:
            if re.search(pat, content_stripped):  # Changed to search() to find anywhere in content
                return False

        # Known short titles that are always valid (e.g., "דבר ראש העיר" = 14 chars)
        known_short_titles = ['דבר ראש', 'שונות']
        for title in known_short_titles:
            if content_stripped.startswith(title):
                return True

        # If the content is very short, it's probably not a real discussion
        if len(content_stripped) < 15:
            return False

        # If the content looks like it's from the middle of a sentence (starts with lowercase-equivalent or conjunction)
        bad_starts = ['ו', 'אך', 'אבל', 'או', 'כי', 'אשר', 'עמוד', 'עמ', 'דף', 'דומע', 'ךותמ']
        if any(content_stripped.startswith(word) for word in bad_starts):
            return False

        return True

    discussions = [(num, content) for num, content in discussions if is_likely_real_discussion(num, content)]
    debug_print(f"DEBUG: After real discussion filter: {len(discussions)} discussions")

    # Remove duplicate discussion numbers - keep first occurrence (from agenda section)
    # This handles cases where same item appears in both agenda and protocol sections
    seen_numbers = set()
    unique_discussions = []
    for num, content in discussions:
        if num not in seen_numbers:
            seen_numbers.add(num)
            unique_discussions.append((num, content))
    discussions = unique_discussions
    debug_print(f"DEBUG: After removing duplicates: {len(discussions)} discussions")

    # Filter out false positives: content that starts mid-sentence or is invalid
    def is_valid_discussion_title(content):
        """Check if content looks like a valid discussion title"""
        content = content.strip()

        # Special cases - always valid (must start with one of these)
        common_titles = ['דבר ראש', 'שונות', 'אישור', 'בקשה', 'מינוי', 'תב"ר', 'פתיחת', 'דיון',
                        'הצעה', 'עדכון', 'דיווח', 'החלטה', 'מכרז', 'סיכום', 'אישור מועצת',
                        'ריווח', 'הנחת', 'הוספת', 'האצלת', 'קביעת', 'בחירת', 'הקמת']
        for title in common_titles:
            if content.startswith(title):
                return True

        # If doesn't start with common title, it's likely a false positive
        # (text from middle of protocol, not a real agenda item)
        # Check for other valid start patterns
        valid_start_patterns = [
            r'^(?:פתיחת|סגירת|עדכון|מינוי|אישור|החלטה|הצעה)',  # Action verbs
            r'^(?:מצב|נושא|סעיף|דיון)\s+',  # Topic starters
        ]
        for pattern in valid_start_patterns:
            if re.match(pattern, content):
                return True

        # Must have minimum length (but allow short titles if they end with punctuation)
        if len(content) < 8:
            return False

        # Should start with capital Hebrew letter or quotation mark
        first_char = content[0]
        if not (first_char in 'אבגדהוזחטיכלמנסעפצקרשת\"\''):
            return False

        # Should not start with common mid-sentence words or dialogue markers
        # Also filter out attachment indicators (מצ"ל = attached) and other non-title starts
        mid_sentence_words = [
            'של ', 'את ', 'על ', 'עם ', 'אבל ', 'כי ', 'או ', 'אז ',
            'זה ', 'זו ', 'אלה ', 'האלה', 'שהוא', 'שהיא',
            'בגין', 'לגבי', 'מתוך', 'והמליצה', 'עבודה מסודרות',
            'השתתפות במועצה', 'משרות', 'מר ', 'גב ', 'עו"ד ',
            'מנהל ', 'אגרות', 'פעימת', 'לא,', 'כן,',
            'מצ"ל', 'מצורף', 'נספח', 'ניתוח', 'פרוטוקול '
        ]
        for word in mid_sentence_words:
            if content.startswith(word):
                return False

        # Should not be mostly numbers/symbols (like table fragments)
        hebrew_chars = len([c for c in content[:50] if 'א' <= c <= 'ת'])
        if hebrew_chars < 4:  # Need at least 4 Hebrew letters in first 50 chars
            return False

        # Additional check: if it looks like middle of sentence (has comma in first 20 chars)
        if ',' in content[:20]:
            return False

        return True

    # Apply filter
    before_filter = len(discussions)
    discussions = [(num, content) for num, content in discussions if is_valid_discussion_title(content)]
    filtered_out = before_filter - len(discussions)
    if filtered_out > 0:
        debug_print(f"DEBUG: Filtered out {filtered_out} invalid discussion titles")

    # SMART NUMBER CORRECTION: Fix OCR-misread numbers based on chronological order
    # Common OCR errors: 11->1, 12->2, 10->0, 9->0, 8->3, etc.
    def fix_discussion_numbers(discussions):
        """
        Fix OCR-misread numbers based on expected chronological sequence.
        If a number doesn't make sense in sequence, try to guess the correct number.
        """
        if len(discussions) < 2:
            return discussions

        fixed = []

        # Determine starting number from first numbered discussion
        # Skip "*" markers when finding first number
        # (agenda often starts from 2 because "דבר ראש העיר" is item 1 without number)
        first_num = 1  # Default
        for num, _ in discussions:
            if num != '*' and num.isdigit():
                first_num = int(num)
                break

        if first_num <= 3:
            expected_next = first_num  # Start from whatever the first number is
        else:
            expected_next = 1  # Something is wrong, start from 1

        for i, (num, content) in enumerate(discussions):
            # Handle special markers like "*" for out-of-agenda items
            if num == '*':
                fixed.append(('*', content))
                continue

            ocr_num = int(num)

            # Check if this number makes sense in sequence
            # Allow some flexibility: expected, expected+1, or expected+2
            if ocr_num >= expected_next and ocr_num <= expected_next + 2:
                # Number seems reasonable
                fixed.append((str(ocr_num), content))
                expected_next = ocr_num + 1
            else:
                # Number doesn't fit - try to correct it
                corrected_num = ocr_num

                # Common OCR misreads for double-digit numbers:
                # 0 could be 9 or 10
                # 1 could be 11 (if we're past 10)
                # 2 could be 12
                # 3 could be 8 or 13

                if ocr_num == 0:
                    # 0 is often 9 or 10
                    if expected_next == 9:
                        corrected_num = 9
                    elif expected_next == 10:
                        corrected_num = 10
                    else:
                        corrected_num = expected_next  # Best guess

                elif ocr_num == 1 and expected_next >= 10:
                    # 1 could be 11
                    corrected_num = 11

                elif ocr_num == 2 and expected_next >= 10:
                    # 2 could be 12
                    corrected_num = 12

                elif ocr_num == 3 and expected_next == 12:
                    # 3 could be 12 (OCR reads "12" as "3" or similar)
                    corrected_num = 12

                elif ocr_num == 3 and expected_next == 13:
                    # 3 could be 13
                    corrected_num = 13

                elif ocr_num == 3 and expected_next == 8:
                    # 3 could be 8 (OCR confusion)
                    corrected_num = 8

                elif ocr_num < expected_next:
                    # Number is too small - likely a misread of expected number
                    # Priority 1: Check if this is just reading only the last digit (e.g., 12 -> 2)
                    # If expected is 12 and we got 2, use expected
                    if expected_next >= 10 and ocr_num == expected_next % 10:
                        corrected_num = expected_next
                    # Priority 2: Check if adding 10 gives exactly the expected number
                    elif ocr_num + 10 == expected_next:
                        corrected_num = expected_next
                    # Priority 3: Check if adding 10 would be close (within +1)
                    elif ocr_num + 10 == expected_next + 1:
                        corrected_num = ocr_num + 10
                    else:
                        corrected_num = expected_next

                else:
                    # Number is too large - just use expected
                    corrected_num = expected_next

                if corrected_num != ocr_num:
                    debug_print(f"DEBUG: Fixed discussion number {ocr_num} -> {corrected_num} (expected ~{expected_next})")

                fixed.append((str(corrected_num), content))
                expected_next = corrected_num + 1

        return fixed

    # Apply smart number correction
    discussions_before_fix = [(num, content) for num, content in discussions]
    discussions = fix_discussion_numbers(discussions)

    debug_print(f"DEBUG: Found {len(discussions)} discussions from agenda section")

    # Extract the full protocol transcript section for detailed extraction
    # Strategy 1: Look for "פרוטוקול" header
    protocol_section = re.search(
        r'(?:^|\n)(?:פרוטוקול|לוקוטורפ)[^\n]*\n(.*)',
        text,
        re.DOTALL | re.IGNORECASE
    )

    protocol_text = protocol_section.group(1) if protocol_section else ""

    # Strategy 2: If no "פרוטוקול" header or it's in wrong place, find "סעיף מס' 1" directly
    # This handles protocols where "פרוטוקול" appears only as part of attachments (e.g., "פרוטוקול ועדת כספים")
    if not protocol_text or len(protocol_text) < 1000:
        # Look for first discussion marker as start of transcript
        # Note: Some protocols have "סעיף מס* 1" (with asterisk for out-of-agenda items)
        # Also handle OCR artifacts: /Db, /D, Db for מס'
        transcript_start = re.search(r'סעיף\s+(?:מס[\'׳י*]?|/Db|/D|Db)\s*[1*]\s*[-:.]', text)
        if transcript_start:
            protocol_text = text[transcript_start.start():]
            debug_print(f"DEBUG: Protocol section found via סעיף מס marker, length: {len(protocol_text)}")
        else:
            debug_print(f"DEBUG: Protocol transcript section NOT found (no header, no סעיף מס)")
    else:
        debug_print(f"DEBUG: Protocol transcript section length: {len(protocol_text)}")

    # HYBRID FALLBACK: If agenda extraction found very few items (< 3), try protocol transcript section as fallback
    # This handles cases where agenda section is missing or poorly formatted
    if len(discussions) < 3:
        debug_print(f"DEBUG: Agenda found only {len(discussions)} items, trying fallback to protocol transcript section")

        # Find the פרוטוקול header that marks the start of discussion transcript section
        protocol_section = re.search(
            r'(?:^|\n)(?:פרוטוקול|לוקוטורפ)[^\n]*\n(.*)',
            text,
            re.DOTALL | re.IGNORECASE
        )

        if protocol_section:
            protocol_text = protocol_section.group(1)
            debug_print(f"DEBUG: Found פרוטוקול transcript section, length: {len(protocol_text)}")

            # Search for discussion markers: "סעיף מס' X:" (normal or reversed)
            # Try NORMAL pattern first (content AFTER marker)
            normal_pattern = r'(?:[סצמ][עצ]י[ףפ]|סעיף|סציף|מעיף)\s+(?:מס[יׂ\'*]*|מספר)\s+(\d{1,2})\s*[-:.]\s*([^\n]+(?:\n(?!(?:[סצמ][עצ]י[ףפ]|סעיף)\s+(?:מס[יׂ\'*]*|מספר))[^\n]+){0,5})'
            discussions_normal = re.findall(normal_pattern, protocol_text, re.MULTILINE | re.IGNORECASE)

            # Try REVERSED pattern (content BEFORE marker)
            reversed_pattern = r'([^\n]{10,200})\s*[-:.]\s*(\d{1,2})\s+[\'*]*סמ\s+(?:ףיעס|ףיצס|ףעיס)'
            discussions_reversed_raw = re.findall(reversed_pattern, protocol_text, re.MULTILINE | re.IGNORECASE)
            discussions_reversed = [(num, content) for content, num in discussions_reversed_raw]

            # Combine both
            discussions_transcript = discussions_normal + discussions_reversed
            debug_print(f"DEBUG: Transcript - Normal pattern found {len(discussions_normal)}, Reversed pattern found {len(discussions_reversed)}")

            # Clean up transcript discussions
            cleaned_transcript = []
            for match in discussions_transcript:
                num = match[0]
                content = match[1]
                content_clean = content.strip()
                content_clean = re.sub(r'\s+', ' ', content_clean)
                if len(content_clean) > 200:
                    content_clean = content_clean[:200]
                cleaned_transcript.append((num, content_clean))

            # If transcript found more discussions than agenda, use transcript instead
            if len(cleaned_transcript) > len(discussions):
                debug_print(f"DEBUG: Using transcript ({len(cleaned_transcript)} items) instead of agenda ({len(discussions)} items)")
                discussions = cleaned_transcript
            else:
                debug_print(f"DEBUG: Keeping agenda results ({len(discussions)} items), transcript only found {len(cleaned_transcript)}")
        else:
            debug_print("DEBUG: פרוטוקול transcript section NOT found")

    # Process discussions with sequential index (to handle duplicate numbering)
    for idx, (disc_num_original, disc_content) in enumerate(discussions[:30], start=1):
        # Use sequential index as discussion number (1, 2, 3, ...)
        # disc_num_original is the number from PDF (may have duplicates like 1-9, then 1-5)
        disc_num = str(idx)

        # Reverse Hebrew content if needed
        disc_content_fixed = reverse_hebrew_text(disc_content)
        # Fix reversed numbers in content (e.g., "000,052" → "250,000")
        disc_content_fixed = fix_reversed_numbers(disc_content_fixed)

        # Extract title (first line or first 80 chars of content)
        disc_title = disc_content_fixed.split('\n')[0].strip()[:100] if disc_content_fixed else ''
        # Clean up title - remove trailing periods, colons, etc.
        disc_title = re.sub(r'[:\.\s]+$', '', disc_title)

        discussion_data = {
            'number': disc_num,
            'title': disc_title,
            'content': disc_content_fixed[:1000].strip()
        }

        # STEP 1: Try to find full text in AGENDA section (contains budget & sources)
        # Extract extended agenda text for this specific discussion by NUMBER
        agenda_item_text = ""
        if agenda_list_section:
            agenda_full = agenda_list_section.group(1)

            # Strategy: Find the section for this specific discussion number
            # Patterns handle both normal and REVERSED Hebrew OCR:
            # Normal: "1. פתיחת תב"ר" or "סעיף 1: פתיחת"
            # Reversed: line ENDS with ".N" like "פתיחת תב"ר - חידוש גג .1"

            # Try to find section by number
            disc_num_str = str(disc_num).replace('*', '')
            next_num = int(disc_num_str) + 1 if disc_num_str.isdigit() else None

            # Pattern 1: Normal format "N. title" or "סעיף N"
            # Pattern 2: Reversed format - line ENDS with ".N"
            agenda_section_patterns = []
            if next_num:
                # Pattern for reversed format: from line ending with ".N" to line ending with ".M"
                # Uses MULTILINE to match $ at end of line
                # IMPORTANT: Stop BEFORE the line with ".M" (next item header)
                agenda_section_patterns.append(
                    rf'\.{disc_num_str}\s*$\n(.*?)(?=^[^\n]+\.{next_num}\s*$|\Z)'
                )
                # Pattern for normal format
                agenda_section_patterns.append(
                    rf'(?:סעיף\s+)?{disc_num_str}\.?\s*[-:.]?\s*(.*?)(?=(?:סעיף\s+)?{next_num}\.?\s*[-:.]|\Z)'
                )
            else:
                # Last item - from ".N" to end
                agenda_section_patterns.append(rf'\.{disc_num_str}\s*$\n(.*)')
                agenda_section_patterns.append(rf'(?:סעיף\s+)?{disc_num_str}\.?\s*[-:.]?\s*(.*)')

            for pattern in agenda_section_patterns:
                match = re.search(pattern, agenda_full, re.DOTALL | re.IGNORECASE | re.MULTILINE)
                if match:
                    agenda_item_text = match.group(1).strip()
                    if len(agenda_item_text) > 20:
                        debug_print(f"DEBUG: Discussion {disc_num} - found agenda text by number pattern, length: {len(agenda_item_text)}")
                        break

            # Fallback: try position-based (original method)
            if not agenda_item_text:
                all_agenda_items = re.split(r'(?:^|\n)[\|\s]*(?:\d{1,2}|[.*])\.?\s+(?=[א-ת])', agenda_full, flags=re.MULTILINE)
                all_agenda_items = [item.strip() for item in all_agenda_items if item.strip() and len(item.strip()) > 10]
                if idx <= len(all_agenda_items):
                    agenda_item_text = all_agenda_items[idx - 1]
                    debug_print(f"DEBUG: Discussion {disc_num} - found agenda text by position (fallback), length: {len(agenda_item_text)}")

            if not agenda_item_text:
                debug_print(f"DEBUG: Discussion {disc_num} - NO agenda text found")

        # STEP 2: Try to find full text in PROTOCOL transcript section (contains decisions & votes)
        # IMPORTANT: OCR often misreads numbers AND protocol may discuss items out of order
        # Strategy: Search by NUMBER first in transcript section, then by title keywords as fallback
        disc_full_text = ""
        if protocol_text and disc_content:
            # Find where the actual discussions start (after the agenda list)
            # The transcript section starts with "סעיף מס' 1" or "סעיף מסי 1" or "סעיף מס* 1" (OCR artifacts)
            # Also handles /Db, /D, Db as OCR artifacts for מס'
            # REVERSED format: "1 'סמ ףיעס" or "1 'םס ףיעס"
            transcript_start_patterns = [
                r'סעיף\s+(?:מס[\'׳י*]?|/Db|/D|Db)\s*[1*]\s*[-:.]',  # Normal: סעיף מס' 1
                r'[1*]\s*[\'\u05f3]\s*(?:סמ|םס)\s+ףיעס',            # Reversed: 1 'סמ ףיעס
            ]
            transcript_text = protocol_text
            for start_pattern in transcript_start_patterns:
                transcript_start_match = re.search(start_pattern, protocol_text)
                if transcript_start_match:
                    transcript_text = protocol_text[transcript_start_match.start():]
                    break

            # Strategy 1: Try by number patterns FIRST (most reliable in transcript)
            # Try sequential number first, then OCR-read number
            numbers_to_try = [str(idx)]
            if disc_num_original != str(idx):
                numbers_to_try.append(disc_num_original)

            for try_num in numbers_to_try:
                # Escape special regex characters in try_num (e.g., "*")
                try_num_escaped = re.escape(try_num)

                disc_marker_patterns = [
                    # Pattern 1: "סעיף מס' X" or "סעיף מסי X" or "סעיף מס* X" (OCR errors: ' → י or ' → *)
                    # Also includes OCR artifacts: /Db, /D, Db for מס'
                    # NOTE: Do NOT stop at "--- Page" - discussions can span multiple pages!
                    rf'סעיף\s+(?:מס[\'׳י*]?|/Db|/D|Db)[\s\u200e\u200f]*{try_num_escaped}\s*[-:.]\s*(.+?)(?=סעיף\s+(?:מס[\'׳י*]?|/Db|/D|Db)\s*\d|\Z)',
                    # Pattern 2: Just "סעיף X" (without מס')
                    rf'(?:[סצמ][עצ]י[ףפ]|סעיף)\s+{try_num_escaped}\s*[-:.](.+?)(?=(?:[סצמ][עצ]י[ףפ]|סעיף)\s+\d{{1,2}}|$)',
                    # Pattern 3: REVERSED "X 'סמ ףיעס" - number BEFORE סמ ףיעס
                    # Example: "2 'סמ ףיעס" (reversed סעיף מס' 2)
                    rf'{try_num_escaped}\s*[\'\u05f3]\s*(?:סמ|םס)\s+ףיעס\s*[-:.]?\s*(.+?)(?=\d{{1,2}}\s*[\'\u05f3]\s*(?:סמ|םס)\s+ףיעס|\Z)',
                ]

                for pattern_idx, pattern in enumerate(disc_marker_patterns):
                    match = re.search(pattern, transcript_text, re.DOTALL | re.IGNORECASE)
                    if match:
                        disc_full_text = match.group(1)
                        debug_print(f"DEBUG: Discussion {disc_num} (original #{disc_num_original}) - found protocol text using number {try_num}, pattern {pattern_idx+1}, length: {len(disc_full_text)}")
                        break

                if disc_full_text:
                    break

            # Strategy 2: If number search failed, try by title keywords
            # This handles cases where agenda numbering differs from protocol numbering
            # (e.g., agenda has items 1,2,3 but protocol starts with "סעיף מס' 1" for item 2)
            if not disc_full_text:
                # Extract significant Hebrew words from title (skip common words)
                title_words = re.findall(r'[\u0590-\u05FF]+', disc_content)
                # Filter out common words that appear in many titles
                stop_words = {'אישור', 'מועצת', 'העיר', 'להרכב', 'ועדת', 'חובה', 'רשות', 'ועדה', 'לשנת', 'בשנת'}
                significant_words = [w for w in title_words if w not in stop_words and len(w) > 2]

                # Try to find a unique signature from the title IN THE TRANSCRIPT SECTION
                if significant_words:
                    for num_words in [2, 1, 3]:
                        if len(significant_words) >= num_words:
                            search_words = significant_words[:num_words]
                            title_pattern = r'.*?'.join(re.escape(w) for w in search_words)
                            # Search in transcript_text (not protocol_text) to avoid matching agenda
                            # Look for the title followed by discussion content until next סעיף or end
                            title_search = rf'{title_pattern}(.{{50,5000}}?)(?=סעיף\s+מס[\'׳י*]?\s*\d|הצבעה:|$)'
                            match = re.search(title_search, transcript_text, re.DOTALL | re.IGNORECASE)
                            if match:
                                disc_full_text = match.group(1)
                                debug_print(f"DEBUG: Discussion {disc_num} - found protocol text using title keywords: {search_words}, length: {len(disc_full_text)}")
                                break

                # Strategy 3: If title keywords also failed, try scanning ALL סעיף markers
                # and matching by title similarity (handles agenda/protocol number mismatch)
                if not disc_full_text and significant_words:
                    # Find all discussion sections in transcript (both normal and reversed)
                    all_sections = re.findall(
                        r'סעיף\s+מס[\'׳י*]?\s*(\d+)\s*[-:.]\s*([^\n]+)(.*?)(?=סעיף\s+מס[\'׳י*]?\s*\d|\Z)',
                        transcript_text, re.DOTALL | re.IGNORECASE
                    )
                    # Also try reversed pattern
                    reversed_sections = re.findall(
                        r'(\d+)\s*[\'\u05f3]\s*(?:סמ|םס)\s+ףיעס\s*[-:.]?\s*([^\n]+)(.*?)(?=\d+\s*[\'\u05f3]\s*(?:סמ|םס)\s+ףיעס|\Z)',
                        transcript_text, re.DOTALL | re.IGNORECASE
                    )
                    all_sections = all_sections + reversed_sections

                    best_match = None
                    best_score = 0

                    for section_num, section_title, section_content in all_sections:
                        # Calculate how many significant words appear in section title
                        section_title_lower = section_title.lower()
                        matching_words = sum(1 for w in significant_words[:3] if w in section_title_lower)

                        if matching_words > best_score:
                            best_score = matching_words
                            best_match = (section_num, section_title, section_content)

                    if best_match and best_score >= 1:
                        disc_full_text = best_match[1] + best_match[2]
                        debug_print(f"DEBUG: Discussion {disc_num} - found via title similarity scan (סעיף {best_match[0]}), score: {best_score}, length: {len(disc_full_text)}")

            if not disc_full_text:
                debug_print(f"DEBUG: Discussion {disc_num} (original #{disc_num_original}) - NO protocol text found")

        # STEP 3: Combine all available text: agenda item + protocol discussion
        # Use agenda for budget/sources, protocol for decisions/votes, title as fallback
        search_text_budget = agenda_item_text if agenda_item_text else disc_content
        search_text_decision = disc_full_text if disc_full_text else disc_content
        search_text_combined = (agenda_item_text + "\n" + disc_full_text) if (agenda_item_text and disc_full_text) else (disc_full_text or agenda_item_text or disc_content)

        # Extract decision (from protocol transcript preferably)
        # NOTE: OCR text often has reversed word order (RTL read as LTR)
        # So "החלטה: מועצת העיר מאשרת" appears as "תרשאמ ריעה תצעומ :הטלחה"
        decision_patterns = [
            # Pattern 0: "ירד מסדר היום" / "הורד מסדר היום" / "נדחה" (removed from agenda)
            r'(?:ירד|הורד|נדחה)\s+(?:מ)?סדר\s+(?:ה)?יום',
            # Pattern 1: "מועצת העיר מאשרת ברוב קולות" (table format - majority vote)
            # IMPROVED: Allow multi-line capture until next section marker (סעיף, הצבעה, ---)
            r'(?:מועצת\s+העיר|ריעה\s+תצעומ)\s+(?:מאשרת|מחליטה|תרשאמ|הטילחמ)\s+ברוב\s+קולות\s+(.+?)(?=\n\s*\n\s*\n|סעיף\s+מס|הצבעה\s*:|---\s+Page|$)',
            # Pattern 2: "מועצת העיר מאשרת/מחליטה" (table format - direct decision, common in protocols)
            # IMPROVED: Capture full paragraph (allow multiple lines, stop at double newline or section)
            r'(?:מועצת\s+העיר|ריעה\s+תצעומ)\s+(?:מאשרת|מחליטה|אושר|תרשאמ|הטילחמ|רשוא)\s+(.+?)(?=\n\s*\n\s*\n|סעיף\s+מס|הצבעה\s*:|---\s+Page|$)',
            # Pattern 3: "החלטה: ..." (most common) - normal order
            # IMPROVED: Capture full decision paragraph (until double blank line, next סעיף, or הצבעה:)
            r'החלטה[:\s]+(.+?)(?=\n\s*\n\s*\n|סעיף\s+מס|הצבעה\s*:|---\s+Page|$)',
            # Pattern 3b: REVERSED - "...תרשאמ ריעה תצעומ :הטלחה" - decision text BEFORE "החלטה:"
            r'((?:תרשאמ|הטילחמ|תכרבמ)\s+ריעה\s+תצעומ[^:]*):הטלחה',
            # Pattern 4: "הוחלט/החליטה"
            # IMPROVED: Capture full paragraph
            r'(?:החליט[הו]?|הוחלט)[:\s]+(.+?)(?=\n\s*\n\s*\n|סעיף\s+מס|מי\s+בעד|הצבעה\s*:|$)',
            # Pattern 5: "הצעת החלטה"
            # IMPROVED: Capture full paragraph
            r'(?:הצעת\s+)?(?:החלטה)[:\s]+(?:מועצת\s+העיר\s+)?(.+?)(?=\n\s*\n\s*\n|סעיף\s+מס|הצבעה\s*:|---\s+Page|$)',
            # Pattern 6: REVERSED - decision ending with ":הטלחה" (capture whole line before it)
            r'^([^\n]*(?:דחא\s+הפ|תולוק\s+בורב)[^\n]*):הטלחה',
        ]
        decision_found = False
        for pattern_idx, pattern in enumerate(decision_patterns):
            # For "removed from agenda" pattern (pattern 0), search in combined text (agenda + protocol)
            # For other patterns, search in protocol text preferably
            search_text = search_text_combined if pattern_idx == 0 else search_text_decision
            # Pattern 7 (index 7) needs MULTILINE for ^ anchor
            flags = re.DOTALL | re.IGNORECASE | (re.MULTILINE if pattern_idx == 7 else 0)
            match = re.search(pattern, search_text, flags)
            if match:
                # Pattern 0 (removed from agenda) doesn't have a capture group
                if pattern_idx == 0:
                    decision_text = match.group(0).strip()
                # Pattern 1 (majority vote) - mark as majority vote type
                elif pattern_idx == 1:
                    decision_text = match.group(1).strip()
                    discussion_data['vote_type'] = 'majority'
                    debug_print(f"DEBUG: Discussion {disc_num} - Found majority vote decision")
                # Patterns 4 and 7 are REVERSED patterns - need to reverse the captured text
                elif pattern_idx in [4, 7]:
                    decision_text = match.group(1).strip()
                    # Reverse the text and normalize final letters
                    decision_text = reverse_hebrew_text(decision_text)
                    debug_print(f"DEBUG: Discussion {disc_num} - Found REVERSED decision pattern {pattern_idx}")
                    # Check for unanimous vote marker in reversed text
                    if 'פה אחד' in decision_text or 'דחא הפ' in match.group(0):
                        discussion_data['vote_type'] = 'unanimous'
                else:
                    decision_text = match.group(1).strip()
                # Clean up decision text
                decision_text = re.sub(r'\s+', ' ', decision_text)
                discussion_data['decision'] = decision_text[:500]
                decision_found = True
                debug_print(f"DEBUG: Discussion {disc_num} - Decision found with pattern {pattern_idx}: {decision_text[:100]}...")
                break

        # LLM fallback for decision extraction
        if not decision_found and OLLAMA_AVAILABLE and search_text_decision and len(search_text_decision) > 100:
            debug_print(f"DEBUG: Discussion {disc_num} - Decision regex failed, trying LLM fallback")
            llm_decision = extract_decision_with_llm(search_text_decision[:2000], disc_num)
            if llm_decision:
                discussion_data['decision'] = llm_decision[:500]
                debug_print(f"DEBUG: Discussion {disc_num} - LLM extracted decision: {llm_decision[:100]}...")
                decision_found = True

        # If decision found contains "מאשרת" or "אושר", extract the short decision
        # But also keep the full decision text separately (decision_statement = נוסח ההחלטה)
        if decision_found and discussion_data.get('decision'):
            decision_text = discussion_data['decision']
            # If it starts with a verb like "מאשרת", "מחליטה", "אושר" - it's likely the full decision text
            # Save the full text and extract just the status
            if re.match(r'(?:מאשרת|מחליטה|מועצת\s+העיר\s+מאשרת|אושר|נדחה)', decision_text, re.IGNORECASE):
                # Save full decision text as decision_statement (נוסח ההחלטה)
                discussion_data['decision_statement'] = decision_text

                # Check if unanimous or majority vote - set categorical decision status
                if discussion_data.get('vote_type') == 'unanimous':
                    discussion_data['decision'] = 'אושר פה אחד'
                elif discussion_data.get('vote_type') == 'majority':
                    discussion_data['decision'] = 'אושר'
                elif 'נדחה' in decision_text or 'דחה' in decision_text:
                    discussion_data['decision'] = 'נדחה'
                elif 'מאשרת' in decision_text:
                    discussion_data['decision'] = 'אושר'
                else:
                    # Keep as "מאשרת" or similar
                    discussion_data['decision'] = decision_text
            else:
                # Even if no standard pattern, keep the full text as decision_statement
                discussion_data['decision_statement'] = decision_text

        # Inferred decision logic (if no explicit decision was found)
        if not decision_found:
            # Special case: "דבר ראש העיר" is always "דיווח ועדכון"
            if 'דבר ראש' in disc_content.lower() or 'רבד שאר' in disc_content.lower():
                discussion_data['decision'] = 'דיווח ועדכון'
                discussion_data['decision_inferred'] = True
                debug_print(f"DEBUG: Discussion {disc_num} - Inferred: דיווח ועדכון (דבר ראש העיר)")
            # Case 1: Discussion in agenda but NOT in protocol → "ירד מסדר היום"
            elif agenda_item_text and not disc_full_text:
                discussion_data['decision'] = 'ירד מסדר היום'
                discussion_data['decision_inferred'] = True
                debug_print(f"DEBUG: Discussion {disc_num} - Inferred: ירד מסדר היום (no protocol)")
            # Case 2: Discussion in protocol but no decision/vote → "דיווח ועדכון"
            elif disc_full_text and not discussion_data.get('vote_type'):
                discussion_data['decision'] = 'דיווח ועדכון'
                discussion_data['decision_inferred'] = True
                debug_print(f"DEBUG: Discussion {disc_num} - Inferred: דיווח ועדכון (no vote)")

        # Extract expert opinion / explanation (דברי הסבר) - search in agenda preferably
        expert_opinion_found = False
        expert_opinion_patterns = [
            r'(?:דברי\s+הסבר|רבסה\s+ירבד)[:\s]+(.*?)(?=\n\s*\n|תקציב|תב["\']ר|מקורות\s+מימון|$)',
            r'(?:הסבר|רבסה)[:\s]+(.*?)(?=\n\s*\n|תקציב|תב["\']ר|$)',
        ]
        for pattern in expert_opinion_patterns:
            match = re.search(pattern, search_text_budget, re.DOTALL | re.IGNORECASE)
            if match:
                expert_text = match.group(1).strip()
                # Clean and limit to 5-6 lines (approx 400-500 chars)
                expert_lines = expert_text.split('\n')
                expert_text = '\n'.join(expert_lines[:6])
                expert_text = re.sub(r'\s+', ' ', expert_text)
                expert_text = reverse_hebrew_text(expert_text)
                expert_text = fix_reversed_numbers(expert_text)  # Fix reversed numbers like 000,012 -> 210,000
                discussion_data['expert_opinion'] = expert_text[:500]
                expert_opinion_found = True
                debug_print(f"DEBUG: Discussion {disc_num} - Extracted expert opinion: {len(expert_text)} chars")
                break

        # Fallback: If no "דברי הסבר" found in agenda, take first 4-5 lines from protocol discussion
        if not expert_opinion_found and disc_full_text:
            # Take first 4-5 lines from the beginning of the discussion protocol
            lines = disc_full_text.split('\n')
            # Filter out empty lines and take first 4-5 substantial lines
            substantial_lines = [line.strip() for line in lines if line.strip() and len(line.strip()) > 20]
            if substantial_lines:
                expert_text = ' '.join(substantial_lines[:5])
                expert_text = re.sub(r'\s+', ' ', expert_text)
                expert_text = reverse_hebrew_text(expert_text)
                expert_text = fix_reversed_numbers(expert_text)  # Fix reversed numbers like 000,012 -> 210,000
                discussion_data['expert_opinion'] = expert_text[:500]
                debug_print(f"DEBUG: Discussion {disc_num} - Using protocol start as expert opinion (fallback): {len(expert_text)} chars")
                expert_opinion_found = True

        # Extract budget (תב"ר) - search in agenda first, then disc_content, then protocol
        budget_patterns = [
            r'(?:תב["\']ר|ר"בת)[:\s]*([0-9,\.]+)\s*(?:₪|שקל|ש"ח|מש"ח)',
            r'(?:תב["\']ר|ר"בת)\s+(?:בגובה|בסך)\s+([0-9,\.]+)\s*(?:₪|שקל|ש"ח|מש"ח|מ"ש)',  # "תב"ר בגובה/בסך X מ"ש"
            r'סך\s+(?:התב["\']ר|הסכום)[:\s]*([0-9,\.]+)\s*(?:₪|שקל|ש"ח|מש"ח)',
            r'תקציב[:\s]*([0-9,\.]+)\s*(?:₪|שקל|ש"ח|מש"ח)',
        ]
        budget_found = False
        # Try searching in: 1) agenda text, 2) discussion title, 3) combined text
        budget_search_texts = [search_text_budget, disc_content, search_text_combined]
        for search_text in budget_search_texts:
            if budget_found or not search_text:
                continue
            # Apply fix for reversed numbers in budget context BEFORE pattern matching
            search_text_fixed = fix_reversed_numbers(search_text)
            for pattern in budget_patterns:
                match = re.search(pattern, search_text_fixed, re.IGNORECASE)
                if match:
                    budget_str = match.group(1).replace(',', '')
                    # Check if this is a "מ"ש" (million shekels) pattern
                    if 'מ"ש' in match.group(0) or 'מש"ח' in match.group(0):
                        # Convert millions to actual value: "7.2 מ"ש" -> 7200000
                        try:
                            budget_value = float(budget_str) * 1000000
                            discussion_data['budget'] = budget_value
                            budget_found = True
                            debug_print(f"DEBUG: Discussion {disc_num} - Converted {budget_str} מ\"ש to {budget_value}")
                        except ValueError:
                            pass
                    else:
                        # Regular budget value
                        budget_str = budget_str.replace('.', '')
                        try:
                            discussion_data['budget'] = float(budget_str)
                            budget_found = True
                        except ValueError:
                            pass
                    break
            if budget_found:
                break

        # LLM fallback for budget extraction - DISABLED due to too many false positives
        # if not budget_found and OLLAMA_AVAILABLE and search_text_budget and len(search_text_budget) > 100:
        #     debug_print(f"DEBUG: Discussion {disc_num} - Budget regex failed, trying LLM fallback")
        #     llm_budget = extract_budget_with_llm(search_text_budget[:2000], disc_num)
        #     if llm_budget:
        #         discussion_data['budget'] = llm_budget
        #         debug_print(f"DEBUG: Discussion {disc_num} - LLM extracted budget: {llm_budget}")

        # Extract budget sources (מקורות מימון) - search in agenda preferably
        budget_sources = []

        # First, reverse the Hebrew text and fix numbers (OCR often gives reversed text)
        search_text_for_sources = search_text_budget or ''
        search_text_for_sources_reversed = reverse_hebrew_text(search_text_for_sources)
        search_text_for_sources_fixed = fix_reversed_numbers(search_text_for_sources_reversed)

        # Try both original (reversed) and fixed text
        texts_to_search = [search_text_for_sources_fixed, search_text_for_sources]

        for search_txt in texts_to_search:
            if budget_sources:  # Already found, skip
                break
            if not search_txt:
                continue

            # Search patterns for finding the sources section
            sources_patterns = [
                # Normal Hebrew: "מקורות מימון:"
                r'(?:מקורות?\s+מימון)[:\s-]+(.*?)(?=\n\s*\n|דברי\s+הסבר|סעיף\s+מס|רבסה\s+ירבד|$)',
                # Reversed Hebrew: "ןומימ תורוקמ"
                r'(?:ןומימ\s+תורוקמ|ןומימ\s+רוקמ)[:\s-]+(.*?)(?=\n\s*\n|$)',
            ]

            for sources_pattern in sources_patterns:
                sources_section = re.search(sources_pattern, search_txt, re.DOTALL | re.IGNORECASE)
                if sources_section:
                    sources_text = sources_section.group(1)
                    # Fix numbers in extracted sources text
                    sources_text = fix_reversed_numbers(sources_text)

                    # Multiple patterns for individual funding sources
                    source_item_patterns = [
                        # Pattern 1: "משרד החינוך ע"ס 300,000 ₪" or with dash
                        r'((?:משרד|הרשאת|קרנות|עירי)[א-ת\s\'\"״׳]+?)\s*(?:ע"ס|ס"ע|-)\s*([0-9,\.]+)\s*(?:₪|ש"ח|ח"ש|שקל)?',
                        # Pattern 2: "קרנות הרשות 200,000"
                        r'(קרנות\s+[א-ת]+)\s+([0-9,\.]+)',
                        # Pattern 3: Generic "source_name - amount"
                        r'([א-ת][א-ת\s\'\"״׳]+?)\s*[-:]\s*([0-9,\.]+)\s*(?:₪|ש"ח|ח"ש|שקל)?',
                        # Pattern 4: "source_name amount ₪" (no separator)
                        r'([א-ת]{2,}[א-ת\s\'\"״׳]*?)\s+([0-9,]+)\s*(?:₪|ש"ח)',
                    ]

                    for source_pattern in source_item_patterns:
                        for source_match in re.finditer(source_pattern, sources_text):
                            source_name = source_match.group(1).strip()
                            # Reverse source name if it appears to be reversed
                            source_name = reverse_hebrew_text(source_name)
                            # Clean up source name
                            source_name = re.sub(r'^[-:\s]+|[-:\s]+$', '', source_name)

                            amount_str = source_match.group(2).replace(',', '').replace('.', '')
                            try:
                                amount = float(amount_str)
                                if amount > 0 and source_name and len(source_name) > 2:
                                    # Avoid duplicates
                                    if not any(bs['source'] == source_name for bs in budget_sources):
                                        budget_sources.append({'source': source_name, 'amount': amount})
                                        debug_print(f"DEBUG: Discussion {disc_num} - Found budget source: {source_name} = {amount}")
                            except ValueError:
                                pass

                    if budget_sources:
                        break  # Found sources, exit pattern loop

        if budget_sources:
            discussion_data['budget_sources'] = budget_sources

        # Extract votes (from protocol transcript preferably)
        # PRIORITY ORDER:
        # 1. Look for explicit roll-call votes first (בעד- X, נגד- Y) - most reliable
        # 2. Look for "ברוב קולות" (majority vote)
        # 3. Look for "הצבעה: פה אחד" or "פה אחד" near decision context
        # Note: "פה אחד" can appear casually in discussion text, so only trust it near vote context
        vote_found = False
        combined_vote_text = search_text_decision + "\n" + discussion_data.get('decision', '')

        # FIRST (PRIORITY): Check for "הצבעה: פה אחד" pattern (normal or reversed)
        # This is very reliable and should be checked first
        direct_unanimous_patterns = [
            r'העבצה\s*:\s*\.?דחא\s+הפ',   # Reversed: הצבעה: פה אחד. or העבצה: .דחא הפ
            r'\.דחא\s+הפ\s*:\s*העבצה',   # Reversed with period at start
            r'הצבעה\s*:\s*פה\s+אחד',      # Normal: הצבעה: פה אחד
        ]
        for pattern in direct_unanimous_patterns:
            if re.search(pattern, combined_vote_text, re.IGNORECASE):
                discussion_data['vote_type'] = 'unanimous'
                vote_found = True
                debug_print(f"DEBUG: Discussion {disc_num} - Found direct unanimous vote pattern")
                break

        # SECOND: Check for explicit vote counts (בעד- 12, נגד- 2) or (בעד - 12, נגד - 2)
        # This is the most reliable indicator for non-unanimous votes
        # Support both "בעד-" and "בעד -" (with optional space before dash)
        if not vote_found:
            explicit_vote_pattern = r'בעד\s*-\s*(\d+)\s+.*?נגד\s*-\s*(\d+)'
            explicit_match = re.search(explicit_vote_pattern, combined_vote_text, re.IGNORECASE | re.DOTALL)
            if explicit_match:
                discussion_data['yes_votes'] = int(explicit_match.group(1))
                discussion_data['no_votes'] = int(explicit_match.group(2))
                discussion_data['vote_type'] = 'majority'
                vote_found = True
                debug_print(f"DEBUG: Discussion {disc_num} - Found explicit vote: {discussion_data['yes_votes']} for, {discussion_data['no_votes']} against")

        # THIRD: Check for "ברוב קולות" (majority vote marker)
        # Also check reversed: "תולוק בורב"
        if not vote_found:
            majority_patterns = [r'ברוב\s+קולות', r'תולוק\s+בורב']
            for pattern in majority_patterns:
                if re.search(pattern, combined_vote_text, re.IGNORECASE):
                    # Only set majority if not already set (from decision pattern)
                    if 'vote_type' not in discussion_data:
                        discussion_data['vote_type'] = 'majority'
                        vote_found = True
                        debug_print(f"DEBUG: Discussion {disc_num} - Found majority vote (pattern: {pattern})")
                    break

        # FOURTH: Look for roll-call vote with numbers: "בעד: 11, נגד: 0, נמנעו: 1"
        # Also support: "בעד - 10", "נגד - 2", "נמנע - 1" (with dash separator)
        # Also support reversed RTL: "דעב", "דגנ", "ועננמ"
        if not vote_found:
            vote_patterns = {
                'yes': [r'בעד\s*[-:]\s*(\d+)', r'בעד[:\s]+(\d+)', r'בזכות[:\s]*(\d+)', r'דעב[:\s]*(\d+)', r'תוכזב[:\s]*(\d+)'],
                'no': [r'נגד\s*[-:]\s*(\d+)', r'נגד[:\s]+(\d+)', r'דגנ[:\s]*(\d+)'],
                'avoid': [r'נמנע[ו]?\s*[-:]\s*(\d+)', r'נמנע[ו]?[:\s]+(\d+)', r'ועננמ[:\s]*(\d+)', r'ענמנ[:\s]*(\d+)'],
            }

            for vote_cat, patterns in vote_patterns.items():
                for pattern in patterns:
                    match = re.search(pattern, search_text_decision, re.IGNORECASE)
                    if match:
                        discussion_data[f'{vote_cat}_votes'] = int(match.group(1))
                        vote_found = True
                        break

        # FIFTH: Look for name lists: "בעד: שמואל, יוסי, ..." or "נמנע: הדר"
        # Count names after each vote category
        if not vote_found or 'yes_votes' not in discussion_data:
            # Try to find name lists
            yes_names_match = re.search(r'(?:בעד|דעב)[:\s]+([^.]+?)(?=\.|נגד|נמנע|$)', search_text_decision, re.IGNORECASE)
            if yes_names_match:
                yes_text = yes_names_match.group(1)
                # Count names (separated by commas or "ו")
                names = re.split(r'[,ו]\s*', yes_text)
                # Filter out empty or very short strings
                valid_names = [n for n in names if len(n.strip()) > 2]
                if valid_names and len(valid_names) <= 20:  # Sanity check
                    discussion_data['yes_votes'] = len(valid_names)
                    vote_found = True
                    debug_print(f"DEBUG: Discussion {disc_num} - Counted {len(valid_names)} yes votes from name list")

            avoid_names_match = re.search(r'(?:נמנע[ו]?|ועננמ)[:\s]+([^.]+?)(?=\.|$)', search_text_decision, re.IGNORECASE)
            if avoid_names_match:
                avoid_text = avoid_names_match.group(1)
                names = re.split(r'[,ו]\s*', avoid_text)
                valid_names = [n for n in names if len(n.strip()) > 2]
                if valid_names and len(valid_names) <= 20:
                    discussion_data['avoid_votes'] = len(valid_names)
                    vote_found = True
                    debug_print(f"DEBUG: Discussion {disc_num} - Counted {len(valid_names)} avoid votes from name list")

        # SIXTH (LAST): Check for "פה אחד" (unanimous) - only near actual vote context
        # This is last because "פה אחד" can appear casually in discussion text
        if not vote_found:
            # More strict pattern: only match near "הצבעה" or at end of decision text
            # Also check REVERSED patterns: "דחא הפ :העבצה" (הצבעה: פה אחד reversed)
            unanimous_patterns = [
                r'הצבעה[:\s]+פה\s+אחד',          # Normal: הצבעה: פה אחד
                r'מאשרת\s+פה\s+אחד',             # Normal: מאשרת פה אחד
                r'אושר\s+פה\s+אחד',              # Normal: אושר פה אחד
                r'דחא\s+הפ[:\s]*העבצה',          # Reversed: .דחא הפ :העבצה
                r'דחא\s+הפ\s+(?:תרשאמ|הטילחמ|תכרבמ)',  # Reversed: דחא הפ תרשאמ (מאשרת פה אחד)
                r'\.דחא\s+הפ',                    # Reversed with period: .דחא הפ
            ]
            for pattern in unanimous_patterns:
                if re.search(pattern, combined_vote_text, re.IGNORECASE):
                    discussion_data['vote_type'] = 'unanimous'
                    vote_found = True
                    debug_print(f"DEBUG: Discussion {disc_num} - Found unanimous vote (pattern: {pattern[:20]}...)")
                    break

        # LLM fallback for vote extraction
        if not vote_found and OLLAMA_AVAILABLE and search_text_decision and len(search_text_decision) > 100:
            debug_print(f"DEBUG: Discussion {disc_num} - Vote regex failed, trying LLM fallback")
            llm_vote = extract_vote_with_llm(search_text_decision[:2000], disc_num)
            if llm_vote:
                vote_type = llm_vote.get('type')
                if vote_type == 'unanimous':
                    discussion_data['vote_type'] = 'unanimous'
                    debug_print(f"DEBUG: Discussion {disc_num} - LLM extracted unanimous vote")
                elif vote_type == 'roll_call':
                    if 'yes' in llm_vote:
                        discussion_data['yes_votes'] = llm_vote['yes']
                    if 'no' in llm_vote:
                        discussion_data['no_votes'] = llm_vote['no']
                    if 'avoid' in llm_vote:
                        discussion_data['avoid_votes'] = llm_vote['avoid']
                    debug_print(f"DEBUG: Discussion {disc_num} - LLM extracted roll-call vote: {llm_vote}")

        # Generate AI summary using LLM from expert_opinion + discussion text
        if OLLAMA_AVAILABLE and generate_discussion_summary:
            expert_opinion = discussion_data.get('expert_opinion', '')
            if expert_opinion or disc_full_text:
                debug_print(f"DEBUG: Discussion {disc_num} - Generating LLM summary")
                summary_result = generate_discussion_summary(
                    expert_opinion=expert_opinion,
                    discussion_text=disc_full_text or '',
                    title=disc_content_fixed[:200] if disc_content_fixed else None
                )
                if summary_result and summary_result.get('summary'):
                    discussion_data['summary'] = summary_result['summary']
                    discussion_data['summary_confidence'] = summary_result.get('confidence', 0)
                    discussion_data['summary_llm_generated'] = summary_result.get('llm_generated', False)
                    debug_print(f"DEBUG: Discussion {disc_num} - LLM summary generated: {len(summary_result['summary'])} chars, confidence: {summary_result.get('confidence', 0)}")

        # Check if this is a committee protocol approval discussion
        # If so, try to extract sub-discussions (individual votes within)
        if is_committee_protocol_approval(disc_content_fixed):
            debug_print(f"DEBUG: Discussion {disc_num} (original #{disc_num_original}) - Detected committee protocol approval, searching for sub-discussions")

            # For committee protocol approvals, we need to find the FULL section text
            # The disc_full_text may have been found using the wrong number
            # Try to find section by the ORIGINAL number from PDF (e.g., 13)
            committee_section_text = disc_full_text
            if protocol_text and disc_num_original != disc_num:
                # Try to find with original number (escape special chars like "*")
                disc_num_orig_escaped = re.escape(disc_num_original)
                orig_pattern = rf'סעיף\s+מס[\'׳י*]?\s*{disc_num_orig_escaped}\s*[-:.]\s*(.+?)(?=סעיף\s+מס[\'׳י*]?\s*\d|\Z)'
                orig_match = re.search(orig_pattern, protocol_text, re.DOTALL | re.IGNORECASE)
                if orig_match:
                    orig_section = orig_match.group(1)
                    if len(orig_section) > len(committee_section_text or ''):
                        committee_section_text = orig_section
                        debug_print(f"DEBUG: Discussion {disc_num} - Found larger section using original number {disc_num_original}: {len(committee_section_text)} chars")

            if not committee_section_text:
                debug_print(f"DEBUG: Discussion {disc_num} - No section text found for committee protocol")
                extracted_data['discussions'].append(discussion_data)
                continue

            sub_discussions = extract_sub_discussions(disc_num, committee_section_text)

            if sub_discussions:
                debug_print(f"DEBUG: Discussion {disc_num} - Found {len(sub_discussions)} sub-discussions")
                # Add parent discussion as a "header" with no votes
                parent_data = {
                    'number': disc_num,
                    'content': disc_content_fixed[:1000].strip(),
                    'decision': 'סעיף מטא - ראה תתי סעיפים',
                    'is_parent': True
                }
                extracted_data['discussions'].append(parent_data)

                # Add each sub-discussion
                for sub_disc in sub_discussions:
                    # Add parent title context to sub-discussion
                    sub_disc['parent_title'] = disc_content_fixed[:200].strip()
                    extracted_data['discussions'].append(sub_disc)
            else:
                # No sub-discussions found, add as regular discussion
                debug_print(f"DEBUG: Discussion {disc_num} - No sub-discussions found, adding as regular")
                extracted_data['discussions'].append(discussion_data)
        else:
            extracted_data['discussions'].append(discussion_data)

    # Extract staff with roles
    staff_list = extract_staff_with_roles(text)
    extracted_data['staff'] = staff_list
    debug_print(f"DEBUG: Extracted {len(staff_list)} staff members")

    # Post-processing: Set vote counts for unanimous decisions based on attendance
    # Count present council members (status == 'present')
    present_count = sum(1 for a in extracted_data.get('attendances', []) if a.get('status') == 'present')
    debug_print(f"DEBUG: Present count for unanimous votes: {present_count}")

    if present_count > 0:
        for discussion in extracted_data.get('discussions', []):
            if discussion.get('vote_type') == 'unanimous':
                # Only set if not already set
                if discussion.get('yes_votes') is None:
                    discussion['yes_votes'] = present_count
                    discussion['no_votes'] = 0
                    discussion['avoid_votes'] = 0
                    debug_print(f"DEBUG: Discussion {discussion.get('number')} - Set unanimous votes to {present_count}")

    # זיהוי והחלת הצבעות מקובצות
    grouped_vote_info = detect_grouped_vote(text)
    if grouped_vote_info and grouped_vote_info.get('count', 0) > 0:
        debug_print(f"DEBUG: Found {grouped_vote_info['count']} grouped vote patterns")
        for group in grouped_vote_info.get('grouped_items', []):
            debug_print(f"DEBUG: Grouped items: {group['items']}")

        # החלת ההצבעה המקובצת על הסעיפים
        extracted_data['discussions'] = apply_grouped_vote(
            extracted_data['discussions'],
            grouped_vote_info,
            text
        )
        extracted_data['grouped_votes'] = grouped_vote_info

    return extracted_data

def compare_with_database(extracted_data, meeting_id):
    """Compare extracted data with database"""
    session = get_session()

    comparison = {
        'meeting_id': meeting_id,
        'matches': [],
        'discrepancies': [],
        'missing_in_db': [],
        'missing_in_pdf': []
    }

    meeting = session.query(Meeting).filter(Meeting.id == meeting_id).first()

    if not meeting:
        comparison['discrepancies'].append(f"Meeting ID {meeting_id} not found")
        session.close()
        return comparison, extracted_data

    # Compare meeting number
    if extracted_data['meeting_info'].get('meeting_no'):
        pdf_no = extracted_data['meeting_info']['meeting_no']
        db_no = meeting.meeting_no

        if pdf_no == db_no or pdf_no.replace('/', '') == db_no:
            comparison['matches'].append(f"Meeting number: {pdf_no}")
        else:
            comparison['discrepancies'].append(f"Meeting number: PDF={pdf_no}, DB={db_no}")

    # Compare attendance
    db_attendances = session.query(Attendance).filter(Attendance.meeting_id == meeting_id).all()
    db_present = [att.person.full_name for att in db_attendances if att.is_present and att.person]
    db_absent = [att.person.full_name for att in db_attendances if not att.is_present and att.person]

    pdf_present_count = len([a for a in extracted_data['attendances'] if a['status'] == 'present'])
    pdf_absent_count = len([a for a in extracted_data['attendances'] if a['status'] == 'absent'])

    comparison['attendance'] = {
        'pdf': {'present': pdf_present_count, 'absent': pdf_absent_count},
        'db': {'present': len(db_present), 'absent': len(db_absent)}
    }

    if pdf_present_count == len(db_present):
        comparison['matches'].append(f"Present count: {pdf_present_count}")
    else:
        comparison['discrepancies'].append(f"Present: PDF={pdf_present_count}, DB={len(db_present)}")

    # Compare discussions
    db_discussions = session.query(Discussion).filter(Discussion.meeting_id == meeting_id).all()

    comparison['discussions'] = {
        'pdf_count': len(extracted_data['discussions']),
        'db_count': len(db_discussions)
    }

    if len(extracted_data['discussions']) == len(db_discussions):
        comparison['matches'].append(f"Discussion count: {len(db_discussions)}")
    else:
        comparison['discrepancies'].append(f"Discussions: PDF={len(extracted_data['discussions'])}, DB={len(db_discussions)}")

    session.close()
    return comparison, extracted_data

def print_report(comparison, extracted_data):
    """Print comparison report"""
    print("\n" + "=" * 100)
    print(f"PROTOCOL OCR EXTRACTION REPORT - Meeting ID {comparison['meeting_id']}")
    print("=" * 100)

    print("\n### EXTRACTED FROM PDF (OCR) ###")
    print(f"Meeting No: {extracted_data['meeting_info'].get('meeting_no', 'Not found')}")
    print(f"Date: {extracted_data['meeting_info'].get('date_str', 'Not found')}")
    print(f"Title: {extracted_data['meeting_info'].get('title', 'Not found')[:80]}")

    if 'attendance' in comparison:
        att = comparison['attendance']
        print(f"\nAttendance (OCR): {att['pdf']['present']} present, {att['pdf']['absent']} absent")
        print(f"Attendance (DB):  {att['db']['present']} present, {att['db']['absent']} absent")

    if 'discussions' in comparison:
        disc = comparison['discussions']
        print(f"\nDiscussions (OCR): {disc['pdf_count']}")
        print(f"Discussions (DB):  {disc['db_count']}")

    print("\n### COMPARISON RESULTS ###")

    if comparison['matches']:
        print(f"\n[OK] MATCHES ({len(comparison['matches'])}):")
        for match in comparison['matches']:
            print(f"  + {match}")

    if comparison['discrepancies']:
        print(f"\n[!] DISCREPANCIES ({len(comparison['discrepancies'])}):")
        for disc in comparison['discrepancies']:
            print(f"  - {disc}")

    print("\n" + "=" * 100)

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python ocr_protocol.py <pdf_path> <meeting_id>")
        print("Example: python ocr_protocol.py 8-15.pdf 30")
        sys.exit(1)

    pdf_path = sys.argv[1]
    meeting_id = int(sys.argv[2])

    print(f"\n{'='*100}")
    print(f"Starting OCR extraction: {pdf_path}")
    print(f"{'='*100}\n")

    # Step 1: Extract text with OCR
    text = extract_text_from_pdf(pdf_path, lang='heb+eng')

    # Save raw OCR text
    text_file = f"ocr_output_{meeting_id}.txt"
    with open(text_file, 'w', encoding='utf-8') as f:
        f.write(text)
    print(f"Raw OCR text saved to: {text_file}")

    # Step 2: Parse text
    print("\nParsing extracted text...")
    extracted_data = parse_protocol_text(text)

    # Step 3: Compare with DB
    print("\nComparing with database...")
    comparison, extracted_data = compare_with_database(extracted_data, meeting_id)

    # Step 4: Print report
    print_report(comparison, extracted_data)

    # Save results
    output_file = f"protocol_ocr_analysis_{meeting_id}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'extracted': extracted_data,
            'comparison': comparison
        }, f, ensure_ascii=False, indent=2, default=str)

    print(f"\nDetailed results saved to: {output_file}")
