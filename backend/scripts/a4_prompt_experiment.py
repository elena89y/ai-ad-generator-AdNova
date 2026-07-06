"""A-4 프롬프트 실험: negative v1 → v2 — 텍스트 아티팩트·소품 환각 억제 — 담당: 한의정.

조건: seed 고정(42, 43) · steps 30 고정 · 동일 입력(쿠키1) · warm_vintage.
v1 = prompt_service 현행 (baseline 산출물 results/ai/cookie1_ad_42·43.png 재사용)
v2 = positive 에서 'sharp focus' 제거(텍스트 'SHARP' 누출 의심) +
     negative 에 문자·간판·포장 계열 및 소품/음식 환각 억제 키워드 보강

산출물: backend/results/ai/a4_prompt/ (git 업로드 금지). OpenAI 호출 없음 — 비용 0.

실행:  .venv/bin/python backend/scripts/a4_prompt_experiment.py
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.schemas.ads import ProductInfo, StylePreset
from app.services import image_service
from app.services.prompt_service import ImagePrompt, build_image_prompt

OUT_DIR = BACKEND_DIR / "results" / "ai" / "a4_prompt"
SEEDS = (42, 43)

# v2 후보 (실험용 — 채택 시 prompt_service 에 반영)
V2_POSITIVE_BASE = "professional product advertisement photo, high detail"
V2_NEGATIVE_EXTRA = (
    "words, typography, writing, signage, label, price tag, packaging design, "
    "brand name, poster, extra food, extra cookies, additional products, people"
)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    product = ProductInfo(name="matcha raspberry cookies")

    v1 = build_image_prompt(product, StylePreset.WARM_VINTAGE)
    v2 = ImagePrompt(
        positive=v1.positive.replace(
            "professional product advertisement photo, sharp focus", V2_POSITIVE_BASE
        ),
        negative=f"{v1.negative}, {V2_NEGATIVE_EXTRA}",
    )

    lines = [
        f"# A-4 프롬프트 실험 (negative v1→v2) — {datetime.now().isoformat(timespec='seconds')}",
        "- 조건: seed 42/43 고정, steps 30, warm_vintage, 입력 쿠키1",
        "",
        f"## v1 (baseline — results/ai/cookie1_ad_42.png, cookie1_ad_43.png 재사용)",
        f"- positive: {v1.positive}",
        f"- negative: {v1.negative}",
        "",
        f"## v2",
        f"- positive: {v2.positive}",
        f"- negative: {v2.negative}",
        "",
        "## 실행 기록",
    ]

    processed = image_service.preprocess(
        str(BACKEND_DIR / "uploads/photoset/쿠키1.png"), output_dir=str(OUT_DIR)
    )
    for seed in SEEDS:
        result = image_service.generate_ad_image(
            processed, v2, seed=seed, output_dir=str(OUT_DIR)
        )
        line = f"- v2 seed={seed}: {result.infer_seconds:.2f}s → {result.final_image_path}"
        print(line)
        lines.append(line)

    lines += [
        "",
        "## 판정 (육안 기입)",
        "- v1 관찰: 나무 받침 텍스트 아티팩트('SHARP' 등), 'Gem' 워터마크, 배경 소품(가짜 쿠키) 환각",
        "- v2 텍스트 아티팩트: (기입)",
        "- v2 소품 환각: (기입)",
        "- 채택 여부: (기입 — 채택 시 prompt_service _BASE_POSITIVE/_BASE_NEGATIVE 반영, fix(prompt) 커밋)",
        "",
        "OpenAI 호출 없음 — 비용 0",
    ]
    (OUT_DIR / "a4_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"결과 저장: {OUT_DIR}/a4_summary.md")


if __name__ == "__main__":
    main()
