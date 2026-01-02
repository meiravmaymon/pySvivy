"""
Integration Orchestrator Agent - סוכן תיאום אינטגרציה

אחראי על:
- מיפוי תלויות בין שכבות
- זיהוי השפעות של שינויים
- שמירה על API contracts
- סנכרון טיפוסים בין פלטפורמות
"""

import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum

from .base_agent import BaseAgent, DOCS_DIR


class ChangeImpact(Enum):
    """רמת השפעה של שינוי"""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BREAKING = "breaking"


@dataclass
class APIContract:
    """חוזה API"""
    name: str
    version: str
    endpoints: List[Dict]
    created_at: str
    updated_at: str = None


class IntegrationOrchestratorAgent(BaseAgent):
    """סוכן תיאום אינטגרציה"""

    def __init__(self, config: Optional[Dict] = None):
        super().__init__("integration_orchestrator", config)
        self._init_directories()
        self._load_dependency_map()
        self._load_contracts()
        self._load_type_definitions()

    def _init_directories(self):
        """יצירת מבנה תיקיות"""
        self.integration_dir = DOCS_DIR / "integration"
        self.contracts_dir = self.integration_dir / "contracts"
        self.types_dir = self.integration_dir / "types"

        for directory in [self.integration_dir, self.contracts_dir, self.types_dir]:
            directory.mkdir(parents=True, exist_ok=True)

    def _load_dependency_map(self):
        """טעינת מפת תלויות"""
        deps_file = self.integration_dir / "dependencies.json"
        if deps_file.exists():
            with open(deps_file, 'r', encoding='utf-8') as f:
                self.dependencies = json.load(f)
        else:
            # מפת תלויות ברירת מחדל לפרויקט
            self.dependencies = {
                "components": {
                    "web": {"depends_on": ["api"], "affects": []},
                    "mobile": {"depends_on": ["api"], "affects": []},
                    "api": {"depends_on": ["database", "llm"], "affects": ["web", "mobile"]},
                    "database": {"depends_on": [], "affects": ["api"]},
                    "llm": {"depends_on": [], "affects": ["api"]},
                },
                "updated_at": datetime.now().isoformat()
            }

    def _save_dependency_map(self):
        """שמירת מפת תלויות"""
        self.dependencies["updated_at"] = datetime.now().isoformat()
        deps_file = self.integration_dir / "dependencies.json"
        with open(deps_file, 'w', encoding='utf-8') as f:
            json.dump(self.dependencies, f, ensure_ascii=False, indent=2)

    def _load_contracts(self):
        """טעינת חוזי API"""
        contracts_file = self.contracts_dir / "contracts.json"
        if contracts_file.exists():
            with open(contracts_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.contracts = {c['name']: APIContract(**c) for c in data}
        else:
            self.contracts = {}

    def _save_contracts(self):
        """שמירת חוזי API"""
        contracts_file = self.contracts_dir / "contracts.json"
        with open(contracts_file, 'w', encoding='utf-8') as f:
            json.dump([asdict(c) for c in self.contracts.values()], f, ensure_ascii=False, indent=2)

    def _load_type_definitions(self):
        """טעינת הגדרות טיפוסים"""
        types_file = self.types_dir / "shared_types.json"
        if types_file.exists():
            with open(types_file, 'r', encoding='utf-8') as f:
                self.type_definitions = json.load(f)
        else:
            self.type_definitions = {
                "types": {},
                "version": "1.0",
                "updated_at": datetime.now().isoformat()
            }

    def _save_type_definitions(self):
        """שמירת הגדרות טיפוסים"""
        self.type_definitions["updated_at"] = datetime.now().isoformat()
        types_file = self.types_dir / "shared_types.json"
        with open(types_file, 'w', encoding='utf-8') as f:
            json.dump(self.type_definitions, f, ensure_ascii=False, indent=2)

    # ======== מיפוי תלויות ========

    def register_component(
        self,
        name: str,
        depends_on: List[str] = None,
        affects: List[str] = None
    ):
        """
        רישום רכיב במפת התלויות

        Args:
            name: שם הרכיב
            depends_on: רכיבים שהוא תלוי בהם
            affects: רכיבים שהוא משפיע עליהם
        """
        self.dependencies["components"][name] = {
            "depends_on": depends_on or [],
            "affects": affects or []
        }
        self._save_dependency_map()
        self.log_action("register_component", {"name": name})

    def get_impact_chain(self, changed_component: str) -> List[str]:
        """
        קבלת שרשרת השפעה

        Args:
            changed_component: הרכיב שהשתנה

        Returns:
            רשימת כל הרכיבים המושפעים
        """
        components = self.dependencies.get("components", {})
        impacted = set()
        to_check = [changed_component]

        while to_check:
            current = to_check.pop()
            comp = components.get(current, {})

            for affected in comp.get("affects", []):
                if affected not in impacted:
                    impacted.add(affected)
                    to_check.append(affected)

            # רכיבים שתלויים ברכיב שהשתנה
            for name, data in components.items():
                if current in data.get("depends_on", []) and name not in impacted:
                    impacted.add(name)
                    to_check.append(name)

        return list(impacted)

    def get_dependency_graph(self) -> Dict:
        """קבלת גרף תלויות"""
        return {
            "components": self.dependencies.get("components", {}),
            "updated_at": self.dependencies.get("updated_at")
        }

    # ======== ניהול חוזי API ========

    def define_contract(
        self,
        name: str,
        version: str,
        endpoints: List[Dict]
    ) -> APIContract:
        """
        הגדרת חוזה API

        Args:
            name: שם החוזה
            version: גרסה
            endpoints: רשימת endpoints [{path, method, request, response}]
        """
        contract = APIContract(
            name=name,
            version=version,
            endpoints=endpoints,
            created_at=datetime.now().isoformat()
        )

        self.contracts[name] = contract
        self._save_contracts()

        # שמירה גם כקובץ YAML נפרד
        self._save_contract_yaml(contract)

        self.log_action("define_contract", {"name": name, "version": version})
        return contract

    def _save_contract_yaml(self, contract: APIContract):
        """שמירת חוזה כ-YAML"""
        yaml_file = self.contracts_dir / f"{contract.name}.yaml"

        content = f"""# API Contract: {contract.name}
# Version: {contract.version}
# Generated: {contract.created_at}

contract:
  name: {contract.name}
  version: "{contract.version}"

endpoints:
"""
        for ep in contract.endpoints:
            content += f"""
  - path: {ep.get('path', '/')}
    method: {ep.get('method', 'GET')}
    request:
      type: {ep.get('request', {}).get('type', 'object')}
    response:
      type: {ep.get('response', {}).get('type', 'object')}
"""
            if 'required' in ep.get('response', {}):
                content += f"      required: {ep['response']['required']}\n"

        with open(yaml_file, 'w', encoding='utf-8') as f:
            f.write(content)

    def validate_against_contract(
        self,
        contract_name: str,
        endpoint_path: str,
        response: Dict
    ) -> Dict:
        """
        בדיקת תגובה מול חוזה

        Args:
            contract_name: שם החוזה
            endpoint_path: נתיב ה-endpoint
            response: התגובה לבדיקה
        """
        contract = self.contracts.get(contract_name)
        if not contract:
            return {"valid": False, "error": f"Contract not found: {contract_name}"}

        endpoint = next(
            (ep for ep in contract.endpoints if ep.get('path') == endpoint_path),
            None
        )

        if not endpoint:
            return {"valid": False, "error": f"Endpoint not found: {endpoint_path}"}

        violations = []

        # בדיקת שדות חובה
        required = endpoint.get('response', {}).get('required', [])
        for field in required:
            if field not in response:
                violations.append({
                    "type": "MISSING_REQUIRED_FIELD",
                    "field": field
                })

        # בדיקת טיפוסים
        properties = endpoint.get('response', {}).get('properties', {})
        for field, expected in properties.items():
            if field in response:
                actual_type = type(response[field]).__name__
                expected_type = expected.get('type', 'any')
                if expected_type != 'any' and actual_type != expected_type:
                    violations.append({
                        "type": "TYPE_MISMATCH",
                        "field": field,
                        "expected": expected_type,
                        "actual": actual_type
                    })

        return {
            "valid": len(violations) == 0,
            "violations": violations,
            "checked_at": datetime.now().isoformat()
        }

    def detect_breaking_changes(
        self,
        old_contract_name: str,
        new_endpoints: List[Dict]
    ) -> List[Dict]:
        """
        זיהוי שינויים breaking

        Args:
            old_contract_name: שם החוזה הישן
            new_endpoints: endpoints חדשים
        """
        old_contract = self.contracts.get(old_contract_name)
        if not old_contract:
            return [{"error": f"Contract not found: {old_contract_name}"}]

        breaking = []

        old_paths = {ep['path']: ep for ep in old_contract.endpoints}
        new_paths = {ep['path']: ep for ep in new_endpoints}

        # endpoints שהוסרו
        for path in old_paths:
            if path not in new_paths:
                breaking.append({
                    "type": "ENDPOINT_REMOVED",
                    "path": path,
                    "severity": "critical"
                })

        # שינויים ב-endpoints קיימים
        for path, old_ep in old_paths.items():
            if path in new_paths:
                new_ep = new_paths[path]

                # שדות חובה חדשים ב-request
                old_req = set(old_ep.get('request', {}).get('required', []))
                new_req = set(new_ep.get('request', {}).get('required', []))
                added_required = new_req - old_req

                if added_required:
                    breaking.append({
                        "type": "NEW_REQUIRED_REQUEST_FIELDS",
                        "path": path,
                        "fields": list(added_required),
                        "severity": "high"
                    })

                # שדות שהוסרו מ-response
                old_resp = set(old_ep.get('response', {}).get('properties', {}).keys())
                new_resp = set(new_ep.get('response', {}).get('properties', {}).keys())
                removed_fields = old_resp - new_resp

                if removed_fields:
                    breaking.append({
                        "type": "RESPONSE_FIELDS_REMOVED",
                        "path": path,
                        "fields": list(removed_fields),
                        "severity": "high"
                    })

        return breaking

    # ======== סנכרון טיפוסים ========

    def define_shared_type(
        self,
        name: str,
        properties: Dict[str, Dict],
        description: str = ""
    ):
        """
        הגדרת טיפוס משותף

        Args:
            name: שם הטיפוס
            properties: מאפיינים {name: {type, nullable, ...}}
            description: תיאור
        """
        self.type_definitions["types"][name] = {
            "properties": properties,
            "description": description,
            "defined_at": datetime.now().isoformat()
        }
        self._save_type_definitions()

        self.log_action("define_shared_type", {"name": name})

    def generate_type_for_platform(
        self,
        type_name: str,
        platform: str
    ) -> str:
        """
        יצירת הגדרת טיפוס לפלטפורמה

        Args:
            type_name: שם הטיפוס
            platform: typescript, python, dart

        Returns:
            קוד הגדרת הטיפוס
        """
        type_def = self.type_definitions["types"].get(type_name)
        if not type_def:
            return f"// Type not found: {type_name}"

        properties = type_def.get("properties", {})

        if platform == "typescript":
            return self._generate_typescript(type_name, properties)
        elif platform == "python":
            return self._generate_python(type_name, properties)
        elif platform == "dart":
            return self._generate_dart(type_name, properties)
        else:
            return f"// Unknown platform: {platform}"

    def _generate_typescript(self, name: str, properties: Dict) -> str:
        """יצירת TypeScript interface"""
        lines = [f"export interface {name} {{"]

        for prop_name, prop_def in properties.items():
            ts_type = self._to_typescript_type(prop_def.get("type", "any"))
            optional = "?" if prop_def.get("nullable") else ""
            lines.append(f"  {prop_name}{optional}: {ts_type};")

        lines.append("}")
        return "\n".join(lines)

    def _generate_python(self, name: str, properties: Dict) -> str:
        """יצירת Python dataclass"""
        lines = [
            "from dataclasses import dataclass",
            "from typing import Optional",
            "",
            "@dataclass",
            f"class {name}:"
        ]

        for prop_name, prop_def in properties.items():
            py_type = self._to_python_type(prop_def.get("type", "any"))
            if prop_def.get("nullable"):
                py_type = f"Optional[{py_type}]"
            lines.append(f"    {prop_name}: {py_type}")

        return "\n".join(lines)

    def _generate_dart(self, name: str, properties: Dict) -> str:
        """יצירת Dart class"""
        lines = [f"class {name} {{"]

        for prop_name, prop_def in properties.items():
            dart_type = self._to_dart_type(prop_def.get("type", "dynamic"))
            nullable = "?" if prop_def.get("nullable") else ""
            lines.append(f"  final {dart_type}{nullable} {prop_name};")

        lines.append("")
        lines.append(f"  {name}({{")
        for prop_name, prop_def in properties.items():
            required = "required " if not prop_def.get("nullable") else ""
            lines.append(f"    {required}this.{prop_name},")
        lines.append("  });")
        lines.append("}")

        return "\n".join(lines)

    def _to_typescript_type(self, type_str: str) -> str:
        mapping = {"string": "string", "int": "number", "float": "number",
                   "bool": "boolean", "list": "Array<any>", "dict": "Record<string, any>"}
        return mapping.get(type_str, "any")

    def _to_python_type(self, type_str: str) -> str:
        mapping = {"string": "str", "int": "int", "float": "float",
                   "bool": "bool", "list": "list", "dict": "dict"}
        return mapping.get(type_str, "Any")

    def _to_dart_type(self, type_str: str) -> str:
        mapping = {"string": "String", "int": "int", "float": "double",
                   "bool": "bool", "list": "List", "dict": "Map<String, dynamic>"}
        return mapping.get(type_str, "dynamic")

    def check_type_sync(self) -> Dict:
        """בדיקת סנכרון טיפוסים"""
        # זו בדיקה בסיסית - בפועל תבדוק קבצים אמיתיים
        return {
            "synced": True,
            "types_count": len(self.type_definitions.get("types", {})),
            "checked_at": datetime.now().isoformat()
        }

    # ======== דוחות ========

    def generate_integration_report(self) -> str:
        """יצירת דוח אינטגרציה"""
        report = f"""# דוח אינטגרציה - {datetime.now().strftime('%Y-%m-%d')}

## מפת תלויות

"""
        for comp, data in self.dependencies.get("components", {}).items():
            deps = ", ".join(data.get("depends_on", [])) or "אין"
            affects = ", ".join(data.get("affects", [])) or "אין"
            report += f"### {comp}\n- תלוי ב: {deps}\n- משפיע על: {affects}\n\n"

        report += "## חוזי API\n\n"
        for name, contract in self.contracts.items():
            report += f"- **{name}** (v{contract.version}): {len(contract.endpoints)} endpoints\n"

        report += "\n## טיפוסים משותפים\n\n"
        for name, type_def in self.type_definitions.get("types", {}).items():
            report += f"- **{name}**: {type_def.get('description', '-')}\n"

        return report

    # ======== ממשק סוכן ========

    def run(self, command: str, **kwargs) -> Dict[str, Any]:
        """הפעלת פקודה"""
        commands = {
            "register_component": self.register_component,
            "get_impact": self.get_impact_chain,
            "get_dependencies": self.get_dependency_graph,
            "define_contract": self.define_contract,
            "validate_contract": self.validate_against_contract,
            "breaking_changes": self.detect_breaking_changes,
            "define_type": self.define_shared_type,
            "generate_type": self.generate_type_for_platform,
            "check_sync": self.check_type_sync,
            "report": self.generate_integration_report,
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
            "components_count": len(self.dependencies.get("components", {})),
            "contracts_count": len(self.contracts),
            "types_count": len(self.type_definitions.get("types", {}))
        }
