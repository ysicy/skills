"""Генерация моделей из недоверенной OpenAPI-спецификации не должна давать исполняемый код.

Запуск из каталога tools/:  python -m unittest discover -s tests
"""

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openapi_tool.generator import PydanticGenerator, validate_generated  # noqa: E402
from openapi_tool.parser import OpenAPIParser  # noqa: E402

PAYLOAD = 'x"""\nimport os\nos.system("echo pwned")\n#'


def malicious_spec() -> dict:
    return {
        "openapi": "3.0.0",
        "info": {"title": "API\nimport os\nos.system('echo pwned')", "version": "1\r\n__import__('os')"},
        "paths": {},
        "components": {
            "schemas": {
                "User": {
                    "type": "object",
                    "description": PAYLOAD,
                    "properties": {
                        "id": {"type": "integer", "description": PAYLOAD},
                        "name\nimport os": {"type": "string"},
                        "role": {"type": "string", "enum": ["a\nimport os", PAYLOAD]},
                    },
                },
                "Role\nimport os": {"type": "string", "enum": ["x\nos.system('id')"], "description": PAYLOAD},
                "Tags": {"type": "array", "items": {"$ref": "#/components/schemas/User"}, "description": PAYLOAD},
            }
        },
    }


def generate(spec: dict) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "spec.json"
        path.write_text(json.dumps(spec), encoding="utf-8")
        return PydanticGenerator(OpenAPIParser(str(path)).parse()).generate()


class MaliciousSpecTest(unittest.TestCase):
    def test_generated_code_has_no_injected_statements(self):
        code = generate(malicious_spec())
        tree = ast.parse(code)
        imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
        self.assertTrue(all(isinstance(n, ast.ImportFrom) for n in imports))
        self.assertNotIn("os", {a.name for n in imports for a in n.names})
        calls = {getattr(n.func, "attr", getattr(n.func, "id", "")) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        self.assertLessEqual(calls, {"Field", "ConfigDict", "model_rebuild"})

    def test_every_comment_line_stays_a_comment(self):
        code = generate(malicious_spec())
        for line in code.splitlines():
            if "import os" in line or "os.system" in line:
                stripped = line.strip()
                self.assertTrue(stripped.startswith("#") or "'" in stripped or '"' in stripped, line)


class ValidatorTest(unittest.TestCase):
    def test_rejects_executable_code(self):
        for code in (
            "import os\n",
            "from x import y\nos.system('id')\n",
            "class A:\n    def f(self):\n        pass\n",
            "class A:\n    x: int = __import__('os')\n",
        ):
            with self.subTest(code=code):
                with self.assertRaises(ValueError):
                    validate_generated(code)

    def test_accepts_regular_models(self):
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "t", "version": "1"},
            "paths": {},
            "components": {"schemas": {"User": {"type": "object", "properties": {"id": {"type": "integer"}}}}},
        }
        validate_generated(generate(spec))


if __name__ == "__main__":
    unittest.main()
