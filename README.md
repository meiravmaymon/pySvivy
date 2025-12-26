# Svivy - מערכת ניהול עירונית 🏛️

מערכת לניהול ומעקב אחר החלטות, ישיבות וחברי מועצה ברשויות מקומיות בישראל.

## 📋 תיאור הפרויקט

Svivy היא מערכת ניהול מקיפה לרשויות מקומיות המאפשרת:
- מעקב אחר חברי מועצה, תפקידים וסיעות
- ניהול ישיבות ועדות ומליאה
- תיעוד החלטות והצבעות
- ניתוח נתונים סטטיסטיים
- ממשק משתמש בעברית עם תמיכה מלאה ב-RTL

**נתונים נוכחיים במערכת:**
- 25 חברי מועצה
- 21 ועדות ומועצות
- 137 ישיבות
- 790 החלטות
- 11,506 הצבעות

## 🚀 התקנה מהירה

### דרישות מקדימות
- Python 3.9 ומעלה
- pip (מנהל חבילות Python)

### שלבי התקנה

1. **שכפול הפרויקט**
   ```bash
   cd c:\SvivyPro\sviviy\pySvivy
   ```

2. **יצירת סביבה וירטואלית**
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   # source venv/bin/activate  # Linux/Mac
   ```

3. **התקנת תלויות**
   ```bash
   pip install -r requirements.txt
   ```

4. **אתחול מסד הנתונים** (אם צריך ליצור מחדש)
   ```bash
   python database.py
   ```

5. **ייבוא נתונים** (אופציונלי)
   ```bash
   python import_data.py
   ```

6. **הרצת שרת הפיתוח**
   ```bash
   cd webapp
   python app.py
   ```

7. **פתיחת הדפדפן**
   ```
   http://localhost:5000
   ```

## 📁 מבנה הפרויקט

```
pySvivy/
├── models.py              # מודלים של מסד הנתונים (10 טבלאות)
├── database.py            # חיבור למסד נתונים
├── import_data.py         # ייבוא נתונים מ-Excel
├── php_unserialize.py     # פענוח נתונים ישנים
├── test_filters.py        # בדיקות מערכת הפילטרים
├── svivyNew.db            # מסד נתונים ראשי
├── requirements.txt       # תלויות Python
│
├── webapp/                # אפליקציית Flask
│   ├── app.py            # שרת Flask ו-API
│   ├── templates/        # תבניות HTML
│   │   ├── index.html           # דשבורד ראשי
│   │   ├── persons.html         # רשימת חברי מועצה
│   │   ├── person_detail.html   # פרטי חבר מועצה
│   │   ├── discussions.html     # רשימת החלטות
│   │   ├── discussion_detail.html
│   │   └── boards.html          # ועדות ומועצות
│   └── static/
│       ├── js/           # JavaScript
│       │   ├── global-filter.js      # ניהול פילטרים
│       │   ├── global-filter-ui.js
│       │   ├── category-icons.js
│       │   ├── empty-state.js
│       │   └── person-avatars.js
│       └── images/
│
├── yehudCsv/             # קבצי Excel לייבוא
├── tests/                # בדיקות
├── backups/              # גיבויים
└── archive/              # קוד היסטורי (firstTest לשעבר)
```

## 🗄️ סכמת מסד הנתונים

המערכת משתמשת ב-10 טבלאות עיקריות:

1. **Term** - קדנציות
2. **Category** - קטגוריות החלטות
3. **DiscussionType** - סוגי דיונים
4. **Faction** - סיעות
5. **Role** - תפקידים
6. **Person** - חברי מועצה
7. **Board** - ועדות ומועצות
8. **Meeting** - ישיבות
9. **Discussion** - החלטות ודיונים
10. **Vote** - הצבעות
11. **Attendance** - נוכחות בישיבות
12. **BudgetSource** - מקורות תקציב

## 🔌 API Endpoints

### סטטיסטיקות
- `GET /api/stats` - סטטיסטיקות כלליות
- `GET /api/periods` - קדנציות ושנים זמינים
- `GET /api/current-term` - קדנציה נוכחית

### חברי מועצה
- `GET /api/persons` - רשימת חברי מועצה
- `GET /api/person/<id>` - פרטי חבר מועצה

### ועדות
- `GET /api/boards` - רשימת ועדות

### החלטות
- `GET /api/discussions` - רשימת החלטות
- `GET /api/discussion/<id>` - פרטי החלטה

### ישיבות
- `GET /api/meetings` - רשימת ישיבות

**פרמטרים לסינון:**
- `filter_type`: 'all' / 'year' / 'term'
- `filter_value`: מספר שנה או קדנציה
- `year`: סינון משני לפי שנה

## 🎨 ממשק המשתמש

- **עיצוב רספונסיבי** - עובד על כל המכשירים
- **תמיכה מלאה בעברית** - RTL, גופנים עבריים
- **מערכת פילטרים גלובלית** - סינון לפי שנה/קדנציה
- **אייקונים לקטגוריות** - ויזואליזציה ברורה
- **אווטרים דינמיים** - ליצירת תמונות פרופיל

## 📊 ניהול נתונים

### ייבוא נתונים מ-Excel
```bash
python import_data.py
```

הסקריפט מייבא מ-4 קבצי Excel בתיקייה `yehudCsv/`:
- `MemberOfCouncilExport.xlsx` - חברי מועצה
- `CommitteesExport.xlsx` - ועדות
- `MeetingsExport.xlsx` - ישיבות
- `ProtocolsExport.xlsx` - פרוטוקולים והחלטות

### איפוס מסד הנתונים
```bash
rm svivyNew.db
python database.py
python import_data.py
```

## 🧪 בדיקות

```bash
# הרצת בדיקות
pytest

# בדיקות עם כיסוי
pytest --cov=. --cov-report=html

# בדיקת פילטרים
python test_filters.py
```

## 🛠️ פיתוח

### כלי פיתוח מותקנים
- **Black** - עיצוב קוד אוטומטי
- **Flake8** - בדיקת איכות קוד
- **Pytest** - מסגרת בדיקות

### הרצת Black
```bash
black .
```

### הרצת Flake8
```bash
flake8 .
```

## 📚 תיעוד נוסף

- `DATA_ANALYSIS.txt` - ניתוח מבנה נתוני Excel
- `DATABASE_SUMMARY.txt` - סיכום בניית מסד הנתונים
- `FILTER_ANALYSIS.md` - ניתוח מערכת הפילטרים
- `archive/` - תיעוד מקיף של גרסה מורחבת (50+ טבלאות)

## 🔧 בעיות ידועות

1. **פילטר ברירת מחדל** - מוגדר לקדנציה 17 (ריקה)
   - פתרון זמני: בחר קדנציה אחרת מהתפריט

2. **אין CSS נפרד** - כרגע הסגנונות מוטמעים ב-HTML
   - בתוכנית: הפרדה לקבצי CSS

## 🚧 תוכנית עבודה עתידית

- [ ] הפרדת CSS מ-HTML
- [ ] הוספת אימות משתמשים
- [ ] מערכת הרשאות
- [ ] ייצוא דוחות לפי קטגוריות
- [ ] גרפים ותרשימים מתקדמים
- [ ] תמיכה ברשויות נוספות
- [ ] API תיעוד (Swagger/OpenAPI)

## 📄 רישיון

מערכת פנימית לשימוש ברשויות מקומיות.

## 👥 צוות הפיתוח

פותח עבור עיריית יהוד-מונוסון

---

**גרסה נוכחית:** 1.0
**עדכון אחרון:** דצמבר 2025
