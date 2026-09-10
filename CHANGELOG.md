# Changelog

本文件记录 ClickGit 的重要变更。

## [Unreleased]

### 0.2.0 当前验收构建（2026-09-10）

版本不变，构建标识 `2026-09-10-source-inline-highlight`；用户已确认验收。
本项描述当前源码，不表示已覆盖旧 GitHub Release 附件。

- 增加三主题、字号/密度偏好、应用及安装器图标样式。
- 完善左右文档比较、可编辑冲突处理与 HTML 需求/源码审阅。
- HTML 静态预览隔离到独立进程，增加超时保护、本机诊断、改动列表、
  版本标题、正文高亮及缩放；继续禁用原型脚本与外部资源。
- 源码比较改为清晰的红删绿增字符高亮，长行小修改先剥离共同前后缀，
  保留预算、UTF-16 定位和原文复制。
- 从产品移除 AI 助手、模型管理及对应运行时打包入口。
- 不调整配置结构、不执行历史迁移、不修改业务仓库。
- Windows 自动回归 453 项：452 通过、1 项权限跳过；详见
  [验收与交付记录](docs/releases/2026-09-10-v0.2.0-acceptance.md)。

## [0.2.0] - 2026-09-07

### Added

- 产品化设计与后续迭代计划。
- 项目代码采用 MIT License。
- 建立设计、实施、发布和第三方依赖声明文档体系。

### Changed

- 将工程治理、产品文档和交付清单纳入发布门禁。
- PyInstaller 运行依赖调整到 `_internal`，PortableGit 继续位于应用目录的
  `runtime\git`。
- Windows 交付改为安装版 `ClickGit-Windows-x64-Setup.exe` 优先，并提供
  便携包 `ClickGit-Windows-x64-Portable.zip` 备用。
- 发布脚本使用干净交付目录，仅保留最终 Windows/macOS 包和包含 SHA-256
  校验值的 `SHA256SUMS.txt`，不再暴露展开的运行依赖。
- Windows 和 macOS 发布包加入第三方许可证原文、Qt/PySide6/Shiboken6
  通知与 SHA-256 锁定清单，依赖版本或材料不一致时阻断构建。
- GitHub Release 对同名附件执行 SHA-256 一致性检查，支持失败后安全重跑；
  Windows/macOS Release 分别上传只覆盖当前平台安装包的校验清单。
- 本地发布会校验 Windows 构建版本和产物哈希，并校验 macOS ZIP 完整性、
  `.app` 版本、可执行权限、Mach-O 格式和 CPU 架构。
- Windows 构建和打包清理会拒绝目录联接点及其他重解析点；打包失败时保留
  上一份已验证产物。

### Distribution

- Windows Release：`windows-v0.2.0`。
- macOS Release：[`mac-v0.2.0`][macOS 0.2.0]。
- 两个 Release 均包含 `SHA256SUMS.txt`，校验项使用纯文件名。

## [0.1.0] - 2026-07-28

### Added

- 发布 Windows x64 便携版和 macOS Apple Silicon、Intel 版本。
- 支持仓库打开、初始化、克隆、文件暂存、提交和远程同步。
- 支持分支、标签、贮藏、提交历史、Reflog、补丁和冲突处理。
- 支持恢复中心、SSH 密钥管理和 HTTPS 凭据助手。
- 支持 Worktree、子模块和 Git LFS。
- 支持未跟踪文件隔离、恢复和敏感信息脱敏。

### Distribution

- Windows Release：`windows-v0.1.0`。
- macOS Release：[`mac-v0.1.0`][macOS 0.1.0]。

### Known Limitations

- Windows 应用尚未代码签名，SmartScreen 可能提示未知发布者。
- macOS 应用尚未签名和公证，Gatekeeper 可能阻止首次直接启动。

[Unreleased]: https://github.com/ljy-codes/clickgit-desktop/compare/windows-v0.2.0...HEAD
[0.2.0]: https://github.com/ljy-codes/clickgit-desktop/releases/tag/windows-v0.2.0
[macOS 0.2.0]: https://github.com/ljy-codes/clickgit-desktop/releases/tag/mac-v0.2.0
[0.1.0]: https://github.com/ljy-codes/clickgit-desktop/releases/tag/windows-v0.1.0
[macOS 0.1.0]: https://github.com/ljy-codes/clickgit-desktop/releases/tag/mac-v0.1.0
