# Changelog

本文件记录 ClickGit 的重要变更。

## [Unreleased]

### Added

- 产品化设计与后续迭代计划。
- 项目代码采用 MIT License。
- 建立设计、实施、发布和第三方依赖声明文档体系。

### Changed

- 将工程治理、产品文档和交付清单纳入发布门禁。

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

[Unreleased]: https://github.com/ljy-codes/clickgit-desktop/compare/windows-v0.1.0...HEAD
[0.1.0]: https://github.com/ljy-codes/clickgit-desktop/releases/tag/windows-v0.1.0
[macOS 0.1.0]: https://github.com/ljy-codes/clickgit-desktop/releases/tag/mac-v0.1.0
