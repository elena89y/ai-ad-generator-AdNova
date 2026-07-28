import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.scripts.migrate_docker_results import migrate_docker_results


class DockerResultMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.database = self.root / "app.db"
        self.source = self.root / "backend" / "results"
        self.destination = self.root / "runtime" / "results"

        source_image = self.source / "ai" / "generated.png"
        source_image.parent.mkdir(parents=True)
        source_image.write_bytes(b"generated-image")

        connection = sqlite3.connect(self.database)
        try:
            connection.execute(
                "CREATE TABLE images (id INTEGER PRIMARY KEY, file_path TEXT)"
            )
            connection.executemany(
                "INSERT INTO images (id, file_path) VALUES (?, ?)",
                [
                    (1, str(source_image)),
                    (2, str(self.source / "ai" / "missing.png")),
                    (3, str(self.root / "uploads" / "input.png")),
                ],
            )
            connection.commit()
        finally:
            connection.close()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_migrates_existing_result_and_preserves_unrelated_paths(self) -> None:
        result = migrate_docker_results(
            self.database,
            self.source,
            self.destination,
        )

        self.assertEqual(result.matched, 2)
        self.assertEqual(result.migrated, 1)
        self.assertEqual(result.missing, 1)
        self.assertIsNotNone(result.backup_path)
        self.assertTrue(result.backup_path.is_file())
        self.assertEqual(
            (self.destination / "ai" / "generated.png").read_bytes(),
            b"generated-image",
        )

        connection = sqlite3.connect(self.database)
        try:
            rows = dict(connection.execute("SELECT id, file_path FROM images"))
        finally:
            connection.close()

        self.assertEqual(rows[1], "/app/results/ai/generated.png")
        self.assertEqual(rows[2], str(self.source / "ai" / "missing.png"))
        self.assertEqual(rows[3], str(self.root / "uploads" / "input.png"))

    def test_dry_run_does_not_change_files_or_database(self) -> None:
        result = migrate_docker_results(
            self.database,
            self.source,
            self.destination,
            dry_run=True,
        )

        self.assertEqual(result.matched, 2)
        self.assertEqual(result.migrated, 0)
        self.assertEqual(result.missing, 1)
        self.assertIsNone(result.backup_path)
        self.assertFalse(self.destination.exists())

        connection = sqlite3.connect(self.database)
        try:
            file_path = connection.execute(
                "SELECT file_path FROM images WHERE id = 1"
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(file_path, str(self.source / "ai" / "generated.png"))
