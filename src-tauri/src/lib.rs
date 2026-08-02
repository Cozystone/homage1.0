use std::net::TcpListener;
use std::path::PathBuf;
use std::sync::Mutex;

use serde::Serialize;
use tauri::{Manager, RunEvent, State};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

#[derive(Default)]
struct ApiRuntimeState {
    child: Mutex<Option<CommandChild>>,
    api_base_url: Mutex<Option<String>>,
    data_dir: Mutex<Option<PathBuf>>,
}

#[derive(Serialize)]
struct DesktopRuntimeInfo {
    api_base_url: Option<String>,
    data_dir: Option<String>,
    sidecar_running: bool,
}

fn find_free_port() -> Result<u16, String> {
    let listener = TcpListener::bind("127.0.0.1:0").map_err(|error| error.to_string())?;
    let port = listener.local_addr().map_err(|error| error.to_string())?.port();
    drop(listener);
    Ok(port)
}

fn operator_data_dir(app: &tauri::App) -> Result<PathBuf, Box<dyn std::error::Error>> {
    if let Ok(override_dir) = std::env::var("ATANOR_OPERATOR_DATA_DIR")
        .or_else(|_| std::env::var("HOMAGE_OPERATOR_DATA_DIR"))
    {
        if !override_dir.trim().is_empty() {
            return Ok(PathBuf::from(override_dir));
        }
    }
    if is_operator_binary() {
        if let Ok(local_app_data) = std::env::var("LOCALAPPDATA") {
            return Ok(PathBuf::from(local_app_data).join("Homage"));
        }
    }
    Ok(app.path().app_data_dir()?)
}

fn kill_sidecar(app: &tauri::AppHandle) {
    if let Some(state) = app.try_state::<ApiRuntimeState>() {
        if let Ok(mut guard) = state.child.lock() {
            if let Some(child) = guard.take() {
                let _ = child.kill();
            }
        }
    }
}

fn spawn_python_sidecar(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let port = find_free_port()?;
    let data_dir = operator_data_dir(app)?;
    std::fs::create_dir_all(&data_dir)?;
    let api_base_url = format!("http://127.0.0.1:{port}");

    let mut args = vec![
        "--host".to_string(),
        "127.0.0.1".to_string(),
        "--port".to_string(),
        port.to_string(),
        "--data-dir".to_string(),
        data_dir.to_string_lossy().to_string(),
    ];
    if is_operator_binary() {
        args.push("--operator".to_string());
    }

    let (mut rx, child) = app.shell().sidecar("homage-api")?.args(args).spawn()?;

    let state = app.state::<ApiRuntimeState>();
    *state.api_base_url.lock().map_err(|_| "api state poisoned")? = Some(api_base_url);
    *state.data_dir.lock().map_err(|_| "data dir state poisoned")? = Some(data_dir);
    *state.child.lock().map_err(|_| "child state poisoned")? = Some(child);

    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    let line = String::from_utf8_lossy(&line);
                    println!("[homage-api] {line}");
                }
                CommandEvent::Stderr(line) => {
                    let line = String::from_utf8_lossy(&line);
                    eprintln!("[homage-api] {line}");
                }
                CommandEvent::Terminated(payload) => {
                    eprintln!("[homage-api] terminated: {payload:?}");
                    break;
                }
                _ => {}
            }
        }
    });

    Ok(())
}

fn is_operator_binary() -> bool {
    std::env::current_exe()
        .ok()
        .and_then(|path| path.file_stem().map(|name| name.to_string_lossy().to_lowercase()))
        .map(|name| name.contains("operator"))
        .unwrap_or(false)
}

fn route_operator_window(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    if !is_operator_binary() {
        return Ok(());
    }
    if let Some(window) = app.get_webview_window("main") {
        window.set_title("ATANOR Operator")?;
        let _ = window.eval("window.location.replace('/admin')");
    }
    Ok(())
}

#[tauri::command]
fn get_desktop_runtime(state: State<ApiRuntimeState>) -> DesktopRuntimeInfo {
    let api_base_url = state.api_base_url.lock().ok().and_then(|value| value.clone());
    let data_dir = state
        .data_dir
        .lock()
        .ok()
        .and_then(|value| value.as_ref().map(|path| path.to_string_lossy().to_string()));
    let sidecar_running = state.child.lock().map(|guard| guard.is_some()).unwrap_or(false);
    DesktopRuntimeInfo {
        api_base_url,
        data_dir,
        sidecar_running,
    }
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(ApiRuntimeState::default())
        .invoke_handler(tauri::generate_handler![get_desktop_runtime])
        .setup(|app| {
            spawn_python_sidecar(app)?;
            route_operator_window(app)?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building ATANOR desktop application")
        .run(|app, event| match event {
            RunEvent::ExitRequested { .. } | RunEvent::Exit => kill_sidecar(app),
            _ => {}
        });
}
