#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // The UI talks to the local backend over loopback HTTP; there are no custom
    // Tauri commands, so no invoke_handler is registered.
    tauri::Builder::default()
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
