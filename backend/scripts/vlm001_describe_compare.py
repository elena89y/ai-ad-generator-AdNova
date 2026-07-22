"""VLM-001 ② 검증 — 이미지 이해: Qwen describe vs GPT Vision describe (같은 프롬프트).

②"이미지 이해가 VLM의 승리 레인인가"를 실측. 같은 광고 이미지에 Qwen(로컬)과 GPT Vision을
동일 프롬프트로 돌려 묘사를 나란히 저장 → 사람/Claude가 실제 이미지 대조해 사실정확도·환각·
누락 판정(판정≠생성, judge 원칙). GPT Vision = 프로덕션 레퍼런스.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import yaml
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
OUT = Path(__file__).resolve().parents[1] / "experiments" / "vlm001_describe_results.json"
PROMPT = ("이 광고 이미지를 광고 카피라이터를 위해 한국어 1~2문장으로 묘사해라: 주제(제품), "
          "가장 매력적인 시각 특징(색·질감·조명·구성), 무드. 반드시 이미지에 실제로 보이는 것만 쓰고, "
          "보이지 않는 재료·요소는 절대 지어내지 마라.")

def gpt_describe(image_path: str) -> str:
    from app.services import gpt_service
    content = [{"type": "text", "text": PROMPT + ' JSON으로만: {"desc":"..."}'},
               gpt_service._vision_part(image_path)]
    r = gpt_service._chat_json([{"role": "user", "content": content}], label="describe_compare/gpt")
    return str(r.get("desc", "")).strip()

def cmd_run(args):
    data = yaml.safe_load(Path(args.manifest).read_text(encoding="utf-8"))
    from app.services import vlm_service
    recs = []
    for it in data["items"]:
        img = Path(it["image"])
        if not img.exists(): print(f"[skip] {img}"); continue
        q = vlm_service.describe(str(img), prompt=PROMPT)
        g = gpt_describe(str(img))
        recs.append({"name": it["name"], "image": str(img), "qwen": q, "gpt": g})
        print(f"\n■ {it['name']}\n  Qwen: {q}\n  GPT : {g}")
    OUT.write_text(json.dumps(recs, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ {OUT}")

def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("--manifest", required=True); r.set_defaults(func=cmd_run)
    a = ap.parse_args(); a.func(a)

if __name__ == "__main__":
    main()
