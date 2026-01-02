"""
OCR Validation Module - מודול אימות פרוטוקולים
כל הלוגיקה של אימות פרוטוקולים מול בסיס הנתונים

שימוש:
    from ocr_validation_module import ValidationSession
    session = ValidationSession()
    session.select_pdf()
    session.run_ocr()
    ...
"""

import os
import re
import json
import tkinter as tk
from tkinter import filedialog
from datetime import datetime
from difflib import SequenceMatcher

from database import get_session
from models import Meeting, Discussion, Vote, Attendance, Person, Category, DiscussionType, Role
from ocr_protocol import extract_text_from_pdf, parse_protocol_text, extract_staff_with_roles
from llm_helper import (
    OLLAMA_AVAILABLE,
    categorize_discussion,
    classify_discussion_type,
    summarize_discussion,
    extract_named_votes,
    extract_decision_status,
    add_custom_value,
    log_change,
    analyze_name_corrections,
    KNOWN_CATEGORIES,
    KNOWN_DISCUSSION_TYPES,
    DECISION_STATUSES,
    KNOWN_STAFF_ROLES
)


# קבועים
MEETING_TYPES = ['מן המניין', 'שלא מן המניין', 'אסיפה כללית']

DEFAULT_STAFF_START_DATE = datetime(2014, 1, 1)


class ValidationSession:
    """מחלקה ראשית לניהול סשן אימות פרוטוקול"""

    def __init__(self):
        self.pdf_path = None
        self.ocr_text = None
        self.ocr_data = None
        self.meeting_id = None
        self.db_meeting = None
        self.db_attendances = []
        self.db_discussions = []
        self.db_persons = []
        self.db_person_names = []
        self.db_roles = []
        self.db_role_names = []
        self.ocr_staff = []
        self.discussion_matches = []
        self.unmatched_db_discussions = []
        self.unanimous_votes = None

        # שינויים לביצוע
        self.changes = {
            'meeting': {},
            'attendance_add': [],
            'attendance_remove': [],
            'discussions_update': [],
            'discussions_add': [],
            'discussions_remove': [],
            'roles_add': [],
            'persons_add': [],
            'categories_add': [],
            'discussion_types_add': []
        }

        # שגיאות OCR שסורבו - לשליחה לסוכן הלמידה
        self.ocr_rejections = []

        # תיקוני שמות שנלמדו
        self.learned_corrections = analyze_name_corrections()

        print('✅ סשן אימות נוצר')
        print(f"   LLM זמין: {'כן' if OLLAMA_AVAILABLE else 'לא'}")
        if self.learned_corrections:
            print(f"   תיקוני שמות נלמדו: {len(self.learned_corrections)}")

    # ========== שלב 1: בחירת קובץ ==========
    def select_pdf(self):
        """פתיחת דיאלוג לבחירת קובץ PDF"""
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)

        file_path = filedialog.askopenfilename(
            title='בחר קובץ PDF',
            filetypes=[('PDF Files', '*.pdf')],
            initialdir=os.getcwd()
        )
        root.destroy()

        if file_path:
            self.pdf_path = file_path
            print(f'✅ נבחר: {os.path.basename(file_path)}')
            return True
        else:
            print('❌ לא נבחר קובץ')
            return False

    # ========== שלב 2: הרצת OCR ==========
    def run_ocr(self):
        """הרצת OCR וניתוח הפרוטוקול"""
        if not self.pdf_path:
            print('❌ יש לבחור קובץ קודם')
            return False

        print(f'מעבד: {os.path.basename(self.pdf_path)}')
        print('⏳ מריץ OCR...')

        self.ocr_text = extract_text_from_pdf(self.pdf_path, lang='heb+eng')
        self.ocr_data = parse_protocol_text(self.ocr_text)

        # סיכום
        info = self.ocr_data.get('meeting_info', {})
        att = self.ocr_data.get('attendances', [])
        disc = self.ocr_data.get('discussions', [])

        present = len([a for a in att if a.get('status') == 'present'])
        absent = len([a for a in att if a.get('status') == 'absent'])

        print('\n' + '='*50)
        print('סיכום OCR')
        print('='*50)
        print(f"מספר ישיבה: {info.get('meeting_no', 'N/A')}")
        print(f"סוג: {info.get('meeting_type_heb', 'מן המניין')}")
        print(f"תאריך: {info.get('date_str', 'N/A')}")
        print(f"נוכחים: {present}, נעדרים: {absent}")
        print(f"סעיפים: {len(disc)}")
        print('='*50)
        print('\n✅ OCR הושלם - ניתן להמשיך לשלב הבא')

        return True

    # ========== שלב 3: חיפוש ישיבה ==========
    def search_meetings(self):
        """חיפוש ישיבות מתאימות בDB"""
        if not self.ocr_data:
            print('❌ יש להריץ OCR קודם')
            return []

        ocr_info = self.ocr_data.get('meeting_info', {})
        ocr_no = ocr_info.get('meeting_no', '')
        ocr_date = ocr_info.get('date_str', '')

        session = get_session()
        meetings = session.query(Meeting).order_by(Meeting.meeting_date.desc()).all()

        matches = []
        for m in meetings:
            score = 0

            # השוואת מספר
            ocr_clean = ocr_no.replace('/', '') if ocr_no else ''
            db_clean = m.meeting_no.replace('/', '') if m.meeting_no else ''
            if ocr_clean and db_clean and ocr_clean == db_clean:
                score += 100

            # השוואת תאריך
            if ocr_date and m.meeting_date:
                for fmt in ['%d/%m/%y', '%d/%m/%Y', '%d.%m.%y', '%d.%m.%Y']:
                    try:
                        ocr_dt = datetime.strptime(ocr_date, fmt)
                        if ocr_dt.date() == m.meeting_date.date():
                            score += 50
                        break
                    except:
                        pass

            if score > 0:
                matches.append({
                    'id': m.id,
                    'meeting_no': m.meeting_no,
                    'date': m.meeting_date.strftime('%d/%m/%Y') if m.meeting_date else 'N/A',
                    'title': m.title[:40] if m.title else '',
                    'score': score
                })

        session.close()

        # מיון
        matches.sort(key=lambda x: x['score'], reverse=True)

        print(f'מחפש: {ocr_no} מתאריך {ocr_date}')
        print('-'*60)
        for m in matches[:10]:
            marker = '⭐' if m['score'] >= 100 else '  '
            print(f"{marker} {m['id']}: [{m['meeting_no']}] {m['date']} - {m['title']}...")
        print('-'*60)

        if matches and matches[0]['score'] >= 100:
            print(f'✅ מומלץ: ID {matches[0]["id"]}')

        return matches

    def load_meeting(self, meeting_id):
        """טעינת ישיבה מהDB"""
        session = get_session()
        meeting = session.query(Meeting).filter_by(id=meeting_id).first()

        if not meeting:
            session.close()
            print(f'❌ לא נמצאה ישיבה {meeting_id}')
            return False

        self.meeting_id = meeting_id
        self.db_meeting = {
            'id': meeting.id,
            'meeting_no': meeting.meeting_no,
            'title': meeting.title,
            'meeting_date': meeting.meeting_date,
            'meeting_type': meeting.meeting_type
        }

        # נוכחות
        attendances = session.query(Attendance).filter_by(meeting_id=meeting_id).all()
        self.db_attendances = [{
            'id': a.id,
            'person_id': a.person_id,
            'name': a.person.full_name if a.person else 'Unknown',
            'is_present': bool(a.is_present),
            'role_id': a.person.role_id if a.person else None
        } for a in attendances]

        # אנשים ותפקידים
        all_persons = session.query(Person).all()
        self.db_persons = [{'id': p.id, 'name': p.full_name, 'role_id': p.role_id}
                          for p in all_persons if p.full_name]
        self.db_person_names = [p.full_name for p in all_persons if p.full_name]

        all_roles = session.query(Role).all()
        self.db_roles = [{'id': r.id, 'name': r.name} for r in all_roles]
        self.db_role_names = [r.name for r in all_roles]

        # דיונים
        discussions = session.query(Discussion).filter_by(meeting_id=meeting_id).all()
        self.db_discussions = [{
            'id': d.id,
            'issue_no': d.issue_no,
            'title': d.title,
            'decision': d.decision,  # סטטוס: אושר/לא אושר
            'decision_statement': d.decision_statement,  # נוסח ההחלטה
            'summary': d.summary,  # תקציר
            'expert_opinion': d.expert_opinion,
            'yes_counter': d.yes_counter,
            'no_counter': d.no_counter,
            'avoid_counter': d.avoid_counter,
            'total_budget': d.total_budget
        } for d in discussions]

        session.close()

        print(f'✅ נטענה: {meeting.meeting_no}')
        print(f"   נוכחות: {len(self.db_attendances)}, דיונים: {len(self.db_discussions)}")
        return True

    # ========== שלב 4: אימות פרטי ישיבה ==========
    def get_meeting_comparison(self):
        """השוואת פרטי ישיבה OCR מול DB"""
        if not self.ocr_data or not self.db_meeting:
            return None

        ocr = self.ocr_data.get('meeting_info', {})
        db = self.db_meeting

        return {
            'title': {
                'db': db['title'] or ''
            },
            'date': {
                'ocr': ocr.get('date_str', ''),
                'db': db['meeting_date'].strftime('%d/%m/%Y') if db['meeting_date'] else ''
            },
            'type': {
                'ocr': ocr.get('meeting_type_heb', 'מן המניין'),
                'db': db['meeting_type'] or 'לא מוגדר',
                'options': MEETING_TYPES
            },
            'number': {
                'ocr': ocr.get('meeting_no', ''),
                'db': db['meeting_no'] or ''
            },
            'discussions_count': len(self.db_discussions)
        }

    def update_meeting_field(self, field, value):
        """עדכון שדה בפרטי ישיבה"""
        self.changes['meeting'][field] = value
        print(f'✏️ {field} יעודכן ל: {value}')

    # ========== שלב 5: אימות נוכחות ==========
    def get_attendance_comparison(self):
        """השוואת נוכחות OCR מול DB"""
        ocr_att = self.ocr_data.get('attendances', []) if self.ocr_data else []

        ocr_present = [a.get('name') for a in ocr_att if a.get('status') == 'present']
        ocr_absent = [a.get('name') for a in ocr_att if a.get('status') == 'absent']
        db_present = [a['name'] for a in self.db_attendances if a['is_present']]
        db_absent = [a['name'] for a in self.db_attendances if not a['is_present']]

        return {
            'present': self._match_names(ocr_present, db_present),
            'absent': self._match_names(ocr_absent, db_absent),
            'counts': {
                'ocr_present': len(ocr_present),
                'ocr_absent': len(ocr_absent),
                'db_present': len(db_present),
                'db_absent': len(db_absent)
            }
        }

    def _match_names(self, ocr_list, db_list):
        """התאמת שמות בין רשימות"""
        results = []
        matched_db = set()

        for ocr_name in ocr_list:
            best_match, best_score = self._find_best_match(ocr_name, db_list)
            if best_score > 0.7:
                matched_db.add(best_match)
                results.append({
                    'ocr': ocr_name,
                    'db': best_match,
                    'score': best_score,
                    'status': 'matched'
                })
            else:
                results.append({
                    'ocr': ocr_name,
                    'db': None,
                    'score': 0,
                    'status': 'ocr_only'
                })

        for db_name in db_list:
            if db_name not in matched_db:
                results.append({
                    'ocr': None,
                    'db': db_name,
                    'score': 0,
                    'status': 'db_only'
                })

        return results

    def _find_best_match(self, name, name_list):
        """מציאת ההתאמה הטובה ביותר לשם"""
        clean_name = self._clean_name(name)
        best_match = None
        best_score = 0.0

        for candidate in name_list:
            clean_candidate = self._clean_name(candidate)
            score = SequenceMatcher(None, clean_name.lower(), clean_candidate.lower()).ratio()
            if score > best_score:
                best_score = score
                best_match = candidate

        return best_match, best_score

    def _clean_name(self, name):
        """ניקוי שם מתארים"""
        if not name:
            return ''
        patterns = [r'עו["\']+[דר]\s+', r'מר\s+', r'גב["\']?\s+', r'ד["\']+ר\s+']
        result = name
        for p in patterns:
            result = re.sub(p, '', result, flags=re.IGNORECASE)
        return result.strip()

    # ========== שלב 5.5: אימות סגל ==========
    def debug_staff_search(self):
        """דיבוג - הצג את קטע הסגל מהטקסט"""
        if not self.ocr_text:
            print("❌ אין טקסט OCR")
            return

        import re
        print('═' * 60)
        print('🔍 דיבוג חיפוש סגל')
        print('═' * 60)

        # חפש את המילה "סגל" בטקסט
        if 'סגל' in self.ocr_text:
            print("✓ המילה 'סגל' נמצאה בטקסט")
            # מצא את המיקום
            idx = self.ocr_text.find('סגל')
            print(f"   מיקום: תו {idx}")
            # הצג 500 תווים מסביב
            start = max(0, idx - 50)
            end = min(len(self.ocr_text), idx + 500)
            print(f"\n   קטע הטקסט:")
            print('-' * 40)
            snippet = self.ocr_text[start:end]
            for line in snippet.split('\n')[:15]:
                print(f"   {line[:70]}")
            print('-' * 40)
        else:
            print("❌ המילה 'סגל' לא נמצאה בטקסט")

        # חפש תפקידים ספציפיים
        roles_to_find = ['מנכ"ל', 'גזבר', 'יועמ"ש', 'מבקר', 'מהנדס', 'דובר']
        print(f"\n📌 חיפוש תפקידים:")
        for role in roles_to_find:
            if role in self.ocr_text:
                idx = self.ocr_text.find(role)
                # מצא את השורה
                start = self.ocr_text.rfind('\n', 0, idx) + 1
                end = self.ocr_text.find('\n', idx)
                if end == -1:
                    end = idx + 50
                line = self.ocr_text[start:end].strip()
                print(f"   ✓ '{role}': {line[:60]}")
            else:
                print(f"   ❌ '{role}' לא נמצא")

        print('═' * 60)

    def extract_staff(self):
        """
        חילוץ סגל מהפרוטוקול והשוואה ל-DB

        מחזיר dict עם:
        - ocr_staff: סגל שחולץ מ-OCR
        - db_staff: סגל מנוכחות הישיבה ב-DB (בעלי תפקיד)
        - matched: סגל שנמצא גם ב-OCR וגם ב-DB
        - ocr_only: סגל ב-OCR בלבד
        - db_only: סגל ב-DB בלבד
        """
        if not self.ocr_text:
            return {'ocr_staff': [], 'db_staff': [], 'matched': [], 'ocr_only': [], 'db_only': []}

        self.ocr_staff = extract_staff_with_roles(self.ocr_text)

        # סגל מ-OCR עם התאמה ל-DB
        ocr_results = []
        matched_db_names = set()

        for staff in self.ocr_staff:
            name = staff['name']
            role = staff['role']

            person_match, person_score = self._find_best_match(name, self.db_person_names)
            role_match, role_score = self._find_best_match(role, self.db_role_names)

            is_matched = person_score > 0.8
            if is_matched:
                matched_db_names.add(person_match)

            ocr_results.append({
                'name': name,
                'role': role,
                'person_in_db': person_match if is_matched else None,
                'role_in_db': role_match if role_score > 0.7 else None,
                'status': 'matched' if is_matched else 'ocr_only'
            })

        # סגל מנוכחות ב-DB (בעלי תפקיד - לא נבחרים)
        # תפקידי נבחרים שיש לסנן
        elected_roles = ['חבר מועצה', 'חברת מועצה', 'ראש העיר', 'סגן ראש העיר', 'חבר מועצה לשעבר']

        db_staff = []
        for att in self.db_attendances:
            if att['role_id']:  # יש תפקיד
                # מצא את שם התפקיד
                role_name = None
                for r in self.db_roles:
                    if r['id'] == att['role_id']:
                        role_name = r['name']
                        break

                # סנן נבחרים - רק סגל
                if role_name and any(elected in role_name for elected in elected_roles):
                    continue

                db_staff.append({
                    'name': att['name'],
                    'role': role_name,
                    'person_id': att['person_id'],
                    'is_present': att['is_present'],
                    'status': 'matched' if att['name'] in matched_db_names else 'db_only'
                })

        # סיווג לקבוצות
        matched = [s for s in ocr_results if s['status'] == 'matched']
        ocr_only = [s for s in ocr_results if s['status'] == 'ocr_only']
        db_only = [s for s in db_staff if s['status'] == 'db_only']

        return {
            'ocr_staff': ocr_results,
            'db_staff': db_staff,
            'matched': matched,
            'ocr_only': ocr_only,
            'db_only': db_only
        }

    def add_new_role(self, role_name):
        """הוספת תפקיד חדש"""
        self.changes['roles_add'].append({'name': role_name})
        add_custom_value('role', role_name)
        print(f'➕ תפקיד יתווסף: {role_name}')

    def add_new_person(self, name, role, add_attendance=True):
        """הוספת אדם חדש (סגל)"""
        self.changes['persons_add'].append({
            'name': name,
            'role': role,
            'start_date': DEFAULT_STAFF_START_DATE,
            'add_attendance': add_attendance
        })
        print(f'➕ אדם יתווסף: {name} ({role})')
        if add_attendance:
            print(f'   + נוכחות בישיבה')

    def add_staff_attendance(self, person_name):
        """הוספת נוכחות לאיש סגל קיים"""
        # מצא את ה-person_id
        person_id = None
        for p in self.db_persons:
            if p['name'] == person_name:
                person_id = p['id']
                break

        if person_id:
            self.changes['attendance_add'].append({
                'person_id': person_id,
                'person_name': person_name,
                'is_present': True
            })
            print(f'➕ נוכחות תתווסף: {person_name}')

    def reject_ocr_value(self, value_type, ocr_value, reason='שגיאת OCR'):
        """
        סירוב להכניס ערך מה-OCR - שומר ללמידה עתידית
        (ה-OCR קרא משהו שגוי)

        Args:
            value_type: 'person', 'role', 'attendance'
            ocr_value: הערך שחולץ מה-OCR
            reason: סיבת הסירוב
        """
        rejection = {
            'type': value_type,
            'ocr_value': ocr_value,
            'correct_value': None,  # אין ערך נכון - זה פשוט שגיאה
            'reason': reason,
            'meeting_id': self.meeting_id,
            'learning_type': 'false_positive'  # OCR זיהה משהו שלא קיים
        }
        self.ocr_rejections.append(rejection)
        log_change('ocr_rejection', ocr_value, None, None, rejection)
        print(f'❌ נדחה: {ocr_value} ({reason})')

    def report_ocr_miss(self, value_type, correct_value, role=None):
        """
        דיווח על ערך שה-OCR החמיץ - שומר ללמידה עתידית
        (הערך היה בטקסט אבל ה-OCR לא זיהה אותו)

        Args:
            value_type: 'person', 'role', 'attendance'
            correct_value: הערך הנכון (מה-DB)
            role: תפקיד (אם רלוונטי)
        """
        miss = {
            'type': value_type,
            'ocr_value': None,  # OCR לא מצא כלום
            'correct_value': correct_value,
            'role': role,
            'reason': 'OCR החמיץ',
            'meeting_id': self.meeting_id,
            'learning_type': 'false_negative'  # OCR לא זיהה משהו שקיים
        }
        self.ocr_rejections.append(miss)
        log_change('ocr_miss', None, correct_value, None, miss)
        print(f'📝 OCR החמיץ: {correct_value}')

    def get_rejections_summary(self):
        """קבלת סיכום הסירובים לשליחה לסוכן הלמידה"""
        return self.ocr_rejections

    def report_field_correction(self, field_name, ocr_value, db_value, chosen_value, entity_type='meeting', entity_id=None):
        """
        דיווח על תיקון שדה - כשהמשתמש בחר בין OCR ל-DB

        Args:
            field_name: שם השדה (date, type, title, decision, etc.)
            ocr_value: הערך שה-OCR קרא
            db_value: הערך שהיה ב-DB
            chosen_value: הערך שהמשתמש בחר
            entity_type: 'meeting' או 'discussion'
            entity_id: ID של הישות
        """
        # קביעת סוג הלמידה
        if chosen_value == ocr_value and ocr_value != db_value:
            # המשתמש בחר OCR = ה-DB היה שגוי
            learning_type = 'db_was_wrong'
            reason = 'DB שגוי, OCR נכון'
        elif chosen_value == db_value and ocr_value != db_value:
            # המשתמש בחר DB = ה-OCR טעה
            learning_type = 'ocr_was_wrong'
            reason = 'OCR שגוי, DB נכון'
        elif chosen_value != ocr_value and chosen_value != db_value:
            # המשתמש הזין ערך ידני = שניהם טעו
            learning_type = 'both_wrong'
            reason = 'שניהם שגויים, תוקן ידנית'
        else:
            # הם זהים - אין מה ללמוד
            return

        correction = {
            'type': f'{entity_type}_{field_name}',
            'field': field_name,
            'ocr_value': ocr_value,
            'db_value': db_value,
            'correct_value': chosen_value,
            'reason': reason,
            'meeting_id': self.meeting_id,
            'entity_type': entity_type,
            'entity_id': entity_id,
            'learning_type': learning_type
        }
        self.ocr_rejections.append(correction)
        log_change('field_correction', ocr_value, chosen_value, db_value, correction)

        if learning_type == 'ocr_was_wrong':
            print(f'📝 תיקון {field_name}: OCR "{ocr_value}" → DB "{db_value}"')
        elif learning_type == 'db_was_wrong':
            print(f'📝 תיקון {field_name}: DB "{db_value}" → OCR "{ocr_value}"')
        else:
            print(f'📝 תיקון {field_name}: ידני "{chosen_value}"')

    # ========== שלב 6: אימות דיונים ==========
    def match_discussions(self):
        """התאמת סעיפי דיון בין OCR ל-DB"""
        ocr_disc = self.ocr_data.get('discussions', []) if self.ocr_data else []

        matched_db_ids = set()
        self.discussion_matches = []

        for i, ocr_d in enumerate(ocr_disc, 1):
            ocr_title = ocr_d.get('content', '')[:100]
            ocr_num = ocr_d.get('number', str(i))

            best_match = None
            best_score = 0

            for db_d in self.db_discussions:
                if db_d['id'] in matched_db_ids:
                    continue

                score = SequenceMatcher(None, ocr_title.lower(),
                                       (db_d['title'] or '').lower()).ratio()

                if db_d['issue_no'] and ocr_num == db_d['issue_no']:
                    score += 0.2

                if score > best_score:
                    best_score = score
                    best_match = db_d

            if best_match and best_score > 0.4:
                matched_db_ids.add(best_match['id'])
                self.discussion_matches.append({
                    'index': i,
                    'ocr': ocr_d,
                    'db': best_match,
                    'score': best_score
                })
            else:
                self.discussion_matches.append({
                    'index': i,
                    'ocr': ocr_d,
                    'db': None,
                    'score': 0
                })

        self.unmatched_db_discussions = [d for d in self.db_discussions
                                         if d['id'] not in matched_db_ids]

        return {
            'matches': self.discussion_matches,
            'unmatched_db': self.unmatched_db_discussions
        }

    # ========== שלב 7: עריכת סעיף ==========
    def get_discussion_details(self, index):
        """קבלת פרטי סעיף לעריכה"""
        if index < 1 or index > len(self.discussion_matches):
            return None

        match = self.discussion_matches[index - 1]
        ocr_d = match['ocr']
        db_d = match['db']
        ocr_title = ocr_d.get('content', '')
        ocr_decision = ocr_d.get('decision', '')

        # קטגוריה וסוג דיון מ-LLM
        cat_result = categorize_discussion(ocr_title)
        type_result = classify_discussion_type(ocr_title)

        # סטטוס החלטה
        decision_status, full_decision = extract_decision_status(ocr_decision)

        # הצבעות
        ocr_vote_type = ocr_d.get('vote_type', '')
        is_unanimous = ocr_vote_type == 'unanimous' or 'פה אחד' in ocr_decision

        # נוכחים מ-DB
        db_present = [a for a in self.db_attendances if a['is_present']]

        return {
            'index': index,
            'title': {
                'ocr': ocr_title,
                'db': db_d['title'] if db_d else None
            },
            'category': {
                'suggested': cat_result['suggested'],
                'confidence': cat_result['confidence'],
                'options': KNOWN_CATEGORIES
            },
            'discussion_type': {
                'suggested': type_result['suggested'],
                'confidence': type_result['confidence'],
                'options': KNOWN_DISCUSSION_TYPES
            },
            'decision': {
                'status': decision_status,  # סטטוס שחולץ מ-OCR
                'full_text': full_decision,  # נוסח ההחלטה מ-OCR
                'db_status': db_d['decision'] if db_d else None,  # סטטוס מ-DB
                'db_statement': db_d['decision_statement'] if db_d else None,  # נוסח מ-DB
                'db_summary': db_d['summary'] if db_d else None,  # תקציר מ-DB
                'status_options': DECISION_STATUSES
            },
            'votes': {
                'is_unanimous': is_unanimous,
                'ocr_yes': ocr_d.get('yes_votes', 0),
                'ocr_no': ocr_d.get('no_votes', 0),
                'ocr_avoid': ocr_d.get('avoid_votes', 0),
                'db_yes': db_d['yes_counter'] if db_d else 0,
                'db_no': db_d['no_counter'] if db_d else 0,
                'db_avoid': db_d['avoid_counter'] if db_d else 0,
                'present_voters': db_present
            },
            'budget': {
                'ocr': ocr_d.get('budget'),
                'db': db_d['total_budget'] if db_d else None
            },
            'db_id': db_d['id'] if db_d else None
        }

    def get_summary(self, index):
        """קבלת תקציר לסעיף"""
        if index < 1 or index > len(self.discussion_matches):
            return None

        match = self.discussion_matches[index - 1]
        ocr_d = match['ocr']
        full_text = ocr_d.get('content', '') + '\n' + ocr_d.get('expert_opinion', '')

        return summarize_discussion(full_text)

    def set_unanimous_votes(self, discussion_index):
        """הגדרת הצבעה פה אחד - רק חברי מועצה (לא סגל)"""
        # תפקידים תחת מועצה: role_id עם parent_id=1 או role_id=1
        # מועצה=1, חבר מועצה=2, ראש העיר=3, סגן ראש העיר=4, חבר מועצה לשעבר=13
        council_role_ids = {1, 2, 3, 4, 13}

        db_present_council = [
            a for a in self.db_attendances
            if a['is_present'] and a.get('role_id') in council_role_ids
        ]

        self.unanimous_votes = {
            'discussion_index': discussion_index,
            'voters': [a['person_id'] for a in db_present_council],
            'voter_names': [a['name'] for a in db_present_council],
            'count': len(db_present_council)
        }

        print(f'🗳️ פה אחד: {len(db_present_council)} חברי מועצה מצביעים')

    def add_custom_category(self, category_name):
        """הוספת קטגוריה חדשה"""
        self.changes['categories_add'].append(category_name)
        add_custom_value('category', category_name)
        print(f'➕ קטגוריה תתווסף: {category_name}')

    def add_custom_discussion_type(self, type_name):
        """הוספת סוג דיון חדש"""
        self.changes['discussion_types_add'].append(type_name)
        add_custom_value('discussion_type', type_name)
        print(f'➕ סוג דיון יתווסף: {type_name}')

    def update_discussion(self, disc_id, **fields):
        """עדכון שדות בדיון"""
        update = {'id': disc_id}
        update.update(fields)
        self.changes['discussions_update'].append(update)
        print(f'✏️ דיון {disc_id} יעודכן')

    def add_new_discussion(self, index, title, category=None, discussion_type=None,
                           decision_status=None, decision_statement=None, summary=None,
                           yes_votes=0, no_votes=0, avoid_votes=0):
        """הוספת סעיף חדש ל-DB

        Args:
            decision_status: סטטוס (אושר/לא אושר/ירד מסדר היום)
            decision_statement: נוסח ההחלטה המלא
            summary: תקציר הדיון
        """
        # קבל את הנתונים מה-OCR אם קיימים
        ocr_data = {}
        if index <= len(self.discussion_matches):
            match = self.discussion_matches[index - 1]
            ocr_data = match.get('ocr', {})

        new_disc = {
            'issue_no': str(index),
            'title': title or ocr_data.get('content', '')[:200],
            'category': category,
            'discussion_type': discussion_type,
            'decision_status': decision_status,  # סטטוס: אושר/לא אושר
            'decision_statement': decision_statement or ocr_data.get('decision', ''),  # נוסח ההחלטה
            'summary': summary,  # תקציר
            'expert_opinion': ocr_data.get('expert_opinion', ''),
            'yes_counter': yes_votes,
            'no_counter': no_votes,
            'avoid_counter': avoid_votes
        }
        self.changes['discussions_add'].append(new_disc)
        print(f'➕ סעיף חדש יתווסף: {title[:50]}...')

    # ========== שלב 8: סיכום ==========
    def get_changes_summary(self):
        """קבלת סיכום שינויים"""
        summary = {
            'roles': len(self.changes['roles_add']),
            'persons': len(self.changes['persons_add']),
            'categories': len(self.changes['categories_add']),
            'discussion_types': len(self.changes['discussion_types_add']),
            'meeting_fields': len(self.changes['meeting']),
            'discussions_update': len(self.changes['discussions_update']),
            'unanimous_votes': self.unanimous_votes is not None
        }
        summary['total'] = sum(v if isinstance(v, int) else (1 if v else 0)
                               for v in summary.values())
        return summary

    def print_changes_summary(self):
        """הדפסת סיכום שינויים"""
        print('='*60)
        print('סיכום שינויים')
        print('='*60)

        if self.changes['roles_add']:
            print('\n🏷️ תפקידים:')
            for r in self.changes['roles_add']:
                print(f"  ➕ {r['name']}")

        if self.changes['persons_add']:
            print('\n👤 סגל להוספה:')
            for p in self.changes['persons_add']:
                print(f"  ➕ {p['name']} - {p['role']}")

        if self.changes['attendance_add']:
            print('\n✅ נוכחות להוספה:')
            for a in self.changes['attendance_add']:
                print(f"  ➕ {a.get('person_name', a.get('person_id'))}")

        if self.changes['attendance_remove']:
            print('\n🗑️ נוכחות להסרה:')
            for a in self.changes['attendance_remove']:
                print(f"  ➖ {a.get('name', a.get('person_id'))}")

        # הפרדה בין דחיות להחמצות
        rejections = [r for r in self.ocr_rejections if r.get('learning_type') == 'false_positive']
        misses = [r for r in self.ocr_rejections if r.get('learning_type') == 'false_negative']

        if rejections:
            print(f'\n❌ ערכי OCR שנדחו (false positive): {len(rejections)}')
            for r in rejections[:5]:
                print(f"  • {r['ocr_value']} ({r['reason']})")
            if len(rejections) > 5:
                print(f"  ... ועוד {len(rejections) - 5}")

        if misses:
            print(f'\n📝 ערכים שה-OCR החמיץ (false negative): {len(misses)}')
            for m in misses[:5]:
                role_info = f" ({m['role']})" if m.get('role') else ""
                print(f"  • {m['correct_value']}{role_info}")
            if len(misses) > 5:
                print(f"  ... ועוד {len(misses) - 5}")

        if self.changes['categories_add']:
            print('\n📂 קטגוריות:')
            for c in self.changes['categories_add']:
                print(f"  ➕ {c}")

        if self.changes['discussion_types_add']:
            print('\n📋 סוגי דיון:')
            for t in self.changes['discussion_types_add']:
                print(f"  ➕ {t}")

        if self.changes['meeting']:
            print('\n📅 פרטי ישיבה:')
            for k, v in self.changes['meeting'].items():
                print(f"  ✏️ {k}: {v}")

        if self.changes['discussions_update']:
            print('\n📝 דיונים לעדכון:')
            for u in self.changes['discussions_update']:
                print(f"  ✏️ ID {u['id']}")

        if self.changes['discussions_add']:
            print('\n➕ דיונים חדשים:')
            for d in self.changes['discussions_add']:
                print(f"  ➕ {d.get('title', '')[:40]}...")

        if self.changes['discussions_remove']:
            print('\n🗑️ דיונים למחיקה:')
            for d in self.changes['discussions_remove']:
                print(f"  ➖ ID {d['id']}")

        if self.unanimous_votes:
            print(f"\n🗳️ פה אחד: {self.unanimous_votes['count']} הצבעות")

        print('='*60)

    # ========== שלב 9: שמירה ==========
    def apply_changes(self):
        """ביצוע כל השינויים בDB"""
        session = get_session()

        try:
            # 1. תפקידים
            role_id_map = {}
            for role_data in self.changes['roles_add']:
                existing = session.query(Role).filter_by(name=role_data['name']).first()
                if existing:
                    role_id_map[role_data['name']] = existing.id
                else:
                    new_role = Role(name=role_data['name'])
                    session.add(new_role)
                    session.flush()
                    role_id_map[role_data['name']] = new_role.id
                    print(f'✅ תפקיד: {role_data["name"]}')

            # 2. אנשים (סגל)
            new_person_ids = {}  # לשמור ID של אנשים חדשים לצורך נוכחות
            for person_data in self.changes['persons_add']:
                existing = session.query(Person).filter_by(full_name=person_data['name']).first()
                if not existing:
                    role_id = role_id_map.get(person_data['role'])
                    new_person = Person(
                        full_name=person_data['name'],
                        role_id=role_id,
                        start_date=person_data['start_date'],
                        municipality_id=self.municipality_id if hasattr(self, 'municipality_id') else None
                    )
                    session.add(new_person)
                    session.flush()  # לקבל ID
                    new_person_ids[person_data['name']] = new_person.id
                    print(f'✅ אדם: {person_data["name"]}')

                    # הוספת נוכחות לאדם חדש
                    if person_data.get('add_attendance') and self.meeting_id:
                        session.add(Attendance(
                            person_id=new_person.id,
                            meeting_id=self.meeting_id,
                            is_present=True
                        ))
                        print(f'   ✅ נוכחות נוספה')
                else:
                    new_person_ids[person_data['name']] = existing.id
                    # הוספת נוכחות לאדם קיים אם נדרש
                    if person_data.get('add_attendance') and self.meeting_id:
                        existing_att = session.query(Attendance).filter_by(
                            person_id=existing.id,
                            meeting_id=self.meeting_id
                        ).first()
                        if not existing_att:
                            session.add(Attendance(
                                person_id=existing.id,
                                meeting_id=self.meeting_id,
                                is_present=True
                            ))
                            print(f'✅ נוכחות: {person_data["name"]}')

            # 2.5 נוכחות לאנשי סגל קיימים
            for att_data in self.changes['attendance_add']:
                existing_att = session.query(Attendance).filter_by(
                    person_id=att_data['person_id'],
                    meeting_id=self.meeting_id
                ).first()
                if not existing_att:
                    session.add(Attendance(
                        person_id=att_data['person_id'],
                        meeting_id=self.meeting_id,
                        is_present=att_data.get('is_present', True)
                    ))
                    print(f'✅ נוכחות: {att_data["person_name"]}')

            # 2.6 הסרת נוכחות
            for att_data in self.changes['attendance_remove']:
                if 'person_id' in att_data:
                    att_to_remove = session.query(Attendance).filter_by(
                        person_id=att_data['person_id'],
                        meeting_id=self.meeting_id
                    ).first()
                elif 'name' in att_data:
                    # חיפוש לפי שם
                    person = session.query(Person).filter_by(full_name=att_data['name']).first()
                    if person:
                        att_to_remove = session.query(Attendance).filter_by(
                            person_id=person.id,
                            meeting_id=self.meeting_id
                        ).first()
                    else:
                        att_to_remove = None

                if att_to_remove:
                    session.delete(att_to_remove)
                    print(f'🗑️ נוכחות הוסרה: {att_data.get("name", att_data.get("person_id"))}')

            # 3. קטגוריות
            for cat_name in self.changes['categories_add']:
                if not session.query(Category).filter_by(name=cat_name).first():
                    session.add(Category(name=cat_name))
                    print(f'✅ קטגוריה: {cat_name}')

            # 4. סוגי דיון
            for type_name in self.changes['discussion_types_add']:
                if not session.query(DiscussionType).filter_by(name=type_name).first():
                    session.add(DiscussionType(name=type_name))
                    print(f'✅ סוג דיון: {type_name}')

            # 5. פרטי ישיבה
            if self.changes['meeting'] and self.meeting_id:
                meeting = session.query(Meeting).filter_by(id=self.meeting_id).first()
                if meeting:
                    new_date = None
                    for field, value in self.changes['meeting'].items():
                        if field == 'meeting_date':
                            # עדכון תאריך ישיבה
                            for fmt in ['%d/%m/%Y', '%d/%m/%y']:
                                try:
                                    new_date = datetime.strptime(value, fmt)
                                    meeting.meeting_date = new_date
                                    break
                                except:
                                    pass
                        elif hasattr(meeting, field):
                            setattr(meeting, field, value)
                    print('✅ פרטי ישיבה')

                    # אם עודכן תאריך - עדכן גם את כל הדיונים של הישיבה
                    if new_date:
                        discussions = session.query(Discussion).filter_by(meeting_id=self.meeting_id).all()
                        for disc in discussions:
                            disc.discussion_date = new_date
                        print(f'✅ עודכן תאריך ב-{len(discussions)} דיונים')

            # 6. עדכון דיונים קיימים
            for upd in self.changes['discussions_update']:
                disc_id = upd.get('id')
                if disc_id:
                    disc = session.query(Discussion).filter_by(id=disc_id).first()
                    if disc:
                        for field, value in upd.items():
                            if field != 'id' and hasattr(disc, field):
                                setattr(disc, field, value)
                        print(f'✅ דיון {disc_id} עודכן')

            # 6.3 מחיקת דיונים
            for disc_data in self.changes['discussions_remove']:
                disc_id = disc_data.get('id')
                if disc_id:
                    disc = session.query(Discussion).filter_by(id=disc_id).first()
                    if disc:
                        # מחיקת הצבעות קשורות
                        session.query(Vote).filter_by(discussion_id=disc_id).delete()
                        # מחיקת הדיון
                        session.delete(disc)
                        print(f'🗑️ דיון {disc_id} נמחק (כולל הצבעות)')

            # 6.5 הוספת דיונים חדשים
            for new_disc in self.changes['discussions_add']:
                # קבל תאריך מהישיבה
                meeting = session.query(Meeting).filter_by(id=self.meeting_id).first()
                disc_date = meeting.meeting_date if meeting else None

                discussion = Discussion(
                    meeting_id=self.meeting_id,
                    issue_no=new_disc.get('issue_no'),
                    title=new_disc.get('title'),
                    decision=new_disc.get('decision_status'),  # סטטוס: אושר/לא אושר
                    decision_statement=new_disc.get('decision_statement'),  # נוסח ההחלטה
                    summary=new_disc.get('summary'),  # תקציר
                    expert_opinion=new_disc.get('expert_opinion'),
                    discussion_date=disc_date,
                    yes_counter=new_disc.get('yes_counter', 0),
                    no_counter=new_disc.get('no_counter', 0),
                    avoid_counter=new_disc.get('avoid_counter', 0)
                )
                session.add(discussion)
                session.flush()
                print(f'✅ סעיף חדש נוסף: {new_disc.get("title", "")[:40]}...')

            # 7. הצבעות פה אחד
            if self.unanimous_votes:
                disc_idx = self.unanimous_votes['discussion_index']
                if disc_idx <= len(self.discussion_matches):
                    match = self.discussion_matches[disc_idx - 1]
                    if match.get('db'):
                        discussion_id = match['db']['id']

                        votes_added = 0
                        for person_id in self.unanimous_votes['voters']:
                            existing = session.query(Vote).filter_by(
                                person_id=person_id,
                                discussion_id=discussion_id
                            ).first()

                            if not existing:
                                session.add(Vote(
                                    person_id=person_id,
                                    discussion_id=discussion_id,
                                    vote='yes'
                                ))
                                votes_added += 1

                        disc = session.query(Discussion).filter_by(id=discussion_id).first()
                        if disc:
                            disc.yes_counter = self.unanimous_votes['count']
                            disc.no_counter = 0
                            disc.avoid_counter = 0

                        print(f'✅ הצבעות: {votes_added} חדשות')

            session.commit()
            print('\n✅ כל השינויים נשמרו!')

            # איפוס
            self._reset_changes()
            return True

        except Exception as e:
            session.rollback()
            print(f'❌ שגיאה: {e}')
            return False
        finally:
            session.close()

    def _reset_changes(self):
        """איפוס השינויים"""
        self.changes = {
            'meeting': {},
            'attendance_add': [],
            'attendance_remove': [],
            'discussions_update': [],
            'discussions_add': [],
            'discussions_remove': [],
            'roles_add': [],
            'persons_add': [],
            'categories_add': [],
            'discussion_types_add': []
        }
        self.unanimous_votes = None

    # ========== פונקציות אינטראקטיביות ==========

    def interactive_meeting_fields(self):
        """שלב 4: טיפול אינטראקטיבי בפרטי ישיבה"""
        comp = self.get_meeting_comparison()

        print('═' * 60)
        print(f"ישיבה: {comp['title']['db']}")
        print(f"מספר דיונים בDB: {comp['discussions_count']}")
        print('═' * 60)

        fields_to_check = []

        # תאריך
        if comp['date']['ocr'] != comp['date']['db']:
            fields_to_check.append({
                'name': 'תאריך', 'field': 'meeting_date',
                'ocr': comp['date']['ocr'], 'db': comp['date']['db']
            })
            print(f"⚠️ תאריך:  OCR: {comp['date']['ocr']}  |  DB: {comp['date']['db']}")
        else:
            print(f"✅ תאריך:  {comp['date']['db']}")

        # סוג
        if comp['type']['ocr'] != comp['type']['db']:
            fields_to_check.append({
                'name': 'סוג', 'field': 'meeting_type',
                'ocr': comp['type']['ocr'], 'db': comp['type']['db']
            })
            print(f"⚠️ סוג:    OCR: {comp['type']['ocr']}  |  DB: {comp['type']['db']}")
        else:
            print(f"✅ סוג:    {comp['type']['db']}")

        # מספר
        if comp['number']['ocr'] != comp['number']['db']:
            fields_to_check.append({
                'name': 'מספר', 'field': 'meeting_no',
                'ocr': comp['number']['ocr'], 'db': comp['number']['db']
            })
            print(f"⚠️ מספר:   OCR: {comp['number']['ocr']}  |  DB: {comp['number']['db']}")
        else:
            print(f"✅ מספר:   {comp['number']['db']}")

        print('═' * 60)

        if not fields_to_check:
            print('\n✅ כל פרטי הישיבה תואמים!')
            return

        # טיפול בשדות שונים
        import sys
        print('\n⚠️ שדות עם הבדלים:')
        print("─" * 50)
        sys.stdout.flush()

        for idx, field in enumerate(fields_to_check, 1):
            prompt = f"\n[{idx}/{len(fields_to_check)}] {field['name']}\n"
            prompt += f"   OCR: {field['ocr']}\n"
            prompt += f"   DB:  {field['db']}\n"
            prompt += f"   [א]=OCR  [ב]=DB  [י]=ידני  [Enter]=דלג: "
            print(prompt, end='', flush=True)
            choice = input().strip()

            if choice in ['א', 'o', 'O']:
                self.update_meeting_field(field['field'], field['ocr'])
                self.report_field_correction(field['field'], field['ocr'], field['db'], field['ocr'],
                                             entity_type='meeting', entity_id=self.meeting_id)
                print(f"   ✓ OCR")
            elif choice in ['ב', 'd', 'D']:
                self.report_field_correction(field['field'], field['ocr'], field['db'], field['db'],
                                             entity_type='meeting', entity_id=self.meeting_id)
                print(f"   ✓ DB")
            elif choice in ['י', 'm', 'M']:
                manual = input(f"   ערך ידני: ").strip()
                if manual:
                    self.update_meeting_field(field['field'], manual)
                    self.report_field_correction(field['field'], field['ocr'], field['db'], manual,
                                                 entity_type='meeting', entity_id=self.meeting_id)
                    print(f"   ✓ {manual}")
                else:
                    print(f"   ⏭️ דילוג")
            else:
                print(f"   ⏭️ דילוג")

        print('\n' + '═' * 60)

    def interactive_attendance(self):
        """שלב 5: טיפול אינטראקטיבי בנוכחות"""
        att = self.get_attendance_comparison()

        print('═' * 60)
        print('נוכחות')
        print('═' * 60)

        # איסוף נתונים
        ocr_only = {'present': [], 'absent': []}
        db_only = {'present': [], 'absent': []}
        matched = {'present': 0, 'absent': 0}

        for item in att['present']:
            if item['status'] == 'matched':
                matched['present'] += 1
            elif item['status'] == 'ocr_only':
                ocr_only['present'].append(item['ocr'])
            elif item['status'] == 'db_only':
                db_only['present'].append(item['db'])

        for item in att['absent']:
            if item['status'] == 'matched':
                matched['absent'] += 1
            elif item['status'] == 'ocr_only':
                ocr_only['absent'].append(item['ocr'])
            elif item['status'] == 'db_only':
                db_only['absent'].append(item['db'])

        print(f"✅ נוכחים מותאמים: {matched['present']}")
        print(f"✅ נעדרים מותאמים: {matched['absent']}")

        has_issues = ocr_only['present'] or ocr_only['absent'] or db_only['present'] or db_only['absent']

        if not has_issues:
            print('\n✅ כל השמות מותאמים!')
            return

        import sys

        # OCR-only - חברי מועצה שנמצאו רק ב-OCR
        all_ocr_only = [(n, 'נוכח') for n in ocr_only['present']] + [(n, 'נעדר') for n in ocr_only['absent']]
        if all_ocr_only:
            print(f"\n⚠️ חברי מועצה חדשים מ-OCR ({len(all_ocr_only)}):")
            print("─" * 50)
            sys.stdout.flush()

            for idx, (name, status) in enumerate(all_ocr_only, 1):
                prompt = f"\n[{idx}/{len(all_ocr_only)}] {name} ({status})\n"
                prompt += f"   [כ]=הוסף  [ל]=דחה  [Enter]=דלג: "
                print(prompt, end='', flush=True)
                choice = input().strip()

                if choice in ['כ', 'y', 'Y']:
                    self.add_new_person(name, role=None, add_attendance=True)
                    print(f"   ✓ נוסף")
                elif choice in ['ל', 'n', 'N']:
                    self.reject_ocr_value('attendance', name, 'שגיאת OCR')
                    print(f"   ✗ נדחה")
                else:
                    print(f"   ⏭️ דילוג")

        # DB-only - חברי מועצה שקיימים ב-DB אבל לא נמצאו ב-OCR
        all_db_only = [(n, 'נוכח') for n in db_only['present']] + [(n, 'נעדר') for n in db_only['absent']]
        if all_db_only:
            print(f"\n⚠️ חברי מועצה ב-DB שלא נמצאו ב-OCR ({len(all_db_only)}):")
            print("─" * 50)
            sys.stdout.flush()

            for idx, (name, status) in enumerate(all_db_only, 1):
                prompt = f"\n[{idx}/{len(all_db_only)}] {name} ({status} ב-DB)\n"
                prompt += f"   [כ]=השאר  [ל]=הסר  [Enter]=דלג: "
                print(prompt, end='', flush=True)
                choice = input().strip()

                if choice in ['כ', 'y', 'Y']:
                    self.report_ocr_miss('attendance', name)
                    print(f"   ✓ נשמר")
                elif choice in ['ל', 'n', 'N']:
                    self.changes['attendance_remove'].append({'name': name})
                    print(f"   ✗ יוסר")
                else:
                    print(f"   ⏭️ דילוג")

        print('\n' + '═' * 60)

    def interactive_staff(self, debug=False):
        """שלב 5.5: טיפול אינטראקטיבי בסגל"""

        # דיבוג - הצג מידע על חיפוש סגל
        if debug and self.ocr_text:
            import re
            print('═' * 60)
            print('🔍 דיבוג - חיפוש סגל')
            print('═' * 60)

            # חפש קטע נוכחים/סגל
            officials = re.search(
                r'(?:נוכחים|סגל)[:\s]+(.*?)(?=על.*היום|סעיף|$)',
                self.ocr_text[:8000], re.DOTALL | re.IGNORECASE
            )
            if officials:
                print(f"\n✓ נמצא קטע 'נוכחים/סגל': {len(officials.group(1))} תווים")
                lines = officials.group(1).split('\n')[:10]
                for line in lines:
                    if line.strip():
                        print(f"   {line.strip()[:70]}")
            else:
                print("\n❌ לא נמצא קטע 'נוכחים/סגל'")

            # חפש תפקידים בכל הטקסט
            staff_keywords = ['מנכ"ל', 'מנכל', 'גזבר', 'יועמ"ש', 'יועץ משפטי', 'מהנדס', 'מבקר', 'מזכיר']
            print("\n📌 תפקידים שנמצאו בטקסט:")
            for kw in staff_keywords:
                if kw in self.ocr_text:
                    # מצא את השורה עם התפקיד
                    for line in self.ocr_text.split('\n'):
                        if kw in line:
                            print(f"   '{kw}': {line.strip()[:60]}")
                            break
            print('─' * 60)

        staff_data = self.extract_staff()

        print('═' * 60)
        print('סגל עירייה')
        print('═' * 60)

        # הצגת מה OCR מצא
        ocr_staff = staff_data.get('ocr_staff', [])
        db_staff = staff_data.get('db_staff', [])

        print(f"\n📋 סגל שחולץ מ-OCR ({len(ocr_staff)}):")
        if ocr_staff:
            for s in ocr_staff:
                print(f"   {s['name']} - {s['role']}")
        else:
            print("   (לא נמצא)")

        print(f"\n📋 סגל מנוכחות ב-DB ({len(db_staff)}):")
        if db_staff:
            for s in db_staff:
                status = '✓' if s['is_present'] else '✗'
                print(f"   {status} {s['name']} - {s['role']}")
        else:
            print("   (לא נמצא)")

        print('─' * 60)

        if not ocr_staff and not db_staff:
            print('\n⚠️ לא נמצא סגל ב-OCR וב-DB')
            return

        if staff_data['matched']:
            print(f"\n✅ סגל מותאם ({len(staff_data['matched'])}):")
            for s in staff_data['matched']:
                print(f"   {s['name']} - {s['role']}")

        has_issues = staff_data['ocr_only'] or staff_data['db_only']

        if not has_issues:
            print('\n✅ כל הסגל מותאם!')
            return

        import sys

        # OCR-only - סגל שנמצא רק ב-OCR
        if staff_data['ocr_only']:
            print(f"\n⚠️ סגל חדש מ-OCR ({len(staff_data['ocr_only'])}):")
            print("─" * 50)
            sys.stdout.flush()

            for idx, s in enumerate(staff_data['ocr_only'], 1):
                ocr_name = s['name']
                ocr_role = s['role']

                # הצגת הרשומה והאפשרויות בשורת האינפוט
                prompt = f"\n[{idx}/{len(staff_data['ocr_only'])}] {ocr_name} - {ocr_role}\n"
                prompt += f"   [כ]=הוסף  [ע]=ערוך  [ל]=דחה  [Enter]=דלג: "
                print(prompt, end='', flush=True)
                choice = input().strip()

                if choice in ['כ', 'y', 'Y']:
                    if not s.get('role_in_db') and ocr_role:
                        self.add_new_role(ocr_role)
                    self.add_new_person(ocr_name, ocr_role, add_attendance=True)
                    print(f"   ✓ נוסף")

                elif choice in ['ע', 'e', 'E']:
                    # עריכה - הצג תפקידים קיימים
                    print(f"\n   תפקידים קיימים: {', '.join(self.db_role_names[:10])}")
                    sys.stdout.flush()

                    new_name = input(f"   שם [{ocr_name}]: ").strip() or ocr_name
                    new_role = input(f"   תפקיד [{ocr_role}]: ").strip() or ocr_role

                    # בדוק אם התפקיד חדש
                    role_exists = any(r.lower() == new_role.lower() for r in self.db_role_names)
                    if not role_exists and new_role:
                        add_role = input(f"   תפקיד '{new_role}' חדש - להוסיף? [כ/ל]: ").strip()
                        if add_role in ['כ', 'y', 'Y']:
                            self.add_new_role(new_role)
                            print(f"   ✓ תפקיד נוסף")
                        else:
                            new_role = None

                    self.add_new_person(new_name, new_role, add_attendance=True)
                    print(f"   ✓ נוסף: {new_name} - {new_role or '(ללא תפקיד)'}")

                    if new_name != ocr_name or new_role != ocr_role:
                        self.report_field_correction('staff_name', ocr_name, None, new_name, 'person')
                        if new_role != ocr_role:
                            self.report_field_correction('staff_role', ocr_role, None, new_role, 'role')

                elif choice in ['ל', 'n', 'N']:
                    self.reject_ocr_value('person', ocr_name, 'שגיאת OCR')
                    print(f"   ✗ נדחה")

                else:
                    print(f"   ⏭️ דילוג")

        # DB-only
        if staff_data['db_only']:
            print(f"\n⚠️ סגל ב-DB שלא נמצא ב-OCR ({len(staff_data['db_only'])}):")
            print("─" * 50)
            sys.stdout.flush()

            for idx, s in enumerate(staff_data['db_only'], 1):
                status = 'נוכח' if s['is_present'] else 'נעדר'

                prompt = f"\n[{idx}/{len(staff_data['db_only'])}] {s['name']} - {s['role']} ({status})\n"
                prompt += f"   [כ]=השאר  [ל]=הסר  [Enter]=דלג: "
                print(prompt, end='', flush=True)
                choice = input().strip()

                if choice in ['כ', 'y', 'Y']:
                    self.report_ocr_miss('person', s['name'], role=s['role'])
                    print(f"   ✓ נשמר")
                elif choice in ['ל', 'n', 'N']:
                    self.changes['attendance_remove'].append({'person_id': s['person_id'], 'name': s['name']})
                    print(f"   ✗ יוסר")
                else:
                    print(f"   ⏭️ דילוג")

        print('\n' + '═' * 60)

    def interactive_discussions_matching(self):
        """שלב 6: התאמת סעיפי דיון"""
        result = self.match_discussions()

        print('═' * 60)
        print('התאמת סעיפים')
        print('═' * 60)

        disc_matched = [m for m in result['matches'] if m['db']]
        disc_ocr_only = [m for m in result['matches'] if not m['db']]
        disc_db_only = result['unmatched_db']

        if disc_matched:
            print(f"\n✅ סעיפים מותאמים ({len(disc_matched)}):")
            for m in disc_matched:
                print(f"   [{m['index']}] {m['ocr'].get('content', '')[:40]}... ({int(m['score']*100)}%)")

        has_issues = disc_ocr_only or disc_db_only

        if not has_issues:
            print('\n✅ כל הסעיפים מותאמים!')
            return

        import sys

        # OCR-only - סעיפים חדשים מ-OCR
        if disc_ocr_only:
            print(f"\n⚠️ סעיפים חדשים מ-OCR ({len(disc_ocr_only)}):")
            print("─" * 50)
            sys.stdout.flush()

            for idx, m in enumerate(disc_ocr_only, 1):
                title = m['ocr'].get('content', '')[:50]
                prompt = f"\n[{idx}/{len(disc_ocr_only)}] סעיף {m['index']}: {title}...\n"
                prompt += f"   [כ]=הוסף  [ל]=דחה  [Enter]=דלג: "
                print(prompt, end='', flush=True)
                choice = input().strip()

                if choice in ['כ', 'y', 'Y']:
                    print(f"   ✓ יתווסף")
                elif choice in ['ל', 'n', 'N']:
                    self.reject_ocr_value('discussion', title, 'שגיאת OCR')
                    m['rejected'] = True
                    print(f"   ✗ נדחה")
                else:
                    print(f"   ⏭️ דילוג")

        # DB-only - סעיפים שקיימים ב-DB אבל לא נמצאו ב-OCR
        if disc_db_only:
            print(f"\n⚠️ סעיפים ב-DB שלא נמצאו ב-OCR ({len(disc_db_only)}):")
            print("─" * 50)
            sys.stdout.flush()

            for idx, d in enumerate(disc_db_only, 1):
                title = (d['title'] or '')[:50]
                prompt = f"\n[{idx}/{len(disc_db_only)}] סעיף {d['issue_no']}: {title}... (ID:{d['id']})\n"
                prompt += f"   [כ]=השאר  [ל]=מחק  [Enter]=דלג: "
                print(prompt, end='', flush=True)
                choice = input().strip()

                if choice in ['כ', 'y', 'Y']:
                    self.report_ocr_miss('discussion', d['title'])
                    print(f"   ✓ נשמר")
                elif choice in ['ל', 'n', 'N']:
                    self.changes['discussions_remove'].append({'id': d['id']})
                    print(f"   ✗ יימחק")
                else:
                    print(f"   ⏭️ דילוג")

        print('\n' + '═' * 60)

    def interactive_discussion_edit(self, disc_index):
        """שלב 7: עריכת סעיף בודד"""
        # בדיקה אם נדחה
        if disc_index > len(self.discussion_matches):
            print(f'❌ סעיף {disc_index} לא קיים')
            return False

        match = self.discussion_matches[disc_index - 1]
        if match.get('rejected'):
            print(f'⏭️ סעיף {disc_index} נדחה')
            return False

        details = self.get_discussion_details(disc_index)
        if not details:
            print(f'❌ לא נמצאו פרטים לסעיף {disc_index}')
            return False

        summary = self.get_summary(disc_index)

        print('═' * 60)
        print(f"סעיף {details['index']}" + (f" (DB ID: {details['db_id']})" if details['db_id'] else " (חדש)"))
        print('═' * 60)

        # ערכי ברירת מחדל מ-OCR
        values = {
            'title': details['title']['ocr'][:200] if details['title']['ocr'] else '',
            'category': details['category']['suggested'],
            'discussion_type': details['discussion_type']['suggested'],
            'decision': details['decision']['status'],
            'decision_statement': details['decision']['full_text'],
            'summary': summary,
            'yes': details['votes']['ocr_yes'],
            'no': details['votes']['ocr_no'],
            'avoid': details['votes']['ocr_avoid'],
            'unanimous': details['votes']['is_unanimous']
        }

        # איסוף שדות שונים
        fields_diff = []

        # כותרת
        db_title = details['title'].get('db', '')
        if db_title and values['title'] != db_title:
            fields_diff.append(('כותרת', 'title', values['title'][:50], db_title[:50]))

        # סטטוס
        db_status = details['decision']['db_status'] or ''
        if db_status and values['decision'] != db_status:
            fields_diff.append(('סטטוס', 'decision', values['decision'], db_status))

        # נוסח
        db_statement = details['decision']['db_statement'] or ''
        if db_statement and values['decision_statement'] != db_statement:
            fields_diff.append(('נוסח', 'decision_statement',
                              (values['decision_statement'] or '')[:50], db_statement[:50]))

        # הצגה
        print(f"📝 כותרת: {values['title'][:60]}...")
        print(f"📂 קטגוריה: {values['category']}")
        print(f"📋 סוג: {values['discussion_type']}")
        print(f"✅ סטטוס: {values['decision']}")
        print(f"🗳️ הצבעות: {values['yes']}/{values['no']}/{values['avoid']}")
        if values['unanimous']:
            print("   💡 פה אחד!")

        # טיפול בשדות שונים
        import sys
        if fields_diff:
            print(f"\n⚠️ שדות עם הבדלים ({len(fields_diff)}):")
            print("─" * 50)
            sys.stdout.flush()

            for idx, (name, field, ocr_val, db_val) in enumerate(fields_diff, 1):
                prompt = f"\n[{idx}/{len(fields_diff)}] {name}\n"
                prompt += f"   OCR: {ocr_val}...\n"
                prompt += f"   DB:  {db_val}...\n"
                prompt += f"   [א]=OCR  [ב]=DB  [י]=ידני  [Enter]=דלג: "
                print(prompt, end='', flush=True)
                choice = input().strip()

                if choice in ['ב', 'd', 'D']:
                    if field == 'title':
                        values['title'] = details['title'].get('db', values['title'])
                    elif field == 'decision':
                        values['decision'] = db_status
                    elif field == 'decision_statement':
                        values['decision_statement'] = db_statement
                    self.report_field_correction(field, ocr_val, db_val, db_val,
                                               entity_type='discussion', entity_id=details['db_id'])
                    print(f"   ✓ DB")
                elif choice in ['י', 'm', 'M']:
                    manual = input(f"   ערך ידני: ").strip()
                    if manual:
                        values[field] = manual
                        self.report_field_correction(field, ocr_val, db_val, manual,
                                                   entity_type='discussion', entity_id=details['db_id'])
                        print(f"   ✓ {manual}")
                    else:
                        print(f"   ⏭️ דילוג")
                elif choice in ['א', 'o', 'O']:
                    self.report_field_correction(field, ocr_val, db_val, ocr_val,
                                               entity_type='discussion', entity_id=details['db_id'])
                    print(f"   ✓ OCR")
                else:
                    print(f"   ⏭️ דילוג")

        # הצבעה פה אחד
        if values['unanimous']:
            self.set_unanimous_votes(disc_index)
            values['yes'] = self.unanimous_votes['count']
            values['no'] = 0
            values['avoid'] = 0

        # שמירה
        if details['db_id']:
            self.update_discussion(
                details['db_id'],
                category=values['category'],
                discussion_type=values['discussion_type'],
                decision=values['decision'],
                decision_statement=values['decision_statement'],
                summary=values['summary'],
                yes_counter=values['yes'],
                no_counter=values['no'],
                avoid_counter=values['avoid']
            )
        else:
            self.add_new_discussion(
                index=disc_index,
                title=values['title'],
                category=values['category'],
                discussion_type=values['discussion_type'],
                decision_status=values['decision'],
                decision_statement=values['decision_statement'],
                summary=values['summary'],
                yes_votes=values['yes'],
                no_votes=values['no'],
                avoid_votes=values['avoid']
            )

        print(f'\n✅ סעיף {disc_index} נוסף לרשימת השינויים')
        return True

    def interactive_all_discussions(self):
        """שלב 7: עריכת כל הסעיפים ברצף"""
        import sys
        print('═' * 60)
        print('עריכת סעיפים')
        print('═' * 60)
        sys.stdout.flush()

        for i, match in enumerate(self.discussion_matches, 1):
            if match.get('rejected'):
                continue
            print(f"\n{'─' * 60}")
            print(f"   סעיף {i}/{len(self.discussion_matches)}")
            print(f"{'─' * 60}")
            sys.stdout.flush()
            self.interactive_discussion_edit(i)

            if i < len(self.discussion_matches):
                prompt = f"\n[Enter]=המשך לסעיף הבא  [ע]=עצור: "
                print(prompt, end='', flush=True)
                cont = input().strip()
                if cont in ['ע', 'n', 'N']:
                    print(f"⏹️ עצירה")
                    break

        print('\n' + '═' * 60)

    def interactive_save(self):
        """שלב 8: סיכום ושמירה"""
        import sys
        # הסרת כפילויות
        seen = set()
        self.changes['discussions_update'] = [
            u for u in self.changes['discussions_update']
            if u['id'] not in seen and not seen.add(u['id'])
        ]

        print('═' * 60)
        print('סיכום שינויים')
        print('═' * 60)

        self.print_changes_summary()
        sys.stdout.flush()

        prompt = f"\nלשמור את השינויים? [כ]=כן  [ל]=לא: "
        print(prompt, end='', flush=True)
        confirm = input().strip()
        if confirm in ['כ', 'y', 'Y']:
            self.apply_changes()
        else:
            print('⚠️ בוטל - השינויים לא נשמרו')

    def move_to_worked_on(self):
        """העברת קובץ ה-PDF לתיקיית worked_on"""
        import shutil

        if not self.pdf_path:
            print('❌ אין קובץ PDF לטפל בו')
            return False

        if not os.path.exists(self.pdf_path):
            print(f'❌ הקובץ לא נמצא: {self.pdf_path}')
            return False

        # תיקיית המקור
        source_dir = os.path.dirname(self.pdf_path)
        filename = os.path.basename(self.pdf_path)

        # תיקיית היעד
        worked_on_dir = os.path.join(source_dir, 'worked_on')

        # יצירת תיקיית worked_on אם לא קיימת
        if not os.path.exists(worked_on_dir):
            os.makedirs(worked_on_dir)
            print(f'📁 נוצרה תיקייה: worked_on')

        # העברת הקובץ
        dest_path = os.path.join(worked_on_dir, filename)

        # בדיקה אם קיים קובץ עם אותו שם ביעד
        if os.path.exists(dest_path):
            print(f'⚠️ קובץ קיים ביעד: {filename}')
            prompt = "   [ד]=דרוס  [ל]=בטל: "
            print(prompt, end='', flush=True)
            choice = input().strip()
            if choice not in ['ד', 'y', 'Y']:
                print('   ⏭️ לא הועבר')
                return False

        try:
            shutil.move(self.pdf_path, dest_path)
            print(f'✅ הקובץ הועבר: {filename} → worked_on/')
            self.pdf_path = dest_path  # עדכון הנתיב
            return True
        except Exception as e:
            print(f'❌ שגיאה בהעברה: {e}')
            return False

    def interactive_move_pdf(self):
        """שלב 9: שאלה אם להעביר את הקובץ לתיקיית worked_on"""
        import sys

        if not self.pdf_path:
            return

        print('═' * 60)
        print('סיום עבודה על הפרוטוקול')
        print('═' * 60)
        print(f'📄 קובץ: {os.path.basename(self.pdf_path)}')
        sys.stdout.flush()

        prompt = "\nלהעביר את הקובץ לתיקיית worked_on? [כ]=כן  [ל]=לא: "
        print(prompt, end='', flush=True)
        choice = input().strip()

        if choice in ['כ', 'y', 'Y']:
            self.move_to_worked_on()
        else:
            print('⏭️ הקובץ נשאר במקומו')


# פונקציות עזר להדפסה
def print_table(headers, rows, col_widths=None):
    """הדפסת טבלה"""
    if not col_widths:
        col_widths = [max(len(str(h)), max(len(str(r[i])) for r in rows))
                     for i, h in enumerate(headers)]

    header_line = ' | '.join(h.ljust(w) for h, w in zip(headers, col_widths))
    print(header_line)
    print('-' * len(header_line))
    for row in rows:
        print(' | '.join(str(c).ljust(w) for c, w in zip(row, col_widths)))
