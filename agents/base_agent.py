"""
Base Agent - מחלקת בסיס לכל הסוכנים

מספקת ממשק אחיד וכלים משותפים לכל הסוכנים במערכת.
"""

import json
import os
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

# הגדרת תיקיית הפרויקט
PROJECT_ROOT = Path(__file__).parent.parent
DOCS_DIR = PROJECT_ROOT / "docs"
LOGS_DIR = PROJECT_ROOT / "logs"
REPORTS_DIR = PROJECT_ROOT / "reports"

# יצירת תיקיות אם לא קיימות
for directory in [DOCS_DIR, LOGS_DIR, REPORTS_DIR]:
    directory.mkdir(exist_ok=True)


class BaseAgent(ABC):
    """מחלקת בסיס לכל הסוכנים"""

    def __init__(self, name: str, config: Optional[Dict] = None):
        """
        אתחול הסוכן

        Args:
            name: שם הסוכן
            config: הגדרות אופציונליות
        """
        self.name = name
        self.config = config or {}
        self.created_at = datetime.now()
        self.logger = self._setup_logger()
        self.state: Dict[str, Any] = {}
        self._load_state()

    def _setup_logger(self) -> logging.Logger:
        """הגדרת מערכת לוגים"""
        logger = logging.getLogger(f"agent.{self.name}")
        logger.setLevel(logging.DEBUG)

        # יצירת handler לקובץ
        log_file = LOGS_DIR / f"{self.name}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)

        # פורמט הלוג
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        return logger

    def _get_state_file(self) -> Path:
        """נתיב קובץ מצב הסוכן"""
        return DOCS_DIR / f"{self.name}_state.json"

    def _load_state(self):
        """טעינת מצב הסוכן"""
        state_file = self._get_state_file()
        if state_file.exists():
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    self.state = json.load(f)
                self.logger.info(f"State loaded from {state_file}")
            except json.JSONDecodeError:
                self.logger.warning(f"Could not parse state file: {state_file}")
                self.state = {}

    def save_state(self):
        """שמירת מצב הסוכן"""
        state_file = self._get_state_file()
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2, default=str)
        self.logger.debug(f"State saved to {state_file}")

    def log(self, message: str, level: str = "info"):
        """כתיבה ללוג"""
        log_func = getattr(self.logger, level, self.logger.info)
        log_func(message)

    def log_action(self, action: str, details: Optional[Dict] = None):
        """תיעוד פעולה"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "details": details or {}
        }

        if "action_log" not in self.state:
            self.state["action_log"] = []

        self.state["action_log"].append(log_entry)
        self.logger.info(f"Action: {action} - {details}")
        self.save_state()

    def get_action_history(self, limit: int = 50) -> List[Dict]:
        """קבלת היסטוריית פעולות"""
        history = self.state.get("action_log", [])
        return history[-limit:]

    @abstractmethod
    def run(self, *args, **kwargs) -> Dict[str, Any]:
        """
        הפעלת הסוכן - כל סוכן מממש את זה בצורה שונה

        Returns:
            תוצאות הפעולה
        """
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """
        קבלת סטטוס הסוכן

        Returns:
            מידע על מצב הסוכן
        """
        pass

    def to_dict(self) -> Dict[str, Any]:
        """המרה למילון"""
        return {
            "name": self.name,
            "type": self.__class__.__name__,
            "created_at": self.created_at.isoformat(),
            "config": self.config,
            "state_size": len(self.state)
        }

    def reset(self):
        """איפוס מצב הסוכן"""
        self.state = {}
        self.save_state()
        self.logger.info("Agent state reset")

    def __repr__(self):
        return f"<{self.__class__.__name__}(name='{self.name}')>"


class AgentMessage:
    """הודעה בין סוכנים"""

    def __init__(
        self,
        sender: str,
        receiver: str,
        message_type: str,
        content: Any,
        priority: int = 0
    ):
        self.id = datetime.now().strftime("%Y%m%d%H%M%S%f")
        self.sender = sender
        self.receiver = receiver
        self.message_type = message_type
        self.content = content
        self.priority = priority
        self.timestamp = datetime.now()
        self.read = False

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "sender": self.sender,
            "receiver": self.receiver,
            "type": self.message_type,
            "content": self.content,
            "priority": self.priority,
            "timestamp": self.timestamp.isoformat(),
            "read": self.read
        }


class AgentEvent:
    """אירוע במערכת הסוכנים"""

    def __init__(
        self,
        event_type: str,
        source: str,
        data: Dict[str, Any]
    ):
        self.id = datetime.now().strftime("%Y%m%d%H%M%S%f")
        self.event_type = event_type
        self.source = source
        self.data = data
        self.timestamp = datetime.now()

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "type": self.event_type,
            "source": self.source,
            "data": self.data,
            "timestamp": self.timestamp.isoformat()
        }
