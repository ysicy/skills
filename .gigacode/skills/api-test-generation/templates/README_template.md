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

### Шаг 1. Зависимости

Создай `requirements.txt` и установи (примерный состав):

```
pip install -r requirements.txt
```

Минимальный набор:
- `pytest`
- `requests`
- `pydantic>=2`
- `allure-pytest`
- (опц.) `python-dotenv` — если грузишь `.env`
- (опц.) `allure-commons`

### Шаг 2. Конфигурация pytest

Скопируй `pytest_config_template.ini` → `pytest.ini`. Зарегистрированные маркеры
(`smoke`, `regression`, `slow`) согласуй с марками, что реально ставишь в тестах.

### Шаг 3. Окружение

Скопируй `env.example` → `.env` и заполни реальные `TEST_BASE_URL`, `TECHNICAL_PARAM`
и т.д. Подключи загрузку в `conftest.py`:

```python
from dotenv import load_dotenv
load_dotenv()   # в начале conftest.py (если используешь .env)
```

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

Отдельный smoke-тест не нужен — сборка контура проверяется напрямую:

```bash
# Синтаксис и компилируемость всех .py каркаса
python -m compileall <test_root>/

# Импортируемость ключевых модулей (соберёт пути, модели, клиент)
python -c "from <test_root>.rest.core.http_client import HttpClient; print('OK')"
```

Если `compileall` и импорт проходят без ошибок — каркас собирается корректно.
Фактическая работоспособность подтверждается первым настоящим тестом,
который доходит до стенда (см. «Как писать тесты»).

## Чек-лист готовности

- [ ] `requirements.txt` установлены
- [ ] `pytest.ini` создан, маркеры зарегистрированы
- [ ] `.env` заполнен, `TEST_BASE_URL` валидный
- [ ] Модели отражают реальные ответы API
- [ ] HTTP-клиент авторизуется (mTLS/Bearer)
- [ ] Хотя бы один клиент-ресурс реализован
- [ ] Билдеры возвращают типизированные DTO
- [ ] conftest собирает `api_client`/`user`/`get_resource_id`
- [ ] `python -m compileall <test_root>/` без ошибок
- [ ] `from <test_root>.rest.core.http_client import HttpClient` импортируется

## Как писать тесты

За основу бери `test_template.py`: три шага на тест (подготовка → запрос → проверка),
Allure-декораторы, билдеры вместо ручного создания DTO, поиск вложенных сообщений
через list comprehension.