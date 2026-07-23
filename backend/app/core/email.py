"""SES SMTP 이메일 발송 유틸 — 인증번호·알림 공용."""
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_email(to_email: str, subject: str, html: str) -> None:
    """단건 HTML 메일 발송. 실패 시 예외 전파 — 호출부에서 처리."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
        server.starttls()
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.sendmail(settings.SMTP_FROM, to_email, msg.as_string())


def _base_template(title: str, body_html: str) -> str:
    return f"""
    <div style="font-family:-apple-system,sans-serif;max-width:480px;margin:0 auto;padding:24px;">
      <h2 style="color:#1a1a2e;">{title}</h2>
      {body_html}
      <p style="color:#888;font-size:12px;margin-top:24px;">
        본인이 요청하지 않았다면 이 메일을 무시하세요.<br/>AdNova · AI 광고 생성 플랫폼
      </p>
    </div>
    """


def send_verification_email(to_email: str, code: str) -> None:
    html = _base_template(
        "AdNova 이메일 인증",
        f"""<p>아래 인증번호를 입력해 주세요. 유효시간은 5분입니다.</p>
        <div style="font-size:32px;font-weight:bold;letter-spacing:8px;background:#f4f4f5;
                    padding:16px;text-align:center;border-radius:8px;">{code}</div>""",
    )
    send_email(to_email, "[AdNova] 이메일 인증번호", html)


def send_ad_complete_email(to_email: str, ad_title: str) -> None:
    html = _base_template(
        "광고 생성이 완료됐어요",
        f"<p><b>{ad_title}</b> 광고가 준비됐습니다. AdNova에서 확인해 보세요.</p>",
    )
    send_email(to_email, "[AdNova] 광고 생성 완료", html)


def send_credit_low_email(to_email: str, remaining: int) -> None:
    html = _base_template(
        "크레딧이 얼마 남지 않았어요",
        f"<p>남은 크레딧: <b>{remaining}개</b>. 플랜 & 결제에서 충전할 수 있어요.</p>",
    )
    send_email(to_email, "[AdNova] 크레딧 소진 알림", html)


def send_marketing_email(to_email: str, subject: str, message: str) -> None:
    html = _base_template(
        escape(subject),
        f"<p style=\"white-space:pre-line;\">{escape(message)}</p>",
    )
    send_email(to_email, f"[AdNova] {subject}", html)
