# ClickGit

ClickGit 是面向完全不使用 Git 命令行用户的 Windows 和 macOS 桌面
Git 工具。程序通过按钮、菜单和对话框完成仓库打开、克隆、提交、同步、
分支、标签、贮藏、冲突解决、恢复和高级维护。

## 下载

首个版本发布为两个独立 Release：

- `windows-v0.1.0`
  - `ClickGit-Windows-x64.zip`
- `mac-v0.1.0`
  - `ClickGit-macOS-arm64.zip`：Apple Silicon，适用于 M1/M2/M3/M4
  - `ClickGit-macOS-x64.zip`：Intel Mac

## Windows 使用

1. 解压 `ClickGit-Windows-x64.zip`。
2. 打开完整的 `ClickGit` 目录。
3. 双击 `ClickGit.exe`。
4. 点击“打开仓库”“克隆”或“新建仓库”。
5. 在“工作区”选择文件并点击“暂存”。
6. 填写提交说明后点击“提交暂存内容”。
7. 使用顶部“获取”“拉取”“推送”按钮同步远程仓库。

Windows 发布目录内包含 PortableGit，不需要安装 Git、Python 或 Qt。必须
保留整个 `ClickGit` 目录，不要只复制单个 EXE。

## macOS 使用

1. 根据 Mac CPU 下载 arm64 或 x64 压缩包。
2. 解压后将 `ClickGit.app` 移入“应用程序”。
3. 点击“打开仓库”“克隆”或“新建仓库”。
4. 在“工作区”选择文件并点击“暂存”。
5. 填写提交说明后点击“提交暂存内容”。
6. 使用顶部“获取”“拉取”“推送”按钮同步远程仓库。

macOS 版本不需要安装 Python 或 Qt，但需要系统能够运行 `git`。如果系统
提示安装 Command Line Tools，请按提示完成安装。应用当前未进行 Apple
签名和公证，首次启动可能需要在 Finder 中右键点击应用并选择“打开”。

## 主要功能

- 本地仓库打开、初始化和远程克隆
- 文件状态、差异、暂存、取消暂存、丢弃修改和提交
- 获取、拉取、推送和安全强制推送
- 分支创建、切换、合并、变基和删除
- 标签、贮藏记录和多个远程仓库
- 提交历史、Reflog、补丁导入导出
- 三方冲突内容查看、编辑、保存、继续和放弃
- Worktree、子模块、Git LFS、仓库完整性检查和优化
- 硬回退前创建隐藏恢复引用
- 清理未跟踪文件时先移动到恢复中心
- 中文路径、空格路径和长文件名

## 认证

- Windows HTTPS 远程使用 Git for Windows 自带的 Git Credential Manager。
- macOS HTTPS 远程使用系统 Git 已配置的凭据助手。
- SSH 远程使用用户现有的 OpenSSH 密钥和 SSH Agent。
- ClickGit 日志和错误对象会脱敏 URL 密码、访问令牌和认证头。
- 密码、访问令牌和私钥不会写入 ClickGit 的 JSON 配置。

## 数据位置

Windows 用户配置和恢复记录保存在：

```text
%APPDATA%\ClickGit\
  settings.json
  recovery\
```

macOS 用户配置和恢复记录保存在：

```text
~/Library/Application Support/ClickGit/
  settings.json
  recovery/
```

恢复中心中的提交恢复点会创建新分支，不会自动覆盖当前分支。隔离文件恢复时若原路径已存在，恢复操作会停止。

## Windows 构建

在 PowerShell 中执行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\bootstrap.ps1
.\scripts\download-portable-git.ps1
.\scripts\build.ps1
.\scripts\verify-package.ps1
```

如果当前网络无法下载 GitHub Release 大文件，可使用本机完整 Git for Windows 发行目录构建：

```powershell
.\scripts\copy-installed-git.ps1
.\scripts\build.ps1
```

最终便携版位于：

```text
dist\ClickGit\ClickGit.exe
```

## macOS 构建

必须在对应 CPU 架构的 macOS 环境中执行：

```bash
python3 -m pip install -r requirements-dev.txt
scripts/build-macos.sh
```

输出文件根据当前 Mac 架构生成：

```text
build/ClickGit-macOS-arm64.zip
build/ClickGit-macOS-x64.zip
```

## 自动发布

推送 `release-v0.1.0` 标签后，GitHub Actions 会在 Windows、macOS Apple
Silicon 和 macOS Intel Runner 上分别测试并构建。三个构建全部通过后，
工作流创建：

```text
windows-v0.1.0
mac-v0.1.0
```

## 已知限制

- Windows 首次访问 HTTPS 远程时，登录窗口由 Git Credential Manager 提供。
- macOS 依赖系统 Git 和系统凭据助手。
- 超大仓库的历史记录当前每次最多加载 200 条。
- 文本冲突编辑器按 UTF-8 保存；二进制冲突需要在外部工具中处理后再暂存。
- Windows 尚未代码签名，SmartScreen 可能显示未知发布者提示。
- macOS 尚未签名和公证，Gatekeeper 可能阻止首次直接双击启动。
