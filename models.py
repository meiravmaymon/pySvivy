"""
Database models for Yehud-Monosson Municipal Decision System.

מודל בסיס הנתונים למערכת החלטות מועצת העיר יהוד-מונוסון

Tables:
    - terms: קדנציות (תקופות כהונה)
    - persons: חברי מועצה וסגל
    - roles: תפקידים (היררכי)
    - factions: סיעות (היררכי)
    - boards: ועדות
    - meetings: ישיבות/פרוטוקולים
    - discussions: סעיפי דיון
    - votes: הצבעות
    - attendances: נוכחות
    - categories: קטגוריות דיון (היררכי)
    - discussion_types: סוגי דיון (היררכי)
    - budget_sources: מקורות מימון
    - administrative_categories: סיווג מנהלתי לסעיפים (לפי פקודת העיריות)
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Table, Float, Index
from sqlalchemy.orm import relationship, declarative_base
from datetime import datetime

Base = declarative_base()

# Many-to-many relationship table for Person and Board
person_board = Table('person_board', Base.metadata,
    Column('person_id', Integer, ForeignKey('persons.id'), primary_key=True),
    Column('board_id', Integer, ForeignKey('boards.id'), primary_key=True),
    Column('start_date', DateTime),
    Column('end_date', DateTime, nullable=True)
)

# Many-to-many relationship table for Discussion and Category
discussion_category = Table('discussion_category', Base.metadata,
    Column('discussion_id', Integer, ForeignKey('discussions.id'), primary_key=True),
    Column('category_id', Integer, ForeignKey('categories.id'), primary_key=True)
)

# Many-to-many relationship table for Discussion and DiscussionType
discussion_type_association = Table('discussion_type_association', Base.metadata,
    Column('discussion_id', Integer, ForeignKey('discussions.id'), primary_key=True),
    Column('type_id', Integer, ForeignKey('discussion_types.id'), primary_key=True)
)

# Many-to-many relationship table for Person and Term (for active members across terms)
person_term = Table('person_term', Base.metadata,
    Column('person_id', Integer, ForeignKey('persons.id'), primary_key=True),
    Column('term_id', Integer, ForeignKey('terms.id'), primary_key=True)
)


class Term(Base):
    """Municipal term / Kadenziya (קדנציה) - election period"""
    __tablename__ = 'terms'

    id = Column(Integer, primary_key=True)
    term_number = Column(Integer, nullable=False, unique=True, index=True)  # 15, 16, 17
    start_date = Column(DateTime, nullable=False)  # Election start date
    end_date = Column(DateTime, nullable=False)  # Next election date
    is_current = Column(Integer, default=0)  # 1 if current term

    # Relationships
    meetings = relationship('Meeting', back_populates='term')

    def __repr__(self):
        return f"<Term(number={self.term_number}, period={self.start_date.year}-{self.end_date.year})>"


class Category(Base):
    """Hierarchical category for discussions (קטגוריות דיון)"""
    __tablename__ = 'categories'

    id = Column(Integer, primary_key=True)
    name = Column(String(300), nullable=False, index=True)
    parent_id = Column(Integer, ForeignKey('categories.id'), nullable=True)

    # Self-referential relationship for hierarchy
    parent = relationship('Category', remote_side=[id], backref='children')

    # Many-to-many with discussions
    discussions = relationship('Discussion', secondary=discussion_category, back_populates='categories')

    def __repr__(self):
        return f"<Category(name='{self.name}', parent_id={self.parent_id})>"


class DiscussionType(Base):
    """Hierarchical discussion type (סוג דיון)"""
    __tablename__ = 'discussion_types'

    id = Column(Integer, primary_key=True)
    name = Column(String(300), nullable=False, index=True)
    parent_id = Column(Integer, ForeignKey('discussion_types.id'), nullable=True)

    # Self-referential relationship for hierarchy
    parent = relationship('DiscussionType', remote_side=[id], backref='children')

    # Many-to-many with discussions
    discussions = relationship('Discussion', secondary=discussion_type_association, back_populates='discussion_types')

    def __repr__(self):
        return f"<DiscussionType(name='{self.name}', parent_id={self.parent_id})>"


class Faction(Base):
    """Hierarchical faction/party (סיעות) - city>local_faction or national_party>local_branch"""
    __tablename__ = 'factions'

    id = Column(Integer, primary_key=True)
    name = Column(String(300), nullable=False, index=True)
    parent_id = Column(Integer, ForeignKey('factions.id'), nullable=True)

    # Self-referential relationship for hierarchy
    parent = relationship('Faction', remote_side=[id], backref='children')

    # Relationship with persons
    persons = relationship('Person', back_populates='faction_obj')

    def __repr__(self):
        return f"<Faction(name='{self.name}', parent_id={self.parent_id})>"


class Role(Base):
    """Hierarchical role (בעלי תפקידים) - organization>position"""
    __tablename__ = 'roles'

    id = Column(Integer, primary_key=True)
    name = Column(String(300), nullable=False, index=True)
    parent_id = Column(Integer, ForeignKey('roles.id'), nullable=True)

    # Self-referential relationship for hierarchy
    parent = relationship('Role', remote_side=[id], backref='children')

    # Relationship with persons
    persons = relationship('Person', back_populates='role_obj')

    def __repr__(self):
        return f"<Role(name='{self.name}', parent_id={self.parent_id})>"


class Person(Base):
    """Council member / Municipal representative"""
    __tablename__ = 'persons'

    id = Column(Integer, primary_key=True)
    original_id = Column(String(50))  # ID from Excel file
    title = Column(String(200))
    full_name = Column(String(200), nullable=False, index=True)
    degree = Column(String(100))  # Academic degree
    start_date = Column(DateTime)
    end_date = Column(DateTime, nullable=True)
    gender = Column(Integer)
    miss_counter = Column(Integer, default=0)

    # Foreign keys
    faction_id = Column(Integer, ForeignKey('factions.id'), nullable=True)
    role_id = Column(Integer, ForeignKey('roles.id'), nullable=True)

    # Relationships
    faction_obj = relationship('Faction', back_populates='persons')
    role_obj = relationship('Role', back_populates='persons')
    terms = relationship('Term', secondary=person_term, backref='active_persons')
    boards = relationship('Board', secondary=person_board, back_populates='members')
    votes = relationship('Vote', back_populates='person')
    attendances = relationship('Attendance', back_populates='person')

    def __repr__(self):
        return f"<Person(name='{self.full_name}', role_id={self.role_id})>"


class Board(Base):
    """Committee / Board (ועדה)"""
    __tablename__ = 'boards'

    id = Column(Integer, primary_key=True)
    original_id = Column(String(50))
    title = Column(String(300), nullable=False)
    committee_type = Column(String(200))  # סוגי ועדות
    start_date = Column(DateTime)
    end_date = Column(DateTime, nullable=True)
    description = Column(Text)
    authority_post_id = Column(String(50))

    # Relationships
    members = relationship('Person', secondary=person_board, back_populates='boards')
    meetings = relationship('Meeting', back_populates='board')

    def __repr__(self):
        return f"<Board(title='{self.title}', type='{self.committee_type}')>"


class Meeting(Base):
    """Protocol / Meeting session (ישיבה)"""
    __tablename__ = 'meetings'

    id = Column(Integer, primary_key=True)
    original_id = Column(String(50))
    title = Column(String(300))
    meeting_no = Column(String(50))
    meeting_date = Column(DateTime, index=True)
    description = Column(Text)
    protocol_file = Column(String(500))  # Link to PDF
    board_id = Column(Integer, ForeignKey('boards.id'))

    # Meeting type: 'regular' (מן המניין), 'special' (שלא מן המניין), 'general_assembly' (אסיפה כללית)
    meeting_type = Column(String(50), nullable=True, default='regular')

    # Foreign key to term
    term_id = Column(Integer, ForeignKey('terms.id'))

    # Relationships
    term = relationship('Term', back_populates='meetings')
    board = relationship('Board', back_populates='meetings')
    discussions = relationship('Discussion', back_populates='meeting')
    attendances = relationship('Attendance', back_populates='meeting')

    def __repr__(self):
        return f"<Meeting(no='{self.meeting_no}', date='{self.meeting_date}')>"


class Discussion(Base):
    """Discussion / Section / Issue (סעיף)"""
    __tablename__ = 'discussions'

    id = Column(Integer, primary_key=True)
    original_id = Column(String(50))
    title = Column(String(500), nullable=False)
    issue_no = Column(String(50))  # Section number
    expert_opinion = Column(Text)  # Expert recommendation / דברי הסבר
    decision = Column(Text)  # Decision status: אושר, לא אושר, ירד מסדר היום, etc.
    decision_statement = Column(Text)  # Full decision text / נוסח ההחלטה
    summary = Column(Text)  # AI-generated summary / תקציר
    discussion_date = Column(DateTime, index=True)

    # Total budget amount
    total_budget = Column(Float, nullable=True)

    # Vote counters
    yes_counter = Column(Integer, default=0)
    no_counter = Column(Integer, default=0)
    avoid_counter = Column(Integer, default=0)
    missing_counter = Column(Integer, default=0)

    # Administrative classification (סיווג מנהלתי לפי פקודת העיריות)
    admin_category_id = Column(Integer, ForeignKey('administrative_categories.id'), nullable=True)
    admin_category_confidence = Column(Float, nullable=True)  # 0-1 confidence of auto-classification
    admin_category_auto = Column(Integer, default=0)  # 1 if auto-classified, 0 if manual

    # Foreign keys
    meeting_id = Column(Integer, ForeignKey('meetings.id'))

    # Relationships
    meeting = relationship('Meeting', back_populates='discussions')
    votes = relationship('Vote', back_populates='discussion')
    categories = relationship('Category', secondary=discussion_category, back_populates='discussions')
    discussion_types = relationship('DiscussionType', secondary=discussion_type_association, back_populates='discussions')
    budget_sources = relationship('BudgetSource', back_populates='discussion', cascade='all, delete-orphan')
    admin_category = relationship('AdministrativeCategory', back_populates='discussions')

    def __repr__(self):
        return f"<Discussion(title='{self.title[:50]}...', id={self.id})>"


class BudgetSource(Base):
    """Budget source for a discussion (מקור מימון)"""
    __tablename__ = 'budget_sources'

    id = Column(Integer, primary_key=True)
    discussion_id = Column(Integer, ForeignKey('discussions.id'), nullable=False)
    source_name = Column(String(300), nullable=False)  # Name of budget source
    amount = Column(Float, nullable=False)  # Amount from this source

    # Relationship
    discussion = relationship('Discussion', back_populates='budget_sources')

    def __repr__(self):
        return f"<BudgetSource(source='{self.source_name}', amount={self.amount})>"


class Vote(Base):
    """Individual vote record"""
    __tablename__ = 'votes'

    id = Column(Integer, primary_key=True)
    person_id = Column(Integer, ForeignKey('persons.id'), nullable=False)
    discussion_id = Column(Integer, ForeignKey('discussions.id'), nullable=False)

    # Vote value: 'yes', 'no', 'avoid', 'missing'
    vote = Column(String(20), nullable=False)

    # Relationships
    person = relationship('Person', back_populates='votes')
    discussion = relationship('Discussion', back_populates='votes')

    def __repr__(self):
        return f"<Vote(person_id={self.person_id}, vote='{self.vote}')>"


class Attendance(Base):
    """Meeting attendance record (רישום נוכחות)"""
    __tablename__ = 'attendances'
    __table_args__ = (
        Index('idx_attendance_meeting', 'meeting_id'),
        Index('idx_attendance_person', 'person_id'),
    )

    id = Column(Integer, primary_key=True)
    person_id = Column(Integer, ForeignKey('persons.id'), nullable=False)
    meeting_id = Column(Integer, ForeignKey('meetings.id'), nullable=False)

    # Attendance status: 1 = present (נוכח), 0 = absent (נעדר)
    is_present = Column(Integer, nullable=False, default=1)

    # Relationships
    person = relationship('Person', back_populates='attendances')
    meeting = relationship('Meeting', back_populates='attendances')

    def __repr__(self):
        status = "נוכח" if self.is_present else "נעדר"
        return f"<Attendance(person_id={self.person_id}, status='{status}')>"


class AdministrativeCategory(Base):
    """
    Administrative category for discussions based on Municipal Ordinance
    סיווג מנהלתי לסעיפים לפי פקודת העיריות

    Categories define what type of municipal action requires council approval,
    discussion, or just update.
    """
    __tablename__ = 'administrative_categories'

    id = Column(Integer, primary_key=True)
    code = Column(String(50), nullable=False, unique=True, index=True)  # e.g., BUDGET_ANNUAL
    name_he = Column(String(200), nullable=False)  # Hebrew name: תקציב שנתי
    name_en = Column(String(200))  # English name: Annual Budget
    parent_code = Column(String(50), nullable=True)  # Parent category code for hierarchy
    description = Column(Text)  # Description of what falls under this category
    decision_level = Column(String(50))  # 'approval', 'discussion', 'update', 'formal'
    keywords = Column(Text)  # Comma-separated keywords for auto-classification

    # Relationships
    discussions = relationship('Discussion', back_populates='admin_category')

    def __repr__(self):
        return f"<AdministrativeCategory(code='{self.code}', name='{self.name_he}')>"


# Constants for vote types
VOTE_YES = 'yes'      # בעד
VOTE_NO = 'no'        # נגד
VOTE_AVOID = 'avoid'  # נמנע
VOTE_MISSING = 'missing'  # חסר

# Constants for meeting types
MEETING_REGULAR = 'מן המניין'
MEETING_SPECIAL = 'שלא מן המניין'
MEETING_ASSEMBLY = 'אסיפה כללית'

# Constants for decision statuses
DECISION_APPROVED = 'אושר'
DECISION_REJECTED = 'לא אושר'
DECISION_REMOVED = 'ירד מסדר היום'
DECISION_REPORT = 'דיווח ועדכון'
DECISION_COMMITTEE = 'הופנה לוועדה'
DECISION_POSTPONED = 'נדחה לדיון נוסף'

# Constants for administrative decision levels
ADMIN_LEVEL_APPROVAL = 'approval'  # אישור מחייב - המועצה חייבת לאשר
ADMIN_LEVEL_DISCUSSION = 'discussion'  # דיון והחלטה - דורש דיון והצבעה
ADMIN_LEVEL_UPDATE = 'update'  # לידיעה - עדכון ודיווח בלבד
ADMIN_LEVEL_FORMAL = 'formal'  # פורמלי - אישור טכני

# Administrative category codes (matching docs/discussion_types_classification.md)
ADMIN_BUDGET_ANNUAL = 'BUDGET_ANNUAL'
ADMIN_BUDGET_TABAR = 'BUDGET_TABAR'
ADMIN_BUDGET_RESERVE = 'BUDGET_RESERVE'
ADMIN_BUDGET_TRANSFER = 'BUDGET_TRANSFER'
ADMIN_CONTRACT_APPROVAL = 'CONTRACT_APPROVAL'
ADMIN_CONTRACT_TENDER = 'CONTRACT_TENDER'
ADMIN_CONTRACT_EXCEPTION = 'CONTRACT_EXCEPTION'
ADMIN_APPOINT_AUDITOR = 'APPOINT_AUDITOR'
ADMIN_APPOINT_TREASURER = 'APPOINT_TREASURER'
ADMIN_APPOINT_SENIOR = 'APPOINT_SENIOR'
ADMIN_APPOINT_COMMITTEE = 'APPOINT_COMMITTEE'
ADMIN_APPOINT_BOARD = 'APPOINT_BOARD'
ADMIN_BYLAW_NEW = 'BYLAW_NEW'
ADMIN_BYLAW_AMENDMENT = 'BYLAW_AMENDMENT'
ADMIN_BYLAW_FEE = 'BYLAW_FEE'
ADMIN_PROPERTY_SALE = 'PROPERTY_SALE'
ADMIN_PROPERTY_PURCHASE = 'PROPERTY_PURCHASE'
ADMIN_PROPERTY_LEASE = 'PROPERTY_LEASE'
ADMIN_PROPERTY_ENCUMBRANCE = 'PROPERTY_ENCUMBRANCE'
ADMIN_LOAN_TAKE = 'LOAN_TAKE'
ADMIN_LOAN_GUARANTEE = 'LOAN_GUARANTEE'
ADMIN_LOAN_INVESTMENT = 'LOAN_INVESTMENT'
ADMIN_CORP_ESTABLISH = 'CORP_ESTABLISH'
ADMIN_CORP_CHANGE = 'CORP_CHANGE'
ADMIN_CORP_DISSOLVE = 'CORP_DISSOLVE'
ADMIN_PLAN_MASTER = 'PLAN_MASTER'
ADMIN_PLAN_DETAIL = 'PLAN_DETAIL'
ADMIN_PLAN_EXCEPTION = 'PLAN_EXCEPTION'
ADMIN_NAME_STREET = 'NAME_STREET'
ADMIN_NAME_PLACE = 'NAME_PLACE'
ADMIN_NAME_MEMORIAL = 'NAME_MEMORIAL'
ADMIN_REPORT_FINANCIAL = 'REPORT_FINANCIAL'
ADMIN_REPORT_AUDIT = 'REPORT_AUDIT'
ADMIN_REPORT_ACCOUNTANT = 'REPORT_ACCOUNTANT'
ADMIN_REPORT_QUARTERLY = 'REPORT_QUARTERLY'
ADMIN_UPDATE_MAYOR = 'UPDATE_MAYOR'
ADMIN_UPDATE_QUERY = 'UPDATE_QUERY'
ADMIN_UPDATE_COMMITTEE = 'UPDATE_COMMITTEE'
ADMIN_UPDATE_PERSONAL = 'UPDATE_PERSONAL'
ADMIN_PROTOCOL_COUNCIL = 'PROTOCOL_COUNCIL'
ADMIN_PROTOCOL_COMMITTEE = 'PROTOCOL_COMMITTEE'
ADMIN_EMERGENCY_DECISION = 'EMERGENCY_DECISION'
ADMIN_EMERGENCY_REPORT = 'EMERGENCY_REPORT'
ADMIN_WELFARE_PROGRAM = 'WELFARE_PROGRAM'
ADMIN_EDUCATION_PROGRAM = 'EDUCATION_PROGRAM'
ADMIN_OTHER_GENERAL = 'OTHER_GENERAL'
ADMIN_OTHER_CEREMONY = 'OTHER_CEREMONY'
