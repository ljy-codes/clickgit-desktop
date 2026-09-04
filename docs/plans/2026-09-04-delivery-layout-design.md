# ClickGit 交付目录产品化改造设计

日期：2026-09-04

## 1. 背景

当前 `交付产品\ClickGit` 是 PyInstaller 的展开式构建结果，包含 PySide6、
Python 扩展模块、DLL 和内置 PortableGit。该目录是程序运行所需内容，但不适合
直接面向只会点击操作的最终用户。

本次参考 `D:\专用工具\图批处理` 的目录职责，将开发文件、展开构建产物与最终
交付包分开管理。

## 2. 已确定方案

采用方案 A：

- Windows 同时提供安装版和 ZIP 便携版。
- macOS 按 CPU 架构提供应用 ZIP。
- 展开的构建产物只保存在 `开发空间\artifacts`。
- `交付产品` 只保存最终用户可以直接下载或运行的文件。
- 根目录提供 Windows 安装包副本和面向普通用户的说明文档。

不采用 PyInstaller 单文件模式。ClickGit 内置 PortableGit，单文件模式会导致
启动时解压大量文件，增加启动时间、临时磁盘占用和安全软件误报概率。

## 3. 目标目录

```text
D:\专用工具\git工具
├─开发空间
│  ├─src
│  ├─tests
│  ├─scripts
│  ├─installer
│  ├─docs
│  ├─runtime
│  └─artifacts
│     ├─build
│     ├─publish
│     ├─installer
│     └─package
├─交付产品
│  ├─ClickGit-Windows-x64-Setup.exe
│  ├─ClickGit-Windows-x64-Portable.zip
│  ├─ClickGit-macOS-arm64.zip
│  ├─ClickGit-macOS-x64.zip
│  └─SHA256SUMS.txt
├─ClickGit-安装包.exe
├─安装说明.html
├─产品介绍.html
├─进度.md
└─文件夹说明.txt
```

macOS 构建机只生成当前 CPU 架构对应的 ZIP，不伪造另一架构产物。两个架构的
文件在各自构建完成后汇总到 `交付产品`。

## 4. Windows 构建设计

### 4.1 展开式应用

继续使用 PyInstaller `onedir` 模式。应用目录调整为：

```text
ClickGit
├─ClickGit.exe
├─_internal
│  ├─PySide6
│  ├─Python DLL 和扩展模块
│  └─其他运行依赖
└─runtime
   └─git
```

`runtime\git` 保持应用根目录下的相对路径，避免改变现有 PortableGit 查找逻辑。
其他 Python 和 Qt 依赖统一放入 `_internal`。

### 4.2 安装包

新增 Inno Setup 配置，安装程序负责：

- 将完整 ClickGit 展开目录安装到当前用户程序目录。
- 创建开始菜单快捷方式。
- 可选创建桌面快捷方式。
- 提供卸载入口。
- 默认不要求管理员权限。
- 安装后可选择直接启动 ClickGit。

安装器输出：

```text
开发空间\artifacts\installer\ClickGit-Windows-x64-Setup.exe
```

### 4.3 便携包

将 `artifacts\publish\windows-x64\ClickGit` 压缩为：

```text
开发空间\artifacts\package\ClickGit-Windows-x64-Portable.zip
```

用户解压后只需双击 `ClickGit.exe`。

## 5. macOS 构建设计

保留现有 `.app` 打包方式和架构识别逻辑。构建结果先生成到：

```text
开发空间/artifacts/publish/macos/ClickGit.app
```

随后压缩为当前架构对应的：

```text
ClickGit-macOS-arm64.zip
ClickGit-macOS-x64.zip
```

macOS 版本不内置 Windows PortableGit，继续使用系统可用的 Git。

## 6. 发布流程

新增统一 Windows 发布脚本，顺序如下：

1. 运行完整自动化测试。
2. 准备 PortableGit。
3. 构建 Windows 展开式应用。
4. 验证 `ClickGit.exe`、内置 Git 和核心资源。
5. 生成便携 ZIP。
6. 检测 Inno Setup 并生成 Windows 安装包。
7. 计算所有最终产物的 SHA-256。
8. 将最终产物复制到 `交付产品`。
9. 将 Windows 安装包复制为根目录 `ClickGit-安装包.exe`。
10. 删除 `交付产品` 中旧的展开式 `ClickGit` 目录。

清理操作必须先解析绝对路径，并确认目标位于
`D:\专用工具\git工具\交付产品` 内，禁止使用通配符递归删除。

## 7. 文档设计

根目录新增：

- `安装说明.html`：Windows 安装、便携版、macOS 启动和常见问题。
- `产品介绍.html`：产品定位、主要功能、支持平台和截图区域。

第一阶段生成 HTML。PDF 仅在渲染工具可用并完成视觉校验后生成，不使用未验证
的 HTML 直接改扩展名。

## 8. 兼容性

- 不修改 Git 操作逻辑、界面工作流、仓库数据和用户配置格式。
- Windows 便携版仍支持直接运行。
- PortableGit 相对位置保持不变。
- macOS 应用包结构保持不变。
- GitHub 仓库源码仍以 `开发空间` 为仓库根目录，不提交构建产物。

## 9. 验证标准

- 全部自动化测试通过。
- Windows 展开式程序启动检查通过。
- 内置 `git.exe --version` 调用成功。
- Windows 安装包能够静默安装、启动和卸载。
- Windows 便携 ZIP 解压后可以启动。
- `交付产品` 中不存在 `.pyd`、DLL、PySide6 文件夹或展开式 `ClickGit` 目录。
- SHA-256 文件与实际发布物一致。
- macOS 构建脚本静态检查和现有验证脚本通过。
- `git status` 只包含本次有意修改。

## 10. 风险与回滚

### 风险

- 当前机器如果未安装 Inno Setup，无法生成 Windows 安装器。
- Windows 安装包未做代码签名，可能触发 SmartScreen 提示。
- macOS 产物需要在对应架构的 macOS 构建机生成。
- Qt、PySide6、PortableGit 等第三方组件的许可证文件需要随安装包保留。

### 回滚

- 构建和发布前不删除现有交付文件。
- 新产物全部验证成功后才替换 `交付产品`。
- 发布失败时保留 `开发空间\artifacts` 中的诊断结果，不修改已有交付包。
- 代码层面可回退本次构建脚本、安装器配置和文档提交，不影响用户仓库数据。
