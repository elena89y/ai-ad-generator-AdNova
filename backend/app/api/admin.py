from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.admin_security import get_current_admin
from app.core.security import get_current_user
from app.crud.admin import (
    count_advertisements_by_user,
    create_admin_audit_log,
    get_purchase_history_for_admin,
    get_admin_summary,
    get_subscription_for_admin,
    get_user_for_admin,
    list_subscriptions_for_admin,
    list_purchase_histories_for_admin,
    list_admin_audit_logs,
    list_users_for_admin,
    refund_demo_purchase_for_admin,
    update_user_active_status,
    update_user_premium_access,
)
from app.crud.inquiry import (
    answer_inquiry,
    get_inquiry_by_id,
    list_inquiries_for_admin,
    update_inquiry_status,
)
from app.database.admin_models import AdminAccount
from app.database.billing_models import Subscription
from app.database.connection import get_db
from app.database.models import User
from app.schemas.admin import (
    AdminAuditLogListResponse,
    AdminAuditLogResponse,
    AdminDemoRefundRequest,
    AdminDemoRefundResponse,
    AdminMeResponse,
    AdminPurchaseHistoryListResponse,
    AdminPurchaseHistoryResponse,
    AdminSubscriptionListResponse,
    AdminSubscriptionResponse,
    AdminUserDetailResponse,
    AdminUserListResponse,
    AdminUserResponse,
    AdminUserStatusUpdateRequest,
    AdminUserSubscriptionUpdateRequest,
    AdminSummaryResponse,
)
from app.schemas.inquiry import (
    AdminInquiryListResponse,
    AdminInquiryResponse,
    InquiryAnswerUpdateRequest,
    InquiryStatusUpdateRequest,
)


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


@router.get("/summary", response_model=AdminSummaryResponse)
def read_admin_summary(
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminSummaryResponse:
    del current_admin
    return AdminSummaryResponse(**get_admin_summary(db))


def _build_admin_user_response(
    user: User,
    subscription: Subscription | None,
) -> AdminUserResponse:
    return AdminUserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        name=user.name,
        business_name=user.business_name,
        is_active=user.is_active,
        created_at=user.created_at,
        plan=subscription.plan if subscription else "free",
        subscription_status=subscription.status if subscription else None,
    )


def _build_admin_purchase_response(
    purchase,
    user: User,
) -> AdminPurchaseHistoryResponse:
    return AdminPurchaseHistoryResponse(
        id=purchase.id,
        user_id=user.id,
        username=user.username,
        email=user.email,
        provider=purchase.provider,
        item_type=purchase.item_type,
        description=purchase.description,
        amount=purchase.amount,
        currency=purchase.currency,
        status=purchase.status,
        purchased_at=purchase.purchased_at,
    )


def _build_admin_subscription_response(
    subscription: Subscription,
    user: User,
) -> AdminSubscriptionResponse:
    return AdminSubscriptionResponse(
        id=subscription.id,
        user_id=user.id,
        username=user.username,
        email=user.email,
        plan=subscription.plan,
        status=subscription.status,
        provider=subscription.provider,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        cancel_at_period_end=subscription.cancel_at_period_end,
        cancel_requested_at=subscription.cancel_requested_at,
    )


def _build_admin_inquiry_response(inquiry, user: User) -> AdminInquiryResponse:
    return AdminInquiryResponse(
        id=inquiry.id,
        user_id=user.id,
        username=user.username,
        email=user.email,
        category=inquiry.category,
        title=inquiry.title,
        content=inquiry.content,
        status=inquiry.status,
        answer=inquiry.answer,
        answered_by_admin_id=inquiry.answered_by_admin_id,
        answered_at=inquiry.answered_at,
        created_at=inquiry.created_at,
        updated_at=inquiry.updated_at,
    )


def _build_admin_audit_log_response(audit_log, user: User) -> AdminAuditLogResponse:
    return AdminAuditLogResponse(
        id=audit_log.id,
        admin_user_id=audit_log.admin_user_id,
        admin_username=user.username,
        action=audit_log.action,
        target_type=audit_log.target_type,
        target_id=audit_log.target_id,
        detail=audit_log.detail,
        created_at=audit_log.created_at,
    )


@router.get("/users", response_model=AdminUserListResponse)
def read_admin_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: str | None = Query(None, min_length=1, max_length=100),
    is_active: bool | None = Query(None),
    plan: Literal["free", "premium"] | None = Query(None),
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminUserListResponse:
    del current_admin
    total, rows = list_users_for_admin(
        db,
        skip=skip,
        limit=limit,
        search=search,
        is_active=is_active,
        plan=plan,
    )
    return AdminUserListResponse(
        total=total,
        items=[_build_admin_user_response(user, subscription) for user, subscription in rows],
    )


@router.get("/purchases", response_model=AdminPurchaseHistoryListResponse)
def read_admin_purchase_histories(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user_id: int | None = Query(None, gt=0),
    search: str | None = Query(None, min_length=1, max_length=100),
    payment_status: str | None = Query(None, min_length=1, max_length=30),
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminPurchaseHistoryListResponse:
    del current_admin
    total, rows = list_purchase_histories_for_admin(
        db,
        skip=skip,
        limit=limit,
        user_id=user_id,
        search=search,
        payment_status=payment_status,
    )
    return AdminPurchaseHistoryListResponse(
        total=total,
        items=[
            _build_admin_purchase_response(purchase, user)
            for purchase, user in rows
        ],
    )


@router.post(
    "/purchases/{purchase_id}/refund",
    response_model=AdminDemoRefundResponse,
)
def refund_admin_demo_purchase(
    purchase_id: int,
    request: AdminDemoRefundRequest,
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminDemoRefundResponse:
    row = get_purchase_history_for_admin(db, purchase_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="구매 내역을 찾을 수 없습니다.",
        )

    purchase, user = row
    if purchase.item_type != "subscription":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="현재는 구독 결제만 환불할 수 있습니다.",
        )
    if purchase.status != "paid":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="환불할 수 있는 결제 내역이 아닙니다.",
        )

    try:
        subscription_revoked = refund_demo_purchase_for_admin(db, purchase)
        create_admin_audit_log(
            db,
            admin_user_id=current_admin.user_id,
            action="purchase.refunded",
            target_type="purchase",
            target_id=purchase.id,
            detail=(
                f"reason={request.reason}; "
                f"subscription_revoked={subscription_revoked}"
            ),
        )
    except Exception:
        db.rollback()
        raise

    return AdminDemoRefundResponse(
        purchase=_build_admin_purchase_response(purchase, user),
        subscription_revoked=subscription_revoked,
    )


@router.get("/purchases/{purchase_id}", response_model=AdminPurchaseHistoryResponse)
def read_admin_purchase_history_detail(
    purchase_id: int,
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminPurchaseHistoryResponse:
    del current_admin
    row = get_purchase_history_for_admin(db, purchase_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="구매 내역을 찾을 수 없습니다.",
        )
    purchase, user = row
    return _build_admin_purchase_response(purchase, user)


@router.get("/subscriptions", response_model=AdminSubscriptionListResponse)
def read_admin_subscriptions(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user_id: int | None = Query(None, gt=0),
    plan: Literal["free", "premium"] | None = Query(None),
    subscription_status: str | None = Query(None, min_length=1, max_length=30),
    search: str | None = Query(None, min_length=1, max_length=100),
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminSubscriptionListResponse:
    del current_admin
    total, rows = list_subscriptions_for_admin(
        db,
        skip=skip,
        limit=limit,
        user_id=user_id,
        plan=plan,
        subscription_status=subscription_status,
        search=search,
    )
    return AdminSubscriptionListResponse(
        total=total,
        items=[
            _build_admin_subscription_response(subscription, user)
            for subscription, user in rows
        ],
    )


@router.get(
    "/subscriptions/{subscription_id}",
    response_model=AdminSubscriptionResponse,
)
def read_admin_subscription_detail(
    subscription_id: int,
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminSubscriptionResponse:
    del current_admin
    row = get_subscription_for_admin(db, subscription_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="구독 정보를 찾을 수 없습니다.",
        )
    subscription, user = row
    return _build_admin_subscription_response(subscription, user)


@router.get("/audit-logs", response_model=AdminAuditLogListResponse)
def read_admin_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    action: str | None = Query(None, min_length=1, max_length=100),
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminAuditLogListResponse:
    del current_admin
    total, rows = list_admin_audit_logs(
        db,
        skip=skip,
        limit=limit,
        action=action,
    )
    return AdminAuditLogListResponse(
        total=total,
        items=[
            _build_admin_audit_log_response(audit_log, user)
            for audit_log, user in rows
        ],
    )


@router.get("/inquiries", response_model=AdminInquiryListResponse)
def read_admin_inquiries(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    inquiry_status: str | None = Query(None, min_length=1, max_length=30),
    search: str | None = Query(None, min_length=1, max_length=100),
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminInquiryListResponse:
    del current_admin
    total, rows = list_inquiries_for_admin(
        db,
        skip=skip,
        limit=limit,
        inquiry_status=inquiry_status,
        search=search,
    )
    return AdminInquiryListResponse(
        total=total,
        items=[
            _build_admin_inquiry_response(inquiry, user)
            for inquiry, user in rows
        ],
    )


@router.get("/inquiries/{inquiry_id}", response_model=AdminInquiryResponse)
def read_admin_inquiry_detail(
    inquiry_id: int,
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminInquiryResponse:
    del current_admin
    inquiry = get_inquiry_by_id(db, inquiry_id)
    if inquiry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="문의를 찾을 수 없습니다.")
    return _build_admin_inquiry_response(inquiry, inquiry.user)


@router.patch("/inquiries/{inquiry_id}/status", response_model=AdminInquiryResponse)
def update_admin_inquiry_status(
    inquiry_id: int,
    request: InquiryStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminInquiryResponse:
    inquiry = get_inquiry_by_id(db, inquiry_id)
    if inquiry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="문의를 찾을 수 없습니다.")
    try:
        inquiry = update_inquiry_status(
            db,
            inquiry,
            inquiry_status=request.status,
            commit=False,
        )
        create_admin_audit_log(
            db,
            admin_user_id=current_admin.user_id,
            action="inquiry.status_updated",
            target_type="inquiry",
            target_id=inquiry.id,
            detail=f"status={request.status}",
        )
    except Exception:
        db.rollback()
        raise
    return _build_admin_inquiry_response(inquiry, inquiry.user)


@router.patch("/inquiries/{inquiry_id}/answer", response_model=AdminInquiryResponse)
def answer_admin_inquiry(
    inquiry_id: int,
    request: InquiryAnswerUpdateRequest,
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminInquiryResponse:
    inquiry = get_inquiry_by_id(db, inquiry_id)
    if inquiry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="문의를 찾을 수 없습니다.")
    try:
        inquiry = answer_inquiry(
            db,
            inquiry,
            answer=request.answer,
            admin_user_id=current_admin.user_id,
            commit=False,
        )
        create_admin_audit_log(
            db,
            admin_user_id=current_admin.user_id,
            action="inquiry.answered",
            target_type="inquiry",
            target_id=inquiry.id,
        )
    except Exception:
        db.rollback()
        raise
    return _build_admin_inquiry_response(inquiry, inquiry.user)


@router.get("/users/{user_id}", response_model=AdminUserDetailResponse)
def read_admin_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminUserDetailResponse:
    del current_admin
    row = get_user_for_admin(db, user_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )

    user, subscription = row
    response = _build_admin_user_response(user, subscription)
    return AdminUserDetailResponse(
        **response.model_dump(),
        business_type=user.business_type,
        updated_at=user.updated_at,
        advertisement_count=count_advertisements_by_user(db, user.id),
    )


@router.patch("/users/{user_id}/status", response_model=AdminUserResponse)
def update_admin_user_status(
    user_id: int,
    request: AdminUserStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminUserResponse:
    if user_id == current_admin.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="현재 로그인한 관리자 계정의 상태는 변경할 수 없습니다.",
        )

    target_admin = (
        db.query(AdminAccount).filter(AdminAccount.user_id == user_id).first()
    )
    if target_admin is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 계정 상태는 이 기능으로 변경할 수 없습니다.",
        )

    row = get_user_for_admin(db, user_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )

    user, subscription = row
    try:
        update_user_active_status(
            db,
            user,
            is_active=request.is_active,
            commit=False,
        )
        create_admin_audit_log(
            db,
            admin_user_id=current_admin.user_id,
            action="user.status_updated",
            target_type="user",
            target_id=user.id,
            detail=f"is_active={request.is_active}",
        )
    except Exception:
        db.rollback()
        raise
    return _build_admin_user_response(user, subscription)


@router.patch("/users/{user_id}/subscription", response_model=AdminUserResponse)
def update_admin_user_subscription(
    user_id: int,
    request: AdminUserSubscriptionUpdateRequest,
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminUserResponse:
    if user_id == current_admin.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="현재 로그인한 관리자 계정의 플랜은 변경할 수 없습니다.",
        )

    target_admin = (
        db.query(AdminAccount).filter(AdminAccount.user_id == user_id).first()
    )
    if target_admin is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 계정 플랜은 이 기능으로 변경할 수 없습니다.",
        )

    if get_user_for_admin(db, user_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )

    try:
        user, subscription = update_user_premium_access(
            db,
            user_id,
            is_premium=request.is_premium,
            commit=False,
        )
        create_admin_audit_log(
            db,
            admin_user_id=current_admin.user_id,
            action="user.subscription_updated",
            target_type="user",
            target_id=user.id,
            detail=f"is_premium={request.is_premium}",
        )
    except Exception:
        db.rollback()
        raise
    return _build_admin_user_response(user, subscription)
