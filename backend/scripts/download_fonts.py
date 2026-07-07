"""오버레이용 폰트 다운로드 — 담당: 한의정.

전부 OFL(SIL Open Font License) — 상업 사용·재배포 가능. 출처: google/fonts 공식 저장소.
폰트 파일은 repo 에 포함하지 않음(backend/assets/fonts/ gitignore) — 배포/신규 환경에서
이 스크립트를 1회 실행. Docker 빌드 반영은 배포 담당과 협의.

실행:  python backend/scripts/download_fonts.py
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

FONT_DIR = Path(__file__).resolve().parents[1] / "assets" / "fonts"

FONTS = {
    # 한글 세리프 (에디토리얼 헤드라인·명조 톤)
    "NanumMyeongjo-Regular.ttf": "https://github.com/google/fonts/raw/main/ofl/nanummyeongjo/NanumMyeongjo-Regular.ttf",
    # 한글 손글씨 (레트로 배너 메뉴명)
    "NanumPenScript-Regular.ttf": "https://github.com/google/fonts/raw/main/ofl/nanumpenscript/NanumPenScript-Regular.ttf",
    # 한글 고딕 (캡션·서브카피)
    "NanumGothic-Regular.ttf": "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf",
    "NanumGothic-Bold.ttf": "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf",
    # 굵은 라운드 디스플레이 (레트로 헤드라인 — 마커체 느낌, 한/영)
    "Jua-Regular.ttf": "https://github.com/google/fonts/raw/main/ofl/jua/Jua-Regular.ttf",
    # 영문 Didone 세리프 (원형 링·영문 헤드라인, variable font)
    "PlayfairDisplay.ttf": "https://github.com/google/fonts/raw/main/ofl/playfairdisplay/PlayfairDisplay%5Bwght%5D.ttf",
}


def main() -> None:
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in FONTS.items():
        dest = FONT_DIR / name
        if dest.is_file() and dest.stat().st_size > 10_000:
            print(f"[스킵] {name} (이미 있음)")
            continue
        print(f"[다운로드] {name} ...")
        try:
            urllib.request.urlretrieve(url, dest)
            print(f"  → {dest.stat().st_size // 1024}KB")
        except Exception as e:
            print(f"  [실패] {e}")
            sys.exit(1)
    print(f"완료: {FONT_DIR}")


if __name__ == "__main__":
    main()
