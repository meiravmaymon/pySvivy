"""
State & Context Agent - סוכן ניהול מצב והקשר

אחראי על:
- תיעוד החלטות ארגוניות
- מעקב אחרי ניסויים וניסיונות
- שמירה על זיכרון ארגוני
- העברת הקשר לסוכנים אחרים
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
from difflib import SequenceMatcher

from .base_agent import BaseAgent, DOCS_DIR


class StateContextAgent(BaseAgent):
    """סוכן ניהול מצב והקשר"""

    def __init__(self, config: Optional[Dict] = None):
        super().__init__("state_context", config)
        self._init_directories()
        self._load_decisions()
        self._load_experiments()
        self._load_status_map()

    def _init_directories(self):
        """יצירת מבנה תיקיות"""
        self.decisions_dir = DOCS_DIR / "decisions"
        self.experiments_dir = DOCS_DIR / "experiments"
        self.status_dir = DOCS_DIR / "status"
        self.context_dir = DOCS_DIR / "context"

        for directory in [self.decisions_dir, self.experiments_dir,
                         self.status_dir, self.context_dir]:
            directory.mkdir(exist_ok=True)

    def _load_decisions(self):
        """טעינת יומן החלטות"""
        decisions_file = self.decisions_dir / "decisions_log.json"
        if decisions_file.exists():
            with open(decisions_file, 'r', encoding='utf-8') as f:
                self.decisions = json.load(f)
        else:
            self.decisions = []

    def _load_experiments(self):
        """טעינת יומן ניסויים"""
        experiments_file = self.experiments_dir / "experiments_log.json"
        if experiments_file.exists():
            with open(experiments_file, 'r', encoding='utf-8') as f:
                self.experiments = json.load(f)
        else:
            self.experiments = []

    def _load_status_map(self):
        """טעינת מפת מצב"""
        status_file = self.status_dir / "current_status.json"
        if status_file.exists():
            with open(status_file, 'r', encoding='utf-8') as f:
                self.status_map = json.load(f)
        else:
            self.status_map = {
                "active_components": {},
                "in_development": {},
                "broken_components": {},
                "external_dependencies": {},
                "last_updated": datetime.now().isoformat()
            }

    def _save_decisions(self):
        """שמירת יומן החלטות"""
        decisions_file = self.decisions_dir / "decisions_log.json"
        with open(decisions_file, 'w', encoding='utf-8') as f:
            json.dump(self.decisions, f, ensure_ascii=False, indent=2)

    def _save_experiments(self):
        """שמירת יומן ניסויים"""
        experiments_file = self.experiments_dir / "experiments_log.json"
        with open(experiments_file, 'w', encoding='utf-8') as f:
            json.dump(self.experiments, f, ensure_ascii=False, indent=2)

    def _save_status_map(self):
        """שמירת מפת מצב"""
        self.status_map["last_updated"] = datetime.now().isoformat()
        status_file = self.status_dir / "current_status.json"
        with open(status_file, 'w', encoding='utf-8') as f:
            json.dump(self.status_map, f, ensure_ascii=False, indent=2)

    # ======== פקודות תיעוד ========

    def log_decision(
        self,
        title: str,
        context: str,
        options: List[Dict[str, str]],
        decision: str,
        reason: str,
        dependencies: Optional[List[str]] = None,
        review_criteria: Optional[str] = None
    ) -> Dict:
        """
        תיעוד החלטה חדשה

        Args:
            title: כותרת ההחלטה
            context: הקשר - מה הבעיה או הצורך
            options: אפשרויות שנשקלו [{name, pros, cons}]
            decision: מה הוחלט
            reason: למה הוחלט כך
            dependencies: רכיבים מושפעים
            review_criteria: מתי להעריך מחדש

        Returns:
            רשומת ההחלטה
        """
        decision_record = {
            "id": len(self.decisions) + 1,
            "date": datetime.now().isoformat(),
            "title": title,
            "context": context,
            "options_considered": options,
            "decision": decision,
            "reason": reason,
            "dependencies": dependencies or [],
            "review_criteria": review_criteria,
            "status": "active"
        }

        self.decisions.append(decision_record)
        self._save_decisions()

        # שמירה גם כקובץ md נפרד
        self._save_decision_md(decision_record)

        self.log_action("log_decision", {"title": title})
        return decision_record

    def _save_decision_md(self, decision: Dict):
        """שמירת החלטה כקובץ markdown"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"{date_str}-{decision['id']:03d}-{decision['title'][:30].replace(' ', '-')}.md"
        filepath = self.decisions_dir / filename

        content = f"""# {decision['title']}

## תאריך
{decision['date'][:10]}

## הקשר
{decision['context']}

## אפשרויות שנשקלו
"""
        for i, opt in enumerate(decision['options_considered'], 1):
            content += f"""
### {i}. {opt.get('name', 'אפשרות')}
- **יתרונות:** {opt.get('pros', '-')}
- **חסרונות:** {opt.get('cons', '-')}
"""

        content += f"""
## ההחלטה
{decision['decision']}

## נימוק
{decision['reason']}
"""

        if decision.get('dependencies'):
            content += f"""
## תלויות
{chr(10).join('- ' + d for d in decision['dependencies'])}
"""

        if decision.get('review_criteria'):
            content += f"""
## קריטריונים להערכה מחדש
{decision['review_criteria']}
"""

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

    def log_experiment(
        self,
        title: str,
        description: str,
        configuration: Dict,
        result: str,  # success, failure, partial
        insights: str,
        related_files: Optional[List[str]] = None
    ) -> Dict:
        """
        תיעוד ניסוי חדש

        Args:
            title: כותרת הניסוי
            description: מה ניסינו
            configuration: פרמטרים וגרסאות
            result: תוצאה (success/failure/partial)
            insights: מה למדנו
            related_files: קבצים רלוונטיים
        """
        experiment_record = {
            "id": len(self.experiments) + 1,
            "date": datetime.now().isoformat(),
            "title": title,
            "description": description,
            "configuration": configuration,
            "result": result,
            "result_emoji": {"success": "", "failure": "", "partial": ""}[result],
            "insights": insights,
            "related_files": related_files or []
        }

        self.experiments.append(experiment_record)
        self._save_experiments()

        self.log_action("log_experiment", {"title": title, "result": result})
        return experiment_record

    def update_status(
        self,
        component: str,
        status: str,  # active, in_development, broken
        notes: Optional[str] = None,
        version: Optional[str] = None
    ):
        """
        עדכון מצב רכיב

        Args:
            component: שם הרכיב
            status: מצב (active/in_development/broken)
            notes: הערות
            version: גרסה
        """
        status_map = {
            "active": "active_components",
            "in_development": "in_development",
            "broken": "broken_components"
        }

        category = status_map.get(status)
        if not category:
            raise ValueError(f"Invalid status: {status}")

        # הסרה מקטגוריות אחרות
        for cat in status_map.values():
            if component in self.status_map.get(cat, {}):
                del self.status_map[cat][component]

        # הוספה לקטגוריה הנכונה
        self.status_map[category][component] = {
            "notes": notes,
            "version": version,
            "updated": datetime.now().isoformat()
        }

        self._save_status_map()
        self.log_action("update_status", {"component": component, "status": status})

    # ======== שאילתות ========

    def get_context(self, topic: str) -> Dict:
        """
        קבלת הקשר מלא על נושא

        Args:
            topic: הנושא לחיפוש

        Returns:
            מידע רלוונטי מכל המקורות
        """
        context = {
            "topic": topic,
            "relevant_decisions": [],
            "relevant_experiments": [],
            "current_status": None,
            "warnings": [],
            "recommendations": []
        }

        # חיפוש בהחלטות
        for decision in self.decisions:
            if self._is_relevant(topic, decision['title'], decision.get('context', '')):
                context["relevant_decisions"].append({
                    "id": decision['id'],
                    "title": decision['title'],
                    "date": decision['date'][:10],
                    "decision": decision['decision']
                })

        # חיפוש בניסויים
        for exp in self.experiments:
            if self._is_relevant(topic, exp['title'], exp.get('description', '')):
                context["relevant_experiments"].append({
                    "id": exp['id'],
                    "title": exp['title'],
                    "date": exp['date'][:10],
                    "result": exp['result'],
                    "insights": exp.get('insights', '')
                })

        # חיפוש במצב נוכחי
        for category in ["active_components", "in_development", "broken_components"]:
            for component, info in self.status_map.get(category, {}).items():
                if topic.lower() in component.lower():
                    context["current_status"] = {
                        "component": component,
                        "category": category,
                        "info": info
                    }

        # הוספת אזהרות
        context["warnings"] = self._get_warnings(topic)

        return context

    def _is_relevant(self, topic: str, *texts: str) -> bool:
        """בדיקה אם נושא רלוונטי לטקסטים"""
        topic_lower = topic.lower()
        for text in texts:
            if text and topic_lower in text.lower():
                return True
            # בדיקת דמיון
            if text and SequenceMatcher(None, topic_lower, text.lower()).ratio() > 0.6:
                return True
        return False

    def _get_warnings(self, topic: str) -> List[str]:
        """קבלת אזהרות רלוונטיות"""
        warnings = []

        # חיפוש ניסויים כושלים
        for exp in self.experiments:
            if exp['result'] == 'failure' and self._is_relevant(topic, exp['title']):
                warnings.append(
                    f" גישה דומה נכשלה בניסוי #{exp['id']} ({exp['date'][:10]}): {exp.get('insights', '')[:100]}"
                )

        # חיפוש רכיבים שבורים
        for component, info in self.status_map.get("broken_components", {}).items():
            if topic.lower() in component.lower():
                warnings.append(f" רכיב '{component}' מסומן כשבור: {info.get('notes', '')}")

        return warnings

    def find_similar(self, description: str, limit: int = 5) -> List[Dict]:
        """
        חיפוש ניסויים/החלטות דומות

        Args:
            description: תיאור מה מחפשים
            limit: מספר תוצאות מקסימלי
        """
        results = []

        # חיפוש בניסויים
        for exp in self.experiments:
            score = SequenceMatcher(
                None,
                description.lower(),
                f"{exp['title']} {exp.get('description', '')}".lower()
            ).ratio()

            if score > 0.3:
                results.append({
                    "type": "experiment",
                    "id": exp['id'],
                    "title": exp['title'],
                    "date": exp['date'][:10],
                    "result": exp['result'],
                    "relevance": score
                })

        # חיפוש בהחלטות
        for dec in self.decisions:
            score = SequenceMatcher(
                None,
                description.lower(),
                f"{dec['title']} {dec.get('context', '')}".lower()
            ).ratio()

            if score > 0.3:
                results.append({
                    "type": "decision",
                    "id": dec['id'],
                    "title": dec['title'],
                    "date": dec['date'][:10],
                    "relevance": score
                })

        # מיון לפי רלוונטיות
        results.sort(key=lambda x: x['relevance'], reverse=True)
        return results[:limit]

    def check_conflicts(self, proposed_change: str) -> List[Dict]:
        """
        בדיקה אם שינוי מוצע מתנגש עם החלטות קיימות

        Args:
            proposed_change: תיאור השינוי המוצע
        """
        conflicts = []

        for decision in self.decisions:
            if decision.get('status') != 'active':
                continue

            # בדיקת חפיפה בתלויות
            for dep in decision.get('dependencies', []):
                if dep.lower() in proposed_change.lower():
                    conflicts.append({
                        "decision_id": decision['id'],
                        "title": decision['title'],
                        "conflict_type": "dependency_overlap",
                        "details": f"השינוי משפיע על '{dep}' שקשור להחלטה זו"
                    })

        return conflicts

    # ======== התראות ========

    def alert_regression(self, description: str, related_experiment: Optional[int] = None):
        """התראה על חזרה לבעיה ישנה"""
        alert = {
            "type": "regression",
            "description": description,
            "related_experiment": related_experiment,
            "timestamp": datetime.now().isoformat()
        }

        if "alerts" not in self.state:
            self.state["alerts"] = []
        self.state["alerts"].append(alert)
        self.save_state()

        self.log("warning", f"REGRESSION ALERT: {description}")

    def alert_conflict(self, description: str):
        """התראה על התנגשות בין רכיבים"""
        alert = {
            "type": "conflict",
            "description": description,
            "timestamp": datetime.now().isoformat()
        }

        if "alerts" not in self.state:
            self.state["alerts"] = []
        self.state["alerts"].append(alert)
        self.save_state()

        self.log("warning", f"CONFLICT ALERT: {description}")

    # ======== ממשק סוכן ========

    def run(self, command: str, **kwargs) -> Dict[str, Any]:
        """
        הפעלת פקודה

        Args:
            command: שם הפקודה
            **kwargs: פרמטרים לפקודה
        """
        commands = {
            "log_decision": self.log_decision,
            "log_experiment": self.log_experiment,
            "update_status": self.update_status,
            "get_context": self.get_context,
            "find_similar": self.find_similar,
            "check_conflicts": self.check_conflicts,
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
            "decisions_count": len(self.decisions),
            "experiments_count": len(self.experiments),
            "active_components": len(self.status_map.get("active_components", {})),
            "broken_components": len(self.status_map.get("broken_components", {})),
            "alerts_count": len(self.state.get("alerts", [])),
            "last_updated": self.status_map.get("last_updated")
        }

    def get_summary_report(self) -> str:
        """יצירת דוח סיכום"""
        report = f"""
# דוח מצב - {datetime.now().strftime('%Y-%m-%d')}

## סיכום
- החלטות מתועדות: {len(self.decisions)}
- ניסויים מתועדים: {len(self.experiments)}

## רכיבים פעילים
"""
        for comp, info in self.status_map.get("active_components", {}).items():
            report += f"- **{comp}** (v{info.get('version', '?')}): {info.get('notes', '')}\n"

        if self.status_map.get("broken_components"):
            report += "\n## רכיבים שבורים \n"
            for comp, info in self.status_map["broken_components"].items():
                report += f"- **{comp}**: {info.get('notes', '')}\n"

        # החלטות אחרונות
        if self.decisions:
            report += "\n## החלטות אחרונות\n"
            for dec in self.decisions[-5:]:
                report += f"- [{dec['date'][:10]}] {dec['title']}\n"

        # ניסויים אחרונים
        if self.experiments:
            report += "\n## ניסויים אחרונים\n"
            for exp in self.experiments[-5:]:
                emoji = exp.get('result_emoji', '')
                report += f"- {emoji} [{exp['date'][:10]}] {exp['title']}\n"

        return report
