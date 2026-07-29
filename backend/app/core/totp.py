import base64
import hashlib
import io

import pyotp
import qrcode
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _get_fernet() -> Fernet:
    if settings.ADMIN_TOTP_ENCRYPTION_KEY:
        return Fernet(settings.ADMIN_TOTP_ENCRYPTION_KEY.encode())

    key = base64.urlsafe_b64encode(
        hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    )
    return Fernet(key)


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def encrypt_totp_secret(secret: str) -> str:
    return _get_fernet().encrypt(secret.encode()).decode()


def decrypt_totp_secret(encrypted_secret: str) -> str:
    try:
        return _get_fernet().decrypt(encrypted_secret.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("TOTP 비밀키를 복호화할 수 없습니다.") from exc


def build_totp_provisioning_uri(secret: str, username: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(
        name=username,
        issuer_name="AdNova Admin",
    )


def build_totp_qr_code_data_url(provisioning_uri: str) -> str:
    qr = qrcode.make(provisioning_uri)
    buffer = io.BytesIO()
    qr.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def verify_totp_code(encrypted_secret: str, code: str) -> bool:
    secret = decrypt_totp_secret(encrypted_secret)
    return pyotp.TOTP(secret).verify(code, valid_window=1)
