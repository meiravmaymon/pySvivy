# CLAUDE.md - Svivy Municipal Management System

## Project Overview

Svivy (סביבי) is a municipal management system for tracking decisions, meetings, council members, and voting records in Israeli local authorities. The system includes OCR capabilities for extracting data from Hebrew PDF protocols.

**Current Scope**: Yehud-Monosson municipality (עיריית יהוד-מונוסון)

**Future Vision**: The system is designed to scale and support all local authorities in Israel, including:
- עיריות (Municipalities)
- מועצות מקומיות (Local councils)
- מועצות אזוריות (Regional councils)
- ועדות מקומיות (Local committees within regional councils)

## Quick Reference

```bash
# Run web app
python ocr_web_app.py  # http://localhost:5000

# Run tests
pytest tests/ -v
pytest tests/ --cov=. --cov-report=html

# Initialize database
python database.py

# Import data from Excel
python import_data.py

# Docker
docker-compose up --build

# Database migrations
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Tech Stack

- **Backend**: Flask 3.0+, SQLAlchemy 2.0+, SQLite
- **OCR**: Tesseract 5.3.3+ (Hebrew), pdfplumber, pdf2image
- **LLM**: Ollama with Gemma3:1b (optional, for fallback extraction)
- **Testing**: pytest, pytest-cov
- **Deployment**: Docker, docker-compose
- **Migrations**: Alembic
- **Configuration**: Centralized config.py with environment variables

## Project Structure

```
pySvivy/
├── config.py              # Centralized configuration (environment variables)
├── models.py              # 12 SQLAlchemy models (core schema)
├── database.py            # DB connection & session management
├── import_data.py         # Excel → DB importer
├── ocr_protocol.py        # Main OCR engine (Hebrew support)
├── ocr_web_app.py         # Flask web app for OCR validation
├── ocr_validation_module.py  # Interactive Jupyter validation
├── llm_helper.py          # Ollama LLM integration
├── db_action_agent.py     # Extract DB actions from discussions
├── ocr_learning_agent.py  # Self-improving OCR via corrections
├── svivyNew.db            # SQLite database (1.6 MB)
│
├── ocr/                   # Modular OCR package
│   ├── __init__.py        # Package exports
│   ├── text_utils.py      # Text reversal, number fixing
│   ├── date_extractor.py  # Date extraction
│   ├── budget_extractor.py # Budget & funding sources
│   ├── vote_extractor.py  # Vote extraction
│   └── pdf_processor.py   # PDF to text conversion
│
├── tests/                 # pytest test suite
│   ├── conftest.py        # Test fixtures
│   ├── test_ocr_functions.py
│   ├── test_budget_extraction.py
│   └── test_database.py
│
├── migrations/            # Alembic database migrations
│   ├── env.py
│   ├── script.py.mako
│   └── versions/          # Migration scripts
│
├── templates/             # HTML templates
├── static/                # CSS, JS, assets
│
├── agents/                # 13 autonomous agents
│   ├── base_agent.py      # Base agent class
│   ├── agent_manager.py   # Central coordination
│   └── *.py               # Specialized agents
│
├── Dockerfile             # Docker image definition
├── docker-compose.yml     # Docker Compose for deployment
├── alembic.ini            # Alembic configuration
│
├── protocols_pdf/         # Input PDF protocols
│   └── worked_on/         # Processed PDFs
├── ocr_results/           # OCR extraction results
├── uploads/               # Uploaded files
├── yehudCsv/              # Source Excel files
└── tessdata/              # Tesseract language data
```

## Database Schema

12 tables with hierarchical relationships:

| Table | Purpose |
|-------|---------|
| terms | קדנציות - Municipal election periods |
| persons | חברי מועצה - Council members & staff |
| roles | תפקידים - Job titles (hierarchical) |
| factions | סיעות - Political parties (hierarchical) |
| boards | ועדות - Committees |
| meetings | ישיבות - Protocol sessions |
| discussions | סעיפים - Agenda items |
| votes | הצבעות - Individual voting records |
| attendances | נוכחות - Meeting presence |
| categories | קטגוריות - Discussion topics (hierarchical) |
| discussion_types | סוגי דיון - Discussion classification (hierarchical) |
| budget_sources | מקורות מימון - Budget funding sources |

**Key Relationships:**
- Person ↔ Board (M2M with dates)
- Person ↔ Term (M2M)
- Discussion ↔ Category (M2M)
- Discussion ↔ DiscussionType (M2M)
- Hierarchical: roles, factions, categories, discussion_types (self-referential via parent_id)

## Key Patterns

### Database Sessions
```python
from database import session_scope

with session_scope() as session:
    persons = session.query(Person).all()
    # Auto-commit on success, rollback on exception
```

### Configuration
```python
from config import config

# Access settings
db_path = config.DATABASE_PATH
tesseract_path = config.TESSERACT_PATH
ollama_host = config.OLLAMA_HOST

# Environment variables override defaults
# SVIVY_DEBUG, SVIVY_DB_NAME, TESSERACT_PATH, OLLAMA_HOST, etc.
```

### OCR Validation Workflow
```python
from ocr_validation_module import ValidationSession

session = ValidationSession()
session.select_pdf()          # Select PDF file
session.run_ocr()             # Run OCR extraction
session.search_meetings()     # Find matching meeting
session.load_meeting(82)      # Load meeting from DB
session.apply_changes()       # Save to database
```

### Web-based OCR Validation (5-step workflow)
```
Step 1: פרטי ישיבה - Meeting details (date, type, number)
Step 2: נוכחות - Attendance matching (OCR vs DB)
Step 3: סגל - Staff validation (new attendees)
Step 4: דיונים - Discussion comparison and matching
Step 5: סיום - Atomic save (all-or-nothing commit)
```

### Session Management (Multi-tab Support)
```python
# Each browser tab gets a unique session ID (sid)
sid = request.args.get('sid') or str(uuid.uuid4())

# Session data stored in memory (session_store dict)
session_data = {
    'extracted': {...},           # OCR results
    'meeting_id': int,            # Matched meeting
    'pending_changes': {...},     # Atomic save buffer
    'validation_complete': False  # Finalization status
}
```

### Atomic Saves (Pending Changes)
```python
# Changes are buffered in session until finalization
pending_changes = {
    'meeting': {'meeting_no': str, 'meeting_date': date},
    'attendances': {person_id: {'is_present': bool}},
    'staff': [{'name': str, 'role': str}],
    'discussions': {disc_id: {'fields': {...}}},
    'new_discussions': [{'issue_no': str, 'title': str}]
}

# Finalize: atomic commit or rollback
POST /api/finalize_validation
POST /api/discard_validation
```

### LLM Helper Usage
```python
from llm_helper import extract_decision_with_llm, classify_discussion

decision = extract_decision_with_llm(discussion_text)
category = classify_discussion(title, content)
```

### OCR Text Utilities (Modular)
```python
from ocr.text_utils import fix_reversed_numbers, reverse_hebrew_text
from ocr.budget_extractor import extract_funding_sources
from ocr.date_extractor import extract_meeting_date

# Fix reversed Hebrew numbers from OCR
fixed = fix_reversed_numbers("000,052")  # → "250,000"

# Extract funding sources
sources = extract_funding_sources(text)
# → [{'name': 'משרד החינוך', 'amount': 300000}, ...]
```

### Smart Name Matching (with Reversal Detection)
```python
from ocr_web_app import names_match

# Checks both normal and reversed versions (Hebrew OCR issue)
matched, was_reversed, matched_name = names_match(
    "ןהכ לחר",      # OCR extracted (reversed)
    "רחל כהן",       # From database
    return_details=True
)
# → (True, True, "רחל כהן")

# Strict matching rules:
# - Two-word names require BOTH words to match
# - Single word must be first name or unique identifier
# - Prevents false positives like "חיים מימון" ↔ "הדר מימון"
```

## Important Conventions

### Language
- **Hebrew** for municipal entities: מועצה, ישיבה, סעיף, החלטה, וכו'
- **English** for technical components
- **Bilingual comments** throughout codebase

### Decision Status Constants
```python
# In Discussion model
DECISION_APPROVED = "אושר"
DECISION_REJECTED = "לא אושר"
DECISION_REMOVED = "ירד מסדר היום"
DECISION_INFO = "לידיעה"
```

### Vote Types
```python
# In Vote model
VOTE_YES = "בעד"
VOTE_NO = "נגד"
VOTE_ABSTAIN = "נמנע"
VOTE_MISSING = "חסר"
```

### Date Formats
- Israeli format: DD/MM/YYYY
- US format also supported: MM/DD/YYYY
- Parse with: `parse_israeli_date()` in import_data.py

## External Dependencies

### Tesseract OCR (Required for OCR)
```bash
# Windows installation path
C:\Program Files\Tesseract-OCR\tesseract.exe

# Environment variable
TESSDATA_PREFIX=<project_root>/tessdata
```

### Ollama (Optional)
```bash
# Local LLM endpoint
http://localhost:11434

# Pull model
ollama pull gemma3:1b
```

## API Endpoints

### Statistics & Data
| Endpoint | Description |
|----------|-------------|
| GET /api/stats | General statistics |
| GET /api/periods | Available terms and years |
| GET /api/current-term | Active term info |
| GET /api/persons | Council member list |
| GET /api/person/<id> | Person details |
| GET /api/boards | Committee list |
| GET /api/discussions | Discussion items |
| GET /api/meetings | Protocol sessions |

### OCR Validation (Web App)
| Endpoint | Description |
|----------|-------------|
| GET /step/1?sid=xxx | Meeting details validation |
| GET /step/2?sid=xxx | Attendance matching |
| GET /step/3?sid=xxx | Staff validation |
| GET /step/4a?sid=xxx | Discussion list comparison |
| GET /step/4b/<id>?sid=xxx | Individual discussion details |
| GET /step/4c?sid=xxx | Unmatched discussions |
| GET /step/5?sid=xxx | Finalization summary |
| POST /api/update_meeting | Save meeting changes (to session) |
| POST /api/update_attendance | Save attendance changes (to session) |
| POST /api/save_staff | Save new staff (to session) |
| POST /api/save_comparison | Save discussion edits (to session) |
| POST /api/finalize_validation | Atomic commit all changes |
| POST /api/discard_validation | Discard all pending changes |
| GET /api/pending_count?sid=xxx | Count of uncommitted changes |
| GET /api/move_to_processed?sid=xxx | Move PDF to processed folder |

## Agent System

13 autonomous agents in `agents/` directory:

- **StateContextAgent** - Session state management
- **InputProcessingAgent** - File validation & PDF processing
- **QAAgent** - Testing & code analysis
- **SchemaEvolutionAgent** - DB migrations
- **ArchitectureAgent** - ADR management
- **RegressionGuardAgent** - Regression detection
- **IntegrationOrchestratorAgent** - Cross-layer coordination
- **ExperimentTrackerAgent** - Experiment management
- **ProjectManagerAgent** - Task management
- **SecurityAgent** - OWASP Top 10 & compliance
- **IntegrationGuardianAgent** - Impact analysis
- **OCRLearningAgent** - Learns from corrections
- **DBActionAgent** - Extracts DB operations

## Common Tasks

### Add New Council Member
```python
from models import Person, Role
from database import get_session

with get_session() as session:
    person = Person(
        full_name="ישראל ישראלי",
        role_id=role.id,
        faction_id=faction.id,
        gender="זכר"
    )
    session.add(person)
```

### Query Discussions by Meeting
```python
from models import Discussion, Meeting
from database import get_session

with get_session() as session:
    discussions = session.query(Discussion)\
        .filter(Discussion.meeting_id == meeting_id)\
        .order_by(Discussion.item_number)\
        .all()
```

### Run OCR on Protocol
```python
from ocr_protocol import extract_protocol_data

result = extract_protocol_data("protocols_pdf/protocol_82.pdf")
# Returns: meeting_date, attendees, discussions, votes
```

## Data Statistics

| Entity | Count |
|--------|-------|
| Council members & staff | 31 |
| Committees | 21 |
| Meetings | 136 |
| Discussions | 790 |
| Votes | 11,499 |
| Terms | 3 |

## File Locations

| Purpose | Location |
|---------|----------|
| PDF protocols | protocols_pdf/ |
| OCR results | ocr_results/ |
| Source Excel | yehudCsv/ |
| Database | svivyNew.db |
| Tesseract data | tessdata/ |
| Logs | logs/ |
| Reports | reports/ |
| Uploads | uploads/ |
| Backups | backups/ |

## Error Handling Pattern

The system uses graceful degradation:
1. **Regex extraction** - First attempt
2. **LLM fallback** - When regex fails
3. **Manual input** - User correction via validation UI

All corrections are logged by `ocr_learning_agent.py` for continuous improvement.

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html

# Run specific test file
pytest tests/test_ocr_functions.py -v
```

Test files:
- `tests/test_ocr_functions.py` - OCR text utilities (22 tests)
- `tests/test_budget_extraction.py` - Budget extraction (17 tests)
- `tests/test_database.py` - Database models (8 tests)

## Docker Deployment

```bash
# Build and run with docker-compose (includes Ollama)
docker-compose up --build

# Or build standalone
docker build -t svivy-ocr .
docker run -p 5000:5000 -v ./svivyNew.db:/app/svivyNew.db svivy-ocr
```

## Database Migrations (Alembic)

```bash
# Create new migration
alembic revision --autogenerate -m "add column"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1

# Show history
alembic history
```

## Recent Updates (January 2026)

### v2.1 - OCR Validation Web App Improvements
- **Atomic Saves**: Changes buffered in session until explicit finalization
- **Multi-tab Support**: Each browser tab gets unique session ID (sid)
- **Smart Name Matching**: Auto-detects reversed Hebrew text from OCR
- **Stricter Matching**: Prevents false positives on shared surnames
- **UI Improvements**: Reverse buttons for names/roles, visual indicators for reversed matches
- **5-Step Workflow**: Meeting → Attendance → Staff → Discussions → Finalize

### Key Files Changed
- `ocr_web_app.py` - Session management, atomic saves, improved name matching
- `templates/step2_attendance.html` - Reversed match indicators
- `templates/step3_staff.html` - Manual text reversal buttons
- `templates/step5_finalize.html` - Summary and commit page
- `templates/base.html` - Pending changes indicator in navbar

---

**Municipality**: Yehud-Monosson (יהוד-מונוסון)
**Version**: 2.1
**Last Updated**: January 2026
