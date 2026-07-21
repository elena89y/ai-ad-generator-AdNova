"""AdNova FastAPI 앱 진입점."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
import os
from fastapi.middleware.cors import CORSMiddleware

from app.api import account, admin, ads, billing, chatbot, dashboard, history, images, inquiries
from app.api.auth import router as auth_router
from app.api.google_auth import router as google_auth_router
from app.api.kakao_auth import router as kakao_auth_router
from app.api.naver_auth import router as naver_auth_router
from app.api.export import router as export_router
from app.core.config import settings
from app.core.observability import init_langfuse, shutdown_langfuse
from app.database import admin_models, billing_models, models
from app.database.connection import Base, engine

# env(.env) 는 core.config 임포트 시점에 이미 로드됨 — Langfuse 는 그 다음, 첫 OpenAI/
# LangChain 호출보다 반드시 앞서 초기화(자격증명 누락 방지, 마스킹 훅 등록).
init_langfuse()

Base.metadata.create_all(bind=engine)
# 리텐션 마이그레이션 자동 적용: create_all 이 못 하는 기존 테이블 컬럼 추가(anonymized_at)를
# 기동 시 멱등하게 반영 → 배포 시 수동 마이그레이션 불필요 (한의정, 07-21).
from app.scripts.migrate_retention import ensure_retention_columns  # noqa: E402

ensure_retention_columns(engine)
upload_dir = Path(settings.UPLOAD_DIR)
upload_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="AdNova API",
    description="AI Ad Generator Backend API",
    version="0.1.0",
)

# 리텐션 파기 배치를 인앱 스케줄러로 자동 실행 → 외부 cron 등록 불필요 (한의정, 07-21).
# RETENTION_PURGE_ENABLED=0 이면 비활성(외부 cron 선택 시).
from app.services.retention_scheduler import start_purge_scheduler  # noqa: E402

start_purge_scheduler(app)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET_KEY", "change-this-session-secret"),
    same_site="lax",
    https_only=os.getenv("SESSION_HTTPS_ONLY", "false").lower() == "true",
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
app.include_router(inquiries.router, prefix=settings.API_PREFIX)
app.include_router(chatbot.router, prefix=settings.API_PREFIX)  # 고객센터 챗봇 (한의정, 07-21 활성화 승인)


@app.get("/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.on_event("shutdown")
def _flush_langfuse() -> None:
    """큐에 남은 트레이스 이벤트를 종료 전 전송(Langfuse 미설정 시 무해하게 스킵)."""
    shutdown_langfuse()
