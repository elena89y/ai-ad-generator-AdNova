"""브리프 확장 — 짧은 한글 브리프 → 배경 프롬프트(영어) + 카피 + load-bearing 정보줄. 담당: 한의정.

OpenAI 단일 창구 원칙 유지: 실제 호출은 gpt_service._chat_json(usage 기록·Langfuse 계승)을
경유한다 — 함수만 이 패키지에 두어 제거 가능성(패키지 삭제=기능 제거)을 지킨다.
프롬프트 원문은 backend/app/prompts/brief.yaml (Prompt 원장 T1 규약, 스냅샷 게이트 비편입 초안).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .. import prompt_registry as _prompts

logger = logging.getLogger(__name__)

_NS = "brief"

_VERTICAL_LABELS = {
    "event": "행사·이벤트",
    "medical": "병원·의원",
    "academy": "학원·교육",
    "realestate": "부동산",
}


@dataclass
class BriefPlan:
    """브리프 확장 산출물.

    info_lines 는 브리프 원문 발췌만(창작 금지) — 코드가 그대로 조판해 오탈자 0(정직성 경계).
    scene_en 은 영어·글자 없는 배경 묘사(CLIP 한글오염·함정 #3 회피).
    """
    scene_en: str
    headline_ko: str
    subcopy_ko: str = ""
    info_lines: list[str] = field(default_factory=list)
    palette_hint: str = ""


def expand_brief(brief: str, vertical: str = "event") -> BriefPlan:
    """짧은 한글 브리프 → BriefPlan. 응답 JSON 형태 변동(함정 #6)·API 실패 시 폴백 진행.

    폴백에서도 정보는 지어내지 않는다(빈 info_lines) — 허위 정보 조판 원천 차단.
    """
    from .. import gpt_service  # OpenAI 단일 창구 — 지연 import(패키지 독립성)

    text = (brief or "").strip()
    label = _VERTICAL_LABELS.get((vertical or "event").lower(), "행사·이벤트")
    try:
        instruction = _prompts.fmt(_NS, "expand.instruction",
                                   brief=text or "(빈 입력)", vertical_label=label)
        result = gpt_service._chat_json(
            [{"role": "user", "content": instruction}], label="expand_brief")
        if not isinstance(result, dict):
            raise TypeError("expand_brief 응답이 JSON 객체가 아님")
        low = {str(k).lower(): v for k, v in result.items()}
        info = low.get("info_lines") or []
        if not isinstance(info, list):
            info = []
        return BriefPlan(
            scene_en=str(low.get("scene_en") or "").strip()
            or "clean minimal studio background, soft light, no text",
            headline_ko=str(low.get("headline_ko") or "").strip() or _first_line(text),
            subcopy_ko=str(low.get("subcopy_ko") or "").strip(),
            info_lines=[str(x).strip() for x in info if str(x).strip()][:5],
            palette_hint=str(low.get("palette_hint") or "").strip(),
        )
    except Exception as e:  # noqa: BLE001 — 폴백(빈 화면·크래시 방지)
        logger.info("expand_brief 실패 → 폴백 진행: %s", e)
        return BriefPlan(
            scene_en="clean minimal studio background, soft light, no text",
            headline_ko=_first_line(text),
            subcopy_ko="",
            info_lines=[],
            palette_hint="",
        )


def _first_line(text: str) -> str:
    """헤드라인 폴백 — 첫 줄만(개행 미포함) 18자. 성공·폴백 경로 공통 규칙."""
    first = text.splitlines()[0].strip() if text else ""
    return first[:18] or "안내"
