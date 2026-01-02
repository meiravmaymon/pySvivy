# -*- coding: utf-8 -*-
"""
OCR Protocol Validation Web Application
אפליקציית ולידציה של פרוטוקולים - ממשק Web
"""

import os
import json
import re
import logging
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from werkzeug.utils import secure_filename

# Import configuration
from config import config, setup_logging

# Setup logging
setup_logging(level=logging.DEBUG if config.DEBUG else logging.INFO)
logger = logging.getLogger(__name__)

# Import existing modules
from database import get_session, session_scope
from models import Meeting, Discussion, Attendance, Person, Role, BudgetSource, AdministrativeCategory
from ocr_protocol import (
    extract_text_from_pdf,
    parse_protocol_text,
    compare_with_database,
    reverse_hebrew_text,
    normalize_final_letters
)
from llm_helper import classify_discussion_admin_category

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH

# Ensure folders exist
config.ensure_folders()

# Global storage for current session data
current_session_data = {}

# Import the OCR Learning Agent for recording corrections
try:
    from ocr_learning_agent import OCRLearningAgent
    ocr_learning_agent = OCRLearningAgent()
except ImportError:
    logger.warning("OCRLearningAgent not available")
    ocr_learning_agent = None


def log_user_preference(user_choice, ocr_data, db_data):
    """
    Log when user prefers DB data over OCR for learning/improvement.
    Uses OCRLearningAgent to record corrections for future OCR improvement.
    """
    if not ocr_data or not db_data:
        return

    if not ocr_learning_agent:
        return

    meeting_id = session.get('meeting_id')
    pdf_filename = session.get('ocr_filename', '')

    context = {
        'meeting_id': meeting_id,
        'pdf_filename': pdf_filename,
        'discussion_id': user_choice.get('discussion_id'),
    }

    # Map field names to learning agent field types
    field_mapping = {
        'title': 'title',
        'decision': 'decision',
        'expert_opinion': 'word',
        'summary': 'word',
        'budget': 'number',
    }

    # Check each field for DB preference and record corrections
    for field, field_type in field_mapping.items():
        source_key = f'{field}_source'
        if user_choice.get(source_key) == 'db':
            ocr_value = ocr_data.get(field) or ocr_data.get('content' if field == 'title' else field)
            db_value = db_data.get(field)

            # Only record if OCR had a different value
            if ocr_value and db_value and str(ocr_value).strip() != str(db_value).strip():
                ocr_learning_agent.record_correction(
                    field_type=field_type,
                    ocr_value=str(ocr_value)[:500],
                    correct_value=str(db_value)[:500],
                    context=context
                )

    # Check votes preference
    if user_choice.get('votes_source') == 'db':
        ocr_votes = f"בעד:{ocr_data.get('yes_votes') or 0} נגד:{ocr_data.get('no_votes') or 0} נמנע:{ocr_data.get('avoid_votes') or 0}"
        db_votes = f"בעד:{db_data.get('yes_votes') or 0} נגד:{db_data.get('no_votes') or 0} נמנע:{db_data.get('avoid_votes') or 0}"

        if ocr_votes != db_votes:
            ocr_learning_agent.record_correction(
                field_type='number',
                ocr_value=ocr_votes,
                correct_value=db_votes,
                context=context
            )

    # Save learning data
    try:
        ocr_learning_agent.save()
    except Exception as e:
        logger.warning(f"Failed to save learning data: {e}")


def normalize_name(name):
    """Normalize a name for comparison - remove titles, extra spaces, quotes"""
    if not name:
        return ''
    # Remove common titles
    name = re.sub(r'עו["\'"\']+[דר]\s*', '', name)
    name = re.sub(r'מר\s+', '', name)
    name = re.sub(r'גב["\']?\s*', '', name)
    name = re.sub(r'ד["\'"\']+ר\s*', '', name)
    # Remove quotes and extra spaces
    name = re.sub(r'[\'\"׳״]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def names_match(name1, name2):
    """Check if two names match using fuzzy matching"""
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)

    if not n1 or not n2:
        return False

    # Exact match
    if n1 == n2:
        return True

    # One contains the other (for partial names)
    if n1 in n2 or n2 in n1:
        return True

    # Split into words and check overlap
    words1 = set(n1.split())
    words2 = set(n2.split())

    # If at least one word matches and it's not too short
    common = words1 & words2
    if common:
        # Check that at least one common word is 3+ chars
        if any(len(w) >= 3 for w in common):
            return True

    # Check if first names match (common with OCR partial recognition)
    if words1 and words2:
        first1 = list(words1)[0] if words1 else ''
        first2 = list(words2)[0] if words2 else ''
        if first1 and first2 and len(first1) >= 3 and len(first2) >= 3:
            if first1 == first2:
                return True

    return False


def match_attendance_lists(ocr_list, db_list):
    """
    Match OCR attendance list with DB attendance list.
    Returns: (matched, ocr_only, db_only)
    - matched: list of {'ocr_name': ..., 'db_name': ..., 'db_id': ...}
    - ocr_only: list of {'name': ...}
    - db_only: list of {'id': ..., 'name': ...}
    """
    matched = []
    ocr_only = []
    db_matched_ids = set()

    for ocr_item in ocr_list:
        ocr_name = ocr_item.get('name', '')
        found_match = False

        for db_item in db_list:
            if db_item['id'] in db_matched_ids:
                continue

            db_name = db_item.get('name', '')
            if names_match(ocr_name, db_name):
                matched.append({
                    'ocr_name': ocr_name,
                    'db_name': db_name,
                    'db_id': db_item['id']
                })
                db_matched_ids.add(db_item['id'])
                found_match = True
                break

        if not found_match:
            ocr_only.append({'name': ocr_name})

    # Find DB items that weren't matched
    db_only = [db_item for db_item in db_list if db_item['id'] not in db_matched_ids]

    return matched, ocr_only, db_only


def get_all_meetings():
    """Get all meetings from database"""
    db_session = get_session()
    try:
        meetings = db_session.query(Meeting).order_by(Meeting.meeting_date.desc()).all()
        return [{'id': m.id, 'meeting_no': m.meeting_no, 'date': m.meeting_date.strftime('%d/%m/%Y') if m.meeting_date else '', 'type': m.meeting_type or ''} for m in meetings]
    finally:
        db_session.close()


def get_meeting_details(meeting_id):
    """Get meeting details including attendance and discussions"""
    db_session = get_session()
    try:
        meeting = db_session.query(Meeting).filter(Meeting.id == meeting_id).first()
        if not meeting:
            return None

        # Get attendance
        attendances = db_session.query(Attendance).filter(Attendance.meeting_id == meeting_id).all()
        present = []
        absent = []
        for att in attendances:
            person_name = att.person.full_name if att.person else 'לא ידוע'
            if att.is_present:
                present.append({'id': att.id, 'name': person_name, 'person_id': att.person_id})
            else:
                absent.append({'id': att.id, 'name': person_name, 'person_id': att.person_id})

        # Get discussions
        discussions = db_session.query(Discussion).filter(Discussion.meeting_id == meeting_id).order_by(Discussion.issue_no).all()
        disc_list = []
        for d in discussions:
            # Get budget sources
            budget_sources = [{'source_name': bs.source_name, 'amount': bs.amount} for bs in d.budget_sources]

            # Get admin category info
            admin_cat_code = None
            admin_cat_name = None
            if d.admin_category:
                admin_cat_code = d.admin_category.code
                admin_cat_name = d.admin_category.name_he

            disc_list.append({
                'id': d.id,
                'number': d.issue_no,
                'title': d.title or '',
                'decision': d.decision or '',
                'decision_statement': d.decision_statement or '',  # Full decision text / נוסח ההחלטה
                'yes_votes': d.yes_counter or 0,
                'no_votes': d.no_counter or 0,
                'avoid_votes': d.avoid_counter or 0,
                'expert_opinion': d.expert_opinion or '',
                'summary': d.summary or '',
                'total_budget': d.total_budget or 0,
                'budget_sources': budget_sources,
                'admin_category_code': admin_cat_code,
                'admin_category_name': admin_cat_name,
            })

        return {
            'id': meeting.id,
            'meeting_no': meeting.meeting_no,
            'date': meeting.meeting_date.strftime('%d/%m/%Y') if meeting.meeting_date else '',
            'type': meeting.meeting_type or '',
            'present': present,
            'absent': absent,
            'staff': [],  # Staff is only extracted from OCR, not stored in DB
            'discussions': disc_list
        }
    finally:
        db_session.close()


# Error handlers
@app.errorhandler(413)
def request_entity_too_large(error):
    """Handle file too large error"""
    return jsonify({'error': 'הקובץ גדול מדי. גודל מקסימלי: 50MB'}), 413


@app.errorhandler(500)
def internal_server_error(error):
    """Handle internal server errors"""
    logger.error(f"Internal server error: {error}")
    return jsonify({'error': 'שגיאה פנימית בשרת'}), 500


@app.route('/')
def index():
    """Main page - file upload and meeting selection"""
    meetings = get_all_meetings()
    return render_template('index.html', meetings=meetings)


@app.route('/upload', methods=['POST'])
def upload_pdf():
    """Handle PDF upload and OCR extraction"""
    if 'pdf_file' not in request.files:
        return jsonify({'error': 'לא נבחר קובץ'}), 400

    file = request.files['pdf_file']
    if file.filename == '':
        return jsonify({'error': 'לא נבחר קובץ'}), 400

    if not file.filename.lower().endswith('.pdf'):
        return jsonify({'error': 'יש לבחור קובץ PDF'}), 400

    # Validate filename
    filename = secure_filename(file.filename)
    if not filename:
        return jsonify({'error': 'שם קובץ לא תקין'}), 400

    # Check file size (double-check, Flask also validates)
    file.seek(0, 2)  # Seek to end
    file_size = file.tell()
    file.seek(0)  # Seek back to start
    if file_size > config.MAX_CONTENT_LENGTH:
        return jsonify({'error': f'הקובץ גדול מדי. גודל מקסימלי: {config.MAX_CONTENT_LENGTH // (1024*1024)}MB'}), 400

    if file_size == 0:
        return jsonify({'error': 'הקובץ ריק'}), 400

    # Save file
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    try:
        file.save(filepath)
        logger.info(f"Saved uploaded file: {filename} ({file_size} bytes)")
    except Exception as e:
        logger.error(f"Failed to save uploaded file: {e}")
        return jsonify({'error': 'שגיאה בשמירת הקובץ'}), 500

    try:
        # Extract text from PDF
        ocr_text = extract_text_from_pdf(filepath)

        # Extract protocol data
        extracted_data = parse_protocol_text(ocr_text)

        # Auto-classify each discussion using admin categories
        for disc in extracted_data.get('discussions', []):
            try:
                title = disc.get('content', '') or disc.get('title', '')
                classification = classify_discussion_admin_category(title)
                disc['admin_category_code'] = classification.get('category_code')
                disc['admin_category_confidence'] = classification.get('confidence', 0)
                disc['admin_category_auto'] = True
            except Exception as e:
                logger.warning(f"Failed to classify discussion: {e}")
                disc['admin_category_code'] = None
                disc['admin_category_confidence'] = 0
                disc['admin_category_auto'] = False

        # Store in session
        session['pdf_path'] = filepath
        session['ocr_filename'] = filename
        current_session_data['extracted'] = extracted_data
        current_session_data['ocr_text'] = ocr_text

        return jsonify({
            'success': True,
            'filename': filename,
            'meeting_info': extracted_data.get('meeting_info', {}),
            'attendances_count': len(extracted_data.get('attendances', [])),
            'staff_count': len(extracted_data.get('staff', [])),
            'discussions_count': len(extracted_data.get('discussions', []))
        })
    except Exception as e:
        return jsonify({'error': f'שגיאה בעיבוד הקובץ: {str(e)}'}), 500


@app.route('/match_meeting', methods=['POST'])
def match_meeting():
    """Match uploaded PDF to a meeting in database"""
    meeting_id = request.json.get('meeting_id')
    if not meeting_id:
        return jsonify({'error': 'לא נבחרה ישיבה'}), 400

    # Get meeting details from DB
    meeting_details = get_meeting_details(meeting_id)
    if not meeting_details:
        return jsonify({'error': 'ישיבה לא נמצאה'}), 404

    # Get extracted data
    extracted = current_session_data.get('extracted', {})

    # Compare and create validation data
    session['meeting_id'] = meeting_id
    current_session_data['db_meeting'] = meeting_details

    # Run comparison
    comparison, _ = compare_with_database(extracted, meeting_id)
    current_session_data['comparison'] = comparison

    return jsonify({
        'success': True,
        'meeting': meeting_details,
        'comparison': comparison
    })


@app.route('/step/<int:step_num>')
def validation_step(step_num):
    """Render validation step page"""
    meeting_id = session.get('meeting_id')
    if not meeting_id:
        return redirect(url_for('index'))

    extracted = current_session_data.get('extracted', {})
    db_meeting = current_session_data.get('db_meeting', {})

    if step_num == 1:
        # Meeting info page
        return render_template('step1_meeting.html',
                             extracted=extracted.get('meeting_info', {}),
                             db_meeting=db_meeting)
    elif step_num == 2:
        # Attendance page - do matching on server side
        ocr_present = [a for a in extracted.get('attendances', []) if a.get('status') == 'present']
        ocr_absent = [a for a in extracted.get('attendances', []) if a.get('status') == 'absent']
        db_present = db_meeting.get('present', [])
        db_absent = db_meeting.get('absent', [])

        # Match names using fuzzy matching
        matched_present, ocr_only_present, db_only_present = match_attendance_lists(ocr_present, db_present)
        matched_absent, ocr_only_absent, db_only_absent = match_attendance_lists(ocr_absent, db_absent)

        return render_template('step2_attendance.html',
                             matched_present=matched_present,
                             ocr_only_present=ocr_only_present,
                             db_only_present=db_only_present,
                             matched_absent=matched_absent,
                             ocr_only_absent=ocr_only_absent,
                             db_only_absent=db_only_absent,
                             ocr_present_count=len(ocr_present),
                             ocr_absent_count=len(ocr_absent),
                             db_present_count=len(db_present),
                             db_absent_count=len(db_absent))
    elif step_num == 3:
        # Staff page
        return render_template('step3_staff.html',
                             extracted_staff=extracted.get('staff', []),
                             db_staff=db_meeting.get('staff', []))
    elif step_num == 4:
        # Redirect to new discussion matching workflow
        return redirect(url_for('step_matching'))
    else:
        return redirect(url_for('index'))


@app.route('/api/update_attendance', methods=['POST'])
def update_attendance():
    """Update attendance record"""
    data = request.json
    attendance_id = data.get('attendance_id')
    action = data.get('action')  # 'set_present', 'set_absent', 'add', 'remove'

    db_session = get_session()
    try:
        if action in ['set_present', 'set_absent']:
            att = db_session.query(Attendance).filter(Attendance.id == attendance_id).first()
            if att:
                att.is_present = (action == 'set_present')
                db_session.commit()
                return jsonify({'success': True})

        return jsonify({'error': 'פעולה לא חוקית'}), 400
    except Exception as e:
        db_session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db_session.close()


@app.route('/api/update_staff', methods=['POST'])
def update_staff():
    """Staff is only displayed from OCR, not stored in DB"""
    # Staff is not stored in the database - only shown from OCR extraction
    return jsonify({'success': True, 'message': 'סגל מוצג מנתוני OCR בלבד'})


@app.route('/api/save_staff', methods=['POST'])
def save_staff():
    """Save staff member and role to database"""
    data = request.json
    name = data.get('name', '').strip()
    role_name = data.get('role', '').strip()

    if not name:
        return jsonify({'error': 'שם נדרש'}), 400

    db_session = get_session()
    try:
        # Check if person exists
        person = db_session.query(Person).filter(Person.full_name == name).first()

        if not person:
            # Create new person
            person = Person(full_name=name)
            db_session.add(person)
            db_session.flush()  # Get the ID

        # If role specified, check/create role and link to person
        if role_name:
            role = db_session.query(Role).filter(Role.name == role_name).first()
            if not role:
                role = Role(name=role_name)
                db_session.add(role)
                db_session.flush()

            # Link person to role (single role per person, not many-to-many)
            person.role_id = role.id

        db_session.commit()
        return jsonify({
            'success': True,
            'person_id': person.id,
            'message': f'נשמר: {name}' + (f' - {role_name}' if role_name else '')
        })
    except Exception as e:
        db_session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db_session.close()


@app.route('/api/update_discussion', methods=['POST'])
def update_discussion():
    """Update discussion record"""
    data = request.json
    discussion_id = data.get('discussion_id')

    db_session = get_session()
    try:
        disc = db_session.query(Discussion).filter(Discussion.id == discussion_id).first()
        if disc:
            if 'decision' in data:
                disc.decision = data['decision']
            if 'yes_votes' in data:
                disc.yes_counter = data['yes_votes']
            if 'no_votes' in data:
                disc.no_counter = data['no_votes']
            if 'avoid_votes' in data:
                disc.avoid_counter = data['avoid_votes']
            if 'title' in data:
                disc.title = data['title']

            db_session.commit()
            return jsonify({'success': True})

        return jsonify({'error': 'דיון לא נמצא'}), 404
    except Exception as e:
        db_session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db_session.close()


@app.route('/api/get_persons')
def get_persons():
    """Get all persons for autocomplete"""
    db_session = get_session()
    try:
        persons = db_session.query(Person).order_by(Person.full_name).all()
        return jsonify([{'id': p.id, 'name': p.full_name} for p in persons])
    finally:
        db_session.close()


@app.route('/api/get_admin_categories')
def get_admin_categories():
    """Get all administrative categories for classification dropdown"""
    db_session = get_session()
    try:
        categories = db_session.query(AdministrativeCategory).order_by(AdministrativeCategory.code).all()
        result = []
        for cat in categories:
            result.append({
                'code': cat.code,
                'name_he': cat.name_he,
                'name_en': cat.name_en,
                'parent_code': cat.parent_code,
                'decision_level': cat.decision_level
            })
        return jsonify(result)
    finally:
        db_session.close()


@app.route('/api/update_meeting', methods=['POST'])
def update_meeting():
    """Update meeting info"""
    data = request.json
    meeting_id = data.get('meeting_id')

    db_session = get_session()
    try:
        meeting = db_session.query(Meeting).filter(Meeting.id == meeting_id).first()
        if meeting:
            if 'meeting_no' in data and data['meeting_no']:
                meeting.meeting_no = data['meeting_no']
            if 'meeting_type' in data and data['meeting_type']:
                meeting.meeting_type = data['meeting_type']
            if 'date' in data and data['date']:
                # Parse date from DD/MM/YYYY format
                try:
                    meeting.meeting_date = datetime.strptime(data['date'], '%d/%m/%Y')
                except ValueError:
                    pass  # Keep original date if parsing fails

            db_session.commit()
            return jsonify({'success': True})

        return jsonify({'error': 'ישיבה לא נמצאה'}), 404
    except Exception as e:
        db_session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db_session.close()


@app.route('/api/save_all', methods=['POST'])
def save_all():
    """Save all changes to database"""
    # This endpoint can be used for batch saves
    return jsonify({'success': True, 'message': 'השינויים נשמרו בהצלחה'})


@app.route('/api/add_discussion', methods=['POST'])
def add_discussion():
    """Add a new discussion from OCR data to database"""
    data = request.json
    meeting_id = session.get('meeting_id')

    if not meeting_id:
        return jsonify({'error': 'לא נבחרה ישיבה'}), 400

    db_session = get_session()
    try:
        # Create new discussion
        new_disc = Discussion(
            meeting_id=meeting_id,
            issue_no=data.get('issue_no', 0),
            title=data.get('title', ''),
            decision=data.get('decision', ''),
            decision_statement=data.get('decision_statement', ''),
            expert_opinion=data.get('expert_opinion', ''),
            yes_counter=data.get('yes_votes', 0),
            no_counter=data.get('no_votes', 0),
            avoid_counter=data.get('avoid_votes', 0)
        )

        # Handle admin category if provided
        admin_cat_code = data.get('admin_category_code')
        if admin_cat_code:
            admin_cat = db_session.query(AdministrativeCategory).filter(
                AdministrativeCategory.code == admin_cat_code
            ).first()
            if admin_cat:
                new_disc.admin_category_id = admin_cat.id
                new_disc.admin_category_auto = 0  # User selected

        db_session.add(new_disc)
        db_session.commit()

        return jsonify({
            'success': True,
            'discussion_id': new_disc.id,
            'message': f'סעיף {data.get("issue_no")} נוסף בהצלחה'
        })
    except Exception as e:
        db_session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db_session.close()


@app.route('/api/record_correction', methods=['POST'])
def record_correction():
    """Record a user correction for the learning system"""
    try:
        from ocr_learning_agent import record_user_correction
        data = request.json
        field_type = data.get('field_type', 'word')
        ocr_value = data.get('ocr_value', '')
        correct_value = data.get('correct_value', '')
        meeting_id = session.get('meeting_id')

        if ocr_value and correct_value and ocr_value != correct_value:
            record_user_correction(field_type, ocr_value, correct_value, meeting_id)
            return jsonify({'success': True, 'message': 'התיקון נשמר ללמידה'})
        return jsonify({'success': True, 'message': 'אין תיקון לשמור'})
    except ImportError:
        return jsonify({'success': False, 'message': 'מערכת הלמידה אינה זמינה'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/log_ocr_rejection', methods=['POST'])
def log_ocr_rejection():
    """Log user rejection of OCR-extracted discussion for learning"""
    data = request.json
    meeting_id = session.get('meeting_id')

    if ocr_learning_agent:
        try:
            ocr_learning_agent.record_correction(
                field_type='discussion_rejection',
                ocr_value=data.get('ocr_content', '')[:500],
                correct_value=data.get('reason_code', 'unknown'),
                context={
                    'meeting_id': meeting_id,
                    'issue_no': data.get('issue_no'),
                    'title': data.get('title', '')[:200],
                    'reason_code': data.get('reason_code', ''),
                    'reason_text': data.get('reason_text', ''),
                    'rejection_type': 'ocr_only_discussion'
                }
            )
            ocr_learning_agent.save()
            logger.info(f"Logged OCR rejection: issue={data.get('issue_no')}, reason={data.get('reason_code')}")
        except Exception as e:
            logger.warning(f"Failed to log OCR rejection: {e}")

    return jsonify({'success': True, 'logged': True})


@app.route('/api/learning_report')
def learning_report():
    """Get learning system accuracy report"""
    try:
        from ocr_learning_agent import get_learning_agent
        agent = get_learning_agent()
        report = agent.get_accuracy_report()
        suggestions = agent.get_improvement_suggestions()
        return jsonify({
            'success': True,
            'report': report,
            'suggestions': suggestions
        })
    except ImportError:
        return jsonify({'success': False, 'message': 'מערכת הלמידה אינה זמינה'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/category_learning_report')
def category_learning_report():
    """Get category classification learning report"""
    try:
        from ocr_learning_agent import get_learning_agent
        agent = get_learning_agent()
        stats = agent.get_category_classification_stats()
        suggestions = agent.get_category_improvement_suggestions()
        return jsonify({
            'success': True,
            'stats': stats,
            'suggestions': suggestions
        })
    except ImportError:
        return jsonify({'success': False, 'message': 'מערכת הלמידה אינה זמינה'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ========================================
# Discussion Matching Workflow Routes
# ========================================

def match_discussions_by_number(db_discussions, ocr_discussions):
    """
    Match discussions by their issue number.
    Returns: (auto_matched, db_unmatched, ocr_unmatched)
    """
    auto_matched = []
    db_matched_ids = set()
    ocr_matched_numbers = set()

    # Create lookup by number
    db_by_number = {}
    for d in db_discussions:
        num = str(d.get('number', '')).strip()
        if num:
            db_by_number[num] = d

    ocr_by_number = {}
    for o in ocr_discussions:
        num = str(o.get('number', '')).strip()
        if num:
            ocr_by_number[num] = o

    # Match by exact number
    for num, db_item in db_by_number.items():
        if num in ocr_by_number:
            ocr_item = ocr_by_number[num]
            auto_matched.append({
                'db': db_item,
                'ocr': ocr_item,
                'match_type': 'auto'
            })
            db_matched_ids.add(db_item.get('id'))
            ocr_matched_numbers.add(num)

    # Collect unmatched
    db_unmatched = [d for d in db_discussions if d.get('id') not in db_matched_ids]
    ocr_unmatched = [o for o in ocr_discussions if str(o.get('number', '')) not in ocr_matched_numbers]

    return auto_matched, db_unmatched, ocr_unmatched


@app.route('/step/4a')
def step_matching():
    """Step 4a: Discussion linking interface"""
    meeting_id = session.get('meeting_id')
    if not meeting_id:
        return redirect(url_for('index'))

    extracted = current_session_data.get('extracted', {})
    db_meeting = current_session_data.get('db_meeting', {})

    db_discussions = db_meeting.get('discussions', [])
    ocr_discussions = extracted.get('discussions', [])

    # Auto-match by number
    auto_matched, db_unmatched, ocr_unmatched = match_discussions_by_number(
        db_discussions, ocr_discussions
    )

    # Sort all lists by item number (ascending)
    def get_number(item):
        if isinstance(item, dict):
            num = item.get('number') or item.get('db', {}).get('number') or 0
        else:
            num = 0
        try:
            return int(num)
        except (ValueError, TypeError):
            return 0

    auto_matched = sorted(auto_matched, key=lambda x: get_number(x.get('db', {})))
    db_unmatched = sorted(db_unmatched, key=get_number)
    ocr_unmatched = sorted(ocr_unmatched, key=get_number)

    # Store for later use
    current_session_data['auto_matched'] = auto_matched
    current_session_data['db_unmatched'] = db_unmatched
    current_session_data['ocr_unmatched'] = ocr_unmatched
    current_session_data['manual_matches'] = []

    return render_template('step4_matching.html',
                         auto_matched=auto_matched,
                         db_unmatched=db_unmatched,
                         ocr_unmatched=ocr_unmatched)


@app.route('/api/save_discussion_matches', methods=['POST'])
def save_discussion_matches():
    """Save manual discussion matches from step 4a"""
    data = request.json
    manual_matches = data.get('manual_matches', [])
    unlinked_auto = data.get('unlinked_auto', [])

    # Store in session data
    current_session_data['manual_matches'] = manual_matches
    current_session_data['unlinked_auto'] = unlinked_auto

    return jsonify({'success': True})


@app.route('/step/4b')
def step_comparison():
    """Step 4b: Field comparison interface"""
    meeting_id = session.get('meeting_id')
    if not meeting_id:
        return redirect(url_for('index'))

    extracted = current_session_data.get('extracted', {})
    db_meeting = current_session_data.get('db_meeting', {})

    db_discussions = db_meeting.get('discussions', [])
    ocr_discussions = extracted.get('discussions', [])

    # Get auto and manual matches
    auto_matched = current_session_data.get('auto_matched', [])
    manual_matches = current_session_data.get('manual_matches', [])
    unlinked_auto = current_session_data.get('unlinked_auto', [])

    # Create lookup for OCR discussions
    ocr_by_number = {str(o.get('number', '')): o for o in ocr_discussions}
    db_by_id = {str(d.get('id')): d for d in db_discussions}

    # Create set of unlinked pairs for quick lookup
    unlinked_pairs = {(str(u.get('db_id')), str(u.get('ocr_number'))) for u in unlinked_auto}

    # Filter out unlinked auto-matches
    filtered_auto_matched = [
        m for m in auto_matched
        if (str(m['db']['id']), str(m['ocr']['number'])) not in unlinked_pairs
    ]

    # Combine filtered auto and manual matches for comparison
    matched_discussions = list(filtered_auto_matched)
    matched_db_ids = {m['db']['id'] for m in filtered_auto_matched}
    matched_ocr_numbers = {m['ocr']['number'] for m in filtered_auto_matched}

    for mm in manual_matches:
        db_id = str(mm.get('db_id'))
        ocr_num = str(mm.get('ocr_number'))

        if db_id in db_by_id and ocr_num in ocr_by_number:
            matched_discussions.append({
                'db': db_by_id[db_id],
                'ocr': ocr_by_number[ocr_num],
                'match_type': 'manual'
            })
            matched_db_ids.add(int(db_id))
            matched_ocr_numbers.add(ocr_num)

    # Find unmatched
    db_only = [d for d in db_discussions if d.get('id') not in matched_db_ids]
    ocr_only = [o for o in ocr_discussions if str(o.get('number', '')) not in matched_ocr_numbers]

    # Store for step 4c
    current_session_data['matched_discussions'] = matched_discussions
    current_session_data['final_db_only'] = db_only
    current_session_data['final_ocr_only'] = ocr_only

    return render_template('step4_compare.html',
                         matched_discussions=matched_discussions,
                         db_only=db_only,
                         ocr_only=ocr_only)


@app.route('/api/save_comparison', methods=['POST'])
def save_comparison():
    """Save field comparison choices"""
    data = request.json
    discussion_id = data.get('discussion_id')

    db_session = get_session()
    try:
        disc = db_session.query(Discussion).filter(Discussion.id == discussion_id).first()
        if not disc:
            return jsonify({'error': 'דיון לא נמצא'}), 404

        # Get OCR data for this discussion
        matched = current_session_data.get('matched_discussions', [])
        ocr_data = None
        db_data = None
        for m in matched:
            if str(m['db']['id']) == str(discussion_id):
                ocr_data = m['ocr']
                db_data = m['db']
                break

        # Log user preferences for learning when DB was chosen over OCR
        try:
            log_user_preference(data, ocr_data, db_data)
        except Exception as e:
            logger.warning(f"Failed to log preference: {e}")

        # Apply values based on source selection
        # Title
        if data.get('title'):
            disc.title = data['title']
        elif data.get('title_source') == 'ocr' and ocr_data:
            disc.title = ocr_data.get('content', disc.title)

        # Decision (status - categorical)
        if data.get('decision'):
            disc.decision = data['decision']
        elif data.get('decision_source') == 'ocr' and ocr_data:
            disc.decision = ocr_data.get('decision', disc.decision)

        # Decision Statement (full text - נוסח ההחלטה)
        if data.get('decision_statement'):
            disc.decision_statement = data['decision_statement']
        elif data.get('decision_statement_source') == 'ocr' and ocr_data:
            disc.decision_statement = ocr_data.get('decision_statement', disc.decision_statement)

        # Expert Opinion
        if data.get('expert_opinion'):
            disc.expert_opinion = data['expert_opinion']
        elif data.get('expert_opinion_source') == 'ocr' and ocr_data:
            disc.expert_opinion = ocr_data.get('expert_opinion', disc.expert_opinion)

        # Summary
        if data.get('summary'):
            disc.summary = data['summary']
        elif data.get('summary_source') == 'ocr' and ocr_data:
            disc.summary = ocr_data.get('summary', disc.summary)

        # Budget
        if data.get('budget'):
            disc.total_budget = float(data['budget'])
        elif data.get('budget_source') == 'ocr' and ocr_data:
            ocr_budget = ocr_data.get('budget')
            if ocr_budget:
                disc.total_budget = float(ocr_budget)
                # Also save budget sources from OCR
                ocr_sources = ocr_data.get('budget_sources', [])
                if ocr_sources:
                    # Clear existing and add new
                    for bs in disc.budget_sources:
                        db_session.delete(bs)
                    for src in ocr_sources:
                        new_source = BudgetSource(
                            discussion_id=disc.id,
                            source_name=src.get('source', 'לא ידוע'),
                            amount=float(src.get('amount', 0))
                        )
                        db_session.add(new_source)

        # Votes are always from the form
        if 'yes_votes' in data:
            disc.yes_counter = data['yes_votes']
        if 'no_votes' in data:
            disc.no_counter = data['no_votes']
        if 'avoid_votes' in data:
            disc.avoid_counter = data['avoid_votes']

        # Administrative Category
        admin_cat_code = None
        admin_cat_confidence = None
        admin_cat_auto = False
        ocr_category_code = ocr_data.get('admin_category_code') if ocr_data else None
        ocr_category_confidence = ocr_data.get('admin_category_confidence', 0) if ocr_data else 0

        if data.get('admin_category_code'):
            # User selected custom category
            admin_cat_code = data['admin_category_code']
            admin_cat_auto = False
        elif data.get('admin_category_source') == 'ocr' and ocr_data:
            # User approved OCR auto-classification
            admin_cat_code = ocr_category_code
            admin_cat_confidence = ocr_category_confidence
            admin_cat_auto = True
        elif data.get('admin_category_source') == 'db' and db_data:
            # Keep DB category
            admin_cat_code = db_data.get('admin_category_code')
            admin_cat_auto = False

        if admin_cat_code:
            # Find category by code
            admin_cat = db_session.query(AdministrativeCategory).filter(
                AdministrativeCategory.code == admin_cat_code
            ).first()
            if admin_cat:
                disc.admin_category_id = admin_cat.id
                disc.admin_category_confidence = admin_cat_confidence
                disc.admin_category_auto = 1 if admin_cat_auto else 0

        # Log category classification feedback for learning
        if ocr_learning_agent and ocr_category_code:
            try:
                title = ocr_data.get('content', '') or ocr_data.get('title', '') if ocr_data else ''
                user_category = admin_cat_code or ocr_category_code
                ocr_learning_agent.record_category_feedback(
                    title=title,
                    auto_category=ocr_category_code,
                    user_category=user_category,
                    confidence=ocr_category_confidence,
                    context={
                        'discussion_id': discussion_id,
                        'meeting_id': session.get('meeting_id')
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to log category feedback: {e}")

        db_session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db_session.close()


@app.route('/api/log_summary_feedback', methods=['POST'])
def log_summary_feedback():
    """Log user feedback on AI-generated summaries for learning"""
    data = request.json
    discussion_id = data.get('discussion_id')
    approved = data.get('approved', False)
    ocr_summary = data.get('ocr_summary', '')

    # Log to OCRLearningAgent for future improvement
    if ocr_learning_agent:
        try:
            # Record summary feedback as a correction type
            correction_type = 'summary_approved' if approved else 'summary_rejected'
            ocr_learning_agent.record_correction(
                field='summary',
                ocr_value=ocr_summary,
                correct_value=ocr_summary if approved else '',  # Empty if rejected means user will provide custom
                context={
                    'discussion_id': discussion_id,
                    'feedback_type': correction_type,
                    'approved': approved
                }
            )
            ocr_learning_agent.save()
            logger.info(f"Logged summary feedback: discussion_id={discussion_id}, approved={approved}")
        except Exception as e:
            logger.warning(f"Failed to log summary feedback: {e}")

    return jsonify({'success': True, 'logged': True})


@app.route('/step/4c')
def step_unmatched():
    """Step 4c: Handle unmatched discussions"""
    meeting_id = session.get('meeting_id')
    if not meeting_id:
        return redirect(url_for('index'))

    db_only = current_session_data.get('final_db_only', [])
    ocr_only = current_session_data.get('final_ocr_only', [])

    return render_template('step4_unmatched.html',
                         db_only=db_only,
                         ocr_only=ocr_only)


@app.route('/api/delete_discussion', methods=['POST'])
def delete_discussion():
    """Delete a discussion from database"""
    data = request.json
    discussion_id = data.get('discussion_id')

    db_session = get_session()
    try:
        disc = db_session.query(Discussion).filter(Discussion.id == discussion_id).first()
        if disc:
            db_session.delete(disc)
            db_session.commit()
            return jsonify({'success': True})
        return jsonify({'error': 'דיון לא נמצא'}), 404
    except Exception as e:
        db_session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db_session.close()


@app.route('/api/move_to_processed', methods=['POST'])
def move_to_processed():
    """Move the processed PDF to 'worked_on' folder (same as ocr_validation_module)"""
    pdf_path = session.get('pdf_path')
    pdf_filename = session.get('ocr_filename')

    logger.debug(f"[move_to_processed] pdf_path={pdf_path}, pdf_filename={pdf_filename}")

    if not pdf_path:
        return jsonify({'error': 'נתיב קובץ לא נמצא בסשן', 'debug': 'pdf_path is None'}), 404

    if not os.path.exists(pdf_path):
        return jsonify({'error': f'קובץ לא נמצא בנתיב: {pdf_path}', 'debug': 'file does not exist'}), 404

    # Move to protocols_pdf/worked_on/ folder (not uploads/worked_on/)
    protocols_folder = os.path.join(os.path.dirname(__file__), 'protocols_pdf')
    worked_on_folder = os.path.join(protocols_folder, 'worked_on')
    os.makedirs(worked_on_folder, exist_ok=True)

    logger.info(f"[move_to_processed] Moving from {pdf_path} to {worked_on_folder}")

    try:
        import shutil
        new_path = os.path.join(worked_on_folder, pdf_filename)

        # If file exists in worked_on folder, add timestamp to avoid overwrite
        if os.path.exists(new_path):
            name, ext = os.path.splitext(pdf_filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            new_filename = f'{name}_{timestamp}{ext}'
            new_path = os.path.join(worked_on_folder, new_filename)

        shutil.move(pdf_path, new_path)
        logger.info(f"[move_to_processed] Successfully moved to {new_path}")

        # Clear session pdf_path
        session.pop('pdf_path', None)

        return jsonify({
            'success': True,
            'new_path': new_path,
            'message': f'הקובץ הועבר ל: worked_on/{os.path.basename(new_path)}'
        })
    except Exception as e:
        return jsonify({'error': f'שגיאה בהעברת הקובץ: {str(e)}'}), 500


if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("OCR Protocol Validation Web App")
    logger.info("=" * 50)
    logger.info("Starting server at http://localhost:5000")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=5000)
