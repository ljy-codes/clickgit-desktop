from __future__ import annotations

import argparse
import plistlib
import stat
import sys
import zipfile
from pathlib import Path


MACHO_64_MAGIC = b"\xcf\xfa\xed\xfe"
CPU_TYPES = {
    "x86_64": 0x01000007,
    "arm64": 0x0100000C,
}


def _console_safe(text: str, stream: object) -> str:
    encoding = getattr(stream, "encoding", None) or "utf-8"
    return text.encode(
        encoding,
        errors="backslashreplace",
    ).decode(encoding)


def validate_archive(
    archive_path: Path,
    architecture: str,
    version: str,
) -> None:
    if not archive_path.is_file() or archive_path.stat().st_size == 0:
        raise ValueError(f"archive is missing or empty: {archive_path}")
    expected_executable = "ClickGit.app/Contents/MacOS/ClickGit"
    expected_info_plist = "ClickGit.app/Contents/Info.plist"
    try:
        with zipfile.ZipFile(archive_path) as archive:
            bad_entry = archive.testzip()
            if bad_entry is not None:
                raise ValueError(f"CRC check failed: {bad_entry}")
            names = {
                name.replace("\\", "/").lstrip("./")
                for name in archive.namelist()
            }
            if expected_executable not in names:
                raise ValueError(
                    f"missing app executable: {expected_executable}"
                )
            if expected_info_plist not in names:
                raise ValueError(
                    f"missing app metadata: {expected_info_plist}"
                )
            executable_info = archive.getinfo(expected_executable)
            unix_mode = executable_info.external_attr >> 16
            if stat.S_IFMT(unix_mode) != stat.S_IFREG:
                raise ValueError("app executable is not a regular Unix file")
            if unix_mode & 0o111 == 0:
                raise ValueError("app executable does not have execute bits")
            if executable_info.file_size < 4096:
                raise ValueError("app executable is unexpectedly small")
            header = archive.read(expected_executable)[:8]
            try:
                info_plist = plistlib.loads(
                    archive.read(expected_info_plist)
                )
            except (plistlib.InvalidFileException, ValueError) as exc:
                raise ValueError("app Info.plist is invalid") from exc
    except zipfile.BadZipFile as exc:
        raise ValueError("archive is not a readable ZIP file") from exc

    bundle_version = info_plist.get("CFBundleShortVersionString")
    if bundle_version != version:
        raise ValueError(
            f"bundle version mismatch: expected {version}, "
            f"found {bundle_version!r}"
        )
    if len(header) < 8 or header[:4] != MACHO_64_MAGIC:
        raise ValueError("app executable is not a 64-bit Mach-O binary")
    actual_cpu_type = int.from_bytes(header[4:8], "little")
    expected_cpu_type = CPU_TYPES[architecture]
    if actual_cpu_type != expected_cpu_type:
        raise ValueError(
            f"Mach-O architecture mismatch: expected {architecture}, "
            f"CPU type is 0x{actual_cpu_type:08x}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument(
        "--architecture",
        required=True,
        choices=tuple(CPU_TYPES),
    )
    parser.add_argument("--version", required=True)
    args = parser.parse_args(argv)
    try:
        validate_archive(args.archive, args.architecture, args.version)
    except (OSError, ValueError) as exc:
        print(
            _console_safe(f"Invalid macOS package: {exc}", sys.stderr),
            file=sys.stderr,
        )
        return 1
    print(
        _console_safe(
            f"macOS archive verified for {args.architecture}: {args.archive}",
            sys.stdout,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
