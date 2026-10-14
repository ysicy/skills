from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class SchemaField(BaseModel):
    """Модель поля OpenAPI-схемы."""
    name: str
    type: str
    is_required: bool = False
    description: Optional[str] = None
    default: Optional[Any] = None
    nested: Optional[List['SchemaField']] = None
    items_type: Optional[str] = None


class Schema(BaseModel):
    """Модель OpenAPI-схемы."""
    name: str
    fields: List[SchemaField]
    description: Optional[str] = None


class Endpoint(BaseModel):
    """Модель OpenAPI-эндпоинта."""
    path: str
    method: str
    summary: str = ""
    description: str = ""
    request_schema: Optional[str] = None
    response_schema: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class ParsedOpenAPI(BaseModel):
    """Результат парсинга OpenAPI-спецификации."""
    title: str = ""
    version: str = ""
    schemas: List[Schema]
    endpoints: List[Endpoint]
    base_path: str = ""