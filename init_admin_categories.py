"""
Initialize Administrative Categories table with predefined categories.
אתחול טבלת הסיווג המנהלתי עם הקטגוריות המוגדרות מראש.
"""

from database import get_session
from models import AdministrativeCategory, Base
from sqlalchemy import create_engine

# Categories definition based on docs/discussion_types_classification.md
ADMIN_CATEGORIES = [
    # ======== MAIN CATEGORIES (parent_code = None) ========
    {'code': 'BUDGET', 'name_he': 'תקציב ומימון', 'name_en': 'Budget & Finance',
     'parent_code': None, 'decision_level': 'approval',
     'keywords': 'תקציב,מימון,כספים'},
    {'code': 'CONTRACT', 'name_he': 'חוזים והתקשרויות', 'name_en': 'Contracts',
     'parent_code': None, 'decision_level': 'approval',
     'keywords': 'חוזה,התקשרות,מכרז'},
    {'code': 'APPOINT', 'name_he': 'מינויים', 'name_en': 'Appointments',
     'parent_code': None, 'decision_level': 'approval',
     'keywords': 'מינוי,מנהל,בכיר'},
    {'code': 'BYLAW', 'name_he': 'חוקי עזר', 'name_en': 'Bylaws',
     'parent_code': None, 'decision_level': 'approval',
     'keywords': 'חוק עזר,תקנה,אגרה'},
    {'code': 'PROPERTY', 'name_he': 'נכסים ומקרקעין', 'name_en': 'Property',
     'parent_code': None, 'decision_level': 'approval',
     'keywords': 'נכס,מקרקעין,קרקע'},
    {'code': 'LOAN', 'name_he': 'הלוואות והתחייבויות', 'name_en': 'Loans',
     'parent_code': None, 'decision_level': 'approval',
     'keywords': 'הלוואה,אשראי,ערבות'},
    {'code': 'CORP', 'name_he': 'תאגידים עירוניים', 'name_en': 'Municipal Corporations',
     'parent_code': None, 'decision_level': 'approval',
     'keywords': 'תאגיד,חברה עירונית'},
    {'code': 'PLAN', 'name_he': 'תכנון ובנייה', 'name_en': 'Planning',
     'parent_code': None, 'decision_level': 'discussion',
     'keywords': 'תכנון,בנייה,תב"ע'},
    {'code': 'NAME', 'name_he': 'שמות רחובות ומוסדות', 'name_en': 'Naming',
     'parent_code': None, 'decision_level': 'discussion',
     'keywords': 'שם רחוב,הנצחה,קריאת שם'},
    {'code': 'REPORT', 'name_he': 'דוחות', 'name_en': 'Reports',
     'parent_code': None, 'decision_level': 'info',
     'keywords': 'דוח,ביקורת,מבקר'},
    {'code': 'UPDATE', 'name_he': 'עדכונים ודיווחים', 'name_en': 'Updates',
     'parent_code': None, 'decision_level': 'info',
     'keywords': 'עדכון,דיווח,דבר ראש'},
    {'code': 'PROTOCOL', 'name_he': 'אישור פרוטוקולים', 'name_en': 'Protocol Approval',
     'parent_code': None, 'decision_level': 'formal',
     'keywords': 'פרוטוקול,אישור פרוטוקול'},
    {'code': 'EMERGENCY', 'name_he': 'חירום וביטחון', 'name_en': 'Emergency',
     'parent_code': None, 'decision_level': 'approval',
     'keywords': 'חירום,ביטחון,מיגון'},
    {'code': 'WELFARE', 'name_he': 'רווחה וחינוך', 'name_en': 'Welfare & Education',
     'parent_code': None, 'decision_level': 'discussion',
     'keywords': 'רווחה,חינוך,בריאות'},

    # ======== SUB-CATEGORIES ========
    # תקציב ומימון
    {'code': 'BUDGET_ANNUAL', 'name_he': 'תקציב שנתי', 'name_en': 'Annual Budget',
     'parent_code': 'BUDGET', 'decision_level': 'approval',
     'keywords': 'תקציב שנתי,תקציב רגיל,אישור התקציב'},
    {'code': 'BUDGET_TABAR', 'name_he': 'תב"ר', 'name_en': 'Special Budget',
     'parent_code': 'BUDGET', 'decision_level': 'approval',
     'keywords': 'תב"ר,תקציב בלתי רגיל,פרויקט'},
    {'code': 'BUDGET_RESERVE', 'name_he': 'תקציב מילואים', 'name_en': 'Reserve Budget',
     'parent_code': 'BUDGET', 'decision_level': 'approval',
     'keywords': 'תקציב מילואים,תוספת תקציב,תקציב נוסף'},
    {'code': 'BUDGET_TRANSFER', 'name_he': 'העברה תקציבית', 'name_en': 'Budget Transfer',
     'parent_code': 'BUDGET', 'decision_level': 'approval',
     'keywords': 'העברה תקציבית,העברת כספים,שינוי תקציב'},

    # חוזים והתקשרויות
    {'code': 'CONTRACT_APPROVAL', 'name_he': 'אישור חוזה', 'name_en': 'Contract Approval',
     'parent_code': 'CONTRACT', 'decision_level': 'approval',
     'keywords': 'חוזה,אישור חוזה,הסכם,התקשרות'},
    {'code': 'CONTRACT_TENDER', 'name_he': 'מכרז', 'name_en': 'Tender',
     'parent_code': 'CONTRACT', 'decision_level': 'approval',
     'keywords': 'מכרז,פטור ממכרז,ועדת מכרזים,תוצאות מכרז'},
    {'code': 'CONTRACT_EXCEPTION', 'name_he': 'התקשרות חריגה', 'name_en': 'Exception Contract',
     'parent_code': 'CONTRACT', 'decision_level': 'approval',
     'keywords': 'התקשרות חריגה,ניגוד עניינים,קרוב משפחה'},

    # מינויים
    {'code': 'APPOINT_AUDITOR', 'name_he': 'מינוי מבקר', 'name_en': 'Auditor Appointment',
     'parent_code': 'APPOINT', 'decision_level': 'approval',
     'keywords': 'מינוי מבקר,מבקר פנימי,מבקר העירייה'},
    {'code': 'APPOINT_TREASURER', 'name_he': 'מינוי גזבר', 'name_en': 'Treasurer Appointment',
     'parent_code': 'APPOINT', 'decision_level': 'approval',
     'keywords': 'מינוי גזבר,גזבר העירייה'},
    {'code': 'APPOINT_SENIOR', 'name_he': 'מינוי בכיר', 'name_en': 'Senior Appointment',
     'parent_code': 'APPOINT', 'decision_level': 'approval',
     'keywords': 'מינוי מנהל,עובד בכיר,מנכ"ל'},
    {'code': 'APPOINT_COMMITTEE', 'name_he': 'מינוי לוועדה', 'name_en': 'Committee Appointment',
     'parent_code': 'APPOINT', 'decision_level': 'discussion',
     'keywords': 'מינוי לוועדה,חבר ועדה,נציג בוועדה'},
    {'code': 'APPOINT_BOARD', 'name_he': 'מינוי לדירקטוריון', 'name_en': 'Board Appointment',
     'parent_code': 'APPOINT', 'decision_level': 'discussion',
     'keywords': 'דירקטוריון,נציג בחברה,תאגיד'},

    # חוקי עזר
    {'code': 'BYLAW_NEW', 'name_he': 'חוק עזר חדש', 'name_en': 'New Bylaw',
     'parent_code': 'BYLAW', 'decision_level': 'approval',
     'keywords': 'חוק עזר,תקנה חדשה'},
    {'code': 'BYLAW_AMENDMENT', 'name_he': 'תיקון חוק עזר', 'name_en': 'Bylaw Amendment',
     'parent_code': 'BYLAW', 'decision_level': 'approval',
     'keywords': 'תיקון חוק עזר,עדכון תקנות'},
    {'code': 'BYLAW_FEE', 'name_he': 'אגרה/היטל', 'name_en': 'Fee/Levy',
     'parent_code': 'BYLAW', 'decision_level': 'approval',
     'keywords': 'אגרה,היטל,ארנונה,תעריף,קנס'},

    # נכסים ומקרקעין
    {'code': 'PROPERTY_SALE', 'name_he': 'מכירת נכס', 'name_en': 'Property Sale',
     'parent_code': 'PROPERTY', 'decision_level': 'approval',
     'keywords': 'מכירת נכס,מכירת מגרש,מכירת מקרקעין'},
    {'code': 'PROPERTY_PURCHASE', 'name_he': 'רכישת נכס', 'name_en': 'Property Purchase',
     'parent_code': 'PROPERTY', 'decision_level': 'approval',
     'keywords': 'רכישת נכס,הפקעה,רכישת קרקע'},
    {'code': 'PROPERTY_LEASE', 'name_he': 'חכירה/השכרה', 'name_en': 'Lease/Rental',
     'parent_code': 'PROPERTY', 'decision_level': 'approval',
     'keywords': 'חכירה,השכרה,השכרת נכס'},
    {'code': 'PROPERTY_ENCUMBRANCE', 'name_he': 'שעבוד', 'name_en': 'Encumbrance',
     'parent_code': 'PROPERTY', 'decision_level': 'approval',
     'keywords': 'שעבוד,משכנתא'},

    # הלוואות והתחייבויות
    {'code': 'LOAN_TAKE', 'name_he': 'לקיחת הלוואה', 'name_en': 'Take Loan',
     'parent_code': 'LOAN', 'decision_level': 'approval',
     'keywords': 'הלוואה,אשראי,לקיחת הלוואה'},
    {'code': 'LOAN_GUARANTEE', 'name_he': 'ערבות', 'name_en': 'Guarantee',
     'parent_code': 'LOAN', 'decision_level': 'approval',
     'keywords': 'ערבות,ערבות עירונית'},
    {'code': 'LOAN_INVESTMENT', 'name_he': 'השקעה', 'name_en': 'Investment',
     'parent_code': 'LOAN', 'decision_level': 'discussion',
     'keywords': 'השקעה,פיקדון'},

    # תאגידים עירוניים
    {'code': 'CORP_ESTABLISH', 'name_he': 'הקמת תאגיד', 'name_en': 'Establish Corporation',
     'parent_code': 'CORP', 'decision_level': 'approval',
     'keywords': 'הקמת חברה,הקמת תאגיד,חברה עירונית'},
    {'code': 'CORP_CHANGE', 'name_he': 'שינוי בתאגיד', 'name_en': 'Corporation Change',
     'parent_code': 'CORP', 'decision_level': 'discussion',
     'keywords': 'שינוי תקנון,שינוי הרכב'},
    {'code': 'CORP_DISSOLVE', 'name_he': 'פירוק תאגיד', 'name_en': 'Dissolve Corporation',
     'parent_code': 'CORP', 'decision_level': 'approval',
     'keywords': 'פירוק,סגירת חברה'},

    # תכנון ובנייה
    {'code': 'PLAN_MASTER', 'name_he': 'תכנית מתאר', 'name_en': 'Master Plan',
     'parent_code': 'PLAN', 'decision_level': 'discussion',
     'keywords': 'תכנית מתאר,מתאר עירוני'},
    {'code': 'PLAN_DETAIL', 'name_he': 'תכנית מפורטת', 'name_en': 'Detailed Plan',
     'parent_code': 'PLAN', 'decision_level': 'discussion',
     'keywords': 'תב"ע,תכנית בניין עיר,תכנית מפורטת'},
    {'code': 'PLAN_EXCEPTION', 'name_he': 'חריגה/הקלה', 'name_en': 'Exception',
     'parent_code': 'PLAN', 'decision_level': 'discussion',
     'keywords': 'הקלה,שימוש חורג,חריגת בנייה'},

    # שמות ואירועים
    {'code': 'NAME_STREET', 'name_he': 'שם רחוב', 'name_en': 'Street Name',
     'parent_code': 'NAME', 'decision_level': 'discussion',
     'keywords': 'שם רחוב,קריאת רחוב'},
    {'code': 'NAME_PLACE', 'name_he': 'שם מקום ציבורי', 'name_en': 'Public Place Name',
     'parent_code': 'NAME', 'decision_level': 'discussion',
     'keywords': 'שם גן,שם מוסד,כיכר'},
    {'code': 'NAME_MEMORIAL', 'name_he': 'הנצחה', 'name_en': 'Memorial',
     'parent_code': 'NAME', 'decision_level': 'discussion',
     'keywords': 'הנצחה,לזכר,ז"ל,קריאה על שם'},

    # דוחות וביקורת
    {'code': 'REPORT_FINANCIAL', 'name_he': 'דוח כספי', 'name_en': 'Financial Report',
     'parent_code': 'REPORT', 'decision_level': 'approval',
     'keywords': 'דוח כספי,דוח שנתי,דוחות כספיים'},
    {'code': 'REPORT_AUDIT', 'name_he': 'דוח מבקר', 'name_en': 'Audit Report',
     'parent_code': 'REPORT', 'decision_level': 'update',
     'keywords': 'דוח מבקר,ביקורת,דוח ביקורת'},
    {'code': 'REPORT_ACCOUNTANT', 'name_he': 'דוח רו"ח', 'name_en': 'Accountant Report',
     'parent_code': 'REPORT', 'decision_level': 'update',
     'keywords': 'רואה חשבון,דוח רו"ח'},
    {'code': 'REPORT_QUARTERLY', 'name_he': 'דוח רבעוני', 'name_en': 'Quarterly Report',
     'parent_code': 'REPORT', 'decision_level': 'update',
     'keywords': 'דוח רבעוני,ביצוע תקציב'},

    # עדכונים ודיווחים
    {'code': 'UPDATE_MAYOR', 'name_he': 'דבר ראש העיר', 'name_en': 'Mayor Statement',
     'parent_code': 'UPDATE', 'decision_level': 'update',
     'keywords': 'דבר ראש העיר,דברי ראש העיר,הודעת ראש העיר'},
    {'code': 'UPDATE_QUERY', 'name_he': 'שאילתה', 'name_en': 'Query',
     'parent_code': 'UPDATE', 'decision_level': 'update',
     'keywords': 'שאילתה,שאלה לראש העיר'},
    {'code': 'UPDATE_COMMITTEE', 'name_he': 'דיווח ועדה', 'name_en': 'Committee Report',
     'parent_code': 'UPDATE', 'decision_level': 'update',
     'keywords': 'דיווח ועדה,דוח ועדה'},
    {'code': 'UPDATE_PERSONAL', 'name_he': 'הודעה אישית', 'name_en': 'Personal Statement',
     'parent_code': 'UPDATE', 'decision_level': 'update',
     'keywords': 'הודעה אישית,ברכה,תנחומים'},

    # פרוטוקולים
    {'code': 'PROTOCOL_COUNCIL', 'name_he': 'פרוטוקול מועצה', 'name_en': 'Council Protocol',
     'parent_code': 'PROTOCOL', 'decision_level': 'formal',
     'keywords': 'אישור פרוטוקול,פרוטוקול ישיבה קודמת'},
    {'code': 'PROTOCOL_COMMITTEE', 'name_he': 'פרוטוקול ועדה', 'name_en': 'Committee Protocol',
     'parent_code': 'PROTOCOL', 'decision_level': 'formal',
     'keywords': 'אישור החלטות ועדה,פרוטוקול ועד הנהלה'},

    # חירום וביטחון
    {'code': 'EMERGENCY_DECISION', 'name_he': 'החלטת חירום', 'name_en': 'Emergency Decision',
     'parent_code': 'EMERGENCY', 'decision_level': 'approval',
     'keywords': 'חירום,הגנה אזרחית,ביטחון'},
    {'code': 'EMERGENCY_REPORT', 'name_he': 'דיווח חירום', 'name_en': 'Emergency Report',
     'parent_code': 'EMERGENCY', 'decision_level': 'update',
     'keywords': 'מצב חירום,עדכון ביטחוני'},

    # רווחה וחינוך
    {'code': 'WELFARE_PROGRAM', 'name_he': 'תכנית רווחה', 'name_en': 'Welfare Program',
     'parent_code': 'WELFARE', 'decision_level': 'discussion',
     'keywords': 'רווחה,סיוע,קשישים,תכנית סיוע'},
    {'code': 'EDUCATION_PROGRAM', 'name_he': 'תכנית חינוך', 'name_en': 'Education Program',
     'parent_code': 'EDUCATION', 'decision_level': 'discussion',
     'keywords': 'חינוך,תכנית חינוך,בית ספר,גן ילדים'},

    # אחר
    {'code': 'OTHER_GENERAL', 'name_he': 'כללי', 'name_en': 'General',
     'parent_code': 'OTHER', 'decision_level': 'discussion',
     'keywords': 'אחר,כללי'},
    {'code': 'OTHER_CEREMONY', 'name_he': 'טקסי', 'name_en': 'Ceremony',
     'parent_code': 'OTHER', 'decision_level': 'formal',
     'keywords': 'טקס,אזרחות כבוד,הוקרה'},
]


def init_admin_categories():
    """Initialize the administrative categories table"""
    session = get_session()

    try:
        # Check if table has data
        existing = session.query(AdministrativeCategory).count()
        if existing > 0:
            print(f"Administrative categories already exist ({existing} categories). Skipping initialization.")
            return existing

        # Add all categories
        added = 0
        for cat_data in ADMIN_CATEGORIES:
            category = AdministrativeCategory(
                code=cat_data['code'],
                name_he=cat_data['name_he'],
                name_en=cat_data.get('name_en'),
                parent_code=cat_data.get('parent_code'),
                decision_level=cat_data.get('decision_level', 'discussion'),
                keywords=cat_data.get('keywords', '')
            )
            session.add(category)
            added += 1

        session.commit()
        print(f"Successfully added {added} administrative categories.")
        return added

    except Exception as e:
        session.rollback()
        print(f"Error initializing categories: {e}")
        raise
    finally:
        session.close()


def create_tables():
    """Create new tables if they don't exist"""
    from database import engine
    Base.metadata.create_all(engine)
    print("Database tables created/updated.")


if __name__ == '__main__':
    print("=" * 50)
    print("Initializing Administrative Categories")
    print("=" * 50)

    # Create tables first
    create_tables()

    # Initialize categories
    init_admin_categories()

    print("=" * 50)
    print("Done!")
