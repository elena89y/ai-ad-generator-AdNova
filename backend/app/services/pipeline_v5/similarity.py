"""구도 유사도 판정 공용 유틸.

상세페이지 최종 게이트(formats/detail_page.py)와 생성 단계의 앵글 재시도
(generation_app.py)가 같은 기준을 써야 "게이트를 통과할 만큼 다르게 만들었는데
막상 최종 검증에서 또 걸리는" 불일치가 안 생긴다(TOPVIEW-001, 2026-07-20).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

MAX_STRUCTURE_CORRELATION = 0.84


def structure_vector(path: Path | str) -> np.ndarray:
    image = Image.open(path).convert("L").resize((32, 32), Image.BILINEAR)
    return np.asarray(image, dtype=np.float32).reshape(-1)


def correlation(left: np.ndarray, right: np.ndarray) -> float:
    if float(left.std()) < 1e-6 or float(right.std()) < 1e-6:
        return 1.0 if np.allclose(left, right, atol=3.0) else 0.0
    return float(np.corrcoef(left, right)[0, 1])
