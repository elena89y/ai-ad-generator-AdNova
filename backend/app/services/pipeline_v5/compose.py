"""v5 — 히어로를 FormatSpec 캔버스에 앉히는 공통 기하 + 포맷 디스패처. 담당: 한의정.

타이포/조판 프리미티브는 v4 overlay_service 를 재사용(수정 금지)한다.
여기서는 (1) 히어로를 규격 캔버스에 fit/crop, (2) 포맷 모듈로 위임 만 한다.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

from .format_spec import FormatSpec
from .hero import HeroAsset


def fit_hero(hero_img: Image.Image, spec: FormatSpec,
             mask: Optional[Image.Image] = None) -> Image.Image:
    """히어로를 spec.canvas 에 앉힌다.

    - cover : 캔버스를 꽉 채우고 넘치는 부분 크롭(주제 중심 유지 = saliency crop).
    - contain: 비율 유지하며 전부 담고 여백은 배경색(전단지 히어로존).
    - reflow: compose 상위(포맷 모듈)가 직접 배치 → 원본 그대로 반환.
    """
    if spec.hero_fit == "reflow":
        return hero_img
    if spec.hero_fit == "contain":
        return _contain(hero_img, spec.canvas)
    return _cover_saliency(hero_img, spec.canvas, mask)


def _contain(img: Image.Image, canvas: tuple[int, int],
             bg: tuple[int, int, int] = (255, 255, 255)) -> Image.Image:
    cw, ch = canvas
    scale = min(cw / img.width, ch / img.height)
    new = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))),
                     Image.LANCZOS)
    out = Image.new("RGB", canvas, bg)
    out.paste(new, ((cw - new.width) // 2, (ch - new.height) // 2))
    return out


def _cover_saliency(img: Image.Image, canvas: tuple[int, int],
                    mask: Optional[Image.Image]) -> Image.Image:
    """cover 크롭. mask 있으면 주제 무게중심을, 없으면 rule-of-thirds(상단 1/3)를 앵커.

    A모드(음식 in-place)는 mask=None → 음식이 보통 중앙·상단이라 세로 앵커 0.4.
    """
    cw, ch = canvas
    scale = max(cw / img.width, ch / img.height)
    rw, rh = max(cw, int(img.width * scale)), max(ch, int(img.height * scale))
    resized = img.resize((rw, rh), Image.LANCZOS)

    ax, ay = _anchor(img, mask)          # 0~1 원본 기준 주제 중심
    left = int((rw - cw) * ax)
    top = int((rh - ch) * ay)
    left = max(0, min(left, rw - cw))
    top = max(0, min(top, rh - ch))
    return resized.crop((left, top, left + cw, top + ch))


def _anchor(img: Image.Image, mask: Optional[Image.Image]) -> tuple[float, float]:
    """크롭 앵커(0~1). mask 무게중심 우선, 없으면 상단 편향 폴백."""
    if mask is not None:
        m = np.array(mask.convert("L").resize(img.size)) >= 128
        if m.any():
            ys, xs = np.nonzero(m)
            return float(xs.mean() / img.width), float(ys.mean() / img.height)
    return 0.5, 0.4   # 폴백: 가로 중앙, 세로 살짝 위(음식·제품 관례)


def render(hero: HeroAsset, spec: FormatSpec, output_dir: str) -> list[str]:
    """FormatSpec → 최종 산출물 경로 리스트(단면=1, 카드뉴스=N). 포맷 모듈로 위임."""
    from ...schemas.ads import AdPurpose  # 지연 import(순환 방지)

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    if spec.purpose == AdPurpose.SNS:
        from .formats import sns
        return sns.render(hero, spec, output_dir)
    if spec.purpose == AdPurpose.BANNER:
        from .formats import banner
        return banner.render(hero, spec, output_dir)
    if spec.purpose == AdPurpose.DETAIL_PAGE:
        from .formats import detail_page
        return detail_page.render(hero, spec, output_dir)
    if spec.purpose == AdPurpose.CARD_NEWS:
        from .formats import cardnews
        return cardnews.render(hero, spec, output_dir)
    if spec.purpose == AdPurpose.FLYER:
        from .formats import flyer
        return flyer.render(hero, spec, output_dir)
    # DETAIL_PAGE 등 미구현은 SNS 폴백(무해)
    from .formats import sns
    return sns.render(hero, spec, output_dir)
