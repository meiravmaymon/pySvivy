"""
Manual protocol entry and comparison with database
For scanned PDFs where OCR is not available
"""
from database import get_session
from models import Meeting, Discussion, Vote, Attendance, Person
import json
from datetime import datetime

# Manual entry for Protocol 8-15 (Meeting ID 30)
PROTOCOL_8_15 = {
    'meeting_info': {
        'meeting_no': '815',
        'date': '2015-06-01',
        'title': 'ישיבת מועצת העיר יהוד מונוסון 8/15',
        'board': 'מועצת העיר'
    },
    'attendance': {
        'present': [
            # הזן כאן את רשימת הנוכחים מהפרוטוקול
        ],
        'absent': [
            # הזן כאן את רשימת הנעדרים מהפרוטוקול
        ]
    },
    'discussions': [
        # הזן כאן את סעיפי הדיון מהפרוטוקול
        # {
        #     'number': 1,
        #     'title': 'כותרת הסעיף',
        #     'decision': 'ההחלטה',
        #     'votes': {'yes': 7, 'no': 0, 'avoid': 0, 'missing': 8}
        # }
    ]
}

def compare_protocol_with_db(protocol_data, meeting_id):
    """Compare manually entered protocol data with database"""
    session = get_session()

    print("=" * 100)
    print(f"PROTOCOL COMPARISON - Meeting ID {meeting_id}")
    print("=" * 100)

    # Get meeting from DB
    meeting = session.query(Meeting).filter(Meeting.id == meeting_id).first()

    if not meeting:
        print(f"\n[!] ERROR: Meeting ID {meeting_id} not found in database!")
        session.close()
        return

    # Meeting Info Comparison
    print("\n### MEETING INFO ###")
    print(f"\nManual Entry:")
    print(f"  Meeting No: {protocol_data['meeting_info']['meeting_no']}")
    print(f"  Date: {protocol_data['meeting_info']['date']}")
    print(f"  Title: {protocol_data['meeting_info']['title']}")

    print(f"\nDatabase:")
    print(f"  Meeting No: {meeting.meeting_no}")
    print(f"  Date: {meeting.meeting_date.strftime('%Y-%m-%d')}")
    print(f"  Title: {meeting.title}")

    matches = []
    discrepancies = []

    if protocol_data['meeting_info']['meeting_no'] == meeting.meeting_no:
        matches.append("Meeting number matches")
    else:
        discrepancies.append(f"Meeting number: Manual={protocol_data['meeting_info']['meeting_no']}, DB={meeting.meeting_no}")

    if protocol_data['meeting_info']['date'] == meeting.meeting_date.strftime('%Y-%m-%d'):
        matches.append("Date matches")
    else:
        discrepancies.append(f"Date: Manual={protocol_data['meeting_info']['date']}, DB={meeting.meeting_date.strftime('%Y-%m-%d')}")

    # Attendance Comparison
    print("\n### ATTENDANCE ###")

    db_attendances = session.query(Attendance).filter(Attendance.meeting_id == meeting_id).all()
    db_present = [att.person.full_name for att in db_attendances if att.is_present and att.person]
    db_absent = [att.person.full_name for att in db_attendances if not att.is_present and att.person]

    print(f"\nManual Entry:")
    print(f"  Present: {len(protocol_data['attendance']['present'])} members")
    for name in protocol_data['attendance']['present']:
        print(f"    - {name}")
    print(f"  Absent: {len(protocol_data['attendance']['absent'])} members")
    for name in protocol_data['attendance']['absent']:
        print(f"    - {name}")

    print(f"\nDatabase:")
    print(f"  Present: {len(db_present)} members")
    for name in db_present:
        print(f"    - {name}")
    print(f"  Absent: {len(db_absent)} members")
    for name in db_absent:
        print(f"    - {name}")

    if len(protocol_data['attendance']['present']) == len(db_present):
        matches.append(f"Present count matches: {len(db_present)}")
    else:
        discrepancies.append(f"Present count: Manual={len(protocol_data['attendance']['present'])}, DB={len(db_present)}")

    if len(protocol_data['attendance']['absent']) == len(db_absent):
        matches.append(f"Absent count matches: {len(db_absent)}")
    else:
        discrepancies.append(f"Absent count: Manual={len(protocol_data['attendance']['absent'])}, DB={len(db_absent)}")

    # Discussions Comparison
    print("\n### DISCUSSIONS ###")

    db_discussions = session.query(Discussion).filter(Discussion.meeting_id == meeting_id).all()

    print(f"\nManual Entry: {len(protocol_data['discussions'])} discussions")
    for disc in protocol_data['discussions']:
        print(f"  #{disc.get('number', '?')}: {disc.get('title', 'No title')[:60]}")
        if 'votes' in disc:
            print(f"      Votes: Yes={disc['votes'].get('yes', 0)}, No={disc['votes'].get('no', 0)}, Avoid={disc['votes'].get('avoid', 0)}")

    print(f"\nDatabase: {len(db_discussions)} discussions")
    for disc in db_discussions:
        print(f"  #{disc.id}: {disc.title[:60]}")
        print(f"      Votes: Yes={disc.yes_counter}, No={disc.no_counter}, Avoid={disc.avoid_counter}")

    if len(protocol_data['discussions']) == len(db_discussions):
        matches.append(f"Discussion count matches: {len(db_discussions)}")
    else:
        discrepancies.append(f"Discussion count: Manual={len(protocol_data['discussions'])}, DB={len(db_discussions)}")

    # Summary
    print("\n### COMPARISON SUMMARY ###")

    if matches:
        print(f"\n[OK] MATCHES ({len(matches)}):")
        for match in matches:
            print(f"  - {match}")

    if discrepancies:
        print(f"\n[!] DISCREPANCIES ({len(discrepancies)}):")
        for disc in discrepancies:
            print(f"  - {disc}")

    print("\n" + "=" * 100)

    session.close()

    return {
        'matches': matches,
        'discrepancies': discrepancies
    }

if __name__ == '__main__':
    print("Please fill in the PROTOCOL_8_15 dictionary with data from the PDF")
    print("Then run this script to compare with database\n")

    # Uncomment to run comparison
    # result = compare_protocol_with_db(PROTOCOL_8_15, 30)
