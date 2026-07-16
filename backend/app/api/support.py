from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.database.admin_models import Inquiry, RefundRequest
from app.database.billing_models import PurchaseHistory
from app.database.connection import get_db
from app.database.models import User
from app.schemas.support import (
    InquiryCreateRequest,
    InquiryResponse,
    RefundRequestCreate,
    RefundRequestResponse,
)


router = APIRouter(tags=["support"])


def _inquiry_response(inquiry: Inquiry) -> InquiryResponse:
    return InquiryResponse(
        id=inquiry.id,
        title=inquiry.title,
        content=inquiry.content,
        status=inquiry.status,
        reply=inquiry.reply,
        created_at=inquiry.created_at,
        answered_at=inquiry.answered_at,
    )


def _refund_response(refund: RefundRequest) -> RefundRequestResponse:
    return RefundRequestResponse(
        id=refund.id,
        payment_id=refund.payment_id,
        amount=refund.amount,
        reason=refund.reason,
        status=refund.status,
        rejection_reason=refund.rejection_reason,
        requested_at=refund.requested_at,
        processed_at=refund.processed_at,
    )


@router.post("/inquiries", response_model=InquiryResponse, status_code=201)
def create_inquiry(
    request: InquiryCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> InquiryResponse:
    inquiry = Inquiry(
        user_id=current_user.id,
        title=request.title,
        content=request.content,
        status="pending",
    )
    db.add(inquiry)
    db.commit()
    db.refresh(inquiry)
    return _inquiry_response(inquiry)


@router.get("/inquiries", response_model=list[InquiryResponse])
def read_my_inquiries(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[InquiryResponse]:
    inquiries = (
        db.query(Inquiry)
        .filter(Inquiry.user_id == current_user.id)
        .order_by(Inquiry.created_at.desc())
        .all()
    )
    return [_inquiry_response(inquiry) for inquiry in inquiries]


@router.post("/refunds", response_model=RefundRequestResponse, status_code=201)
def create_refund_request(
    request: RefundRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RefundRequestResponse:
    payment = (
        db.query(PurchaseHistory)
        .filter(
            PurchaseHistory.id == request.payment_id,
            PurchaseHistory.user_id == current_user.id,
        )
        .first()
    )
    if payment is None:
        raise HTTPException(status_code=404, detail="결제 내역을 찾을 수 없습니다.")
    if payment.status != "paid":
        raise HTTPException(status_code=409, detail="환불을 신청할 수 없는 결제입니다.")
    if request.amount > payment.amount:
        raise HTTPException(status_code=422, detail="환불 금액이 결제 금액을 초과합니다.")

    pending = (
        db.query(RefundRequest)
        .filter(
            RefundRequest.payment_id == payment.id,
            RefundRequest.status == "pending",
        )
        .first()
    )
    if pending is not None:
        raise HTTPException(status_code=409, detail="이미 처리 대기 중인 환불 신청이 있습니다.")

    refund = RefundRequest(
        payment_id=payment.id,
        user_id=current_user.id,
        amount=request.amount,
        reason=request.reason,
        status="pending",
    )
    payment.status = "refund_pending"
    db.add(refund)
    db.commit()
    db.refresh(refund)
    return _refund_response(refund)


@router.get("/refunds", response_model=list[RefundRequestResponse])
def read_my_refunds(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[RefundRequestResponse]:
    refunds = (
        db.query(RefundRequest)
        .filter(RefundRequest.user_id == current_user.id)
        .order_by(RefundRequest.requested_at.desc())
        .all()
    )
    return [_refund_response(refund) for refund in refunds]
