from __future__ import annotations

import json
from pathlib import Path

from suite_backend.domain.migrate import migrate_study_dict, needs_migration
from suite_backend.domain.models import (
    AnalysisReport,
    DataSplit,
    DataStream,
    DatasetArtifact,
    EpochSet,
    Experiment,
    FeatureSet,
    MLDataset,
    ModelRecord,
    Prediction,
    ProcessingPlan,
    Result,
    Study,
    SyncGroup,
)


class LocalWorkspace:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.studies_dir = self.root / "studies"
        self.studies_dir.mkdir(parents=True, exist_ok=True)

    def study_dir(self, study_id: str) -> Path:
        path = self.studies_dir / study_id
        path.mkdir(parents=True, exist_ok=True)
        for sub in (
            "subjects",
            "artifacts",
            "streams",
            "sync",
            "epochs",
            "features",
            "datasets",
            "plans",
            "experiments",
            "models",
            "results",
            "reports",
            "logs",
        ):
            (path / sub).mkdir(exist_ok=True)
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
            study_id = path.parent.name
            studies.append(self.get_study(study_id))
        return studies

    def _study_path(self, study_id: str) -> Path:
        return self.workspace.study_dir(study_id) / "study.json"

    def _load_study_raw(self, study_id: str) -> dict:
        path = self._study_path(study_id)
        if not path.exists():
            raise KeyError(f"study not found: {study_id}")
        return _read_json(path)

    def get_study(self, study_id: str) -> Study:
        raw = self._load_study_raw(study_id)
        if needs_migration(raw):
            study, new_streams = migrate_study_dict(raw)
            for stream in new_streams:
                self._write_stream_file(study_id, stream)
            return self.save_study(study)
        return Study.model_validate(raw)

    def save_study(self, study: Study) -> Study:
        _write_json(self._study_path(study.id), study.model_dump(mode="json"))
        return study

    def create_study(self, name: str, task_name: str | None = None) -> Study:
        study = Study(name=name, task_name=task_name)
        return self.save_study(study)

    def _write_stream_file(self, study_id: str, stream: DataStream) -> None:
        path = self.workspace.study_dir(study_id) / "streams" / f"{stream.id}.json"
        _write_json(path, stream.model_dump(mode="json"))

    def save_stream(self, study_id: str, stream: DataStream) -> DataStream:
        self._write_stream_file(study_id, stream)
        study = Study.model_validate(self._load_study_raw(study_id))
        dirty = False
        if stream.id not in study.stream_ids:
            study.stream_ids.append(stream.id)
            dirty = True
        for subject in study.subjects:
            for session in subject.sessions:
                for run in session.runs:
                    for rec in run.recordings:
                        if rec.id == stream.recording_id and stream.id not in rec.stream_ids:
                            rec.stream_ids.append(stream.id)
                            dirty = True
        if dirty:
            self.save_study(study)
        return stream

    def get_stream(self, study_id: str, stream_id: str) -> DataStream:
        path = self.workspace.study_dir(study_id) / "streams" / f"{stream_id}.json"
        if not path.exists():
            raise KeyError(f"stream not found: {stream_id}")
        return DataStream.model_validate(_read_json(path))

    def list_streams(
        self,
        study_id: str,
        *,
        recording_id: str | None = None,
        subject_id: str | None = None,
    ) -> list[DataStream]:
        root = self.workspace.study_dir(study_id) / "streams"
        streams = [
            DataStream.model_validate(_read_json(p)) for p in sorted(root.glob("*.json"))
        ]
        if recording_id is not None:
            streams = [s for s in streams if s.recording_id == recording_id]
        if subject_id is not None:
            streams = [s for s in streams if s.subject_id == subject_id]
        return streams

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

    def save_sync_group(self, study_id: str, group: SyncGroup) -> SyncGroup:
        path = self.workspace.study_dir(study_id) / "sync" / f"{group.id}.json"
        _write_json(path, group.model_dump(mode="json"))
        study = Study.model_validate(self._load_study_raw(study_id))
        dirty = False
        for subject in study.subjects:
            for session in subject.sessions:
                for run in session.runs:
                    for rec in run.recordings:
                        if rec.id != group.recording_id:
                            continue
                        if group.id not in rec.sync_group_ids:
                            rec.sync_group_ids.append(group.id)
                            dirty = True
                        for link in group.links:
                            # stamp sync_group_id on stream files
                            try:
                                stream = self.get_stream(study_id, link.stream_id)
                                if stream.sync_group_id != group.id:
                                    stream.sync_group_id = group.id
                                    self._write_stream_file(study_id, stream)
                            except KeyError:
                                pass
        if dirty:
            self.save_study(study)
        return group

    def get_sync_group(self, study_id: str, sync_group_id: str) -> SyncGroup:
        path = self.workspace.study_dir(study_id) / "sync" / f"{sync_group_id}.json"
        if not path.exists():
            raise KeyError(f"sync group not found: {sync_group_id}")
        return SyncGroup.model_validate(_read_json(path))

    def list_sync_groups(
        self, study_id: str, *, recording_id: str | None = None
    ) -> list[SyncGroup]:
        root = self.workspace.study_dir(study_id) / "sync"
        groups = [
            SyncGroup.model_validate(_read_json(p)) for p in sorted(root.glob("*.json"))
        ]
        if recording_id is not None:
            groups = [g for g in groups if g.recording_id == recording_id]
        return groups

    def save_epochset(self, study_id: str, epochset: EpochSet) -> EpochSet:
        path = self.workspace.study_dir(study_id) / "epochs" / f"{epochset.id}.json"
        _write_json(path, epochset.model_dump(mode="json"))
        return epochset

    def get_epochset(self, study_id: str, epochset_id: str) -> EpochSet:
        path = self.workspace.study_dir(study_id) / "epochs" / f"{epochset_id}.json"
        if not path.exists():
            raise KeyError(f"epochset not found: {epochset_id}")
        return EpochSet.model_validate(_read_json(path))

    def list_epochsets(
        self, study_id: str, *, recording_id: str | None = None
    ) -> list[EpochSet]:
        root = self.workspace.study_dir(study_id) / "epochs"
        sets = [
            EpochSet.model_validate(_read_json(p)) for p in sorted(root.glob("*.json"))
        ]
        if recording_id is not None:
            sets = [e for e in sets if e.recording_id == recording_id]
        return sets

    def save_featureset(self, study_id: str, featureset: FeatureSet) -> FeatureSet:
        path = self.workspace.study_dir(study_id) / "features" / f"{featureset.id}.json"
        _write_json(path, featureset.model_dump(mode="json"))
        return featureset

    def get_featureset(self, study_id: str, featureset_id: str) -> FeatureSet:
        path = self.workspace.study_dir(study_id) / "features" / f"{featureset_id}.json"
        if not path.exists():
            raise KeyError(f"featureset not found: {featureset_id}")
        return FeatureSet.model_validate(_read_json(path))

    def list_featuresets(
        self, study_id: str, *, recording_id: str | None = None
    ) -> list[FeatureSet]:
        root = self.workspace.study_dir(study_id) / "features"
        sets = [
            FeatureSet.model_validate(_read_json(p)) for p in sorted(root.glob("*.json"))
        ]
        if recording_id is not None:
            sets = [f for f in sets if f.recording_id == recording_id]
        return sets

    def save_analysis(self, study_id: str, report: AnalysisReport) -> AnalysisReport:
        path = self.workspace.study_dir(study_id) / "reports" / f"{report.id}.json"
        _write_json(path, report.model_dump(mode="json"))
        return report

    def get_analysis(self, study_id: str, report_id: str) -> AnalysisReport:
        path = self.workspace.study_dir(study_id) / "reports" / f"{report_id}.json"
        if not path.exists():
            raise KeyError(f"analysis report not found: {report_id}")
        return AnalysisReport.model_validate(_read_json(path))

    def list_analyses(
        self, study_id: str, *, recording_id: str | None = None
    ) -> list[AnalysisReport]:
        root = self.workspace.study_dir(study_id) / "reports"
        reports = [
            AnalysisReport.model_validate(_read_json(p))
            for p in sorted(root.glob("anl_*.json"))
        ]
        if recording_id is not None:
            reports = [r for r in reports if r.recording_id == recording_id]
        return reports

    def save_mldataset(self, study_id: str, dataset: MLDataset) -> MLDataset:
        path = self.workspace.study_dir(study_id) / "datasets" / f"{dataset.id}.json"
        _write_json(path, dataset.model_dump(mode="json"))
        return dataset

    def get_mldataset(self, study_id: str, dataset_id: str) -> MLDataset:
        path = self.workspace.study_dir(study_id) / "datasets" / f"{dataset_id}.json"
        if not path.exists():
            raise KeyError(f"dataset not found: {dataset_id}")
        return MLDataset.model_validate(_read_json(path))

    def list_mldatasets(self, study_id: str) -> list[MLDataset]:
        root = self.workspace.study_dir(study_id) / "datasets"
        return [
            MLDataset.model_validate(_read_json(p))
            for p in sorted(root.glob("mlds_*.json"))
        ]

    def save_split(self, study_id: str, split: DataSplit) -> DataSplit:
        path = self.workspace.study_dir(study_id) / "datasets" / f"{split.id}.json"
        _write_json(path, split.model_dump(mode="json"))
        return split

    def get_split(self, study_id: str, split_id: str) -> DataSplit:
        path = self.workspace.study_dir(study_id) / "datasets" / f"{split_id}.json"
        if not path.exists():
            raise KeyError(f"split not found: {split_id}")
        return DataSplit.model_validate(_read_json(path))

    def list_splits(self, study_id: str, *, dataset_id: str | None = None) -> list[DataSplit]:
        root = self.workspace.study_dir(study_id) / "datasets"
        splits = [
            DataSplit.model_validate(_read_json(p))
            for p in sorted(root.glob("split_*.json"))
        ]
        if dataset_id is not None:
            splits = [s for s in splits if s.dataset_id == dataset_id]
        return splits

    def save_experiment(self, study_id: str, experiment: Experiment) -> Experiment:
        path = self.workspace.study_dir(study_id) / "experiments" / f"{experiment.id}.json"
        _write_json(path, experiment.model_dump(mode="json"))
        return experiment

    def get_experiment(self, study_id: str, experiment_id: str) -> Experiment:
        path = self.workspace.study_dir(study_id) / "experiments" / f"{experiment_id}.json"
        if not path.exists():
            raise KeyError(f"experiment not found: {experiment_id}")
        return Experiment.model_validate(_read_json(path))

    def list_experiments(self, study_id: str) -> list[Experiment]:
        root = self.workspace.study_dir(study_id) / "experiments"
        return [
            Experiment.model_validate(_read_json(p)) for p in sorted(root.glob("*.json"))
        ]

    def save_model(self, study_id: str, model: ModelRecord) -> ModelRecord:
        path = self.workspace.study_dir(study_id) / "models" / f"{model.id}.json"
        _write_json(path, model.model_dump(mode="json"))
        return model

    def get_model(self, study_id: str, model_id: str) -> ModelRecord:
        path = self.workspace.study_dir(study_id) / "models" / f"{model_id}.json"
        if not path.exists():
            raise KeyError(f"model not found: {model_id}")
        return ModelRecord.model_validate(_read_json(path))

    def list_models(self, study_id: str, *, experiment_id: str | None = None) -> list[ModelRecord]:
        root = self.workspace.study_dir(study_id) / "models"
        models = [
            ModelRecord.model_validate(_read_json(p)) for p in sorted(root.glob("mdl_*.json"))
        ]
        if experiment_id is not None:
            models = [m for m in models if m.experiment_id == experiment_id]
        return models

    def save_prediction(self, study_id: str, prediction: Prediction) -> Prediction:
        path = self.workspace.study_dir(study_id) / "results" / f"{prediction.id}.json"
        _write_json(path, prediction.model_dump(mode="json"))
        return prediction

    def save_result(self, study_id: str, result: Result) -> Result:
        path = self.workspace.study_dir(study_id) / "results" / f"{result.id}.json"
        _write_json(path, result.model_dump(mode="json"))
        return result

    def list_results(self, study_id: str, *, experiment_id: str | None = None) -> list[Result]:
        root = self.workspace.study_dir(study_id) / "results"
        results = [
            Result.model_validate(_read_json(p)) for p in sorted(root.glob("res_*.json"))
        ]
        if experiment_id is not None:
            results = [r for r in results if r.experiment_id == experiment_id]
        return results
