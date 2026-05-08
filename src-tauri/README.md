# DeskVane Tauri Shell

This is the initial Tauri 2 shell for the long-term migration.

Current scope:

- Main window hosting `frontend/`
- Basic tray menu
- Shell plugin enabled for future sidecar supervision

The current machine does not have Cargo/Rust installed, so this shell has not
yet been compiled locally.

After installing Rust and Tauri prerequisites:

```bash
npm --prefix frontend run build
cargo build --manifest-path src-tauri/Cargo.toml
```

For development with Tauri CLI, use the standard Tauri workflow after installing
the CLI/tooling required by Tauri 2.
