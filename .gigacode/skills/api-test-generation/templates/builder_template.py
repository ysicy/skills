"""
Шаблон билдера для создания запросов.

Билдер — функция или класс, который скрывает сложность сборки DTO.
Паттерн единый для любых проектов:

- Билдер принимает ключевые параметры (текст, конфиг, ID сущности)
- Внутри собирает сложный объект с дефолтными значениями
- Возвращает структуру запроса

Как использовать:
1. Определи свои DTO-модели (Pydantic) в <test_root>/models/
2. Замени сигнатуру и строку return на реальный вызов конструктора DTO
3. Используй билдеры в тестах вместо ручного создания данных
"""

from typing import Any, Dict, Optional

# 1. Импорты (раскомментируй и подставь свои):
# from <test_root>.models.<model_module> import <RequestDto>


# 2. Билдеры (адаптируй под свои модели)
# Универсальный билдер: прими ключевые параметры и собери DTO/словарь
# для конкретного эндпоинта проекта. Имена полей — намеренно нейтральные,
# замени их на реальные из моделей твоего контура.
def build_create_request(
        metadata: Optional[Dict[str, Any]] = None,
        initial_state: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Создаёт запрос на создание сущности (ресурса).
    Обязательные поля заполняй дефолтами, вариативные — параметрами.

    Когда есть DTO:
        return <RequestDto>(metadata=metadata or {}, initial_state=initial_state or {})
    """
    return {
        "metadata": metadata or {},
        "initial_state": initial_state or {},
    }


def build_action_request(
    payload: Optional[Dict[str, Any]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Универсальный билдер действия/запроса к целевому эндпоинту.
    payload — бизнес-данные запроса; config — параметры выполнения.
    Адаптируй под свой эндпоинт: замени поля на реальные из проекта.

    Когда есть DTO:
        from <test_root>.models.<model_module> import <RequestDto>
        return <RequestDto>(
            <body_field>="<...>",
            payload=payload or {},
            config=config or {},
        )
    """
    return {
        "<body_field>": "<value>",
        "payload": payload or {},
        "config": config or {},
    }


# 3. Пример использования (только для ручного запуска)
if __name__ == "__main__":
    entity = build_create_request(metadata={"source": "test"})
    print("Создана сущность:", entity)

    request = build_action_request(payload={"query": "тестовый запрос"}, config={})
    print("Создан запрос:", request)