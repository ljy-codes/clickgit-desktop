# ClickGit macOS And Dual Release Design

## Goal

在不破坏现有 Windows 便携版的前提下，让 ClickGit 支持 macOS，并通过
GitHub Actions 为 `v0.1.0` 自动构建和发布两个独立 Release。

## Release Layout

- `windows-v0.1.0`
  - `ClickGit-Windows-x64.zip`
- `mac-v0.1.0`
  - `ClickGit-macOS-arm64.zip`
  - `ClickGit-macOS-x64.zip`

发布由 `release-v0.1.0` 标签触发。Windows 和两个 macOS 架构均构建、
测试成功后，发布任务才创建 Release，避免产生缺少附件的半成品版本。

## Platform Behavior

- Windows 继续优先使用发行目录内的 PortableGit。
- macOS 使用系统可执行路径中的 `git` 和 `ssh-keygen`。
- Windows 配置目录保持 `%APPDATA%\ClickGit`。
- macOS 配置目录使用 `~/Library/Application Support/ClickGit`。
- Windows 使用 Microsoft YaHei UI，macOS 使用 PingFang SC。
- 诊断模式必须报告实际 Git 路径，并能在两个平台启动隐藏 GUI 冒烟测试。

## Packaging

- Windows 保留现有 `packaging/clickgit.spec` 和 PowerShell 构建流程。
- macOS 新增 `packaging/clickgit-macos.spec`，输出 `ClickGit.app`。
- macOS 构建不捆绑 Git，减小体积并避免分发 Git for Windows 文件。
- macOS 使用 `ditto` 压缩 `.app`，保留应用包权限、资源和符号链接。
- 当前版本不做 Apple 代码签名或公证，README 必须明确 Gatekeeper 风险。

## GitHub Actions

工作流使用三个独立构建任务：

1. `windows-x64` 在 `windows-latest` 构建便携目录。
2. `macos-arm64` 在 `macos-15-arm64` 构建 Apple Silicon 应用。
3. `macos-x64` 在 `macos-15` 构建 Intel 应用。

发布任务下载三个构建产物，使用仓库的 `GITHUB_TOKEN` 创建 Windows 和
macOS 两个 Release。工作流只在 `release-v*` 标签上执行，并授予最小的
`contents: write` 权限。

## Verification

- 为平台路径、字体和 Git 定位增加单元测试。
- 为 macOS spec 和 Release 工作流增加配置测试。
- Windows 本地运行完整测试和现有发行包冒烟测试。
- macOS 构建与 `.app` 启动检查由 GitHub Actions 的真实 macOS Runner 完成。
- Release 创建后检查两个 Release 的标签和三个附件是否存在。

## Compatibility And Risks

- Windows 使用方式、配置目录和发行结构保持兼容。
- macOS 依赖系统 Git；如果系统找不到 Git，应用显示明确错误。
- 未签名、未公证的 `.app` 可能被 macOS Gatekeeper 阻止首次启动。
- Intel 和 Apple Silicon 分开构建，用户必须下载匹配 CPU 架构的附件。
