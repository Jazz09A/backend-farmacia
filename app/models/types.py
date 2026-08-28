"""Tipos personalizados compartidos entre modelos."""
import json

from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.types import JSON, String, TypeDecorator


class ArrayType(TypeDecorator):
    """Custom type que almacena arrays como JSON en SQLite y como ARRAY
    nativo en PostgreSQL. Misma implementación en `app.models.product`
    y `app.models.promotion`; consolidada aquí (S3-T6).
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(ARRAY(String))
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value, dialect):
        if dialect.name == "postgresql":
            return value
        if value is None:
            return None
        return json.dumps(value) if isinstance(value, list) else value

    def process_result_value(self, value, dialect):
        if dialect.name == "postgresql":
            return value
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass
        return value if isinstance(value, list) else []


__all__ = ["ArrayType"]
