#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$PROJECT_ROOT"
export PYTHONPATH="src"
export QT_QPA_PLATFORM="offscreen"
"$PYTHON_BIN" -m unittest discover -s tests -v
unset QT_QPA_PLATFORM

"$PYTHON_BIN" -m PyInstaller \
    --noconfirm \
    --clean \
    --workpath artifacts/build/macos \
    --distpath artifacts/publish/macos \
    installer/clickgit-macos.spec

PYTHON_BIN="$PYTHON_BIN" scripts/verify-macos.sh

case "$(uname -m)" in
    arm64)
        ARCHIVE_NAME="ClickGit-macOS-arm64.zip"
        ;;
    x86_64)
        ARCHIVE_NAME="ClickGit-macOS-x64.zip"
        ;;
    *)
        echo "Unsupported macOS architecture: $(uname -m)" >&2
        exit 1
        ;;
esac

mkdir -p artifacts/package
rm -f "artifacts/package/$ARCHIVE_NAME"
ditto -c -k --sequesterRsrc --keepParent \
    "artifacts/publish/macos/ClickGit.app" \
    "artifacts/package/$ARCHIVE_NAME"

echo "macOS package ready: $PROJECT_ROOT/artifacts/package/$ARCHIVE_NAME"
