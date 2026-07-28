from __future__ import annotations

import json
import sys
from pathlib import Path, PurePosixPath


def verify_report(report_path: Path) -> str:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("git_returncode") != 0:
        raise ValueError("Packaged Git diagnostic failed")
    if not report.get("gui_started"):
        raise ValueError("Packaged macOS GUI smoke test did not complete")

    git_executable = PurePosixPath(report.get("git_executable", ""))
    if not git_executable.is_absolute():
        raise ValueError(
            "Packaged app did not resolve an absolute Git path"
        )

    git_version = report.get("git_version", "Git")
    return f"macOS package verified with {git_version}"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        raise SystemExit(
            "Usage: verify_macos_report.py <smoke-report.json>"
        )

    try:
        message = verify_report(Path(argv[1]))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc

    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
