from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class Visibility(str, Enum):
    PRIVATE = "private"
    ORGANIZATION = "organization"
    PUBLIC = "public"


class ChannelType(str, Enum):
    EEG = "eeg"
    EOG = "eog"
    ECG = "ecg"
    EMG = "emg"
    ACCEL = "accelerometer"
    GYRO = "gyroscope"
    TRIGGER = "trigger"
    GSR = "gsr"
    RESPIRATION = "respiration"
    EYE_TRACKING = "eye_tracking"
    MISC = "misc"


class ChannelStatus(str, Enum):
    GOOD = "good"
    BAD = "bad"
    UNKNOWN = "unknown"


class ChannelLocation(BaseModel):
    x: float | None = None
    y: float | None = None
    z: float | None = None
    coordinate_frame: str | None = None
    source: str | None = None  # standard | imported | custom


class Channel(BaseModel):
    id: str = Field(default_factory=lambda: _id("ch"))
    name: str
    type: ChannelType = ChannelType.EEG
    unit: str | None = "uV"
    location: ChannelLocation | None = None
    reference: str | None = None
    status: ChannelStatus = ChannelStatus.UNKNOWN
    metadata: dict[str, Any] = Field(default_factory=dict)


class Event(BaseModel):
    id: str = Field(default_factory=lambda: _id("ev"))
    timestamp: float
    sample_index: int
    duration: float = 0.0
    code: str | None = None
    name: str
    condition: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Annotation(BaseModel):
    id: str = Field(default_factory=lambda: _id("ann"))
    kind: str  # continuous | channel | epoch | ica_component
    label: str
    start: float | None = None
    end: float | None = None
    channel_ids: list[str] = Field(default_factory=list)
    epoch_indices: list[int] = Field(default_factory=list)
    component_indices: list[int] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)


class HumanDecision(BaseModel):
    id: str = Field(default_factory=lambda: _id("dec"))
    target_kind: str
    target_id: str
    action: str  # accept | reject | keep | label | mark_bad | mark_good
    label: str | None = None
    recommendation_id: str | None = None
    reason: str | None = None
    created_at: datetime = Field(default_factory=_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Recording(BaseModel):
    id: str = Field(default_factory=lambda: _id("rec"))
    subject_id: str
    session_id: str
    run_id: str
    source_files: list[str] = Field(default_factory=list)
    source_format: str | None = None
    sampling_rate: float | None = None
    duration: float | None = None
    channel_count: int = 0
    channels: list[Channel] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    annotations: list[Annotation] = Field(default_factory=list)
    decisions: list[HumanDecision] = Field(default_factory=list)
    acquisition_metadata: dict[str, Any] = Field(default_factory=dict)
    preprocessing_state: dict[str, Any] = Field(default_factory=dict)
    parent_artifact_id: str | None = None
    artifact_id: str | None = None
    created_at: datetime = Field(default_factory=_now)


class Run(BaseModel):
    id: str = Field(default_factory=lambda: _id("run"))
    name: str = "run-001"
    recordings: list[Recording] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Session(BaseModel):
    id: str = Field(default_factory=lambda: _id("ses"))
    name: str = "session-001"
    runs: list[Run] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Subject(BaseModel):
    id: str = Field(default_factory=lambda: _id("sub"))
    label: str
    sessions: list[Session] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProcessingStep(BaseModel):
    id: str = Field(default_factory=lambda: _id("step"))
    operation: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    input_requirements: list[str] = Field(default_factory=list)
    output_type: str = "recording_artifact"


class ProcessingPlan(BaseModel):
    id: str = Field(default_factory=lambda: _id("plan"))
    name: str
    version: int = 1
    steps: list[ProcessingStep] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
    notes: str | None = None


class DatasetArtifact(BaseModel):
    id: str = Field(default_factory=lambda: _id("art"))
    type: str
    parent_id: str | None = None
    source: str | None = None
    operation: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    application_version: str = "0.1.0"
    algorithm_version: str | None = None
    checksum: str | None = None
    paths: dict[str, str] = Field(default_factory=dict)
    recording_id: str | None = None
    study_id: str | None = None


class Experiment(BaseModel):
    id: str = Field(default_factory=lambda: _id("exp"))
    study_id: str
    input_artifact_id: str | None = None
    preprocessing_plan_id: str | None = None
    template_id: str | None = None
    split_definition: dict[str, Any] = Field(default_factory=dict)
    model: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    random_seed: int | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    checkpoints: list[str] = Field(default_factory=list)
    results: dict[str, Any] = Field(default_factory=dict)
    export_package_ref: str | None = None
    created_at: datetime = Field(default_factory=_now)


class ModelRecord(BaseModel):
    id: str = Field(default_factory=lambda: _id("mdl"))
    experiment_id: str
    template_id: str | None = None
    paths: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)


class Prediction(BaseModel):
    id: str = Field(default_factory=lambda: _id("pred"))
    model_id: str
    target_ref: str
    outputs: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)


class Result(BaseModel):
    id: str = Field(default_factory=lambda: _id("res"))
    experiment_id: str
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)


class RecommendationResult(BaseModel):
    recommendations: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    confidence: float | None = None
    explanation: str | None = None


class InspectionReport(BaseModel):
    study_id: str | None = None
    subjects: int = 0
    sessions: int = 0
    recordings: int = 0
    sampling_rates: dict[str, int] = Field(default_factory=dict)
    channel_counts: dict[str, int] = Field(default_factory=dict)
    event_types: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class Study(BaseModel):
    id: str = Field(default_factory=lambda: _id("study"))
    name: str
    task_name: str | None = None
    notes: str | None = None
    subjects: list[Subject] = Field(default_factory=list)
    event_definitions: dict[str, str] = Field(default_factory=dict)
    channel_definitions: dict[str, Any] = Field(default_factory=dict)
    plan_ids: list[str] = Field(default_factory=list)
    artifact_ids: list[str] = Field(default_factory=list)
    experiment_ids: list[str] = Field(default_factory=list)
    visibility: Visibility = Visibility.PRIVATE
    organization_id: str | None = None
    hub_uri: str | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
