"""기존 라떼 실험 결과 5장으로 멀티컷 상세페이지 구조를 검증한다."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.schemas.ads import AdPurpose
from app.services.pipeline_v5 import generate_v5
from app.services.pipeline_v5.hero import DetailCut, DetailCutRole, hero_from_existing

paths = [
    "/Users/colourxswitch/Desktop/AdNova/PU005_same_domain_reference_ab_20260719/latte_a_text_only.png",
    "/Users/colourxswitch/Desktop/AdNova/abjudge/카페라떼_seed42.png",
    "/Users/colourxswitch/Desktop/AdNova/abjudge/카페라떼_seed7.png",
    "/Users/colourxswitch/Desktop/AdNova/abjudge/카페라떼_seed123.png",
    "/Users/colourxswitch/Desktop/AdNova/abjudge/카페라떼_seed2024.png",
]
root = Path(__file__).resolve().parents[2] / "backend" / "results" / "ai" / "detail_page_gate_v2"
root.mkdir(parents=True, exist_ok=True)
hero = hero_from_existing(
    paths[0], headline="오늘의 시그니처 라떼", subcopy="부드러운 한 잔의 균형",
    domain="cafe",
    detail_cuts=tuple(DetailCut(path, role) for path, role in zip(paths, DetailCutRole)),
)
result = generate_v5(paths[0], "latte", purpose=AdPurpose.DETAIL_PAGE, hero_asset=hero, output_dir=str(root))
print(result.outputs[0])
