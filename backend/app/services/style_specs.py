"""스타일 디자인 토큰 로더 (DESIGN_SYSTEM_v1 반영, 레퍼런스 1차) — 담당: 한의정.

overlay_service(타이포)·생성경로(씬 프롬프트)·저지(목표미학)가 공유하는 단일 기준.
데이터 원장: backend/app/styles/specs.yaml (DIRECTION_v6 T1 소프트코딩 — 새 스타일 추가는
YAML 항목 추가만, 코드 수정 불필요). 값 변경은 tests/test_style_specs_snapshot.py 가 감지.

font 값은 overlay_service._font 의 kind(serif_elegant/display_heavy/condensed/…)와 일치.
production: 'hybrid'(원본 편집+PIL 타이포) | 'generative'(크리에이티브 씬 생성 비중↑).

--- scene_prompt 문구 결정 이력(실측 근거 — YAML 수정 전 반드시 읽을 것) ---
- editorial: 'magazine layout/moodboard' 어휘는 FLUX가 가짜 잡지 텍스트(gibberish)를 그림
  (실측 2026-07-10) → 단일 히어로 클린 에디토리얼 규약, 콜라주·텍스트 유발어 금지.
- realism: 과한 스타일화로 고기가 CGI/장난감처럼 뭉갬(2026-07-10) → 사진 사실감 앵커 +
  마블링·살결 대비 명시. negative 에 CGI/plastic/toy 차단 유지.
- warm_vintage: 'bojagi wrapping'이 없던 비닐봉투 생성, 'beige studio'가 실제색을 오렌지
  모노톤으로 뭉갬(2026-07-10) → 포장어휘 금지·제품 히어로 명시·실제색 유지.
- object_studio/object_splash: 'photograph of {subject}' 프레이밍은 제품 전체 재생성을 유도해
  형태 붕괴(문어 괄사→구, 2026-07-10) → "제품은 그대로, 배경만" 편집 지시로 형태 잠금.
  사물은 SKU — 신품화(마모 제거)만 허용, 로고·형태·색 왜곡은 negative 로 차단(정직성 경계).
- cross_section: 생성비중↑ — 레이어는 실제 재료만(gpt_service 레시피 검증 후 주입), 허위 금지.
- BUTTON_STYLE_MAP retro_paper 슬롯 재활용(2026-07-13): StylePreset enum 에 realism 이 없어
  '내추럴' 버튼이 retro_paper 값을 전송 → realism 씬으로 매핑.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

_SPECS_PATH = Path(__file__).resolve().parents[1] / "styles" / "specs.yaml"


@dataclass(frozen=True)
class StyleSpec:
    key: str
    mood: str
    palette: tuple[str, ...]          # 대표 hex (2~3색 중심)
    head_font: str                    # 헤드라인 폰트 kind
    sub_font: str                     # 서브/캡션 폰트 kind
    accent: tuple[int, int, int]      # 액센트 RGB
    production: str                   # hybrid | generative
    scene_prompt: str = ""            # 생성 씬 프롬프트 템플릿({subject} 치환)
    negative: str = ""


@lru_cache(maxsize=1)
def _load() -> dict:
    with open(_SPECS_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or "specs" not in data or "button_map" not in data:
        raise ValueError(f"스타일 원장 형식 오류: {_SPECS_PATH}")
    return data


def _build_specs() -> dict[str, StyleSpec]:
    specs: dict[str, StyleSpec] = {}
    for key, raw in _load()["specs"].items():
        specs[key] = StyleSpec(
            key=key,
            mood=raw["mood"],
            palette=tuple(raw["palette"]),
            head_font=raw["head_font"],
            sub_font=raw["sub_font"],
            accent=tuple(raw["accent"]),
            production=raw["production"],
            scene_prompt=raw.get("scene_prompt", ""),
            negative=raw.get("negative", ""),
        )
    return specs


STYLE_SPECS: dict[str, StyleSpec] = _build_specs()

# 프론트 6버튼(무드) → style_spec 키 매핑 (2026-07-10, 봄·한의정 조율안).
#   특수 4종(object_studio/object_splash/pop_split/cross_section)은 '포맷'이라 버튼이 아니라
#   라우터가 콘텐츠(사물/여름음료/케이크단면)로 자동 선택 — 무드 버튼과 직교.
BUTTON_STYLE_MAP: dict[str, str] = dict(_load()["button_map"])


def get_spec(key: str) -> StyleSpec:
    """스타일 키 → 스펙(없으면 editorial 폴백)."""
    return STYLE_SPECS.get(key, STYLE_SPECS["editorial"])


def resolve_style(button: str) -> str:
    """프론트 버튼/프리셋명 → style_spec 키. 미지값은 editorial 폴백. ads.py 가 process_ad(style=) 로 전달."""
    return BUTTON_STYLE_MAP.get((button or "").strip().lower(), "editorial")
