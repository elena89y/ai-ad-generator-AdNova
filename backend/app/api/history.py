from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
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

    output_image = advertisement.output_image
    output_file_path = None
    if (
        output_image is not None
        and output_image.image_type == "generated"
        and output_image.user_id == current_user.id
    ):
        output_file_path = output_image.file_path

    delete_generated_result_by_history(db, history)
    _delete_generated_image_file(output_file_path)
