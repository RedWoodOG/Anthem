"""
Pydantic v1/v2 compatibility layer.
Every file in Anthem imports these instead of writing its own shims.
"""

from typing import Any, Dict

from pydantic import BaseModel

try:
    from pydantic import ConfigDict, field_validator

    PYDANTIC_V2 = True
except ImportError:
    from pydantic import validator as field_validator  # type: ignore[assignment]

    ConfigDict = None  # type: ignore[assignment,misc]
    PYDANTIC_V2 = False


def model_copy(instance: BaseModel, **kwargs: Any) -> BaseModel:
    """Copy a model instance, compatible with Pydantic v1 and v2."""
    if hasattr(instance, "model_copy"):
        return instance.model_copy(**kwargs)
    return instance.copy(**kwargs)  # type: ignore[call-arg]


def model_dump(instance: BaseModel) -> Dict[str, Any]:
    """Serialize a model instance, compatible with Pydantic v1 and v2."""
    if hasattr(instance, "model_dump"):
        return instance.model_dump()
    return instance.dict()  # type: ignore[union-attr]


def model_dump_json_safe(instance: BaseModel) -> Dict[str, Any]:
    """Serialize a model to a JSON-safe dict (datetimes as ISO strings, etc.)."""
    from fastapi.encoders import jsonable_encoder

    return jsonable_encoder(model_dump(instance))
