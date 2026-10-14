"""
Шаблон Pydantic-моделей (DTO) для тестового контура.

Здесь живут модели запросов и ответов. Используются билдерами (для сборки
запросов) и HTTP-клиентом (для валидации ответов через TypeAdapter).

Как использовать:
1. Переименуй классы под свою предметную область (например, CreateXRequest,
   XResponse). НАЗВАНИЯ В УГЛОВЫХ СКОБКАХ ЯВНО ТРЕБУЮТ ЗАМЕНЫ.
2. Поля ответа приведи в соответствие с фактическим JSON API.
3. Если поле в JSON именуется иначе (snake_case в Python, camelCase в API),
   используй alias: `alias="camelCaseField"`. При отправке наружу не забудь
   `model_dump(by_alias=True, exclude_none=True)`: это уже делает HttpClient.
"""

from typing import Any, Dict, Optional

# Строковая аннотация ниже нужна, чтобы файл был валидным Python-синтаксисом
# до того, как ты заменишь имя базового класса. Замени на свой `from ... import BaseModel`.
from pydantic import BaseModel, Field


class RequestDto(BaseModel):
    """Пример DTO запроса. Адаптируй поля под свой API."""

    metadata: Optional[Dict[str, Any]] = None
    initial_state: Optional[Dict[str, Any]] = Field(default=None)
    # <добавь поля под свой эндпоинт>


class ResponseDto(BaseModel):
    """Пример DTO ответа. Адаптируй поля под реальный JSON API."""

    # Если API отдаёт camelCase, задай alias. Пример:
    # some_field: Optional[str] = Field(default=None, alias="someField")
    # Пример поля под замену:
    # some_field: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    id: Optional[str] = None


class ItemDto(BaseModel):
    """Вложенная структура ответа (элемент списка/вложенный объект)."""

    kind: Optional[str] = None
    name: Optional[str] = None
    value: Optional[Any] = None
    status: Optional[str] = None