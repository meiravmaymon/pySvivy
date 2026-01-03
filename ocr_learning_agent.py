"""
OCR Learning Agent - לומד מתיקונים לשיפור דיוק ה-OCR

הסוכן הזה:
1. שומר כל תיקון שהמשתמש עושה (OCR -> ערך נכון)
2. מנתח דפוסי שגיאות נפוצות
3. בונה מילון תיקונים אוטומטי
4. מספק המלצות לשיפור ה-OCR
"""

import json
import os
import re
from datetime import datetime
from collections import defaultdict
from difflib import SequenceMatcher
from typing import Dict, List, Tuple, Optional

# קובץ אחסון הלמידה
LEARNING_DATA_FILE = 'ocr_learning_data.json'
CORRECTIONS_LOG_FILE = 'ocr_corrections_log.json'


class OCRLearningAgent:
    """סוכן למידה מתיקוני OCR"""

    def __init__(self):
        self.corrections = self._load_corrections()
        self.patterns = self._load_patterns()
        self.stats = self._load_stats()

    def _load_corrections(self) -> Dict:
        """טעינת היסטוריית תיקונים"""
        if os.path.exists(LEARNING_DATA_FILE):
            with open(LEARNING_DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('corrections', {})
        return {
            'names': {},           # תיקוני שמות
            'titles': {},          # תיקוני כותרות
            'decisions': {},       # תיקוני החלטות
            'numbers': {},         # תיקוני מספרים
            'dates': {},           # תיקוני תאריכים
            'words': {},           # תיקוני מילים כלליות
            'summarys': {},        # משוב על תקצירים שנוצרו ע"י AI
            'admin_categories': {},  # משוב על סיווג מנהלתי אוטומטי
        }

    def _load_patterns(self) -> Dict:
        """טעינת דפוסי שגיאות שזוהו"""
        if os.path.exists(LEARNING_DATA_FILE):
            with open(LEARNING_DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('patterns', {})
        return {
            'char_substitutions': {},  # החלפות תווים נפוצות
            'prefix_errors': {},       # שגיאות בתחילת מילים
            'suffix_errors': {},       # שגיאות בסוף מילים
            'common_misreads': {},     # קריאות שגויות נפוצות
            'reversals': {},           # היפוכי טקסט RTL/LTR
        }

    def _load_stats(self) -> Dict:
        """טעינת סטטיסטיקות"""
        if os.path.exists(LEARNING_DATA_FILE):
            with open(LEARNING_DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('stats', {})
        return {
            'total_corrections': 0,
            'corrections_by_field': defaultdict(int),
            'accuracy_over_time': [],
            'most_common_errors': defaultdict(int),
        }

    def save(self):
        """שמירת כל נתוני הלמידה"""
        data = {
            'corrections': self.corrections,
            'patterns': self.patterns,
            'stats': dict(self.stats),
            'last_updated': datetime.now().isoformat()
        }
        with open(LEARNING_DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def record_correction(self, field_type: str, ocr_value: str, correct_value: str,
                         context: Optional[Dict] = None):
        """
        שמירת תיקון חדש

        Args:
            field_type: סוג השדה (name, title, decision, number, date, word)
            ocr_value: הערך שה-OCR קרא
            correct_value: הערך הנכון שהמשתמש הזין
            context: הקשר נוסף (מזהה ישיבה, תאריך, וכו')
        """
        if ocr_value == correct_value:
            return  # אין תיקון

        # הוספה למילון התיקונים
        category = f"{field_type}s" if not field_type.endswith('s') else field_type
        if category not in self.corrections:
            self.corrections[category] = {}

        if ocr_value not in self.corrections[category]:
            self.corrections[category][ocr_value] = {
                'correct': correct_value,
                'count': 0,
                'first_seen': datetime.now().isoformat(),
                'contexts': []
            }

        self.corrections[category][ocr_value]['count'] += 1
        self.corrections[category][ocr_value]['last_seen'] = datetime.now().isoformat()

        if context:
            self.corrections[category][ocr_value]['contexts'].append(context)

        # עדכון סטטיסטיקות
        self.stats['total_corrections'] += 1
        if isinstance(self.stats['corrections_by_field'], defaultdict):
            self.stats['corrections_by_field'][field_type] += 1
        else:
            self.stats['corrections_by_field'] = defaultdict(int, self.stats['corrections_by_field'])
            self.stats['corrections_by_field'][field_type] += 1

        # ניתוח דפוס השגיאה
        self._analyze_error_pattern(ocr_value, correct_value)

        # שמירה ללוג
        self._log_correction(field_type, ocr_value, correct_value, context)

        # שמירת הנתונים
        self.save()

    def _analyze_error_pattern(self, ocr_value: str, correct_value: str):
        """ניתוח דפוס השגיאה לזיהוי תבניות"""

        # חיפוש החלפות תווים
        if len(ocr_value) == len(correct_value):
            for i, (o, c) in enumerate(zip(ocr_value, correct_value)):
                if o != c:
                    key = f"{o}->{c}"
                    if key not in self.patterns['char_substitutions']:
                        self.patterns['char_substitutions'][key] = 0
                    self.patterns['char_substitutions'][key] += 1

        # חיפוש שגיאות בתחילת/סוף מילים
        words_ocr = ocr_value.split()
        words_correct = correct_value.split()

        if len(words_ocr) == len(words_correct):
            for w_ocr, w_correct in zip(words_ocr, words_correct):
                if w_ocr != w_correct:
                    # בדיקת קידומת
                    if w_ocr[:2] != w_correct[:2] and len(w_ocr) >= 2:
                        key = f"{w_ocr[:2]}->{w_correct[:2]}"
                        if key not in self.patterns['prefix_errors']:
                            self.patterns['prefix_errors'][key] = 0
                        self.patterns['prefix_errors'][key] += 1

                    # בדיקת סיומת
                    if w_ocr[-2:] != w_correct[-2:] and len(w_ocr) >= 2:
                        key = f"{w_ocr[-2:]}->{w_correct[-2:]}"
                        if key not in self.patterns['suffix_errors']:
                            self.patterns['suffix_errors'][key] = 0
                        self.patterns['suffix_errors'][key] += 1

        # שמירת קריאה שגויה נפוצה
        key = f"{ocr_value}=>{correct_value}"
        if key not in self.patterns['common_misreads']:
            self.patterns['common_misreads'][key] = 0
        self.patterns['common_misreads'][key] += 1

        # זיהוי היפוך טקסט (RTL/LTR)
        self._detect_reversal_pattern(ocr_value, correct_value)

    def _detect_reversal_pattern(self, ocr_value: str, correct_value: str):
        """
        זיהוי אם התיקון היה היפוך טקסט (RTL/LTR issue)
        ושמירת הדפוס ללמידה עתידית
        """
        if not ocr_value or not correct_value:
            return

        # בדיקה אם זה היפוך פשוט
        if correct_value == ocr_value[::-1]:
            if 'reversals' not in self.patterns:
                self.patterns['reversals'] = {}
            if ocr_value not in self.patterns['reversals']:
                self.patterns['reversals'][ocr_value] = {
                    'correct': correct_value,
                    'count': 0,
                    'type': 'simple_reversal'
                }
            self.patterns['reversals'][ocr_value]['count'] += 1
            return

        # בדיקה אם זה היפוך עם תיקון אותיות סופיות
        # למשל: ודאינל -> לניאדו (היפוך + תיקון ד->ו בסוף)
        reversed_ocr = ocr_value[::-1]

        # אותיות סופיות ומקבילותיהן
        final_letter_pairs = {
            'מ': 'ם', 'נ': 'ן', 'פ': 'ף', 'צ': 'ץ', 'כ': 'ך',
            'ם': 'מ', 'ן': 'נ', 'ף': 'פ', 'ץ': 'צ', 'ך': 'כ'
        }

        # נסה להחליף אותיות סופיות ולבדוק התאמה
        normalized_reversed = list(reversed_ocr)
        for i, char in enumerate(normalized_reversed):
            if char in final_letter_pairs:
                # בסוף מילה - צריך להיות סופית
                if i == len(normalized_reversed) - 1 or not normalized_reversed[i + 1].isalpha():
                    if char in ['מ', 'נ', 'פ', 'צ', 'כ']:
                        normalized_reversed[i] = final_letter_pairs[char]
                # בתחילת/אמצע - צריך להיות רגילה
                else:
                    if char in ['ם', 'ן', 'ף', 'ץ', 'ך']:
                        normalized_reversed[i] = final_letter_pairs[char]

        normalized_reversed_str = ''.join(normalized_reversed)

        if normalized_reversed_str == correct_value:
            if 'reversals' not in self.patterns:
                self.patterns['reversals'] = {}
            if ocr_value not in self.patterns['reversals']:
                self.patterns['reversals'][ocr_value] = {
                    'correct': correct_value,
                    'count': 0,
                    'type': 'reversal_with_final_letters'
                }
            self.patterns['reversals'][ocr_value]['count'] += 1

    def _log_correction(self, field_type: str, ocr_value: str, correct_value: str,
                       context: Optional[Dict] = None):
        """שמירת תיקון ללוג"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'field_type': field_type,
            'ocr_value': ocr_value,
            'correct_value': correct_value,
            'context': context
        }

        log = []
        if os.path.exists(CORRECTIONS_LOG_FILE):
            with open(CORRECTIONS_LOG_FILE, 'r', encoding='utf-8') as f:
                log = json.load(f)

        log.append(log_entry)

        with open(CORRECTIONS_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(log, f, ensure_ascii=False, indent=2)

    def auto_correct(self, text: str, field_type: str = 'word') -> Tuple[str, List[Dict]]:
        """
        תיקון אוטומטי של טקסט לפי התיקונים שנלמדו

        Args:
            text: הטקסט לתיקון
            field_type: סוג השדה

        Returns:
            tuple: (טקסט מתוקן, רשימת תיקונים שבוצעו)
        """
        corrections_made = []
        corrected_text = text

        # בדיקה בקטגוריה הספציפית
        category = f"{field_type}s" if not field_type.endswith('s') else field_type
        if category in self.corrections:
            for ocr_val, data in self.corrections[category].items():
                if ocr_val in corrected_text and data['count'] >= 2:  # רק תיקונים שחזרו 2+ פעמים
                    corrected_text = corrected_text.replace(ocr_val, data['correct'])
                    corrections_made.append({
                        'original': ocr_val,
                        'corrected': data['correct'],
                        'confidence': min(data['count'] / 5, 1.0)  # ביטחון לפי מספר חזרות
                    })

        # בדיקה בקטגוריית מילים כללית
        if category != 'words' and 'words' in self.corrections:
            for ocr_val, data in self.corrections['words'].items():
                if ocr_val in corrected_text and data['count'] >= 3:
                    corrected_text = corrected_text.replace(ocr_val, data['correct'])
                    corrections_made.append({
                        'original': ocr_val,
                        'corrected': data['correct'],
                        'confidence': min(data['count'] / 5, 1.0)
                    })

        return corrected_text, corrections_made

    def suggest_correction(self, ocr_value: str, field_type: str = 'word') -> Optional[Dict]:
        """
        הצעת תיקון לערך נתון

        Args:
            ocr_value: הערך שה-OCR קרא
            field_type: סוג השדה

        Returns:
            dict עם הצעת התיקון או None
        """
        category = f"{field_type}s" if not field_type.endswith('s') else field_type

        # חיפוש התאמה מדויקת
        if category in self.corrections and ocr_value in self.corrections[category]:
            data = self.corrections[category][ocr_value]
            return {
                'suggestion': data['correct'],
                'confidence': min(data['count'] / 5, 1.0),
                'times_corrected': data['count']
            }

        # חיפוש התאמה דומה (fuzzy)
        best_match = None
        best_similarity = 0

        for cat in [category, 'words']:
            if cat not in self.corrections:
                continue
            for known_ocr, data in self.corrections[cat].items():
                similarity = SequenceMatcher(None, ocr_value, known_ocr).ratio()
                if similarity > 0.8 and similarity > best_similarity:
                    best_match = {
                        'suggestion': data['correct'],
                        'confidence': similarity * min(data['count'] / 5, 1.0),
                        'similar_to': known_ocr,
                        'times_corrected': data['count']
                    }
                    best_similarity = similarity

        return best_match

    def get_accuracy_report(self) -> Dict:
        """יצירת דוח דיוק ה-OCR"""
        report = {
            'total_corrections': self.stats['total_corrections'],
            'corrections_by_field': dict(self.stats['corrections_by_field']) if isinstance(self.stats['corrections_by_field'], defaultdict) else self.stats['corrections_by_field'],
            'most_common_char_substitutions': sorted(
                self.patterns['char_substitutions'].items(),
                key=lambda x: x[1],
                reverse=True
            )[:10],
            'most_common_misreads': sorted(
                self.patterns['common_misreads'].items(),
                key=lambda x: x[1],
                reverse=True
            )[:20],
            'known_corrections_count': sum(
                len(cat) for cat in self.corrections.values()
            )
        }
        return report

    def get_improvement_suggestions(self) -> List[str]:
        """המלצות לשיפור ה-OCR"""
        suggestions = []

        # ניתוח החלפות תווים נפוצות
        if self.patterns['char_substitutions']:
            top_subs = sorted(
                self.patterns['char_substitutions'].items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]
            for sub, count in top_subs:
                if count >= 3:
                    suggestions.append(f"החלפת תווים נפוצה: {sub} ({count} פעמים)")

        # ניתוח שגיאות לפי סוג שדה
        if self.stats['corrections_by_field']:
            fields = dict(self.stats['corrections_by_field']) if isinstance(self.stats['corrections_by_field'], defaultdict) else self.stats['corrections_by_field']
            worst_field = max(fields.items(), key=lambda x: x[1]) if fields else None
            if worst_field and worst_field[1] >= 5:
                suggestions.append(f"שדה '{worst_field[0]}' דורש תשומת לב - {worst_field[1]} תיקונים")

        # המלצות כלליות
        if self.stats['total_corrections'] > 50:
            suggestions.append("שקול להוסיף מילון מותאם אישית ל-Tesseract")

        if len(self.corrections.get('names', {})) > 10:
            suggestions.append("יש הרבה תיקוני שמות - שקול ליצור רשימת שמות מוכרים")

        return suggestions

    def export_dictionary(self, output_file: str = 'ocr_custom_dictionary.txt'):
        """ייצוא מילון תיקונים לשימוש עם Tesseract"""
        words = set()

        # איסוף כל המילים הנכונות
        for category in self.corrections.values():
            for data in category.values():
                correct = data.get('correct', '')
                words.update(correct.split())

        # כתיבה לקובץ
        with open(output_file, 'w', encoding='utf-8') as f:
            for word in sorted(words):
                if len(word) > 1:  # התעלמות מתווים בודדים
                    f.write(f"{word}\n")

        return len(words)

    def get_reversal_patterns(self) -> List[str]:
        """
        החזרת רשימת דפוסי היפוך שנלמדו לשימוש ב-ocr_protocol.py

        Returns:
            רשימת מחרוזות הפוכות שזוהו 2+ פעמים
        """
        if 'reversals' not in self.patterns:
            return []

        # החזר רק דפוסים שחזרו לפחות פעמיים
        return [
            ocr_val
            for ocr_val, data in self.patterns['reversals'].items()
            if data.get('count', 0) >= 2
        ]

    def export_reversal_patterns(self, output_file: str = 'ocr_reversal_patterns.py'):
        """
        ייצוא דפוסי היפוך לקובץ Python להכללה ב-ocr_protocol.py

        Args:
            output_file: נתיב הקובץ לייצוא

        Returns:
            מספר הדפוסים שיוצאו
        """
        if 'reversals' not in self.patterns:
            return 0

        patterns = []
        for ocr_val, data in self.patterns['reversals'].items():
            if data.get('count', 0) >= 2:
                correct = data.get('correct', '')
                pattern_type = data.get('type', 'unknown')
                patterns.append({
                    'reversed': ocr_val,
                    'correct': correct,
                    'count': data['count'],
                    'type': pattern_type
                })

        # מיון לפי מספר חזרות (הנפוצים ביותר קודם)
        patterns.sort(key=lambda x: x['count'], reverse=True)

        # כתיבה לקובץ Python
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('# דפוסי היפוך שנלמדו מתיקוני משתמש\n')
            f.write('# נוצר אוטומטית על ידי OCRLearningAgent\n')
            f.write(f'# עודכן: {datetime.now().isoformat()}\n\n')
            f.write('LEARNED_REVERSAL_PATTERNS = [\n')
            for p in patterns:
                f.write(f"    '{p['reversed']}',  # {p['correct']} ({p['count']}x, {p['type']})\n")
            f.write(']\n')

        return len(patterns)

    def get_known_name_mapping(self, ocr_name: str) -> Optional[Dict]:
        """
        בדיקה אם שם OCR מוכר ויש לו תיקון למוד.
        מחזיר את השם הנכון מבסיס הנתונים אם נמצא.

        Args:
            ocr_name: השם שזוהה ב-OCR

        Returns:
            dict עם {correct_name, db_person_id, confidence} או None
        """
        if 'names' not in self.corrections:
            return None

        # חיפוש התאמה מדויקת
        if ocr_name in self.corrections['names']:
            data = self.corrections['names'][ocr_name]
            if data.get('count', 0) >= 1:  # אפילו תיקון אחד מספיק לשמות
                return {
                    'correct_name': data['correct'],
                    'db_person_id': data.get('db_person_id'),
                    'confidence': min(data['count'] / 3, 1.0),
                    'times_corrected': data['count']
                }

        # חיפוש שם הפוך (בעיית RTL)
        reversed_name = ocr_name[::-1]
        if reversed_name in self.corrections['names']:
            data = self.corrections['names'][reversed_name]
            if data.get('count', 0) >= 1:
                return {
                    'correct_name': data['correct'],
                    'db_person_id': data.get('db_person_id'),
                    'confidence': min(data['count'] / 3, 1.0),
                    'times_corrected': data['count'],
                    'was_reversed': True
                }

        return None

    def record_name_match(self, ocr_name: str, correct_name: str, db_person_id: int = None):
        """
        שמירת התאמת שם - כשהמשתמש מאשר התאמה בין שם OCR לאדם בבסיס הנתונים

        Args:
            ocr_name: השם שזוהה ב-OCR
            correct_name: השם הנכון מבסיס הנתונים
            db_person_id: מזהה האדם בבסיס הנתונים
        """
        if ocr_name == correct_name:
            return  # אין צורך לשמור אם זהה

        if 'names' not in self.corrections:
            self.corrections['names'] = {}

        if ocr_name not in self.corrections['names']:
            self.corrections['names'][ocr_name] = {
                'correct': correct_name,
                'db_person_id': db_person_id,
                'count': 0,
                'first_seen': datetime.now().isoformat()
            }

        self.corrections['names'][ocr_name]['count'] += 1
        self.corrections['names'][ocr_name]['last_seen'] = datetime.now().isoformat()
        if db_person_id:
            self.corrections['names'][ocr_name]['db_person_id'] = db_person_id

        # שמירה
        self.save()

        # לוג
        self._log_correction('name', ocr_name, correct_name, {
            'db_person_id': db_person_id,
            'type': 'name_match'
        })

    def get_known_role_mapping(self, ocr_role: str) -> Optional[Dict]:
        """
        בדיקה אם תפקיד OCR מוכר ויש לו תיקון למוד.

        Args:
            ocr_role: התפקיד שזוהה ב-OCR

        Returns:
            dict עם {correct_role, confidence} או None
        """
        if 'roles' not in self.corrections:
            return None

        # חיפוש התאמה מדויקת
        if ocr_role in self.corrections['roles']:
            data = self.corrections['roles'][ocr_role]
            if data.get('count', 0) >= 1:
                return {
                    'correct_role': data['correct'],
                    'confidence': min(data['count'] / 3, 1.0),
                    'times_corrected': data['count']
                }

        # חיפוש תפקיד הפוך
        reversed_role = ocr_role[::-1]
        if reversed_role in self.corrections['roles']:
            data = self.corrections['roles'][reversed_role]
            if data.get('count', 0) >= 1:
                return {
                    'correct_role': data['correct'],
                    'confidence': min(data['count'] / 3, 1.0),
                    'times_corrected': data['count'],
                    'was_reversed': True
                }

        return None

    def record_role_correction(self, ocr_role: str, correct_role: str):
        """
        שמירת תיקון תפקיד

        Args:
            ocr_role: התפקיד שזוהה ב-OCR
            correct_role: התפקיד הנכון
        """
        if ocr_role == correct_role:
            return

        if 'roles' not in self.corrections:
            self.corrections['roles'] = {}

        if ocr_role not in self.corrections['roles']:
            self.corrections['roles'][ocr_role] = {
                'correct': correct_role,
                'count': 0,
                'first_seen': datetime.now().isoformat()
            }

        self.corrections['roles'][ocr_role]['count'] += 1
        self.corrections['roles'][ocr_role]['last_seen'] = datetime.now().isoformat()

        self.save()
        self._log_correction('role', ocr_role, correct_role, {'type': 'role_correction'})

    def get_summary_feedback_stats(self) -> Dict:
        """
        סטטיסטיקות משוב על תקצירים שנוצרו ע"י AI

        Returns:
            dict עם סטטיסטיקות אישורים ודחיות
        """
        if 'summarys' not in self.corrections:
            return {
                'total_feedback': 0,
                'approved': 0,
                'rejected': 0,
                'approval_rate': 0.0
            }

        approved = 0
        rejected = 0

        for summary, data in self.corrections['summarys'].items():
            contexts = data.get('contexts', [])
            for ctx in contexts:
                if ctx.get('feedback_type') == 'summary_approved':
                    approved += 1
                elif ctx.get('feedback_type') == 'summary_rejected':
                    rejected += 1

        total = approved + rejected
        return {
            'total_feedback': total,
            'approved': approved,
            'rejected': rejected,
            'approval_rate': approved / total if total > 0 else 0.0
        }

    def get_summary_improvement_suggestions(self) -> List[str]:
        """
        המלצות לשיפור יצירת תקצירים

        Returns:
            רשימת המלצות לשיפור
        """
        stats = self.get_summary_feedback_stats()
        suggestions = []

        if stats['total_feedback'] < 10:
            return ['נדרש יותר משוב כדי לספק המלצות']

        if stats['approval_rate'] < 0.5:
            suggestions.append('שיעור האישור נמוך - שקול לשפר את ההנחיות ל-LLM')
            suggestions.append('בדוק האם דברי ההסבר נחלצים כראוי לפני יצירת התקציר')

        if stats['rejected'] > 10:
            suggestions.append('יש הרבה דחיות - בדוק את איכות הטקסט הנכנס ל-LLM')

        return suggestions

    # ========================================
    # Administrative Category Learning Methods
    # ========================================

    def record_category_feedback(self, title: str, auto_category: str, user_category: str,
                                 confidence: float = 0.0, context: Optional[Dict] = None):
        """
        שמירת משוב על סיווג מנהלתי אוטומטי

        Args:
            title: כותרת הסעיף שסווג
            auto_category: הקטגוריה שהמערכת הציעה
            user_category: הקטגוריה שהמשתמש בחר
            confidence: רמת הביטחון של הסיווג האוטומטי
            context: הקשר נוסף
        """
        if 'admin_categories' not in self.corrections:
            self.corrections['admin_categories'] = {}

        # מפתח: שילוב של כותרת + קטגוריה אוטומטית
        key = f"{auto_category}|{title[:100]}"  # חיתוך כותרת לאורך סביר

        approved = (auto_category == user_category)

        if key not in self.corrections['admin_categories']:
            self.corrections['admin_categories'][key] = {
                'auto_category': auto_category,
                'title_sample': title[:200],
                'approved_count': 0,
                'rejected_count': 0,
                'user_corrections': {},  # מיפוי לקטגוריות שהמשתמש בחר
                'first_seen': datetime.now().isoformat(),
                'confidence_avg': confidence,
            }

        entry = self.corrections['admin_categories'][key]

        if approved:
            entry['approved_count'] += 1
        else:
            entry['rejected_count'] += 1
            # שמור את התיקון של המשתמש
            if user_category not in entry['user_corrections']:
                entry['user_corrections'][user_category] = 0
            entry['user_corrections'][user_category] += 1

        entry['last_seen'] = datetime.now().isoformat()

        # עדכון ממוצע רמת ביטחון
        total = entry['approved_count'] + entry['rejected_count']
        entry['confidence_avg'] = (entry['confidence_avg'] * (total - 1) + confidence) / total

        # שמירת הקשר
        if context:
            if 'contexts' not in entry:
                entry['contexts'] = []
            entry['contexts'].append({
                **context,
                'user_category': user_category,
                'approved': approved,
                'timestamp': datetime.now().isoformat()
            })

        # עדכון סטטיסטיקות
        self.stats['total_corrections'] += 1
        if 'category_classifications' not in self.stats:
            self.stats['category_classifications'] = {
                'total': 0,
                'approved': 0,
                'rejected': 0,
                'by_category': {}
            }

        self.stats['category_classifications']['total'] += 1
        if approved:
            self.stats['category_classifications']['approved'] += 1
        else:
            self.stats['category_classifications']['rejected'] += 1

        # סטטיסטיקות לפי קטגוריה
        if auto_category not in self.stats['category_classifications']['by_category']:
            self.stats['category_classifications']['by_category'][auto_category] = {
                'total': 0, 'approved': 0, 'rejected': 0
            }
        cat_stats = self.stats['category_classifications']['by_category'][auto_category]
        cat_stats['total'] += 1
        if approved:
            cat_stats['approved'] += 1
        else:
            cat_stats['rejected'] += 1

        # לוג ושמירה
        self._log_correction('admin_category', auto_category, user_category, {
            'title': title[:200],
            'confidence': confidence,
            'approved': approved,
            **(context or {})
        })
        self.save()

    def get_category_classification_stats(self) -> Dict:
        """
        סטטיסטיקות סיווג מנהלתי

        Returns:
            dict עם סטטיסטיקות אישורים ודחיות לפי קטגוריה
        """
        if 'category_classifications' not in self.stats:
            return {
                'total': 0,
                'approved': 0,
                'rejected': 0,
                'approval_rate': 0.0,
                'by_category': {}
            }

        stats = self.stats['category_classifications']
        total = stats.get('total', 0)

        # חישוב שיעורי אישור לכל קטגוריה
        by_category_with_rates = {}
        for cat, cat_stats in stats.get('by_category', {}).items():
            cat_total = cat_stats.get('total', 0)
            cat_approved = cat_stats.get('approved', 0)
            by_category_with_rates[cat] = {
                **cat_stats,
                'approval_rate': cat_approved / cat_total if cat_total > 0 else 0.0
            }

        return {
            'total': total,
            'approved': stats.get('approved', 0),
            'rejected': stats.get('rejected', 0),
            'approval_rate': stats.get('approved', 0) / total if total > 0 else 0.0,
            'by_category': by_category_with_rates
        }

    def get_category_improvement_suggestions(self) -> List[str]:
        """
        המלצות לשיפור סיווג מנהלתי

        Returns:
            רשימת המלצות לשיפור
        """
        stats = self.get_category_classification_stats()
        suggestions = []

        if stats['total'] < 20:
            return ['נדרש יותר משוב כדי לספק המלצות לסיווג מנהלתי']

        # שיעור אישור כולל
        if stats['approval_rate'] < 0.6:
            suggestions.append(f"שיעור האישור הכולל נמוך ({stats['approval_rate']:.0%}) - שקול להוסיף מילות מפתח")

        # קטגוריות בעייתיות
        for cat, cat_stats in stats.get('by_category', {}).items():
            if cat_stats.get('total', 0) >= 5:
                rate = cat_stats.get('approval_rate', 0)
                if rate < 0.5:
                    suggestions.append(f"קטגוריה '{cat}' בעייתית ({rate:.0%} אישור) - בדוק מילות מפתח")

        # בדיקת קטגוריות שלא נבחרו
        if 'admin_categories' in self.corrections:
            user_corrections = defaultdict(int)
            for entry in self.corrections['admin_categories'].values():
                for user_cat, count in entry.get('user_corrections', {}).items():
                    user_corrections[user_cat] += count

            # קטגוריות שהמשתמשים בוחרים הרבה במקום האוטומטי
            for cat, count in sorted(user_corrections.items(), key=lambda x: x[1], reverse=True)[:3]:
                if count >= 3:
                    suggestions.append(f"המשתמשים בוחרים הרבה ב-'{cat}' - שקול להוסיף מילות מפתח עבורה")

        return suggestions

    def suggest_category_keywords(self, category_code: str) -> List[str]:
        """
        הצעת מילות מפתח חדשות לקטגוריה בהתבסס על כותרות שסווגו אליה ידנית

        Args:
            category_code: קוד הקטגוריה

        Returns:
            רשימת מילות מפתח מוצעות
        """
        if 'admin_categories' not in self.corrections:
            return []

        # איסוף כותרות שסווגו לקטגוריה זו ידנית
        titles = []
        for key, entry in self.corrections['admin_categories'].items():
            user_corrections = entry.get('user_corrections', {})
            if category_code in user_corrections and user_corrections[category_code] >= 1:
                titles.append(entry.get('title_sample', ''))

        if len(titles) < 2:
            return []

        # מציאת מילים נפוצות
        word_counts = defaultdict(int)
        for title in titles:
            words = re.findall(r'[\u0590-\u05FF]+', title)  # מילים בעברית
            for word in words:
                if len(word) >= 3:  # רק מילים של 3 תווים ומעלה
                    word_counts[word] += 1

        # החזרת מילים שמופיעות ביותר מכותרת אחת
        suggested = [word for word, count in word_counts.items() if count >= 2]
        return sorted(suggested, key=lambda w: word_counts[w], reverse=True)[:10]


# פונקציות עזר לשימוש מהמחברת

def get_learning_agent() -> OCRLearningAgent:
    """קבלת מופע של סוכן הלמידה"""
    return OCRLearningAgent()


def record_user_correction(field_type: str, ocr_value: str, user_value: str,
                          meeting_id: Optional[int] = None):
    """שמירת תיקון משתמש"""
    agent = get_learning_agent()
    context = {'meeting_id': meeting_id} if meeting_id else None
    agent.record_correction(field_type, ocr_value, user_value, context)


def get_auto_correction(text: str, field_type: str = 'word') -> Tuple[str, List[Dict]]:
    """קבלת תיקון אוטומטי"""
    agent = get_learning_agent()
    return agent.auto_correct(text, field_type)


def print_accuracy_report():
    """הדפסת דוח דיוק"""
    agent = get_learning_agent()
    report = agent.get_accuracy_report()

    print("=" * 50)
    print("דוח דיוק OCR")
    print("=" * 50)
    print(f"סה\"כ תיקונים: {report['total_corrections']}")
    print(f"תיקונים ידועים במערכת: {report['known_corrections_count']}")
    print()

    print("תיקונים לפי סוג שדה:")
    for field, count in report['corrections_by_field'].items():
        print(f"  {field}: {count}")
    print()

    if report['most_common_char_substitutions']:
        print("החלפות תווים נפוצות:")
        for sub, count in report['most_common_char_substitutions'][:5]:
            print(f"  {sub}: {count} פעמים")
    print()

    suggestions = agent.get_improvement_suggestions()
    if suggestions:
        print("המלצות לשיפור:")
        for s in suggestions:
            print(f"  - {s}")


if __name__ == '__main__':
    # דוגמה לשימוש
    agent = OCRLearningAgent()

    # רישום תיקונים לדוגמה
    agent.record_correction('name', 'מקלים', 'מקליס', {'meeting_id': 108})
    agent.record_correction('name', 'גנח', "ג'נח", {'meeting_id': 108})
    agent.record_correction('title', 'מועצת צעיר', 'מועצת העיר', {'meeting_id': 108})

    # הדפסת דוח
    print_accuracy_report()
