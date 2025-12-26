"""
Database models for Yehud-Monosson Municipal Decision System
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, Table, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
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
    expert_opinion = Column(Text)  # Expert recommendation (clean text without HTML)
    decision = Column(Text)  # Final decision
    discussion_date = Column(DateTime, index=True)

    # Total budget amount
    total_budget = Column(Float, nullable=True)

    # Vote counters
    yes_counter = Column(Integer, default=0)
    no_counter = Column(Integer, default=0)
    avoid_counter = Column(Integer, default=0)
    missing_counter = Column(Integer, default=0)

    # Foreign keys
    meeting_id = Column(Integer, ForeignKey('meetings.id'))

    # Relationships
    meeting = relationship('Meeting', back_populates='discussions')
    votes = relationship('Vote', back_populates='discussion')
    categories = relationship('Category', secondary=discussion_category, back_populates='discussions')
    discussion_types = relationship('DiscussionType', secondary=discussion_type_association, back_populates='discussions')
    budget_sources = relationship('BudgetSource', back_populates='discussion', cascade='all, delete-orphan')

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
    """Meeting attendance record"""
    __tablename__ = 'attendances'

    id = Column(Integer, primary_key=True)
    person_id = Column(Integer, ForeignKey('persons.id'), nullable=False)
    meeting_id = Column(Integer, ForeignKey('meetings.id'), nullable=False)

    # Attendance status: True = present, False = missing
    is_present = Column(Integer, nullable=False)  # 0 or 1

    # Relationships
    person = relationship('Person', back_populates='attendances')
    meeting = relationship('Meeting', back_populates='attendances')

    def __repr__(self):
        status = "Present" if self.is_present else "Missing"
        return f"<Attendance(person_id={self.person_id}, status='{status}')>"
