from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.crud.advertisement import get_advertisement_by_id
from app.crud.report import create_report, get_report_by_id, list_reports_by_user
from app.database.connection import get_db
from app.database.models import User
from app.schemas.report import ReportCreateRequest, ReportListResponse, ReportResponse


router = APIRouter(prefix="/reports", tags=["reports"])


def _build_report_response(report) -> ReportResponse:
    return ReportResponse(
        id=report.id,
        category=report.category,
        title=report.title,
        content=report.content,
        advertisement_id=report.advertisement_id,
        status=report.status,
        admin_note=report.admin_note,
        handled_at=report.handled_at,
        created_at=report.created_at,
        updated_at=report.updated_at,
    )


@router.post("", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def create_user_report(
    request: ReportCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReportResponse:
    if request.advertisement_id is not None:
        advertisement = get_advertisement_by_id(db, request.advertisement_id)
        if advertisement is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="신고할 광고를 찾을 수 없습니다.",
            )
        if advertisement.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="본인 광고만 신고할 수 있습니다.",
            )

    report = create_report(
        db,
        user_id=current_user.id,
        category=request.category,
        title=request.title,
        content=request.content,
        advertisement_id=request.advertisement_id,
    )
    return _build_report_response(report)


@router.get("", response_model=ReportListResponse)
def read_user_reports(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReportListResponse:
    total, reports = list_reports_by_user(
        db,
        user_id=current_user.id,
        skip=skip,
        limit=limit,
    )
    return ReportListResponse(
        total=total,
        items=[_build_report_response(report) for report in reports],
    )


@router.get("/{report_id}", response_model=ReportResponse)
def read_user_report_detail(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ReportResponse:
    report = get_report_by_id(db, report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="신고 내역을 찾을 수 없습니다.",
        )
    if report.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="본인 신고만 조회할 수 있습니다.",
        )
    return _build_report_response(report)
