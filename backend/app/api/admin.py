import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.admin_security import get_current_admin, get_current_super_admin
from app.core.email import send_inquiry_answer_email, send_inquiry_status_email
from app.core.security import hash_password, verify_password
from app.core.totp import (
    build_totp_provisioning_uri,
    build_totp_qr_code_data_url,
    encrypt_totp_secret,
    generate_totp_secret,
    verify_totp_code,
)
from app.crud.admin import (
    count_active_super_admins,
    count_advertisements_by_user,
    create_admin_audit_log,
    create_admin_user_account,
    get_advertisement_for_admin,
    get_admin_account_by_id,
    get_purchase_history_for_admin,
    get_admin_summary,
    get_subscription_for_admin,
    get_user_for_admin,
    list_admin_accounts,
    list_subscriptions_for_admin,
    list_purchase_histories_for_admin,
    list_admin_audit_logs,
    list_admin_login_failure_logs,
    list_advertisements_for_admin,
    list_users_for_admin,
    refund_demo_purchase_for_admin,
    update_admin_account_active_status,
    update_admin_account_role,
    update_user_active_status,
    update_user_premium_access,
)
from app.crud.billing import get_demo_credit_pack_credits
from app.crud.chatbot_stats import get_chatbot_stats
from app.crud.credits import get_bonus_credits_remaining, grant_bonus_credits
from app.crud.history import (
    delete_generated_image_files,
    delete_generated_result_by_advertisement,
)
from app.crud.faq_candidate import (
    create_faq_candidate,
    get_faq_candidate_by_id,
    has_active_candidate_for_inquiry,
    list_faq_candidates_for_admin,
    update_faq_candidate_status,
)
from app.crud.inquiry import (
    answer_inquiry,
    get_inquiry_by_id,
    list_inquiries_for_admin,
    update_inquiry_status,
)
from app.crud.report import (
    get_report_by_id,
    list_reports_for_admin,
    update_report_status,
)
from app.crud.notice import (
    create_notice,
    delete_notice,
    get_notice_by_id,
    list_notices_for_admin,
    update_notice,
)
from app.services.notification_service import send_marketing_notifications
from app.database.admin_models import AdminUser
from app.database.billing_models import PurchaseHistory, RefundRequest, Subscription, utc_now
from app.database.connection import get_admin_db, get_db
from app.database.models import User
from app.schemas.admin import (
    AdminAccountCreateRequest,
    AdminAccountListResponse,
    AdminAccountResponse,
    AdminAccountRoleUpdateRequest,
    AdminAccountStatusUpdateRequest,
    AdminAuditLogListResponse,
    AdminAuditLogResponse,
    AdminAdvertisementListResponse,
    AdminAdvertisementResponse,
    AdminBonusCreditGrantRequest,
    AdminBonusCreditGrantResponse,
    AdminDemoRefundRequest,
    AdminDemoRefundResponse,
    AdminMeResponse,
    AdminPurchaseHistoryListResponse,
    AdminPurchaseHistoryResponse,
    AdminSubscriptionListResponse,
    AdminSubscriptionResponse,
    AdminTotpDisableRequest,
    AdminTotpSetupRequest,
    AdminTotpSetupResponse,
    AdminTotpVerifyRequest,
    AdminUserDetailResponse,
    AdminUserListResponse,
    AdminUserResponse,
    AdminUserStatusUpdateRequest,
    AdminUserSubscriptionUpdateRequest,
    AdminSummaryResponse,
    AdminRefundListResponse,
    AdminRefundRejectRequest,
    AdminRefundResponse,
    AdminPasswordChangeRequest,
    AdminMessageResponse,
    AdminMarketingNotificationRequest,
    AdminMarketingNotificationResponse,
    AdminChatbotStatsResponse,
    AdminFaqCandidateListResponse,
    AdminFaqCandidateResponse,
    FaqCandidateStatusUpdateRequest,
)
from app.schemas.inquiry import (
    AdminInquiryListResponse,
    AdminInquiryResponse,
    InquiryAnswerUpdateRequest,
    InquiryStatusUpdateRequest,
)
from app.schemas.report import (
    AdminReportListResponse,
    AdminReportResponse,
    ReportStatusUpdateRequest,
)
from app.schemas.notice import (
    AdminNoticeListResponse,
    AdminNoticeResponse,
    NoticeCreateRequest,
    NoticeUpdateRequest,
)


router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger(__name__)


@router.post(
    "/notifications/marketing",
    response_model=AdminMarketingNotificationResponse,
)
def send_admin_marketing_notification(
    request: AdminMarketingNotificationRequest,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    current_admin: AdminUser = Depends(get_current_super_admin),
) -> AdminMarketingNotificationResponse:
    eligible_count, sent_count, failed_count = send_marketing_notifications(
        db,
        subject=request.subject,
        message=request.message,
        audience=request.audience,
        user_ids=request.user_ids,
    )
    create_admin_audit_log(
        admin_db,
        admin_user_id=current_admin.id,
        action="notification.marketing_sent",
        target_type="notification",
        target_id=0,
        detail=(
            f"audience={request.audience}; eligible={eligible_count}; "
            f"sent={sent_count}; failed={failed_count}"
        ),
    )
    return AdminMarketingNotificationResponse(
        eligible_count=eligible_count,
        sent_count=sent_count,
        failed_count=failed_count,
    )


def _build_refund_response(refund: RefundRequest, purchase: PurchaseHistory, user: User) -> AdminRefundResponse:
    return AdminRefundResponse(
        id=refund.id,
        purchase_id=purchase.id,
        user_id=user.id,
        username=user.username,
        email=user.email,
        description=purchase.description,
        amount=refund.amount,
        reason=refund.reason,
        status=refund.status,
        rejection_reason=refund.rejection_reason,
        requested_at=refund.requested_at,
        processed_at=refund.processed_at,
    )


@router.get("/me", response_model=AdminMeResponse)
def read_admin_me(
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminMeResponse:
    return AdminMeResponse(
        id=current_admin.id,
        username=current_admin.username,
        email=current_admin.email,
        role=current_admin.role,
        totp_enabled=current_admin.totp_enabled,
    )


def _build_admin_account_response(
    admin_account: AdminUser,
) -> AdminAccountResponse:
    return AdminAccountResponse(
        id=admin_account.id,
        user_id=admin_account.id,
        username=admin_account.username,
        email=admin_account.email,
        name=admin_account.name,
        role=admin_account.role,
        is_active=admin_account.is_active,
        created_at=admin_account.created_at,
        updated_at=admin_account.updated_at,
    )


@router.post(
    "/accounts",
    response_model=AdminAccountResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_admin_account_by_super_admin(
    request: AdminAccountCreateRequest,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    current_admin: AdminUser = Depends(get_current_super_admin),
) -> AdminAccountResponse:
    if admin_db.query(AdminUser).filter(AdminUser.email == str(request.email)).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 사용 중인 관리자 이메일입니다.",
        )
    if admin_db.query(AdminUser).filter(AdminUser.username == request.username).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 사용 중인 관리자 아이디입니다.",
        )
    if db.query(User).filter(User.email == str(request.email)).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="일반 사용자와 같은 이메일은 관리자 계정에 사용할 수 없습니다.",
        )
    if db.query(User).filter(User.username == request.username).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="일반 사용자와 같은 아이디는 관리자 계정에 사용할 수 없습니다.",
        )

    try:
        admin_account = create_admin_user_account(
            admin_db,
            email=str(request.email),
            username=request.username,
            password_hash=hash_password(request.password),
            name=request.name,
            role=request.role,
        )
        create_admin_audit_log(
            admin_db,
            admin_user_id=current_admin.id,
            action="admin.account_created",
            target_type="admin_account",
            target_id=admin_account.id,
            detail=f"username={admin_account.username}, role={request.role}",
        )
    except IntegrityError as exc:
        admin_db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 사용 중인 이메일 또는 아이디입니다.",
        ) from exc
    except Exception:
        admin_db.rollback()
        raise

    return _build_admin_account_response(admin_account)


@router.get("/accounts", response_model=AdminAccountListResponse)
def read_admin_accounts(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: str | None = Query(None, min_length=1, max_length=100),
    admin_db: Session = Depends(get_admin_db),
    current_admin: AdminUser = Depends(get_current_super_admin),
) -> AdminAccountListResponse:
    del current_admin
    total, rows = list_admin_accounts(
        admin_db,
        skip=skip,
        limit=limit,
        search=search,
    )
    return AdminAccountListResponse(
        total=total,
        items=[_build_admin_account_response(admin_account) for admin_account in rows],
    )


@router.patch(
    "/accounts/{admin_account_id}/role",
    response_model=AdminAccountResponse,
)
def update_admin_account_role_by_super_admin(
    admin_account_id: int,
    request: AdminAccountRoleUpdateRequest,
    admin_db: Session = Depends(get_admin_db),
    current_admin: AdminUser = Depends(get_current_super_admin),
) -> AdminAccountResponse:
    target_admin = get_admin_account_by_id(admin_db, admin_account_id)
    if target_admin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="관리자 계정을 찾을 수 없습니다.",
        )

    if target_admin.id == current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="현재 로그인한 관리자 역할은 변경할 수 없습니다.",
        )
    if (
        target_admin.role == "super_admin"
        and target_admin.is_active
        and request.role != "super_admin"
        and count_active_super_admins(admin_db) <= 1
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="활성 최고 관리자는 최소 한 명 이상 필요합니다.",
        )

    try:
        update_admin_account_role(
            admin_db,
            target_admin,
            role=request.role,
            commit=False,
        )
        create_admin_audit_log(
            admin_db,
            admin_user_id=current_admin.id,
            action="admin.role_updated",
            target_type="admin_account",
            target_id=target_admin.id,
            detail=f"role={request.role}",
        )
    except Exception:
        admin_db.rollback()
        raise

    return _build_admin_account_response(target_admin)


@router.patch(
    "/accounts/{admin_account_id}/status",
    response_model=AdminAccountResponse,
)
def update_admin_account_status_by_super_admin(
    admin_account_id: int,
    request: AdminAccountStatusUpdateRequest,
    admin_db: Session = Depends(get_admin_db),
    current_admin: AdminUser = Depends(get_current_super_admin),
) -> AdminAccountResponse:
    target_admin = get_admin_account_by_id(admin_db, admin_account_id)
    if target_admin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="관리자 계정을 찾을 수 없습니다.",
        )

    if target_admin.id == current_admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="현재 로그인한 관리자 계정 상태는 변경할 수 없습니다.",
        )
    if (
        target_admin.role == "super_admin"
        and target_admin.is_active
        and not request.is_active
        and count_active_super_admins(admin_db) <= 1
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="활성 최고 관리자는 최소 한 명 이상 필요합니다.",
        )

    try:
        update_admin_account_active_status(
            admin_db,
            target_admin,
            is_active=request.is_active,
            commit=False,
        )
        create_admin_audit_log(
            admin_db,
            admin_user_id=current_admin.id,
            action="admin.status_updated",
            target_type="admin_account",
            target_id=target_admin.id,
            detail=f"is_active={request.is_active}",
        )
    except Exception:
        admin_db.rollback()
        raise

    return _build_admin_account_response(target_admin)


@router.get("/summary", response_model=AdminSummaryResponse)
def read_admin_summary(
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminSummaryResponse:
    del current_admin
    return AdminSummaryResponse(**get_admin_summary(db))


def _build_admin_user_response(
    user: User,
    subscription: Subscription | None,
) -> AdminUserResponse:
    is_premium = bool(
        subscription
        and subscription.plan == "premium"
        and subscription.status == "active"
    )
    return AdminUserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        name=user.name,
        business_name=user.business_name,
        is_active=user.is_active,
        created_at=user.created_at,
        plan="premium" if is_premium else "free",
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


def _build_admin_report_response(report, user: User) -> AdminReportResponse:
    return AdminReportResponse(
        id=report.id,
        user_id=user.id,
        username=user.username,
        email=user.email,
        category=report.category,
        title=report.title,
        content=report.content,
        advertisement_id=report.advertisement_id,
        status=report.status,
        admin_note=report.admin_note,
        handled_by_admin_id=report.handled_by_admin_id,
        handled_at=report.handled_at,
        created_at=report.created_at,
        updated_at=report.updated_at,
    )


def _build_admin_notice_response(notice) -> AdminNoticeResponse:
    return AdminNoticeResponse(
        id=notice.id,
        title=notice.title,
        content=notice.content,
        is_published=notice.is_published,
        published_at=notice.published_at,
        created_by_admin_id=notice.created_by_admin_id,
        updated_by_admin_id=notice.updated_by_admin_id,
        created_at=notice.created_at,
        updated_at=notice.updated_at,
    )


def _build_admin_audit_log_response(
    audit_log,
    admin_user: AdminUser,
) -> AdminAuditLogResponse:
    return AdminAuditLogResponse(
        id=audit_log.id,
        source="admin_action",
        admin_user_id=audit_log.admin_user_id,
        admin_username=admin_user.username,
        action=audit_log.action,
        target_type=audit_log.target_type,
        target_id=audit_log.target_id,
        detail=audit_log.detail,
        created_at=audit_log.created_at,
    )


def _build_admin_login_failure_log_response(login_failure_log) -> AdminAuditLogResponse:
    return AdminAuditLogResponse(
        id=login_failure_log.id,
        source="login_failure",
        admin_user_id=login_failure_log.admin_user_id,
        admin_username=login_failure_log.attempted_username,
        action="admin.login_failed",
        target_type="admin_login",
        target_id=login_failure_log.admin_user_id,
        detail=login_failure_log.reason,
        created_at=login_failure_log.created_at,
    )


def _build_admin_advertisement_response(
    advertisement,
    user: User,
) -> AdminAdvertisementResponse:
    output_image = advertisement.output_image
    return AdminAdvertisementResponse(
        id=advertisement.id,
        user_id=user.id,
        username=user.username,
        email=user.email,
        title=advertisement.title,
        ad_type=advertisement.ad_type,
        style=advertisement.style,
        status=advertisement.status,
        prompt=advertisement.prompt,
        generated_text=advertisement.generated_text,
        error_message=advertisement.error_message,
        output_image_id=advertisement.output_image_id,
        output_image_url=output_image.image_url if output_image else None,
        created_at=advertisement.created_at,
        updated_at=advertisement.updated_at,
    )


@router.get("/advertisements", response_model=AdminAdvertisementListResponse)
def read_admin_advertisements(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user_id: int | None = Query(None, gt=0),
    search: str | None = Query(None, min_length=1, max_length=100),
    status: str | None = Query(None, min_length=1, max_length=50),
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminAdvertisementListResponse:
    del current_admin
    total, rows = list_advertisements_for_admin(
        db,
        skip=skip,
        limit=limit,
        user_id=user_id,
        search=search,
        status=status,
    )
    return AdminAdvertisementListResponse(
        total=total,
        items=[
            _build_admin_advertisement_response(advertisement, user)
            for advertisement, user in rows
        ],
    )


@router.get(
    "/advertisements/{advertisement_id}",
    response_model=AdminAdvertisementResponse,
)
def read_admin_advertisement_detail(
    advertisement_id: int,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminAdvertisementResponse:
    del current_admin
    row = get_advertisement_for_admin(db, advertisement_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="광고를 찾을 수 없습니다.",
        )

    advertisement, user = row
    return _build_admin_advertisement_response(advertisement, user)


@router.delete(
    "/advertisements/{advertisement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_admin_advertisement(
    advertisement_id: int,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    current_admin: AdminUser = Depends(get_current_super_admin),
) -> None:
    row = get_advertisement_for_admin(db, advertisement_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="광고를 찾을 수 없습니다.",
        )

    advertisement, user = row
    try:
        generated_file_paths = delete_generated_result_by_advertisement(
            db,
            advertisement,
            commit=False,
        )
        create_admin_audit_log(
            admin_db,
            admin_user_id=current_admin.id,
            action="advertisement.force_deleted",
            target_type="advertisement",
            target_id=advertisement_id,
            detail=f"user_id={user.id}; generated_file_count={len(generated_file_paths)}",
            commit=False,
        )
        db.commit()
        admin_db.commit()
    except Exception:
        db.rollback()
        admin_db.rollback()
        raise

    delete_generated_image_files(generated_file_paths)


@router.get("/users", response_model=AdminUserListResponse)
def read_admin_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    search: str | None = Query(None, min_length=1, max_length=100),
    is_active: bool | None = Query(None),
    plan: Literal["free", "premium"] | None = Query(None),
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
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
    current_admin: AdminUser = Depends(get_current_admin),
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
    admin_db: Session = Depends(get_admin_db),
    current_admin: AdminUser = Depends(get_current_super_admin),
) -> AdminDemoRefundResponse:
    row = get_purchase_history_for_admin(db, purchase_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="구매 내역을 찾을 수 없습니다.",
        )

    purchase, user = row
    if purchase.provider != "demo":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="데모 결제 내역만 환불할 수 있습니다.",
        )
    if purchase.item_type not in {"subscription", "credit_pack"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="구독 또는 크레딧 구매 내역만 환불할 수 있습니다.",
        )
    if purchase.item_type == "credit_pack" and get_demo_credit_pack_credits(purchase.description) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="확인할 수 없는 크레딧 상품은 환불할 수 없습니다.",
        )
    if purchase.status != "paid":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="환불할 수 있는 결제 내역이 아닙니다.",
        )

    try:
        subscription_revoked, purchased_credits_revoked = refund_demo_purchase_for_admin(db, purchase)
        refund_record = RefundRequest(
            purchase_id=purchase.id,
            user_id=user.id,
            amount=purchase.amount,
            reason=request.reason.strip(),
            status="approved",
            processed_by_admin_id=current_admin.id,
            processed_at=utc_now(),
        )
        db.add(refund_record)
        create_admin_audit_log(
            admin_db,
            admin_user_id=current_admin.id,
            action="purchase.refunded",
            target_type="purchase",
            target_id=purchase.id,
            detail=(
                f"reason={request.reason}; "
                f"subscription_revoked={subscription_revoked}; "
                f"purchased_credits_revoked={purchased_credits_revoked}"
            ),
        )
        db.commit()
    except Exception:
        db.rollback()
        admin_db.rollback()
        raise

    return AdminDemoRefundResponse(
        purchase=_build_admin_purchase_response(purchase, user),
        subscription_revoked=subscription_revoked,
        purchased_credits_revoked=purchased_credits_revoked,
    )


@router.get("/purchases/{purchase_id}", response_model=AdminPurchaseHistoryResponse)
def read_admin_purchase_history_detail(
    purchase_id: int,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
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
    current_admin: AdminUser = Depends(get_current_admin),
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
    current_admin: AdminUser = Depends(get_current_admin),
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
    admin_db: Session = Depends(get_admin_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminAuditLogListResponse:
    del current_admin
    if action == "admin.login_failed":
        total, login_failure_logs = list_admin_login_failure_logs(
            admin_db,
            skip=skip,
            limit=limit,
        )
        return AdminAuditLogListResponse(
            total=total,
            items=[
                _build_admin_login_failure_log_response(login_failure_log)
                for login_failure_log in login_failure_logs
            ],
        )

    if action:
        total, rows = list_admin_audit_logs(
            admin_db,
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

    fetch_limit = skip + limit
    admin_action_total, rows = list_admin_audit_logs(
        admin_db,
        skip=0,
        limit=fetch_limit,
    )
    login_failure_total, login_failure_logs = list_admin_login_failure_logs(
        admin_db,
        skip=0,
        limit=fetch_limit,
    )
    combined_logs = [
        _build_admin_audit_log_response(audit_log, user)
        for audit_log, user in rows
    ]
    combined_logs.extend(
        _build_admin_login_failure_log_response(login_failure_log)
        for login_failure_log in login_failure_logs
    )
    combined_logs.sort(key=lambda log: log.created_at, reverse=True)
    return AdminAuditLogListResponse(
        total=admin_action_total + login_failure_total,
        items=combined_logs[skip : skip + limit],
    )


@router.get("/inquiries", response_model=AdminInquiryListResponse)
def read_admin_inquiries(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    inquiry_status: str | None = Query(None, min_length=1, max_length=30),
    search: str | None = Query(None, min_length=1, max_length=100),
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
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
    current_admin: AdminUser = Depends(get_current_admin),
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
    admin_db: Session = Depends(get_admin_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminInquiryResponse:
    inquiry = get_inquiry_by_id(db, inquiry_id)
    if inquiry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="문의를 찾을 수 없습니다.")
    previous_status = inquiry.status
    try:
        inquiry = update_inquiry_status(
            db,
            inquiry,
            inquiry_status=request.status,
            commit=False,
        )
        create_admin_audit_log(
            admin_db,
            admin_user_id=current_admin.id,
            action="inquiry.status_updated",
            target_type="inquiry",
            target_id=inquiry.id,
            detail=f"status={request.status}",
        )
        db.commit()
    except Exception:
        db.rollback()
        admin_db.rollback()
        raise
    if inquiry.status != previous_status and inquiry.user.is_active:
        try:
            send_inquiry_status_email(
                inquiry.user.email,
                inquiry.title,
                inquiry.status,
            )
        except Exception:
            logger.exception("문의 상태 변경 메일 발송 실패: inquiry_id=%s", inquiry.id)
    return _build_admin_inquiry_response(inquiry, inquiry.user)


@router.patch("/inquiries/{inquiry_id}/answer", response_model=AdminInquiryResponse)
def answer_admin_inquiry(
    inquiry_id: int,
    request: InquiryAnswerUpdateRequest,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminInquiryResponse:
    inquiry = get_inquiry_by_id(db, inquiry_id)
    if inquiry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="문의를 찾을 수 없습니다.")
    previous_answer = inquiry.answer
    previous_status = inquiry.status
    try:
        inquiry = answer_inquiry(
            db,
            inquiry,
            answer=request.answer,
            admin_user_id=current_admin.id,
            commit=False,
        )
        create_admin_audit_log(
            admin_db,
            admin_user_id=current_admin.id,
            action="inquiry.answered",
            target_type="inquiry",
            target_id=inquiry.id,
        )
        db.commit()
    except Exception:
        db.rollback()
        admin_db.rollback()
        raise
    if (
        (inquiry.answer != previous_answer or inquiry.status != previous_status)
        and inquiry.user.is_active
    ):
        try:
            send_inquiry_answer_email(
                inquiry.user.email,
                inquiry.title,
                inquiry.answer or "",
            )
        except Exception:
            logger.exception("문의 답변 메일 발송 실패: inquiry_id=%s", inquiry.id)
    return _build_admin_inquiry_response(inquiry, inquiry.user)


@router.get("/reports", response_model=AdminReportListResponse)
def read_admin_reports(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    report_status: str | None = Query(None, min_length=1, max_length=30),
    search: str | None = Query(None, min_length=1, max_length=100),
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminReportListResponse:
    del current_admin
    total, rows = list_reports_for_admin(
        db,
        skip=skip,
        limit=limit,
        report_status=report_status,
        search=search,
    )
    return AdminReportListResponse(
        total=total,
        items=[
            _build_admin_report_response(report, user)
            for report, user in rows
        ],
    )


@router.get("/reports/{report_id}", response_model=AdminReportResponse)
def read_admin_report_detail(
    report_id: int,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminReportResponse:
    del current_admin
    report = get_report_by_id(db, report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="신고 내역을 찾을 수 없습니다.",
        )
    return _build_admin_report_response(report, report.user)


@router.patch("/reports/{report_id}", response_model=AdminReportResponse)
def update_admin_report(
    report_id: int,
    request: ReportStatusUpdateRequest,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminReportResponse:
    report = get_report_by_id(db, report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="신고 내역을 찾을 수 없습니다.",
        )
    try:
        report = update_report_status(
            db,
            report,
            report_status=request.status,
            admin_note=request.admin_note,
            admin_user_id=current_admin.id,
            commit=False,
        )
        create_admin_audit_log(
            admin_db,
            admin_user_id=current_admin.id,
            action="report.status_updated",
            target_type="report",
            target_id=report.id,
            detail=f"status={request.status}",
        )
        db.commit()
    except Exception:
        db.rollback()
        admin_db.rollback()
        raise
    return _build_admin_report_response(report, report.user)


@router.get("/notices", response_model=AdminNoticeListResponse)
def read_admin_notices(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    is_published: bool | None = None,
    search: str | None = Query(None, min_length=1, max_length=100),
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminNoticeListResponse:
    del current_admin
    total, notices = list_notices_for_admin(
        db,
        skip=skip,
        limit=limit,
        is_published=is_published,
        search=search,
    )
    return AdminNoticeListResponse(
        total=total,
        items=[_build_admin_notice_response(notice) for notice in notices],
    )


@router.post(
    "/notices",
    response_model=AdminNoticeResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_admin_notice(
    request: NoticeCreateRequest,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminNoticeResponse:
    try:
        notice = create_notice(
            db,
            title=request.title,
            content=request.content,
            is_published=request.is_published,
            admin_user_id=current_admin.id,
            commit=False,
        )
        create_admin_audit_log(
            admin_db,
            admin_user_id=current_admin.id,
            action="notice.created",
            target_type="notice",
            target_id=notice.id,
            detail=f"published={notice.is_published}",
        )
        db.commit()
    except Exception:
        db.rollback()
        admin_db.rollback()
        raise
    return _build_admin_notice_response(notice)


@router.patch("/notices/{notice_id}", response_model=AdminNoticeResponse)
def update_admin_notice(
    notice_id: int,
    request: NoticeUpdateRequest,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminNoticeResponse:
    notice = get_notice_by_id(db, notice_id)
    if notice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="공지사항을 찾을 수 없습니다.",
        )

    was_published = notice.is_published
    try:
        notice = update_notice(
            db,
            notice,
            title=request.title,
            content=request.content,
            is_published=request.is_published,
            admin_user_id=current_admin.id,
            commit=False,
        )
        action = "notice.updated"
        if request.is_published is True and not was_published:
            action = "notice.published"
        elif request.is_published is False and was_published:
            action = "notice.unpublished"
        create_admin_audit_log(
            admin_db,
            admin_user_id=current_admin.id,
            action=action,
            target_type="notice",
            target_id=notice.id,
        )
        db.commit()
    except Exception:
        db.rollback()
        admin_db.rollback()
        raise
    return _build_admin_notice_response(notice)


@router.delete("/notices/{notice_id}", response_model=AdminMessageResponse)
def delete_admin_notice(
    notice_id: int,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminMessageResponse:
    notice = get_notice_by_id(db, notice_id)
    if notice is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="공지사항을 찾을 수 없습니다.",
        )
    try:
        delete_notice(db, notice, commit=False)
        create_admin_audit_log(
            admin_db,
            admin_user_id=current_admin.id,
            action="notice.deleted",
            target_type="notice",
            target_id=notice_id,
        )
        db.commit()
    except Exception:
        db.rollback()
        admin_db.rollback()
        raise
    return AdminMessageResponse(message="공지사항이 삭제되었습니다.")


@router.get("/users/{user_id}", response_model=AdminUserDetailResponse)
def read_admin_user_detail(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
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
        bonus_credits_remaining=get_bonus_credits_remaining(db, user.id),
    )


@router.patch("/users/{user_id}/status", response_model=AdminUserResponse)
def update_admin_user_status(
    user_id: int,
    request: AdminUserStatusUpdateRequest,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    current_admin: AdminUser = Depends(get_current_super_admin),
) -> AdminUserResponse:
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
            admin_db,
            admin_user_id=current_admin.id,
            action="user.status_updated",
            target_type="user",
            target_id=user.id,
            detail=f"is_active={request.is_active}",
        )
        db.commit()
    except Exception:
        db.rollback()
        admin_db.rollback()
        raise
    return _build_admin_user_response(user, subscription)


@router.patch("/users/{user_id}/subscription", response_model=AdminUserResponse)
def update_admin_user_subscription(
    user_id: int,
    request: AdminUserSubscriptionUpdateRequest,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    current_admin: AdminUser = Depends(get_current_super_admin),
) -> AdminUserResponse:
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
            admin_db,
            admin_user_id=current_admin.id,
            action="user.subscription_updated",
            target_type="user",
            target_id=user.id,
            detail=f"is_premium={request.is_premium}",
        )
        db.commit()
    except Exception:
        db.rollback()
        admin_db.rollback()
        raise
    return _build_admin_user_response(user, subscription)


@router.post(
    "/users/{user_id}/bonus-credits",
    response_model=AdminBonusCreditGrantResponse,
)
def grant_admin_user_bonus_credits(
    user_id: int,
    request: AdminBonusCreditGrantRequest,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    current_admin: AdminUser = Depends(get_current_super_admin),
) -> AdminBonusCreditGrantResponse:
    if get_user_for_admin(db, user_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="사용자를 찾을 수 없습니다.",
        )

    try:
        balance = grant_bonus_credits(db, user_id, request.amount, commit=False)
        create_admin_audit_log(
            admin_db,
            admin_user_id=current_admin.id,
            action="user.bonus_credits_granted",
            target_type="user",
            target_id=user_id,
            detail=(
                f"amount={request.amount}; "
                f"bonus_credits_remaining={balance.credits_remaining}"
            ),
        )
        db.commit()
    except Exception:
        db.rollback()
        admin_db.rollback()
        raise
    return AdminBonusCreditGrantResponse(
        user_id=user_id,
        bonus_credits_remaining=balance.credits_remaining,
    )


@router.get("/refunds", response_model=AdminRefundListResponse)
def read_admin_refunds(
    refund_status: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminRefundListResponse:
    del current_admin
    query = (
        db.query(RefundRequest, PurchaseHistory, User)
        .join(PurchaseHistory, PurchaseHistory.id == RefundRequest.purchase_id)
        .join(User, User.id == RefundRequest.user_id)
    )
    if refund_status:
        query = query.filter(RefundRequest.status == refund_status)
    rows = query.order_by(RefundRequest.requested_at.desc()).all()
    return AdminRefundListResponse(
        total=len(rows),
        items=[_build_refund_response(refund, purchase, user) for refund, purchase, user in rows],
    )


@router.post("/refunds/{refund_id}/approve", response_model=AdminRefundResponse)
def approve_admin_refund(
    refund_id: int,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    current_admin: AdminUser = Depends(get_current_super_admin),
) -> AdminRefundResponse:
    row = (
        db.query(RefundRequest, PurchaseHistory, User)
        .join(PurchaseHistory, PurchaseHistory.id == RefundRequest.purchase_id)
        .join(User, User.id == RefundRequest.user_id)
        .filter(RefundRequest.id == refund_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="환불 신청을 찾을 수 없습니다.")
    refund, purchase, user = row
    if refund.status != "pending":
        raise HTTPException(status_code=409, detail="이미 처리된 환불 신청입니다.")
    if purchase.provider != "demo":
        raise HTTPException(status_code=400, detail="데모 결제 내역만 환불할 수 있습니다.")
    if purchase.item_type not in {"subscription", "credit_pack"}:
        raise HTTPException(status_code=400, detail="구독 또는 크레딧 구매 내역만 환불할 수 있습니다.")
    if purchase.item_type == "credit_pack" and get_demo_credit_pack_credits(purchase.description) is None:
        raise HTTPException(status_code=400, detail="확인할 수 없는 크레딧 상품은 환불할 수 없습니다.")
    if purchase.status != "paid":
        raise HTTPException(status_code=409, detail="환불할 수 있는 결제 내역이 아닙니다.")

    try:
        subscription_revoked, purchased_credits_revoked = refund_demo_purchase_for_admin(db, purchase)
        refund.status = "approved"
        refund.processed_at = utc_now()
        refund.processed_by_admin_id = current_admin.id
        create_admin_audit_log(
            admin_db,
            admin_user_id=current_admin.id,
            action="refund.approved",
            target_type="refund",
            target_id=refund.id,
            detail=(
                f"purchase_id={purchase.id}; amount={refund.amount}; "
                f"subscription_revoked={subscription_revoked}; "
                f"purchased_credits_revoked={purchased_credits_revoked}"
            ),
        )
        db.commit()
    except Exception:
        db.rollback()
        admin_db.rollback()
        raise
    return _build_refund_response(refund, purchase, user)


@router.post("/refunds/{refund_id}/reject", response_model=AdminRefundResponse)
def reject_admin_refund(
    refund_id: int,
    request: AdminRefundRejectRequest,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    current_admin: AdminUser = Depends(get_current_super_admin),
) -> AdminRefundResponse:
    row = (
        db.query(RefundRequest, PurchaseHistory, User)
        .join(PurchaseHistory, PurchaseHistory.id == RefundRequest.purchase_id)
        .join(User, User.id == RefundRequest.user_id)
        .filter(RefundRequest.id == refund_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="환불 신청을 찾을 수 없습니다.")
    refund, purchase, user = row
    if refund.status != "pending":
        raise HTTPException(status_code=409, detail="이미 처리된 환불 신청입니다.")
    refund.status = "rejected"
    refund.rejection_reason = request.reason.strip()
    refund.processed_at = utc_now()
    refund.processed_by_admin_id = current_admin.id
    create_admin_audit_log(
        admin_db,
        admin_user_id=current_admin.id,
        action="refund.rejected",
        target_type="refund",
        target_id=refund.id,
        detail=f"reason={refund.rejection_reason}",
    )
    db.commit()
    return _build_refund_response(refund, purchase, user)


@router.patch("/password", response_model=AdminMessageResponse)
def change_admin_password(
    request: AdminPasswordChangeRequest,
    admin_db: Session = Depends(get_admin_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminMessageResponse:
    if not verify_password(request.current_password, current_admin.password_hash):
        raise HTTPException(status_code=400, detail="현재 비밀번호가 올바르지 않습니다.")
    if request.current_password == request.new_password:
        raise HTTPException(status_code=400, detail="새 비밀번호는 현재 비밀번호와 달라야 합니다.")
    current_admin.password_hash = hash_password(request.new_password)
    create_admin_audit_log(
        admin_db,
        admin_user_id=current_admin.id,
        action="admin.password_changed",
        target_type="admin",
        target_id=current_admin.id,
    )
    admin_db.commit()
    return AdminMessageResponse(message="관리자 비밀번호가 변경되었습니다.")


@router.post("/totp/setup", response_model=AdminTotpSetupResponse)
def setup_admin_totp(
    request: AdminTotpSetupRequest,
    admin_db: Session = Depends(get_admin_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminTotpSetupResponse:
    if not verify_password(request.current_password, current_admin.password_hash):
        raise HTTPException(status_code=400, detail="현재 비밀번호가 올바르지 않습니다.")

    secret = generate_totp_secret()
    current_admin.totp_secret_encrypted = encrypt_totp_secret(secret)
    current_admin.totp_enabled = False
    create_admin_audit_log(
        admin_db,
        admin_user_id=current_admin.id,
        action="admin.totp_setup_started",
        target_type="admin",
        target_id=current_admin.id,
        commit=False,
    )
    admin_db.commit()
    provisioning_uri = build_totp_provisioning_uri(secret, current_admin.username)
    return AdminTotpSetupResponse(
        manual_entry_key=secret,
        provisioning_uri=provisioning_uri,
        qr_code_data_url=build_totp_qr_code_data_url(provisioning_uri),
    )


@router.post("/totp/confirm", response_model=AdminMessageResponse)
def confirm_admin_totp(
    request: AdminTotpVerifyRequest,
    admin_db: Session = Depends(get_admin_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminMessageResponse:
    if not current_admin.totp_secret_encrypted:
        raise HTTPException(status_code=400, detail="먼저 TOTP 설정을 시작해 주세요.")
    try:
        is_valid_totp = verify_totp_code(
            current_admin.totp_secret_encrypted,
            request.code,
        )
    except ValueError:
        is_valid_totp = False
    if not is_valid_totp:
        raise HTTPException(status_code=400, detail="인증 코드가 올바르지 않습니다.")

    current_admin.totp_enabled = True
    create_admin_audit_log(
        admin_db,
        admin_user_id=current_admin.id,
        action="admin.totp_enabled",
        target_type="admin",
        target_id=current_admin.id,
        commit=False,
    )
    admin_db.commit()
    return AdminMessageResponse(message="관리자 2단계 인증이 활성화되었습니다.")


@router.delete("/totp", response_model=AdminMessageResponse)
def disable_admin_totp(
    request: AdminTotpDisableRequest,
    admin_db: Session = Depends(get_admin_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminMessageResponse:
    if not current_admin.totp_enabled or not current_admin.totp_secret_encrypted:
        raise HTTPException(status_code=400, detail="활성화된 TOTP 인증이 없습니다.")
    if not verify_password(request.current_password, current_admin.password_hash):
        raise HTTPException(status_code=400, detail="현재 비밀번호가 올바르지 않습니다.")
    try:
        is_valid_totp = verify_totp_code(
            current_admin.totp_secret_encrypted,
            request.code,
        )
    except ValueError:
        is_valid_totp = False
    if not is_valid_totp:
        raise HTTPException(status_code=400, detail="인증 코드가 올바르지 않습니다.")

    current_admin.totp_secret_encrypted = None
    current_admin.totp_enabled = False
    create_admin_audit_log(
        admin_db,
        admin_user_id=current_admin.id,
        action="admin.totp_disabled",
        target_type="admin",
        target_id=current_admin.id,
        commit=False,
    )
    admin_db.commit()
    return AdminMessageResponse(message="관리자 2단계 인증이 해제되었습니다.")

# --- 챗봇 이용통계 (한의정) ---------------------------------------------------
@router.get("/chatbot/stats", response_model=AdminChatbotStatsResponse)
def read_chatbot_stats(
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminChatbotStatsResponse:
    del current_admin
    return AdminChatbotStatsResponse(**get_chatbot_stats(db))


# --- FAQ 후보 큐 (한의정) -----------------------------------------------------
def _build_faq_candidate_response(candidate) -> AdminFaqCandidateResponse:
    return AdminFaqCandidateResponse(
        id=candidate.id,
        source_inquiry_id=candidate.source_inquiry_id,
        category=candidate.category,
        question=candidate.question,
        answer=candidate.answer,
        status=candidate.status,
        created_at=candidate.created_at,
        updated_at=candidate.updated_at,
    )


@router.post(
    "/inquiries/{inquiry_id}/promote-faq",
    response_model=AdminFaqCandidateResponse,
    status_code=status.HTTP_201_CREATED,
)
def promote_inquiry_to_faq(
    inquiry_id: int,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminFaqCandidateResponse:
    audit_db = admin_db if isinstance(admin_db, Session) else db
    admin_id = getattr(current_admin, "id", getattr(current_admin, "user_id", None))
    inquiry = get_inquiry_by_id(db, inquiry_id)
    if inquiry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="문의를 찾을 수 없습니다.")
    if inquiry.status != "answered" or not inquiry.answer:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="답변이 완료된 문의만 FAQ 후보로 등록할 수 있습니다.",
        )
    if has_active_candidate_for_inquiry(db, inquiry.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 이 문의로 등록되었거나 승인된 FAQ 후보가 있습니다.",
        )
    try:
        candidate = create_faq_candidate(
            db,
            source_inquiry_id=inquiry.id,
            category=inquiry.category,
            question=inquiry.title,
            answer=inquiry.answer,
            created_by_admin_id=admin_id,
            commit=False,
        )
        create_admin_audit_log(
            audit_db,
            admin_user_id=admin_id,
            action="faq_candidate.promoted",
            target_type="faq_candidate",
            target_id=candidate.id,
            detail=f"inquiry_id={inquiry.id}",
            commit=False,
        )
        db.commit()
        if audit_db is admin_db:
            admin_db.commit()
    except Exception:
        db.rollback()
        if audit_db is admin_db:
            admin_db.rollback()
        raise
    return _build_faq_candidate_response(candidate)


@router.get("/faq-candidates", response_model=AdminFaqCandidateListResponse)
def read_faq_candidates(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    candidate_status: str | None = Query(None, min_length=1, max_length=20),
    db: Session = Depends(get_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminFaqCandidateListResponse:
    del current_admin
    total, rows = list_faq_candidates_for_admin(
        db, skip=skip, limit=limit, candidate_status=candidate_status
    )
    return AdminFaqCandidateListResponse(
        total=total,
        items=[_build_faq_candidate_response(candidate) for candidate in rows],
    )


@router.patch("/faq-candidates/{candidate_id}", response_model=AdminFaqCandidateResponse)
def update_faq_candidate(
    candidate_id: int,
    request: FaqCandidateStatusUpdateRequest,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    current_admin: AdminUser = Depends(get_current_admin),
) -> AdminFaqCandidateResponse:
    audit_db = admin_db if isinstance(admin_db, Session) else db
    admin_id = getattr(current_admin, "id", getattr(current_admin, "user_id", None))
    candidate = get_faq_candidate_by_id(db, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="FAQ 후보를 찾을 수 없습니다.")
    if candidate.status != "pending":
        # 이미 검토된 후보의 상태 뒤집기 차단 (승인분 KB 반영과의 상태 불일치·중복삽입 방지)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 검토된 FAQ 후보입니다.",
        )
    try:
        candidate = update_faq_candidate_status(
            db,
            candidate,
            candidate_status=request.status,
            admin_user_id=admin_id,
            commit=False,
        )
        create_admin_audit_log(
            audit_db,
            admin_user_id=admin_id,
            action=f"faq_candidate.{request.status}",
            target_type="faq_candidate",
            target_id=candidate.id,
            commit=False,
        )
        db.commit()
        if audit_db is admin_db:
            admin_db.commit()
    except Exception:
        db.rollback()
        if audit_db is admin_db:
            admin_db.rollback()
        raise
    return _build_faq_candidate_response(candidate)
