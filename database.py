"""
Database connection and session management for Svivy Municipal System.

מודול ניהול חיבורי בסיס הנתונים עבור מערכת סביבי - ניהול פרוטוקולים עירוניים
"""
import os
import logging
from contextlib import contextmanager
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, scoped_session
from models import Base

# Configure logging
logger = logging.getLogger(__name__)

# Database configuration
DATABASE_NAME = 'svivyNew.db'
DATABASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_PATH = os.path.join(DATABASE_DIR, DATABASE_NAME)
DATABASE_URL = f'sqlite:///{DATABASE_PATH}'

# Create engine with optimized settings for SQLite
engine = create_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL debugging
    connect_args={
        'check_same_thread': False,  # Required for multi-threaded access
        'timeout': 30  # Connection timeout in seconds
    },
    pool_pre_ping=True  # Verify connections before use
)


# Enable foreign key support for SQLite
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# Create session factory
session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)


def init_db():
    """Initialize database - create all tables."""
    Base.metadata.create_all(engine)
    print(f"Database initialized: {DATABASE_PATH}")


def get_session():
    """Get a database session."""
    return Session()


def close_session():
    """Close and remove the current session."""
    Session.remove()


@contextmanager
def session_scope():
    """
    Context manager for database sessions with automatic commit/rollback.

    Usage:
        with session_scope() as session:
            session.add(new_object)
            # Commits automatically on success, rolls back on exception
    """
    session = Session()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database error, rolling back: {e}")
        raise
    finally:
        session.close()


def get_db_stats():
    """Get database statistics."""
    from models import Person, Meeting, Discussion, Vote, Attendance, Board

    with session_scope() as session:
        stats = {
            'persons': session.query(Person).count(),
            'meetings': session.query(Meeting).count(),
            'discussions': session.query(Discussion).count(),
            'votes': session.query(Vote).count(),
            'attendances': session.query(Attendance).count(),
            'boards': session.query(Board).count(),
            'database_path': DATABASE_PATH,
            'database_size_mb': round(os.path.getsize(DATABASE_PATH) / (1024 * 1024), 2)
        }
        return stats


if __name__ == '__main__':
    init_db()
    stats = get_db_stats()
    print(f"\nDatabase Statistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
