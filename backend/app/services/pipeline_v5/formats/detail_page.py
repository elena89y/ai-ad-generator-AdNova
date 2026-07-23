"""v5 판매 상세페이지 — 레이아웃 DSL(layouts/detail.yaml) + layout_engine.render_page. (v6-1 L4b)

8섹션 세로 롱스크롤, story/benefits 는 카피 길이로 높이 가변(render_page 가 계산). 기존 하드코딩
조판(_title_overlay 등)을 데이터로 이전했다. 픽셀 동등은 파일럿에서 확인(전환 전 렌더와 bbox=None).

⚠️ _scrim·_select_role_cuts 는 cardnews/layout_engine 이 재사용하므로 유지. layout_engine 이
detail_page._scrim 을 top import 하므로 render 는 layout_engine 을 지연 import(순환 방지).
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from PIL import Image

from ..commercial_copy import detail_copy_for
from ..format_spec import FormatSpec
from ..hero import DetailCut, DetailCutRole, HeroAsset
from ..palette import palette
from ..similarity import MAX_STRUCTURE_CORRELATION, correlation, structure_vector

logger = logging.getLogger(__name__)

MIN_UNIQUE_CUTS = 5
REQUIRED_ROLES = tuple(DetailCutRole)
DEFAULT_CTA_TITLE = "지금 만나보세요"
DEFAULT_CTA_LABEL = "자세히 보기"

# detail 자체 _palette 는 공용 palette 로 통일(L4b) — 참조처(테스트 등) 하위호환 alias.
_palette = palette


def render(hero: HeroAsset, spec: FormatSpec, output_dir: str) -> list[str]:
    """상세페이지 8섹션을 DSL 레이아웃(세로 스택·가변 높이)으로 조판한다."""
    from ..layout_engine import load_layout, render_page  # 지연 import(순환 방지)

    cuts = {cut.role: cut.image_path for cut in _select_role_cuts(hero)}
    by_name = {role.value: cuts[role] for role in DetailCutRole}
    copy = detail_copy_for(hero)
    pal = palette(hero.style)
    ctx = {"domain": hero.domain, "density": spec.copy_density}  # L5 콘텐츠 적응
    width = spec.canvas[0]
    canvas = render_page(width, load_layout("detail"), by_name, copy, pal, spec.safe_margin, ctx=ctx)
    out = Path(output_dir) / f"detail_{width}x{canvas.height}_{spec.label}.jpg"
    canvas.save(out, quality=93)
    return [str(out)]


def _unique_images(paths: tuple[str, ...]) -> list[str]:
    unique, hashes = [], set()
    for value in paths:
        path = Path(value)
        if not path.is_file():
            raise ValueError(f"상세페이지 이미지가 없습니다: {value}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest not in hashes:
            hashes.add(digest)
            unique.append(str(path))
    return unique


def _select_role_cuts(hero: HeroAsset) -> list[DetailCut]:
    """필수 구도 5종을 고정 순서로 선택하고 내용·역할 중복을 거부한다.

    cardnews.render 도 이 함수를 재사용(다구도 검증 단일 소스)."""
    if not hero.detail_cuts:
        raise ValueError(
            "상세페이지 컷에 구도 역할이 필요합니다: "
            + ", ".join(role.value for role in REQUIRED_ROLES)
        )
    by_role: dict[DetailCutRole, DetailCut] = {}
    hashes: set[str] = set()
    structures: list[tuple[DetailCutRole, object]] = []
    for cut in hero.detail_cuts:
        path = Path(cut.image_path)
        if not path.is_file():
            raise ValueError(f"상세페이지 이미지가 없습니다: {cut.image_path}")
        if cut.role in by_role:
            raise ValueError(f"상세페이지 구도 역할이 중복되었습니다: {cut.role.value}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest in hashes:
            raise ValueError("같은 이미지 내용을 서로 다른 상세페이지 구도로 사용할 수 없습니다")
        structure = structure_vector(path)
        for existing_role, existing in structures:
            # GATE-001(2026-07-20)/개정(07-21): 4개 구도는 생성 단계(generation_app.
            # _generate_with_retry)에서 이미 "확정된 모든 컷"과 비교하며 재시도해 최선을 골라온
            # 뒤다. 여기서 같은 임계값으로 다시 하드 실패시키면 "5장 만들고 전체 날리기"가 재발
            # (라이브 실측: 김치찌개 상세 561s 생성 → 400 → 전량 폐기). 비-히어로 쌍의 유사는
            # 경고 로그로 강등, 완전 동일(해시 중복)만 하드 실패.
            if DetailCutRole.HERO in (existing_role, cut.role):
                continue
            if correlation(existing, structure) >= MAX_STRUCTURE_CORRELATION:
                logger.warning(
                    "상세페이지 구도 유사(상류 재시도의 최선 채택 존중): %s vs %s",
                    existing_role.value, cut.role.value,
                )
        hashes.add(digest)
        structures.append((cut.role, structure))
        by_role[cut.role] = cut
    missing = [role.value for role in REQUIRED_ROLES if role not in by_role]
    if missing:
        raise ValueError("상세페이지 필수 구도가 부족합니다: " + ", ".join(missing))
    return [by_role[role] for role in REQUIRED_ROLES]


def _scrim(canvas, y_top: int, y_bottom: int, width: int, rgb: tuple, amax: int, fade: int):
    """제품 이미지 위 타이포 배경 — 솔리드 대신 위쪽 페이드 밴드(제품 노출↑).

    layout_engine.render_elements 의 scrim 요소가 이 함수를 호출한다(단일 소스)."""
    h = int(y_bottom - y_top)
    if h <= 0:
        return
    ramp = Image.new("L", (1, h))
    px = ramp.load()
    for i in range(h):
        px[0, i] = int(amax * min(1.0, i / max(1, fade)))
    overlay = Image.new("RGBA", (width, h), (rgb[0], rgb[1], rgb[2], 0))
    overlay.putalpha(ramp.resize((width, h)))
    region = canvas.crop((0, int(y_top), width, int(y_top) + h)).convert("RGBA")
    canvas.paste(Image.alpha_composite(region, overlay).convert("RGB"), (0, int(y_top)))
