import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEFAULT_UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"


class Settings:
    PROJECT_NAME: str = "AdNova_AI Ad Generator"
    API_PREFIX: str = "/api"
    ADMIN_DATABASE_URL: str = os.getenv(
        "ADMIN_DATABASE_URL",
        "sqlite:///./data/admin.db",
    )

    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-this-secret-key")
    ADMIN_TOTP_ENCRYPTION_KEY: str = os.getenv("ADMIN_TOTP_ENCRYPTION_KEY", "")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    )
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", str(DEFAULT_UPLOAD_DIR))
    # 15MB: 폰 원본(12MB급) 수용 — 업로드 즉시 정규화(장변 2048)로 축소 저장되므로 부담 없음
    MAX_IMAGE_SIZE_MB: int = int(os.getenv("MAX_IMAGE_SIZE_MB", "15"))
    CORS_ORIGINS: tuple[str, ...] = tuple(
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5500,http://127.0.0.1:5500",
        ).split(",")
        if origin.strip()
    )

    # 생성 서비스 위치 (배포 구조 B). 비면 로컬(모놀리식) 실행, URL 이면 HTTP 호출.
    #   예) 웹 백엔드(Docker): GENERATION_SERVICE_URL=http://<gpu-vm>:8100
    GENERATION_SERVICE_URL: str = os.getenv("GENERATION_SERVICE_URL", "")
    GENERATION_TIMEOUT_S: int = int(os.getenv("GENERATION_TIMEOUT_S", "180"))

    # LangGraph 문구 품질 게이트 루프 사용 (1=사용, 0=끄고 gpt_service 직접 호출로 폴백).
    # langgraph 미설치 시에도 자동 폴백 — 제거 가능 설계.
    USE_COPY_GATE: bool = os.getenv("USE_COPY_GATE", "1") == "1"


settings = Settings()
