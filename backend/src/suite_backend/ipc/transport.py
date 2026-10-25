"""Local-only IPC transport: Unix domain socket, or a named pipe on Windows.

CPython on Windows has no ``AF_UNIX``, so there the server listens on a named pipe
(``\\\\.\\pipe\\<name>``) through the stdlib ``multiprocessing.connection``. Both
transports hand the server the same small socket-like interface (``recv``, ``sendall``,
timeouts and ``MSG_PEEK``), so the request loop in ``server.py`` is shared.
"""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path
from typing import Any, Self

IS_WINDOWS = sys.platform == "win32"
PIPE_PREFIX = "\\\\.\\pipe\\"


def default_address(name: str) -> str:
    """A private address for ``name``: a named pipe on Windows, else a socket in /tmp.

    AF_UNIX paths have a low length limit, so sockets stay under /tmp.
    """
    return PIPE_PREFIX + name if IS_WINDOWS else f"/tmp/{name}.sock"


class Listener:
    def __init__(self, address: str) -> None:
        self.address = address
        if IS_WINDOWS:
            from multiprocessing.connection import Listener as PipeListener

            # No authkey: the protocol is plain JSON lines, like the Unix socket. The
            # pipe name is a fresh random UUID per launch.
            self._pipe = PipeListener(address, family="AF_PIPE", backlog=8)
            self._sock = None
            return
        path = Path(address)
        if path.exists():
            path.unlink()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._pipe = None
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.bind(str(path))
        os.chmod(path, 0o600)
        self._sock.listen(8)

    def accept(self) -> Any:
        if self._pipe is not None:
            return PipeConn(self._pipe.accept())
        conn, _ = self._sock.accept()
        return conn

    def close(self) -> None:
        if self._pipe is not None:
            self._pipe.close()
            return
        self._sock.close()
        path = Path(self.address)
        if path.exists():
            path.unlink()


def connect(address: str, timeout: float | None = None) -> Any:
    """Connect as a client; the result behaves like a connected stream socket."""
    if IS_WINDOWS:
        from multiprocessing.connection import Client

        conn = PipeConn(Client(address, family="AF_PIPE"))
        conn.settimeout(timeout)
        return conn
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(address)
    return sock


class PipeConn:
    """Socket-like wrapper over a message-mode ``multiprocessing`` PipeConnection.

    Each pipe message is one chunk of the byte stream; a closed or broken pipe reads as
    EOF, and a failed write raises ``BrokenPipeError``, as on a socket.
    """

    def __init__(self, conn: Any) -> None:
        self._conn = conn
        self._pending = b""
        self._timeout: float | None = None

    def settimeout(self, value: float | None) -> None:
        self._timeout = value

    def gettimeout(self) -> float | None:
        return self._timeout

    def setblocking(self, flag: bool) -> None:
        self._timeout = None if flag else 0.0

    def recv(self, size: int, flags: int = 0) -> bytes:
        if not self._pending:
            try:
                ready = self._conn.poll(self._timeout)
            except (OSError, EOFError):
                return b""  # client is gone
            if not ready:
                if self._timeout == 0:
                    raise BlockingIOError
                raise TimeoutError("timed out")
            try:
                self._pending = self._conn.recv_bytes()
            except (OSError, EOFError):
                return b""
        data = self._pending[:size]
        if not flags & socket.MSG_PEEK:
            self._pending = self._pending[size:]
        return data

    def sendall(self, data: bytes) -> None:
        try:
            self._conn.send_bytes(data)
        except (OSError, EOFError) as exc:
            raise BrokenPipeError(str(exc)) from exc

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
