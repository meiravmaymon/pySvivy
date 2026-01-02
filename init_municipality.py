"""
Initialize municipality data for Svivy system.

This script:
1. Creates the Yehud-Monosson municipality record
2. Updates all existing data to link to this municipality

Run after alembic migration: alembic upgrade head
"""
from datetime import datetime
from database import get_session
from models import Municipality, Term, Person, Board, Meeting


def create_yehud_monosson():
    """Create Yehud-Monosson municipality record."""
    return Municipality(
        semel='6600',
        name_he='יהוד-מונוסון',
        name_en='Yehud-Monosson',
        municipality_type='עירייה',
        region='מרכז',
        created_date=datetime.utcnow()
    )


def init_municipality():
    """Initialize municipality and link existing data."""
    with get_session() as session:
        # Check if municipality already exists
        existing = session.query(Municipality).filter_by(semel='6600').first()
        if existing:
            print(f"Municipality already exists: {existing.name_he} (id={existing.id})")
            municipality = existing
        else:
            # Create new municipality
            municipality = create_yehud_monosson()
            session.add(municipality)
            session.flush()  # Get the ID
            print(f"Created municipality: {municipality.name_he} (id={municipality.id})")

        # Update all terms
        terms_updated = session.query(Term).filter(
            Term.municipality_id.is_(None)
        ).update({Term.municipality_id: municipality.id})
        print(f"Updated {terms_updated} terms")

        # Update all persons
        persons_updated = session.query(Person).filter(
            Person.municipality_id.is_(None)
        ).update({Person.municipality_id: municipality.id})
        print(f"Updated {persons_updated} persons")

        # Update all boards
        boards_updated = session.query(Board).filter(
            Board.municipality_id.is_(None)
        ).update({Board.municipality_id: municipality.id})
        print(f"Updated {boards_updated} boards")

        # Update all meetings
        meetings_updated = session.query(Meeting).filter(
            Meeting.municipality_id.is_(None)
        ).update({Meeting.municipality_id: municipality.id})
        print(f"Updated {meetings_updated} meetings")

        session.commit()
        print("\nMunicipality initialization complete!")

        # Print summary
        print(f"\nSummary for {municipality.name_he}:")
        print(f"  - Terms: {session.query(Term).filter_by(municipality_id=municipality.id).count()}")
        print(f"  - Persons: {session.query(Person).filter_by(municipality_id=municipality.id).count()}")
        print(f"  - Boards: {session.query(Board).filter_by(municipality_id=municipality.id).count()}")
        print(f"  - Meetings: {session.query(Meeting).filter_by(municipality_id=municipality.id).count()}")


if __name__ == '__main__':
    init_municipality()
