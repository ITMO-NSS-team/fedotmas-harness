from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Recipe(BaseModel):
    """Coordinates of a coordination structure on five orthogonal axes."""

    model_config = {"extra": "forbid"}

    decompose: Literal["none", "pipeline", "master"] = "none"
    cooperate: Literal["none", "shared"] = "none"
    width: int = Field(default=1, ge=1, le=5)
    iterate: int = Field(default=0, ge=0, le=3)
    verify: Literal["none", "judge", "critic"] = "none"


AXES = tuple(Recipe.model_fields)
