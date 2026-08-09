# Architecture overview

NeuroTendrils Suite is a local-first, multi-subject EEG research OS.

## Runtime

- **Tauri (Rust):** window, process lifecycle, allowlisted `suite_call` commands
- **React (TypeScript):** utilitarian UI only — no scientific logic
- **Python `suite_backend`:** domain, NeuroFlow, NeuroStudio stubs, MNE-backed I/O

IPC is a private Unix domain socket (named pipes planned for Windows). JSON request/response lines with Pydantic schemas. No free-form code execution.

## Product modules

| Module | Role |
|--------|------|
| NeuroFlow | Inspect, visualize, manual reject, plans, ERP, ICA |
| NeuroStudio | Templates (EEGNet…), train/eval/export stubs |
| Hub / Teams | Future cloud; `visibility` / quota interfaces only today |

## Provenance

Raw files are never mutated. Processing produces immutable artifacts with parent links, parameters, checksums, and human decisions.
