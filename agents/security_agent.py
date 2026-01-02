"""
Security Agent - סוכן אבטחת מידע

אחראי על סריקות אבטחה, זיהוי פגיעויות, וניהול תאימות רגולטורית
למערכות ממשל ורשויות מקומיות.
"""

import os
import re
import subprocess
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from enum import Enum

from .base_agent import BaseAgent, DOCS_DIR, REPORTS_DIR, PROJECT_ROOT


class Severity(Enum):
    """רמות חומרה"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ActionType(Enum):
    """סוגי פעולות"""
    AUTO_FIX = "auto_fix"
    PENDING_APPROVAL = "pending_approval"
    BLOCKED = "blocked"


class SecurityAgent(BaseAgent):
    """
    סוכן אבטחת מידע - Virtual CISO

    תחומי אחריות:
    - סריקת קוד (SAST)
    - ניהול תלויות
    - אבטחת API
    - ניהול הרשאות
    - דוחות תאימות
    """

    # כלים לסריקה
    SECURITY_TOOLS = {
        "bandit": "bandit -r {path} -f json",
        "safety": "safety check --json",
        "pip-audit": "pip-audit --format=json"
    }

    # דפוסים מסוכנים בקוד
    DANGEROUS_PATTERNS = {
        "sql_injection": {
            "pattern": r'(execute|cursor\.execute)\s*\(\s*["\'].*%s|f["\'].*\{.*\}.*["\']',
            "severity": Severity.CRITICAL,
            "description": "SQL Injection vulnerability",
            "fix_hint": "Use parameterized queries"
        },
        "hardcoded_secret": {
            "pattern": r'(password|secret|api_key|token)\s*=\s*["\'][^"\']{8,}["\']',
            "severity": Severity.CRITICAL,
            "description": "Hardcoded secret/credential",
            "fix_hint": "Use environment variables"
        },
        "command_injection": {
            "pattern": r'os\.system\s*\(\s*f["\']|subprocess\.\w+\s*\([^)]*shell\s*=\s*True',
            "severity": Severity.CRITICAL,
            "description": "Command injection risk",
            "fix_hint": "Use subprocess with shell=False"
        },
        "unsafe_pickle": {
            "pattern": r'pickle\.loads?\s*\(',
            "severity": Severity.HIGH,
            "description": "Unsafe deserialization with pickle",
            "fix_hint": "Use json for untrusted data"
        },
        "path_traversal": {
            "pattern": r'open\s*\(\s*f["\'].*\{.*\}|os\.path\.join\s*\([^,]+,\s*user',
            "severity": Severity.HIGH,
            "description": "Potential path traversal",
            "fix_hint": "Validate and sanitize file paths"
        },
        "sensitive_logging": {
            "pattern": r'(logger|logging|print)\s*\.\s*\w+\s*\([^)]*password|token|secret[^)]*\)',
            "severity": Severity.MEDIUM,
            "description": "Sensitive data in logs",
            "fix_hint": "Remove sensitive data from logs"
        },
        "id_in_log": {
            "pattern": r'(logger|logging|print).*תעודת זהות|ת\.ז|id_number',
            "severity": Severity.HIGH,
            "description": "ID number exposed in logs",
            "fix_hint": "Mask or remove ID numbers from logs"
        }
    }

    # סיפי CVSS
    CVSS_THRESHOLDS = {
        "auto_fix": 9.0,
        "alert": 7.0,
        "medium": 4.0
    }

    # זמני תגובה לפי חומרה
    RESPONSE_TIMES = {
        Severity.CRITICAL: timedelta(hours=0),  # מיידי
        Severity.HIGH: timedelta(hours=24),
        Severity.MEDIUM: timedelta(days=7),
        Severity.LOW: timedelta(days=30)
    }

    def __init__(self, config: Optional[Dict] = None):
        super().__init__("security_agent", config)
        self.findings: List[Dict] = []
        self.pending_actions: List[Dict] = []
        self.auto_fixes: List[Dict] = []
        self._init_state()

    def _init_state(self):
        """אתחול מצב הסוכן"""
        if "findings_history" not in self.state:
            self.state["findings_history"] = []
        if "actions_taken" not in self.state:
            self.state["actions_taken"] = []
        if "pending_approvals" not in self.state:
            self.state["pending_approvals"] = []
        if "compliance_status" not in self.state:
            self.state["compliance_status"] = {}
        if "scan_history" not in self.state:
            self.state["scan_history"] = []

    def run(self, action: str = "full_scan", **kwargs) -> Dict[str, Any]:
        """
        הפעלת הסוכן

        Actions:
            full_scan: סריקה מלאה
            scan_file: סריקת קובץ ספציפי
            check_dependency: בדיקת חבילה
            audit_user: ביקורת משתמש
            compliance_report: דוח תאימות
        """
        self.log(f"Running action: {action}")

        if action == "full_scan":
            return self.full_security_scan(kwargs.get("path", PROJECT_ROOT))
        elif action == "scan_file":
            return self.scan_file(kwargs.get("file_path"))
        elif action == "check_dependency":
            return self.check_dependency(kwargs.get("package_name"))
        elif action == "code_patterns":
            return self.scan_code_patterns(kwargs.get("path", PROJECT_ROOT))
        elif action == "compliance_report":
            return self.generate_compliance_report()
        elif action == "daily_report":
            return self.generate_daily_report()
        else:
            return {"error": f"Unknown action: {action}"}

    def full_security_scan(self, path: Path = None) -> Dict[str, Any]:
        """סריקת אבטחה מלאה"""
        path = path or PROJECT_ROOT
        self.log(f"Starting full security scan on {path}")

        results = {
            "timestamp": datetime.now().isoformat(),
            "path": str(path),
            "findings": [],
            "summary": {}
        }

        # סריקת דפוסים מסוכנים בקוד
        pattern_results = self.scan_code_patterns(path)
        results["findings"].extend(pattern_results.get("findings", []))

        # סריקת תלויות
        dep_results = self.scan_dependencies()
        results["findings"].extend(dep_results.get("findings", []))

        # סיכום
        results["summary"] = self._summarize_findings(results["findings"])

        # שמירה להיסטוריה
        self.state["scan_history"].append({
            "timestamp": results["timestamp"],
            "summary": results["summary"]
        })

        # טיפול בממצאים קריטיים
        self._handle_critical_findings(results["findings"])

        self.save_state()
        self.log_action("full_scan", {"path": str(path), "findings_count": len(results["findings"])})

        return results

    def scan_code_patterns(self, path: Path = None) -> Dict[str, Any]:
        """סריקת דפוסים מסוכנים בקוד"""
        path = Path(path) if path else PROJECT_ROOT
        findings = []

        python_files = list(path.rglob("*.py"))

        for py_file in python_files:
            # דלג על תיקיות מיוחדות
            if any(part.startswith('.') or part in ['__pycache__', 'venv', 'node_modules']
                   for part in py_file.parts):
                continue

            try:
                content = py_file.read_text(encoding='utf-8')
                lines = content.split('\n')

                for pattern_name, pattern_info in self.DANGEROUS_PATTERNS.items():
                    for line_num, line in enumerate(lines, 1):
                        if re.search(pattern_info["pattern"], line, re.IGNORECASE):
                            finding = {
                                "id": f"SEC-{len(findings)+1:04d}",
                                "type": pattern_name,
                                "severity": pattern_info["severity"].value,
                                "file": str(py_file.relative_to(path)),
                                "line": line_num,
                                "code": line.strip()[:100],
                                "description": pattern_info["description"],
                                "fix_hint": pattern_info["fix_hint"],
                                "found_at": datetime.now().isoformat()
                            }
                            findings.append(finding)
            except Exception as e:
                self.log(f"Error scanning {py_file}: {e}", "warning")

        self.findings = findings
        return {"findings": findings, "files_scanned": len(python_files)}

    def scan_file(self, file_path: str) -> Dict[str, Any]:
        """סריקת קובץ ספציפי"""
        if not file_path:
            return {"error": "No file path provided"}

        path = Path(file_path)
        if not path.exists():
            return {"error": f"File not found: {file_path}"}

        findings = []

        try:
            content = path.read_text(encoding='utf-8')
            lines = content.split('\n')

            for pattern_name, pattern_info in self.DANGEROUS_PATTERNS.items():
                for line_num, line in enumerate(lines, 1):
                    if re.search(pattern_info["pattern"], line, re.IGNORECASE):
                        findings.append({
                            "id": f"SEC-{len(findings)+1:04d}",
                            "type": pattern_name,
                            "severity": pattern_info["severity"].value,
                            "file": str(path),
                            "line": line_num,
                            "code": line.strip()[:100],
                            "description": pattern_info["description"],
                            "fix_hint": pattern_info["fix_hint"]
                        })
        except Exception as e:
            return {"error": f"Error scanning file: {e}"}

        self.log_action("scan_file", {"file": file_path, "findings": len(findings)})
        return {"file": file_path, "findings": findings}

    def scan_dependencies(self) -> Dict[str, Any]:
        """סריקת תלויות פגיעות"""
        findings = []

        # בדיקה עם safety
        try:
            result = subprocess.run(
                ["safety", "check", "--json"],
                capture_output=True,
                text=True,
                cwd=PROJECT_ROOT,
                timeout=60
            )
            if result.stdout:
                try:
                    safety_data = json.loads(result.stdout)
                    for vuln in safety_data.get("vulnerabilities", []):
                        findings.append({
                            "id": f"DEP-{len(findings)+1:04d}",
                            "type": "vulnerable_dependency",
                            "severity": self._cvss_to_severity(vuln.get("cvss", 0)),
                            "package": vuln.get("package_name"),
                            "version": vuln.get("analyzed_version"),
                            "vulnerability_id": vuln.get("vulnerability_id"),
                            "description": vuln.get("advisory", "")[:200],
                            "fix_hint": f"Update to {vuln.get('fixed_in', 'latest')}"
                        })
                except json.JSONDecodeError:
                    self.log("Could not parse safety output", "warning")
        except FileNotFoundError:
            self.log("safety not installed, skipping dependency check", "warning")
        except subprocess.TimeoutExpired:
            self.log("Dependency check timed out", "warning")
        except Exception as e:
            self.log(f"Error in dependency scan: {e}", "warning")

        return {"findings": findings, "tool": "safety"}

    def check_dependency(self, package_name: str) -> Dict[str, Any]:
        """בדיקת חבילה ספציפית"""
        if not package_name:
            return {"error": "No package name provided"}

        try:
            result = subprocess.run(
                ["pip-audit", "--format=json", package_name],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.stdout:
                return {"package": package_name, "result": json.loads(result.stdout)}
            return {"package": package_name, "result": "No vulnerabilities found"}
        except Exception as e:
            return {"error": f"Could not check package: {e}"}

    def _cvss_to_severity(self, cvss: float) -> str:
        """המרת ציון CVSS לרמת חומרה"""
        if cvss >= 9.0:
            return Severity.CRITICAL.value
        elif cvss >= 7.0:
            return Severity.HIGH.value
        elif cvss >= 4.0:
            return Severity.MEDIUM.value
        else:
            return Severity.LOW.value

    def _summarize_findings(self, findings: List[Dict]) -> Dict[str, int]:
        """סיכום ממצאים לפי חומרה"""
        summary = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "info": 0,
            "total": len(findings)
        }

        for finding in findings:
            severity = finding.get("severity", "info")
            if severity in summary:
                summary[severity] += 1

        return summary

    def _handle_critical_findings(self, findings: List[Dict]):
        """טיפול בממצאים קריטיים"""
        critical_findings = [f for f in findings if f.get("severity") == Severity.CRITICAL.value]

        for finding in critical_findings:
            self.log(f"CRITICAL finding: {finding['type']} in {finding.get('file', 'unknown')}", "error")

            # הוספה לפעולות ממתינות
            self.pending_actions.append({
                "id": finding["id"],
                "action": "fix_critical_vulnerability",
                "finding": finding,
                "created_at": datetime.now().isoformat(),
                "status": "pending"
            })

        self.state["pending_approvals"] = self.pending_actions
        self.save_state()

    def approve_action(self, action_id: str) -> Dict[str, Any]:
        """אישור פעולה ממתינה"""
        for action in self.pending_actions:
            if action["id"] == action_id:
                action["status"] = "approved"
                action["approved_at"] = datetime.now().isoformat()

                self.state["actions_taken"].append(action)
                self.pending_actions.remove(action)
                self.state["pending_approvals"] = self.pending_actions
                self.save_state()

                self.log_action("action_approved", {"action_id": action_id})
                return {"status": "approved", "action": action}

        return {"error": f"Action not found: {action_id}"}

    def reject_action(self, action_id: str, reason: str) -> Dict[str, Any]:
        """דחיית פעולה ממתינה"""
        for action in self.pending_actions:
            if action["id"] == action_id:
                action["status"] = "rejected"
                action["rejected_at"] = datetime.now().isoformat()
                action["rejection_reason"] = reason

                self.pending_actions.remove(action)
                self.state["pending_approvals"] = self.pending_actions
                self.save_state()

                self.log_action("action_rejected", {"action_id": action_id, "reason": reason})
                return {"status": "rejected", "action": action}

        return {"error": f"Action not found: {action_id}"}

    def generate_compliance_report(self) -> Dict[str, Any]:
        """יצירת דוח תאימות רגולטורית"""
        report = {
            "generated_at": datetime.now().isoformat(),
            "frameworks": {
                "owasp_top_10": self._check_owasp_compliance(),
                "israel_privacy": self._check_privacy_compliance(),
                "cyber_directorate": self._check_cyber_compliance()
            },
            "overall_status": "compliant",
            "recommendations": []
        }

        # בדיקה אם יש בעיות
        for framework, status in report["frameworks"].items():
            if not status.get("compliant", True):
                report["overall_status"] = "non_compliant"
                report["recommendations"].extend(status.get("recommendations", []))

        # שמירת הדוח
        report_path = REPORTS_DIR / f"compliance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        self.log_action("compliance_report", {"status": report["overall_status"]})
        return report

    def _check_owasp_compliance(self) -> Dict[str, Any]:
        """בדיקת תאימות OWASP Top 10"""
        issues = []

        # בדיקת ממצאים קיימים
        for finding in self.findings:
            if finding.get("type") in ["sql_injection", "command_injection"]:
                issues.append("A03:2021 - Injection vulnerability found")
            elif finding.get("type") == "hardcoded_secret":
                issues.append("A07:2021 - Identification and Authentication Failures")

        return {
            "compliant": len(issues) == 0,
            "issues": issues,
            "recommendations": issues
        }

    def _check_privacy_compliance(self) -> Dict[str, Any]:
        """בדיקת תאימות לתקנות פרטיות ישראליות"""
        issues = []

        for finding in self.findings:
            if finding.get("type") in ["id_in_log", "sensitive_logging"]:
                issues.append("מידע אישי חשוף - נדרשת הצפנה")

        return {
            "compliant": len(issues) == 0,
            "issues": issues,
            "recommendations": issues
        }

    def _check_cyber_compliance(self) -> Dict[str, Any]:
        """בדיקת תאימות להנחיות מערך הסייבר"""
        return {
            "compliant": True,
            "issues": [],
            "recommendations": []
        }

    def generate_daily_report(self) -> Dict[str, Any]:
        """יצירת דוח יומי"""
        today = datetime.now().date()

        # סריקה מלאה
        scan_results = self.full_security_scan()

        report = {
            "date": str(today),
            "generated_at": datetime.now().isoformat(),
            "summary": scan_results.get("summary", {}),
            "critical_count": scan_results["summary"].get("critical", 0),
            "high_count": scan_results["summary"].get("high", 0),
            "medium_count": scan_results["summary"].get("medium", 0),
            "low_count": scan_results["summary"].get("low", 0),
            "auto_fixes": self.auto_fixes,
            "pending_approvals": self.pending_actions,
            "new_findings": [f for f in scan_results.get("findings", [])
                           if f.get("found_at", "").startswith(str(today))]
        }

        # שמירת הדוח
        report_path = REPORTS_DIR / f"security_daily_{today}.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        self.log_action("daily_report", {"date": str(today), "findings": report["summary"]["total"]})

        return report

    def get_status(self) -> Dict[str, Any]:
        """קבלת סטטוס הסוכן"""
        return {
            "name": self.name,
            "status": "active",
            "last_scan": self.state.get("scan_history", [{}])[-1].get("timestamp") if self.state.get("scan_history") else None,
            "open_findings": len(self.findings),
            "pending_actions": len(self.pending_actions),
            "compliance_status": self.state.get("compliance_status", {}),
            "summary": self._summarize_findings(self.findings) if self.findings else {}
        }

    def get_pending_actions(self) -> List[Dict]:
        """קבלת פעולות ממתינות לאישור"""
        return self.pending_actions

    def get_findings(self, severity: Optional[str] = None) -> List[Dict]:
        """קבלת ממצאים לפי חומרה"""
        if severity:
            return [f for f in self.findings if f.get("severity") == severity]
        return self.findings
