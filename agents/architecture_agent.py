"""
Architecture Agent - סוכן ארכיטקטורה

אחראי על:
- שמירה על עקביות ארכיטקטונית
- ניהול Architecture Decision Records (ADRs)
- בדיקת תלויות ועקביות
- ייעוץ ארכיטקטוני
"""

import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass, asdict, field
from enum import Enum

from .base_agent import BaseAgent, DOCS_DIR


class ADRStatus(Enum):
    """סטטוס ADR"""
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    DEPRECATED = "deprecated"
    SUPERSEDED = "superseded"


@dataclass
class ADR:
    """Architecture Decision Record"""
    id: int
    title: str
    status: str
    context: str
    decision: str
    reasoning: str
    alternatives: List[Dict[str, str]]
    consequences: str
    created_at: str
    updated_at: str = None
    superseded_by: int = None


class ArchitectureAgent(BaseAgent):
    """סוכן ארכיטקטורה"""

    def __init__(self, config: Optional[Dict] = None):
        super().__init__("architecture", config)
        self._init_directories()
        self._load_adrs()
        self._load_architecture_doc()

    def _init_directories(self):
        """יצירת מבנה תיקיות"""
        self.arch_dir = DOCS_DIR / "architecture"
        self.adr_dir = self.arch_dir / "adrs"

        for directory in [self.arch_dir, self.adr_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    def _load_adrs(self):
        """טעינת ADRs"""
        adrs_file = self.adr_dir / "adrs.json"
        if adrs_file.exists():
            with open(adrs_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.adrs = [ADR(**adr) for adr in data]
        else:
            self.adrs = []

    def _save_adrs(self):
        """שמירת ADRs"""
        adrs_file = self.adr_dir / "adrs.json"
        with open(adrs_file, 'w', encoding='utf-8') as f:
            json.dump([asdict(adr) for adr in self.adrs], f, ensure_ascii=False, indent=2)

    def _load_architecture_doc(self):
        """טעינת מסמך ארכיטקטורה"""
        arch_file = self.arch_dir / "architecture.json"
        if arch_file.exists():
            with open(arch_file, 'r', encoding='utf-8') as f:
                self.architecture = json.load(f)
        else:
            self.architecture = {
                "version": "1.0",
                "overview": "",
                "components": {},
                "principles": [],
                "dependencies": {},
                "updated_at": datetime.now().isoformat()
            }

    def _save_architecture_doc(self):
        """שמירת מסמך ארכיטקטורה"""
        self.architecture["updated_at"] = datetime.now().isoformat()
        arch_file = self.arch_dir / "architecture.json"
        with open(arch_file, 'w', encoding='utf-8') as f:
            json.dump(self.architecture, f, ensure_ascii=False, indent=2)

    # ======== ניהול ADRs ========

    def create_adr(
        self,
        title: str,
        context: str,
        decision: str,
        reasoning: str,
        alternatives: List[Dict[str, str]],
        consequences: str
    ) -> ADR:
        """
        יצירת ADR חדש

        Args:
            title: כותרת ההחלטה
            context: הקשר - מה הבעיה
            decision: מה הוחלט
            reasoning: למה זה נכון
            alternatives: אלטרנטיבות [{name, pros, cons}]
            consequences: השלכות
        """
        adr_id = len(self.adrs) + 1

        adr = ADR(
            id=adr_id,
            title=title,
            status=ADRStatus.PROPOSED.value,
            context=context,
            decision=decision,
            reasoning=reasoning,
            alternatives=alternatives,
            consequences=consequences,
            created_at=datetime.now().isoformat()
        )

        self.adrs.append(adr)
        self._save_adrs()

        # שמירה כקובץ markdown
        self._save_adr_md(adr)

        self.log_action("create_adr", {"id": adr_id, "title": title})
        return adr

    def _save_adr_md(self, adr: ADR):
        """שמירת ADR כ-markdown"""
        filename = f"ADR-{adr.id:03d}-{adr.title[:30].replace(' ', '-')}.md"
        filepath = self.adr_dir / filename

        content = f"""# ADR-{adr.id:03d}: {adr.title}

## סטטוס
{adr.status.upper()}

## הקשר
{adr.context}

## החלטה
{adr.decision}

## נימוקים
{adr.reasoning}

## אלטרנטיבות שנשקלו
"""
        for i, alt in enumerate(adr.alternatives, 1):
            content += f"""
### {i}. {alt.get('name', 'אפשרות')}
- **יתרונות:** {alt.get('pros', '-')}
- **חסרונות:** {alt.get('cons', '-')}
"""

        content += f"""
## השלכות
{adr.consequences}

## תאריך
{adr.created_at[:10]}
"""

        if adr.superseded_by:
            content += f"\n## הוחלף על ידי\nADR-{adr.superseded_by:03d}\n"

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

    def update_adr_status(self, adr_id: int, new_status: str, superseded_by: int = None) -> Dict:
        """
        עדכון סטטוס ADR

        Args:
            adr_id: מזהה ה-ADR
            new_status: סטטוס חדש
            superseded_by: מזהה ADR שמחליף (אם רלוונטי)
        """
        adr = next((a for a in self.adrs if a.id == adr_id), None)
        if not adr:
            return {"error": f"ADR not found: {adr_id}"}

        adr.status = new_status
        adr.updated_at = datetime.now().isoformat()
        if superseded_by:
            adr.superseded_by = superseded_by

        self._save_adrs()
        self._save_adr_md(adr)

        self.log_action("update_adr_status", {"id": adr_id, "status": new_status})
        return {"success": True, "adr_id": adr_id, "new_status": new_status}

    def list_adrs(self, status: str = None) -> List[Dict]:
        """רשימת ADRs"""
        adrs = self.adrs
        if status:
            adrs = [a for a in adrs if a.status == status]

        return [
            {
                "id": a.id,
                "title": a.title,
                "status": a.status,
                "created_at": a.created_at[:10]
            }
            for a in adrs
        ]

    # ======== ניהול ארכיטקטורה ========

    def register_component(
        self,
        name: str,
        technology: str,
        purpose: str,
        communication: str,
        dependencies: List[str] = None
    ):
        """
        רישום רכיב במסמך הארכיטקטורה

        Args:
            name: שם הרכיב
            technology: טכנולוגיה
            purpose: תפקיד
            communication: צורת תקשורת
            dependencies: תלויות
        """
        self.architecture["components"][name] = {
            "technology": technology,
            "purpose": purpose,
            "communication": communication,
            "dependencies": dependencies or [],
            "registered_at": datetime.now().isoformat()
        }

        self._save_architecture_doc()
        self.log_action("register_component", {"name": name})

    def add_principle(self, principle: str, description: str):
        """הוספת עיקרון מנחה"""
        self.architecture["principles"].append({
            "principle": principle,
            "description": description,
            "added_at": datetime.now().isoformat()
        })
        self._save_architecture_doc()

    def update_dependencies(self, component: str, dependencies: List[str]):
        """עדכון תלויות של רכיב"""
        if component in self.architecture["components"]:
            self.architecture["components"][component]["dependencies"] = dependencies
            self._save_architecture_doc()

    # ======== בדיקות עקביות ========

    def check_consistency(self) -> Dict:
        """בדיקת עקביות ארכיטקטונית"""
        issues = []
        warnings = []

        # בדיקת תלויות מעגליות
        circular = self._find_circular_dependencies()
        if circular:
            issues.append({
                "type": "CIRCULAR_DEPENDENCY",
                "components": circular
            })

        # בדיקת רכיבים לא מחוברים
        orphans = self._find_orphan_components()
        if orphans:
            warnings.append({
                "type": "ORPHAN_COMPONENT",
                "components": orphans
            })

        # בדיקת ADRs לא מעודכנים
        old_adrs = [
            a for a in self.adrs
            if a.status == "accepted" and not a.updated_at
        ]
        if old_adrs:
            warnings.append({
                "type": "STALE_ADRS",
                "count": len(old_adrs)
            })

        return {
            "consistent": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "checked_at": datetime.now().isoformat()
        }

    def _find_circular_dependencies(self) -> List[List[str]]:
        """זיהוי תלויות מעגליות"""
        components = self.architecture.get("components", {})
        circular = []

        def dfs(node, visited, path):
            if node in path:
                cycle_start = path.index(node)
                circular.append(path[cycle_start:] + [node])
                return

            if node in visited:
                return

            visited.add(node)
            path.append(node)

            comp = components.get(node, {})
            for dep in comp.get("dependencies", []):
                dfs(dep, visited, path)

            path.pop()

        for comp_name in components:
            dfs(comp_name, set(), [])

        return circular

    def _find_orphan_components(self) -> List[str]:
        """זיהוי רכיבים לא מחוברים"""
        components = self.architecture.get("components", {})

        # רכיבים שמישהו תלוי בהם
        referenced = set()
        for comp in components.values():
            for dep in comp.get("dependencies", []):
                referenced.add(dep)

        # רכיבים שלא תלויים באף אחד ואף אחד לא תלוי בהם
        orphans = []
        for name, comp in components.items():
            if not comp.get("dependencies") and name not in referenced:
                orphans.append(name)

        return orphans

    def check_adr_compliance(self, file_path: str) -> Dict:
        """
        בדיקת תאימות קוד ל-ADRs

        Args:
            file_path: נתיב לקובץ
        """
        violations = []

        path = Path(file_path)
        if not path.exists():
            return {"error": f"File not found: {file_path}"}

        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            code = f.read()

        # בדיקות לפי ADRs פעילים
        for adr in self.adrs:
            if adr.status != "accepted":
                continue

            # חיפוש הפרות אפשריות
            violation = self._check_code_against_adr(code, adr)
            if violation:
                violations.append({
                    "adr_id": adr.id,
                    "adr_title": adr.title,
                    "violation": violation
                })

        return {
            "file": file_path,
            "violations_count": len(violations),
            "violations": violations,
            "checked_at": datetime.now().isoformat()
        }

    def _check_code_against_adr(self, code: str, adr: ADR) -> Optional[str]:
        """בדיקת קוד מול ADR ספציפי"""
        # זו דוגמה פשוטה - ניתן להרחיב לפי הצורך
        return None

    # ======== ייעוץ ========

    def ask(self, question: str) -> Dict:
        """
        שאלה ארכיטקטונית

        Args:
            question: השאלה
        """
        # חיפוש ADRs רלוונטיים
        relevant_adrs = []
        question_lower = question.lower()

        for adr in self.adrs:
            if adr.status != "accepted":
                continue

            # חיפוש במילות מפתח
            adr_text = f"{adr.title} {adr.context} {adr.decision}".lower()
            if any(word in adr_text for word in question_lower.split()):
                relevant_adrs.append({
                    "id": adr.id,
                    "title": adr.title,
                    "decision": adr.decision[:200]
                })

        # חיפוש ברכיבים
        relevant_components = []
        for name, comp in self.architecture.get("components", {}).items():
            comp_text = f"{name} {comp.get('purpose', '')}".lower()
            if any(word in comp_text for word in question_lower.split()):
                relevant_components.append({
                    "name": name,
                    "technology": comp.get("technology"),
                    "purpose": comp.get("purpose")
                })

        return {
            "question": question,
            "relevant_adrs": relevant_adrs,
            "relevant_components": relevant_components,
            "note": "This is automated analysis. Review with team for final decision."
        }

    # ======== דוחות ========

    def generate_architecture_doc(self) -> str:
        """יצירת מסמך ארכיטקטורה"""
        doc = """# ארכיטקטורת המערכת

## סקירה כללית
"""
        doc += self.architecture.get("overview", "טרם הוגדר.") + "\n\n"

        doc += "## רכיבים\n\n"
        for name, comp in self.architecture.get("components", {}).items():
            doc += f"""### {name}
- **טכנולוגיה:** {comp.get('technology', '-')}
- **תפקיד:** {comp.get('purpose', '-')}
- **תקשורת:** {comp.get('communication', '-')}
- **תלויות:** {', '.join(comp.get('dependencies', [])) or '-'}

"""

        doc += "## עקרונות מנחים\n\n"
        for p in self.architecture.get("principles", []):
            doc += f"1. **{p.get('principle')}** - {p.get('description')}\n"

        doc += "\n## החלטות ארכיטקטוניות (ADRs)\n\n"
        for adr in self.adrs:
            if adr.status == "accepted":
                doc += f"- [ADR-{adr.id:03d}] {adr.title}\n"

        # שמירה
        doc_file = self.arch_dir / "ARCHITECTURE.md"
        with open(doc_file, 'w', encoding='utf-8') as f:
            f.write(doc)

        return doc

    # ======== ממשק סוכן ========

    def run(self, command: str, **kwargs) -> Dict[str, Any]:
        """הפעלת פקודה"""
        commands = {
            "create_adr": self.create_adr,
            "update_adr_status": self.update_adr_status,
            "list_adrs": self.list_adrs,
            "register_component": self.register_component,
            "add_principle": self.add_principle,
            "check_consistency": self.check_consistency,
            "check_compliance": self.check_adr_compliance,
            "ask": self.ask,
            "generate_doc": self.generate_architecture_doc,
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
        return {
            "name": self.name,
            "total_adrs": len(self.adrs),
            "active_adrs": sum(1 for a in self.adrs if a.status == "accepted"),
            "components_count": len(self.architecture.get("components", {})),
            "principles_count": len(self.architecture.get("principles", []))
        }
