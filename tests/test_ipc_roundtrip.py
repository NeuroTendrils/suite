#!/usr/bin/env python3
"""End-to-end JSON-lines round-trip against NeuroFlow ipc (argv-only).

Run from the suite repo root:

    PYTHONPATH=workers/_shared:workers/neuroflow \\
      .venv/bin/python tests/test_ipc_roundtrip.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEUROFLOW = ROOT / "workers" / "neuroflow"
SHARED = ROOT / "workers" / "_shared"


def python_executable() -> str:
    venv = ROOT / ".venv" / "bin" / "python"
    if venv.exists():
        return str(venv)
    venv_win = ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_win.exists():
        return str(venv_win)
    return sys.executable


def run_ipc(requests: list[dict]) -> list[dict]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(SHARED), str(NEUROFLOW)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    env["PYTHONUNBUFFERED"] = "1"

    payload = "".join(json.dumps(req, separators=(",", ":")) + "\n" for req in requests)
    completed = subprocess.run(
        [python_executable(), "-m", "neuroflow", "ipc"],
        input=payload,
        text=True,
        capture_output=True,
        env=env,
        cwd=str(ROOT),
        check=False,
        timeout=20,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"neuroflow ipc exited {completed.returncode}\n"
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )

    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


class IpcRoundTripTests(unittest.TestCase):
    def test_ping_and_echo(self) -> None:
        responses = run_ipc(
            [
                {"v": 1, "id": "r-ping", "cmd": "ping", "args": {}},
                {"v": 1, "id": "r-echo", "cmd": "echo", "args": {"hello": "suite"}},
            ]
        )
        self.assertEqual(len(responses), 2)

        ping, echo = responses
        self.assertTrue(ping["ok"])
        self.assertEqual(ping["id"], "r-ping")
        self.assertTrue(ping["result"]["pong"])
        self.assertEqual(ping["result"]["worker"], "neuroflow")

        self.assertTrue(echo["ok"])
        self.assertEqual(echo["id"], "r-echo")
        self.assertEqual(echo["result"]["echo"], {"hello": "suite"})

    def test_unknown_command_error_envelope(self) -> None:
        responses = run_ipc(
            [{"v": 1, "id": "r-bad", "cmd": "not-a-command", "args": {}}]
        )
        self.assertEqual(len(responses), 1)
        err = responses[0]
        self.assertFalse(err["ok"])
        self.assertEqual(err["error"]["code"], "unknown_command")


if __name__ == "__main__":
    unittest.main()
