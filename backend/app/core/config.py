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


settings = Settings()
