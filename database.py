"""
Database connection and session management
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from models import Base

# Database file path
DATABASE_URL = 'sqlite:///svivyNew.db'

# Create engine
engine = create_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL debugging
    connect_args={'check_same_thread': False}  # Needed for SQLite
)

# Create session factory
session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)


def init_db():
    """Initialize database - create all tables"""
    Base.metadata.create_all(engine)
    print("Database initialized successfully!")


def get_session():
    """Get a database session"""
    return Session()


def close_session():
    """Close the session"""
    Session.remove()


if __name__ == '__main__':
    # Initialize database when run directly
    init_db()
    print(f"Database created at: {DATABASE_URL}")
