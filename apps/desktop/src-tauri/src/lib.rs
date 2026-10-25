use serde_json::{json, Value};
use std::collections::HashSet;
use std::io::{BufRead, BufReader, Read, Write};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{mpsc, Mutex};
use std::thread;
use std::time::{Duration, Instant};
use tauri::Manager;
use uuid::Uuid;

mod robot;

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
        "studies.manager",
        "subjects.add",
        "subjects.set_metadata",
        "sessions.add",
        "runs.add",
        "streams.list",
        "streams.get",
        "import.inspect",
        "insight.capture",
        "import.recording",
        "import.stream.inspect",
        "import.stream",
        "recordings.get",
        "recordings.inspect",
        "recordings.normalize",
        "recordings.signal_window",
        "recordings.timeline",
        "sync.create",
        "sync.list",
        "sync.get",
        "sync.set_offset",
        "validate.stream",
        "validate.recording",
        "validate.study",
        "annotations.create",
        "annotations.list",
        "annotations.delete",
        "channels.set_bad",
        "channels.list",
        "channels.update",
        "channels.reorder",
        "channels.apply_montage",
        "events.list",
        "events.create",
        "events.delete",
        "artifacts.detect",
        "artifacts.apply",
        "artifacts.list",
        "artifacts.revert",
        "epochs.create",
        "epochs.list",
        "epochs.get",
        "epochs.reject",
        "features.extract",
        "features.list",
        "features.get",
        "analysis.run",
        "analysis.list",
        "analysis.get",
        "datasets.build",
        "datasets.list",
        "datasets.get",
        "datasets.splits.create",
        "datasets.splits.list",
        "erp.compute",
        "ica.components.list",
        "ica.component.set_rejection",
        "ica.apply",
        "neuroflow.recommend_preprocessing",
        "neuroflow.detect_artifacts",
        "neuroflow.detect_lab_interference",
        "neuroflow.clean_continuous",
        "plans.create",
        "plans.list",
        "plans.get",
        "plans.default",
        "plans.execute",
        "augmentation.run",
        "neurostudio.templates.list",
        "neurostudio.templates.get",
        "neurostudio.templates.recommend",
        "neurostudio.experiments.create",
        "neurostudio.experiments.list",
        "neurostudio.experiments.get",
        "neurostudio.train.start",
        "neurostudio.hypertune.start",
        "neurostudio.eval.run",
        "neurostudio.generalization.run",
        "neurostudio.model.export",
        "neurostudio.infer.run",
        "neurostudio.explain.run",
        "neurostudio.leakage.check",
        "neurostudio.report.build",
        "study.export",
    ])
}

const IPC_TIMEOUT: Duration = Duration::from_secs(120);

/// Private per-launch IPC address: a Unix domain socket, or a named pipe on Windows.
#[cfg(unix)]
fn new_ipc_path() -> PathBuf {
    PathBuf::from(format!("/tmp/neurotendrils-{}.sock", Uuid::new_v4().simple()))
}

#[cfg(windows)]
fn new_ipc_path() -> PathBuf {
    PathBuf::from(format!(r"\\.\pipe\neurotendrils-{}", Uuid::new_v4().simple()))
}

/// Remove a leftover socket file. A named pipe disappears with the backend process.
fn remove_ipc_path(ipc_path: &Path) {
    if cfg!(unix) && ipc_path.exists() {
        let _ = std::fs::remove_file(ipc_path);
    }
}

/// Write one request line, read one response line.
fn exchange(stream: &mut (impl Read + Write), line: &str) -> Result<String, String> {
    stream
        .write_all(line.as_bytes())
        .map_err(|e| format!("ipc write: {e}"))?;
    let mut response = String::new();
    BufReader::new(stream)
        .read_line(&mut response)
        .map_err(|e| format!("ipc read: {e}"))?;
    Ok(response)
}

#[cfg(unix)]
fn ipc_send(ipc_path: &Path, line: &str) -> Result<String, String> {
    use std::net::Shutdown;
    use std::os::unix::net::UnixStream;

    let mut stream = UnixStream::connect(ipc_path).map_err(|e| format!("ipc connect: {e}"))?;
    stream.set_read_timeout(Some(IPC_TIMEOUT)).ok();
    let response = exchange(&mut stream, line);
    let _ = stream.shutdown(Shutdown::Both);
    response
}

#[cfg(windows)]
fn ipc_send(ipc_path: &Path, line: &str) -> Result<String, String> {
    // The backend serves one connection at a time and keeps one spare pipe instance, so
    // "busy" means queued behind another call: retry, as a socket's listen backlog would.
    const ERROR_PIPE_BUSY: i32 = 231;
    let start = Instant::now();
    let mut pipe = loop {
        match std::fs::OpenOptions::new().read(true).write(true).open(ipc_path) {
            Ok(pipe) => break pipe,
            Err(e) if e.raw_os_error() == Some(ERROR_PIPE_BUSY) && start.elapsed() < IPC_TIMEOUT => {
                thread::sleep(Duration::from_millis(20))
            }
            Err(e) => return Err(format!("ipc connect: {e}")),
        }
    };
    // Pipe handles have no read timeout, so wait for the reply on a worker thread.
    let line = line.to_string();
    let (tx, rx) = mpsc::channel();
    thread::spawn(move || {
        let _ = tx.send(exchange(&mut pipe, &line));
    });
    rx.recv_timeout(IPC_TIMEOUT)
        .unwrap_or_else(|_| Err("ipc read: timed out".into()))
}

fn call_python_ipc(ipc_path: &Path, command: &str, params: Value) -> Result<Value, String> {
    let request = json!({
        "id": Uuid::new_v4().to_string(),
        "command": command,
        "params": params,
    });
    let response = ipc_send(ipc_path, &format!("{request}\n"))?;
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

// `async`: a backend call can take minutes, and a sync command would block the main
// (UI) thread for that long.
#[tauri::command(async)]
fn suite_call(
    state: tauri::State<'_, AppState>,
    command: String,
    params: Option<Value>,
) -> Result<Value, String> {
    if !allowlisted_commands().contains(command.as_str()) {
        return Err(format!("command not allowlisted: {command}"));
    }
    // Release the lock before the round-trip so one slow call does not hold it.
    let ipc_path = {
        let guard = state.backend.lock().map_err(|_| "backend lock poisoned")?;
        guard.as_ref().ok_or("python backend not running")?.ipc_path.clone()
    };
    call_python_ipc(&ipc_path, &command, params.unwrap_or(json!({})))
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

/// `npm run setup` writes a placeholder so Tauri's `externalBin` exists in dev. It is
/// not a real backend (on Windows it cannot run at all); the repo venv is used instead.
fn is_dev_stub(path: &Path) -> bool {
    const MARKER: &[u8] = b"SUITE_DEV_SIDECAR_STUB";
    let mut head = [0u8; 256];
    std::fs::File::open(path)
        .and_then(|mut f| f.read(&mut head))
        .is_ok_and(|n| head[..n].windows(MARKER.len()).any(|w| w == MARKER))
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
        if candidate.is_file() && !is_dev_stub(&candidate) {
            return Some(candidate);
        }
        let nested = dir.join("binaries").join(&name);
        if nested.is_file() && !is_dev_stub(&nested) {
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

    // 3) Repo-root venv (dev) — created by `npm run setup` (scripts/ensure_dev.mjs)
    let venv_pythons: &[&str] = if cfg!(windows) {
        &["Scripts/python.exe"]
    } else {
        &["bin/python", "bin/python3"]
    };
    let mut dir = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    for _ in 0..8 {
        for name in venv_pythons {
            let candidate = dir.join(".venv").join(name);
            if candidate.is_file() {
                return Ok(BackendCmd::Module(candidate));
            }
        }
        if !dir.pop() {
            break;
        }
    }

    Err(
        "No backend found. Run `npm run setup` (dev) or `npm run sidecar` (PyInstaller) in apps/desktop."
            .into(),
    )
}

fn spawn_backend(app: &tauri::App, workspace: PathBuf) -> Result<BackendState, String> {
    let ipc_path = new_ipc_path();
    remove_ipc_path(&ipc_path);

    let launch = resolve_backend(app)?;
    let mut command = match &launch {
        BackendCmd::Sidecar(path) => Command::new(path),
        BackendCmd::Module(python) => {
            let mut cmd = Command::new(python);
            cmd.args(["-m", "suite_backend"]);
            cmd
        }
    };
    command
        .arg("--ipc")
        .arg(&ipc_path)
        .arg("--workspace")
        .arg(&workspace)
        // Windows otherwise decodes text files with the legacy ANSI code page.
        .env("PYTHONUTF8", "1");
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        // The release app is a GUI process; without this the backend opens a console window.
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    let label = match &launch {
        BackendCmd::Sidecar(p) => format!("sidecar {}", p.display()),
        BackendCmd::Module(p) => format!("module {}", p.display()),
    };

    let mut child = command
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|e| format!("failed to spawn backend ({label}): {e}"))?;

    // The backend prints one `{"event": "ready"}` line once it is listening (a named pipe
    // cannot be polled like a socket file). Keep draining stdout after that so a full pipe
    // never blocks the backend.
    let stdout = child.stdout.take().ok_or("backend stdout not captured")?;
    let (ready_tx, ready_rx) = mpsc::channel();
    thread::spawn(move || {
        let mut reader = BufReader::new(stdout);
        let mut ready_tx = Some(ready_tx);
        let mut line = Vec::new();
        while reader.read_until(b'\n', &mut line).is_ok_and(|n| n > 0) {
            let is_ready = serde_json::from_slice::<Value>(&line)
                .is_ok_and(|v| v.get("event").and_then(Value::as_str) == Some("ready"));
            if is_ready {
                if let Some(tx) = ready_tx.take() {
                    let _ = tx.send(());
                }
            }
            line.clear();
        }
    });

    // Generous: a first launch on Windows can spend a while unpacking and virus-scanning.
    let start = Instant::now();
    while start.elapsed() < Duration::from_secs(90) {
        if ready_rx.recv_timeout(Duration::from_millis(50)).is_ok() {
            return Ok(BackendState { child, ipc_path });
        }
        if let Ok(Some(status)) = child.try_wait() {
            return Err(format!("backend exited early ({label}): {status}"));
        }
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
        .manage(robot::RobotState(std::sync::Arc::new(robot::controller::Robot::new(
            robot::controller::Config::default(),
        ))))
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
        .invoke_handler(tauri::generate_handler![
            suite_call,
            robot::robot_list_ports,
            robot::robot_connect,
            robot::robot_disconnect,
            robot::robot_status,
            robot::robot_arm,
            robot::robot_disarm,
            robot::robot_preset,
            robot::robot_decoder_command,
            robot::robot_estop,
            robot::robot_clear_estop
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if let tauri::RunEvent::Exit = event {
                if let Some(state) = app_handle.try_state::<AppState>() {
                    if let Ok(mut guard) = state.backend.lock() {
                        if let Some(mut backend) = guard.take() {
                            let _ = backend.child.kill();
                            remove_ipc_path(&backend.ipc_path);
                        }
                    }
                }
            }
        });
}
