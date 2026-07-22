# NeuroTendrils IPC (`nt_ipc`)

Apache-2.0 shared helpers for suite ↔ worker JSON-lines IPC.

Licensed separately from the AGPL-3.0 NeuroFlow worker so proprietary
suite workers (e.g. NeuroStudio) can reuse the same wire format without
pulling AGPL into those workers. NeuroFlow may import this package;
AGPL can depend on Apache-2.0.

## Protocol

One JSON object per line on stdin/stdout (UTF-8).

**Request**

```json
{"v":1,"id":"req-1","cmd":"ping","args":{}}
```

**Success response**

```json
{"v":1,"id":"req-1","ok":true,"result":{"pong":true}}
```

**Error response**

```json
{"v":1,"id":"req-1","ok":false,"error":{"code":"invalid_request","message":"..."}}
```

**Event** (optional progress / metrics while a command runs)

```json
{"v":1,"id":"req-1","type":"event","name":"progress","data":{"pct":40}}
```

## Redaction

`nt_ipc.redact` strips or summarizes keys that look like raw EEG /
sample payloads before anything is written to logs. Prefer metadata
(channel count, shape) over arrays.

## Use

```bash
PYTHONPATH=workers/_shared:workers/neuroflow python -c "from nt_ipc import protocol; print(protocol.PROTOCOL_VERSION)"
PYTHONPATH=workers/_shared python -m unittest discover -s workers/_shared/tests -v
```
