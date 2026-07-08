"""스타일 결정 서비스 — 담당: 한의정.

엔드포인트: POST /ads/style  (신설, 팀장 공유 미실행)
호출 계층:  api/ads.py → style_service.py → gpt_service.py

스타일 결정 2경로 (2026-07-01 확정):
  경로1: 이미지 → Vision 분석 → 후보 3개 추천 → 유저 선택
  경로2: 유저 자유 텍스트 → 스타일 결정

스타일 = 문구 톤·색상 (용도와 축 분리). schemas/ads.py 참조.
비용: 경로1 Vision 호출은 OpenAI $30 한도 소모. 개발 중 호출 최소화(B-0 단계분리).
"""
from __future__ import annotations

from pathlib import Path

from ..schemas.ads import StyleCandidate, StylePreset, StyleRequest, StyleResponse
from . import gpt_service


def decide_style(req: StyleRequest, image_path: str | None = None) -> StyleResponse:
    """2경로 분기 진입점.

    image_id 존재 → API에서 검증한 image_path로 _decide_from_image (경로1)
    free_text 존재  → _decide_from_text  (경로2)
    둘 다 제공/둘 다 없음 → ValueError (상호배타)
    """
    if req.image_id and req.free_text:
        raise ValueError("image_id 와 free_text 는 동시에 지정할 수 없습니다")
    if req.image_id:
        if not image_path:
            raise ValueError("image_id에 해당하는 이미지 경로를 확인할 수 없습니다")
        return _decide_from_image(image_path)
    if req.free_text:
        return _decide_from_text(req.free_text)
    raise ValueError("image_id 또는 free_text 중 하나 필요")


def _decide_from_image(image_path: str) -> StyleResponse:
    """경로1: Vision 분석 → 후보 3개 → 유저 선택 대기 (resolved=None).

    ⚠️ Vision 호출 = 비용 발생 ($30 한도). 호출 전 파일 존재를 먼저 검증해
    무의미한 API 소모를 방지.
    """
    if not Path(image_path).is_file():
        raise FileNotFoundError(f"이미지 파일이 존재하지 않습니다: {image_path}")

    candidates = gpt_service.analyze_image_for_style(image_path)
    return StyleResponse(candidates=candidates, resolved=None)


def _decide_from_text(free_text: str) -> StyleResponse:
    """경로2: 자유 텍스트 → 스타일 매핑.

    TODO: 임시 규칙 기반 구현. STY-002 실험 후 gpt_service.resolve_style_from_text()로 교체 예정.
    """
    text = free_text.lower()
    if "빈티지" in free_text or "카페" in free_text or "vintage" in text:
        preset = StylePreset.WARM_VINTAGE
    elif "레트로" in free_text or "복고" in free_text or "포스터" in free_text or "retro" in text:
        preset = StylePreset.RETRO_PAPER
    elif "럭셔리" in free_text or "고급" in free_text or "프리미엄" in free_text or \
            "luxury" in text or "editorial" in text:
        preset = StylePreset.EDITORIAL
    elif "파스텔" in free_text or "몽환" in free_text or "산뜻" in free_text or \
            "pastel" in text or "float" in text:
        preset = StylePreset.PASTEL_FLOAT
    elif "팝" in free_text or "pop" in text:
        preset = StylePreset.POP
    else:
        preset = StylePreset.MONOTONE

    candidate = StyleCandidate(preset=preset, reason=f"자유 텍스트 임시 매핑: '{free_text}'")
    return StyleResponse(candidates=[candidate], resolved=preset)
