# Svivy - מערכת ניהול עירונית

> ⚠️ **שימו לב: המערכת בשלבי פיתוח פעיל**
>
> הפרויקט עדיין בבנייה ובפיתוח. חלק מהתכונות עשויות להשתנות.
> מוזמנים לעקוב, לתרום או לפתוח Issues!

---

מערכת לניהול ומעקב אחר החלטות, ישיבות וחברי מועצה ברשויות מקומיות בישראל.

## תיאור הפרויקט

Svivy היא מערכת ניהול מקיפה לרשויות מקומיות המאפשרת:
- מעקב אחר חברי מועצה, תפקידים וסיעות
- ניהול ישיבות ועדות ומליאה
- תיעוד החלטות והצבעות
- חילוץ אוטומטי של נתונים מפרוטוקולים (OCR)
- ניתוח נתונים סטטיסטיים

## נתונים במערכת

| סוג | כמות |
|-----|------|
| חברי מועצה וסגל | 31 |
| ועדות ומועצות | 21 |
| ישיבות | 136 |
| דיונים | 790 |
| הצבעות | 11,499 |
| קדנציות | 3 |

## מערכת OCR לפרוטוקולים

המערכת כוללת מנוע OCR מתקדם לחילוץ אוטומטי של נתונים מפרוטוקולים בעברית:

### תכונות עיקריות
- **זיהוי טקסט עברי** - Tesseract 5.3.3
- **חילוץ החלטות** - שימוש ב-LLM (Ollama/Gemma3)
- **התאמת שמות חכמה** - כולל זיהוי אוטומטי של טקסט הפוך
- **אימות רב-שלבי** - ממשק ווב ל-5 שלבי ולידציה
- **שמירה אטומית** - כל השינויים נשמרים יחד או לא בכלל

### אפליקציית ולידציה (Web)

```bash
python ocr_web_app.py
# פתח: http://localhost:5000
```

**שלבי האימות:**
1. **פרטי ישיבה** - מספר, תאריך וסוג הישיבה
2. **נוכחות** - התאמה בין OCR לבסיס הנתונים
3. **סגל** - אימות אנשי צוות חדשים
4. **דיונים** - השוואה ועדכון סעיפי הדיון
5. **סיום** - סיכום ושמירה סופית

### תכונות מתקדמות

- **תמיכה במספר לשוניות** - כל לשונית עם session נפרד
- **זיהוי שמות הפוכים** - מזהה אוטומטית טקסט עברי הפוך מ-OCR
- **כפתורי היפוך** - לתיקון ידני של שמות ותפקידים
- **התאמה מחמירה** - מונע התאמות שגויות על בסיס שם משפחה בלבד

### שימוש ב-OCR (Jupyter)

```python
from ocr_validation_module import ValidationSession

session = ValidationSession()
session.select_pdf()          # בחירת קובץ
session.run_ocr()             # הרצת OCR
session.search_meetings()     # חיפוש ישיבה מתאימה
session.load_meeting(82)      # טעינת ישיבה
session.apply_changes()       # שמירת שינויים
```

## התקנה

### דרישות מקדימות
- Python 3.9+
- Tesseract OCR 5.3.3+ עם תמיכה בעברית
- Ollama (אופציונלי, לתכונות LLM)

### שלבי התקנה

```bash
# 1. יצירת סביבה וירטואלית
python -m venv venv
venv\Scripts\activate  # Windows

# 2. התקנת תלויות
pip install -r requirements.txt

# 3. התקנת Tesseract (Windows)
# הורד מ: https://github.com/UB-Mannheim/tesseract/wiki
# התקן ל: C:\Program Files\Tesseract-OCR\

# 4. התקנת Ollama (אופציונלי)
# הורד מ: https://ollama.com
ollama pull gemma3:1b

# 5. אתחול מסד הנתונים
python database.py
```

## מבנה הפרויקט

```
pySvivy/
├── config.py                  # קונפיגורציה מרכזית
├── models.py                  # מודלים SQLAlchemy (12 טבלאות)
├── database.py                # ניהול חיבור לDB
├── import_data.py             # ייבוא מ-Excel
├── ocr_protocol.py            # מנוע OCR
├── ocr_validation_module.py   # אימות פרוטוקולים
├── ocr_web_app.py             # אפליקציית Flask לאימות OCR
├── llm_helper.py              # עזר LLM
├── ocr_learning_agent.py      # סוכן למידה מתיקוני OCR
├── db_action_agent.py         # חילוץ פעולות DB מדיונים
├── requirements.txt           # תלויות Python
│
├── ocr/                       # מודולי OCR
│   ├── text_utils.py          # עיבוד טקסט עברי
│   ├── date_extractor.py      # חילוץ תאריכים
│   ├── budget_extractor.py    # חילוץ תקציבים
│   ├── vote_extractor.py      # חילוץ הצבעות
│   └── pdf_processor.py       # המרת PDF לטקסט
│
├── agents/                    # מערכת סוכנים אוטונומיים
│   ├── base_agent.py
│   └── agent_manager.py
│
├── templates/                 # תבניות HTML
├── static/                    # CSS, JS
├── tests/                     # בדיקות pytest
├── migrations/                # מיגרציות Alembic
├── tools/                     # כלי עזר
├── docs/                      # תיעוד
│
├── Dockerfile                 # הגדרת Docker image
├── docker-compose.yml         # Compose לפריסה
└── alembic.ini                # קונפיגורציית Alembic
```

## סכמת מסד הנתונים

### טבלאות עיקריות

| טבלה | תיאור |
|------|-------|
| terms | קדנציות (תקופות כהונה) |
| persons | חברי מועצה וסגל |
| roles | תפקידים (היררכי) |
| factions | סיעות (היררכי) |
| boards | ועדות |
| meetings | ישיבות |
| discussions | סעיפי דיון |
| votes | הצבעות |
| attendances | נוכחות |
| categories | קטגוריות (היררכי) |
| discussion_types | סוגי דיון (היררכי) |
| budget_sources | מקורות מימון |

### שדות Discussion (דיון)

| שדה | תיאור |
|-----|-------|
| title | כותרת הסעיף |
| decision | סטטוס: אושר/לא אושר/ירד מסדר היום |
| decision_statement | נוסח ההחלטה המלא |
| summary | תקציר (נוצר ע"י LLM) |
| expert_opinion | דברי הסבר |
| yes_counter | מספר הצבעות בעד |
| no_counter | מספר הצבעות נגד |
| avoid_counter | מספר נמנעים |

## API Endpoints

### סטטיסטיקות
- `GET /api/stats` - סטטיסטיקות כלליות
- `GET /api/periods` - קדנציות ושנים זמינים

### נתונים
- `GET /api/persons` - רשימת חברי מועצה
- `GET /api/person/<id>` - פרטי חבר מועצה
- `GET /api/boards` - רשימת ועדות
- `GET /api/discussions` - רשימת דיונים
- `GET /api/meetings` - רשימת ישיבות

## הרצת השרת

```bash
# אפליקציית אימות OCR
python ocr_web_app.py
# פתח: http://localhost:5000

# הרצה עם Docker
docker-compose up --build
```

## בדיקות

```bash
pytest
pytest --cov=. --cov-report=html
```

## קבצים עיקריים

| קובץ | שורות | תיאור |
|------|-------|-------|
| models.py | 335 | מודלים SQLAlchemy |
| database.py | 107 | ניהול DB |
| ocr_protocol.py | 1,563 | מנוע OCR |
| ocr_validation_module.py | 904 | אימות פרוטוקולים |
| llm_helper.py | 931 | עזר LLM |
| import_data.py | 608 | ייבוא נתונים |

## עדכונים אחרונים

### גרסה 2.2 (ינואר 2026)
- **עיבוד אצווה** - עיבוד כל קבצי PDF בתיקייה ברקע עם מעקב התקדמות
- **מערכת למידה** - הסוכן לומד מתיקוני המשתמש ומתקן אוטומטית בעתיד
- **אבטחה משופרת** - הגנה מפני path traversal ובדיקות אבטחה

### גרסה 2.1 (ינואר 2026)
- **שמירה אטומית** - כל השינויים נשמרים בזיכרון עד לאישור סופי
- **תמיכה במספר לשוניות** - כל לשונית דפדפן עם session נפרד
- **התאמת שמות חכמה** - זיהוי אוטומטי של טקסט עברי הפוך
- **התאמה מחמירה יותר** - מניעת התאמות שגויות על בסיס שם משפחה בלבד
- **שיפורי UI** - כפתורי היפוך טקסט, אינדיקציות ויזואליות לשינויים

---

**גרסה:** 2.2
**עדכון אחרון:** ינואר 2026
**פותח עבור:** סביבי קום בע"מ
**רישיון:** MIT
**סטטוס:** 🚧 בפיתוח פעיל
