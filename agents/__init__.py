"""
Svivy Project Agents - מערכת סוכנים אוטונומיים לניהול פרויקט

This package contains specialized agents that help manage various aspects
of the Svivy municipal system project:

Core Agents (New):
    - StateContextAgent: ניהול מצב והקשר, תיעוד החלטות וניסויים
    - InputProcessingAgent: עיבוד ווולידציה של קלטים (PDF, טקסט)
    - QAAgent: בקרת איכות, זיהוי באגים, יצירת בדיקות
    - SchemaEvolutionAgent: ניהול מיגרציות ושינויי סכמה
    - ArchitectureAgent: שמירה על עקביות ארכיטקטונית
    - RegressionGuardAgent: זיהוי רגרסיות ושמירת baselines
    - IntegrationOrchestratorAgent: תיאום בין שכבות המערכת
    - ExperimentTrackerAgent: מעקב אחרי ניסויים והשוואת גישות
    - ProjectManagerAgent: ניהול משימות ותעדוף
    - SecurityAgent: אבטחת מידע ובדיקות אבטחה
    - IntegrationGuardianAgent: שמירה על תאימות לפני שינויים

Existing Agents (Integrated):
    - OCRLearningAgent: למידה מתיקוני OCR לשיפור דיוק
    - DBActionAgent: חילוץ פעולות מדיונים ויצירת פקודות DB

Central Management:
    - AgentManager: מנהל מרכזי לכל הסוכנים

Usage:
    from agents import AgentManager

    # אתחול כל הסוכנים
    manager = AgentManager()
    manager.initialize_all_agents()

    # הפעלת סוכן ספציפי
    result = manager.run_agent("security_agent", action="full_scan")

    # קבלת סטטוס כל הסוכנים
    status = manager.get_all_status()
"""

from .base_agent import BaseAgent, AgentMessage, AgentEvent
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
from .agent_manager import AgentManager

# Import existing agents from project root
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from ocr_learning_agent import OCRLearningAgent, get_learning_agent
    from db_action_agent import DBActionAgent, get_action_agent
    _EXISTING_AGENTS_AVAILABLE = True
except ImportError:
    OCRLearningAgent = None
    DBActionAgent = None
    get_learning_agent = None
    get_action_agent = None
    _EXISTING_AGENTS_AVAILABLE = False

__all__ = [
    # Base classes
    'BaseAgent',
    'AgentMessage',
    'AgentEvent',

    # Core agents
    'StateContextAgent',
    'InputProcessingAgent',
    'QAAgent',
    'SchemaEvolutionAgent',
    'ArchitectureAgent',
    'RegressionGuardAgent',
    'IntegrationOrchestratorAgent',
    'ExperimentTrackerAgent',
    'ProjectManagerAgent',
    'SecurityAgent',
    'IntegrationGuardianAgent',

    # Existing agents (if available)
    'OCRLearningAgent',
    'DBActionAgent',
    'get_learning_agent',
    'get_action_agent',

    # Manager
    'AgentManager',
]


def get_all_agents_info() -> dict:
    """
    Get information about all available agents

    Returns:
        Dictionary with agent information
    """
    agents_info = {
        "core_agents": {
            "StateContextAgent": "ניהול מצב והקשר, תיעוד החלטות וניסויים",
            "InputProcessingAgent": "עיבוד ווולידציה של קלטים (PDF, טקסט)",
            "QAAgent": "בקרת איכות, זיהוי באגים, יצירת בדיקות",
            "SchemaEvolutionAgent": "ניהול מיגרציות ושינויי סכמה",
            "ArchitectureAgent": "שמירה על עקביות ארכיטקטונית",
            "RegressionGuardAgent": "זיהוי רגרסיות ושמירת baselines",
            "IntegrationOrchestratorAgent": "תיאום בין שכבות המערכת",
            "ExperimentTrackerAgent": "מעקב אחרי ניסויים והשוואת גישות",
            "ProjectManagerAgent": "ניהול משימות ותעדוף",
            "SecurityAgent": "אבטחת מידע ובדיקות אבטחה",
            "IntegrationGuardianAgent": "שמירה על תאימות לפני שינויים",
        },
        "existing_agents": {
            "OCRLearningAgent": "למידה מתיקוני OCR לשיפור דיוק" if _EXISTING_AGENTS_AVAILABLE else "Not available",
            "DBActionAgent": "חילוץ פעולות מדיונים ויצירת פקודות DB" if _EXISTING_AGENTS_AVAILABLE else "Not available",
        },
        "existing_agents_available": _EXISTING_AGENTS_AVAILABLE,
        "total_agents": 11 + (2 if _EXISTING_AGENTS_AVAILABLE else 0)
    }
    return agents_info
