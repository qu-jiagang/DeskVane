# DeskVane 发布流程

本文档整理当前仓库已经具备的发布入口、产物形态和各平台的最后人工步骤。

## 当前结论

- Linux：正式发布路径已经具备，主安装方式仍然是 `.deb`
- Windows：已经具备 PyInstaller + Inno Setup 的构建入口，但尚未发布正式安装包
- macOS：已经具备 `.app` / `.dmg` 构建入口，但尚未接入签名与 notarization

这意味着当前仓库已经完成“构建闭环”，但还没有完成“正式分发闭环”。

## Linux 发布

构建：

```bash
./scripts/build-deb.sh
```

安装验证：

```bash
sudo apt install ./dist/deskvane_*.deb
deskvane
```

应确认：

- 应用菜单中可见 `DeskVane`
- `/usr/bin/deskvane` 可执行
- 首次启动能正常生成配置文件
- 托盘、截图、设置页、通知正常

## Windows 发布

构建：

```powershell
python -m pip install -e .[packaging]
powershell -ExecutionPolicy Bypass -File .\scripts\build-win.ps1
```

可选安装器：

- 若系统已安装 Inno Setup，脚本会继续生成安装器
- 若未安装，则至少会保留 `dist/pyinstaller/DeskVane/` 或单文件 EXE

应确认：

- 主程序可启动
- 托盘可显示
- 全局快捷键可注册
- 文本剪贴板和截图可用
- 开机自启脚本可生成到 Startup 目录

正式分发前还需要：

- 对 EXE / 安装器做企业已有的代码签名
- 在真实 Windows 环境完成一次安装器安装和卸载验证

## macOS 发布

构建：

```bash
python3 -m pip install -e .[packaging]
./scripts/build-macos.sh
```

产物：

- `dist/pyinstaller/DeskVane.app`
- 若系统提供 `hdiutil`，附带 `dist/DeskVane.dmg`

应确认：

- `.app` 可启动
- 托盘可显示
- 快捷键监听可用
- 文本剪贴板和截图可用
- LaunchAgent 文件可正确生成

正式分发前还需要：

- `codesign`
- `notarytool`
- 对 `.app` 和 `.dmg` 在真实 macOS 上完成一次启动与权限验证

## 发布前统一检查

在提交发布前，至少执行：

```bash
python -m compileall deskvane
python -m pytest -q
```

并确认以下文档与产物保持一致：

- [README.md](/home/midea/GithubRepository/DeskVane/README.md)
- [docs/platform-feature-matrix.md](/home/midea/GithubRepository/DeskVane/docs/platform-feature-matrix.md)
- [docs/platform-support-statement.md](/home/midea/GithubRepository/DeskVane/docs/platform-support-statement.md)
- `scripts/build-*.sh`
- `scripts/build-win.ps1`

## 目前还不应该对外宣称的内容

在正式完成签名、实机验收和安装验证前，不应对外宣称：

- Windows 已正式支持
- macOS 已正式支持
- Windows/macOS 已提供官方安装包
