from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
        backups = list((self.path.parent / "diagnostics").glob("settings.json.*.corrupt"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "{broken")
        self.assertTrue(store.warnings)

    def test_missing_file_returns_defaults(self) -> None:
        self.assertEqual(SettingsStore(self.path).load(), AppSettings())

    def write_config(self, **overrides) -> None:
        data = {"schema_version": 1, **overrides}
        self.path.write_text(json.dumps(data), encoding="utf-8")

    def test_first_release_schema_separates_projects(self) -> None:
        store = SettingsStore(self.path)
        store.save(AppSettings(recent_repositories=["D:/产品"]))
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(data["ui"], {
            "mode": "simple", "theme": "system",
            "font_size_px": 14, "density": "comfortable",
        })
        self.assertNotIn("ai", data)
        self.assertFalse(data["onboarding_completed"])
        self.assertNotIn("recent_repositories", data)
        projects = json.loads(self.path.with_name("projects.json").read_text(encoding="utf-8"))
        self.assertEqual(projects["recent_repositories"], ["D:/产品"])

    def test_all_preferences_round_trip(self) -> None:
        expected = AppSettings(
            theme="tech", mode="professional", font_size_px=18,
            density="compact", onboarding_completed=True,
        )
        store = SettingsStore(self.path)
        store.save(expected)
        self.assertEqual(store.load(), expected)

    def test_invalid_optional_fields_default_with_safe_warnings(self) -> None:
        self.write_config(
            ui={"theme": ["dark"], "mode": "secret-value", "font_size_px": True, "density": 4},
            onboarding_completed="false",
            external_editor=22,
        )
        store = SettingsStore(self.path)
        self.assertEqual(store.load(), AppSettings())
        self.assertTrue(store.warnings)
        self.assertNotIn("secret-value", "\n".join(store.warnings))
        self.assertFalse(store.read_only)
        self.assertTrue(self.path.exists())

    def test_wrong_section_types_are_not_coerced(self) -> None:
        for section in ("ui",):
            with self.subTest(section=section):
                self.write_config(**{section: ["secret"]})
                store = SettingsStore(self.path)
                self.assertEqual(store.load(), AppSettings())
                self.assertTrue(store.warnings)

    def test_invalid_root_and_encoding_are_quarantined(self) -> None:
        for payload in (b"[]", b"null", b"1", b"\xff", b'{"schema_version":1,"ui":NaN}'):
            with self.subTest(payload=payload):
                self.path.write_bytes(payload)
                store = SettingsStore(self.path)
                self.assertEqual(store.load(), AppSettings())
                self.assertFalse(self.path.exists())
                self.assertTrue(store.warnings)

    def test_duplicate_keys_are_rejected(self) -> None:
        self.path.write_text('{"schema_version":1,"schema_version":2}', encoding="utf-8")
        store = SettingsStore(self.path)
        self.assertEqual(store.load(), AppSettings())
        self.assertFalse(self.path.exists())

    def test_oversized_config_is_quarantined(self) -> None:
        self.path.write_bytes(b" " * (1024 * 1024 + 1))
        store = SettingsStore(self.path)
        self.assertEqual(store.load(), AppSettings())
        self.assertFalse(self.path.exists())
        self.assertTrue(store.warnings)

    def test_unsupported_or_missing_schema_never_overwritten(self) -> None:
        for schema in (2, "1", True, None):
            with self.subTest(schema=schema):
                self.path.write_text(json.dumps({"schema_version": schema}), encoding="utf-8")
                original = self.path.read_bytes()
                store = SettingsStore(self.path)
                self.assertEqual(store.load(), AppSettings())
                self.assertTrue(store.read_only)
                with self.assertRaises(OSError):
                    store.save(AppSettings(theme="dark"))
                self.assertEqual(self.path.read_bytes(), original)
        self.path.write_text('{"theme":"dark"}', encoding="utf-8")
        store = SettingsStore(self.path)
        self.assertEqual(store.load(), AppSettings())
        self.assertTrue(store.read_only)

    def test_save_without_load_does_not_overwrite_unsupported_schema(self) -> None:
        self.write_config(schema_version=99)
        original = self.path.read_bytes()
        with self.assertRaises(OSError):
            SettingsStore(self.path).save(AppSettings())
        self.assertEqual(self.path.read_bytes(), original)

    def test_quarantine_failure_enters_read_only_mode(self) -> None:
        self.path.write_text("{broken", encoding="utf-8")
        store = SettingsStore(self.path)
        with patch.object(Path, "rename", side_effect=PermissionError("secret path")):
            self.assertEqual(store.load(), AppSettings())
        self.assertTrue(store.read_only)
        with self.assertRaises(OSError):
            store.save(AppSettings())
        self.assertEqual(self.path.read_text(encoding="utf-8"), "{broken")
        self.assertNotIn("secret path", "\n".join(store.warnings))

    def test_unreadable_file_is_not_quarantined_or_overwritten(self) -> None:
        self.write_config()
        store = SettingsStore(self.path)
        with patch.object(Path, "open", side_effect=PermissionError("private")):
            self.assertEqual(store.load(), AppSettings())
        self.assertTrue(store.read_only)
        self.assertTrue(self.path.exists())
        with self.assertRaises(OSError):
            store.save(AppSettings())

    def test_atomic_replace_failure_preserves_original_and_removes_temp(self) -> None:
        store = SettingsStore(self.path)
        store.save(AppSettings())
        original = self.path.read_bytes()
        with patch.object(Path, "replace", side_effect=PermissionError("locked")):
            with self.assertRaises(OSError):
                store.save(AppSettings(theme="dark"))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.glob(".*.tmp")), [])

    def test_flush_failure_preserves_original_and_removes_temp(self) -> None:
        store = SettingsStore(self.path)
        store.save(AppSettings())
        original = self.path.read_bytes()
        with patch("clickgit.settings.os.fsync", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                store.save(AppSettings(theme="dark"))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.glob(".*.tmp")), [])

    def test_invalid_in_memory_settings_do_not_replace_file(self) -> None:
        store = SettingsStore(self.path)
        store.save(AppSettings())
        original = self.path.read_bytes()
        with self.assertRaises(ValueError):
            store.save(AppSettings(theme="invalid"))
        self.assertEqual(self.path.read_bytes(), original)

    def test_project_list_validation(self) -> None:
        project_path = self.path.with_name("projects.json")
        for value in ("D:/repo", [1], [""], ["bad\u0000path"]):
            with self.subTest(value=value):
                project_path.write_text(json.dumps({
                    "schema_version": 1, "recent_repositories": value,
                    "favorite_repositories": ["D:/favorite"],
                }), encoding="utf-8")
                store = SettingsStore(self.path)
                settings = store.load()
                self.assertEqual(settings.recent_repositories, [])
                self.assertEqual(settings.favorite_repositories, ["D:/favorite"])
                self.assertTrue(store.warnings)

    def test_saving_projects_does_not_touch_settings(self) -> None:
        self.write_config(schema_version=99)
        original = self.path.read_bytes()
        store = SettingsStore(self.path)
        settings = store.load()
        settings.recent_repositories = ["D:/repo"]
        store.save_projects(settings)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(SettingsStore(self.path).load().recent_repositories, ["D:/repo"])

    def test_external_change_is_not_silently_overwritten(self) -> None:
        store = SettingsStore(self.path)
        store.save(AppSettings())
        self.write_config(schema_version=99)
        original = self.path.read_bytes()
        with self.assertRaises(OSError):
            store.save(AppSettings(theme="dark"))
        self.assertEqual(self.path.read_bytes(), original)

    def test_repeated_corruption_does_not_replace_previous_quarantine(self) -> None:
        for payload in ("{broken-one", "{broken-two"):
            self.path.write_text(payload, encoding="utf-8")
            SettingsStore(self.path).load()
        backups = list((self.path.parent / "diagnostics").glob("settings.json.*.corrupt"))
        self.assertEqual(
            {backup.read_text(encoding="utf-8") for backup in backups},
            {"{broken-one", "{broken-two"},
        )

    def test_corrupt_projects_do_not_discard_valid_preferences(self) -> None:
        self.write_config(ui={"theme": "dark"})
        project_path = self.path.with_name("projects.json")
        project_path.write_text("[]", encoding="utf-8")
        store = SettingsStore(self.path)
        self.assertEqual(store.load().theme, "dark")
        self.assertFalse(project_path.exists())
        self.assertTrue(store.warnings)
        self.assertTrue(self.path.exists())

    def test_unsupported_projects_survive_partial_save(self) -> None:
        project_path = self.path.with_name("projects.json")
        project_path.write_text('{"schema_version":99}', encoding="utf-8")
        original = project_path.read_bytes()
        store = SettingsStore(self.path)
        store.load()
        with self.assertRaises(OSError):
            store.save(AppSettings(theme="dark"))
        self.assertEqual(project_path.read_bytes(), original)
        self.assertEqual(SettingsStore(self.path).load().theme, "dark")

    def test_later_external_creation_is_not_overwritten(self) -> None:
        store = SettingsStore(self.path)
        store.load()
        self.write_config(ui={"theme": "dark"})
        original = self.path.read_bytes()
        with self.assertRaises(OSError):
            store.save(AppSettings())
        self.assertEqual(self.path.read_bytes(), original)

    def test_ranges_and_string_boundaries(self) -> None:
        for ui in (
            {"font_size_px": 13}, {"font_size_px": 14.0},
            {"theme": "DARK"}, {"density": ""}, {"mode": None},
        ):
            with self.subTest(ui=ui):
                self.write_config(ui=ui)
                store = SettingsStore(self.path)
                self.assertEqual(store.load(), AppSettings())
                self.assertTrue(store.warnings)
        self.write_config(external_editor="a" * 4097)
        store = SettingsStore(self.path)
        self.assertEqual(store.load(), AppSettings())
        self.assertTrue(store.warnings)

    def test_invalid_project_entry_cannot_erase_other_records_on_auto_save(self) -> None:
        path = self.path.with_name("projects.json")
        original = json.dumps({
            "schema_version": 1,
            "favorite_repositories": ["D:/important-favorite", None],
        }).encode("utf-8")
        path.write_bytes(original)
        store = SettingsStore(self.path)
        settings = store.load()
        settings.recent_repositories = ["D:/new"]
        with self.assertRaises(OSError):
            store.save_projects(settings)
        self.assertEqual(path.read_bytes(), original)
        self.assertTrue(store.read_only)

    def test_first_save_also_validates_existing_project_records(self) -> None:
        path = self.path.with_name("projects.json")
        original = b'{"schema_version":1,"favorite_repositories":["D:/keep",null]}'
        path.write_bytes(original)
        with self.assertRaises(OSError):
            SettingsStore(self.path).save_projects(AppSettings())
        self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
