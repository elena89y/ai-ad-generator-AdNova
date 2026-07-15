from fastapi import APIRouter, Depends

from app.core.admin_security import get_current_admin
from app.core.security import get_current_user
from app.database.admin_models import AdminAccount
from app.database.models import User
from app.schemas.admin import AdminMeResponse


router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/me", response_model=AdminMeResponse)
def read_admin_me(
    current_user: User = Depends(get_current_user),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminMeResponse:
    return AdminMeResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        role=current_admin.role,
    )
