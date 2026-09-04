# ClickGit 完整产品化改造设计

**日期：** 2026-09-04
**状态：** 已确认
**实施方式：** 直接在 `main` 分支渐进实施
**参考项目：** `D:\专用工具\图批处理`
**目标项目：** `D:\专用工具\git工具\开发空间`

## 1. 结论

ClickGit 采用“渐进式完整产品化”方案：

- 保留 Python、PySide6、PortableGit、PyInstaller 和现有跨平台能力。
- 不进行技术栈重写，不照搬参考项目的 .NET 实现。
- 参考“图批处理”的目录规范、工作台布局、文档体系、测试体系和交付方式。
- 先固化现有行为，再拆分职责和改造界面，最后分批完善 Git 操作体验。
- Windows 和 macOS 保持两个独立 GitHub Release。

本次改造不是重新开发 Git 功能。当前项目已经包含仓库、提交、同步、分支、
标签、贮藏、冲突、恢复、Worktree、子模块和 Git LFS 等能力，主要问题是
职责集中、界面信息架构不统一、工程文档和安装交付不够产品化。

## 2. 已确认事实

### 2.1 当前外层目录

```text
D:\专用工具\git工具\
├─ 开发空间\
├─ 交付产品\
└─ 文件夹说明.txt
```

当前 `交付产品` 保存了解压后的 Windows 便携目录和 `ClickGit.zip`。大量
PortableGit、Python 和 Qt 运行文件直接展开在交付目录中，用户可用，但缺少
安装包、平台分区、图文说明和统一校验清单。

### 2.2 当前代码结构

当前主要职责集中在以下文件：

- `src/clickgit/ui/main_window.py`：约 1557 行，承担界面构建、事件处理和大量
  状态刷新。
- `src/clickgit/app.py`：约 633 行，承担应用编排、任务和部分状态模型。
- `src/clickgit/repository.py`：约 845 行，集中实现大部分 Git 仓库操作。
- `src/clickgit/git_runner.py`：执行 Git 子进程并返回结果。
- `src/clickgit/settings.py`、`recovery.py`、`credentials.py`：分别处理配置、
  恢复和认证。

当前调用链大致为：

```text
MainWindow
    -> AppController
        -> Repository
            -> GitRunner
                -> PortableGit / system git
```

该调用链方向基本正确，但各层边界不够明确，`MainWindow`、`AppController`
和 `Repository` 的职责持续膨胀。

### 2.3 当前平台和数据兼容约束

- Windows 优先使用发行目录内的 PortableGit。
- macOS 使用系统 `git` 和 `ssh-keygen`。
- Windows 配置目录为 `%APPDATA%\ClickGit`。
- macOS 配置目录为 `~/Library/Application Support/ClickGit`。
- 当前发布使用 Windows 和 macOS 两个独立 Release。
- 配置、恢复记录、最近仓库和已有凭据行为必须继续兼容。

## 3. 改造目标

### 3.1 用户目标

面向完全不使用 Git 命令行、只会点击操作的用户，形成统一、可预测的操作
工作台。用户无需理解 Git 参数和终端输出，也能完成日常操作并处理失败。

### 3.2 工程目标

- UI、应用用例、领域模型和基础设施形成清晰依赖方向。
- 大文件按业务职责拆分，而不是按代码类型机械拆分。
- 测试目录与源码职责对应。
- 构建中间产物、发布产物和最终交付严格分离。
- 文档、测试报告、发布说明和许可证可随版本追踪。
- Windows 和 macOS 形成可重复、可核验的发布流程。

### 3.3 非目标

- 不将项目迁移到 .NET、Electron、Tauri 或其他技术栈。
- 不一次性重写全部现有代码。
- 不在结构调整阶段改变 Git 操作语义。
- 不改变用户配置目录或强制清除旧配置。
- 不在没有恢复保护的情况下增加硬回退、强制推送等危险入口。

## 4. 目标目录

外层目录保持简洁，并增加阶段进度记录：

```text
D:\专用工具\git工具\
├─ 开发空间\
├─ 交付产品\
├─ 进度.md
└─ 文件夹说明.txt
```

开发目录目标结构：

```text
开发空间\
├─ .github\
│  └─ workflows\
├─ artifacts\
│  ├─ build\
│  ├─ publish\
│  ├─ installer\
│  ├─ package\
│  └─ reports\
├─ docs\
│  ├─ images\
│  ├─ development\
│  ├─ releases\
│  ├─ licenses\
│  └─ superpowers\
│     ├─ specs\
│     └─ plans\
├─ installer\
│  ├─ windows\
│  └─ macos\
├─ scripts\
│  ├─ build\
│  ├─ test\
│  ├─ publish\
│  └─ package\
├─ src\
│  └─ clickgit\
│     ├─ ui\
│     ├─ application\
│     ├─ domain\
│     └─ infrastructure\
├─ tests\
│  ├─ ui\
│  ├─ application\
│  ├─ domain\
│  └─ infrastructure\
├─ CHANGELOG.md
├─ LICENSE
├─ README.md
└─ THIRD-PARTY-NOTICES.txt
```

约束：

- `artifacts` 可以整体清理和重新生成。
- `交付产品` 不保存构建缓存、测试缓存或源码。
- `.venv`、`__pycache__`、`.pytest_cache` 不进入版本库和交付目录。
- 文档中的截图、测试报告和发布记录按版本管理。

## 5. 四层架构

### 5.1 UI 层

职责：

- Qt 窗口、组件、对话框和视图状态。
- 将点击行为转换为应用请求。
- 展示结构化结果、业务错误和后台任务状态。
- 不直接拼装或执行 Git 命令。

建议模块：

```text
ui\
├─ main_window.py
├─ workspace\
├─ history\
├─ branches\
├─ conflicts\
├─ recovery\
├─ settings\
└─ shared\
```

### 5.2 Application 层

职责：

- 组织打开仓库、刷新、提交、同步、分支和恢复等完整用例。
- 管理同一仓库写操作串行化。
- 执行前置校验、危险操作保护、进度、取消和错误映射。
- 返回 UI 可直接使用的视图数据，不依赖 Qt 控件。

建议用例：

- `OpenRepositoryUseCase`
- `RefreshWorkspaceUseCase`
- `CommitChangesUseCase`
- `SyncRepositoryUseCase`
- `ManageBranchUseCase`
- `ResolveConflictUseCase`
- `RestoreOperationUseCase`

### 5.3 Domain 层

职责：

- 仓库、分支、提交、文件变化、冲突和恢复点等领域模型。
- Git 状态和危险级别规则。
- 不依赖 Qt、`subprocess`、文件对话框或具体操作系统。

建议模型：

- `RepositoryState`
- `WorkingTreeChange`
- `BranchInfo`
- `CommitInfo`
- `ConflictState`
- `OperationRisk`
- `RecoveryPoint`

### 5.4 Infrastructure 层

职责：

- Git 命令执行和机器可读输出解析。
- PortableGit、系统 Git、SSH 和凭据适配。
- 配置存储、日志、恢复文件和平台路径。
- Windows/macOS 构建与运行差异。

建议模块：

```text
infrastructure\
├─ git\
│  ├─ runner.py
│  ├─ repository_gateway.py
│  ├─ parsers.py
│  └─ errors.py
├─ credentials\
├─ persistence\
├─ recovery\
└─ platform\
```

### 5.5 依赖方向

```text
UI -> Application -> Domain
          |
          v
   Infrastructure
```

`Domain` 不反向依赖其他层。`Application` 通过接口使用基础设施，实现可测试
替换。基础设施可以依赖领域数据类型，但不得依赖 UI。

## 6. 渐进迁移策略

目录调整必须通过兼容层逐步完成：

1. 为现有公共行为补充特征测试。
2. 先抽取纯数据模型和错误类型，不改变入口导入。
3. 新建应用用例，并让 `AppController` 委托到新用例。
4. 拆分 `Repository`，保留原类作为兼容门面。
5. 拆分 `MainWindow` 的面板和动作控制器。
6. 更新内部导入、测试和打包配置。
7. 所有调用迁移完成后再删除兼容导出。

在一个阶段内不得同时大规模移动 UI、Git 执行和打包入口。每次提交只完成
一个可验证边界，保证 `main` 始终可运行。

## 7. 主界面设计

主界面采用面向操作的三栏工作台：

### 7.1 顶部仓库栏

- 打开、克隆、初始化和切换仓库。
- 展示当前仓库、路径和当前分支。
- 提供获取、拉取、推送和更多操作。
- 展示后台任务状态，不因网络操作冻结窗口。

### 7.2 左侧变更区

- 未暂存、已暂存、冲突和忽略文件分组。
- 支持勾选、全选、暂存、取消暂存和撤销。
- 文件状态同时使用文字/符号和颜色表达。
- 保持固定宽度范围，内容变化不能推动整体布局跳动。

### 7.3 中央工作区

- 差异对比。
- 提交历史。
- 分支图。
- 冲突编辑器。

工作区通过标签页切换，避免把所有功能堆叠在一个页面。差异视图优先展示
文件内容，工具栏保持紧凑。

### 7.4 右侧操作区

- 根据当前场景展示提交、分支、标签、合并或冲突操作。
- 只保留一个高强调主操作。
- 危险操作不与普通操作同级展示。
- 小屏或窄窗口允许收起，不影响主工作区。

### 7.5 底部状态栏

- Git 可用状态和实际 Git 来源。
- 远程连接状态。
- 当前分支领先/落后数量。
- 最后刷新时间、后台任务和失败入口。

### 7.6 视觉规范

- 采用安静、紧凑、工作型桌面风格，不制作宣传型首页。
- 卡片圆角不超过 8px，页面区域不使用层层嵌套卡片。
- 图标优先使用现有 Qt 图标体系或统一图标库。
- 命令按钮使用图标或图标加文字，危险操作使用明确警示。
- 支持浅色和深色主题，并遵循 Windows/macOS 字体差异。
- 关键文字在常用桌面分辨率和窄窗口下不得截断或重叠。

## 8. 功能整理与补齐

### 8.1 第一批：高频工作流

- 打开、克隆和初始化仓库。
- 文件状态、差异、暂存、取消暂存、丢弃修改和提交。
- 获取、拉取、推送和领先/落后状态。
- 失败后的中文处理建议。

第一批以整理现有功能、统一交互和提高可发现性为主。

### 8.2 第二批：分支和冲突

- 分支新建、切换、重命名、删除和合并。
- 合并、变基、挑选和应用贮藏产生的冲突处理。
- 操作继续、放弃和恢复入口。

### 8.3 第三批：高级操作

- 变基、拣选、贮藏、标签和提交回退。
- Reflog、补丁导入导出和仓库维护。
- 强制推送只允许使用租约保护作为默认方式。

### 8.4 第四批：扩展能力

- 多远程仓库。
- Worktree。
- 子模块。
- Git LFS 检测和操作引导。

每一批都先验证已有实现，再决定是迁移、修复还是补齐，不重复实现已经稳定
工作的能力。

## 9. 操作、安全和错误设计

### 9.1 操作流程

```text
用户点击
  -> UI 生成类型化请求
  -> Application 校验仓库状态和操作风险
  -> 必要时创建恢复点
  -> Infrastructure 执行参数数组形式的 Git 命令
  -> 解析成结构化结果
  -> Application 刷新仓库快照
  -> UI 展示结果或解决建议
```

### 9.2 后台任务

- 同一仓库的提交、拉取、合并、变基等写操作必须串行。
- 读取状态可以并发，但重复刷新需要合并。
- 网络任务显示进度并允许取消；取消后重新检查仓库状态。
- 写操作进行时禁用冲突动作，避免重复点击。

### 9.3 危险操作

- 硬回退、删除分支、清理和强制推送执行前展示影响清单。
- 提交图变更前创建隐藏恢复引用。
- 工作区覆盖前创建快照或隔离文件。
- 强制推送默认使用 `--force-with-lease` 语义。
- 二次确认按钮必须直接说明结果，不能只显示“确定”。

### 9.4 错误展示

- 普通区域展示中文原因、影响和下一步动作。
- 原始 Git 输出放在可展开的技术详情中。
- URL 密码、令牌、认证头和私钥路径按现有规则脱敏。
- 日志必须包含操作类型、仓库和耗时，但不能记录敏感凭据。

## 10. 构建和交付

### 10.1 构建产物

```text
artifacts\
├─ build\       # PyInstaller 等中间文件
├─ publish\     # 可运行目录或 .app
├─ installer\   # 安装包和 dmg
├─ package\     # zip 等发布压缩包
└─ reports\     # 测试、体积、清单和校验报告
```

### 10.2 最终交付

```text
交付产品\
├─ ClickGit-Windows\
│  ├─ ClickGit-Setup-x64.exe
│  ├─ ClickGit-Portable-x64.zip
│  ├─ 安装说明.html
│  └─ 使用说明.html
├─ ClickGit-macOS\
│  ├─ ClickGit-macOS-arm64.dmg
│  ├─ ClickGit-macOS-x64.dmg
│  ├─ 安装说明.html
│  └─ 使用说明.html
└─ SHA256SUMS.txt
```

正式实施时，若当前 CI 环境暂时无法生成签名 DMG，可以先保留 ZIP 作为兼容
产物，但目标交付格式仍为 DMG。

### 10.3 GitHub Releases

- Windows 和 macOS 继续使用两个独立 Release。
- Windows Release 包含安装版和便携版。
- macOS Release 包含 arm64 和 x64 版本。
- Release 附带版本说明、测试结果、已知问题和 SHA-256。
- 所有平台构建和测试成功后才允许发布，避免出现附件不完整的 Release。

### 10.4 签名和公证

- 未签名版本必须在安装说明和 Release 中明确 SmartScreen/Gatekeeper 风险。
- Windows 预留 Authenticode 签名步骤。
- macOS 预留 Developer ID 签名、Hardened Runtime 和公证步骤。
- 签名证书和密钥只通过 CI Secret 注入，不进入仓库。

## 11. 文档体系

### 11.1 根目录文档

- `README.md`：下载、截图、快速开始、功能矩阵、环境、构建和安全说明。
- `CHANGELOG.md`：按版本记录新增、修复、变化和已知问题。
- `LICENSE`：项目许可证。
- `THIRD-PARTY-NOTICES.txt`：PySide6、Qt、PortableGit 等第三方声明。

### 11.2 docs

- `docs/images`：主界面、安装、冲突处理和恢复中心截图。
- `docs/development`：测试报告、构建报告和技术说明。
- `docs/releases`：每个版本的发布说明、测试报告和已知问题。
- `docs/licenses`：第三方许可证原文。
- `docs/superpowers/specs`：确认后的设计。
- `docs/superpowers/plans`：可执行实施计划。

### 11.3 外层进度

`D:\专用工具\git工具\进度.md` 记录：

- 已确认事实。
- 已修改文件。
- 当前实施阶段。
- 测试和打包结果。
- 兼容性说明。
- 风险和未完成事项。
- 下一步计划。

## 12. 测试和质量门禁

### 12.1 测试分层

- `tests/domain`：纯规则和数据模型测试。
- `tests/application`：使用伪基础设施验证用例、风险和错误映射。
- `tests/infrastructure`：Git 临时仓库、解析器、配置、恢复和平台适配。
- `tests/ui`：关键控件、信号、状态刷新和高频点击流程。

### 12.2 必测流程

- 打开、初始化和克隆仓库。
- 修改、暂存、取消暂存、提交。
- 获取、拉取、推送和非快进错误。
- 分支新建、切换、合并和冲突。
- 变基、挑选、贮藏和继续/放弃。
- 回退、清理和恢复点。
- 中文路径、空格路径和长文件名。
- Windows/macOS 配置目录和 Git 定位。

### 12.3 发布门禁

- 单元测试和集成测试全部通过。
- UI 冒烟测试通过。
- Windows 和 macOS 各自在真实 Runner 完成打包后启动测试。
- 旧配置迁移测试通过。
- 安装、卸载和便携版启动验证通过。
- 交付清单与 SHA-256 校验一致。
- README、CHANGELOG、发布说明和版本号一致。

## 13. 兼容性

### 13.1 必须保持

- `python -m clickgit` 开发入口继续可用，或提供等价兼容入口。
- PyInstaller 入口在迁移期间继续解析旧模块路径。
- Windows PortableGit 优先级保持。
- macOS 系统 Git 行为保持。
- 现有 `settings.json` 和恢复记录可直接读取。
- 已有 Git 仓库不需要迁移或重新克隆。

### 13.2 允许变化

- 主窗口布局和功能入口位置调整。
- 内部 Python 模块路径调整，但通过兼容导出过渡。
- 构建脚本移动到分类目录，但根目录保留短入口或明确迁移说明。
- 最终交付从展开目录改为安装包和压缩包。

## 14. 实施阶段

### 阶段 1：基线和产品文档

- 补充特征测试和当前结构清单。
- 增加 `进度.md`、CHANGELOG、LICENSE 和第三方声明。
- 建立 docs、artifacts、installer 和 scripts 目标目录。
- 整理 README 和产品截图要求。

退出标准：现有测试通过，运行入口和发布行为不变。

### 阶段 2：领域与基础设施边界

- 抽取领域模型、Git 错误和仓库网关。
- 迁移 runner、parser、settings、credentials、recovery 和 platform。
- 保留旧模块兼容导出。

退出标准：主要 Git 集成测试通过，打包入口不变。

### 阶段 3：应用用例和任务编排

- 将 `AppController` 拆分为高频用例。
- 明确读写任务、取消、刷新合并和错误映射。
- 建立危险操作策略和恢复策略。

退出标准：用例测试覆盖高频和危险操作。

### 阶段 4：工作台 UI

- 拆分左侧变更区、中央工作区、右侧操作区和底部状态栏。
- 建立统一动作状态和选择状态。
- 完成浅色/深色和窄窗口检查。

退出标准：高频点击流程和 UI 冒烟测试通过。

### 阶段 5：功能整理与补齐

- 按高频、分支冲突、高级、扩展四批验证和完善功能。
- 对每个危险操作增加预览、恢复和错误处理。

退出标准：功能矩阵和测试矩阵一致。

### 阶段 6：安装、交付和发布

- Windows 安装包和便携包。
- macOS arm64/x64 DMG 或兼容 ZIP。
- 图文安装说明、使用说明、校验清单和发布报告。
- 两个 GitHub Release 自动发布。

退出标准：真实平台打包冒烟通过，最终交付目录通过清单核验。

## 15. 风险和控制

| 风险 | 影响 | 控制方式 |
| --- | --- | --- |
| 主窗口拆分破坏 Qt 信号 | 操作无响应或重复执行 | 先补 UI 冒烟测试，逐面板迁移 |
| Repository 拆分改变 Git 参数 | 仓库状态或历史被错误修改 | 保留特征测试和兼容门面 |
| 多任务刷新覆盖新状态 | 界面显示过期数据 | 请求版本号、取消旧刷新、写操作串行 |
| 旧配置无法读取 | 最近仓库和设置丢失 | 版本化配置、迁移测试、原文件备份 |
| macOS 只在 Windows 验证 | 产物无法启动 | 使用真实 macOS Runner |
| 未签名安装包被拦截 | 用户无法直接启动 | 明确说明并规划签名、公证 |
| 交付目录包含中间文件 | 体积膨胀、用户困惑 | 最终清单白名单和自动校验 |
| 直接在 main 实施 | 阶段性回归影响主线 | 小提交、阶段门禁、每阶段可回滚 |

## 16. 预计修改范围

实施期间预计涉及：

- `src/clickgit`：新增四层目录并迁移现有职责。
- `tests`：按层整理并补充特征、集成和 UI 测试。
- `scripts`：分类构建、测试、发布和打包脚本。
- `installer`：Windows 安装器和 macOS 打包配置。
- `.github/workflows`：双平台测试和 Release。
- `README.md`、`CHANGELOG.md`、许可证和 docs。
- 外层 `进度.md` 和 `交付产品` 清单。

不会在单个提交中同时修改全部范围。每个阶段必须列出实际修改文件、兼容性、
验证结果和剩余风险。

## 17. 验收标准

产品化改造完成时必须满足：

- 用户无需输入 Git 命令即可完成 README 功能矩阵中的所有操作。
- 高频操作可以在主工作台直接找到，高级危险操作与普通操作隔离。
- Git 操作不会冻结界面，写操作不会并发破坏仓库。
- 错误提示提供中文原因和可执行处理入口。
- 源码、测试、脚本、文档、构建产物和最终交付边界清晰。
- Windows 和 macOS 都有可启动、可校验的正式产物。
- 旧配置、旧仓库和现有认证方式保持兼容。
- 自动化测试、打包冒烟和交付清单全部通过。
- GitHub 上的源码、标签、两个 Release 和本地交付内容一致。

## 18. 已确认决策

- 改造范围：完整产品化。
- 功能策略：分阶段整理和补齐。
- UI：三栏 Git 工作台。
- 架构：UI、Application、Domain、Infrastructure 四层。
- 技术栈：继续使用 Python 和 PySide6。
- 平台：Windows 和 macOS。
- 发布：两个独立 GitHub Release。
- 实施分支：直接使用 `main`。
