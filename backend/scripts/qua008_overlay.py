"""QUA-008: 층2 타이포 오버레이 검증 — 담당: 한의정. Issue #26.

QUA-007 산출물(층1 배경)에 오버레이 3템플릿 적용 → 레퍼런스 대비 육안 판정.
비용 0 (전부 로컬 렌더링).

실행:  .venv/bin/python backend/scripts/qua008_overlay.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.schemas.ads import StylePreset
from app.services.overlay_service import apply_overlay, extract_signature_color

OUT_DIR = BACKEND_DIR / "results" / "ai" / "qua008"
QUA7 = BACKEND_DIR / "results" / "ai" / "qua007"
PROCESSED = BACKEND_DIR / "processed"

CASES = [
    # (배경 이미지, 마스크, 프리셋, 헤드라인, 서브카피)
    (QUA7 / "v2_editorial/음료1_ad_42.png", "음료1_mask.png", StylePreset.EDITORIAL,
     "STRAWBERRY ADE", "FRESH BERRY REFRESHMENT"),
    (QUA7 / "v3_retro_paper/음료1_ad_42.png", "음료1_mask.png", StylePreset.RETRO_PAPER,
     "딸기 에이드", "상큼한 과일이 톡 터지는 시원한 한 잔"),
    (QUA7 / "v2_pastel_float/음료1_ad_42.png", "음료1_mask.png", StylePreset.PASTEL_FLOAT,
     "딸기 에이드", "가볍게 즐기는 오후의 산뜻함"),
    (QUA7 / "v2_editorial/스프1_ad_42.png", "스프1_mask.png", StylePreset.EDITORIAL,
     "CREAM SOUP", "SLOW MORNING COMFORT"),
    (QUA7 / "v3_retro_paper/스프1_ad_42.png", "스프1_mask.png", StylePreset.RETRO_PAPER,
     "크림 수프", "따끈하게 데운 아침의 위로"),
]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [f"# QUA-008 결과 — {datetime.now().isoformat(timespec='seconds')}", ""]

    for img_path, mask_name, preset, headline, subcopy in CASES:
        mask_path = PROCESSED / mask_name
        if not img_path.is_file() or not mask_path.is_file():
            print(f"[스킵] 입력 없음: {img_path} / {mask_path}")
            continue
        sig = extract_signature_color(str(img_path), str(mask_path))
        out = apply_overlay(
            str(img_path), preset, headline, subcopy, str(mask_path),
            output_path=str(OUT_DIR / f"{preset.value}_{img_path.stem}_poster.png"),
        )
        line = f"- {preset.value} / {img_path.stem}: 주도색 {sig} → {Path(out).name}"
        print(line)
        lines.append(line)

    lines += ["", "## 판정 (육안 기입)", "- 레퍼런스(PickBite) 대비 완성도: (기입)", "",
              "OpenAI 호출 없음 — 비용 0"]
    (OUT_DIR / "qua008_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n결과 저장: {OUT_DIR}/qua008_summary.md")


if __name__ == "__main__":
    main()
