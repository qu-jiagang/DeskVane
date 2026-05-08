# DeskVane

Linux 系统托盘聚合工具箱。将日常桌面上零散的小工具（截图、翻译、OCR、剪贴板、代理、订阅转换）集中到一个托盘图标里。

## 平台状态

- Linux（Debian / Ubuntu）：当前正式支持的平台，提供 `.deb` 和 `pipx` 安装路径。
- Windows：已纳入跨平台重构和 CI 验证范围，但尚未发布正式安装包。
- macOS：已纳入跨平台重构和 CI 验证范围，但尚未发布正式安装包。

详细边界见：
- [平台功能矩阵](docs/platform-feature-matrix.md)
- [平台支持声明](docs/platform-support-statement.md)

## 功能

- **截图 / 钉图 / OCR**
  - 区域截图，自动保存并复制到剪贴板（默认 `Ctrl+Shift+A`）
  - 钉图：把截图悬浮在屏幕最上层，双击关闭（默认 `F1`）
  - 纯 OCR：框选区域识别为文本（默认 `Alt+F1`）
- **翻译**
  - 通过 Ollama 自动翻译剪贴板内容，鼠标附近弹出译文浮窗
  - 可一键暂停 / 恢复监控（默认 `Ctrl+Alt+T`）
- **剪贴板历史**
  - 记录最近复制过的文本，快捷键唤出历史面板（默认 `Alt+V`）
- **代理**
  - 一键开启 / 关闭全局 git 代理
  - 新开终端自动继承代理环境变量
- **订阅转换**
  - 内建订阅转换器，支持把机场订阅转换成 Clash/Mihomo 兼容的 YAML 配置，可直接复制或导出
- **系统监控**
  - 托盘图标可显示 CPU / GPU 占用
- **图形设置面板**
  - 所有常用配置均可在 GUI 中调整，无需手写 YAML

## 安装

### Linux（正式支持）

主安装方式（Debian / Ubuntu）：

```bash
./scripts/build-deb.sh
sudo apt install ./dist/deskvane_*.deb
```

安装后直接在应用菜单里搜索 `DeskVane`，或者在终端里执行：

```bash
deskvane
```

默认安装不包含 Ollama 这类重功能前置要求；翻译/OCR 现在应作为可选附加功能按需开启。

附加安装方式（`pipx`，适合开发者或不想装 `.deb` 的用户）：

```bash
sudo apt install pipx
pipx install .
```

## 打包

Linux（Debian / Ubuntu）：

```bash
./scripts/build-deb.sh
```

Windows（PyInstaller + 可选 Inno Setup）：

```powershell
python -m pip install -e .[packaging]
powershell -ExecutionPolicy Bypass -File .\scripts\build-win.ps1
```

macOS（PyInstaller + DMG）：

```bash
python3 -m pip install -e .[packaging]
./scripts/build-macos.sh
```

更具体的打包说明见：

- `packaging/README.md`
- `packaging/pyinstaller/README.md`
- `packaging/windows/README.md`
- `packaging/macos/README.md`
- `docs/release-process.md`

### Windows / macOS（开发中）

这两个平台当前还没有正式安装包，也不承诺完整功能对齐。现阶段主要完成了：

- 平台服务层抽象
- Linux-only 能力显式隔离
- GitHub Actions 三平台基础导入和核心单测验证

如果你是在做源码验证或参与开发，可以先使用：

```bash
python -m pip install -e .
python -m pytest -q
```

但对普通终端用户，当前仍建议优先使用 Linux 发行版本。

## 系统依赖

必须：
- Python 3.10+
- `libnotify-bin`（系统通知）

推荐：
- `python3-gi` + Ayatana AppIndicator（完整托盘菜单）
- `xclip` 或 `wl-clipboard`（截图 / 翻译复制到剪贴板）
- Tesseract（OCR 功能，需要对应语言包）

Ubuntu / Debian：
```bash
sudo apt install python3-venv python3-tk python3-gi gir1.2-ayatanaappindicator3-0.1 \
                 libnotify-bin xclip tesseract-ocr tesseract-ocr-chi-sim
```

## 默认快捷键

| 功能 | 默认快捷键 |
| --- | --- |
| 区域截图 | `Ctrl+Shift+A` |
| 钉图截图 | `F1` |
| 纯 OCR | `Alt+F1` |
| 将剪贴板图片钉到屏幕 | `F3` |
| 翻译暂停 / 恢复 | `Ctrl+Alt+T` |
| 剪贴板历史面板 | `Alt+V` |

全部快捷键均可在 `config.yaml` 或设置面板中修改。

## 可选功能：翻译 / OCR（Ollama）

翻译相关功能默认关闭。只有在你明确需要时，才建议安装并启动 Ollama：

```bash
ollama serve
ollama pull qwen2.5:3b
```

然后在 DeskVane 的“设置 -> 翻译”里开启“启用翻译功能”。

## 配置

首次运行会自动生成配置文件 `~/.config/deskvane/config.yaml`，主要配置段：

- `screenshot`：截图 / 钉图 / OCR 的快捷键、保存目录、是否复制到剪贴板
- `translator`：Ollama 地址、模型、源 / 目标语言、浮窗宽度、请求超时等
- `proxy`：git / 终端共享的代理地址
- `general`：通知开关、剪贴板历史开关及其快捷键、托盘显示模式
- `subconverter`：本地订阅转换服务端口

推荐直接打开托盘菜单里的「设置」面板进行修改，保存后会热重载。

## 托盘菜单

- 截图 / 钉图 / OCR（显示当前快捷键）
- 剪贴板历史
- 翻译：状态 / 模型 / 后端 / 最近译文 / 复制 / 重试 / 暂停
- 代理（git / 终端）：开启 / 关闭 / 当前状态
- 订阅转换：打开转换窗口
- 设置 / 帮助 / 打开配置文件 / 重新加载配置
- 退出

## 开机自启

```bash
cp /usr/share/applications/deskvane.desktop ~/.config/autostart/deskvane.desktop
```

## 目录速查

仓库结构：

- `deskvane/`：应用源码
- `tests/`：测试
- `docs/`：架构与支持策略文档
- `packaging/`：各平台打包元数据与说明
- `scripts/`：构建、安装、发布脚本
- `dist/`：本地产物目录，不提交构建产物

说明文档：

- [docs/README.md](docs/README.md)
- [packaging/README.md](packaging/README.md)
- [scripts/README.md](scripts/README.md)

- 配置文件：`~/.config/deskvane/config.yaml`
- 帮助页面：`~/.config/deskvane/help.html`（应用内可一键打开）
