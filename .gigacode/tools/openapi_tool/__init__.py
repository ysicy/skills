"""
OpenAPI Tool — парсинг OpenAPI спецификаций и генерация Pydantic-моделей.
"""

from .main import parse_openapi, parse_openapi_from_url
from .models import ParsedOpenAPI, Endpoint, SchemaField

__all__ = [
    "parse_openapi",
    "parse_openapi_from_url",
    "ParsedOpenAPI",
    "Endpoint",
    "SchemaField"
]