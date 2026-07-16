"""Tier 1 결정론적 장면 렌더러 — 담당: 한의정. PIL+NumPy만(신규 의존성 금지).

기하 스타일(색면·밴드·그라디언트·시임리스 평면)은 생성모델이 아니라 코드가 그린다(D-12) —
슬롯·카피 여백이 구성상 보장되고 기계 검증된다(D-15). 그래픽 미감은 결함이 아니라
이 4개 스타일의 레퍼런스 미학(컬러블록·듀오톤·분할카드) 그 자체다.
"""
from __future__ import annotations

import colorsys
import math
from typing import TYPE_CHECKING

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

if TYPE_CHECKING:
    from app.services.scene_plans import ScenePlan


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) != 6:
        raise ValueError(f"6자리 hex 색상 필요: {value}")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a: tuple[int, int, int], b: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return tuple(round(x * (1 - amount) + y * amount) for x, y in zip(a, b, strict=True))


def _hue_shift(color: tuple[int, int, int], degrees: float) -> tuple[int, int, int]:
    r, g, b = (channel / 255 for channel in color)
    hue, lightness, saturation = colorsys.rgb_to_hls(r, g, b)
    r, g, b = colorsys.hls_to_rgb((hue + degrees / 360) % 1, lightness, saturation)
    return tuple(round(channel * 255) for channel in (r, g, b))


def _vgrad(size: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> np.ndarray:
    """수직 선형 그라디언트."""
    t = np.linspace(0, 1, size, dtype=np.float32)[:, None, None]
    start = np.asarray(top, dtype=np.float32)[None, None, :]
    end = np.asarray(bottom, dtype=np.float32)[None, None, :]
    return np.repeat(start * (1 - t) + end * t, size, axis=1).astype(np.uint8)


def _dgrad(size: int, first: tuple[int, int, int], second: tuple[int, int, int],
           angle: float, blend_px: int | None = None, split_at: float = 0.5) -> np.ndarray:
    """각도를 가진 선형 그라디언트. blend_px 지정 시 유계 하드 분할."""
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    radians = math.radians(angle)
    projection = xx * math.cos(radians) + yy * math.sin(radians)
    projection = (projection - projection.min()) / max(float(np.ptp(projection)), 1.0)
    if blend_px is not None:
        blend = max(blend_px / size, 1 / size)
        projection = np.clip((projection - split_at) / blend + 0.5, 0, 1)
    start = np.asarray(first, dtype=np.float32)
    end = np.asarray(second, dtype=np.float32)
    return (start + projection[..., None] * (end - start)).astype(np.uint8)


def _radial(size: int, inner: tuple[int, int, int], outer: tuple[int, int, int],
            center: tuple[float, float] = (0.5, 0.42)) -> np.ndarray:
    """다크 모노용 타원형 중심 글로우."""
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    dx = (xx / size - center[0]) / 0.72
    dy = (yy / size - center[1]) / 0.58
    distance = np.clip(np.sqrt(dx * dx + dy * dy), 0, 1)[..., None]
    light = np.asarray(inner, dtype=np.float32)
    dark = np.asarray(outer, dtype=np.float32)
    return (light * (1 - distance) + dark * distance).astype(np.uint8)


def _floor_wall(wall: np.ndarray, horizon: float, floor: tuple[int, int, int],
                blend: int = 12) -> np.ndarray:
    """벽 그라디언트에 바닥을 붙이고 접지선을 짧게 블렌딩한다."""
    out = wall.astype(np.float32).copy()
    size = wall.shape[0]
    line = int(np.clip(horizon, 0.4, 0.9) * size)
    floor_arr = np.asarray(floor, dtype=np.float32)
    for y in range(max(0, line - blend), size):
        amount = np.clip((y - line + blend) / max(blend * 2, 1), 0, 1)
        out[y] = out[y] * (1 - amount) + floor_arr * amount
    return np.clip(out, 0, 255).astype(np.uint8)


def slot_bbox(plan: "ScenePlan", size: int) -> tuple[int, int, int, int]:
    """제품이 차지할 보호 bbox. 바닥 접점까지 포함한다."""
    width = plan.subject_scale * size
    height = min(width * 1.02, size * 0.48)
    cx = plan.subject_pos[0] * size
    bottom = plan.surface_y * size
    return (
        max(0, round(cx - width / 2)),
        max(0, round(bottom - height)),
        min(size, round(cx + width / 2)),
        min(size, round(bottom)),
    )


def text_zone_bbox(plan: "ScenePlan", size: int) -> tuple[int, int, int, int]:
    """상단 32%의 헤드라인 보호 구역."""
    zones = {
        "top": (0.20, 0.04, 0.80, 0.32),
        "top_left": (0.04, 0.04, 0.48, 0.32),
        "top_right": (0.52, 0.04, 0.96, 0.32),
    }
    if plan.text_zone not in zones:
        raise ValueError(f"지원하지 않는 text_zone: {plan.text_zone}")
    return tuple(round(value * size) for value in zones[plan.text_zone])


def _protected_mask(plan: "ScenePlan", size: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle(slot_bbox(plan, size), fill=255)
    draw.rectangle(text_zone_bbox(plan, size), fill=255)
    return mask


def _shadow_stripe(image: Image.Image, angle: float, opacity: float,
                   protected: Image.Image) -> Image.Image:
    """보호 영역을 침범하지 않는 하드 섀도 스트라이프."""
    size = image.width
    mask = Image.new("L", (size, size), 0)
    offset = math.tan(math.radians(angle)) * size * 0.16
    ImageDraw.Draw(mask).polygon(
        (
            (0, size * 0.82),
            (0, size * 0.90),
            (size * 0.42 + offset, size),
            (size * 0.24 + offset, size),
        ),
        fill=round(255 * opacity),
    )
    mask_arr = np.asarray(mask).copy()
    mask_arr[np.asarray(protected) > 0] = 0
    mask = Image.fromarray(mask_arr)
    shade = Image.new("RGB", image.size, (18, 16, 24))
    return Image.composite(shade, image, mask)


def _grain(image: Image.Image, rng: np.random.Generator, sigma: float = 1.8) -> Image.Image:
    """밴딩 방지용 미세 결정론적 그레인."""
    arr = np.asarray(image, dtype=np.float32)
    noise = rng.normal(0, sigma, (image.height, image.width, 1))
    return Image.fromarray(np.clip(arr + noise, 0, 255).astype(np.uint8), "RGB")


def _vignette(image: Image.Image, strength: float = 0.08) -> Image.Image:
    """가장자리에만 약한 비네팅을 적용한다."""
    size = image.width
    yy, xx = np.mgrid[-1:1:complex(size), -1:1:complex(size)]
    distance = np.clip((xx * xx + yy * yy) / 2, 0, 1)[..., None]
    arr = np.asarray(image, dtype=np.float32) * (1 - distance * strength)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


def _accent_palette(palette: list[tuple[int, int, int]], accent_hue: float | None) -> list[tuple[int, int, int]]:
    if accent_hue is None:
        return palette
    hue = (accent_hue / 360 if abs(accent_hue) > 1 else accent_hue) % 1
    tinted = []
    for color in palette:
        _, lightness, _ = colorsys.rgb_to_hls(*(channel / 255 for channel in color))
        rgb = colorsys.hls_to_rgb(hue, lightness, 0.12)
        tinted.append(tuple(round(channel * 255) for channel in rgb))
    return tinted


def render(plan: "ScenePlan", seed: int = 0, accent_hue: float | None = None,
           size: int = 1024) -> Image.Image:
    """plan 레시피로 배경을 렌더한다. 같은 인자는 항상 동일 픽셀을 만든다."""
    if plan.render_mode != "code":
        raise ValueError(f"code 플랜만 렌더 가능: {plan.key} ({plan.render_mode})")
    if size < 256:
        raise ValueError("size는 256 이상이어야 함")
    if len(plan.palette) < 2:
        raise ValueError(f"코드 플랜 팔레트 부족: {plan.key}")

    rng = np.random.default_rng(seed)
    hue_jitter = float(rng.uniform(-4, 4))
    palette = [_hue_shift(_rgb(value), hue_jitter) for value in plan.palette]
    if plan.style == "monotone":
        palette = _accent_palette(palette, accent_hue)
    angle = float(rng.uniform(-5, 5))
    horizon = plan.surface_y - 0.04

    if plan.archetype == "diagonal_field":
        blend_px = int(rng.integers(4, 9))
        canvas = _dgrad(size, palette[0], palette[1], 82 + angle,
                        blend_px=blend_px, split_at=0.74)
    elif plan.archetype in {"cloud_gradient", "soft_seamless", "asym_negative"}:
        canvas = _dgrad(size, palette[0], palette[1], 90 + angle)
    elif plan.archetype == "dark_mono":
        canvas = _radial(size, palette[1], palette[0])
    else:
        canvas = _vgrad(size, _mix(palette[0], (255, 255, 255), 0.05), palette[0])

    floor_color = _mix(palette[1], (255, 255, 255), 0.14)
    if plan.archetype == "asym_negative":
        wall_color = tuple(int(channel) for channel in canvas[round(horizon * size), size // 2])
        canvas = _floor_wall(canvas, horizon,
                             tuple(round(channel * 0.88) for channel in wall_color), blend=12)
    elif plan.archetype == "concept_stage":
        canvas = _floor_wall(canvas, horizon, palette[1], blend=12)
    elif plan.archetype == "split_card":
        canvas = _floor_wall(canvas, 0.58, palette[1], blend=12)
    elif plan.archetype in {"seamless_min", "lilac_seamless", "tone_seamless"}:
        canvas = _floor_wall(canvas, horizon, palette[1], blend=12)
    elif plan.archetype == "soft_seamless":
        canvas = _floor_wall(canvas, horizon, palette[-1], blend=12)
    elif plan.archetype not in {"diagonal_field", "cloud_gradient"}:
        canvas = _floor_wall(canvas, horizon, floor_color)
    base = _grain(_vignette(Image.fromarray(canvas, "RGB")), rng)
    image = base.copy()
    protected = _protected_mask(plan, size)

    if plan.archetype == "diagonal_field":
        draw = ImageDraw.Draw(image)
        draw.polygon(
            ((round(size * 0.84), 0), (size, 0), (size, round(size * 0.40))),
            fill=palette[1],
        )
        image = _shadow_stripe(image, -24 + angle, 0.22, protected)
    elif plan.archetype in {"color_block_duo", "color_block"}:
        side = "right" if plan.light_dir == "right" else "left"
        draw = ImageDraw.Draw(image)
        if side == "right":
            draw.rectangle((round(size * 0.84), 0, size, size), fill=palette[1])
        else:
            draw.rectangle((0, 0, round(size * 0.16), size), fill=palette[1])
        image = _shadow_stripe(image, 18 + angle, 0.16, protected)
    elif plan.archetype == "concept_stage":
        draw = ImageDraw.Draw(image)
        draw.polygon(
            ((0, round(size * 0.78)), (round(size * 0.24), size), (0, size)),
            fill=_mix(palette[0], palette[1], 0.22),
        )
    elif plan.archetype in {
        "split_card", "asym_negative", "seamless_min", "soft_seamless",
        "cloud_gradient", "lilac_seamless", "tone_seamless",
    }:
        pass
    elif plan.archetype == "dark_mono":
        reflection = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(reflection)
        cx = plan.subject_pos[0] * size
        y = plan.surface_y * size
        width = plan.subject_scale * size * 0.72
        draw.ellipse((cx - width / 2, y, cx + width / 2, y + size * 0.05),
                     fill=palette[1] + (55,))
        reflection = reflection.filter(ImageFilter.GaussianBlur(max(10, size // 55)))
        image = Image.alpha_composite(image.convert("RGBA"), reflection).convert("RGB")
    else:
        raise ValueError(f"지원하지 않는 code archetype: {plan.archetype}")

    return image
