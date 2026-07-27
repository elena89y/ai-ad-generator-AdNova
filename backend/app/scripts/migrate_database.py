"""Apply all pending app/admin database migrations."""

from app.database.connection import admin_engine, engine
from app.database.migrations import run_database_migrations


def main() -> None:
    run_database_migrations(engine, admin_engine)
    print("데이터베이스 마이그레이션이 완료되었습니다.")


if __name__ == "__main__":
    main()
