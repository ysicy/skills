import json
import yaml
from typing import Dict, Any, List, Optional
from pathlib import Path
from urllib.parse import urlparse

from .models import ParsedOpenAPI, Schema, SchemaField, Endpoint


class OpenAPIParser:
    """Парсер OpenAPI-спецификаций (v3.0, v3.1)."""

    TYPE_MAP = {
        "string": "str",
        "integer": "int",
        "number": "float",
        "boolean": "bool",
        "array": "List",
        "object": "Dict[str, Any]"
    }

    def __init__(
            self,
            source: str,
            headers: Optional[Dict[str, str]] = None,
            cert: Optional[str] = None,
            key: Optional[str] = None
    ):
        """
        Args:
            source: Путь к файлу или URL OpenAPI-спецификации
            headers: Опциональные кастомные заголовки запроса (например авторизация)
            cert: Путь к mTLS сертификату (.crt) для защищённых API
            key: Путь к mTLS ключу (.key) для защищённых API
        """
        self.source = source
        self.headers = headers or {}
        self.cert = (cert, key) if (cert and key) else None
        self.spec = self._load_spec()

    def _load_spec(self) -> Dict[str, Any]:
        """Загружает спецификацию из файла или URL."""
        if self._is_url(self.source):
            import requests
            session = requests.Session()

            # mTLS (опционально)
            if self.cert:
                session.cert = self.cert
                session.verify = False

            # Заголовки (опционально)
            if self.headers:
                session.headers.update(self.headers)

            response = session.get(self.source, timeout=30)
            response.raise_for_status()
            return response.json()

        path = Path(self.source)
        if not path.exists():
            raise FileNotFoundError(f"Файл не найден: {self.source}")

        with open(path, 'r', encoding='utf-8') as f:
            if path.suffix in ['.yaml', '.yml']:
                return yaml.safe_load(f)
            return json.load(f)

    @staticmethod
    def _is_url(source: str) -> bool:
        try:
            result = urlparse(source)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    def parse(self) -> ParsedOpenAPI:
        """Парсит спецификацию и возвращает структурированный результат."""
        info = self.spec.get('info', {})
        servers = self.spec.get('servers', [])
        base_path = servers[0].get('url', '') if servers else ''

        schemas = self._parse_schemas()
        endpoints = self._parse_endpoints()

        return ParsedOpenAPI(
            title=info.get('title', ''),
            version=info.get('version', ''),
            schemas=schemas,
            endpoints=endpoints,
            base_path=base_path
        )

    def _parse_schemas(self) -> List[Schema]:
        """Извлекает схемы из components/schemas."""
        schemas_data = self.spec.get('components', {}).get('schemas', {})
        schemas = []

        for name, schema_data in schemas_data.items():
            fields = self._parse_schema_fields(schema_data)
            schemas.append(Schema(
                name=name,
                fields=fields,
                description=schema_data.get('description', '')
            ))

        return schemas

    def _parse_schema_fields(self, schema_data: Dict[str, Any]) -> List[SchemaField]:
        """Парсит поля внутри схемы."""
        properties = schema_data.get('properties', {})
        required = schema_data.get('required', [])
        fields = []

        for field_name, field_data in properties.items():
            field_type = self._convert_type(field_data)
            is_required = field_name in required

            fields.append(SchemaField(
                name=field_name,
                type=field_type,
                is_required=is_required,
                description=field_data.get('description', ''),
            ))

        return fields

    def _convert_type(self, field_data: Dict[str, Any]) -> str:
        """Конвертирует OpenAPI-тип в Python/Pydantic-тип."""
        openapi_type = field_data.get('type', 'string')
        openapi_format = field_data.get('format', '')
        ref = field_data.get('$ref')

        # Если есть $ref — это ссылка на другую схему
        if ref:
            return self._extract_ref_name(ref)


        if openapi_format == 'date-time':
            return 'datetime'
        if openapi_format == 'uuid':
            return 'UUID'


        if openapi_type == 'array':
            items = field_data.get('items', {})
            if '$ref' in items:
                item_type = self._extract_ref_name(items['$ref'])
            else:
                item_type = self._convert_type(items)
            return f"List[{item_type}]"


        if openapi_type == 'object':
            return 'Dict[str, Any]'

        return self.TYPE_MAP.get(openapi_type, 'Any')

    @staticmethod
    def _extract_ref_name(ref: str) -> str:
        """Извлекает имя схемы из $ref."""
        return ref.split('/')[-1]

    def _parse_endpoints(self) -> List[Endpoint]:
        """Извлекает эндпоинты из paths."""
        paths = self.spec.get('paths', {})
        endpoints = []

        for path, methods in paths.items():
            for method, operation in methods.items():
                if method.lower() not in ['get', 'post', 'put', 'delete', 'patch']:
                    continue

                request_schema = self._extract_request_schema(operation)
                response_schema = self._extract_response_schema(operation)

                endpoints.append(Endpoint(
                    path=path,
                    method=method.upper(),
                    summary=operation.get('summary', ''),
                    description=operation.get('description', ''),
                    request_schema=request_schema,
                    response_schema=response_schema,
                    tags=operation.get('tags', [])
                ))

        return endpoints

    def _extract_request_schema(self, operation: Dict[str, Any]) -> Optional[str]:
        """Извлекает имя схемы запроса."""
        request_body = operation.get('requestBody', {})
        if not request_body:
            return None

        content = request_body.get('content', {})
        for media_type, media_data in content.items():
            if 'schema' in media_data:
                schema = media_data['schema']
                if '$ref' in schema:
                    return self._extract_ref_name(schema['$ref'])
        return None

    def _extract_response_schema(self, operation: Dict[str, Any]) -> Optional[str]:
        """Извлекает имя схемы ответа (статус 200)."""
        responses = operation.get('responses', {})
        response = responses.get('200', {})
        if not response:
            return None

        content = response.get('content', {})
        for media_type, media_data in content.items():
            if 'schema' in media_data:
                schema = media_data['schema']
                if '$ref' in schema:
                    return self._extract_ref_name(schema['$ref'])
        return None