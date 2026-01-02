"""
Project Manager Agent - סוכן ניהול פרויקט (גרסה קלה)

אחראי על:
- עזרה בתעדוף משימות
- פירוק עבודה מורכבת
- שמירה על פוקוס
- תיעוד סטטוס
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass, asdict, field
from enum import Enum

from .base_agent import BaseAgent, DOCS_DIR


class TaskStatus(Enum):
    """סטטוס משימה"""
    BACKLOG = "backlog"  # רשימה
    CURRENT = "current"  # עכשיו
    BLOCKED = "blocked"  # ממתין
    DONE = "done"        # סיים
    DROPPED = "dropped"  # נזנח


class TaskPriority(Enum):
    """עדיפות משימה"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


@dataclass
class Task:
    """משימה"""
    id: str
    title: str
    description: str
    status: str
    priority: str
    parent_id: Optional[str] = None  # לתתי-משימות
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None
    blocked_reason: Optional[str] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class Goal:
    """יעד גדול"""
    id: str
    title: str
    description: str
    features: List[str]  # מזהי features
    created_at: str
    completed_at: Optional[str] = None


class ProjectManagerAgent(BaseAgent):
    """סוכן ניהול פרויקט"""

    def __init__(self, config: Optional[Dict] = None):
        super().__init__("project_manager", config)
        self._init_directories()
        self._load_data()

    def _init_directories(self):
        """יצירת מבנה תיקיות"""
        self.pm_dir = DOCS_DIR / "project"
        self.pm_dir.mkdir(parents=True, exist_ok=True)

    def _load_data(self):
        """טעינת נתונים"""
        data_file = self.pm_dir / "tasks.json"
        if data_file.exists():
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.tasks = {t['id']: Task(**t) for t in data.get('tasks', [])}
                self.goals = {g['id']: Goal(**g) for g in data.get('goals', [])}
        else:
            self.tasks = {}
            self.goals = {}

    def _save_data(self):
        """שמירת נתונים"""
        data_file = self.pm_dir / "tasks.json"
        data = {
            "tasks": [asdict(t) for t in self.tasks.values()],
            "goals": [asdict(g) for g in self.goals.values()],
            "updated_at": datetime.now().isoformat()
        }
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ======== ניהול משימות ========

    def add_task(
        self,
        title: str,
        description: str = "",
        priority: str = "medium",
        parent_id: str = None,
        tags: List[str] = None
    ) -> Task:
        """
        הוספת משימה

        Args:
            title: כותרת המשימה
            description: תיאור
            priority: עדיפות (low/medium/high/urgent)
            parent_id: מזהה משימת הורה
            tags: תגיות
        """
        task_id = f"task_{len(self.tasks) + 1:04d}"

        task = Task(
            id=task_id,
            title=title,
            description=description,
            status=TaskStatus.BACKLOG.value,
            priority=priority,
            parent_id=parent_id,
            tags=tags or []
        )

        self.tasks[task_id] = task
        self._save_data()

        self.log_action("add_task", {"id": task_id, "title": title})
        return task

    def update_task_status(
        self,
        task_id: str,
        status: str,
        blocked_reason: str = None
    ) -> Dict:
        """
        עדכון סטטוס משימה

        Args:
            task_id: מזהה המשימה
            status: סטטוס חדש
            blocked_reason: סיבת חסימה (אם blocked)
        """
        task = self.tasks.get(task_id)
        if not task:
            return {"error": f"Task not found: {task_id}"}

        task.status = status
        if status == TaskStatus.BLOCKED.value:
            task.blocked_reason = blocked_reason
        elif status == TaskStatus.DONE.value:
            task.completed_at = datetime.now().isoformat()

        self._save_data()
        self.log_action("update_task_status", {"id": task_id, "status": status})
        return {"success": True, "task": asdict(task)}

    def complete_task(self, task_id: str) -> Dict:
        """סימון משימה כהושלמה"""
        return self.update_task_status(task_id, TaskStatus.DONE.value)

    def start_task(self, task_id: str) -> Dict:
        """התחלת עבודה על משימה"""
        return self.update_task_status(task_id, TaskStatus.CURRENT.value)

    def block_task(self, task_id: str, reason: str) -> Dict:
        """סימון משימה כחסומה"""
        return self.update_task_status(task_id, TaskStatus.BLOCKED.value, reason)

    def drop_task(self, task_id: str) -> Dict:
        """נטישת משימה"""
        return self.update_task_status(task_id, TaskStatus.DROPPED.value)

    # ======== תעדוף ========

    def get_prioritized_tasks(self) -> List[Dict]:
        """קבלת משימות ממויינות לפי עדיפות"""
        priority_order = {"urgent": 0, "high": 1, "medium": 2, "low": 3}

        active_tasks = [
            t for t in self.tasks.values()
            if t.status in [TaskStatus.BACKLOG.value, TaskStatus.CURRENT.value]
        ]

        sorted_tasks = sorted(
            active_tasks,
            key=lambda x: priority_order.get(x.priority, 3)
        )

        return [asdict(t) for t in sorted_tasks]

    def prioritize_helper(self, task_ids: List[str] = None) -> Dict:
        """
        עוזר לתעדף - שואל שאלות

        Args:
            task_ids: משימות לתעדוף (ברירת מחדל: כל הפתוחות)
        """
        if task_ids is None:
            tasks = [t for t in self.tasks.values()
                    if t.status == TaskStatus.BACKLOG.value]
        else:
            tasks = [self.tasks[tid] for tid in task_ids if tid in self.tasks]

        if not tasks:
            return {"message": "אין משימות לתעדוף"}

        return {
            "tasks_to_prioritize": [
                {"id": t.id, "title": t.title, "current_priority": t.priority}
                for t in tasks
            ],
            "questions": [
                "מה חוסם דברים אחרים?",
                "מה נותן הכי הרבה ערך?",
                "מה הכי קל/מהיר?",
                "מה הכי מעניין אותי עכשיו?"
            ],
            "tip": "ענה על כל שאלה עבור כל משימה כדי למיין"
        }

    # ======== פירוק עבודה ========

    def breakdown_task(
        self,
        parent_id: str,
        subtasks: List[Dict]
    ) -> List[Task]:
        """
        פירוק משימה לתתי-משימות

        Args:
            parent_id: מזהה משימת ההורה
            subtasks: רשימת תתי-משימות [{title, description}]
        """
        parent = self.tasks.get(parent_id)
        if not parent:
            raise ValueError(f"Parent task not found: {parent_id}")

        created = []
        for sub in subtasks:
            task = self.add_task(
                title=sub.get("title"),
                description=sub.get("description", ""),
                priority=parent.priority,
                parent_id=parent_id,
                tags=parent.tags
            )
            created.append(task)

        self.log_action("breakdown_task", {
            "parent": parent_id,
            "subtasks_count": len(created)
        })

        return created

    def create_feature_breakdown(
        self,
        feature_name: str,
        mvp_description: str,
        steps: List[str],
        nice_to_have: List[str] = None,
        out_of_scope: List[str] = None
    ) -> Dict:
        """
        פירוק פיצ'ר למשימות

        Args:
            feature_name: שם הפיצ'ר
            mvp_description: תיאור הגרסה המינימלית
            steps: צעדים לביצוע
            nice_to_have: דברים שנחמד להוסיף אחר כך
            out_of_scope: דברים שלא עושים עכשיו
        """
        # יצירת משימת הורה
        parent = self.add_task(
            title=f"פיצ'ר: {feature_name}",
            description=f"MVP: {mvp_description}",
            priority="high",
            tags=["feature"]
        )

        # יצירת תתי-משימות
        subtasks = [
            self.add_task(
                title=step,
                parent_id=parent.id,
                tags=["feature", "mvp"]
            )
            for step in steps
        ]

        result = {
            "feature_task": asdict(parent),
            "subtasks": [asdict(t) for t in subtasks],
            "nice_to_have": nice_to_have or [],
            "out_of_scope": out_of_scope or []
        }

        # שמירת תיעוד הפירוק
        self._save_breakdown_doc(feature_name, result)

        return result

    def _save_breakdown_doc(self, name: str, breakdown: Dict):
        """שמירת מסמך פירוק"""
        filename = f"breakdown_{datetime.now().strftime('%Y%m%d')}_{name[:20].replace(' ', '_')}.md"
        filepath = self.pm_dir / filename

        content = f"""# פירוק: {name}

## תיאור MVP
{breakdown['feature_task']['description']}

## צעדים לביצוע
"""
        for i, task in enumerate(breakdown['subtasks'], 1):
            content += f"{i}. [ ] {task['title']}\n"

        if breakdown.get('nice_to_have'):
            content += "\n## Nice to Have\n"
            for item in breakdown['nice_to_have']:
                content += f"- {item}\n"

        if breakdown.get('out_of_scope'):
            content += "\n## Out of Scope\n"
            for item in breakdown['out_of_scope']:
                content += f"- {item}\n"

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

    # ======== מצב יומי ========

    def get_daily_status(self) -> Dict:
        """מפת מצב יומית"""
        current = [t for t in self.tasks.values()
                   if t.status == TaskStatus.CURRENT.value]
        blocked = [t for t in self.tasks.values()
                   if t.status == TaskStatus.BLOCKED.value]

        # משימות שהושלמו היום
        today = datetime.now().date().isoformat()
        done_today = [
            t for t in self.tasks.values()
            if t.status == TaskStatus.DONE.value
            and t.completed_at and t.completed_at.startswith(today)
        ]

        # הבא בתור
        backlog = sorted(
            [t for t in self.tasks.values() if t.status == TaskStatus.BACKLOG.value],
            key=lambda x: {"urgent": 0, "high": 1, "medium": 2, "low": 3}.get(x.priority, 3)
        )

        return {
            "date": today,
            "working_on": [asdict(t) for t in current],
            "blocked": [
                {"task": asdict(t), "reason": t.blocked_reason}
                for t in blocked
            ],
            "done_today": [asdict(t) for t in done_today],
            "next_in_queue": [asdict(t) for t in backlog[:3]]
        }

    def generate_status_md(self) -> str:
        """יצירת מפת מצב כ-markdown"""
        status = self.get_daily_status()

        md = f"""## איפה אני היום - {status['date']}

### עובד עכשיו על:
"""
        for task in status['working_on']:
            md += f"- {task['title']}\n"

        if not status['working_on']:
            md += "_(אין משימות פעילות)_\n"

        md += "\n###  מה סיימתי היום:\n"
        for task in status['done_today']:
            md += f"- {task['title']}\n"

        if status['blocked']:
            md += "\n###  מה תקוע:\n"
            for item in status['blocked']:
                md += f"- {item['task']['title']} - למה: {item['reason']}\n"

        md += "\n###  מה הבא בתור:\n"
        for i, task in enumerate(status['next_in_queue'], 1):
            md += f"{i}. {task['title']}\n"

        return md

    # ======== רשימת משימות ========

    def get_task_list(self, status: str = None) -> str:
        """רשימת משימות מפורמטת"""
        tasks_list = list(self.tasks.values())

        if status:
            tasks_list = [t for t in tasks_list if t.status == status]

        md = f"# משימות - {datetime.now().strftime('%Y-%m-%d')}\n\n"

        # עכשיו
        current = [t for t in tasks_list if t.status == TaskStatus.CURRENT.value]
        if current:
            md += "##  עכשיו\n"
            for t in current:
                md += f"- [ ] {t.title}\n"

        # בקרוב
        backlog = [t for t in tasks_list if t.status == TaskStatus.BACKLOG.value]
        backlog_sorted = sorted(backlog,
            key=lambda x: {"urgent": 0, "high": 1, "medium": 2, "low": 3}.get(x.priority, 3))

        if backlog_sorted:
            md += "\n##  בקרוב\n"
            for t in backlog_sorted[:10]:
                priority_emoji = {"urgent": "", "high": "", "medium": "", "low": ""}.get(t.priority, "")
                md += f"- [ ] {priority_emoji} {t.title}\n"

        # הושלם (השבוע)
        done = [t for t in tasks_list if t.status == TaskStatus.DONE.value]
        recent_done = done[-5:]  # 5 אחרונות

        if recent_done:
            md += "\n##  הושלם לאחרונה\n"
            for t in recent_done:
                md += f"- [x] {t.title}\n"

        return md

    # ======== סטטיסטיקות ========

    def get_statistics(self) -> Dict:
        """סטטיסטיקות משימות"""
        tasks = list(self.tasks.values())

        by_status = {}
        for t in tasks:
            by_status[t.status] = by_status.get(t.status, 0) + 1

        by_priority = {}
        active = [t for t in tasks if t.status not in ['done', 'dropped']]
        for t in active:
            by_priority[t.priority] = by_priority.get(t.priority, 0) + 1

        # קצב השלמה (השבוע)
        week_ago = datetime.now().timestamp() - 7 * 24 * 3600
        completed_this_week = [
            t for t in tasks
            if t.status == 'done' and t.completed_at
            and datetime.fromisoformat(t.completed_at).timestamp() > week_ago
        ]

        return {
            "total_tasks": len(tasks),
            "by_status": by_status,
            "by_priority": by_priority,
            "completed_this_week": len(completed_this_week),
            "active_count": sum(1 for t in tasks if t.status in ['current', 'backlog'])
        }

    # ======== ממשק סוכן ========

    def run(self, command: str, **kwargs) -> Dict[str, Any]:
        """הפעלת פקודה"""
        commands = {
            "add": self.add_task,
            "complete": self.complete_task,
            "start": self.start_task,
            "block": self.block_task,
            "drop": self.drop_task,
            "prioritize": self.get_prioritized_tasks,
            "breakdown": self.breakdown_task,
            "feature_breakdown": self.create_feature_breakdown,
            "status": self.get_daily_status,
            "status_md": self.generate_status_md,
            "list": self.get_task_list,
            "stats": self.get_statistics,
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
        stats = self.get_statistics()
        return {
            "name": self.name,
            "total_tasks": stats["total_tasks"],
            "active_tasks": stats["active_count"],
            "completed_this_week": stats["completed_this_week"]
        }
