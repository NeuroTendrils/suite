"""Shared JSON-lines IPC helpers for NeuroTendrils workers.

Copyright 2026 NeuroTendrils
SPDX-License-Identifier: Apache-2.0
"""

from .protocol import (
    PROTOCOL_VERSION,
    ProtocolError,
    encode_error,
    encode_event,
    encode_request,
    encode_success,
    read_message,
    write_message,
)
from .redact import redact

__all__ = [
    "PROTOCOL_VERSION",
    "ProtocolError",
    "encode_error",
    "encode_event",
    "encode_request",
    "encode_success",
    "read_message",
    "redact",
    "write_message",
]

__version__ = "0.0.1"
