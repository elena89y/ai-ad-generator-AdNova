import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.database.connection import Base, engine
from app.database import models


def main() -> None:
    Base.metadata.create_all(bind=engine)
    table_names = ", ".join(sorted(Base.metadata.tables.keys()))
    print(f"테이블 생성 확인 완료: {table_names}")


if __name__ == "__main__":
    main()
