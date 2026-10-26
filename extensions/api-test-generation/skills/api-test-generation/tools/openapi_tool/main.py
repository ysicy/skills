"""
Основной модуль OpenAPI Tool.
"""
import ast
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Set

if __package__ in (None, ""):
    # Запуск как скрипта: python "<skill_dir>/tools/openapi_tool/main.py" ...
    # Относительные импорты работают только внутри пакета, поэтому подключаем пакет по пути.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from openapi_tool.generator import PydanticGenerator
    from openapi_tool.models import ParsedOpenAPI  # noqa: F401
    from openapi_tool.parser import OpenAPIParser
else:
    from .generator import PydanticGenerator
    from .models import ParsedOpenAPI  # noqa: F401
    from .parser import OpenAPIParser


def _read_existing_schemas(models_dir: str, skip_file: Optional[str] = None) -> Set[str]:
    """
    Читает существующие Pydantic-модели из каталога моделей (output_dir)
    и возвращает набор имён классов. Файл, который сейчас будет перезаписан, не учитывается.
    """
    existing = set()
    models_path = Path(models_dir)
    if not models_path.exists():
        return existing

    for py_file in models_path.glob("*.py"):
        if skip_file and py_file.name == skip_file:
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                existing.add(node.name)

    return existing


def _check_duplicate_schemas(
        new_schemas: list,
        output_dir: str,
        skip_file: Optional[str] = None
) -> Dict[str, Any]:
    """
    Проверяет, какие DTO уже существуют в проекте.

    Args:
        new_schemas: список Schema из OpenAPI
        output_dir: каталог моделей, в котором ищутся уже существующие классы
        skip_file: файл, который будет перезаписан генерацией (не считается дубликатом)

    Returns:
        Dict с классификацией:
        {
            "existing": ["User", "Order"],  # уже есть в коде
            "new": ["Address"],              # новых не было
            "duplicates_detected": True/False,
            "recommendation": "..."
        }
    """
    existing = _read_existing_schemas(output_dir, skip_file)

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
        check_duplicates: bool = True,
        duplicate_action: str = "warn"
) -> Dict[str, Any]:
    """
    Парсит OpenAPI-спецификацию и генерирует Pydantic-модели.

    Args:
        source: Путь к локальному файлу OpenAPI-спецификации (.json/.yaml)
        output_dir: Директория для сохранения моделей (по умолчанию: None — спросить у пользователя или взять из code-patterns.json)
        output_filename: Имя файла с моделями
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

    parser = OpenAPIParser(source)
    parsed = parser.parse()

    # Проверка дубликатов DTO
    duplicate_result = None
    if check_duplicates and output_dir:
        duplicate_result = _check_duplicate_schemas(
            parsed.schemas, output_dir, skip_file=output_filename
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
        "endpoints": [e.model_dump(exclude_none=True) for e in parsed.endpoints],
        "enums": {
            f"{s.name}.{f.name}": f.enum
            for s in parsed.schemas for f in s.fields if f.enum
        },
        "output_file": saved_path
    }

    if duplicate_result is not None:
        result["duplicate_check"] = duplicate_result

    return result


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
    import json

    if len(sys.argv) < 2:
        print("❌ Укажи путь к OpenAPI-спецификации")
        print('Пример: python "<skill_dir>/tools/openapi_tool/main.py" docs/openapi.json tests/models')
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
            print('  python "<skill_dir>/tools/openapi_tool/main.py" <spec_path> <output_dir>')
            sys.exit(1)

    project_root = Path.cwd().resolve()
    target = (project_root / output_dir).resolve()
    if target != project_root and project_root not in target.parents:
        print(f"❌ Каталог моделей {output_dir} вне проекта {project_root} — запись отклонена")
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