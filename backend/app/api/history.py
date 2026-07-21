from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.crud.billing import get_subscription_by_user
from app.crud.history import (
    delete_generated_result_by_history,
    get_history_with_result_by_id,
    list_histories_by_user,
)
from app.database.connection import get_db
from app.database.models import User
from app.schemas.history import HistoryResponse
from app.services import image_service


router = APIRouter(prefix="/history", tags=["history"])


def _delete_generated_image_file(file_path: str | None) -> None:
    if not file_path:
        return

    path = Path(file_path).resolve()
    results_dir = image_service.RESULTS_DIR.resolve()
    if results_dir not in path.parents:
        return

    try:
        if path.is_file():
            path.unlink()
    except OSError:
        return


def _has_active_premium_subscription(db: Session, user_id: int) -> bool:
    subscription = get_subscription_by_user(db, user_id)
    return bool(
        subscription
        and subscription.plan == "premium"
        and subscription.status == "active"
    )


@router.get("", response_model=list[HistoryResponse])
def read_histories(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[HistoryResponse]:
    return list_histories_by_user(
        db,
        current_user.id,
        skip=skip,
        limit=limit,
    )


@router.get("/{history_id}", response_model=HistoryResponse)
def read_history_detail(
    history_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> HistoryResponse:
    history = get_history_with_result_by_id(db, history_id)
    if history is None:
        raise HTTPException(status_code=404, detail="history를 찾을 수 없습니다.")

    if history.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="본인 생성 결과만 조회할 수 있습니다.")

    return history


@router.get("/{history_id}/result/download")
def download_generated_result(
    history_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    history = get_history_with_result_by_id(db, history_id)
    if history is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="history를 찾을 수 없습니다.",
        )

    if history.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="본인 생성 결과만 다운로드할 수 있습니다.",
        )

    if not _has_active_premium_subscription(db, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="원본 다운로드는 프리미엄 구독에서 사용할 수 있습니다.",
        )

    output_image = history.advertisement.output_image if history.advertisement else None
    if output_image is None or output_image.image_type != "generated":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="다운로드할 생성 이미지를 찾을 수 없습니다.",
        )

    file_path = Path(output_image.file_path or "")
    if not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="생성 이미지 파일을 찾을 수 없습니다.",
        )

    return FileResponse(
        file_path,
        media_type=output_image.content_type or "image/png",
        filename=output_image.original_filename or output_image.stored_filename or "adnova-ad.png",
    )


@router.delete("/{history_id}/result", status_code=status.HTTP_204_NO_CONTENT)
def delete_generated_result(
    history_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    history = get_history_with_result_by_id(db, history_id)
    if history is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="history를 찾을 수 없습니다.",
        )

    if history.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="본인 생성 결과만 삭제할 수 있습니다.",
        )

    advertisement = history.advertisement
    if advertisement is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="삭제할 생성 결과가 없는 history입니다.",
        )

    if advertisement.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="본인 생성 결과만 삭제할 수 있습니다.",
        )

    generated_file_paths = delete_generated_result_by_history(db, history)
    for file_path in generated_file_paths:
        _delete_generated_image_file(file_path)
