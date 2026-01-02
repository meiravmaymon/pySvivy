"""
Integration Guardian Agent - סוכן שומר אינטגרציה

אחראי על בדיקת תאימות לפני שינויים, זיהוי השפעות,
ומניעת breaking changes במערכת.
"""

import os
import re
import ast
import json
from datetime import datetime
from typing import Dict, List, Optional, Any, Set, Tuple
from pathlib import Path
from enum import Enum
from dataclasses import dataclass, field

from .base_agent import BaseAgent, DOCS_DIR, PROJECT_ROOT


class RiskLevel(Enum):
    """רמות סיכון"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ChangeType(Enum):
    """סוגי שינויים"""
    ADD = "add"
    MODIFY = "modify"
    DELETE = "delete"
    RENAME = "rename"


@dataclass
class ProjectTechnology:
    """מידע על טכנולוגיה בפרויקט"""
    name: str
    type: str  # backend, frontend, database, mobile
    config_file: str
    detected: bool = False
    version: Optional[str] = None


@dataclass
class ImpactAnalysis:
    """ניתוח השפעה"""
    direct_files: List[str] = field(default_factory=list)
    indirect_files: List[str] = field(default_factory=list)
    api_endpoints: List[str] = field(default_factory=list)
    db_tables: List[str] = field(default_factory=list)
    ui_components: List[str] = field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    breaking_changes: List[str] = field(default_factory=list)


class IntegrationGuardianAgent(BaseAgent):
    """
    סוכן שומר אינטגרציה

    תחומי אחריות:
    - סריקת פרויקט וזיהוי טכנולוגיות
    - ניתוח השפעות לפני שינויים
    - זיהוי breaking changes
    - וידוא תאימות לאחור
    """

    # קבצי תצורה לזיהוי טכנולוגיות
    TECH_DETECTORS = {
        # Python
        "requirements.txt": ProjectTechnology("Python", "backend", "requirements.txt"),
        "pyproject.toml": ProjectTechnology("Python", "backend", "pyproject.toml"),
        "setup.py": ProjectTechnology("Python", "backend", "setup.py"),

        # JavaScript/Node
        "package.json": ProjectTechnology("Node.js", "backend", "package.json"),

        # Databases
        "prisma/schema.prisma": ProjectTechnology("Prisma", "database", "prisma/schema.prisma"),
        "drizzle.config.ts": ProjectTechnology("Drizzle", "database", "drizzle.config.ts"),
        "alembic.ini": ProjectTechnology("SQLAlchemy/Alembic", "database", "alembic.ini"),

        # Frontend
        "next.config.js": ProjectTechnology("Next.js", "frontend", "next.config.js"),
        "vite.config.ts": ProjectTechnology("Vite", "frontend", "vite.config.ts"),
        "angular.json": ProjectTechnology("Angular", "frontend", "angular.json"),

        # Mobile
        "pubspec.yaml": ProjectTechnology("Flutter", "mobile", "pubspec.yaml"),
        "app.json": ProjectTechnology("React Native", "mobile", "app.json"),
    }

    # דפוסים לזיהוי תלויות
    IMPORT_PATTERNS = {
        "python": r'^(?:from|import)\s+([\w.]+)',
        "javascript": r'(?:import|require)\s*\(?[\'"]([^"\']+)[\'"]',
    }

    def __init__(self, config: Optional[Dict] = None):
        super().__init__("integration_guardian", config)
        self.detected_technologies: List[ProjectTechnology] = []
        self.file_dependencies: Dict[str, Set[str]] = {}
        self.api_contracts: Dict[str, Dict] = {}
        self._init_state()

    def _init_state(self):
        """אתחול מצב הסוכן"""
        if "project_scan" not in self.state:
            self.state["project_scan"] = {}
        if "change_history" not in self.state:
            self.state["change_history"] = []
        if "breaking_changes_log" not in self.state:
            self.state["breaking_changes_log"] = []

    def run(self, action: str = "scan_project", **kwargs) -> Dict[str, Any]:
        """
        הפעלת הסוכן

        Actions:
            scan_project: סריקת הפרויקט וזיהוי טכנולוגיות
            analyze_impact: ניתוח השפעה לפני שינוי
            check_compatibility: בדיקת תאימות לאחור
            validate_change: אימות שינוי
        """
        self.log(f"Running action: {action}")

        if action == "scan_project":
            return self.scan_project(kwargs.get("path", PROJECT_ROOT))
        elif action == "analyze_impact":
            return self.analyze_impact(
                kwargs.get("files", []),
                kwargs.get("change_type", ChangeType.MODIFY)
            )
        elif action == "check_compatibility":
            return self.check_backward_compatibility(
                kwargs.get("old_code"),
                kwargs.get("new_code")
            )
        elif action == "validate_change":
            return self.validate_change(kwargs.get("change_plan", {}))
        elif action == "map_dependencies":
            return self.map_file_dependencies(kwargs.get("file_path"))
        else:
            return {"error": f"Unknown action: {action}"}

    def scan_project(self, path: Path = None) -> Dict[str, Any]:
        """סריקת פרויקט וזיהוי טכנולוגיות"""
        path = Path(path) if path else PROJECT_ROOT
        self.log(f"Scanning project at {path}")

        result = {
            "scanned_at": datetime.now().isoformat(),
            "path": str(path),
            "technologies": {},
            "structure": {},
            "summary": {}
        }

        # זיהוי טכנולוגיות
        for config_file, tech in self.TECH_DETECTORS.items():
            config_path = path / config_file
            if config_path.exists():
                tech.detected = True
                tech.version = self._extract_version(config_path, tech.name)
                self.detected_technologies.append(tech)

                result["technologies"][tech.type] = result["technologies"].get(tech.type, [])
                result["technologies"][tech.type].append({
                    "name": tech.name,
                    "config_file": tech.config_file,
                    "version": tech.version
                })

        # סריקת מבנה תיקיות
        result["structure"] = self._scan_directory_structure(path)

        # סיכום
        result["summary"] = {
            "backend": self._get_backend_summary(),
            "frontend": self._get_frontend_summary(),
            "database": self._get_database_summary(),
            "mobile": self._get_mobile_summary()
        }

        # שמירה למצב
        self.state["project_scan"] = result
        self.save_state()

        self.log_action("scan_project", {"path": str(path), "technologies_found": len(self.detected_technologies)})

        return result

    def _extract_version(self, config_path: Path, tech_name: str) -> Optional[str]:
        """חילוץ גרסה מקובץ תצורה"""
        try:
            content = config_path.read_text(encoding='utf-8')

            if tech_name == "Python" and "requirements.txt" in str(config_path):
                return "Detected"
            elif "package.json" in str(config_path):
                data = json.loads(content)
                return data.get("version", "unknown")
            elif "pubspec.yaml" in str(config_path):
                for line in content.split('\n'):
                    if line.startswith('version:'):
                        return line.split(':')[1].strip()

        except Exception as e:
            self.log(f"Could not extract version from {config_path}: {e}", "warning")

        return None

    def _scan_directory_structure(self, path: Path) -> Dict[str, List[str]]:
        """סריקת מבנה תיקיות"""
        structure = {
            "src": [],
            "components": [],
            "api": [],
            "lib": [],
            "db": [],
            "tests": []
        }

        for item in path.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                if item.name in ['src', 'app']:
                    structure["src"] = [str(f.relative_to(path)) for f in item.rglob("*") if f.is_file()][:20]
                elif item.name == 'components':
                    structure["components"] = [str(f.relative_to(path)) for f in item.rglob("*") if f.is_file()][:20]
                elif item.name in ['api', 'routes', 'endpoints']:
                    structure["api"] = [str(f.relative_to(path)) for f in item.rglob("*") if f.is_file()][:20]
                elif item.name in ['lib', 'utils', 'helpers']:
                    structure["lib"] = [str(f.relative_to(path)) for f in item.rglob("*") if f.is_file()][:20]
                elif item.name in ['prisma', 'db', 'database', 'models']:
                    structure["db"] = [str(f.relative_to(path)) for f in item.rglob("*") if f.is_file()][:20]
                elif item.name in ['tests', 'test', '__tests__']:
                    structure["tests"] = [str(f.relative_to(path)) for f in item.rglob("*") if f.is_file()][:20]

        return structure

    def _get_backend_summary(self) -> Dict[str, Any]:
        """סיכום backend"""
        backend_tech = [t for t in self.detected_technologies if t.type == "backend"]
        if backend_tech:
            return {
                "framework": backend_tech[0].name,
                "language": "Python" if "Python" in backend_tech[0].name else "JavaScript"
            }
        return {"framework": "Unknown", "language": "Unknown"}

    def _get_frontend_summary(self) -> Dict[str, Any]:
        """סיכום frontend"""
        frontend_tech = [t for t in self.detected_technologies if t.type == "frontend"]
        if frontend_tech:
            return {"framework": frontend_tech[0].name}
        return {"framework": "None detected"}

    def _get_database_summary(self) -> Dict[str, Any]:
        """סיכום database"""
        db_tech = [t for t in self.detected_technologies if t.type == "database"]
        if db_tech:
            return {"orm": db_tech[0].name}
        return {"orm": "None detected"}

    def _get_mobile_summary(self) -> Dict[str, Any]:
        """סיכום mobile"""
        mobile_tech = [t for t in self.detected_technologies if t.type == "mobile"]
        if mobile_tech:
            return {"framework": mobile_tech[0].name}
        return {"framework": "None detected"}

    def analyze_impact(
        self,
        files: List[str],
        change_type: ChangeType = ChangeType.MODIFY
    ) -> Dict[str, Any]:
        """ניתוח השפעה לפני שינוי"""
        impact = ImpactAnalysis()

        for file_path in files:
            # קבצים מושפעים ישירות
            impact.direct_files.append(file_path)

            # מציאת קבצים תלויים
            dependents = self._find_dependents(file_path)
            impact.indirect_files.extend(dependents)

            # בדיקת API endpoints
            if self._is_api_file(file_path):
                endpoints = self._extract_endpoints(file_path)
                impact.api_endpoints.extend(endpoints)

            # בדיקת DB
            if self._is_db_file(file_path):
                tables = self._extract_tables(file_path)
                impact.db_tables.extend(tables)

        # הסרת כפילויות
        impact.indirect_files = list(set(impact.indirect_files) - set(impact.direct_files))

        # חישוב רמת סיכון
        impact.risk_level = self._calculate_risk_level(impact, change_type)

        # זיהוי breaking changes
        impact.breaking_changes = self._identify_breaking_changes(files, change_type)

        result = {
            "direct_files": impact.direct_files,
            "indirect_files": impact.indirect_files,
            "api_endpoints": impact.api_endpoints,
            "db_tables": impact.db_tables,
            "ui_components": impact.ui_components,
            "risk_level": impact.risk_level.value,
            "breaking_changes": impact.breaking_changes,
            "requires_approval": impact.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
        }

        self.log_action("analyze_impact", {
            "files": files,
            "risk_level": impact.risk_level.value
        })

        return result

    def _find_dependents(self, file_path: str) -> List[str]:
        """מציאת קבצים שתלויים בקובץ נתון"""
        dependents = []
        file_path = Path(file_path)

        if not file_path.exists():
            return dependents

        # שם המודול
        module_name = file_path.stem

        # חיפוש קבצים שמייבאים את המודול
        for py_file in PROJECT_ROOT.rglob("*.py"):
            if py_file == file_path:
                continue

            try:
                content = py_file.read_text(encoding='utf-8')
                if re.search(rf'(?:from|import)\s+.*{module_name}', content):
                    dependents.append(str(py_file.relative_to(PROJECT_ROOT)))
            except Exception:
                pass

        return dependents

    def _is_api_file(self, file_path: str) -> bool:
        """בדיקה אם קובץ הוא חלק מ-API"""
        indicators = ['api', 'routes', 'endpoints', 'views', 'handlers']
        return any(ind in file_path.lower() for ind in indicators)

    def _is_db_file(self, file_path: str) -> bool:
        """בדיקה אם קובץ קשור ל-DB"""
        indicators = ['models', 'schema', 'migration', 'database', 'db']
        return any(ind in file_path.lower() for ind in indicators)

    def _extract_endpoints(self, file_path: str) -> List[str]:
        """חילוץ endpoints מקובץ API"""
        endpoints = []
        path = Path(file_path)

        if not path.exists():
            return endpoints

        try:
            content = path.read_text(encoding='utf-8')
            # דפוסי Flask/FastAPI
            patterns = [
                r'@app\.(?:get|post|put|delete|patch)\s*\(["\']([^"\']+)',
                r'@router\.(?:get|post|put|delete|patch)\s*\(["\']([^"\']+)',
                r'@blueprint\.route\s*\(["\']([^"\']+)',
            ]

            for pattern in patterns:
                matches = re.findall(pattern, content)
                endpoints.extend(matches)

        except Exception:
            pass

        return endpoints

    def _extract_tables(self, file_path: str) -> List[str]:
        """חילוץ טבלאות מקובץ DB"""
        tables = []
        path = Path(file_path)

        if not path.exists():
            return tables

        try:
            content = path.read_text(encoding='utf-8')
            # דפוסי SQLAlchemy
            pattern = r'class\s+(\w+)\s*\([^)]*(?:Base|db\.Model)'
            matches = re.findall(pattern, content)
            tables.extend(matches)

        except Exception:
            pass

        return tables

    def _calculate_risk_level(self, impact: ImpactAnalysis, change_type: ChangeType) -> RiskLevel:
        """חישוב רמת סיכון"""
        score = 0

        # מספר קבצים מושפעים
        total_files = len(impact.direct_files) + len(impact.indirect_files)
        if total_files > 10:
            score += 3
        elif total_files > 5:
            score += 2
        elif total_files > 2:
            score += 1

        # API endpoints
        if impact.api_endpoints:
            score += 2

        # DB tables
        if impact.db_tables:
            score += 2

        # סוג השינוי
        if change_type == ChangeType.DELETE:
            score += 3
        elif change_type == ChangeType.RENAME:
            score += 2
        elif change_type == ChangeType.MODIFY:
            score += 1

        # המרה לרמת סיכון
        if score >= 7:
            return RiskLevel.CRITICAL
        elif score >= 5:
            return RiskLevel.HIGH
        elif score >= 3:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW

    def _identify_breaking_changes(self, files: List[str], change_type: ChangeType) -> List[str]:
        """זיהוי breaking changes"""
        breaking = []

        if change_type == ChangeType.DELETE:
            breaking.append("File deletion may break dependent code")

        for file_path in files:
            if self._is_api_file(file_path):
                breaking.append(f"API changes in {file_path} may affect clients")
            if self._is_db_file(file_path):
                breaking.append(f"DB changes in {file_path} require migration")

        return breaking

    def check_backward_compatibility(
        self,
        old_code: Optional[str],
        new_code: Optional[str]
    ) -> Dict[str, Any]:
        """בדיקת תאימות לאחור"""
        if not old_code or not new_code:
            return {"error": "Both old_code and new_code are required"}

        issues = []
        warnings = []

        try:
            old_tree = ast.parse(old_code)
            new_tree = ast.parse(new_code)

            old_functions = self._extract_function_signatures(old_tree)
            new_functions = self._extract_function_signatures(new_tree)

            # בדיקת פונקציות שהוסרו
            for func_name in old_functions:
                if func_name not in new_functions:
                    issues.append(f"Function '{func_name}' was removed - breaking change")

            # בדיקת שינויי חתימה
            for func_name, old_sig in old_functions.items():
                if func_name in new_functions:
                    new_sig = new_functions[func_name]
                    sig_issues = self._compare_signatures(func_name, old_sig, new_sig)
                    issues.extend(sig_issues)

        except SyntaxError as e:
            return {"error": f"Syntax error in code: {e}"}

        return {
            "compatible": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "recommendation": "Proceed with changes" if not issues else "Review breaking changes before proceeding"
        }

    def _extract_function_signatures(self, tree: ast.AST) -> Dict[str, Dict]:
        """חילוץ חתימות פונקציות"""
        signatures = {}

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                args = node.args
                signatures[node.name] = {
                    "args": [arg.arg for arg in args.args],
                    "defaults_count": len(args.defaults),
                    "has_vararg": args.vararg is not None,
                    "has_kwarg": args.kwonlyargs is not None
                }

        return signatures

    def _compare_signatures(self, func_name: str, old_sig: Dict, new_sig: Dict) -> List[str]:
        """השוואת חתימות פונקציות"""
        issues = []

        old_required = len(old_sig["args"]) - old_sig["defaults_count"]
        new_required = len(new_sig["args"]) - new_sig["defaults_count"]

        # פרמטרים חובה חדשים
        if new_required > old_required:
            issues.append(f"Function '{func_name}' now requires more arguments - breaking change")

        # הסרת פרמטרים
        old_args = set(old_sig["args"])
        new_args = set(new_sig["args"])
        removed = old_args - new_args
        if removed:
            issues.append(f"Function '{func_name}' removed parameters: {removed} - breaking change")

        return issues

    def validate_change(self, change_plan: Dict) -> Dict[str, Any]:
        """אימות תכנית שינוי"""
        validation = {
            "valid": True,
            "checks": [],
            "warnings": [],
            "errors": []
        }

        # בדיקת קבצים קיימים
        for file_path in change_plan.get("files", []):
            if not Path(file_path).exists():
                validation["errors"].append(f"File not found: {file_path}")
                validation["valid"] = False

        # בדיקת migration אם יש שינויי DB
        if change_plan.get("db_changes") and not change_plan.get("migration"):
            validation["warnings"].append("DB changes detected but no migration specified")

        # בדיקת עדכון types
        if change_plan.get("api_changes") and not change_plan.get("types_updated"):
            validation["warnings"].append("API changes detected - ensure types are updated")

        self.log_action("validate_change", {
            "valid": validation["valid"],
            "errors_count": len(validation["errors"])
        })

        return validation

    def map_file_dependencies(self, file_path: Optional[str] = None) -> Dict[str, Any]:
        """מיפוי תלויות של קובץ"""
        if not file_path:
            return {"error": "No file path provided"}

        path = Path(file_path)
        if not path.exists():
            return {"error": f"File not found: {file_path}"}

        imports = []
        dependents = self._find_dependents(file_path)

        try:
            content = path.read_text(encoding='utf-8')
            # Python imports
            pattern = r'^(?:from|import)\s+([\w.]+)'
            matches = re.findall(pattern, content, re.MULTILINE)
            imports = list(set(matches))

        except Exception as e:
            return {"error": f"Error reading file: {e}"}

        return {
            "file": file_path,
            "imports": imports,
            "imported_by": dependents,
            "total_dependencies": len(imports),
            "total_dependents": len(dependents)
        }

    def get_status(self) -> Dict[str, Any]:
        """קבלת סטטוס הסוכן"""
        return {
            "name": self.name,
            "status": "active",
            "last_scan": self.state.get("project_scan", {}).get("scanned_at"),
            "technologies_detected": len(self.detected_technologies),
            "changes_logged": len(self.state.get("change_history", [])),
            "breaking_changes_found": len(self.state.get("breaking_changes_log", []))
        }

    def get_project_summary(self) -> Dict[str, Any]:
        """קבלת סיכום הפרויקט"""
        scan = self.state.get("project_scan", {})
        return scan.get("summary", {})

    def generate_change_report(
        self,
        files_changed: List[str],
        files_added: List[str],
        files_deleted: List[str],
        breaking_changes: List[str]
    ) -> str:
        """יצירת דוח שינויים"""
        report = f"""
📝 סיכום שינויים:
══════════════════════════════════════
├── ✅ קבצים שנוספו: {len(files_added)}
│   • {chr(10).join(['   ' + f for f in files_added[:5]])}
├── 📝 קבצים שהשתנו: {len(files_changed)}
│   • {chr(10).join(['   ' + f for f in files_changed[:5]])}
├── 🗑️ קבצים שנמחקו: {len(files_deleted)}
│   • {chr(10).join(['   ' + f for f in files_deleted[:5]])}
├── ⚠️ Breaking changes: {'כן' if breaking_changes else 'לא'}
│   • {chr(10).join(['   ' + b for b in breaking_changes[:5]])}
└── 📌 נדרשות פעולות נוספות:
    • {'עדכון migrations' if files_deleted else 'אין'}
══════════════════════════════════════
"""
        return report
