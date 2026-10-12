from __future__ import annotations

import errno
import json
import logging
import logging.handlers
import os
import socket
import sys
import time
from pathlib import Path

from suite_backend.app_context import AppContext
from suite_backend.ipc import handlers  # noqa: F401 — register commands
from suite_backend.ipc.protocol import RpcRequest, RpcResponse
from suite_backend.ipc.registry import REGISTRY

logger = logging.getLogger(__name__)

# A connected client that sends nothing for this long is dropped so it cannot stall
# the (single-threaded) server. Does not limit how long a command may run.
CLIENT_IDLE_TIMEOUT_S = 60.0

# errno values meaning "the peer is gone" (EPROTOTYPE: macOS race when writing to a
# Unix socket whose peer is closing).
_DISCONNECT_ERRNOS = {
    errno.EPIPE,
    errno.ECONNRESET,
    errno.ECONNABORTED,
    errno.ENOTCONN,
    errno.ESHUTDOWN,
    errno.EPROTOTYPE,
}
# accept() failures that concern a single pending connection or a transient shortage.
_TRANSIENT_ACCEPT_ERRNOS = {
    errno.ECONNABORTED,
    errno.EINTR,
    errno.EMFILE,
    errno.ENFILE,
    errno.ENOBUFS,
    errno.ENOMEM,
}


class ClientDisconnected(Exception):
    """The client went away; nothing more can be sent on this connection."""


def _is_disconnect(exc: OSError) -> bool:
    return isinstance(exc, (ConnectionError, TimeoutError)) or exc.errno in _DISCONNECT_ERRNOS


def configure_logging(workspace_root: str | Path) -> Path:
    """Log to ``<workspace>/logs/backend.log``.

    Deliberately not stderr: the desktop shell pipes stderr without reading it, so
    unbounded output there can fill the pipe and block the backend.
    """
    log_path = Path(workspace_root).expanduser().resolve() / "logs" / "backend.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    package_logger = logging.getLogger("suite_backend")
    package_logger.setLevel(logging.INFO)
    for existing in package_logger.handlers:
        if getattr(existing, "baseFilename", None) == str(log_path):
            return log_path
    handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [pid %(process)d] %(name)s: %(message)s")
    )
    package_logger.addHandler(handler)
    return log_path


def serve_ipc(ipc_path: str, workspace_root: str) -> None:
    """Serve allowlisted JSON-RPC lines over a Unix domain socket."""
    path = Path(ipc_path)
    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)

    ctx = AppContext(workspace_root)
    configure_logging(ctx.workspace.root)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    os.chmod(path, 0o600)
    server.listen(8)
    logger.info("backend listening on %s (workspace %s)", path, ctx.workspace.root)
    print(json.dumps({"event": "ready", "ipc": str(path), "commands": REGISTRY.allowlist()}), flush=True)

    try:
        while True:
            try:
                conn, _ = server.accept()
            except OSError as exc:
                if exc.errno not in _TRANSIENT_ACCEPT_ERRNOS:
                    raise
                logger.warning("accept failed, continuing: %r", exc)
                if exc.errno not in (errno.ECONNABORTED, errno.EINTR):
                    time.sleep(0.1)
                continue
            with conn:
                _serve_connection(conn, ctx)
    except KeyboardInterrupt:
        pass
    except BaseException:
        logger.critical("IPC server stopped by unhandled exception", exc_info=True)
        raise
    finally:
        logger.info("backend shutting down")
        server.close()
        if path.exists():
            path.unlink()


def _serve_connection(conn: socket.socket, ctx: AppContext) -> None:
    """Contain every per-connection failure so the accept loop keeps running."""
    try:
        _handle_connection(conn, ctx)
    except Exception:  # logged with traceback; one connection must not kill the server
        logger.exception("unexpected error while serving connection; connection dropped")


def _handle_connection(conn: socket.socket, ctx: AppContext) -> None:
    conn.settimeout(CLIENT_IDLE_TIMEOUT_S)
    buffer = b""
    while True:
        try:
            chunk = conn.recv(65536)
        except OSError as exc:
            if not _is_disconnect(exc):
                raise
            logger.warning(
                "client disconnected while sending request (%r); %d unprocessed bytes discarded",
                exc,
                len(buffer),
            )
            return
        if not chunk:
            if buffer.strip():
                logger.warning(
                    "client closed with incomplete request (%d bytes) discarded", len(buffer)
                )
            return
        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                _handle_line(conn, ctx, line)
            except ClientDisconnected:
                return


def _handle_line(conn: socket.socket, ctx: AppContext, line: bytes) -> None:
    try:
        request = RpcRequest.model_validate_json(line)
    except Exception as exc:  # noqa: BLE001
        logger.warning("invalid request rejected: %s", exc)
        _send_line(
            conn,
            json.dumps({"id": "unknown", "ok": False, "error": f"invalid request: {exc}"}),
            request_id="unknown",
            command="?",
            started=time.monotonic(),
        )
        return

    # A client that gave up while queued behind a long operation has already reported a
    # failure to the user; running its command now would be a side effect nobody sees.
    if _peer_closed(conn):
        logger.warning(
            "client disconnected before request %s (%s) was started; skipping it",
            request.id,
            request.command,
        )
        raise ClientDisconnected

    started = time.monotonic()
    try:
        response = REGISTRY.dispatch(request, ctx)
        payload = response.model_dump_json()
    except Exception as exc:  # programming error: reported, logged, not fatal
        logger.exception("internal error handling request %s (%s)", request.id, request.command)
        payload = RpcResponse(
            id=request.id,
            ok=False,
            error=f"internal error: {type(exc).__name__}: {exc}",
        ).model_dump_json()
    _send_line(conn, payload, request_id=request.id, command=request.command, started=started)


def _send_line(
    conn: socket.socket, payload: str, *, request_id: str, command: str, started: float
) -> None:
    try:
        conn.sendall((payload + "\n").encode("utf-8"))
    except OSError as exc:
        if not _is_disconnect(exc):
            raise
        logger.warning(
            "client disconnected before response to request %s (%s) after %.1fs; "
            "command finished and its result was discarded: %r",
            request_id,
            command,
            time.monotonic() - started,
            exc,
        )
        raise ClientDisconnected from exc


def _peer_closed(conn: socket.socket) -> bool:
    """True if the client has hung up (EOF or reset) with no further data pending.

    Clients that half-close their write side after sending a request look the same;
    neither the Rust bridge nor ``IpcClient`` do that.
    """
    timeout = conn.gettimeout()
    try:
        conn.setblocking(False)
        return conn.recv(1, socket.MSG_PEEK) == b""
    except (BlockingIOError, InterruptedError):
        return False
    except OSError as exc:
        return _is_disconnect(exc)
    finally:
        conn.settimeout(timeout)


def main_stdio_debug() -> None:
    """Optional stdio mode for tests (still no TCP)."""
    ctx = AppContext(sys.argv[1] if len(sys.argv) > 1 else "./workspace")
    for line in sys.stdin:
        request = RpcRequest.model_validate_json(line)
        print(REGISTRY.dispatch(request, ctx).model_dump_json(), flush=True)
