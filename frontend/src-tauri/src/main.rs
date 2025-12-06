#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

// Minimal Tauri shell. Wire backend bridges here later (e.g., commands that
// proxy to the Python service).
fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![])
        .run(tauri::generate_context!())
        .expect("error while running Algent");
}
