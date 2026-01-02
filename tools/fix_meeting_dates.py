"""
Script to fix incorrectly imported meeting dates
Run this AFTER import_data.py to correct known date errors
"""
from database import get_session
from models import Meeting
from datetime import datetime

# Known date corrections
# Format: meeting_id: (incorrect_date, correct_date, notes)
DATE_FIXES = {
    30: {
        'incorrect': datetime(2015, 1, 6),
        'correct': datetime(2015, 6, 1),
        'meeting_no': '815',
        'notes': 'Meeting 8/15 should be June 1, 2015, not January 6, 2015'
    },
    # Add more corrections here as needed
    # Example:
    # 31: {
    #     'incorrect': datetime(2015, 2, 9),
    #     'correct': datetime(2015, 9, 2),
    #     'meeting_no': '915',
    #     'notes': 'Meeting 9/15 correction'
    # },
}

def fix_meeting_dates():
    """Fix known incorrect meeting dates"""
    session = get_session()

    print("=" * 80)
    print("Fixing Meeting Dates")
    print("=" * 80)

    fixes_applied = 0

    for meeting_id, fix_info in DATE_FIXES.items():
        meeting = session.query(Meeting).filter(Meeting.id == meeting_id).first()

        if not meeting:
            print(f"\n[!] Meeting {meeting_id} not found - skipping")
            continue

        # Verify current date matches what we expect to be wrong
        if meeting.meeting_date != fix_info['incorrect']:
            print(f"\n[!] Meeting {meeting_id} ({fix_info['meeting_no']}):")
            print(f"   Expected incorrect date: {fix_info['incorrect'].strftime('%Y-%m-%d')}")
            print(f"   But found: {meeting.meeting_date.strftime('%Y-%m-%d')}")
            print(f"   Skipping this fix")
            continue

        # Apply fix
        old_date = meeting.meeting_date
        meeting.meeting_date = fix_info['correct']

        print(f"\n[OK] Fixed Meeting {meeting_id} ({fix_info['meeting_no']}):")
        print(f"   From: {old_date.strftime('%d/%m/%Y')} ({old_date.strftime('%A')})")
        print(f"   To:   {fix_info['correct'].strftime('%d/%m/%Y')} ({fix_info['correct'].strftime('%A')})")
        print(f"   Note: {fix_info['notes']}")

        fixes_applied += 1

    if fixes_applied > 0:
        print(f"\n{'=' * 80}")
        print(f"Committing {fixes_applied} date fix(es) to database...")
        session.commit()
        print("[OK] All fixes applied successfully!")
    else:
        print("\n[!] No fixes were applied")

    session.close()
    print("=" * 80)

if __name__ == '__main__':
    fix_meeting_dates()
