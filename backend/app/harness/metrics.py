"""품질 지표 래퍼 — 담당: 한의정.

identity(정체성 보존): DINOv2 코사인 · LPIPS  — 제품 마스크 영역만 비교.
aesthetic(심미): LAION improved-aesthetic-predictor(CLIP ViT-L/14 + MLP) — 결과물 절대 점수.

⚠️ 캘리브레이션(P2-2): 어떤 단일 자동지표도 사람 아트디렉터 미세판정을 재현 못 함.
  aesthetic 는 **advisory 회귀 트립와이어**(큰 하락 감지)용이지 미세 A/B 오라클 아님.
  DINO 는 "덜 바꿈"을 높게 봐 좋은 향상을 penalize. 최종 미세 미학판정은 사람(육안)이 정본.
  ImageReward/HPS 는 이 torch2.12/cu130 스택에서 구 transformers 의존으로 로드 실패 → LAION 채택.

⚠️ 각 지표 모델은 lazy 로드 + 의존성/다운로드 실패 시 **None 반환**(크래시 금지).
  → 평가가 일부 지표 미설치로 막히지 않는다. None 은 원장에 그대로 기록.

지표 모델 디스크: DINOv2 ~0.35G · LPIPS ~few MB · CLIP ViT-L/14 ~0.9G · aesthetic MLP ~5MB.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

_dino = None
_lpips = None
_clip = None
_clip_prep = None
_laion_mlp = None

# LAION improved-aesthetic-predictor 가중치(CLIP ViT-L/14 위 5MB MLP)
_AESTHETIC_WPATH = Path(__file__).resolve().parents[2] / "experiments" / "aesthetic_l14.pth"
_AESTHETIC_WURL = ("https://github.com/christophschuhmann/improved-aesthetic-predictor/"
                   "raw/main/sac+logos+ava1-l14-linearMSE.pth")


# --- 공통 ---------------------------------------------------------------------
def _crop_to_mask(img: Image.Image, mask_path: Optional[str], pad: float = 0.05) -> Image.Image:
    """마스크 bbox 로 크롭(제품 영역 집중). 마스크 없으면 원본."""
    if not mask_path or not Path(mask_path).is_file():
        return img
    m = np.asarray(Image.open(mask_path).convert("L").resize(img.size)) > 40
    ys, xs = np.nonzero(m)
    if len(xs) < 10:
        return img
    w, h = img.size
    px, py = int(w * pad), int(h * pad)
    x0, y0 = max(0, xs.min() - px), max(0, ys.min() - py)
    x1, y1 = min(w, xs.max() + px), min(h, ys.max() + py)
    return img.crop((x0, y0, x1, y1))


# --- DINOv2 정체성 ------------------------------------------------------------
def _load_dino():  # noqa: ANN202
    global _dino
    if _dino is None:
        import torch

        model = torch.hub.load("facebookresearch/dinov2", "dinov2_vitb14", verbose=False)
        model.eval()
        if torch.cuda.is_available():
            model = model.to("cuda")
        _dino = model
    return _dino


def _dino_embed(img: Image.Image, size: int = 224):  # noqa: ANN202
    """torchvision 의존 없이 PIL+numpy 전처리(짧은변 리사이즈→센터크롭→ImageNet 정규화)."""
    import torch

    im = img.convert("RGB")
    w, h = im.size
    s = size / min(w, h)
    im = im.resize((round(w * s), round(h * s)), Image.BICUBIC)
    w, h = im.size
    l, t = (w - size) // 2, (h - size) // 2
    im = im.crop((l, t, l + size, t + size))
    arr = np.asarray(im, dtype=np.float32) / 255.0
    arr = (arr - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
    x = torch.from_numpy(arr).permute(2, 0, 1).unsqueeze(0).float()
    if torch.cuda.is_available():
        x = x.to("cuda")
    with torch.no_grad():
        feat = _load_dino()(x)
    return torch.nn.functional.normalize(feat, dim=-1)


def identity_dino(before_path: str, after_path: str,
                  mask_path: Optional[str] = None) -> Optional[float]:
    """편집 전후 제품영역 DINOv2 코사인(1=동일). 정체성 보존 핵심 지표."""
    try:
        import torch

        a = _crop_to_mask(Image.open(before_path), mask_path)
        b = _crop_to_mask(Image.open(after_path), mask_path)
        cos = torch.sum(_dino_embed(a) * _dino_embed(b)).item()
        return round(float(cos), 4)
    except Exception as e:
        logger.warning(f"identity_dino 실패 → None: {e}")
        return None


# --- LPIPS 정체성 -------------------------------------------------------------
def _load_lpips():  # noqa: ANN202
    global _lpips
    if _lpips is None:
        import lpips
        import torch

        m = lpips.LPIPS(net="alex", verbose=False)
        if torch.cuda.is_available():
            m = m.to("cuda")
        _lpips = m
    return _lpips


def identity_lpips(before_path: str, after_path: str,
                   mask_path: Optional[str] = None) -> Optional[float]:
    """편집 전후 제품영역 LPIPS(0=동일, 낮을수록 보존). 지각적 거리."""
    try:
        import torch

        def prep(p):
            im = _crop_to_mask(Image.open(p), mask_path).convert("RGB").resize((256, 256))
            t = torch.from_numpy(np.asarray(im)).float().permute(2, 0, 1) / 127.5 - 1.0
            return t.unsqueeze(0).to("cuda" if torch.cuda.is_available() else "cpu")

        with torch.no_grad():
            d = _load_lpips()(prep(before_path), prep(after_path)).item()
        return round(float(d), 4)
    except Exception as e:
        logger.warning(f"identity_lpips 실패 → None: {e}")
        return None


# --- 심미 점수 (LAION aesthetic, advisory) ------------------------------------
def _load_laion():  # noqa: ANN202
    """CLIP ViT-L/14 + aesthetic MLP lazy 로드. 가중치 없으면 다운로드."""
    global _clip, _clip_prep, _laion_mlp
    if _laion_mlp is not None:
        return _clip, _clip_prep, _laion_mlp
    import urllib.request

    import clip  # openai CLIP
    import torch
    import torch.nn as nn

    class MLP(nn.Module):
        def __init__(self, d: int = 768):
            super().__init__()
            self.layers = nn.Sequential(
                nn.Linear(d, 1024), nn.Dropout(0.2), nn.Linear(1024, 128), nn.Dropout(0.2),
                nn.Linear(128, 64), nn.Dropout(0.1), nn.Linear(64, 16), nn.Linear(16, 1))

        def forward(self, x):  # noqa: ANN001
            return self.layers(x)

    if not _AESTHETIC_WPATH.is_file():
        _AESTHETIC_WPATH.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(_AESTHETIC_WURL, _AESTHETIC_WPATH)
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    mlp = MLP().to(dev)
    mlp.load_state_dict(torch.load(_AESTHETIC_WPATH, map_location=dev))
    mlp.eval()
    model, prep = clip.load("ViT-L/14", device=dev)
    _clip, _clip_prep, _laion_mlp = model, prep, mlp
    return _clip, _clip_prep, _laion_mlp


def aesthetic(image_path: str, prompt: str = "") -> dict:
    """결과물 심미 절대 점수 {laion}(≈1~10). **advisory**(회귀 트립와이어). 실패 시 None.

    캘리브레이션상 미세 A/B 오라클 아님 — 큰 하락 감지·회귀 스크리닝용. prompt 는 미사용
    (LAION 은 순수 심미). 미세 미학 최종판정은 사람(육안).
    """
    out: dict[str, Optional[float]] = {"laion": None}
    try:
        import torch

        model, prep, mlp = _load_laion()
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        img = prep(Image.open(image_path).convert("RGB")).unsqueeze(0).to(dev)
        with torch.no_grad():
            f = model.encode_image(img).float()
            f = f / f.norm(dim=-1, keepdim=True)
            out["laion"] = round(float(mlp(f).item()), 4)
    except Exception as e:
        logger.warning(f"aesthetic(laion) 실패 → None: {e}")
    return out


def compute_identity(before_path: str, after_path: str,
                     mask_path: Optional[str] = None) -> dict:
    """정체성 지표 묶음(기준선·평가 공통)."""
    return {
        "identity_dino": identity_dino(before_path, after_path, mask_path),
        "identity_lpips": identity_lpips(before_path, after_path, mask_path),
    }
