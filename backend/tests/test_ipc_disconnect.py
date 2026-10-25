"""Regression tests: the IPC server must survive clients that disconnect.

Reproduces the original crash: the Rust bridge gives up on a slow request (read timeout),
closes its socket, and the backend later dies with BrokenPipeError when it writes the
response — taking every subsequent request down with it.

Integration tests run the real server in a subprocess so they can assert that the
*process* stays alive. Timeouts are scaled down to fractions of a second.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

import suite_backend
from suite_backend.app_context import AppContext
from suite_backend.ipc.server import _handle_connection
from suite_backend.ipc.transport import IS_WINDOWS, connect, default_address

TESTS_DIR = Path(__file__).resolve().parent
SRC_DIR = Path(suite_backend.__file__).resolve().parents[1]


class Backend:
    def __init__(self, proc: subprocess.Popen, ipc: str, workspace: Path) -> None:
        self.proc = proc
        self.ipc = ipc
        self.workspace = workspace

    @property
    def log_path(self) -> Path:
        return self.workspace / "logs" / "backend.log"

    def log_text(self) -> str:
        return self.log_path.read_text(encoding="utf-8") if self.log_path.exists() else ""

    def assert_alive(self) -> None:
        assert self.proc.poll() is None, f"backend exited with {self.proc.returncode}"
        # A named pipe is not a file; probing it would open a connection.
        assert IS_WINDOWS or Path(self.ipc).exists(), "backend socket was removed"

    def connect(self, timeout: float = 10.0) -> socket.socket:
        return connect(self.ipc, timeout)

    def call(self, command: str, params: dict | None = None, timeout: float = 10.0) -> dict:
        """One request per connection, like the Rust bridge's call_python_ipc."""
        with self.connect(timeout) as sock:
            _send(sock, _request(command, params))
            return _read_response(sock)


def _request(command: str, params: dict | None = None) -> dict:
    return {"id": uuid.uuid4().hex, "command": command, "params": params or {}}


def _send(sock: socket.socket, request: dict) -> None:
    sock.sendall((json.dumps(request) + "\n").encode("utf-8"))


def _read_line(sock: socket.socket) -> bytes:
    data = b""
    while b"\n" not in data:
        chunk = sock.recv(65536)
        if not chunk:
            raise ConnectionError(f"backend closed connection; got {data!r}")
        data += chunk
    return data


def _read_response(sock: socket.socket) -> dict:
    return json.loads(_read_line(sock).split(b"\n", 1)[0])


def _abandon(backend: Backend, request: dict, wait: float) -> None:
    """Send a request, give up after ``wait`` seconds, and close — the Rust timeout path."""
    sock = backend.connect(timeout=wait)
    try:
        _send(sock, request)
        with pytest.raises(TimeoutError):
            sock.recv(65536)
    finally:
        sock.close()


def _wait_for(predicate, timeout: float = 10.0, interval: float = 0.02) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError("condition not met before timeout")


@pytest.fixture
def backend(tmp_path: Path) -> Iterator[Backend]:
    ipc = default_address(f"suite-ipc-{uuid.uuid4().hex[:12]}")
    workspace = tmp_path / "workspace"
    stdout = (tmp_path / "stdout.txt").open("wb")
    stderr = (tmp_path / "stderr.txt").open("wb")
    proc = subprocess.Popen(
        [
            sys.executable,
            str(TESTS_DIR / "_ipc_test_server.py"),
            "--ipc",
            ipc,
            "--workspace",
            str(workspace),
        ],
        stdout=stdout,
        stderr=stderr,
        # Windows needs SYSTEMROOT and friends to start Python at all.
        env={**os.environ, "PYTHONPATH": str(SRC_DIR)},
    )
    try:
        _wait_for(lambda: b'"event": "ready"' in (tmp_path / "stdout.txt").read_bytes())
        yield Backend(proc, ipc, workspace)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        stdout.close()
        stderr.close()
        if not IS_WINDOWS and Path(ipc).exists():
            Path(ipc).unlink()


# --- Integration: real server process -------------------------------------------------


def test_normal_request_and_response(backend: Backend) -> None:
    health = backend.call("health")
    assert health["ok"] is True
    assert health["result"]["status"] == "ok"

    created = backend.call("studies.create", {"name": "Demo"})
    assert created["ok"] is True
    assert created["result"]["name"] == "Demo"
    backend.assert_alive()


def test_response_contract_is_unchanged(backend: Backend) -> None:
    with backend.connect() as sock:
        request = {"id": "req-123", "command": "health", "params": {}}
        _send(sock, request)
        raw = _read_line(sock)
    assert raw.endswith(b"\n") and raw.count(b"\n") == 1
    payload = json.loads(raw)
    assert set(payload) == {"id", "ok", "result", "error"}
    assert payload["id"] == "req-123"
    assert payload["ok"] is True and payload["error"] is None

    with backend.connect() as sock:
        sock.sendall(b"not json\n")
        bad = _read_response(sock)
    assert bad["id"] == "unknown" and bad["ok"] is False
    assert bad["error"].startswith("invalid request:")

    unknown = backend.call("rm -rf /")
    assert unknown["ok"] is False and "not allowlisted" in unknown["error"]


def test_operation_finishing_after_client_disconnect_does_not_kill_backend(
    backend: Backend,
) -> None:
    """The original crash: response written to a socket whose client timed out."""
    request = _request("test.slow_write", {"seconds": 0.6, "name": "late.txt", "content": "42"})
    _abandon(backend, request, wait=0.1)

    output = backend.workspace / "test_outputs" / "late.txt"
    _wait_for(output.exists)
    # The operation ran to completion and its persisted output is intact.
    assert output.read_text(encoding="utf-8") == "42"

    _wait_for(lambda: "client disconnected before response" in backend.log_text())
    backend.assert_alive()
    assert backend.call("health")["ok"] is True

    log = backend.log_text()
    assert request["id"] in log
    assert "test.slow_write" in log
    assert "BrokenPipeError" in log or "EPIPE" in log or "Errno" in log


def test_client_disconnect_before_response_then_new_client_works(backend: Backend) -> None:
    _abandon(backend, _request("test.slow_write", {"seconds": 0.3, "name": "a.txt"}), wait=0.05)
    # A fresh client connects while (or after) the abandoned operation runs.
    second = backend.call("studies.create", {"name": "After disconnect"})
    assert second["ok"] is True
    listed = backend.call("studies.list")
    assert listed["ok"] is True
    backend.assert_alive()


def test_multiple_requests_after_disconnect(backend: Backend) -> None:
    _abandon(backend, _request("test.slow_write", {"seconds": 0.3, "name": "x.txt"}), wait=0.05)
    for i in range(5):
        created = backend.call("studies.create", {"name": f"Study {i}"})
        assert created["ok"] is True
    listed = backend.call("studies.list")
    assert listed["ok"] is True
    assert {s["name"] for s in listed["result"]["studies"]} >= {f"Study {i}" for i in range(5)}

    # Several requests pipelined on a single connection still work too.
    with backend.connect() as sock:
        ids = []
        for _ in range(3):
            request = _request("health")
            ids.append(request["id"])
            _send(sock, request)
        buffer = b""
        while buffer.count(b"\n") < 3:
            chunk = sock.recv(65536)
            assert chunk, "connection closed early"
            buffer += chunk
    responses = [json.loads(line) for line in buffer.splitlines()]
    assert [r["id"] for r in responses] == ids
    assert all(r["ok"] for r in responses)
    backend.assert_alive()


def test_repeated_disconnects_do_not_accumulate_failures(backend: Backend) -> None:
    for i in range(3):
        _abandon(
            backend,
            _request("test.slow_write", {"seconds": 0.15, "name": f"r{i}.txt", "content": str(i)}),
            wait=0.02,
        )
        _wait_for((backend.workspace / "test_outputs" / f"r{i}.txt").exists)
        assert backend.call("health")["ok"] is True
    for i in range(3):
        assert (backend.workspace / "test_outputs" / f"r{i}.txt").read_text() == str(i)
    backend.assert_alive()


def test_request_abandoned_while_queued_is_not_executed(backend: Backend) -> None:
    """A client that gave up while waiting behind a busy backend must not trigger work later."""
    busy = backend.connect()
    _send(busy, _request("test.slow_write", {"seconds": 0.5, "name": "busy.txt"}))
    time.sleep(0.05)  # let the backend start the slow operation

    stale = _request("test.slow_write", {"seconds": 0.0, "name": "stale.txt"})
    _abandon(backend, stale, wait=0.05)  # queued in the listen backlog, then closed

    assert _read_response(busy)["ok"] is True
    busy.close()
    # Health is queued after the stale connection, so by the time it returns the
    # stale request has been seen and skipped.
    assert backend.call("health")["ok"] is True
    assert not (backend.workspace / "test_outputs" / "stale.txt").exists()
    assert "skipping" in backend.log_text() and stale["id"] in backend.log_text()
    backend.assert_alive()


def test_handler_exception_is_reported_logged_and_survived(backend: Backend) -> None:
    failed = backend.call("test.raise")
    assert failed["ok"] is False
    assert "deliberate handler failure" in failed["error"]
    log = backend.log_text()
    assert "Traceback" in log and "RuntimeError: deliberate handler failure" in log
    backend.assert_alive()
    assert backend.call("health")["ok"] is True


def test_unserializable_result_is_reported_logged_and_survived(backend: Backend) -> None:
    """A programming error outside the handler (response serialization) must not kill the
    backend, but must be visible both to the client and in the log."""
    failed = backend.call("test.unserializable")
    assert failed["ok"] is False
    assert failed["error"].startswith("internal error:")
    log = backend.log_text()
    assert "Traceback" in log and "test.unserializable" in log
    backend.assert_alive()
    assert backend.call("health")["ok"] is True


def test_client_closing_without_sending_is_harmless(backend: Backend) -> None:
    backend.connect().close()
    with backend.connect() as sock:
        sock.sendall(b'{"id": "partial", "comm')  # truncated request, then hang up
    assert backend.call("health")["ok"] is True
    backend.assert_alive()


# --- Unit: connection handler with deterministic socket failures ---------------------


OPEN = object()  # FakeConn marker: client still connected but has sent nothing more


class FakeConn:
    """Minimal socket stand-in that can fail on recv or sendall."""

    def __init__(self, chunks: list, send_error: BaseException | None = None):
        self._chunks = list(chunks)
        self._send_error = send_error
        self.sent: list[bytes] = []
        self.closed = False

    def recv(self, _size: int, flags: int = 0) -> bytes:
        if not self._chunks:
            return b""
        item = self._chunks[0]
        if flags & socket.MSG_PEEK:
            if item is OPEN:
                raise BlockingIOError
            if isinstance(item, BaseException):
                raise item
            return item[:1]
        self._chunks.pop(0)
        if item is OPEN:
            return b""  # client finally hangs up
        if isinstance(item, BaseException):
            raise item
        return item

    def sendall(self, data: bytes) -> None:
        if self._send_error is not None:
            raise self._send_error
        self.sent.append(data)

    def settimeout(self, _value: float | None) -> None:
        pass

    def gettimeout(self) -> float | None:
        return None

    def setblocking(self, _flag: bool) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def _line(command: str, request_id: str = "u1") -> bytes:
    return (json.dumps({"id": request_id, "command": command, "params": {}}) + "\n").encode()


@pytest.mark.parametrize(
    "error", [BrokenPipeError(32, "Broken pipe"), ConnectionResetError(54, "reset")]
)
def test_send_failure_is_contained(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, error: OSError
) -> None:
    # Keep the client "open" (an extra pending chunk) so the request is dispatched.
    conn = FakeConn([_line("health", "send-fail"), OPEN], send_error=error)
    with caplog.at_level(logging.WARNING, logger="suite_backend.ipc.server"):
        _handle_connection(conn, AppContext(tmp_path))  # must not raise
    assert "client disconnected before response" in caplog.text
    assert "send-fail" in caplog.text and "health" in caplog.text


def test_recv_reset_is_contained(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    conn = FakeConn([ConnectionResetError(54, "Connection reset by peer")])
    with caplog.at_level(logging.WARNING, logger="suite_backend.ipc.server"):
        _handle_connection(conn, AppContext(tmp_path))  # must not raise
    assert "client disconnected" in caplog.text


def test_unexpected_error_is_logged_not_swallowed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from suite_backend.ipc import server

    def broken_dispatch(_request, _ctx):
        raise KeyError("bug in dispatch")

    monkeypatch.setattr(server.REGISTRY, "dispatch", broken_dispatch)
    conn = FakeConn([_line("health", "bug-1"), OPEN])
    with caplog.at_level(logging.ERROR, logger="suite_backend.ipc.server"):
        _handle_connection(conn, AppContext(tmp_path))
    assert any(r.exc_info for r in caplog.records), "traceback must be logged"
    assert "bug-1" in caplog.text
    response = json.loads(conn.sent[-1])
    assert response == {
        "id": "bug-1",
        "ok": False,
        "result": None,
        "error": "internal error: KeyError: 'bug in dispatch'",
    }


def test_keyboard_interrupt_is_not_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from suite_backend.ipc import server

    def interrupted(_request, _ctx):
        raise KeyboardInterrupt

    monkeypatch.setattr(server.REGISTRY, "dispatch", interrupted)
    conn = FakeConn([_line("health"), OPEN])
    with pytest.raises(KeyboardInterrupt):
        _handle_connection(conn, AppContext(tmp_path))
