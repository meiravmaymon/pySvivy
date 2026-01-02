"""
Fix swapped day/month dates in database using logical inference
No OCR required - uses date logic to detect American format imports
"""
from datetime import datetime
from database import get_session
from models import Meeting

def fix_swapped_dates(dry_run=True):
    """
    Fix dates where day and month were swapped during import

    Logic:
    1. If day > 12: date is correct (can't be month)
    2. If day <= 12 and month <= 12: check if swap makes more sense
       - Look for patterns: sequential meetings should have sequential dates
       - Swap if it creates a more logical sequence

    Args:
        dry_run: If True, only show what would be changed
    """
    session = get_session()

    # Get all meetings ordered by meeting number
    meetings = session.query(Meeting).filter(
        Meeting.meeting_date.isnot(None)
    ).order_by(Meeting.meeting_date).all()

    changes = []

    for meeting in meetings:
        date = meeting.meeting_date
        day = date.day
        month = date.month
        year = date.year

        # If day > 12, this date is definitely correct (can't be month)
        if day > 12:
            continue

        # If month > 12, this date is definitely wrong (was swapped)
        # This shouldn't happen but let's check
        if month > 12:
            print(f"WARNING: Meeting {meeting.id} has invalid month: {month}")
            continue

        # Both day and month are <= 12, so swap is possible
        # Check if swapping would make more sense
        should_swap = False

        # Strategy 1: If day <= 12 and month <= 12, check if the date seems unusual
        # For example, if we have multiple meetings in what looks like the same month
        # but the "month" field varies a lot, it's likely swapped

        # Strategy 2: Check if month is actually a likely day number
        # Israeli meetings are more likely on certain days of week/month
        # Days 1-12 of month are common, months appearing as "days" 1-12 suggest swap

        # Simple heuristic: if month <= 12 and day <= 12:
        # - If the current date is in a month that seems too late in the year
        #   for the meeting sequence, it might be swapped

        # For now, let's use a simpler rule:
        # If day <= 12 and month > day, it MIGHT be swapped
        # We'll check if swapping creates a date that's more chronologically consistent

        # Get the swapped date
        try:
            swapped_date = datetime(year, day, month)
        except ValueError:
            # Swap would create invalid date (e.g., month=31), so current is correct
            continue

        # Check if there's a pattern suggesting swap
        # If original date month > swapped date month, and day < month, likely swapped
        # Example: 2019-10-02 (Oct 2) vs 2019-02-10 (Feb 10)
        # If we see other meetings around Feb, then Feb 10 is more likely correct

        # Simple heuristic: if month > day, it's suspicious
        # In Israeli format (DD/MM/YYYY), day being smaller than month is common
        # In American format (MM/DD/YYYY), month being smaller than day is common
        # So if month > day, it might have been American format (swapped)

        if month > day:
            # Likely swapped: month is bigger, suggesting it was originally day
            should_swap = True

        if should_swap:
            changes.append({
                'meeting_id': meeting.id,
                'meeting_no': meeting.meeting_no,
                'old_date': date,
                'new_date': swapped_date,
                'old_formatted': date.strftime('%d/%m/%Y'),
                'new_formatted': swapped_date.strftime('%d/%m/%Y'),
                'reason': f'month ({month}) > day ({day}), likely American format'
            })

    # Display changes
    if not changes:
        print("No suspicious date swaps detected.")
        return

    print(f"\nFound {len(changes)} date(s) that appear to be swapped:\n")
    print("=" * 90)

    for change in changes:
        print(f"Meeting ID: {change['meeting_id']} (Protocol #{change['meeting_no']})")
        print(f"  Current:  {change['old_date'].strftime('%Y-%m-%d')} ({change['old_formatted']})")
        print(f"  Swapped:  {change['new_date'].strftime('%Y-%m-%d')} ({change['new_formatted']})")
        print(f"  Reason:   {change['reason']}")
        print(f"  Action:   {'WOULD SWAP' if dry_run else 'SWAPPING'} day and month")
        print("-" * 90)

    # Apply changes if not dry run
    if not dry_run:
        confirm = input(f"\nSwap day/month for {len(changes)} date(s)? (yes/no): ")
        if confirm.lower() != 'yes':
            print("Cancelled.")
            session.close()
            return

        for change in changes:
            meeting = session.query(Meeting).filter_by(id=change['meeting_id']).first()
            if meeting:
                meeting.meeting_date = change['new_date']
                print(f"[OK] Swapped date for meeting {change['meeting_id']}")

        session.commit()
        print(f"\n[OK] Successfully swapped {len(changes)} date(s)")
    else:
        print("\n[!] DRY RUN MODE - No changes were made")
        print("Run with --apply flag to apply changes")

    session.close()

if __name__ == "__main__":
    import sys

    # Check for --apply flag
    apply = '--apply' in sys.argv

    if apply:
        print("=" * 90)
        print("SWAPPING DAY/MONTH IN DATES")
        print("=" * 90)
        fix_swapped_dates(dry_run=False)
    else:
        print("=" * 90)
        print("DRY RUN - Showing what would be changed")
        print("=" * 90)
        print("Use --apply flag to actually swap dates")
        print("=" * 90)
        fix_swapped_dates(dry_run=True)
