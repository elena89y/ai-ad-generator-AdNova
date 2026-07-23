import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.crud.account import update_notification_settings
from app.database.connection import Base
from app.database.models import CreditBalance, NotificationSettings, User
from app.services.notification_service import (
    notify_credit_depletion,
    send_marketing_notifications,
)


class NotificationServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.user = User(
            email="notify@example.com",
            username="notifyuser",
            password_hash="hash",
            is_active=True,
        )
        self.session.add(self.user)
        self.session.commit()

    def tearDown(self) -> None:
        self.session.close()
        Base.metadata.drop_all(bind=self.engine)
        self.engine.dispose()

    @patch("app.services.notification_service.send_credit_low_email")
    def test_credit_depletion_alert_respects_setting(self, send_email) -> None:
        update_notification_settings(
            self.session,
            self.user.id,
            {"credit_depletion_alert": True},
        )
        self.session.add(CreditBalance(user_id=self.user.id, free_credits_remaining=1))
        self.session.commit()

        self.assertTrue(notify_credit_depletion(self.session, self.user.id))
        send_email.assert_called_once_with("notify@example.com", 1)

        self.session.query(NotificationSettings).update(
            {NotificationSettings.credit_depletion_alert: False}
        )
        self.session.commit()
        send_email.reset_mock()
        self.assertFalse(notify_credit_depletion(self.session, self.user.id))
        send_email.assert_not_called()

    @patch("app.services.notification_service.send_marketing_email")
    def test_marketing_mail_only_targets_opted_in_active_users(self, send_email) -> None:
        opted_in = NotificationSettings(user_id=self.user.id, marketing_updates=True)
        opted_out = User(
            email="optout@example.com",
            username="optoutuser",
            password_hash="hash",
            is_active=True,
            notification_settings=NotificationSettings(marketing_updates=False),
        )
        inactive = User(
            email="inactive@example.com",
            username="inactiveuser",
            password_hash="hash",
            is_active=False,
            notification_settings=NotificationSettings(marketing_updates=True),
        )
        self.session.add_all([opted_in, opted_out, inactive])
        self.session.commit()

        result = send_marketing_notifications(
            self.session,
            subject="새 소식",
            message="새 기능이 추가됐어요.",
        )

        self.assertEqual(result, (1, 1, 0))
        send_email.assert_called_once_with(
            "notify@example.com",
            "새 소식",
            "새 기능이 추가됐어요.",
        )
