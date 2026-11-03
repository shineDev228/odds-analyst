"""Schémas génériques."""

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    """Base des schémas lus depuis les objets SQLAlchemy."""

    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):  # noqa: UP046 - syntaxe PEP 695 encore peu supportée par Pydantic
    items: list[T]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)


class Message(BaseModel):
    message: str
