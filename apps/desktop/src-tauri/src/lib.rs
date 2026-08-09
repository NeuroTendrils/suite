use serde_json::{json, Value};
use std::collections::HashSet;
use std::io::{BufRead, BufReader, Write};
use std::net::Shutdown;
use std::os::unix::net::UnixStream;
use std::path::PathBuf;
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
        "subjects.add",
        "import.inspect",
        "import.recording",
        "recordings.get",
        "recordings.inspect",
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

fn resolve_python() -> Result<PathBuf, String> {
    if let Ok(explicit) = std::env::var("SUITE_PYTHON") {
        let path = PathBuf::from(&explicit);
        if path.is_file() {
            return Ok(path);
        }
        return Err(format!(
            "SUITE_PYTHON is set to '{explicit}' but that file does not exist. \
             Point it at the repo venv, e.g. /Users/you/Projects/suite/.venv/bin/python"
        ));
    }

    // Walk up from cwd: apps/desktop -> apps -> repo root (.venv lives at repo root).
    let mut dir = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    for _ in 0..6 {
        let candidate = dir.join(".venv/bin/python");
        if candidate.is_file() {
            return Ok(candidate);
        }
        // Also accept python3 inside the venv.
        let candidate3 = dir.join(".venv/bin/python3");
        if candidate3.is_file() {
            return Ok(candidate3);
        }
        if !dir.pop() {
            break;
        }
    }

    // Last resort: PATH
    Ok(PathBuf::from("python3"))
}

fn spawn_backend(workspace: PathBuf) -> Result<BackendState, String> {
    let ipc_path = PathBuf::from(format!(
        "/tmp/neurotendrils-{}.sock",
        Uuid::new_v4().simple()
    ));
    if ipc_path.exists() {
        let _ = std::fs::remove_file(&ipc_path);
    }

    let python = resolve_python()?;
    let mut child = Command::new(&python)
        .args([
            "-m",
            "suite_backend",
            "--ipc",
            ipc_path.to_str().unwrap(),
            "--workspace",
            workspace.to_str().unwrap(),
        ])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| {
            format!(
                "failed to spawn python backend ({}): {e}. \
                 Create the repo venv: python3 -m venv .venv && .venv/bin/pip install -e backend[dev]",
                python.display()
            )
        })?;

    // Wait until socket exists or process dies.
    let start = Instant::now();
    while start.elapsed() < Duration::from_secs(20) {
        if ipc_path.exists() {
            return Ok(BackendState { child, ipc_path });
        }
        if let Ok(Some(status)) = child.try_wait() {
            return Err(format!("python backend exited early: {status}"));
        }
        thread::sleep(Duration::from_millis(50));
    }
    let _ = child.kill();
    Err("timed out waiting for python backend socket".into())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
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

            let backend = spawn_backend(workspace)?;
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
