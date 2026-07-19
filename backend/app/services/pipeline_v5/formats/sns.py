"""v5 SNS 포맷 — v4 조판으로 위임(재구현 금지). 담당: 한의정.

원칙: SNS 출력 == v4 출력. 회귀 위험 0.
  - 일반 경로: generate_v5 가 애초에 v4 process_ad(poster=True)를 그대로 태운다(§__init__).
  - 여기 render 는 '이미 만든 히어로로 SNS도 뽑는' 멀티포맷 배치용.
    히어로는 규격 없는 리터치 결과(A모드=전체 사진 경로) → apply_food_poster(경로) 재사용.
    ⚠️ 에디토리얼/누끼(RGBA 입력) 도메인 SNS 는 v4 process_ad 직행이 정답(TODO: 배치 분기).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from ..compose import fit_hero
from ..format_spec import FormatSpec
from ..hero import HeroAsset


def render(hero: HeroAsset, spec: FormatSpec, output_dir: str) -> list[str]:
    from ... import overlay_service  # v4 — 호출 전용

    # 히어로를 SNS 규격(1:1)에 맞춰 저장 → v4 포스터 함수는 '경로'를 받는다.
    img = Image.open(hero.image_path).convert("RGB")
    fitted = fit_hero(img, spec)
    tmp = str(Path(output_dir) / "_sns_hero.jpg")
    fitted.save(tmp, quality=95)

    out = str(Path(output_dir) / "sns_1080.jpg")
    overlay_service.apply_food_poster(
        tmp, hero.headline, hero.subcopy,
        layout="overlay", style_key=hero.style, output_path=out,
    )
    return [out]
