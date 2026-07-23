"""v5 멀티포맷 — 포맷(용도)별 캔버스 기하의 단일 진실 원천. 담당: 한의정.

설계 불변식(v5 핵심):
  히어로 생성(v4 process_ad)은 포맷을 모른다. 여기 정의한 FormatSpec 만이
  "규격 없는 히어로"를 각 채널 산출물로 굽는 기하를 소유한다.
  한 히어로로 4포맷 전부 뽑을 수 있어야 한다(재생성 비용·일관성).

신규 의존성 금지 — PIL+NumPy 만. HTTP/프론트 미노출(내부 병행 단계).
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml

from ...schemas.ads import AdPurpose

HeroFit = Literal["cover", "contain", "reflow"]
CopyDensity = Literal["minimal", "medium", "dense"]

# 규격 데이터 원장(L1 소프트코딩): format_spec.py 옆 format_specs.yaml.
# 새 규격·사이즈는 코드가 아니라 YAML 에서 — test_format_specs_snapshot 이 값 변경 감지.
_SPECS_PATH = Path(__file__).parent / "format_specs.yaml"


@dataclass(frozen=True)
class FormatSpec:
    """한 산출물 면(面)의 기하 규격. slides>1 이면 시퀀스의 한 슬라이드 템플릿.

    디지털 전용(2026-07-17 인쇄 트랙 폐기 — 커머셜 집중). px 가 곧 최종.
    """
    purpose: AdPurpose
    canvas: tuple[int, int]        # (W, H) px — 최종 출력 규격
    hero_fit: HeroFit              # 히어로를 캔버스에 앉히는 방식
    copy_density: CopyDensity      # 카피 분량 정책(GPT 카피 구조·타이포 밀도)
    safe_margin: float = 0.06      # 세이프존 비율(경계 잘림 방지)
    label: str = ""                # 규격 별칭(예: "commerce_wide")
    note: str = ""                 # 채널/용도 메모(유저 노출용 라벨 후보)

    @property
    def aspect(self) -> float:
        w, h = self.canvas
        return w / h


# --- 포맷별 규격 레지스트리 (format_specs.yaml 로드) -------------------------
# 한 purpose 가 복수 규격을 가질 수 있다. 리스트 = 자동 생성 팩(순서 = 대표 우선순위).
@lru_cache(maxsize=1)
def _load_specs() -> dict[AdPurpose, list[FormatSpec]]:
    """format_specs.yaml → {AdPurpose: [FormatSpec]}. 값 변경은 스냅샷 테스트가 감지."""
    with open(_SPECS_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or "specs" not in data:
        raise ValueError(f"포맷 규격 원장 형식 오류: {_SPECS_PATH}")
    specs: dict[AdPurpose, list[FormatSpec]] = {}
    for pkey, items in data["specs"].items():
        purpose = AdPurpose(pkey)
        specs[purpose] = [
            FormatSpec(
                purpose=purpose,
                canvas=tuple(it["canvas"]),
                hero_fit=it["hero_fit"],
                copy_density=it["copy_density"],
                safe_margin=it.get("safe_margin", 0.06),
                label=it.get("label", ""),
                note=it.get("note", ""),
            )
            for it in items
        ]
    return specs


_SPECS: dict[AdPurpose, list[FormatSpec]] = _load_specs()


def specs_for(purpose: AdPurpose) -> list[FormatSpec]:
    """용도에 해당하는 규격 목록. 미정의 시 SNS 로 폴백(무해)."""
    return _SPECS.get(purpose, _SPECS[AdPurpose.SNS])


def primary_spec(purpose: AdPurpose) -> FormatSpec:
    """용도의 대표 규격 1건."""
    return specs_for(purpose)[0]
