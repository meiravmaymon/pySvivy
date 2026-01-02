"""
Get discussion titles from database for meeting 97
"""
from database import get_session
from models import Discussion

session = get_session()
discussions = session.query(Discussion).filter_by(meeting_id=97).order_by(Discussion.issue_no).all()

print(f"Meeting 97 has {len(discussions)} discussions in database:\n")
for d in discussions:
    print(f"{d.issue_no}. {d.title}")

session.close()
