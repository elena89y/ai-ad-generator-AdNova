"""토큰 → 비용($) 환산표 — 담당: 한의정.

단가는 $/1M tokens. gpt-5.4-mini 는 2026-07-08 팀 OpenAI 대시보드에서 역산:
  input  $0.0262 / 41,892 tok ≈ $0.625/1M
  output $0.0156 /  3,470 tok ≈ $4.50/1M
→ 정확 단가는 OpenAI 요금표로 교체 가능. 로컬 모델(Qwen3-VL 등)은 비용 0(전력 제외).
"""
from __future__ import annotations

PRICES: dict[str, dict[str, float]] = {
    "gpt-5.4-mini": {"in": 0.625, "out": 4.50, "cached_in": 0.0625},
    # 로컬 모델 — API 비용 없음(토큰은 계측하되 $0)
    "qwen3-vl-4b": {"in": 0.0, "out": 0.0},
    "qwen3-vl-8b": {"in": 0.0, "out": 0.0},
    "qwen3-vl": {"in": 0.0, "out": 0.0},
}


def _lookup(model: str) -> dict[str, float]:
    if model in PRICES:
        return PRICES[model]
    # 버전 접미사(-2026-03-17) 제거 후 재조회
    base = model.split("-2026")[0].split("-2025")[0]
    return PRICES.get(base, {"in": 0.0, "out": 0.0})


def cost_of(model: str, tok_in: int = 0, tok_out: int = 0) -> float:
    """토큰 → 비용($). 미등록 모델은 0(로컬 가정)."""
    p = _lookup(model)
    return round((tok_in * p.get("in", 0.0) + tok_out * p.get("out", 0.0)) / 1_000_000, 6)


# --- GPU 시간 → 비용($) 환산 (v6 T0) -------------------------------------------
# "로컬 모델은 공짜"가 아니라는 KPI 논거용 근사치. GCP g2(NVIDIA L4, us-central1)
# 온디맨드 시간당 요금 근사 — 정확 단가는 팀 청구서 기준으로 env GPU_USD_PER_HOUR 교체.
GPU_USD_PER_HOUR_DEFAULT = 0.71


def gpu_usd_per_hour() -> float:
    import os

    try:
        return float(os.environ.get("GPU_USD_PER_HOUR", GPU_USD_PER_HOUR_DEFAULT))
    except ValueError:
        return GPU_USD_PER_HOUR_DEFAULT


def gpu_cost_of(seconds: float) -> float:
    """GPU 점유 초 → 환산 비용($). CPU 실행(로컬 Mac 등)은 호출부에서 0초로 들어온다."""
    return round(max(seconds, 0.0) / 3600.0 * gpu_usd_per_hour(), 6)


# --- 이미지 생성 API 장당 비용($) ------------------------------------------------
# gpt-image-2 edit 실측(2026-07-17 A/B/C 전모드 검증): 장당 $0.01~0.02 → 중앙값 근사.
# gpt-image-1-mini 는 미실측 추정치 — T2 첫 실호출에서 usage 역산으로 보정할 것.
IMAGE_PRICES: dict[str, float] = {
    "gpt-image-2": 0.015,
    "gpt-image-1-mini": 0.005,
}


def image_cost_of(model: str, n: int = 1) -> float:
    """이미지 생성/편집 API n장 → 비용($). 미등록 모델은 0(로컬 가정)."""
    return round(IMAGE_PRICES.get(model, 0.0) * max(n, 0), 6)
