# DeskVane 架构设计草案

## 目标

这份文档不是“当前代码说明书”，而是 DeskVane 接下来 1 到 3 个大版本应该收敛到的目标架构。

核心目标只有四个：

- 可扩展：新增功能时，不需要继续把逻辑堆进 `app.py` 和托盘控制器。
- 可维护：平台适配、UI、业务逻辑、后台任务边界清楚。
- 可测试：核心逻辑尽量脱离 Tk、系统命令和真实平台环境。
- 可发布：Linux、Windows、macOS 共用一套主干架构，只替换平台实现。

## 我对当前项目的理解

当前项目已经具备完整的桌面工具能力，主要模块有：

- 截图 / 钉图 / OCR
- 翻译（Ollama）
- 剪贴板历史
- Git / 终端代理
- Mihomo / PAC
- 订阅转换
- 托盘、设置面板、帮助页
- 平台服务层（通知、截图、剪贴板、打开路径、热键、托盘适配、自启动、代理会话）

当前代码最大的优点是“功能已经能跑”，最大的风险是“主干正在变成巨型协调器”。

现在的典型结构是：

- `DeskVaneApp` 负责组装几乎所有模块
- 各功能模块直接拿 `app` 对象回调彼此
- UI 与业务逻辑仍有较多交叉
- 后台线程、轮询、Tk `after` 调度分散在多个模块中
- 配置虽然已经 dataclass 化，但仍是单一大对象集中管理

这套结构对现阶段够用，但继续加功能会出现几个问题：

- 新功能只能继续往 `app.py` 塞入口
- 菜单、快捷键、设置项会越来越难统一管理
- 后台任务和子进程生命周期难以收敛
- 模块之间会越来越依赖 `self.app.xxx`

所以后续不应该继续“补几个类”，而应该把主干结构收紧。

## 总体设计原则

### 1. 组合根唯一

应用启动时只能有一个组合根负责装配依赖：

- `__main__.py`
- `bootstrap.py`
- `AppKernel` / `Application`

除了这里，其他模块不再主动 new 其他大模块。

### 2. 功能模块化，而不是按技术堆文件

DeskVane 更适合按“能力”拆，而不是继续按“零散工具文件”堆在根目录：

- 截图是一个 feature
- 翻译是一个 feature
- Mihomo 是一个 feature
- 托盘/设置/帮助属于 shell feature

### 3. 平台层只解决平台差异，不承载业务决策

平台层负责：

- 系统通知
- 热键注册
- 截图能力
- 剪贴板
- 打开文件 / URI
- 自启动
- 终端代理挂钩

平台层不应该决定：

- 菜单怎么组织
- 什么情况下弹通知
- OCR 完成后怎么展示
- Mihomo 面板里显示哪些操作

### 4. UI 只负责展示和收集输入

Tk 窗口、托盘、弹窗、设置面板应该尽量只做：

- 渲染状态
- 收集用户输入
- 调用 use case / controller

不要让 UI 直接管理复杂状态机和系统调用。

### 5. 后台任务统一治理

未来所有这类能力都应该进入统一模型：

- 轮询任务
- Worker 线程
- 子进程
- 本地 HTTP 服务
- 定时刷新

不能再由每个模块自行维护一套“线程 + after + stop flag”。

## 目标架构总览

推荐的目标结构：

```text
deskvane/
  __main__.py
  bootstrap.py

  app/
    kernel.py
    context.py
    lifecycle.py
    registry.py
    state.py

  core/
    config/
      models.py
      loader.py
      manager.py
      migrate.py
      validate.py
    events.py
    tasks.py
    supervisor.py
    results.py
    errors.py

  platform/
    base.py
    factory.py
    linux/
    windows/
    macos/

  features/
    shell/
      module.py
      tray/
      settings/
      help/
    capture/
      module.py
      service.py
      controller.py
      state.py
      ui/
    translator/
      module.py
      service.py
      worker.py
      state.py
      ui/
    clipboard_history/
      module.py
      service.py
      state.py
      ui/
    proxy/
      module.py
      git_proxy.py
      terminal_proxy.py
      state.py
    mihomo/
      module.py
      service.py
      runtime.py
      api.py
      state.py
      ui/
    subconverter/
      module.py
      service.py
      server.py

  ui/
    shared/
      theme.py
      widgets.py
      dialogs.py

  infra/
    storage/
    network/
    subprocess/
```

说明：

- `app/`：应用装配与生命周期
- `core/`：跨 feature 的通用基础设施
- `platform/`：平台能力抽象与实现
- `features/`：真正的业务能力
- `ui/shared/`：跨 feature 复用的 UI 基础组件
- `infra/`：底层基础设施封装

## 推荐的核心对象

### AppKernel

`AppKernel` 应该替代当前“巨型 `DeskVaneApp` 协调器”的角色，但它不直接承载所有业务方法。

它只负责：

- 持有 `PlatformServices`
- 持有 `ConfigManager`
- 持有 `EventBus`
- 持有 `TaskManager`
- 注册并启动 `FeatureModule`
- 管理应用整体生命周期

它不负责：

- 直接实现截图
- 直接管理翻译状态
- 直接构建托盘菜单
- 直接处理 Mihomo 细节

### ModuleContext

每个功能模块初始化时拿到统一上下文：

```python
class ModuleContext:
    platform: PlatformServices
    config: ConfigManager
    events: EventBus
    tasks: TaskManager
    ui_dispatcher: UiDispatcher
    state: AppStateStore
    opener: OpenerService
    notifier: NotificationService
    logger: Logger
```

这样 feature 不再需要互相拿 `app.xxx`。

### FeatureModule

每个 feature 都应该有统一入口，而不是靠 `app.py` 一行一行装配。

建议接口：

```python
class FeatureModule(Protocol):
    name: str

    def register(self, context: ModuleContext) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
```

如果后续继续增强，可以再增加：

- `contribute_hotkeys()`
- `contribute_tray_menu()`
- `contribute_settings_schema()`
- `contribute_help()`

## 推荐的基础设施设计

### 1. ConfigManager

当前 `config.py` 已经是正确方向，但最终应拆成一个完整配置子系统。

推荐职责：

- 加载 YAML
- 迁移旧配置
- 校验与补默认值
- 原子写入
- 按 section 读取
- 发布配置变更事件

建议结构：

- `core/config/models.py`
- `core/config/loader.py`
- `core/config/migrate.py`
- `core/config/validate.py`
- `core/config/manager.py`

需要新增的能力：

- `config_version`
- 原子写入（临时文件 + rename）
- `update_section("translator", patch)`
- `subscribe(section, callback)`

目标是：设置面板、托盘动作、后台模块都不再直接 `_save_config()`。

### 2. EventBus

当前模块之间大量通过：

- `self.app.xxx`
- 直接回调
- UI dispatcher 包装函数

后续建议加入轻量事件总线，用于解耦以下场景：

- 配置已更新
- Mihomo 状态已变化
- 翻译任务完成
- 剪贴板历史已更新
- 订阅已刷新
- 托盘需要重建

注意：这里只要“轻量同步事件总线”，不需要搞成复杂消息系统。

### 3. TaskManager / Supervisor

这是未来最重要的基础设施之一。

当前项目里存在多种后台执行模型：

- Tk `after` 轮询
- 普通线程
- worker 线程
- 子进程
- HTTP server

建议统一抽象成三类：

- `PollingTask`
  - 用于剪贴板轮询、状态刷新
- `BackgroundWorker`
  - 用于翻译/OCR 这类阻塞任务
- `ManagedProcess`
  - 用于 mihomo core、subconverter server

这样就能统一解决：

- 启动顺序
- 停止顺序
- 异常上报
- 状态监控
- 测试替换

## 推荐的 feature 设计

### Shell Feature

这个 feature 统一负责应用壳层能力：

- 托盘
- 设置面板
- 帮助页
- 全局动作入口

这是整个应用的 UI 外壳，不承载具体业务逻辑。

它的职责应该是：

- 从各 feature 收集菜单贡献
- 从各 feature 收集设置页 schema
- 渲染托盘和设置 UI
- 将用户操作转发给对应 use case

不应该由 shell feature 决定业务规则。

### Capture Feature

把这几块统一收进一个 feature：

- `capture.py`
- `screenshot.py`
- `screenshot_service.py`
- `screenshot_controller.py`
- `overlay.py`
- `pin.py`

推荐职责分层：

- `service.py`
  - 截图保存、剪贴板图片写入、OCR payload 构造
- `controller.py`
  - 处理一次截图流程
- `ui/overlay.py`
  - 区域选择 UI
- `ui/pin.py`
  - 钉图 UI
- `module.py`
  - 注册 hotkey、菜单和动作

### Translator Feature

建议拆成四层：

- `service.py`
  - 翻译用例、OCR 用例
- `worker.py`
  - 后台执行
- `state.py`
  - 当前状态、最后结果、错误摘要
- `ui/`
  - 翻译浮窗、OCR 结果窗口

关键点：

- OCR 只是 translator feature 的一种 use case，不应该让截图模块知道太多翻译细节
- 剪贴板轮询逻辑应该由标准 `PollingTask` 托管
- 翻译状态应通过状态对象暴露给托盘/设置，而不是让别的模块直接读引擎内部字段

### Clipboard History Feature

当前实现已经比较独立，后续重点是进一步标准化：

- 持久化通过 storage adapter 统一处理
- 轮询交给 `TaskManager`
- UI overlay 独立成 `ui/history_overlay.py`
- 对外只暴露：
  - `show_overlay()`
  - `push(text)`
  - `latest_items()`

### Proxy Feature

这一块未来会明显复杂化，所以应该尽早独立。

建议拆成两个子域：

- `git_proxy`
- `terminal_proxy`

同时再加一层统一 facade：

- `ProxyFeatureService`

这样 shell、设置、托盘只需要知道：

- 当前代理地址
- Git 代理开关状态
- 终端代理支持状态 / 开关状态

而不需要知道 `.bashrc`、`.zshrc`、环境变量细节。

### Mihomo Feature

这是当前最复杂的 feature，建议单独当成一个小应用域来设计。

推荐拆成：

- `service.py`
  - 对上层暴露统一用例
- `runtime.py`
  - 管理 party/core 选择、启动、停止、重载
- `api.py`
  - 控制 API 访问
- `pac.py`
  - PAC 生成逻辑
- `state.py`
  - 运行状态、模式、代理组、端口、错误
- `ui/panel.py`
  - GUI 面板

重要原则：

- Mihomo UI 不直接驱动进程和 API，统一通过 service/use case
- `party` 和 `core` 只是 runtime backend
- Linux-only 行为必须显式包在 backend 内部，不能散在业务层

### Subconverter Feature

建议最终结构：

- `service.py`
  - 订阅解析与转换
- `server.py`
  - 本地服务
- `ui/dialog.py`
  - GUI
- `module.py`
  - 动作注册

这块本身已经接近 feature 结构了，主要是继续与 shell 解耦。

## 托盘、快捷键、设置项的可扩展设计

这是 DeskVane 后续扩展性的关键。

### 1. 托盘菜单改为声明式贡献

不要再让托盘控制器知道所有业务细节。

建议每个 feature 暴露：

- 菜单项
- 当前可用性
- 当前选中状态
- 对应 action id

Shell feature 只负责汇总和渲染。

### 2. 快捷键改为注册表模式

不要由 `app.py` 手写每条热键注册。

建议每个 feature 暴露：

- `HotkeySpec(id, default, description, action)`

Shell 或 hotkey registry 统一负责：

- 读取配置
- 注册平台热键
- 配置变更后重绑

### 3. 设置面板改为 schema 驱动

当前 `settings_panel.py` 已经很大，后续不应该继续膨胀。

建议每个 feature 贡献：

- section 元数据
- 字段 schema
- 说明文字
- 校验规则
- 提交回调

设置面板变成一个通用 renderer，而不是把所有字段写死。

## 平台层建议

当前平台层已经成型，但建议继续稳住边界。

### 平台层保留的职责

- 通知
- 剪贴板
- 截图
- 打开器
- 热键后端
- 托盘适配
- 自启动
- 终端代理挂钩

### 平台层不要继续承担的职责

- 配置迁移
- 菜单业务拼装
- 帮助文案
- 翻译逻辑
- Mihomo 控制流程
- 订阅转换流程

### 建议增加 capability 模型

除了 `PlatformInfo`，建议后续增加更细粒度 capability：

- `supports_tray_menu`
- `supports_selection_clipboard`
- `supports_image_clipboard`
- `supports_terminal_proxy`
- `supports_mihomo_party`
- `supports_hotkey_grab`

这样 feature 可以按 capability 决定功能显示和降级，而不是继续写平台判断。

## UI 设计建议

当前已经开始把 UI 模块挪进 `ui/`，方向是对的。

后续建议分成两层：

- `ui/shared/`
  - 主题、通用按钮、通用弹窗、基础组件
- `features/*/ui/`
  - 具体 feature 的界面

不要把所有窗口都塞回全局 `ui/`，否则只是把根目录混乱搬到另一个目录。

## 状态管理建议

DeskVane 不需要引入复杂状态管理框架，但需要一个统一状态出口。

推荐方式：

- 每个 feature 有自己的 state dataclass
- `AppStateStore` 持有所有 feature state
- shell/tray/settings 只读 state，不直接读 feature 私有字段

例如：

```python
@dataclass
class TranslatorState:
    enabled: bool
    paused: bool
    status_text: str
    model_label: str
    last_translation_preview: str
```

这样托盘和设置不需要知道 `TranslatorEngine` 内部结构。

## 推荐的迁移映射

### 当前文件到目标位置

- `app.py`
  - 拆到 `app/kernel.py` + feature module 装配
- `config.py`
  - 拆到 `core/config/`
- `notifier.py`
  - 最终收敛为平台通知 facade，可保留薄兼容层
- `hotkeys.py`
  - 变成 shell 层 hotkey registry
- `capture.py` / `screenshot.py` / `screenshot_service.py` / `screenshot_controller.py`
  - 收敛到 `features/capture/`
- `clipboard_history.py`
  - 收敛到 `features/clipboard_history/`
- `git_proxy.py` / `terminal_proxy.py`
  - 收敛到 `features/proxy/`
- `translator/*`
  - 收敛到 `features/translator/`
- `mihomo/*`
  - 收敛到 `features/mihomo/`
- `subconverter/*`
  - 保持 feature 化，继续补 `module.py`
- `ui/tray.py` / `ui/settings_panel.py` / `ui/help_doc.py`
  - 收敛到 `features/shell/`

## 我建议的演进顺序

### 第一阶段

先稳住主干，不大拆：

- 引入 `AppKernel`
- 引入 `ModuleContext`
- 引入 `FeatureModule`
- 引入 `ConfigManager`
- 引入 `TaskManager`

目标：停止继续扩大 `DeskVaneApp`。

### 第二阶段

把现有模块映射到 feature：

- `capture`
- `translator`
- `clipboard_history`
- `proxy`
- `mihomo`
- `subconverter`
- `shell`

目标：让每个 feature 有自己的 `module.py` 和 `state.py`。

### 第三阶段

做真正的“声明式外壳”：

- tray contribution
- hotkey contribution
- settings schema contribution

目标：新功能不再需要手工改多个中心文件。

### 第四阶段

再继续做跨平台补齐：

- Windows tray / hotkey / autostart
- macOS tray / hotkey / autostart
- 打包与发布闭环

## 不建议继续做的事情

- 不要再往 `app.py` 加新的业务入口方法
- 不要再让 UI 模块直接调用多个底层服务
- 不要再新增根目录散文件
- 不要再通过 `self.app.xxx` 做跨模块耦合
- 不要让某个 feature 顺手承担别的 feature 的状态展示职责

## 结论

DeskVane 现在最需要的不是“再补一些类”，而是把现有功能收敛成一个稳定的应用骨架。

最合理的目标形态是：

- 一个很薄的启动层
- 一个明确的应用内核
- 一组边界清楚的 feature 模块
- 一套稳定的平台服务层
- 一个声明式的 shell（tray / settings / hotkeys / help）
- 一个统一的配置、状态和后台任务治理模型

如果按这个方向推进，DeskVane 后面继续加：

- 新工具
- 新平台
- 新设置项
- 新托盘动作
- 新后台服务

都不会再把主干结构拖垮。
