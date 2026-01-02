"""
Schema Evolution Agent - סוכן ניהול סכמה ומיגרציות

אחראי על:
- ניהול מיגרציות בסיס נתונים
- בדיקת תאימות אחורה
- תיעוד שינויים
- התראות על שינויים מסוכנים
"""

import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from enum import Enum
from dataclasses import dataclass, asdict

from .base_agent import BaseAgent, DOCS_DIR


class RiskLevel(Enum):
    """רמות סיכון"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ChangeType(Enum):
    """סוגי שינויים"""
    ADD_TABLE = "add_table"
    DROP_TABLE = "drop_table"
    ADD_COLUMN = "add_column"
    DROP_COLUMN = "drop_column"
    MODIFY_COLUMN = "modify_column"
    ADD_INDEX = "add_index"
    DROP_INDEX = "drop_index"
    ADD_CONSTRAINT = "add_constraint"
    DROP_CONSTRAINT = "drop_constraint"


@dataclass
class Migration:
    """מיגרציה"""
    id: str
    description: str
    created_at: str
    risk_level: str
    reversible: bool
    up_sql: str
    down_sql: str
    affected_tables: List[str]
    affected_code: List[str]
    status: str  # pending, applied, failed, rolled_back


class SchemaEvolutionAgent(BaseAgent):
    """סוכן ניהול סכמה"""

    def __init__(self, config: Optional[Dict] = None):
        super().__init__("schema_evolution", config)
        self._init_directories()
        self._load_migrations()
        self._load_schema()

    def _init_directories(self):
        """יצירת מבנה תיקיות"""
        self.schema_dir = DOCS_DIR / "database"
        self.migrations_dir = self.schema_dir / "migrations"
        self.rollbacks_dir = self.schema_dir / "rollbacks"
        self.history_dir = self.schema_dir / "history"

        for directory in [self.schema_dir, self.migrations_dir,
                         self.rollbacks_dir, self.history_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    def _load_migrations(self):
        """טעינת מיגרציות"""
        migrations_file = self.migrations_dir / "migrations.json"
        if migrations_file.exists():
            with open(migrations_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.migrations = [Migration(**m) for m in data]
        else:
            self.migrations = []

    def _save_migrations(self):
        """שמירת מיגרציות"""
        migrations_file = self.migrations_dir / "migrations.json"
        with open(migrations_file, 'w', encoding='utf-8') as f:
            json.dump([asdict(m) for m in self.migrations], f, ensure_ascii=False, indent=2)

    def _load_schema(self):
        """טעינת סכמה נוכחית"""
        schema_file = self.schema_dir / "current_schema.json"
        if schema_file.exists():
            with open(schema_file, 'r', encoding='utf-8') as f:
                self.current_schema = json.load(f)
        else:
            self.current_schema = {"tables": {}, "version": "0.0.0"}

    def _save_schema(self):
        """שמירת סכמה נוכחית"""
        schema_file = self.schema_dir / "current_schema.json"
        self.current_schema["last_updated"] = datetime.now().isoformat()
        with open(schema_file, 'w', encoding='utf-8') as f:
            json.dump(self.current_schema, f, ensure_ascii=False, indent=2)

    # ======== יצירת מיגרציות ========

    def create_migration(
        self,
        description: str,
        up_sql: str,
        down_sql: str,
        affected_tables: Optional[List[str]] = None,
        affected_code: Optional[List[str]] = None
    ) -> Migration:
        """
        יצירת מיגרציה חדשה

        Args:
            description: תיאור השינוי
            up_sql: פקודות SQL להרצה
            down_sql: פקודות rollback
            affected_tables: טבלאות מושפעות
            affected_code: קוד מושפע
        """
        # יצירת מזהה
        date_prefix = datetime.now().strftime("%Y%m%d")
        existing_today = [m for m in self.migrations if m.id.startswith(date_prefix)]
        seq = len(existing_today) + 1
        migration_id = f"{date_prefix}_{seq:03d}"

        # זיהוי רמת סיכון
        risk_level = self._assess_risk(up_sql)

        # בדיקת reversibility
        reversible = bool(down_sql and down_sql.strip())

        migration = Migration(
            id=migration_id,
            description=description,
            created_at=datetime.now().isoformat(),
            risk_level=risk_level.value,
            reversible=reversible,
            up_sql=up_sql,
            down_sql=down_sql,
            affected_tables=affected_tables or self._extract_tables(up_sql),
            affected_code=affected_code or [],
            status="pending"
        )

        self.migrations.append(migration)
        self._save_migrations()

        # שמירה גם כקובץ SQL נפרד
        self._save_migration_files(migration)

        self.log_action("create_migration", {
            "id": migration_id,
            "description": description,
            "risk": risk_level.value
        })

        return migration

    def _assess_risk(self, sql: str) -> RiskLevel:
        """הערכת רמת סיכון של SQL"""
        sql_upper = sql.upper()

        # שינויים קריטיים
        if any(op in sql_upper for op in ["DROP TABLE", "TRUNCATE", "DROP DATABASE"]):
            return RiskLevel.CRITICAL

        # שינויים בסיכון גבוה
        if any(op in sql_upper for op in ["DROP COLUMN", "ALTER COLUMN", "NOT NULL"]):
            return RiskLevel.HIGH

        # שינויים בסיכון בינוני
        if any(op in sql_upper for op in ["ADD CONSTRAINT", "DROP INDEX", "RENAME"]):
            return RiskLevel.MEDIUM

        # שינויים בטוחים
        return RiskLevel.LOW

    def _extract_tables(self, sql: str) -> List[str]:
        """חילוץ שמות טבלאות מ-SQL"""
        tables = set()

        # ALTER TABLE
        matches = re.findall(r'ALTER\s+TABLE\s+(\w+)', sql, re.IGNORECASE)
        tables.update(matches)

        # CREATE TABLE
        matches = re.findall(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)', sql, re.IGNORECASE)
        tables.update(matches)

        # DROP TABLE
        matches = re.findall(r'DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?(\w+)', sql, re.IGNORECASE)
        tables.update(matches)

        return list(tables)

    def _save_migration_files(self, migration: Migration):
        """שמירת קבצי מיגרציה"""
        # קובץ up
        up_file = self.migrations_dir / f"{migration.id}_up.sql"
        with open(up_file, 'w', encoding='utf-8') as f:
            f.write(f"-- Migration: {migration.id}\n")
            f.write(f"-- Description: {migration.description}\n")
            f.write(f"-- Created: {migration.created_at}\n")
            f.write(f"-- Risk Level: {migration.risk_level}\n\n")
            f.write(migration.up_sql)

        # קובץ down
        if migration.down_sql:
            down_file = self.rollbacks_dir / f"{migration.id}_down.sql"
            with open(down_file, 'w', encoding='utf-8') as f:
                f.write(f"-- Rollback for: {migration.id}\n\n")
                f.write(migration.down_sql)

    # ======== בדיקת תאימות ========

    def check_compatibility(self, migration: Migration) -> Dict:
        """
        בדיקת תאימות של מיגרציה

        Args:
            migration: המיגרציה לבדיקה

        Returns:
            דוח תאימות
        """
        issues = []
        warnings = []

        sql_upper = migration.up_sql.upper()

        # בדיקת שימושים בקוד
        for table in migration.affected_tables:
            usages = self._find_table_usages(table)
            if usages:
                if "DROP TABLE" in sql_upper or "DROP COLUMN" in sql_upper:
                    issues.append({
                        "type": "BREAKING_CHANGE",
                        "severity": "high",
                        "message": f"Table '{table}' is used in {len(usages)} places",
                        "locations": usages[:5]  # הצגת 5 ראשונים
                    })

        # בדיקת שינויים breaking
        if re.search(r'DROP\s+COLUMN', sql_upper):
            issues.append({
                "type": "COLUMN_REMOVAL",
                "severity": "high",
                "message": "Dropping columns may break existing code"
            })

        if re.search(r'NOT\s+NULL', sql_upper) and "DEFAULT" not in sql_upper:
            warnings.append({
                "type": "NOT_NULL_WITHOUT_DEFAULT",
                "severity": "medium",
                "message": "Adding NOT NULL constraint without DEFAULT may fail on existing data"
            })

        # בדיקת reversibility
        if not migration.reversible:
            warnings.append({
                "type": "NOT_REVERSIBLE",
                "severity": "medium",
                "message": "Migration has no rollback script"
            })

        return {
            "migration_id": migration.id,
            "safe": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "checked_at": datetime.now().isoformat()
        }

    def _find_table_usages(self, table_name: str) -> List[str]:
        """חיפוש שימושים בטבלה בקוד"""
        usages = []
        project_root = Path(__file__).parent.parent

        for py_file in project_root.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            try:
                with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    if table_name.lower() in content.lower():
                        usages.append(str(py_file.relative_to(project_root)))
            except Exception:
                pass

        return usages

    # ======== הרצת מיגרציות ========

    def apply_migration(self, migration_id: str, session=None, dry_run: bool = True) -> Dict:
        """
        הרצת מיגרציה

        Args:
            migration_id: מזהה המיגרציה
            session: סשן DB
            dry_run: רק הדמיה, ללא שינוי אמיתי
        """
        migration = next((m for m in self.migrations if m.id == migration_id), None)
        if not migration:
            return {"success": False, "error": f"Migration not found: {migration_id}"}

        if migration.status == "applied":
            return {"success": False, "error": "Migration already applied"}

        # בדיקת תאימות
        compatibility = self.check_compatibility(migration)
        if not compatibility["safe"]:
            if not dry_run:
                return {
                    "success": False,
                    "error": "Migration has breaking changes",
                    "issues": compatibility["issues"]
                }

        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "sql": migration.up_sql,
                "compatibility": compatibility
            }

        # הרצה אמיתית
        try:
            if session:
                from sqlalchemy import text
                for statement in migration.up_sql.split(';'):
                    statement = statement.strip()
                    if statement:
                        session.execute(text(statement))
                session.commit()

            migration.status = "applied"
            self._save_migrations()

            # שמירת היסטוריה
            self._save_to_history(migration, "applied")

            self.log_action("apply_migration", {"id": migration_id, "status": "applied"})

            return {"success": True, "migration_id": migration_id}

        except Exception as e:
            if session:
                session.rollback()
            migration.status = "failed"
            self._save_migrations()

            return {"success": False, "error": str(e)}

    def rollback_migration(self, migration_id: str, session=None) -> Dict:
        """
        ביטול מיגרציה

        Args:
            migration_id: מזהה המיגרציה
            session: סשן DB
        """
        migration = next((m for m in self.migrations if m.id == migration_id), None)
        if not migration:
            return {"success": False, "error": f"Migration not found: {migration_id}"}

        if migration.status != "applied":
            return {"success": False, "error": "Migration not applied"}

        if not migration.reversible:
            return {"success": False, "error": "Migration is not reversible"}

        try:
            if session:
                from sqlalchemy import text
                for statement in migration.down_sql.split(';'):
                    statement = statement.strip()
                    if statement:
                        session.execute(text(statement))
                session.commit()

            migration.status = "rolled_back"
            self._save_migrations()

            self._save_to_history(migration, "rolled_back")

            self.log_action("rollback_migration", {"id": migration_id})

            return {"success": True, "migration_id": migration_id}

        except Exception as e:
            if session:
                session.rollback()
            return {"success": False, "error": str(e)}

    def _save_to_history(self, migration: Migration, action: str):
        """שמירת מיגרציה להיסטוריה"""
        history_file = self.history_dir / f"{migration.id}_{action}.json"
        record = {
            "migration": asdict(migration),
            "action": action,
            "timestamp": datetime.now().isoformat()
        }
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

    # ======== דוחות ========

    def get_migration_status(self) -> Dict:
        """סטטוס מיגרציות"""
        return {
            "total": len(self.migrations),
            "pending": sum(1 for m in self.migrations if m.status == "pending"),
            "applied": sum(1 for m in self.migrations if m.status == "applied"),
            "failed": sum(1 for m in self.migrations if m.status == "failed"),
            "by_risk": {
                "low": sum(1 for m in self.migrations if m.risk_level == "low"),
                "medium": sum(1 for m in self.migrations if m.risk_level == "medium"),
                "high": sum(1 for m in self.migrations if m.risk_level == "high"),
                "critical": sum(1 for m in self.migrations if m.risk_level == "critical"),
            },
            "last_migration": self.migrations[-1].id if self.migrations else None
        }

    def get_pending_migrations(self) -> List[Dict]:
        """רשימת מיגרציות ממתינות"""
        return [
            {
                "id": m.id,
                "description": m.description,
                "risk_level": m.risk_level,
                "affected_tables": m.affected_tables,
                "created_at": m.created_at
            }
            for m in self.migrations if m.status == "pending"
        ]

    def generate_migration_log(self) -> str:
        """יצירת יומן מיגרציות"""
        log = """# יומן מיגרציות

| תאריך | ID | תיאור | סטטוס | סיכון |
|-------|-----|--------|--------|-------|
"""
        for m in sorted(self.migrations, key=lambda x: x.created_at, reverse=True):
            status_emoji = {
                "pending": "",
                "applied": "",
                "failed": "",
                "rolled_back": ""
            }.get(m.status, "")

            log += f"| {m.created_at[:10]} | {m.id} | {m.description[:40]} | {status_emoji} {m.status} | {m.risk_level} |\n"

        return log

    # ======== ממשק סוכן ========

    def run(self, command: str, **kwargs) -> Dict[str, Any]:
        """הפעלת פקודה"""
        commands = {
            "create": self.create_migration,
            "check": lambda migration_id: self.check_compatibility(
                next((m for m in self.migrations if m.id == migration_id), None)
            ),
            "apply": self.apply_migration,
            "rollback": self.rollback_migration,
            "status": self.get_migration_status,
            "pending": self.get_pending_migrations,
        }

        if command not in commands:
            return {"error": f"Unknown command: {command}"}

        try:
            result = commands[command](**kwargs)
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_status(self) -> Dict[str, Any]:
        """קבלת סטטוס הסוכן"""
        status = self.get_migration_status()
        return {
            "name": self.name,
            "migrations_total": status["total"],
            "migrations_pending": status["pending"],
            "last_migration": status["last_migration"]
        }
