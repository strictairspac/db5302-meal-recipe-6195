from typing import Any

from pydantic import BaseModel, Field


class LoginForm(BaseModel):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=128)


class CaseForm(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    payload: dict[str, Any]


class ReviewForm(BaseModel):
    note: str = Field(min_length=1, max_length=500)


class LotForm(BaseModel):
    ingredient: str = Field(min_length=1, max_length=32)
    lot: str = Field(min_length=1, max_length=32)


class InputForm(BaseModel):
    ingredient: str | None = Field(default=None, max_length=32)
    lot: str | None = Field(default=None, max_length=32)
    semi_batch: str | None = Field(default=None, max_length=32)
    quantity: Any


class ProductionForm(BaseModel):
    batch: str = Field(min_length=1, max_length=32)
    kind: str = Field(min_length=1, max_length=8)
    recipe: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=80)
    unit: str = Field(min_length=1, max_length=12)
    quantity: Any
    inputs: list[InputForm] = Field(min_length=1, max_length=200)
