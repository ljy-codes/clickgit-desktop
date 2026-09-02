# Development Directory Reorganization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize ClickGit's development-only folders to match the reference project's structure without changing application behavior or release contents.

**Architecture:** All generated build, publish, smoke-test, and archive files move under `artifacts/`. PyInstaller specifications move from `packaging/` to `installer/`. Existing entry commands remain unchanged, while scripts, tests, documentation, and GitHub Actions use the new paths.

**Tech Stack:** Python 3.13, unittest, PyInstaller, PowerShell, Bash, GitHub Actions

---

### Task 1: Define the new directory contract in tests

**Files:**
- Modify: `tests/test_release_configuration.py`

- [x] **Step 1: Add failing assertions for the new layout**

Add assertions that require:

```python
PROJECT_ROOT / "installer" / "clickgit.spec"
PROJECT_ROOT / "installer" / "clickgit-macos.spec"
```

The scripts and workflow must reference:

```text
artifacts/build
artifacts/publish/windows-x64
artifacts/publish/macos
artifacts/package
installer/clickgit.spec
installer/clickgit-macos.spec
```

- [x] **Step 2: Run the focused test and verify it fails**

Run:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest tests.test_release_configuration -v
```

Expected: FAIL because the project still references `packaging`, `build`, and `dist`.

### Task 2: Move specifications and update local build scripts

**Files:**
- Move: `packaging/clickgit.spec` to `installer/clickgit.spec`
- Move: `packaging/clickgit-macos.spec` to `installer/clickgit-macos.spec`
- Modify: `scripts/build.ps1`
- Modify: `scripts/build-macos.sh`
- Modify: `scripts/verify-package.ps1`
- Modify: `scripts/verify-macos.sh`

- [x] **Step 1: Move both PyInstaller specifications**

Keep specification content unchanged except for path handling required by the new parent directory.

- [x] **Step 2: Route Windows build output**

Invoke PyInstaller with:

```powershell
--workpath artifacts\build\windows
--distpath artifacts\publish\windows-x64
installer\clickgit.spec
```

Store the Windows smoke report at:

```text
artifacts/build/windows/package-smoke.json
```

- [x] **Step 3: Route macOS build output**

Invoke PyInstaller with:

```text
--workpath artifacts/build/macos
--distpath artifacts/publish/macos
installer/clickgit-macos.spec
```

Store the macOS smoke report under `artifacts/build/macos` and the architecture-specific ZIP under `artifacts/package`.

- [x] **Step 4: Run the focused test**

Run:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest tests.test_release_configuration -v
```

Expected: local script assertions PASS; workflow assertions may still FAIL until Task 3.

### Task 3: Update CI release paths and ignore rules

**Files:**
- Modify: `.github/workflows/release.yml`
- Modify: `.gitignore`

- [x] **Step 1: Update Windows archive paths**

Archive:

```text
artifacts/publish/windows-x64/ClickGit
```

to:

```text
artifacts/package/ClickGit-Windows-x64.zip
```

- [x] **Step 2: Update macOS artifact paths**

Upload:

```text
artifacts/package/${{ matrix.archive }}
```

- [x] **Step 3: Replace old generated-directory ignore entries**

Ignore:

```gitignore
artifacts/
```

Remove the obsolete `build/` and `dist/` entries.

- [x] **Step 4: Run release configuration tests**

Run:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest tests.test_release_configuration -v
```

Expected: PASS.

### Task 4: Update developer documentation

**Files:**
- Modify: `README.md`

- [x] **Step 1: Document the new Windows output**

Use:

```text
artifacts\publish\windows-x64\ClickGit\ClickGit.exe
```

- [x] **Step 2: Document the new macOS outputs**

Use:

```text
artifacts/package/ClickGit-macOS-arm64.zip
artifacts/package/ClickGit-macOS-x64.zip
```

- [x] **Step 3: Document the development directory layout**

List `artifacts`, `installer`, `scripts`, `src`, `tests`, `docs`, and `runtime`, including each directory's responsibility.

### Task 5: Verify and clean obsolete generated directories

**Files:**
- Remove generated local directories: `build/`, `dist/`

- [x] **Step 1: Run all unit tests**

Run:

```powershell
$env:PYTHONPATH = "src"
$env:QT_QPA_PLATFORM = "offscreen"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Expected: all tests PASS.

- [x] **Step 2: Run the Windows build and package smoke test**

Run:

```powershell
.\scripts\build.ps1
.\scripts\verify-package.ps1
```

Expected: `artifacts/publish/windows-x64/ClickGit/ClickGit.exe` exists and the packaged smoke test succeeds.

- [x] **Step 3: Check for active references to old paths**

Run:

```powershell
rg -n --hidden --glob "!.git/**" --glob "!.venv/**" --glob "!docs/superpowers/**" "(packaging|build|dist)[/\\]" .
```

Expected: no active configuration, script, test, or README references.

- [x] **Step 4: Remove old generated directories**

Verify the absolute targets are exactly:

```text
D:\专用工具\git工具\build
D:\专用工具\git工具\dist
```

Then remove those generated directories. Do not remove source-controlled content.

- [x] **Step 5: Review the final diff**

Run:

```powershell
git status --short
git diff --check
git diff
```

Expected: only directory organization, path-reference, test, and documentation changes.
