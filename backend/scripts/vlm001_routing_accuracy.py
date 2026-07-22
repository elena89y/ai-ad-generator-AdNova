"""VLM-001 ① — Qwen3-VL 로컬 라우팅 정확도 (담당: 한의정).

골든 12장(hyb001_inputs.yaml: name→expected_mode)에 대해 Qwen3-VL 로컬 라우팅
(vlm_service.analyze_menu_local)의 route 예측을 정답과 대조한다. --with-gpt 로 GPT
analyze_menu 베이스라인도 병기(API 소량 호출). Qwen 추론은 GPU(VM) 필요.

route 정의: object → 'object' / food+cafe → 'cafe' / food+dish → 'dish' (= expected_mode).

사용:
  # 로컬 CPU 자가검증(Qwen 없이 배선·매핑만)
  python scripts/vlm001_routing_accuracy.py --self-test
  # VM 실측 (Qwen 라우팅 정확도)
  python scripts/vlm001_routing_accuracy.py run
  python scripts/vlm001_routing_accuracy.py run --with-gpt   # GPT 베이스라인 병기
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BACKEND = Path(__file__).resolve().parents[1]
MANIFEST = BACKEND / "experiments" / "hyb001_inputs.yaml"
SUMMARY = BACKEND / "experiments" / "vlm001_routing_summary.md"


def _route_of(domain: str, food_mode: str) -> str:
    """MenuAnalysis(domain, food_mode) → expected_mode 어휘(object|cafe|dish)."""
    if domain == "object":
        return "object"
    return "cafe" if food_mode == "cafe" else "dish"


def cmd_selftest(_args) -> None:
    """Qwen 없이 로컬 검증: 프롬프트 조립·공용 파서·route 매핑이 도는지."""
    from app.services import gpt_service
    instr = gpt_service.build_menu_instruction("육개장")
    assert "육개장" in instr and "JSON" in instr, "프롬프트 조립 실패"
    # 공용 파서: 자유형 dict → 클램프된 MenuAnalysis
    ma = gpt_service.menu_from_result(
        {"domain": "food", "food_mode": "cafe", "subject_en": "iced latte",
         "category": "weird", "material": "nonsense"}, "아이스라떼")
    assert ma.domain == "food" and ma.food_mode == "cafe", "파서 route 실패"
    assert ma.category == "default", "화이트리스트 클램프 실패(category)"
    assert _route_of(ma.domain, ma.food_mode) == "cafe", "route 매핑 실패"
    assert _route_of("object", "dish") == "object", "object route 실패"
    print("SELF-TEST OK — 프롬프트·파서·클램프·route 매핑 정상 (Qwen 미필요 부분)")


def cmd_run(args: argparse.Namespace) -> None:
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    items = data["items"]
    from app.services import vlm_service
    gpt = None
    if args.with_gpt:
        from app.services import gpt_service as gpt

    rows, q_ok, g_ok, agree = [], 0, 0, 0
    for it in items:
        name = it.get("name") or it.get("subject_en")
        exp = it.get("expected_mode")
        qma = vlm_service.analyze_menu_local(name)
        qroute = _route_of(qma.domain, qma.food_mode)
        qhit = (qroute == exp)
        q_ok += qhit
        groute = "—"
        if gpt is not None:
            gma = gpt.analyze_menu(name)
            groute = _route_of(gma.domain, gma.food_mode)
            g_ok += (groute == exp)
            agree += (groute == qroute)
        rows.append((name, exp, qroute, "✓" if qhit else "✗", groute, qma.subject_en))

    n = len(items)
    lines = ["# VLM-001 ① Qwen3-VL 로컬 라우팅 정확도 (골든 12, expected_mode 대조)\n",
             f"- **Qwen route 정확도: {q_ok}/{n} ({100*q_ok//n}%)**"]
    if gpt is not None:
        lines.append(f"- GPT 베이스라인: {g_ok}/{n} ({100*g_ok//n}%) · Qwen-GPT 일치: {agree}/{n}")
    lines += ["\n| 상품명 | 정답 | Qwen | 적중 | GPT | Qwen subject_en |",
              "|---|---|---|---|---|---|"]
    for name, exp, qr, hit, gr, subj in rows:
        lines.append(f"| {name} | {exp} | {qr} | {hit} | {gr} | {subj} |")
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n→ 저장: {SUMMARY}")


def main() -> None:
    ap = argparse.ArgumentParser(description="VLM-001 라우팅 정확도")
    sub = ap.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("self-test", aliases=["--self-test"]); st.set_defaults(func=cmd_selftest)
    r = sub.add_parser("run"); r.add_argument("--with-gpt", action="store_true"); r.set_defaults(func=cmd_run)
    # --self-test 단독 플래그도 허용
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        sys.argv[1] = "self-test"
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
