from __future__ import annotations

import json
import shutil
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from clickgit.repository import Repository


class RecoveryError(RuntimeError):
    pass


class RecoveryPathError(RecoveryError):
    pass


@dataclass(slots=True)
class RecoveryPoint:
    identifier: str
    kind: str
    reason: str
    repository_path: Path
    created_at: datetime
    manifest_path: Path
    ref_name: str = ""
    files: tuple[str, ...] = ()
    _restore_callback: Callable[["RecoveryPoint"], bool] = field(
        repr=False,
        compare=False,
        default=lambda _: False,
    )

    def restore(self) -> bool:
        return self._restore_callback(self)


class RecoveryManager:
    def __init__(
        self,
        repository: Repository,
        recovery_root: Path,
    ) -> None:
        self.repository = repository
        self.recovery_root = Path(recovery_root).resolve()

    def protect_commit_graph(self, reason: str) -> RecoveryPoint:
        identifier = self._new_identifier()
        ref_name = f"refs/clickgit/recovery/{identifier}"
        self.repository._run(["update-ref", ref_name, "HEAD"])
        point = RecoveryPoint(
            identifier=identifier,
            kind="commit-graph",
            reason=reason,
            repository_path=self.repository.path,
            created_at=datetime.now().astimezone(),
            manifest_path=self._manifest_path(identifier),
            ref_name=ref_name,
            _restore_callback=self.restore,
        )
        self._write_manifest(point)
        return point

    def quarantine(self, paths: Iterable[Path]) -> RecoveryPoint:
        validated = [self._validate_source(path) for path in paths]
        identifier = self._new_identifier()
        point_root = self.recovery_root / identifier
        files_root = point_root / "files"
        moved: list[tuple[Path, Path]] = []
        try:
            for source, relative in validated:
                destination = files_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(destination))
                moved.append((source, destination))
        except OSError as exc:
            for source, destination in reversed(moved):
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(source))
            shutil.rmtree(point_root, ignore_errors=True)
            raise RecoveryError(f"Failed to quarantine files: {exc}") from exc

        point = RecoveryPoint(
            identifier=identifier,
            kind="quarantine",
            reason="clean",
            repository_path=self.repository.path,
            created_at=datetime.now().astimezone(),
            manifest_path=self._manifest_path(identifier),
            files=tuple(relative.as_posix() for _, relative in validated),
            _restore_callback=self.restore,
        )
        self._write_manifest(point)
        return point

    def restore(self, point: RecoveryPoint) -> bool:
        if point.repository_path.resolve() != self.repository.path:
            raise RecoveryPathError("Recovery point belongs to another repository")
        if point.kind == "quarantine":
            return self._restore_quarantine(point)
        if point.kind == "commit-graph":
            branch_name = f"clickgit-recovered-{point.identifier}"
            result = self.repository.runner.run(
                ["branch", branch_name, point.ref_name],
                cwd=self.repository.path,
            )
            return result.returncode == 0
        return False

    def list_points(self) -> list[RecoveryPoint]:
        if not self.recovery_root.exists():
            return []
        points: list[RecoveryPoint] = []
        for manifest_path in self.recovery_root.glob("*/manifest.json"):
            try:
                resolved_manifest = manifest_path.resolve()
                self._ensure_inside(resolved_manifest, self.recovery_root)
                payload = json.loads(
                    resolved_manifest.read_text(encoding="utf-8")
                )
                repository_path = Path(payload["repository_path"]).resolve()
                if repository_path != self.repository.path:
                    continue
                points.append(
                    RecoveryPoint(
                        identifier=str(payload["identifier"]),
                        kind=str(payload["kind"]),
                        reason=str(payload.get("reason", "")),
                        repository_path=repository_path,
                        created_at=datetime.fromisoformat(
                            str(payload["created_at"])
                        ),
                        manifest_path=resolved_manifest,
                        ref_name=str(payload.get("ref_name", "")),
                        files=tuple(
                            str(item) for item in payload.get("files", [])
                        ),
                        _restore_callback=self.restore,
                    )
                )
            except (
                json.JSONDecodeError,
                KeyError,
                OSError,
                TypeError,
                ValueError,
                RecoveryPathError,
            ):
                continue
        return sorted(points, key=lambda item: item.created_at, reverse=True)

    def delete(self, point: RecoveryPoint) -> None:
        if point.repository_path.resolve() != self.repository.path:
            raise RecoveryPathError("Recovery point belongs to another repository")
        point_root = point.manifest_path.parent.resolve()
        self._ensure_inside(point_root, self.recovery_root)
        if point.kind == "commit-graph" and point.ref_name:
            self.repository.runner.run(
                ["update-ref", "-d", point.ref_name],
                cwd=self.repository.path,
            )
        shutil.rmtree(point_root)

    def _restore_quarantine(self, point: RecoveryPoint) -> bool:
        files_root = point.manifest_path.parent / "files"
        sources_and_destinations: list[tuple[Path, Path]] = []
        for relative_text in point.files:
            relative = Path(relative_text)
            source = (files_root / relative).resolve()
            destination = (self.repository.path / relative).resolve()
            self._ensure_inside(source, files_root)
            self._ensure_inside(destination, self.repository.path)
            if destination.exists():
                return False
            sources_and_destinations.append((source, destination))

        restored: list[tuple[Path, Path]] = []
        try:
            for source, destination in sources_and_destinations:
                if not source.exists():
                    raise RecoveryError(f"Recovery file is missing: {source}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(destination))
                restored.append((source, destination))
        except OSError as exc:
            for source, destination in reversed(restored):
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(destination), str(source))
            raise RecoveryError(f"Failed to restore files: {exc}") from exc
        return True

    def _validate_source(self, path: Path) -> tuple[Path, Path]:
        source = Path(path).resolve()
        self._ensure_inside(source, self.repository.path)
        if not source.exists():
            raise RecoveryPathError(f"Path does not exist: {path}")
        return source, source.relative_to(self.repository.path)

    @staticmethod
    def _ensure_inside(path: Path, root: Path) -> None:
        try:
            path.relative_to(root.resolve())
        except ValueError as exc:
            raise RecoveryPathError(f"Path escapes recovery boundary: {path}") from exc

    def _manifest_path(self, identifier: str) -> Path:
        return self.recovery_root / identifier / "manifest.json"

    def _write_manifest(self, point: RecoveryPoint) -> None:
        point.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "identifier": point.identifier,
            "kind": point.kind,
            "reason": point.reason,
            "repository_path": str(point.repository_path),
            "created_at": point.created_at.isoformat(),
            "ref_name": point.ref_name,
            "files": list(point.files),
        }
        temporary = point.manifest_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(point.manifest_path)

    @staticmethod
    def _new_identifier() -> str:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return f"{timestamp}-{uuid.uuid4().hex[:8]}"
