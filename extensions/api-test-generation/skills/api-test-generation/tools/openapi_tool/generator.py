import keyword
import re
from pathlib import Path
from typing import Dict, List

from .models import ParsedOpenAPI, Schema, SchemaField

HEADER = '''from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
'''


def to_field_name(name: str) -> str:
    """Имя поля JSON → допустимый идентификатор Python (from → from_, x-request-id → x_request_id)."""
    cleaned = re.sub(r"\W", "_", name)
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"field_{cleaned}"
    if keyword.iskeyword(cleaned) or cleaned in {"model_config", "model_fields", "schema", "json", "dict", "copy"}:
        cleaned = f"{cleaned}_"
    return cleaned


def _referenced_names(type_str: str, known: set) -> set:
    return {tok for tok in re.findall(r"[A-Za-z_]\w*", type_str) if tok in known}


class PydanticGenerator:
    """Генератор Pydantic-моделей (v2) из разобранной спецификации."""

    def __init__(self, parsed: ParsedOpenAPI):
        self.parsed = parsed

    def generate(self) -> str:
        models = [s for s in self.parsed.schemas if s.kind == "model"]
        aliases = [s for s in self.parsed.schemas if s.kind == "alias"]

        lines = [
            HEADER,
            "",
            "# Сгенерировано из OpenAPI-спецификации",
            f"# Title: {self.parsed.title}",
            f"# Version: {self.parsed.version}",
            "",
        ]
        for schema in models:
            lines.extend(self._generate_model(schema))

        if aliases:
            lines.append("")
            lines.append("# Схемы, не являющиеся объектами (массивы, перечисления, oneOf)")
            for schema in self._order_aliases(aliases):
                if schema.description:
                    lines.append(f"# {self._one_line(schema.description)}")
                if schema.enum:
                    lines.append(f"# enum: {schema.enum!r}")
                lines.append(f"{schema.name} = {schema.alias_type}")
            lines.append("")

        if models:
            lines.append("")
            lines.append("# Ссылки между моделями (в т.ч. вперёд по файлу) разрешаются здесь")
            for schema in models:
                lines.append(f"{schema.name}.model_rebuild()")
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _one_line(text: str) -> str:
        return " ".join(str(text).split())

    def _order_aliases(self, aliases: List[Schema]) -> List[Schema]:
        """Псевдонимы вычисляются сразу, поэтому сортируем их по зависимостям друг от друга."""
        alias_names = {a.name for a in aliases}
        deps: Dict[str, set] = {a.name: _referenced_names(a.alias_type or "", alias_names) - {a.name} for a in aliases}
        ordered, done = [], set()
        pending = list(aliases)
        while pending:
            progressed = False
            for a in list(pending):
                if deps[a.name] <= done:
                    ordered.append(a)
                    done.add(a.name)
                    pending.remove(a)
                    progressed = True
            if not progressed:  # циклическая зависимость — оставляем как есть
                ordered.extend(pending)
                break
        return ordered

    def _generate_model(self, schema: Schema) -> List[str]:
        lines = ["", f"class {schema.name}(BaseModel):"]
        if schema.description:
            lines.append(f"    {self._one_line(schema.description)!r}")
            lines.append("")
        lines.append("    model_config = ConfigDict(populate_by_name=True)")
        used = set()
        for field in schema.fields:
            lines.append(f"    {self._generate_field(field, used)}")
        lines.append("")
        return lines

    def _generate_field(self, field: SchemaField, used: set) -> str:
        py_name = to_field_name(field.name)
        base, n = py_name, 2
        while py_name in used:
            py_name = f"{base}_{n}"
            n += 1
        used.add(py_name)

        type_hint = field.type
        optional = field.nullable or not field.is_required
        if optional and not type_hint.startswith("Optional["):
            type_hint = f"Optional[{type_hint}]"

        args = []
        if not field.is_required:
            args.append("default=None")
        if py_name != field.name:
            args.append(f"alias={field.name!r}")
        if field.description:
            args.append(f"description={self._one_line(field.description)!r}")

        line = f"{py_name}: {type_hint}"
        if args:
            line += f" = Field({', '.join(args)})"
        if field.enum:
            line += f"  # enum: {field.enum!r}"
        return line

    def save_to_file(self, output_path: str) -> str:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.generate(), encoding="utf-8")
        return str(path)
