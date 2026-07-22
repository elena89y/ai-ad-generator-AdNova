"""VLM-001 ② — Qwen3-VL 로컬 광고 카피 (완성 광고 이미지 → 어울리는 한국어 문구).

VLM 본연 목적: 완성된 광고 이미지를 '보고' 어울리는 카피를 붙인다. 무-OpenAI.
매니페스트(image 절대경로 + name)의 각 이미지에 vlm_service.generate_copy_local 을 돌려
{headline, subcopy, violations} 를 원장(JSON)+요약(md)으로 남긴다. 카피-이미지 시트는
로컬에서 렌더(폰트·이미지 회수 후).

사용(VM):
  python scripts/vlm001_local_copy.py run --manifest experiments/vlm001_copy_demo.yaml
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BACKEND = Path(__file__).resolve().parents[1]
OUT_JSON = BACKEND / "experiments" / "vlm001_copy_results.json"
SUMMARY = BACKEND / "experiments" / "vlm001_copy_summary.md"


def cmd_run(args: argparse.Namespace) -> None:
    data = yaml.safe_load(Path(args.manifest).expanduser().read_text(encoding="utf-8"))
    from app.services import vlm_service

    results = []
    for it in data["items"]:
        img = Path(it["image"]).expanduser()
        name = it.get("name", "상품")
        if not img.exists():
            print(f"[skip] 이미지 없음: {img}")
            continue
        r = vlm_service.generate_copy_local(str(img), name)
        r["image"] = str(img)
        r["name"] = name
        results.append(r)
        print(f"■ {name}: 「{r['headline']}」 / {r['subcopy']}  (위반 {len(r['violations'])})")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    clean = sum(1 for r in results if not r["violations"])
    lines = ["# VLM-001 ② Qwen3-VL 로컬 광고 카피 (완성 이미지 그라운딩, 무-API)\n",
             f"- 생성 {len(results)}건 · 게이트 통과(위반 0) {clean}/{len(results)}\n",
             "| 제품 | 헤드라인 | 서브카피 | 위반 |", "|---|---|---|---|"]
    for r in results:
        v = ", ".join(r["violations"]) if r["violations"] else "—"
        lines.append(f"| {r['name']} | {r['headline']} | {r['subcopy']} | {v} |")
    SUMMARY.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n→ 원장 {OUT_JSON}\n→ 요약 {SUMMARY}")


def main() -> None:
    ap = argparse.ArgumentParser(description="VLM-001 로컬 광고 카피")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("--manifest", required=True); r.set_defaults(func=cmd_run)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
