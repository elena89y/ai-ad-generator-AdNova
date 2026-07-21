import unittest
from datetime import timedelta
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.admin import (
    approve_admin_refund,
    create_admin_account_by_super_admin,
    read_admin_accounts,
    read_admin_audit_logs,
    read_admin_summary,
    read_admin_me,
    read_admin_purchase_histories,
    read_admin_purchase_history_detail,
    read_admin_subscription_detail,
    read_admin_subscriptions,
    read_admin_user_detail,
    read_admin_users,
    refund_admin_demo_purchase,
    update_admin_account_role_by_super_admin,
    update_admin_account_status_by_super_admin,
    update_admin_user_status,
    update_admin_user_subscription,
)
from app.core.admin_security import get_current_admin, get_current_super_admin
from app.core.security import create_access_token, get_current_user
from app.database.admin_models import AdminAccount, AdminAuditLog, AdminLoginFailureLog
from app.database.billing_models import (
    PremiumCreditBalance,
    PurchaseHistory,
    RefundRequest,
    Subscription,
    utc_now,
)
from app.database.connection import Base
from app.database.models import Advertisement, User
from app.schemas.admin import (
    AdminAccountCreateRequest,
    AdminAccountRoleUpdateRequest,
    AdminAccountStatusUpdateRequest,
    AdminUserStatusUpdateRequest,
    AdminUserSubscriptionUpdateRequest,
    AdminDemoRefundRequest,
    AdminPasswordChangeRequest,
)


class AdminApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.session = sessionmaker(bind=self.engine)()

        self.user = User(
            email="user@example.com",
            username="normaluser",
            password_hash="test-hash",
            is_active=True,
        )
        self.admin_user = User(
            email="admin@example.com",
            username="adminuser",
            password_hash="test-hash",
            is_active=True,
        )
        self.session.add_all([self.user, self.admin_user])
        self.session.commit()

        self.admin_account = AdminAccount(
            user_id=self.admin_user.id,
            role="super_admin",
        )
        self.session.add(self.admin_account)
        self.session.add(
            Subscription(
                user_id=self.user.id,
                plan="premium",
                status="active",
            )
        )
        self.session.add(
            Advertisement(
                user_id=self.user.id,
                ad_type="image",
                prompt="test prompt",
                status="completed",
            )
        )
        self.session.add(
            PurchaseHistory(
                user_id=self.user.id,
                provider="demo",
                item_type="subscription",
                description="프리미엄 월 구독 (테스트)",
                amount=9900,
                currency="KRW",
                status="paid",
            )
        )
        self.session.commit()

    def _create_admin_account(
        self,
        *,
        username: str,
        role: str = "operator",
        is_active: bool = True,
    ) -> tuple[User, AdminAccount]:
        user = User(
            email=f"{username}@example.com",
            username=username,
            password_hash="test-hash",
            is_active=True,
        )
        self.session.add(user)
        self.session.commit()

        admin_account = AdminAccount(
            user_id=user.id,
            role=role,
            is_active=is_active,
        )
        self.session.add(admin_account)
        self.session.commit()
        return user, admin_account

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_normal_user_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as context:
            get_current_admin(current_user=self.user, db=self.session)

        self.assertEqual(context.exception.status_code, 403)

    def test_active_admin_can_read_own_admin_profile(self) -> None:
        current_admin = get_current_admin(
            current_user=self.admin_user,
            db=self.session,
        )

        response = read_admin_me(
            current_user=self.admin_user,
            current_admin=current_admin,
        )

        self.assertEqual(response.username, "adminuser")
        self.assertEqual(response.role, "super_admin")

    def test_inactive_admin_is_rejected(self) -> None:
        self.admin_account.is_active = False
        self.session.commit()

        with self.assertRaises(HTTPException) as context:
            get_current_admin(current_user=self.admin_user, db=self.session)

        self.assertEqual(context.exception.status_code, 403)

    def test_operator_cannot_use_super_admin_dependency(self) -> None:
        _, operator_account = self._create_admin_account(username="operator")

        with self.assertRaises(HTTPException) as context:
            get_current_super_admin(current_admin=operator_account)

        self.assertEqual(context.exception.status_code, 403)

    def test_invalid_admin_role_is_rejected(self) -> None:
        invalid_user, _ = self._create_admin_account(
            username="invalidrole",
            role="unknown",
        )

        with self.assertRaises(HTTPException) as context:
            get_current_admin(current_user=invalid_user, db=self.session)

        self.assertEqual(context.exception.status_code, 403)

    def test_super_admin_can_manage_operator_account(self) -> None:
        operator_user, operator_account = self._create_admin_account(
            username="operator",
        )

        accounts = read_admin_accounts(
            skip=0,
            limit=50,
            search="operator",
            db=self.session,
            current_admin=self.admin_account,
        )
        updated_role = update_admin_account_role_by_super_admin(
            admin_account_id=operator_account.id,
            request=AdminAccountRoleUpdateRequest(role="super_admin"),
            db=self.session,
            current_admin=self.admin_account,
        )
        updated_status = update_admin_account_status_by_super_admin(
            admin_account_id=operator_account.id,
            request=AdminAccountStatusUpdateRequest(is_active=False),
            db=self.session,
            current_admin=self.admin_account,
        )

        self.assertEqual(accounts.total, 1)
        self.assertEqual(updated_role.role, "super_admin")
        self.assertFalse(updated_status.is_active)
        with self.assertRaises(HTTPException) as context:
            get_current_admin(current_user=operator_user, db=self.session)
        self.assertEqual(context.exception.status_code, 403)
        self.assertEqual(
            self.session.query(AdminAuditLog)
            .filter(AdminAuditLog.action.in_(["admin.role_updated", "admin.status_updated"]))
            .count(),
            2,
        )

    def test_super_admin_can_create_new_operator_account(self) -> None:
        response = create_admin_account_by_super_admin(
            request=AdminAccountCreateRequest(
                username="newadmin",
                email="newadmin@example.com",
                password="Password1!",
                name="새 관리자",
                role="operator",
            ),
            db=self.session,
            current_admin=self.admin_account,
        )

        user = self.session.query(User).filter(User.id == response.user_id).one()
        self.assertEqual(user.username, "newadmin")
        self.assertEqual(user.email, "newadmin@example.com")
        self.assertNotEqual(user.password_hash, "Password1!")
        self.assertEqual(response.role, "operator")
        self.assertTrue(response.is_active)
        self.assertEqual(
            self.session.query(AdminAuditLog)
            .filter(AdminAuditLog.action == "admin.account_created")
            .count(),
            1,
        )

    def test_audit_logs_include_admin_login_failures(self) -> None:
        self.session.add(
            AdminLoginFailureLog(
                attempted_username="missinguser",
                reason="아이디 또는 비밀번호 불일치",
            )
        )
        self.session.commit()

        response = read_admin_audit_logs(
            skip=0,
            limit=50,
            action=None,
            db=self.session,
            current_admin=self.admin_account,
        )

        login_failure = next(
            item for item in response.items if item.action == "admin.login_failed"
        )
        self.assertEqual(login_failure.source, "login_failure")
        self.assertEqual(login_failure.admin_username, "missinguser")
        self.assertIsNone(login_failure.target_id)

    def test_duplicate_admin_username_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as context:
            create_admin_account_by_super_admin(
                request=AdminAccountCreateRequest(
                    username=self.admin_user.username,
                    email="another-admin@example.com",
                    password="Password1!",
                    role="operator",
                ),
                db=self.session,
                current_admin=self.admin_account,
            )

        self.assertEqual(context.exception.status_code, 409)
        self.assertEqual(
            context.exception.detail,
            "이미 사용 중인 아이디입니다.",
        )

    def test_duplicate_admin_email_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as context:
            create_admin_account_by_super_admin(
                request=AdminAccountCreateRequest(
                    username="anotheradmin",
                    email=self.admin_user.email,
                    password="Password1!",
                    role="operator",
                ),
                db=self.session,
                current_admin=self.admin_account,
            )

        self.assertEqual(context.exception.status_code, 409)
        self.assertEqual(
            context.exception.detail,
            "이미 사용 중인 이메일입니다.",
        )

    def test_admin_registration_rolls_back_when_audit_log_fails(self) -> None:
        with patch(
            "app.api.admin.create_admin_audit_log",
            side_effect=RuntimeError("audit log failed"),
        ):
            with self.assertRaises(RuntimeError):
                create_admin_account_by_super_admin(
                    request=AdminAccountCreateRequest(
                        username="rolladmin",
                        email="rollbackadmin@example.com",
                        password="Password1!",
                        role="operator",
                    ),
                    db=self.session,
                    current_admin=self.admin_account,
                )

        self.assertIsNone(
            self.session.query(User).filter(User.username == "rolladmin").first()
        )

    def test_super_admin_cannot_modify_own_admin_account(self) -> None:
        with self.assertRaises(HTTPException) as role_context:
            update_admin_account_role_by_super_admin(
                admin_account_id=self.admin_account.id,
                request=AdminAccountRoleUpdateRequest(role="operator"),
                db=self.session,
                current_admin=self.admin_account,
            )
        with self.assertRaises(HTTPException) as status_context:
            update_admin_account_status_by_super_admin(
                admin_account_id=self.admin_account.id,
                request=AdminAccountStatusUpdateRequest(is_active=False),
                db=self.session,
                current_admin=self.admin_account,
            )

        self.assertEqual(role_context.exception.status_code, 400)
        self.assertEqual(status_context.exception.status_code, 400)

    def test_last_active_super_admin_is_protected(self) -> None:
        _, other_super_admin = self._create_admin_account(
            username="othersuper",
            role="super_admin",
        )
        self.admin_account.is_active = False
        self.session.commit()

        with self.assertRaises(HTTPException) as context:
            update_admin_account_status_by_super_admin(
                admin_account_id=other_super_admin.id,
                request=AdminAccountStatusUpdateRequest(is_active=False),
                db=self.session,
                current_admin=self.admin_account,
            )

        self.assertEqual(context.exception.status_code, 409)

    def test_admin_role_update_rolls_back_when_audit_log_fails(self) -> None:
        _, operator_account = self._create_admin_account(username="operator")

        with patch(
            "app.api.admin.create_admin_audit_log",
            side_effect=RuntimeError("audit log failed"),
        ):
            with self.assertRaises(RuntimeError):
                update_admin_account_role_by_super_admin(
                    admin_account_id=operator_account.id,
                    request=AdminAccountRoleUpdateRequest(role="super_admin"),
                    db=self.session,
                    current_admin=self.admin_account,
                )

        self.session.expire_all()
        restored_account = self.session.query(AdminAccount).filter(
            AdminAccount.id == operator_account.id
        ).one()
        self.assertEqual(restored_account.role, "operator")


    def test_admin_can_list_users_with_subscription_status(self) -> None:
        response = read_admin_users(
            skip=0,
            limit=50,
            search=None,
            is_active=None,
            plan=None,
            db=self.session,
            current_admin=self.admin_account,
        )

        listed_user = next(item for item in response.items if item.id == self.user.id)
        self.assertEqual(response.total, 2)
        self.assertEqual(listed_user.plan, "premium")
        self.assertEqual(listed_user.subscription_status, "active")

    def test_inactive_premium_subscription_is_shown_as_free(self) -> None:
        subscription = self.session.query(Subscription).one()
        subscription.status = "inactive"
        self.session.commit()

        response = read_admin_users(
            skip=0,
            limit=50,
            search=None,
            is_active=None,
            plan=None,
            db=self.session,
            current_admin=self.admin_account,
        )

        listed_user = next(item for item in response.items if item.id == self.user.id)
        self.assertEqual(listed_user.plan, "free")
        self.assertEqual(listed_user.subscription_status, "inactive")

    def test_expired_premium_subscription_is_shown_as_free(self) -> None:
        subscription = self.session.query(Subscription).one()
        subscription.current_period_end = utc_now() - timedelta(minutes=1)
        self.session.commit()

        response = read_admin_users(
            skip=0,
            limit=50,
            search=None,
            is_active=None,
            plan=None,
            db=self.session,
            current_admin=self.admin_account,
        )

        listed_user = next(item for item in response.items if item.id == self.user.id)
        self.assertEqual(listed_user.plan, "free")
        self.assertEqual(listed_user.subscription_status, "expired")

    def test_admin_can_filter_users_by_status_and_plan(self) -> None:
        inactive_user = User(
            email="inactive@example.com",
            username="inactiveuser",
            password_hash="test-hash",
            is_active=False,
        )
        self.session.add(inactive_user)
        self.session.commit()

        inactive_users = read_admin_users(
            skip=0,
            limit=50,
            search=None,
            is_active=False,
            plan="free",
            db=self.session,
            current_admin=self.admin_account,
        )
        premium_users = read_admin_users(
            skip=0,
            limit=50,
            search=None,
            is_active=True,
            plan="premium",
            db=self.session,
            current_admin=self.admin_account,
        )

        self.assertEqual(inactive_users.total, 1)
        self.assertEqual(inactive_users.items[0].id, inactive_user.id)
        self.assertEqual(premium_users.total, 1)
        self.assertEqual(premium_users.items[0].id, self.user.id)

    def test_admin_can_read_summary(self) -> None:
        response = read_admin_summary(
            db=self.session,
            current_admin=self.admin_account,
        )

        self.assertEqual(response.total_users, 2)
        self.assertEqual(response.active_users, 2)
        self.assertEqual(response.premium_users, 1)
        self.assertEqual(response.total_advertisements, 1)
        self.assertEqual(response.unresolved_inquiries, 0)
        self.assertEqual(response.paid_purchase_count, 1)
        self.assertEqual(response.paid_purchase_amount, 9900)
        self.assertEqual(response.monthly_paid_purchase_amount, 9900)

    def test_admin_can_read_user_detail(self) -> None:
        response = read_admin_user_detail(
            user_id=self.user.id,
            db=self.session,
            current_admin=self.admin_account,
        )

        self.assertEqual(response.username, "normaluser")
        self.assertEqual(response.advertisement_count, 1)

    def test_admin_can_list_purchase_histories(self) -> None:
        response = read_admin_purchase_histories(
            skip=0,
            limit=50,
            user_id=None,
            search=None,
            payment_status=None,
            db=self.session,
            current_admin=self.admin_account,
        )

        self.assertEqual(response.total, 1)
        self.assertEqual(response.items[0].username, "normaluser")
        self.assertEqual(response.items[0].amount, 9900)

    def test_admin_can_filter_purchase_histories_by_user_and_status(self) -> None:
        response = read_admin_purchase_histories(
            skip=0,
            limit=50,
            user_id=self.user.id,
            search=None,
            payment_status="paid",
            db=self.session,
            current_admin=self.admin_account,
        )

        self.assertEqual(response.total, 1)
        self.assertEqual(response.items[0].status, "paid")

    def test_admin_can_list_and_read_subscriptions(self) -> None:
        listed = read_admin_subscriptions(
            skip=0,
            limit=50,
            user_id=self.user.id,
            plan="premium",
            subscription_status="active",
            search="normaluser",
            db=self.session,
            current_admin=self.admin_account,
        )
        detail = read_admin_subscription_detail(
            subscription_id=listed.items[0].id,
            db=self.session,
            current_admin=self.admin_account,
        )

        self.assertEqual(listed.total, 1)
        self.assertEqual(listed.items[0].email, "user@example.com")
        self.assertEqual(detail.plan, "premium")
        self.assertEqual(detail.status, "active")

    def test_admin_can_read_purchase_history_detail(self) -> None:
        purchase = self.session.query(PurchaseHistory).one()

        response = read_admin_purchase_history_detail(
            purchase_id=purchase.id,
            db=self.session,
            current_admin=self.admin_account,
        )

        self.assertEqual(response.username, "normaluser")
        self.assertEqual(response.description, "프리미엄 월 구독 (테스트)")

    def test_admin_can_refund_demo_subscription_purchase(self) -> None:
        purchase = self.session.query(PurchaseHistory).one()

        response = refund_admin_demo_purchase(
            purchase_id=purchase.id,
            request=AdminDemoRefundRequest(reason="고객 요청"),
            db=self.session,
            current_admin=self.admin_account,
        )

        self.session.refresh(purchase)
        subscription = self.session.query(Subscription).one()
        self.assertEqual(response.purchase.status, "refunded")
        self.assertTrue(response.subscription_revoked)
        self.assertEqual(purchase.status, "refunded")
        self.assertEqual(subscription.plan, "free")
        self.assertEqual(subscription.status, "inactive")
        summary = read_admin_summary(
            db=self.session,
            current_admin=self.admin_account,
        )
        self.assertEqual(summary.premium_users, 0)
        self.assertEqual(summary.paid_purchase_count, 0)
        self.assertEqual(
            self.session.query(AdminAuditLog)
            .filter(AdminAuditLog.action == "purchase.refunded")
            .count(),
            1,
        )

    def test_admin_cannot_refund_the_same_purchase_twice(self) -> None:
        purchase = self.session.query(PurchaseHistory).one()
        request = AdminDemoRefundRequest(reason="고객 요청")

        refund_admin_demo_purchase(
            purchase_id=purchase.id,
            request=request,
            db=self.session,
            current_admin=self.admin_account,
        )

        with self.assertRaises(HTTPException) as context:
            refund_admin_demo_purchase(
                purchase_id=purchase.id,
                request=request,
                db=self.session,
                current_admin=self.admin_account,
            )

        self.assertEqual(context.exception.status_code, 409)

    def test_admin_cannot_refund_non_demo_purchase(self) -> None:
        purchase = self.session.query(PurchaseHistory).one()
        purchase.provider = "external"
        self.session.commit()

        with self.assertRaises(HTTPException) as context:
            refund_admin_demo_purchase(
                purchase_id=purchase.id,
                request=AdminDemoRefundRequest(reason="고객 요청"),
                db=self.session,
                current_admin=self.admin_account,
            )

        self.assertEqual(context.exception.status_code, 400)
        self.session.refresh(purchase)
        self.assertEqual(purchase.status, "paid")
        self.assertEqual(
            self.session.query(AdminAuditLog)
            .filter(AdminAuditLog.action == "purchase.refunded")
            .count(),
            0,
        )

    def test_refund_keeps_premium_with_another_paid_subscription(self) -> None:
        purchase = self.session.query(PurchaseHistory).one()
        self.session.add(
            PurchaseHistory(
                user_id=self.user.id,
                item_type="subscription",
                description="추가 프리미엄 구독",
                amount=9900,
                currency="KRW",
                status="paid",
            )
        )
        self.session.commit()

        response = refund_admin_demo_purchase(
            purchase_id=purchase.id,
            request=AdminDemoRefundRequest(reason="중복 결제"),
            db=self.session,
            current_admin=self.admin_account,
        )

        subscription = self.session.query(Subscription).one()
        self.assertFalse(response.subscription_revoked)
        self.assertEqual(subscription.plan, "premium")
        self.assertEqual(subscription.status, "active")

    def test_refund_rolls_back_when_audit_log_fails(self) -> None:
        purchase = self.session.query(PurchaseHistory).one()

        with patch(
            "app.api.admin.create_admin_audit_log",
            side_effect=RuntimeError("audit log failed"),
        ):
            with self.assertRaises(RuntimeError):
                refund_admin_demo_purchase(
                    purchase_id=purchase.id,
                    request=AdminDemoRefundRequest(reason="테스트"),
                    db=self.session,
                    current_admin=self.admin_account,
                )

        self.session.expire_all()
        restored_purchase = self.session.query(PurchaseHistory).one()
        restored_subscription = self.session.query(Subscription).one()
        self.assertEqual(restored_purchase.status, "paid")
        self.assertEqual(restored_subscription.plan, "premium")
        self.assertEqual(restored_subscription.status, "active")

    def test_missing_user_detail_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as context:
            read_admin_user_detail(
                user_id=9999,
                db=self.session,
                current_admin=self.admin_account,
            )

        self.assertEqual(context.exception.status_code, 404)

    def test_admin_can_deactivate_and_reactivate_normal_user(self) -> None:
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=create_access_token({"sub": str(self.user.id)}),
        )
        deactivated = update_admin_user_status(
            user_id=self.user.id,
            request=AdminUserStatusUpdateRequest(is_active=False),
            db=self.session,
            current_admin=self.admin_account,
        )
        self.assertFalse(deactivated.is_active)
        with self.assertRaises(HTTPException) as inactive_context:
            get_current_user(credentials=credentials, db=self.session)
        self.assertEqual(inactive_context.exception.status_code, 403)

        reactivated = update_admin_user_status(
            user_id=self.user.id,
            request=AdminUserStatusUpdateRequest(is_active=True),
            db=self.session,
            current_admin=self.admin_account,
        )
        self.assertTrue(reactivated.is_active)
        self.assertEqual(
            get_current_user(credentials=credentials, db=self.session).id,
            self.user.id,
        )

        audit_logs = read_admin_audit_logs(
            skip=0,
            limit=50,
            action="user.status_updated",
            db=self.session,
            current_admin=self.admin_account,
        )
        self.assertEqual(audit_logs.total, 2)
        self.assertEqual(audit_logs.items[0].target_id, self.user.id)

    def test_admin_cannot_change_own_status(self) -> None:
        with self.assertRaises(HTTPException) as context:
            update_admin_user_status(
                user_id=self.admin_user.id,
                request=AdminUserStatusUpdateRequest(is_active=False),
                db=self.session,
                current_admin=self.admin_account,
            )

        self.assertEqual(context.exception.status_code, 400)

    def test_admin_cannot_change_another_admin_status(self) -> None:
        other_admin_user = User(
            email="other-admin@example.com",
            username="otheradmin",
            password_hash="test-hash",
            is_active=True,
        )
        self.session.add(other_admin_user)
        self.session.commit()
        self.session.add(AdminAccount(user_id=other_admin_user.id))
        self.session.commit()

        with self.assertRaises(HTTPException) as context:
            update_admin_user_status(
                user_id=other_admin_user.id,
                request=AdminUserStatusUpdateRequest(is_active=False),
                db=self.session,
                current_admin=self.admin_account,
            )

        self.assertEqual(context.exception.status_code, 403)

    def test_admin_can_grant_premium_without_creating_purchase_history(self) -> None:
        free_user = User(
            email="free@example.com",
            username="freeuser",
            password_hash="test-hash",
            is_active=True,
        )
        self.session.add(free_user)
        self.session.commit()

        response = update_admin_user_subscription(
            user_id=free_user.id,
            request=AdminUserSubscriptionUpdateRequest(is_premium=True),
            db=self.session,
            current_admin=self.admin_account,
        )

        self.assertEqual(response.plan, "premium")
        self.assertEqual(response.subscription_status, "active")
        subscription = (
            self.session.query(Subscription)
            .filter(Subscription.user_id == free_user.id)
            .one()
        )
        self.assertEqual(subscription.provider, "admin")
        self.assertEqual(
            self.session.query(PurchaseHistory)
            .filter(PurchaseHistory.user_id == free_user.id)
            .count(),
            0,
        )
        premium_balance = (
            self.session.query(PremiumCreditBalance)
            .filter(PremiumCreditBalance.user_id == free_user.id)
            .one()
        )
        self.assertEqual(premium_balance.credits_remaining, 30)

    def test_refund_request_approval_revokes_demo_premium(self) -> None:
        purchase = self.session.query(PurchaseHistory).one()
        refund = RefundRequest(
            purchase_id=purchase.id,
            user_id=self.user.id,
            amount=purchase.amount,
            reason="서비스 미사용",
        )
        self.session.add(refund)
        self.session.commit()

        response = approve_admin_refund(
            refund_id=refund.id,
            db=self.session,
            current_admin=self.admin_account,
        )

        self.assertEqual(response.status, "approved")
        subscription = self.session.query(Subscription).one()
        self.session.refresh(purchase)
        self.session.refresh(subscription)
        self.assertEqual(purchase.status, "refunded")
        self.assertEqual(subscription.plan, "free")
        self.assertEqual(subscription.status, "inactive")

    def test_admin_password_schema_enforces_account_password_rule(self) -> None:
        with self.assertRaises(ValueError):
            AdminPasswordChangeRequest(
                current_password="Password1!",
                new_password="onlylowercase",
            )

        request = AdminPasswordChangeRequest(
            current_password="Password1!",
            new_password="NewPassword2!",
        )
        self.assertEqual(request.new_password, "NewPassword2!")

    def test_admin_can_revoke_premium_access(self) -> None:
        response = update_admin_user_subscription(
            user_id=self.user.id,
            request=AdminUserSubscriptionUpdateRequest(is_premium=False),
            db=self.session,
            current_admin=self.admin_account,
        )

        self.assertEqual(response.plan, "free")
        self.assertEqual(response.subscription_status, "inactive")


if __name__ == "__main__":
    unittest.main()
