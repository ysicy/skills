from typing import List, Any, Optional
from pydantic import BaseModel, Field


class SchemaField(BaseModel):
    """Поле OpenAPI-схемы."""
    name: str                                   # имя в JSON (как в спецификации)
    type: str                                   # Python-тип (без Optional)
    is_required: bool = False
    nullable: bool = False                      # значение может быть null
    description: Optional[str] = None
    default: Optional[Any] = None
    enum: Optional[List[Any]] = None            # допустимые значения из спецификации
    nested: Optional[List['SchemaField']] = None
    items_type: Optional[str] = None


class Schema(BaseModel):
    """OpenAPI-схема.

    kind="model" — объект, генерируется класс Pydantic;
    kind="alias" — не объект (массив, строка с enum, oneOf и т.п.), генерируется псевдоним типа.
    """
    name: str
    fields: List[SchemaField]
    description: Optional[str] = None
    kind: str = "model"
    alias_type: Optional[str] = None
    enum: Optional[List[Any]] = None


class Parameter(BaseModel):
    """Параметр операции (path/query/header/cookie)."""
    name: str
    location: str
    required: bool = False
    type: str = "Any"
    enum: Optional[List[Any]] = None


class Endpoint(BaseModel):
    """OpenAPI-эндпоинт."""
    path: str
    method: str
    summary: str = ""
    description: str = ""
    request_schema: Optional[str] = None
    response_schema: Optional[str] = None
    responses: List[str] = Field(default_factory=list)       # коды ответов из спецификации
    parameters: List[Parameter] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)


class ParsedOpenAPI(BaseModel):
    """Результат парсинга OpenAPI-спецификации."""
    title: str = ""
    version: str = ""
    schemas: List[Schema]
    endpoints: List[Endpoint]
    base_path: str = ""
