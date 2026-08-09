from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from suite_backend.app_context import AppContext
from suite_backend.ipc.client import IpcClient
from suite_backend.ipc.protocol import RpcRequest
from suite_backend.ipc.registry import REGISTRY
from suite_backend.ipc import handlers  # noqa: F401
from suite_backend.ipc.server import serve_ipc
from suite_backend.neurostudio.templates import catalog
from suite_backend.storage.local import LocalStudyRepository, LocalWorkspace


def test_create_multi_subject_study(tmp_path: Path) -> None:
    repo = LocalStudyRepository(LocalWorkspace(tmp_path))
    study = repo.create_study("Motor Imagery", task_name="MI")
    assert study.id.startswith("study_")

    from suite_backend.ipc.handlers.study_cmds import SubjectAddParams, subjects_add

    ctx = AppContext(tmp_path)
    # recreate study in ctx workspace
    study = ctx.studies.create_study("Motor Imagery")
    a = subjects_add(
        SubjectAddParams(study_id=study.id, label="S001"),
        ctx,
    )
    b = subjects_add(
        SubjectAddParams(study_id=study.id, label="S002"),
        ctx,
    )
    loaded = ctx.studies.get_study(study.id)
    assert len(loaded.subjects) == 2
    assert a["subject"]["label"] == "S001"
    assert b["subject"]["label"] == "S002"


def test_command_allowlist_dispatch(tmp_path: Path) -> None:
    ctx = AppContext(tmp_path)
    resp = REGISTRY.dispatch(
        RpcRequest(id="1", command="health", params={}),
        ctx,
    )
    assert resp.ok
    assert resp.result["status"] == "ok"

    bad = REGISTRY.dispatch(
        RpcRequest(id="2", command="rm -rf /", params={}),
        ctx,
    )
    assert not bad.ok
    assert "not allowlisted" in (bad.error or "")


def test_templates_include_eegnet() -> None:
    ids = {t["id"] for t in catalog.list_templates()}
    assert "eegnet" in ids
    assert "shallow_fbcsp" in ids


def test_uds_roundtrip(tmp_path: Path) -> None:
    # AF_UNIX paths have a low length limit; keep socket under /tmp.
    ipc = Path(f"/tmp/suite-test-{tmp_path.name}.sock")
    if ipc.exists():
        ipc.unlink()
    workspace = tmp_path / "workspace"
    thread = threading.Thread(
        target=serve_ipc,
        kwargs={"ipc_path": str(ipc), "workspace_root": str(workspace)},
        daemon=True,
    )
    thread.start()
    for _ in range(50):
        if ipc.exists():
            break
        time.sleep(0.05)
    assert ipc.exists()
    try:
        client = IpcClient(str(ipc))
        health = client.call("health")
        assert health.ok
        created = client.call("studies.create", {"name": "Demo"})
        assert created.ok
        assert created.result["name"] == "Demo"
    finally:
        if ipc.exists():
            ipc.unlink()
