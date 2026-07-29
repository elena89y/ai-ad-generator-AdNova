import unittest

from sqlalchemy import create_engine, inspect

from app.database import admin_models  # noqa: F401
from app.database.connection import AdminBase


class AdminDatabaseModelTests(unittest.TestCase):
    def test_admin_database_creates_admin_users_table(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        try:
            AdminBase.metadata.create_all(bind=engine)
            table_names = inspect(engine).get_table_names()
            self.assertIn("admin_users", table_names)
            self.assertIn("admin_audit_logs", table_names)
            self.assertIn("admin_login_failure_logs", table_names)
        finally:
            engine.dispose()
