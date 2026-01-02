"""
Regression Guard Agent - סוכן שמירה על רגרסיות

אחראי על:
- שמירת baselines של פלטים
- השוואת תוצאות לפלטים צפויים
- זיהוי רגרסיות
- מעקב אחרי שינויים
"""

import json
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict
from difflib import SequenceMatcher, unified_diff

from .base_agent import BaseAgent, DOCS_DIR


@dataclass
class Baseline:
    """תמונת בסיס"""
    id: str
    input_id: str
    output: Any
    output_hash: str
    created_at: str
    created_by: str
    metadata: Dict


@dataclass
class RegressionResult:
    """תוצאת בדיקת רגרסיה"""
    input_id: str
    status: str  # pass, regression, no_baseline
    baseline_date: Optional[str]
    diff: Optional[Dict]
    checked_at: str


class RegressionGuardAgent(BaseAgent):
    """סוכן שמירה על רגרסיות"""

    def __init__(self, config: Optional[Dict] = None):
        super().__init__("regression_guard", config)
        self._init_directories()
        self._load_baselines()
        self._load_config()

    def _init_directories(self):
        """יצירת מבנה תיקיות"""
        self.baselines_dir = DOCS_DIR / "baselines"
        self.results_dir = DOCS_DIR / "regression_results"
        self.archive_dir = self.baselines_dir / "archive"

        for directory in [self.baselines_dir, self.results_dir, self.archive_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    def _load_baselines(self):
        """טעינת baselines"""
        baselines_file = self.baselines_dir / "baselines.json"
        if baselines_file.exists():
            with open(baselines_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.baselines = {b['input_id']: Baseline(**b) for b in data}
        else:
            self.baselines = {}

    def _save_baselines(self):
        """שמירת baselines"""
        baselines_file = self.baselines_dir / "baselines.json"
        with open(baselines_file, 'w', encoding='utf-8') as f:
            json.dump([asdict(b) for b in self.baselines.values()], f, ensure_ascii=False, indent=2)

    def _load_config(self):
        """טעינת הגדרות"""
        config_file = self.baselines_dir / "config.json"
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                self.regression_config = json.load(f)
        else:
            self.regression_config = {
                "ignored_fields": ["timestamp", "processing_time", "id"],
                "tolerances": {
                    "confidence": 0.01,
                    "score": 0.05
                },
                "similarity_threshold": 0.95
            }

    # ======== ניהול Baselines ========

    def create_baseline(
        self,
        input_id: str,
        output: Any,
        metadata: Dict = None,
        created_by: str = "system"
    ) -> Baseline:
        """
        יצירת baseline חדש

        Args:
            input_id: מזהה הקלט
            output: הפלט לשמירה
            metadata: מטאדאטה נוספת
            created_by: יוצר ה-baseline
        """
        baseline_id = f"bl_{input_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        baseline = Baseline(
            id=baseline_id,
            input_id=input_id,
            output=output,
            output_hash=self._hash_output(output),
            created_at=datetime.now().isoformat(),
            created_by=created_by,
            metadata=metadata or {}
        )

        self.baselines[input_id] = baseline
        self._save_baselines()

        self.log_action("create_baseline", {"input_id": input_id, "id": baseline_id})
        return baseline

    def update_baseline(
        self,
        input_id: str,
        new_output: Any,
        reason: str,
        updated_by: str = "system"
    ) -> Baseline:
        """
        עדכון baseline קיים

        Args:
            input_id: מזהה הקלט
            new_output: הפלט החדש
            reason: סיבת העדכון
            updated_by: מעדכן
        """
        old_baseline = self.baselines.get(input_id)

        # ארכוב הישן
        if old_baseline:
            self._archive_baseline(old_baseline)

        # יצירת חדש
        new_baseline = self.create_baseline(
            input_id,
            new_output,
            metadata={
                "previous_baseline": old_baseline.id if old_baseline else None,
                "update_reason": reason,
                "updated_by": updated_by
            },
            created_by=updated_by
        )

        self.log_action("update_baseline", {
            "input_id": input_id,
            "reason": reason
        })

        return new_baseline

    def _archive_baseline(self, baseline: Baseline):
        """ארכוב baseline ישן"""
        archive_file = self.archive_dir / f"{baseline.id}.json"
        with open(archive_file, 'w', encoding='utf-8') as f:
            json.dump(asdict(baseline), f, ensure_ascii=False, indent=2)

    def delete_baseline(self, input_id: str) -> bool:
        """מחיקת baseline"""
        if input_id in self.baselines:
            baseline = self.baselines[input_id]
            self._archive_baseline(baseline)
            del self.baselines[input_id]
            self._save_baselines()
            return True
        return False

    def get_baseline(self, input_id: str) -> Optional[Baseline]:
        """קבלת baseline לקלט"""
        return self.baselines.get(input_id)

    # ======== בדיקות רגרסיה ========

    def check_regression(self, input_id: str, current_output: Any) -> RegressionResult:
        """
        בדיקת רגרסיה

        Args:
            input_id: מזהה הקלט
            current_output: הפלט הנוכחי

        Returns:
            תוצאת הבדיקה
        """
        baseline = self.baselines.get(input_id)

        if not baseline:
            return RegressionResult(
                input_id=input_id,
                status="no_baseline",
                baseline_date=None,
                diff=None,
                checked_at=datetime.now().isoformat()
            )

        # השוואה
        is_match, diff = self._compare_outputs(baseline.output, current_output)

        status = "pass" if is_match else "regression"

        result = RegressionResult(
            input_id=input_id,
            status=status,
            baseline_date=baseline.created_at,
            diff=diff if not is_match else None,
            checked_at=datetime.now().isoformat()
        )

        self.log_action("check_regression", {
            "input_id": input_id,
            "status": status
        })

        return result

    def _compare_outputs(self, baseline: Any, current: Any) -> Tuple[bool, Optional[Dict]]:
        """
        השוואת פלטים

        Returns:
            (האם תואם, הבדלים)
        """
        if type(baseline) != type(current):
            return False, {"type_mismatch": f"{type(baseline)} vs {type(current)}"}

        if isinstance(baseline, dict):
            return self._compare_dicts(baseline, current)
        elif isinstance(baseline, list):
            return self._compare_lists(baseline, current)
        elif isinstance(baseline, str):
            return self._compare_strings(baseline, current)
        else:
            is_equal = baseline == current
            return is_equal, None if is_equal else {"value_mismatch": f"{baseline} vs {current}"}

    def _compare_dicts(self, baseline: Dict, current: Dict) -> Tuple[bool, Optional[Dict]]:
        """השוואת מילונים"""
        ignored = set(self.regression_config.get("ignored_fields", []))
        tolerances = self.regression_config.get("tolerances", {})

        diff = {
            "added_keys": [],
            "removed_keys": [],
            "changed_values": []
        }

        baseline_keys = set(baseline.keys()) - ignored
        current_keys = set(current.keys()) - ignored

        # מפתחות שנוספו/הוסרו
        diff["added_keys"] = list(current_keys - baseline_keys)
        diff["removed_keys"] = list(baseline_keys - current_keys)

        # השוואת ערכים משותפים
        for key in baseline_keys & current_keys:
            b_val = baseline[key]
            c_val = current[key]

            # בדיקת tolerance לערכים מספריים
            if key in tolerances and isinstance(b_val, (int, float)) and isinstance(c_val, (int, float)):
                if abs(b_val - c_val) > tolerances[key]:
                    diff["changed_values"].append({
                        "key": key,
                        "baseline": b_val,
                        "current": c_val
                    })
            elif b_val != c_val:
                # השוואה רקורסיבית למילונים מקוננים
                if isinstance(b_val, dict) and isinstance(c_val, dict):
                    is_match, sub_diff = self._compare_dicts(b_val, c_val)
                    if not is_match:
                        diff["changed_values"].append({
                            "key": key,
                            "nested_diff": sub_diff
                        })
                else:
                    diff["changed_values"].append({
                        "key": key,
                        "baseline": str(b_val)[:100],
                        "current": str(c_val)[:100]
                    })

        is_match = not (diff["added_keys"] or diff["removed_keys"] or diff["changed_values"])
        return is_match, None if is_match else diff

    def _compare_lists(self, baseline: List, current: List) -> Tuple[bool, Optional[Dict]]:
        """השוואת רשימות"""
        if len(baseline) != len(current):
            return False, {
                "length_mismatch": f"{len(baseline)} vs {len(current)}"
            }

        differences = []
        for i, (b_item, c_item) in enumerate(zip(baseline, current)):
            is_match, diff = self._compare_outputs(b_item, c_item)
            if not is_match:
                differences.append({"index": i, "diff": diff})

        is_match = len(differences) == 0
        return is_match, None if is_match else {"item_differences": differences}

    def _compare_strings(self, baseline: str, current: str) -> Tuple[bool, Optional[Dict]]:
        """השוואת מחרוזות"""
        threshold = self.regression_config.get("similarity_threshold", 0.95)
        similarity = SequenceMatcher(None, baseline, current).ratio()

        if similarity >= threshold:
            return True, None

        # יצירת diff
        diff_lines = list(unified_diff(
            baseline.splitlines(keepends=True),
            current.splitlines(keepends=True),
            fromfile='baseline',
            tofile='current',
            lineterm=''
        ))

        return False, {
            "similarity": similarity,
            "diff": ''.join(diff_lines[:50])  # הגבלת גודל
        }

    def _hash_output(self, output: Any) -> str:
        """יצירת hash לפלט"""
        output_str = json.dumps(output, sort_keys=True, default=str)
        return hashlib.sha256(output_str.encode()).hexdigest()[:16]

    # ======== הרצת בדיקות ========

    def run_all_checks(
        self,
        get_current_output: callable,
        input_ids: List[str] = None
    ) -> Dict:
        """
        הרצת כל בדיקות הרגרסיה

        Args:
            get_current_output: פונקציה שמקבלת input_id ומחזירה פלט נוכחי
            input_ids: רשימת קלטים לבדיקה (ברירת מחדל: כל ה-baselines)
        """
        if input_ids is None:
            input_ids = list(self.baselines.keys())

        results = {
            "passed": [],
            "regressions": [],
            "no_baseline": [],
            "errors": []
        }

        for input_id in input_ids:
            try:
                current = get_current_output(input_id)
                result = self.check_regression(input_id, current)

                if result.status == "pass":
                    results["passed"].append(input_id)
                elif result.status == "regression":
                    results["regressions"].append({
                        "input_id": input_id,
                        "diff": result.diff
                    })
                else:
                    results["no_baseline"].append(input_id)

            except Exception as e:
                results["errors"].append({
                    "input_id": input_id,
                    "error": str(e)
                })

        # שמירת תוצאות
        self._save_run_results(results)

        return {
            "total": len(input_ids),
            "passed": len(results["passed"]),
            "regressions": len(results["regressions"]),
            "no_baseline": len(results["no_baseline"]),
            "errors": len(results["errors"]),
            "details": results,
            "run_at": datetime.now().isoformat()
        }

    def _save_run_results(self, results: Dict):
        """שמירת תוצאות הרצה"""
        filename = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        results_file = self.results_dir / filename
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

    # ======== דוחות ========

    def generate_report(self) -> str:
        """יצירת דוח רגרסיות"""
        report = f"""# דוח רגרסיות - {datetime.now().strftime('%Y-%m-%d')}

## סיכום Baselines
- **סה"כ baselines:** {len(self.baselines)}
"""

        # לפי יוצר
        by_creator = {}
        for bl in self.baselines.values():
            creator = bl.created_by
            by_creator[creator] = by_creator.get(creator, 0) + 1

        report += "\n### לפי יוצר\n"
        for creator, count in by_creator.items():
            report += f"- {creator}: {count}\n"

        # baselines אחרונים
        recent = sorted(self.baselines.values(), key=lambda x: x.created_at, reverse=True)[:10]
        report += "\n### Baselines אחרונים\n"
        for bl in recent:
            report += f"- [{bl.created_at[:10]}] {bl.input_id}\n"

        # הרצות אחרונות
        report += "\n## הרצות אחרונות\n"
        run_files = sorted(self.results_dir.glob("run_*.json"), reverse=True)[:5]
        for run_file in run_files:
            with open(run_file, 'r', encoding='utf-8') as f:
                run_data = json.load(f)
                passed = len(run_data.get("passed", []))
                regressions = len(run_data.get("regressions", []))
                report += f"- {run_file.stem}: {passed} passed, {regressions} regressions\n"

        return report

    def list_baselines(self, limit: int = 50) -> List[Dict]:
        """רשימת baselines"""
        baselines = sorted(
            self.baselines.values(),
            key=lambda x: x.created_at,
            reverse=True
        )[:limit]

        return [
            {
                "id": bl.id,
                "input_id": bl.input_id,
                "created_at": bl.created_at[:10],
                "created_by": bl.created_by,
                "hash": bl.output_hash
            }
            for bl in baselines
        ]

    # ======== ממשק סוכן ========

    def run(self, command: str, **kwargs) -> Dict[str, Any]:
        """הפעלת פקודה"""
        commands = {
            "create_baseline": self.create_baseline,
            "update_baseline": self.update_baseline,
            "delete_baseline": self.delete_baseline,
            "get_baseline": lambda input_id: asdict(self.get_baseline(input_id)) if self.get_baseline(input_id) else None,
            "check": self.check_regression,
            "list": self.list_baselines,
            "report": self.generate_report,
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
            "baselines_count": len(self.baselines),
            "last_baseline": max(
                (bl.created_at for bl in self.baselines.values()),
                default=None
            )
        }
