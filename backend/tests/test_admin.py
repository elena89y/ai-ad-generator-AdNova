import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.admin import (
    read_admin_me,
    read_admin_purchase_histories,
    read_admin_user_detail,
    read_admin_users,
    update_admin_user_status,
    update_admin_user_subscription,
)
from app.core.admin_security import get_current_admin
from app.database.admin_models import AdminAccount
from app.database.billing_models import PurchaseHistory, Subscription
from app.database.connection import Base
from app.database.models import Advertisement, User
from app.schemas.admin import (
    AdminUserStatusUpdateRequest,
    AdminUserSubscriptionUpdateRequest,
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

    def test_admin_can_list_users_with_subscription_status(self) -> None:
        response = read_admin_users(
            skip=0,
            limit=50,
            search=None,
            db=self.session,
            current_admin=self.admin_account,
        )

        listed_user = next(item for item in response.items if item.id == self.user.id)
        self.assertEqual(response.total, 2)
        self.assertEqual(listed_user.plan, "premium")
        self.assertEqual(listed_user.subscription_status, "active")

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

    def test_missing_user_detail_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as context:
            read_admin_user_detail(
                user_id=9999,
                db=self.session,
                current_admin=self.admin_account,
            )

        self.assertEqual(context.exception.status_code, 404)

    def test_admin_can_deactivate_and_reactivate_normal_user(self) -> None:
        deactivated = update_admin_user_status(
            user_id=self.user.id,
            request=AdminUserStatusUpdateRequest(is_active=False),
            db=self.session,
            current_admin=self.admin_account,
        )
        self.assertFalse(deactivated.is_active)

        reactivated = update_admin_user_status(
            user_id=self.user.id,
            request=AdminUserStatusUpdateRequest(is_active=True),
            db=self.session,
            current_admin=self.admin_account,
        )
        self.assertTrue(reactivated.is_active)

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
