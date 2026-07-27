import unittest

from sqlalchemy import create_engine, inspect, text

from app.database.migrations import run_database_migrations


class DatabaseMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app_engine = create_engine("sqlite:///:memory:")
        self.admin_engine = create_engine("sqlite:///:memory:")

    def tearDown(self) -> None:
        self.app_engine.dispose()
        self.admin_engine.dispose()

    def test_refund_admin_reference_migration_preserves_rows(self) -> None:
        with self.app_engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE users ("
                    "id INTEGER PRIMARY KEY, email VARCHAR NOT NULL, "
                    "username VARCHAR NOT NULL, password_hash VARCHAR NOT NULL)"
                )
            )
            connection.execute(
                text(
                    "CREATE TABLE purchase_histories ("
                    "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, "
                    "item_type VARCHAR NOT NULL, description VARCHAR NOT NULL, "
                    "amount INTEGER NOT NULL, status VARCHAR NOT NULL, "
                    "FOREIGN KEY(user_id) REFERENCES users(id))"
                )
            )
            connection.execute(
                text(
                    "CREATE TABLE refund_requests ("
                    "id INTEGER PRIMARY KEY, purchase_id INTEGER NOT NULL, "
                    "user_id INTEGER NOT NULL, amount INTEGER NOT NULL, "
                    "reason VARCHAR NOT NULL, status VARCHAR NOT NULL, "
                    "rejection_reason VARCHAR, processed_by_admin_id INTEGER, "
                    "requested_at DATETIME NOT NULL, processed_at DATETIME, "
                    "FOREIGN KEY(purchase_id) REFERENCES purchase_histories(id), "
                    "FOREIGN KEY(user_id) REFERENCES users(id), "
                    "FOREIGN KEY(processed_by_admin_id) REFERENCES users(id))"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(id, email, username, password_hash) "
                    "VALUES (1, 'user@example.com', 'normaluser', 'hash')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO purchase_histories "
                    "(id, user_id, item_type, description, amount, status) "
                    "VALUES (1, 1, 'subscription', 'Premium', 9900, 'paid')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO refund_requests "
                    "(id, purchase_id, user_id, amount, reason, status, "
                    "processed_by_admin_id, requested_at) "
                    "VALUES (1, 1, 1, 9900, 'test', 'approved', 1, CURRENT_TIMESTAMP)"
                )
            )

        run_database_migrations(self.app_engine, self.admin_engine)

        foreign_keys = inspect(self.app_engine).get_foreign_keys("refund_requests")
        processed_by_targets = [
            foreign_key
            for foreign_key in foreign_keys
            if "processed_by_admin_id" in foreign_key["constrained_columns"]
        ]
        with self.app_engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT processed_by_admin_id, anonymized_at "
                    "FROM refund_requests WHERE id = 1"
                )
            ).one()
            applied = connection.execute(
                text("SELECT COUNT(*) FROM schema_migrations")
            ).scalar_one()
            foreign_keys_enabled = connection.execute(
                text("PRAGMA foreign_keys")
            ).scalar_one()

        self.assertEqual(processed_by_targets, [])
        self.assertEqual(row.processed_by_admin_id, 1)
        self.assertIsNone(row.anonymized_at)
        self.assertEqual(applied, 2)
        self.assertEqual(foreign_keys_enabled, 1)

    def test_migrations_are_idempotent(self) -> None:
        run_database_migrations(self.app_engine, self.admin_engine)
        run_database_migrations(self.app_engine, self.admin_engine)

        with self.app_engine.connect() as connection:
            app_versions = connection.execute(
                text("SELECT COUNT(*) FROM schema_migrations")
            ).scalar_one()
        with self.admin_engine.connect() as connection:
            admin_versions = connection.execute(
                text("SELECT COUNT(*) FROM schema_migrations")
            ).scalar_one()

        self.assertEqual(app_versions, 2)
        self.assertEqual(admin_versions, 1)
