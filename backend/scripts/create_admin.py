import argparse
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.security import hash_password
from app.database import admin_models  # noqa: F401 - 테이블 메타데이터 등록
from app.database.admin_models import AdminUser
from app.database.connection import AdminBase, AdminSessionLocal, admin_engine


def main() -> None:
    parser = argparse.ArgumentParser(description="관리자 전용 DB에 계정을 생성하거나 갱신합니다.")
    parser.add_argument("username", help="관리자 아이디")
    parser.add_argument("email", help="관리자 이메일")
    parser.add_argument("password", help="관리자 비밀번호")
    parser.add_argument(
        "--role",
        choices=("super_admin", "operator"),
        default="operator",
        help="관리자 역할 (기본값: operator)",
    )
    args = parser.parse_args()

    AdminBase.metadata.create_all(bind=admin_engine)
    db = AdminSessionLocal()
    try:
        admin = db.query(AdminUser).filter(AdminUser.username == args.username).first()
        if admin is None:
            admin = AdminUser(
                username=args.username,
                email=args.email,
                password_hash=hash_password(args.password),
                role=args.role,
                is_active=True,
            )
            db.add(admin)
        else:
            admin.email = args.email
            admin.password_hash = hash_password(args.password)
            admin.role = args.role
            admin.is_active = True

        db.commit()
        print(f"관리자 계정 준비 완료: {admin.username} ({admin.role})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
