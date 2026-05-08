# DeskVane Tauri 迁移计划

## 目标

长期目标是把 DeskVane 从 `tkinter + pystray` 的单进程桌面工具，迁移为跨平台的本地桌面应用：

```text
Tauri/Rust shell + Web frontend + Python sidecar
```

这条路线的核心不是立刻重写所有功能，而是先把当前 Python 代码收敛成可被外部壳调用的本地运行时，再逐步迁移 UI 和平台能力。

## 为什么选择这条路线

- DeskVane 是常驻系统工具，需要托盘、全局热键、通知、截图、剪贴板、开机启动、代理设置等平台能力。
- 这些能力长期放在 Rust/Tauri shell 里比放在 Tkinter/pystray 里更稳定。
- 设置页、状态页、剪贴板历史、日志和功能面板更适合用 Web frontend 实现。
- 现有 Python 功能已经可用，先作为 sidecar 保留，能避免一次性重写带来的风险。

## 目标架构

```text
frontend/
  React 或 Svelte UI
  settings
  clipboard history
  status dashboard
  logs

src-tauri/
  tray
  windows
  global hotkeys
  notifications
  autostart
  config commands
  sidecar supervisor

deskvane/
  Python runtime API
  feature services
  translator / OCR / subconverter
  legacy compatibility layer
```

## 边界划分

### Tauri/Rust 负责

- 主窗口和设置窗口生命周期
- 系统托盘和托盘菜单
- 全局快捷键注册
- 系统通知
- 开机启动
- 平台权限和平台差异
- 启动、停止、监控 Python sidecar

### Web frontend 负责

- 设置页
- 剪贴板历史页
- 状态面板
- 日志查看
- 功能入口和用户反馈

### Python sidecar 负责

- 当前已实现的业务功能
- 翻译、OCR、订阅转换等 Python 生态更方便维护的能力
- 作为迁移期的兼容运行时

## 分阶段计划

### Phase 1：收敛 Python 运行时 API

目标是让现有 Python 应用先形成稳定的本地 API 面，不再让外部 UI 直接依赖 `DeskVaneApp` 的零散方法。

工作项：

- 新增 `RuntimeApi`，集中暴露状态读取和动作触发。
- 状态统一序列化为 JSON 友好的 dict。
- 动作统一通过 action name 调用。
- 保持 Tkinter UI 和托盘继续可用。

验收标准：

- 测试可以不启动 Tk 主循环就读取 runtime snapshot。
- 测试可以通过 `RuntimeApi.dispatch_action()` 触发已有动作。

### Phase 2：引入本地 sidecar 通信层

目标是给未来 Tauri shell 一个稳定进程边界。

建议先用 stdlib HTTP 或 Unix/TCP loopback，不急于引入重依赖。

候选 API：

```text
GET  /health
GET  /state
GET  /config
PATCH /config
POST /actions/{name}
```

验收标准：

- 外部进程可以读取状态。
- 外部进程可以触发截图、设置、代理切换等动作。
- sidecar 可以被单独启动和停止。

当前实现：

- `RuntimeHttpServer` 使用 Python 标准库 `http.server`，只监听 `127.0.0.1`。
- 默认端口是 `37655`，端口被占用时只记录警告，不阻断主程序启动。
- 已提供 `GET /health`、`GET /state`、`GET /config`、`PATCH /config`、`GET /actions`、`POST /actions/{name}`、`GET /events`。
- `GET /events` 返回内存环形缓冲中的运行时事件，支持 `after_id` 和 `limit` 查询参数。
- `AppKernel` 将该服务注册为 `runtime-api` 长生命周期任务。

### Phase 3：创建 Tauri 壳

目标是先用 Tauri 替换托盘和设置入口，但不迁移业务逻辑。

工作项：

- 新建 `frontend/` 和 `src-tauri/`。
- Tauri 启动 Python sidecar。
- Tauri 托盘菜单调用 sidecar action。
- Web 设置页读取 sidecar config/state。

验收标准：

- Linux 上可以通过 Tauri 托盘打开设置页。
- 原 Python Tk 设置页可以保留为 fallback，但默认不再使用。

当前实现：

- `frontend/` 已提供一个零业务依赖的 runtime dashboard，通过 HTTP 读取 `/health`、`/state`、`/config` 和 `/events`。
- `frontend/` 当前不依赖 Vite/React/Svelte，先用 Node 标准库脚本提供 dev/build，降低早期迁移摩擦。
- `frontend/` 已支持编辑少量通用配置，并通过 `PATCH /config` 保存。
- `src-tauri/` 已提供 Tauri 2 配置和最小 Rust shell，包含主窗口和基础托盘菜单。
- `deskvane runtime-api` 已提供不导入 Tk 的 headless Python sidecar，Tauri 启动时会自动拉起，退出时会回收子进程。
- `src-tauri/` 托盘菜单已能通过 localhost runtime API 触发当前 headless 阶段可用的代理动作。
- 截图、剪贴板弹窗、翻译暂停和旧 Tk 设置入口仍属于 legacy Tk runtime 能力，默认不放入 Tauri/headless 菜单，避免出现可点击但不可用的入口。
- 当前环境已安装 Rust/Cargo/Tauri CLI，并完成 `cargo tauri build --no-bundle` 验证。

### Phase 4：迁移平台能力到 Rust

优先迁移对稳定性影响最大的系统能力：

- 托盘菜单
- 全局快捷键
- 通知
- 开机启动
- 窗口管理
- 配置文件读写

验收标准：

- Python 不再依赖 `pystray` 管理主托盘。
- Python 不再负责全局快捷键注册。
- 三个平台共用同一套 UI 和 action API。

当前实现：

- Tauri shell 已接入 `tauri-plugin-global-shortcut`。
- Tauri 启动后会从 runtime `/config` 读取快捷键配置，将 Python 风格的 `<ctrl>+<shift>+a` 转换为 Tauri/global-hotkey 支持的 `Ctrl+Shift+A`。
- Tauri 会读取 runtime `/actions`，只注册当前 sidecar 明确支持的动作，避免生成“可触发但不可用”的快捷键。
- Tauri 会轮询 runtime `/events`，收到 `config.updated` 后自动清理并重绑快捷键。
- Tauri shell 已接入 `tauri-plugin-autostart`，前端配置里的 `general.autostart_enabled` 会同步到系统开机自启动项。
- 前端配置页已提供“开机自启动”开关，保存后通过 runtime event 驱动 Tauri 同步系统状态。
- Python headless sidecar 会按配置启动订阅转换 server；如果端口被占用，状态会显示未由当前 sidecar 启动。
- Tauri shell 已接入 `tauri-plugin-notification`，runtime 动作失败、后台翻译完成或后台翻译失败时由原生通知提示。
- Tauri 托盘 tooltip 会定期从 runtime state 更新，展示翻译、剪贴板条数、Git 代理和终端代理状态。

### Phase 5：逐步迁移或保留 Python 功能

按收益和风险决定是否迁移：

- 截图、剪贴板、通知等平台能力适合迁 Rust。
- 翻译、OCR、订阅转换可以长期留 Python。
- 代理功能按平台拆分，Git 代理可先跨平台，终端代理保留 Linux-only。

当前实现：

- Python headless sidecar 已提供 `POST /translator/translate`，用于直接提交文本并返回译文、模型和耗时。
- headless 翻译服务复用现有 `OllamaClient`、翻译 prompt、文本校验和结果清理逻辑，不依赖 Tk popup 或 Tk clipboard。
- runtime 状态会暴露 headless 翻译的启用、暂停、运行、最近译文和模型信息。
- headless sidecar 支持 `translator.toggle_pause` 和 `translator.retry_last` 动作；`translator.copy_last` 在迁移期仍转发到 legacy companion。
- 前端 dashboard 已新增文本翻译面板，并暴露启用翻译、Ollama 地址、模型、目标语言等必要配置。
- 前端配置页除常用字段外，已提供完整 JSON 编辑区，可以修改旧设置面板里的高级字段，包括截图热键、翻译 debounce、popup、auto copy、订阅转换端口等。
- 订阅转换服务保留在 Python sidecar 中，按配置启动；截图、剪贴板历史 UI、OCR 弹窗仍等待 Rust/Tauri 平台能力迁移。
- 为了让 Tauri 新入口先具备完整可用功能，headless sidecar 会在需要截图、OCR、剪贴板历史、完整设置、帮助、订阅转换 GUI、复制最近译文等 Tk 依赖动作时，自动拉起 legacy Python runtime companion。
- legacy companion 监听 `127.0.0.1:37656`，由主 sidecar 转发动作；它禁用旧托盘和旧热键，避免和 Tauri 新壳抢系统资源。
- 这是一层迁移期兼容桥。后续可以逐步把这些 Tk 动作替换为 Rust/Tauri 原生实现，每替换一个就从 legacy 转发列表移除一个。
- 剪贴板历史后台已开始脱离 Tk：headless sidecar 会轮询系统剪贴板、持久化历史，并通过 `GET /clipboard/history` 与 `POST /clipboard/select` 供前端展示和置顶回写。
- 剪贴板自动翻译已开始脱离 Tk：headless sidecar 捕获新剪贴板文本后，会按 `translator.enabled`、`clipboard_enabled`、`min_chars`、`max_chars`、`debounce_ms` 等配置异步翻译，并发布 `translator.auto_translated` 或 `translator.error` runtime event。
- 剪贴板历史 overlay、截图选区 overlay、钉图窗口、OCR 结果窗口仍通过 legacy companion 保持功能可用；这些是下一轮原生 UI 迁移的剩余项。

## 当前执行起点

当前先执行 Phase 1：新增 Python `RuntimeApi`，为后续 sidecar 和 Tauri shell 建立稳定边界。
