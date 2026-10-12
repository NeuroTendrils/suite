from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from suite_backend.ipc.protocol import RpcRequest, RpcResponse

P = TypeVar("P", bound=BaseModel)

logger = logging.getLogger(__name__)


class CommandSpec:
    def __init__(
        self,
        name: str,
        params_model: type[BaseModel],
        handler: Callable[[BaseModel, Any], Any],
    ) -> None:
        self.name = name
        self.params_model = params_model
        self.handler = handler


class CommandRegistry:
    def __init__(self) -> None:
        self._commands: dict[str, CommandSpec] = {}

    def register(
        self,
        name: str,
        params_model: type[BaseModel],
    ) -> Callable[[Callable[[BaseModel, Any], Any]], Callable[[BaseModel, Any], Any]]:
        def decorator(fn: Callable[[BaseModel, Any], Any]) -> Callable[[BaseModel, Any], Any]:
            self._commands[name] = CommandSpec(name, params_model, fn)
            return fn

        return decorator

    def allowlist(self) -> list[str]:
        return sorted(self._commands)

    def dispatch(self, request: RpcRequest, ctx: Any) -> RpcResponse:
        spec = self._commands.get(request.command)
        if spec is None:
            return RpcResponse(
                id=request.id,
                ok=False,
                error=f"command not allowlisted: {request.command}",
            )
        try:
            params = spec.params_model.model_validate(request.params)
        except ValidationError as exc:
            return RpcResponse(id=request.id, ok=False, error=f"invalid params: {exc}")
        try:
            result = spec.handler(params, ctx)
        except Exception as exc:  # boundary; logged and structured to client
            logger.exception("command %s (request %s) failed", request.command, request.id)
            return RpcResponse(id=request.id, ok=False, error=str(exc))
        if isinstance(result, BaseModel):
            payload = result.model_dump(mode="json")
        else:
            payload = result
        return RpcResponse(id=request.id, ok=True, result=payload)


REGISTRY = CommandRegistry()
