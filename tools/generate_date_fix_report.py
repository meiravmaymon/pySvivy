"""
Generate detailed report of dates to be fixed, grouped by criterion
"""
from datetime import datetime
from collections import defaultdict
from database import get_session
from models import Meeting, Discussion

def generate_fix_report():
    """Generate markdown report of all dates to be fixed"""
    session = get_session()

    # Get all meetings with dates
    all_meetings = session.query(Meeting).filter(
        Meeting.meeting_date.isnot(None)
    ).order_by(Meeting.meeting_date).all()

    # Group by year for chronology analysis
    meetings_by_year = defaultdict(list)
    for meeting in all_meetings:
        year = meeting.meeting_date.year
        meetings_by_year[year].append(meeting)

    # Analyze chronological sequence
    sequence_suspicious = []
    for year, meetings in meetings_by_year.items():
        meetings.sort(key=lambda m: m.meeting_no or '')
        prev_month = 0
        for i, meeting in enumerate(meetings):
            if not meeting.meeting_date:
                continue
            current_month = meeting.meeting_date.month
            current_day = meeting.meeting_date.day
            if current_day > 12:
                prev_month = current_month
                continue
            if i > 0 and current_month < prev_month - 1:
                sequence_suspicious.append(meeting.id)
            prev_month = current_month

    # Categorize all meetings
    chronology_only = []
    weekday_only = []
    both_criteria = []

    for meeting in all_meetings:
        date = meeting.meeting_date
        day = date.day
        month = date.month
        year = date.year

        if day > 12:
            continue

        try:
            swapped_date = datetime(year, day, month)
        except ValueError:
            continue

        current_weekday = date.weekday()
        swapped_weekday = swapped_date.weekday()

        in_sequence = meeting.id in sequence_suspicious
        is_monday_swap = (current_weekday != 0 and swapped_weekday == 0)

        if in_sequence and is_monday_swap:
            both_criteria.append(meeting)
        elif in_sequence:
            chronology_only.append(meeting)
        elif is_monday_swap:
            weekday_only.append(meeting)

    # Generate markdown report
    md_lines = []
    md_lines.append("# דוח תיקון תאריכים - פירוט לפי קריטריון")
    md_lines.append("")
    md_lines.append(f"**תאריך יצירה:** {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")

    # Summary
    md_lines.append("## סיכום")
    md_lines.append("")
    md_lines.append(f"- **סה\"כ תאריכים לתיקון:** {len(chronology_only) + len(weekday_only) + len(both_criteria)}")
    md_lines.append(f"- **סדר כרונולוגי בלבד:** {len(chronology_only)}")
    md_lines.append(f"- **יום בשבוע בלבד (→ יום שני):** {len(weekday_only)}")
    md_lines.append(f"- **שני הקריטריונים (בטוח):** {len(both_criteria)}")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")

    # Helper function to format meeting entry
    def format_meeting(meeting):
        date = meeting.meeting_date
        try:
            swapped = datetime(date.year, date.day, date.month)
            weekday_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            current_day = weekday_names[date.weekday()]
            swapped_day = weekday_names[swapped.weekday()]

            # Check if meeting has discussions
            disc_count = session.query(Discussion).filter_by(meeting_id=meeting.id).count()

            return (
                f"- **Protocol #{meeting.meeting_no}** (Meeting ID: {meeting.id})\n"
                f"  - נוכחי: `{date.strftime('%d/%m/%Y')}` ({current_day})\n"
                f"  - אחרי תיקון: `{swapped.strftime('%d/%m/%Y')}` ({swapped_day})\n"
                f"  - דיונים: {disc_count}\n"
            )
        except:
            return f"- Protocol #{meeting.meeting_no} (Error)\n"

    # Section 1: Both criteria (most reliable)
    md_lines.append("## 1. שני הקריטריונים (בטוח ביותר)")
    md_lines.append("")
    md_lines.append(f"**{len(both_criteria)} פרוטוקולים** - גם הסדר הכרונולוגי שגוי וגם ההחלפה תיצור יום שני")
    md_lines.append("")

    for meeting in sorted(both_criteria, key=lambda m: m.meeting_date):
        md_lines.append(format_meeting(meeting))

    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")

    # Section 2: Chronology only
    md_lines.append("## 2. סדר כרונולוגי בלבד")
    md_lines.append("")
    md_lines.append(f"**{len(chronology_only)} פרוטוקולים** - הסדר הכרונולוגי של הישיבות לא הגיוני")
    md_lines.append("")

    for meeting in sorted(chronology_only, key=lambda m: m.meeting_date):
        md_lines.append(format_meeting(meeting))

    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")

    # Section 3: Weekday only
    md_lines.append("## 3. יום בשבוע בלבד")
    md_lines.append("")
    md_lines.append(f"**{len(weekday_only)} פרוטוקולים** - ההחלפה תיצור יום שני (רוב הישיבות ביום שני)")
    md_lines.append("")

    for meeting in sorted(weekday_only, key=lambda m: m.meeting_date):
        md_lines.append(format_meeting(meeting))

    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")

    # Discussion dates section
    md_lines.append("## בדיקת תאריכי דיונים")
    md_lines.append("")

    # Check if discussions have dates that match meetings
    total_discussions = 0
    discussions_same_date = 0
    discussions_different_date = 0

    for meeting in (chronology_only + weekday_only + both_criteria):
        discussions = session.query(Discussion).filter_by(meeting_id=meeting.id).all()
        for disc in discussions:
            total_discussions += 1
            if disc.discussion_date:
                # Compare dates
                if disc.discussion_date.date() == meeting.meeting_date.date():
                    discussions_same_date += 1
                else:
                    discussions_different_date += 1

    md_lines.append(f"**סה\"כ דיונים בישיבות שצריכות תיקון:** {total_discussions}")
    md_lines.append("")
    md_lines.append(f"- דיונים עם תאריך זהה לישיבה: **{discussions_same_date}**")
    md_lines.append(f"- דיונים עם תאריך שונה מהישיבה: **{discussions_different_date}**")
    md_lines.append("")

    if discussions_same_date > 0:
        md_lines.append(f"⚠️ **יש לעדכן {discussions_same_date} דיונים** - התאריכים שלהם זהים לתאריך הישיבה ויתוקנו אוטומטית")
        md_lines.append("")

    if discussions_different_date > 0:
        md_lines.append(f"ℹ️ **{discussions_different_date} דיונים** עם תאריכים שונים - לא יתוקנו (כנראה תאריכים ספציפיים לדיון)")
        md_lines.append("")

    # Write report
    output_path = "date_fix_report.md"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(md_lines))

    print(f"[OK] Report generated: {output_path}")
    print(f"[INFO] Total dates to fix: {len(chronology_only) + len(weekday_only) + len(both_criteria)}")
    print(f"  - Chronology only: {len(chronology_only)}")
    print(f"  - Weekday only: {len(weekday_only)}")
    print(f"  - Both criteria: {len(both_criteria)}")

    session.close()
    return output_path

if __name__ == "__main__":
    generate_fix_report()
