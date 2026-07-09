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
