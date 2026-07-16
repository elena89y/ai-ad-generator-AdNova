"""v4 P4-2 — 장면 배경 라이브러리 빌더 (오프라인, 유지보수 창 전용) — 담당: 한의정.

⚠️ 반드시 GPU 워커(adnova-generation.service) 정지 상태에서 실행할 것 (결정 D-1):
   SDXL(≈7GB) + 상주 Kontext(≈14GB) 동시 상주 = L4 22GB OOM.
   본 스크립트는 시작 시 free VRAM < 16GB 면 스스로 중단한다.

사용법 (VM, 레포 backend/ 에서):
  # 1) 후보 생성 (플랜 24종 × 소품변형 × 후보 N) + 갤러리
  ../.venv/bin/python scripts/v4_build_scene_library.py build \
      --outdir /opt/adnova/models/scene_library --candidates 4
  # 필터 예: --plans "pop/drink/*" 만 먼저
  # 2) 갤러리(gallery.html)를 보고 채택 파일명을 picks.txt 에 한 줄씩 기록 (사람 큐레이션)
  # 3) 확정 — 매니페스트(sha256·version) 작성
  ../.venv/bin/python scripts/v4_build_scene_library.py finalize \
      --outdir /opt/adnova/models/scene_library --picks picks.txt --curated-by 의정

산출:
  {outdir}/candidates/{plan__props__seed}.png   (후보 전부)
  {outdir}/gallery.html                          (큐레이션용)
  {outdir}/{plan_key.replace('/','_')}__{n}.png  (finalize 후 채택본)
  backend/assets/scene_library_manifest.jsonl    (채택본 sha256·version — 서버 불일치 방지)
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services import scene_plans  # noqa: E402

SDXL_REPO = "stabilityai/stable-diffusion-xl-base-1.0"
SEEDS = [11, 23, 37, 49, 61, 73]
MANIFEST = Path(__file__).resolve().parents[1] / "assets" / "scene_library_manifest.jsonl"


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _guard_vram() -> None:
    import torch
    if not torch.cuda.is_available():
        sys.exit("CUDA 없음 — VM에서 실행할 것")
    free, total = torch.cuda.mem_get_info()
    if free < 16 * (1 << 30):
        sys.exit(f"free VRAM {free/2**30:.1f}GB < 16GB — 워커가 떠있음. "
                 "sudo systemctl stop adnova-generation.service 후 재실행 (결정 D-1)")


def _variants(plan) -> list[tuple]:
    """소품 변형: 항상 무소품 판 + (소품 있으면) 슬롯 전체를 넣은 판 1개."""
    out: list[tuple] = [()]
    if plan.prop_slots:
        out.append(tuple(plan.prop_slots))
    return out


def cmd_build(args) -> None:
    _guard_vram()
    import torch
    from diffusers import StableDiffusionXLPipeline

    outdir = Path(args.outdir); cand_dir = outdir / "candidates"
    cand_dir.mkdir(parents=True, exist_ok=True)

    plans = [p for p in scene_plans.PLANS if fnmatch.fnmatch(p.key, args.plans)]
    if not plans:
        sys.exit(f"플랜 필터 매치 없음: {args.plans}")
    jobs = [(p, v) for p in plans for v in _variants(p)]
    n_img = len(jobs) * args.candidates
    print(f"플랜 {len(plans)} · 프롬프트셋 {len(jobs)} · 이미지 {n_img}장 "
          f"(예상 {n_img * 16 / 60:.0f}분 @16s/장)")

    pipe = StableDiffusionXLPipeline.from_pretrained(
        SDXL_REPO, torch_dtype=torch.float16, use_safetensors=True).to("cuda")

    rows = []
    for i, (plan, props) in enumerate(jobs, 1):
        prompt = scene_plans.build_bg_prompt(plan, props)
        assert len(prompt.split()) <= 60, f"프롬프트 60단어 초과(77토큰 함정): {plan.key}"
        for seed in SEEDS[: args.candidates]:
            name = f"{plan.key.replace('/', '_')}__{'-'.join(props) or 'none'}__s{seed}.png"
            fp = cand_dir / name
            if fp.exists():
                print(f"[{i}/{len(jobs)}] skip {name}"); rows.append((plan, props, name)); continue
            img = pipe(prompt=prompt, negative_prompt=scene_plans.NEGATIVE_PROMPT,
                       num_inference_steps=args.steps, width=1024, height=1024,
                       generator=torch.Generator("cuda").manual_seed(seed)).images[0]
            img.save(fp)
            rows.append((plan, props, name))
            print(f"[{i}/{len(jobs)}] {name}")

    # 갤러리 — 사람 큐레이션용
    cells = "\n".join(
        f'<div class="c"><img src="candidates/{n}"><p>{n}</p></div>'
        for _, _, n in rows)
    (outdir / "gallery.html").write_text(
        '<meta charset="utf-8"><style>body{font-family:sans-serif;background:#111;color:#eee}'
        ".c{display:inline-block;width:31%;margin:1%}.c img{width:100%}p{font-size:11px}</style>"
        f"<h2>scene library candidates — 채택할 파일명을 picks.txt 에 기록</h2>{cells}",
        encoding="utf-8")
    print(f"완료 → {outdir}/gallery.html 를 열어 큐레이션 후 finalize 실행")


def cmd_finalize(args) -> None:
    outdir = Path(args.outdir); cand_dir = outdir / "candidates"
    picks = [l.strip() for l in Path(args.picks).read_text().splitlines()
             if l.strip() and not l.startswith("#")]
    if not picks:
        sys.exit("picks 비어있음")
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    seen: dict[str, int] = {}
    with open(MANIFEST, "w", encoding="utf-8") as mf:
        for name in picks:
            src = cand_dir / name
            if not src.exists():
                sys.exit(f"후보 없음: {name}")
            plan_key = name.split("__")[0].replace("_", "/", 2)
            # key 복원: style_domain_archetype → style/domain/archetype (아키타입 내 '_' 보존)
            parts = name.split("__")[0].split("_")
            for p in scene_plans.PLANS:
                if name.split("__")[0] == p.key.replace("/", "_"):
                    plan_key = p.key; break
            props = [] if "__none__" in name else name.split("__")[1].split("-")
            seen[plan_key] = seen.get(plan_key, 0) + 1
            dst = outdir / f"{plan_key.replace('/', '_')}__{seen[plan_key]}.png"
            shutil.copy(src, dst)
            mf.write(json.dumps({
                "plan": plan_key, "file": dst.name, "sha256": _sha256(dst),
                "version": 1, "props": props, "curated_by": args.curated_by,
            }, ensure_ascii=False) + "\n")
            print(f"채택 {plan_key} ← {name}")
    missing = {p.key for p in scene_plans.PLANS
               if not p.requires_recompose} - set(seen)
    if missing:
        print(f"⚠️ 채택본 없는 플랜(런타임 폴백됨): {sorted(missing)}")
    print(f"매니페스트 → {MANIFEST}")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--outdir", default="/opt/adnova/models/scene_library")
    b.add_argument("--plans", default="*", help='fnmatch 필터, 예 "pop/drink/*"')
    b.add_argument("--candidates", type=int, default=4, choices=range(1, 7))
    b.add_argument("--steps", type=int, default=28)
    b.set_defaults(fn=cmd_build)
    f = sub.add_parser("finalize")
    f.add_argument("--outdir", default="/opt/adnova/models/scene_library")
    f.add_argument("--picks", required=True)
    f.add_argument("--curated-by", default="의정")
    f.set_defaults(fn=cmd_finalize)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
