from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.crud.billing import (
    get_payment_method_by_user,
    get_subscription_by_user,
    list_purchase_histories_by_user,
    resume_subscription,
    schedule_subscription_cancellation,
)
from app.database.billing_models import Subscription
from app.database.connection import get_db
from app.database.models import User
from app.schemas.billing import BillingSummaryResponse, PurchaseHistoryResponse


router = APIRouter(prefix="/billing", tags=["billing"])


def _is_premium(subscription: Subscription | None) -> bool:
    return bool(
        subscription
        and subscription.plan == "premium"
        and subscription.status == "active"
    )


def _build_summary(db: Session, user_id: int) -> BillingSummaryResponse:
    subscription = get_subscription_by_user(db, user_id)
    payment_method = get_payment_method_by_user(db, user_id)
    return BillingSummaryResponse(
        is_premium=_is_premium(subscription),
        subscription=subscription,
        payment_method=payment_method,
    )


@router.get("/summary", response_model=BillingSummaryResponse)
def read_billing_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BillingSummaryResponse:
    return _build_summary(db, current_user.id)


@router.get("/purchases", response_model=list[PurchaseHistoryResponse])
def read_purchase_histories(
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PurchaseHistoryResponse]:
    return list_purchase_histories_by_user(db, current_user.id, limit=limit)


@router.post("/subscription/cancel", response_model=BillingSummaryResponse)
def cancel_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BillingSummaryResponse:
    subscription = get_subscription_by_user(db, current_user.id)
    if not _is_premium(subscription):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="해지할 활성 구독이 없습니다.",
        )

    schedule_subscription_cancellation(db, subscription)
    return _build_summary(db, current_user.id)


@router.post("/subscription/resume", response_model=BillingSummaryResponse)
def resume_canceled_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BillingSummaryResponse:
    subscription = get_subscription_by_user(db, current_user.id)
    if not _is_premium(subscription) or not subscription.cancel_at_period_end:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="취소할 해지 예약이 없습니다.",
        )

    resume_subscription(db, subscription)
    return _build_summary(db, current_user.id)


@router.post("/payment-method/change-session")
def create_payment_method_change_session(
    current_user: User = Depends(get_current_user),
) -> None:
    del current_user
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="결제 방법 변경은 결제사 연동 후 사용할 수 있습니다.",
    )
