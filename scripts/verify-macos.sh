#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
EXECUTABLE="$PROJECT_ROOT/dist/ClickGit.app/Contents/MacOS/ClickGit"
REPORT="$PROJECT_ROOT/build/macos-package-smoke.json"

if [[ ! -x "$EXECUTABLE" ]]; then
    echo "Packaged macOS executable was not found: $EXECUTABLE" >&2
    exit 1
fi

mkdir -p "$(dirname "$REPORT")"
"$EXECUTABLE" --smoke-test "$REPORT"

"$PYTHON_BIN" -c '
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if report.get("git_returncode") != 0:
    raise SystemExit("Packaged Git diagnostic failed")
if not report.get("gui_started"):
    raise SystemExit("Packaged macOS GUI smoke test did not complete")
git_executable = Path(report.get("git_executable", ""))
if not git_executable.is_absolute():
    raise SystemExit("Packaged app did not resolve an absolute Git path")
print(f"macOS package verified with {report.get(\"git_version\", \"Git\")}")
' "$REPORT"

