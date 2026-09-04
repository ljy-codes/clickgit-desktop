from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ProjectMetadataTests(unittest.TestCase):
    def test_project_uses_mit_license_and_repository_urls(self) -> None:
        with (PROJECT_ROOT / "pyproject.toml").open("rb") as pyproject_file:
            pyproject = tomllib.load(pyproject_file)

        project = pyproject["project"]
        with self.subTest(metadata="build-system"):
            self.assertIn(
                "setuptools>=77",
                pyproject["build-system"]["requires"],
            )
        with self.subTest(metadata="license-files"):
            self.assertEqual(project.get("license-files"), ["LICENSE"])
        self.assertEqual(project["license"], "MIT")
        self.assertEqual(project["authors"], [{"name": "ljy-codes"}])
        self.assertCountEqual(
            project["keywords"],
            ["git", "desktop", "gui", "pyside6"],
        )
        self.assertEqual(
            project["urls"]["Repository"],
            "https://github.com/ljy-codes/clickgit-desktop",
        )
        self.assertEqual(
            project["urls"]["Issues"],
            "https://github.com/ljy-codes/clickgit-desktop/issues",
        )

        license_text = (PROJECT_ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertTrue(license_text.startswith("MIT License\n"))
        self.assertIn("Copyright (c) 2026 ljy-codes", license_text)


if __name__ == "__main__":
    unittest.main()
