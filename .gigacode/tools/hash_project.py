#!/usr/bin/env python3
"""
Хэш состояния тестового контура для кэша code-pattern-matcher.

Если хэш совпадает с metadata.last_scan_hash в code-patterns.json — контур
не менялся, и матчер может переиспользовать кэш вместо полного сканирования.

Что входит в хэш (путь файла + содержимое):
1. Инфраструктура контура: все *.py, КРОМЕ самих тест-файлов (test_*.py, *_test.py).
   conftest.py, клиенты, модели, билдеры, конфиги — входят.
   Тест-файлы исключены намеренно: каждый прогон пайплайна дописывает тест,
   и без исключения кэш инвалидировался бы на каждом прогоне. Новый тест,
   написанный в том же стиле, паттернов контура не меняет.
   Флаг --include-tests возвращает тест-файлы в хэш.
2. Конфигурация раннера и зависимости: pytest.ini, pyproject.toml, setup.cfg,
   tox.ini, requirements*.txt, .env.example.
3. Внешние спецификации (Swagger/OpenAPI), переданные аргументами: локальные
   файлы — по содержимому; URL — по содержимому, если его удалось скачать,
   иначе только по самой строке URL (с предупреждением в stderr).

Перевод строк нормализуется (CRLF -> LF), чтобы хэш совпадал на Windows и Linux.

Использование (из корня проекта или с явным корнем):
    python .gigacode/tools/hash_project.py
    python .gigacode/tools/hash_project.py <project_root>
    python .gigacode/tools/hash_project.py <project_root> spec.yaml https://host/openapi.json
    python .gigacode/tools/hash_project.py --include-tests

Вывод: одна строка — MD5-хэш.
"""

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path
from typing import Iterable, List, Optional

IGNORED_DIRS = {
    ".git", ".gigacode", ".idea", ".vscode", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".tox", ".venv", "venv", "env",
    "node_modules", "build", "dist", "allure-results", "allure-report",
}
CONFIG_NAMES = {"pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini", ".env.example"}
URL_TIMEOUT_SEC = 10


def _is_test_file(path: Path) -> bool:
    return path.suffix == ".py" and (path.name.startswith("test_") or path.stem.endswith("_test"))


def _is_tracked(path: Path, include_tests: bool) -> bool:
    if path.name in CONFIG_NAMES:
        return True
    if path.name.startswith("requirements") and path.suffix == ".txt":
        return True
    if path.suffix == ".py":
        return include_tests or not _is_test_file(path)
    return False


def iter_contour_files(root: Path, include_tests: bool = False) -> List[Path]:
    """Файлы контура, отсортированные по относительному пути (детерминированно)."""
    files = []
    for path in root.rglob("*"):
        rel_parts = path.relative_to(root).parts
        if any(part in IGNORED_DIRS for part in rel_parts[:-1]):
            continue
        if path.is_file() and _is_tracked(path, include_tests):
            files.append(path)
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def _normalized(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def _read_spec(spec: str) -> Optional[bytes]:
    if spec.startswith(("http://", "https://")):
        try:
            with urllib.request.urlopen(spec, timeout=URL_TIMEOUT_SEC) as resp:
                return resp.read()
        except Exception as exc:  # сеть/доступ — не повод падать, но изменения спеки не увидим
            print(f"[hash_project] не удалось скачать {spec}: {exc}; в хэш входит только URL",
                  file=sys.stderr)
            return None
    path = Path(spec)
    if path.is_file():
        return path.read_bytes()
    print(f"[hash_project] спецификация не найдена: {spec}; в хэш входит только путь", file=sys.stderr)
    return None


def compute_hash(root: Path, specs: Iterable[str] = (), include_tests: bool = False) -> str:
    md5 = hashlib.md5()
    for path in iter_contour_files(root, include_tests):
        md5.update(path.relative_to(root).as_posix().encode("utf-8"))
        md5.update(b"\0")
        try:
            md5.update(_normalized(path.read_bytes()))
        except OSError:
            md5.update(b"<unreadable>")
        md5.update(b"\0")
    for spec in sorted(specs):
        md5.update(f"spec:{spec}".encode("utf-8"))
        md5.update(b"\0")
        content = _read_spec(spec)
        if content is not None:
            md5.update(_normalized(content))
        md5.update(b"\0")
    return md5.hexdigest()


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MD5-хэш тестового контура для кэша code-patterns.json")
    parser.add_argument("paths", nargs="*",
                        help="[корень проекта] [спецификации...]. Первый аргумент — корень, "
                             "если это каталог; остальные (и первый, если это не каталог) — спецификации.")
    parser.add_argument("--include-tests", action="store_true",
                        help="включить тест-файлы (test_*.py) в хэш")
    args = parser.parse_args(argv)
    args.root = Path(".")
    args.specs = list(args.paths)
    if args.specs and Path(args.specs[0]).is_dir():
        args.root = Path(args.specs.pop(0))
    return args


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    print(compute_hash(args.root.resolve(), args.specs, args.include_tests))


if __name__ == "__main__":
    main()
