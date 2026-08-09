from __future__ import annotations

from pydantic import BaseModel, Field

from suite_backend import __version__
from suite_backend.app_context import AppContext
from suite_backend.ipc.registry import REGISTRY


class EmptyParams(BaseModel):
    pass


class WorkspaceInfoParams(BaseModel):
    pass


@REGISTRY.register("health", EmptyParams)
def health(_params: EmptyParams, _ctx: AppContext) -> dict:
    return {"status": "ok", "version": __version__}


@REGISTRY.register("workspace.info", WorkspaceInfoParams)
def workspace_info(_params: WorkspaceInfoParams, ctx: AppContext) -> dict:
    return {
        "root": str(ctx.workspace.root),
        "studies": len(ctx.studies.list_studies()),
        "commands": REGISTRY.allowlist(),
    }


class CommandsListParams(BaseModel):
    pass


@REGISTRY.register("commands.list", CommandsListParams)
def commands_list(_params: CommandsListParams, _ctx: AppContext) -> dict:
    return {"commands": REGISTRY.allowlist()}
