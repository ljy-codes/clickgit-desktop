from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")


class RepositoryTaskQueue:
    def __init__(self, max_workers: int = 4) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="clickgit",
        )
        self._registry_lock = threading.Lock()
        self._write_locks: dict[Path, threading.Lock] = {}

    def submit(
        self,
        repository_path: Path,
        function: Callable[..., T],
        *args: Any,
        write: bool,
        **kwargs: Any,
    ) -> Future[T]:
        repository = Path(repository_path).resolve()
        if not write:
            return self._executor.submit(function, *args, **kwargs)

        with self._registry_lock:
            write_lock = self._write_locks.setdefault(
                repository,
                threading.Lock(),
            )

        def serialized() -> T:
            with write_lock:
                return function(*args, **kwargs)

        return self._executor.submit(serialized)

    def shutdown(self, *, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=True)
