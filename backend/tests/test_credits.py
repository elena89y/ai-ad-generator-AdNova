import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.crud.credits import (
    consume_bonus_credit,
    consume_free_credit,
    get_bonus_credits_remaining,
    get_purchased_credits_remaining,
    consume_premium_credit,
    get_credit_balance,
    get_credit_status,
    get_premium_credit_status,
    grant_bonus_credits,
    grant_premium_credits,
    grant_purchased_credits,
    restore_bonus_credit,
    restore_free_credit,
    restore_premium_credit,
    restore_purchased_credit,
    consume_purchased_credit,
)
from app.database.connection import Base
from app.database.models import User


class CreditBalanceCrudTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.user = User(
            email="credits@example.com",
            username="credits1",
            password_hash="test-hash",
            is_active=True,
        )
        self.session.add(self.user)
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    def test_credit_balance_is_created_once_and_persists(self) -> None:
        self.assertEqual(get_credit_balance(self.session, self.user.id).free_credits_remaining, 3)
        self.assertEqual(consume_free_credit(self.session, self.user.id), 2)
        self.assertEqual(get_credit_balance(self.session, self.user.id).free_credits_remaining, 2)

    def test_credit_cannot_be_consumed_after_all_free_credits_are_used(self) -> None:
        self.assertEqual(consume_free_credit(self.session, self.user.id), 2)
        self.assertEqual(consume_free_credit(self.session, self.user.id), 1)
        self.assertEqual(consume_free_credit(self.session, self.user.id), 0)
        self.assertIsNone(consume_free_credit(self.session, self.user.id))

    def test_failed_generation_can_restore_one_credit(self) -> None:
        consume_free_credit(self.session, self.user.id)

        self.assertEqual(restore_free_credit(self.session, self.user.id), 3)

    def test_bonus_credits_are_persistent_and_can_be_restored(self) -> None:
        self.assertEqual(get_bonus_credits_remaining(self.session, self.user.id), 0)
        grant_bonus_credits(self.session, self.user.id, 5)

        self.assertEqual(consume_bonus_credit(self.session, self.user.id), 4)
        self.assertEqual(restore_bonus_credit(self.session, self.user.id), 5)

    def test_one_credit_is_refilled_every_24_hours(self) -> None:
        now = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(consume_free_credit(self.session, self.user.id, now=now), 2)
        self.assertEqual(consume_free_credit(self.session, self.user.id, now=now), 1)
        self.assertEqual(consume_free_credit(self.session, self.user.id, now=now), 0)

        balance, next_refill_at = get_credit_status(
            self.session,
            self.user.id,
            now=now + timedelta(hours=23),
        )
        self.assertEqual(balance.free_credits_remaining, 0)
        self.assertEqual(next_refill_at, now + timedelta(days=1))

        balance, next_refill_at = get_credit_status(
            self.session,
            self.user.id,
            now=now + timedelta(days=1),
        )
        self.assertEqual(balance.free_credits_remaining, 1)
        self.assertEqual(next_refill_at, now + timedelta(days=2))

        balance, next_refill_at = get_credit_status(
            self.session,
            self.user.id,
            now=now + timedelta(days=3),
        )
        self.assertEqual(balance.free_credits_remaining, 3)
        self.assertIsNone(next_refill_at)

    def test_premium_credits_are_renewed_every_30_days(self) -> None:
        now = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
        next_reset_at = now + timedelta(days=30)
        balance = grant_premium_credits(
            self.session,
            self.user.id,
            next_reset_at=next_reset_at,
            now=now,
        )

        self.assertEqual(balance.credits_remaining, 30)
        self.assertEqual(
            consume_premium_credit(
                self.session,
                self.user.id,
                next_reset_at=next_reset_at,
                now=now,
            ),
            29,
        )

        balance, reset_at = get_premium_credit_status(
            self.session,
            self.user.id,
            now=next_reset_at,
        )
        self.assertEqual(balance.credits_remaining, 30)
        self.assertEqual(reset_at, next_reset_at + timedelta(days=30))

    def test_premium_credit_cannot_drop_below_zero_and_can_be_restored(self) -> None:
        now = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
        next_reset_at = now + timedelta(days=30)
        grant_premium_credits(
            self.session,
            self.user.id,
            next_reset_at=next_reset_at,
            now=now,
        )

        for expected in range(29, -1, -1):
            self.assertEqual(
                consume_premium_credit(
                    self.session,
                    self.user.id,
                    next_reset_at=next_reset_at,
                    now=now,
                ),
                expected,
            )
        self.assertIsNone(
            consume_premium_credit(
                self.session,
                self.user.id,
                next_reset_at=next_reset_at,
                now=now,
            )
        )
        self.assertEqual(
            restore_premium_credit(
                self.session,
                self.user.id,
                next_reset_at=next_reset_at,
            ),
            1,
        )

    def test_purchased_credits_are_separate_and_can_be_restored(self) -> None:
        self.assertEqual(get_purchased_credits_remaining(self.session, self.user.id), 0)
        grant_purchased_credits(self.session, self.user.id, 10)

        self.assertEqual(consume_purchased_credit(self.session, self.user.id), 9)
        self.assertEqual(restore_purchased_credit(self.session, self.user.id), 10)
        self.assertEqual(get_credit_balance(self.session, self.user.id).free_credits_remaining, 3)


if __name__ == "__main__":
    unittest.main()
