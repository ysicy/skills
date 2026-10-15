"""
Шаблон клиента-ресурса (client) для тестового контура.

Клиент-ресурс наследует базовый HttpClient и инкапсулирует операции над
конкретной сущностью API (create, get, execute, delete и т.д.). Именно его
используют фикстуры в conftest.py.

Правила:
- Клиент НЕ содержит проверок (это прерогатива тестов).
- Все запросы идут через `self._send_request` базового HttpClient
  (там Allure-аттачи + Pydantic-валидация).
- Повторы при временных сбоях — через `self._request(..., retries=N)` и только для
  идемпотентных методов (GET, PUT, DELETE). POST/PATCH не повторяй: повтор может
  создать дубль. Негативные запросы (`raise_for_status=False`) не повторяются.

Как использовать:
1. Этот файл синтаксически валиден сам по себе (без реального HttpClient),
   чтобы тебя не сыпала подсветка линтера до готовности каркаса.
2. Когда создашь <test_root>/core/http_client.py и модели — раскомментируй
   импорты и наследование (строки с # ACTIVE), а заглушку класса-переопределения
   удали.
3. Замени плейсхолдеры <resource_path>, <action> на свои.
"""

from typing import Any, Dict, Optional

# # Раскомментируй, когда каркас собран:
# from <test_root>.core.http_client import HttpClient
# from <test_root>.models.<model_module> import <ResponseDto>


class ResourceClient:
    """
    Клиент для работы с сущностью <resource>.

    #ACTIVE: когда появится Httpclient — сделай `class ResourceClient(HttpClient):`
    и удали метод `_not_implemented_raise` / заглушку ниже.
    Замени типы ответов на реальные модели (<ResponseDto> / Dict[str, Any]).
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        # Реальный конструктор Httpclient подставится автоматически после наследования.
        self._resource_path = "<resource_path>"  # например "/<resource>"

    def create(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        POST /<resource>
        Создаёт сущность и возвращает типизированный ответ.

        # ACTIVE-код после наследования:
        # return self._send_request("POST", self._resource_path,
        #                            step_title="Создание ресурса",
        #                            expected_model=<ResponseDto>, json=request)
        """
        return self._not_implemented()

    def get(self, resource_id: str) -> Optional[Dict[str, Any]]:
        """
        GET /<resource_path>/{id}
        Возвращает сущность по идентификатору. GET идемпотентен — повторы безопасны.

        # ACTIVE-код после наследования:
        # return self._request("GET", f"{self._resource_path}/{resource_id}",
        #                      step_title="Получение ресурса",
        #                      expected_model=<ResponseDto>, retries=2)
        """
        return self._not_implemented()

    def delete(self, resource_id: str) -> Any:
        """
        DELETE /<resource_path>/{id}
        Удаляет сущность — используется в teardown фикстур (conftest.py).
        Без исключения на 4xx: сущность могли уже удалить в самом тесте.

        # ACTIVE-код после наследования:
        # return self._send_request("DELETE", f"{self._resource_path}/{resource_id}",
        #                            step_title="Удаление ресурса", raise_for_status=False)
        """
        return self._not_implemented()

    def execute(self, resource_id: str, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        POST /<resource_path>/{id}/<action>
        Пример команды над ресурсом. Это POST — без повторов, через _send_request.
        """
        self._not_implemented()

    def create_raw(self, request: Dict[str, Any]) -> Any:
        """
        POST /<resource> без исключения на 4xx/5xx — для негативных кейсов
        («ожидаю 400/403»): тест сам проверяет response.status_code и тело.

        # ACTIVE-код после наследования:
        # return self._send_request("POST", self._resource_path,
        #                            step_title="Создание ресурса",
        #                            raise_for_status=False, json=request)
        """
        return self._not_implemented()

    def run_stream(self, resource_id: str, request: Dict[str, Any]) -> Any:
        """
        POST /<resource_path>/{id}/<stream_action> с ответом text/event-stream.
        Возвращает SSEStream (status_code, events, events_by_type, last, find).

        Хелперы под формат событий своего API (поиск события нужного типа,
        финальное состояние) добавляй здесь или в helpers/, поверх SSEStream.find(...).

        # ACTIVE-код после наследования:
        # return self.stream_request("POST", f"{self._resource_path}/{resource_id}/<stream_action>",
        #                            step_title="Потоковый запрос", json=request)
        """
        return self._not_implemented()

    @staticmethod
    def _not_implemented() -> None:
        """Заглушка, пока клиент не подключён к реальному HttpClient."""
        raise NotImplementedError(
            "Клиент-шаблон ещё не подключён к HttpClient. Собери каркас "
            "по README и раскомментируй ACTIVE-фрагменты."
        )