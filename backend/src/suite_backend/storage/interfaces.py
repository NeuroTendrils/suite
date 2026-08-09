from __future__ import annotations

from typing import Protocol

from suite_backend.domain.models import (
    DatasetArtifact,
    Experiment,
    ModelRecord,
    ProcessingPlan,
    Study,
)


class StorageProvider(Protocol):
    def read_bytes(self, path: str) -> bytes: ...
    def write_bytes(self, path: str, data: bytes) -> None: ...
    def exists(self, path: str) -> bool: ...


class StudyRepository(Protocol):
    def list_studies(self) -> list[Study]: ...
    def get_study(self, study_id: str) -> Study: ...
    def save_study(self, study: Study) -> Study: ...
    def create_study(self, name: str, task_name: str | None = None) -> Study: ...


class ArtifactRepository(Protocol):
    def get(self, study_id: str, artifact_id: str) -> DatasetArtifact: ...
    def save(self, artifact: DatasetArtifact) -> DatasetArtifact: ...
    def list_for_study(self, study_id: str) -> list[DatasetArtifact]: ...


class PlanRepository(Protocol):
    def get(self, study_id: str, plan_id: str, version: int | None = None) -> ProcessingPlan: ...
    def save(self, study_id: str, plan: ProcessingPlan) -> ProcessingPlan: ...
    def list_for_study(self, study_id: str) -> list[ProcessingPlan]: ...


class ModelRepository(Protocol):
    def get(self, study_id: str, model_id: str) -> ModelRecord: ...
    def save(self, study_id: str, model: ModelRecord) -> ModelRecord: ...


class SharingProvider(Protocol):
    """Future Hub publishing. Not implemented locally."""

    def publish(self, *args, **kwargs): ...


class QuotaProvider(Protocol):
    """Future Hub quota (default 1 GB). Not implemented locally."""

    def get_quota(self, *args, **kwargs): ...


class TeamRepository(Protocol):
    """Future Teams private sharing. Not implemented locally."""

    def list_teams(self, *args, **kwargs): ...


class HubPublisher(Protocol):
    def upload_bundle(self, *args, **kwargs): ...


class HubClient(Protocol):
    def download_bundle(self, *args, **kwargs): ...
