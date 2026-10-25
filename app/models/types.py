"""Tipos personalizados compartidos entre modelos."""
import json
from typing import Any

from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import JSON, String, TypeDecorator, TypeEngine


class ArrayType(TypeDecorator[list[Any]]):
    """Custom type que almacena arrays como JSON en SQLite y como ARRAY
    nativo en PostgreSQL. Misma implementación en `app.models.product`
    y `app.models.promotion`; consolidada aquí (S3-T6).
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(String))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: list[Any] | None, dialect: Dialect) -> str | list[Any] | None:
        if dialect.name == "postgresql":
            return value
        if value is None:
            return None
        return json.dumps(value) if isinstance(value, list) else value

    def process_result_value(self, value: str | list[Any] | None, dialect: Dialect) -> list[Any] | None:
        if dialect.name == "postgresql":
            return value if isinstance(value, list) else []
        if value is None:
            return None
        if isinstance(value, str):
            try:
                loaded: list[Any] = json.loads(value)
                return loaded
            except json.JSONDecodeError:
                return []
        return list(value) if isinstance(value, list) else []
