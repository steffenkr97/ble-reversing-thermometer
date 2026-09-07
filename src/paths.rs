use std::path::{Path, PathBuf};

/// Repo-Wurzel: `CARGO_MANIFEST_DIR`, sonst cwd/Eltern mit `dashboard/rooms.json`.
pub fn repo_root() -> PathBuf {
    if let Ok(manifest) = std::env::var("CARGO_MANIFEST_DIR") {
        let p = PathBuf::from(manifest);
        if p.join("dashboard").join("rooms.json").is_file() {
            return p;
        }
    }
    let mut dir = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    loop {
        if dir.join("dashboard").join("rooms.json").is_file() {
            return dir;
        }
        if !dir.pop() {
            break;
        }
    }
    PathBuf::from(".")
}

pub fn default_rooms_path() -> PathBuf {
    repo_root().join("dashboard").join("rooms.json")
}

pub fn default_data_dir() -> PathBuf {
    repo_root().join("data")
}

pub fn default_extract_dir() -> PathBuf {
    repo_root().join("hci-logs").join("extract")
}

pub fn default_static_dir() -> PathBuf {
    repo_root().join("dashboard").join("static")
}

pub fn resolve_path(path: impl AsRef<Path>) -> PathBuf {
    let path = path.as_ref();
    if path.is_absolute() {
        path.to_path_buf()
    } else {
        repo_root().join(path)
    }
}
