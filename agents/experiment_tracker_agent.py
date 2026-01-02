"""
Experiment Tracker Agent - סוכן מעקב ניסויים

אחראי על:
- ניהול ניסויים בפיתוח
- השוואת גישות שונות
- שמירת קונפיגורציות
- שחזור ניסויים
"""

import json
import shutil
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict, field
from enum import Enum

from .base_agent import BaseAgent, DOCS_DIR


class ExperimentStatus(Enum):
    """סטטוס ניסוי"""
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABANDONED = "abandoned"


class ExperimentType(Enum):
    """סוג ניסוי"""
    AB_TEST = "ab_test"
    PARAMETER_SEARCH = "parameter_search"
    REGRESSION_TEST = "regression_test"
    FEATURE_EXPERIMENT = "feature_experiment"


@dataclass
class Metric:
    """מדד ניסוי"""
    name: str
    description: str
    higher_is_better: bool = True


@dataclass
class Experiment:
    """ניסוי"""
    id: str
    name: str
    hypothesis: str
    experiment_type: str
    status: str
    baseline_id: Optional[str]
    configuration: Dict
    metrics: List[Dict]
    results: Optional[Dict]
    conclusion: Optional[str]
    created_at: str
    completed_at: Optional[str] = None
    artifacts: List[str] = field(default_factory=list)


class ExperimentTrackerAgent(BaseAgent):
    """סוכן מעקב ניסויים"""

    def __init__(self, config: Optional[Dict] = None):
        super().__init__("experiment_tracker", config)
        self._init_directories()
        self._load_experiments()

    def _init_directories(self):
        """יצירת מבנה תיקיות"""
        self.experiments_dir = DOCS_DIR / "experiments"
        self.active_dir = self.experiments_dir / "active"
        self.completed_dir = self.experiments_dir / "completed"
        self.failed_dir = self.experiments_dir / "failed"
        self.templates_dir = self.experiments_dir / "templates"

        for directory in [self.experiments_dir, self.active_dir, self.completed_dir,
                         self.failed_dir, self.templates_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    def _load_experiments(self):
        """טעינת ניסויים"""
        experiments_file = self.experiments_dir / "experiments.json"
        if experiments_file.exists():
            with open(experiments_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.experiments = {e['id']: Experiment(**e) for e in data}
        else:
            self.experiments = {}

    def _save_experiments(self):
        """שמירת ניסויים"""
        experiments_file = self.experiments_dir / "experiments.json"
        with open(experiments_file, 'w', encoding='utf-8') as f:
            json.dump([asdict(e) for e in self.experiments.values()], f, ensure_ascii=False, indent=2)

    # ======== יצירת ניסויים ========

    def create_experiment(
        self,
        name: str,
        hypothesis: str,
        experiment_type: str,
        configuration: Dict,
        metrics: List[Dict],
        baseline_id: str = None
    ) -> Experiment:
        """
        יצירת ניסוי חדש

        Args:
            name: שם הניסוי
            hypothesis: ההיפותזה לבדיקה
            experiment_type: סוג הניסוי (ab_test, parameter_search, etc.)
            configuration: הגדרות הניסוי
            metrics: מדדים להערכה [{name, description, higher_is_better}]
            baseline_id: מזהה ניסוי baseline להשוואה
        """
        # יצירת מזהה
        exp_id = f"exp-{len(self.experiments) + 1:03d}"

        experiment = Experiment(
            id=exp_id,
            name=name,
            hypothesis=hypothesis,
            experiment_type=experiment_type,
            status=ExperimentStatus.DRAFT.value,
            baseline_id=baseline_id,
            configuration=configuration,
            metrics=metrics,
            results=None,
            conclusion=None,
            created_at=datetime.now().isoformat()
        )

        self.experiments[exp_id] = experiment
        self._save_experiments()

        # יצירת תיקיית ניסוי
        self._create_experiment_folder(experiment)

        self.log_action("create_experiment", {"id": exp_id, "name": name})
        return experiment

    def _create_experiment_folder(self, experiment: Experiment):
        """יצירת תיקיית ניסוי"""
        exp_dir = self.active_dir / experiment.id
        exp_dir.mkdir(exist_ok=True)

        (exp_dir / "code").mkdir(exist_ok=True)
        (exp_dir / "data").mkdir(exist_ok=True)
        (exp_dir / "results").mkdir(exist_ok=True)

        # שמירת config
        config_file = exp_dir / "config.yaml"
        self._save_experiment_config(experiment, config_file)

    def _save_experiment_config(self, experiment: Experiment, filepath: Path):
        """שמירת קונפיגורציית ניסוי"""
        content = f"""# Experiment: {experiment.id}
# Name: {experiment.name}
# Created: {experiment.created_at}

experiment:
  id: "{experiment.id}"
  name: "{experiment.name}"
  status: "{experiment.status}"

  hypothesis: |
    {experiment.hypothesis}

  baseline:
    experiment_id: {experiment.baseline_id or 'null'}

  configuration:
"""
        for key, value in experiment.configuration.items():
            content += f"    {key}: {json.dumps(value)}\n"

        content += "\n  metrics:\n"
        for metric in experiment.metrics:
            content += f"""    - name: "{metric['name']}"
      description: "{metric.get('description', '')}"
      higher_is_better: {str(metric.get('higher_is_better', True)).lower()}
"""

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

    # ======== ניהול ניסויים ========

    def start_experiment(self, exp_id: str) -> Dict:
        """התחלת ניסוי"""
        exp = self.experiments.get(exp_id)
        if not exp:
            return {"error": f"Experiment not found: {exp_id}"}

        exp.status = ExperimentStatus.RUNNING.value
        self._save_experiments()

        self.log_action("start_experiment", {"id": exp_id})
        return {"success": True, "status": exp.status}

    def record_results(
        self,
        exp_id: str,
        results: Dict,
        conclusion: str = None
    ) -> Dict:
        """
        רישום תוצאות

        Args:
            exp_id: מזהה הניסוי
            results: תוצאות {metric_name: value}
            conclusion: מסקנה
        """
        exp = self.experiments.get(exp_id)
        if not exp:
            return {"error": f"Experiment not found: {exp_id}"}

        exp.results = results
        if conclusion:
            exp.conclusion = conclusion
            exp.status = ExperimentStatus.COMPLETED.value
            exp.completed_at = datetime.now().isoformat()

            # העברה לתיקיית completed
            self._move_experiment_folder(exp, self.completed_dir)

        self._save_experiments()

        # שמירת תוצאות לקובץ
        self._save_results_file(exp)

        self.log_action("record_results", {"id": exp_id, "results": results})
        return {"success": True, "experiment": asdict(exp)}

    def _save_results_file(self, experiment: Experiment):
        """שמירת קובץ תוצאות"""
        if experiment.status == ExperimentStatus.COMPLETED.value:
            results_dir = self.completed_dir / experiment.id / "results"
        else:
            results_dir = self.active_dir / experiment.id / "results"

        results_dir.mkdir(parents=True, exist_ok=True)

        results_file = results_dir / "results.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump({
                "experiment_id": experiment.id,
                "results": experiment.results,
                "conclusion": experiment.conclusion,
                "recorded_at": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)

    def _move_experiment_folder(self, experiment: Experiment, target_dir: Path):
        """העברת תיקיית ניסוי"""
        source = self.active_dir / experiment.id
        target = target_dir / experiment.id

        if source.exists():
            shutil.move(str(source), str(target))

    def fail_experiment(self, exp_id: str, reason: str) -> Dict:
        """סימון ניסוי ככושל"""
        exp = self.experiments.get(exp_id)
        if not exp:
            return {"error": f"Experiment not found: {exp_id}"}

        exp.status = ExperimentStatus.FAILED.value
        exp.conclusion = f"FAILED: {reason}"
        exp.completed_at = datetime.now().isoformat()

        self._move_experiment_folder(exp, self.failed_dir)
        self._save_experiments()

        self.log_action("fail_experiment", {"id": exp_id, "reason": reason})
        return {"success": True}

    def abandon_experiment(self, exp_id: str, reason: str) -> Dict:
        """נטישת ניסוי"""
        exp = self.experiments.get(exp_id)
        if not exp:
            return {"error": f"Experiment not found: {exp_id}"}

        exp.status = ExperimentStatus.ABANDONED.value
        exp.conclusion = f"ABANDONED: {reason}"
        exp.completed_at = datetime.now().isoformat()

        self._save_experiments()

        self.log_action("abandon_experiment", {"id": exp_id, "reason": reason})
        return {"success": True}

    # ======== השוואה ושחזור ========

    def compare_experiments(self, exp_ids: List[str]) -> Dict:
        """
        השוואת ניסויים

        Args:
            exp_ids: רשימת מזהי ניסויים להשוואה
        """
        experiments = [self.experiments.get(eid) for eid in exp_ids]
        experiments = [e for e in experiments if e]

        if len(experiments) < 2:
            return {"error": "Need at least 2 experiments to compare"}

        comparison = {
            "experiments": [
                {"id": e.id, "name": e.name, "status": e.status}
                for e in experiments
            ],
            "metrics_comparison": []
        }

        # איסוף כל המדדים
        all_metrics = set()
        for exp in experiments:
            if exp.results:
                all_metrics.update(exp.results.keys())

        # השוואה לפי מדד
        for metric in all_metrics:
            metric_data = {
                "metric": metric,
                "values": {}
            }

            for exp in experiments:
                value = exp.results.get(metric) if exp.results else None
                metric_data["values"][exp.id] = value

            # זיהוי הטוב ביותר
            values_with_ids = [
                (exp.id, exp.results.get(metric))
                for exp in experiments
                if exp.results and exp.results.get(metric) is not None
            ]

            if values_with_ids:
                best = max(values_with_ids, key=lambda x: x[1])
                metric_data["best"] = best[0]

            comparison["metrics_comparison"].append(metric_data)

        return comparison

    def restore_experiment(
        self,
        exp_id: str,
        target_dir: str = None
    ) -> Dict:
        """
        שחזור ניסוי

        Args:
            exp_id: מזהה הניסוי
            target_dir: תיקיית יעד (אופציונלי)
        """
        exp = self.experiments.get(exp_id)
        if not exp:
            return {"error": f"Experiment not found: {exp_id}"}

        # מציאת תיקיית הניסוי
        for search_dir in [self.active_dir, self.completed_dir, self.failed_dir]:
            source = search_dir / exp_id
            if source.exists():
                if target_dir:
                    target = Path(target_dir)
                    shutil.copytree(str(source), str(target))
                    return {
                        "success": True,
                        "restored_to": str(target),
                        "configuration": exp.configuration
                    }
                else:
                    return {
                        "success": True,
                        "location": str(source),
                        "configuration": exp.configuration
                    }

        return {"error": f"Experiment folder not found: {exp_id}"}

    def rerun_experiment(
        self,
        exp_id: str,
        override_config: Dict = None
    ) -> Experiment:
        """
        הרצה מחדש של ניסוי

        Args:
            exp_id: מזהה הניסוי המקורי
            override_config: שינויים בקונפיגורציה
        """
        original = self.experiments.get(exp_id)
        if not original:
            raise ValueError(f"Experiment not found: {exp_id}")

        # יצירת קונפיגורציה חדשה
        new_config = original.configuration.copy()
        if override_config:
            new_config.update(override_config)

        new_exp = self.create_experiment(
            name=f"{original.name} (rerun)",
            hypothesis=original.hypothesis,
            experiment_type=original.experiment_type,
            configuration=new_config,
            metrics=original.metrics,
            baseline_id=exp_id
        )

        self.log_action("rerun_experiment", {
            "original": exp_id,
            "new": new_exp.id
        })

        return new_exp

    def clone_experiment(
        self,
        exp_id: str,
        new_name: str,
        new_config: Dict = None
    ) -> Experiment:
        """
        שכפול ניסוי עם שינויים

        Args:
            exp_id: מזהה הניסוי לשכפול
            new_name: שם חדש
            new_config: קונפיגורציה חדשה
        """
        original = self.experiments.get(exp_id)
        if not original:
            raise ValueError(f"Experiment not found: {exp_id}")

        config = new_config if new_config else original.configuration.copy()

        new_exp = self.create_experiment(
            name=new_name,
            hypothesis=original.hypothesis,
            experiment_type=original.experiment_type,
            configuration=config,
            metrics=original.metrics,
            baseline_id=exp_id
        )

        return new_exp

    # ======== דוחות ========

    def list_experiments(
        self,
        status: str = None,
        exp_type: str = None,
        limit: int = 50
    ) -> List[Dict]:
        """רשימת ניסויים"""
        experiments = list(self.experiments.values())

        if status:
            experiments = [e for e in experiments if e.status == status]
        if exp_type:
            experiments = [e for e in experiments if e.experiment_type == exp_type]

        experiments.sort(key=lambda x: x.created_at, reverse=True)

        return [
            {
                "id": e.id,
                "name": e.name,
                "status": e.status,
                "type": e.experiment_type,
                "created_at": e.created_at[:10],
                "has_results": e.results is not None
            }
            for e in experiments[:limit]
        ]

    def get_experiment_details(self, exp_id: str) -> Optional[Dict]:
        """פרטי ניסוי"""
        exp = self.experiments.get(exp_id)
        if exp:
            return asdict(exp)
        return None

    def generate_summary(self, period: str = "all") -> str:
        """יצירת סיכום ניסויים"""
        experiments = list(self.experiments.values())

        # סינון לפי תקופה
        if period == "weekly":
            week_ago = datetime.now().timestamp() - 7 * 24 * 3600
            experiments = [e for e in experiments
                         if datetime.fromisoformat(e.created_at).timestamp() > week_ago]
        elif period == "monthly":
            month_ago = datetime.now().timestamp() - 30 * 24 * 3600
            experiments = [e for e in experiments
                         if datetime.fromisoformat(e.created_at).timestamp() > month_ago]

        # סטטיסטיקות
        by_status = {}
        for exp in experiments:
            by_status[exp.status] = by_status.get(exp.status, 0) + 1

        summary = f"""# סיכום ניסויים - {period}

## סה"כ: {len(experiments)}

### לפי סטטוס
"""
        status_emoji = {
            "completed": "",
            "failed": "",
            "running": "",
            "draft": "",
            "abandoned": ""
        }

        for status, count in by_status.items():
            emoji = status_emoji.get(status, "")
            summary += f"- {emoji} {status}: {count}\n"

        # ניסויים שהסתיימו
        completed = [e for e in experiments if e.status == "completed"]
        if completed:
            summary += "\n### ניסויים שהושלמו\n"
            for exp in completed[:10]:
                result_emoji = "" if exp.conclusion and "אושרה" in exp.conclusion else ""
                summary += f"- {result_emoji} [{exp.id}] {exp.name}\n"

        return summary

    # ======== ממשק סוכן ========

    def run(self, command: str, **kwargs) -> Dict[str, Any]:
        """הפעלת פקודה"""
        commands = {
            "create": self.create_experiment,
            "start": self.start_experiment,
            "record_results": self.record_results,
            "fail": self.fail_experiment,
            "abandon": self.abandon_experiment,
            "compare": self.compare_experiments,
            "restore": self.restore_experiment,
            "rerun": self.rerun_experiment,
            "clone": self.clone_experiment,
            "list": self.list_experiments,
            "details": self.get_experiment_details,
            "summary": self.generate_summary,
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
        by_status = {}
        for exp in self.experiments.values():
            by_status[exp.status] = by_status.get(exp.status, 0) + 1

        return {
            "name": self.name,
            "total_experiments": len(self.experiments),
            "by_status": by_status,
            "active_count": by_status.get("running", 0) + by_status.get("draft", 0)
        }
