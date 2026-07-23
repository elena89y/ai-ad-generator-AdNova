"""v5 카드뉴스 — 레이아웃 DSL(layouts/cardnews.yaml) + layout_engine 으로 조판. (v6-1 L3)

기존 하드코딩 슬라이드 함수(_cover_slide 등)를 데이터로 이전했다. 조판 값은 YAML, 코드는
범용 해석기(layout_engine.render_slide)만 — '생성된 광고(스타일·카피)'에 맞게 적응.
픽셀 동등은 test_layout_engine.py 가 고정(데이터화 전 렌더와 bbox=None).

카피는 detail_copy_for(F1 엔진) 1회 — 4슬라이드가 intro/story/profile/cta 전용 문구(D1 해소).
GPT 실패 시 폴백으로 종전 문구 구성 유지. 팔레트는 hero.style accent 파생(D4).
"""
from __future__ import annotations

from pathlib import Path

from ..commercial_copy import detail_copy_for
from ..format_spec import FormatSpec
from ..hero import DetailCutRole, HeroAsset
from ..layout_engine import _first_sentence, load_layout, render_slide  # noqa: F401  (_first_sentence: 하위호환 re-export)
from ..palette import palette
from .detail_page import _select_role_cuts

SLIDE_COUNT = 4
DEFAULT_CTA_TITLE = "지금 만나보세요"
DEFAULT_CTA_LABEL = "자세히 보기"
_SLIDE_NAMES = ("cover", "story", "detail", "cta")


def render(hero: HeroAsset, spec: FormatSpec, output_dir: str) -> list[str]:
    """표지·스토리·디테일·CTA 4슬라이드를 DSL 레이아웃으로 조판한다."""
    cuts = {cut.role: cut.image_path for cut in _select_role_cuts(hero)}
    by_name = {role.value: cuts[role] for role in DetailCutRole}
    copy = detail_copy_for(hero)
    pal = palette(hero.style)
    layout = load_layout("cardnews")
    size = spec.canvas

    output = Path(output_dir)
    paths: list[str] = []
    for index, name in enumerate(_SLIDE_NAMES, start=1):
        slide = render_slide(size, layout[name], by_name, copy, pal, spec.safe_margin)
        path = output / f"cardnews_{index:02d}_{name}_{size[0]}x{size[1]}.jpg"
        slide.save(path, quality=93)
        paths.append(str(path))
    return paths
