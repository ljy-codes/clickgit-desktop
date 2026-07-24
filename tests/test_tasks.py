from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from clickgit.tasks import RepositoryTaskQueue


class RepositoryTaskQueueTests(unittest.TestCase):
    def test_write_tasks_for_same_repository_are_serialized(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            queue = RepositoryTaskQueue(max_workers=4)
            self.addCleanup(queue.shutdown)
            repository = Path(temp_dir)
            active = 0
            maximum_active = 0
            lock = threading.Lock()

            def write_task(value: int) -> int:
                nonlocal active, maximum_active
                with lock:
                    active += 1
                    maximum_active = max(maximum_active, active)
                time.sleep(0.05)
                with lock:
                    active -= 1
                return value

            futures = [
                queue.submit(repository, write_task, value, write=True)
                for value in range(4)
            ]

            self.assertEqual([future.result() for future in futures], list(range(4)))
            self.assertEqual(maximum_active, 1)

    def test_read_tasks_can_run_in_parallel(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            queue = RepositoryTaskQueue(max_workers=4)
            self.addCleanup(queue.shutdown)
            repository = Path(temp_dir)
            barrier = threading.Barrier(2)

            def read_task() -> bool:
                barrier.wait(timeout=1)
                return True

            first = queue.submit(repository, read_task, write=False)
            second = queue.submit(repository, read_task, write=False)

            self.assertTrue(first.result())
            self.assertTrue(second.result())


if __name__ == "__main__":
    unittest.main()
