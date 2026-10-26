"""
Шаблон теста для API-тестов.

Демонстрирует паттерны написания тестов:
1. Использование фикстур (api_client, get_resource_id, user)
2. Использование билдеров для создания запросов
3. Три обязательных шага: подготовка, запрос, проверка
4. Проверки — ровно по ожидаемым результатам кейса (guard `is not None` — только
   перед обращением к полю объекта, который может отсутствовать)
5. Поиск сообщений в ответе через list comprehension
6. Проверка AI-ответов на наличие ключевых фраз

ВАЖНО:
- Файл синтаксически валиден (не сыплет подсветку линтера) — тела тестов
  заведомо заглушены `NotImplementedError`. Когда каркас готов, замени
  `_not_implemented()` на реальные шаги (см. комментарии # ACTIVE).
- Импорты билдеров/конфига закомменчены — раскомментируй после сборки каркаса.
"""

import allure
import pytest

# Импорты (раскомментируй, когда каркас собран):
# from <test_root>.models.<model_module> import <RequestDto>
# from <test_root>.utils.builders import build_action_request, build_create_request
# from <test_root>.config import DEFAULT_CONFIG


def _not_implemented() -> None:
    """Заглушка: тест не подключён к реальному контуру."""
    raise NotImplementedError(
        "Тест-шаблон ещё не подключён. Собери каркас по README и замени "
        "вызов _not_implemented() на реальные шаги."
    )


# 2. Пример тестового класса
@allure.feature("<Название фичи>")
class TestFeatureName:
    """Тесты для <описание фичи>. ЗАМЕНИ НА СВОЙ КЛАСС."""

    @allure.title("Создание ресурса")
    def test_create_resource(self, api_client):
        """Ожидаемый результат: ресурс создан, ID не пустой."""
        # ACTIVE — пример:
        # with allure.step("Подготовим данные"):
        #     create_request = build_create_request(metadata={}, initial_state={})
        # with allure.step("Выполним запрос"):
        #     resource = api_client.create(create_request)
        # with allure.step("Проверим результат"):
        #     assert resource is not None
        #     assert resource.id is not None
        _not_implemented()

    @allure.title("Вызов метода с проверкой ответа")
    @pytest.mark.parametrize("user", ["user_1"], indirect=True)
    def test_check_method_response(self, get_resource_id, api_client):
        """Ожидаемый результат: метод выполнен, ответ содержит ожидаемые данные."""
        # Пример (ACTIVE):
        # resource_id = get_resource_id
        # with allure.step("Подготовим данные"):
        #     request = build_action_request(payload={"query": "тестовый запрос"}, config=DEFAULT_CONFIG)
        # with allure.step("Выполним запрос"):
        #     response = api_client.call(resource_id, request)
        # with allure.step("Проверим результат"):
        #     assert response is not None
        #     assert response.status == "success"
        #     result = None
        #     for item in response.items:
        #         if item.kind == "expected_kind":
        #             result = item
        #             break
        #     assert result is not None
        #     assert result.value is not None
        _not_implemented()

    @allure.title("Проверка ответа на наличие ключевых фраз")
    def test_check_response_phrases(self, get_resource_id, api_client):
        """Ожидаемый результат: ответ содержит все ожидаемые фразы."""
        # Пример (ACTIVE):
        # resource_id = get_resource_id
        # with allure.step("Подготовим данные"):
        #     request = build_action_request(payload={"query": "тестовый запрос"}, config=DEFAULT_CONFIG)
        # with allure.step("Выполним запрос"):
        #     response = api_client.call(resource_id, request)
        # with allure.step("Проверим результат"):
        #     text_blocks = [item for item in response.items if item.kind == "text"]
        #     assert text_blocks
        #     content = text_blocks[-1].value
        #     expected_phrases = ["фраза_1", "фраза_2"]
        #     for phrase in expected_phrases:
        #         assert phrase in content, f"В ответе отсутствует фраза '{phrase}'"
        _not_implemented()


# 3. Негативный сценарий (пример)
@allure.feature("<Негативные сценарии>")
class TestNegativeScenarios:

    @allure.title("Ошибка при невалидном запросе")
    def test_invalid_request(self, api_client):
        """Ожидаемый результат: невалидный запрос возвращает ошибку."""
        # Пример (ACTIVE): статус ошибки проверяется на ответе, без pytest.raises
        # with allure.step("Подготовим невалидные данные"):
        #     invalid_request = {"invalid_field": "value"}
        # with allure.step("Выполним запрос"):
        #     response = api_client.create_raw(invalid_request)  # raise_for_status=False
        # with allure.step("Проверим, что вернулась ошибка 400"):
        #     assert response.status_code == 400, f"Ожидали 400, получили {response.status_code}"
        _not_implemented()