"""AdNova FastAPI 앱 진입점."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
import os
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import account, admin, ads, billing, dashboard, history, images
from app.api.auth import router as auth_router
from app.api.google_auth import router as google_auth_router
from app.api.kakao_auth import router as kakao_auth_router
from app.api.naver_auth import router as naver_auth_router
from app.api.export import router as export_router
from app.core.config import settings
from app.database import admin_models, models
from app.database.connection import Base, engine

Base.metadata.create_all(bind=engine)
upload_dir = Path(settings.UPLOAD_DIR)
upload_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="AdNova API",
    description="AI Ad Generator Backend API",
    version="0.1.0",
)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET_KEY"),
    same_site="lax",
    https_only=False, # HTTPS 도메인 적용 후 True로 변경
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.CORS_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix=settings.API_PREFIX)
app.include_router(account.router, prefix=settings.API_PREFIX)
app.include_router(admin.router, prefix=settings.API_PREFIX)
app.include_router(google_auth_router, prefix=settings.API_PREFIX)
app.include_router(kakao_auth_router, prefix=settings.API_PREFIX)
app.include_router(naver_auth_router, prefix=settings.API_PREFIX)
app.include_router(export_router, prefix=settings.API_PREFIX)
app.include_router(ads.router, prefix=settings.API_PREFIX)
app.include_router(billing.router, prefix=settings.API_PREFIX)
app.include_router(dashboard.router, prefix=settings.API_PREFIX)
app.include_router(history.router, prefix=settings.API_PREFIX)
app.include_router(images.router, prefix=settings.API_PREFIX)
app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
