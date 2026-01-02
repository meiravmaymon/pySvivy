"""
DB Action Agent - מחלץ פעולות מתוכן דיונים ויוצר פקודות לבסיס הנתונים

הסוכן הזה:
1. מנתח את תוכן הדיונים וההחלטות
2. מזהה פעולות נדרשות (עדכון תאריכים, הוספת אנשים, שינוי תפקידים וכו')
3. יוצר פקודות SQL/ORM לביצוע
4. מציג למשתמש לאישור לפני ביצוע
"""

import re
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

# ייבוא המודלים
try:
    from database import get_session
    from models import Person, Role, Board, Meeting, Discussion, Attendance, Term, Faction
except ImportError:
    print("Warning: Could not import database models")


class ActionType(Enum):
    """סוגי פעולות אפשריות"""
    ADD_PERSON = "add_person"
    UPDATE_PERSON = "update_person"
    END_ROLE = "end_role"
    START_ROLE = "start_role"
    ADD_TO_BOARD = "add_to_board"
    REMOVE_FROM_BOARD = "remove_from_board"
    UPDATE_BOARD = "update_board"
    ADD_BUDGET = "add_budget"
    UPDATE_MEETING = "update_meeting"
    CUSTOM = "custom"


@dataclass
class DBAction:
    """פעולה בבסיס הנתונים"""
    action_type: ActionType
    table: str
    description: str  # תיאור בעברית
    params: Dict
    sql_preview: str  # הצגת ה-SQL לצפייה
    confidence: float  # רמת הביטחון בזיהוי (0-1)
    source_text: str  # הטקסט המקורי שממנו חולצה הפעולה
    requires_confirmation: bool = True


class DBActionAgent:
    """סוכן לחילוץ פעולות מדיונים"""

    def __init__(self):
        self.actions_queue: List[DBAction] = []
        self.executed_actions: List[DBAction] = []
        self.patterns = self._load_patterns()

    def _load_patterns(self) -> Dict:
        """טעינת דפוסי זיהוי"""
        return {
            # דפוסי סיום תפקיד
            'end_role': [
                r'סיום (?:כהונת|תפקיד|שירות)(?:ו|ה)?\s+(?:של\s+)?(?:מר|גב\'?|הגב\'?|ה?עובד)?\s*([א-ת\s\-\'\"]+)',
                r'(?:מר|גב\'?|הגב\'?)?\s*([א-ת\s\-\'\"]+)\s+(?:סיים|סיימה|מסיים|מסיימת)\s+(?:את\s+)?(?:תפקיד|כהונת)',
                r'הפסקת (?:עבודת|שירות|כהונת)\s+([א-ת\s\-\'\"]+)',
                r'פרישת?\s+([א-ת\s\-\'\"]+)',
            ],
            # דפוסי תחילת תפקיד
            'start_role': [
                r'מינוי\s+(?:מר|גב\'?|הגב\'?)?\s*([א-ת\s\-\'\"]+)\s+(?:ל|כ)(?:תפקיד)?\s*([א-ת\s\-\'\"]+)',
                r'(?:מר|גב\'?|הגב\'?)?\s*([א-ת\s\-\'\"]+)\s+(?:מונה|מונתה|ימונה|תמונה)\s+(?:ל|כ)\s*([א-ת\s\-\'\"]+)',
                r'אישור מינוי\s+([א-ת\s\-\'\"]+)',
            ],
            # דפוסי הארכת שירות
            'extend_service': [
                r'הארכת (?:שירות|כהונת|העסקת)(?:ו|ה)?\s+(?:של\s+)?(?:מר|גב\'?|העובד)?\s*([א-ת\s\-\'\"]+)',
                r'אישור הארכת שירותו של (?:העובד\s+)?(?:מר\s+)?([א-ת\s\-\'\"]+)',
            ],
            # דפוסי תקציב
            'budget': [
                r'(?:תקציב|סכום|עלות)\s+(?:של\s+)?(?:כ?-?\s*)?([\d,]+(?:\.\d+)?)\s*(?:ש"ח|שקל|₪)',
                r'([\d,]+(?:\.\d+)?)\s*(?:ש"ח|שקל|₪)',
                r'בסך\s+(?:של\s+)?([\d,]+(?:\.\d+)?)',
            ],
            # דפוסי הוספה לוועדה
            'add_to_board': [
                r'(?:הוספת|צירוף|מינוי)\s+(?:מר|גב\'?)?\s*([א-ת\s\-\'\"]+)\s+(?:ל|כחבר\s+)(?:ב)?ועד(?:ת|ה)\s+([א-ת\s\-\'\"]+)',
                r'([א-ת\s\-\'\"]+)\s+(?:יצורף|תצורף|יצטרף|תצטרף)\s+(?:ל|כחבר\s+)ועד(?:ת|ה)\s+([א-ת\s\-\'\"]+)',
            ],
            # דפוסי הסרה מוועדה
            'remove_from_board': [
                r'(?:הסרת|הוצאת)\s+(?:מר|גב\'?)?\s*([א-ת\s\-\'\"]+)\s+מועד(?:ת|ה)\s+([א-ת\s\-\'\"]+)',
                r'([א-ת\s\-\'\"]+)\s+(?:יוסר|תוסר|עוזב|עוזבת)\s+(?:את\s+)?ועד(?:ת|ה)\s+([א-ת\s\-\'\"]+)',
            ],
            # דפוסי תאריכים
            'dates': [
                r'(?:מתאריך|החל מ|מיום)\s+(\d{1,2}[./]\d{1,2}[./]\d{2,4})',
                r'(?:עד תאריך|עד ליום|עד)\s+(\d{1,2}[./]\d{1,2}[./]\d{2,4})',
                r'(?:ביום|בתאריך)\s+(\d{1,2}[./]\d{1,2}[./]\d{2,4})',
            ],
        }

    def analyze_discussion(self, discussion_text: str, discussion_title: str,
                          decision: str = None, meeting_date: datetime = None) -> List[DBAction]:
        """
        ניתוח דיון וחילוץ פעולות נדרשות

        Args:
            discussion_text: תוכן הדיון (expert_opinion או תמליל)
            discussion_title: כותרת הדיון
            decision: ההחלטה
            meeting_date: תאריך הישיבה

        Returns:
            רשימת פעולות שזוהו
        """
        actions = []
        full_text = f"{discussion_title}\n{discussion_text or ''}\n{decision or ''}"

        # זיהוי סיום תפקיד
        for pattern in self.patterns['end_role']:
            matches = re.finditer(pattern, full_text, re.IGNORECASE)
            for match in matches:
                person_name = match.group(1).strip() if match.groups() else None
                if person_name:
                    actions.append(self._create_end_role_action(
                        person_name, meeting_date, match.group(0)
                    ))

        # זיהוי הארכת שירות
        for pattern in self.patterns['extend_service']:
            matches = re.finditer(pattern, full_text, re.IGNORECASE)
            for match in matches:
                person_name = match.group(1).strip() if match.groups() else None
                if person_name:
                    actions.append(self._create_extend_service_action(
                        person_name, meeting_date, match.group(0)
                    ))

        # זיהוי מינוי חדש
        for pattern in self.patterns['start_role']:
            matches = re.finditer(pattern, full_text, re.IGNORECASE)
            for match in matches:
                groups = match.groups()
                if len(groups) >= 1:
                    person_name = groups[0].strip()
                    role_name = groups[1].strip() if len(groups) > 1 else None
                    actions.append(self._create_start_role_action(
                        person_name, role_name, meeting_date, match.group(0)
                    ))

        # זיהוי הוספה לוועדה
        for pattern in self.patterns['add_to_board']:
            matches = re.finditer(pattern, full_text, re.IGNORECASE)
            for match in matches:
                groups = match.groups()
                if len(groups) >= 2:
                    person_name = groups[0].strip()
                    board_name = groups[1].strip()
                    actions.append(self._create_add_to_board_action(
                        person_name, board_name, meeting_date, match.group(0)
                    ))

        # זיהוי תקציב
        budget_amount = self._extract_budget(full_text)
        if budget_amount:
            actions.append(self._create_budget_action(
                budget_amount, discussion_title, full_text[:100]
            ))

        return actions

    def _create_end_role_action(self, person_name: str, end_date: datetime,
                                source_text: str) -> DBAction:
        """יצירת פעולת סיום תפקיד"""
        date_str = end_date.strftime('%Y-%m-%d') if end_date else 'CURRENT_DATE'

        return DBAction(
            action_type=ActionType.END_ROLE,
            table='persons',
            description=f"סיום תפקיד: {person_name}",
            params={
                'person_name': person_name,
                'end_date': date_str
            },
            sql_preview=f"UPDATE persons SET end_date = '{date_str}' WHERE full_name LIKE '%{person_name}%'",
            confidence=0.7,
            source_text=source_text
        )

    def _create_extend_service_action(self, person_name: str, meeting_date: datetime,
                                      source_text: str) -> DBAction:
        """יצירת פעולת הארכת שירות"""
        return DBAction(
            action_type=ActionType.UPDATE_PERSON,
            table='persons',
            description=f"הארכת שירות: {person_name}",
            params={
                'person_name': person_name,
                'action': 'extend_service',
                'meeting_date': meeting_date.strftime('%Y-%m-%d') if meeting_date else None
            },
            sql_preview=f"-- הארכת שירות ל-{person_name}, יש לעדכן end_date",
            confidence=0.8,
            source_text=source_text
        )

    def _create_start_role_action(self, person_name: str, role_name: str,
                                  start_date: datetime, source_text: str) -> DBAction:
        """יצירת פעולת מינוי לתפקיד"""
        date_str = start_date.strftime('%Y-%m-%d') if start_date else 'CURRENT_DATE'

        return DBAction(
            action_type=ActionType.START_ROLE,
            table='persons',
            description=f"מינוי: {person_name} ל{role_name}" if role_name else f"מינוי: {person_name}",
            params={
                'person_name': person_name,
                'role_name': role_name,
                'start_date': date_str
            },
            sql_preview=f"-- מינוי {person_name} לתפקיד {role_name or 'חדש'}",
            confidence=0.6,
            source_text=source_text
        )

    def _create_add_to_board_action(self, person_name: str, board_name: str,
                                    start_date: datetime, source_text: str) -> DBAction:
        """יצירת פעולת הוספה לוועדה"""
        date_str = start_date.strftime('%Y-%m-%d') if start_date else 'CURRENT_DATE'

        return DBAction(
            action_type=ActionType.ADD_TO_BOARD,
            table='person_board',
            description=f"הוספה לוועדה: {person_name} -> {board_name}",
            params={
                'person_name': person_name,
                'board_name': board_name,
                'start_date': date_str
            },
            sql_preview=f"INSERT INTO person_board (person_id, board_id, start_date) VALUES (?, ?, '{date_str}')",
            confidence=0.7,
            source_text=source_text
        )

    def _create_budget_action(self, amount: float, title: str, source_text: str) -> DBAction:
        """יצירת פעולת עדכון תקציב"""
        return DBAction(
            action_type=ActionType.ADD_BUDGET,
            table='discussions',
            description=f"תקציב: {amount:,.0f} ש\"ח",
            params={
                'amount': amount,
                'title': title
            },
            sql_preview=f"UPDATE discussions SET total_budget = {amount} WHERE title LIKE '%{title[:30]}%'",
            confidence=0.9,
            source_text=source_text
        )

    def _extract_budget(self, text: str) -> Optional[float]:
        """חילוץ סכום תקציב מטקסט"""
        for pattern in self.patterns['budget']:
            matches = re.findall(pattern, text)
            for match in matches:
                try:
                    # ניקוי פסיקים והמרה למספר
                    amount_str = match.replace(',', '').replace(' ', '')
                    amount = float(amount_str)
                    if amount > 100:  # התעלמות מסכומים קטנים מדי
                        return amount
                except ValueError:
                    continue
        return None

    def analyze_all_discussions(self, discussions: List[Dict],
                               meeting_date: datetime = None) -> List[DBAction]:
        """
        ניתוח כל הדיונים של ישיבה

        Args:
            discussions: רשימת דיונים
            meeting_date: תאריך הישיבה

        Returns:
            רשימת כל הפעולות שזוהו
        """
        all_actions = []

        for disc in discussions:
            title = disc.get('title', '')
            text = disc.get('expert_opinion', '') or disc.get('content', '')
            decision = disc.get('decision', '')

            actions = self.analyze_discussion(title, text, decision, meeting_date)
            all_actions.extend(actions)

        # הסרת כפילויות
        unique_actions = []
        seen = set()
        for action in all_actions:
            key = (action.action_type, action.description)
            if key not in seen:
                seen.add(key)
                unique_actions.append(action)

        self.actions_queue = unique_actions
        return unique_actions

    def execute_action(self, action: DBAction, session=None) -> Tuple[bool, str]:
        """
        ביצוע פעולה בבסיס הנתונים

        Args:
            action: הפעולה לביצוע
            session: סשן DB (אופציונלי)

        Returns:
            tuple: (הצלחה, הודעה)
        """
        close_session = False
        if session is None:
            session = get_session()
            close_session = True

        try:
            if action.action_type == ActionType.END_ROLE:
                return self._execute_end_role(action, session)
            elif action.action_type == ActionType.START_ROLE:
                return self._execute_start_role(action, session)
            elif action.action_type == ActionType.ADD_TO_BOARD:
                return self._execute_add_to_board(action, session)
            elif action.action_type == ActionType.ADD_BUDGET:
                return self._execute_add_budget(action, session)
            else:
                return False, f"סוג פעולה לא נתמך: {action.action_type}"

        except Exception as e:
            session.rollback()
            return False, f"שגיאה: {str(e)}"

        finally:
            if close_session:
                session.close()

    def _execute_end_role(self, action: DBAction, session) -> Tuple[bool, str]:
        """ביצוע סיום תפקיד"""
        person_name = action.params.get('person_name')
        end_date_str = action.params.get('end_date')

        # חיפוש האדם
        person = session.query(Person).filter(
            Person.full_name.contains(person_name)
        ).first()

        if not person:
            return False, f"לא נמצא אדם בשם: {person_name}"

        # עדכון תאריך סיום
        if end_date_str and end_date_str != 'CURRENT_DATE':
            person.end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        else:
            person.end_date = datetime.now()

        session.commit()
        self.executed_actions.append(action)
        return True, f"עודכן תאריך סיום ל-{person.full_name}"

    def _execute_start_role(self, action: DBAction, session) -> Tuple[bool, str]:
        """ביצוע מינוי לתפקיד"""
        person_name = action.params.get('person_name')
        role_name = action.params.get('role_name')
        start_date_str = action.params.get('start_date')

        # חיפוש האדם
        person = session.query(Person).filter(
            Person.full_name.contains(person_name)
        ).first()

        if not person:
            # יצירת אדם חדש
            person = Person(
                full_name=person_name,
                title=person_name,
                start_date=datetime.strptime(start_date_str, '%Y-%m-%d') if start_date_str != 'CURRENT_DATE' else datetime.now()
            )
            session.add(person)
            session.flush()

        # עדכון תאריך התחלה
        if start_date_str and start_date_str != 'CURRENT_DATE':
            person.start_date = datetime.strptime(start_date_str, '%Y-%m-%d')

        # חיפוש תפקיד אם צוין
        if role_name:
            role = session.query(Role).filter(
                Role.name.contains(role_name)
            ).first()
            if role:
                person.role_id = role.id

        session.commit()
        self.executed_actions.append(action)
        return True, f"מינוי {person.full_name} בוצע בהצלחה"

    def _execute_add_to_board(self, action: DBAction, session) -> Tuple[bool, str]:
        """ביצוע הוספה לוועדה"""
        from sqlalchemy import text

        person_name = action.params.get('person_name')
        board_name = action.params.get('board_name')
        start_date_str = action.params.get('start_date')

        # חיפוש האדם
        person = session.query(Person).filter(
            Person.full_name.contains(person_name)
        ).first()

        if not person:
            return False, f"לא נמצא אדם בשם: {person_name}"

        # חיפוש הוועדה
        board = session.query(Board).filter(
            Board.title.contains(board_name)
        ).first()

        if not board:
            return False, f"לא נמצאה ועדה: {board_name}"

        # הוספה לטבלת הקשר
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d') if start_date_str != 'CURRENT_DATE' else datetime.now()

        # בדיקה אם כבר קיים
        existing = session.execute(text(
            "SELECT 1 FROM person_board WHERE person_id = :pid AND board_id = :bid"
        ), {'pid': person.id, 'bid': board.id}).fetchone()

        if existing:
            return False, f"{person.full_name} כבר חבר בוועדת {board.title}"

        session.execute(text(
            "INSERT INTO person_board (person_id, board_id, start_date) VALUES (:pid, :bid, :date)"
        ), {'pid': person.id, 'bid': board.id, 'date': start_date})

        session.commit()
        self.executed_actions.append(action)
        return True, f"{person.full_name} נוסף לוועדת {board.title}"

    def _execute_add_budget(self, action: DBAction, session) -> Tuple[bool, str]:
        """ביצוע עדכון תקציב"""
        amount = action.params.get('amount')
        title = action.params.get('title')

        # חיפוש הדיון
        discussion = session.query(Discussion).filter(
            Discussion.title.contains(title[:30])
        ).first()

        if not discussion:
            return False, f"לא נמצא דיון: {title[:30]}"

        discussion.total_budget = amount
        session.commit()
        self.executed_actions.append(action)
        return True, f"עודכן תקציב: {amount:,.0f} ש\"ח"

    def get_pending_actions(self) -> List[Dict]:
        """קבלת רשימת פעולות ממתינות"""
        return [
            {
                'type': a.action_type.value,
                'description': a.description,
                'table': a.table,
                'params': a.params,
                'sql_preview': a.sql_preview,
                'confidence': a.confidence,
                'source_text': a.source_text[:100] + '...' if len(a.source_text) > 100 else a.source_text
            }
            for a in self.actions_queue
        ]

    def clear_queue(self):
        """ניקוי תור הפעולות"""
        self.actions_queue = []


# פונקציות עזר לשימוש מהמחברת

def analyze_meeting_discussions(meeting_id: int) -> List[Dict]:
    """
    ניתוח כל הדיונים של ישיבה

    Args:
        meeting_id: מזהה הישיבה

    Returns:
        רשימת פעולות שזוהו
    """
    session = get_session()
    meeting = session.query(Meeting).filter_by(id=meeting_id).first()

    if not meeting:
        session.close()
        return []

    discussions = session.query(Discussion).filter_by(meeting_id=meeting_id).all()

    disc_list = [{
        'title': d.title,
        'expert_opinion': d.expert_opinion,
        'decision': d.decision
    } for d in discussions]

    session.close()

    agent = DBActionAgent()
    actions = agent.analyze_all_discussions(disc_list, meeting.meeting_date)

    return agent.get_pending_actions()


def get_action_agent() -> DBActionAgent:
    """קבלת מופע של סוכן הפעולות"""
    return DBActionAgent()


if __name__ == '__main__':
    # דוגמה לשימוש
    agent = DBActionAgent()

    # דוגמה לדיון
    sample_discussion = """
    אישור הארכת שירותו של העובד מר יהודה עובד בתפקיד ראש צוות תחזוקה באיכות הסביבה.
    למר יהודה עובד ימלאו 70 ביום 28/08/2019.
    בהתאם לחוזר מנכ"ל 4/2014 נדרש אישור מועצה להארכת שירותו.
    התקציב הנדרש: 150,000 ש"ח.
    """

    actions = agent.analyze_discussion(
        sample_discussion,
        "הארכת שירות - יהודה עובד",
        "אושר",
        datetime(2019, 7, 1)
    )

    print("פעולות שזוהו:")
    for action in actions:
        print(f"  - {action.description}")
        print(f"    SQL: {action.sql_preview}")
        print(f"    ביטחון: {action.confidence:.0%}")
        print()
