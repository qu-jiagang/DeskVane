# PyInstaller 打包入口

共享 spec 文件：`packaging/pyinstaller/deskvane.spec`

用途：

- Windows: 由 `scripts/build-win.ps1` 调用
- macOS / Linux: 由 `scripts/build-pyinstaller.sh` 或 `scripts/build-macos.sh` 调用

关键环境变量：

- `DESKVANE_APP_NAME`
- `DESKVANE_APP_VERSION`
- `DESKVANE_TARGET_OS`
- `DESKVANE_ONEFILE`
- `DESKVANE_WINDOWED`
- `DESKVANE_ICON_FILE`
- `DESKVANE_BUNDLE_IDENTIFIER`

默认策略：

- Windows / macOS 采用 `windowed` 模式
- 默认构建 `onedir`
- 资源文件会打包 `deskvane/assets/*.png` 与 `deskvane/assets/*.svg`
