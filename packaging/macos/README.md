# macOS 打包

首选构建链路：

1. `python3 -m pip install -e .[packaging]`
2. `./scripts/build-macos.sh`

脚本行为：

- 使用 `packaging/pyinstaller/deskvane.spec` 生成 `dist/pyinstaller/DeskVane.app`
- 若系统可用 `hdiutil`，自动继续封装 `dist/DeskVane.dmg`
- 若提供 `DESKVANE_ICON_FILE` 指向 `.icns` 文件，PyInstaller 会将其用于 `.app` 图标

签名与 notarization：

- 当前仓库只提供构建入口，不在脚本中内置证书或 Apple 开发者账号参数
- 实际发布前应在 CI 或本地发行流程中补充 `codesign` 与 `notarytool`
