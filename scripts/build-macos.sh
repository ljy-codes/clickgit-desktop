#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$PROJECT_ROOT"

CLICKGIT_VERSION="${CLICKGIT_VERSION:-$(
    "$PYTHON_BIN" -c \
        'import pathlib, tomllib; print(tomllib.loads(pathlib.Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"])'
)}"
export CLICKGIT_VERSION

"$PYTHON_BIN" scripts/verify_licenses.py \
    --project-root "$PROJECT_ROOT" \
    --python-executable "$PYTHON_BIN"
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

RESOURCE_ROOT="$PROJECT_ROOT/artifacts/publish/macos/ClickGit.app/Contents/Resources"
mkdir -p "$RESOURCE_ROOT"
cp "$PROJECT_ROOT/LICENSE" "$RESOURCE_ROOT/LICENSE"
cp "$PROJECT_ROOT/THIRD-PARTY-NOTICES.txt" \
    "$RESOURCE_ROOT/THIRD-PARTY-NOTICES.txt"
cp -R "$PROJECT_ROOT/docs/licenses/distribution" \
    "$RESOURCE_ROOT/licenses"

PYTHON_BIN="$PYTHON_BIN" scripts/verify-macos.sh

case "$(uname -m)" in
    arm64)
        ARCHIVE_NAME="ClickGit-macOS-arm64.zip"
        EXPECTED_ARCHITECTURE="arm64"
        ;;
    x86_64)
        ARCHIVE_NAME="ClickGit-macOS-x64.zip"
        EXPECTED_ARCHITECTURE="x86_64"
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
"$PYTHON_BIN" scripts/validate_macos_archive.py \
    "artifacts/package/$ARCHIVE_NAME" \
    --architecture "$EXPECTED_ARCHITECTURE" \
    --version "$CLICKGIT_VERSION"

echo "macOS package ready: $PROJECT_ROOT/artifacts/package/$ARCHIVE_NAME"
