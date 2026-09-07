# Changelog

本文件记录 ClickGit 的重要变更。

## [Unreleased]

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
