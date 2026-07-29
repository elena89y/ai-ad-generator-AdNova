from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.crud.notice import get_notice_by_id, list_published_notices
from app.database.connection import get_db
from app.schemas.notice import NoticeListResponse, NoticeResponse


router = APIRouter(prefix="/notices", tags=["notices"])


def _build_notice_response(notice) -> NoticeResponse:
    return NoticeResponse(
        id=notice.id,
        title=notice.title,
        content=notice.content,
        published_at=notice.published_at,
        created_at=notice.created_at,
        updated_at=notice.updated_at,
    )


@router.get("", response_model=NoticeListResponse)
def read_published_notices(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
) -> NoticeListResponse:
    total, notices = list_published_notices(db, skip=skip, limit=limit)
    return NoticeListResponse(
        total=total,
        items=[_build_notice_response(notice) for notice in notices],
    )


@router.get("/{notice_id}", response_model=NoticeResponse)
def read_published_notice_detail(
    notice_id: int,
    db: Session = Depends(get_db),
) -> NoticeResponse:
    notice = get_notice_by_id(db, notice_id)
    if notice is None or not notice.is_published:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="공지사항을 찾을 수 없습니다.",
        )
    return _build_notice_response(notice)
