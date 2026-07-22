"""VLM-001 ② — Qwen3-VL 로컬 4매체 SNS 카피 vs 무-AI 템플릿 (채택 판단).

완성 광고 이미지를 Qwen 이 직접 보고 매체별(IG/FB/X/Threads) 카피 생성 + 무-AI 규칙
템플릿 베이스라인을 병기해, "VLM이 무-AI 대비 실제로 나은가"를 육안 대조하게 한다.
무-OpenAI. 결과는 JSON 원장 + 비교 md.

사용(VM): python scripts/vlm001_local_copy.py run --manifest experiments/vlm001_copy_demo.yaml
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
_CH = ["instagram", "facebook", "x", "threads"]


def _fmt_block(blk: dict) -> str:
    hs = " ".join(blk.get("hashtags") or [])
    return f"{blk.get('headline','')} / {blk.get('body','')} {hs}".strip()


def cmd_run(args: argparse.Namespace) -> None:
    data = yaml.safe_load(Path(args.manifest).expanduser().read_text(encoding="utf-8"))
    from app.services import vlm_service

    records = []
    for it in data["items"]:
        img = Path(it["image"]).expanduser()
        name = it.get("name", "상품")
        core = it.get("core_ingredients") or []
        if not img.exists():
            print(f"[skip] 이미지 없음: {img}"); continue
        vlm = vlm_service.generate_platform_copy_local(str(img), name, core_ingredients=core)
        base = vlm_service.platform_copy_template(name, core_ingredients=core)
        records.append({"name": name, "image": str(img), "core": core, "vlm": vlm, "baseline": base})
        print(f"\n■ {name}")
        for ch in _CH:
            print(f"  [{ch:9}] VLM : {_fmt_block(vlm.get(ch, {}))}")
            print(f"  [{ch:9}] 무AI: {_fmt_block(base.get(ch, {}))}")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# VLM-001 ② 로컬 4매체 SNS 카피 — VLM(Qwen3-VL) vs 무-AI 템플릿 (무-OpenAI)\n",
             "판정 기준: VLM이 무-AI 대비 **확실히 나아야** AI 채택 가치. 이미지 그라운딩·매체 페르소나 반영도 육안.\n"]
    for r in records:
        lines.append(f"\n## {r['name']}  (core: {', '.join(r['core'])})")
        lines.append("| 매체 | VLM (Qwen, 이미지 관찰) | 무-AI 템플릿 |")
        lines.append("|---|---|---|")
        for ch in _CH:
            lines.append(f"| {ch} | {_fmt_block(r['vlm'].get(ch, {}))} | {_fmt_block(r['baseline'].get(ch, {}))} |")
    SUMMARY.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n→ 원장 {OUT_JSON}\n→ 비교 {SUMMARY}")


def main() -> None:
    ap = argparse.ArgumentParser(description="VLM-001 로컬 4매체 카피 vs 무-AI")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("--manifest", required=True); r.set_defaults(func=cmd_run)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
