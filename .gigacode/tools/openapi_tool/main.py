"""
Основной модуль OpenAPI Tool.
"""
from typing import Dict, Any, Optional, Set
from pathlib import Path

from .parser import OpenAPIParser
from .generator import PydanticGenerator
from .models import ParsedOpenAPI


def _read_existing_schemas(test_root: str) -> Set[str]:
    """
    Читает существующие Pydantic-модели из <test_root>/models/
    и возвращает набор имён классов.
    """
    existing = set()
    models_path = Path(test_root) / "models"
    if not models_path.exists():
        return existing

    for py_file in models_path.glob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("class ") and "BaseModel" in line:
                    class_name = line.split("(")[0].replace("class ", "")
                    existing.add(class_name)
        except Exception:
            continue

    return existing


def _check_duplicate_schemas(
        new_schemas: list,
        output_dir: str,
        test_root: str
) -> Dict[str, Any]:
    """
    Проверяет, какие DTO уже существуют в проекте.

    Args:
        new_schemas: список Schema из OpenAPI
        output_dir: целевая директория
        test_root: корень тестового дерева

    Returns:
        Dict с классификацией:
        {
            "existing": ["User", "Order"],  # уже есть в коде
            "new": ["Address"],              # новых не было
            "duplicates_detected": True/False,
            "recommendation": "..."
        }
    """
    existing = _read_existing_schemas(test_root)

    existing_schemas = []
    new_schemas_list = []

    for schema in new_schemas:
        if schema.name in existing:
            existing_schemas.append(schema.name)
        else:
            new_schemas_list.append(schema.name)

    return {
        "existing": existing_schemas,
        "new": new_schemas_list,
        "duplicates_detected": len(existing_schemas) > 0,
        "recommendation": (
            f"Найдены дублирующиеся DTO: {existing_schemas}. "
            f"Используй duplicate_action='skip' для пропуска или 'merge' для объединения."
        ) if existing_schemas else "Дубликатов не найдено, все DTO новые."
    }


def parse_openapi(
        source: str,
        output_dir: Optional[str] = None,
        output_filename: str = "openapi_models.py",
        headers: Optional[Dict[str, str]] = None,
        cert: Optional[str] = None,
        key: Optional[str] = None,
        check_duplicates: bool = True,
        duplicate_action: str = "warn"
) -> Dict[str, Any]:
    """
    Парсит OpenAPI-спецификацию и генерирует Pydantic-модели.

    Args:
        source: Путь к файлу или URL OpenAPI-спецификации
        output_dir: Директория для сохранения моделей (по умолчанию: None — спросить у пользователя или взять из code-patterns.json)
        output_filename: Имя файла с моделями
        headers: Опциональные кастомные заголовки запроса (например авторизация)
        cert: Путь к mTLS сертификату (.crt) для защищённых API
        key: Путь к mTLS ключу (.key) для защищённых API
        check_duplicates: Если True — проверит существующие DTO перед генерацией (по умолчанию True)
        duplicate_action: Действие при обнаружении дубликатов:
            - "warn" (по умолчанию) — только предупреждение, генерирует все DTO
            - "skip" — пропускает существующие DTO, генерирует только новые

    Returns:
        Dict с результатами:
        {
            "schemas": ["User", "Order", ...],
            "endpoints": [...],
            "output_file": "<test_root>/models/openapi_models.py",
            "duplicate_check": {...}  # если check_duplicates=True
        }
    """

    parser = OpenAPIParser(source, headers=headers, cert=cert, key=key)
    parsed = parser.parse()

    # Проверка дубликатов DTO
    duplicate_result = None
    if check_duplicates and output_dir:
        duplicate_result = _check_duplicate_schemas(
            parsed.schemas, output_dir, test_root=output_dir
        )
        if duplicate_result.get("duplicates_detected"):
            if duplicate_action == "warn":
                print(f"⚠️  Обнаружены дублирующиеся DTO:")
                for schema_name in duplicate_result["existing"]:
                    print(f"   - {schema_name} (уже существует)")
                print(f"💡 {duplicate_result['recommendation']}")
            elif duplicate_action == "skip":
                print(f"⏭️  Пропускаем существующие DTO: {duplicate_result['existing']}")
                print(f"✅ Генерируем только новые: {duplicate_result['new']}")
                # Фильтруем схемы — оставляем только новые
                existing_names = set(duplicate_result["existing"])
                parsed.schemas = [s for s in parsed.schemas if s.name not in existing_names]
                duplicate_result["skipped"] = duplicate_result.pop("existing")
                duplicate_result["generated"] = duplicate_result.pop("new")

    generator = PydanticGenerator(parsed)
    output_path = Path(output_dir) / output_filename
    saved_path = generator.save_to_file(str(output_path))

    result = {
        "title": parsed.title,
        "version": parsed.version,
        "base_path": parsed.base_path,
        "schemas": [s.name for s in parsed.schemas],
        "endpoints": [
            {
                "path": e.path,
                "method": e.method,
                "request_schema": e.request_schema,
                "response_schema": e.response_schema
            }
            for e in parsed.endpoints
        ],
        "output_file": saved_path
    }

    if duplicate_result is not None:
        result["duplicate_check"] = duplicate_result

    return result


def parse_openapi_from_url(
        url: str,
        output_dir: Optional[str] = None,
        output_filename: str = "openapi_models.py",
        headers: Optional[Dict[str, str]] = None,
        cert: Optional[str] = None,
        key: Optional[str] = None
) -> Dict[str, Any]:
    """Парсит OpenAPI по URL."""
    return parse_openapi(url, output_dir, output_filename, headers=headers, cert=cert, key=key)


def parse_openapi_from_file(
        filepath: str,
        output_dir: Optional[str] = None,
        output_filename: str = "openapi_models.py"
) -> Dict[str, Any]:
    """Парсит OpenAPI из файла."""
    return parse_openapi(filepath, output_dir, output_filename)


def _resolve_test_root() -> Optional[str]:
    """
    Определяет корень тестового дерева из кэша .gigacode/design/code-patterns.json.

    Если кэша нет или поле отсутствует — возвращает None (вызывающий решает).
    Читает project_context.test_root.
    """
    try:
        from pathlib import Path as _P
        cache_path = _P(".gigacode/design/code-patterns.json")
        if not cache_path.exists():
            return None
        import json as _json
        data = _json.loads(cache_path.read_text(encoding="utf-8"))
        test_root = data.get("project_context", {}).get("test_root")
        return str(test_root) if test_root else None
    except Exception:
        return None


def run_tool():
    """Точка входа для GigaCode CLI как инструмента."""
    import sys
    import json

    if len(sys.argv) < 2:
        print("❌ Укажи путь к OpenAPI-спецификации")
        print("Пример: python -m tools.openapi_tool.main docs/openapi.json")
        sys.exit(1)

    source = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    if output_dir is None:
        # Резолвим корень тестов из code-patterns.json, если он есть.
        resolved_test_root = _resolve_test_root()
        if resolved_test_root:
            output_dir = str(Path(resolved_test_root) / "models")
            print(f"ℹ️  test_root из code-patterns.json: {resolved_test_root}")
            print(f"ℹ️  output_dir: {output_dir}")
        else:
            print("❌ Не передан output_dir, а test_root не найден в .gigacode/design/code-patterns.json")
            print("Укажи путь вторым аргументом:")
            print("  python -m tools.openapi_tool.main <spec_path> <output_dir>")
            sys.exit(1)

    try:
        result = parse_openapi(source, output_dir)
        print(f"✅ Сгенерировано {len(result['schemas'])} моделей")
        print(f"📁 Файл: {result['output_file']}")
        print(f"📋 Найдено {len(result['endpoints'])} эндпоинтов")

        # Сохраняем результат в файл для GigaCode
        summary_path = Path(".gigacode/design/openapi_parsed.json")
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"📄 Результат сохранён в {summary_path}")
        return result

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_tool()