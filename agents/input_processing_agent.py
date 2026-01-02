"""
Input Processing Agent - סוכן עיבוד ווולידציה של קלטים

אחראי על:
- עיבוד קבצי PDF וטקסט
- נרמול לפורמט אחיד
- ולידציה וזיהוי בעיות
- דוחות עיבוד
"""

import json
import os
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
from enum import Enum

from .base_agent import BaseAgent, DOCS_DIR, REPORTS_DIR

# ניסיון לייבא ספריות עיבוד
try:
    import chardet
except ImportError:
    chardet = None

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


class FileType(Enum):
    """סוגי קבצים נתמכים"""
    PDF_DIGITAL = "pdf_digital"
    PDF_SCANNED = "pdf_scanned"
    PDF_MIXED = "pdf_mixed"
    TXT = "txt"
    CSV = "csv"
    JSON = "json"
    XML = "xml"
    MARKDOWN = "md"
    HTML = "html"
    UNKNOWN = "unknown"


class ProcessingStatus(Enum):
    """סטטוס עיבוד"""
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class InputProcessingAgent(BaseAgent):
    """סוכן עיבוד קלטים"""

    def __init__(self, config: Optional[Dict] = None):
        super().__init__("input_processing", config)
        self._init_directories()
        self._load_processing_history()

    def _init_directories(self):
        """יצירת מבנה תיקיות"""
        self.input_dir = Path(self.config.get("input_dir", "data/input"))
        self.output_dir = Path(self.config.get("output_dir", "data/output"))
        self.versions_dir = Path(self.config.get("versions_dir", "data/versions"))

        for directory in [self.input_dir / "pending",
                         self.input_dir / "processed",
                         self.input_dir / "failed",
                         self.output_dir / "normalized",
                         self.output_dir / "tables",
                         self.output_dir / "raw",
                         self.output_dir / "reports",
                         self.versions_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    def _load_processing_history(self):
        """טעינת היסטוריית עיבודים"""
        history_file = self.output_dir / "processing_history.json"
        if history_file.exists():
            with open(history_file, 'r', encoding='utf-8') as f:
                self.processing_history = json.load(f)
        else:
            self.processing_history = []

    def _save_processing_history(self):
        """שמירת היסטוריית עיבודים"""
        history_file = self.output_dir / "processing_history.json"
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(self.processing_history[-1000:], f, ensure_ascii=False, indent=2)

    def classify_input(self, file_path: str) -> Dict:
        """
        זיהוי וסיווג קובץ

        Args:
            file_path: נתיב לקובץ

        Returns:
            מידע על הקובץ
        """
        path = Path(file_path)

        if not path.exists():
            return {"error": f"File not found: {file_path}"}

        # זיהוי סוג קובץ
        ext = path.suffix.lower()
        file_type = self._detect_file_type(path, ext)

        # זיהוי encoding
        encoding = self._detect_encoding(path) if ext in ['.txt', '.csv', '.md'] else 'binary'

        # זיהוי שפה (בסיסי)
        language = self._detect_language(path) if file_type != FileType.UNKNOWN else 'unknown'

        # בדיקות איכות
        quality_indicators = self._check_quality_indicators(path, file_type)

        return {
            "file_path": str(path.absolute()),
            "file_name": path.name,
            "file_size": path.stat().st_size,
            "file_type": file_type.value,
            "encoding": encoding,
            "language": language,
            "quality_indicators": quality_indicators,
            "analyzed_at": datetime.now().isoformat()
        }

    def _detect_file_type(self, path: Path, ext: str) -> FileType:
        """זיהוי סוג קובץ"""
        type_map = {
            '.pdf': FileType.PDF_DIGITAL,
            '.txt': FileType.TXT,
            '.csv': FileType.CSV,
            '.json': FileType.JSON,
            '.xml': FileType.XML,
            '.md': FileType.MARKDOWN,
            '.html': FileType.HTML,
            '.htm': FileType.HTML,
        }

        file_type = type_map.get(ext, FileType.UNKNOWN)

        # בדיקה מעמיקה יותר ל-PDF
        if file_type == FileType.PDF_DIGITAL and pdfplumber:
            try:
                with pdfplumber.open(path) as pdf:
                    first_page = pdf.pages[0] if pdf.pages else None
                    if first_page:
                        text = first_page.extract_text() or ""
                        if len(text.strip()) < 50:
                            file_type = FileType.PDF_SCANNED
            except Exception:
                pass

        return file_type

    def _detect_encoding(self, path: Path) -> str:
        """זיהוי encoding של קובץ טקסט"""
        if chardet:
            try:
                with open(path, 'rb') as f:
                    raw = f.read(10000)
                    result = chardet.detect(raw)
                    return result.get('encoding', 'utf-8') or 'utf-8'
            except Exception:
                pass
        return 'utf-8'

    def _detect_language(self, path: Path) -> str:
        """זיהוי שפה (בסיסי)"""
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                sample = f.read(1000)

            # ספירת תווים עבריים
            hebrew_chars = sum(1 for c in sample if '\u0590' <= c <= '\u05FF')
            english_chars = sum(1 for c in sample if 'a' <= c.lower() <= 'z')

            if hebrew_chars > english_chars:
                return 'he'
            elif english_chars > hebrew_chars:
                return 'en'
            else:
                return 'mixed'
        except Exception:
            return 'unknown'

    def _check_quality_indicators(self, path: Path, file_type: FileType) -> Dict:
        """בדיקת אינדיקטורים לאיכות"""
        indicators = {
            "has_selectable_text": True,
            "needs_ocr": False,
            "has_tables": False,
            "has_images": False,
            "estimated_quality": "high"
        }

        if file_type in [FileType.PDF_DIGITAL, FileType.PDF_SCANNED, FileType.PDF_MIXED]:
            if pdfplumber:
                try:
                    with pdfplumber.open(path) as pdf:
                        if pdf.pages:
                            first_page = pdf.pages[0]
                            text = first_page.extract_text() or ""
                            tables = first_page.extract_tables() or []

                            indicators["has_selectable_text"] = len(text) > 50
                            indicators["needs_ocr"] = len(text) < 50
                            indicators["has_tables"] = len(tables) > 0
                            indicators["has_images"] = len(first_page.images or []) > 0

                            if indicators["needs_ocr"]:
                                indicators["estimated_quality"] = "low"
                            elif indicators["has_tables"]:
                                indicators["estimated_quality"] = "medium"
                except Exception:
                    indicators["estimated_quality"] = "unknown"

        return indicators

    def process_file(
        self,
        file_path: str,
        output_format: str = "json",
        force: bool = False
    ) -> Dict:
        """
        עיבוד קובץ

        Args:
            file_path: נתיב לקובץ
            output_format: פורמט פלט (json/md)
            force: לכפות עיבוד מחדש

        Returns:
            תוצאות העיבוד
        """
        path = Path(file_path)
        start_time = datetime.now()

        # בדיקת קיום
        if not path.exists():
            return self._create_error_result(file_path, "File not found")

        # יצירת מזהה
        file_id = self._generate_file_id(path)

        # בדיקה אם כבר עובד
        if not force and self._is_already_processed(file_id):
            return self._get_cached_result(file_id)

        # סיווג הקובץ
        classification = self.classify_input(file_path)
        file_type = FileType(classification.get("file_type", "unknown"))

        # עיבוד לפי סוג
        try:
            if file_type == FileType.PDF_DIGITAL:
                result = self._process_pdf(path)
            elif file_type == FileType.TXT:
                result = self._process_text(path, classification.get("encoding", "utf-8"))
            elif file_type == FileType.JSON:
                result = self._process_json(path)
            elif file_type == FileType.CSV:
                result = self._process_csv(path, classification.get("encoding", "utf-8"))
            else:
                result = self._process_generic(path, classification.get("encoding", "utf-8"))

            result["status"] = ProcessingStatus.SUCCESS.value

        except Exception as e:
            result = self._create_error_result(file_path, str(e))
            result["status"] = ProcessingStatus.FAILED.value

        # הוספת מטאדאטה
        end_time = datetime.now()
        result.update({
            "id": file_id,
            "source_file": str(path.absolute()),
            "classification": classification,
            "extraction_timestamp": end_time.isoformat(),
            "processing_time_seconds": (end_time - start_time).total_seconds()
        })

        # שמירה
        self._save_result(file_id, result, output_format)

        # עדכון היסטוריה
        self._record_processing(result)

        self.log_action("process_file", {
            "file": path.name,
            "status": result["status"],
            "time": result["processing_time_seconds"]
        })

        return result

    def _generate_file_id(self, path: Path) -> str:
        """יצירת מזהה ייחודי לקובץ"""
        with open(path, 'rb') as f:
            file_hash = hashlib.md5(f.read(10000)).hexdigest()[:8]
        return f"{path.stem}_{file_hash}"

    def _is_already_processed(self, file_id: str) -> bool:
        """בדיקה אם קובץ כבר עובד"""
        result_file = self.output_dir / "normalized" / f"{file_id}.json"
        return result_file.exists()

    def _get_cached_result(self, file_id: str) -> Dict:
        """קבלת תוצאה שמורה"""
        result_file = self.output_dir / "normalized" / f"{file_id}.json"
        with open(result_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _process_pdf(self, path: Path) -> Dict:
        """עיבוד קובץ PDF"""
        if not pdfplumber:
            return {
                "error": "pdfplumber not installed",
                "content": {"full_text": "", "tables": []}
            }

        content = {
            "full_text": "",
            "sections": [],
            "tables": [],
            "metadata": {}
        }

        warnings = []

        with pdfplumber.open(path) as pdf:
            content["metadata"]["page_count"] = len(pdf.pages)

            for i, page in enumerate(pdf.pages):
                # חילוץ טקסט
                text = page.extract_text() or ""
                content["full_text"] += f"\n--- עמוד {i+1} ---\n{text}"
                content["sections"].append({
                    "page": i + 1,
                    "text": text,
                    "char_count": len(text)
                })

                # חילוץ טבלאות
                tables = page.extract_tables() or []
                for j, table in enumerate(tables):
                    content["tables"].append({
                        "page": i + 1,
                        "table_index": j + 1,
                        "data": table,
                        "rows": len(table),
                        "cols": len(table[0]) if table else 0
                    })

                # בדיקת איכות
                if len(text) < 50:
                    warnings.append(f"עמוד {i+1}: טקסט מועט - ייתכן שנדרש OCR")

        return {
            "content": content,
            "quality_report": {
                "confidence_score": 0.9 if not warnings else 0.7,
                "warnings": warnings,
                "char_count": len(content["full_text"]),
                "table_count": len(content["tables"])
            }
        }

    def _process_text(self, path: Path, encoding: str) -> Dict:
        """עיבוד קובץ טקסט"""
        with open(path, 'r', encoding=encoding, errors='replace') as f:
            text = f.read()

        return {
            "content": {
                "full_text": text,
                "line_count": text.count('\n') + 1,
                "word_count": len(text.split()),
                "char_count": len(text)
            },
            "quality_report": {
                "confidence_score": 0.95,
                "warnings": [],
                "encoding_used": encoding
            }
        }

    def _process_json(self, path: Path) -> Dict:
        """עיבוד קובץ JSON"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return {
            "content": {
                "data": data,
                "type": type(data).__name__,
                "size": len(data) if isinstance(data, (list, dict)) else 1
            },
            "quality_report": {
                "confidence_score": 1.0,
                "warnings": [],
                "valid_json": True
            }
        }

    def _process_csv(self, path: Path, encoding: str) -> Dict:
        """עיבוד קובץ CSV"""
        import csv

        rows = []
        with open(path, 'r', encoding=encoding, errors='replace') as f:
            reader = csv.reader(f)
            for row in reader:
                rows.append(row)

        headers = rows[0] if rows else []
        data = rows[1:] if len(rows) > 1 else []

        return {
            "content": {
                "headers": headers,
                "data": data,
                "row_count": len(data),
                "column_count": len(headers)
            },
            "quality_report": {
                "confidence_score": 0.95,
                "warnings": [],
                "encoding_used": encoding
            }
        }

    def _process_generic(self, path: Path, encoding: str) -> Dict:
        """עיבוד קובץ גנרי"""
        try:
            with open(path, 'r', encoding=encoding, errors='replace') as f:
                text = f.read()
        except Exception:
            with open(path, 'rb') as f:
                text = f"[Binary file: {len(f.read())} bytes]"

        return {
            "content": {"full_text": text},
            "quality_report": {
                "confidence_score": 0.5,
                "warnings": ["Generic processing - may need manual review"]
            }
        }

    def _create_error_result(self, file_path: str, error: str) -> Dict:
        """יצירת תוצאת שגיאה"""
        return {
            "status": ProcessingStatus.FAILED.value,
            "error": error,
            "source_file": file_path,
            "content": None,
            "quality_report": {
                "confidence_score": 0,
                "warnings": [error]
            }
        }

    def _save_result(self, file_id: str, result: Dict, output_format: str):
        """שמירת תוצאת עיבוד"""
        # שמירה כ-JSON
        json_file = self.output_dir / "normalized" / f"{file_id}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        # שמירת דוח
        self._save_processing_report(file_id, result)

    def _save_processing_report(self, file_id: str, result: Dict):
        """שמירת דוח עיבוד"""
        report_file = self.output_dir / "reports" / f"{file_id}_report.md"

        classification = result.get("classification", {})
        quality = result.get("quality_report", {})
        content = result.get("content", {})

        status_emoji = {"success": "", "partial": "", "failed": ""}.get(
            result.get("status", ""), ""
        )

        report = f"""# דוח עיבוד - {Path(result.get('source_file', '')).name}

## סיכום
- **מזהה:** {file_id}
- **סוג:** {classification.get('file_type', 'unknown')}
- **גודל:** {classification.get('file_size', 0):,} בייטים
- **זמן עיבוד:** {result.get('processing_time_seconds', 0):.2f} שניות
- **סטטוס:** {status_emoji} {result.get('status', 'unknown')}

## תוצאות חילוץ
| מדד | ערך |
|-----|-----|
| תווים שחולצו | {content.get('char_count', len(str(content.get('full_text', ''))))} |
| מילים | {content.get('word_count', '-')} |
| טבלאות | {len(content.get('tables', []))} |

## איכות
- **ציון ביטחון:** {quality.get('confidence_score', 0):.0%}
"""

        if quality.get('warnings'):
            report += "\n### אזהרות \n"
            for w in quality['warnings']:
                report += f"- {w}\n"

        if result.get('error'):
            report += f"\n### שגיאות \n{result['error']}\n"

        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)

    def _record_processing(self, result: Dict):
        """רישום עיבוד בהיסטוריה"""
        record = {
            "id": result.get("id"),
            "file": Path(result.get("source_file", "")).name,
            "status": result.get("status"),
            "timestamp": result.get("extraction_timestamp"),
            "processing_time": result.get("processing_time_seconds")
        }
        self.processing_history.append(record)
        self._save_processing_history()

    def validate_content(self, content: Dict) -> Dict:
        """
        ולידציה של תוכן מעובד

        Args:
            content: התוכן לבדיקה

        Returns:
            תוצאות הולידציה
        """
        issues = []
        score = 1.0

        # בדיקה שהטקסט לא ריק
        text = content.get("full_text", "")
        if not text or len(text.strip()) == 0:
            issues.append({"type": "empty_content", "severity": "error"})
            score *= 0

        # בדיקת תווים בעייתיים
        problematic_chars = ['\x00', '\ufffd']
        for char in problematic_chars:
            if char in text:
                issues.append({"type": "problematic_chars", "char": repr(char), "severity": "warning"})
                score *= 0.9

        # בדיקת עקביות טבלאות
        tables = content.get("tables", [])
        for i, table in enumerate(tables):
            if not table.get("data"):
                continue
            col_counts = [len(row) for row in table["data"]]
            if len(set(col_counts)) > 1:
                issues.append({
                    "type": "inconsistent_table",
                    "table_index": i,
                    "severity": "warning"
                })
                score *= 0.95

        return {
            "valid": len([i for i in issues if i["severity"] == "error"]) == 0,
            "score": score,
            "issues": issues
        }

    # ======== ממשק סוכן ========

    def run(self, command: str, **kwargs) -> Dict[str, Any]:
        """הפעלת פקודה"""
        commands = {
            "classify": self.classify_input,
            "process": self.process_file,
            "validate": self.validate_content,
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
        recent = self.processing_history[-10:] if self.processing_history else []
        success_count = sum(1 for r in recent if r.get("status") == "success")

        return {
            "name": self.name,
            "total_processed": len(self.processing_history),
            "recent_success_rate": f"{success_count}/{len(recent)}",
            "input_dir": str(self.input_dir),
            "output_dir": str(self.output_dir)
        }
