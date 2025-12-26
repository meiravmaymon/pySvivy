"""
בדיקת מערכת הפילטרים של האתר Svivy
========================================

מבנה הפילטרים:
---------------
1. פילטר ראשי (גלובלי): עירייה + קדנציה
2. פילטר משני (מקומי): שנה/תקופה בתוך הקדנציה

כללי הפילטור:
--------------
1. ברירת מחדל: קדנציה נוכחית של יהוד-מונוסון
2. שינוי בפילטר הראשי משפיע על כל הדפים
3. פילטר משני מוגבל לשנים של הקדנציה שנבחרה
"""

import sys
from webapp.app import app
from webapp.models import db, Municipality, Term, Discussion, Person, Board
from datetime import datetime
from collections import defaultdict

def print_section(title):
    print("\n" + "="*70)
    print(title)
    print("="*70)

def test_1_municipalities_and_terms():
    """בדיקת עיריות וקדנציות במערכת"""
    print_section("1. בדיקת נתוני העירייה והקדנציות הקיימות במערכת")

    with app.app_context():
        # עיריות
        municipalities = Municipality.query.all()
        print("\nעיריות במערכת:")
        for muni in municipalities:
            print(f"  - {muni.name} (ID: {muni.id})")

        # קדנציות
        terms = Term.query.order_by(Term.term_number.desc()).all()
        print("\nקדנציות במערכת:")
        for term in terms:
            is_current = "✓ נוכחית" if term.is_current else ""
            end_date = term.end_date.strftime('%Y-%m-%d') if term.end_date else 'פתוח'
            print(f"  קדנציה {term.term_number}: {term.start_date.strftime('%Y-%m-%d')} - {end_date} {is_current}")

def test_2_api_periods():
    """בדיקת API /api/periods"""
    print_section("2. בדיקת API: /api/periods")

    with app.test_client() as client:
        response = client.get('/api/periods')
        periods_data = response.get_json()

        print("\nשנים זמינות:")
        print(periods_data.get('years', []))

        print("\nקדנציות זמינות:")
        for term in periods_data.get('terms', []):
            current = '(נוכחית)' if term['is_current'] else ''
            print(f"  - קדנציה {term['term_number']}: {term['label']} {current}")

def test_3_home_page_default():
    """תרחיש 1: דף הבית - ברירת מחדל (קדנציה נוכחית)"""
    print_section("3. תרחיש 1: דף הבית - ברירת מחדל (קדנציה נוכחית)")

    with app.app_context():
        current_term = Term.query.filter_by(is_current=True).first()
        current_term_number = current_term.term_number if current_term else None

    print(f"\nקדנציה נוכחית: {current_term_number}")

    with app.test_client() as client:
        url = f'/api/stats?term={current_term_number}'
        print(f"\nשאילתה: GET {url}")

        response = client.get(url)
        stats = response.get_json()

        print("\nתוצאות:")
        print(f"  - נוכחות בישיבות: {stats.get('attendance_rate', 'N/A')}%")
        print(f"  - החלטות בקדנציה: {stats.get('total_discussions', 'N/A')}")
        print(f"  - חברי מועצה פעילים: {stats.get('active_members', 'N/A')}")
        print(f"  - ישיבות השנה: {stats.get('meetings_this_year', 'N/A')}")

def test_4_specific_term():
    """תרחיש 2: בחירת קדנציה ספציפית"""
    print_section("4. תרחיש 2: בחירת קדנציה ספציפית (קדנציה 16)")

    selected_term = 16

    with app.test_client() as client:
        url = f'/api/stats?term={selected_term}'
        print(f"\nשאילתה: GET {url}")

        response = client.get(url)
        stats = response.get_json()

        print("\nתוצאות:")
        print(f"  - נוכחות בישיבות: {stats.get('attendance_rate', 'N/A')}%")
        print(f"  - החלטות בקדנציה: {stats.get('total_discussions', 'N/A')}")
        print(f"  - חברי מועצה פעילים: {stats.get('active_members', 'N/A')}")
        print(f"  - ישיבות השנה: {stats.get('meetings_this_year', 'N/A')}")

def test_5_all_terms():
    """תרחיש 3: כל הקדנציות"""
    print_section("5. תרחיש 3: כל הקדנציות")

    with app.test_client() as client:
        url = '/api/stats'
        print(f"\nשאילתה: GET {url}")

        response = client.get(url)
        stats = response.get_json()

        print("\nתוצאות:")
        print(f"  - נוכחות בישיבות: {stats.get('attendance_rate', 'N/A')}%")
        print(f"  - החלטות בכל הקדנציות: {stats.get('total_discussions', 'N/A')}")
        print(f"  - חברי מועצה פעילים: {stats.get('active_members', 'N/A')}")
        print(f"  - ישיבות השנה: {stats.get('meetings_this_year', 'N/A')}")

def test_6_discussions_default():
    """תרחיש 4: דף החלטות - ברירת מחדל"""
    print_section("6. תרחיש 4: דף החלטות - ברירת מחדל (קדנציה נוכחית)")

    with app.app_context():
        current_term = Term.query.filter_by(is_current=True).first()
        current_term_number = current_term.term_number if current_term else None

    with app.test_client() as client:
        url = f'/api/discussions?term={current_term_number}'
        print(f"\nשאילתה: GET {url}")

        response = client.get(url)
        discussions = response.get_json()

        print(f"\nמספר החלטות שהתקבלו: {len(discussions)}")

        if discussions:
            print("\n5 ההחלטות הראשונות:")
            for d in discussions[:5]:
                print(f"  - #{d['id']}: {d['title'][:50]}... ({d['date']}) - {d['status']}")

def test_7_discussions_with_year():
    """תרחיש 5: דף החלטות - קדנציה נוכחית + שנה"""
    print_section("7. תרחיש 5: דף החלטות - קדנציה נוכחית + שנה ספציפית (2024)")

    with app.app_context():
        current_term = Term.query.filter_by(is_current=True).first()
        current_term_number = current_term.term_number if current_term else None

    selected_year = 2024

    with app.test_client() as client:
        url = f'/api/discussions?term={current_term_number}&year={selected_year}'
        print(f"\nשאילתה: GET {url}")

        response = client.get(url)
        discussions = response.get_json()

        print(f"\nמספר החלטות בשנת {selected_year}: {len(discussions)}")

def test_8_discussions_specific_term():
    """תרחיש 6: דף החלטות - קדנציה ספציפית"""
    print_section("8. תרחיש 6: דף החלטות - קדנציה 16")

    selected_term = 16

    with app.test_client() as client:
        url = f'/api/discussions?term={selected_term}'
        print(f"\nשאילתה: GET {url}")

        response = client.get(url)
        discussions = response.get_json()

        print(f"\nמספר החלטות בקדנציה {selected_term}: {len(discussions)}")

        # חישוב שנים בפועל
        if discussions:
            years = set()
            for d in discussions:
                if d.get('date'):
                    year = int(d['date'].split('-')[0])
                    years.add(year)

            print(f"שנים בפועל בקדנציה זו: {sorted(years)}")

def test_9_years_per_term():
    """בדיקת התאמה בין שנים לקדנציות"""
    print_section("9. בדיקת התאמה: שנים זמינות לפי קדנציה")

    with app.app_context():
        terms = Term.query.order_by(Term.term_number).all()

        for term in terms:
            start_year = term.start_date.year
            end_year = term.end_date.year if term.end_date else datetime.now().year

            years_in_term = list(range(start_year, end_year + 1))

            print(f"\nקדנציה {term.term_number}: {term.start_date.strftime('%Y-%m-%d')} עד {term.end_date.strftime('%Y-%m-%d') if term.end_date else 'פתוח'}")
            print(f"  שנים תיאורטיות: {years_in_term}")

            # בדיקת מספר החלטות בכל שנה
            discussions = Discussion.query.filter(
                Discussion.term_id == term.id
            ).all()

            year_counts = defaultdict(int)
            for disc in discussions:
                if disc.date:
                    year = disc.date.year
                    year_counts[year] += 1

            if year_counts:
                print(f"  החלטות בפועל לפי שנה: {dict(sorted(year_counts.items()))}")
            else:
                print(f"  אין החלטות בקדנציה זו")

def test_10_current_filter_behavior():
    """בדיקת התנהגות הפילטור הנוכחי"""
    print_section("10. בדיקת התנהגות global-filter.js הנוכחי")

    import os
    filter_file = 'webapp/static/js/global-filter.js'

    if os.path.exists(filter_file):
        with open(filter_file, 'r', encoding='utf-8') as f:
            content = f.read()

        print("\nקובץ הפילטור הגלובלי נמצא.")
        print(f"גודל: {len(content)} תווים")

        # בדיקת ברירת מחדל
        if 'DEFAULT_TERM = 17' in content:
            print("✓ ברירת מחדל: קדנציה 17")
        else:
            print("✗ בעיה: לא נמצאה ברירת מחדל ברורה")

        # בדיקת localStorage
        if 'localStorage' in content:
            print("✓ משתמש ב-localStorage לשמירת מצב")
        else:
            print("✗ לא משתמש ב-localStorage")
    else:
        print(f"\n✗ קובץ {filter_file} לא נמצא!")

def main():
    """הרצת כל הבדיקות"""
    print("\n" + "="*70)
    print("בדיקת מערכת הפילטרים - Svivy")
    print("="*70)

    tests = [
        test_1_municipalities_and_terms,
        test_2_api_periods,
        test_3_home_page_default,
        test_4_specific_term,
        test_5_all_terms,
        test_6_discussions_default,
        test_7_discussions_with_year,
        test_8_discussions_specific_term,
        test_9_years_per_term,
        test_10_current_filter_behavior,
    ]

    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"\n✗ שגיאה בבדיקה: {str(e)}")
            import traceback
            traceback.print_exc()

    print("\n" + "="*70)
    print("סיכום והמלצות")
    print("="*70)
    print("""
    על בסיס הבדיקות שבוצעו, יש לוודא:

    1. ברירת מחדל באתר צריכה להיות הקדנציה הנוכחית
    2. בחירת קדנציה בפילטר הראשי משפיעה על כל הדפים
    3. פילטר השנים בדפים מסוימים מוגבל לשנים של הקדנציה שנבחרה
    4. "כל הקדנציות" מציג את כל השנים הזמינות במערכת

    הבעיות שזוהו יתוקנו בקובץ global-filter.js
    """)

if __name__ == '__main__':
    main()
