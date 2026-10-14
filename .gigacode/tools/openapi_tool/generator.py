from typing import List, Dict, Any
from pathlib import Path

from .models import ParsedOpenAPI, Schema, SchemaField


class PydanticGenerator:
    """Генератор Pydantic-моделей из OpenAPI-схем."""

    def __init__(self, parsed: ParsedOpenAPI):
        self.parsed = parsed

    def generate(self) -> str:
        """Генерирует код Pydantic-моделей."""
        lines = [
            "from typing import Optional, List, Dict, Any",
            "from pydantic import BaseModel, Field",
            "from datetime import datetime",
            "",
            "",
            "# Сгенерировано из OpenAPI-спецификации",
            f"# Title: {self.parsed.title}",
            f"# Version: {self.parsed.version}",
            "",
        ]

        for schema in self.parsed.schemas:
            lines.extend(self._generate_schema(schema))
            lines.append("")

        return "\n".join(lines)

    def _generate_schema(self, schema: Schema) -> List[str]:
        """Генерирует код одной Pydantic-модели."""
        lines = []
        description = f'    """{schema.description}"""' if schema.description else ''
        lines.append(f"class {schema.name}(BaseModel):")
        if description:
            lines.append(description)

        if not schema.fields:
            lines.append("    pass")
            return lines

        for field in schema.fields:
            field_line = self._generate_field(field)
            lines.append(f"    {field_line}")

        lines.append("")
        return lines

    def _generate_field(self, field: SchemaField) -> str:
        """Генерирует код одного поля."""
        type_hint = field.type
        default = ""

        if not field.is_required:
            type_hint = f"Optional[{field.type}]"
            default = (
                f' = Field(default=None, description="{field.description}")'
                if field.description else " = None"
            )
        elif field.description:
            default = f' = Field(description="{field.description}")'

        return f"{field.name}: {type_hint}{default}"

    def save_to_file(self, output_path: str) -> str:
        """Сохраняет сгенерированные модели в файл."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        code = self.generate()
        with open(path, 'w', encoding='utf-8') as f:
            f.write(code)

        return str(path)