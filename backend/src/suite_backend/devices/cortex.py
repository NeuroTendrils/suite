"""Bounded Insight acquisition over the local, TLS-verified Cortex service.

Credentials live in the backend environment, never in UI storage or study files.
No network destination is accepted from the UI. EMOTIV Launcher manages login.
"""

from __future__ import annotations

import csv
import json
import logging
import math
import os
import ssl
import time
import uuid
from pathlib import Path

from suite_backend.scientific.io.insight import CHANNELS, SFREQ


class CortexClient:
    def __init__(self, socket):
        self.socket = socket
        self.sequence = 0

    def receive(self, timeout=10):
        try:
            return json.loads(self.socket.recv(timeout=timeout))
        except TimeoutError:
            raise
        except Exception as exc:
            raise ValueError(
                "Cortex connection interrupted or returned invalid data; check Launcher and retry"
            ) from exc

    def call(self, method: str, **params):
        self.sequence += 1
        request_id = self.sequence
        self.socket.send(
            json.dumps({"id": request_id, "jsonrpc": "2.0", "method": method, "params": params})
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                reply = self.receive(max(0.01, deadline - time.monotonic()))
            except TimeoutError as exc:
                raise ValueError(f"Cortex {method} timed out; check EMOTIV Launcher") from exc
            if reply.get("id") != request_id:
                continue
            if "error" in reply:
                # Vendor messages may contain tokens or identifiers; never echo them.
                raise ValueError(
                    f"Cortex {method} failed (code {reply['error'].get('code', 'unknown')}); check Launcher approval, license and headset"
                )
            return reply.get("result", {})
        raise ValueError(f"Cortex {method} timed out; check EMOTIV Launcher")


def eeg_row(message: dict, columns: list[str], session: str) -> list[float] | None:
    if message.get("sid") != session or "eeg" not in message:
        return None
    values = message["eeg"]
    if len(values) != len(columns) or len(columns) != len(set(columns)):
        raise ValueError("Cortex EEG column layout is invalid")
    try:
        row = [float(message["time"]), float(values[columns.index("INTERPOLATED")])]
        row.extend(float(values[columns.index(c)]) for c in CHANNELS)
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("Cortex EEG sample is missing required Insight fields") from exc
    if not all(math.isfinite(v) for v in row):
        raise ValueError("Cortex returned non-finite EEG samples")
    return row


def capture_insight(directory: Path, seconds: int, *, connect_fn=None) -> dict:
    if not 2 <= seconds <= 30:
        raise ValueError("Insight capture duration must be 2–30 seconds")
    client_id = os.environ.get("EMOTIV_CLIENT_ID", "")
    secret = os.environ.get("EMOTIV_CLIENT_SECRET", "")
    if not client_id or not secret:
        raise ValueError(
            "Configure EMOTIV_CLIENT_ID and EMOTIV_CLIENT_SECRET in the backend environment; restart the app"
        )
    if connect_fn is None:
        from websockets.sync.client import connect

        connect_fn = connect
    tls = ssl.create_default_context()
    ca = os.environ.get("EMOTIV_CA_CERT")
    if ca:
        tls.load_verify_locations(cafile=ca)
    try:
        socket = connect_fn(
            "wss://localhost:6868",
            ssl=tls,
            open_timeout=5,
            close_timeout=2,
            proxy=None,
            max_size=1024 * 1024,
        )
    except Exception as exc:
        raise ValueError(
            "Cannot connect securely to Cortex. Start EMOTIV Launcher and trust its Root CA (EMOTIV_CA_CERT)"
        ) from exc
    client = CortexClient(socket)
    token = session = None
    rows = []
    quality = None
    try:
        access = client.call("requestAccess", clientId=client_id, clientSecret=secret)
        if not access.get("accessGranted"):
            raise ValueError("Approve this application in EMOTIV Launcher, then capture again")
        token = client.call("authorize", clientId=client_id, clientSecret=secret, debit=1).get(
            "cortexToken"
        )
        if not token:
            raise ValueError("Cortex authorization returned no token; check Launcher login")
        headsets = client.call("queryHeadsets")
        candidates = [
            h
            for h in headsets
            if h.get("status") == "connected" and set(h.get("sensors", [])) == set(CHANNELS)
        ]
        if len(candidates) != 1:
            raise ValueError("Connect exactly one EMOTIV Insight in Launcher before capture")
        headset = candidates[0]
        if float(headset.get("settings", {}).get("eegRate", SFREQ)) != SFREQ:
            raise ValueError("Insight must stream at 128 Hz")
        session = client.call(
            "createSession", cortexToken=token, headset=headset["id"], status="active"
        ).get("id")
        if not session:
            raise ValueError("Cortex did not activate a session; check the raw EEG license")
        subscription = client.call(
            "subscribe", cortexToken=token, session=session, streams=["eeg", "eq"]
        )
        streams = {s["streamName"]: s["cols"] for s in subscription.get("success", [])}
        if "eeg" not in streams or not set(CHANNELS).issubset(streams["eeg"]):
            raise ValueError(
                "Raw Insight EEG subscription failed; an activated EEG license is required"
            )
        expected = int(seconds * SFREQ)
        deadline = time.monotonic() + seconds + 5
        while len(rows) < expected and time.monotonic() < deadline:
            try:
                message = client.receive(min(2, max(0.01, deadline - time.monotonic())))
            except TimeoutError:
                continue
            if message.get("sid") != session:
                continue
            if "eq" in message and "eq" in streams:
                q = message["eq"]
                if len(q) == len(streams["eq"]):
                    quality = {
                        k: v
                        for k, v in zip(streams["eq"], q)
                        if k in {*CHANNELS, "overall", "sampleRateQuality"}
                    }
            row = eeg_row(message, streams["eeg"], session)
            if row is not None:
                if rows and row[0] <= rows[-1][0]:
                    raise ValueError(
                        "Cortex timestamps are not strictly increasing; capture discarded"
                    )
                rows.append(row)
        if len(rows) < expected:
            raise ValueError(
                "EEG stream stopped or dropped samples; capture discarded. Check headset contact and connection"
            )
    finally:
        try:
            if session and token:
                client.call("updateSession", cortexToken=token, session=session, status="close")
        except Exception:  # noqa: BLE001 — cleanup must preserve the acquisition error
            logging.getLogger(__name__).warning(
                "Cortex session cleanup failed; close the session in Launcher"
            )
        socket.close()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / f"insight_{uuid.uuid4().hex}.csv"
    # Exclusive owner-only file. Write only after acquisition succeeds.
    with path.open("x", encoding="utf-8", newline="") as handle:
        path.chmod(0o600)
        writer = csv.writer(handle)
        writer.writerow(["EMOTIV Insight", "sampling rate:128", "units:uV"])
        writer.writerow(["Timestamp", "INTERPOLATED", *[f"EEG.{c}" for c in CHANNELS]])
        writer.writerows(rows)
    interpolated = sum(r[1] != 0 for r in rows)
    return {
        "status": "ok",
        "path": str(path),
        "n_samples": len(rows),
        "sfreq": SFREQ,
        "channels": list(CHANNELS),
        "interpolated_samples": interpolated,
        "quality": quality,
        "warnings": (
            ["No EEG quality stream was received; inspect contact in Launcher"]
            if quality is None
            else []
        )
        + ([f"{interpolated} interpolated samples will be marked bad"] if interpolated else []),
    }
