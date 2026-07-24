# ClickGit

ClickGit 是面向完全不使用 Git 命令行的 Windows 桌面 Git 工具。程序通过按钮、菜单和对话框完成仓库打开、克隆、提交、同步、分支、标签、贮藏、冲突解决、恢复和高级维护。

## 直接使用

1. 打开 `dist\ClickGit`。
2. 双击 `ClickGit.exe`。
3. 点击“打开仓库”“克隆”或“新建仓库”。
4. 在“工作区”选择文件并点击“暂存”。
5. 填写提交说明后点击“提交暂存内容”。
6. 使用顶部“获取”“拉取”“推送”按钮同步远程仓库。

发布目录内已包含 PortableGit，不需要目标电脑安装 Git、Python 或 Qt。请保留整个 `ClickGit` 目录，不要只复制单个 EXE。

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

- HTTPS 远程使用 Git for Windows 自带的 Git Credential Manager 图形登录。
- SSH 远程使用用户现有的 OpenSSH 密钥和 SSH Agent。
- ClickGit 日志和错误对象会脱敏 URL 密码、访问令牌和认证头。
- 密码、访问令牌和私钥不会写入 ClickGit 的 JSON 配置。

## 数据位置

用户配置和恢复记录保存在：

```text
%APPDATA%\ClickGit\
  settings.json
  recovery\
```

恢复中心中的提交恢复点会创建新分支，不会自动覆盖当前分支。隔离文件恢复时若原路径已存在，恢复操作会停止。

## 构建

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

## 已知限制

- 首次访问 HTTPS 远程时，登录窗口由 Git Credential Manager 提供。
- 超大仓库的历史记录当前每次最多加载 200 条。
- 文本冲突编辑器按 UTF-8 保存；二进制冲突需要在外部工具中处理后再暂存。
- 应用尚未进行代码签名，Windows SmartScreen 可能显示未知发布者提示。
