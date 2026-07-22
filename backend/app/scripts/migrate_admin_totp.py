"""기존 관리자 DB에 TOTP 컬럼을 추가한다."""

from sqlalchemy import inspect, text

from app.database import admin_models  # noqa: F401 - 테이블 메타데이터 등록
from app.database.connection import AdminBase, admin_engine


def main() -> None:
    AdminBase.metadata.create_all(bind=admin_engine)
    columns = {
        column["name"]
        for column in inspect(admin_engine).get_columns("admin_users")
    }
    statements = []
    if "totp_secret_encrypted" not in columns:
        statements.append(
            "ALTER TABLE admin_users ADD COLUMN totp_secret_encrypted VARCHAR(255)"
        )
    if "totp_enabled" not in columns:
        statements.append(
            "ALTER TABLE admin_users ADD COLUMN totp_enabled BOOLEAN NOT NULL DEFAULT 0"
        )

    with admin_engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))

    if statements:
        print("관리자 TOTP 컬럼 추가 완료")
    else:
        print("관리자 TOTP 컬럼이 이미 준비되어 있습니다.")


if __name__ == "__main__":
    main()
