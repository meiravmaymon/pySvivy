"""
LLM Helper for OCR fallback using Ollama (local LLM)

This module provides functions to extract information from protocol text
using a local LLM (Ollama) when regex patterns fail.

Also includes:
- Category inference for discussions
- Discussion type classification
- Named vote matching
- Summary generation
- Change logging for learning
"""
import requests
import json
import re
import os
from datetime import datetime
from difflib import SequenceMatcher


# Ollama configuration
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "gemma3:1b"  # Using available model (qwen2.5:7b recommended for Hebrew)
OLLAMA_TIMEOUT = 30  # seconds

# Known categories for municipal discussions (יהוד-מונוסון)
KNOWN_CATEGORIES = [
    "תקציב וכספים",
    "תשתיות ופיתוח",
    "חינוך",
    "תרבות ופנאי",
    "רווחה ושירותים חברתיים",
    "בריאות",
    "בטיחות וביטחון",
    "תכנון ובניה",
    "איכות הסביבה",
    "ספורט ונוער",
    "שונות",
    "דיווח ועדכון",
    "מינויים וכח אדם",
    "משפטי"
]

# Known discussion types
KNOWN_DISCUSSION_TYPES = [
    "אישור תקציב/תב\"ר",
    "מינוי/בחירה",
    "דיווח",
    "עדכון מדיניות",
    "אישור הסכם",
    "אישור פרוטוקול",
    "הצגת תכנית",
    "דיון ציבורי",
    "שונות"
]

# Decision status options
DECISION_STATUSES = [
    "אושר",
    "לא אושר",
    "ירד מסדר היום",
    "לא התקבלה החלטה",
    "דיווח ועדכון",
    "הופנה לוועדה",
    "נדחה לדיון נוסף"
]

# Known staff roles (סגל)
KNOWN_STAFF_ROLES = [
    "מנכ\"ל",
    "גזבר",
    "יועמ\"ש",
    "מבקר העירייה",
    "מהנדס העיר",
    "מנהל אגף",
    "דובר",
    "מזכיר העירייה",
    "עוזר ראש העיר",
    "יועץ משפטי"
]

# Log file path
CHANGE_LOG_PATH = os.path.join(os.path.dirname(__file__), "ocr_changes_log.json")


def check_ollama_available():
    """Check if Ollama is running and the model is available"""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get('models', [])
            model_names = [m.get('name', '') for m in models]
            if OLLAMA_MODEL in model_names or OLLAMA_MODEL.split(':')[0] in [m.split(':')[0] for m in model_names]:
                return True
            else:
                print(f"Warning: Ollama is running but model '{OLLAMA_MODEL}' not found.")
                print(f"Available models: {', '.join(model_names)}")
                print(f"Install with: ollama pull {OLLAMA_MODEL}")
                return False
        return False
    except requests.exceptions.RequestException:
        return False


def extract_with_llm(text_segment, segment_type='decision', disc_num=None):
    """
    Use Ollama LLM to extract information when regex fails

    Args:
        text_segment: The text to analyze (max 2000 chars recommended)
        segment_type: Type of extraction ('decision', 'budget', 'vote')
        disc_num: Discussion number (for context)

    Returns:
        Extracted information or None if failed
    """
    if not text_segment or len(text_segment.strip()) < 20:
        return None

    # Truncate very long segments
    if len(text_segment) > 3000:
        text_segment = text_segment[:3000] + "..."

    # Build prompt based on segment type
    prompts = {
        'decision': """אתה עוזר לחילוץ מידע מפרוטוקולי ישיבות מועצת עיר בעברית.

טקסט מסעיף בפרוטוקול:
{text}

משימה: חלץ את ההחלטה שהתקבלה בסעיף זה.

הנחיות:
- חפש ביטויים כמו: "הוחלט", "החליטה", "מאשרת", "מאשר", "אושר"
- החזר רק את טקסט ההחלטה עצמה, ללא הקדמות
- אם אין החלטה ברורה, החזר: NONE
- אל תוסיף הסברים או פרשנויות

תשובה:""",

        'budget': """אתה עוזר לחילוץ מידע מפרוטוקולי ישיבות מועצת עיר בעברית.

טקסט מסעיף בפרוטוקול:
{text}

משימה: חלץ את סכום התקציב (תב"ר) המוזכר בסעיף.

הנחיות:
- חפש ביטויים כמו: "תב\"ר", "תקציב", "סך של", "בסך"
- החזר רק את המספר בשקלים (לדוגמה: 500000 או 1100000)
- אם הסכום במיליונים (למשל "7.2 מיליון"), המר לשקלים (7200000)
- אל תכלול פסיקים, נקודות או סימני מטבע
- אם אין תקציב, החזר: NONE

דוגמאות:
- "תב\"ר בסך 1,100,000 ₪" → 1100000
- "תקציב של 7.2 מיליון שקל" → 7200000
- "500 אלף ₪" → 500000

תשובה (מספר בלבד):""",

        'vote': """אתה עוזר לחילוץ מידע מפרוטוקולי ישיבות מועצת עיר בעברית.

טקסט מסעיף בפרוטוקול:
{text}

משימה: חלץ את תוצאות ההצבעה.

הנחיות:
- אם יש "פה אחד", החזר: {{"type": "unanimous"}}
- אם יש הצבעה שמית עם מספרים (בעד, נגד, נמנעו), החזר JSON עם המספרים
- אם אין הצבעה, החזר: {{"type": "NONE"}}

דוגמאות:
- "ההחלטה התקבלה פה אחד" → {{"type": "unanimous"}}
- "בעד: 11, נגד: 2, נמנעו: 1" → {{"type": "roll_call", "yes": 11, "no": 2, "avoid": 1}}
- "אין הצבעה בסעיף זה" → {{"type": "NONE"}}

תשובה (JSON בלבד):"""
    }

    prompt_template = prompts.get(segment_type, prompts['decision'])
    prompt = prompt_template.format(text=text_segment)

    # Call Ollama API
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,  # Low temperature for consistent extraction
                    "top_p": 0.9,
                    "num_predict": 200,  # Limit output length
                }
            },
            timeout=OLLAMA_TIMEOUT
        )

        if response.status_code == 200:
            result = response.json()
            answer = result.get('response', '').strip()

            # Handle NONE responses
            if answer.upper() == 'NONE' or not answer:
                return None

            # For vote type, try to parse JSON
            if segment_type == 'vote':
                try:
                    # Extract JSON from response (might have extra text)
                    json_match = re.search(r'\{.*\}', answer, re.DOTALL)
                    if json_match:
                        vote_data = json.loads(json_match.group())
                        if vote_data.get('type') == 'NONE':
                            return None
                        return vote_data
                    return None
                except (json.JSONDecodeError, AttributeError):
                    return None

            # For budget, try to convert to float
            if segment_type == 'budget':
                try:
                    # Clean answer - remove any Hebrew text, punctuation
                    cleaned = re.sub(r'[א-ת\s,\.₪]', '', answer)
                    # Extract first number
                    number_match = re.search(r'\d+', cleaned)
                    if number_match:
                        return float(number_match.group())
                    return None
                except (ValueError, AttributeError):
                    return None

            # For decision, return as is
            return answer

        else:
            print(f"DEBUG: Ollama API returned status {response.status_code}")
            return None

    except requests.exceptions.Timeout:
        print(f"DEBUG: Ollama timeout after {OLLAMA_TIMEOUT}s")
        return None
    except requests.exceptions.RequestException as e:
        print(f"DEBUG: Ollama connection error: {e}")
        return None
    except Exception as e:
        print(f"DEBUG: Unexpected error in LLM extraction: {e}")
        return None


def extract_decision_with_llm(discussion_text, disc_num=None):
    """Extract decision using LLM"""
    return extract_with_llm(discussion_text, segment_type='decision', disc_num=disc_num)


def extract_budget_with_llm(discussion_text, disc_num=None):
    """Extract budget using LLM"""
    return extract_with_llm(discussion_text, segment_type='budget', disc_num=disc_num)


def extract_vote_with_llm(discussion_text, disc_num=None):
    """Extract vote using LLM"""
    return extract_with_llm(discussion_text, segment_type='vote', disc_num=disc_num)


# ==============================================================================
# NEW FUNCTIONS: Category inference, discussion type, summaries, named votes
# ==============================================================================

def categorize_discussion(title, content=None):
    """
    Use LLM to suggest a category for a discussion.
    Returns a dict with 'suggested' category and 'confidence' score.
    """
    text = title
    if content:
        text += "\n" + content[:500]

    categories_list = "\n".join([f"- {cat}" for cat in KNOWN_CATEGORIES])

    prompt = f"""אתה מסווג סעיפי דיון בישיבות מועצת עיר.

סעיף הדיון:
{text}

קטגוריות אפשריות:
{categories_list}

הנחיות:
- בחר את הקטגוריה המתאימה ביותר מהרשימה
- החזר JSON בפורמט: {{"category": "שם הקטגוריה", "confidence": 0.8}}
- confidence בין 0 ל-1 (עד כמה אתה בטוח)
- אם לא ברור, השתמש ב"שונות"

תשובה (JSON בלבד):"""

    if not OLLAMA_AVAILABLE:
        # Fallback: simple keyword matching
        return _categorize_by_keywords(title)

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 100}
            },
            timeout=OLLAMA_TIMEOUT
        )

        if response.status_code == 200:
            answer = response.json().get('response', '').strip()
            json_match = re.search(r'\{.*\}', answer, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                return {
                    'suggested': result.get('category', 'שונות'),
                    'confidence': float(result.get('confidence', 0.5))
                }
    except Exception as e:
        print(f"DEBUG: categorize_discussion error: {e}")

    return _categorize_by_keywords(title)


def _categorize_by_keywords(title):
    """Fallback categorization by keywords"""
    title_lower = title.lower() if title else ''

    keyword_map = {
        'תקציב וכספים': ['תב"ר', 'תקציב', 'כספי', 'תקצוב', 'מימון', 'אגרות'],
        'חינוך': ['חינוך', 'בית ספר', 'גן', 'תלמיד', 'מורה', 'לימוד'],
        'תרבות ופנאי': ['תרבות', 'ספרייה', 'מוזיאון', 'אומנות', 'פנאי', 'אירוע'],
        'תשתיות ופיתוח': ['תשתית', 'כביש', 'מים', 'ביוב', 'פיתוח', 'בנייה', 'שיקום'],
        'רווחה ושירותים חברתיים': ['רווחה', 'חברתי', 'סיוע', 'קשיש', 'נכה'],
        'בריאות': ['בריאות', 'רפואי', 'מרפאה', 'חולה'],
        'ספורט ונוער': ['ספורט', 'נוער', 'התעמלות', 'אצטדיון', 'מגרש'],
        'מינויים וכח אדם': ['מינוי', 'בחירת', 'העסקה', 'משרה', 'נציג'],
        'דיווח ועדכון': ['דיווח', 'עדכון', 'דבר ראש'],
        'תכנון ובניה': ['תכנון', 'בניה', 'תב"ע', 'היתר'],
    }

    for category, keywords in keyword_map.items():
        if any(kw in title_lower for kw in keywords):
            return {'suggested': category, 'confidence': 0.7}

    return {'suggested': 'שונות', 'confidence': 0.3}


def classify_discussion_type(title, content=None):
    """
    Use LLM to suggest a discussion type.
    Returns a dict with 'suggested' type and 'confidence' score.
    """
    text = title
    if content:
        text += "\n" + content[:500]

    types_list = "\n".join([f"- {t}" for t in KNOWN_DISCUSSION_TYPES])

    prompt = f"""אתה מסווג את סוג הדיון בישיבות מועצת עיר.

סעיף הדיון:
{text}

סוגי דיון אפשריים:
{types_list}

הנחיות:
- בחר את הסוג המתאים ביותר מהרשימה
- החזר JSON בפורמט: {{"type": "סוג הדיון", "confidence": 0.8}}
- confidence בין 0 ל-1

תשובה (JSON בלבד):"""

    if not OLLAMA_AVAILABLE:
        return _classify_type_by_keywords(title)

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 100}
            },
            timeout=OLLAMA_TIMEOUT
        )

        if response.status_code == 200:
            answer = response.json().get('response', '').strip()
            json_match = re.search(r'\{.*\}', answer, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                    return {
                        'suggested': result.get('type', 'שונות'),
                        'confidence': float(result.get('confidence', 0.5))
                    }
                except json.JSONDecodeError:
                    # נסה לחלץ את הטקסט ישירות
                    type_match = re.search(r'"type"\s*:\s*"([^"]+)"', answer)
                    if type_match:
                        return {'suggested': type_match.group(1), 'confidence': 0.5}
    except Exception as e:
        pass  # נפול ל-fallback

    return _classify_type_by_keywords(title)


def _classify_type_by_keywords(title):
    """Fallback type classification by keywords"""
    title_lower = title.lower() if title else ''

    if 'תב"ר' in title_lower or 'תקציב' in title_lower:
        return {'suggested': 'אישור תקציב/תב"ר', 'confidence': 0.8}
    if 'מינוי' in title_lower or 'בחירת' in title_lower:
        return {'suggested': 'מינוי/בחירה', 'confidence': 0.8}
    if 'דיווח' in title_lower or 'דבר ראש' in title_lower:
        return {'suggested': 'דיווח', 'confidence': 0.8}
    if 'הסכם' in title_lower:
        return {'suggested': 'אישור הסכם', 'confidence': 0.8}
    if 'פרוטוקול' in title_lower:
        return {'suggested': 'אישור פרוטוקול', 'confidence': 0.8}

    return {'suggested': 'שונות', 'confidence': 0.3}


def summarize_discussion(full_text, max_length=150):
    """
    Use LLM to generate a brief summary of a discussion.
    Summarizes content up to the decision or start of next item.
    Does NOT include the final decision/vote results.
    Returns the summary text or None.
    """
    if not full_text or len(full_text) < 50:
        return None

    text = full_text[:3000]

    # Find where the decision/next item starts and cut there
    # These mark the END of the discussion content we want to summarize
    decision_markers = [
        'החלטה:',
        'החלטה -',
        'הוחלט:',
        'הוחלט -',
        'מועצת העיר מחליטה',
        'מועצת העיר מאשרת',
        'סעיף',  # Start of next item (סעיף 2, סעיף 3, etc.)
    ]

    cut_point = len(text)
    for marker in decision_markers:
        # For "סעיף" we need to check it's followed by a number (next item)
        if marker == 'סעיף':
            import re
            next_item = re.search(r'סעיף\s+\d', text[100:])  # Skip first 100 chars (current item title)
            if next_item:
                pos = next_item.start() + 100
                if pos < cut_point:
                    cut_point = pos
        else:
            pos = text.find(marker)
            if pos > 50 and pos < cut_point:  # Must be after at least 50 chars
                cut_point = pos

    text_to_summarize = text[:cut_point].strip()
    if len(text_to_summarize) < 30:
        text_to_summarize = text[:500]  # Fallback

    prompt = f"""אתה מסכם דיונים מישיבות מועצת עיר בעברית.

טקסט הדיון (עד ההחלטה):
{text_to_summarize}

משימה: כתוב סיכום קצר של הנושא שנדון (עד {max_length} תווים).

הנחיות:
- התמקד בנושא הדיון, ההצעה שהוגשה, והנקודות העיקריות שעלו
- אל תכלול את ההחלטה הסופית או תוצאות ההצבעה
- כתוב בעברית, בגוף שלישי
- היה תמציתי וברור

סיכום:"""

    if not OLLAMA_AVAILABLE:
        return None

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 200}
            },
            timeout=OLLAMA_TIMEOUT
        )

        if response.status_code == 200:
            summary = response.json().get('response', '').strip()
            if summary and len(summary) > 10:
                return summary[:max_length * 2]  # Allow some buffer
    except Exception as e:
        print(f"DEBUG: summarize_discussion error: {e}")

    return None


def generate_discussion_summary(expert_opinion, discussion_text, title=None, max_length=300):
    """
    Generate a comprehensive summary from explanation (דברי הסבר) and discussion text.

    This creates a two-part summary:
    1. Summary of the explanation/background (דברי הסבר)
    2. Key points raised by council members during discussion

    Args:
        expert_opinion: The explanation text (דברי הסבר) from agenda
        discussion_text: The full discussion text from protocol
        title: Discussion title for context
        max_length: Maximum length of summary

    Returns:
        dict with 'summary', 'confidence', 'sources' or None if failed
    """
    if not expert_opinion and not discussion_text:
        return None

    # Build context
    context_parts = []
    if title:
        context_parts.append(f"כותרת הסעיף: {title}")
    if expert_opinion:
        context_parts.append(f"דברי הסבר:\n{expert_opinion[:1500]}")
    if discussion_text:
        context_parts.append(f"הדיון בפרוטוקול:\n{discussion_text[:2000]}")

    full_context = "\n\n".join(context_parts)

    prompt = f"""אתה מסכם דיונים מישיבות מועצת עיר יהוד-מונוסון בעברית.

{full_context}

משימה: כתוב תקציר מובנה הכולל שני חלקים:

1. **רקע והסבר**: סיכום קצר של הנושא והרקע (מדברי ההסבר)
2. **נקודות מהדיון**: אם עלו נקודות מהותיות בדיון - ציין אותן בקצרה

הנחיות:
- כתוב בעברית תקנית וברורה
- היה תמציתי - עד {max_length} תווים בסה"כ
- אל תציין את ההחלטה הסופית או תוצאות ההצבעה
- אם לא היה דיון מהותי, ציין רק את הרקע
- השתמש בסגנון ניטרלי ועובדתי

תקציר:"""

    if not OLLAMA_AVAILABLE:
        # Fallback: just use first part of expert opinion
        if expert_opinion:
            return {
                'summary': expert_opinion[:max_length],
                'confidence': 0.3,
                'sources': ['expert_opinion_only'],
                'llm_generated': False
            }
        return None

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 400}
            },
            timeout=OLLAMA_TIMEOUT * 2  # Allow more time for longer response
        )

        if response.status_code == 200:
            summary = response.json().get('response', '').strip()
            if summary and len(summary) > 20:
                sources = []
                if expert_opinion:
                    sources.append('expert_opinion')
                if discussion_text:
                    sources.append('discussion_text')

                return {
                    'summary': summary[:max_length * 2],
                    'confidence': 0.8 if len(sources) == 2 else 0.6,
                    'sources': sources,
                    'llm_generated': True
                }
    except Exception as e:
        print(f"DEBUG: generate_discussion_summary error: {e}")

    # Fallback
    if expert_opinion:
        return {
            'summary': expert_opinion[:max_length],
            'confidence': 0.3,
            'sources': ['expert_opinion_only'],
            'llm_generated': False
        }

    return None


# ==============================================================================
# ADMINISTRATIVE CATEGORY CLASSIFICATION - סיווג מנהלתי לסעיפים
# ==============================================================================

# Keywords for each category (matching init_admin_categories.py)
ADMIN_CATEGORY_KEYWORDS = {
    # תקציב ומימון
    'BUDGET_ANNUAL': ['תקציב שנתי', 'תקציב רגיל', 'אישור התקציב', 'תקציב העירייה'],
    'BUDGET_TABAR': ['תב"ר', 'תקציב בלתי רגיל', 'פרויקט', 'פיתוח'],
    'BUDGET_RESERVE': ['תקציב מילואים', 'תוספת תקציב', 'תקציב נוסף'],
    'BUDGET_TRANSFER': ['העברה תקציבית', 'העברת כספים', 'שינוי תקציב'],

    # חוזים והתקשרויות
    'CONTRACT_APPROVAL': ['חוזה', 'אישור חוזה', 'הסכם', 'התקשרות'],
    'CONTRACT_TENDER': ['מכרז', 'פטור ממכרז', 'ועדת מכרזים', 'תוצאות מכרז', 'זוכה במכרז'],
    'CONTRACT_EXCEPTION': ['התקשרות חריגה', 'ניגוד עניינים', 'קרוב משפחה'],

    # מינויים
    'APPOINT_AUDITOR': ['מינוי מבקר', 'מבקר פנימי', 'מבקר העירייה'],
    'APPOINT_TREASURER': ['מינוי גזבר', 'גזבר העירייה', 'גזבר'],
    'APPOINT_SENIOR': ['מינוי מנהל', 'עובד בכיר', 'מנכ"ל'],
    'APPOINT_COMMITTEE': ['מינוי לוועדה', 'חבר ועדה', 'נציג בוועדה', 'מינוי חבר'],
    'APPOINT_BOARD': ['דירקטוריון', 'נציג בחברה', 'תאגיד עירוני'],

    # חוקי עזר
    'BYLAW_NEW': ['חוק עזר', 'תקנה חדשה'],
    'BYLAW_AMENDMENT': ['תיקון חוק עזר', 'עדכון תקנות', 'שינוי חוק'],
    'BYLAW_FEE': ['אגרה', 'היטל', 'ארנונה', 'תעריף', 'קנס', 'היטל השבחה'],

    # נכסים ומקרקעין
    'PROPERTY_SALE': ['מכירת נכס', 'מכירת מגרש', 'מכירת מקרקעין'],
    'PROPERTY_PURCHASE': ['רכישת נכס', 'הפקעה', 'רכישת קרקע', 'רכישה'],
    'PROPERTY_LEASE': ['חכירה', 'השכרה', 'השכרת נכס', 'הקצאת קרקע'],
    'PROPERTY_ENCUMBRANCE': ['שעבוד', 'משכנתא'],

    # הלוואות
    'LOAN_TAKE': ['הלוואה', 'אשראי', 'לקיחת הלוואה'],
    'LOAN_GUARANTEE': ['ערבות', 'ערבות עירונית'],
    'LOAN_INVESTMENT': ['השקעה', 'פיקדון'],

    # תאגידים
    'CORP_ESTABLISH': ['הקמת חברה', 'הקמת תאגיד', 'חברה עירונית'],
    'CORP_CHANGE': ['שינוי תקנון', 'שינוי הרכב', 'חברה עירונית'],
    'CORP_DISSOLVE': ['פירוק', 'סגירת חברה'],

    # תכנון
    'PLAN_MASTER': ['תכנית מתאר', 'מתאר עירוני'],
    'PLAN_DETAIL': ['תב"ע', 'תכנית בניין עיר', 'תכנית מפורטת'],
    'PLAN_EXCEPTION': ['הקלה', 'שימוש חורג', 'חריגת בנייה'],

    # שמות
    'NAME_STREET': ['שם רחוב', 'קריאת רחוב'],
    'NAME_PLACE': ['שם גן', 'שם מוסד', 'כיכר', 'שם מקום'],
    'NAME_MEMORIAL': ['הנצחה', 'לזכר', 'ז"ל', 'קריאה על שם', 'הנצחת'],

    # דוחות
    'REPORT_FINANCIAL': ['דוח כספי', 'דוח שנתי', 'דוחות כספיים'],
    'REPORT_AUDIT': ['דוח מבקר', 'ביקורת', 'דוח ביקורת'],
    'REPORT_ACCOUNTANT': ['רואה חשבון', 'דוח רו"ח'],
    'REPORT_QUARTERLY': ['דוח רבעוני', 'ביצוע תקציב'],

    # עדכונים
    'UPDATE_MAYOR': ['דבר ראש העיר', 'דברי ראש העיר', 'הודעת ראש העיר'],
    'UPDATE_QUERY': ['שאילתה', 'שאלה לראש העיר'],
    'UPDATE_COMMITTEE': ['דיווח ועדה', 'דוח ועדה'],
    'UPDATE_PERSONAL': ['הודעה אישית', 'ברכה', 'תנחומים'],

    # פרוטוקולים
    'PROTOCOL_COUNCIL': ['אישור פרוטוקול', 'פרוטוקול ישיבה קודמת', 'אישור פרוטוקולים'],
    'PROTOCOL_COMMITTEE': ['אישור החלטות ועדה', 'פרוטוקול ועד הנהלה', 'החלטות ועדה', 'ועד הנהלה'],

    # חירום
    'EMERGENCY_DECISION': ['חירום', 'הגנה אזרחית', 'ביטחון', 'מלחמה'],
    'EMERGENCY_REPORT': ['מצב חירום', 'עדכון ביטחוני'],

    # רווחה וחינוך
    'WELFARE_PROGRAM': ['רווחה', 'סיוע', 'קשישים', 'תכנית סיוע', 'שירותי רווחה'],
    'EDUCATION_PROGRAM': ['חינוך', 'תכנית חינוך', 'בית ספר', 'גן ילדים', 'מוסדות חינוך'],

    # אחר
    'OTHER_CEREMONY': ['טקס', 'אזרחות כבוד', 'הוקרה', 'אות הוקרה'],
    'OTHER_GENERAL': ['אחר', 'כללי', 'שונות'],
}


def classify_discussion_admin_category(title: str, content: str = None) -> dict:
    """
    Classify a discussion into an administrative category based on keywords.
    סיווג סעיף לקטגוריה מנהלתית לפי מילות מפתח.

    Args:
        title: Discussion title (כותרת הסעיף)
        content: Optional discussion content (תוכן הסעיף)

    Returns:
        dict with 'category_code', 'confidence', 'matched_keywords'
    """
    if not title:
        return {
            'category_code': 'OTHER_GENERAL',
            'confidence': 0.1,
            'matched_keywords': []
        }

    # Combine title and content for search
    search_text = title.lower()
    if content:
        search_text += ' ' + content[:500].lower()

    best_match = None
    best_score = 0
    matched_keywords = []

    for category_code, keywords in ADMIN_CATEGORY_KEYWORDS.items():
        score = 0
        current_matches = []

        for keyword in keywords:
            keyword_lower = keyword.lower()
            if keyword_lower in search_text:
                # Weight by keyword length (longer = more specific)
                keyword_weight = len(keyword) / 10
                score += 1 + keyword_weight
                current_matches.append(keyword)

                # Bonus for title match (more relevant than content)
                if keyword_lower in title.lower():
                    score += 0.5

        if score > best_score:
            best_score = score
            best_match = category_code
            matched_keywords = current_matches

    # Calculate confidence (0-1)
    # Higher score = higher confidence, max out at 3+ matches
    confidence = min(best_score / 3, 1.0) if best_score > 0 else 0

    # Default to OTHER_GENERAL if no match
    if not best_match or confidence < 0.2:
        return {
            'category_code': 'OTHER_GENERAL',
            'confidence': 0.1,
            'matched_keywords': []
        }

    return {
        'category_code': best_match,
        'confidence': round(confidence, 2),
        'matched_keywords': matched_keywords
    }


def classify_discussion_with_llm(title: str, content: str = None) -> dict:
    """
    Use LLM to classify discussion if keyword matching is uncertain.
    שימוש ב-LLM לסיווג סעיף אם ההתאמה לפי מילות מפתח לא בטוחה.

    Only used as fallback when keyword confidence is low.
    """
    if not OLLAMA_AVAILABLE:
        return classify_discussion_admin_category(title, content)

    # First try keyword-based classification
    keyword_result = classify_discussion_admin_category(title, content)
    if keyword_result['confidence'] >= 0.6:
        return keyword_result

    # Use LLM for uncertain cases
    prompt = f"""אתה מסווג סעיפים מישיבות מועצת עיר לפי הקטגוריות הבאות:

BUDGET - תקציב ומימון (תקציב שנתי, תב"ר, העברות)
CONTRACT - חוזים ומכרזים
APPOINT - מינויים (מבקר, גזבר, ועדות)
BYLAW - חוקי עזר ואגרות
PROPERTY - נכסים ומקרקעין
LOAN - הלוואות וערבויות
CORP - תאגידים עירוניים
PLAN - תכנון ובנייה
NAME - שמות רחובות והנצחות
REPORT - דוחות וביקורת
UPDATE - דבר ראש העיר ושאילתות
PROTOCOL - אישור פרוטוקולים
EMERGENCY - חירום וביטחון
WELFARE - רווחה
EDUCATION - חינוך
OTHER - אחר

כותרת הסעיף: {title}

החזר רק את קוד הקטגוריה המתאימה ביותר (לדוגמה: BUDGET או CONTRACT).
אם הסעיף עוסק בתב"ר החזר BUDGET_TABAR.
אם הסעיף עוסק באישור פרוטוקול ועד הנהלה החזר PROTOCOL_COMMITTEE.

קטגוריה:"""

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 30}
            },
            timeout=OLLAMA_TIMEOUT
        )

        if response.status_code == 200:
            llm_category = response.json().get('response', '').strip().upper()
            # Clean up response
            llm_category = llm_category.replace(' ', '_').split('\n')[0]

            # Validate it's a known category
            if llm_category in ADMIN_CATEGORY_KEYWORDS:
                return {
                    'category_code': llm_category,
                    'confidence': 0.7,
                    'matched_keywords': ['llm_classified'],
                    'llm_used': True
                }

            # Try to match parent category
            for cat_code in ADMIN_CATEGORY_KEYWORDS.keys():
                if cat_code.startswith(llm_category):
                    return {
                        'category_code': cat_code,
                        'confidence': 0.5,
                        'matched_keywords': ['llm_classified'],
                        'llm_used': True
                    }

    except Exception as e:
        print(f"DEBUG: classify_discussion_with_llm error: {e}")

    # Return keyword result as fallback
    return keyword_result


def extract_decision_status(decision_text):
    """
    Extract the decision status (result) from decision text.
    Returns tuple: (status, full_decision_text)

    Status is one of: אושר, לא אושר, ירד מסדר היום, etc.
    """
    if not decision_text:
        return ('לא התקבלה החלטה', '')

    text_lower = decision_text.lower()

    # Check for specific patterns
    if 'ירד מסדר היום' in text_lower or 'הורד מסדר היום' in text_lower:
        return ('ירד מסדר היום', decision_text)

    if 'לא אושר' in text_lower or 'נדחה' in text_lower or 'לא התקבל' in text_lower:
        return ('לא אושר', decision_text)

    if 'הופנה לוועדה' in text_lower or 'יועבר לוועדה' in text_lower:
        return ('הופנה לוועדה', decision_text)

    if 'נדחה לדיון' in text_lower or 'יידחה' in text_lower:
        return ('נדחה לדיון נוסף', decision_text)

    if 'דיווח' in text_lower or 'עדכון' in text_lower or 'דבר ראש' in text_lower:
        return ('דיווח ועדכון', decision_text)

    if 'מאשר' in text_lower or 'אושר' in text_lower or 'מחליט' in text_lower:
        return ('אושר', decision_text)

    # Default
    return ('לא התקבלה החלטה', decision_text)


def extract_staff_with_roles(text):
    """
    Extract staff members (סגל) with their roles from protocol text.

    Returns list of dicts: [{'name': 'שם', 'role': 'תפקיד', 'matched_role': 'תפקיד ב-DB'}, ...]
    """
    staff_list = []

    if not text:
        return staff_list

    # Find the staff section
    # Structure: משתתפים -> חסרים -> סגל -> על סדר היום
    # OCR sometimes misses the "סגל" header, so we search the whole attendance area
    staff_text = None

    # Pattern 1: Explicit "סגל:" section
    staff_section = re.search(
        r'סגל[:\s]+(.*?)(?=על\s+סדר\s+היום|---\s+Page|\Z)',
        text,
        re.DOTALL | re.IGNORECASE
    )
    if staff_section:
        staff_text = staff_section.group(1)

    # Pattern 2: Search from "משתתפים" to "על סדר היום" - covers all attendance area
    # Staff lines will be filtered by keywords
    if not staff_text:
        full_section = re.search(
            r'(?:משתתפים|נוכחים)[:\s]+(.*?)(?=על\s+סדר\s+היום)',
            text,
            re.DOTALL | re.IGNORECASE
        )
        if full_section:
            staff_text = full_section.group(1)

    if not staff_text:
        return staff_list

    # Pattern to extract name and role
    # Format: "שם - תפקיד" or "תפקיד - שם"
    # Staff keywords that indicate this is a staff member
    staff_keywords = [
        'מנכ"ל', 'מנכל', 'מנכ"לית', 'מנכלית',
        'גזבר', 'גזברית',
        'יועמ"ש', 'יועץ משפטי', 'יועצת משפטית',
        'מבקר', 'מבקרת',
        'מהנדס', 'מהנדסת',
        'דובר', 'דוברת',
        'מזכיר', 'מזכירה',
        'עוזר', 'עוזרת',
        'מנהל', 'מנהלת',
        'רכז', 'רכזת',
        'תקציבן', 'תקציבנית',
        'העירייה'  # "גזבר העירייה" וכד'
    ]

    lines = staff_text.split('\n')
    for line in lines:
        line = line.strip()
        if len(line) < 5:
            continue

        # Check if line contains staff keyword
        has_staff_keyword = any(kw in line for kw in staff_keywords)
        if not has_staff_keyword:
            continue

        # Try to split by separator
        separator = None
        if ' - ' in line:
            separator = ' - '
        elif ' – ' in line:
            separator = ' – '
        elif ', ' in line:
            separator = ', '

        if separator:
            parts = line.split(separator, 1)
            if len(parts) == 2:
                part0 = parts[0].strip()
                part1 = parts[1].strip()

                # Determine which is name and which is role
                part0_is_role = any(kw in part0 for kw in staff_keywords)
                part1_is_role = any(kw in part1 for kw in staff_keywords)

                if part0_is_role and not part1_is_role:
                    role = part0
                    name = part1
                elif part1_is_role and not part0_is_role:
                    name = part0
                    role = part1
                elif part0_is_role and part1_is_role:
                    # Both look like roles - skip
                    continue
                else:
                    # Neither looks like role - skip
                    continue

                # Clean name (remove titles)
                name = re.sub(r'^(עו"ד|מר|גב\'?|ד"ר)\s+', '', name)
                name = re.sub(r'[^א-ת\s\'\"]', '', name).strip()

                if len(name) >= 3:
                    # Try to match role to known roles
                    matched_role = None
                    for known_role in KNOWN_STAFF_ROLES:
                        if known_role in role or role in known_role:
                            matched_role = known_role
                            break

                    staff_list.append({
                        'name': name,
                        'role': role,
                        'matched_role': matched_role
                    })

    return staff_list


def add_custom_value(value_type, new_value):
    """
    Add a new custom value (category or discussion type) to the learning log.
    These will be used to suggest additions to the database.

    Args:
        value_type: 'category' or 'discussion_type' or 'role'
        new_value: The new value to add
    """
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'type': f'new_{value_type}',
        'value': new_value,
        'status': 'pending'  # Will be 'added' after DB update
    }

    # Load existing log
    custom_values_path = os.path.join(os.path.dirname(__file__), "custom_values_log.json")
    values = []
    if os.path.exists(custom_values_path):
        try:
            with open(custom_values_path, 'r', encoding='utf-8') as f:
                values = json.load(f)
        except:
            values = []

    # Check if already exists
    exists = any(v.get('type') == f'new_{value_type}' and v.get('value') == new_value for v in values)
    if not exists:
        values.append(log_entry)

        try:
            with open(custom_values_path, 'w', encoding='utf-8') as f:
                json.dump(values, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Warning: Could not save custom value: {e}")
            return False

    return True  # Already exists


def get_pending_custom_values(value_type=None):
    """
    Get all pending custom values that need to be added to the database.
    """
    custom_values_path = os.path.join(os.path.dirname(__file__), "custom_values_log.json")

    if not os.path.exists(custom_values_path):
        return []

    try:
        with open(custom_values_path, 'r', encoding='utf-8') as f:
            values = json.load(f)

        pending = [v for v in values if v.get('status') == 'pending']

        if value_type:
            pending = [v for v in pending if v.get('type') == f'new_{value_type}']

        return pending
    except:
        return []


def extract_named_votes(text, db_persons=None):
    """
    Extract named votes from text and try to match to database persons.

    Args:
        text: The text containing vote information
        db_persons: List of person names from database for matching

    Returns:
        dict with 'yes', 'no', 'avoid' lists of {name, matched_person, confidence}
    """
    result = {
        'yes': [],
        'no': [],
        'avoid': []
    }

    if not text:
        return result

    # Patterns for extracting named votes
    vote_patterns = {
        'yes': [
            r'בעד[:\s]+([^.נ]+?)(?=\.|נגד|נמנע|$)',
            r'הצביעו בעד[:\s]+([^.]+?)(?=\.|$)',
        ],
        'no': [
            r'נגד[:\s]+([^.נ]+?)(?=\.|נמנע|$)',
            r'הצביעו נגד[:\s]+([^.]+?)(?=\.|$)',
        ],
        'avoid': [
            r'נמנע[ו]?[:\s]+([^.]+?)(?=\.|$)',
        ]
    }

    for vote_type, patterns in vote_patterns.items():
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                names_text = match.group(1)
                # Split by comma, "ו", or line break
                names = re.split(r'[,\n]|(?<!\S)ו(?!\S)', names_text)

                for name in names:
                    name = name.strip()
                    # Clean up the name
                    name = re.sub(r'^(עו"ד|מר|גב\'?|ד"ר)\s+', '', name)
                    name = re.sub(r'\s+', ' ', name)

                    if len(name) >= 3 and len(name) <= 50:
                        vote_entry = {
                            'name': name,
                            'matched_person': None,
                            'confidence': 0.0
                        }

                        # Try to match to DB persons
                        if db_persons:
                            best_match = None
                            best_score = 0.0

                            for db_name in db_persons:
                                # Clean DB name too
                                db_clean = re.sub(r'^(עו"ד|מר|גב\'?|ד"ר)\s+', '', db_name)
                                score = SequenceMatcher(None, name.lower(), db_clean.lower()).ratio()

                                if score > best_score:
                                    best_score = score
                                    best_match = db_name

                            if best_score > 0.6:
                                vote_entry['matched_person'] = best_match
                                vote_entry['confidence'] = best_score

                        result[vote_type].append(vote_entry)
                break  # Use first matching pattern

    return result


# ==============================================================================
# CHANGE LOGGING SYSTEM - for learning and improvement
# ==============================================================================

def log_change(change_type, ocr_value, db_value, final_value, context=None):
    """
    Log a change/correction for future learning.

    Args:
        change_type: Type of change ('name_match', 'category', 'decision', 'vote', etc.)
        ocr_value: Value extracted by OCR
        db_value: Value from database (if exists)
        final_value: Final value chosen by user
        context: Additional context (meeting_id, discussion_id, etc.)
    """
    log_entry = {
        'timestamp': datetime.now().isoformat(),
        'type': change_type,
        'ocr_value': ocr_value,
        'db_value': db_value,
        'final_value': final_value,
        'context': context or {}
    }

    # Load existing log
    logs = []
    if os.path.exists(CHANGE_LOG_PATH):
        try:
            with open(CHANGE_LOG_PATH, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        except:
            logs = []

    # Add new entry
    logs.append(log_entry)

    # Save log
    try:
        with open(CHANGE_LOG_PATH, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Warning: Could not save change log: {e}")


def get_learned_corrections(change_type=None):
    """
    Get all logged corrections, optionally filtered by type.
    Useful for analyzing patterns and improving algorithms.
    """
    if not os.path.exists(CHANGE_LOG_PATH):
        return []

    try:
        with open(CHANGE_LOG_PATH, 'r', encoding='utf-8') as f:
            logs = json.load(f)

        if change_type:
            logs = [l for l in logs if l.get('type') == change_type]

        return logs
    except:
        return []


def analyze_name_corrections():
    """
    Analyze name corrections to build a correction dictionary.
    Returns dict of {ocr_name: correct_name} based on past corrections.
    """
    corrections = get_learned_corrections('name_match')

    name_map = {}
    for c in corrections:
        ocr_name = c.get('ocr_value')
        final_name = c.get('final_value')

        if ocr_name and final_name and ocr_name != final_name:
            # Count occurrences
            key = ocr_name.lower().strip()
            if key not in name_map:
                name_map[key] = {}

            if final_name not in name_map[key]:
                name_map[key][final_name] = 0
            name_map[key][final_name] += 1

    # Return most common correction for each OCR name
    result = {}
    for ocr_name, corrections in name_map.items():
        if corrections:
            best = max(corrections, key=corrections.get)
            if corrections[best] >= 1:  # At least 1 occurrence
                result[ocr_name] = best

    return result


# ==============================================================================
# INITIALIZATION
# ==============================================================================

# Check if Ollama is available on module import
OLLAMA_AVAILABLE = check_ollama_available()

if OLLAMA_AVAILABLE:
    print(f"[OK] Ollama is available with model: {OLLAMA_MODEL}")
else:
    print(f"[!] Ollama not available. LLM fallback will be disabled.")
    print(f"  To enable: 1) Install Ollama from https://ollama.com")
    print(f"             2) Run: ollama pull {OLLAMA_MODEL}")
