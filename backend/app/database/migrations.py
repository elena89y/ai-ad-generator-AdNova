"""Small, versioned database migrations for the app and admin databases."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, MetaData, String, Table, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.schema import CreateIndex, CreateTable

from app.database.billing_models import RefundRequest
from app.scripts.migrate_admin_totp import ensure_admin_totp_columns
from app.scripts.migrate_retention import ensure_retention_columns

Migration = tuple[str, Callable[[Engine], None]]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _migration_table() -> Table:
    metadata = MetaData()
    return Table(
        "schema_migrations",
        metadata,
        Column("version", String(100), primary_key=True),
        Column("applied_at", DateTime(timezone=True), nullable=False),
    )


def _remove_refund_admin_user_foreign_key(bind: Engine) -> None:
    """Remove the cross-database admin id -> users.id foreign key."""
    inspector = inspect(bind)
    if "refund_requests" not in inspector.get_table_names():
        return

    has_invalid_foreign_key = any(
        foreign_key.get("referred_table") == "users"
        and "processed_by_admin_id" in foreign_key.get("constrained_columns", [])
        for foreign_key in inspector.get_foreign_keys("refund_requests")
    )
    if not has_invalid_foreign_key:
        return
    if bind.dialect.name != "sqlite":
        raise RuntimeError(
            "refund_requests 외래 키 변경은 현재 SQLite 마이그레이션만 지원합니다."
        )
    if "_refund_requests_legacy" in inspector.get_table_names():
        raise RuntimeError(
            "중단된 refund_requests 마이그레이션 테이블이 남아 있습니다."
        )

    current_columns = [column["name"] for column in inspector.get_columns("refund_requests")]
    target_columns = [column.name for column in RefundRequest.__table__.columns]
    common_columns = [column for column in target_columns if column in current_columns]
    quote = bind.dialect.identifier_preparer.quote
    column_list = ", ".join(quote(column) for column in common_columns)
    create_table_sql = str(CreateTable(RefundRequest.__table__).compile(dialect=bind.dialect))

    raw_connection = bind.raw_connection()
    cursor = raw_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute(
            f"ALTER TABLE {quote('refund_requests')} "
            f"RENAME TO {quote('_refund_requests_legacy')}"
        )
        cursor.execute(create_table_sql)
        cursor.execute(
            f"INSERT INTO {quote('refund_requests')} ({column_list}) "
            f"SELECT {column_list} FROM {quote('_refund_requests_legacy')}"
        )
        cursor.execute(f"DROP TABLE {quote('_refund_requests_legacy')}")
        for index in sorted(RefundRequest.__table__.indexes, key=lambda item: item.name or ""):
            cursor.execute(str(CreateIndex(index).compile(dialect=bind.dialect)))
        raw_connection.commit()
    except Exception:
        raw_connection.rollback()
        raise
    finally:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
        raw_connection.close()


APP_MIGRATIONS: tuple[Migration, ...] = (
    ("2026072101_retention_columns", ensure_retention_columns),
    ("2026072701_refund_admin_reference", _remove_refund_admin_user_foreign_key),
)

ADMIN_MIGRATIONS: tuple[Migration, ...] = (
    ("2026072701_admin_totp_columns", ensure_admin_totp_columns),
)


def _run_migrations(bind: Engine, migrations: tuple[Migration, ...]) -> None:
    migration_table = _migration_table()
    migration_table.create(bind=bind, checkfirst=True)

    with bind.connect() as connection:
        applied = set(connection.execute(select(migration_table.c.version)).scalars())

    for version, migration in migrations:
        if version in applied:
            continue
        migration(bind)
        with bind.begin() as connection:
            connection.execute(
                migration_table.insert().values(version=version, applied_at=utc_now())
            )


def run_database_migrations(app_bind: Engine, admin_bind: Engine) -> None:
    """Apply pending migrations to both databases in version order."""
    _run_migrations(app_bind, APP_MIGRATIONS)
    _run_migrations(admin_bind, ADMIN_MIGRATIONS)
