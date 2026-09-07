from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


MANIFEST_NAME = "LICENSE-MANIFEST.json"


def _text_lf_sha256(path: Path) -> str:
    canonical_bytes = (
        path.read_bytes()
        .replace(b"\r\n", b"\n")
        .replace(b"\r", b"\n")
    )
    return hashlib.sha256(canonical_bytes).hexdigest()


def _load_manifest(license_root: Path) -> dict[str, object]:
    manifest_path = license_root / MANIFEST_NAME
    if not manifest_path.is_file():
        raise ValueError(f"License manifest was not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported license manifest schema.")
    if manifest.get("digest_mode") != "sha256-text-lf":
        raise ValueError("Unsupported license manifest digest mode.")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("License manifest does not contain files.")
    return manifest


def _verify_files(
    license_root: Path,
    manifest: dict[str, object],
) -> None:
    expected_files = manifest["files"]
    assert isinstance(expected_files, dict)
    actual_files = {
        path.name
        for path in license_root.iterdir()
        if path.is_file() and path.name != MANIFEST_NAME
    }
    if actual_files != set(expected_files):
        raise ValueError(
            "License bundle file set does not match the manifest."
        )
    for file_name, expected_digest in expected_files.items():
        file_path = license_root / file_name
        if not file_path.is_file() or file_path.stat().st_size == 0:
            raise ValueError(f"License file is missing or empty: {file_name}")
        actual_digest = _text_lf_sha256(file_path)
        if actual_digest != expected_digest:
            raise ValueError(
                f"License file SHA-256 mismatch: {file_name}"
            )


def _run_version(executable: Path, arguments: list[str]) -> str:
    result = subprocess.run(
        [str(executable), *arguments],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(
            f"Version command failed for {executable}: {result.stderr}"
        )
    return result.stdout.strip()


def _verify_python(
    python_executable: Path,
    manifest: dict[str, object],
) -> None:
    python_config = manifest["python"]
    assert isinstance(python_config, dict)
    expected = python_config["major_minor"]
    actual = _run_version(
        python_executable,
        [
            "-c",
            "import sys; print(f'{sys.version_info.major}."
            "{sys.version_info.minor}')",
        ],
    )
    if actual != expected:
        raise ValueError(
            f"Python runtime version mismatch: expected {expected}, "
            f"got {actual}."
        )

    for distribution_name, manifest_key in (
        ("PySide6", "pyside6"),
        ("PyInstaller", "pyinstaller"),
    ):
        config = manifest[manifest_key]
        assert isinstance(config, dict)
        expected_version = config["version"]
        actual_version = _run_version(
            python_executable,
            [
                "-c",
                (
                    "import importlib.metadata; "
                    f"print(importlib.metadata.version('{distribution_name}'))"
                ),
            ],
        )
        if actual_version != expected_version:
            raise ValueError(
                f"{distribution_name} version mismatch: expected "
                f"{expected_version}, got {actual_version}."
            )


def _verify_git(
    git_executable: Path,
    manifest: dict[str, object],
) -> None:
    git_config = manifest["portable_git"]
    assert isinstance(git_config, dict)
    expected = f"git version {git_config['version']}"
    actual = _run_version(git_executable, ["--version"])
    if actual != expected:
        raise ValueError(
            f"PortableGit runtime version mismatch: expected {expected}, "
            f"got {actual}."
        )
    _verify_git_materials(git_executable.parents[3], manifest)


def _verify_git_materials(
    package_root: Path,
    manifest: dict[str, object],
) -> None:
    git_config = manifest["portable_git"]
    assert isinstance(git_config, dict)
    required_files = git_config["required_files"]
    assert isinstance(required_files, list)
    for relative_path in required_files:
        material_path = package_root / relative_path
        if (
            not material_path.is_file()
            or material_path.stat().st_size == 0
        ):
            raise ValueError(
                f"PortableGit license material is missing: {relative_path}"
            )


def verify(
    project_root: Path,
    *,
    python_executable: Path | None = None,
    git_executable: Path | None = None,
    package_root: Path | None = None,
) -> None:
    source_license_root = (
        project_root / "docs" / "licenses" / "distribution"
    )
    manifest = _load_manifest(source_license_root)
    _verify_files(source_license_root, manifest)

    if python_executable is not None:
        _verify_python(python_executable, manifest)
    if git_executable is not None:
        _verify_git(git_executable, manifest)
    if package_root is not None:
        package_license_root = package_root / "licenses"
        package_manifest = _load_manifest(package_license_root)
        if package_manifest != manifest:
            raise ValueError(
                "Packaged license manifest differs from the source manifest."
            )
        _verify_files(package_license_root, package_manifest)
        for required_name in ("LICENSE", "THIRD-PARTY-NOTICES.txt"):
            required_path = package_root / required_name
            if (
                not required_path.is_file()
                or required_path.stat().st_size == 0
            ):
                raise ValueError(
                    f"Packaged notice is missing or empty: {required_name}"
                )
        if (package_root / "runtime" / "git").is_dir():
            _verify_git_materials(package_root, manifest)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--python-executable", type=Path)
    parser.add_argument("--git-executable", type=Path)
    parser.add_argument("--package-root", type=Path)
    args = parser.parse_args(argv)
    try:
        verify(
            args.project_root.resolve(),
            python_executable=args.python_executable,
            git_executable=args.git_executable,
            package_root=args.package_root,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"License verification failed: {exc}", file=sys.stderr)
        return 1
    print("Third-party license bundle verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
