import json
import keyword
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import yaml

from .models import Endpoint, Parameter, ParsedOpenAPI, Schema, SchemaField

HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}


def to_class_name(name: str) -> str:
    """Имя схемы → допустимое имя Python-класса (Book.Response → Book_Response)."""
    cleaned = re.sub(r"\W", "_", name)
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"Model_{cleaned}"
    if keyword.iskeyword(cleaned):
        cleaned = f"{cleaned}_"
    return cleaned


class OpenAPIParser:
    """Парсер OpenAPI-спецификаций (v3.0, v3.1)."""

    TYPE_MAP = {
        "string": "str",
        "integer": "int",
        "number": "float",
        "boolean": "bool",
        "array": "List[Any]",
        "object": "Dict[str, Any]",
    }
    FORMAT_MAP = {"date-time": "datetime", "date": "date", "uuid": "UUID"}

    def __init__(
            self,
            source: str,
    ):
        """
        Args:
            source: путь к локальному файлу спецификации (.json/.yaml).
                Сеть инструмент не использует: спецификацию по ссылке
                сначала сохраняют в файл.
        """
        self.source = source
        self.spec = self._load_spec()
        self._schemas_raw: Dict[str, Any] = self.spec.get("components", {}).get("schemas", {}) or {}
        self._class_names = self._build_class_names()

    # ------------------------------------------------------------------
    # Загрузка
    # ------------------------------------------------------------------
    def _load_spec(self) -> Dict[str, Any]:
        if self._is_url(self.source):
            raise ValueError(
                "openapi_tool читает только локальные файлы: сохрани спецификацию "
                f"по ссылке {self.source} в файл и передай путь к нему"
            )

        path = Path(self.source)
        if not path.exists():
            raise FileNotFoundError(f"Файл не найден: {self.source}")
        with open(path, "r", encoding="utf-8") as f:
            if path.suffix in (".yaml", ".yml"):
                return yaml.safe_load(f)
            return json.load(f)

    @staticmethod
    def _is_url(source: str) -> bool:
        try:
            result = urlparse(source)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Имена и ссылки
    # ------------------------------------------------------------------
    def _build_class_names(self) -> Dict[str, str]:
        """Уникальные имена классов для всех схем."""
        names: Dict[str, str] = {}
        used = set()
        for raw in self._schemas_raw:
            candidate = to_class_name(raw)
            base, n = candidate, 2
            while candidate in used:
                candidate = f"{base}_{n}"
                n += 1
            used.add(candidate)
            names[raw] = candidate
        return names

    @staticmethod
    def _ref_name(ref: str) -> str:
        return ref.split("/")[-1]

    def _ref_class(self, ref: str) -> str:
        raw = self._ref_name(ref)
        return self._class_names.get(raw, to_class_name(raw))

    def _resolve(self, obj: Dict[str, Any]) -> Dict[str, Any]:
        """Разворачивает $ref на компонент (parameters, schemas, responses...)."""
        seen = 0
        while isinstance(obj, dict) and "$ref" in obj and seen < 20:
            parts = obj["$ref"].lstrip("#/").split("/")
            target: Any = self.spec
            for part in parts:
                target = target.get(part, {}) if isinstance(target, dict) else {}
            obj = target
            seen += 1
        return obj if isinstance(obj, dict) else {}

    # ------------------------------------------------------------------
    # Типы
    # ------------------------------------------------------------------
    def _convert_type(self, data: Dict[str, Any]) -> Tuple[str, bool]:
        """OpenAPI-схема поля → (Python-тип без Optional, допускает ли null)."""
        if not isinstance(data, dict) or not data:
            return "Any", False

        nullable = bool(data.get("nullable", False))

        if "$ref" in data:
            return self._ref_class(data["$ref"]), nullable

        for combo in ("oneOf", "anyOf"):
            if combo in data:
                types: List[str] = []
                for member in data[combo]:
                    if isinstance(member, dict) and member.get("type") == "null":
                        nullable = True
                        continue
                    t, member_null = self._convert_type(member)
                    nullable = nullable or member_null
                    if t not in types:
                        types.append(t)
                if not types:
                    return "Any", True
                if len(types) == 1:
                    return types[0], nullable
                return f"Union[{', '.join(types)}]", nullable

        if "allOf" in data:
            parts = data["allOf"]
            refs = [p for p in parts if isinstance(p, dict) and "$ref" in p]
            if len(parts) == 1 or (len(refs) == 1 and all("$ref" in p or "properties" not in p for p in parts)):
                t, member_null = self._convert_type(refs[0] if refs else parts[0])
                return t, nullable or member_null
            return "Dict[str, Any]", nullable

        openapi_type = data.get("type")
        if isinstance(openapi_type, list):  # OpenAPI 3.1: type: [string, "null"]
            non_null = [t for t in openapi_type if t != "null"]
            nullable = nullable or "null" in openapi_type
            if not non_null:
                return "Any", True
            if len(non_null) > 1:
                return f"Union[{', '.join(self.TYPE_MAP.get(t, 'Any') for t in non_null)}]", nullable
            openapi_type = non_null[0]

        fmt = data.get("format", "")
        if openapi_type == "string" and fmt in self.FORMAT_MAP:
            return self.FORMAT_MAP[fmt], nullable

        if openapi_type == "array":
            item_type, _ = self._convert_type(data.get("items", {}))
            return f"List[{item_type}]", nullable

        if openapi_type == "object" or (openapi_type is None and "properties" in data):
            extra = data.get("additionalProperties")
            if isinstance(extra, dict) and extra:
                value_type, _ = self._convert_type(extra)
                return f"Dict[str, {value_type}]", nullable
            return "Dict[str, Any]", nullable

        if openapi_type is None:
            return "Any", nullable
        return self.TYPE_MAP.get(openapi_type, "Any"), nullable

    # ------------------------------------------------------------------
    # Схемы
    # ------------------------------------------------------------------
    def parse(self) -> ParsedOpenAPI:
        info = self.spec.get("info", {})
        servers = self.spec.get("servers", [])
        base_path = servers[0].get("url", "") if servers else ""
        return ParsedOpenAPI(
            title=info.get("title", ""),
            version=str(info.get("version", "")),
            schemas=self._parse_schemas(),
            endpoints=self._parse_endpoints(),
            base_path=base_path,
        )

    def _collect_properties(self, data: Dict[str, Any], depth: int = 0) -> Tuple[Dict[str, Any], List[str]]:
        """Свойства и обязательные поля схемы с учётом allOf (наследование)."""
        if depth > 20:
            return {}, []
        props: Dict[str, Any] = {}
        required: List[str] = []
        for part in data.get("allOf", []):
            part_data = self._resolve(part) if "$ref" in part else part
            p, r = self._collect_properties(part_data, depth + 1)
            props.update(p)
            required.extend(r)
        props.update(data.get("properties", {}) or {})
        required.extend(data.get("required", []) or [])
        return props, required

    def _is_model(self, data: Dict[str, Any]) -> bool:
        """Объект со свойствами (в т.ч. через allOf) → класс; иначе псевдоним типа."""
        if data.get("properties"):
            return True
        parts = data.get("allOf") or []
        if len(parts) > 1:
            return True
        if len(parts) == 1 and "$ref" not in parts[0]:
            return self._is_model(parts[0])
        return False

    def _parse_schemas(self) -> List[Schema]:
        schemas = []
        for raw_name, data in self._schemas_raw.items():
            data = data or {}
            class_name = self._class_names[raw_name]
            if self._is_model(data):
                props, required = self._collect_properties(data)
                fields = []
                for field_name, field_data in props.items():
                    field_data = field_data or {}
                    field_type, nullable = self._convert_type(field_data)
                    fields.append(SchemaField(
                        name=field_name,
                        type=field_type,
                        is_required=field_name in required,
                        nullable=nullable,
                        description=field_data.get("description", "") or "",
                        default=field_data.get("default"),
                        enum=field_data.get("enum"),
                    ))
                schemas.append(Schema(name=class_name, fields=fields,
                                      description=data.get("description", "") or ""))
            else:
                alias_type, nullable = self._convert_type(data)
                if nullable:
                    alias_type = f"Optional[{alias_type}]"
                schemas.append(Schema(name=class_name, fields=[], kind="alias", alias_type=alias_type,
                                      description=data.get("description", "") or "", enum=data.get("enum")))
        return schemas

    # ------------------------------------------------------------------
    # Эндпоинты
    # ------------------------------------------------------------------
    def _parse_parameters(self, path_item: Dict[str, Any], operation: Dict[str, Any]) -> List[Parameter]:
        merged: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for raw in (path_item.get("parameters", []) or []) + (operation.get("parameters", []) or []):
            p = self._resolve(raw) if "$ref" in raw else raw
            if p.get("name"):
                merged[(p["name"], p.get("in", ""))] = p
        result = []
        for (name, location), p in merged.items():
            schema = p.get("schema", {}) or {}
            p_type, _ = self._convert_type(schema)
            result.append(Parameter(
                name=name, location=location,
                required=bool(p.get("required", location == "path")),
                type=p_type, enum=schema.get("enum"),
            ))
        return result

    def _content_schema(self, content: Dict[str, Any]) -> Optional[str]:
        for media in (content or {}).values():
            schema = (media or {}).get("schema")
            if schema:
                t, nullable = self._convert_type(schema)
                return t
        return None

    def _parse_endpoints(self) -> List[Endpoint]:
        endpoints = []
        for path, path_item in (self.spec.get("paths", {}) or {}).items():
            path_item = path_item or {}
            for method, operation in path_item.items():
                if method.lower() not in HTTP_METHODS or not isinstance(operation, dict):
                    continue
                request_body = self._resolve(operation.get("requestBody", {}) or {})
                responses = operation.get("responses", {}) or {}
                response_schema = None
                for code in sorted(responses, key=str):
                    if str(code).startswith("2"):
                        response_schema = self._content_schema(self._resolve(responses[code] or {}).get("content", {}))
                        if response_schema:
                            break
                endpoints.append(Endpoint(
                    path=path,
                    method=method.upper(),
                    summary=operation.get("summary", "") or "",
                    description=operation.get("description", "") or "",
                    request_schema=self._content_schema(request_body.get("content", {})),
                    response_schema=response_schema,
                    responses=[str(c) for c in responses],
                    parameters=self._parse_parameters(path_item, operation),
                    tags=operation.get("tags", []) or [],
                ))
        return endpoints
