"""
Шаблон HTTP-клиента для тестов.

HTTP-клиент — это обёртка над requests, которая:
1. Управляет сессией и заголовками (mTLS / Bearer / кастомные заголовки)
2. Логирует запросы и ответы и аттачит их в Allure
3. Валидирует ответы через Pydantic-модели
4. Поддерживает таймаут по умолчанию и опциональные ретраи
5. Отдаёт сырой ответ без исключения на 4xx/5xx (raise_for_status=False) —
   для кейсов, где ожидаемый результат сам является ошибкой
6. Читает потоковые ответы Server-Sent Events (stream_request -> SSEStream)

Как использовать:
1. Адаптируй импорты под свой проект
2. Настрой способ авторизации (mTLS, токен, или без авторизации)
3. Используй в тестах через фикстуры
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, List, Optional, Type, TypeVar, Union

import allure
import requests
from allure_commons.types import AttachmentType
from pydantic import BaseModel, TypeAdapter, ValidationError

logger = logging.getLogger(__name__)
T = TypeVar("T")

# Фильтр «ретраить ли этот ответ/ошибку» (см. retry_filter)
RetryFilter = Callable[[Optional[requests.Response], Optional[Exception]], bool]


# 1. Модель потокового ответа (Server-Sent Events)
@dataclass
class SSEEvent:
    """Одно событие SSE-потока.

    event — имя события (поле `event:`), по умолчанию "message";
    data  — распарсенный JSON из `data:` или исходная строка, если это не JSON;
    raw_data — исходная строка `data:` (несколько строк склеиваются через \\n);
    id    — значение поля `id:` (если было).
    """

    event: str
    data: Any
    raw_data: str
    id: Optional[str] = None


@dataclass
class SSEStream:
    """Результат потокового запроса: статус, заголовки и список событий.

    Хелперы под формат событий конкретного API (поиск события нужного типа,
    сборка финального состояния и т.п.) добавляются в клиенте ресурса или в
    helpers/, поверх find(...), а не здесь: формат событий у сервисов разный.
    """

    status_code: int
    headers: dict
    events: List[SSEEvent] = field(default_factory=list)

    def events_by_type(self, name: str, prefix: bool = False) -> List[SSEEvent]:
        """События с именем name. prefix=True — имя начинается с name
        (например "values" найдёт и "values|agent:<id>")."""
        if prefix:
            return [e for e in self.events if e.event.startswith(name)]
        return [e for e in self.events if e.event == name]

    def last(self, name: str, prefix: bool = False) -> Optional[SSEEvent]:
        """Последнее событие с именем name (или None)."""
        found = self.events_by_type(name, prefix=prefix)
        return found[-1] if found else None

    def find(self, predicate: Callable[[SSEEvent], bool]) -> Optional[SSEEvent]:
        """Первое событие, удовлетворяющее условию (или None)."""
        return next((e for e in self.events if predicate(e)), None)


def parse_sse_lines(lines: Iterable[str]) -> List[SSEEvent]:
    """Разбирает строки SSE-потока в события (по спецификации text/event-stream).

    - поле отделяется от значения первым двоеточием (значение может само
      содержать двоеточия: "values|agent:78c2...");
    - несколько строк data: одного события склеиваются через перевод строки;
    - пустая строка завершает событие; строки, начинающиеся с ":", — комментарии.
    """
    events: List[SSEEvent] = []
    event_name: Optional[str] = None
    data_lines: List[str] = []
    event_id: Optional[str] = None

    def dispatch() -> None:
        nonlocal event_name, data_lines, event_id
        if data_lines or event_name is not None:
            raw = "\n".join(data_lines)
            try:
                parsed: Any = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                parsed = raw
            events.append(SSEEvent(event=event_name or "message", data=parsed, raw_data=raw, id=event_id))
        event_name, data_lines, event_id = None, [], None

    for line in lines:
        line = line.rstrip("\r")
        if line == "":
            dispatch()
            continue
        if line.startswith(":"):
            continue
        name, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if name == "event":
            event_name = value
        elif name == "data":
            data_lines.append(value)
        elif name == "id":
            event_id = value
    dispatch()
    return events


# 2. HTTP-клиент
class HttpClient:
    """
    Базовый HTTP-клиент для тестов.

    Args:
        base_url: Базовый URL сервера
        cert_path: Путь к файлу сертификата (.crt) — для mTLS
        key_path: Путь к файлу приватного ключа (.key) — для mTLS
        token: Bearer-токен для авторизации
        timeout: Таймаут запроса в секундах (по умолчанию 60)
        retries: Количество повторов при сбоях (по умолчанию 0)
        retry_backoff: Базовая задержка ретраев в сек (экспоненциальный рост)
        verify: Проверка TLS-сертификата сервера. True — проверять (безопасно).
            False — отключать (только для тестовых стендов за MITM/прокси).
        **headers: Произвольные кастомные заголовки (x_*).
    """

    def __init__(
            self,
            base_url: str,
            cert_path: Optional[str] = None,
            key_path: Optional[str] = None,
            token: Optional[str] = None,
            timeout: int = 60,
            retries: int = 0,
            retry_backoff: float = 0.5,
            verify: bool = True,
            **headers: Optional[str],
    ):
        base_url = (base_url or "").strip()
        if not base_url:
            raise ValueError("base_url не может быть пустым")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.retry_backoff = retry_backoff
        self.session = requests.Session()

        default_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        # Кастомные заголовки (передают "x_client_id=..." -> "x-client-id").
        for key, value in headers.items():
            if value:
                default_headers[key.replace("_", "-")] = value
        if token:
            default_headers["Authorization"] = f"Bearer {token}"

        self.session.headers.update(default_headers)

        if cert_path and key_path:
            self.session.cert = (cert_path, key_path)
            logger.info("mTLS настроен: cert=%s, key=%s", cert_path, key_path)

        # Проверка TLS-сертификата сервера. Для тестовых стендов за
        # MITM/прокси с самоподписанным сертификатом укажи verify=False.
        self.session.verify = verify
        if not verify:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            logger.warning("Проверка TLS-сертификата ОТКЛЮЧЕНА (verify=False) — только для тест-стендов")

        logger.info("Базовый URL: %s", self.base_url)

    # ------------------------------------------------------------
    # Политика ретраев
    # ------------------------------------------------------------
    @staticmethod
    def _default_retry_filter(response, exc) -> bool:
        """Ретраим сетевые ошибки и 5xx (нестабильность сервера)."""
        if exc is not None:
            return True
        if response is None:
            return True
        return response.status_code >= 500

    # ------------------------------------------------------------
    # Центральный метод отправки (с ретраями)
    # ------------------------------------------------------------
    def _request(
            self,
            method: str,
            path: str,
            step_title: str,
            expected_model: Type[T] = None,
            timeout: int = None,
            retries: int = None,
            retry_filter: RetryFilter = None,
            raise_for_status: bool = True,
            **kwargs: Any,
    ) -> Union[T, requests.Response, None]:
        """
        Единая точка отправки с опциональными ретраями и Pydantic-валидацией.

        Аттачи и логирование — внутри _send_request. Здесь — цикл повторов:
        повторяем, пока срабатывает retry_filter и не исчерпаны попытки.

        Args:
            method: HTTP-метод
            path: Путь (относительно base_url)
            step_title: Заголовок Allure-шага
            expected_model: Pydantic-модель для валидации ответа
            timeout: Таймаут (перекрывает дефолт конструктора)
            retries: Число повторов (перекрывает дефолт конструктора)
            retry_filter: Кастомный фильтр (response, exc) -> стоит ли ретраить
            raise_for_status: False — не бросать исключение на 4xx/5xx (см. _send_request)
            **kwargs: Аргументы requests (json, params, headers и т.д.)
        """
        timeout = timeout if timeout is not None else self.timeout
        retries = retries if retries is not None else self.retries
        retry_filter = retry_filter or self._default_retry_filter

        for attempt in range(retries + 1):
            try:
                return self._send_request(
                    method, path, step_title,
                    expected_model=expected_model, timeout=timeout,
                    raise_for_status=raise_for_status, **kwargs,
                )
            except (requests.exceptions.RequestException, ValidationError) as exc:
                logger.warning(
                    "Попытка %d/%d не удалась (%s %s): %s",
                    attempt + 1, retries + 1, method, path, exc,
                )
                if attempt < retries and retry_filter(None, exc):
                    time.sleep(self.retry_backoff * (2 ** attempt))
                    continue
                raise

    # ------------------------------------------------------------
    # Одиночная отправка (логирование + Allure + Pydantic)
    # ------------------------------------------------------------
    def _send_request(
            self,
            method: str,
            path: str,
            step_title: str,
            expected_model: Type[T] = None,
            timeout: int = 60,
            raise_for_status: bool = True,
            **kwargs: Any,
    ) -> Union[T, requests.Response, None]:
        """
        Одиночная отправка запроса. Именно его вызывают клиенты (<ClientClass> и др.).
        Для автоматических ретраев оборачивай в self._request.

        raise_for_status=True (по умолчанию): на 4xx/5xx бросается HTTPError,
            на 2xx при expected_model возвращается провалидированная модель.
        raise_for_status=False: всегда возвращается requests.Response, чтобы тест
            мог проверить статус и тело сам (негативные кейсы: «ожидаю 400/403»).
            Pydantic-валидацию в этом режиме делай в тесте/хелпере, если её
            требует кейс.
        """
        with allure.step(step_title):
            url = f"{self.base_url}{path}"

            # Конвертация Pydantic-модели в словарь
            if "json" in kwargs and isinstance(kwargs["json"], BaseModel):
                kwargs["json"] = kwargs["json"].model_dump(by_alias=True, exclude_none=True)

            logger.info("--> %s %s", method, url)
            if "params" in kwargs:
                logger.info("    Query params: %s", kwargs["params"])

            try:
                response = self.session.request(method, url, timeout=timeout, **kwargs)
                request = response.request

                # Allure: endpoint
                allure.attach(
                    f"{request.method} {request.url}",
                    name="Request Endpoint",
                    attachment_type=AttachmentType.TEXT,
                )

                # Allure: тело запроса
                if request.body:
                    try:
                        body_str = (
                            request.body.decode("utf-8")
                            if isinstance(request.body, bytes)
                            else str(request.body)
                        )
                        body_json = json.loads(body_str)
                        pretty_body = json.dumps(body_json, indent=2, ensure_ascii=False)
                        allure.attach(pretty_body, name="Request Body", attachment_type=AttachmentType.JSON)
                        logger.info("    Request Body: %s", pretty_body)
                    except Exception:
                        logger.info("    Request Body (raw): %s", request.body)

                # Allure: статус ответа
                logger.info("<-- %s %s", response.status_code, response.reason)
                allure.attach(
                    f"{response.status_code} {response.reason}",
                    name="Response Status",
                    attachment_type=AttachmentType.TEXT,
                )

                # Allure: тело ответа
                try:
                    response_json = response.json()
                    pretty_response = json.dumps(response_json, indent=2, ensure_ascii=False)
                    allure.attach(pretty_response, name="Response Body", attachment_type=AttachmentType.JSON)
                    logger.info("    Response Body: %s", pretty_response)
                except json.JSONDecodeError:
                    if response.text:
                        allure.attach(response.text, name="Response Body", attachment_type=AttachmentType.TEXT)
                        logger.info("    Response Body (text): %s", response.text)

                # Проверка статуса
                if not raise_for_status:
                    return response
                response.raise_for_status()

                # Валидация через Pydantic
                if expected_model and response.text:
                    try:
                        adapter = TypeAdapter(expected_model)
                        return adapter.validate_python(response.json())
                    except ValidationError as e:
                        allure.attach(str(e), name="Pydantic Validation Error", attachment_type=AttachmentType.TEXT)
                        raise

                return response

            except requests.exceptions.SSLError as e:
                logger.error("SSL Ошибка: %s", e)
                allure.attach(str(e), name="SSL Error", attachment_type=AttachmentType.TEXT)
                raise
            except requests.exceptions.RequestException as e:
                logger.error("HTTP ошибка: %s", e)
                allure.attach(str(e), name="HTTP Error", attachment_type=AttachmentType.TEXT)
                raise

    # ------------------------------------------------------------
    # Потоковые ответы (Server-Sent Events)
    # ------------------------------------------------------------
    def stream_request(
            self,
            method: str,
            path: str,
            step_title: str,
            timeout: int = None,
            raise_for_status: bool = True,
            **kwargs: Any,
    ) -> SSEStream:
        """
        Отправляет запрос с потоковым ответом (text/event-stream), дочитывает поток
        до конца и возвращает SSEStream (status_code, headers, events).

        Весь сырой поток аттачится в Allure одним вложением — по нему удобно
        разбирать падения. raise_for_status=False — вернуть поток и при 4xx/5xx
        (тело ошибки окажется в events, если сервер прислал его как SSE,
        иначе — одним событием "message").
        """
        timeout = timeout if timeout is not None else self.timeout
        with allure.step(step_title):
            url = f"{self.base_url}{path}"
            if "json" in kwargs and isinstance(kwargs["json"], BaseModel):
                kwargs["json"] = kwargs["json"].model_dump(by_alias=True, exclude_none=True)
            headers = {"Accept": "text/event-stream", **kwargs.pop("headers", {})}

            logger.info("--> %s %s (stream)", method, url)
            with self.session.request(
                    method, url, timeout=timeout, stream=True, headers=headers, **kwargs,
            ) as response:
                allure.attach(f"{method} {response.url}", name="Request Endpoint",
                              attachment_type=AttachmentType.TEXT)
                if "json" in kwargs:
                    allure.attach(json.dumps(kwargs["json"], indent=2, ensure_ascii=False),
                                  name="Request Body", attachment_type=AttachmentType.JSON)
                logger.info("<-- %s %s", response.status_code, response.reason)
                allure.attach(f"{response.status_code} {response.reason}", name="Response Status",
                              attachment_type=AttachmentType.TEXT)

                # SSE всегда в UTF-8 (спецификация text/event-stream). Без явного
                # charset requests подставляет ISO-8859-1 для text/* — кириллица ломается.
                response.encoding = "utf-8"
                lines = list(response.iter_lines(decode_unicode=True))
                raw_stream = "\n".join(lines)
                allure.attach(raw_stream, name="Response Stream", attachment_type=AttachmentType.TEXT)

                if raise_for_status:
                    response.raise_for_status()

                return SSEStream(
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    events=parse_sse_lines(lines),
                )

    def close(self):
        """Закрывает сессию."""
        self.session.close()
        logger.debug("HTTP сессия закрыта")