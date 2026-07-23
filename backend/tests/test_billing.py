import unittest
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.billing import (
    cancel_subscription,
    change_demo_payment_method,
    create_demo_subscription,
    create_payment_method_change_session,
    purchase_credit_pack,
    read_billing_summary,
    read_purchase_histories,
    resume_canceled_subscription,
)
from app.database.billing_models import (
    PaymentMethod,
    PremiumCreditBalance,
    PurchasedCreditBalance,
    PurchaseHistory,
    Subscription,
)
from app.database.connection import Base
from app.database.models import User
from app.crud.credits import grant_bonus_credits
from app.schemas.billing import CreditPackRequest, DemoCardRequest


class BillingApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.session = sessionmaker(bind=self.engine)()

        self.user = User(
            email="billing@example.com",
            username="billing1",
            password_hash="test-hash",
            is_active=True,
        )
        self.other_user = User(
            email="other@example.com",
            username="billing2",
            password_hash="test-hash",
            is_active=True,
        )
        self.session.add_all([self.user, self.other_user])
        self.session.commit()

        period_end = datetime.now(timezone.utc) + timedelta(days=20)
        self.subscription = Subscription(
            user_id=self.user.id,
            plan="premium",
            status="active",
            current_period_end=period_end,
        )
        self.payment_method = PaymentMethod(
            user_id=self.user.id,
            provider="test-provider",
            card_brand="테스트카드",
            card_last4="1234",
        )
        self.session.add_all(
            [
                self.subscription,
                self.payment_method,
                PurchaseHistory(
                    user_id=self.user.id,
                    item_type="subscription",
                    description="프리미엄 월 구독",
                    amount=9900,
                    currency="KRW",
                    status="paid",
                ),
                PurchaseHistory(
                    user_id=self.other_user.id,
                    item_type="subscription",
                    description="다른 사용자 결제",
                    amount=9900,
                    currency="KRW",
                    status="paid",
                ),
            ]
        )
        self.session.commit()
        self.session.refresh(self.subscription)

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_summary_uses_current_user_billing_data(self) -> None:
        summary = read_billing_summary(db=self.session, current_user=self.user)

        self.assertTrue(summary.is_premium)
        self.assertEqual(summary.free_credits_remaining, 3)
        self.assertEqual(summary.free_credit_limit, 3)
        self.assertIsNone(summary.next_free_credit_at)
        self.assertEqual(summary.bonus_credits_remaining, 0)
        self.assertEqual(summary.purchased_credits_remaining, 0)
        self.assertEqual(summary.premium_credits_remaining, 30)
        self.assertEqual(summary.premium_credit_limit, 30)
        self.assertEqual(
            summary.next_premium_credit_at,
            self.subscription.current_period_end.replace(tzinfo=timezone.utc),
        )
        self.assertEqual(summary.subscription.id, self.subscription.id)
        self.assertEqual(summary.payment_method.card_last4, "1234")

    def test_summary_includes_admin_granted_bonus_credits(self) -> None:
        grant_bonus_credits(self.session, self.user.id, 7)

        summary = read_billing_summary(db=self.session, current_user=self.user)

        self.assertEqual(summary.bonus_credits_remaining, 7)

    def test_expired_subscription_loses_premium_access(self) -> None:
        self.subscription.current_period_end = datetime.now(timezone.utc) - timedelta(
            minutes=1
        )
        self.session.commit()

        summary = read_billing_summary(db=self.session, current_user=self.user)

        self.assertFalse(summary.is_premium)
        self.assertEqual(summary.subscription.status, "expired")
        self.assertIsNone(summary.premium_credits_remaining)

    def test_canceled_subscription_ends_after_current_period(self) -> None:
        self.subscription.current_period_end = datetime.now(timezone.utc) - timedelta(
            minutes=1
        )
        self.subscription.cancel_at_period_end = True
        self.session.commit()

        summary = read_billing_summary(db=self.session, current_user=self.user)

        self.assertFalse(summary.is_premium)
        self.assertEqual(summary.subscription.status, "canceled")
        self.assertFalse(summary.subscription.cancel_at_period_end)

    def test_purchase_history_does_not_include_other_user(self) -> None:
        histories = read_purchase_histories(
            limit=50,
            db=self.session,
            current_user=self.user,
        )

        self.assertEqual(len(histories), 1)
        self.assertEqual(histories[0].description, "프리미엄 월 구독")

    def test_subscription_can_be_canceled_and_resumed(self) -> None:
        canceled = cancel_subscription(db=self.session, current_user=self.user)

        self.assertTrue(canceled.is_premium)
        self.assertTrue(canceled.subscription.cancel_at_period_end)
        self.assertIsNotNone(canceled.subscription.cancel_requested_at)

        resumed = resume_canceled_subscription(
            db=self.session,
            current_user=self.user,
        )

        self.assertTrue(resumed.is_premium)
        self.assertFalse(resumed.subscription.cancel_at_period_end)
        self.assertIsNone(resumed.subscription.cancel_requested_at)

    def test_user_without_subscription_cannot_cancel(self) -> None:
        with self.assertRaises(HTTPException) as context:
            cancel_subscription(db=self.session, current_user=self.other_user)

        self.assertEqual(context.exception.status_code, 409)

    def test_payment_method_change_waits_for_provider_integration(self) -> None:
        with self.assertRaises(HTTPException) as context:
            create_payment_method_change_session(current_user=self.user)

        self.assertEqual(context.exception.status_code, 503)

    def test_demo_subscription_creates_billing_records(self) -> None:
        request = DemoCardRequest(card_brand="Visa", card_last4="4242")

        summary = create_demo_subscription(
            request=request,
            db=self.session,
            current_user=self.other_user,
        )

        self.assertTrue(summary.is_premium)
        self.assertEqual(summary.subscription.provider, "demo")
        self.assertEqual(summary.payment_method.card_brand, "Visa")
        self.assertEqual(summary.payment_method.card_last4, "4242")
        premium_balance = (
            self.session.query(PremiumCreditBalance)
            .filter(PremiumCreditBalance.user_id == self.other_user.id)
            .one()
        )
        self.assertEqual(premium_balance.credits_remaining, 30)
        self.assertEqual(
            premium_balance.next_reset_at,
            summary.subscription.current_period_end,
        )

        purchases = read_purchase_histories(
            limit=50,
            db=self.session,
            current_user=self.other_user,
        )
        self.assertEqual(len(purchases), 2)
        self.assertEqual(purchases[0].amount, 9900)
        self.assertEqual(purchases[0].status, "paid")

    def test_active_demo_subscription_cannot_be_created_twice(self) -> None:
        request = DemoCardRequest(card_brand="Visa", card_last4="4242")

        with self.assertRaises(HTTPException) as context:
            create_demo_subscription(
                request=request,
                db=self.session,
                current_user=self.user,
            )

        self.assertEqual(context.exception.status_code, 409)

    def test_demo_payment_method_can_be_changed(self) -> None:
        request = DemoCardRequest(card_brand="Mastercard", card_last4="5678")

        summary = change_demo_payment_method(
            request=request,
            db=self.session,
            current_user=self.user,
        )

        self.assertEqual(summary.payment_method.card_brand, "Mastercard")
        self.assertEqual(summary.payment_method.card_last4, "5678")

    def test_premium_user_can_purchase_credit_pack(self) -> None:
        summary = purchase_credit_pack(
            request=CreditPackRequest(
                product_id="credit_10",
                card_brand="Visa",
                card_last4="4242",
            ),
            db=self.session,
            current_user=self.user,
        )

        self.assertEqual(summary.purchased_credits_remaining, 10)
        balance = self.session.query(PurchasedCreditBalance).filter(
            PurchasedCreditBalance.user_id == self.user.id
        ).one()
        self.assertEqual(balance.credits_remaining, 10)
        purchase = self.session.query(PurchaseHistory).filter(
            PurchaseHistory.user_id == self.user.id,
            PurchaseHistory.item_type == "credit_pack",
        ).one()
        self.assertEqual(purchase.amount, 4900)

    def test_non_premium_user_cannot_purchase_credit_pack(self) -> None:
        with self.assertRaises(HTTPException) as context:
            purchase_credit_pack(
                request=CreditPackRequest(
                    product_id="credit_10",
                    card_brand="Visa",
                    card_last4="4242",
                ),
                db=self.session,
                current_user=self.other_user,
            )

        self.assertEqual(context.exception.status_code, 403)

if __name__ == "__main__":
    unittest.main()
