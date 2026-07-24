# ClickGit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个内置 PortableGit、无需命令行、可在 Windows 10/11 双击运行的完整 Git 桌面工具。

**Architecture:** 使用 PySide6 构建桌面界面，应用服务层组织 Git 用例，Git 适配层通过参数数组调用内置 `git.exe`，解析器将机器可读输出转换为数据模型。仓库写操作按仓库串行执行，危险操作由恢复服务创建保护点，凭据通过 AskPass 和 Windows 凭据设施处理。

**Tech Stack:** Python 3.14、PySide6 6.10.3、PyInstaller 6.21、标准库 unittest、PortableGit、PowerShell

---

## File Structure

```text
git工具/
  pyproject.toml
  requirements-dev.txt
  README.md
  src/clickgit/
    __init__.py
    __main__.py
    app.py
    models.py
    settings.py
    git_runner.py
    parsers.py
    repository.py
    recovery.py
    credentials.py
    tasks.py
    ui/
      __init__.py
      main_window.py
      dialogs.py
      conflict_editor.py
      styles.py
  tests/
    test_parsers.py
    test_git_runner.py
    test_repository.py
    test_recovery.py
    test_settings.py
    test_ui_smoke.py
  scripts/
    bootstrap.ps1
    download-portable-git.ps1
    build.ps1
    verify-package.ps1
  packaging/
    clickgit.spec
  runtime/git/
  resources/
    app.ico
```

## Task 1: Project Skeleton and Domain Models

**Files:**
- Create: `pyproject.toml`
- Create: `requirements-dev.txt`
- Create: `src/clickgit/__init__.py`
- Create: `src/clickgit/models.py`
- Create: `src/clickgit/settings.py`
- Test: `tests/test_settings.py`

- [ ] **Step 1: Write the failing settings tests**

```python
class SettingsTests(unittest.TestCase):
    def test_round_trip_preserves_recent_repositories(self):
        store = SettingsStore(self.temp_dir / "settings.json")
        store.save(AppSettings(recent_repositories=["D:/repo"]))
        self.assertEqual(store.load().recent_repositories, ["D:/repo"])

    def test_invalid_json_returns_defaults_and_preserves_corrupt_file(self):
        self.path.write_text("{broken", encoding="utf-8")
        loaded = SettingsStore(self.path).load()
        self.assertEqual(loaded, AppSettings())
        self.assertTrue(self.path.with_suffix(".json.corrupt").exists())
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m unittest tests.test_settings -v`  
Expected: FAIL because `clickgit.settings` does not exist.

- [ ] **Step 3: Implement typed models and atomic JSON settings**

```python
@dataclass(slots=True)
class AppSettings:
    recent_repositories: list[str] = field(default_factory=list)
    favorite_repositories: list[str] = field(default_factory=list)
    theme: str = "system"
    external_editor: str = ""

class SettingsStore:
    def load(self) -> AppSettings: ...
    def save(self, settings: AppSettings) -> None: ...
```

Use a temporary sibling file followed by `Path.replace()` for atomic writes.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m unittest tests.test_settings -v`  
Expected: PASS.

- [ ] **Step 5: Commit**

```text
git add pyproject.toml requirements-dev.txt src/clickgit tests/test_settings.py
git commit -m "feat: add ClickGit project foundation"
```

## Task 2: Git Runner and Machine-Readable Parsers

**Files:**
- Create: `src/clickgit/git_runner.py`
- Create: `src/clickgit/parsers.py`
- Test: `tests/test_git_runner.py`
- Test: `tests/test_parsers.py`

- [ ] **Step 1: Write failing parser tests**

```python
def test_parse_porcelain_v2_modified_and_untracked():
    raw = (
        "1 .M N... 100644 100644 100644 abc def src/app.py\\0"
        "? notes.txt\\0"
    ).encode()
    changes = parse_status_v2(raw)
    assert [(item.path, item.kind) for item in changes] == [
        ("src/app.py", ChangeKind.MODIFIED),
        ("notes.txt", ChangeKind.UNTRACKED),
    ]

def test_parse_refs_keeps_upstream_and_ahead_behind():
    raw = "main\\0refs/remotes/origin/main\\02\\01\\0"
    branches = parse_branches(raw)
    assert branches[0].ahead == 2
    assert branches[0].behind == 1
```

- [ ] **Step 2: Run parser tests and verify RED**

Run: `python -m unittest tests.test_parsers -v`  
Expected: FAIL because parser functions do not exist.

- [ ] **Step 3: Implement parsers**

Implement:

```python
def parse_status_v2(raw: bytes) -> list[FileChange]: ...
def parse_log_records(raw: bytes) -> list[Commit]: ...
def parse_branches(raw: str) -> list[Branch]: ...
def parse_remotes(raw: str) -> list[Remote]: ...
def parse_stashes(raw: str) -> list[StashEntry]: ...
def parse_reflog(raw: str) -> list[ReflogEntry]: ...
```

Use NUL and record separators; do not split localized human output.

- [ ] **Step 4: Write failing runner tests**

```python
def test_runner_passes_argument_list_without_shell(fake_git):
    runner = GitRunner(git_executable=fake_git)
    result = runner.run(["status", "--porcelain=v2"], cwd=repo)
    assert result.returncode == 0
    assert result.command == ("status", "--porcelain=v2")

def test_runner_redacts_tokens():
    text = redact_secrets("https://user:secret@example.com token=abc")
    assert "secret" not in text
    assert "abc" not in text
```

- [ ] **Step 5: Implement runner**

```python
class GitRunner:
    def run(
        self,
        args: Sequence[str],
        *,
        cwd: Path | None = None,
        input_bytes: bytes | None = None,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> GitResult: ...
```

Use `subprocess.run(..., shell=False)`, UTF-8 environment, hidden Windows process flags, captured bytes, timeout handling, and redacted diagnostics.

- [ ] **Step 6: Run tests and verify GREEN**

Run: `python -m unittest tests.test_parsers tests.test_git_runner -v`  
Expected: PASS.

- [ ] **Step 7: Commit**

```text
git add src/clickgit/git_runner.py src/clickgit/parsers.py tests
git commit -m "feat: add safe Git execution and parsers"
```

## Task 3: Repository Service and Core Git Workflows

**Files:**
- Create: `src/clickgit/repository.py`
- Test: `tests/test_repository.py`

- [ ] **Step 1: Write failing integration tests**

```python
def test_stage_commit_branch_and_merge(temp_repository):
    repo = Repository(temp_repository.path, temp_repository.runner)
    (repo.path / "hello.txt").write_text("hello", encoding="utf-8")
    repo.stage(["hello.txt"])
    commit = repo.commit("initial")
    repo.create_branch("feature")
    repo.checkout("feature")
    assert commit.oid
    assert repo.current_branch() == "feature"

def test_clone_fetch_pull_and_push(local_remote):
    clone = Repository.clone(local_remote.url, local_remote.clone_path, runner)
    clone.commit_all("first")
    clone.push()
    assert local_remote.contains_branch("main")
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m unittest tests.test_repository -v`  
Expected: FAIL because `Repository` does not exist.

- [ ] **Step 3: Implement repository API**

Implement typed methods for:

```python
status()
diff(path=None, staged=False)
stage(paths)
unstage(paths)
restore(paths)
commit(message, amend=False)
fetch(remote=None)
pull(remote=None, branch=None, rebase=False)
push(remote=None, branch=None, force_with_lease=False)
branches()
create_branch(name, start_point=None)
checkout(name)
rename_branch(old, new)
delete_branch(name, force=False)
merge(name)
rebase(name)
cherry_pick(oid)
revert(oid)
history(limit, skip, query=None)
tags()
create_tag(name, target=None, message=None)
stashes()
stash_create(message, include_untracked=True)
stash_apply(ref, pop=False)
remotes()
add_remote(name, url)
remove_remote(name)
```

- [ ] **Step 4: Add conflict-state and abort/continue tests**

Verify merge and rebase conflicts return `OperationConflict`, and test:

```python
repo.continue_merge()
repo.abort_merge()
repo.continue_rebase()
repo.abort_rebase()
```

- [ ] **Step 5: Run tests and verify GREEN**

Run: `python -m unittest tests.test_repository -v`  
Expected: PASS using only temporary repositories.

- [ ] **Step 6: Commit**

```text
git add src/clickgit/repository.py tests/test_repository.py
git commit -m "feat: implement core Git repository workflows"
```

## Task 4: Recovery, Credentials, Conflict Editing, and Task Queue

**Files:**
- Create: `src/clickgit/recovery.py`
- Create: `src/clickgit/credentials.py`
- Create: `src/clickgit/tasks.py`
- Create: `src/clickgit/ui/conflict_editor.py`
- Test: `tests/test_recovery.py`

- [ ] **Step 1: Write failing recovery tests**

```python
def test_create_commit_recovery_ref(repository):
    point = RecoveryManager(repository).protect_commit_graph("hard-reset")
    assert point.ref_name.startswith("refs/clickgit/recovery/")
    assert repository.rev_parse(point.ref_name) == repository.head_oid()

def test_quarantine_untracked_file(repository, recovery_root):
    path = repository.path / "large.tmp"
    path.write_text("data", encoding="utf-8")
    point = RecoveryManager(repository, recovery_root).quarantine([path])
    assert not path.exists()
    assert point.restore()
    assert path.read_text(encoding="utf-8") == "data"
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m unittest tests.test_recovery -v`  
Expected: FAIL because recovery module does not exist.

- [ ] **Step 3: Implement recovery**

Implement hidden refs, worktree snapshots, quarantine manifests, restore, expiration and size limits. Resolve every path and verify it remains under the repository root before moving files.

- [ ] **Step 4: Implement credentials**

Provide:

```python
class AskPassServer: ...
class WindowsCredentialStore: ...
class SshKeyService:
    def generate(self, path: Path, comment: str, passphrase: str | None) -> Path: ...
    def public_key(self, private_key: Path) -> str: ...
    def test_connection(self, remote_url: str) -> GitResult: ...
```

Never place secrets in command logs.

- [ ] **Step 5: Implement per-repository task queue**

Read tasks may run concurrently; write tasks use one FIFO queue per resolved repository path. Emit progress, result, error and cancelled signals to the UI.

- [ ] **Step 6: Implement conflict editor**

Use a Qt splitter with base/ours/theirs read-only panes and an editable result pane. Provide per-file ours/theirs/both actions, save, mark resolved, continue and abort.

- [ ] **Step 7: Run tests and commit**

Run: `python -m unittest discover -s tests -v`  
Expected: PASS.

```text
git add src/clickgit/recovery.py src/clickgit/credentials.py src/clickgit/tasks.py src/clickgit/ui/conflict_editor.py tests
git commit -m "feat: add recovery authentication and conflict services"
```

## Task 5: Main Desktop Interface

**Files:**
- Create: `src/clickgit/ui/__init__.py`
- Create: `src/clickgit/ui/main_window.py`
- Create: `src/clickgit/ui/dialogs.py`
- Create: `src/clickgit/ui/styles.py`
- Create: `src/clickgit/app.py`
- Create: `src/clickgit/__main__.py`

- [ ] **Step 1: Write failing UI construction smoke test**

```python
def test_main_window_constructs_without_repository():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(AppController(...))
    assert window.windowTitle() == "ClickGit"
    assert window.repository_path is None
```

- [ ] **Step 2: Run test and verify RED**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m unittest tests.test_ui_smoke -v`  
Expected: FAIL because `MainWindow` does not exist.

- [ ] **Step 3: Implement application shell**

Create:

- Repository picker and recent repositories.
- Toolbar with fetch, pull, push and refresh.
- Sidebar for workspace, history, branches, tags, stashes, remotes, recovery and advanced.
- Stable three-pane workspace layout.
- Status bar with current task, branch and ahead/behind state.

- [ ] **Step 4: Implement workspace and history views**

Provide selectable changes, stage/unstage/restore, patch preview, commit message, amend option, history pagination, search and commit details.

- [ ] **Step 5: Implement branch, tag, stash and remote views**

Use dialogs with validation and confirmation. Destructive actions remain in contextual menus or advanced view.

- [ ] **Step 6: Implement clone, init and settings dialogs**

All dialogs validate paths and names before dispatching operations.

- [ ] **Step 7: Run smoke and core tests**

Run: `python -m unittest discover -s tests -v`  
Expected: PASS.

- [ ] **Step 8: Commit**

```text
git add src/clickgit tests/test_ui_smoke.py
git commit -m "feat: add ClickGit desktop interface"
```

## Task 6: Advanced Git Features

**Files:**
- Modify: `src/clickgit/repository.py`
- Modify: `src/clickgit/ui/main_window.py`
- Modify: `src/clickgit/ui/dialogs.py`
- Test: `tests/test_repository.py`

- [ ] **Step 1: Add failing integration tests**

Cover:

```python
repo.reflog()
repo.reset(target, mode)
repo.clean_preview()
repo.submodule_update(init=True, recursive=True)
repo.worktrees()
repo.worktree_add(path, branch)
repo.worktree_remove(path)
repo.lfs_track(pattern)
repo.create_patch(revisions, destination)
repo.apply_patch(path)
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m unittest tests.test_repository -v`  
Expected: FAIL for missing advanced methods.

- [ ] **Step 3: Implement advanced repository methods**

Every destructive method accepts a `RecoveryPoint` created before command execution. LFS actions first detect `git lfs version` and return a typed unavailable result when missing.

- [ ] **Step 4: Add advanced UI**

Add reset, revert, cherry-pick, reflog recovery, clean preview, submodule, Worktree, LFS and patch dialogs. Require typed confirmation for hard reset and force push.

- [ ] **Step 5: Run tests and commit**

Run: `python -m unittest discover -s tests -v`  
Expected: PASS.

```text
git add src/clickgit tests/test_repository.py
git commit -m "feat: add advanced Git workflows"
```

## Task 7: PortableGit, Packaging, and Documentation

**Files:**
- Create: `scripts/bootstrap.ps1`
- Create: `scripts/download-portable-git.ps1`
- Create: `scripts/build.ps1`
- Create: `scripts/verify-package.ps1`
- Create: `packaging/clickgit.spec`
- Create: `README.md`
- Create: `.gitignore`

- [ ] **Step 1: Add dependency bootstrap**

Create `.venv`, install pinned dependencies and verify imports:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -c "import PySide6, PyInstaller"
```

- [ ] **Step 2: Add PortableGit downloader**

Download a pinned official 64-bit PortableGit archive, verify its SHA-256, extract to `runtime/git`, and fail closed on checksum mismatch.

- [ ] **Step 3: Add PyInstaller onedir build**

The spec file must:

- Produce `dist/ClickGit/ClickGit.exe`.
- Hide the console window.
- Include Qt plugins and application resources.
- Include `runtime/git`.
- Exclude unused Qt modules.

- [ ] **Step 4: Add package verification**

Launch the built app with system Git removed from `PATH`, run a bundled-Git diagnostic, and verify `runtime/git/cmd/git.exe` is the executable used.

- [ ] **Step 5: Write user documentation**

Document double-click startup, opening/cloning repositories, common workflows, recovery, credential storage, build commands and known limitations.

- [ ] **Step 6: Build and commit**

Run: `powershell -ExecutionPolicy Bypass -File scripts/build.ps1`  
Expected: `dist/ClickGit/ClickGit.exe` exists.

```text
git add scripts packaging README.md .gitignore requirements-dev.txt
git commit -m "build: package ClickGit with PortableGit"
```

## Task 8: Final Verification and Review

**Files:**
- Modify only files required by discovered defects.

- [ ] **Step 1: Run all automated tests**

Run: `.\.venv\Scripts\python.exe -m unittest discover -s tests -v`  
Expected: all tests PASS with no warnings or tracebacks.

- [ ] **Step 2: Run static compilation**

Run: `.\.venv\Scripts\python.exe -m compileall -q src tests`  
Expected: exit code 0.

- [ ] **Step 3: Build package**

Run: `powershell -ExecutionPolicy Bypass -File scripts/build.ps1`  
Expected: exit code 0 and `dist/ClickGit/ClickGit.exe`.

- [ ] **Step 4: Verify package**

Run: `powershell -ExecutionPolicy Bypass -File scripts/verify-package.ps1`  
Expected: bundled Git detected and application smoke check passes.

- [ ] **Step 5: Visual verification**

Open the packaged application and inspect:

- 1440×900 desktop layout.
- 1024×720 compact layout.
- Chinese path repository.
- Empty repository.
- Repository with modified, staged and conflicted files.

- [ ] **Step 6: Request code review and fix findings**

Review for command injection, destructive-operation recovery, secret leakage, UI thread blocking, path escape, missing tests and packaging omissions.

- [ ] **Step 7: Final commit**

```text
git add .
git commit -m "feat: deliver ClickGit Windows desktop tool"
```
