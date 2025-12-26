"""
Flask Web Application for Yehud-Monosson Municipal System
"""
import sys
import os
from flask import Flask, render_template, jsonify, request
from sqlalchemy import func, desc, create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models import Person, Board, Meeting, Discussion, Vote, Attendance, Term, Category, DiscussionType, Faction, Role, BudgetSource, Base

# Database setup - use absolute path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATABASE_PATH = os.path.join(BASE_DIR, 'svivyNew.db')
DATABASE_URL = f'sqlite:///{DATABASE_PATH}'

engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False})
Session = scoped_session(sessionmaker(bind=engine))

def get_session():
    return Session()

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False  # Enable Hebrew in JSON responses


# ===== API ENDPOINTS =====

@app.route('/api/periods')
def get_periods():
    """Get available time periods (years and terms)"""
    session = get_session()

    # Get all years from meetings
    years = session.query(
        func.strftime('%Y', Meeting.meeting_date).label('year')
    ).distinct().filter(Meeting.meeting_date.isnot(None)).order_by(desc('year')).all()

    years_list = [int(y[0]) for y in years if y[0]]

    # Get all terms from Term table
    terms = session.query(Term).order_by(desc(Term.term_number)).all()

    terms_list = []
    for term in terms:
        terms_list.append({
            'term_number': term.term_number,
            'label': f'קדנציה {term.term_number}',
            'start_year': term.start_date.year,
            'end_year': term.end_date.year,
            'is_current': bool(term.is_current)
        })

    session.close()

    return jsonify({
        'years': years_list,
        'terms': terms_list,
        'current_year': datetime.now().year
    })


@app.route('/api/current-term')
def get_current_term():
    """Get the current active term"""
    session = get_session()

    # Try to get the current term (marked as is_current=True)
    current_term = session.query(Term).filter_by(is_current=True).first()

    if current_term:
        result = {
            'term_number': current_term.term_number,
            'start_date': current_term.start_date.isoformat(),
            'end_date': current_term.end_date.isoformat() if current_term.end_date else None,
            'is_current': True,
            'label': f'קדנציה {current_term.term_number}'
        }
        session.close()
        return jsonify(result)

    # Fallback - get the latest term by term_number
    latest_term = session.query(Term).order_by(desc(Term.term_number)).first()

    if latest_term:
        result = {
            'term_number': latest_term.term_number,
            'start_date': latest_term.start_date.isoformat(),
            'end_date': latest_term.end_date.isoformat() if latest_term.end_date else None,
            'is_current': False,
            'label': f'קדנציה {latest_term.term_number}'
        }
        session.close()
        return jsonify(result)

    session.close()
    return jsonify({'error': 'No terms found'}), 404


@app.route('/api/municipalities')
def get_municipalities():
    """Get list of all municipalities in the system"""
    session = get_session()

    # For now, return Yehud-Monosson as the only municipality
    # In the future, this will query the Municipality table
    municipalities = [
        {
            'id': 1,
            'name': 'יהוד-מונוסון',
            'name_en': 'Yehud-Monosson',
            'is_default': True
        }
    ]

    session.close()
    return jsonify({'municipalities': municipalities})


@app.route('/api/available-years')
def get_available_years():
    """Get available years, optionally filtered by term"""
    session = get_session()
    filter_type = request.args.get('filter_type')
    filter_value = request.args.get('filter_value')

    query = session.query(
        func.strftime('%Y', Meeting.meeting_date).label('year')
    ).distinct().filter(Meeting.meeting_date.isnot(None))

    # Filter by term if specified
    if filter_type == 'term' and filter_value:
        term_number = int(filter_value)
        term = session.query(Term).filter_by(term_number=term_number).first()
        if term:
            query = query.filter(Meeting.term_id == term.id)

    years = [int(row.year) for row in query.order_by(desc('year')).all() if row.year]
    session.close()

    return jsonify({
        'years': sorted(years, reverse=True),
        'filter': {
            'type': filter_type,
            'value': filter_value
        }
    })


@app.route('/api/stats')
def get_stats():
    """Get overall statistics for dashboard"""
    session = get_session()

    # Get filter parameters
    filter_type = request.args.get('filter_type', 'all')  # 'all', 'year', 'term'
    filter_value = request.args.get('filter_value')  # year number or term number
    year_filter = request.args.get('year')  # Optional secondary year filter

    # Build base queries
    persons_query = session.query(Person)
    discussions_query = session.query(Discussion)
    meetings_query = session.query(Meeting)
    votes_query = session.query(Vote)
    attendances_query = session.query(Attendance)

    # Apply term filter first (primary filter)
    if filter_type == 'term' and filter_value:
        term_number = int(filter_value)
        # Get the term from database
        term = session.query(Term).filter_by(term_number=term_number).first()
        if term:
            # Filter persons by term (many-to-many)
            persons_query = persons_query.filter(Person.terms.contains(term))
            # Filter meetings by term_id
            meetings_query = meetings_query.filter(Meeting.term_id == term.id)
            # Filter discussions by their meeting's term
            discussions_query = discussions_query.join(Meeting).filter(Meeting.term_id == term.id)
            # Filter votes by discussion's meeting term
            votes_query = votes_query.join(Discussion).join(Meeting).filter(Meeting.term_id == term.id)
            # Filter attendance by meeting term
            attendances_query = attendances_query.join(Meeting).filter(Meeting.term_id == term.id)

    # Apply year filter (can be primary or secondary)
    if year_filter or (filter_type == 'year' and filter_value):
        year = int(year_filter if year_filter else filter_value)
        # Filter discussions by their meeting's date
        if filter_type != 'term':
            discussions_query = discussions_query.join(Meeting)
        discussions_query = discussions_query.filter(
            func.strftime('%Y', Meeting.meeting_date) == str(year)
        )
        meetings_query = meetings_query.filter(
            func.strftime('%Y', Meeting.meeting_date) == str(year)
        )
        # Filter votes by discussion's meeting date
        if filter_type != 'term':
            votes_query = votes_query.join(Discussion).join(Meeting)
        votes_query = votes_query.filter(
            func.strftime('%Y', Meeting.meeting_date) == str(year)
        )
        # Filter attendance by meeting date
        if filter_type != 'term':
            attendances_query = attendances_query.join(Meeting)
        attendances_query = attendances_query.filter(
            func.strftime('%Y', Meeting.meeting_date) == str(year)
        )

    # Calculate stats
    active_members = persons_query.filter(Person.end_date.is_(None)).count()
    total_discussions = discussions_query.count()
    total_meetings = meetings_query.count()

    total_attendances = attendances_query.count()
    present_count = attendances_query.filter(Attendance.is_present == 1).count()
    attendance_rate = round((present_count / total_attendances * 100) if total_attendances > 0 else 0, 1)

    yes_votes = votes_query.filter(Vote.vote == 'yes').count()
    no_votes = votes_query.filter(Vote.vote == 'no').count()
    avoid_votes = votes_query.filter(Vote.vote == 'avoid').count()

    session.close()

    return jsonify({
        'active_members': active_members,
        'meetings_this_year': total_meetings,
        'total_discussions': total_discussions,
        'attendance_rate': attendance_rate,
        'votes': {
            'yes': yes_votes,
            'no': no_votes,
            'avoid': avoid_votes
        },
        'filter': {
            'type': filter_type,
            'value': filter_value
        }
    })


@app.route('/api/persons')
def get_persons():
    """Get all council members"""
    session = get_session()
    active_only = request.args.get('active', 'false').lower() == 'true'
    filter_type = request.args.get('filter_type', 'all')
    filter_value = request.args.get('filter_value')

    query = session.query(Person)

    # Apply term filter - use many-to-many relationship
    if filter_type == 'term' and filter_value:
        term_number = int(filter_value)
        term = session.query(Term).filter_by(term_number=term_number).first()
        if term:
            query = query.filter(Person.terms.contains(term))

    if active_only:
        query = query.filter(Person.end_date.is_(None))

    persons = query.all()

    result = []
    for p in persons:
        # Calculate votes and attendance for this person
        total_votes = session.query(Vote).filter(Vote.person_id == p.id).count()
        yes_votes = session.query(Vote).filter(Vote.person_id == p.id, Vote.vote == 'yes').count()

        attendances = session.query(Attendance).filter(Attendance.person_id == p.id)
        total_meetings = attendances.count()
        present_meetings = attendances.filter(Attendance.is_present == 1).count()
        attendance_pct = round((present_meetings / total_meetings * 100) if total_meetings > 0 else 0, 1)

        result.append({
            'id': p.id,
            'name': p.full_name,
            'title': p.title,
            'role': p.role_obj.name if p.role_obj else None,
            'role_full': f"{p.role_obj.parent.name} > {p.role_obj.name}" if p.role_obj and p.role_obj.parent else (p.role_obj.name if p.role_obj else None),
            'faction': p.faction_obj.name if p.faction_obj else None,
            'faction_full': f"{p.faction_obj.parent.name} > {p.faction_obj.name}" if p.faction_obj and p.faction_obj.parent else (p.faction_obj.name if p.faction_obj else None),
            'degree': p.degree,
            'gender': p.gender,
            'is_active': p.end_date is None,
            'start_date': p.start_date.strftime('%Y-%m-%d') if p.start_date else None,
            'total_votes': total_votes,
            'yes_votes': yes_votes,
            'attendance_percentage': attendance_pct,
            'boards_count': len(p.boards)
        })

    session.close()
    return jsonify(result)


@app.route('/api/person/<int:person_id>')
def get_person(person_id):
    """Get detailed information about a specific person"""
    session = get_session()
    person = session.query(Person).filter(Person.id == person_id).first()

    if not person:
        session.close()
        return jsonify({'error': 'Person not found'}), 404

    # Get votes
    votes = session.query(Vote).filter(Vote.person_id == person_id).all()
    yes_count = len([v for v in votes if v.vote == 'yes'])
    no_count = len([v for v in votes if v.vote == 'no'])
    avoid_count = len([v for v in votes if v.vote == 'avoid'])

    # Get attendance
    attendances = session.query(Attendance).filter(Attendance.person_id == person_id).all()
    present_count = len([a for a in attendances if a.is_present == 1])
    attendance_pct = round((present_count / len(attendances) * 100) if attendances else 0, 1)

    # Get boards
    boards_info = [{
        'id': b.id,
        'title': b.title,
        'type': b.committee_type
    } for b in person.boards]

    # Get recent votes with discussions
    recent_votes = session.query(Vote, Discussion).join(
        Discussion, Vote.discussion_id == Discussion.id
    ).filter(Vote.person_id == person_id).order_by(
        desc(Discussion.discussion_date)
    ).limit(10).all()

    recent_activity = []
    for vote, disc in recent_votes:
        recent_activity.append({
            'date': disc.discussion_date.strftime('%Y-%m-%d') if disc.discussion_date else None,
            'title': disc.title,
            'vote': vote.vote,
            'categories': [{'id': c.id, 'name': c.name} for c in disc.categories[:2]]  # Max 2 categories
        })

    result = {
        'id': person.id,
        'name': person.full_name,
        'title': person.title,
        'role': person.role_obj.name if person.role_obj else None,
        'role_full': f"{person.role_obj.parent.name} > {person.role_obj.name}" if person.role_obj and person.role_obj.parent else (person.role_obj.name if person.role_obj else None),
        'faction': person.faction_obj.name if person.faction_obj else None,
        'faction_full': f"{person.faction_obj.parent.name} > {person.faction_obj.name}" if person.faction_obj and person.faction_obj.parent else (person.faction_obj.name if person.faction_obj else None),
        'terms': [{'term_number': t.term_number, 'label': f'קדנציה {t.term_number}', 'is_current': bool(t.is_current)} for t in person.terms],
        'degree': person.degree,
        'is_active': person.end_date is None,
        'start_date': person.start_date.strftime('%Y-%m-%d') if person.start_date else None,
        'votes': {
            'yes': yes_count,
            'no': no_count,
            'avoid': avoid_count,
            'total': len(votes)
        },
        'attendance': {
            'percentage': attendance_pct,
            'present': present_count,
            'total': len(attendances)
        },
        'boards': boards_info,
        'recent_activity': recent_activity
    }

    session.close()
    return jsonify(result)


@app.route('/api/boards')
def get_boards():
    """Get all boards/committees"""
    session = get_session()
    boards = session.query(Board).all()

    result = []
    for b in boards:
        members_count = len(b.members)
        meetings_count = len(b.meetings)

        result.append({
            'id': b.id,
            'title': b.title,
            'type': b.committee_type,
            'description': b.description,
            'members_count': members_count,
            'meetings_count': meetings_count,
            'is_active': b.end_date is None,
            'start_date': b.start_date.strftime('%Y-%m-%d') if b.start_date else None
        })

    session.close()
    return jsonify(result)


@app.route('/api/discussions')
def get_discussions():
    """Get all discussions with filters"""
    session = get_session()

    # Filters
    category = request.args.get('category')
    discussion_type = request.args.get('type')
    limit = int(request.args.get('limit', 50))
    filter_type = request.args.get('filter_type', 'all')
    filter_value = request.args.get('filter_value')
    year_filter = request.args.get('year')  # Secondary filter for year within term

    # Build query with proper ordering
    query = session.query(Discussion).join(Meeting).order_by(desc(Meeting.meeting_date))

    # Apply time filters using meeting date
    if filter_type == 'year' and filter_value:
        year = int(filter_value)
        query = query.filter(func.strftime('%Y', Meeting.meeting_date) == str(year))
    elif filter_type == 'term' and filter_value:
        term_number = int(filter_value)
        term = session.query(Term).filter_by(term_number=term_number).first()
        if term:
            query = query.filter(Meeting.term_id == term.id)

            # Apply secondary year filter if provided (within the term)
            if year_filter:
                year = int(year_filter)
                query = query.filter(func.strftime('%Y', Meeting.meeting_date) == str(year))

    if category:
        query = query.filter(Discussion.categories.like(f'%{category}%'))
    if discussion_type:
        query = query.filter(Discussion.discussion_type == discussion_type)

    discussions = query.limit(limit).all()

    result = []
    for d in discussions:
        # Determine status based on vote counters
        if d.yes_counter > d.no_counter:
            status = 'approved'
        elif d.no_counter > d.yes_counter:
            status = 'rejected'
        else:
            status = 'pending'

        # Build category hierarchy (parent -> child)
        # Prioritize sub-categories (with parent_id) over parent categories
        category_info = None
        if d.categories:
            # Try to find a sub-category first (one with parent_id)
            sub_category = None
            for cat in d.categories:
                if cat.parent_id:
                    sub_category = cat
                    break

            if sub_category:
                # Found a sub-category, get its parent
                parent_cat = session.query(Category).filter_by(id=sub_category.parent_id).first()
                category_info = {
                    'parent': parent_cat.name if parent_cat else None,
                    'child': sub_category.name
                }
            else:
                # No sub-category found, use the first parent category
                primary_cat = d.categories[0]
                category_info = {
                    'parent': None,
                    'child': primary_cat.name
                }

        result.append({
            'id': d.id,
            'title': d.title,
            'type': ', '.join([dt.name for dt in d.discussion_types]) if d.discussion_types else None,
            'category': category_info,
            'board': d.meeting.board.title if d.meeting and d.meeting.board else None,
            'date': d.discussion_date.strftime('%Y-%m-%d') if d.discussion_date else None,
            'decision': d.decision,
            'status': status,
            'votes': {
                'yes': d.yes_counter,
                'no': d.no_counter,
                'avoid': d.avoid_counter,
                'missing': d.missing_counter
            },
            'budget': d.total_budget
        })

    session.close()
    return jsonify(result)


@app.route('/api/discussion/<int:discussion_id>')
def get_discussion(discussion_id):
    """Get detailed information about a specific discussion"""
    session = get_session()
    discussion = session.query(Discussion).filter(Discussion.id == discussion_id).first()

    if not discussion:
        session.close()
        return jsonify({'error': 'Discussion not found'}), 404

    # Get votes with person info
    votes_data = session.query(Vote, Person).join(
        Person, Vote.person_id == Person.id
    ).filter(Vote.discussion_id == discussion_id).all()

    votes_list = [{
        'person_name': person.full_name,
        'person_role': person.role,
        'vote': vote.vote
    } for vote, person in votes_data]

    # Get meeting info
    meeting = discussion.meeting
    meeting_info = None
    if meeting:
        meeting_info = {
            'id': meeting.id,
            'title': meeting.title,
            'date': meeting.meeting_date.strftime('%Y-%m-%d') if meeting.meeting_date else None,
            'protocol_file': meeting.protocol_file
        }

    result = {
        'id': discussion.id,
        'title': discussion.title,
        'type': discussion.discussion_type,
        'categories': discussion.categories,
        'date': discussion.discussion_date.strftime('%Y-%m-%d') if discussion.discussion_date else None,
        'expert_opinion': discussion.expert_opinion,
        'decision': discussion.decision,
        'votes': {
            'yes': discussion.yes_counter,
            'no': discussion.no_counter,
            'avoid': discussion.avoid_counter,
            'missing': discussion.missing_counter,
            'details': votes_list
        },
        'budget': discussion.confirmed_budget,
        'meeting': meeting_info
    }

    session.close()
    return jsonify(result)


@app.route('/api/meetings')
def get_meetings():
    """Get recent meetings"""
    session = get_session()
    limit = int(request.args.get('limit', 20))
    filter_type = request.args.get('filter_type', 'all')
    filter_value = request.args.get('filter_value')

    query = session.query(Meeting).order_by(desc(Meeting.meeting_date))

    # Apply time filters
    if filter_type == 'year' and filter_value:
        year = int(filter_value)
        query = query.filter(func.strftime('%Y', Meeting.meeting_date) == str(year))
    elif filter_type == 'term' and filter_value:
        term_year = int(filter_value)
        term_start_date = f'{term_year}-01-01'
        next_term = session.query(Person.start_date).filter(
            Person.start_date > term_start_date
        ).order_by(Person.start_date).first()
        term_end_date = next_term[0].strftime('%Y-%m-%d') if next_term else datetime.now().strftime('%Y-%m-%d')
        query = query.filter(
            Meeting.meeting_date >= term_start_date,
            Meeting.meeting_date <= term_end_date
        )

    meetings = query.limit(limit).all()

    result = []
    for m in meetings:
        attendances_count = len(m.attendances)
        present_count = len([a for a in m.attendances if a.is_present == 1])

        result.append({
            'id': m.id,
            'title': m.title,
            'meeting_no': m.meeting_no,
            'date': m.meeting_date.strftime('%Y-%m-%d') if m.meeting_date else None,
            'description': m.description,
            'protocol_file': m.protocol_file,
            'attendances': {
                'total': attendances_count,
                'present': present_count
            },
            'discussions_count': len(m.discussions),
            'board_title': m.board.title if m.board else None
        })

    session.close()
    return jsonify(result)


# ===== WEB PAGES =====

@app.route('/')
def index():
    """Homepage - Dashboard"""
    return render_template('index.html')


@app.route('/persons')
def persons_page():
    """Council members page"""
    return render_template('persons.html')


@app.route('/person/<int:person_id>')
def person_detail_page(person_id):
    """Person detail page"""
    return render_template('person_detail.html', person_id=person_id)


@app.route('/boards')
def boards_page():
    """Boards/Committees page"""
    return render_template('boards.html')


@app.route('/discussions')
def discussions_page():
    """Discussions/Decisions page"""
    return render_template('discussions.html')


@app.route('/discussion/<int:discussion_id>')
def discussion_detail_page(discussion_id):
    """Discussion detail page"""
    return render_template('discussion_detail.html', discussion_id=discussion_id)


@app.route('/api/contact-request', methods=['POST'])
def handle_contact_request():
    """Handle contact requests for adding new municipalities/terms"""
    try:
        data = request.get_json()

        # Validate required fields
        if not data.get('name') or not data.get('email'):
            return jsonify({'error': 'Name and email are required'}), 400

        # Log the request (in production, save to database or send email)
        contact_info = {
            'name': data.get('name'),
            'email': data.get('email'),
            'municipality': data.get('municipality', ''),
            'hasOfficialRole': data.get('hasOfficialRole', ''),
            'officialRole': data.get('officialRole', ''),
            'message': data.get('message', ''),
            'timestamp': datetime.now().isoformat()
        }

        # For now, just log to console
        # TODO: In production, save to database or send email notification
        print('=' * 80)
        print('NEW CONTACT REQUEST:')
        print(f"Name: {contact_info['name']}")
        print(f"Email: {contact_info['email']}")
        print(f"Requested Municipality: {contact_info['municipality']}")
        print(f"Has Official Role: {contact_info['hasOfficialRole']}")
        if contact_info['officialRole']:
            print(f"Official Role: {contact_info['officialRole']}")
        print(f"Message: {contact_info['message']}")
        print(f"Time: {contact_info['timestamp']}")
        print('=' * 80)

        return jsonify({'success': True, 'message': 'Request received'}), 200

    except Exception as e:
        print(f"Error handling contact request: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
