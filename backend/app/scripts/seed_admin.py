import os

from app.core.security import hash_password
from app.database import admin_models  # noqa: F401 - 테이블 메타데이터 등록
from app.database.admin_models import AdminUser
from app.database.connection import AdminBase, AdminSessionLocal, admin_engine


def main() -> None:
    username = os.getenv("ADMIN_USERNAME", "admin").lower()
    password = os.getenv("ADMIN_PASSWORD", "admin")
    email = os.getenv("ADMIN_EMAIL", "admin@adnova.local").lower()

    AdminBase.metadata.create_all(bind=admin_engine)
    db = AdminSessionLocal()
    try:
        admin = db.query(AdminUser).filter(AdminUser.username == username).first()
        if admin is None:
            admin = AdminUser(
                username=username,
                email=email,
                password_hash=hash_password(password),
                name="AdNova 관리자",
                role="super_admin",
                is_active=True,
            )
            db.add(admin)
        else:
            admin.email = email
            admin.password_hash = hash_password(password)
            admin.role = "super_admin"
            admin.is_active = True

        db.commit()
        print(f"관리자 계정 준비 완료: {username}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
