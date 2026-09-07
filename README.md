# ClickGit

[![Release ClickGit](https://github.com/ljy-codes/clickgit-desktop/actions/workflows/release.yml/badge.svg)](https://github.com/ljy-codes/clickgit-desktop/actions/workflows/release.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-blue.svg)](#下载)

ClickGit 是面向完全不使用 Git 命令行用户的 Windows 和 macOS 桌面 Git
客户端。仓库、提交、同步、分支、冲突和恢复操作均通过按钮、列表和对话框
完成。

## 下载

### 当前稳定版 v0.1.0

- [`windows-v0.1.0`](https://github.com/ljy-codes/clickgit-desktop/releases/tag/windows-v0.1.0)
  - [`ClickGit-Windows-x64.zip`](https://github.com/ljy-codes/clickgit-desktop/releases/download/windows-v0.1.0/ClickGit-Windows-x64.zip)：历史便携包
- [`mac-v0.1.0`](https://github.com/ljy-codes/clickgit-desktop/releases/tag/mac-v0.1.0)
  - [`ClickGit-macOS-arm64.zip`](https://github.com/ljy-codes/clickgit-desktop/releases/download/mac-v0.1.0/ClickGit-macOS-arm64.zip)：macOS Apple Silicon
  - [`ClickGit-macOS-x64.zip`](https://github.com/ljy-codes/clickgit-desktop/releases/download/mac-v0.1.0/ClickGit-macOS-x64.zip)：macOS Intel

当前稳定版的 Windows Release 只有上述历史便携包，不包含新版安装包。macOS
版本包含应用运行环境，但需要系统 Git。
使用 Git LFS 功能时还需安装 Git LFS。

### 下一版本交付格式与本地构建产物

本地执行 `scripts\package.ps1` 后，Windows 会生成：

- `ClickGit-Windows-x64-Setup.exe`：安装版优先，适合普通用户
- `ClickGit-Windows-x64-Portable.zip`：便携版备用，适合无安装权限或需要随身携带的场景

这两个新文件名是下一版本的交付格式和本地构建产物。
它们尚未作为当前稳定版附件发布。两种包均包含 PortableGit，不要求另外安装
Git、Python 或 Qt。

## 快速开始

### Windows

当前稳定版 `v0.1.0`：

1. 下载 [`ClickGit-Windows-x64.zip`](https://github.com/ljy-codes/clickgit-desktop/releases/download/windows-v0.1.0/ClickGit-Windows-x64.zip)。
2. 完整解压下载的历史便携包。
3. 保留解压后的完整 `ClickGit` 目录，不单独移动其中的 EXE。
4. 双击 `ClickGit.exe`。

新版本发布后，普通用户优先安装版；无安装权限或需要随身携带时再使用便携版
备用。

启动后，点击“打开仓库”“克隆”或“新建仓库”，勾选文件并点击“暂存”，
输入提交说明后点击“提交暂存内容”，再使用“获取”“拉取”和“推送”同步
远程仓库。

### macOS

1. 下载与 CPU 架构匹配的压缩包。
2. 解压并将 `ClickGit.app` 移入“应用程序”。
3. 首次启动被阻止时，在 Finder 中右键应用并选择“打开”。
4. 通过界面完成仓库打开、提交和同步。

## 功能矩阵

| 分类 | 功能 |
| --- | --- |
| 仓库 | 打开、初始化、克隆、最近仓库 |
| 工作区 | 状态、差异、暂存、取消暂存、丢弃修改 |
| 提交 | 提交、修正提交、历史、文件历史 |
| 同步 | 获取、拉取、推送、安全强制推送 |
| 分支 | 新建、切换、合并、变基、删除 |
| 版本 | 标签、贮藏、Reflog、补丁 |
| 冲突 | 三方查看、编辑、继续和放弃 |
| 恢复 | 提交恢复点、未跟踪文件隔离、恢复中心 |
| 扩展 | Worktree、子模块、Git LFS、完整性检查 |

## 安全与恢复

- 同一仓库的写操作串行执行。
- Git 命令使用参数数组执行，不拼接 Shell 命令字符串。
- 硬回退前创建隐藏恢复引用。
- 清理未跟踪文件前先移动到恢复目录。
- 强制推送默认使用租约保护。
- 日志和错误对象会脱敏 URL 密码、访问令牌和认证头。

恢复中心中的提交恢复点会创建新分支，不会自动覆盖当前分支。恢复隔离文件
时，如果目标路径已存在，操作会停止并要求用户处理冲突。

## 数据与隐私

Windows 数据目录：

```text
%APPDATA%\ClickGit\
  settings.json
  recovery\
```

macOS 数据目录：

```text
~/Library/Application Support/ClickGit/
  settings.json
  recovery/
```

密码、访问令牌和私钥内容不会写入 ClickGit 的 JSON 配置。HTTPS 和 SSH
认证使用操作系统、Git Credential Manager 或用户已有 SSH Agent。

## 开发与测试

Windows 初始化和测试：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\bootstrap.ps1
$env:PYTHONPATH = "src"
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
```

Windows 构建、打包和验证：

```powershell
.\scripts\download-portable-git.ps1
.\scripts\build.ps1
.\scripts\verify-package.ps1
.\scripts\package.ps1 -Version 0.1.0
```

整理本机外层交付目录：

```powershell
.\scripts\publish.ps1 -Version 0.1.0
```

`scripts\package.ps1` 生成 Windows 安装版和便携版；`scripts\publish.ps1`
将最终包、用户文档和 SHA-256 清单整理到外层目录。展开的应用运行文件只保留
在 `artifacts` 中。

macOS 构建：

```bash
python3 -m pip install -r requirements-dev.txt
scripts/build-macos.sh
```

## 项目结构

```text
artifacts/   本地和 CI 生成的构建产物
docs/        设计、开发、许可证和发布记录
installer/   PyInstaller 和 Windows 安装器配置
runtime/     Windows PortableGit 运行时
scripts/     构建、验证、打包和发布脚本
src/         ClickGit 源码
tests/       自动化测试
```

`artifacts`、`.venv`、缓存和本地运行日志不提交到 Git 仓库。

## 发布

推送 `release-vX.Y.Z` 标签后，GitHub Actions 在 Windows、macOS Apple
Silicon 和 macOS Intel Runner 上测试并构建。三个构建全部成功后创建：

```text
windows-vX.Y.Z
mac-vX.Y.Z
```

Windows Release 以 `ClickGit-Windows-x64-Setup.exe` 安装版优先，并提供
`ClickGit-Windows-x64-Portable.zip` 便携版备用。macOS Release 保留
`ClickGit-macOS-arm64.zip` 和 `ClickGit-macOS-x64.zip` 双架构附件。
文档描述的是发布流程和产物约定；只有工作流实际成功后，才表示对应 GitHub
附件已同步。

版本变化记录在 [CHANGELOG.md](CHANGELOG.md)，详细发布记录保存在
`docs/releases`。当前发布工作流尚未自动检查第三方许可证材料；在自动化
门禁建立前，发布负责人必须按实际产物人工检查，检查未完成不得发布。

## 已知限制

- Windows 应用尚未代码签名，SmartScreen 可能显示未知发布者。
- macOS 应用尚未签名和公证，Gatekeeper 可能阻止首次直接启动。
- 超大仓库的历史记录当前最多加载 200 条。
- 文本冲突编辑器按 UTF-8 保存，二进制冲突需要外部工具处理。

## 许可证

ClickGit 源码采用 [MIT License](LICENSE)。发布包包含的第三方组件继续遵循
各自许可证，基线声明见
[THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt)。`docs/licenses`
目前是待完善的许可证治理入口，不代表现有发布包的许可证材料已经齐全。
