import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


DEFAULT_DATABASE_URL = "sqlite:///./data/app.db"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
DEFAULT_ADMIN_DATABASE_URL = "sqlite:///./data/admin.db"
ADMIN_DATABASE_URL = os.getenv("ADMIN_DATABASE_URL", DEFAULT_ADMIN_DATABASE_URL)


def _ensure_sqlite_directory(database_url: str) -> None:
    if not database_url.startswith("sqlite:///"):
        return

    db_path = database_url.replace("sqlite:///", "", 1)
    if db_path == ":memory:":
        return

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_directory(DATABASE_URL)
_ensure_sqlite_directory(ADMIN_DATABASE_URL)

def _connect_args(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args(DATABASE_URL))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

admin_engine = create_engine(
    ADMIN_DATABASE_URL,
    connect_args=_connect_args(ADMIN_DATABASE_URL),
)
AdminSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=admin_engine,
)
AdminBase = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_admin_db():
    db = AdminSessionLocal()
    try:
        yield db
    finally:
        db.close()
