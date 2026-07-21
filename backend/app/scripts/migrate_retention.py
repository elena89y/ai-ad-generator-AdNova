"""리텐션 마이그레이션 — anonymized_at 컬럼 추가 (멱등) — 담당: 한의정.

배경: DB 초기화가 Base.metadata.create_all() 이라 기존 테이블에 신규 컬럼이 반영되지
않는다(create_all 은 CREATE TABLE IF NOT EXISTS 만 수행). 이 스크립트가 기존 운영 DB
(SQLite)의 3개 테이블에 anonymized_at 컬럼을 추가한다.

⚠️ 배포 순서: 신 코드 배포 "전에" 반드시 이 스크립트를 먼저 실행해야 한다.
  (컬럼 없이 신 코드가 뜨면 탈퇴 시 anonymize UPDATE 가 OperationalError → 롤백)

센티넬 방식이라 user_id NOT NULL→NULL 같은 테이블 재작성은 불필요 — ADD COLUMN 뿐이라
SQLite 에서도 안전하고 멱등하다.

실행 (backend/ 에서):
  ../.venv/bin/python -m app.scripts.migrate_retention
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text

from app.database import billing_models  # noqa: F401 - 메타데이터 등록
from app.database.connection import engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

_TABLES = ("support_inquiries", "purchase_histories", "refund_requests")
_COLUMN = "anonymized_at"


def main() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table in _TABLES:
            if table not in existing_tables:
                logger.info("%s 테이블 없음 — create_all 이 생성하므로 건너뜀", table)
                continue
            columns = {c["name"] for c in inspector.get_columns(table)}
            if _COLUMN in columns:
                logger.info("%s.%s 이미 존재 — 건너뜀", table, _COLUMN)
                continue
            # timestamp 계열. SQLite=DATETIME / PostgreSQL=TIMESTAMP 둘 다 수용하는 표기.
            col_type = "TIMESTAMP" if engine.dialect.name != "sqlite" else "DATETIME"
            conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {_COLUMN} {col_type}'))
            logger.info("%s.%s 추가 완료", table, _COLUMN)
    logger.info("리텐션 마이그레이션 완료")


if __name__ == "__main__":
    main()
