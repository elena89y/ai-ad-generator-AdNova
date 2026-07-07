import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEFAULT_UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"


class Settings:
    PROJECT_NAME: str = "AdNova_AI Ad Generator"
    API_PREFIX: str = "/api"

    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-this-secret-key")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    )
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", str(DEFAULT_UPLOAD_DIR))
    MAX_IMAGE_SIZE_MB: int = int(os.getenv("MAX_IMAGE_SIZE_MB", "10"))

    # 생성 서비스 위치 (배포 구조 B). 비면 로컬(모놀리식) 실행, URL 이면 HTTP 호출.
    #   예) 웹 백엔드(Docker): GENERATION_SERVICE_URL=http://<gpu-vm>:8100
    GENERATION_SERVICE_URL: str = os.getenv("GENERATION_SERVICE_URL", "")
    GENERATION_TIMEOUT_S: int = int(os.getenv("GENERATION_TIMEOUT_S", "180"))


settings = Settings()
