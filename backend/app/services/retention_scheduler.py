"""리텐션 파기 배치 인앱 스케줄러 — 담당: 한의정.

보존기간 경과 기록 파기(purge_expired_records)를 앱 내부에서 주기 실행한다 →
외부 cron/systemd timer 등록 없이 자동 동작(연정님 인프라 수동 단계 제거).

- 기동 직후 1회 + 이후 RETENTION_PURGE_INTERVAL_HOURS(기본 24h)마다 실행.
  자동배포로 앱이 자주 재기동돼도 각 기동 직후 실행되므로 "지체 없이 파기"에 유리.
- 웹 서비스는 uvicorn 단일 워커(--workers 미지정)라 중복 실행 우려 없음.
- 실패는 로그만 남기고 다음 주기 재시도 — 파기 실패가 앱을 죽이지 않는다.
- 외부 cron 을 쓰고 싶으면 RETENTION_PURGE_ENABLED=0 으로 끄면 됨(연정님 선택).
"""
from __future__ import annotations

import asyncio
import logging
import os

from app.crud.retention import purge_expired_records
from app.database.connection import SessionLocal

logger = logging.getLogger(__name__)


def _interval_seconds() -> float:
    try:
        hours = float(os.getenv("RETENTION_PURGE_INTERVAL_HOURS", "24"))
    except ValueError:
        hours = 24.0
    return max(hours, 1.0) * 3600.0


def run_purge_once() -> dict[str, int]:
    """파기 1회 실행 (독립 세션). 스케줄러·수동 호출 공용."""
    db = SessionLocal()
    try:
        return purge_expired_records(db)
    finally:
        db.close()


async def _purge_loop() -> None:
    interval = _interval_seconds()
    while True:
        try:
            result = await asyncio.to_thread(run_purge_once)
            if any(result.values()):
                logger.info(
                    "리텐션 파기: 문의 %d · 환불 %d · 구매 %d",
                    result["inquiries"], result["refunds"], result["purchases"],
                )
        except Exception:  # noqa: BLE001 — 파기 실패가 스케줄러/앱을 죽이면 안 됨
            logger.warning("리텐션 파기 배치 실패 (다음 주기 재시도)", exc_info=True)
        await asyncio.sleep(interval)


def start_purge_scheduler(app) -> None:  # noqa: ANN001
    """FastAPI startup 에 파기 루프를 등록. RETENTION_PURGE_ENABLED=0 이면 비활성."""
    if os.getenv("RETENTION_PURGE_ENABLED", "1") == "0":
        logger.info("리텐션 파기 스케줄러 비활성 (RETENTION_PURGE_ENABLED=0) — 외부 cron 사용")
        return

    @app.on_event("startup")
    async def _start_purge_scheduler() -> None:  # noqa: ANN202
        app.state.purge_task = asyncio.create_task(_purge_loop())
        logger.info("리텐션 파기 스케줄러 시작 (주기 %.0fh)", _interval_seconds() / 3600)

    @app.on_event("shutdown")
    async def _stop_purge_scheduler() -> None:  # noqa: ANN202
        task = getattr(app.state, "purge_task", None)
        if task is not None:
            task.cancel()
