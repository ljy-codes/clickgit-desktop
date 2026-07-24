from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from clickgit.settings import AppSettings, SettingsStore


class SettingsStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "settings.json"

    def test_round_trip_preserves_recent_repositories(self) -> None:
        store = SettingsStore(self.path)
        expected = AppSettings(
            recent_repositories=["D:/repo"],
            favorite_repositories=["D:/favorite"],
            theme="dark",
            external_editor="code.exe",
        )

        store.save(expected)

        self.assertEqual(store.load(), expected)

    def test_invalid_json_returns_defaults_and_preserves_corrupt_file(self) -> None:
        self.path.write_text("{broken", encoding="utf-8")
        store = SettingsStore(self.path)

        loaded = store.load()

        self.assertEqual(loaded, AppSettings())
        self.assertFalse(self.path.exists())
        self.assertTrue(self.path.with_suffix(".json.corrupt").exists())

    def test_missing_file_returns_defaults(self) -> None:
        self.assertEqual(SettingsStore(self.path).load(), AppSettings())


if __name__ == "__main__":
    unittest.main()
