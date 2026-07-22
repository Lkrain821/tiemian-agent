"""Public response envelopes shared by every JSON endpoint."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApiResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    data: dict[str, Any] = Field(default_factory=dict)

