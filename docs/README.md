# Docs

这个目录存放项目文档，按用途分两类：

- 产品/架构文档
  - `architecture-design.md`
  - `cross-platform-refactor-plan.md`
  - `tauri-migration-plan.md`
  - `platform-feature-matrix.md`
  - `platform-support-statement.md`
  - `release-process.md`

- 后续建议
  - 新增文档时优先放到 `docs/`
  - 与某个平台强绑定的发布说明，优先放到 `packaging/<platform>/`

当前约定：

- `README.md` 只保留用户入口、安装方式和高层说明
- 详细平台边界、支持声明、重构计划放到 `docs/`
- 打包脚本的具体使用说明放到 `packaging/`
- 脚本职责划分放到 `scripts/README.md`
