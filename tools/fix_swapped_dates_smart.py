"""
Smart date swap detection using meeting sequence and weekday analysis
Updates both meeting dates and discussion dates
"""
from datetime import datetime
from collections import defaultdict
from database import get_session
from models import Meeting, Discussion

def get_weekday_name_he(weekday):
    """Get Hebrew weekday name"""
    names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    # Adjust: Python weekday() returns 0=Monday, but we want Hebrew week starting Sunday
    # So: 0=Monday, 1=Tuesday, ..., 6=Sunday
    return names[weekday]

def analyze_meeting_sequence(meetings_by_year):
    """
    Analyze if meetings in a year follow chronological order
    Returns list of suspicious dates
    """
    suspicious = []

    for year, meetings in meetings_by_year.items():
        # Sort by meeting number (extract number from meeting_no like "1/19" -> 1)
        meetings.sort(key=lambda m: m.meeting_no or '')

        prev_month = 0
        for i, meeting in enumerate(meetings):
            if not meeting.meeting_date:
                continue

            current_month = meeting.meeting_date.month
            current_day = meeting.meeting_date.day

            # Skip if day > 12 (definitely correct)
            if current_day > 12:
                prev_month = current_month
                continue

            # Check if month goes backwards (suspicious)
            if i > 0 and current_month < prev_month - 1:  # Allow 1 month back for year transition
                suspicious.append({
                    'meeting': meeting,
                    'reason': f'chronology',
                    'details': f'Month {current_month} after month {prev_month} in sequence'
                })

            prev_month = current_month

    return suspicious

def fix_swapped_dates_smart(dry_run=True):
    """
    Smart detection of swapped dates using:
    1. Meeting sequence chronology
    2. Weekday analysis (most meetings on Monday)
    3. Only check dates where day <= 12
    """
    session = get_session()

    # Get all meetings with dates
    all_meetings = session.query(Meeting).filter(
        Meeting.meeting_date.isnot(None)
    ).order_by(Meeting.meeting_date).all()

    # Group by year
    meetings_by_year = defaultdict(list)
    for meeting in all_meetings:
        year = meeting.meeting_date.year
        meetings_by_year[year].append(meeting)

    # Analyze chronological sequence
    print("Analyzing meeting sequences by year...")
    sequence_suspicious = analyze_meeting_sequence(meetings_by_year)

    # Now analyze all meetings where day <= 12
    changes = []

    for meeting in all_meetings:
        date = meeting.meeting_date
        day = date.day
        month = date.month
        year = date.year

        # Only check if day <= 12 (possible swap)
        if day > 12:
            continue

        # Get swapped date
        try:
            swapped_date = datetime(year, day, month)
        except ValueError:
            # Swap would create invalid date
            continue

        # Calculate scores for both dates
        current_weekday = date.weekday()  # 0=Monday, 6=Sunday
        swapped_weekday = swapped_date.weekday()

        current_weekday_name = get_weekday_name_he(current_weekday)
        swapped_weekday_name = get_weekday_name_he(swapped_weekday)

        # Check if in sequence suspicious list
        in_sequence_suspicious = any(
            s['meeting'].id == meeting.id
            for s in sequence_suspicious
        )

        reasons = []
        should_swap = False

        # Criterion 1: Chronological sequence
        if in_sequence_suspicious:
            reasons.append(f'Wrong chronology')
            should_swap = True

        # Criterion 2: Weekday analysis
        # If current is NOT Monday but swapped IS Monday, very likely swap
        if current_weekday != 0 and swapped_weekday == 0:
            reasons.append(f'Current={current_weekday_name}, Swap=Mon')
            should_swap = True

        # Additional check: if current IS Monday but swap is also valid weekday,
        # check month progression
        # (Don't swap if current is already Monday unless chronology is wrong)

        if should_swap:
            changes.append({
                'meeting_id': meeting.id,
                'meeting_no': meeting.meeting_no,
                'old_date': date,
                'new_date': swapped_date,
                'old_formatted': date.strftime('%d/%m/%Y'),
                'new_formatted': swapped_date.strftime('%d/%m/%Y'),
                'old_weekday': current_weekday_name,
                'new_weekday': swapped_weekday_name,
                'reasons': ', '.join(reasons)
            })

    # Display changes
    if not changes:
        print("No dates need swapping based on smart analysis.")
        return

    # Calculate statistics by criterion
    chronology_only = sum(1 for c in changes if 'Wrong chronology' in c['reasons'] and 'Swap=Mon' not in c['reasons'])
    weekday_only = sum(1 for c in changes if 'Swap=Mon' in c['reasons'] and 'Wrong chronology' not in c['reasons'])
    both_criteria = sum(1 for c in changes if 'Wrong chronology' in c['reasons'] and 'Swap=Mon' in c['reasons'])

    print(f"\nFound {len(changes)} date(s) that should be swapped:\n")
    print("=" * 100)
    print("STATISTICS BY CRITERION:")
    print(f"  Chronology only:        {chronology_only:3d} dates")
    print(f"  Weekday (to Monday):    {weekday_only:3d} dates")
    print(f"  Both criteria:          {both_criteria:3d} dates")
    print(f"  {'-' * 40}")
    print(f"  TOTAL:                  {len(changes):3d} dates")
    print("=" * 100)
    print()

    for change in changes:
        print(f"Meeting ID: {change['meeting_id']} (Protocol #{change['meeting_no']})")
        print(f"  Current:  {change['old_date'].strftime('%Y-%m-%d')} ({change['old_formatted']}) - {change['old_weekday']}")
        print(f"  Swapped:  {change['new_date'].strftime('%Y-%m-%d')} ({change['new_formatted']}) - {change['new_weekday']}")
        print(f"  Reasons:  {change['reasons']}")
        print(f"  Action:   {'WOULD SWAP' if dry_run else 'SWAPPING'} day and month")
        print("-" * 100)

    # Apply changes if not dry run
    if not dry_run:
        # Count discussions that will be updated
        total_discussions = 0
        for change in changes:
            disc_count = session.query(Discussion).filter_by(meeting_id=change['meeting_id']).count()
            total_discussions += disc_count

        print()
        print("=" * 100)
        print(f"TOTAL CHANGES:")
        print(f"  Meetings:    {len(changes)}")
        print(f"  Discussions: {total_discussions}")
        print(f"  TOTAL:       {len(changes) + total_discussions}")
        print("=" * 100)

        print(f"\nProceeding to swap day/month for {len(changes)} meetings + {total_discussions} discussions...")
        print("(Using --apply flag, changes will be applied automatically)")
        print()

        meetings_updated = 0
        discussions_updated = 0

        for change in changes:
            meeting = session.query(Meeting).filter_by(id=change['meeting_id']).first()
            if meeting:
                # Update meeting date
                meeting.meeting_date = change['new_date']
                meetings_updated += 1

                # Update all discussions with same date as meeting
                discussions = session.query(Discussion).filter_by(meeting_id=meeting.id).all()
                for disc in discussions:
                    if disc.discussion_date and disc.discussion_date.date() == change['old_date'].date():
                        disc.discussion_date = change['new_date']
                        discussions_updated += 1

                print(f"[OK] Meeting {change['meeting_id']}: Updated meeting + {len([d for d in discussions if d.discussion_date and d.discussion_date.date() == change['old_date'].date()])} discussions")

        session.commit()
        print(f"\n[OK] Successfully swapped dates:")
        print(f"  - {meetings_updated} meetings")
        print(f"  - {discussions_updated} discussions")
        print(f"  - Total: {meetings_updated + discussions_updated}")
    else:
        # In dry run, also show discussion count
        total_discussions = 0
        for change in changes:
            disc_count = session.query(Discussion).filter_by(meeting_id=change['meeting_id']).count()
            total_discussions += disc_count

        print()
        print("=" * 100)
        print(f"WOULD UPDATE:")
        print(f"  Meetings:    {len(changes)}")
        print(f"  Discussions: {total_discussions}")
        print(f"  TOTAL:       {len(changes) + total_discussions}")
        print("=" * 100)
        print("\n[!] DRY RUN MODE - No changes were made")
        print("Run with --apply flag to apply changes")

    session.close()

if __name__ == "__main__":
    import sys

    # Check for --apply flag
    apply = '--apply' in sys.argv

    if apply:
        print("=" * 100)
        print("SMART DATE SWAP - APPLYING CHANGES")
        print("=" * 100)
        fix_swapped_dates_smart(dry_run=False)
    else:
        print("=" * 100)
        print("SMART DATE SWAP - DRY RUN")
        print("=" * 100)
        print("Using chronological sequence + weekday analysis")
        print("=" * 100)
        fix_swapped_dates_smart(dry_run=True)
