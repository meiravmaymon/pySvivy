"""
Improved OCR-based protocol extraction
Main improvement: Better attendance extraction with proper title handling
Discussion extraction uses the original algorithm which works well
"""
import os
import sys
import re
from datetime import datetime
from database import get_session
from models import Meeting, Discussion, Vote, Attendance, Person
import json

# Import the original module - we'll use its discussion extraction
import ocr_protocol

# Use the same configuration as original
import pytesseract
pytesseract.pytesseract.tesseract_cmd = ocr_protocol.TESSERACT_PATH
os.environ['TESSDATA_PREFIX'] = ocr_protocol.TESSDATA_PREFIX


def normalize_name_with_title(name):
    """
    Normalize names by handling titles properly
    Returns the clean name without title, and whether a title was found
    """
    if not name:
        return name, False

    clean_name = name.strip()

    # Fix common OCR errors in titles BEFORE processing
    # עו"ר is often OCR misread of עו"ד (lawyer)
    clean_name = re.sub(r'^עו"ר\s+', 'עו"ד ', clean_name)

    # Common titles in Hebrew protocols
    titles = [
        r'עו"ד\s+',  # Lawyer (עורך דין)
        r'מר\s+',    # Mr
        r'גב\'\s+',  # Ms
        r'גב׳\s+',   # Ms (with Hebrew geresh)
        r'דר\'\s+',  # Dr
        r'ד"ר\s+',   # Dr (alternate format)
        r'פרופ\'\s+', # Prof
        r'רו"ח\s+',  # CPA (רואה חשבון)
    ]

    has_title = False

    for title_pattern in titles:
        match = re.match(title_pattern, clean_name, re.IGNORECASE)
        if match:
            clean_name = clean_name[match.end():]
            has_title = True
            break

    return clean_name.strip(), has_title


def extract_attendances_improved(text):
    """
    Improved attendance extraction with proper title handling
    Uses the robust patterns from original algorithm
    """
    attendances = []

    # Section 1: "משתתפים" = Present council members + officials
    # IMPORTANT: Stop at "סגל" section to avoid including staff members
    present_section = re.search(
        r'(?:משתתפ[א-ת]*|םיפתתשמ)[:\s\W]+(.*?)(?=חפסרים|חסרים|נעדרים|נוכחים|סגל|םירסח|םירדענ|םיכוחנ|לגס|על\s+סדר\s+היום|---\s+Page|\n\s*\n\s*\n)',
        text,
        re.DOTALL | re.IGNORECASE
    )

    # Fallback: If not found, look for attendance list after meeting header
    if not present_section:
        present_section = re.search(
            r'(?:נפתחה בשעה|הישיבה נפתחה|העשב החתפנ|החתפנ הבישיה)[^\n]*\n(.*?)(?=חפסרים|חסרים|נעדרים|םירסח|םירדענ|סגל|לגס)',
            text,
            re.DOTALL | re.IGNORECASE
        )

    # Section 2: "חסרים/נעדרים" = Absent council members
    absent_section = re.search(
        r'(?:נעדרים|חסרים|חפסרים|םירדענ|םירסח)[:\s]+(.*?)(?=נוכחים|סגל|על.*היום|םיכוחנ|לגס|םויה.*רדס)',
        text,
        re.DOTALL | re.IGNORECASE
    )

    # Process present members (משתתפים)
    if present_section:
        present_text = present_section.group(1)
        lines = present_text.split('\n')
        print(f"DEBUG: Found present section with {len(lines)} lines")

        for line in lines:
            line_stripped = line.strip()
            if not line_stripped or len(line_stripped) < 5:
                continue

            # Clean line from RTL/LTR marks
            line_cleaned = re.sub(r'^[^\u0590-\u05FF\s\'"]+', '', line_stripped)

            # Pattern: "name - role" OR "name . role"
            separator = None
            if '-' in line_cleaned:
                separator = '-'
            elif '.' in line_cleaned:
                separator = '.'

            if separator and re.search(r'(ראש|סגן|חבר|חברת|מועצה|שאר|ןגס|רבח|תרבח|הצעומ)', line_cleaned):
                parts = line_cleaned.split(separator, 1)
                if len(parts) == 2:
                    part0 = parts[0].strip()
                    part1 = parts[1].strip()

                    # Check which part is the role
                    is_official_part0 = re.search(
                        r'(ראש\s+העיר|סגן\s+ראש|חבר\s+מועצה|חברת\s+מועצה|'
                        r'ריעה\s+שאר|ריעה\s+שאר\s+ןגס|הצעומ\s+רבח|הצעומ\s+תרבח)',
                        part0, re.IGNORECASE
                    )
                    is_official_part1 = re.search(
                        r'(ראש\s+העיר|סגן\s+ראש|חבר\s+מועצה|חברת\s+מועצה|'
                        r'ריעה\s+שאר|ריעה\s+שאר\s+ןגס|הצעומ\s+רבח|הצעומ\s+תרבח)',
                        part1, re.IGNORECASE
                    )

                    # Determine which part is name
                    if is_official_part0:
                        name_part = part1
                        role_part = part0
                    elif is_official_part1:
                        name_part = part0
                        role_part = part1
                    else:
                        continue

                    # Filter out staff positions (not elected council members)
                    # But keep elected officials like סגן ראש העיר (deputy mayor)

                    # First check if this is an elected official (keep these!)
                    elected_keywords = ['סגן ראש', 'ראש העיר', 'ראש"ע', 'סגן ראש"ע']
                    is_elected = any(keyword in role_part for keyword in elected_keywords)

                    if not is_elected:
                        staff_keywords = [
                            'מנכ', 'גזבר', 'יועמ', 'תובע', 'מבקר', 'תקציבן',
                            'עוזר ראש', 'עוזרת', 'דובר', 'מנהל', 'מנהלת',
                            'עוזר מנכ', 'מזכיר', 'רכז', 'יו"ר', 'סגל'
                        ]
                        if any(keyword in role_part for keyword in staff_keywords):
                            continue

                    # Clean name using improved function
                    clean_name, has_title = normalize_name_with_title(name_part)

                    # Remove remaining non-Hebrew characters
                    clean_name = re.sub(r'[^א-ת\s\'"]', '', clean_name).strip()
                    clean_name = re.sub(r'\s+', ' ', clean_name)

                    if 3 <= len(clean_name) <= 50:
                        attendances.append({
                            'name': clean_name,
                            'status': 'present'
                        })

    # Process absent members (חסרים)
    if absent_section:
        absent_text = absent_section.group(1)
        lines = absent_text.split('\n')
        print(f"DEBUG: Found absent section with {len(lines)} lines")

        for line in lines:
            line_cleaned = re.sub(r'^[^\u0590-\u05FF\s\'"]+', '', line.strip())

            separator = None
            if '-' in line_cleaned:
                separator = '-'
            elif '.' in line_cleaned:
                separator = '.'

            if separator and re.search(r'(ראש|סגן|חבר|חברת|מועצה|שאר|ןגס|רבח|תרבח)', line_cleaned):
                parts = line_cleaned.split(separator, 1)
                if len(parts) == 2:
                    name_part = parts[0].strip()
                    role_part = parts[1].strip()

                    # If part 0 looks like a role, swap
                    if re.search(r'(ראש|סגן|חבר|חברת|שאר|ןגס|רבח|תרבח)', name_part):
                        name_part, role_part = role_part, name_part

                    # Filter out staff
                    staff_keywords = [
                        'מנכ', 'גזבר', 'יועמ', 'תובע', 'מבקר', 'תקציבן',
                        'עוזר ראש', 'עוזרת', 'דובר', 'מנהל', 'מנהלת',
                        'עוזר מנכ', 'מזכיר', 'רכז', 'יו"ר'
                    ]
                    if any(keyword in role_part for keyword in staff_keywords):
                        continue

                    # Clean name using improved function
                    clean_name, has_title = normalize_name_with_title(name_part)

                    # Remove remaining non-Hebrew characters
                    clean_name = re.sub(r'[^א-ת\s\'"]', '', clean_name).strip()
                    clean_name = re.sub(r'\s+', ' ', clean_name)

                    if 3 <= len(clean_name) <= 50 and clean_name.count(' ') in [0, 1, 2, 3]:
                        attendances.append({
                            'name': clean_name,
                            'status': 'absent'
                        })

    print(f"DEBUG: Extracted {len(attendances)} total attendees ({sum(1 for a in attendances if a['status']=='present')} present, {sum(1 for a in attendances if a['status']=='absent')} absent)")
    return attendances


def run_improved_ocr(pdf_path, meeting_id):
    """
    Run improved OCR extraction on a protocol
    Uses original algorithm for discussions (proven to work well)
    Uses improved algorithm for attendance (cleaner code, same results)
    """
    # Use original text extraction (it works well)
    text = ocr_protocol.extract_text_from_pdf(pdf_path)

    # Save raw OCR output
    output_file = f"ocr_output_{meeting_id}.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(text)
    print(f"Raw OCR text saved to: {output_file}")

    # Use ORIGINAL parse_protocol_text for discussions (it works better)
    original_result = ocr_protocol.parse_protocol_text(text)

    # Use IMPROVED attendance extraction
    attendances = extract_attendances_improved(text)

    # Combine results
    result = {
        'extracted': {
            'meeting_info': original_result['meeting_info'],
            'attendances': attendances,
            'discussions': original_result['discussions']
        }
    }

    # Save to JSON
    json_output = f"protocol_ocr_analysis_{meeting_id}_improved.json"
    with open(json_output, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] Improved OCR results saved to: {json_output}")
    print(f"[INFO] Extracted: {len(original_result['discussions'])} discussions, {len(attendances)} attendees")

    return result


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python ocr_protocol_improved.py <pdf_path> <meeting_id>")
        print("Example: python ocr_protocol_improved.py 19-6.pdf 101")
        sys.exit(1)

    pdf_path = sys.argv[1]
    meeting_id = int(sys.argv[2])

    if not os.path.exists(pdf_path):
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)

    result = run_improved_ocr(pdf_path, meeting_id)
