"""
Agent Manager - מנהל מרכזי לכל הסוכנים

מספק ממשק אחיד להפעלה, תיאום ותקשורת בין כל הסוכנים במערכת.
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Any, Type
from pathlib import Path
from enum import Enum

from .base_agent import BaseAgent, AgentMessage, AgentEvent, DOCS_DIR, LOGS_DIR


class AgentStatus(Enum):
    """סטטוס סוכן"""
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"
    DISABLED = "disabled"


class AgentManager:
    """
    מנהל הסוכנים המרכזי

    תחומי אחריות:
    - רישום והפעלת סוכנים
    - תיאום בין סוכנים
    - ניהול הודעות ואירועים
    - מעקב אחר סטטוס
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        אתחול מנהל הסוכנים

        Args:
            config: הגדרות אופציונליות
        """
        self.config = config or {}
        self.agents: Dict[str, BaseAgent] = {}
        self.agent_status: Dict[str, AgentStatus] = {}
        self.message_queue: List[AgentMessage] = []
        self.event_log: List[AgentEvent] = []
        self.created_at = datetime.now()

        # טעינת מצב קודם אם קיים
        self._load_state()

    def _get_state_file(self) -> Path:
        """נתיב קובץ מצב"""
        return DOCS_DIR / "agent_manager_state.json"

    def _load_state(self):
        """טעינת מצב קודם"""
        state_file = self._get_state_file()
        if state_file.exists():
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    # שחזור event log
                    self.event_log = [
                        AgentEvent(e["type"], e["source"], e["data"])
                        for e in state.get("event_log", [])[-100:]  # שמירת 100 אחרונים
                    ]
            except Exception:
                pass

    def _save_state(self):
        """שמירת מצב"""
        state_file = self._get_state_file()
        state = {
            "created_at": self.created_at.isoformat(),
            "agents": list(self.agents.keys()),
            "event_log": [e.to_dict() for e in self.event_log[-100:]]
        }
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def register_agent(self, agent: BaseAgent) -> bool:
        """
        רישום סוכן חדש

        Args:
            agent: מופע הסוכן לרישום

        Returns:
            True אם הרישום הצליח
        """
        if agent.name in self.agents:
            self._log_event("agent_registration_failed", agent.name, {
                "reason": "Agent already registered"
            })
            return False

        self.agents[agent.name] = agent
        self.agent_status[agent.name] = AgentStatus.IDLE

        self._log_event("agent_registered", agent.name, {
            "type": agent.__class__.__name__
        })

        return True

    def unregister_agent(self, agent_name: str) -> bool:
        """
        הסרת סוכן

        Args:
            agent_name: שם הסוכן להסרה

        Returns:
            True אם ההסרה הצליחה
        """
        if agent_name not in self.agents:
            return False

        del self.agents[agent_name]
        del self.agent_status[agent_name]

        self._log_event("agent_unregistered", "manager", {
            "agent": agent_name
        })

        return True

    def get_agent(self, agent_name: str) -> Optional[BaseAgent]:
        """
        קבלת סוכן לפי שם

        Args:
            agent_name: שם הסוכן

        Returns:
            הסוכן או None
        """
        return self.agents.get(agent_name)

    def run_agent(self, agent_name: str, *args, **kwargs) -> Dict[str, Any]:
        """
        הפעלת סוכן

        Args:
            agent_name: שם הסוכן להפעלה
            *args, **kwargs: פרמטרים להעברה לסוכן

        Returns:
            תוצאות הפעולה
        """
        if agent_name not in self.agents:
            return {"error": f"Agent not found: {agent_name}"}

        agent = self.agents[agent_name]
        self.agent_status[agent_name] = AgentStatus.RUNNING

        self._log_event("agent_started", agent_name, {
            "args": str(args)[:100],
            "kwargs": str(kwargs)[:100]
        })

        try:
            result = agent.run(*args, **kwargs)
            self.agent_status[agent_name] = AgentStatus.IDLE

            self._log_event("agent_completed", agent_name, {
                "success": True
            })

            return result

        except Exception as e:
            self.agent_status[agent_name] = AgentStatus.ERROR

            self._log_event("agent_error", agent_name, {
                "error": str(e)
            })

            return {"error": str(e)}

    def run_agents_parallel(
        self,
        agent_tasks: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        הפעלת מספר סוכנים (סדרתית - ניתן להרחיב לפרללית)

        Args:
            agent_tasks: רשימת משימות [{agent_name, args, kwargs}, ...]

        Returns:
            תוצאות כל הסוכנים
        """
        results = {}

        for task in agent_tasks:
            agent_name = task.get("agent_name")
            args = task.get("args", [])
            kwargs = task.get("kwargs", {})

            results[agent_name] = self.run_agent(agent_name, *args, **kwargs)

        return results

    def send_message(
        self,
        sender: str,
        receiver: str,
        message_type: str,
        content: Any,
        priority: int = 0
    ) -> bool:
        """
        שליחת הודעה בין סוכנים

        Args:
            sender: שם הסוכן השולח
            receiver: שם הסוכן המקבל
            message_type: סוג ההודעה
            content: תוכן ההודעה
            priority: עדיפות (0 = רגיל)

        Returns:
            True אם ההודעה נשלחה
        """
        if receiver not in self.agents and receiver != "broadcast":
            return False

        message = AgentMessage(sender, receiver, message_type, content, priority)
        self.message_queue.append(message)

        self._log_event("message_sent", sender, {
            "receiver": receiver,
            "type": message_type
        })

        return True

    def get_messages(
        self,
        receiver: str,
        unread_only: bool = True
    ) -> List[AgentMessage]:
        """
        קבלת הודעות לסוכן

        Args:
            receiver: שם הסוכן
            unread_only: רק הודעות שלא נקראו

        Returns:
            רשימת הודעות
        """
        messages = []

        for msg in self.message_queue:
            if msg.receiver == receiver or msg.receiver == "broadcast":
                if not unread_only or not msg.read:
                    messages.append(msg)
                    msg.read = True

        # מיון לפי עדיפות
        messages.sort(key=lambda m: m.priority, reverse=True)

        return messages

    def broadcast(self, sender: str, message_type: str, content: Any):
        """
        שידור הודעה לכל הסוכנים

        Args:
            sender: שם הסוכן השולח
            message_type: סוג ההודעה
            content: תוכן ההודעה
        """
        self.send_message(sender, "broadcast", message_type, content)

    def _log_event(self, event_type: str, source: str, data: Dict[str, Any]):
        """תיעוד אירוע"""
        event = AgentEvent(event_type, source, data)
        self.event_log.append(event)

        # שמירת מצב כל 10 אירועים
        if len(self.event_log) % 10 == 0:
            self._save_state()

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """
        קבלת סטטוס כל הסוכנים

        Returns:
            מילון עם סטטוס כל סוכן
        """
        status = {}

        for name, agent in self.agents.items():
            try:
                agent_status = agent.get_status()
            except Exception as e:
                agent_status = {"error": str(e)}

            status[name] = {
                "status": self.agent_status[name].value,
                "type": agent.__class__.__name__,
                **agent_status
            }

        return status

    def get_agent_status(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """
        קבלת סטטוס סוכן ספציפי

        Args:
            agent_name: שם הסוכן

        Returns:
            סטטוס הסוכן או None
        """
        if agent_name not in self.agents:
            return None

        agent = self.agents[agent_name]

        return {
            "name": agent_name,
            "status": self.agent_status[agent_name].value,
            "type": agent.__class__.__name__,
            **agent.get_status()
        }

    def get_event_log(self, limit: int = 50) -> List[Dict]:
        """
        קבלת יומן אירועים

        Args:
            limit: מספר אירועים מקסימלי

        Returns:
            רשימת אירועים
        """
        return [e.to_dict() for e in self.event_log[-limit:]]

    def get_message_stats(self) -> Dict[str, Any]:
        """
        סטטיסטיקות הודעות

        Returns:
            סטטיסטיקות
        """
        total = len(self.message_queue)
        unread = sum(1 for m in self.message_queue if not m.read)

        by_type = {}
        for msg in self.message_queue:
            by_type[msg.message_type] = by_type.get(msg.message_type, 0) + 1

        return {
            "total": total,
            "unread": unread,
            "by_type": by_type
        }

    def run_workflow(self, workflow: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        הרצת workflow של סוכנים

        Args:
            workflow: רשימת שלבים [{agent, action, params}, ...]

        Returns:
            תוצאות ה-workflow
        """
        results = {
            "started_at": datetime.now().isoformat(),
            "steps": [],
            "success": True
        }

        for i, step in enumerate(workflow):
            agent_name = step.get("agent")
            action = step.get("action")
            params = step.get("params", {})

            step_result = {
                "step": i + 1,
                "agent": agent_name,
                "action": action
            }

            try:
                result = self.run_agent(agent_name, action=action, **params)
                step_result["result"] = result
                step_result["success"] = "error" not in result

                if not step_result["success"]:
                    results["success"] = False
                    if step.get("stop_on_error", True):
                        step_result["stopped"] = True
                        results["steps"].append(step_result)
                        break

            except Exception as e:
                step_result["error"] = str(e)
                step_result["success"] = False
                results["success"] = False
                results["steps"].append(step_result)
                break

            results["steps"].append(step_result)

        results["completed_at"] = datetime.now().isoformat()
        return results

    def initialize_all_agents(self) -> Dict[str, bool]:
        """
        אתחול כל הסוכנים הזמינים

        Returns:
            מילון עם סטטוס אתחול לכל סוכן
        """
        from .state_context_agent import StateContextAgent
        from .input_processing_agent import InputProcessingAgent
        from .qa_agent import QAAgent
        from .schema_evolution_agent import SchemaEvolutionAgent
        from .architecture_agent import ArchitectureAgent
        from .regression_guard_agent import RegressionGuardAgent
        from .integration_orchestrator_agent import IntegrationOrchestratorAgent
        from .experiment_tracker_agent import ExperimentTrackerAgent
        from .project_manager_agent import ProjectManagerAgent
        from .security_agent import SecurityAgent
        from .integration_guardian_agent import IntegrationGuardianAgent

        agents_to_init = [
            StateContextAgent,
            InputProcessingAgent,
            QAAgent,
            SchemaEvolutionAgent,
            ArchitectureAgent,
            RegressionGuardAgent,
            IntegrationOrchestratorAgent,
            ExperimentTrackerAgent,
            ProjectManagerAgent,
            SecurityAgent,
            IntegrationGuardianAgent
        ]

        results = {}

        for AgentClass in agents_to_init:
            try:
                agent = AgentClass()
                success = self.register_agent(agent)
                results[agent.name] = success
            except Exception as e:
                results[AgentClass.__name__] = False
                self._log_event("agent_init_error", "manager", {
                    "agent_class": AgentClass.__name__,
                    "error": str(e)
                })

        self._save_state()
        return results

    def reset_agent(self, agent_name: str) -> bool:
        """
        איפוס סוכן

        Args:
            agent_name: שם הסוכן

        Returns:
            True אם האיפוס הצליח
        """
        if agent_name not in self.agents:
            return False

        agent = self.agents[agent_name]
        agent.reset()
        self.agent_status[agent_name] = AgentStatus.IDLE

        self._log_event("agent_reset", "manager", {
            "agent": agent_name
        })

        return True

    def disable_agent(self, agent_name: str) -> bool:
        """
        השבתת סוכן

        Args:
            agent_name: שם הסוכן

        Returns:
            True אם ההשבתה הצליחה
        """
        if agent_name not in self.agents:
            return False

        self.agent_status[agent_name] = AgentStatus.DISABLED

        self._log_event("agent_disabled", "manager", {
            "agent": agent_name
        })

        return True

    def enable_agent(self, agent_name: str) -> bool:
        """
        הפעלת סוכן מושבת

        Args:
            agent_name: שם הסוכן

        Returns:
            True אם ההפעלה הצליחה
        """
        if agent_name not in self.agents:
            return False

        self.agent_status[agent_name] = AgentStatus.IDLE

        self._log_event("agent_enabled", "manager", {
            "agent": agent_name
        })

        return True

    def get_summary(self) -> Dict[str, Any]:
        """
        סיכום מצב המערכת

        Returns:
            סיכום כללי
        """
        status_counts = {}
        for status in self.agent_status.values():
            status_counts[status.value] = status_counts.get(status.value, 0) + 1

        return {
            "total_agents": len(self.agents),
            "status_breakdown": status_counts,
            "messages_pending": sum(1 for m in self.message_queue if not m.read),
            "events_logged": len(self.event_log),
            "uptime_since": self.created_at.isoformat()
        }

    def cleanup(self):
        """ניקוי משאבים"""
        # ניקוי הודעות ישנות
        self.message_queue = [m for m in self.message_queue if not m.read]

        # שמירת מצב
        self._save_state()

        self._log_event("cleanup", "manager", {
            "messages_remaining": len(self.message_queue)
        })

    def __repr__(self):
        return f"<AgentManager(agents={len(self.agents)})>"
