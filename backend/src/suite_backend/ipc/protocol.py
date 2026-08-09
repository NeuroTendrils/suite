from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RpcRequest(BaseModel):
    id: str
    command: str
    params: dict[str, Any] = Field(default_factory=dict)


class RpcResponse(BaseModel):
    id: str
    ok: bool
    result: Any = None
    error: str | None = None
