"""
Шаблон conftest.py для тестов API.

conftest.py — корневой файл тестового контура. Здесь живут:
1. Фикстуры верхнего уровня (по умолчанию scope="session")
2. Базовые тестовые пользователи (USERS)
3. Клиенты API и хелперы-ресурсы

Как использовать:
1. Замени плейсхолдеры в скобках <...> на реальные (см. блоки ниже)
2. Раскомментируй ACTIVE-фрагменты, когда каркас собран
3. Удали фикстуры, которые не нужны твоему проекту

ВАЖНО: имя `conftest.py` фиксированно. pytest подхватывает его автоматически
для тестов в каталоге и подкаталогах.
"""

import os

import pytest


# 1. Импорты (раскомментируй, когда каркас собран):
# from <test_root>.clients.<client_module> import <ClientClass>
# from <test_root>.models.<model_module> import <RequestDto>


# 2. Базовый URL (из переменной окружения или дефолт)
def _env_or_default(name: str, default: str) -> str:
    """Возвращает значение переменной окружения или дефолт."""
    return os.environ.get(name, default)


@pytest.fixture(scope="session")
def base_url() -> str:
    """Базовый URL API (переопределяется через TEST_BASE_URL)."""
    return _env_or_default("TEST_BASE_URL", "<test_base_url>")


# 3. Тестовые пользователи
# Ключ — алиас, значение — заголовки/токены, уходящие в клиенты.
_USERS = {
    "user_1": {"<header_1>": "<value>", "<header_2>": "<value>"},
    "user_2": {"<header_1>": "<value>", "<header_2>": "<value>"},
}


@pytest.fixture(scope="function")
def user(request) -> dict:
    """Возвращает данные пользователя по ключу из параметризации.

    Параметризация: @pytest.mark.parametrize("user", ["user_2"], indirect=True)
    """
    user_key = getattr(request, "param", "user_1")
    return _USERS.get(user_key, _USERS["user_1"])


# 4. Клиенты
@pytest.fixture(scope="function")
def api_client(base_url, user):
    """
    Создаёт клиент API под текущего пользователя.

    # ACTIVE — когда каркас собран, замени тело фикстуры на:
    #     client = <ClientClass>(base_url=base_url, **user)
    #     yield client
    #     client.close()
    """
    raise NotImplementedError(
        "Клиент ещё не подключён. Собери каркас и замени тело api_client "
        "на реальный экземпляр <ClientClass>."
    )


@pytest.fixture(scope="function")
def get_resource_id(api_client):
    """
    Создаёт ресурс, отдаёт его идентификатор тесту и удаляет после теста.

    Фикстура, которая создаёт данные на стенде, обязана их убрать: иначе
    мусор копится с каждым прогоном, а повторный запуск видит чужие данные
    (принцип независимости и идемпотентности теста). Удаление — после
    `yield`, оно выполнится и при упавшем тесте. Если API не умеет удалять
    сущность — напиши об этом в docstring фикстуры, а не молча оставляй данные.

    # ACTIVE-заглушка ниже; после создания модели:
    #     create_request = <RequestDto>(metadata={}, initial_state={})
    #     resource = api_client.create(create_request)
    #     yield resource.id
    #     api_client.delete(resource.id)  # без исключения: тест мог удалить сам
    """
    raise NotImplementedError(
        "get_resource_id ещё не подключён к реальному ресурсу. "
        "Собери каркас по README."
    )