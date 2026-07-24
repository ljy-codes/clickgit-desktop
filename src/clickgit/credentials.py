from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass, fields
from pathlib import Path

@dataclass(slots=True, frozen=True)
class CredentialRequest:
    protocol: str = ""
    host: str = ""
    path: str = ""
    username: str = ""
    password: str = ""


def build_credential_payload(request: CredentialRequest) -> bytes:
    lines: list[str] = []
    for item in fields(request):
        value = str(getattr(request, item.name))
        if "\n" in value or "\r" in value or "\0" in value:
            raise ValueError(f"Invalid credential field: {item.name}")
        if value:
            lines.append(f"{item.name}={value}")
    return ("\n".join(lines) + "\n\n").encode("utf-8")


def parse_credential_output(payload: bytes | str) -> CredentialRequest:
    text = (
        payload.decode("utf-8", errors="replace")
        if isinstance(payload, bytes)
        else payload
    )
    values: dict[str, str] = {}
    allowed = {item.name for item in fields(CredentialRequest)}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in allowed:
            values[key] = value
    return CredentialRequest(**values)


class SshKeyService:
    def __init__(self, ssh_keygen: Path) -> None:
        self.ssh_keygen = Path(ssh_keygen)

    @classmethod
    def from_git(cls, git_executable: Path) -> SshKeyService:
        git_root = Path(git_executable).resolve().parent.parent
        candidates = [
            git_root / "usr" / "bin" / "ssh-keygen.exe",
            git_root / "mingw64" / "bin" / "ssh-keygen.exe",
        ]
        discovered = shutil.which("ssh-keygen")
        if discovered:
            candidates.append(Path(discovered))
        for candidate in candidates:
            if candidate.is_file():
                return cls(candidate)
        raise FileNotFoundError("ssh-keygen.exe was not found")

    def generate(
        self,
        private_key: Path,
        *,
        comment: str,
        passphrase: str | None,
    ) -> Path:
        private_key = Path(private_key)
        private_key.parent.mkdir(parents=True, exist_ok=True)
        command = [
            str(self.ssh_keygen),
            "-q",
            "-t",
            "ed25519",
            "-f",
            str(private_key),
            "-C",
            comment,
            "-N",
            passphrase or "",
        ]
        creationflags = (
            subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            shell=False,
            creationflags=creationflags,
        )
        if completed.returncode != 0:
            message = completed.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(message or "SSH key generation failed")
        return private_key

    @staticmethod
    def public_key(private_key: Path) -> str:
        public_path = Path(f"{Path(private_key)}.pub")
        return public_path.read_text(encoding="utf-8").strip()
