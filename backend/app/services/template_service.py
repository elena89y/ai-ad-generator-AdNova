"""템플릿 프리셋 로더 (DIRECTION_v6 T4, 모노브 M1·M4·M5) — 담당: 한의정.

데이터 원장: backend/app/templates/templates.yaml — 스타일(style_specs 키) × 포맷(pipeline_v5)
조합 프리셋. 신규 템플릿 = YAML 1항목 추가(코드 수정 불필요, T1 소프트코딩 원칙).

서비스 계층만 제공한다. HTTP 노출(GET /api/ads/templates · POST generate-from-template)은
공유 파일(api/ads.py·schemas/ads.py) 수정이라 범수님 통지·조율 후 붙인다.
로드 시 스타일 키·포맷·target·knob 을 전수 검증 — 데이터 오타를 기동/테스트 시점에 잡는다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml

from .style_specs import STYLE_SPECS

logger = logging.getLogger(__name__)

_TEMPLATES_PATH = Path(__file__).resolve().parents[1] / "templates" / "templates.yaml"

# pipeline_v5/formats/ 모듈명과 1:1 (신규 포맷 추가 시 여기도 갱신 — 테스트가 디렉터리와 대조)
KNOWN_FORMATS = frozenset({"banner", "cardnews", "detail_page", "flyer", "sns"})
KNOWN_TARGETS = frozenset({"food", "drink", "object", "any"})
_KNOB_MAX = 0.65  # 정직성 상한(허위광고 방지) — 템플릿 권장 knob 도 이 위를 못 넘는다


@dataclass(frozen=True)
class TemplatePreset:
    id: str
    title: str
    desc: str
    style: str                       # style_specs 키 (로드 시 존재 검증)
    target: str                      # food | drink | object | any
    formats: tuple[str, ...]         # 생성 팩 구성 (KNOWN_FORMATS 부분집합)
    knob: Optional[float] = None     # None = 파이프라인 기본 강도
    thumbnail: Optional[str] = None  # 정적 썸네일 경로 (D-1 생성 후 채움)
    palette: tuple[str, ...] = field(default=())  # style_specs 파생(프론트 그리드 미리보기용)
    mood: str = ""


def _validate(tid: str, raw: dict) -> None:
    if raw["style"] not in STYLE_SPECS:
        raise ValueError(f"템플릿 {tid}: 미등록 스타일 키 '{raw['style']}' (styles/specs.yaml 대조)")
    bad = set(raw["formats"]) - KNOWN_FORMATS
    if bad:
        raise ValueError(f"템플릿 {tid}: 미지 포맷 {sorted(bad)} (pipeline_v5/formats 대조)")
    if raw["target"] not in KNOWN_TARGETS:
        raise ValueError(f"템플릿 {tid}: 미지 target '{raw['target']}'")
    knob = raw.get("knob")
    if knob is not None and not (0.0 < float(knob) <= _KNOB_MAX):
        raise ValueError(f"템플릿 {tid}: knob {knob} 범위 위반 (0 초과 ~ {_KNOB_MAX} 이하)")


@lru_cache(maxsize=1)
def load_templates() -> dict[str, TemplatePreset]:
    """원장 로드 + 전수 검증. 반환은 id → 프리셋 (원장 순서 유지)."""
    with open(_TEMPLATES_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or "templates" not in data:
        raise ValueError(f"템플릿 원장 형식 오류: {_TEMPLATES_PATH}")
    presets: dict[str, TemplatePreset] = {}
    for tid, raw in data["templates"].items():
        _validate(tid, raw)
        spec = STYLE_SPECS[raw["style"]]
        presets[tid] = TemplatePreset(
            id=tid,
            title=raw["title"],
            desc=raw["desc"],
            style=raw["style"],
            target=raw["target"],
            formats=tuple(raw["formats"]),
            knob=raw.get("knob"),
            thumbnail=raw.get("thumbnail"),
            palette=spec.palette,
            mood=spec.mood,
        )
    return presets


def list_templates(target: Optional[str] = None) -> list[dict]:
    """API 직렬화용 목록. target 지정 시 해당 도메인 + 'any' 만."""
    items = load_templates().values()
    if target:
        items = [t for t in items if t.target in (target, "any")]
    return [
        {"id": t.id, "title": t.title, "desc": t.desc, "style": t.style,
         "target": t.target, "formats": list(t.formats), "knob": t.knob,
         "thumbnail": t.thumbnail, "palette": list(t.palette), "mood": t.mood}
        for t in items
    ]


def get_template(tid: str) -> TemplatePreset:
    """id → 프리셋. 미지 id 는 KeyError (호출부가 404 로 변환)."""
    presets = load_templates()
    if tid not in presets:
        raise KeyError(f"미지 템플릿 id: {tid}")
    return presets[tid]
