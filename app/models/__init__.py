"""Shared base model for all API models."""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base model that serializes to camelCase and accepts both camelCase and snake_case input."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )
