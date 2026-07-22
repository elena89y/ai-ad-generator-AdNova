"""VLM-001 실측 비교 — 실제 프로덕션 GPT 카피 vs 로컬 VLM(4B) 4매체 카피.

hej4016 계정 광고(완성 이미지 + DB의 GPT generated_text)에 로컬 VLM 카피를 돌려, 사람이
만든(GPT) 카피와 온프레미스 VLM 카피를 같은 이미지에서 대조한다. 무-OpenAI(VLM측).
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
BACKEND = Path(__file__).resolve().parents[1]
OUT = BACKEND / "experiments" / "vlm001_vsgpt_results.json"

def cmd_run(args):
    data = yaml.safe_load(Path(args.manifest).read_text(encoding="utf-8"))
    from app.services import vlm_service
    recs = []
    for it in data["items"]:
        img = Path(it["image"])
        if not img.exists():
            print(f"[skip] {img} 없음"); continue
        vlm = vlm_service.generate_platform_copy_local(str(img), it["name"], core_ingredients=it.get("core_ingredients") or [])
        rec = {"name": it["name"], "image": str(img), "gpt_copy": it.get("gpt_copy",""), "baked": it.get("baked", False), "vlm": vlm}
        recs.append(rec)
        print(f"\n■ {it['name']} (baked={it.get('baked')})")
        print(f"  GPT : {it.get('gpt_copy')}")
        for ch in ["instagram","facebook","x","threads"]:
            b = vlm.get(ch, {}); print(f"  VLM[{ch}]: {b.get('headline','')} / {b.get('body','')[:50]}")
    OUT.write_text(json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ {OUT}")

def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("--manifest", required=True); r.set_defaults(func=cmd_run)
    a = ap.parse_args(); a.func(a)

if __name__ == "__main__":
    main()
