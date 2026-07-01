"""스타일 결정 서비스 (스캐폴드) — 담당: 한의정. 신설.

엔드포인트: POST /ads/style  (신설, 팀장 공유 미실행)
호출 계층:  api/ads.py → style_service.py → gpt_service.py

스타일 결정 2경로 (2026-07-01 확정):
  경로1: 이미지 → Vision 분석 → 후보 3개 추천 → 유저 선택
  경로2: 유저 자유 텍스트 → 스타일 결정

스타일 = 문구 톤·색상 (용도와 축 분리). schemas/ads.py 참조.
비용: 경로1 Vision 호출은 OpenAI $30 한도 소모. 개발 중 호출 최소화(B-0 단계분리).
"""
from __future__ import annotations

from ..schemas.ads import StyleCandidate, StylePreset, StyleRequest, StyleResponse


def decide_style(req: StyleRequest) -> StyleResponse:
    """2경로 분기 진입점.

    image_path 존재 → _decide_from_image (경로1)
    free_text 존재  → _decide_from_text  (경로2)
    """
    if req.image_path:
        return _decide_from_image(req.image_path)
    if req.free_text:
        return _decide_from_text(req.free_text)
    raise ValueError("image_path 또는 free_text 중 하나 필요")
    # TODO: 둘 다/둘 다 없음 케이스 검증 규칙 확정


def _decide_from_image(image_path: str) -> StyleResponse:
    """경로1: Vision 분석 → 후보 3개.

    gpt_service.analyze_image_for_style() 호출 전제(미구현).
    """
    raise NotImplementedError("경로1 Vision 추천 미구현 — STY-001 실험 후")


def _decide_from_text(free_text: str) -> StyleResponse:
    """경로2: 자유 텍스트 → 스타일 매핑.

    TODO: 임시 규칙 기반 구현. STY-002 실험 후 gpt_service.resolve_style_from_text()로 교체 예정.
    """
    text = free_text.lower()
    if "빈티지" in free_text or "vintage" in text:
        preset = StylePreset.WARM_VINTAGE
    elif "팝" in free_text or "pop" in text:
        preset = StylePreset.POP
    else:
        preset = StylePreset.MONOTONE

    candidate = StyleCandidate(preset=preset, reason=f"자유 텍스트 임시 매핑: '{free_text}'")
    return StyleResponse(candidates=[candidate], resolved=preset)
