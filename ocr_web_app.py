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
from models import Meeting, Discussion, Attendance, Person, Role, BudgetSource, AdministrativeCategory, Municipality
from ocr_protocol import (
    extract_text_from_pdf,
    parse_protocol_text,
    compare_with_database,
    reverse_hebrew_text,
    normalize_final_letters,
    extract_municipality_name
)
from llm_helper import classify_discussion_admin_category

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = config.SECRET_KEY
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH

# Ensure folders exist
config.ensure_folders()

# Global storage for current session data - keyed by session ID (sid)
# Each tab gets its own sid for isolated data storage
import uuid
import threading
import queue
from collections import OrderedDict

session_data_store = {}

# ==============================================================================
# Processing Queue System - מערכת תור עיבוד ברקע
# ==============================================================================
# Allows batch processing of PDFs in background while user works on other tasks

# Queue structure
processing_queue = queue.Queue()
processing_status = {
    'is_running': False,
    'current_file': None,
    'current_index': 0,
    'total_files': 0,
    'completed': [],      # List of {sid, filename, status, error?}
    'failed': [],         # List of {filename, error}
    'pending': [],        # List of filenames waiting to be processed
    'year': None,         # Current batch year
    'started_at': None,
    'completed_at': None
}
processing_lock = threading.Lock()

def process_pdf_for_queue(file_path, filename):
    """
    Process a single PDF and store results in session_data_store.
    Returns (sid, success, error_message)
    Each PDF gets its own unique sid for data isolation.
    """
    # Generate unique sid for this file
    sid = str(uuid.uuid4())[:8]

    try:
        # Extract text from PDF
        ocr_text = extract_text_from_pdf(file_path)

        # Extract protocol data
        extracted_data = parse_protocol_text(ocr_text)

        # Try to extract municipality name from OCR text
        detected_municipality = extract_municipality_name(ocr_text)
        extracted_data['detected_municipality'] = detected_municipality

        # Auto-classify each discussion
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

        # Store in session_data_store with unique sid
        session_data_store[sid] = {
            'original_pdf_path': file_path,
            'pdf_path': file_path,
            'ocr_filename': filename,
            'extracted': extracted_data,
            'ocr_text': ocr_text,
            'pending_changes': {
                'meeting': {},
                'attendances': {},
                'staff': [],
                'discussions': {},
                'new_discussions': [],
            },
            'queued_at': datetime.now().isoformat(),
            'from_batch': True  # Mark as batch processed
        }

        return sid, True, None

    except Exception as e:
        logger.error(f"Queue processing error for {filename}: {e}")
        return None, False, str(e)

def queue_worker():
    """
    Background worker that processes PDFs from the queue.
    Runs in a separate thread.
    """
    global processing_status

    while True:
        try:
            # Get next file from queue (blocks until available)
            file_info = processing_queue.get(timeout=1)

            if file_info is None:
                # Poison pill - stop the worker
                break

            file_path = file_info['path']
            filename = file_info['filename']

            with processing_lock:
                processing_status['current_file'] = filename
                processing_status['current_index'] += 1
                # Remove from pending
                if filename in processing_status['pending']:
                    processing_status['pending'].remove(filename)

            logger.info(f"Queue processing: {filename} ({processing_status['current_index']}/{processing_status['total_files']})")

            # Process the PDF
            sid, success, error = process_pdf_for_queue(file_path, filename)

            with processing_lock:
                if success:
                    processing_status['completed'].append({
                        'sid': sid,
                        'filename': filename,
                        'status': 'ready',
                        'processed_at': datetime.now().isoformat()
                    })
                else:
                    processing_status['failed'].append({
                        'filename': filename,
                        'error': error,
                        'failed_at': datetime.now().isoformat()
                    })

            processing_queue.task_done()

        except queue.Empty:
            # Check if we should stop
            with processing_lock:
                if processing_queue.empty() and not processing_status['pending']:
                    processing_status['is_running'] = False
                    processing_status['current_file'] = None
                    processing_status['completed_at'] = datetime.now().isoformat()
                    break
        except Exception as e:
            logger.error(f"Queue worker error: {e}")

# Worker thread reference
queue_worker_thread = None

def get_sid():
    """Get session ID from request args or generate new one"""
    sid = request.args.get('sid') or request.form.get('sid')
    if not sid:
        # Try to get from JSON body
        if request.is_json:
            sid = request.json.get('sid')
    return sid

def get_session_data(sid):
    """Get session data for given sid, create if not exists"""
    if not sid:
        sid = str(uuid.uuid4())[:8]
    if sid not in session_data_store:
        session_data_store[sid] = {}
    return session_data_store[sid], sid


def get_pending_changes(session_data):
    """Get or initialize pending_changes structure in session_data"""
    if 'pending_changes' not in session_data:
        session_data['pending_changes'] = {
            'meeting': {},           # {field: value} for meeting updates
            'attendances': {},       # {person_id: {'is_present': bool, 'action': str}}
            'staff': [],             # [{'name': str, 'role': str}]
            'discussions': {},       # {disc_id: {'action': str, 'fields': {}}}
            'new_discussions': [],   # [{'issue_no': str, 'title': str, ...}]
        }
    return session_data['pending_changes']


def count_pending_changes(session_data):
    """Count total pending changes for UI display"""
    pending = session_data.get('pending_changes', {})
    count = 0
    count += 1 if pending.get('meeting') else 0
    count += len(pending.get('attendances', {}))
    count += len(pending.get('staff', []))
    count += len(pending.get('discussions', {}))
    count += len(pending.get('new_discussions', []))
    return count

def cleanup_old_sessions():
    """Clean up sessions older than 24 hours (called periodically)"""
    # Simple cleanup - keep only last 100 sessions
    if len(session_data_store) > 100:
        # Remove oldest entries (first added)
        keys_to_remove = list(session_data_store.keys())[:-50]
        for key in keys_to_remove:
            del session_data_store[key]

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

    # Remove common Hebrew titles (with various quote styles)
    # מר - Mr. (can appear as מר, 'מר, "מר)
    name = re.sub(r'^["\'\u05f3\u05f4\u201c\u201d]*מר["\'\u05f3\u05f4\u201c\u201d\.\s]*', '', name)
    # גברת / גב' - Mrs. (can appear as גב', גברת, 'גב)
    name = re.sub(r'^["\'\u05f3\u05f4]*גב(?:רת)?["\'\u05f3\u05f4\.\s]*', '', name)
    # עו"ד - Attorney (עורך דין / עורכת דין)
    name = re.sub(r'^עו["\'\u05f3\u05f4]*[דר]["\'\u05f3\u05f4\.\s]*', '', name)
    # ד"ר - Dr.
    name = re.sub(r'^ד["\'\u05f3\u05f4]*ר["\'\u05f3\u05f4\.\s]*', '', name)
    # רו"ח - CPA (רואה חשבון)
    name = re.sub(r'^רו["\'\u05f3\u05f4]*ח["\'\u05f3\u05f4\.\s]*', '', name)
    # פרופ' - Professor
    name = re.sub(r'^פרופ["\'\u05f3\u05f4\.\s]*', '', name)
    # מהנדס/ת
    name = re.sub(r'^מהנדס(?:ת)?["\'\u05f3\u05f4\.\s]*', '', name)
    # סגן/ית
    name = re.sub(r'^סגנ?(?:ית)?["\'\u05f3\u05f4\.\s]+', '', name)
    # ראש העיר / ראש המועצה
    name = re.sub(r'^ראש\s+(?:העיר|המועצה|עיר|מועצה)["\'\u05f3\u05f4\.\s]*', '', name)

    # Remove all types of quotes (Hebrew and English)
    name = re.sub(r'[\'\"\u05f3\u05f4\u201c\u201d\u2018\u2019`´]', '', name)

    # Remove extra spaces and trim
    name = re.sub(r'\s+', ' ', name).strip()

    return name


def names_match(name1, name2, return_details=False):
    """
    Check if two names match using fuzzy matching.
    Also checks reversed names (common OCR issue with Hebrew).

    If return_details=True, returns (matched: bool, was_reversed: bool, matched_name: str)
    Otherwise returns just bool.
    """
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)

    if not n1 or not n2:
        return (False, False, None) if return_details else False

    def check_match(a, b):
        """Check if a matches b (without reversal)"""
        # Exact match
        if a == b:
            return True

        # One contains the other (for partial names) - but only if it's a significant portion
        # This handles cases like "יוסי כהן" matching "יוסי"
        if len(a) >= 3 and len(b) >= 3:
            # Only match if one is a substantial part of the other (>60%)
            if a in b and len(a) >= len(b) * 0.6:
                return True
            if b in a and len(b) >= len(a) * 0.6:
                return True

        # Split into words
        words_a = set(a.split())
        words_b = set(b.split())

        # For two-word names (first + last), require BOTH words to match
        # OR require the first name (שם פרטי) to match
        if len(words_a) >= 2 and len(words_b) >= 2:
            common = words_a & words_b
            # If both names have 2+ words, require at least 2 common words
            # OR require the first word (first name) to match
            if len(common) >= 2:
                return True

            # Check if first names match (more important than last name)
            # Convert to list to get ordered words
            list_a = a.split()
            list_b = b.split()
            first_a = list_a[0] if list_a else ''
            first_b = list_b[0] if list_b else ''

            # First names must match AND be at least 3 chars
            if first_a and first_b and len(first_a) >= 3 and len(first_b) >= 3:
                if first_a == first_b:
                    # Also check if last names are similar (not completely different)
                    last_a = list_a[-1] if len(list_a) > 1 else ''
                    last_b = list_b[-1] if len(list_b) > 1 else ''
                    # If last names exist, they should either match or one should be empty
                    if not last_a or not last_b or last_a == last_b:
                        return True

        # For single-word names, require exact match (already handled above)
        return False

    # Check direct match
    if check_match(n1, n2):
        return (True, False, name2) if return_details else True

    # Check reversed match (OCR sometimes reverses Hebrew text)
    n1_reversed = n1[::-1]
    if check_match(n1_reversed, n2):
        return (True, True, name2) if return_details else True

    return (False, False, None) if return_details else False


def match_attendance_lists(ocr_list, db_list):
    """
    Match OCR attendance list with DB attendance list.
    Also handles reversed names (common OCR issue with Hebrew).
    Uses learned corrections from OCRLearningAgent to auto-match known names.

    Returns: (matched, ocr_only, db_only)
    - matched: list of {'ocr_name': ..., 'db_name': ..., 'db_id': ..., 'was_reversed': bool, 'auto_learned': bool}
    - ocr_only: list of {'name': ...}
    - db_only: list of {'id': ..., 'name': ...}
    """
    matched = []
    ocr_only = []
    db_matched_ids = set()

    for ocr_item in ocr_list:
        ocr_name = ocr_item.get('name', '')
        found_match = False

        # === First: Check if we have a learned match for this name ===
        if ocr_learning_agent:
            learned_match = ocr_learning_agent.get_known_name_mapping(ocr_name)
            if learned_match and learned_match.get('db_person_id'):
                # Find the db item with this person_id
                for db_item in db_list:
                    if db_item['id'] not in db_matched_ids and db_item.get('person_id') == learned_match['db_person_id']:
                        matched.append({
                            'ocr_name': ocr_name,
                            'db_name': db_item.get('name', learned_match['correct_name']),
                            'db_id': db_item['id'],
                            'was_reversed': learned_match.get('was_reversed', False),
                            'auto_learned': True,
                            'confidence': learned_match.get('confidence', 1.0)
                        })
                        db_matched_ids.add(db_item['id'])
                        found_match = True
                        break

            # Also try matching by correct_name if person_id didn't work
            if not found_match and learned_match:
                correct_name = learned_match.get('correct_name', '')
                for db_item in db_list:
                    if db_item['id'] not in db_matched_ids:
                        db_name = db_item.get('name', '')
                        if normalize_name(correct_name) == normalize_name(db_name):
                            matched.append({
                                'ocr_name': ocr_name,
                                'db_name': db_name,
                                'db_id': db_item['id'],
                                'was_reversed': learned_match.get('was_reversed', False),
                                'auto_learned': True,
                                'confidence': learned_match.get('confidence', 1.0)
                            })
                            db_matched_ids.add(db_item['id'])
                            found_match = True
                            break

        # === Second: Regular matching ===
        if not found_match:
            for db_item in db_list:
                if db_item['id'] in db_matched_ids:
                    continue

                db_name = db_item.get('name', '')
                is_match, was_reversed, _ = names_match(ocr_name, db_name, return_details=True)

                if is_match:
                    matched.append({
                        'ocr_name': ocr_name,
                        'db_name': db_name,
                        'db_id': db_item['id'],
                        'was_reversed': was_reversed,
                        'auto_learned': False
                    })
                    db_matched_ids.add(db_item['id'])
                    found_match = True
                    break

        if not found_match:
            ocr_only.append({'name': ocr_name})

    # Find DB items that weren't matched
    db_only = [db_item for db_item in db_list if db_item['id'] not in db_matched_ids]

    return matched, ocr_only, db_only


def get_all_municipalities():
    """Get all municipalities from database"""
    db_session = get_session()
    try:
        municipalities = db_session.query(Municipality).order_by(Municipality.name_he).all()
        return [{'id': m.id, 'name': m.name_he, 'semel': m.semel, 'type': m.municipality_type or ''} for m in municipalities]
    finally:
        db_session.close()


def get_all_meetings(municipality_id=None):
    """Get all meetings from database, optionally filtered by municipality"""
    db_session = get_session()
    try:
        query = db_session.query(Meeting)
        if municipality_id:
            query = query.filter(Meeting.municipality_id == municipality_id)
        meetings = query.order_by(Meeting.meeting_date.desc()).all()
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
    # Generate unique session ID for this tab
    sid = get_sid()
    if not sid:
        # New tab - generate new sid and redirect
        new_sid = str(uuid.uuid4())[:8]
        return redirect(url_for('index', sid=new_sid))

    # Initialize session data for this sid
    session_data, sid = get_session_data(sid)
    cleanup_old_sessions()

    # Get municipalities for dropdown
    municipalities = get_all_municipalities()

    # Get current municipality from session or default to first one
    municipality_id = session.get('municipality_id')
    if not municipality_id and municipalities:
        municipality_id = municipalities[0]['id']
        session['municipality_id'] = municipality_id
        session['municipality_name'] = municipalities[0]['name']

    # Get meetings for selected municipality
    meetings = get_all_meetings(municipality_id)

    return render_template('index.html',
                         meetings=meetings,
                         municipalities=municipalities,
                         current_municipality_id=municipality_id,
                         sid=sid)


@app.route('/set_municipality', methods=['POST'])
def set_municipality():
    """Set current municipality in session"""
    data = request.get_json()
    municipality_id = data.get('municipality_id')

    if not municipality_id:
        return jsonify({'error': 'לא נבחרה רשות'}), 400

    # Get municipality name
    db_session = get_session()
    try:
        municipality = db_session.query(Municipality).filter(Municipality.id == municipality_id).first()
        if not municipality:
            return jsonify({'error': 'רשות לא נמצאה'}), 404

        session['municipality_id'] = municipality_id
        session['municipality_name'] = municipality.name_he

        # Get meetings for new municipality
        meetings = get_all_meetings(municipality_id)

        return jsonify({
            'success': True,
            'municipality_name': municipality.name_he,
            'meetings': meetings
        })
    finally:
        db_session.close()


@app.route('/api/list_year_folders')
def list_year_folders():
    """List year subfolders in the source folder"""
    try:
        source_folder = config.SOURCE_PDF_FOLDER

        if not os.path.exists(source_folder):
            return jsonify({
                'error': f'תיקיית המקור לא נמצאה: {source_folder}',
                'years': []
            })

        # Get subfolders (excluding worked_on)
        years = []
        for f in os.listdir(source_folder):
            full_path = os.path.join(source_folder, f)
            if os.path.isdir(full_path) and f.lower() != 'worked_on':
                # Count PDFs in this folder
                pdf_count = len([p for p in os.listdir(full_path) if p.lower().endswith('.pdf')])
                if pdf_count > 0:
                    years.append({
                        'name': f,
                        'path': full_path,
                        'pdf_count': pdf_count
                    })

        # Sort by name descending (newest year first)
        years.sort(key=lambda x: x['name'], reverse=True)

        return jsonify({
            'success': True,
            'source_folder': source_folder,
            'years': years
        })
    except Exception as e:
        logger.error(f"Error listing year folders: {e}")
        return jsonify({'error': str(e), 'years': []}), 500


@app.route('/api/list_source_pdfs')
def list_source_pdfs():
    """List PDF files from a year subfolder that haven't been processed yet"""
    try:
        base_folder = config.SOURCE_PDF_FOLDER
        year = request.args.get('year')

        # If year specified, use that subfolder
        if year:
            source_folder = os.path.join(base_folder, year)
        else:
            source_folder = base_folder

        worked_on_folder = config.WORKED_ON_FOLDER

        if not os.path.exists(source_folder):
            return jsonify({
                'error': f'תיקייה לא נמצאה: {source_folder}',
                'files': []
            })

        # Get list of already processed files
        processed_files = set()
        if os.path.exists(worked_on_folder):
            processed_files = {f.lower() for f in os.listdir(worked_on_folder) if f.lower().endswith('.pdf')}

        # Get PDF files from source
        pdf_files = []
        for f in os.listdir(source_folder):
            if f.lower().endswith('.pdf'):
                full_path = os.path.join(source_folder, f)
                if os.path.isfile(full_path):
                    is_processed = f.lower() in processed_files
                    file_stat = os.stat(full_path)
                    pdf_files.append({
                        'filename': f,
                        'path': full_path,
                        'size': file_stat.st_size,
                        'size_mb': round(file_stat.st_size / (1024 * 1024), 2),
                        'modified': datetime.fromtimestamp(file_stat.st_mtime).strftime('%d/%m/%Y %H:%M'),
                        'is_processed': is_processed
                    })

        # Sort by filename descending
        pdf_files.sort(key=lambda x: x['filename'], reverse=True)

        return jsonify({
            'success': True,
            'source_folder': source_folder,
            'year': year,
            'files': pdf_files,
            'total': len(pdf_files),
            'unprocessed': len([f for f in pdf_files if not f['is_processed']])
        })
    except Exception as e:
        logger.error(f"Error listing source PDFs: {e}")
        return jsonify({'error': str(e), 'files': []}), 500


# ==============================================================================
# Batch Processing Queue API - ממשק API לתור עיבוד
# ==============================================================================

@app.route('/api/start_batch_processing', methods=['POST'])
def start_batch_processing():
    """
    Start batch processing of all unprocessed PDFs in a year folder.
    התחל עיבוד אצוות של כל הקבצים הממתינים בתיקיית שנה.
    """
    global queue_worker_thread, processing_status

    year = request.json.get('year')
    if not year:
        return jsonify({'error': 'לא צוינה שנה'}), 400

    with processing_lock:
        if processing_status['is_running']:
            return jsonify({
                'error': 'עיבוד כבר רץ ברקע',
                'current': processing_status['current_file'],
                'progress': f"{processing_status['current_index']}/{processing_status['total_files']}"
            }), 400

    # Get list of unprocessed files
    source_folder = os.path.join(config.SOURCE_PDF_FOLDER, year)
    worked_on_folder = config.WORKED_ON_FOLDER

    if not os.path.exists(source_folder):
        return jsonify({'error': f'תיקייה לא נמצאה: {source_folder}'}), 404

    # Get already processed files
    processed_files = set()
    if os.path.exists(worked_on_folder):
        processed_files = {f.lower() for f in os.listdir(worked_on_folder) if f.lower().endswith('.pdf')}

    # Get unprocessed PDFs
    files_to_process = []
    for f in os.listdir(source_folder):
        if f.lower().endswith('.pdf') and f.lower() not in processed_files:
            full_path = os.path.join(source_folder, f)
            if os.path.isfile(full_path):
                files_to_process.append({'filename': f, 'path': full_path})

    if not files_to_process:
        return jsonify({
            'success': True,
            'message': 'אין קבצים ממתינים לעיבוד',
            'count': 0
        })

    # Sort by filename
    files_to_process.sort(key=lambda x: x['filename'])

    # Reset status
    with processing_lock:
        processing_status = {
            'is_running': True,
            'current_file': None,
            'current_index': 0,
            'total_files': len(files_to_process),
            'completed': [],
            'failed': [],
            'pending': [f['filename'] for f in files_to_process],
            'year': year,
            'started_at': datetime.now().isoformat(),
            'completed_at': None
        }

    # Clear the queue
    while not processing_queue.empty():
        try:
            processing_queue.get_nowait()
        except queue.Empty:
            break

    # Add files to queue
    for file_info in files_to_process:
        processing_queue.put(file_info)

    # Start worker thread
    queue_worker_thread = threading.Thread(target=queue_worker, daemon=True)
    queue_worker_thread.start()

    logger.info(f"Started batch processing for {year}: {len(files_to_process)} files")

    return jsonify({
        'success': True,
        'message': f'התחיל עיבוד של {len(files_to_process)} קבצים',
        'count': len(files_to_process),
        'year': year,
        'files': [f['filename'] for f in files_to_process]
    })


@app.route('/api/queue_status')
def get_queue_status():
    """
    Get current status of the processing queue.
    קבל את מצב תור העיבוד הנוכחי.
    """
    with processing_lock:
        return jsonify({
            'is_running': processing_status['is_running'],
            'current_file': processing_status['current_file'],
            'current_index': processing_status['current_index'],
            'total_files': processing_status['total_files'],
            'completed_count': len(processing_status['completed']),
            'failed_count': len(processing_status['failed']),
            'pending_count': len(processing_status['pending']),
            'completed': processing_status['completed'],
            'failed': processing_status['failed'],
            'pending': processing_status['pending'],
            'year': processing_status['year'],
            'started_at': processing_status['started_at'],
            'completed_at': processing_status['completed_at'],
            'progress_percent': round(
                (processing_status['current_index'] / processing_status['total_files'] * 100)
                if processing_status['total_files'] > 0 else 0, 1
            )
        })


@app.route('/api/clear_queue', methods=['POST'])
def clear_queue():
    """
    Clear completed files from queue status.
    נקה קבצים שהושלמו מהסטטוס.
    """
    global processing_status

    with processing_lock:
        if processing_status['is_running']:
            return jsonify({'error': 'לא ניתן לנקות בזמן עיבוד'}), 400

        processing_status = {
            'is_running': False,
            'current_file': None,
            'current_index': 0,
            'total_files': 0,
            'completed': [],
            'failed': [],
            'pending': [],
            'year': None,
            'started_at': None,
            'completed_at': None
        }

    return jsonify({'success': True, 'message': 'התור נוקה'})


@app.route('/api/get_queued_data')
def get_queued_data():
    """
    Get extracted data from a queued processing session.
    קבל נתונים שהופקו מעיבוד בתור.
    """
    sid = request.args.get('sid')
    if not sid:
        return jsonify({'error': 'חסר מזהה session'}), 400

    if sid not in session_data_store:
        return jsonify({'error': 'לא נמצאו נתונים לסשן זה'}), 404

    session_data = session_data_store[sid]
    extracted = session_data.get('extracted', {})

    return jsonify({
        'success': True,
        'meeting_info': extracted.get('meeting_info', {}),
        'attendances_count': len(extracted.get('attendances', [])),
        'staff_count': len([a for a in extracted.get('attendances', []) if a.get('status') == 'staff']),
        'discussions_count': len(extracted.get('discussions', [])),
        'filename': session_data.get('ocr_filename', ''),
        'from_batch': session_data.get('from_batch', False)
    })


@app.route('/api/stop_queue', methods=['POST'])
def stop_queue():
    """
    Stop the processing queue (current file will complete).
    עצור את תור העיבוד (הקובץ הנוכחי יסתיים).
    """
    global processing_status

    with processing_lock:
        if not processing_status['is_running']:
            return jsonify({'message': 'העיבוד לא רץ'})

        # Clear pending items from queue
        processing_status['pending'] = []

    # Clear the queue
    while not processing_queue.empty():
        try:
            processing_queue.get_nowait()
            processing_queue.task_done()
        except queue.Empty:
            break

    # Add poison pill to stop worker
    processing_queue.put(None)

    logger.info("Queue processing stopped by user")

    return jsonify({
        'success': True,
        'message': 'העיבוד יעצור לאחר סיום הקובץ הנוכחי',
        'completed': len(processing_status['completed'])
    })


@app.route('/process_local', methods=['POST'])
def process_local_pdf():
    """Process a PDF file directly from the source folder (no upload needed)"""
    # Get sid for this tab's session data
    sid = request.json.get('sid') or get_sid()
    if not sid:
        return jsonify({'error': 'חסר מזהה session'}), 400
    session_data, sid = get_session_data(sid)

    file_path = request.json.get('file_path')
    if not file_path:
        return jsonify({'error': 'לא צוין נתיב קובץ'}), 400

    # Security: Validate path is within allowed source folder (prevent path traversal)
    try:
        abs_file_path = os.path.abspath(file_path)
        abs_source_folder = os.path.abspath(config.SOURCE_PDF_FOLDER)
        if not abs_file_path.startswith(abs_source_folder):
            logger.warning(f"Path traversal attempt blocked: {file_path}")
            return jsonify({'error': 'נתיב קובץ לא חוקי'}), 403
    except Exception as e:
        logger.error(f"Path validation error: {e}")
        return jsonify({'error': 'שגיאה באימות נתיב'}), 400

    if not os.path.exists(file_path):
        return jsonify({'error': f'הקובץ לא נמצא: {file_path}'}), 404

    if not file_path.lower().endswith('.pdf'):
        return jsonify({'error': 'יש לבחור קובץ PDF'}), 400

    filename = os.path.basename(file_path)

    try:
        # Extract text from PDF (directly from source - no copy needed)
        ocr_text = extract_text_from_pdf(file_path)

        # Extract protocol data
        extracted_data = parse_protocol_text(ocr_text)

        # Try to extract municipality name from OCR text
        detected_municipality = extract_municipality_name(ocr_text)
        extracted_data['detected_municipality'] = detected_municipality

        # Auto-classify each discussion
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

        # Store in session - use original path directly (no upload copy)
        session_data['original_pdf_path'] = file_path  # This is the key - original location
        session_data['pdf_path'] = file_path  # Same path - we'll move from here
        session_data['ocr_filename'] = filename
        session_data['extracted'] = extracted_data
        session_data['ocr_text'] = ocr_text

        logger.info(f"Processed local PDF: {file_path} for sid={sid}")

        return jsonify({
            'success': True,
            'filename': filename,
            'file_path': file_path,
            'meeting_info': extracted_data.get('meeting_info', {}),
            'attendances_count': len(extracted_data.get('attendances', [])),
            'staff_count': len(extracted_data.get('staff', [])),
            'discussions_count': len(extracted_data.get('discussions', [])),
            'detected_municipality': detected_municipality
        })
    except Exception as e:
        logger.error(f"Error processing local PDF: {e}")
        return jsonify({'error': f'שגיאה בעיבוד הקובץ: {str(e)}'}), 500


@app.route('/upload', methods=['POST'])
def upload_pdf():
    """Handle PDF upload and OCR extraction"""
    # Get sid for this tab's session data
    sid = request.form.get('sid') or get_sid()
    if not sid:
        return jsonify({'error': 'חסר מזהה session'}), 400
    session_data, sid = get_session_data(sid)

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

    # Save file with sid prefix to avoid conflicts between tabs
    safe_filename = f"{sid}_{filename}"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
    try:
        file.save(filepath)
        logger.info(f"Saved uploaded file: {safe_filename} ({file_size} bytes) for sid={sid}")
    except Exception as e:
        logger.error(f"Failed to save uploaded file: {e}")
        return jsonify({'error': 'שגיאה בשמירת הקובץ'}), 500

    try:
        # Extract text from PDF
        ocr_text = extract_text_from_pdf(filepath)

        # Extract protocol data
        extracted_data = parse_protocol_text(ocr_text)

        # Try to extract municipality name from OCR text
        detected_municipality = extract_municipality_name(ocr_text)
        extracted_data['detected_municipality'] = detected_municipality

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

        # Store in sid-specific session data (not global!)
        session_data['pdf_path'] = filepath
        session_data['ocr_filename'] = filename
        session_data['extracted'] = extracted_data
        session_data['ocr_text'] = ocr_text

        # Store original path if provided (for moving file at end of validation)
        original_path = request.form.get('original_path', '').strip()
        if original_path:
            session_data['original_pdf_path'] = original_path
            logger.info(f"Original PDF path stored: {original_path}")

        return jsonify({
            'success': True,
            'filename': filename,
            'meeting_info': extracted_data.get('meeting_info', {}),
            'attendances_count': len(extracted_data.get('attendances', [])),
            'staff_count': len(extracted_data.get('staff', [])),
            'discussions_count': len(extracted_data.get('discussions', [])),
            'detected_municipality': detected_municipality
        })
    except Exception as e:
        return jsonify({'error': f'שגיאה בעיבוד הקובץ: {str(e)}'}), 500


@app.route('/match_meeting', methods=['POST'])
def match_meeting():
    """Match uploaded PDF to a meeting in database"""
    # Get sid for this tab's session data
    sid = request.json.get('sid') or get_sid()
    if not sid:
        return jsonify({'error': 'חסר מזהה session'}), 400
    session_data, sid = get_session_data(sid)

    meeting_id = request.json.get('meeting_id')
    if not meeting_id:
        return jsonify({'error': 'לא נבחרה ישיבה'}), 400

    # Get meeting details from DB
    meeting_details = get_meeting_details(meeting_id)
    if not meeting_details:
        return jsonify({'error': 'ישיבה לא נמצאה'}), 404

    # Get extracted data from sid-specific storage
    extracted = session_data.get('extracted', {})

    # Store meeting_id in both Flask session and sid-specific data
    session['meeting_id'] = meeting_id
    session_data['meeting_id'] = meeting_id
    session_data['db_meeting'] = meeting_details

    # Run comparison
    comparison, _ = compare_with_database(extracted, meeting_id)
    session_data['comparison'] = comparison

    return jsonify({
        'success': True,
        'meeting': meeting_details,
        'comparison': comparison,
        'sid': sid
    })


@app.route('/step/<int:step_num>')
def validation_step(step_num):
    """Render validation step page"""
    # Get sid for this tab's session data
    sid = get_sid()
    if not sid:
        return redirect(url_for('index'))
    session_data, sid = get_session_data(sid)

    meeting_id = session_data.get('meeting_id') or session.get('meeting_id')
    if not meeting_id:
        return redirect(url_for('index', sid=sid))

    extracted = session_data.get('extracted', {})
    db_meeting = session_data.get('db_meeting', {})

    if step_num == 1:
        # Meeting info page
        return render_template('step1_meeting.html',
                             extracted=extracted.get('meeting_info', {}),
                             db_meeting=db_meeting,
                             sid=sid)
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
                             db_absent_count=len(db_absent),
                             sid=sid)
    elif step_num == 3:
        # Staff page
        return render_template('step3_staff.html',
                             extracted_staff=extracted.get('staff', []),
                             db_staff=db_meeting.get('staff', []),
                             sid=sid)
    elif step_num == 4:
        # Redirect to new discussion matching workflow
        return redirect(url_for('step_matching', sid=sid))
    else:
        return redirect(url_for('index', sid=sid))


@app.route('/api/update_attendance', methods=['POST'])
def update_attendance():
    """Update attendance record - saves to pending_changes (not DB)"""
    # Get sid for this tab's session data
    sid = request.json.get('sid') or get_sid()
    session_data, _ = get_session_data(sid) if sid else ({}, None)

    data = request.json
    attendance_id = data.get('attendance_id')
    person_id = data.get('person_id')
    action = data.get('action')  # 'set_present', 'set_absent', 'add', 'remove'

    # Store in pending_changes instead of committing to DB
    pending = get_pending_changes(session_data)

    if action in ['set_present', 'set_absent']:
        # Use attendance_id or person_id as key
        key = str(attendance_id) if attendance_id else str(person_id)
        pending['attendances'][key] = {
            'attendance_id': attendance_id,
            'person_id': person_id,
            'is_present': (action == 'set_present'),
            'action': 'update'
        }
        return jsonify({
            'success': True,
            'pending': True,
            'message': 'שינוי נוכחות נשמר (ממתין לאישור סופי)'
        })
    elif action == 'add':
        key = str(person_id)
        pending['attendances'][key] = {
            'person_id': person_id,
            'is_present': True,
            'action': 'add'
        }
        return jsonify({
            'success': True,
            'pending': True,
            'message': 'נוכחות חדשה נשמרה (ממתין לאישור סופי)'
        })
    elif action == 'remove':
        key = str(attendance_id) if attendance_id else str(person_id)
        pending['attendances'][key] = {
            'attendance_id': attendance_id,
            'person_id': person_id,
            'action': 'remove'
        }
        return jsonify({
            'success': True,
            'pending': True,
            'message': 'הסרת נוכחות נשמרה (ממתין לאישור סופי)'
        })

    return jsonify({'error': 'פעולה לא חוקית'}), 400


@app.route('/api/update_staff', methods=['POST'])
def update_staff():
    """Staff is only displayed from OCR, not stored in DB"""
    # Staff is not stored in the database - only shown from OCR extraction
    return jsonify({'success': True, 'message': 'סגל מוצג מנתוני OCR בלבד'})


@app.route('/api/save_staff', methods=['POST'])
def save_staff():
    """Save staff member and role - saves to pending_changes (not DB)"""
    # Get sid for this tab's session data
    sid = request.json.get('sid') or get_sid()
    session_data, _ = get_session_data(sid) if sid else ({}, None)

    data = request.json
    name = data.get('name', '').strip()
    role_name = data.get('role', '').strip()

    if not name:
        return jsonify({'error': 'שם נדרש'}), 400

    # Store in pending_changes instead of committing to DB
    pending = get_pending_changes(session_data)

    # Check if staff member already in pending list
    existing = next((s for s in pending['staff'] if s['name'] == name), None)
    if existing:
        # Update existing
        existing['role'] = role_name
    else:
        # Add new
        pending['staff'].append({
            'name': name,
            'role': role_name
        })

    return jsonify({
        'success': True,
        'pending': True,
        'message': f'נשמר (ממתין לאישור): {name}' + (f' - {role_name}' if role_name else '')
    })


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
    """Update meeting info - saves to pending_changes (not DB)"""
    # Get sid for this tab's session data
    sid = request.json.get('sid') or get_sid()
    session_data, _ = get_session_data(sid) if sid else ({}, None)

    data = request.json
    meeting_id = data.get('meeting_id')

    # Store in pending_changes instead of committing to DB
    pending = get_pending_changes(session_data)

    if 'meeting_no' in data and data['meeting_no']:
        pending['meeting']['meeting_no'] = data['meeting_no']
    if 'meeting_type' in data and data['meeting_type']:
        pending['meeting']['meeting_type'] = data['meeting_type']
    if 'date' in data and data['date']:
        pending['meeting']['meeting_date'] = data['date']  # Store as string, parse on finalize

    pending['meeting']['meeting_id'] = meeting_id

    return jsonify({
        'success': True,
        'pending': True,
        'message': 'השינויים נשמרו (ממתינים לאישור סופי)'
    })


@app.route('/api/save_all', methods=['POST'])
def save_all():
    """Save all changes to database"""
    # This endpoint can be used for batch saves
    return jsonify({'success': True, 'message': 'השינויים נשמרו בהצלחה'})


@app.route('/api/add_discussion', methods=['POST'])
def add_discussion():
    """Add a new discussion from OCR data - saves to pending_changes (not DB)"""
    # Get sid for this tab's session data
    sid = request.json.get('sid') or get_sid()
    session_data, _ = get_session_data(sid) if sid else ({}, None)

    data = request.json
    meeting_id = session.get('meeting_id')

    if not meeting_id:
        return jsonify({'error': 'לא נבחרה ישיבה'}), 400

    # Store in pending_changes instead of committing to DB
    pending = get_pending_changes(session_data)

    # Create new discussion data
    new_disc_data = {
        'issue_no': data.get('issue_no', 0),
        'title': data.get('title', ''),
        'decision': data.get('decision', ''),
        'decision_statement': data.get('decision_statement', ''),
        'expert_opinion': data.get('expert_opinion', ''),
        'yes_counter': data.get('yes_votes', 0),
        'no_counter': data.get('no_votes', 0),
        'avoid_counter': data.get('avoid_votes', 0),
        'admin_category_code': data.get('admin_category_code'),
        'temp_id': f"new_{len(pending['new_discussions']) + 1}"  # Temporary ID
    }

    pending['new_discussions'].append(new_disc_data)

    return jsonify({
        'success': True,
        'pending': True,
        'temp_id': new_disc_data['temp_id'],
        'message': f'סעיף {data.get("issue_no")} נוסף (ממתין לאישור סופי)'
    })


@app.route('/api/record_correction', methods=['POST'])
def record_correction():
    """Record a user correction for the learning system"""
    try:
        from ocr_learning_agent import record_user_correction
        data = request.json

        # Support both old format (field_type, correct_value) and new format (correction_type, corrected_value)
        field_type = data.get('field_type') or data.get('correction_type', 'word')
        ocr_value = data.get('ocr_value', '')
        correct_value = data.get('correct_value') or data.get('corrected_value', '')
        meeting_id = session.get('meeting_id')

        # Additional context for name matching
        context = data.get('context')
        person_id = data.get('person_id')

        if ocr_value and correct_value and ocr_value != correct_value:
            # Enhanced logging for name matches - use the specialized method
            if field_type == 'name_match' and ocr_learning_agent:
                ocr_learning_agent.record_name_match(
                    ocr_name=ocr_value,
                    correct_name=correct_value,
                    db_person_id=person_id
                )
                logger.info(f"Recorded name match: '{ocr_value}' -> '{correct_value}' (person_id={person_id})")

            # Enhanced logging for role corrections
            elif field_type == 'role' and ocr_learning_agent:
                ocr_learning_agent.record_role_correction(
                    ocr_role=ocr_value,
                    correct_role=correct_value
                )
                logger.info(f"Recorded role correction: '{ocr_value}' -> '{correct_value}'")

            else:
                record_user_correction(field_type, ocr_value, correct_value, meeting_id)

            return jsonify({'success': True, 'message': 'התיקון נשמר ללמידה'})
        return jsonify({'success': True, 'message': 'אין תיקון לשמור'})
    except ImportError:
        return jsonify({'success': False, 'message': 'מערכת הלמידה אינה זמינה'})
    except Exception as e:
        logger.error(f"Error recording correction: {e}")
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
    # Get sid for this tab's session data
    sid = get_sid()
    if not sid:
        return redirect(url_for('index'))
    session_data, sid = get_session_data(sid)

    meeting_id = session_data.get('meeting_id') or session.get('meeting_id')
    if not meeting_id:
        return redirect(url_for('index', sid=sid))

    extracted = session_data.get('extracted', {})
    db_meeting = session_data.get('db_meeting', {})

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

    # Store for later use in sid-specific storage
    session_data['auto_matched'] = auto_matched
    session_data['db_unmatched'] = db_unmatched
    session_data['ocr_unmatched'] = ocr_unmatched
    session_data['manual_matches'] = []

    return render_template('step4_matching.html',
                         auto_matched=auto_matched,
                         db_unmatched=db_unmatched,
                         ocr_unmatched=ocr_unmatched,
                         sid=sid)


@app.route('/api/save_discussion_matches', methods=['POST'])
def save_discussion_matches():
    """Save manual discussion matches from step 4a"""
    # Get sid for this tab's session data
    sid = request.json.get('sid') or get_sid()
    if not sid:
        return jsonify({'error': 'חסר מזהה session'}), 400
    session_data, sid = get_session_data(sid)

    data = request.json
    manual_matches = data.get('manual_matches', [])
    unlinked_auto = data.get('unlinked_auto', [])

    # Store in sid-specific session data
    session_data['manual_matches'] = manual_matches
    session_data['unlinked_auto'] = unlinked_auto

    return jsonify({'success': True})


@app.route('/step/4b')
def step_comparison():
    """Step 4b: Field comparison interface"""
    # Get sid for this tab's session data
    sid = get_sid()
    if not sid:
        return redirect(url_for('index'))
    session_data, sid = get_session_data(sid)

    meeting_id = session_data.get('meeting_id') or session.get('meeting_id')
    if not meeting_id:
        return redirect(url_for('index', sid=sid))

    extracted = session_data.get('extracted', {})
    db_meeting = session_data.get('db_meeting', {})

    db_discussions = db_meeting.get('discussions', [])
    ocr_discussions = extracted.get('discussions', [])

    # Get auto and manual matches from sid-specific storage
    auto_matched = session_data.get('auto_matched', [])
    manual_matches = session_data.get('manual_matches', [])
    unlinked_auto = session_data.get('unlinked_auto', [])

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

    # Store for step 4c in sid-specific storage
    session_data['matched_discussions'] = matched_discussions
    session_data['final_db_only'] = db_only
    session_data['final_ocr_only'] = ocr_only

    return render_template('step4_compare.html',
                         matched_discussions=matched_discussions,
                         db_only=db_only,
                         ocr_only=ocr_only,
                         sid=sid)


@app.route('/api/save_comparison', methods=['POST'])
def save_comparison():
    """Save field comparison choices - saves to pending_changes (not DB)"""
    # Get sid for this tab's session data
    sid = request.json.get('sid') or get_sid()
    session_data, _ = get_session_data(sid) if sid else ({}, None)

    data = request.json
    discussion_id = data.get('discussion_id')

    # Get OCR data for this discussion from sid-specific storage
    matched = session_data.get('matched_discussions', [])
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

    # Store in pending_changes instead of committing to DB
    pending = get_pending_changes(session_data)

    # Build fields dict based on source selection
    fields = {}

    # Title
    if data.get('title'):
        fields['title'] = data['title']
    elif data.get('title_source') == 'ocr' and ocr_data:
        fields['title'] = ocr_data.get('content')

    # Decision (status - categorical)
    if data.get('decision'):
        fields['decision'] = data['decision']
    elif data.get('decision_source') == 'ocr' and ocr_data:
        fields['decision'] = ocr_data.get('decision')

    # Decision Statement (full text - נוסח ההחלטה)
    if data.get('decision_statement'):
        fields['decision_statement'] = data['decision_statement']
    elif data.get('decision_statement_source') == 'ocr' and ocr_data:
        fields['decision_statement'] = ocr_data.get('decision_statement')

    # Expert Opinion
    if data.get('expert_opinion'):
        fields['expert_opinion'] = data['expert_opinion']
    elif data.get('expert_opinion_source') == 'ocr' and ocr_data:
        fields['expert_opinion'] = ocr_data.get('expert_opinion')

    # Summary
    if data.get('summary'):
        fields['summary'] = data['summary']
    elif data.get('summary_source') == 'ocr' and ocr_data:
        fields['summary'] = ocr_data.get('summary')

    # Budget
    if data.get('budget'):
        fields['total_budget'] = float(data['budget'])
        fields['budget_sources'] = []  # Clear sources if manual budget
    elif data.get('budget_source') == 'ocr' and ocr_data:
        ocr_budget = ocr_data.get('budget')
        if ocr_budget:
            fields['total_budget'] = float(ocr_budget)
            # Store budget sources for later
            fields['budget_sources'] = ocr_data.get('budget_sources', [])

    # Votes are always from the form
    if 'yes_votes' in data:
        fields['yes_counter'] = data['yes_votes']
    if 'no_votes' in data:
        fields['no_counter'] = data['no_votes']
    if 'avoid_votes' in data:
        fields['avoid_counter'] = data['avoid_votes']

    # Administrative Category
    ocr_category_code = ocr_data.get('admin_category_code') if ocr_data else None
    ocr_category_confidence = ocr_data.get('admin_category_confidence', 0) if ocr_data else 0

    if data.get('admin_category_code'):
        fields['admin_category_code'] = data['admin_category_code']
        fields['admin_category_auto'] = False
    elif data.get('admin_category_source') == 'ocr' and ocr_data:
        fields['admin_category_code'] = ocr_category_code
        fields['admin_category_confidence'] = ocr_category_confidence
        fields['admin_category_auto'] = True
    elif data.get('admin_category_source') == 'db' and db_data:
        fields['admin_category_code'] = db_data.get('admin_category_code')
        fields['admin_category_auto'] = False

    # Log category classification feedback for learning
    if ocr_learning_agent and ocr_category_code:
        try:
            title = ocr_data.get('content', '') or ocr_data.get('title', '') if ocr_data else ''
            user_category = fields.get('admin_category_code') or ocr_category_code
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

    # Store in pending changes
    pending['discussions'][str(discussion_id)] = {
        'action': 'update',
        'fields': fields
    }

    return jsonify({
        'success': True,
        'pending': True,
        'message': 'שינויים נשמרו (ממתינים לאישור סופי)'
    })


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
    # Get sid for this tab's session data
    sid = get_sid()
    if not sid:
        return redirect(url_for('index'))
    session_data, sid = get_session_data(sid)

    meeting_id = session_data.get('meeting_id') or session.get('meeting_id')
    if not meeting_id:
        return redirect(url_for('index', sid=sid))

    db_only = session_data.get('final_db_only', [])
    ocr_only = session_data.get('final_ocr_only', [])

    return render_template('step4_unmatched.html',
                         db_only=db_only,
                         ocr_only=ocr_only,
                         sid=sid)


@app.route('/step/5')
def step_finalize():
    """Step 5: Finalize validation - review and save all pending changes"""
    # Get sid for this tab's session data
    sid = get_sid()
    if not sid:
        return redirect(url_for('index'))
    session_data, sid = get_session_data(sid)

    meeting_id = session_data.get('meeting_id') or session.get('meeting_id')
    if not meeting_id:
        return redirect(url_for('index', sid=sid))

    # Get pending changes count and details
    pending = session_data.get('pending_changes', {})
    pending_count = count_pending_changes(session_data)

    # Get meeting info for display
    db_session = get_session()
    try:
        meeting = db_session.query(Meeting).filter(Meeting.id == meeting_id).first()
        meeting_info = {
            'id': meeting.id,
            'meeting_no': meeting.meeting_no,
            'meeting_date': meeting.meeting_date.strftime('%d/%m/%Y') if meeting.meeting_date else '',
            'meeting_type': meeting.meeting_type
        } if meeting else {}
    finally:
        db_session.close()

    return render_template('step5_finalize.html',
                         meeting_info=meeting_info,
                         pending=pending,
                         pending_count=pending_count,
                         sid=sid)


@app.route('/api/delete_discussion', methods=['POST'])
def delete_discussion():
    """Mark discussion for deletion - saves to pending_changes (not DB)"""
    # Get sid for this tab's session data
    sid = request.json.get('sid') or get_sid()
    session_data, _ = get_session_data(sid) if sid else ({}, None)

    data = request.json
    discussion_id = data.get('discussion_id')

    # Store in pending_changes instead of committing to DB
    pending = get_pending_changes(session_data)

    pending['discussions'][str(discussion_id)] = {
        'action': 'delete'
    }

    return jsonify({
        'success': True,
        'pending': True,
        'message': 'סעיף סומן למחיקה (ממתין לאישור סופי)'
    })


@app.route('/api/finalize_validation', methods=['POST'])
def finalize_validation():
    """
    שמירה אטומית של כל השינויים הממתינים לבסיס הנתונים.
    זה ה-endpoint היחיד שמבצע commit לבסיס הנתונים.
    """
    # Get sid for this tab's session data
    sid = request.json.get('sid') or get_sid()
    session_data, _ = get_session_data(sid) if sid else ({}, None)

    pending = session_data.get('pending_changes', {})
    meeting_id = session.get('meeting_id')

    if not meeting_id:
        return jsonify({'error': 'לא נבחרה ישיבה'}), 400

    db_session = get_session()
    try:
        # === 1. Update Meeting ===
        if pending.get('meeting'):
            meeting = db_session.query(Meeting).filter(Meeting.id == meeting_id).first()
            if meeting:
                meeting_data = pending['meeting']
                if 'meeting_no' in meeting_data:
                    meeting.meeting_no = meeting_data['meeting_no']
                if 'meeting_type' in meeting_data:
                    meeting.meeting_type = meeting_data['meeting_type']
                if 'meeting_date' in meeting_data:
                    try:
                        meeting.meeting_date = datetime.strptime(meeting_data['meeting_date'], '%d/%m/%Y')
                    except ValueError:
                        pass  # Keep original if parsing fails

        # === 2. Update Attendance ===
        for key, att_data in pending.get('attendances', {}).items():
            action = att_data.get('action')
            if action == 'update':
                att_id = att_data.get('attendance_id')
                if att_id:
                    att = db_session.query(Attendance).filter(Attendance.id == att_id).first()
                    if att:
                        att.is_present = att_data.get('is_present', True)
            elif action == 'add':
                person_id = att_data.get('person_id')
                if person_id:
                    new_att = Attendance(
                        meeting_id=meeting_id,
                        person_id=person_id,
                        is_present=att_data.get('is_present', True)
                    )
                    db_session.add(new_att)
            elif action == 'remove':
                att_id = att_data.get('attendance_id')
                if att_id:
                    att = db_session.query(Attendance).filter(Attendance.id == att_id).first()
                    if att:
                        db_session.delete(att)

        # === 3. Create Staff (new Person records) ===
        municipality_id = session.get('municipality_id')
        for staff_data in pending.get('staff', []):
            name = staff_data.get('name', '').strip()
            role_name = staff_data.get('role', '').strip()

            if not name:
                continue

            # Check if person exists
            person = db_session.query(Person).filter(Person.full_name == name).first()

            if not person:
                # Create new person
                person = Person(full_name=name, municipality_id=municipality_id)
                db_session.add(person)
                db_session.flush()  # Get the ID

            # Handle role
            if role_name:
                role = db_session.query(Role).filter(Role.name == role_name).first()
                if not role:
                    role = Role(name=role_name)
                    db_session.add(role)
                    db_session.flush()
                person.role_id = role.id

        # === 4. Update/Delete existing Discussions ===
        for disc_id, disc_data in pending.get('discussions', {}).items():
            action = disc_data.get('action')

            if action == 'delete':
                disc = db_session.query(Discussion).filter(Discussion.id == int(disc_id)).first()
                if disc:
                    db_session.delete(disc)
            elif action == 'update':
                disc = db_session.query(Discussion).filter(Discussion.id == int(disc_id)).first()
                if disc:
                    fields = disc_data.get('fields', {})

                    # Update simple fields
                    for field in ['title', 'decision', 'decision_statement', 'expert_opinion', 'summary']:
                        if field in fields and fields[field] is not None:
                            setattr(disc, field, fields[field])

                    # Update vote counters
                    if 'yes_counter' in fields:
                        disc.yes_counter = fields['yes_counter']
                    if 'no_counter' in fields:
                        disc.no_counter = fields['no_counter']
                    if 'avoid_counter' in fields:
                        disc.avoid_counter = fields['avoid_counter']

                    # Update budget
                    if 'total_budget' in fields:
                        disc.total_budget = fields['total_budget']

                        # Handle budget sources
                        budget_sources = fields.get('budget_sources', [])
                        # Clear existing
                        for bs in disc.budget_sources:
                            db_session.delete(bs)
                        # Add new
                        for src in budget_sources:
                            new_source = BudgetSource(
                                discussion_id=disc.id,
                                source_name=src.get('source', 'לא ידוע'),
                                amount=float(src.get('amount', 0))
                            )
                            db_session.add(new_source)

                    # Update admin category
                    if 'admin_category_code' in fields:
                        admin_cat = db_session.query(AdministrativeCategory).filter(
                            AdministrativeCategory.code == fields['admin_category_code']
                        ).first()
                        if admin_cat:
                            disc.admin_category_id = admin_cat.id
                            disc.admin_category_confidence = fields.get('admin_category_confidence')
                            disc.admin_category_auto = 1 if fields.get('admin_category_auto') else 0

        # === 5. Create new Discussions ===
        for new_disc_data in pending.get('new_discussions', []):
            new_disc = Discussion(
                meeting_id=meeting_id,
                issue_no=new_disc_data.get('issue_no', 0),
                title=new_disc_data.get('title', ''),
                decision=new_disc_data.get('decision', ''),
                decision_statement=new_disc_data.get('decision_statement', ''),
                expert_opinion=new_disc_data.get('expert_opinion', ''),
                yes_counter=new_disc_data.get('yes_counter', 0),
                no_counter=new_disc_data.get('no_counter', 0),
                avoid_counter=new_disc_data.get('avoid_counter', 0)
            )

            # Handle admin category
            admin_cat_code = new_disc_data.get('admin_category_code')
            if admin_cat_code:
                admin_cat = db_session.query(AdministrativeCategory).filter(
                    AdministrativeCategory.code == admin_cat_code
                ).first()
                if admin_cat:
                    new_disc.admin_category_id = admin_cat.id
                    new_disc.admin_category_auto = 0

            db_session.add(new_disc)

        # === Atomic Commit ===
        db_session.commit()

        # Clear pending changes
        session_data['pending_changes'] = {}
        session_data['validation_complete'] = True

        # Remove from queue completed list (if this was from batch processing)
        if session_data.get('from_batch'):
            with processing_lock:
                processing_status['completed'] = [
                    f for f in processing_status['completed']
                    if f.get('sid') != sid
                ]

        # Save learning data
        if ocr_learning_agent:
            try:
                ocr_learning_agent.save()
            except Exception as e:
                logger.warning(f"Failed to save learning data: {e}")

        logger.info(f"Finalized validation for meeting {meeting_id}")

        # === Move PDF to worked_on folder ===
        pdf_moved = False
        pdf_message = ''

        # Prefer original path (from user's computer) over uploaded path
        original_path = session_data.get('original_pdf_path')
        pdf_path = session_data.get('pdf_path') or session.get('pdf_path')
        pdf_filename = session_data.get('ocr_filename') or session.get('ocr_filename')

        # Determine source path - use original if exists, otherwise use uploaded
        source_path = None
        if original_path and os.path.exists(original_path):
            source_path = original_path
            logger.info(f"Using original path for move: {original_path}")
        elif pdf_path and os.path.exists(pdf_path):
            source_path = pdf_path
            logger.info(f"Using uploaded path for move: {pdf_path}")

        if source_path:
            try:
                import shutil
                # Use the configured worked_on folder
                worked_on_folder = config.WORKED_ON_FOLDER
                os.makedirs(worked_on_folder, exist_ok=True)

                # Use original filename from source path
                source_filename = os.path.basename(source_path)
                new_path = os.path.join(worked_on_folder, source_filename)

                # If file exists, add timestamp
                if os.path.exists(new_path):
                    name, ext = os.path.splitext(source_filename)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    new_filename = f'{name}_{timestamp}{ext}'
                    new_path = os.path.join(worked_on_folder, new_filename)

                shutil.move(source_path, new_path)
                pdf_moved = True
                pdf_message = f'הקובץ הועבר ל: {new_path}'
                logger.info(f"Moved PDF from {source_path} to: {new_path}")

                # Also delete uploaded copy if we moved from original
                if original_path and pdf_path and os.path.exists(pdf_path) and pdf_path != source_path:
                    try:
                        os.remove(pdf_path)
                        logger.info(f"Deleted uploaded copy: {pdf_path}")
                    except Exception as del_err:
                        logger.warning(f"Failed to delete uploaded copy: {del_err}")

                # Clear session paths
                session_data.pop('pdf_path', None)
                session_data.pop('original_pdf_path', None)
                session.pop('pdf_path', None)
            except Exception as e:
                logger.warning(f"Failed to move PDF: {e}")
                pdf_message = f'שגיאה בהעברת הקובץ: {str(e)}'

        return jsonify({
            'success': True,
            'message': 'כל השינויים נשמרו בהצלחה לבסיס הנתונים',
            'pdf_moved': pdf_moved,
            'pdf_message': pdf_message
        })

    except Exception as e:
        db_session.rollback()
        logger.error(f"Error finalizing validation: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        db_session.close()


@app.route('/api/discard_validation', methods=['POST'])
def discard_validation():
    """ביטול כל השינויים הממתינים"""
    # Get sid for this tab's session data
    sid = request.json.get('sid') or get_sid()
    session_data, _ = get_session_data(sid) if sid else ({}, None)

    # Clear pending changes
    session_data['pending_changes'] = {}

    return jsonify({
        'success': True,
        'message': 'כל השינויים הממתינים בוטלו'
    })


@app.route('/api/pending_count', methods=['GET'])
def pending_count():
    """Get count of pending changes for UI display"""
    sid = get_sid()
    session_data, _ = get_session_data(sid) if sid else ({}, None)

    count = count_pending_changes(session_data)
    pending = session_data.get('pending_changes', {})

    return jsonify({
        'count': count,
        'details': {
            'meeting': 1 if pending.get('meeting') else 0,
            'attendances': len(pending.get('attendances', {})),
            'staff': len(pending.get('staff', [])),
            'discussions': len(pending.get('discussions', {})),
            'new_discussions': len(pending.get('new_discussions', []))
        }
    })


@app.route('/api/move_to_processed', methods=['GET', 'POST'])
def move_to_processed():
    """Move the processed PDF to 'worked_on' folder (same as ocr_validation_module)"""
    # Get sid from request (GET or POST)
    sid = request.args.get('sid') or (request.json.get('sid') if request.is_json else None)

    pdf_path = session.get('pdf_path')
    pdf_filename = session.get('ocr_filename')

    logger.debug(f"[move_to_processed] pdf_path={pdf_path}, pdf_filename={pdf_filename}")

    # If no PDF path, just redirect to index (data was saved successfully, just no file to move)
    if not pdf_path:
        if request.method == 'GET':
            flash('הנתונים נשמרו בהצלחה!', 'success')
            return redirect(url_for('index'))
        return jsonify({'success': True, 'message': 'הנתונים נשמרו (אין קובץ להעברה)'})

    if not os.path.exists(pdf_path):
        if request.method == 'GET':
            flash('הנתונים נשמרו בהצלחה! (קובץ PDF לא נמצא להעברה)', 'success')
            return redirect(url_for('index'))
        return jsonify({'success': True, 'message': 'הנתונים נשמרו (קובץ לא נמצא)'})

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

        # If GET request (redirect from finalize), redirect to index with success message
        if request.method == 'GET':
            flash(f'הקובץ הועבר ל: worked_on/{os.path.basename(new_path)}', 'success')
            return redirect(url_for('index'))

        return jsonify({
            'success': True,
            'new_path': new_path,
            'message': f'הקובץ הועבר ל: worked_on/{os.path.basename(new_path)}'
        })
    except Exception as e:
        if request.method == 'GET':
            flash(f'שגיאה בהעברת הקובץ: {str(e)}', 'error')
            return redirect(url_for('index'))
        return jsonify({'error': f'שגיאה בהעברת הקובץ: {str(e)}'}), 500


if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("OCR Protocol Validation Web App")
    logger.info("=" * 50)
    logger.info("Starting server at http://localhost:5000")
    logger.info("Press Ctrl+C to stop")
    logger.info("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)
