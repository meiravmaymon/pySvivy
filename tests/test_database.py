# -*- coding: utf-8 -*-
"""
Tests for database models and operations.
בדיקות למודלים ופעולות בסיס נתונים
"""
import pytest
import sys
from pathlib import Path
from datetime import datetime, date

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import (
    Person, Meeting, Discussion, Vote, Attendance,
    Board, Term, Faction, Role, AdministrativeCategory
)


class TestPersonModel:
    """Tests for Person model."""

    def test_create_person(self, db_session):
        """Test creating a person."""
        person = Person(
            full_name="ישראל ישראלי",
            gender=1  # 1 for male
        )
        db_session.add(person)
        db_session.commit()

        assert person.id is not None
        assert person.full_name == "ישראל ישראלי"

    def test_person_repr(self, db_session):
        """Test person string representation."""
        person = Person(full_name="דני כהן")
        db_session.add(person)
        db_session.commit()

        repr_str = repr(person)
        assert "דני כהן" in repr_str


class TestMeetingModel:
    """Tests for Meeting model."""

    def test_create_meeting(self, db_session):
        """Test creating a meeting."""
        meeting = Meeting(
            meeting_no="82",
            meeting_date=datetime(2023, 3, 15),
            title="ישיבה רגילה"
        )
        db_session.add(meeting)
        db_session.commit()

        assert meeting.id is not None
        assert meeting.meeting_no == "82"


class TestDiscussionModel:
    """Tests for Discussion model."""

    def test_create_discussion(self, db_session):
        """Test creating a discussion."""
        # Create meeting first
        meeting = Meeting(
            meeting_no="82",
            meeting_date=datetime(2023, 3, 15),
            title="ישיבה"
        )
        db_session.add(meeting)
        db_session.commit()

        discussion = Discussion(
            meeting_id=meeting.id,
            issue_no="1",
            title="אישור תקציב"
        )
        db_session.add(discussion)
        db_session.commit()

        assert discussion.id is not None
        assert discussion.issue_no == "1"

    def test_discussion_with_votes(self, db_session):
        """Test discussion with vote counts."""
        meeting = Meeting(
            meeting_no="83",
            meeting_date=datetime(2023, 4, 1),
            title="ישיבה"
        )
        db_session.add(meeting)
        db_session.commit()

        discussion = Discussion(
            meeting_id=meeting.id,
            issue_no="1",
            title="הצבעה",
            yes_counter=10,
            no_counter=2,
            avoid_counter=1
        )
        db_session.add(discussion)
        db_session.commit()

        assert discussion.yes_counter == 10
        assert discussion.no_counter == 2
        assert discussion.avoid_counter == 1


class TestVoteModel:
    """Tests for Vote model."""

    def test_create_vote(self, db_session):
        """Test creating a vote record."""
        # Create required objects
        person = Person(full_name="שרה לוי")
        meeting = Meeting(
            meeting_no="84",
            meeting_date=datetime(2023, 5, 1),
            title="ישיבה"
        )
        db_session.add_all([person, meeting])
        db_session.commit()

        discussion = Discussion(
            meeting_id=meeting.id,
            issue_no="1",
            title="test"
        )
        db_session.add(discussion)
        db_session.commit()

        vote = Vote(
            discussion_id=discussion.id,
            person_id=person.id,
            vote="yes"
        )
        db_session.add(vote)
        db_session.commit()

        assert vote.id is not None
        assert vote.vote == "yes"


class TestAttendanceModel:
    """Tests for Attendance model."""

    def test_create_attendance(self, db_session):
        """Test creating an attendance record."""
        person = Person(full_name="משה כהן")
        meeting = Meeting(
            meeting_no="85",
            meeting_date=datetime(2023, 6, 1),
            title="ישיבה"
        )
        db_session.add_all([person, meeting])
        db_session.commit()

        attendance = Attendance(
            meeting_id=meeting.id,
            person_id=person.id,
            is_present=1  # 1 = present
        )
        db_session.add(attendance)
        db_session.commit()

        assert attendance.id is not None
        assert attendance.is_present == 1


class TestBoardModel:
    """Tests for Board model."""

    def test_create_board(self, db_session):
        """Test creating a board/committee."""
        board = Board(
            title="ועדת תכנון ובנייה"
        )
        db_session.add(board)
        db_session.commit()

        assert board.id is not None
        assert board.title == "ועדת תכנון ובנייה"


class TestRelationships:
    """Tests for model relationships."""

    def test_meeting_discussions_relationship(self, db_session):
        """Test meeting to discussions relationship."""
        meeting = Meeting(
            meeting_no="86",
            meeting_date=datetime(2023, 7, 1),
            title="ישיבה"
        )
        db_session.add(meeting)
        db_session.commit()

        disc1 = Discussion(meeting_id=meeting.id, issue_no="1", title="סעיף 1")
        disc2 = Discussion(meeting_id=meeting.id, issue_no="2", title="סעיף 2")
        db_session.add_all([disc1, disc2])
        db_session.commit()

        # Query meeting and check discussions
        queried_meeting = db_session.query(Meeting).filter_by(id=meeting.id).first()
        assert len(queried_meeting.discussions) == 2

    def test_discussion_votes_relationship(self, db_session):
        """Test discussion to votes relationship."""
        person1 = Person(full_name="אדם ראשון")
        person2 = Person(full_name="אדם שני")
        meeting = Meeting(
            meeting_no="87",
            meeting_date=datetime(2023, 8, 1),
            title="ישיבה"
        )
        db_session.add_all([person1, person2, meeting])
        db_session.commit()

        discussion = Discussion(
            meeting_id=meeting.id,
            issue_no="1",
            title="הצבעה"
        )
        db_session.add(discussion)
        db_session.commit()

        vote1 = Vote(discussion_id=discussion.id, person_id=person1.id, vote="yes")
        vote2 = Vote(discussion_id=discussion.id, person_id=person2.id, vote="no")
        db_session.add_all([vote1, vote2])
        db_session.commit()

        # Query discussion and check votes
        queried_disc = db_session.query(Discussion).filter_by(id=discussion.id).first()
        assert len(queried_disc.votes) == 2
