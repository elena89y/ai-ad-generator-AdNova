"""보존기간 경과 법정기록 파기 배치 — 담당: 한의정.

전자상거래법 시행령 제6조 최소 보존기간(문의 3년·결제 5년)이 지난 기록을 파기한다.
개인정보보호법상 과보관 방지 — 보존의무가 끝나면 지체 없이 파기.

실행 (backend/ 에서):
  ../.venv/bin/python -m app.scripts.purge_expired_records
cron 등록 예 (하루 1회 03:00):
  0 3 * * *  cd .../backend && ../.venv/bin/python -m app.scripts.purge_expired_records

⚠️ cron 스케줄 등록은 인프라(연정님) 영역 — LEGAL_RETENTION_COORDINATION.md (C) 참조.
"""
from __future__ import annotations

import logging

from app.crud.retention import purge_expired_records
from app.database import billing_models  # noqa: F401 - 테이블 메타데이터 등록
from app.database.connection import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    db = SessionLocal()
    try:
        result = purge_expired_records(db)
        logger.info(
            "보존기간 경과 기록 파기 완료 — 문의 %d · 환불 %d · 구매 %d",
            result["inquiries"],
            result["refunds"],
            result["purchases"],
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
