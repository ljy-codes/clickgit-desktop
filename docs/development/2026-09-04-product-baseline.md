# ClickGit 产品化改造基线

**日期：** 2026-09-04
**平台：** Windows
**Python：** 3.14.2
**Git：** 2.54.0.windows.1
**目标分支：** `main`
**验证前 HEAD：** `562a0f8bb9c775c27e40a4a3f3bb959d493eec19`

## 改造前已确认基线

以下数据来自产品化改造计划编写前的正常 Windows 权限验证，不是本阶段重新
执行的结果：

- 自动化测试：65 项通过，耗时 59.659 秒。
- 主窗口：`src/clickgit/ui/main_window.py`，1557 行。
- 应用控制器：`src/clickgit/app.py`，633 行。
- 仓库服务：`src/clickgit/repository.py`，845 行。
- Windows ZIP：`D:\专用工具\git工具\交付产品\ClickGit.zip`。
- Windows ZIP 大小：242925095 字节。
- 展开交付目录：`D:\专用工具\git工具\交付产品\ClickGit`。
- 展开交付目录文件数量：9789。

源码行数、ZIP 大小和展开交付文件数量已在本阶段按当前目录重新采集，结果与
计划中的改造前记录一致。

## 本阶段实际验证

### 运行环境

```powershell
.\.venv\Scripts\python.exe --version
git --version
git rev-parse HEAD
```

结果：

```text
Python 3.14.2
git version 2.54.0.windows.1
562a0f8bb9c775c27e40a4a3f3bb959d493eec19
```

### 本地 Windows 交付物

执行：

```powershell
$ZipPath = "D:\专用工具\git工具\交付产品\ClickGit.zip"
$Delivery = "D:\专用工具\git工具\交付产品\ClickGit"
$ZipItem = Get-Item -LiteralPath $ZipPath
$ZipHash = Get-FileHash -LiteralPath $ZipPath -Algorithm SHA256
$FileCount = (
    Get-ChildItem -LiteralPath $Delivery -Recurse -File |
        Measure-Object
).Count

$ZipItem | Select-Object FullName, Length, LastWriteTime
$ZipHash | Select-Object Algorithm, Hash, Path
([DateTimeOffset]$ZipItem.LastWriteTime).ToString(
    "yyyy-MM-ddTHH:mm:ss.fffffffzzz"
)
$FileCount
git rev-parse windows-v0.1.0
```

实际采集结果：

- 准确路径：`D:\专用工具\git工具\交付产品\ClickGit.zip`。
- 文件大小：242925095 字节。
- 最后写入时间：`2026-09-02T15:40:58.6155552+08:00`。
- SHA-256：
  `7D942203669E263F70EE73DE8D03918F0580DCB19F2B943D43B7C9B5AD7208E4`。
- 展开目录文件数量：9789。
- 参考发布标签 `windows-v0.1.0` 指向提交
  `5128113329b589df380e9530e9fc0efcd8c9d330`。

本地没有可验证的生成链路证明该外部 ZIP 一定由 `windows-v0.1.0` 标签
构建，因此该标签只作为发布历史参考，不作为 ZIP 来源证明。

### 完整自动化测试

在正常 Windows 权限下执行：

```powershell
$env:PYTHONPATH = "src"
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
```

结果：

```text
Ran 70 tests in 65.673s
OK
```

- 项目元数据测试：5 项通过。
- 全部自动化测试：70 项通过。
- 未出现代码测试失败。

### 开发入口冒烟

执行：

```powershell
$Report = "artifacts\reports\product-baseline-smoke.json"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Report) | Out-Null
$env:PYTHONPATH = "src"
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m clickgit --smoke-test $Report
```

随后执行以下采集命令：

```powershell
$SmokeItem = Get-Item -LiteralPath $Report
$SmokeHash = Get-FileHash -LiteralPath $Report -Algorithm SHA256
$SmokeData = Get-Content -LiteralPath $Report -Encoding UTF8 -Raw |
    ConvertFrom-Json

$SmokeItem | Select-Object FullName, LastWriteTime
$SmokeHash | Select-Object Algorithm, Hash, Path
([DateTimeOffset]$SmokeItem.LastWriteTime).ToString(
    "yyyy-MM-ddTHH:mm:ss.fffffffzzz"
)
$SmokeData
.\.venv\Scripts\python.exe --version
[System.Environment]::OSVersion.VersionString
git check-ignore -v $Report
```

本次 smoke 验证信息：

- 本次执行时间（以 smoke JSON 最后写入时间记录）：
  `2026-09-04T12:14:29.9108926+08:00`。
- 被验证提交：
  `562a0f8bb9c775c27e40a4a3f3bb959d493eec19`。
- Python：`3.14.2`。
- 平台：Windows，`Microsoft Windows NT 10.0.26200.0`。
- 进程退出码：`0`。
- JSON SHA-256：
  `085A3DA5AF324EE7B28D0ED42B861A3B275559940773D4B105D92AC22983887B`。

验证产物 `artifacts/reports/product-baseline-smoke.json` 内容摘要：

```json
{
  "git_executable": "C:\\Program Files\\Git\\cmd\\git.exe",
  "git_version": "git version 2.54.0.windows.1",
  "git_returncode": 0,
  "gui_started": true
}
```

- `gui_started`：`true`。
- `git_returncode`：`0`。
- `git_executable`：绝对路径 `C:\Program Files\Git\cmd\git.exe`。
- 开发入口冒烟和 Git 诊断：通过。

该 JSON 由 `.gitignore` 中的 `artifacts/` 规则忽略，不提交到仓库。上述
SHA-256 用于将本报告与本次实际读取的 smoke JSON 对应，不改变应用输出格式，
也不把临时验证产物纳入版本控制。

## 兼容性结论

- 本阶段提交只新增和修订产品基线报告，未修改业务源码。
- 本阶段提交未修改用户配置格式和数据目录实现。
- 本阶段提交未修改仓库中的 `.github/workflows/release.yml` 发布工作流。
- 本阶段提交未修改 `installer` 下的打包入口。
- 未在线核验 GitHub Release 资产状态，不能据此判断远端附件是否存在或是否
  被覆盖。
- 本地只核验了已存在的 Windows ZIP 及其展开目录，未核验 macOS 发布文件。

## 环境限制

在受限沙箱中复跑使用临时 Git 仓库的集成测试：

```powershell
$env:PYTHONPATH = "src"
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m unittest `
  tests.test_repository.RepositoryIntegrationTests.test_stage_commit_branch_and_history `
  -v
```

关键错误：

```text
fatal: cannot mkdir ...\AppData\Local\Temp\...\repo: Permission denied
PermissionError: [WinError 5]
Ran 1 test in 0.118s
FAILED (errors=2)
```

错误发生在受限沙箱的 Windows 临时目录创建和清理阶段。正常 Windows 权限下
执行的完整 70 项测试和 smoke test 结果作为本阶段正式门禁；沙箱权限错误不
计为代码回归。

## 发布风险

- Qt/PySide6 许可证原文、Qt notices、适用开源许可证材料及必要的源代码提供
  信息，尚未按最终 Windows/macOS 安装包完成收集和验证。
- 当前许可证文档是治理基线，不能证明现有或后续发布包已经完成第三方许可
  合规验证。
- 正式发布前必须按最终产物重新盘点第三方组件并验证许可证材料；验证不完整
  时应阻断发布。

## 下一阶段

进入领域模型与 Git 基础设施边界改造。开始前重新确认工作区干净，并以本
报告中的 70 项测试作为最低回归门禁。
