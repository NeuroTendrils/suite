"""Unit tests for nt_ipc protocol + redaction (stdlib unittest)."""

from __future__ import annotations

import io
import unittest

from nt_ipc import protocol
from nt_ipc.redact import redact


class ProtocolTests(unittest.TestCase):
    def test_round_trip_request(self) -> None:
        message = protocol.encode_request("r1", "ping", {"x": 1})
        line = io.StringIO()
        protocol.write_message(line, message)
        line.seek(0)
        parsed = protocol.read_message(line)
        self.assertEqual(parsed["cmd"], "ping")
        self.assertEqual(parsed["args"]["x"], 1)

    def test_success_and_error_envelopes(self) -> None:
        ok = protocol.encode_success("r1", {"pong": True})
        self.assertTrue(ok["ok"])
        err = protocol.encode_error("r1", "boom", "nope", {"hint": 1})
        self.assertFalse(err["ok"])
        self.assertEqual(err["error"]["code"], "boom")
        self.assertEqual(err["error"]["details"]["hint"], 1)

    def test_event_envelope(self) -> None:
        event = protocol.encode_event("r1", "progress", {"pct": 10})
        self.assertEqual(event["type"], "event")
        self.assertEqual(event["name"], "progress")

    def test_rejects_bad_json(self) -> None:
        with self.assertRaises(protocol.ProtocolError) as ctx:
            protocol.parse_message("{not json")
        self.assertEqual(ctx.exception.code, "invalid_json")


class RedactTests(unittest.TestCase):
    def test_redacts_sensitive_keys(self) -> None:
        payload = {
            "channels": ["Cz", "Pz"],
            "samples": [0.1, 0.2, 0.3, 0.4],
            "nested": {"eeg": list(range(32))},
        }
        safe = redact(payload)
        self.assertEqual(safe["channels"], ["Cz", "Pz"])
        self.assertEqual(safe["samples"]["_redacted"], "array")
        self.assertEqual(safe["nested"]["eeg"]["_redacted"], "array")
        self.assertNotIn("0.1", str(safe))

    def test_redacts_long_numeric_series_without_key(self) -> None:
        series = list(range(64))
        safe = redact(series)
        self.assertEqual(safe["_redacted"], "numeric_series")
        self.assertEqual(safe["length"], 64)


if __name__ == "__main__":
    unittest.main()
