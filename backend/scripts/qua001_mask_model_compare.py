"""QUA-001: 마스킹 모델 비교 — u2net vs isnet-general-use vs birefnet-general — 담당: 한의정.

배경: MASK-001 에서 u2net 이 다중 객체·접촉·프레임 잘림 입력(쿠키1)의 제품 일부를
누락 → 접합 붕괴의 원인으로 확정. 대체 모델의 커버리지를 정량·시각 비교한다.

산출물 (backend/results/ai/qua001/, git 업로드 금지):
  - grid_<사진>.png       : [원본 | u2net | isnet | birefnet] 마스크 비교 그리드
  - qua001_summary.md     : 사진×모델 커버리지 표
비용 0 (로컬 ONNX 추론). 모델 최초 사용 시 가중치 다운로드 발생.

실행:  .venv/bin/python backend/scripts/qua001_mask_model_compare.py \
         [--photos backend/uploads/photoset] [--models u2net,isnet-general-use,birefnet-general]
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from PIL import Image

OUT_DIR = BACKEND_DIR / "results" / "ai" / "qua001"
THUMB = 256


def _ensure_ort() -> None:
    """ORT(CU13) 로드 전 torch 선로드 (image_service._get_rembg_session 과 동일 이유)."""
    try:
        import torch  # noqa: F401
    except Exception:
        pass
    try:
        import onnxruntime

        if hasattr(onnxruntime, "preload_dlls"):
            onnxruntime.preload_dlls()
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--photos", default=str(BACKEND_DIR / "uploads/photoset"))
    parser.add_argument("--models", default="u2net,isnet-general-use,birefnet-general")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    models = [m.strip() for m in args.models.split(",")]
    photos = sorted(Path(args.photos).glob("*.png")) + sorted(Path(args.photos).glob("*.jpg"))

    _ensure_ort()
    from rembg import new_session, remove

    sessions = {}
    lines = [
        f"# QUA-001 결과 — {datetime.now().isoformat(timespec='seconds')}",
        f"- 입력 {len(photos)}장 / 모델: {', '.join(models)}",
        "- 커버리지 = 마스크(α≥128) 픽셀 비율. GT 없음 → 모델 간 상대 비교 + 육안 그리드 판정",
        "",
        "| 사진 | " + " | ".join(f"{m} 커버리지(추론s)" for m in models) + " | 최대-최소 격차 |",
        "|---" * (len(models) + 2) + "|",
    ]

    for m in models:
        t0 = time.perf_counter()
        sessions[m] = new_session(m)
        print(f"[세션] {m}: {time.perf_counter() - t0:.1f}s")

    for photo in photos:
        img = Image.open(photo).convert("RGBA")
        img.thumbnail((1024, 1024), Image.LANCZOS)

        cells = [np.array(img.convert("RGB").resize((THUMB, THUMB)))]
        covs, cells_stats = [], []
        for m in models:
            t0 = time.perf_counter()
            result = remove(img, session=sessions[m])
            elapsed = time.perf_counter() - t0
            alpha = np.array(result.split()[-1])
            cov = float((alpha >= 128).mean())
            covs.append(cov)
            cells_stats.append(f"{cov:.1%} ({elapsed:.2f}s)")
            # 마스크 시각화 (제품=원본색, 배경=자홍 — 누락이 눈에 띄게)
            rgb = np.array(result.convert("RGB").resize((THUMB, THUMB)))
            a_small = np.array(Image.fromarray(alpha).resize((THUMB, THUMB)))
            vis = rgb.copy()
            vis[a_small < 128] = [255, 0, 255]
            cells.append(vis)

        grid = np.concatenate(cells, axis=1)
        Image.fromarray(grid).save(OUT_DIR / f"grid_{photo.stem}.png")

        gap = max(covs) - min(covs)
        row = f"| {photo.stem} | " + " | ".join(cells_stats) + f" | {gap:.1%} |"
        print(row)
        lines.append(row)

    lines += [
        "",
        "## 판정 (육안 기입)",
        "- 쿠키1(MASK-001 실패 입력)에서 전체 제품을 잡는 모델: (기입)",
        "- 채택 모델: (기입 — 채택 시 image_service._get_rembg_session 모델 교체, refactor(image) 커밋)",
        "",
        "OpenAI 호출 없음 — 비용 0",
    ]
    (OUT_DIR / "qua001_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n결과 저장: {OUT_DIR}/qua001_summary.md")


if __name__ == "__main__":
    main()
