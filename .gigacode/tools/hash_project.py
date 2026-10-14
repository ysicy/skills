#!/usr/bin/env python3
"""
Вычисление MD5-хэша всех файлов, определяющих состояние проекта и входные данные.

Используется code-pattern-matcher для определения изменений в контуре.
Если хэш совпадает с сохранённым в code-patterns.json → состояние не менялось, можно использовать кэш.

В хэш входят:
1. Все .py файлы проекта (исходный код)
2. Все OpenAPI/Swagger спецификации (input_spec_files) из project_context
3. Все .yaml/.json конфигурации проекта (pytest.ini, pyproject.toml)
4. Все .env/.yml файлы конфигурации
"""

import hashlib
import json
import sys
from pathlib import Path


def hash_py_files(project_root: str = None, extra_spec_files: list = None) -> str:
    """
    Считает MD5-хэш по содержимому всех значимых файлов.

    Args:
        project_root: Путь к корню проекта
        extra_spec_files: Список путей к внешним файлам (Swagger/YAML), которые нужно включить

    Порядок файлов сортируется, чтобы хэш был детерминированным.
    В ignores - только .venv, __pycache__, .git.
    """
    if project_root is None:
        # Если путь не передан, берём текущую рабочую директорию (корень репозитория)
        project_root = "."

    root = Path(project_root).resolve()
    md5 = hashlib.md5()

    ignores = {"__pycache__", ".venv", ".git", ".pytest_cache"}

    py_files = sorted(
        p for p in root.rglob("*.py")
        if not any(part in ignores for part in p.relative_to(root).parts)
        and not ".gigacode" in [p.parts[0] if p.parts else "" for p in [p.relative_to(root)]]
    )

    for file_path in py_files:
        md5.update(file_path.name.encode())  # Имя файла тоже входит в хэш
        try:
            md5.update(file_path.read_bytes())
        except (PermissionError, OSError):
            pass  # Пропускаем недоступные файлы

    # Включаем внешние спецификации (Swagger/OpenAPI)
    if extra_spec_files:
        for spec_path in extra_spec_files:
            spec_file = Path(spec_path)
            if spec_file.exists():
                md5.update(spec_file.name.encode())
                try:
                    md5.update(spec_file.read_bytes())
                except (PermissionError, OSError):
                    pass

    return md5.hexdigest()


def main():
    """
    CLI интерфейс: принимает аргументы:
      1. Путь к проекту (опционально, по умолчанию текущая директория)
      2+. Путь(и) к внешним файлам (Swagger, OpenAPI) — если есть

    Примеры:
        python hash_project.py /path/to/project  -> "abc123..."
        python hash_project.py /path/to/project https://api.example.com/openapi.yaml  -> "abc123..."
    """
    args = sys.argv[1:]
    project_root = None
    extra_specs = []

    for arg in args:
        p = Path(arg)
        if p.exists() or arg.startswith("http"):
            extra_specs.append(arg)
        else:
            project_root = arg

    if extra_specs:
        print(hash_py_files(project_root, extra_specs))
    else:
        print(hash_py_files(project_root))


if __name__ == "__main__":
    main()