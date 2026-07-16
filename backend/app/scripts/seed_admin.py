import os

from app.core.security import hash_password
from app.database import billing_models  # noqa: F401 - 테이블 메타데이터 등록
from app.database.admin_models import AdminAccount
from app.database.connection import Base, SessionLocal, engine
from app.database.models import User


def main() -> None:
    username = os.getenv("ADMIN_USERNAME", "admin").lower()
    password = os.getenv("ADMIN_PASSWORD", "admin")
    email = os.getenv("ADMIN_EMAIL", "admin@adnova.local").lower()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if user is None:
            user = User(
                username=username,
                email=email,
                password_hash=hash_password(password),
                name="AdNova 관리자",
                business_name="AdNova",
                business_type="서비스 운영",
                is_active=True,
            )
            db.add(user)
            db.flush()
        else:
            user.password_hash = hash_password(password)
            user.is_active = True

        admin = db.query(AdminAccount).filter(AdminAccount.user_id == user.id).first()
        if admin is None:
            admin = AdminAccount(user_id=user.id, role="admin", is_active=True)
            db.add(admin)
        else:
            admin.role = "admin"
            admin.is_active = True

        db.commit()
        print(f"관리자 계정 준비 완료: {username}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
