# DeskVane 跨平台重构计划

> 注：Mihomo 集成已从 DeskVane 中彻底移除。本文档中提及的 Mihomo 相关阶段和策略仅作为历史设计保留，不再执行。

## 目标

将 DeskVane 从当前的 Linux-first 桌面工具，重构为可稳定支持 Linux、Windows、macOS 的桌面托盘应用，并为后续各平台打包发布建立统一的架构基础。

这份计划的重点不是“先把包打出来”，而是先拆掉当前代码里大量直接绑定 Linux 的实现方式，让平台能力可以替换、降级和演进。

## 当前代码现状总结

当前项目的主体能力已经比较完整，但主干架构仍然明显偏向 Linux：

- 应用启动时直接实例化截图、托盘、热键、通知、终端代理等实现，没有平台服务注入层。
- 通知目前直接依赖 `notify-send`。
- 终端代理通过修改 `~/.bashrc`、`~/.zshrc` 和写入 shell hook 实现。
- 全局热键优先依赖 X11 和 Linux 环境下的 `keyboard`/`python-xlib`。
- 截图与图片剪贴板对 Wayland / X11 命令有大量回退逻辑。
- 托盘实现深度依赖 `pystray + AppIndicator + GTK` 的 Linux 路径。
- Mihomo Party 集成直接写了 Linux `.deb` 安装提示，并使用 `xdotool` 操作窗口。
- 启动 bootstrap 中存在 Debian/Ubuntu `dist-packages` 注入逻辑。

结论很明确：

- 现在不是“稍微补点兼容层”就能变成跨平台。
- 必须先抽平台边界，再逐步实现 Windows/macOS 适配。

## 总体原则

跨平台改造应遵循以下原则：

- 先做架构拆分，再做平台打包。
- 先定义功能分层，再谈平台功能对齐。
- 共享逻辑与平台实现必须分离。
- 不追求第一阶段就全平台功能完全一致。
- 允许某些能力在 Windows/macOS 上先降级或隐藏。

## 功能分层建议

### 核心功能

这些功能应优先实现跨平台支持：

- 系统托盘
- 设置面板
- 截图
- 钉图
- 剪贴板历史
- 翻译模块（作为可选功能）
- Git 代理切换

### 可选功能

这些功能可以在不同平台逐步完善：

- OCR
- 托盘系统状态显示（CPU/GPU）
- 图片剪贴板增强能力

### Linux-only（第一阶段保留）

这些功能建议在第一阶段保持 Linux-only：

- 终端代理环境继承
- Mihomo Party 集成
- 基于 Linux 环境的 PAC/TUN 深度控制
- 使用 `xdotool`、`notify-send`、`xclip`、`wl-copy` 等命令的扩展逻辑

## 分阶段重构计划

## Phase 0：明确支持范围与验收标准

### 目标

先定义“跨平台”到底意味着什么，避免开发过程中边界持续漂移。

### 工作项

- 制定 Linux / Windows / macOS 三平台功能矩阵。
- 明确哪些功能必须全平台一致，哪些允许降级。
- 为每个平台定义 MVP 范围。
- 为每个平台定义发布形式。

### 建议的 MVP 范围

#### Linux

- 保持现有完整能力

#### Windows

- 托盘
- 设置
- 截图
- 钉图
- 剪贴板历史
- 翻译模块
- Git 代理

#### macOS

- 托盘
- 设置
- 截图
- 钉图
- 剪贴板历史
- 翻译模块

### 产出物

- 一份平台功能矩阵文档
- 一份平台支持声明

## Phase 1：引入平台服务层

### 目标

把当前直接写死在业务代码里的平台实现，替换为可注入的服务接口。

### 核心问题

目前 `DeskVaneApp` 在启动时直接构造：

- `ScreenshotTool`
- `TranslatorEngine`
- `ClipboardHistoryManager`
- `HotkeyManager`
- `TrayController`
- `Notifier`
- `TerminalProxyManager`

这会导致：

- 共享逻辑与平台能力无法分离
- Windows/macOS 无法替换实现
- 测试很难隔离平台依赖

### 重构方向

新增 `deskvane/platform/` 目录，并定义平台服务集合。

建议抽象出以下接口：

- `TrayService`
- `NotificationService`
- `HotkeyService`
- `ScreenCaptureService`
- `ClipboardService`
- `AutostartService`
- `ProxySessionService`
- `PlatformInfo`

再新增统一容器：

- `PlatformServices`

### 应用启动结构目标

当前：

- `DeskVaneApp` 直接 new 各种具体实现

目标：

- `bootstrap` 根据平台选择 `PlatformServices`
- `DeskVaneApp` 只依赖平台接口，不依赖 Linux 实现细节

### 产出物

- `deskvane/platform/base.py`
- `deskvane/platform/factory.py`
- `deskvane/platform/linux/...`
- `deskvane/platform/windows/...`
- `deskvane/platform/macos/...`

## Phase 2：把共享业务逻辑从平台实现中拆出来

### 目标

让“功能逻辑”与“平台 API 调用”彻底分离。

### 需要拆分的模块

#### 托盘

当前问题：

- 直接在 `TrayController` 里构建图标、菜单、GTK 特殊处理、AppIndicator 特殊逻辑。

目标：

- 抽出纯数据菜单模型
- 平台层只负责渲染菜单和响应事件

建议新增：

- `tray_model.py`
- `tray_actions.py`
- `platform/.../tray_service.py`

#### 截图

当前问题：

- 截图、图片剪贴板、平台命令回退逻辑混在 `capture.py`

目标：

- 共享层只表达“捕获屏幕”“写入图片剪贴板”
- 平台层决定如何实现

建议新增：

- `services/screenshot_controller.py`
- `platform/.../capture_service.py`

#### 通知

当前问题：

- 只支持 `notify-send`

目标：

- 通知调用统一走 `NotificationService`

#### 热键

当前问题：

- 热键虽然有接口名，但平台判断逻辑和 Linux 细节仍写在共享管理器里

目标：

- 共享层只处理热键配置和事件映射
- 平台层负责注册/卸载全局热键

## Phase 3：重构托盘架构

### 目标

把托盘能力做成真正可替换的跨平台模块。

### 当前问题

当前托盘逻辑不仅依赖 `pystray`，还额外耦合了：

- AppIndicator
- GTK 菜单对象
- Linux tray label
- Linux backend 特殊刷新路径

这些都不应存在于共享层。

### 重构方案

定义统一菜单模型，例如：

- `MenuItem`
- `MenuSeparator`
- `MenuGroup`
- `MenuState`

共享层负责：

- 根据应用状态生成菜单结构
- 决定 label / enabled / checked / action id

平台层负责：

- 把菜单结构渲染成对应平台托盘 UI
- 将点击事件回传给共享层 action dispatcher

### 平台实现建议

#### Linux

- 保留 `pystray`
- Linux 下继续支持 AppIndicator 增强

#### Windows

- 先尝试 `pystray`
- 如果稳定性不足，再切原生 Win32 tray 方案

#### macOS

- 初期也可先尝试 `pystray`
- 后续如有必要再切原生 AppKit 菜单

### 产出物

- 纯平台无关的 tray menu builder
- 三个平台各自的 tray renderer

## Phase 4：重构热键系统

### 目标

把热键注册完全平台化。

### 当前问题

现有热键模块存在几个问题：

- Linux/X11 路径写得太深
- `keyboard` 在 Linux 下还涉及 root/权限问题
- Wayland 提示写死在共享逻辑里
- Windows/macOS 没有正式实现

### 目标结构

共享层：

- 统一热键配置语法
- 管理注册表和回调映射

平台层：

- LinuxHotkeyService
- WindowsHotkeyService
- MacOSHotkeyService

### 平台实现建议

#### Linux

- 保留 X11 backend
- Wayland 下允许降级

#### Windows

- 使用 Win32 全局热键

#### macOS

- 使用 Quartz / AppKit event tap

### 特别注意

不要再让共享层去判断：

- 是否在 X11
- 是否是 Wayland
- 是否需要 root

这些都应下沉到平台实现层。

## Phase 5：重构截图与剪贴板能力

### 目标

建立统一的截图与剪贴板能力抽象。

### 当前问题

当前 `capture.py` 中混合了：

- `mss`
- `PIL.ImageGrab`
- `grim`
- `xclip`
- `wl-copy`
- `wl-paste`

这会带来两个问题：

- 行为难以预测
- 共享代码与平台命令耦合严重

### 推荐抽象

定义以下能力接口：

- `capture_fullscreen()`
- `capture_region_background()`
- `read_text_clipboard()`
- `write_text_clipboard()`
- `read_image_clipboard()`
- `write_image_clipboard()`

### 平台策略

#### Linux

- 保留现有多后端兼容策略

#### Windows

- 优先使用原生 API 或跨平台库

#### macOS

- 优先使用原生 API 或稳定绑定

### UI 部分

`SelectionOverlay`、`PinnedImage`、OCR 结果弹窗等 Tk 交互组件，应单独确认：

- 在 Windows 是否行为一致
- 在 macOS 是否层级、置顶、焦点表现正常

如果有平台差异明显的问题，需要继续抽 UI adapter。

## Phase 6：重构通知与系统集成

### 目标

将系统通知、自启动、平台集成从业务逻辑中剥离。

### 通知

当前：

- Linux only 的 `notify-send`

目标：

- Linux 使用 `notify-send` 或桌面通知后端
- Windows 使用 Toast
- macOS 使用 Notification Center

### 自启动

当前：

- 主要围绕 Linux desktop/autostart

目标：

- Linux：`.desktop` autostart
- Windows：注册表或 Startup 文件夹
- macOS：LaunchAgent

### 错误提示

很多当前报错提示仍然写死 Linux 依赖和 Linux 安装方式，必须统一改成：

- 平台中立文案
- 平台特定补充说明

## Phase 7：拆分代理与 Mihomo 功能边界

### 目标

明确哪些代理相关能力可以跨平台，哪些必须先限制平台。

### Git 代理

`git config --global` 本身是跨平台的，建议保留为全平台支持功能。

### 终端代理

当前终端代理依赖：

- bash
- zsh
- shell source hook
- alias

这不适合直接照搬到 Windows/macOS。

建议：

- 第一阶段将其标记为 Linux-only
- UI 中根据平台动态隐藏或标注“不支持”

### Mihomo

需要拆成两层：

#### 可跨平台部分

- Core 配置写入
- 本地控制 API 调用
- 代理组切换
- 订阅 provider 管理

#### Linux-only 部分

- Mihomo Party 集成
- `.deb` 安装提示
- `xdotool` 窗口操作
- 某些 TUN / PAC 运行态管理

### 结论

Mihomo 不应整个删掉，但必须做成“部分跨平台、部分平台限定”。

## Phase 8：统一打包与发布流程

### 目标

在共享架构稳定后，建立各平台独立打包链路。

### Linux

- 保留 `.deb`

### Windows

- 目标产物：`.exe` 或安装器
- 建议：`PyInstaller` + `Inno Setup`

### macOS

- 目标产物：`.app` / `.dmg`
- 建议：`PyInstaller` 或 `py2app`

### 特别注意

macOS 打包不是简单出 `.app` 就结束，还涉及：

- 签名
- notarization
- 权限申请

因此应放在 Windows 之后推进。

## Phase 9：测试与 CI

### 目标

让跨平台支持具备可验证性，而不是仅靠本机手测。

### 测试策略

#### 单元测试

- 平台接口契约测试
- tray menu model 测试
- 配置与功能状态测试

#### 集成测试

- 应用启动 smoke test
- 托盘初始化 smoke test
- 通知调用 smoke test
- 截图服务 mock test
- 热键注册 smoke test

#### CI

- Linux
- Windows
- macOS

三平台矩阵至少应覆盖：

- 安装依赖
- 启动应用基础测试
- 核心模块导入测试

## 推荐实施顺序

建议按下面顺序推进，而不是同时铺开：

1. 定义平台功能矩阵和 MVP
2. 引入 `platform` 服务层
3. 在 Linux 上先完成“无行为变化”的架构重构
4. 重构托盘、通知、热键、截图、剪贴板
5. 将 Linux-only 功能显式隔离
6. 做 Windows MVP
7. 做 macOS MVP
8. 再补高级功能对齐

## 建议的第一批落地任务

如果正式开始实施，第一批任务建议是：

1. 新建 `deskvane/platform/` 目录与基础接口定义
2. 引入 `PlatformServices` 与平台工厂
3. 将 `Notifier` 改造成 `NotificationService`
4. 将 `TrayController` 拆成“共享菜单模型 + Linux 渲染器”
5. 将 `capture.py` 拆成共享接口和 Linux 实现
6. 将 `HotkeyManager` 改为平台注入式实现
7. 将 `TerminalProxyManager` 标记为 Linux-only 能力
8. 将 Mihomo Party 路径从共享逻辑中剥离

## 风险与注意事项

### 风险 1：过早追求三平台完全一致

这会显著拉长周期，并让架构设计失焦。

建议：

- 先完成统一架构
- 再做逐平台功能补齐

### 风险 2：继续在共享层里写平台判断

例如继续在业务代码里出现：

- `if sys.platform == ...`
- `if wayland ...`
- `if xclip exists ...`

这会把问题重新写回去。

建议：

- 平台判断只出现在平台工厂和平台实现层

### 风险 3：把打包当成跨平台工作的起点

如果不先重构平台边界，打包只会把 Linux 假设原封不动带到其他系统，最终得到“能启动但不好用”的产物。

## 最终建议

DeskVane 的跨平台方向是可行的，但应采用“先架构、后移植、再打包”的路线。

短期最现实的目标不是立刻做出 Windows 和 macOS 完全版，而是：

- 先把平台边界抽出来
- 先做 Windows MVP
- Linux 保持完整能力
- macOS 放在 Windows 之后推进

如果要进入实施阶段，推荐先从 `platform` 服务层和 `tray/hotkey/capture/notify` 四个基础模块开始拆。
