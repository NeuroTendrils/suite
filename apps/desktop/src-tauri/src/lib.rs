use serde_json::{json, Value};
use std::collections::HashSet;
use std::io::{BufRead, BufReader, Write};
use std::net::Shutdown;
use std::os::unix::net::UnixStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};
use tauri::Manager;
use uuid::Uuid;

struct BackendState {
    child: Child,
    ipc_path: PathBuf,
}

struct AppState {
    backend: Mutex<Option<BackendState>>,
}

enum BackendCmd {
    /// Frozen PyInstaller (or similar) sidecar — argv is just IPC flags.
    Sidecar(PathBuf),
    /// Dev: python -m suite_backend …
    Module(PathBuf),
}

fn allowlisted_commands() -> HashSet<&'static str> {
    HashSet::from([
        "health",
        "workspace.info",
        "commands.list",
        "studies.create",
        "studies.list",
        "studies.get",
        "studies.inspect",
        "studies.set_event_map",
        "studies.set_visibility",
        "studies.tree",
        "subjects.add",
        "subjects.set_metadata",
        "sessions.add",
        "runs.add",
        "streams.list",
        "streams.get",
        "import.inspect",
        "import.recording",
        "import.stream.inspect",
        "import.stream",
        "recordings.get",
        "recordings.inspect",
        "recordings.normalize",
        "recordings.signal_window",
        "annotations.create",
        "channels.set_bad",
        "erp.compute",
        "ica.components.list",
        "ica.component.set_rejection",
        "neuroflow.recommend_preprocessing",
        "neuroflow.detect_artifacts",
        "neuroflow.detect_lab_interference",
        "plans.create",
        "plans.list",
        "plans.execute",
        "augmentation.run",
        "neurostudio.templates.list",
        "neurostudio.templates.get",
        "neurostudio.templates.recommend",
        "neurostudio.experiments.create",
        "neurostudio.train.start",
        "neurostudio.hypertune.start",
        "neurostudio.eval.run",
        "neurostudio.generalization.run",
        "neurostudio.model.export",
        "neurostudio.infer.run",
        "neurostudio.leakage.check",
    ])
}

fn call_python_ipc(ipc_path: &PathBuf, command: &str, params: Value) -> Result<Value, String> {
    let request = json!({
        "id": Uuid::new_v4().to_string(),
        "command": command,
        "params": params,
    });
    let mut stream = UnixStream::connect(ipc_path).map_err(|e| format!("ipc connect: {e}"))?;
    stream
        .set_read_timeout(Some(Duration::from_secs(120)))
        .ok();
    let line = format!("{}\n", request);
    stream
        .write_all(line.as_bytes())
        .map_err(|e| format!("ipc write: {e}"))?;
    let mut reader = BufReader::new(stream.try_clone().map_err(|e| e.to_string())?);
    let mut response = String::new();
    reader
        .read_line(&mut response)
        .map_err(|e| format!("ipc read: {e}"))?;
    let _ = stream.shutdown(Shutdown::Both);
    let value: Value =
        serde_json::from_str(response.trim()).map_err(|e| format!("ipc parse: {e}"))?;
    if value.get("ok").and_then(|v| v.as_bool()) == Some(true) {
        Ok(value.get("result").cloned().unwrap_or(Value::Null))
    } else {
        Err(value
            .get("error")
            .and_then(|v| v.as_str())
            .unwrap_or("backend error")
            .to_string())
    }
}

#[tauri::command]
fn suite_call(
    state: tauri::State<'_, AppState>,
    command: String,
    params: Option<Value>,
) -> Result<Value, String> {
    if !allowlisted_commands().contains(command.as_str()) {
        return Err(format!("command not allowlisted: {command}"));
    }
    let guard = state.backend.lock().map_err(|_| "backend lock poisoned")?;
    let backend = guard.as_ref().ok_or("python backend not running")?;
    call_python_ipc(&backend.ipc_path, &command, params.unwrap_or(json!({})))
}

fn host_target_triple() -> String {
    // Matches rustc host / Tauri externalBin suffix convention.
    std::env::consts::ARCH.to_string()
        + "-"
        + match std::env::consts::OS {
            "macos" => "apple-darwin",
            "linux" => "unknown-linux-gnu",
            "windows" => "pc-windows-msvc",
            other => other,
        }
}

fn find_sidecar_near(dir: &Path) -> Option<PathBuf> {
    let triple = host_target_triple();
    let names = [
        format!("suite-backend-{triple}"),
        "suite-backend".to_string(),
        format!("suite-backend-{triple}.exe"),
        "suite-backend.exe".to_string(),
    ];
    for name in names {
        let candidate = dir.join(&name);
        if candidate.is_file() {
            return Some(candidate);
        }
        let nested = dir.join("binaries").join(&name);
        if nested.is_file() {
            return Some(nested);
        }
    }
    None
}

fn resolve_backend(app: &tauri::App) -> Result<BackendCmd, String> {
    // 1) Explicit override (absolute path to sidecar OR python)
    if let Ok(explicit) = std::env::var("SUITE_BACKEND") {
        let path = PathBuf::from(&explicit);
        if !path.is_file() {
            return Err(format!("SUITE_BACKEND={explicit} does not exist"));
        }
        let is_python = path
            .file_name()
            .and_then(|s| s.to_str())
            .is_some_and(|n| n.starts_with("python"));
        return Ok(if is_python {
            BackendCmd::Module(path)
        } else {
            BackendCmd::Sidecar(path)
        });
    }
    if let Ok(explicit) = std::env::var("SUITE_PYTHON") {
        let path = PathBuf::from(&explicit);
        if path.is_file() {
            return Ok(BackendCmd::Module(path));
        }
        return Err(format!("SUITE_PYTHON={explicit} does not exist"));
    }

    // 2) Bundled / local PyInstaller sidecar (preferred for shipping)
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            if let Some(bin) = find_sidecar_near(dir) {
                return Ok(BackendCmd::Sidecar(bin));
            }
            // macOS .app: Contents/MacOS -> Contents/Resources
            if let Some(contents) = dir.parent() {
                let resources = contents.join("Resources");
                if let Some(bin) = find_sidecar_near(&resources) {
                    return Ok(BackendCmd::Sidecar(bin));
                }
            }
        }
    }
    if let Ok(resource_dir) = app.path().resource_dir() {
        if let Some(bin) = find_sidecar_near(&resource_dir) {
            return Ok(BackendCmd::Sidecar(bin));
        }
    }
    // Dev tree: apps/desktop/src-tauri/binaries
    let mut dir = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    for _ in 0..8 {
        if let Some(bin) = find_sidecar_near(&dir.join("src-tauri")) {
            return Ok(BackendCmd::Sidecar(bin));
        }
        if let Some(bin) = find_sidecar_near(&dir.join("apps/desktop/src-tauri")) {
            return Ok(BackendCmd::Sidecar(bin));
        }
        if !dir.pop() {
            break;
        }
    }

    // 3) Repo-root venv (dev) — created by scripts/ensure_dev.sh
    let mut dir = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    for _ in 0..8 {
        for name in ["python", "python3"] {
            let candidate = dir.join(".venv/bin").join(name);
            if candidate.is_file() {
                return Ok(BackendCmd::Module(candidate));
            }
        }
        if !dir.pop() {
            break;
        }
    }

    Err(
        "No backend found. Run `./scripts/ensure_dev.sh` (dev) or `./scripts/build_sidecar.sh` (PyInstaller)."
            .into(),
    )
}

fn spawn_backend(app: &tauri::App, workspace: PathBuf) -> Result<BackendState, String> {
    let ipc_path = PathBuf::from(format!(
        "/tmp/neurotendrils-{}.sock",
        Uuid::new_v4().simple()
    ));
    if ipc_path.exists() {
        let _ = std::fs::remove_file(&ipc_path);
    }

    let launch = resolve_backend(app)?;
    let mut command = match &launch {
        BackendCmd::Sidecar(path) => {
            let mut cmd = Command::new(path);
            cmd.args([
                "--ipc",
                ipc_path.to_str().unwrap(),
                "--workspace",
                workspace.to_str().unwrap(),
            ]);
            cmd
        }
        BackendCmd::Module(python) => {
            let mut cmd = Command::new(python);
            cmd.args([
                "-m",
                "suite_backend",
                "--ipc",
                ipc_path.to_str().unwrap(),
                "--workspace",
                workspace.to_str().unwrap(),
            ]);
            cmd
        }
    };

    let label = match &launch {
        BackendCmd::Sidecar(p) => format!("sidecar {}", p.display()),
        BackendCmd::Module(p) => format!("module {}", p.display()),
    };

    let mut child = command
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("failed to spawn backend ({label}): {e}"))?;

    let start = Instant::now();
    while start.elapsed() < Duration::from_secs(30) {
        if ipc_path.exists() {
            return Ok(BackendState { child, ipc_path });
        }
        if let Ok(Some(status)) = child.try_wait() {
            return Err(format!("backend exited early ({label}): {status}"));
        }
        thread::sleep(Duration::from_millis(50));
    }
    let _ = child.kill();
    Err(format!("timed out waiting for backend socket ({label})"))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(AppState {
            backend: Mutex::new(None),
        })
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            let workspace = app
                .path()
                .app_data_dir()
                .map_err(|e| e.to_string())?
                .join("workspace");
            std::fs::create_dir_all(&workspace).map_err(|e| e.to_string())?;

            let backend = spawn_backend(app, workspace)?;
            let state = app.state::<AppState>();
            let mut guard = state.backend.lock().unwrap();
            *guard = Some(backend);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![suite_call])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if let tauri::RunEvent::Exit = event {
                if let Some(state) = app_handle.try_state::<AppState>() {
                    if let Ok(mut guard) = state.backend.lock() {
                        if let Some(mut backend) = guard.take() {
                            let _ = backend.child.kill();
                            if backend.ipc_path.exists() {
                                let _ = std::fs::remove_file(&backend.ipc_path);
                            }
                        }
                    }
                }
            }
        });
}
