"""QUA-007: 스타일 프리셋 6종 비교 생성 — 담당: 한의정.

동일 입력·동일 seed 로 6개 프리셋 각각 생성 (조화 패스 포함, 서비스 공식 경로).
설계메모 검증 포인트: "프리셋만 바꿔 생성 → 결과가 톤별로 분명히 구분되는가".
CLIP 77토큰 한도 검사(positive/negative)도 전 프리셋에 대해 수행.

산출물 (backend/results/ai/qua007/, git 업로드 금지). 비용 0.

실행:  .venv/bin/python backend/scripts/qua007_preset_six.py [--input ...] [--seed 42]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.schemas.ads import ProductInfo, StylePreset
from app.services import image_service
from app.services.prompt_service import build_image_prompt

OUT_DIR = BACKEND_DIR / "results" / "ai" / "qua007"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(BACKEND_DIR / "uploads/photoset/스프1.png"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--name", default="크림 수프")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# QUA-007 결과 — {datetime.now().isoformat(timespec='seconds')}",
        f"- 입력: {args.input} / seed={args.seed} / 조화 패스 포함 (서비스 공식 경로)",
        "",
        "| 프리셋 | pos 토큰 | neg 토큰 | 생성(s) | 조화(s) | 산출물 |",
        "|---|---|---|---|---|---|",
    ]

    # CLIP 토큰 검사기 (SDXL tokenizer 재사용)
    pipe = image_service._load_pipeline()
    tokenizer = pipe.tokenizer

    def n_tokens(text: str) -> int:
        return len(tokenizer(text).input_ids)

    processed = image_service.preprocess(args.input, output_dir=str(OUT_DIR))
    product = ProductInfo(name=args.name)

    for preset in StylePreset:
        prompt = build_image_prompt(product, preset)
        pos_n, neg_n = n_tokens(prompt.positive), n_tokens(prompt.negative)
        warn = " ⚠️초과" if max(pos_n, neg_n) > 77 else ""

        result = image_service.generate_ad_image(
            processed, prompt, seed=args.seed,
            output_dir=str(OUT_DIR / preset.value),
        )
        row = (
            f"| {preset.value} | {pos_n}{warn if pos_n > 77 else ''} | "
            f"{neg_n}{warn if neg_n > 77 else ''} | {result.infer_seconds:.2f} | "
            f"{result.harmonize_seconds:.2f} | {Path(result.final_image_path).name} |"
        )
        print(row)
        lines.append(row)

    lines += [
        "",
        "## 판정 (육안 기입 — 설계메모 검증 포인트)",
        "- 6종이 톤별로 분명히 구분되는가: (기입)",
        "- 신규 3종(editorial/retro_paper/pastel_float)이 레퍼런스 무드를 재현하는가: (기입)",
        "",
        "OpenAI 호출 없음 — 비용 0",
    ]
    (OUT_DIR / "qua007_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n결과 저장: {OUT_DIR}/qua007_summary.md")


if __name__ == "__main__":
    main()
