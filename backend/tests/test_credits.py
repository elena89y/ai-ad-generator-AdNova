import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.crud.credits import (
    consume_free_credit,
    get_credit_balance,
    restore_free_credit,
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


if __name__ == "__main__":
    unittest.main()
