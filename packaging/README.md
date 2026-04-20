# Packaging

这个目录只放发布和安装相关文件，不放运行时代码。

当前约定：

- `debian/`
  - Debian / Ubuntu `.deb` 打包元数据
  - `postinst` / `postrm` 等安装后脚本
- `pyinstaller/`
  - PyInstaller spec 和通用打包说明
- `windows/`
  - Windows 安装器模板和说明
- `macos/`
  - macOS 打包说明
- `deskvane.desktop`
  - Linux 桌面启动项模板

配套脚本放在项目根目录下的 `scripts/`：

- `scripts/build-deb.sh`
- `scripts/build-pyinstaller.sh`
- `scripts/build-macos.sh`
- `scripts/build-win.ps1`

如果新增平台打包逻辑：

- 元数据、模板、平台说明放 `packaging/<platform>/`
- 实际执行脚本放 `scripts/`
- 不要把构建产物提交进仓库，产物统一留在 `dist/`
