# DeskVane

Linux 系统托盘聚合工具箱。将日常桌面上零散的小工具（截图、翻译、OCR、剪贴板、代理、订阅转换、Mihomo 控制）集中到一个托盘图标里。

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
- **Mihomo 集成**
  - 可保留 Mihomo Party，或改由 DeskVane 直接托管 `mihomo` core
  - 托盘内切换模式、切换代理组、查看节点延迟
  - 支持 TUN、PAC（本地分流）、`external-ui` 直开浏览器面板
- **订阅转换**
  - 内建订阅转换器，支持把多家机场订阅合成 Mihomo 配置
  - 结果可直接写入 Core 的 `providers/deskvane-subscription.yaml`
- **系统监控**
  - 托盘图标可显示 CPU / GPU 占用
- **图形设置面板**
  - 所有常用配置均可在 GUI 中调整，无需手写 YAML

## 安装

翻译功能依赖 Ollama，先拉好模型：

```bash
ollama serve
ollama pull qwen2.5:3b
```

安装 DeskVane：

```bash
/usr/bin/python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -U pip setuptools wheel
pip install -e .
deskvane
```

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
sudo apt install python3-tk python3-gi gir1.2-ayatanaappindicator3-0.1 \
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

## 配置

首次运行会自动生成配置文件 `~/.config/deskvane/config.yaml`，主要配置段：

- `screenshot`：截图 / 钉图 / OCR 的快捷键、保存目录、是否复制到剪贴板
- `translator`：Ollama 地址、模型、源 / 目标语言、浮窗宽度、请求超时等
- `proxy`：git / 终端共享的代理地址
- `general`：通知开关、剪贴板历史开关及其快捷键、托盘显示模式
- `subconverter`：本地订阅转换服务端口
- `mihomo`：后端模式（`party` / `core`）、core 工作目录、订阅地址、`external-ui`、TUN、PAC 等

推荐直接打开托盘菜单里的「设置」面板进行修改，保存后会热重载。

## Mihomo Core

- `http://127.0.0.1:9090/` 返回 `{"hello":"mihomo"}` 是正常的，这只是 API 根路径。
- 真正的控制接口在 `/configs`、`/proxies` 等 REST 路径，DeskVane 的托盘和轻量面板也是调用这些接口。
- 想在浏览器里直接打开可视化面板：在 `~/.config/deskvane/mihomo/config.yaml` 里配置 `external-ui`，或在 DeskVane 设置里填 `external_ui` / `external_ui_name` / `external_ui_url`。
- 想让 Core 面板里直接「更新订阅到 Core」：填写 `mihomo.subscription_url`，也可以在订阅转换窗口中保存多个订阅。
- DeskVane 会把订阅节点写到 `~/.config/deskvane/mihomo/providers/deskvane-subscription.yaml`，并在主 `config.yaml` 里最小注入 `proxy-providers` 和 `DESKVANE-*` 代理组；不会整体覆盖你手写的 DNS、TUN、规则等配置。
- PAC 开启后会在 `mihomo.pac_port` 上提供本地 PAC 文件，方便浏览器 / 系统做精细分流。

## 托盘菜单

- 截图 / 钉图 / OCR（显示当前快捷键）
- 剪贴板历史
- 翻译：状态 / 模型 / 后端 / 最近译文 / 复制 / 重试 / 暂停
- 代理（git / 终端）：开启 / 关闭 / 当前状态
- Mihomo：后端切换、模式切换、代理组、节点延迟、打开 Web 面板
- 订阅转换：打开转换窗口、应用到 Core
- 设置 / 帮助 / 打开配置文件 / 重新加载配置
- 退出

## 开机自启

```bash
./scripts/install-desktop-entry.sh --autostart
```

## 目录速查

- 配置文件：`~/.config/deskvane/config.yaml`
- 帮助页面：`~/.config/deskvane/help.html`（应用内可一键打开）
- Mihomo 工作目录：`~/.config/deskvane/mihomo/`
- 订阅 Provider：`~/.config/deskvane/mihomo/providers/deskvane-subscription.yaml`
