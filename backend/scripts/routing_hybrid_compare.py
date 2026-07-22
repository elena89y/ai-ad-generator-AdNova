"""VLM-001 ① 라우팅 하이브리드 — 규칙(키워드) vs VLM vs GPT.

이름→route(object|cafe|dish)는 텍스트 분류 태스크. 한국어 제품명 키워드 규칙이 VLM
(한국어 오역: 꽃등심→flower pot)보다 나은지 골든12로 검증. 규칙은 $0·무-GPU·결정론.
"""
from __future__ import annotations
import sys
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
MANIFEST = Path(__file__).resolve().parents[1] / "experiments" / "hyb001_inputs.yaml"

# 하드굿즈(사물) — 음식과 안 겹치는 명확 키워드만 (크림/로션 등 애매어 제외)
_OBJECT = ["마우스","키보드","컵","머그","텀블러","보틀","세럼","앰플","토너","에센스","선크림",
           "향수","괄사","거울","헤드폰","이어폰","브러시","립스틱","파운데이션","쿠션","패드",
           "케이스","충전기","스탠드","조명","가방","지갑","시계","반지","목걸이","양말","의자"]
# 카페(음료·베이커리·디저트)
_CAFE = ["에이드","라떼","아메리카노","커피","콜드브루","스무디","주스","에스프레소","티","녹차","홍차",
         "스콘","쿠키","케이크","빵","토스트","크로플","크루아상","마카롱","디저트","파이","타르트",
         "와플","젤라토","아이스크림","푸딩","무스","베이글","도넛","브라우니","마들렌","휘낭시에",
         "롤케이크","티라미수","팬케이크","레모네이드","셰이크","프라페","모카","라떼","빙수","젤리"]

def rule_route(name: str) -> str:
    n = (name or "").replace(" ", "")
    if any(k in n for k in _OBJECT):
        return "object"
    if "플레이트" in n or "플래터" in n or "정식" in n or "상차림" in n:
        return "dish"   # 접시/플레이트/정식 = 차려낸 요리
    if any(k in n for k in _CAFE):
        return "cafe"
    return "dish"

def main():
    mf = MANIFEST
    if "--manifest" in sys.argv:
        mf = Path(sys.argv[sys.argv.index("--manifest")+1])
    data = yaml.safe_load(mf.read_text(encoding="utf-8"))
    items = data["items"]
    with_gpt = "--with-gpt" in sys.argv
    gpt = None
    if with_gpt:
        from app.services import gpt_service as gpt
    rok = gok = 0
    rows = []
    for it in items:
        name = it.get("name") or it.get("subject_en"); exp = it.get("expected_mode")
        rr = rule_route(name); rhit = (rr == exp); rok += rhit
        gr = "—"
        if gpt is not None:
            gma = gpt.analyze_menu(name)
            gr = "object" if gma.domain == "object" else ("cafe" if gma.food_mode == "cafe" else "dish")
            gok += (gr == exp)
        rows.append((name, exp, rr, "✓" if rhit else "✗", gr))
    n = len(items)
    print(f"# 라우팅 하이브리드 비교 (골든 {n})")
    print(f"- 규칙(키워드): {rok}/{n} ({100*rok//n}%)  |  VLM-4B(기측정): 10/12 (83%)" + (f"  |  GPT: {gok}/{n} ({100*gok//n}%)" if gpt else ""))
    print("| 이름 | 정답 | 규칙 | 적중 | GPT |"); print("|---|---|---|---|---|")
    for name, exp, rr, hit, gr in rows:
        print(f"| {name} | {exp} | {rr} | {hit} | {gr} |")

if __name__ == "__main__":
    main()
