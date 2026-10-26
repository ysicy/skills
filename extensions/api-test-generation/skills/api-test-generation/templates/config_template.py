"""
Шаблон конфигурации для тестов.

Конфиги передают параметры в запросы. Паттерн единый для любых проектов:

1. Фабрика создания конфига (create_config)
2. Готовые конфиги для тестов (DEFAULT_CONFIG, CUSTOM_CONFIG)
3. Возможность создавать кастомные конфиги под сценарии
4. Возможность переопределять значения через переменные окружения

Использование:
1. Определи структуру конфига под свой проект
2. Фабрика должна возвращать конфиг с дефолтными значениями
3. Создай готовые конфиги для разных сценариев
4. Используй их в тестах вместо хардкода
"""

import os

# 1. Фабрика конфигов (адаптируй под свой проект)
def _env_or_default(name: str, default) -> str:
    """Возвращает значение переменной окружения или дефолт."""
    return os.environ.get(name, default)


def create_config(
        scenario_param: str = None,
        extra: dict = None,
        technical_param: int = None,
) -> dict:
    """
    Фабрика конфига.
    scenario_param / extra — зависящие от сценария параметры.
    technical_param — технический параметр (дефолт из окружения TEST_TECHNICAL_PARAM).
    Замени имена параметров на реальные из своего проекта.
    """
    return {
        "<technical_key>": technical_param or int(_env_or_default("TECHNICAL_PARAM", "100")),
        "<configurable_group>": {
            "<scenario_key>": scenario_param,
            "<extra_key>": extra or {},
        },
    }


# 2. Готовые конфиги
DEFAULT_CONFIG = create_config()

CUSTOM_CONFIG = create_config(extra={"<param_key>": "<value>"})

CONFIG_WITH_SCENARIO = create_config(scenario_param="<scenario_value>")

CONFIG_WITH_FULL_SETTINGS = create_config(
    scenario_param="<scenario_value>",
    extra={
        "<param_key>": "<value>",
        "<filter_key>": "active",
        "<limit_key>": 100,
    },
)


# 3. Пример использования
if __name__ == "__main__":
    print("DEFAULT_CONFIG:", DEFAULT_CONFIG)
    print("CUSTOM_CONFIG:", CUSTOM_CONFIG)
    print("CONFIG_WITH_SCENARIO:", CONFIG_WITH_SCENARIO)