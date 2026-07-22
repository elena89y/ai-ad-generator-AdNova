"""리텐션 마이그레이션 — anonymized_at 컬럼 추가 (멱등) — 담당: 한의정.

배경: DB 초기화가 Base.metadata.create_all() 이라 기존 테이블에 신규 컬럼이 반영되지
않는다(create_all 은 CREATE TABLE IF NOT EXISTS 만 수행). 이 모듈이 기존 운영 DB
(SQLite)의 3개 테이블에 anonymized_at 컬럼을 추가한다.

⚙️ 자동 적용: main.py 가 create_all 직후 ensure_retention_columns() 를 호출하므로
  배포 시 별도 수동 실행이 필요 없다 (앱 기동 때 자동 반영). 멱등이라 매 기동 무해.
  단독 실행도 가능: ../.venv/bin/python -m app.scripts.migrate_retention

센티넬 방식이라 user_id NOT NULL→NULL 같은 테이블 재작성은 불필요 — ADD COLUMN 뿐이라
SQLite 에서도 안전하고 멱등하다.
"""
from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.database import billing_models  # noqa: F401 - 메타데이터 등록
from app.database.connection import engine as _default_engine

logger = logging.getLogger(__name__)

_TABLES = ("support_inquiries", "purchase_histories", "refund_requests")
_COLUMN = "anonymized_at"


def ensure_retention_columns(bind: Engine | None = None) -> None:
    """3개 법정보존 테이블에 anonymized_at 컬럼을 보장 (없으면 ADD, 있으면 무시).

    멱등 — 앱 기동마다 호출해도 안전. 기존 테이블이 없으면(신규 DB) create_all 이
    이미 컬럼 포함해 생성하므로 건너뛴다.
    """
    eng = bind or _default_engine
    inspector = inspect(eng)
    existing_tables = set(inspector.get_table_names())
    added = []
    for table in _TABLES:
        if table not in existing_tables:
            continue
        columns = {c["name"] for c in inspector.get_columns(table)}
        if _COLUMN in columns:
            continue
        # timestamp 계열. SQLite=DATETIME / PostgreSQL=TIMESTAMP 둘 다 수용하는 표기.
        col_type = "TIMESTAMP" if eng.dialect.name != "sqlite" else "DATETIME"
        with eng.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {_COLUMN} {col_type}"))
        added.append(table)
    if added:
        logger.info("리텐션 마이그레이션: %s 에 %s 컬럼 추가", ", ".join(added), _COLUMN)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    ensure_retention_columns()
    logger.info("리텐션 마이그레이션 완료")


if __name__ == "__main__":
    main()
