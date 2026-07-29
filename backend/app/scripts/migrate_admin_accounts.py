"""기존 일반 DB 관리자 계정을 관리자 전용 DB로 복사한다."""

from app.database import admin_models  # noqa: F401 - 테이블 메타데이터 등록
from app.database.admin_models import AdminAccount, AdminUser
from app.database.connection import (
    AdminBase,
    AdminSessionLocal,
    SessionLocal,
    admin_engine,
)
from app.database.models import User


def main() -> None:
    AdminBase.metadata.create_all(bind=admin_engine)
    source_db = SessionLocal()
    admin_db = AdminSessionLocal()
    try:
        rows = (
            source_db.query(AdminAccount, User)
            .join(User, User.id == AdminAccount.user_id)
            .all()
        )
        migrated = 0
        skipped = 0

        for legacy_account, user in rows:
            existing = (
                admin_db.query(AdminUser)
                .filter(
                    (AdminUser.username == user.username)
                    | (AdminUser.email == user.email)
                )
                .first()
            )
            if existing is not None:
                skipped += 1
                continue

            admin_db.add(
                AdminUser(
                    username=user.username,
                    email=user.email,
                    password_hash=user.password_hash,
                    name=user.name,
                    role=legacy_account.role,
                    is_active=legacy_account.is_active,
                )
            )
            migrated += 1

        admin_db.commit()
        print(f"관리자 계정 이전 완료: {migrated}개, 이미 존재하여 건너뜀: {skipped}개")
    except Exception:
        admin_db.rollback()
        raise
    finally:
        admin_db.close()
        source_db.close()


if __name__ == "__main__":
    main()
