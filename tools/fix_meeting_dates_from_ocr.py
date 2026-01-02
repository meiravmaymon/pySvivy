"""
Fix meeting dates in database based on OCR extraction results
This script corrects date format issues where day/month were swapped
"""
import json
import os
from datetime import datetime
from database import get_session
from models import Meeting

def fix_dates_from_ocr(dry_run=True):
    """
    Fix meeting dates in database based on OCR results

    Args:
        dry_run: If True, only show what would be changed without actually changing
    """
    session = get_session()

    # Find all OCR result files
    ocr_dir = "ocr_results"
    if not os.path.exists(ocr_dir):
        print(f"OCR directory not found: {ocr_dir}")
        return

    changes = []

    for filename in os.listdir(ocr_dir):
        if not filename.startswith("protocol_ocr_analysis_") or not filename.endswith(".json"):
            continue

        # Extract meeting ID from filename
        try:
            meeting_id = int(filename.replace("protocol_ocr_analysis_", "").replace(".json", ""))
        except ValueError:
            continue

        # Load OCR data
        ocr_path = os.path.join(ocr_dir, filename)
        with open(ocr_path, 'r', encoding='utf-8') as f:
            ocr_data = json.load(f)

        # Get OCR date
        ocr_date_str = ocr_data.get('extracted', {}).get('meeting_info', {}).get('date_str')
        if not ocr_date_str or ocr_date_str == 'N/A':
            continue

        # Parse OCR date
        ocr_date = None
        for fmt in ['%d/%m/%y', '%d/%m/%Y', '%d.%m.%y', '%d.%m.%Y']:
            try:
                ocr_date = datetime.strptime(ocr_date_str, fmt)
                break
            except ValueError:
                continue

        if not ocr_date:
            print(f"Could not parse OCR date for meeting {meeting_id}: {ocr_date_str}")
            continue

        # Get DB meeting
        meeting = session.query(Meeting).filter_by(id=meeting_id).first()
        if not meeting:
            print(f"Meeting {meeting_id} not found in database")
            continue

        # Compare dates
        if meeting.meeting_date and meeting.meeting_date.date() != ocr_date.date():
            changes.append({
                'meeting_id': meeting_id,
                'meeting_no': meeting.meeting_no,
                'old_date': meeting.meeting_date,
                'new_date': ocr_date,
                'ocr_date_str': ocr_date_str
            })

    # Display changes
    if not changes:
        print("No date mismatches found between OCR and database.")
        return

    print(f"\nFound {len(changes)} date mismatch(es):\n")
    print("=" * 80)

    for change in changes:
        print(f"Meeting ID: {change['meeting_id']} (Protocol #{change['meeting_no']})")
        print(f"  Current DB date: {change['old_date'].strftime('%Y-%m-%d')} ({change['old_date'].strftime('%d/%m/%Y')})")
        print(f"  OCR extracted:   {change['new_date'].strftime('%Y-%m-%d')} ({change['ocr_date_str']})")
        print(f"  Action: {'WOULD UPDATE' if dry_run else 'UPDATING'} to {change['new_date'].strftime('%Y-%m-%d')}")
        print("-" * 80)

    # Apply changes if not dry run
    if not dry_run:
        confirm = input(f"\nApply {len(changes)} date corrections? (yes/no): ")
        if confirm.lower() != 'yes':
            print("Cancelled.")
            session.close()
            return

        for change in changes:
            meeting = session.query(Meeting).filter_by(id=change['meeting_id']).first()
            if meeting:
                meeting.meeting_date = change['new_date']
                print(f"[OK] Updated meeting {change['meeting_id']}")

        session.commit()
        print(f"\n[OK] Successfully updated {len(changes)} meeting date(s)")
    else:
        print("\n[!] DRY RUN MODE - No changes were made")
        print("Run with dry_run=False to apply changes")

    session.close()

if __name__ == "__main__":
    import sys

    # Check for --apply flag
    apply = '--apply' in sys.argv

    if apply:
        print("=" * 80)
        print("APPLYING DATE CORRECTIONS FROM OCR")
        print("=" * 80)
        fix_dates_from_ocr(dry_run=False)
    else:
        print("=" * 80)
        print("DRY RUN - Showing what would be changed")
        print("=" * 80)
        print("Use --apply flag to actually apply changes")
        print("=" * 80)
        fix_dates_from_ocr(dry_run=True)
