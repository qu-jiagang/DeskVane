# Scripts

这个目录只放“可执行入口”，不放平台元数据，也不放业务模块。

当前脚本分工：

- `install.sh`
  - Linux 本地安装入口
- `install-desktop-entry.sh`
  - 注册或更新桌面启动项
- `build-deb.sh`
  - 构建 Debian / Ubuntu `.deb`
- `build-pyinstaller.sh`
  - 构建通用 PyInstaller 包
- `build-macos.sh`
  - 构建 macOS 包
- `build-win.ps1`
  - 构建 Windows 包

维护约定：

- 脚本只做编排，不承载复杂业务逻辑
- 平台模板、安装器配置放到 `packaging/`
- 用户可见的主入口优先写进 `README.md`
