const API_BASE = "http://127.0.0.1:37655";

const runtimeStatus = document.querySelector("#runtime-status");
const runtimeChip = document.querySelector("#runtime-chip");
const trayChip = document.querySelector("#tray-chip");
const gpuMemChip = document.querySelector("#gpu-mem-chip");
const translatorChip = document.querySelector("#translator-chip");
const stateUpdated = document.querySelector("#state-updated");
const trayModeLabel = document.querySelector("#tray-mode-label");
const trayPreview = document.querySelector("#tray-preview");
const cpuMetric = document.querySelector("#cpu-metric");
const gpuMetric = document.querySelector("#gpu-metric");
const proxyMetric = document.querySelector("#proxy-metric");
const subconverterMetric = document.querySelector("#subconverter-metric");
const actionStatus = document.querySelector("#action-status");
const gitProxyAction = document.querySelector("#git-proxy-action");
const terminalProxyAction = document.querySelector("#terminal-proxy-action");
const translatorPauseAction = document.querySelector("#translator-pause-action");
const proxyPageStatus = document.querySelector("#proxy-page-status");
const proxyAddressView = document.querySelector("#proxy-address-view");
const gitProxyView = document.querySelector("#git-proxy-view");
const terminalProxyView = document.querySelector("#terminal-proxy-view");
const subconverterPageStatus = document.querySelector("#subconverter-page-status");
const subconverterEnabledView = document.querySelector("#subconverter-enabled-view");
const subconverterPortView = document.querySelector("#subconverter-port-view");
const subconverterRunningView = document.querySelector("#subconverter-running-view");
const subconverterUrlView = document.querySelector("#subconverter-url-view");
const subconverterLocalUrl = document.querySelector("#subconverter-local-url");
const subconverterHealthView = document.querySelector("#subconverter-health-view");
const captureSaveMode = document.querySelector("#capture-save-mode");
const captureSaveDirView = document.querySelector("#capture-save-dir-view");
const captureHotkeyView = document.querySelector("#capture-hotkey-view");
const captureHotkeyPinView = document.querySelector("#capture-hotkey-pin-view");
const captureHotkeyInteractiveView = document.querySelector("#capture-hotkey-interactive-view");
const captureHotkeyOcrView = document.querySelector("#capture-hotkey-ocr-view");
const captureHotkeyClipboardView = document.querySelector("#capture-hotkey-clipboard-view");
const captureCopyView = document.querySelector("#capture-copy-view");
const captureDiskView = document.querySelector("#capture-disk-view");
const translatorMonitorView = document.querySelector("#translator-monitor-view");
const translatorBackendView = document.querySelector("#translator-backend-view");
const translatorModelView = document.querySelector("#translator-model-view");
const translatorHostView = document.querySelector("#translator-host-view");
const translatorLanguageView = document.querySelector("#translator-language-view");
const translatorClipboardView = document.querySelector("#translator-clipboard-view");
const translatorAutoCopyView = document.querySelector("#translator-auto-copy-view");
const configView = document.querySelector("#config-view");
const configForm = document.querySelector("#config-form");
const configJsonSave = document.querySelector("#config-json-save");
const configSaveStatus = document.querySelector("#config-save-status");
const translatorForm = document.querySelector("#translator-form");
const translatorStatus = document.querySelector("#translator-status");
const translatorResult = document.querySelector("#translator-result");
const clipboardList = document.querySelector("#clipboard-list");
const clipboardCount = document.querySelector("#clipboard-count");
const clipboardSearch = document.querySelector("#clipboard-search");
const clipboardSelectedIndex = document.querySelector("#clipboard-selected-index");
const clipboardSelectedPreview = document.querySelector("#clipboard-selected-preview");
const proxyEventList = document.querySelector("#proxy-event-list");

let lastEventId = 0;
const events = [];
let configJsonDirty = false;
let currentConfig = null;
let currentState = null;
let clipboardItems = [];
let clipboardQuery = "";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status} ${body}`);
  }
  return response.json();
}

function setRuntimeStatus(ok, message) {
  runtimeStatus.textContent = message;
  runtimeStatus.dataset.state = ok ? "ok" : "error";
  runtimeChip.textContent = ok ? "已连接" : "未连接";
  runtimeChip.dataset.state = ok ? "ok" : "error";
}

function renderState(state) {
  currentState = state;
  const cpu = state.system?.cpu;
  const gpu = state.system?.gpu;
  const gpuMemPct = gpu?.mem_total_mb > 0 ? Math.round((gpu.mem_used_mb / gpu.mem_total_mb) * 100) : null;
  const trayMode = currentConfig?.general?.tray_display ?? "default";
  const trayValue = trayDisplayValue(trayMode, cpu, gpu, gpuMemPct);

  trayChip.textContent = state.shell?.tray_supports_menu ? "已启用" : "受限";
  trayChip.dataset.state = state.shell?.tray_supports_menu ? "ok" : "warn";
  gpuMemChip.textContent = gpuMemPct == null ? "未知" : `${gpuMemPct}%`;
  gpuMemChip.dataset.state = gpuMemPct != null && gpuMemPct >= 80 ? "warn" : "ok";
  translatorChip.textContent = state.translator?.enabled ? state.translator.status_text ?? "已启用" : "关闭";
  translatorChip.dataset.state = state.translator?.enabled ? "ok" : "idle";

  trayModeLabel.textContent = trayModeLabelText(trayMode);
  trayPreview.textContent = trayValue ?? "--";
  trayPreview.dataset.mode = trayMode;
  cpuMetric.textContent = cpu ? `${Math.round(cpu.usage_pct)}%${cpu.temp_c == null ? "" : ` / ${Math.round(cpu.temp_c)}°C`}` : "未知";
  gpuMetric.textContent = gpu
    ? `${Math.round(gpu.usage_pct)}% / ${Math.round(gpu.temp_c)}°C / ${formatGpuMem(gpu)}`
    : "未知";
  proxyMetric.textContent = `Git ${state.proxy?.git_proxy_enabled ? "开" : "关"} / 终端 ${state.proxy?.terminal_proxy_enabled ? "开" : "关"}`;
  subconverterMetric.textContent = state.subconverter?.running ? `运行中 :${state.subconverter.port}` : "停止";
  gitProxyAction.textContent = state.proxy?.git_proxy_enabled ? "关闭 Git 代理" : "开启 Git 代理";
  terminalProxyAction.textContent = state.proxy?.terminal_proxy_enabled ? "关闭终端代理" : "开启终端代理";
  proxyPageStatus.textContent = state.proxy?.git_proxy_enabled || state.proxy?.terminal_proxy_enabled ? "部分开启" : "全部关闭";
  proxyAddressView.textContent = currentConfig?.proxy?.address ?? "--";
  gitProxyView.textContent = state.proxy?.git_proxy_status_display ?? (state.proxy?.git_proxy_enabled ? "已开启" : "未开启");
  terminalProxyView.textContent = state.proxy?.terminal_proxy_status_display ?? (state.proxy?.terminal_proxy_enabled ? "已开启" : "未开启");
  subconverterPageStatus.textContent = state.subconverter?.running ? "运行中" : "停止";
  subconverterEnabledView.textContent = state.subconverter?.enabled ? "已启用" : "已关闭";
  subconverterPortView.textContent = state.subconverter?.port ? `:${state.subconverter.port}` : "--";
  subconverterRunningView.textContent = state.subconverter?.running ? "由当前 sidecar 启动" : "未运行";
  const subconverterUrl = `http://127.0.0.1:${state.subconverter?.port ?? 7777}`;
  subconverterUrlView.textContent = subconverterUrl;
  subconverterLocalUrl.textContent = subconverterUrl;
  subconverterHealthView.textContent = state.subconverter?.running ? "健康" : "不可用";
  const translatorEnabled = Boolean(state.translator?.enabled);
  const translatorPaused = Boolean(state.translator?.paused);
  translatorPauseAction.disabled = !translatorEnabled;
  translatorPauseAction.dataset.monitorState = !translatorEnabled ? "disabled" : translatorPaused ? "paused" : "running";
  translatorPauseAction.setAttribute("aria-pressed", translatorEnabled && !translatorPaused ? "true" : "false");
  translatorPauseAction.querySelector(".toggle-label").textContent = !translatorEnabled
    ? "监控未启用"
    : translatorPaused
      ? "监控已暂停"
      : "监控开启";
  translatorMonitorView.textContent = !translatorEnabled ? "关闭" : translatorPaused ? "已暂停" : "监控中";
  translatorBackendView.textContent = state.translator?.backend_label ?? "--";
  translatorModelView.textContent = state.translator?.model_label ?? "--";
  stateUpdated.textContent = `刷新 ${new Date().toLocaleTimeString()}`;
}

function renderConfig(config) {
  currentConfig = config;
  if (!configJsonDirty && document.activeElement !== configView) {
    configView.value = JSON.stringify(config, null, 2);
  }
  configForm.elements.tray_display.value = config.general?.tray_display ?? "default";
  configForm.elements.notifications_enabled.checked = Boolean(config.general?.notifications_enabled);
  configForm.elements.clipboard_history_enabled.checked = Boolean(config.general?.clipboard_history_enabled);
  configForm.elements.autostart_enabled.checked = Boolean(config.general?.autostart_enabled);
  configForm.elements.hotkey_clipboard_history.value = config.general?.hotkey_clipboard_history ?? "<alt>+v";
  configForm.elements.screenshot_save_dir.value = config.screenshot?.save_dir ?? "";
  configForm.elements.screenshot_hotkey.value = config.screenshot?.hotkey ?? "";
  configForm.elements.screenshot_hotkey_pin.value = config.screenshot?.hotkey_pin ?? "";
  configForm.elements.screenshot_hotkey_pure_ocr.value = config.screenshot?.hotkey_pure_ocr ?? "";
  configForm.elements.screenshot_hotkey_interactive.value = config.screenshot?.hotkey_interactive ?? "";
  configForm.elements.screenshot_hotkey_pin_clipboard.value = config.screenshot?.hotkey_pin_clipboard ?? "";
  configForm.elements.screenshot_copy_to_clipboard.checked = Boolean(config.screenshot?.copy_to_clipboard);
  configForm.elements.screenshot_save_to_disk.checked = Boolean(config.screenshot?.save_to_disk);
  configForm.elements.screenshot_notifications_enabled.checked = Boolean(config.screenshot?.notifications_enabled);
  configForm.elements.proxy_address.value = config.proxy?.address ?? "";
  configForm.elements.translator_enabled.checked = Boolean(config.translator?.enabled);
  configForm.elements.translator_clipboard_enabled.checked = Boolean(config.translator?.clipboard_enabled);
  configForm.elements.translator_popup_enabled.checked = Boolean(config.translator?.popup_enabled);
  configForm.elements.translator_auto_copy.checked = Boolean(config.translator?.auto_copy);
  configForm.elements.ollama_host.value = config.translator?.ollama_host ?? "http://127.0.0.1:11434";
  configForm.elements.translator_model.value = config.translator?.model ?? "";
  configForm.elements.source_language.value = config.translator?.source_language ?? "auto";
  configForm.elements.target_language.value = config.translator?.target_language ?? "简体中文";
  configForm.elements.hotkey_toggle_pause.value = config.translator?.hotkey_toggle_pause ?? "<ctrl>+<alt>+t";
  configForm.elements.poll_interval_ms.value = config.translator?.poll_interval_ms ?? 350;
  configForm.elements.debounce_ms.value = config.translator?.debounce_ms ?? 220;
  configForm.elements.min_chars.value = config.translator?.min_chars ?? 2;
  configForm.elements.max_chars.value = config.translator?.max_chars ?? 1600;
  configForm.elements.request_timeout_s.value = config.translator?.request_timeout_s ?? 25;
  configForm.elements.max_output_tokens.value = config.translator?.max_output_tokens ?? 1024;
  configForm.elements.popup_width_px.value = config.translator?.popup_width_px ?? 360;
  configForm.elements.keep_alive.value = config.translator?.keep_alive ?? "15m";
  configForm.elements.prompt_extra.value = config.translator?.prompt_extra ?? "";
  configForm.elements.subconverter_enable_server.checked = Boolean(config.subconverter?.enable_server);
  configForm.elements.subconverter_port.value = config.subconverter?.port ?? 7777;
  captureSaveMode.textContent = [
    config.screenshot?.copy_to_clipboard ? "复制" : null,
    config.screenshot?.save_to_disk ? "保存" : null,
  ].filter(Boolean).join(" + ") || "仅动作";
  captureSaveDirView.textContent = config.screenshot?.save_dir ?? "--";
  captureHotkeyView.textContent = config.screenshot?.hotkey ?? "--";
  captureHotkeyPinView.textContent = config.screenshot?.hotkey_pin ?? "--";
  captureHotkeyInteractiveView.textContent = config.screenshot?.hotkey_interactive ?? "--";
  captureHotkeyOcrView.textContent = config.screenshot?.hotkey_pure_ocr ?? "--";
  captureHotkeyClipboardView.textContent = config.screenshot?.hotkey_pin_clipboard ?? "--";
  captureCopyView.textContent = config.screenshot?.copy_to_clipboard ? "开启" : "关闭";
  captureDiskView.textContent = config.screenshot?.save_to_disk ? "开启" : "关闭";
  translatorHostView.textContent = config.translator?.ollama_host ?? "--";
  translatorLanguageView.textContent = `${config.translator?.source_language ?? "auto"} -> ${config.translator?.target_language ?? "简体中文"}`;
  translatorClipboardView.textContent = config.translator?.clipboard_enabled ? "开启" : "关闭";
  translatorAutoCopyView.textContent = config.translator?.auto_copy ? "开启" : "关闭";
}

function trayModeLabelText(mode) {
  return {
    default: "默认图标",
    cpu_usage: "CPU 使用率",
    cpu_temp: "CPU 温度",
    gpu_usage: "GPU 使用率",
    gpu_temp: "GPU 温度",
    gpu_mem: "GPU 显存占用",
  }[mode] ?? mode;
}

function trayDisplayValue(mode, cpu, gpu, gpuMemPct) {
  if (mode === "cpu_usage") return cpu ? String(Math.round(cpu.usage_pct)).padStart(2, "0") : null;
  if (mode === "cpu_temp") return cpu?.temp_c == null ? null : String(Math.round(cpu.temp_c)).padStart(2, "0");
  if (mode === "gpu_usage") return gpu ? String(Math.round(gpu.usage_pct)).padStart(2, "0") : null;
  if (mode === "gpu_temp") return gpu?.temp_c == null ? null : String(Math.round(gpu.temp_c)).padStart(2, "0");
  if (mode === "gpu_mem") return gpuMemPct == null ? null : String(gpuMemPct).padStart(2, "0");
  return "DV";
}

function formatGpuMem(gpu) {
  if (!gpu?.mem_total_mb) return "显存未知";
  const used = gpu.mem_used_mb / 1024;
  const total = gpu.mem_total_mb / 1024;
  const pct = Math.round((gpu.mem_used_mb / gpu.mem_total_mb) * 100);
  return `显存 ${pct}% (${used.toFixed(1)}/${total.toFixed(0)}G)`;
}

function renderEvents() {
  if (proxyEventList) {
    proxyEventList.replaceChildren(
      ...renderEventItems(events.filter((event) => event.topic.includes("proxy") || event.message.includes("proxy")).slice(-30)),
    );
  }
}

function renderEventItems(sourceEvents) {
  return sourceEvents.reverse().map((event) => {
      const item = document.createElement("li");
      const time = new Date(event.timestamp).toLocaleTimeString();
      item.innerHTML = `<span>${time}</span><strong>${event.topic}</strong><p>${event.message}</p>`;
      return item;
    });
}

function renderClipboardHistory(items) {
  clipboardItems = items;
  const normalizedQuery = clipboardQuery.trim().toLowerCase();
  const visibleItems = normalizedQuery
    ? items.filter((item) => String(item.text ?? item.preview ?? "").toLowerCase().includes(normalizedQuery))
    : items;
  clipboardCount.textContent = `${visibleItems.length}/${items.length}`;
  clipboardList.replaceChildren(
    ...visibleItems.map((item) => {
      const row = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "置顶";
      button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          await request("/clipboard/select", {
            method: "POST",
            body: JSON.stringify({ index: item.index }),
          });
          await refresh();
        } catch (error) {
          setRuntimeStatus(false, error.message);
        } finally {
          button.disabled = false;
        }
      });
      const text = document.createElement("span");
      text.textContent = item.preview || item.text || "";
      text.addEventListener("click", () => selectClipboardPreview(item));
      row.replaceChildren(button, text);
      return row;
    }),
  );
  if (visibleItems.length > 0 && clipboardSelectedPreview.textContent === "") {
    selectClipboardPreview(visibleItems[0]);
  }
}

function selectClipboardPreview(item) {
  clipboardSelectedIndex.textContent = `#${item.index}`;
  clipboardSelectedPreview.textContent = item.text || item.preview || "";
}

async function refresh() {
  let health;
  let state;
  let config;
  let eventPayload;
  let clipboardPayload;
  try {
    [health, state, config, eventPayload, clipboardPayload] = await Promise.all([
      request("/health"),
      request("/state"),
      request("/config"),
      request(`/events?after_id=${lastEventId}&limit=50`),
      request("/clipboard/history"),
    ]);
  } catch (error) {
    setRuntimeStatus(false, "未连接");
    stateUpdated.textContent = error.message;
    return;
  }
  setRuntimeStatus(true, health.status === "ok" ? "已连接" : "状态未知");
  renderConfig(config);
  renderState(state);
  for (const event of eventPayload.events ?? []) {
    events.push(event);
    lastEventId = Math.max(lastEventId, event.id);
  }
  renderEvents();
  renderClipboardHistory(clipboardPayload.items ?? []);
}

async function dispatchAction(action) {
  actionStatus.textContent = `执行中: ${action}`;
  await request(`/actions/${encodeURIComponent(action)}`, {
    method: "POST",
    body: JSON.stringify({}),
  });
  actionStatus.textContent = `已执行: ${action}`;
  await refresh();
}

async function saveConfig() {
  const patch = {
    general: {
      tray_display: configForm.elements.tray_display.value,
      notifications_enabled: configForm.elements.notifications_enabled.checked,
      clipboard_history_enabled: configForm.elements.clipboard_history_enabled.checked,
      autostart_enabled: configForm.elements.autostart_enabled.checked,
      hotkey_clipboard_history: configForm.elements.hotkey_clipboard_history.value,
    },
    screenshot: {
      save_dir: configForm.elements.screenshot_save_dir.value,
      hotkey: configForm.elements.screenshot_hotkey.value,
      hotkey_pin: configForm.elements.screenshot_hotkey_pin.value,
      hotkey_pure_ocr: configForm.elements.screenshot_hotkey_pure_ocr.value,
      hotkey_interactive: configForm.elements.screenshot_hotkey_interactive.value,
      hotkey_pin_clipboard: configForm.elements.screenshot_hotkey_pin_clipboard.value,
      copy_to_clipboard: configForm.elements.screenshot_copy_to_clipboard.checked,
      save_to_disk: configForm.elements.screenshot_save_to_disk.checked,
      notifications_enabled: configForm.elements.screenshot_notifications_enabled.checked,
    },
    proxy: {
      address: configForm.elements.proxy_address.value,
    },
    translator: {
      enabled: configForm.elements.translator_enabled.checked,
      clipboard_enabled: configForm.elements.translator_clipboard_enabled.checked,
      popup_enabled: configForm.elements.translator_popup_enabled.checked,
      auto_copy: configForm.elements.translator_auto_copy.checked,
      ollama_host: configForm.elements.ollama_host.value,
      model: configForm.elements.translator_model.value,
      source_language: configForm.elements.source_language.value,
      target_language: configForm.elements.target_language.value,
      hotkey_toggle_pause: configForm.elements.hotkey_toggle_pause.value,
      poll_interval_ms: Number(configForm.elements.poll_interval_ms.value),
      debounce_ms: Number(configForm.elements.debounce_ms.value),
      min_chars: Number(configForm.elements.min_chars.value),
      max_chars: Number(configForm.elements.max_chars.value),
      request_timeout_s: Number(configForm.elements.request_timeout_s.value),
      max_output_tokens: Number(configForm.elements.max_output_tokens.value),
      popup_width_px: Number(configForm.elements.popup_width_px.value),
      keep_alive: configForm.elements.keep_alive.value,
      prompt_extra: configForm.elements.prompt_extra.value,
    },
    subconverter: {
      enable_server: configForm.elements.subconverter_enable_server.checked,
      port: Number(configForm.elements.subconverter_port.value),
    },
  };
  configSaveStatus.textContent = "保存中";
  const updated = await request("/config", {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
  configJsonDirty = false;
  renderConfig(updated);
  configSaveStatus.textContent = "已保存";
  await refresh();
}

async function saveConfigJson() {
  let patch;
  try {
    patch = JSON.parse(configView.value);
  } catch (error) {
    throw new Error(`配置 JSON 无效: ${error.message}`);
  }
  if (!patch || typeof patch !== "object" || Array.isArray(patch)) {
    throw new Error("配置 JSON 必须是对象");
  }
  configSaveStatus.textContent = "保存全部中";
  const updated = await request("/config", {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
  configJsonDirty = false;
  renderConfig(updated);
  configSaveStatus.textContent = "全部已保存";
  await refresh();
}

async function translateText() {
  const text = translatorForm.elements.source_text.value;
  translatorStatus.textContent = "翻译中";
  const result = await request("/translator/translate", {
    method: "POST",
    body: JSON.stringify({ text }),
  });
  translatorResult.textContent = result.text ?? "";
  translatorStatus.textContent = `${result.model ?? "model"} | ${result.elapsed_ms ?? 0} ms`;
  await refresh();
}

document.querySelectorAll("[data-action]").forEach((button) => {
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await dispatchAction(button.dataset.action);
    } catch (error) {
      actionStatus.textContent = `失败: ${button.dataset.action}`;
      setRuntimeStatus(false, error.message);
    } finally {
      button.disabled = false;
    }
  });
});

document.querySelectorAll(".nav a").forEach((link) => {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    document.querySelectorAll(".nav a").forEach((item) => item.classList.remove("active"));
    link.classList.add("active");
    showPage(link.dataset.pageTarget);
  });
});

clipboardSearch.addEventListener("input", () => {
  clipboardQuery = clipboardSearch.value;
  clipboardSelectedPreview.textContent = "";
  renderClipboardHistory(clipboardItems);
});

function showPage(page) {
  document.querySelectorAll("[data-page]").forEach((section) => {
    section.classList.toggle("active", section.dataset.page === page);
  });
}

configForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = configForm.querySelector("button[type='submit']");
  submit.disabled = true;
  try {
    await saveConfig();
  } catch (error) {
    configSaveStatus.textContent = error.message;
    setRuntimeStatus(false, error.message);
  } finally {
    submit.disabled = false;
  }
});

configView.addEventListener("input", () => {
  configJsonDirty = true;
  configSaveStatus.textContent = "JSON 已修改";
});

configJsonSave.addEventListener("click", async () => {
  configJsonSave.disabled = true;
  try {
    await saveConfigJson();
  } catch (error) {
    configSaveStatus.textContent = error.message;
    setRuntimeStatus(false, error.message);
  } finally {
    configJsonSave.disabled = false;
  }
});

translatorForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = translatorForm.querySelector("button[type='submit']");
  submit.disabled = true;
  try {
    await translateText();
  } catch (error) {
    translatorStatus.textContent = error.message;
    setRuntimeStatus(false, error.message);
  } finally {
    submit.disabled = false;
  }
});

refresh();
setInterval(refresh, 2500);
