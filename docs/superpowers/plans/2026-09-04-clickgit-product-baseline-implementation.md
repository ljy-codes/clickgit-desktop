# ClickGit Product Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立 ClickGit 完整产品化改造的第一阶段基线，包括 MIT 许可证、项目元数据、版本记录、第三方声明、文档目录、产品化 README、外层进度记录和可重复验证门禁。

**Architecture:** 本阶段不移动业务代码、不调整 Git 行为、不改变配置和打包入口，只补齐产品元数据和工程治理基线。后续工程分层、应用用例、工作台 UI、功能整理和双平台安装发布分别编写独立实施计划，以当前阶段的测试和目录状态作为输入。

**Tech Stack:** Python 3.11+、PySide6 6.10.3、unittest、PowerShell、GitHub Actions、Markdown、PyProject/Setuptools

---

## Plan Boundary

本设计包含多个可独立验收的子系统，不能在一个超大提交中同时实施。本计划
只执行第一阶段“产品基线”，后续按以下顺序分别生成实施计划：

1. 领域模型与 Git 基础设施边界。
2. Application 用例和后台任务编排。
3. 三栏工作台 UI。
4. Git 功能整理、安全和恢复完善。
5. Windows/macOS 安装、交付和 Release。

本阶段禁止修改：

- `src/clickgit/app.py`
- `src/clickgit/repository.py`
- `src/clickgit/ui/main_window.py`
- 用户配置格式和数据目录
- `.github/workflows/release.yml` 的发布语义
- `installer/*.spec` 的打包入口

## Baseline

计划编写前已在 2026-09-04 使用正常 Windows 权限执行：

```powershell
$env:PYTHONPATH = "src"
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
```

结果：

```text
Ran 65 tests in 59.659s
OK
```

在受限沙箱中运行时，Python 3.14 的临时目录清理可能出现
`PermissionError: [WinError 5]`。该错误属于执行环境权限问题，不能作为项目
回归判断；正式验证必须在正常 Windows 权限或明确可写的 CI Runner 中执行。

## File Structure

本阶段新增或修改的文件及职责：

```text
开发空间\
├─ LICENSE
├─ CHANGELOG.md
├─ THIRD-PARTY-NOTICES.txt
├─ README.md
├─ pyproject.toml
├─ tests\
│  └─ test_project_metadata.py
└─ docs\
   ├─ images\
   │  └─ README.md
   ├─ development\
   │  ├─ README.md
   │  └─ 2026-09-04-product-baseline.md
   ├─ releases\
   │  ├─ README.md
   │  └─ 2026-07-28-v0.1.0.md
   └─ licenses\
      └─ README.md

D:\专用工具\git工具\
├─ 进度.md
└─ 文件夹说明.txt
```

- `LICENSE`：ClickGit 源码的 MIT 许可证。
- `CHANGELOG.md`：按版本记录用户可感知变化。
- `THIRD-PARTY-NOTICES.txt`：列出随应用构建或分发的主要第三方组件。
- `README.md`：产品介绍、下载、使用、安全、构建和发布入口。
- `test_project_metadata.py`：防止许可证、版本文档和项目结构在后续重构中丢失。
- `docs/images`：规定截图名称、内容和隐私要求。
- `docs/development`：保存基线、测试和构建报告。
- `docs/releases`：保存与 GitHub Release 对应的版本记录。
- `docs/licenses`：保存第三方许可证收集规则和后续许可证原文。
- 外层 `进度.md`：记录当前阶段、验证结果、风险和下一步。

### Task 1: Adopt the MIT license and package metadata

**Files:**
- Create: `LICENSE`
- Create: `tests/test_project_metadata.py`
- Modify: `pyproject.toml`
- Test: `tests/test_project_metadata.py`

- [ ] **Step 1: Write the failing metadata test**

Create `tests/test_project_metadata.py`:

```python
from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ProjectMetadataTests(unittest.TestCase):
    def test_project_uses_mit_license_and_repository_urls(self) -> None:
        pyproject = tomllib.loads(
            (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        project = pyproject["project"]

        self.assertEqual(project["license"], "MIT")
        self.assertEqual(
            project["urls"]["Repository"],
            "https://github.com/ljy-codes/clickgit-desktop",
        )
        self.assertEqual(
            project["urls"]["Issues"],
            "https://github.com/ljy-codes/clickgit-desktop/issues",
        )

        license_text = (PROJECT_ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertTrue(license_text.startswith("MIT License\n"))
        self.assertIn("Copyright (c) 2026 ljy-codes", license_text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest `
  tests.test_project_metadata.ProjectMetadataTests.test_project_uses_mit_license_and_repository_urls `
  -v
```

Expected:

```text
ERROR
FileNotFoundError: LICENSE
```

The failure may first appear as `KeyError: 'license'`; either failure confirms that the
metadata baseline is not implemented.

- [ ] **Step 3: Add MIT metadata to `pyproject.toml`**

Replace the current `[project]` section with:

```toml
[project]
name = "clickgit"
version = "0.1.0"
description = "A click-only Git desktop client for Windows and macOS"
readme = "README.md"
requires-python = ">=3.11"
license = "MIT"
keywords = ["git", "desktop", "gui", "pyside6"]
authors = [
    { name = "ljy-codes" },
]
dependencies = [
    "PySide6==6.10.3",
]

[project.urls]
Repository = "https://github.com/ljy-codes/clickgit-desktop"
Issues = "https://github.com/ljy-codes/clickgit-desktop/issues"
```

Keep the existing `[build-system]`, `[project.scripts]`, `[tool.setuptools]` and
`[tool.setuptools.packages.find]` sections unchanged.

- [ ] **Step 4: Add the MIT license**

Create `LICENSE`:

```text
MIT License

Copyright (c) 2026 ljy-codes

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 5: Run the metadata test and verify it passes**

Run:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest `
  tests.test_project_metadata.ProjectMetadataTests.test_project_uses_mit_license_and_repository_urls `
  -v
```

Expected:

```text
Ran 1 test
OK
```

- [ ] **Step 6: Commit the license baseline**

```powershell
git add LICENSE pyproject.toml tests/test_project_metadata.py
git commit -m "docs: adopt MIT license"
```

### Task 2: Add changelog, release history and third-party notices

**Files:**
- Create: `CHANGELOG.md`
- Create: `THIRD-PARTY-NOTICES.txt`
- Create: `docs/releases/2026-07-28-v0.1.0.md`
- Modify: `tests/test_project_metadata.py`
- Test: `tests/test_project_metadata.py`

- [ ] **Step 1: Add failing tests for release and dependency records**

Add these methods to `ProjectMetadataTests`:

```python
    def test_change_log_and_release_record_describe_v010(self) -> None:
        changelog = (PROJECT_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        release = (
            PROJECT_ROOT / "docs" / "releases" / "2026-07-28-v0.1.0.md"
        ).read_text(encoding="utf-8")

        self.assertIn("## [Unreleased]", changelog)
        self.assertIn("## [0.1.0] - 2026-07-28", changelog)
        self.assertIn("windows-v0.1.0", release)
        self.assertIn("mac-v0.1.0", release)
        self.assertIn("ClickGit-Windows-x64.zip", release)
        self.assertIn("ClickGit-macOS-arm64.zip", release)
        self.assertIn("ClickGit-macOS-x64.zip", release)

    def test_third_party_notice_lists_distributed_components(self) -> None:
        notices = (
            PROJECT_ROOT / "THIRD-PARTY-NOTICES.txt"
        ).read_text(encoding="utf-8")

        for component in (
            "Python",
            "PySide6",
            "Shiboken6",
            "PyInstaller",
            "Git for Windows",
            "Git Credential Manager",
        ):
            with self.subTest(component=component):
                self.assertIn(component, notices)
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest `
  tests.test_project_metadata.ProjectMetadataTests.test_change_log_and_release_record_describe_v010 `
  tests.test_project_metadata.ProjectMetadataTests.test_third_party_notice_lists_distributed_components `
  -v
```

Expected:

```text
FAILED (errors=2)
```

The errors must identify the missing changelog, release record or third-party notice.

- [ ] **Step 3: Create `CHANGELOG.md`**

```markdown
# Changelog

本项目所有重要变化均记录在此文件中。

## [Unreleased]

### Added

- 增加完整产品化改造设计和分阶段实施计划。
- 采用 MIT 开源许可证。
- 建立开发、发布、许可证和截图文档目录。

### Changed

- 将工程治理、产品文档和交付清单纳入发布门禁。

## [0.1.0] - 2026-07-28

### Added

- 发布 Windows x64 便携版。
- 发布 macOS Apple Silicon 和 Intel 应用包。
- 支持仓库打开、初始化、克隆、提交、同步、分支和标签。
- 支持贮藏、冲突处理、Reflog、补丁、Worktree、子模块和 Git LFS。
- 增加危险操作恢复点、未跟踪文件隔离和敏感信息脱敏。

### Known limitations

- Windows 应用尚未代码签名。
- macOS 应用尚未签名和公证。
- macOS 依赖系统 Git。

[Unreleased]: https://github.com/ljy-codes/clickgit-desktop/compare/windows-v0.1.0...HEAD
[0.1.0]: https://github.com/ljy-codes/clickgit-desktop/releases/tag/windows-v0.1.0
```

- [ ] **Step 4: Create the v0.1.0 release record**

Create `docs/releases/2026-07-28-v0.1.0.md`:

```markdown
# ClickGit v0.1.0 发布记录

**发布日期：** 2026-07-28
**Windows Release：** `windows-v0.1.0`
**macOS Release：** `mac-v0.1.0`

## 交付文件

- `ClickGit-Windows-x64.zip`
- `ClickGit-macOS-arm64.zip`
- `ClickGit-macOS-x64.zip`

## 平台说明

- Windows 版本包含 PortableGit，不要求用户安装 Git、Python 或 Qt。
- macOS 版本包含 Python/Qt 应用运行环境，但使用系统 Git。
- macOS 用户必须下载与 CPU 架构匹配的应用包。

## 主要能力

- 仓库打开、初始化和克隆。
- 工作区查看、暂存、提交、拉取和推送。
- 分支、标签、贮藏、冲突、恢复和仓库维护。
- Worktree、子模块、Git LFS 和补丁操作。

## 已知问题

- Windows 未签名，SmartScreen 可能显示未知发布者。
- macOS 未签名和公证，首次启动可能被 Gatekeeper 阻止。
- 大型仓库的历史记录默认最多加载 200 条。
- 二进制冲突需要使用外部工具处理。
```

- [ ] **Step 5: Create `THIRD-PARTY-NOTICES.txt`**

```text
ClickGit Third-Party Notices
============================

ClickGit source code is licensed under the MIT License. The packaged
applications also contain or are built with third-party software governed by
their own licenses.

Python
------
Used as the application runtime and distributed in packaged builds.
License: Python Software Foundation License.

PySide6 6.10.3
--------------
Used for the desktop user interface.
License expression reported by the installed package:
LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only.

Shiboken6 6.10.3
----------------
Used by PySide6.
License expression reported by the installed package:
LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only.

PyInstaller 6.21.0
------------------
Used to build distributable applications.
License: GPLv2-or-later with the PyInstaller exception.

Git for Windows
---------------
Bundled with the Windows portable application.
Git is distributed under GNU General Public License version 2. Git for Windows
also contains separately licensed components. Their license files remain in
the bundled runtime directories.

Git Credential Manager
----------------------
Bundled as part of Git for Windows for HTTPS credential handling.
Its LICENSE and NOTICE files remain in the bundled runtime.

Complete license texts
----------------------
The release packaging process must preserve applicable license and notice
files from Python, Qt/PySide6, Git for Windows, Git Credential Manager and
their redistributed dependencies. The inventory is maintained under
docs/licenses and verified before each release.
```

- [ ] **Step 6: Run the release metadata tests**

Run:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest `
  tests.test_project_metadata.ProjectMetadataTests.test_change_log_and_release_record_describe_v010 `
  tests.test_project_metadata.ProjectMetadataTests.test_third_party_notice_lists_distributed_components `
  -v
```

Expected:

```text
Ran 2 tests
OK
```

- [ ] **Step 7: Commit release and dependency records**

```powershell
git add CHANGELOG.md THIRD-PARTY-NOTICES.txt `
  docs/releases/2026-07-28-v0.1.0.md `
  tests/test_project_metadata.py
git commit -m "docs: add release and dependency records"
```

### Task 3: Establish the product documentation directories

**Files:**
- Create: `docs/images/README.md`
- Create: `docs/development/README.md`
- Create: `docs/releases/README.md`
- Create: `docs/licenses/README.md`
- Modify: `tests/test_project_metadata.py`
- Test: `tests/test_project_metadata.py`

- [ ] **Step 1: Add a failing documentation structure test**

Add this method to `ProjectMetadataTests`:

```python
    def test_documentation_directories_are_tracked(self) -> None:
        expected_files = (
            "docs/images/README.md",
            "docs/development/README.md",
            "docs/releases/README.md",
            "docs/licenses/README.md",
        )

        for relative_path in expected_files:
            with self.subTest(path=relative_path):
                path = PROJECT_ROOT / relative_path
                self.assertTrue(path.is_file())
                self.assertGreater(len(path.read_text(encoding="utf-8")), 80)
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest `
  tests.test_project_metadata.ProjectMetadataTests.test_documentation_directories_are_tracked `
  -v
```

Expected:

```text
FAIL
AssertionError: False is not true
```

- [ ] **Step 3: Create `docs/images/README.md`**

```markdown
# 产品截图

此目录保存 README、安装说明和发布说明使用的 ClickGit 截图。

## 命名

- `main-workspace-light.png`
- `main-workspace-dark.png`
- `conflict-editor.png`
- `recovery-center.png`
- `windows-installer.png`
- `macos-install.png`

截图必须来自真实应用，不使用无法操作的概念图代替产品截图。截图前清除访问
令牌、用户名、私有仓库地址、本地个人目录和提交中的敏感信息。工作台 UI
改造完成后重新生成主界面截图，旧截图不得继续用于新版本发布。
```

- [ ] **Step 4: Create `docs/development/README.md`**

```markdown
# 开发记录

此目录保存可复核的工程记录，包括测试基线、构建报告、性能检查和兼容性验证。

每份报告必须包含日期、提交哈希、执行环境、完整命令、结果摘要、失败原因和
未验证项。沙箱、网络、签名证书或平台缺失导致的环境问题必须与代码失败分开
记录，不能把未执行项标记为通过。
```

- [ ] **Step 5: Create `docs/releases/README.md`**

```markdown
# 发布记录

此目录保存每个 ClickGit 版本的发布说明和验证结论。

文件名使用 `YYYY-MM-DD-vX.Y.Z.md`。每份记录必须列出 Windows/macOS Release
名称、附件、SHA-256、测试结果、签名状态、已知问题和回滚方式。GitHub
Release、CHANGELOG 和此目录中的版本信息必须一致。
```

- [ ] **Step 6: Create `docs/licenses/README.md`**

```markdown
# 第三方许可证

此目录用于保存 ClickGit 发布包实际分发组件的许可证原文和清单。

Windows 清单必须覆盖 Python、PySide6/Qt、Shiboken6、PortableGit、Git
Credential Manager 以及 PortableGit 中随包分发的依赖。macOS 清单必须覆盖
应用包内的 Python、PySide6/Qt 和 Shiboken6。每次升级依赖后重新生成清单，
不得仅沿用旧版本声明。
```

- [ ] **Step 7: Run the structure test**

Run:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest `
  tests.test_project_metadata.ProjectMetadataTests.test_documentation_directories_are_tracked `
  -v
```

Expected:

```text
Ran 1 test
OK
```

- [ ] **Step 8: Commit the documentation structure**

```powershell
git add docs/images/README.md docs/development/README.md `
  docs/releases/README.md docs/licenses/README.md `
  tests/test_project_metadata.py
git commit -m "docs: establish product documentation structure"
```

### Task 4: Rewrite README as a product entry point

**Files:**
- Modify: `README.md`
- Modify: `tests/test_project_metadata.py`
- Test: `tests/test_project_metadata.py`

- [ ] **Step 1: Add a failing README contract test**

Add this method to `ProjectMetadataTests`:

```python
    def test_readme_contains_product_sections(self) -> None:
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        required_sections = (
            "## 下载",
            "## 快速开始",
            "## 功能矩阵",
            "## 安全与恢复",
            "## 数据与隐私",
            "## 开发与测试",
            "## 项目结构",
            "## 发布",
            "## 许可证",
        )

        for section in required_sections:
            with self.subTest(section=section):
                self.assertIn(section, readme)

        self.assertIn("windows-v0.1.0", readme)
        self.assertIn("mac-v0.1.0", readme)
        self.assertIn("MIT", readme)
```

- [ ] **Step 2: Run the README test and verify it fails**

Run:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest `
  tests.test_project_metadata.ProjectMetadataTests.test_readme_contains_product_sections `
  -v
```

Expected:

```text
FAIL
AssertionError: '## 快速开始' not found
```

- [ ] **Step 3: Replace `README.md`**

Use this complete content:

```markdown
# ClickGit

[![Release ClickGit](https://github.com/ljy-codes/clickgit-desktop/actions/workflows/release.yml/badge.svg)](https://github.com/ljy-codes/clickgit-desktop/actions/workflows/release.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platforms](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-blue.svg)](#下载)

ClickGit 是面向完全不使用 Git 命令行用户的 Windows 和 macOS 桌面 Git
客户端。仓库、提交、同步、分支、冲突和恢复操作均通过按钮、列表和对话框
完成。

## 下载

当前版本为 `v0.1.0`，Windows 和 macOS 分别发布：

- `windows-v0.1.0`
  - `ClickGit-Windows-x64.zip`
- `mac-v0.1.0`
  - `ClickGit-macOS-arm64.zip`：Apple Silicon
  - `ClickGit-macOS-x64.zip`：Intel Mac

Windows 便携版包含 PortableGit，不要求安装 Git、Python 或 Qt。macOS 版本
包含应用运行环境，但需要系统 Git。

## 快速开始

### Windows

1. 下载并解压 `ClickGit-Windows-x64.zip`。
2. 保留完整的 `ClickGit` 目录。
3. 双击 `ClickGit.exe`。
4. 点击“打开仓库”“克隆”或“新建仓库”。
5. 勾选文件并点击“暂存”。
6. 输入提交说明并点击“提交暂存内容”。
7. 使用“获取”“拉取”和“推送”同步远程仓库。

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

Windows 构建和验证：

```powershell
.\scripts\download-portable-git.ps1
.\scripts\build.ps1
.\scripts\verify-package.ps1
```

macOS 构建：

```bash
python3 -m pip install -r requirements-dev.txt
scripts/build-macos.sh
```

## 项目结构

```text
artifacts/   本地和 CI 生成的构建产物
docs/        设计、开发、许可证和发布记录
installer/   PyInstaller 和后续安装器配置
runtime/     Windows PortableGit 运行时
scripts/     构建、验证和运行时准备脚本
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

版本变化记录在 [CHANGELOG.md](CHANGELOG.md)，详细发布记录保存在
`docs/releases`。

## 已知限制

- Windows 应用尚未代码签名，SmartScreen 可能显示未知发布者。
- macOS 应用尚未签名和公证，Gatekeeper 可能阻止首次直接启动。
- 超大仓库的历史记录当前最多加载 200 条。
- 文本冲突编辑器按 UTF-8 保存，二进制冲突需要外部工具处理。

## 许可证

ClickGit 源码采用 [MIT License](LICENSE)。发布包包含的第三方组件继续遵循
各自许可证，详见 [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt) 和
`docs/licenses`。
```

- [ ] **Step 4: Run the README contract test**

Run:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest `
  tests.test_project_metadata.ProjectMetadataTests.test_readme_contains_product_sections `
  -v
```

Expected:

```text
Ran 1 test
OK
```

- [ ] **Step 5: Commit the product README**

```powershell
git add README.md tests/test_project_metadata.py
git commit -m "docs: productize project readme"
```

### Task 5: Record the verified product baseline

**Files:**
- Create: `docs/development/2026-09-04-product-baseline.md`
- Test: full automated test suite

- [ ] **Step 1: Run the complete test suite**

Run in a normal Windows permission environment:

```powershell
$env:PYTHONPATH = "src"
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
```

Expected:

```text
Ran 70 tests
OK
```

There are 65 existing tests and five new metadata tests. If the count is not 70,
inspect discovery output before creating the baseline report.

- [ ] **Step 2: Verify the development entry point**

Run:

```powershell
$Report = "artifacts\reports\product-baseline-smoke.json"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Report) | Out-Null
$env:PYTHONPATH = "src"
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m clickgit --smoke-test $Report
Get-Content -LiteralPath $Report -Encoding UTF8 -Raw
```

Expected:

- Process exit code is `0`.
- JSON contains `"gui_started": true`.
- JSON contains `"git_returncode": 0`.
- `git_executable` is an absolute path.

- [ ] **Step 3: Create the baseline report**

Create `docs/development/2026-09-04-product-baseline.md`:

```markdown
# ClickGit 产品化改造基线

**日期：** 2026-09-04
**平台：** Windows
**Python：** 3.14.2
**Git：** 2.54.0.windows.1
**目标分支：** `main`

## 改造前状态

- 自动化测试：65 项通过，耗时 59.659 秒。
- 主窗口：`src/clickgit/ui/main_window.py`，约 1557 行。
- 应用控制器：`src/clickgit/app.py`，约 633 行。
- 仓库服务：`src/clickgit/repository.py`，约 845 行。
- Windows 交付：展开后的 `ClickGit` 目录和 `ClickGit.zip`。
- Windows ZIP 大小：242925095 字节。
- 展开目录文件数量：9789。

## 第一阶段验证

- 项目元数据测试：5 项通过。
- 全部自动化测试：70 项通过。
- 开发入口冒烟：通过。
- Git 诊断：通过。
- 业务源码：未修改。
- 用户配置格式：未修改。
- 发布工作流语义：未修改。

## 环境说明

受限沙箱可能拒绝 Python 临时目录的子进程和清理操作，表现为
`PermissionError: [WinError 5]`。本报告结果来自正常 Windows 权限环境，
环境权限错误不计为项目回归。

## 下一阶段

进入领域模型与 Git 基础设施边界改造。开始前重新确认工作区干净，并以本
报告中的 70 项测试作为最低回归门禁。
```

- [ ] **Step 4: Validate the report facts**

Run:

```powershell
Select-String -LiteralPath `
  "docs\development\2026-09-04-product-baseline.md" `
  -Pattern "70 项通过","业务源码：未修改","用户配置格式：未修改"
```

Expected: three matching lines.

- [ ] **Step 5: Commit the verified baseline report**

```powershell
git add docs/development/2026-09-04-product-baseline.md
git commit -m "docs: record product baseline verification"
```

### Task 6: Create the outer progress record

**Files:**
- Create: `D:\专用工具\git工具\进度.md`
- Modify: `D:\专用工具\git工具\文件夹说明.txt`
- Test: manual content and path verification

The outer files are not inside the Git repository and must not be included in a
repository commit.

- [ ] **Step 1: Create `D:\专用工具\git工具\进度.md`**

```markdown
# ClickGit 改造进度

**更新日期：** 2026-09-04
**当前阶段：** 第一阶段 - 产品基线
**分支：** `main`

## 已确认事实

- 项目采用 Python、PySide6、PortableGit 和 PyInstaller。
- 支持 Windows 和 macOS。
- Windows 和 macOS 使用两个独立 GitHub Release。
- 当前业务基线包含 65 项自动化测试。
- 改造采用渐进方式，不重写技术栈。

## 已修改文件

- `LICENSE`
- `CHANGELOG.md`
- `THIRD-PARTY-NOTICES.txt`
- `pyproject.toml`
- `README.md`
- `tests/test_project_metadata.py`
- `docs/images/README.md`
- `docs/development/README.md`
- `docs/development/2026-09-04-product-baseline.md`
- `docs/releases/README.md`
- `docs/releases/2026-07-28-v0.1.0.md`
- `docs/licenses/README.md`

## 当前方案

- 采用 MIT 开源许可证。
- 建立产品文档、测试报告、许可证和发布记录目录。
- 保持源码、配置、打包入口和 Release 语义不变。
- 后续按领域与基础设施、Application、UI、功能、交付五个子计划实施。

## 验证结果

- 项目元数据测试：5 项通过。
- 全部自动化测试：70 项通过。
- 开发入口冒烟：通过。

## 兼容性

- 未修改 Git 操作行为。
- 未修改配置目录和 `settings.json` 格式。
- 未修改 Windows PortableGit 和 macOS 系统 Git 选择逻辑。
- 未修改 v0.1.0 发布文件。

## 风险点

- 后续直接在 `main` 拆分大文件，需要保持小提交和完整回归。
- macOS 打包必须继续在真实 macOS Runner 验证。
- 第三方许可证清单需要在最终安装包阶段按实际产物复核。

## 未完成事项

- 领域模型与 Git 基础设施边界。
- Application 用例与后台任务编排。
- 三栏工作台 UI。
- Git 功能整理和危险操作体验。
- Windows/macOS 安装包、使用文档和正式 Release。

## 下一步

编写并执行“领域模型与 Git 基础设施边界”实施计划。
```

- [ ] **Step 2: Replace `文件夹说明.txt` with the explicit directory contract**

```text
开发空间
--------
保存 Git 仓库、源码、测试、构建脚本、安装器配置和工程文档。
开发过程产生的中间文件统一放入 开发空间\artifacts，不放入交付产品。

交付产品
--------
只保存最终用户直接使用的安装包、便携包、使用说明、安装说明和 SHA-256
校验文件。不得放入源码、虚拟环境、构建缓存或测试报告。

进度.md
---------
记录当前实施阶段、已修改文件、验证结果、兼容性、风险、未完成事项和下一步。
```

- [ ] **Step 3: Verify the outer structure**

Run:

```powershell
Get-ChildItem -Force -LiteralPath "D:\专用工具\git工具" |
  Select-Object Name,Mode
Get-Content -LiteralPath "D:\专用工具\git工具\进度.md" -Encoding UTF8
Get-Content -LiteralPath "D:\专用工具\git工具\文件夹说明.txt" -Encoding UTF8
```

Expected:

- `开发空间` and `交付产品` remain directories.
- `进度.md` and `文件夹说明.txt` are readable.
- No source or build directories are moved at this stage.

### Task 7: Run final gates and confirm a clean main branch

**Files:**
- Verify only; no planned source edits
- Test: all tests, smoke test, metadata consistency and Git diff

- [ ] **Step 1: Run metadata tests**

Run:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest tests.test_project_metadata -v
```

Expected:

```text
Ran 5 tests
OK
```

- [ ] **Step 2: Run all automated tests**

Run:

```powershell
$env:PYTHONPATH = "src"
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
```

Expected:

```text
Ran 70 tests
OK
```

- [ ] **Step 3: Check formatting and unintended changes**

Run:

```powershell
git diff --check
git status --short
git diff --name-only HEAD~5..HEAD
```

Expected:

- `git diff --check` produces no output.
- `git status --short` produces no output.
- The five phase commits contain only metadata, tests and documentation files.
- No file under `src/clickgit` changed.

- [ ] **Step 4: Inspect the phase history**

Run:

```powershell
git log -5 --oneline
```

Expected commit subjects, newest first:

```text
docs: record product baseline verification
docs: productize project readme
docs: establish product documentation structure
docs: add release and dependency records
docs: adopt MIT license
```

- [ ] **Step 5: Update the progress record with actual commit hashes**

Append a `## 阶段提交` section to
`D:\专用工具\git工具\进度.md`, listing the five actual hashes and subjects from
`git log -5 --oneline`. Do not invent hashes in advance.

- [ ] **Step 6: Stop before pushing**

Report:

- Modified files.
- Why each group changed.
- Compatibility result.
- Exact test and smoke results.
- Remaining risks.
- `main` ahead/behind status.

Do not push to GitHub until the user approves the completed phase or the active
execution request explicitly includes synchronization.

## Compatibility Checklist

- [ ] No files under `src/clickgit` changed.
- [ ] `clickgit = "clickgit.__main__:main"` remains unchanged.
- [ ] Version remains `0.1.0`.
- [ ] `%APPDATA%\ClickGit` behavior remains unchanged.
- [ ] `~/Library/Application Support/ClickGit` behavior remains unchanged.
- [ ] PortableGit lookup remains unchanged.
- [ ] macOS system Git lookup remains unchanged.
- [ ] `release-v*`, `windows-v*` and `mac-v*` tag behavior remains unchanged.
- [ ] Existing Windows and macOS release files are not deleted or overwritten.

## Risks

- MIT applies to ClickGit source code, not to third-party components.
- `THIRD-PARTY-NOTICES.txt` is an inventory baseline, not a substitute for
  preserving complete third-party license files in final installers.
- README badges depend on GitHub Actions and the public repository path.
- The baseline test count changes from 65 to 70 only because five metadata tests
  are added; a different count requires investigation.
- Direct work on `main` is controlled through small commits and a full test gate,
  but it still has a larger blast radius than an isolated worktree.
