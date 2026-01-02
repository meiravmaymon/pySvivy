"""
Import data from Excel files into the database
"""
import sys
import pandas as pd
from datetime import datetime
from database import init_db, get_session
from models import Person, Board, Meeting, Discussion, Vote, Attendance, Term, Category, DiscussionType, Faction, Role, BudgetSource, Municipality
import re
from html import unescape
from php_unserialize import php_unserialize_simple, parse_attendees_list, extract_vote_from_attendee

# Configure UTF-8 output
sys.stdout.reconfigure(encoding='utf-8')

# File paths
FILES = {
    'persons': r'yehudCsv\-מועצה-Export-2025-December-22-1758.xlsx',
    'discussions': r'yehudCsv\-Export-2025-December-22-1730 (1).xlsx',
    'meetings': r'yehudCsv\-Export-2025-December-22-1732 (1).xlsx',
    'boards': r'yehudCsv\-Export-2025-December-22-1734 (1).xlsx'
}

# Terms definitions based on election dates
TERMS = [
    {
        'term_number': 15,
        'start_date': datetime(2013, 11, 1),  # November 2013
        'end_date': datetime(2018, 10, 31),   # October 2018
        'is_current': 0
    },
    {
        'term_number': 16,
        'start_date': datetime(2018, 11, 1),  # November 2018
        'end_date': datetime(2024, 2, 28),    # February 2024
        'is_current': 0
    },
    {
        'term_number': 17,
        'start_date': datetime(2024, 3, 1),   # March 2024
        'end_date': datetime(2028, 11, 30),   # November 2028
        'is_current': 1
    }
]


def clean_html(html_text):
    """Remove HTML tags and decode entities, keeping only clean text"""
    if not html_text or pd.isna(html_text):
        return ''

    text = str(html_text)
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Decode HTML entities
    text = unescape(text)
    # Clean up extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def parse_date(date_value):
    """Parse various date formats to datetime object with Israeli format preference"""
    if pd.isna(date_value):
        return None

    if isinstance(date_value, datetime):
        return date_value

    if isinstance(date_value, str):
        date_value = date_value.strip()

        # Try different date formats
        # NOTE: Israeli format (DD/MM/YYYY) should be tried BEFORE American format (MM/DD/YYYY)
        formats = [
            '%Y-%m-%d %H:%M:%S',  # ISO with time
            '%Y-%m-%d',           # ISO without time
            '%d/%m/%Y',           # Israeli/European format (DAY/MONTH/YEAR) - TRY FIRST
            '%m/%d/%Y'            # American format (MONTH/DAY/YEAR) - TRY SECOND
        ]

        # Smart detection: if format is DD/MM/YYYY, check if day > 12
        # This helps disambiguate between Israeli and American formats
        if '/' in date_value:
            parts = date_value.split('/')
            if len(parts) == 3:
                try:
                    first_num = int(parts[0])
                    second_num = int(parts[1])

                    # If first number > 12, it MUST be DD/MM/YYYY
                    if first_num > 12:
                        try:
                            return datetime.strptime(date_value, '%d/%m/%Y')
                        except ValueError:
                            pass

                    # If second number > 12, it MUST be MM/DD/YYYY
                    elif second_num > 12:
                        try:
                            return datetime.strptime(date_value, '%m/%d/%Y')
                        except ValueError:
                            pass
                except (ValueError, IndexError):
                    pass

        # Try all formats in order
        for fmt in formats:
            try:
                return datetime.strptime(date_value, fmt)
            except ValueError:
                continue

    return None


def get_term_for_date(date_value, term_map):
    """Determine which term a date belongs to"""
    if not date_value:
        return None

    for term in term_map.values():
        if term.start_date <= date_value < term.end_date:
            return term
    return None


def parse_hierarchical_field(value_str):
    """
    Parse hierarchical field with '>' separator
    Returns list of parts from parent to child
    Example: "שירות ליחידה>מרכזים קהילתיים" -> ["שירות ליחידה", "מרכזים קהילתיים"]
    """
    if not value_str or pd.isna(value_str):
        return []

    value_str = str(value_str).strip()
    if not value_str:
        return []

    # Split by '>' and clean up whitespace
    parts = [part.strip() for part in value_str.split('>')]
    return [part for part in parts if part]  # Remove empty parts


def parse_budget_sources(budget_data_str):
    """
    Parse budget sources from PHP serialized data
    Returns list of tuples: [(source_name, amount), ...]
    """
    if not budget_data_str or pd.isna(budget_data_str):
        return [], 0

    budget_data_str = str(budget_data_str).strip()
    if not budget_data_str:
        return [], 0

    sources = []
    total = 0

    # Check if it's an array of budget sources
    if budget_data_str.startswith('a:'):
        # Try to parse as array of items
        try:
            # Split by budget items - look for patterns like a:14:{...}
            # This is a simplified parser for nested arrays
            items = re.findall(r'a:\d+:\{[^}]+\}', budget_data_str)

            if not items:
                # Try parsing the whole thing as a single item
                parsed = php_unserialize_simple(budget_data_str)
                if parsed and isinstance(parsed, dict):
                    name = parsed.get('name', '')
                    amount_str = parsed.get('budget_amount', '0')
                    try:
                        amount = float(amount_str)
                        if name and amount > 0:
                            sources.append((name, amount))
                            total += amount
                    except (ValueError, TypeError):
                        pass
            else:
                # Parse each item
                for item_str in items:
                    parsed = php_unserialize_simple(item_str)
                    if parsed and isinstance(parsed, dict):
                        name = parsed.get('name', '')
                        amount_str = parsed.get('budget_amount', '0')
                        try:
                            amount = float(amount_str)
                            if name and amount > 0:
                                sources.append((name, amount))
                                total += amount
                        except (ValueError, TypeError):
                            pass
        except Exception:
            pass

    return sources, total


def get_or_create_hierarchical_items(session, model, value_str, cache, **extra_attrs):
    """
    Parse hierarchical string and create parent-child items
    Returns list of created/existing items (from parent to deepest child)

    Args:
        session: Database session
        model: Category or DiscussionType class
        value_str: String like "parent>child>grandchild"
        cache: Dictionary cache for quick lookups {name: item}
        **extra_attrs: Additional attributes to set on new items (e.g., municipality_id, faction_type)
    """
    parts = parse_hierarchical_field(value_str)
    if not parts:
        return []

    items = []
    parent_id = None

    for part in parts:
        # Check cache first
        cache_key = f"{parent_id}:{part}"
        if cache_key in cache:
            item = cache[cache_key]
        else:
            # Check if exists in database
            query = session.query(model).filter_by(name=part, parent_id=parent_id)
            item = query.first()

            if not item:
                # Create new item with extra attributes
                item = model(name=part, parent_id=parent_id, **extra_attrs)
                session.add(item)
                session.flush()  # Get the ID

            cache[cache_key] = item

        items.append(item)
        parent_id = item.id

    return items


def create_terms(session, municipality_id=None):
    """Create term records based on election periods"""
    print("\n=== Creating Terms (Kadenziyot) ===")

    term_map = {}

    for term_data in TERMS:
        # Check if term already exists
        existing = session.query(Term).filter_by(term_number=term_data['term_number']).first()
        if existing:
            term_map[term_data['term_number']] = existing
            continue

        term = Term(
            term_number=term_data['term_number'],
            start_date=term_data['start_date'],
            end_date=term_data['end_date'],
            is_current=term_data['is_current'],
            municipality_id=municipality_id
        )
        session.add(term)
        term_map[term_data['term_number']] = term

    session.commit()
    print(f"✓ Created {len(term_map)} terms")
    return term_map


def import_boards(session, municipality_id=None):
    """Import boards/committees from Excel"""
    print("\n=== Importing Boards/Committees ===")
    df = pd.read_excel(FILES['boards'])

    board_map = {}  # Map original_id to Board object

    for _, row in df.iterrows():
        original_id = str(row.get('id', ''))

        # Skip if already exists
        existing = session.query(Board).filter_by(original_id=original_id).first()
        if existing:
            board_map[original_id] = existing
            continue

        board = Board(
            original_id=original_id,
            title=row.get('Title', ''),
            committee_type=row.get('סוגי ועדות', ''),
            start_date=parse_date(row.get('start_date')),
            end_date=parse_date(row.get('end_date')),
            description=row.get('board_desc', ''),
            authority_post_id=str(row.get('authority_post_id', '')),
            municipality_id=municipality_id
        )
        session.add(board)
        board_map[original_id] = board

    session.commit()
    print(f"✓ Imported {len(board_map)} boards")
    return board_map


def import_persons(session, board_map, term_map, municipality_id=None):
    """Import persons/council members from Excel"""
    print("\n=== Importing Council Members ===")
    df = pd.read_excel(FILES['persons'])

    person_map = {}  # Map original_id to Person object
    person_name_map = {}  # Map full_name to Person object for matching
    faction_cache = {}
    role_cache = {}

    for _, row in df.iterrows():
        start_date = parse_date(row.get('start_date'))
        end_date = parse_date(row.get('end_date'))

        # Parse faction (city>faction_name) - factions are local to municipality
        faction_str = row.get('סיעות', '')
        faction_items = get_or_create_hierarchical_items(
            session, Faction, faction_str, faction_cache,
            faction_type='local', municipality_id=municipality_id
        )
        faction_obj = faction_items[-1] if faction_items else None  # Get the deepest (most specific) faction

        # Parse role (organization>position)
        role_str = row.get('בעלי תפקידים', '')
        role_items = get_or_create_hierarchical_items(session, Role, role_str, role_cache)
        role_obj = role_items[-1] if role_items else None  # Get the deepest (most specific) role

        person = Person(
            original_id=str(row.get('id', '')),
            title=row.get('Title', ''),
            full_name=row.get('full_name', ''),
            degree=row.get('degree', ''),
            start_date=start_date,
            end_date=end_date,
            gender=int(row.get('gender', 0)) if pd.notna(row.get('gender')) else None,
            miss_counter=int(row.get('miss_counter', 0)) if pd.notna(row.get('miss_counter')) else 0,
            faction_id=faction_obj.id if faction_obj else None,
            role_id=role_obj.id if role_obj else None,
            municipality_id=municipality_id  # municipality_id passed to function
        )
        session.add(person)
        session.flush()  # Get person.id

        # Link person to all relevant terms
        # If no end_date, person is active across multiple terms
        for term_num, term in term_map.items():
            # Person belongs to this term if:
            # 1. They started before/during this term AND
            # 2. They haven't ended OR they ended after term started
            if start_date:
                if start_date <= term.end_date:
                    if not end_date or end_date >= term.start_date:
                        person.terms.append(term)

        person_map[person.original_id] = person
        person_name_map[person.full_name] = person

        # Parse authorities_ids to link person to boards
        authorities_ids = row.get('authorities_ids', '')
        if authorities_ids and isinstance(authorities_ids, str):
            auth_data = php_unserialize_simple(authorities_ids)
            if auth_data:
                # Link person to boards (simplified - can be enhanced later)
                for board_id, board in board_map.items():
                    if board_id in str(authorities_ids):
                        person.boards.append(board)

    session.commit()
    print(f"✓ Imported {len(person_map)} persons")
    print(f"✓ Created {len(faction_cache)} unique factions")
    print(f"✓ Created {len(role_cache)} unique roles")
    return person_map, person_name_map


def import_meetings(session, board_map, term_map, municipality_id=None):
    """Import meetings/protocols from Excel"""
    print("\n=== Importing Meetings/Protocols ===")
    df = pd.read_excel(FILES['meetings'])

    meeting_map = {}  # Map original_id to Meeting object

    for _, row in df.iterrows():
        # Find the board for this meeting
        board_id = str(row.get('board_post_id', ''))
        board = board_map.get(board_id)

        meeting_date = parse_date(row.get('meeting_date'))

        # Determine term based on meeting_date
        term = get_term_for_date(meeting_date, term_map) if meeting_date else None

        meeting = Meeting(
            original_id=str(row.get('id', '')),
            title=row.get('Title', ''),
            meeting_no=str(row.get('meeting_no', '')),
            meeting_date=meeting_date,
            description=row.get('meeting_desc', ''),
            protocol_file=row.get('protocol_file', ''),
            board_id=board.id if board else None,
            term_id=term.id if term else None,
            municipality_id=municipality_id
        )
        session.add(meeting)
        meeting_map[meeting.original_id] = meeting

    session.commit()
    print(f"✓ Imported {len(meeting_map)} meetings")
    return meeting_map


def import_discussions_and_votes(session, meeting_map, person_name_map):
    """Import discussions, parse categories/types, and extract votes"""
    print("\n=== Importing Discussions, Categories, Types and Votes ===")
    df = pd.read_excel(FILES['discussions'])

    discussion_count = 0
    vote_count = 0

    # Caches for hierarchical data
    category_cache = {}
    type_cache = {}

    for _, row in df.iterrows():
        # Find the meeting for this discussion
        meeting_id_raw = str(row.get('meeting_id', ''))
        meeting_id = meeting_id_raw.split('|')[0] if meeting_id_raw and '|' in meeting_id_raw else meeting_id_raw
        meeting = meeting_map.get(meeting_id)

        # Use full_date as discussion_date
        discussion_date = parse_date(row.get('full_date')) or parse_date(row.get('discussion_date'))

        # Clean expert opinion HTML
        expert_html = row.get('expert', '')
        expert_clean = clean_html(expert_html)

        # Parse budget sources
        budget_str = row.get('budgets', '')
        budget_sources_list, total_budget = parse_budget_sources(budget_str)

        discussion = Discussion(
            original_id=str(row.get('id', '')),
            title=row.get('Title', ''),
            issue_no=str(row.get('issue_no', '')),
            expert_opinion=expert_clean,  # Clean text without HTML
            decision=row.get('desition', ''),
            discussion_date=discussion_date,
            total_budget=total_budget if total_budget > 0 else None,
            yes_counter=int(row.get('yes_counter', 0)) if pd.notna(row.get('yes_counter')) else 0,
            no_counter=int(row.get('no_counter', 0)) if pd.notna(row.get('no_counter')) else 0,
            avoid_counter=int(row.get('aviod_counter', 0)) if pd.notna(row.get('aviod_counter')) else 0,
            missing_counter=int(row.get('missing_counter', 0)) if pd.notna(row.get('missing_counter')) else 0,
            meeting_id=meeting.id if meeting else None
        )
        session.add(discussion)
        session.flush()  # Get the discussion.id
        discussion_count += 1

        # Add budget sources
        for source_name, amount in budget_sources_list:
            budget_source = BudgetSource(
                discussion_id=discussion.id,
                source_name=source_name,
                amount=amount
            )
            session.add(budget_source)

        # Parse and link categories (קטגוריות דיון)
        categories_str = row.get('קטגוריות דיון', '')
        if categories_str:
            category_items = get_or_create_hierarchical_items(session, Category, categories_str, category_cache)
            # Link all items in the hierarchy to the discussion
            for cat in category_items:
                if cat not in discussion.categories:
                    discussion.categories.append(cat)

        # Parse and link discussion types (סוג דיון)
        type_str = row.get('סוג דיון', '')
        if type_str:
            type_items = get_or_create_hierarchical_items(session, DiscussionType, type_str, type_cache)
            # Link all items in the hierarchy to the discussion
            for dtype in type_items:
                if dtype not in discussion.discussion_types:
                    discussion.discussion_types.append(dtype)

        # Parse attendees to extract votes
        attendees_data = row.get('attendees', '')
        if attendees_data and isinstance(attendees_data, str):
            attendees = parse_attendees_list(attendees_data)

            for attendee in attendees:
                # Match person by name
                person_name = attendee.get('name', '').strip()
                person = person_name_map.get(person_name)

                if person:
                    vote_value = extract_vote_from_attendee(attendee)
                    vote = Vote(
                        person_id=person.id,
                        discussion_id=discussion.id,
                        vote=vote_value
                    )
                    session.add(vote)
                    vote_count += 1

    session.commit()

    # Count budget sources
    budget_sources_count = session.query(BudgetSource).count()

    print(f"✓ Imported {discussion_count} discussions")
    print(f"✓ Created {len(category_cache)} unique categories")
    print(f"✓ Created {len(type_cache)} unique discussion types")
    print(f"✓ Created {budget_sources_count} budget sources")
    print(f"✓ Extracted {vote_count} votes")


def import_attendances(session, meeting_map, person_name_map):
    """Import attendance records from meetings"""
    print("\n=== Importing Attendance Records ===")
    df = pd.read_excel(FILES['meetings'])

    attendance_count = 0

    for _, row in df.iterrows():
        meeting_id = str(row.get('id', ''))
        meeting = meeting_map.get(meeting_id)

        if not meeting:
            continue

        # Parse attendees data
        attendees_data = row.get('attendees', '')
        if attendees_data and isinstance(attendees_data, str):
            attendees = parse_attendees_list(attendees_data)

            for attendee in attendees:
                # Match person by name
                person_name = attendee.get('name', '').strip()
                person = person_name_map.get(person_name)

                if person:
                    is_missing = attendee.get('is_missing', '0')
                    is_present = 1 if is_missing == '0' else 0

                    attendance = Attendance(
                        person_id=person.id,
                        meeting_id=meeting.id,
                        is_present=is_present
                    )
                    session.add(attendance)
                    attendance_count += 1

    session.commit()
    print(f"✓ Imported {attendance_count} attendance records")


def main():
    """Main import process"""
    print("=" * 60)
    print("YEHUD-MONOSSON MUNICIPAL DATA IMPORT")
    print("=" * 60)

    # Initialize database
    print("\nInitializing database...")
    init_db()

    # Get database session
    session = get_session()

    try:
        # Get or create Yehud-Monosson municipality
        municipality = session.query(Municipality).filter_by(semel='6600').first()
        if not municipality:
            municipality = Municipality(
                semel='6600',
                name_he='יהוד-מונוסון',
                name_en='Yehud-Monosson',
                municipality_type='עירייה'
            )
            session.add(municipality)
            session.commit()
            print(f"✓ Created municipality: {municipality.name_he}")
        municipality_id = municipality.id

        # Create terms first (based on election dates)
        term_map = create_terms(session, municipality_id)

        # Import in order of dependencies
        board_map = import_boards(session, municipality_id)
        person_map, person_name_map = import_persons(session, board_map, term_map, municipality_id)
        meeting_map = import_meetings(session, board_map, term_map, municipality_id)
        import_discussions_and_votes(session, meeting_map, person_name_map)
        import_attendances(session, meeting_map, person_name_map)

        print("\n" + "=" * 60)
        print("✓ DATA IMPORT COMPLETED SUCCESSFULLY!")
        print("=" * 60)

        # Print summary statistics
        print("\nDatabase Statistics:")
        print(f"  Terms: {session.query(Term).count()}")
        print(f"  Persons: {session.query(Person).count()}")
        print(f"  Factions: {session.query(Faction).count()}")
        print(f"  Roles: {session.query(Role).count()}")
        print(f"  Boards: {session.query(Board).count()}")
        print(f"  Meetings: {session.query(Meeting).count()}")
        print(f"  Discussions: {session.query(Discussion).count()}")
        print(f"  Categories: {session.query(Category).count()}")
        print(f"  Discussion Types: {session.query(DiscussionType).count()}")
        print(f"  Budget Sources: {session.query(BudgetSource).count()}")
        print(f"  Votes: {session.query(Vote).count()}")
        print(f"  Attendance Records: {session.query(Attendance).count()}")

    except Exception as e:
        print(f"\n✗ Error during import: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
    finally:
        session.close()


if __name__ == '__main__':
    main()
