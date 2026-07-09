"""모델 VRAM 원장 + 언로드 오케스트레이션 — 담당: 한의정.

cafe_service 의 수동 VRAM 시퀀싱(RealVis→unload→FLUX)을 일반화.
  - 정적 등록표: 모델별 추정 VRAM([실측필요], Phase 별 갱신) — 계획·리포트용
  - gpu_free_gb(): torch 로 실제 여유 조회(원장보다 신뢰)
  - reclaim(need_gb, keep): 실제 여유가 need 이상이 될 때까지 알려진 파이프라인 언로드
    (기존 image_service.unload_pipelines / flux_service.unload 재사용, lazy import 로 순환 회피)

L4 22GB. 안전 상한 = 20GB(2GB 여유). 동시 상주 조합은 이 상한 아래로만.
"""
from __future__ import annotations

import logging
from typing import Iterable

logger = logging.getLogger(__name__)

VRAM_CAP_GB = 20.0
SAFETY_MARGIN_GB = 1.5

# 모델별 추정 VRAM (GB). [실측필요] — 로드 후 gpu_used_gb 로 갱신.
MODELS: dict[str, float] = {
    "sdxl_inpaint": 9.0,
    "sdxl_harmonize": 5.0,   # 인페인트와 컴포넌트 공유(추가분)
    "realvis": 7.0,
    "flux": 13.0,
    "kontext": 13.0,         # Phase 1 [실측필요]
    "qwen3vl_4b": 6.0,       # Phase 2 [실측필요]
    "qwen3vl_8b": 10.0,      # [실측필요]
    "qwen_edit": 14.0,       # Phase 4 [실측필요]
}


def gpu_free_gb() -> float:
    """실제 GPU 여유 VRAM(GB). CUDA 없으면 inf."""
    try:
        import torch

        if torch.cuda.is_available():
            free, _ = torch.cuda.mem_get_info()
            return round(free / 1024**3, 2)
    except Exception:
        pass
    return float("inf")


def gpu_used_gb() -> float:
    try:
        import torch

        if torch.cuda.is_available():
            free, total = torch.cuda.mem_get_info()
            return round((total - free) / 1024**3, 2)
    except Exception:
        pass
    return 0.0


def snapshot() -> dict:
    """현재 VRAM 상태(원장 기록용)."""
    return {"free_gb": gpu_free_gb(), "used_gb": gpu_used_gb()}


def _unload_all(keep: Iterable[str]) -> list[str]:
    """알려진 파이프라인 언로드(keep 제외). 반환: 언로드 시도한 그룹명."""
    keep = set(keep)
    freed: list[str] = []
    try:
        from ..services import image_service

        # image_service 는 sdxl/harmonize/food(realvis) 를 keep 인자로 관리
        img_keep = tuple(k for k in ("sdxl", "harmonize", "food") if k in keep)
        image_service.unload_pipelines(keep=img_keep)
        freed.append("image_service.pipelines")
    except Exception as e:
        logger.warning(f"image_service 언로드 스킵: {e}")
    if "flux" not in keep:
        try:
            from ..services import flux_service

            flux_service.unload()
            freed.append("flux")
        except Exception as e:
            logger.warning(f"flux 언로드 스킵: {e}")
    return freed


def reclaim(need_gb: float, keep: Iterable[str] = ()) -> dict:
    """need_gb 만큼의 여유를 확보(keep 은 언로드 제외). 반환: {before, after, freed}.

    대형 모델(FLUX/Kontext/RealVis) 로드 전 호출. 실제 여유가 이미 충분하면 무동작.
    """
    before = gpu_free_gb()
    if before >= need_gb + SAFETY_MARGIN_GB:
        return {"before": before, "after": before, "freed": [], "note": "충분"}
    freed = _unload_all(keep)
    try:
        import gc

        import torch

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
    after = gpu_free_gb()
    if after < need_gb:
        logger.warning(f"reclaim 부족: 필요 {need_gb} / 확보 {after}GB (keep={list(keep)})")
    return {"before": before, "after": after, "freed": freed}


def will_fit(name: str, keep: Iterable[str] = ()) -> bool:
    """등록 추정치 기준, name 을 keep 과 함께 올렸을 때 상한 이내인지(계획용)."""
    load = MODELS.get(name, 0.0) + sum(MODELS.get(k, 0.0) for k in keep)
    return load <= VRAM_CAP_GB
