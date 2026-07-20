"""고객센터 챗봇 API 라우터 — 담당: 한의정.

엔드포인트:
  GET  /support/faqs — FAQ 목록 (고객센터 FAQ 게시판용, 카테고리 필터 지원)
  POST /support/chat — 챗봇 1턴 질의응답. 답변 또는 1:1 문의 프리필 초안 반환.

⚠️ main.py 라우터 등록은 연정님 도메인 — 아직 미등록 상태 (팀 조율 후 1줄 추가).
⚠️ 스키마는 schemas/ (범수님 도메인) 대신 이 파일에 정의 — 챗봇 전용 계약이므로.
   인증: 프로토타입은 비로그인 허용 (FAQ 는 공개 정보). 문의 제출 자체는 기존
   /inquiries (로그인 필수) 가 담당하므로 개인정보 경로는 없음.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.chatbot import chat_service, knowledge

router = APIRouter(prefix="/support", tags=["support"])


# --- 스키마 -------------------------------------------------------------------
class FaqItem(BaseModel):
    id: str
    category: str
    question: str
    answer: str


class FaqListResponse(BaseModel):
    total: int
    categories: list[str]
    items: list[FaqItem]


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000, description="사용자 질문 (1턴)")


class InquiryDraft(BaseModel):
    """에스컬레이션 시 1:1 문의 폼 프리필용 초안 — POST /inquiries 계약에 맞춘 필드."""

    title: str
    content: str
    category_hint: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    escalate: bool
    sources: list[str] = []
    inquiry_draft: Optional[InquiryDraft] = None


# --- 엔드포인트 ---------------------------------------------------------------
@router.get("/faqs", response_model=FaqListResponse)
def read_faqs(category: Optional[str] = Query(None, description="카테고리 필터")) -> FaqListResponse:
    faqs = knowledge.load_faqs()
    categories = list(dict.fromkeys(f.category for f in faqs))  # 정의 순서 유지 dedupe
    if category is not None:
        if category not in categories:
            raise HTTPException(status_code=404, detail=f"없는 카테고리: {category}")
        faqs = tuple(f for f in faqs if f.category == category)
    return FaqListResponse(
        total=len(faqs),
        categories=categories,
        items=[FaqItem(id=f.id, category=f.category, question=f.question, answer=f.answer) for f in faqs],
    )


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    result = chat_service.get_service().chat(request.question)
    draft = None
    if result.escalate and result.inquiry_draft_title:
        draft = InquiryDraft(
            title=result.inquiry_draft_title,
            content=result.inquiry_draft_content or "",
            category_hint=result.matched_category,
        )
    return ChatResponse(
        answer=result.answer,
        escalate=result.escalate,
        sources=result.sources,
        inquiry_draft=draft,
    )
