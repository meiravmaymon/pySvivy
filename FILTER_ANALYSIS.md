# ניתוח מערכת הפילטרים - Svivy

## מבנה נוכחי

### מערכת הפילטרים הקיימת

1. **global-filter.js** - מנהל את הפילטור הגלובלי דרך localStorage
2. **API Parameters**:
   - `filter_type`: 'all' | 'year' | 'term'
   - `filter_value`: מספר השנה או מספר הקדנציה

### דפי האתר

1. **index.html** (דף הבית)
   - פילטר ראשי: all / year / term

2. **discussions.html** (החלטות)
   - פילטר לפי קדנציה/שנה

3. **persons.html** (חברי מועצה)
   - פילטר לפי קדנציה

4. **boards.html** (ועדות)
   - ללא פילטר מיוחד

---

## הבעיות שזוהו

### 1. ברירת מחדל שגויה ❌
**בעיה**: קובץ `global-filter.js` מוגדר עם `DEFAULT_TERM = 17` שהיא קדנציה ריקה.

```javascript
this.DEFAULT_TERM = 17; // Current term (empty, no data)
```

**פתרון נדרש**:
- צריך לשלוף את הקדנציה הנוכחית מה-API (קדנציה עם `is_current=true`)
- לא להגדיר ערך קשיח בקוד

### 2. חוסר עקביות בשמות פרמטרים ❌
**בעיה**: המערכת משתמשת בשני סטים של שמות פרמטרים:

**ב-global-filter.js** (שגוי):
```javascript
return `${baseUrl}${separator}filter_type=${filter.type}&filter_value=${filter.value}`;
```

**ב-index.html** ובדפים אחרים (נכון):
```javascript
const url = termFilter.buildApiUrl('/api/stats');
// מצפה לקבל: /api/stats?filter_type=term&filter_value=16
```

**הערכה**: למעשה זה נכון! ה-API מקבל `filter_type` ו-`filter_value`.

###  3. חוסר היררכיה בפילטרים ❌

**הבעיה העיקרית שהמשתמשת תיארה**:

הרצוי:
```
פילטר ראשי (גלובלי):
├─ עירייה: יהוד-מונוסון (ברירת מחדל)
└─ קדנציה: קדנציה נוכחית / קדנציה X / כל הקדנציות

פילטר משני (בדף ספציפי):
├─ אם נבחרה קדנציה ספציפית → שנים של הקדנציה הזו בלבד
└─ אם נבחר "כל הקדנציות" → כל השנים במערכת
```

**הבעיה**: כרגע אין הפרדה בין פילטר ראשי למשני. הכל מעורבב ביחד.

---

## הפתרון המוצע

### שלב 1: תיקון ברירת המחדל

נוסיף API endpoint חדש שמחזיר את הקדנציה הנוכחית:

```python
# webapp/app.py
@app.route('/api/current-term')
def get_current_term():
    """Get the current active term"""
    session = get_session()
    current_term = session.query(Term).filter_by(is_current=True).first()
    session.close()

    if current_term:
        return jsonify({
            'term_number': current_term.term_number,
            'start_date': current_term.start_date.isoformat(),
            'end_date': current_term.end_date.isoformat() if current_term.end_date else None,
            'is_current': True
        })

    # Fallback - get the latest term
    session = get_session()
    latest_term = session.query(Term).order_by(Term.term_number.desc()).first()
    session.close()

    if latest_term:
        return jsonify({
            'term_number': latest_term.term_number,
            'start_date': latest_term.start_date.isoformat(),
            'end_date': latest_term.end_date.isoformat() if latest_term.end_date else None,
            'is_current': False
        })

    return jsonify({'error': 'No terms found'}), 404
```

### שלב 2: עדכון global-filter.js

```javascript
class GlobalTermFilter {
    constructor() {
        this.STORAGE_KEY = 'svivy_selected_term';
        this.currentTerm = null; // Will be loaded from API
        this.currentFilter = null;
        this.init();
    }

    async init() {
        // Load current term from API
        await this.loadCurrentTerm();
        // Load user's filter preference or set default
        this.currentFilter = this.loadFilter();
    }

    async loadCurrentTerm() {
        try {
            const response = await fetch('/api/current-term');
            const data = await response.json();
            this.currentTerm = data.term_number;
        } catch (error) {
            console.error('Error loading current term:', error);
            this.currentTerm = 16; // Fallback
        }
    }

    loadFilter() {
        const stored = localStorage.getItem(this.STORAGE_KEY);
        if (stored) {
            try {
                return JSON.parse(stored);
            } catch (e) {
                console.error('Error parsing stored filter:', e);
            }
        }
        // Default: Show current term
        return {
            type: 'term',
            value: this.currentTerm,
            label: `קדנציה ${this.currentTerm} (נוכחית)`
        };
    }

    // ... rest of the methods remain the same
}
```

### שלב 3: הוספת פילטור היררכי

צריך להוסיף לוגיקה שמחזירה רק שנים רלוונטיות לקדנציה שנבחרה:

```python
# webapp/app.py
@app.route('/api/available-years')
def get_available_years():
    """Get available years, optionally filtered by term"""
    session = get_session()
    filter_type = request.args.get('filter_type')
    filter_value = request.args.get('filter_value')

    query = session.query(
        func.strftime('%Y', Meeting.meeting_date).label('year')
    ).distinct()

    if filter_type == 'term' and filter_value:
        term_number = int(filter_value)
        term = session.query(Term).filter_by(term_number=term_number).first()
        if term:
            query = query.filter(Meeting.term_id == term.id)

    years = [int(row.year) for row in query.order_by('year').all() if row.year]
    session.close()

    return jsonify({
        'years': sorted(years),
        'filter': {
            'type': filter_type,
            'value': filter_value
        }
    })
```

### שלב 4: עדכון הדפים

**index.html** - פילטר ראשי בלבד (קדנציה / כל הקדנציות):
```html
<select id="filterType" onchange="updateFilterType()">
    <option value="term" selected>קדנציה נוכחית</option>
    <option value="all">כל הקדנציות</option>
</select>

<select id="filterValue" onchange="applyFilter()">
    <!-- Populated from /api/periods -->
</select>
```

**discussions.html** - פילטר משני (שנים בתוך הקדנציה):
```html
<!-- הפילטר הראשי נטען אוטומטית מ-localStorage -->
<div id="globalFilterDisplay">
    <!-- מציג את הקדנציה שנבחרה -->
</div>

<!-- פילטר משני - שנים -->
<select id="yearFilter" onchange="filterByYear()">
    <option value="all">כל השנים (בקדנציה)</option>
    <!-- Years loaded from /api/available-years?filter_type=term&filter_value=X -->
</select>
```

---

## תרחישי שימוש

### תרחיש 1: משתמש חדש נכנס לאתר
1. global-filter.js קורא ל-`/api/current-term`
2. מקבל בחזרה: `{ term_number: 16, is_current: true }`
3. מגדיר ברירת מחדל: קדנציה 16
4. כל הדפים מציגים נתוני קדנציה 16

### תרחיש 2: משתמש בוחר "כל הקדנציות"
1. בדף הבית: בוחר "כל הקדנציות"
2. global-filter.js שומר ב-localStorage: `{ type: 'all', value: null }`
3. עובר לדף החלטות
4. פילטר השנים קורא `/api/available-years` (ללא term)
5. מקבל את **כל** השנים הזמינות במערכת

### תרחיש 3: משתמש בוחר קדנציה 15
1. בדף הבית: בוחר "קדנציה 15"
2. global-filter.js שומר: `{ type: 'term', value: 15 }`
3. עובר לדף החלטות
4. פילטר השנים קורא `/api/available-years?filter_type=term&filter_value=15`
5. מקבל רק את השנים של קדנציה 15 (למשל: 2013-2018)
6. המשתמש יכול לבחור שנה ספציפית מתוך הרשימה הזו

---

## שאלות לבירור

1. **האם צריך תמיכה בבחירת עירייה?**
   - כרגע יש רק יהוד-מונוסון במערכת
   - אם כן, צריך להוסיף municipality_id לפילטר הגלובלי

2. **מה ברירת המחדל בדפים עם פילטר משני?**
   - "כל השנים בקדנציה" או "השנה הנוכחית"?

3. **האם לאפשר שילוב של שנה + קדנציה?**
   - למשל: "השנה 2024 רק בקדנציה 16"
   - זה כבר קיים ב-API

---

## סיכום השינויים הנדרשים

### קבצים לשינוי:

1. ✅ `webapp/app.py` - הוספת `/api/current-term` ו-`/api/available-years`
2. ✅ `webapp/static/js/global-filter.js` - תיקון ברירת מחדל + async init
3. ✅ `webapp/templates/index.html` - פילטר ראשי בלבד
4. ✅ `webapp/templates/discussions.html` - הוספת פילטר משני (שנים)
5. ✅ `webapp/templates/persons.html` - הצגת הפילטר הגלובלי
6. ✅ `webapp/templates/boards.html` - הצגת הפילטר הגלובלי

### סדר ביצוע:

1. **קודם** - נוסיף את ה-API endpoints החדשים
2. **אחר כך** - נתקן את global-filter.js
3. **בסוף** - נעדכן כל דף בנפרד
4. **בדיקה** - נריץ את test_filters.py לווידוא
