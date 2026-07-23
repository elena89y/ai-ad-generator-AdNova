"""법정 보존 기록 라이프사이클 — 담당: 한의정 (범수님 DB 도메인 조율, 2026-07-21).

근거 (LEGAL_RETENTION_COORDINATION.md 참조):
  - 전자상거래법 시행령 제6조: 소비자 불만·분쟁처리 기록 3년 / 대금결제·재화공급 5년 보존 의무.
  - 개인정보보호법 제21조: 탈퇴 시 원칙적 즉시 파기, 단 법정 보존의무 있는 기록은
    다른 정보와 분리하여 보관.

탈퇴 시 아래 3종은 삭제하지 않고 "탈퇴회원" 센티넬 계정으로 user_id 를 재지정해
개인 식별 링크를 끊는다(가명처리-분리보존). 보존기간이 지난 가명처리 기록만
purge_expired_records 로 파기한다.

⚠️ 명명 주의: 본문(문의 content, 환불 reason, 결제 description/식별자)은 분쟁 대응
근거로 보존하므로, 이는 완전한 "익명화"가 아니라 "가명처리"에 가깝다(재식별 여지 잔존).
본문 마스킹 여부는 법무 판단 사항 — LEGAL_RETENTION_COORDINATION.md (D) 참조.

센티넬 방식을 택한 이유(운영 DB=SQLite):
  user_id 를 NULL 로 바꾸는 설계는 SQLite 의 ALTER COLUMN DROP NOT NULL 미지원 →
  위험한 테이블 재작성이 필요하고, 모든 관리자 INNER JOIN 을 outerjoin 으로 고쳐야 함.
  센티넬 재지정은 user_id NOT NULL 을 유지해 FK·기존 조인 무결 + 마이그레이션이
  anonymized_at 컬럼 ADD 하나로 끝난다.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.billing_models import PurchaseHistory, RefundRequest
from app.database.models import SupportInquiry, User, utc_now

# 전자상거래법 시행령 제6조 1항 — 법정 최소 보존기간. 사내 정책상 연장 시 이 값만 변경.
INQUIRY_RETENTION_YEARS = 3  # 3호: 소비자의 불만 또는 분쟁처리에 관한 기록
PAYMENT_RETENTION_YEARS = 5  # 2호: 대금결제 및 재화등의 공급에 관한 기록

# "탈퇴회원" 센티넬 계정. username 이 한글이라 회원가입 정규식(^[A-Za-z0-9]{7,12}$)으로는
# 절대 생성 불가 → 실제 회원과 충돌 없음. 로그인 불가(unusable password + is_active=False).
WITHDRAWN_USERNAME = "탈퇴회원"
WITHDRAWN_EMAIL = "withdrawn@adnova.invalid"


def get_or_create_withdrawn_placeholder(db: Session) -> User:
    """탈퇴 회원 기록 귀속용 센티넬 계정 조회/생성. 프로세스당 사실상 1회."""
    placeholder = db.query(User).filter(User.username == WITHDRAWN_USERNAME).first()
    if placeholder is None:
        placeholder = User(
            email=WITHDRAWN_EMAIL,
            username=WITHDRAWN_USERNAME,
            password_hash="!",  # bcrypt 검증 항상 실패 → 로그인 불가
            name=WITHDRAWN_USERNAME,
            is_active=False,
        )
        db.add(placeholder)
        db.flush()  # id 확보 (커밋은 호출부 트랜잭션에 위임)
    return placeholder


def anonymize_legal_records_for_user(
    db: Session,
    user_id: int,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    """탈퇴 회원의 법정 보존 기록을 가명처리(센티넬 재지정 + anonymized_at 기록).

    본문은 분쟁 대응 근거라 보존하고, 개인 식별 링크(user_id)만 센티넬로 끊는다.
    호출 시점에 커밋하지 않음 — delete_user_account 의 단일 트랜잭션에 합류.
    """
    now = now or utc_now()
    # 이 회원이 관리자로서 처리한 환불의 처리자 링크는 기록 유무와 무관하게 끊는다
    # (향후 관리자 삭제 플로우 대비 FK 안전).
    db.query(RefundRequest).filter(
        RefundRequest.processed_by_admin_id == user_id
    ).update({"processed_by_admin_id": None}, synchronize_session=False)

    # 보존 대상 기록이 있을 때만 센티넬 생성 → 기록 없는 회원 탈퇴 시 불필요한 센티넬 안 만듦.
    has_records = (
        db.query(SupportInquiry.id).filter(SupportInquiry.user_id == user_id).first() is not None
        or db.query(PurchaseHistory.id).filter(PurchaseHistory.user_id == user_id).first() is not None
        or db.query(RefundRequest.id).filter(RefundRequest.user_id == user_id).first() is not None
    )
    if not has_records:
        return {"inquiries": 0, "purchases": 0, "refunds": 0}

    placeholder = get_or_create_withdrawn_placeholder(db)
    payload = {"user_id": placeholder.id, "anonymized_at": now}
    return {
        "inquiries": db.query(SupportInquiry)
        .filter(SupportInquiry.user_id == user_id)
        .update(payload, synchronize_session=False),
        "purchases": db.query(PurchaseHistory)
        .filter(PurchaseHistory.user_id == user_id)
        .update(payload, synchronize_session=False),
        "refunds": db.query(RefundRequest)
        .filter(RefundRequest.user_id == user_id)
        .update(payload, synchronize_session=False),
    }


def purge_expired_records(db: Session, *, now: datetime | None = None) -> dict[str, int]:
    """보존기간이 지난 "가명처리된" 기록을 파기. 배치(scripts/purge_expired_records.py)에서 호출.

    ⚠️ anonymized_at IS NOT NULL 가드 필수: 활성 회원의 오래된 결제/문의를 지우면 안 된다.
      파기 대상은 탈퇴로 가명처리된 기록에 한정(보존의무 종료 → 개인정보 최소화 파기).
    기산점: 문의=답변완료일(없으면 접수일), 구매=결제일, 환불=처리일(없으면 신청일).
    FK 안전: RefundRequest.purchase_id → PurchaseHistory 참조이므로 남은 환불이
      참조하는 구매는 보존(dangling FK 방지).
    """
    now = now or utc_now()
    inquiry_cutoff = _shift_years(now, -INQUIRY_RETENTION_YEARS)
    payment_cutoff = _shift_years(now, -PAYMENT_RETENTION_YEARS)

    inquiry_anchor = func.coalesce(SupportInquiry.answered_at, SupportInquiry.created_at)
    refund_anchor = func.coalesce(RefundRequest.processed_at, RefundRequest.requested_at)

    inquiries = (
        db.query(SupportInquiry)
        .filter(SupportInquiry.anonymized_at.is_not(None), inquiry_anchor < inquiry_cutoff)
        .delete(synchronize_session=False)
    )
    refunds = (
        db.query(RefundRequest)
        .filter(RefundRequest.anonymized_at.is_not(None), refund_anchor < payment_cutoff)
        .delete(synchronize_session=False)
    )
    # 남아있는 환불이 참조하는 구매는 보존 (FK 무결성 + 분쟁 근거 유지)
    referenced_purchase_ids = db.query(RefundRequest.purchase_id).distinct().subquery()
    purchases = (
        db.query(PurchaseHistory)
        .filter(
            PurchaseHistory.anonymized_at.is_not(None),
            PurchaseHistory.purchased_at < payment_cutoff,
            PurchaseHistory.id.not_in(db.query(referenced_purchase_ids.c.purchase_id)),
        )
        .delete(synchronize_session=False)
    )

    db.commit()
    return {"inquiries": inquiries, "refunds": refunds, "purchases": purchases}


def _shift_years(dt: datetime, years: int) -> datetime:
    """dt 에서 years 만큼 이동. 2/29 → 비윤년이면 2/28 로 보정."""
    try:
        return dt.replace(year=dt.year + years)
    except ValueError:
        return dt.replace(year=dt.year + years, day=28)
