# -*- coding: utf-8 -*-
"""
Pytest configuration and fixtures for Svivy tests.
"""
import os
import sys
import pytest
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base


@pytest.fixture(scope='session')
def test_db_engine():
    """Create a test database engine (in-memory SQLite)."""
    engine = create_engine('sqlite:///:memory:', echo=False)
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture(scope='function')
def db_session(test_db_engine):
    """Create a new database session for each test."""
    Session = sessionmaker(bind=test_db_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def sample_ocr_text():
    """Sample OCR text for testing extraction functions."""
    return """
    פרוטוקול ישיבת מועצת העיר יהוד-מונוסון מס' 82
    מיום 15/03/2023

    נוכחים:
    ראש העיר: יוסי בן דוד
    חברי מועצה:
    1. דני כהן
    2. שרה לוי
    3. משה ישראלי

    סעיף מס' 1
    אישור תקציב פיתוח שכונת נווה אפק
    סך התב"ר: 250,000 ש"ח
    מקורות מימון: משרד השיכון 150,000 ש"ח, קרנות הרשות 100,000 ש"ח

    הצבעה:
    בעד: 12
    נגד: 0
    נמנעים: 1

    החלטה: אושר פה אחד

    סעיף מס' 2
    דיווח על פעילות מחלקת החינוך

    לידיעה בלבד
    """


@pytest.fixture
def sample_reversed_text():
    """Sample reversed Hebrew text (as it comes from OCR)."""
    return """
    .תושרה תונרק -ןומימ תורוקמ .₪ 250,000-ר"בתה ךס
    :ןומימ תורוקמ
    ח"ש 150,000 ןוכישה דרשמ
    ח"ש 100,000 תושרה תונרק
    """


@pytest.fixture
def sample_budget_text():
    """Sample text with budget information."""
    return """
    סעיף מס' 5: פיתוח תשתיות בכביש 46
    סך התב"ר: 500,000 ש"ח
    מקורות מימון:
    - משרד התחבורה: 300,000 ש"ח
    - עירייה: 200,000 ש"ח

    דברי הסבר:
    הפרויקט כולל שיפוץ מדרכות והרחבת הכביש.
    """
