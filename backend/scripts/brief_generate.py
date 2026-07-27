"""기능 1 데모 러너 — 텍스트 브리프만으로 멀티포맷 광고팩 생성(상품 사진 없음). 담당: 한의정.

배경 생성 엔진: --engine api(gpt-image-2, GPU 불필요·Mac 가능) | local(RealVisXL, VM 전용).
정직성: 일시·장소·문의처는 브리프 원문 발췌만 조판(오탈자 0). 규정 경고는 보조 체크리스트로 출력.

예:
    cd backend && ../.venv/bin/python -m scripts.brief_generate \
        --brief "○○구 벚꽃축제 · 4/5~4/7 · ○○공원 · 문의 02-123-4567" \
        --engine api --purposes sns banner --desktop
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")  # OPENAI_API_KEY (VM 실행 시 — g2_api_smoke 패턴)

from app.schemas.ads import AdPurpose  # noqa: E402
from app.services import generation_service  # noqa: E402

_PURPOSE_MAP = {
    "sns": AdPurpose.SNS,
    "banner": AdPurpose.BANNER,
    "card_news": AdPurpose.CARD_NEWS,
    "detail_page": AdPurpose.DETAIL_PAGE,
}


def main() -> int:
    ap = argparse.ArgumentParser(description="브리프 → 멀티포맷 광고팩(기능 1)")
    ap.add_argument("--brief", required=True, help="자유 텍스트 브리프(일시·장소·문의처 포함 권장)")
    ap.add_argument("--vertical", default="event", help="업종 시드(event 등)")
    ap.add_argument("--engine", default=None, choices=["api", "local"],
                    help="배경 생성 엔진(미지정 시 ENGINE_POLICY, 기본 api)")
    ap.add_argument("--purposes", nargs="+", default=["sns", "banner"],
                    choices=list(_PURPOSE_MAP), help="생성할 포맷 팩")
    ap.add_argument("--sizes", nargs="*", default=None, help="규격 label 필터(선택)")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--style", default=None, help="타이포 스타일 키(editorial 등)")
    ap.add_argument("--out", default=str(BACKEND_DIR / "results" / "ai" / "brief"),
                    help="산출물 저장 경로(기본: cwd 무관 절대경로 — backend/backend/ 사고 방지)")
    ap.add_argument("--desktop", action="store_true",
                    help="~/Desktop/AdNova/brief 로 결과 복사(육안 확인)")
    args = ap.parse_args()

    purposes = [_PURPOSE_MAP[p] for p in args.purposes]
    result = generation_service.run_from_brief(
        brief=args.brief, vertical=args.vertical, purposes=purposes,
        sizes=args.sizes, engine=args.engine, seed=args.seed,
        style=args.style, output_dir=args.out,
    )

    print(f"\n헤드라인: {result.headline}")
    print(f"정보줄(원문): {list(result.info_lines)}")
    if result.fine_print:
        print(f"규정 문구: {result.fine_print}")
    if result.violations:
        print("규정 경고(보조 체크리스트):")
        for v in result.violations:
            print(f"  - {v}")
    print(f"\n생성 {len(result.outputs)}장 ({', '.join(result.purposes)}):")
    for path in result.outputs:
        print(f"  {path}")

    if args.desktop:
        dest = Path.home() / "Desktop" / "AdNova" / "brief"
        dest.mkdir(parents=True, exist_ok=True)
        for path in result.outputs:
            src = Path(path)
            if src.is_file():
                shutil.copy2(src, dest / src.name)
        print(f"\n복사됨 → {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
