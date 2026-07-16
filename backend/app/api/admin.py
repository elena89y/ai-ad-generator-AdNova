import json
import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.admin_security import get_current_admin
from app.core.security import get_current_user, hash_password, verify_password
from app.crud.admin import (
    count_advertisements_by_user,
    get_user_for_admin,
    list_users_for_admin,
)
from app.database.admin_models import (
    AdminAccount,
    AdminLog,
    Inquiry,
    RefundRequest,
    utc_now,
)
from app.database.billing_models import PurchaseHistory, Subscription
from app.database.connection import get_db
from app.database.models import User
from app.schemas.admin import (
    AdminInquiryListResponse,
    AdminInquiryReplyRequest,
    AdminInquiryResponse,
    AdminMeResponse,
    AdminMessageResponse,
    AdminPasswordChangeRequest,
    AdminPaymentListResponse,
    AdminPaymentResponse,
    AdminRefundCreateRequest,
    AdminRefundRejectRequest,
    AdminRefundResponse,
    AdminSubscriptionUpdateRequest,
    AdminUserDetailResponse,
    AdminUserListResponse,
    AdminUserResponse,
    AdminUserStatusRequest,
)
from app.schemas.auth import PASSWORD_PATTERN


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
        subscription_id=subscription.id if subscription else None,
    )


@router.get("/users", response_model=AdminUserListResponse)
def read_admin_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: str | None = Query(None, min_length=1, max_length=100),
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminUserListResponse:
    del current_admin
    total, rows = list_users_for_admin(
        db,
        skip=skip,
        limit=limit,
        search=search,
    )
    return AdminUserListResponse(
        total=total,
        items=[_build_admin_user_response(user, subscription) for user, subscription in rows],
    )


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


def _write_admin_log(
    db: Session,
    admin: AdminAccount,
    *,
    action: str,
    target_type: str,
    target_id: int | None,
    before: dict | None = None,
    after: dict | None = None,
    note: str | None = None,
) -> None:
    db.add(
        AdminLog(
            admin_id=admin.id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            before_value=json.dumps(before, ensure_ascii=False) if before else None,
            after_value=json.dumps(after, ensure_ascii=False) if after else None,
            note=note,
        )
    )


@router.patch("/users/{user_id}/status", response_model=AdminUserResponse)
def update_admin_user_status(
    user_id: int,
    request: AdminUserStatusRequest,
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminUserResponse:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")
    if user.id == current_admin.user_id and not request.is_active:
        raise HTTPException(status_code=409, detail="자기 관리자 계정은 정지할 수 없습니다.")

    before = {"is_active": user.is_active}
    user.is_active = request.is_active
    _write_admin_log(
        db,
        current_admin,
        action="user_status_update",
        target_type="user",
        target_id=user.id,
        before=before,
        after={"is_active": user.is_active},
    )
    db.commit()
    db.refresh(user)
    subscription = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    return _build_admin_user_response(user, subscription)


@router.patch(
    "/users/{user_id}/subscription",
    response_model=AdminUserResponse,
)
def update_admin_user_subscription(
    user_id: int,
    request: AdminSubscriptionUpdateRequest,
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminUserResponse:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

    plan = request.plan.strip().lower()
    if plan not in {"free", "premium"}:
        raise HTTPException(status_code=422, detail="지원하지 않는 구독 플랜입니다.")

    subscription = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    before = {
        "plan": subscription.plan if subscription else "free",
        "status": subscription.status if subscription else None,
    }
    if subscription is None:
        subscription = Subscription(user_id=user.id)
        db.add(subscription)

    subscription.plan = plan
    subscription.status = "active" if plan == "premium" else "inactive"
    subscription.cancel_at_period_end = False
    subscription.cancel_requested_at = None
    _write_admin_log(
        db,
        current_admin,
        action="subscription_update",
        target_type="user",
        target_id=user.id,
        before=before,
        after={"plan": subscription.plan, "status": subscription.status},
    )
    db.commit()
    db.refresh(subscription)
    return _build_admin_user_response(user, subscription)


def _latest_refund(db: Session, payment_id: int) -> RefundRequest | None:
    return (
        db.query(RefundRequest)
        .filter(RefundRequest.payment_id == payment_id)
        .order_by(RefundRequest.requested_at.desc())
        .first()
    )


def _build_admin_payment_response(
    db: Session,
    payment: PurchaseHistory,
    user: User,
) -> AdminPaymentResponse:
    refund = _latest_refund(db, payment.id)
    payment_status = payment.status
    if refund and refund.status == "pending":
        payment_status = "refund_pending"
    elif refund and refund.status == "approved":
        payment_status = "refunded"

    return AdminPaymentResponse(
        id=payment.id,
        user_id=user.id,
        order_number=payment.provider_payment_id or f"ADN-{payment.id:08d}",
        user_name=user.name or user.username,
        email=user.email,
        business_name=user.business_name,
        product=payment.description,
        amount=payment.amount,
        currency=payment.currency,
        paid_at=payment.purchased_at,
        status=payment_status,
        refund_id=refund.id if refund else None,
        refund_amount=refund.amount if refund else None,
        refund_reason=refund.reason if refund else None,
        refund_requested_at=refund.requested_at if refund else None,
    )


@router.get("/payments", response_model=AdminPaymentListResponse)
def read_admin_payments(
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    search: str | None = Query(None, max_length=100),
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminPaymentListResponse:
    del current_admin
    query = db.query(PurchaseHistory, User).join(User, User.id == PurchaseHistory.user_id)
    if search:
        keyword = f"%{search}%"
        query = query.filter(
            or_(
                User.username.ilike(keyword),
                User.name.ilike(keyword),
                User.email.ilike(keyword),
                User.business_name.ilike(keyword),
                PurchaseHistory.provider_payment_id.ilike(keyword),
                PurchaseHistory.description.ilike(keyword),
            )
        )
    total = query.count()
    rows = (
        query.order_by(PurchaseHistory.purchased_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return AdminPaymentListResponse(
        total=total,
        items=[_build_admin_payment_response(db, payment, user) for payment, user in rows],
    )


def _build_refund_response(refund: RefundRequest) -> AdminRefundResponse:
    return AdminRefundResponse(
        id=refund.id,
        payment_id=refund.payment_id,
        status=refund.status,
        amount=refund.amount,
        reason=refund.reason,
        rejection_reason=refund.rejection_reason,
        requested_at=refund.requested_at,
        processed_at=refund.processed_at,
    )


@router.post("/refunds", response_model=AdminRefundResponse, status_code=201)
def create_admin_refund(
    request: AdminRefundCreateRequest,
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminRefundResponse:
    payment = db.query(PurchaseHistory).filter(PurchaseHistory.id == request.payment_id).first()
    if payment is None:
        raise HTTPException(status_code=404, detail="결제 내역을 찾을 수 없습니다.")
    if payment.status not in {"paid", "refund_pending"}:
        raise HTTPException(status_code=409, detail="환불할 수 없는 결제 상태입니다.")
    if request.amount > payment.amount:
        raise HTTPException(status_code=422, detail="환불 금액이 결제 금액을 초과합니다.")

    refund = RefundRequest(
        payment_id=payment.id,
        user_id=payment.user_id,
        amount=request.amount,
        reason=request.reason,
        status="approved",
        processed_by=current_admin.id,
        processed_at=utc_now(),
    )
    payment.status = "refunded"
    db.add(refund)
    db.flush()
    _write_admin_log(
        db,
        current_admin,
        action="refund_create",
        target_type="refund",
        target_id=refund.id,
        after={"payment_id": payment.id, "amount": request.amount, "status": "approved"},
        note=request.reason,
    )
    db.commit()
    db.refresh(refund)
    return _build_refund_response(refund)


@router.post("/refunds/{refund_id}/approve", response_model=AdminRefundResponse)
def approve_admin_refund(
    refund_id: int,
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminRefundResponse:
    refund = db.query(RefundRequest).filter(RefundRequest.id == refund_id).first()
    if refund is None:
        raise HTTPException(status_code=404, detail="환불 신청을 찾을 수 없습니다.")
    if refund.status != "pending":
        raise HTTPException(status_code=409, detail="이미 처리된 환불 신청입니다.")

    payment = db.query(PurchaseHistory).filter(PurchaseHistory.id == refund.payment_id).first()
    if payment is None:
        raise HTTPException(status_code=404, detail="결제 내역을 찾을 수 없습니다.")
    refund.status = "approved"
    refund.processed_by = current_admin.id
    refund.processed_at = utc_now()
    payment.status = "refunded"
    _write_admin_log(
        db,
        current_admin,
        action="refund_approve",
        target_type="refund",
        target_id=refund.id,
        before={"status": "pending"},
        after={"status": "approved"},
    )
    db.commit()
    db.refresh(refund)
    return _build_refund_response(refund)


@router.post("/refunds/{refund_id}/reject", response_model=AdminRefundResponse)
def reject_admin_refund(
    refund_id: int,
    request: AdminRefundRejectRequest,
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminRefundResponse:
    refund = db.query(RefundRequest).filter(RefundRequest.id == refund_id).first()
    if refund is None:
        raise HTTPException(status_code=404, detail="환불 신청을 찾을 수 없습니다.")
    if refund.status != "pending":
        raise HTTPException(status_code=409, detail="이미 처리된 환불 신청입니다.")

    payment = db.query(PurchaseHistory).filter(PurchaseHistory.id == refund.payment_id).first()
    refund.status = "rejected"
    refund.rejection_reason = request.reason
    refund.processed_by = current_admin.id
    refund.processed_at = utc_now()
    if payment is not None:
        payment.status = "paid"
    _write_admin_log(
        db,
        current_admin,
        action="refund_reject",
        target_type="refund",
        target_id=refund.id,
        before={"status": "pending"},
        after={"status": "rejected"},
        note=request.reason,
    )
    db.commit()
    db.refresh(refund)
    return _build_refund_response(refund)


def _build_admin_inquiry_response(inquiry: Inquiry, user: User) -> AdminInquiryResponse:
    return AdminInquiryResponse(
        id=inquiry.id,
        user_id=user.id,
        user_name=user.name or user.username,
        email=user.email,
        business_name=user.business_name,
        title=inquiry.title,
        content=inquiry.content,
        status=inquiry.status,
        reply=inquiry.reply,
        created_at=inquiry.created_at,
        answered_at=inquiry.answered_at,
    )


@router.get("/inquiries", response_model=AdminInquiryListResponse)
def read_admin_inquiries(
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminInquiryListResponse:
    del current_admin
    query = db.query(Inquiry, User).join(User, User.id == Inquiry.user_id)
    total = query.count()
    rows = query.order_by(Inquiry.created_at.desc()).offset(skip).limit(limit).all()
    return AdminInquiryListResponse(
        total=total,
        items=[_build_admin_inquiry_response(inquiry, user) for inquiry, user in rows],
    )


@router.post(
    "/inquiries/{inquiry_id}/reply",
    response_model=AdminInquiryResponse,
)
def reply_admin_inquiry(
    inquiry_id: int,
    request: AdminInquiryReplyRequest,
    db: Session = Depends(get_db),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminInquiryResponse:
    row = (
        db.query(Inquiry, User)
        .join(User, User.id == Inquiry.user_id)
        .filter(Inquiry.id == inquiry_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없습니다.")
    inquiry, user = row
    before = {"status": inquiry.status, "reply": inquiry.reply}
    inquiry.reply = request.reply
    inquiry.status = "answered"
    inquiry.answered_by = current_admin.id
    inquiry.answered_at = utc_now()
    _write_admin_log(
        db,
        current_admin,
        action="inquiry_reply",
        target_type="inquiry",
        target_id=inquiry.id,
        before=before,
        after={"status": inquiry.status, "reply": inquiry.reply},
    )
    db.commit()
    db.refresh(inquiry)
    return _build_admin_inquiry_response(inquiry, user)


@router.patch("/password", response_model=AdminMessageResponse)
def change_admin_password(
    request: AdminPasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_admin: AdminAccount = Depends(get_current_admin),
) -> AdminMessageResponse:
    if not verify_password(request.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="현재 비밀번호가 올바르지 않습니다.")
    if not re.match(PASSWORD_PATTERN, request.new_password):
        raise HTTPException(
            status_code=422,
            detail="새 비밀번호는 영문 대소문자, 숫자, 특수문자를 포함해야 합니다.",
        )

    current_user.password_hash = hash_password(request.new_password)
    _write_admin_log(
        db,
        current_admin,
        action="admin_password_change",
        target_type="admin",
        target_id=current_admin.id,
    )
    db.commit()
    return AdminMessageResponse(message="관리자 비밀번호가 변경되었습니다.")
