use std::{
    collections::HashSet,
    fs::OpenOptions,
    io::{Read, Write},
    net::TcpStream,
    process::{Child, Command, Stdio},
    sync::Mutex,
    time::Duration,
};
use tauri::{
    image::Image,
    menu::{Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager, WindowEvent,
};
use tauri_plugin_autostart::ManagerExt as AutostartExt;
use tauri_plugin_global_shortcut::{GlobalShortcutExt, ShortcutState};
use tauri_plugin_notification::NotificationExt;

const RUNTIME_HOST: &str = "127.0.0.1:37655";
const DEFAULT_RUNTIME_SIDECAR: &str =
    "/home/midea/GithubRepository/DeskVane/scripts/run-runtime-api.sh";

struct SidecarState(Mutex<Option<Child>>);

struct RuntimeHotkey {
    config_section: &'static str,
    config_field: &'static str,
    fallback: &'static str,
    action: &'static str,
}

const RUNTIME_HOTKEYS: &[RuntimeHotkey] = &[
    RuntimeHotkey {
        config_section: "screenshot",
        config_field: "hotkey",
        fallback: "<ctrl>+<shift>+a",
        action: "capture.screenshot",
    },
    RuntimeHotkey {
        config_section: "screenshot",
        config_field: "hotkey_pin",
        fallback: "<f1>",
        action: "capture.screenshot_and_pin",
    },
    RuntimeHotkey {
        config_section: "screenshot",
        config_field: "hotkey_interactive",
        fallback: "<ctrl>+<f1>",
        action: "capture.interactive_screenshot",
    },
    RuntimeHotkey {
        config_section: "screenshot",
        config_field: "hotkey_pure_ocr",
        fallback: "<alt>+<f1>",
        action: "capture.pure_ocr",
    },
    RuntimeHotkey {
        config_section: "screenshot",
        config_field: "hotkey_pin_clipboard",
        fallback: "<f3>",
        action: "capture.pin_clipboard",
    },
    RuntimeHotkey {
        config_section: "general",
        config_field: "hotkey_clipboard_history",
        fallback: "<alt>+v",
        action: "clipboard.show_history",
    },
    RuntimeHotkey {
        config_section: "translator",
        config_field: "hotkey_toggle_pause",
        fallback: "<ctrl>+<alt>+t",
        action: "translator.toggle_pause",
    },
];

fn show_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.set_focus();
    }
}

fn post_runtime_action(action: &str) -> std::io::Result<()> {
    let body = "{}";
    let request = format!(
        "POST /actions/{action} HTTP/1.1\r\n\
         Host: {host}\r\n\
         Content-Type: application/json\r\n\
         Content-Length: {length}\r\n\
         Connection: close\r\n\r\n\
         {body}",
        action = action,
        host = RUNTIME_HOST,
        length = body.len(),
        body = body,
    );
    let mut stream = TcpStream::connect(RUNTIME_HOST)?;
    stream.set_read_timeout(Some(Duration::from_secs(2)))?;
    stream.set_write_timeout(Some(Duration::from_secs(2)))?;
    stream.write_all(request.as_bytes())?;
    let mut response = String::new();
    stream.read_to_string(&mut response)?;
    if response.starts_with("HTTP/1.1 200") || response.starts_with("HTTP/1.0 200") {
        Ok(())
    } else {
        Err(std::io::Error::new(std::io::ErrorKind::Other, response))
    }
}

fn get_runtime_json(path: &str) -> std::io::Result<serde_json::Value> {
    let request = format!(
        "GET {path} HTTP/1.1\r\n\
         Host: {host}\r\n\
         Connection: close\r\n\r\n",
        path = path,
        host = RUNTIME_HOST,
    );
    let mut stream = TcpStream::connect(RUNTIME_HOST)?;
    stream.set_read_timeout(Some(Duration::from_secs(2)))?;
    stream.set_write_timeout(Some(Duration::from_secs(2)))?;
    stream.write_all(request.as_bytes())?;
    let mut response = String::new();
    stream.read_to_string(&mut response)?;
    if !(response.starts_with("HTTP/1.1 200") || response.starts_with("HTTP/1.0 200")) {
        return Err(std::io::Error::new(std::io::ErrorKind::Other, response));
    }
    let Some((_headers, body)) = response.split_once("\r\n\r\n") else {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "invalid HTTP response",
        ));
    };
    serde_json::from_str(body)
        .map_err(|error| std::io::Error::new(std::io::ErrorKind::InvalidData, error))
}

fn notify_user(app: &AppHandle, title: &str, body: &str) {
    let _ = app.notification().builder().title(title).body(body).show();
}

fn dispatch_runtime_action(app: &AppHandle, action: &'static str) {
    let handle = app.clone();
    std::thread::spawn(move || {
        if let Err(error) = post_runtime_action(action) {
            eprintln!("DeskVane runtime action failed ({action}): {error}");
            notify_user(&handle, "DeskVane 动作失败", &format!("{action}: {error}"));
        }
    });
}

fn wait_for_runtime() -> bool {
    for _ in 0..20 {
        if get_runtime_json("/health").is_ok() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    false
}

fn runtime_config_hotkey(config: &serde_json::Value, hotkey: &RuntimeHotkey) -> String {
    config
        .get(hotkey.config_section)
        .and_then(|section| section.get(hotkey.config_field))
        .and_then(|value| value.as_str())
        .filter(|value| !value.trim().is_empty())
        .unwrap_or(hotkey.fallback)
        .to_string()
}

fn runtime_config_autostart_enabled(config: &serde_json::Value) -> bool {
    config
        .get("general")
        .and_then(|section| section.get("autostart_enabled"))
        .and_then(|value| value.as_bool())
        .unwrap_or(false)
}

fn normalize_hotkey(raw: &str) -> Option<String> {
    let mut parts = Vec::new();
    for token in raw.split('+') {
        let token = token.trim().trim_start_matches('<').trim_end_matches('>');
        if token.is_empty() {
            return None;
        }
        let normalized = match token.to_ascii_lowercase().as_str() {
            "ctrl" | "control" => "Ctrl".to_string(),
            "alt" | "option" => "Alt".to_string(),
            "shift" => "Shift".to_string(),
            "cmd" | "command" | "super" | "meta" => "Super".to_string(),
            other if other.len() == 1 => other.to_ascii_uppercase(),
            other if other.starts_with('f') && other[1..].chars().all(|ch| ch.is_ascii_digit()) => {
                other.to_ascii_uppercase()
            }
            other => other.to_string(),
        };
        parts.push(normalized);
    }
    Some(parts.join("+"))
}

fn sync_autostart_from_config(app: &AppHandle) {
    if !wait_for_runtime() {
        eprintln!("DeskVane runtime API did not become ready; autostart was not synced");
        return;
    }
    let Ok(config) = get_runtime_json("/config") else {
        eprintln!("DeskVane runtime config unavailable; autostart was not synced");
        return;
    };
    let desired = runtime_config_autostart_enabled(&config);
    let manager = app.autolaunch();
    let current = manager.is_enabled().unwrap_or(false);
    let result = if desired && !current {
        manager.enable()
    } else if !desired && current {
        manager.disable()
    } else {
        Ok(())
    };
    if let Err(error) = result {
        eprintln!("DeskVane autostart sync failed: {error}");
    }
}

fn update_tray_tooltip(app: &AppHandle) {
    let Ok(state) = get_runtime_json("/state") else {
        return;
    };
    let translator = state
        .get("translator")
        .and_then(|value| value.get("status_text"))
        .and_then(|value| value.as_str())
        .unwrap_or("未知");
    let clipboard = state
        .get("clipboard_history")
        .and_then(|value| value.get("item_count"))
        .and_then(|value| value.as_i64())
        .unwrap_or(0);
    let git_proxy = state
        .get("proxy")
        .and_then(|value| value.get("git_proxy_enabled"))
        .and_then(|value| value.as_bool())
        .unwrap_or(false);
    let terminal_proxy = state
        .get("proxy")
        .and_then(|value| value.get("terminal_proxy_enabled"))
        .and_then(|value| value.as_bool())
        .unwrap_or(false);
    let cpu_line = match (
        json_f64_at(&state, &["system", "cpu", "usage_pct"]),
        json_f64_at(&state, &["system", "cpu", "temp_c"]),
    ) {
        (Some(usage), Some(temp)) => format!("CPU: {usage:.0}%  {temp:.0}°C"),
        (Some(usage), None) => format!("CPU: {usage:.0}%"),
        _ => "CPU: 未知".to_string(),
    };
    let gpu_line = match (
        json_f64_at(&state, &["system", "gpu", "usage_pct"]),
        json_f64_at(&state, &["system", "gpu", "temp_c"]),
        json_i64_at(&state, &["system", "gpu", "mem_used_mb"]),
        json_i64_at(&state, &["system", "gpu", "mem_total_mb"]),
    ) {
        (Some(usage), Some(temp), Some(used), Some(total)) if total > 0 => {
            let used_gb = used as f64 / 1024.0;
            let total_gb = total as f64 / 1024.0;
            let mem_pct = used as f64 / total as f64 * 100.0;
            format!(
                "GPU: {usage:.0}%  {temp:.0}°C  显存 {mem_pct:.0}% ({used_gb:.1}/{total_gb:.0}G)"
            )
        }
        (Some(usage), Some(temp), _, _) => format!("GPU: {usage:.0}%  {temp:.0}°C"),
        _ => "GPU: 未知".to_string(),
    };
    let tooltip = format!(
        "DeskVane\n{cpu_line}\n{gpu_line}\n翻译: {translator}\n剪贴板: {clipboard} 条\nGit 代理: {git}\n终端代理: {terminal}",
        cpu_line = cpu_line,
        gpu_line = gpu_line,
        translator = translator,
        clipboard = clipboard,
        git = if git_proxy { "开启" } else { "关闭" },
        terminal = if terminal_proxy { "开启" } else { "关闭" },
    );
    if let Some(tray) = app.tray_by_id("main") {
        let _ = tray.set_tooltip(Some(tooltip));
    }
}

fn json_f64_at<'a>(value: &'a serde_json::Value, path: &[&str]) -> Option<f64> {
    let mut current = value;
    for key in path {
        current = current.get(*key)?;
    }
    current.as_f64()
}

fn json_i64_at<'a>(value: &'a serde_json::Value, path: &[&str]) -> Option<i64> {
    let mut current = value;
    for key in path {
        current = current.get(*key)?;
    }
    current.as_i64()
}

fn json_str_at<'a>(value: &'a serde_json::Value, path: &[&str]) -> Option<&'a str> {
    let mut current = value;
    for key in path {
        current = current.get(*key)?;
    }
    current.as_str()
}

fn fill_rect(
    rgba: &mut [u8],
    width: usize,
    x: usize,
    y: usize,
    w: usize,
    h: usize,
    color: [u8; 4],
) {
    for yy in y..(y + h).min(width) {
        for xx in x..(x + w).min(width) {
            let idx = (yy * width + xx) * 4;
            rgba[idx..idx + 4].copy_from_slice(&color);
        }
    }
}

fn draw_segment_digit(rgba: &mut [u8], x: usize, y: usize, digit: u8, color: [u8; 4]) {
    const DIGITS: [[bool; 7]; 10] = [
        [true, true, true, true, true, true, false],
        [false, true, true, false, false, false, false],
        [true, true, false, true, true, false, true],
        [true, true, true, true, false, false, true],
        [false, true, true, false, false, true, true],
        [true, false, true, true, false, true, true],
        [true, false, true, true, true, true, true],
        [true, true, true, false, false, false, false],
        [true, true, true, true, true, true, true],
        [true, true, true, true, false, true, true],
    ];
    let Some(segments) = DIGITS.get(digit as usize) else {
        return;
    };
    let rects = [
        (x + 5, y, 17, 5),
        (x + 22, y + 5, 5, 17),
        (x + 22, y + 29, 5, 17),
        (x + 5, y + 46, 17, 5),
        (x, y + 29, 5, 17),
        (x, y + 5, 5, 17),
        (x + 5, y + 23, 17, 5),
    ];
    for (enabled, (rx, ry, rw, rh)) in segments.iter().zip(rects) {
        if *enabled {
            fill_rect(rgba, 64, rx, ry, rw, rh, color);
        }
    }
}

fn draw_icon_value(rgba: &mut [u8], value: Option<i64>, color: [u8; 4]) {
    let Some(value) = value else {
        fill_rect(rgba, 64, 9, 29, 46, 7, color);
        return;
    };
    let clamped = value.clamp(0, 99) as u8;
    draw_segment_digit(rgba, 3, 7, clamped / 10, color);
    draw_segment_digit(rgba, 34, 7, clamped % 10, color);
}

fn draw_icon_meter(rgba: &mut [u8], pct: i64, color: [u8; 4]) {
    let clamped = pct.clamp(0, 100) as usize;
    fill_rect(rgba, 64, 56, 8, 4, 48, [44, 49, 63, 255]);
    if clamped == 0 {
        return;
    }
    let fill_height = (44 * clamped / 100).max(1);
    fill_rect(rgba, 64, 56, 56 - fill_height, 4, fill_height, color);
}

fn build_tray_image(mode: &str, state: Option<&serde_json::Value>) -> Image<'static> {
    let mut rgba = vec![0_u8; 64 * 64 * 4];
    let mut value = None;
    let mut meter = 0_i64;
    let mut value_color = [255, 255, 255, 255];

    if mode == "default" {
        fill_rect(&mut rgba, 64, 4, 4, 56, 56, [91, 97, 246, 255]);
        fill_rect(&mut rgba, 64, 19, 15, 7, 34, [255, 255, 255, 255]);
        fill_rect(&mut rgba, 64, 26, 24, 20, 7, [255, 255, 255, 255]);
        fill_rect(&mut rgba, 64, 26, 33, 20, 7, [255, 255, 255, 255]);
        return Image::new_owned(rgba, 64, 64);
    }

    if let Some(state) = state {
        match mode {
            "cpu_usage" => {
                value =
                    json_f64_at(state, &["system", "cpu", "usage_pct"]).map(|v| v.round() as i64);
                meter = value.unwrap_or(0);
                value_color = [158, 255, 178, 255];
            }
            "cpu_temp" => {
                value = json_f64_at(state, &["system", "cpu", "temp_c"]).map(|v| v.round() as i64);
                meter = value.unwrap_or(0);
                value_color = [255, 191, 128, 255];
            }
            "gpu_usage" => {
                value =
                    json_f64_at(state, &["system", "gpu", "usage_pct"]).map(|v| v.round() as i64);
                meter = value.unwrap_or(0);
                value_color = [139, 190, 255, 255];
            }
            "gpu_temp" => {
                value = json_f64_at(state, &["system", "gpu", "temp_c"]).map(|v| v.round() as i64);
                meter = value.unwrap_or(0);
                value_color = [255, 191, 128, 255];
            }
            "gpu_mem" => {
                let used = json_i64_at(state, &["system", "gpu", "mem_used_mb"]).unwrap_or(0);
                let total = json_i64_at(state, &["system", "gpu", "mem_total_mb"]).unwrap_or(0);
                if total > 0 {
                    let pct = (used as f64 / total as f64 * 100.0).round() as i64;
                    value = Some(pct);
                    meter = pct;
                }
                value_color = [225, 180, 255, 255];
            }
            _ => {}
        }
    }

    if meter >= 80 {
        value_color = [255, 118, 118, 255];
    }
    fill_rect(&mut rgba, 64, 0, 0, 64, 64, [16, 18, 24, 255]);
    draw_icon_value(&mut rgba, value, value_color);
    draw_icon_meter(&mut rgba, meter, value_color);
    Image::new_owned(rgba, 64, 64)
}

fn update_tray_visual(app: &AppHandle) {
    let config = get_runtime_json("/config").ok();
    let state = get_runtime_json("/state").ok();
    let mode = config
        .as_ref()
        .and_then(|config| json_str_at(config, &["general", "tray_display"]))
        .unwrap_or("default");
    let image = build_tray_image(mode, state.as_ref());
    if let Some(tray) = app.tray_by_id("main") {
        let _ = tray.set_icon(Some(image));
    }
}

fn register_runtime_hotkeys(app: &AppHandle) {
    if !wait_for_runtime() {
        eprintln!("DeskVane runtime API did not become ready; global hotkeys were not registered");
        return;
    }
    if let Err(error) = app.global_shortcut().unregister_all() {
        eprintln!("DeskVane hotkey cleanup failed: {error}");
    }
    let Ok(config) = get_runtime_json("/config") else {
        eprintln!("DeskVane runtime config unavailable; global hotkeys were not registered");
        return;
    };
    let supported_actions = get_runtime_json("/actions")
        .ok()
        .and_then(|value| {
            value
                .get("actions")
                .and_then(|actions| actions.as_array())
                .cloned()
        })
        .map(|actions| {
            actions
                .into_iter()
                .filter_map(|action| action.as_str().map(str::to_string))
                .collect::<HashSet<_>>()
        })
        .unwrap_or_default();

    for hotkey in RUNTIME_HOTKEYS {
        if !supported_actions.contains(hotkey.action) {
            continue;
        }
        let raw = runtime_config_hotkey(&config, hotkey);
        let Some(shortcut) = normalize_hotkey(&raw) else {
            eprintln!("DeskVane hotkey ignored: {raw}");
            continue;
        };
        let action = hotkey.action;
        if let Err(error) =
            app.global_shortcut()
                .on_shortcut(shortcut.as_str(), move |app, _shortcut, event| {
                    if event.state == ShortcutState::Pressed {
                        dispatch_runtime_action(app, action);
                    }
                })
        {
            eprintln!("DeskVane hotkey registration failed ({raw} -> {shortcut}): {error}");
        }
    }
}

fn start_hotkey_event_watcher(app: AppHandle) {
    std::thread::spawn(move || {
        let mut last_event_id = 0_i64;
        let mut last_tooltip_refresh = std::time::Instant::now() - Duration::from_secs(60);
        let mut last_visual_refresh = std::time::Instant::now() - Duration::from_secs(60);
        loop {
            let path = format!("/events?after_id={last_event_id}&limit=50");
            if let Ok(payload) = get_runtime_json(&path) {
                if let Some(events) = payload.get("events").and_then(|value| value.as_array()) {
                    let mut should_reload = false;
                    let mut should_update_tooltip = false;
                    for event in events {
                        if let Some(id) = event.get("id").and_then(|value| value.as_i64()) {
                            last_event_id = last_event_id.max(id);
                        }
                        match event.get("topic").and_then(|value| value.as_str()) {
                            Some("config.updated") => {
                                should_reload = true;
                                should_update_tooltip = true;
                            }
                            Some("translator.auto_translated") => {
                                let message = event
                                    .get("message")
                                    .and_then(|value| value.as_str())
                                    .unwrap_or("剪贴板文本已翻译");
                                notify_user(&app, "DeskVane 翻译完成", message);
                                should_update_tooltip = true;
                            }
                            Some("translator.error") => {
                                let message = event
                                    .get("message")
                                    .and_then(|value| value.as_str())
                                    .unwrap_or("剪贴板翻译失败");
                                notify_user(&app, "DeskVane 翻译失败", message);
                                should_update_tooltip = true;
                            }
                            Some("action.dispatched")
                            | Some("clipboard.selected")
                            | Some("legacy.action") => {
                                should_update_tooltip = true;
                            }
                            _ => {}
                        }
                    }
                    if should_reload {
                        sync_autostart_from_config(&app);
                        register_runtime_hotkeys(&app);
                    }
                    if should_update_tooltip {
                        update_tray_tooltip(&app);
                        update_tray_visual(&app);
                        last_tooltip_refresh = std::time::Instant::now();
                        last_visual_refresh = std::time::Instant::now();
                    }
                }
            }
            if last_visual_refresh.elapsed() >= Duration::from_secs(1) {
                update_tray_visual(&app);
                last_visual_refresh = std::time::Instant::now();
            }
            if last_tooltip_refresh.elapsed() >= Duration::from_secs(10) {
                update_tray_tooltip(&app);
                last_tooltip_refresh = std::time::Instant::now();
            }
            std::thread::sleep(Duration::from_secs(1));
        }
    });
}

fn start_python_sidecar() -> std::io::Result<Child> {
    let sidecar = std::env::var("DESKVANE_RUNTIME_SIDECAR")
        .unwrap_or_else(|_| DEFAULT_RUNTIME_SIDECAR.to_string());
    let log = OpenOptions::new()
        .create(true)
        .append(true)
        .open("/tmp/deskvane-runtime-api.log")?;
    let log_for_stderr = log.try_clone()?;
    Command::new(sidecar)
        .stdout(Stdio::from(log))
        .stderr(Stdio::from(log_for_stderr))
        .spawn()
}

fn stop_python_sidecar(app: &AppHandle) {
    let Some(state) = app.try_state::<SidecarState>() else {
        return;
    };
    let Ok(mut guard) = state.0.lock() else {
        return;
    };
    if let Some(mut child) = guard.take() {
        let _ = child.kill();
        let _ = child.wait();
    }
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            match start_python_sidecar() {
                Ok(child) => app.manage(SidecarState(Mutex::new(Some(child)))),
                Err(error) => {
                    eprintln!("DeskVane runtime sidecar failed to start: {error}");
                    app.manage(SidecarState(Mutex::new(None)))
                }
            };
            sync_autostart_from_config(app.handle());
            register_runtime_hotkeys(app.handle());
            update_tray_tooltip(app.handle());
            update_tray_visual(app.handle());
            start_hotkey_event_watcher(app.handle().clone());

            let show = MenuItem::with_id(app, "show", "显示", true, None::<&str>)?;
            let screenshot = MenuItem::with_id(
                app,
                "capture.screenshot_and_pin",
                "截图并钉住",
                true,
                None::<&str>,
            )?;
            let ocr = MenuItem::with_id(app, "capture.pure_ocr", "纯 OCR", true, None::<&str>)?;
            let clipboard = MenuItem::with_id(
                app,
                "clipboard.show_history",
                "剪贴板历史",
                true,
                None::<&str>,
            )?;
            let settings = MenuItem::with_id(app, "settings.show", "完整设置", true, None::<&str>)?;
            let git_proxy =
                MenuItem::with_id(app, "proxy.toggle_git", "切换 Git 代理", true, None::<&str>)?;
            let terminal_proxy = MenuItem::with_id(
                app,
                "proxy.toggle_terminal",
                "切换终端代理",
                true,
                None::<&str>,
            )?;
            let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
            let separator = PredefinedMenuItem::separator(app)?;
            let menu = Menu::with_items(
                app,
                &[
                    &show,
                    &separator,
                    &screenshot,
                    &ocr,
                    &clipboard,
                    &settings,
                    &separator,
                    &git_proxy,
                    &terminal_proxy,
                    &separator,
                    &quit,
                ],
            )?;
            let handle = app.handle().clone();
            let initial_config = get_runtime_json("/config").ok();
            let initial_state = get_runtime_json("/state").ok();
            let initial_mode = initial_config
                .as_ref()
                .and_then(|config| json_str_at(config, &["general", "tray_display"]))
                .unwrap_or("default");

            TrayIconBuilder::with_id("main")
                .icon(build_tray_image(initial_mode, initial_state.as_ref()))
                .tooltip("DeskVane")
                .menu(&menu)
                .on_menu_event(move |app, event| match event.id.as_ref() {
                    "show" => show_main_window(app),
                    "capture.screenshot_and_pin" => {
                        dispatch_runtime_action(app, "capture.screenshot_and_pin")
                    }
                    "capture.pure_ocr" => dispatch_runtime_action(app, "capture.pure_ocr"),
                    "clipboard.show_history" => {
                        dispatch_runtime_action(app, "clipboard.show_history")
                    }
                    "settings.show" => dispatch_runtime_action(app, "settings.show"),
                    "proxy.toggle_git" => dispatch_runtime_action(app, "proxy.toggle_git"),
                    "proxy.toggle_terminal" => {
                        dispatch_runtime_action(app, "proxy.toggle_terminal")
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(move |_tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        show_main_window(&handle);
                    }
                })
                .build(app)?;
            Ok(())
        })
        .plugin(
            tauri_plugin_autostart::Builder::new()
                .app_name("DeskVane")
                .build(),
        )
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_shell::init())
        .build(tauri::generate_context!())
        .expect("error while building DeskVane")
        .run(|app, event| {
            if let tauri::RunEvent::WindowEvent {
                label,
                event: WindowEvent::CloseRequested { api, .. },
                ..
            } = &event
            {
                api.prevent_close();
                if let Some(window) = app.get_webview_window(label) {
                    let _ = window.hide();
                }
                return;
            }
            if matches!(
                event,
                tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit
            ) {
                stop_python_sidecar(app);
            }
        });
}
