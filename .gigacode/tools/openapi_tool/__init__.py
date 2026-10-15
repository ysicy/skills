"""
OpenAPI Tool — парсинг OpenAPI-спецификаций и генерация Pydantic-моделей.

Запуск из корня проекта:
    python .gigacode/tools/openapi_tool/main.py <spec_path_or_url> <output_dir>
"""

from .models import Endpoint, ParsedOpenAPI, SchemaField

__all__ = ["parse_openapi", "parse_openapi_from_url", "ParsedOpenAPI", "Endpoint", "SchemaField"]


def __getattr__(name):
    # Ленивый импорт: пакет не тянет main при загрузке, поэтому `python -m openapi_tool.main`
    # и запуск main.py как скрипта не дают предупреждения о двойном импорте.
    if name in ("parse_openapi", "parse_openapi_from_url"):
        from . import main
        return getattr(main, name)
    raise AttributeError(name)
