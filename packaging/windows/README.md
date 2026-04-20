# Windows 打包

首选构建链路：

1. `python -m pip install -e .[packaging]`
2. `powershell -ExecutionPolicy Bypass -File .\scripts\build-win.ps1`

脚本行为：

- 使用 `packaging/pyinstaller/deskvane.spec` 构建 `dist/pyinstaller/DeskVane/`
- 如检测到 Inno Setup 的 `ISCC.exe`，继续基于 `packaging/windows/deskvane.iss` 生成安装器
- 如未检测到 `ISCC.exe`，保留 PyInstaller 产物并给出后续命令提示

可选准备项：

- 若需要自定义 EXE 图标，可在执行时传入 `-IconPath path\to\deskvane.ico`
- 若需要签名，请在 Inno Setup 产物生成后接入企业已有的签名流程
