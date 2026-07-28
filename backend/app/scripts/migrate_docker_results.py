"""Migrate legacy generated image paths to the Docker results volume."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class MigrationResult:
    matched: int
    migrated: int
    missing: int
    backup_path: Path | None


def _backup_database(database_path: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_path = database_path.with_name(
        f"{database_path.name}.before-docker-results-{timestamp}"
    )
    source = sqlite3.connect(database_path)
    backup = sqlite3.connect(backup_path)
    try:
        source.backup(backup)
    finally:
        backup.close()
        source.close()
    return backup_path


def migrate_docker_results(
    database_path: str | Path,
    source_root: str | Path,
    destination_root: str | Path,
    stored_root: str | Path = "/app/results",
    *,
    dry_run: bool = False,
) -> MigrationResult:
    database = Path(database_path).resolve()
    source = Path(source_root).resolve()
    destination = Path(destination_root).resolve()
    stored = PurePosixPath(str(stored_root))

    if not database.is_file():
        raise FileNotFoundError(f"DB 파일이 없습니다: {database}")
    if not source.is_dir():
        raise FileNotFoundError(f"기존 결과 폴더가 없습니다: {source}")
    if not stored.is_absolute():
        raise ValueError("DB 저장 경로(--stored-root)는 절대 경로여야 합니다.")

    connection = sqlite3.connect(database)
    try:
        table_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='images'"
        ).fetchone()
        if table_exists is None:
            raise RuntimeError("images 테이블이 없는 DB입니다.")

        rows = connection.execute(
            "SELECT id, file_path FROM images WHERE file_path IS NOT NULL"
        ).fetchall()

        candidates: list[tuple[int, Path, Path, str]] = []
        missing = 0
        for image_id, file_path in rows:
            candidate = Path(file_path).resolve()
            try:
                relative_path = candidate.relative_to(source)
            except ValueError:
                continue

            source_file = source / relative_path
            if not source_file.is_file():
                missing += 1
                continue

            candidates.append(
                (
                    image_id,
                    source_file,
                    destination / relative_path,
                    str(stored / relative_path),
                )
            )

        if dry_run or not candidates:
            return MigrationResult(
                matched=len(candidates) + missing,
                migrated=0,
                missing=missing,
                backup_path=None,
            )

        backup_path = _backup_database(database)
        updates: list[tuple[str, int]] = []
        for image_id, source_file, destination_file, stored_path in candidates:
            destination_file.parent.mkdir(parents=True, exist_ok=True)
            if not destination_file.exists():
                shutil.copy2(source_file, destination_file)
            updates.append((stored_path, image_id))

        with connection:
            connection.executemany(
                "UPDATE images SET file_path = ? WHERE id = ?",
                updates,
            )

        return MigrationResult(
            matched=len(candidates) + missing,
            migrated=len(updates),
            missing=missing,
            backup_path=backup_path,
        )
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="기존 생성 이미지와 DB 경로를 Docker 결과 볼륨으로 이전합니다."
    )
    parser.add_argument("--database", required=True, help="이전할 app.db 경로")
    parser.add_argument("--source", required=True, help="기존 backend/results 경로")
    parser.add_argument("--destination", required=True, help="runtime/results 경로")
    parser.add_argument(
        "--stored-root",
        default="/app/results",
        help="컨테이너에서 사용하는 결과 루트 경로",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="파일과 DB를 변경하지 않고 대상만 확인",
    )
    args = parser.parse_args()

    result = migrate_docker_results(
        database_path=args.database,
        source_root=args.source,
        destination_root=args.destination,
        stored_root=args.stored_root,
        dry_run=args.dry_run,
    )
    print(f"대상 이미지: {result.matched}개")
    print(f"이전 완료: {result.migrated}개")
    print(f"기존 파일 없음: {result.missing}개")
    if args.dry_run:
        print("드라이런이므로 파일과 DB를 변경하지 않았습니다.")
    elif result.backup_path:
        print(f"DB 백업: {result.backup_path}")
    else:
        print("이전할 이미지가 없어 DB를 변경하지 않았습니다.")


if __name__ == "__main__":
    main()
