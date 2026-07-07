"""IMG-003: FLUX.1 Fill 씬 엔진 실험 — 담당: 한의정.

목적: 코드 드로잉으로 안 나오는 '디자이너급 그래픽 배경'을 FLUX 로 생성.
      그래픽=FLUX / 타이포=overlay_service 역할 분담 검증.

측정: 로드 시간, 추론 시간, Peak VRAM, 육안 품질. OpenAI 호출 없음(비용 0).
⚠️ FLUX.1 Fill = gated + 비상업. `huggingface-cli login` 선행 필요.

실행:  .venv/bin/python backend/scripts/img003_flux_poster.py \
         --input backend/uploads/photoset/음료1.png [--overlay]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.services import flux_service, image_service

OUT_DIR = BACKEND_DIR / "results" / "ai" / "img003"

# 스타일별 FLUX 프롬프트 (T5 = 서술형 자연어. 'no text' 필수 — Fill 은 negative 없음)
FLUX_PROMPTS = {
    "retro": (
        "a retro screen-printed food advertisement poster background, one bold organic "
        "flowing ribbon shape in warm terracotta on a cream ivory paper background, "
        "vintage risograph texture, playful hand-crafted editorial design, matte print "
        "grain, the product sits on a soft grounding shadow, no text, no letters, no words"
    ),
    "pastel": (
        "a dreamy pastel product photography scene, soft peach and pink gradient studio "
        "background, floating fresh fruit pieces and translucent water droplets suspended "
        "in the air around the product, glossy bokeh, soft cinematic rim light, airy and "
        "weightless commercial advertising look, no text, no letters, no words"
    ),
    "editorial": (
        "a premium editorial product campaign, deep solid saturated color studio backdrop, "
        "dramatic soft key light from upper left, elegant minimal luxury magazine aesthetic, "
        "subtle contact shadow under the product, high-end commercial photography, "
        "no text, no letters, no words"
    ),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=str(BACKEND_DIR / "uploads/photoset/음료1.png"))
    ap.add_argument("--styles", default="retro,pastel,editorial")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--steps", type=int, default=28)
    ap.add_argument("--overlay", action="store_true", help="타이포 오버레이까지 적용")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# IMG-003 FLUX 씬 엔진 — {datetime.now().isoformat(timespec='seconds')}",
        f"- 입력: {args.input} / seed {args.seed} / steps {args.steps}",
        "",
        "| 스타일 | 로드(s) | 추론(s) | Peak VRAM(GB) | 산출물 |",
        "|---|---|---|---|---|",
    ]

    processed = image_service.preprocess(args.input, output_dir=str(OUT_DIR))

    for style in (s.strip() for s in args.styles.split(",")):
        prompt = FLUX_PROMPTS.get(style)
        if not prompt:
            print(f"[스킵] 프롬프트 없음: {style}")
            continue
        r = flux_service.generate_with_flux(
            processed, prompt, seed=args.seed, steps=args.steps,
            output_dir=str(OUT_DIR / style),
        )
        out_path = r.final_image_path
        if args.overlay:
            from app.schemas.ads import StylePreset
            from app.services.overlay_service import apply_overlay

            preset = {"retro": StylePreset.RETRO_PAPER, "pastel": StylePreset.PASTEL_FLOAT,
                      "editorial": StylePreset.EDITORIAL}[style]
            out_path = apply_overlay(r.final_image_path, preset, "STRAWBERRY ADE",
                                     "가볍게 즐기는 오후의 산뜻함", processed.mask_path)
        row = f"| {style} | {r.load_seconds:.1f} | {r.infer_seconds:.1f} | {r.peak_vram_gb} | {Path(out_path).name} |"
        print(row)
        lines.append(row)

    lines += ["", "## 판정 (육안 기입)",
              "- 코드 드로잉 대비 그래픽 품질: (기입)",
              "- SDXL 대비: (기입) / 추론시간 수용 가능?: (기입)",
              "- 비상업 라이선스 — 데모 한정 확인", ""]
    (OUT_DIR / "img003_summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n결과 저장: {OUT_DIR}/img003_summary.md")


if __name__ == "__main__":
    main()
