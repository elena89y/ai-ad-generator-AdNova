"""스타일별 결정론적 색 마감 — 담당: 한의정. 제거 가능(STYLE_FINISH=0).

생성모델의 구도·재질 표현은 유지하고 색·대비만 CPU에서 보정한다. 실제 상품 마스크가
있으면 그 영역을 우선 보호하고, 없으면 중앙 소프트 보호영역을 사용한다. 중앙 보호영역은
정확한 세그멘테이션이 아니므로 배포 전 실제 입력의 육안 검증이 필수다.
"""
from __future__ import annotations

import colorsys
import logging
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

_LOG = logging.getLogger(__name__)
_LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
_ALIASES = {
    "editorial": "editorial",
    "pop": "pop",
    "realism": "realism",
    "retro_paper": "realism",
    "pastel": "pastel_float",
    "pastel_float": "pastel_float",
    "monotone": "monotone",
    "warm_organic": "warm_vintage",
    "warm_vintage": "warm_vintage",
}


def _to_array(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0


def _to_image(array: np.ndarray) -> Image.Image:
    pixels = (np.clip(array, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    return Image.fromarray(pixels, mode="RGB")


def _rgb_to_hsv(array: np.ndarray) -> np.ndarray:
    pixels = (np.clip(array, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    return np.asarray(Image.fromarray(pixels, mode="RGB").convert("HSV"), dtype=np.float32) / 255.0


def _hsv_to_rgb(array: np.ndarray) -> np.ndarray:
    pixels = (np.clip(array, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
    return _to_array(Image.fromarray(pixels, mode="HSV").convert("RGB"))


def _central_protection(height: int, width: int) -> np.ndarray:
    """마스크가 없을 때 중앙 상품을 부드럽게 보호하는 타원형 prior."""
    yy, xx = np.mgrid[0:height, 0:width]
    nx = (xx - (width - 1) * 0.5) / max(width * 0.34, 1.0)
    ny = (yy - (height - 1) * 0.50) / max(height * 0.43, 1.0)
    radius = np.sqrt(nx * nx + ny * ny)
    return np.clip(1.55 - radius, 0.0, 1.0).astype(np.float32)


def _fallback_protection(image: Image.Image) -> np.ndarray:
    """중앙 prior와 코너 배경색 차이를 결합한 소프트 상품 추정."""
    rgb = _to_array(image)
    height, width = rgb.shape[:2]
    patch = max(4, int(min(height, width) * 0.08))
    corners = np.stack((
        rgb[:patch, :patch].mean(axis=(0, 1)),
        rgb[:patch, -patch:].mean(axis=(0, 1)),
        rgb[-patch:, :patch].mean(axis=(0, 1)),
        rgb[-patch:, -patch:].mean(axis=(0, 1)),
    ))
    distances = np.linalg.norm(rgb[..., None, :] - corners[None, None, ...], axis=-1)
    foreground = np.clip((distances.min(axis=-1) - 0.06) / 0.22, 0.0, 1.0)
    foreground = np.asarray(
        Image.fromarray((foreground * 255).astype(np.uint8), mode="L").filter(
            ImageFilter.GaussianBlur(radius=max(2, min(height, width) / 90))
        ),
        dtype=np.float32,
    ) / 255.0
    central = _central_protection(height, width)
    return central * (0.18 + 0.82 * foreground)


def _protection_mask(image: Image.Image, mask_path: str | None) -> tuple[np.ndarray, bool]:
    if mask_path:
        mask = Image.open(mask_path).convert("L").resize(image.size, Image.Resampling.LANCZOS)
        return np.asarray(mask, dtype=np.float32) / 255.0, True
    return _fallback_protection(image), False


def dominant_hue(img: Image.Image, mask: np.ndarray | None = None) -> float:
    """상품 대표 색상(H, 0~1). 마스크가 없으면 중앙 영역의 S*V 가중 원형 평균."""
    rgb = _to_array(img)
    hsv = _rgb_to_hsv(rgb)
    if mask is None:
        mask = _central_protection(rgb.shape[0], rgb.shape[1])
    if mask.shape != rgb.shape[:2]:
        raise ValueError("mask 크기가 이미지와 다릅니다")
    weights = hsv[..., 1] * hsv[..., 2] * np.clip(mask, 0.0, 1.0)
    if float(weights.sum()) < 1e-5:
        return 0.08
    angles = hsv[..., 0] * (2.0 * np.pi)
    vector = np.sum(weights * np.exp(1j * angles))
    return float((np.angle(vector) / (2.0 * np.pi)) % 1.0)


def _monotone(rgb: np.ndarray, hue: float) -> np.ndarray:
    base = np.asarray(colorsys.hsv_to_rgb(hue, 0.62, 0.88), dtype=np.float32)
    dark = base * 0.22
    light = 0.82 + base * 0.18
    lum = np.clip(rgb @ _LUMA, 0.0, 1.0)[..., None]
    lum = np.clip((lum - 0.5) * 1.08 + 0.5, 0.0, 1.0)
    return dark + (light - dark) * lum


def _warm_vintage(rgb: np.ndarray) -> np.ndarray:
    target = rgb.copy()
    target[..., 0] *= 1.06
    target[..., 2] *= 0.94
    target = np.clip(target, 0.0, 1.0) ** 0.97
    target = target * (1.0 - 8.0 / 255.0) + 8.0 / 255.0
    noise = np.random.default_rng(20260716).normal(0.0, 2.5 / 255.0, target.shape[:2])
    return target + noise[..., None]


def _pop(rgb: np.ndarray) -> np.ndarray:
    hsv = _rgb_to_hsv(rgb)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.30, 0.0, 1.0)
    target = _hsv_to_rgb(hsv)
    target = np.clip((target - 0.5) * 1.25 + 0.5, 0.0, 1.0)
    return _to_array(_to_image(target).filter(
        ImageFilter.UnsharpMask(radius=2, percent=60, threshold=3)
    ))


def _pastel(rgb: np.ndarray) -> np.ndarray:
    target = np.clip((rgb - 0.5) * 0.85 + 0.5 + 18.0 / 255.0, 0.0, 1.0)
    hsv = _rgb_to_hsv(target)
    hsv[..., 1] *= 0.90
    target = _hsv_to_rgb(hsv)
    return target + np.array([2.0, 0.0, 4.0], dtype=np.float32) / 255.0


def _editorial(rgb: np.ndarray) -> np.ndarray:
    means = rgb.reshape(-1, 3).mean(axis=0) + 1e-6
    gray = float(means.mean())
    gain = 1.0 + 0.5 * (gray / means - 1.0)
    neutral = np.clip(rgb * gain, 0.0, 1.0)
    return np.clip((neutral - 0.5) * 1.06 + 0.5, 0.0, 1.0)


def _realism(rgb: np.ndarray) -> np.ndarray:
    return np.clip((rgb - 0.5) * 1.03 + 0.5, 0.0, 1.0)


def apply(path: str, style_key: str, mask_path: str | None = None,
          strength: float = 0.6) -> str:
    """스타일 마감을 적용해 `_finish` 파일을 반환한다. 실패하거나 미지원이면 원본을 유지한다."""
    try:
        style = _ALIASES.get((style_key or "").strip().lower())
        if style is None:
            _LOG.warning("style_finish 미지원 스타일(원본 유지): %s", style_key)
            return path
        amount = float(np.clip(strength, 0.0, 1.0))
        if amount == 0.0:
            return path

        source = Path(path)
        image = Image.open(source).convert("RGB")
        rgb = _to_array(image)
        protection, has_mask = _protection_mask(image, mask_path)

        if style == "monotone":
            target = _monotone(rgb, dominant_hue(image, protection))
            protected_fraction = 0.92 if has_mask else 0.88
        elif style == "warm_vintage":
            target = _warm_vintage(rgb)
            protected_fraction = 0.90 if has_mask else 0.85
        elif style == "pop":
            target = _pop(rgb)
            protected_fraction = 0.88 if has_mask else 0.82
        elif style == "pastel_float":
            target = _pastel(rgb)
            protected_fraction = 0.94 if has_mask else 0.92
        elif style == "editorial":
            target = _editorial(rgb)
            protected_fraction = 0.90 if has_mask else 0.84
        else:
            target = _realism(rgb)
            protected_fraction = 0.94 if has_mask else 0.88

        blend = amount * (1.0 - protected_fraction * protection)
        finished = rgb * (1.0 - blend[..., None]) + target * blend[..., None]
        # JPEG 재압축 손실과 품질 설정 편차를 피하기 위해 마감본은 항상 lossless PNG로 저장한다.
        output = source.with_name(f"{source.stem}_finish.png")
        _to_image(finished).save(output)
        return str(output)
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("style_finish 실패(원본 유지): %s", exc)
        return path


def style_stats(path: str, mask_path: str | None = None,
                background_only: bool = False) -> dict[str, float]:
    """스타일 분리 게이트용 색 통계를 반환한다."""
    image = Image.open(path).convert("RGB")
    rgb = _to_array(image)
    hsv = _rgb_to_hsv(rgb)
    weights = hsv[..., 1]

    region = np.ones(rgb.shape[:2], dtype=bool)
    if background_only:
        protection, _ = _protection_mask(image, mask_path)
        region = protection < 0.25
    selected_weights = weights[region]
    selected_hues = hsv[..., 0][region]
    if float(selected_weights.sum()) < 1e-5:
        concentration = 0.0
    else:
        angles = selected_hues * (2.0 * np.pi)
        concentration = float(abs(np.sum(selected_weights * np.exp(1j * angles)))
                              / selected_weights.sum())

    selected = rgb[region]
    selected_hsv = hsv[region]
    lum = selected @ _LUMA
    return {
        "hue_concentration": concentration,
        "mean_sat": float(selected_hsv[:, 1].mean()),
        "warmth": float((selected[:, 0].mean() + 1e-6) / (selected[:, 2].mean() + 1e-6)),
        "contrast": float(lum.std()),
    }
