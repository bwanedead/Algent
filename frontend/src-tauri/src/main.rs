#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::Manager;

struct BackendProcess(Mutex<Option<Child>>);

fn spawn_backend() -> Option<Child> {
    if !cfg!(debug_assertions) {
        return None;
    }

    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let backend_dir = manifest_dir.join("..").join("..").join("backend");
    let venv_python = backend_dir
        .join(".venv")
        .join("Scripts")
        .join("python.exe");

    let mut command = if venv_python.exists() {
        let mut cmd = Command::new(venv_python);
        cmd.current_dir(&backend_dir)
            .arg("-m")
            .arg("algent_backend.app");
        cmd
    } else {
        let mut cmd = Command::new("python");
        cmd.current_dir(&backend_dir)
            .arg("-m")
            .arg("algent_backend.app");
        cmd
    };

    command
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
        .ok()
}

// Minimal Tauri shell. Wire backend bridges here later (e.g., commands that
// proxy to the Python service).
fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let child = spawn_backend();
            app.manage(BackendProcess(Mutex::new(child)));
            Ok(())
        })
        .on_window_event(|event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event.event() {
                api.prevent_close();
                if let Ok(mut guard) = event.window().state::<BackendProcess>().0.lock() {
                    if let Some(mut child) = guard.take() {
                        let _ = child.kill();
                    }
                }
                let _ = event.window().close();
            }
        })
        .invoke_handler(tauri::generate_handler![])
        .run(tauri::generate_context!())
        .expect("error while running Algent");
}
