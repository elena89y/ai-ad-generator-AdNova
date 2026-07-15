import argparse
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.database import admin_models, models
from app.database.admin_models import AdminAccount
from app.database.connection import Base, SessionLocal, engine


def main() -> None:
    parser = argparse.ArgumentParser(description="기존 사용자를 관리자 계정으로 등록합니다.")
    parser.add_argument("username", help="관리자로 등록할 사용자 아이디")
    parser.add_argument(
        "--role",
        choices=("super_admin", "operator"),
        default="operator",
        help="관리자 역할 (기본값: operator)",
    )
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.username == args.username).first()
        if user is None:
            raise SystemExit(f"사용자를 찾을 수 없습니다: {args.username}")

        admin_account = (
            db.query(AdminAccount).filter(AdminAccount.user_id == user.id).first()
        )
        if admin_account is None:
            admin_account = AdminAccount(user_id=user.id, role=args.role)
            db.add(admin_account)
        else:
            admin_account.role = args.role
            admin_account.is_active = True

        db.commit()
        print(f"관리자 등록 완료: {user.username} ({admin_account.role})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
