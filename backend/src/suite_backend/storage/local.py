from __future__ import annotations

import json
from pathlib import Path

from suite_backend.domain.models import (
    DatasetArtifact,
    ProcessingPlan,
    Study,
)


class LocalWorkspace:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.studies_dir = self.root / "studies"
        self.studies_dir.mkdir(parents=True, exist_ok=True)

    def study_dir(self, study_id: str) -> Path:
        path = self.studies_dir / study_id
        path.mkdir(parents=True, exist_ok=True)
        (path / "subjects").mkdir(exist_ok=True)
        (path / "artifacts").mkdir(exist_ok=True)
        (path / "plans").mkdir(exist_ok=True)
        (path / "experiments").mkdir(exist_ok=True)
        (path / "models").mkdir(exist_ok=True)
        (path / "results").mkdir(exist_ok=True)
        (path / "logs").mkdir(exist_ok=True)
        return path

    def ensure_inside(self, path: Path) -> Path:
        resolved = path.expanduser().resolve()
        if not str(resolved).startswith(str(self.root)):
            raise ValueError("path escapes workspace root")
        return resolved


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class LocalStudyRepository:
    def __init__(self, workspace: LocalWorkspace) -> None:
        self.workspace = workspace

    def list_studies(self) -> list[Study]:
        studies: list[Study] = []
        for path in sorted(self.workspace.studies_dir.glob("*/study.json")):
            studies.append(Study.model_validate(_read_json(path)))
        return studies

    def get_study(self, study_id: str) -> Study:
        path = self.workspace.study_dir(study_id) / "study.json"
        if not path.exists():
            raise KeyError(f"study not found: {study_id}")
        return Study.model_validate(_read_json(path))

    def save_study(self, study: Study) -> Study:
        path = self.workspace.study_dir(study.id) / "study.json"
        _write_json(path, study.model_dump(mode="json"))
        return study

    def create_study(self, name: str, task_name: str | None = None) -> Study:
        study = Study(name=name, task_name=task_name)
        return self.save_study(study)

    def save_artifact(self, artifact: DatasetArtifact) -> DatasetArtifact:
        if not artifact.study_id:
            raise ValueError("artifact.study_id required")
        path = self.workspace.study_dir(artifact.study_id) / "artifacts" / f"{artifact.id}.json"
        _write_json(path, artifact.model_dump(mode="json"))
        study = self.get_study(artifact.study_id)
        if artifact.id not in study.artifact_ids:
            study.artifact_ids.append(artifact.id)
            self.save_study(study)
        return artifact

    def list_artifacts(self, study_id: str) -> list[DatasetArtifact]:
        root = self.workspace.study_dir(study_id) / "artifacts"
        return [
            DatasetArtifact.model_validate(_read_json(p))
            for p in sorted(root.glob("*.json"))
        ]

    def save_plan(self, study_id: str, plan: ProcessingPlan) -> ProcessingPlan:
        plan_dir = self.workspace.study_dir(study_id) / "plans" / plan.id
        plan_dir.mkdir(parents=True, exist_ok=True)
        path = plan_dir / f"v{plan.version}.json"
        _write_json(path, plan.model_dump(mode="json"))
        study = self.get_study(study_id)
        if plan.id not in study.plan_ids:
            study.plan_ids.append(plan.id)
            self.save_study(study)
        return plan

    def list_plans(self, study_id: str) -> list[ProcessingPlan]:
        plans: list[ProcessingPlan] = []
        root = self.workspace.study_dir(study_id) / "plans"
        for plan_dir in sorted(root.glob("*")):
            versions = sorted(plan_dir.glob("v*.json"))
            if not versions:
                continue
            plans.append(ProcessingPlan.model_validate(_read_json(versions[-1])))
        return plans
