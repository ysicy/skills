# README: Развёртывание тестового контура с нуля

Этот документ — пошаговая инструкция, как развернуть полноценный API-тестовый
контур в пустом проекте на базе шаблонов из `skills/api-test-generation/templates/`.

## Что получится на выходе

```
<test_root>/                      # корень тестов (обычно tests/)
├── conftest.py                   # фикстуры, базовые пользователи, base_url
├── requirements.txt              # зависимости (pytest, requests, pydantic)
├── README.md                     # этот файл
└── rest/
    ├── core/
    │   └── http_client.py        # базовый HTTP-клиент
    ├── clients/
    │   └── <resource>.py         # клиенты-ресурсы (create/get/execute)
    ├── models/
    │   └── <dto>.py              # Pydantic DTO
    ├── config/
    │   └── configs.py            # конфиги
    ├── helpers/
    │   └── request_builders.py   # билдеры запросов
    └── test_suites/
        └── test_<feature>.py     # сценарии тестов
```

В корне проекта (рядом с `tests/`):

```
pytest.ini         # конфигурация pytest (шаблон pytest_config_template.ini)
.env               # значения окружения (НЕ коммитить; .env.example — пример)
.gitignore         # игнор кэша, отчётов, env (шаблон gitignore_template.txt)
```

## Порядок развёртывания

### Шаг 1. Зависимости (делает человек)

Зависимости ставит человек в окружении проекта своим менеджером пакетов
(`uv`, `poetry`, `pip`) — агент генерации их не устанавливает. Версии фиксируй
в lock-файле проекта.

Минимальный набор:
- `pytest`
- `requests`
- `pydantic>=2`
- `PyYAML` — если спецификация OpenAPI в YAML (нужен инструменту генерации моделей)
- `allure-pytest`
- (опц.) `allure-commons`

### Шаг 2. Конфигурация pytest

Скопируй `pytest_config_template.ini` → `pytest.ini`. Зарегистрированные маркеры
(`smoke`, `regression`, `slow`) согласуй с марками, что реально ставишь в тестах.

### Шаг 3. Окружение

Переменные, которые читает контур, перечислены в `.env.example`. Значения задаёт окружение
запуска: в CI — секрет-хранилище пайплайна, локально — как принято в команде. Значения не
коммитятся; код контура читает их только из переменных окружения.

### Шаг 4. Модели (DTO)

Скопируй `model_template.py` → `<test_root>/models/<model_module>.py`.
Адаптируй поля под фактический JSON вашего API.

### Шаг 5. HTTP-клиент

Скопируй `http_client_template.py` → `<test_root>/rest/core/http_client.py`.
Настрой авторизацию: mTLS (cert/key) или Bearer, или без авторизации.

### Шаг 6. Клиенты-ресурсы

Скопируй `client_template.py` → `<test_root>/rest/clients/<resource>.py`.
Унаследуйся от `HttpClient`, реализуй операции (`create`, `get`, `execute`).

### Шаг 7. Билдеры и конфиги

Скопируй `builder_template.py` → `<test_root>/rest/helpers/request_builders.py`.
Скопируй `config_template.py` → `<test_root>/rest/config/configs.py`
(поправь import-пути, если нужно).

### Шаг 8. conftest + фикстуры

Скопируй `conftest_template.py` → `<test_root>/conftest.py`.
Подключи `api_client`, `user`, `get_resource_id` к реальным клиентам.

### Шаг 9. Проверка сборки каркаса

Каркас проверяется первым настоящим тестом: запусти его сам
(`python -m pytest <test_root>/rest/test_suites/test_<feature>.py -v`). Ошибки синтаксиса
и импортов покажет сбор тестов, работоспособность клиента — ответ стенда.

## Чек-лист готовности

- [ ] `requirements.txt` установлены
- [ ] `pytest.ini` создан, маркеры зарегистрированы
- [ ] Переменные из `.env.example` заданы в окружении запуска (CI — секрет-хранилище), значения не в коде
- [ ] Модели отражают реальные ответы API
- [ ] HTTP-клиент авторизуется (mTLS/Bearer)
- [ ] Хотя бы один клиент-ресурс реализован
- [ ] Билдеры возвращают типизированные DTO
- [ ] conftest собирает `api_client`/`user`/`get_resource_id`
- [ ] Первый тест собирается и запускается
- [ ] `from <test_root>.rest.core.http_client import HttpClient` импортируется

## Как писать тесты

За основу бери `test_template.py`: три шага на тест (подготовка → запрос → проверка),
Allure-декораторы, билдеры вместо ручного создания DTO, поиск вложенных сообщений
через list comprehension.