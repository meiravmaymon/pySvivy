"""
בדיקת שאילתות הפילטרים - סקריפט פשוט
==========================================

סקריפט זה בודק את כל השאילתות של הפילטרים בכל הדפים
ומציג את התוצאות בצורה ברורה

הערה: זהו סקריפט בדיקה ידני (לא pytest) - יש להריץ עם python tests/test_filters_simple.py
"""

import pytest
pytest.skip("Manual test script - run directly with: python tests/test_filters_simple.py", allow_module_level=True)

import requests
import json
from datetime import datetime

BASE_URL = 'http://127.0.0.1:5000'

def print_header(text):
    print("\n" + "="*80)
    print(text)
    print("="*80)

def print_subheader(text):
    print("\n" + "-"*80)
    print(text)
    print("-"*80)

def call_api(endpoint, description):
    """Test an API endpoint and display results"""
    url = f"{BASE_URL}{endpoint}"
    print(f"\n🔍 שאילתה: GET {endpoint}")

    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ סטטוס: 200 OK")
            print(f"📊 תוצאות:")
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return data
        else:
            print(f"❌ שגיאה: {response.status_code}")
            print(response.text)
            return None
    except Exception as e:
        print(f"❌ שגיאה בחיבור: {str(e)}")
        return None

def main():
    print_header("בדיקת מערכת הפילטרים - Svivy")
    print(f"זמן בדיקה: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # ============================================================
    # 1. בדיקת API Endpoints החדשים
    # ============================================================
    print_header("1. בדיקת API Endpoints החדשים")

    print_subheader("1.1 קדנציה נוכחית")
    current_term_data = call_api('/api/current-term', 'קדנציה נוכחית')

    print_subheader("1.2 רשימת עיריות")
    municipalities_data = call_api('/api/municipalities', 'רשימת עיריות')

    print_subheader("1.3 תקופות זמינות")
    periods_data = call_api('/api/periods', 'תקופות זמינות (קדנציות ושנים)')

    # ============================================================
    # 2. בדיקת פילטרים - דף הבית
    # ============================================================
    print_header("2. דף הבית - סטטיסטיקות")

    print_subheader("2.1 ברירת מחדל - קדנציה נוכחית")
    if current_term_data:
        term = current_term_data['term_number']
        stats = call_api(f'/api/stats?filter_type=term&filter_value={term}',
                        f'סטטיסטיקות לקדנציה {term}')

    print_subheader("2.2 קדנציה 16")
    stats_16 = call_api('/api/stats?filter_type=term&filter_value=16',
                       'סטטיסטיקות לקדנציה 16')

    print_subheader("2.3 קדנציה 15")
    stats_15 = call_api('/api/stats?filter_type=term&filter_value=15',
                       'סטטיסטיקות לקדנציה 15')

    print_subheader("2.4 שנה 2020")
    stats_2020 = call_api('/api/stats?filter_type=year&filter_value=2020',
                         'סטטיסטיקות לשנת 2020')

    # ============================================================
    # 3. בדיקת פילטרים - דף החלטות
    # ============================================================
    print_header("3. דף החלטות")

    print_subheader("3.1 קדנציה 16 - כל השנים")
    disc_16 = call_api('/api/discussions?filter_type=term&filter_value=16&limit=3',
                      'החלטות בקדנציה 16')
    if disc_16:
        print(f"\n📈 סה\"כ החלטות שהתקבלו: {len(disc_16)}")
        if len(disc_16) > 0:
            years = set()
            for d in disc_16:
                if d.get('date'):
                    year = d['date'][:4]
                    years.add(year)
            print(f"📅 שנים בפועל: {sorted(years)}")

    print_subheader("3.2 שנים זמינות לקדנציה 16")
    years_16 = call_api('/api/available-years?filter_type=term&filter_value=16',
                       'שנים זמינות לקדנציה 16')

    print_subheader("3.3 קדנציה 16 + שנה 2020")
    disc_16_2020 = call_api('/api/discussions?filter_type=term&filter_value=16&year=2020&limit=3',
                           'החלטות בקדנציה 16, שנת 2020')
    if disc_16_2020:
        print(f"\n📈 סה\"כ החלטות: {len(disc_16_2020)}")

    print_subheader("3.4 קדנציה 15")
    disc_15 = call_api('/api/discussions?filter_type=term&filter_value=15&limit=3',
                      'החלטות בקדנציה 15')

    print_subheader("3.5 שנים זמינות לקדנציה 15")
    years_15 = call_api('/api/available-years?filter_type=term&filter_value=15',
                       'שנים זמינות לקדנציה 15')

    # ============================================================
    # 4. בדיקת פילטרים - דף חברי מועצה
    # ============================================================
    print_header("4. דף חברי מועצה")

    print_subheader("4.1 קדנציה 16")
    persons_16 = call_api('/api/persons?filter_type=term&filter_value=16',
                         'חברי מועצה בקדנציה 16')
    if persons_16:
        print(f"\n📈 סה\"כ חברי מועצה: {len(persons_16)}")
        active = sum(1 for p in persons_16 if p.get('is_active'))
        print(f"👥 פעילים: {active}, לשעבר: {len(persons_16) - active}")

    print_subheader("4.2 קדנציה 15")
    persons_15 = call_api('/api/persons?filter_type=term&filter_value=15',
                         'חברי מועצה בקדנציה 15')
    if persons_15:
        print(f"\n📈 סה\"כ חברי מועצה: {len(persons_15)}")

    # ============================================================
    # 5. בדיקת פילטרים - דף ועדות
    # ============================================================
    print_header("5. דף ועדות")

    print_subheader("5.1 כל הועדות")
    boards = call_api('/api/boards', 'כל הועדות')
    if boards:
        print(f"\n📈 סה\"כ ועדות: {len(boards)}")
        active_boards = sum(1 for b in boards if b.get('is_active'))
        print(f"✅ פעילות: {active_boards}, ❌ לא פעילות: {len(boards) - active_boards}")

    # ============================================================
    # 6. סיכום ממצאים
    # ============================================================
    print_header("6. סיכום ממצאים")

    if current_term_data:
        print(f"\n✅ קדנציה נוכחית: {current_term_data['term_number']}")
        print(f"   מתאריך: {current_term_data['start_date']}")
        if current_term_data['end_date']:
            print(f"   עד תאריך: {current_term_data['end_date']}")
        print(f"   סטטוס: {'פעילה' if current_term_data['is_current'] else 'לא פעילה'}")

    if periods_data:
        print(f"\n✅ קדנציות זמינות:")
        for term in periods_data.get('terms', []):
            status = '(נוכחית)' if term['is_current'] else ''
            print(f"   - קדנציה {term['term_number']}: {term['start_year']}-{term['end_year']} {status}")

        print(f"\n✅ שנים זמינות במערכת:")
        years = periods_data.get('years', [])
        print(f"   {', '.join(map(str, years))}")

    # המלצות
    print_header("7. המלצות")

    print("\n🎯 ברירת מחדל מומלצת:")
    if current_term_data and current_term_data['term_number'] == 17:
        print("   ⚠️  קדנציה 17 ריקה - מומלץ להגדיר ברירת מחדל לקדנציה 16")
        print("   📝 פתרון: global-filter.js יבדוק אם הקדנציה הנוכחית ריקה")
        print("           ואם כן, יעבור אוטומטית לקדנציה האחרונה עם נתונים")
    else:
        print(f"   ✅ קדנציה נוכחית ({current_term_data['term_number']}) תקינה")

    print("\n🎯 פילטור היררכי:")
    print("   1️⃣  פילטר ראשי: עירייה + קדנציה (גלובלי לכל האתר)")
    print("   2️⃣  פילטר משני: שנה (בדפים ספציפיים, מוגבל לשנים של הקדנציה)")

    print("\n🎯 דוגמה לתרחיש:")
    print("   1. משתמש נכנס לאתר → ברירת מחדל: יהוד-מונוסון, קדנציה 16")
    print("   2. עובר לדף החלטות → רואה את כל ההחלטות של קדנציה 16")
    print("   3. בוחר בפילטר המשני 'שנת 2020' → רואה רק החלטות מ-2020 בקדנציה 16")
    print("   4. חוזר לדף הבית → עדיין בקדנציה 16")
    print("   5. מחליף בפילטר הראשי לקדנציה 15 → כל האתר עובר לקדנציה 15")

    print("\n" + "="*80)
    print("בדיקה הושלמה!")
    print("="*80)

if __name__ == '__main__':
    main()
