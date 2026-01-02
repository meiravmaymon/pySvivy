"""
QA Agent - סוכן בקרת איכות

אחראי על:
- זיהוי באגים ובעיות בקוד
- יצירת בדיקות מקלטים אמיתיים
- בדיקות עקביות בין שכבות
- דוחות איכות
"""

import json
import os
import subprocess
import re
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
from dataclasses import dataclass, asdict

from .base_agent import BaseAgent, DOCS_DIR, REPORTS_DIR


@dataclass
class TestCase:
    """מקרה בדיקה"""
    id: str
    name: str
    description: str
    input_data: Any
    expected_output: Any
    tags: List[str]
    created_at: str
    source: str  # manual, generated, regression


@dataclass
class TestResult:
    """תוצאת בדיקה"""
    test_id: str
    passed: bool
    actual_output: Any
    error_message: Optional[str]
    duration_ms: float
    timestamp: str


class QAAgent(BaseAgent):
    """סוכן בקרת איכות"""

    def __init__(self, config: Optional[Dict] = None):
        super().__init__("qa", config)
        self._init_directories()
        self._load_test_cases()
        self._load_test_results()

    def _init_directories(self):
        """יצירת מבנה תיקיות"""
        self.tests_dir = DOCS_DIR / "tests"
        self.test_data_dir = self.tests_dir / "data"
        self.results_dir = self.tests_dir / "results"

        for directory in [self.tests_dir, self.test_data_dir, self.results_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    def _load_test_cases(self):
        """טעינת מקרי בדיקה"""
        tests_file = self.tests_dir / "test_cases.json"
        if tests_file.exists():
            with open(tests_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.test_cases = [TestCase(**tc) for tc in data]
        else:
            self.test_cases = []

    def _save_test_cases(self):
        """שמירת מקרי בדיקה"""
        tests_file = self.tests_dir / "test_cases.json"
        with open(tests_file, 'w', encoding='utf-8') as f:
            json.dump([asdict(tc) for tc in self.test_cases], f, ensure_ascii=False, indent=2)

    def _load_test_results(self):
        """טעינת היסטוריית תוצאות"""
        results_file = self.results_dir / "test_history.json"
        if results_file.exists():
            with open(results_file, 'r', encoding='utf-8') as f:
                self.test_history = json.load(f)
        else:
            self.test_history = []

    def _save_test_results(self, results: List[TestResult]):
        """שמירת תוצאות בדיקה"""
        run_record = {
            "timestamp": datetime.now().isoformat(),
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "results": [asdict(r) for r in results]
        }
        self.test_history.append(run_record)

        # שמירה
        results_file = self.results_dir / "test_history.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(self.test_history[-100:], f, ensure_ascii=False, indent=2)

        # שמירת הרצה אחרונה
        latest_file = self.results_dir / "latest_run.json"
        with open(latest_file, 'w', encoding='utf-8') as f:
            json.dump(run_record, f, ensure_ascii=False, indent=2)

    # ======== יצירת בדיקות ========

    def create_test(
        self,
        name: str,
        description: str,
        input_data: Any,
        expected_output: Any,
        tags: Optional[List[str]] = None,
        source: str = "manual"
    ) -> TestCase:
        """
        יצירת מקרה בדיקה חדש

        Args:
            name: שם הבדיקה
            description: תיאור
            input_data: קלט הבדיקה
            expected_output: פלט צפוי
            tags: תגיות (smoke, regression, edge-case)
            source: מקור הבדיקה
        """
        test_id = f"test_{len(self.test_cases) + 1:04d}"

        test_case = TestCase(
            id=test_id,
            name=name,
            description=description,
            input_data=input_data,
            expected_output=expected_output,
            tags=tags or [],
            created_at=datetime.now().isoformat(),
            source=source
        )

        self.test_cases.append(test_case)
        self._save_test_cases()

        self.log_action("create_test", {"id": test_id, "name": name})
        return test_case

    def create_test_from_bug(
        self,
        bug_id: str,
        description: str,
        input_data: Any,
        expected_output: Any,
        input_file: Optional[str] = None
    ) -> TestCase:
        """
        יצירת בדיקה מבאג שנמצא

        Args:
            bug_id: מזהה הבאג
            description: תיאור הבאג
            input_data: קלט בעייתי
            expected_output: פלט נכון
            input_file: קובץ קלט לשמירה
        """
        test = self.create_test(
            name=f"Regression test for bug #{bug_id}",
            description=description,
            input_data=input_data,
            expected_output=expected_output,
            tags=["regression", f"bug_{bug_id}"],
            source="regression"
        )

        # שמירת קובץ קלט אם סופק
        if input_file and Path(input_file).exists():
            dest = self.test_data_dir / f"bug_{bug_id}_{Path(input_file).name}"
            import shutil
            shutil.copy(input_file, dest)
            self.log(f"Saved test input file: {dest}")

        return test

    # ======== הרצת בדיקות ========

    def run_tests(
        self,
        tags: Optional[List[str]] = None,
        test_ids: Optional[List[str]] = None,
        test_function: Optional[Callable] = None
    ) -> List[TestResult]:
        """
        הרצת בדיקות

        Args:
            tags: סינון לפי תגיות
            test_ids: סינון לפי מזהים
            test_function: פונקציית הבדיקה

        Returns:
            רשימת תוצאות
        """
        # סינון בדיקות
        tests_to_run = self.test_cases

        if tags:
            tests_to_run = [t for t in tests_to_run if any(tag in t.tags for tag in tags)]

        if test_ids:
            tests_to_run = [t for t in tests_to_run if t.id in test_ids]

        results = []
        for test in tests_to_run:
            result = self._run_single_test(test, test_function)
            results.append(result)

        # שמירת תוצאות
        self._save_test_results(results)

        self.log_action("run_tests", {
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed)
        })

        return results

    def _run_single_test(
        self,
        test: TestCase,
        test_function: Optional[Callable]
    ) -> TestResult:
        """הרצת בדיקה בודדת"""
        start_time = datetime.now()

        try:
            if test_function:
                actual = test_function(test.input_data)
            else:
                # הרצה פשוטה - השוואה ישירה
                actual = test.input_data  # Placeholder

            # השוואה
            passed = self._compare_outputs(actual, test.expected_output)
            error = None if passed else "Output mismatch"

        except Exception as e:
            actual = None
            passed = False
            error = str(e)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds() * 1000

        return TestResult(
            test_id=test.id,
            passed=passed,
            actual_output=actual,
            error_message=error,
            duration_ms=duration,
            timestamp=end_time.isoformat()
        )

    def _compare_outputs(self, actual: Any, expected: Any) -> bool:
        """השוואת פלטים"""
        if type(actual) != type(expected):
            return False

        if isinstance(actual, dict):
            return self._compare_dicts(actual, expected)
        elif isinstance(actual, list):
            return all(self._compare_outputs(a, e) for a, e in zip(actual, expected))
        else:
            return actual == expected

    def _compare_dicts(self, actual: Dict, expected: Dict) -> bool:
        """השוואת מילונים"""
        for key in expected:
            if key not in actual:
                return False
            if not self._compare_outputs(actual[key], expected[key]):
                return False
        return True

    # ======== ניתוח קוד ========

    def analyze_code(self, file_path: str) -> Dict:
        """
        ניתוח קוד לזיהוי בעיות פוטנציאליות

        Args:
            file_path: נתיב לקובץ

        Returns:
            ממצאים
        """
        path = Path(file_path)
        if not path.exists():
            return {"error": f"File not found: {file_path}"}

        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            code = f.read()

        findings = []

        # בדיקת SQL Injection
        sql_patterns = [
            r'f".*SELECT.*{',
            r'f".*INSERT.*{',
            r'f".*UPDATE.*{',
            r'f".*DELETE.*{',
            r'".*SELECT.*" \% ',
            r'".*SELECT.*".format\(',
        ]
        for pattern in sql_patterns:
            matches = re.findall(pattern, code, re.IGNORECASE)
            if matches:
                findings.append({
                    "type": "SQL_INJECTION_RISK",
                    "severity": "HIGH",
                    "file": file_path,
                    "pattern": pattern,
                    "count": len(matches)
                })

        # בדיקת Hardcoded Secrets
        secret_patterns = [
            (r'password\s*=\s*["\'][^"\']+["\']', "HARDCODED_PASSWORD"),
            (r'api_key\s*=\s*["\'][^"\']+["\']', "HARDCODED_API_KEY"),
            (r'secret\s*=\s*["\'][^"\']+["\']', "HARDCODED_SECRET"),
        ]
        for pattern, finding_type in secret_patterns:
            matches = re.findall(pattern, code, re.IGNORECASE)
            if matches:
                findings.append({
                    "type": finding_type,
                    "severity": "CRITICAL",
                    "file": file_path,
                    "count": len(matches)
                })

        # בדיקת Error Handling
        if 'except:' in code or 'except Exception:' in code:
            if 'pass' in code:
                findings.append({
                    "type": "BARE_EXCEPT_WITH_PASS",
                    "severity": "MEDIUM",
                    "file": file_path,
                    "message": "Bare except with pass may hide errors"
                })

        # בדיקת Logging רגיש
        log_sensitive = [
            r'log.*password',
            r'log.*secret',
            r'print\(.*password',
        ]
        for pattern in log_sensitive:
            if re.search(pattern, code, re.IGNORECASE):
                findings.append({
                    "type": "SENSITIVE_DATA_LOGGING",
                    "severity": "HIGH",
                    "file": file_path,
                    "pattern": pattern
                })

        return {
            "file": file_path,
            "analyzed_at": datetime.now().isoformat(),
            "findings_count": len(findings),
            "findings": findings,
            "lines_of_code": code.count('\n') + 1
        }

    def analyze_directory(self, directory: str, patterns: List[str] = None) -> Dict:
        """
        ניתוח תיקייה שלמה

        Args:
            directory: נתיב לתיקייה
            patterns: תבניות קבצים (ברירת מחדל: *.py)
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            return {"error": f"Directory not found: {directory}"}

        patterns = patterns or ["*.py"]
        all_findings = []
        files_analyzed = 0

        for pattern in patterns:
            for file_path in dir_path.rglob(pattern):
                if "__pycache__" in str(file_path):
                    continue
                result = self.analyze_code(str(file_path))
                if "findings" in result:
                    all_findings.extend(result["findings"])
                    files_analyzed += 1

        # סיכום לפי חומרה
        severity_counts = {}
        for f in all_findings:
            sev = f.get("severity", "UNKNOWN")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        return {
            "directory": directory,
            "files_analyzed": files_analyzed,
            "total_findings": len(all_findings),
            "by_severity": severity_counts,
            "findings": all_findings
        }

    # ======== דוחות ========

    def generate_report(self) -> str:
        """יצירת דוח QA"""
        latest = self.test_history[-1] if self.test_history else None

        report = f"""# דוח QA - {datetime.now().strftime('%Y-%m-%d')}

## סיכום בדיקות
"""

        if latest:
            pass_rate = (latest['passed'] / latest['total'] * 100) if latest['total'] > 0 else 0
            report += f"""
- **בדיקות שעברו:** {latest['passed']}/{latest['total']} ({pass_rate:.1f}%)
- **בדיקות שנכשלו:** {latest['failed']}
- **זמן הרצה אחרונה:** {latest['timestamp']}
"""

            # כשלונות
            failed = [r for r in latest.get('results', []) if not r['passed']]
            if failed:
                report += "\n### כשלונות \n"
                for f in failed[:10]:
                    report += f"- **{f['test_id']}:** {f.get('error_message', 'Unknown error')}\n"
        else:
            report += "\nאין היסטוריית בדיקות.\n"

        # סטטיסטיקות
        report += f"""
## סטטיסטיקות
- **מקרי בדיקה:** {len(self.test_cases)}
- **הרצות אחרונות:** {len(self.test_history)}
"""

        # לפי תגית
        tag_counts = {}
        for tc in self.test_cases:
            for tag in tc.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        if tag_counts:
            report += "\n### בדיקות לפי תגית\n"
            for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1]):
                report += f"- {tag}: {count}\n"

        # שמירת הדוח
        report_file = REPORTS_DIR / f"qa_report_{datetime.now().strftime('%Y%m%d')}.md"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)

        return report

    def get_coverage_summary(self) -> Dict:
        """סיכום כיסוי בדיקות"""
        return {
            "total_test_cases": len(self.test_cases),
            "by_source": {
                "manual": sum(1 for t in self.test_cases if t.source == "manual"),
                "generated": sum(1 for t in self.test_cases if t.source == "generated"),
                "regression": sum(1 for t in self.test_cases if t.source == "regression")
            },
            "by_tag": self._count_by_tags(),
            "last_run": self.test_history[-1] if self.test_history else None
        }

    def _count_by_tags(self) -> Dict[str, int]:
        """ספירת בדיקות לפי תגית"""
        counts = {}
        for tc in self.test_cases:
            for tag in tc.tags:
                counts[tag] = counts.get(tag, 0) + 1
        return counts

    # ======== ממשק סוכן ========

    def run(self, command: str, **kwargs) -> Dict[str, Any]:
        """הפעלת פקודה"""
        commands = {
            "create_test": self.create_test,
            "create_test_from_bug": self.create_test_from_bug,
            "run_tests": self.run_tests,
            "analyze_code": self.analyze_code,
            "analyze_directory": self.analyze_directory,
            "generate_report": self.generate_report,
            "get_coverage": self.get_coverage_summary,
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
        latest = self.test_history[-1] if self.test_history else None
        return {
            "name": self.name,
            "test_cases_count": len(self.test_cases),
            "test_runs_count": len(self.test_history),
            "last_run_passed": latest['passed'] if latest else None,
            "last_run_total": latest['total'] if latest else None
        }
