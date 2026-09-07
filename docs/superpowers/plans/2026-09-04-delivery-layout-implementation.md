# ClickGit Packaged Delivery Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a clean ClickGit delivery directory containing a Windows installer, a Windows portable ZIP, macOS architecture ZIPs when available, checksums, and user-facing HTML documents without exposing expanded runtime dependencies.

**Architecture:** Keep PyInstaller in `onedir` mode and place Python/Qt support files under `_internal`. Copy PortableGit and license notices into the application root after PyInstaller completes, then package the verified directory with PowerShell and Inno Setup. A separate publish script stages verified outputs before replacing only known delivery files.

**Tech Stack:** Python 3.11+, PySide6, PyInstaller, PowerShell 7/Windows PowerShell, Inno Setup 6, GitHub Actions, `unittest`.

---

## File Structure

- Modify `installer/clickgit.spec`: move PyInstaller-managed dependencies under `_internal`.
- Create `installer/ClickGit.iss`: define the per-user Windows installer.
- Modify `scripts/build.ps1`: copy PortableGit and notices after PyInstaller completes.
- Create `scripts/package.ps1`: verify and package Windows installer and portable ZIP.
- Create `scripts/publish.ps1`: stage and copy final products into the outer delivery layout.
- Create `docs/user/安装说明.html`: source of the outer installation guide.
- Create `docs/user/产品介绍.html`: source of the outer product introduction.
- Modify `.github/workflows/release.yml`: build and release Windows installer plus portable ZIP.
- Modify `tests/test_release_configuration.py`: enforce the packaging and workflow contract.
- Modify `tests/test_project_metadata.py`: enforce user document presence and required content.
- Modify `README.md`: document installer and local publishing commands.
- Modify `CHANGELOG.md`: record the delivery layout change.
- Modify outer `文件夹说明.txt`: describe the new directory responsibilities.
- Modify outer `进度.md`: record implementation and verification results.

### Task 1: Lock The Packaging Contract With Tests

**Files:**
- Modify: `tests/test_release_configuration.py`
- Modify: `tests/test_project_metadata.py`

- [x] **Step 1: Add failing Windows layout assertions**

Add assertions that require:

```python
self.assertIn('contents_directory="_internal"', windows_spec)
self.assertNotIn('(str(runtime_git), "runtime/git")', windows_spec)
self.assertTrue((PROJECT_ROOT / "installer" / "ClickGit.iss").is_file())
self.assertTrue((PROJECT_ROOT / "scripts" / "package.ps1").is_file())
self.assertTrue((PROJECT_ROOT / "scripts" / "publish.ps1").is_file())
```

Also require the build script to contain:

```python
self.assertIn('Copy-Item -LiteralPath $GitRuntime', build_script)
self.assertIn('"runtime\\git"', build_script)
self.assertIn('"LICENSE"', build_script)
self.assertIn('"THIRD-PARTY-NOTICES.txt"', build_script)
```

- [x] **Step 2: Add failing installer and publishing assertions**

Read `installer/ClickGit.iss`, `scripts/package.ps1`, and
`scripts/publish.ps1`, then assert these exact contracts:

```python
self.assertIn("PrivilegesRequired=lowest", installer)
self.assertIn("ClickGit-Windows-x64-Setup", installer)
self.assertIn("recursesubdirs createallsubdirs", installer)
self.assertIn("ClickGit-Windows-x64-Portable.zip", package_script)
self.assertIn("scripts\\verify-package.ps1", package_script)
self.assertIn("SHA256SUMS.txt", publish_script)
self.assertIn("ClickGit-安装包.exe", publish_script)
self.assertIn("Assert-ChildPath", publish_script)
```

- [x] **Step 3: Add failing user-document assertions**

Require both HTML files and verify their user-facing sections:

```python
install_guide = (
    PROJECT_ROOT / "docs" / "user" / "安装说明.html"
).read_text(encoding="utf-8")
product_intro = (
    PROJECT_ROOT / "docs" / "user" / "产品介绍.html"
).read_text(encoding="utf-8")

self.assertIn("<title>ClickGit 安装说明</title>", install_guide)
self.assertIn("Windows 安装版", install_guide)
self.assertIn("Windows 便携版", install_guide)
self.assertIn("macOS", install_guide)
self.assertIn("<title>ClickGit 产品介绍</title>", product_intro)
self.assertIn("完全点击操作", product_intro)
```

- [x] **Step 4: Run focused tests and verify failure**

Run:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest `
  tests.test_release_configuration `
  tests.test_project_metadata -v
```

Expected: failure because the installer, packaging scripts, user documents,
and `_internal` contract do not exist yet.

- [x] **Step 5: Commit the failing tests**

```powershell
git add tests/test_release_configuration.py tests/test_project_metadata.py
git commit -m "test: define packaged delivery contract"
```

### Task 2: Build A Clean Windows Application Directory

**Files:**
- Modify: `installer/clickgit.spec`
- Modify: `scripts/build.ps1`

- [x] **Step 1: Configure PyInstaller support files**

Remove the PortableGit data entry from the spec and set:

```python
datas=[],
```

and:

```python
contents_directory="_internal",
```

- [x] **Step 2: Copy root-level runtime and notices after PyInstaller**

After a successful PyInstaller invocation, define the package root and copy
the required root-level files:

```powershell
$PackageRoot = Join-Path $ProjectRoot "artifacts\publish\windows-x64\ClickGit"
$PackageRuntime = Join-Path $PackageRoot "runtime\git"

New-Item -ItemType Directory -Force -Path (Split-Path $PackageRuntime) |
    Out-Null
Copy-Item -LiteralPath $GitExecutable.Parent.Parent `
    -Destination $PackageRuntime -Recurse -Force
Copy-Item -LiteralPath (Join-Path $ProjectRoot "LICENSE") `
    -Destination (Join-Path $PackageRoot "LICENSE") -Force
Copy-Item -LiteralPath (Join-Path $ProjectRoot "THIRD-PARTY-NOTICES.txt") `
    -Destination (Join-Path $PackageRoot "THIRD-PARTY-NOTICES.txt") -Force
```

Use a dedicated `$GitRuntime = Join-Path $ProjectRoot "runtime\git"` variable
so the copy source is explicit and testable.

- [x] **Step 3: Run focused release tests**

Run the release configuration test. Expected: `_internal` and build-copy
assertions pass; installer and publishing assertions still fail.

- [x] **Step 4: Build and verify the Windows directory**

Run:

```powershell
.\scripts\build.ps1
.\scripts\verify-package.ps1
```

Expected:

- `ClickGit.exe` exists at the package root.
- `_internal\PySide6` exists.
- `runtime\git\cmd\git.exe` exists.
- package smoke test reports `gui_started=true` and Git exit code `0`.

- [x] **Step 5: Commit the layout change**

```powershell
git add installer/clickgit.spec scripts/build.ps1
git commit -m "build: isolate Windows runtime dependencies"
```

### Task 3: Add Windows Installer And Packaging

**Files:**
- Create: `installer/ClickGit.iss`
- Create: `scripts/package.ps1`

- [x] **Step 1: Create the Inno Setup definition**

Define:

```ini
#define MyAppName "ClickGit"
#define MyAppPublisher "ljy-codes"
#define MyAppExeName "ClickGit.exe"

[Setup]
AppId={{F6FD5C54-1D99-4A6F-887F-61945AF02634}
AppName={#MyAppName}
DefaultDirName={localappdata}\Programs\ClickGit
PrivilegesRequired=lowest
OutputBaseFilename=ClickGit-Windows-x64-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "{#PublishDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\ClickGit"; Filename: "{app}\ClickGit.exe"
Name: "{autodesktop}\ClickGit"; Filename: "{app}\ClickGit.exe"; Tasks: desktopicon
```

Add Simplified Chinese language, optional desktop shortcut, uninstall entry,
and post-install launch.

- [x] **Step 2: Create the Windows packaging script**

The script must:

```powershell
param(
    [string]$Version = "0.1.0",
    [switch]$SkipBuild
)
```

It runs `build.ps1` unless skipped, always runs `verify-package.ps1`, creates
`artifacts\package\ClickGit-Windows-x64-Portable.zip`, locates `ISCC.exe`,
compiles `installer\ClickGit.iss` into a PID-specific staging directory, and
copies the verified installer to
`artifacts\installer\ClickGit-Windows-x64-Setup.exe`.

- [x] **Step 3: Run focused tests**

Run `tests.test_release_configuration`. Expected: installer and package
assertions pass; publishing and user-document assertions still fail.

- [x] **Step 4: Generate both Windows packages**

Run:

```powershell
.\scripts\package.ps1 -Version 0.1.0
```

Expected:

```text
artifacts\package\ClickGit-Windows-x64-Portable.zip
artifacts\installer\ClickGit-Windows-x64-Setup.exe
```

- [x] **Step 5: Commit the installer**

```powershell
git add installer/ClickGit.iss scripts/package.ps1
git commit -m "build: add Windows installer packaging"
```

### Task 4: Add User Documents And Safe Local Publishing

**Files:**
- Create: `docs/user/安装说明.html`
- Create: `docs/user/产品介绍.html`
- Create: `scripts/publish.ps1`

- [x] **Step 1: Create the installation guide**

Create a responsive UTF-8 HTML document with these visible sections:

```html
<h1>ClickGit 安装说明</h1>
<h2>Windows 安装版</h2>
<h2>Windows 便携版</h2>
<h2>macOS</h2>
<h2>首次使用</h2>
<h2>卸载与数据</h2>
```

State that Windows users should prefer the installer, portable users must
extract the complete ZIP, and macOS users must choose the matching CPU
architecture.

- [x] **Step 2: Create the product introduction**

Create a responsive UTF-8 HTML document containing:

```html
<h1>ClickGit</h1>
<p>为完全不使用 Git 命令行的用户设计的桌面 Git 工具。</p>
```

Describe click-only repository opening, cloning, committing, synchronizing,
branching, conflict handling, and recovery without marketing-only content.

- [x] **Step 3: Create the safe publish script**

Implement `Assert-ChildPath` using normalized absolute paths and
`StringComparison.OrdinalIgnoreCase`. Stage all outputs under
`artifacts\delivery-staging-$PID`, verify installer and ZIP presence, then:

```powershell
Copy-Item $Installer "$DeliveryRoot\ClickGit-Windows-x64-Setup.exe"
Copy-Item $Portable "$DeliveryRoot\ClickGit-Windows-x64-Portable.zip"
Copy-Item $Installer "$OuterRoot\ClickGit-安装包.exe"
Copy-Item "$ProjectRoot\docs\user\安装说明.html" $OuterRoot
Copy-Item "$ProjectRoot\docs\user\产品介绍.html" $OuterRoot
```

Preserve any valid macOS architecture ZIPs already present in
`artifacts\package` or `交付产品`. Remove only the known obsolete
`交付产品\ClickGit` directory and `交付产品\ClickGit.zip` after staging has
been validated. Generate `SHA256SUMS.txt` from final delivery files.

- [x] **Step 4: Run focused tests**

Run both metadata and release configuration test modules. Expected: all
focused tests pass.

- [x] **Step 5: Validate publishing in a temporary layout**

Run the Windows integration test with temporary `ProjectRoot` and
`OuterRoot` paths:

```powershell
.\.venv\Scripts\python.exe -m unittest `
  tests.test_release_configuration.ReleaseConfigurationTests.test_publish_script_replaces_delivery_safely -v
```

Expected: the temporary outer root contains the installer and two HTML
documents; its `交付产品` contains only packaged files and
`SHA256SUMS.txt`. The real outer delivery is replaced only in Task 7 after
full verification.

- [x] **Step 6: Commit publishing and documents**

```powershell
git add scripts/publish.ps1 docs/user
git commit -m "build: publish clean end-user deliverables"
```

### Task 5: Update GitHub Releases

**Files:**
- Modify: `.github/workflows/release.yml`
- Modify: `tests/test_release_configuration.py`

- [x] **Step 1: Update workflow assertions**

Require:

```python
self.assertIn("scripts/package.ps1", workflow)
self.assertIn("ClickGit-Windows-x64-Setup.exe", workflow)
self.assertIn("ClickGit-Windows-x64-Portable.zip", workflow)
self.assertNotIn("ClickGit-Windows-x64.zip", workflow)
```

- [x] **Step 2: Verify the updated assertions fail**

Run `tests.test_release_configuration`. Expected: failure on the old Windows
archive names.

- [x] **Step 3: Update the Windows job**

Install Inno Setup, run:

```powershell
scripts/package.ps1 -Version $env:RELEASE_VERSION
```

Upload both:

```text
artifacts/installer/ClickGit-Windows-x64-Setup.exe
artifacts/package/ClickGit-Windows-x64-Portable.zip
```

- [x] **Step 4: Update release asset handling**

Set:

```bash
WINDOWS_SETUP="release-assets/windows-x64/ClickGit-Windows-x64-Setup.exe"
WINDOWS_PORTABLE="release-assets/windows-x64/ClickGit-Windows-x64-Portable.zip"
```

Upload both assets to `windows-v${VERSION}` and leave the two macOS ZIPs on
`mac-v${VERSION}`.

- [x] **Step 5: Run focused tests and commit**

Run `tests.test_release_configuration`. Expected: all tests pass.

```powershell
git add .github/workflows/release.yml tests/test_release_configuration.py
git commit -m "ci: publish Windows installer and portable package"
```

### Task 6: Update Product Documentation

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.md`
- Modify: `tests/test_project_metadata.py`
- Modify: outer `文件夹说明.txt`

- [ ] **Step 1: Update metadata assertions**

Require README references to:

```text
ClickGit-Windows-x64-Setup.exe
ClickGit-Windows-x64-Portable.zip
scripts\package.ps1
scripts\publish.ps1
```

- [ ] **Step 2: Verify metadata test failure**

Run `tests.test_project_metadata`. Expected: failure until README is updated.

- [ ] **Step 3: Update README and changelog**

Document installer-first Windows usage, portable ZIP fallback, local
packaging commands, macOS architecture packages, and the clean delivery
layout. Record the change under `Unreleased / Changed`.

- [ ] **Step 4: Update outer folder explanation**

Replace the obsolete statement that delivery files must not be adjusted.
Describe:

- `开发空间`: source and expanded artifacts.
- `交付产品`: final packages and checksums only.
- root installer and HTML files: direct user entry points.

- [ ] **Step 5: Run metadata tests and commit**

Run `tests.test_project_metadata`. Expected: all tests pass.

```powershell
git add README.md CHANGELOG.md tests/test_project_metadata.py
git commit -m "docs: explain packaged delivery workflow"
```

The outer `文件夹说明.txt` is not inside the repository and is recorded in
the final progress report rather than the Git commit.

### Task 7: Full Verification And Delivery Replacement

**Files:**
- Modify: outer `进度.md`

- [ ] **Step 1: Run all automated tests**

```powershell
$env:PYTHONPATH = "src"
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
```

Expected: all tests pass.

- [ ] **Step 2: Rebuild and verify Windows packages**

```powershell
.\scripts\package.ps1 -Version 0.1.0
.\scripts\verify-package.ps1
```

Expected: installer and portable ZIP exist and package smoke passes.

- [ ] **Step 3: Test installer lifecycle**

Install silently into a temporary directory:

```powershell
& .\artifacts\installer\ClickGit-Windows-x64-Setup.exe `
  /VERYSILENT /SUPPRESSMSGBOXES /NORESTART `
  /DIR="$env:TEMP\ClickGit-install-check"
```

Run the installed `ClickGit.exe --smoke-test`, verify bundled Git, invoke the
generated uninstaller silently, and confirm the temporary installation
directory is removed.

- [ ] **Step 4: Publish final local delivery**

```powershell
.\scripts\publish.ps1 -Version 0.1.0 -SkipPackage
```

Verify:

```text
交付产品\ClickGit-Windows-x64-Setup.exe
交付产品\ClickGit-Windows-x64-Portable.zip
交付产品\SHA256SUMS.txt
ClickGit-安装包.exe
安装说明.html
产品介绍.html
```

Confirm `交付产品\ClickGit` and `交付产品\ClickGit.zip` no longer exist.

- [ ] **Step 5: Validate checksums and directory cleanliness**

Recalculate SHA-256 for every packaged file and compare it with
`SHA256SUMS.txt`. Recursively confirm that no `.pyd`, `.dll`, `PySide6`
directory, or unpacked application folder exists directly under
`交付产品`.

- [ ] **Step 6: Update progress**

Record confirmed facts, modified files, final directory tree, test totals,
package smoke output, installer lifecycle result, compatibility, risks,
remaining macOS/GitHub release work, and commit identifiers in outer
`进度.md`.

- [ ] **Step 7: Final repository checks**

```powershell
git diff --check
git status --short --branch
git log -10 --oneline
```

Expected: no unintended tracked changes, no whitespace errors, and local
`main` ahead of `origin/main` by the new implementation commits.
