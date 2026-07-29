from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.crud.inquiry import create_inquiry, get_inquiry_by_id, list_inquiries_by_user
from app.database.connection import get_db
from app.database.models import SupportInquiry, User
from app.schemas.inquiry import InquiryCreateRequest, InquiryListResponse, InquiryResponse


router = APIRouter(prefix="/inquiries", tags=["inquiries"])


def _build_inquiry_response(inquiry: SupportInquiry) -> InquiryResponse:
    return InquiryResponse(
        id=inquiry.id,
        category=inquiry.category,
        title=inquiry.title,
        content=inquiry.content,
        status=inquiry.status,
        answer=inquiry.answer,
        answered_at=inquiry.answered_at,
        created_at=inquiry.created_at,
        updated_at=inquiry.updated_at,
    )


@router.post("", response_model=InquiryResponse, status_code=status.HTTP_201_CREATED)
def create_user_inquiry(
    request: InquiryCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InquiryResponse:
    inquiry = create_inquiry(
        db,
        user_id=current_user.id,
        category=request.category,
        title=request.title,
        content=request.content,
    )
    return _build_inquiry_response(inquiry)


@router.get("", response_model=InquiryListResponse)
def read_user_inquiries(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InquiryListResponse:
    total, inquiries = list_inquiries_by_user(
        db,
        user_id=current_user.id,
        skip=skip,
        limit=limit,
    )
    return InquiryListResponse(
        total=total,
        items=[_build_inquiry_response(inquiry) for inquiry in inquiries],
    )


@router.get("/{inquiry_id}", response_model=InquiryResponse)
def read_user_inquiry_detail(
    inquiry_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InquiryResponse:
    inquiry = get_inquiry_by_id(db, inquiry_id)
    if inquiry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="문의를 찾을 수 없습니다.")
    if inquiry.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="본인 문의만 조회할 수 있습니다.")
    return _build_inquiry_response(inquiry)
