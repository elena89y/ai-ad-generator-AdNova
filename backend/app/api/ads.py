"""광고 스타일/생성 API 라우터.

담당: 한의정
엔드포인트: POST /ads/style (D-2 스펙)
호출 계층: api/ads.py -> style_service.py -> gpt_service.py
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.ads import StyleRequest, StyleResponse
from ..services import style_service

router = APIRouter(prefix="/ads", tags=["ads"])


@router.post("/style", response_model=StyleResponse)
def decide_style(req: StyleRequest) -> StyleResponse:
    """스타일 결정 2경로 진입점 (경로1: 추천 / 경로2: 자유 텍스트)."""
    try:
        return style_service.decide_style(req)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e