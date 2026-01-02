"""
Display detailed meeting information from database
"""
import sys
from database import get_session
from models import Meeting, Discussion, Attendance, Person, Vote

def show_meeting_details(meeting_id):
    session = get_session()

    meeting = session.query(Meeting).filter_by(id=meeting_id).first()

    if not meeting:
        print(f'Meeting ID {meeting_id} not found in database')
        session.close()
        return

    print('=' * 70)
    print(f'פרוטוקול {meeting.meeting_no} - פרטים מבסיס הנתונים')
    print('=' * 70)
    print()
    print('=== פרטי הישיבה ===')
    print(f'מספר ישיבה: {meeting.meeting_no}')
    print(f'תאריך: {meeting.meeting_date.strftime("%d/%m/%Y")}')
    print(f'שם הועדה: {meeting.board.name if meeting.board else "לא זמין"}')
    print(f'כותרת: {meeting.title or "לא זמין"}')
    print()

    # Attendance
    attendances = session.query(Attendance).filter_by(meeting_id=meeting_id).all()
    present = [a for a in attendances if a.is_present == 1]
    absent = [a for a in attendances if a.is_present == 0]

    print(f'=== נוכחות ===')
    print(f'נוכחים: {len(present)} | נעדרים: {len(absent)}')
    print()
    print('נוכחים:')
    for a in present:
        person = session.query(Person).filter_by(id=a.person_id).first()
        if person:
            print(f'  + {person.full_name}')

    print()
    print('נעדרים:')
    for a in absent:
        person = session.query(Person).filter_by(id=a.person_id).first()
        if person:
            print(f'  - {person.full_name}')

    print()

    # Discussions
    discussions = session.query(Discussion).filter_by(meeting_id=meeting_id).all()
    print(f'=== סעיפים לדיון ({len(discussions)}) ===')
    print()

    for d in discussions:
        print(f'--- סעיף {d.issue_no} ---')
        print(f'כותרת: {d.title}')

        if d.expert_opinion:
            opinion_preview = d.expert_opinion[:150].replace('\n', ' ').replace('\r', ' ')
            print(f'דעת מומחה: {opinion_preview}...')

        if d.total_budget and d.total_budget > 0:
            print(f'תקציב: {d.total_budget:,.0f} ש"ח')

        if d.decision:
            decision_preview = d.decision[:150].replace('\n', ' ').replace('\r', ' ')
            print(f'החלטה: {decision_preview}...')

        # Vote counters
        if d.yes_counter or d.no_counter or d.avoid_counter:
            print(f'הצבעה: בעד={d.yes_counter or 0}, נגד={d.no_counter or 0}, נמנעו={d.avoid_counter or 0}')

        # Named votes
        votes = session.query(Vote).filter_by(discussion_id=d.id).all()
        if votes:
            print(f'הצבעות שמיות ({len(votes)}):')
            for v in votes:
                person = session.query(Person).filter_by(id=v.person_id).first()
                if person:
                    vote_text = 'בעד' if v.vote == 1 else 'נגד' if v.vote == -1 else 'נמנע'
                    print(f'  {vote_text}: {person.full_name}')

        print()

    print('=' * 70)
    session.close()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python show_meeting_details.py <meeting_id>')
        print('Example: python show_meeting_details.py 93')
        sys.exit(1)

    meeting_id = int(sys.argv[1])
    show_meeting_details(meeting_id)
