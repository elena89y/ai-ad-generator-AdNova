from datetime import timedelta

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.crud.billing import expire_ended_subscriptions, get_demo_credit_pack_credits
from app.crud.credits import grant_premium_credits, revoke_purchased_credits
from app.crud.retention import WITHDRAWN_USERNAME
from app.database.admin_models import (
    AdminAuditLog,
    AdminLoginFailureLog,
    AdminUser,
)
from app.database.billing_models import PurchaseHistory, Subscription, utc_now
from app.database.models import Advertisement, SupportInquiry, User


def get_admin_summary(db: Session) -> dict[str, int]:
    expire_ended_subscriptions(db)
    paid_purchase_count, paid_purchase_amount = (
        db.query(
            func.count(PurchaseHistory.id),
            func.coalesce(func.sum(PurchaseHistory.amount), 0),
        )
        .filter(PurchaseHistory.status == "paid")
        .one()
    )
    month_start = utc_now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_paid_purchase_amount = (
        db.query(func.coalesce(func.sum(PurchaseHistory.amount), 0))
        .filter(
            PurchaseHistory.status == "paid",
            PurchaseHistory.purchased_at >= month_start,
        )
        .scalar()
    )

    return {
        # 탈퇴회원 센티넬 제외 (active_users 는 is_active=False 라 이미 제외됨)
        "total_users": db.query(User).filter(User.username != WITHDRAWN_USERNAME).count(),
        "active_users": db.query(User).filter(User.is_active.is_(True)).count(),
        "premium_users": (
            db.query(Subscription)
            .filter(Subscription.plan == "premium", Subscription.status == "active")
            .count()
        ),
        "total_advertisements": db.query(Advertisement).count(),
        "unresolved_inquiries": (
            db.query(SupportInquiry)
            .filter(SupportInquiry.status.in_(["pending", "in_progress"]))
            .count()
        ),
        "paid_purchase_count": int(paid_purchase_count or 0),
        "paid_purchase_amount": int(paid_purchase_amount or 0),
        "monthly_paid_purchase_amount": int(monthly_paid_purchase_amount or 0),
    }


def create_admin_audit_log(
    db: Session,
    *,
    admin_user_id: int,
    action: str,
    target_type: str,
    target_id: int,
    detail: str | None = None,
    commit: bool = True,
) -> AdminAuditLog:
    audit_log = AdminAuditLog(
        admin_user_id=admin_user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail=detail,
    )
    db.add(audit_log)
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(audit_log)
    return audit_log


def list_admin_audit_logs(
    db: Session,
    *,
    skip: int,
    limit: int,
    action: str | None = None,
) -> tuple[int, list[tuple[AdminAuditLog, AdminUser]]]:
    query = db.query(AdminAuditLog, AdminUser).join(
        AdminUser,
        AdminUser.id == AdminAuditLog.admin_user_id,
    )
    if action:
        query = query.filter(AdminAuditLog.action == action)

    return (
        query.count(),
        query.order_by(AdminAuditLog.created_at.desc()).offset(skip).limit(limit).all(),
    )


def create_admin_login_failure_log(
    db: Session,
    *,
    attempted_username: str,
    reason: str,
    admin_user_id: int | None = None,
) -> AdminLoginFailureLog:
    login_failure_log = AdminLoginFailureLog(
        attempted_username=attempted_username,
        admin_user_id=admin_user_id,
        reason=reason,
    )
    db.add(login_failure_log)
    db.commit()
    db.refresh(login_failure_log)
    return login_failure_log


def list_admin_login_failure_logs(
    db: Session,
    *,
    skip: int,
    limit: int,
) -> tuple[int, list[AdminLoginFailureLog]]:
    query = db.query(AdminLoginFailureLog)
    return (
        query.count(),
        query.order_by(AdminLoginFailureLog.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all(),
    )


def list_admin_accounts(
    db: Session,
    *,
    skip: int,
    limit: int,
    search: str | None = None,
) -> tuple[int, list[AdminUser]]:
    query = db.query(AdminUser)
    if search:
        keyword = f"%{search}%"
        query = query.filter(
            or_(
                AdminUser.username.ilike(keyword),
                AdminUser.email.ilike(keyword),
                AdminUser.name.ilike(keyword),
            )
        )

    total = query.count()
    rows = (
        query.order_by(AdminUser.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return total, rows


def get_admin_account_by_id(
    db: Session,
    admin_account_id: int,
) -> AdminUser | None:
    return db.query(AdminUser).filter(AdminUser.id == admin_account_id).first()


def create_admin_user_account(
    db: Session,
    *,
    email: str,
    username: str,
    password_hash: str,
    name: str | None,
    role: str,
) -> AdminUser:
    admin_user = AdminUser(
        email=email,
        username=username,
        password_hash=password_hash,
        name=name,
        is_active=True,
        role=role,
    )
    db.add(admin_user)
    db.flush()
    return admin_user


def count_active_super_admins(db: Session) -> int:
    return (
        db.query(AdminUser)
        .filter(
            AdminUser.role == "super_admin",
            AdminUser.is_active.is_(True),
        )
        .count()
    )


def update_admin_account_role(
    db: Session,
    admin_account: AdminUser,
    *,
    role: str,
    commit: bool = True,
) -> AdminUser:
    admin_account.role = role
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(admin_account)
    return admin_account


def update_admin_account_active_status(
    db: Session,
    admin_account: AdminUser,
    *,
    is_active: bool,
    commit: bool = True,
) -> AdminUser:
    admin_account.is_active = is_active
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(admin_account)
    return admin_account


def list_users_for_admin(
    db: Session,
    *,
    skip: int,
    limit: int,
    search: str | None = None,
    is_active: bool | None = None,
    plan: str | None = None,
) -> tuple[int, list[tuple[User, Subscription | None]]]:
    expire_ended_subscriptions(db)
    query = db.query(User, Subscription).outerjoin(
        Subscription,
        Subscription.user_id == User.id,
    ).filter(User.username != WITHDRAWN_USERNAME)  # 탈퇴회원 센티넬은 회원목록에서 제외
    if search:
        keyword = f"%{search}%"
        query = query.filter(
            or_(
                User.username.ilike(keyword),
                User.email.ilike(keyword),
                User.business_name.ilike(keyword),
            )
        )
    if is_active is not None:
        query = query.filter(User.is_active.is_(is_active))
    if plan == "premium":
        query = query.filter(
            Subscription.plan == "premium",
            Subscription.status == "active",
        )
    elif plan == "free":
        query = query.filter(
            or_(
                Subscription.id.is_(None),
                Subscription.plan != "premium",
                Subscription.status != "active",
            )
        )

    total = query.count()
    rows = (
        query.order_by(User.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return total, rows


def get_user_for_admin(
    db: Session,
    user_id: int,
) -> tuple[User, Subscription | None] | None:
    expire_ended_subscriptions(db)
    return (
        db.query(User, Subscription)
        .outerjoin(Subscription, Subscription.user_id == User.id)
        .filter(User.id == user_id)
        .first()
    )


def count_advertisements_by_user(db: Session, user_id: int) -> int:
    return db.query(Advertisement).filter(Advertisement.user_id == user_id).count()


def update_user_active_status(
    db: Session,
    user: User,
    *,
    is_active: bool,
    commit: bool = True,
) -> User:
    user.is_active = is_active
    if commit:
        db.commit()
    else:
        db.flush()
    db.refresh(user)
    return user


def update_user_premium_access(
    db: Session,
    user_id: int,
    *,
    is_premium: bool,
    commit: bool = True,
) -> tuple[User, Subscription | None]:
    subscription = (
        db.query(Subscription).filter(Subscription.user_id == user_id).first()
    )

    if is_premium:
        now = utc_now()
        if subscription is None:
            subscription = Subscription(user_id=user_id)
            db.add(subscription)

        subscription.plan = "premium"
        subscription.status = "active"
        subscription.provider = "admin"
        subscription.current_period_start = now
        subscription.current_period_end = now + timedelta(days=30)
        subscription.cancel_at_period_end = False
        subscription.cancel_requested_at = None
        grant_premium_credits(
            db,
            user_id,
            next_reset_at=subscription.current_period_end,
            now=now,
            commit=False,
        )
    elif subscription is not None:
        subscription.plan = "free"
        subscription.status = "inactive"
        subscription.cancel_at_period_end = False
        subscription.cancel_requested_at = None

    if commit:
        db.commit()
    else:
        db.flush()
    user = db.query(User).filter(User.id == user_id).one()
    db.refresh(user)
    return user, subscription


def list_subscriptions_for_admin(
    db: Session,
    *,
    skip: int,
    limit: int,
    user_id: int | None = None,
    plan: str | None = None,
    subscription_status: str | None = None,
    search: str | None = None,
) -> tuple[int, list[tuple[Subscription, User]]]:
    expire_ended_subscriptions(db)
    query = db.query(Subscription, User).join(
        User,
        User.id == Subscription.user_id,
    )
    if user_id is not None:
        query = query.filter(Subscription.user_id == user_id)
    if plan:
        query = query.filter(Subscription.plan == plan)
    if subscription_status:
        query = query.filter(Subscription.status == subscription_status)
    if search:
        keyword = f"%{search}%"
        query = query.filter(
            or_(
                User.username.ilike(keyword),
                User.email.ilike(keyword),
            )
        )

    total = query.count()
    rows = (
        query.order_by(Subscription.updated_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return total, rows


def get_subscription_for_admin(
    db: Session,
    subscription_id: int,
) -> tuple[Subscription, User] | None:
    expire_ended_subscriptions(db)
    return (
        db.query(Subscription, User)
        .join(User, User.id == Subscription.user_id)
        .filter(Subscription.id == subscription_id)
        .first()
    )


def list_purchase_histories_for_admin(
    db: Session,
    *,
    skip: int,
    limit: int,
    user_id: int | None = None,
    search: str | None = None,
    payment_status: str | None = None,
) -> tuple[int, list[tuple[PurchaseHistory, User]]]:
    query = db.query(PurchaseHistory, User).join(
        User,
        User.id == PurchaseHistory.user_id,
    )
    if user_id is not None:
        query = query.filter(PurchaseHistory.user_id == user_id)
    if search:
        keyword = f"%{search}%"
        query = query.filter(
            or_(
                User.username.ilike(keyword),
                User.email.ilike(keyword),
                PurchaseHistory.description.ilike(keyword),
            )
        )
    if payment_status:
        query = query.filter(PurchaseHistory.status == payment_status)

    total = query.count()
    rows = (
        query.order_by(PurchaseHistory.purchased_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return total, rows


def get_purchase_history_for_admin(
    db: Session,
    purchase_id: int,
) -> tuple[PurchaseHistory, User] | None:
    return (
        db.query(PurchaseHistory, User)
        .join(User, User.id == PurchaseHistory.user_id)
        .filter(PurchaseHistory.id == purchase_id)
        .first()
    )


def refund_demo_purchase_for_admin(
    db: Session,
    purchase: PurchaseHistory,
) -> tuple[bool, int]:
    purchase.status = "refunded"

    subscription_revoked = False
    purchased_credits_revoked = 0
    if purchase.item_type == "subscription":
        subscription = (
            db.query(Subscription)
            .filter(Subscription.user_id == purchase.user_id)
            .first()
        )
        has_other_paid_subscription = (
            db.query(PurchaseHistory.id)
            .filter(
                PurchaseHistory.user_id == purchase.user_id,
                PurchaseHistory.item_type == "subscription",
                PurchaseHistory.status == "paid",
                PurchaseHistory.id != purchase.id,
            )
            .first()
            is not None
        )

        if (
            subscription is not None
            and subscription.plan == "premium"
            and subscription.status == "active"
            and subscription.provider != "admin"
            and not has_other_paid_subscription
        ):
            subscription.plan = "free"
            subscription.status = "inactive"
            subscription.cancel_at_period_end = False
            subscription.cancel_requested_at = None
            subscription_revoked = True
    elif purchase.item_type == "credit_pack":
        credits = get_demo_credit_pack_credits(purchase.description)
        if credits is not None:
            purchased_credits_revoked = revoke_purchased_credits(
                db,
                purchase.user_id,
                credits,
                commit=False,
            )

    db.flush()
    return subscription_revoked, purchased_credits_revoked
