#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
EXECUTABLE="$PROJECT_ROOT/artifacts/publish/macos/ClickGit.app/Contents/MacOS/ClickGit"
REPORT="$PROJECT_ROOT/artifacts/build/macos/macos-package-smoke.json"
RESOURCE_ROOT="$PROJECT_ROOT/artifacts/publish/macos/ClickGit.app/Contents/Resources"

if [[ ! -x "$EXECUTABLE" ]]; then
    echo "Packaged macOS executable was not found: $EXECUTABLE" >&2
    exit 1
fi

mkdir -p "$(dirname "$REPORT")"
"$EXECUTABLE" --smoke-test "$REPORT"
"$PYTHON_BIN" "$PROJECT_ROOT/scripts/verify_macos_report.py" "$REPORT"
"$PYTHON_BIN" "$PROJECT_ROOT/scripts/verify_licenses.py" \
    --project-root "$PROJECT_ROOT" \
    --package-root "$RESOURCE_ROOT"
