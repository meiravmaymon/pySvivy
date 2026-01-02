# Svivy Project Agents - מערכת סוכנים אוטונומיים

מערכת של 13 סוכנים אוטונומיים לניהול ופיתוח פרויקט Svivy.

---

## סקירה כללית

```
┌─────────────────────────────────────────────────────────────────┐
│                      AgentManager                                │
│                   (מנהל מרכזי)                                   │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌────────────┐ │
│  │   State     │ │   Input     │ │     QA      │ │  Schema    │ │
│  │  Context    │ │ Processing  │ │   Agent     │ │ Evolution  │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └────────────┘ │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌────────────┐ │
│  │Architecture │ │ Regression  │ │ Integration │ │ Experiment │ │
│  │   Agent     │ │   Guard     │ │Orchestrator │ │  Tracker   │ │
│  └─────────────┘ └─────────────┘ └─────────────┘ └────────────┘ │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                │
│  │  Project    │ │  Security   │ │ Integration │                │
│  │  Manager    │ │   Agent     │ │  Guardian   │                │
│  └─────────────┘ └─────────────┘ └─────────────┘                │
│  ┌─────────────┐ ┌─────────────┐                                │
│  │    OCR      │ │  DB Action  │  ← סוכנים קיימים               │
│  │  Learning   │ │   Agent     │                                │
│  └─────────────┘ └─────────────┘                                │
└─────────────────────────────────────────────────────────────────┘
```

---

## רשימת הסוכנים (13)

### סוכנים חדשים (11)

| # | סוכן | קובץ | תפקיד |
|---|------|------|-------|
| 1 | **StateContextAgent** | `state_context_agent.py` | ניהול מצב והקשר, תיעוד החלטות וניסויים |
| 2 | **InputProcessingAgent** | `input_processing_agent.py` | עיבוד ווולידציה של קלטים (PDF, טקסט) |
| 3 | **QAAgent** | `qa_agent.py` | בקרת איכות, זיהוי באגים, יצירת בדיקות |
| 4 | **SchemaEvolutionAgent** | `schema_evolution_agent.py` | ניהול מיגרציות ושינויי סכמה |
| 5 | **ArchitectureAgent** | `architecture_agent.py` | שמירה על עקביות ארכיטקטונית, ADRs |
| 6 | **RegressionGuardAgent** | `regression_guard_agent.py` | זיהוי רגרסיות ושמירת baselines |
| 7 | **IntegrationOrchestratorAgent** | `integration_orchestrator_agent.py` | תיאום בין שכבות המערכת |
| 8 | **ExperimentTrackerAgent** | `experiment_tracker_agent.py` | מעקב אחרי ניסויים והשוואת גישות |
| 9 | **ProjectManagerAgent** | `project_manager_agent.py` | ניהול משימות ותעדוף (למפתחת יחידה) |
| 10 | **SecurityAgent** | `security_agent.py` | אבטחת מידע, OWASP, רגולציה ישראלית |
| 11 | **IntegrationGuardianAgent** | `integration_guardian_agent.py` | שמירה על תאימות לפני שינויים |

### סוכנים קיימים (משולבים) (2)

| # | סוכן | קובץ | תפקיד |
|---|------|------|-------|
| 12 | **OCRLearningAgent** | `../ocr_learning_agent.py` | למידה מתיקוני OCR לשיפור דיוק |
| 13 | **DBActionAgent** | `../db_action_agent.py` | חילוץ פעולות מדיונים ויצירת פקודות DB |

### ניהול מרכזי

| סוכן | קובץ | תפקיד |
|------|------|-------|
| **AgentManager** | `agent_manager.py` | מנהל מרכזי - אתחול, תיאום, הודעות, workflows |

---

## התקנה ושימוש

### ייבוא בסיסי

```python
from agents import AgentManager

# אתחול כל הסוכנים
manager = AgentManager()
results = manager.initialize_all_agents()
print(f"Initialized: {results}")
```

### הפעלת סוכן ספציפי

```python
# סריקת אבטחה
result = manager.run_agent("security_agent", action="full_scan")

# בדיקת תאימות לפני שינוי
result = manager.run_agent("integration_guardian", action="analyze_impact",
                           files=["models.py"])

# יצירת ADR
result = manager.run_agent("architecture", action="create_adr",
                           title="Database Selection",
                           context="Need to choose database",
                           decision="SQLite for simplicity")
```

### הרצת Workflow

```python
workflow = [
    {"agent": "integration_guardian", "action": "scan_project"},
    {"agent": "security_agent", "action": "code_patterns"},
    {"agent": "qa", "action": "run_tests"}
]
results = manager.run_workflow(workflow)
```

### קבלת סטטוס

```python
# סטטוס כל הסוכנים
status = manager.get_all_status()

# סטטוס סוכן ספציפי
status = manager.get_agent_status("security_agent")

# סיכום כללי
summary = manager.get_summary()
```

### שליחת הודעות בין סוכנים

```python
manager.send_message(
    sender="qa",
    receiver="security_agent",
    message_type="vulnerability_found",
    content={"file": "api.py", "issue": "SQL injection"}
)

# שידור לכל הסוכנים
manager.broadcast(
    sender="schema_evolution",
    message_type="migration_completed",
    content={"version": "20240115_001"}
)
```

---

## פירוט סוכנים

### 1. StateContextAgent - ניהול מצב והקשר

**תפקיד:** שומר על הקשר בין סשנים, מתעד החלטות וניסויים.

**פעולות:**
- `log_decision` - תיעוד החלטה
- `log_experiment` - תיעוד ניסוי
- `update_status` - עדכון סטטוס יומי
- `get_context` - קבלת הקשר נוכחי

---

### 2. InputProcessingAgent - עיבוד קלטים

**תפקיד:** עיבוד וולידציה של קבצי PDF וטקסט.

**פעולות:**
- `process_file` - עיבוד קובץ
- `validate_input` - וולידציה
- `classify_file` - סיווג סוג הקובץ

---

### 3. QAAgent - בקרת איכות

**תפקיד:** יצירת בדיקות, זיהוי באגים, ניתוח קוד.

**פעולות:**
- `run_tests` - הרצת בדיקות
- `analyze_code` - ניתוח קוד
- `create_test` - יצירת בדיקה חדשה
- `get_coverage` - כיסוי בדיקות

---

### 4. SchemaEvolutionAgent - ניהול סכמה

**תפקיד:** ניהול מיגרציות ושינויי סכמת DB.

**פעולות:**
- `create_migration` - יצירת מיגרציה
- `apply_migration` - הרצת מיגרציה
- `rollback` - ביטול מיגרציה
- `check_compatibility` - בדיקת תאימות

---

### 5. ArchitectureAgent - ארכיטקטורה

**תפקיד:** שמירה על עקביות ארכיטקטונית, ניהול ADRs.

**פעולות:**
- `create_adr` - יצירת Architecture Decision Record
- `check_consistency` - בדיקת עקביות
- `list_adrs` - רשימת החלטות

---

### 6. RegressionGuardAgent - שמירה מפני רגרסיות

**תפקיד:** השוואת תוצאות, זיהוי רגרסיות.

**פעולות:**
- `create_baseline` - יצירת baseline
- `compare` - השוואה לbaseline
- `get_regressions` - רשימת רגרסיות

---

### 7. IntegrationOrchestratorAgent - תיאום אינטגרציה

**תפקיד:** תיאום בין שכבות המערכת, ניהול API contracts.

**פעולות:**
- `map_dependencies` - מיפוי תלויות
- `validate_contracts` - בדיקת חוזי API
- `sync_types` - סנכרון טיפוסים

---

### 8. ExperimentTrackerAgent - מעקב ניסויים

**תפקיד:** ניהול ניסויים, השוואת גישות.

**פעולות:**
- `create_experiment` - יצירת ניסוי
- `record_result` - תיעוד תוצאה
- `compare_experiments` - השוואה
- `get_best` - הניסוי הטוב ביותר

---

### 9. ProjectManagerAgent - ניהול משימות

**תפקיד:** תעדוף, פירוק משימות, מעקב התקדמות (למפתחת יחידה).

**פעולות:**
- `add_task` - הוספת משימה
- `prioritize` - תעדוף
- `breakdown` - פירוק משימה
- `get_status` - סטטוס

---

### 10. SecurityAgent - אבטחת מידע

**תפקיד:** סריקות אבטחה, תאימות רגולטורית, OWASP.

**פעולות:**
- `full_scan` - סריקה מלאה
- `scan_file` - סריקת קובץ
- `code_patterns` - זיהוי דפוסים מסוכנים
- `compliance_report` - דוח תאימות
- `daily_report` - דוח יומי

**תקנים:**
- OWASP Top 10 2024
- תקנות הגנת הפרטיות (ישראל)
- הנחיות מערך הסייבר הלאומי

---

### 11. IntegrationGuardianAgent - שמירה על תאימות

**תפקיד:** בדיקת השפעות לפני שינויים, מניעת breaking changes.

**פעולות:**
- `scan_project` - סריקת פרויקט
- `analyze_impact` - ניתוח השפעה
- `check_compatibility` - בדיקת תאימות לאחור
- `validate_change` - אימות שינוי

---

### 12. OCRLearningAgent - למידת OCR

**תפקיד:** למידה מתיקוני משתמש לשיפור דיוק ה-OCR.

**פונקציות:**
- `record_correction()` - שמירת תיקון
- `auto_correct()` - תיקון אוטומטי
- `suggest_correction()` - הצעת תיקון
- `get_accuracy_report()` - דוח דיוק

---

### 13. DBActionAgent - פעולות DB

**תפקיד:** חילוץ פעולות מדיונים ויצירת פקודות SQL.

**פעולות:**
- `analyze_discussion` - ניתוח דיון
- `execute_action` - ביצוע פעולה
- `get_pending_actions` - פעולות ממתינות

---

## מבנה קבצים

```
agents/
├── __init__.py                      # ייבוא מרכזי
├── README.md                        # תיעוד זה
├── base_agent.py                    # מחלקת בסיס
├── agent_manager.py                 # מנהל מרכזי
├── state_context_agent.py           # 1. ניהול מצב
├── input_processing_agent.py        # 2. עיבוד קלטים
├── qa_agent.py                      # 3. בקרת איכות
├── schema_evolution_agent.py        # 4. מיגרציות
├── architecture_agent.py            # 5. ארכיטקטורה
├── regression_guard_agent.py        # 6. רגרסיות
├── integration_orchestrator_agent.py # 7. תיאום
├── experiment_tracker_agent.py      # 8. ניסויים
├── project_manager_agent.py         # 9. ניהול משימות
├── security_agent.py                # 10. אבטחה
└── integration_guardian_agent.py    # 11. תאימות

# סוכנים קיימים (בתיקייה הראשית)
../ocr_learning_agent.py             # 12. למידת OCR
../db_action_agent.py                # 13. פעולות DB
```

---

## תיקיות נוספות

המערכת יוצרת אוטומטית:

```
docs/           # קבצי מצב של סוכנים (_state.json)
logs/           # קבצי לוג לכל סוכן
reports/        # דוחות (אבטחה, תאימות וכו')
```

---

## פיתוח סוכן חדש

```python
from agents.base_agent import BaseAgent

class MyNewAgent(BaseAgent):
    def __init__(self, config=None):
        super().__init__("my_new_agent", config)

    def run(self, action: str = "default", **kwargs):
        if action == "do_something":
            return self._do_something(**kwargs)
        return {"error": f"Unknown action: {action}"}

    def get_status(self):
        return {
            "name": self.name,
            "status": "active"
        }

    def _do_something(self, **kwargs):
        self.log_action("do_something", kwargs)
        return {"success": True}
```

---

## רישיון

חלק מפרויקט Svivy Municipal System.
