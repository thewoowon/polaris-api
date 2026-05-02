from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    """Base for schemas that are built from SQLAlchemy model instances."""

    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int = Field(20, ge=1, le=200)
    offset: int = Field(0, ge=0)


class PageParams(BaseModel):
    limit: int = Field(20, ge=1, le=200)
    offset: int = Field(0, ge=0)
