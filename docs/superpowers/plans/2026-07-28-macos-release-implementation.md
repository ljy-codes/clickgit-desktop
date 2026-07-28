# ClickGit macOS And Dual Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add native macOS packaging for Intel and Apple Silicon, then publish separate Windows and macOS GitHub Releases.

**Architecture:** Move platform-specific path, font, and Git resolution into a small pure helper module used by the application entry point. Keep the Windows PortableGit package unchanged, add a separate PyInstaller macOS app bundle, and build all three artifacts on native GitHub-hosted runners before publishing.

**Tech Stack:** Python 3.13, PySide6 6.10.3, PyInstaller 6.21.0, unittest, PowerShell, Bash, GitHub Actions, GitHub CLI.

---

### Task 1: Cross-Platform Runtime Behavior

**Files:**
- Create: `src/clickgit/platform_support.py`
- Create: `tests/test_platform_support.py`
- Modify: `src/clickgit/__main__.py`
- Modify: `src/clickgit/credentials.py`
- Modify: `src/clickgit/ui/styles.py`

- [ ] **Step 1: Write failing platform tests**

Test Windows and macOS application-data directories, preferred fonts, bundled
Git selection, PATH fallback, and cross-platform `ssh-keygen` lookup.

- [ ] **Step 2: Verify the tests fail**

Run:

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -m unittest tests.test_platform_support -v
```

Expected: failure because `clickgit.platform_support` does not exist.

- [ ] **Step 3: Implement the platform helper**

Provide pure functions with injectable platform, environment, home, executable
root, and PATH lookup values. Keep the Win32 wide-character executable-path
lookup in the helper.

- [ ] **Step 4: Integrate the helper**

Use platform data directory, actual Git resolution and platform font selection
from `__main__.py`. Make the SSH key error message platform neutral and add
PingFang SC to the stylesheet fallback chain.

- [ ] **Step 5: Verify targeted and full tests**

Run:

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -m unittest tests.test_platform_support -v
.venv\Scripts\python.exe -m unittest discover -s tests
```

Expected: all tests pass.

### Task 2: Native macOS Application Bundle

**Files:**
- Create: `packaging/clickgit-macos.spec`
- Create: `scripts/build-macos.sh`
- Create: `scripts/verify-macos.sh`
- Create: `tests/test_release_configuration.py`
- Modify: `.gitignore`

- [ ] **Step 1: Write failing packaging configuration tests**

Assert that the macOS spec creates `ClickGit.app`, does not include
`runtime/git`, and that the build and verification scripts invoke PyInstaller,
`ditto`, and the diagnostic smoke mode.

- [ ] **Step 2: Verify the tests fail**

Run:

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -m unittest tests.test_release_configuration -v
```

Expected: failure because the macOS packaging files do not exist.

- [ ] **Step 3: Add macOS spec and scripts**

Create an onedir PyInstaller bundle wrapped by `BUNDLE`, build with the native
runner architecture, run the packaged app in smoke mode, and archive the
`.app` with `ditto`.

- [ ] **Step 4: Verify configuration tests**

Run:

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -m unittest tests.test_release_configuration -v
```

Expected: all packaging configuration tests pass.

### Task 3: GitHub Actions Dual Release

**Files:**
- Create: `.github/workflows/release.yml`
- Modify: `tests/test_release_configuration.py`

- [ ] **Step 1: Add failing workflow assertions**

Assert the workflow triggers on `release-v*`, uses Windows x64,
`macos-15`, and `macos-15-intel`, uploads all three named ZIP files, grants
`contents: write`, and creates `windows-v$VERSION` and `mac-v$VERSION`.

- [ ] **Step 2: Verify the workflow test fails**

Run:

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -m unittest tests.test_release_configuration -v
```

Expected: failure because `.github/workflows/release.yml` does not exist.

- [ ] **Step 3: Implement the workflow**

Build and test each target on its native runner, upload immutable artifacts,
download them in the release job, and create the two releases with
`gh release create`.

- [ ] **Step 4: Verify configuration and full tests**

Run:

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -m unittest tests.test_release_configuration -v
.venv\Scripts\python.exe -m unittest discover -s tests
```

Expected: all tests pass.

### Task 4: Documentation, Windows Regression And Publication

**Files:**
- Modify: `README.md`
- Modify: `pyproject.toml`

- [ ] **Step 1: Update product and release documentation**

Describe Windows and macOS downloads, architecture selection, system Git usage,
configuration paths, build commands, unsigned-app warnings, and release tags.

- [ ] **Step 2: Run local verification**

Run:

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m compileall -q src tests
git diff --check
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
powershell -ExecutionPolicy Bypass -File scripts\verify-package.ps1
```

Expected: tests, compilation, Windows build and package smoke verification pass.

- [ ] **Step 3: Commit and synchronize**

Rename the completed branch to `main`, commit all macOS and release work, and
push `main` to `origin` using a one-command proxy override because the global
Git proxy points at an inactive local port.

- [ ] **Step 4: Trigger release**

Create and push annotated tag `release-v0.1.0`. The workflow must build all
three targets before creating `windows-v0.1.0` and `mac-v0.1.0`.

- [ ] **Step 5: Verify remote results**

Confirm the workflow succeeded and both Release tags contain the expected
Windows x64, macOS arm64, and macOS x64 ZIP assets.

