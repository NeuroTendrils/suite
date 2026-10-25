from pydantic import BaseModel, Field

from suite_backend.app_context import AppContext
from suite_backend.devices.cortex import capture_insight
from suite_backend.ipc.registry import REGISTRY


class CaptureParams(BaseModel):
    study_id: str
    seconds: int = Field(default=10, ge=2, le=30)
    consent_to_record: bool = False


@REGISTRY.register("insight.capture", CaptureParams)
def capture(params: CaptureParams, ctx: AppContext) -> dict:
    if not params.consent_to_record:
        raise ValueError("Explicit consent to record EEG is required")
    ctx.studies.get_study(params.study_id)
    return capture_insight(ctx.workspace.study_dir(params.study_id) / "captures", params.seconds)
