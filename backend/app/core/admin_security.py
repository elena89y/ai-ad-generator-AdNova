from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database.admin_models import AdminAccount
from app.database.connection import get_db
from app.database.models import User


def get_current_admin(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AdminAccount:
    admin_account = (
        db.query(AdminAccount)
        .filter(
            AdminAccount.user_id == current_user.id,
            AdminAccount.is_active.is_(True),
        )
        .first()
    )
    if admin_account is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 권한이 필요합니다.",
        )

    return admin_account
