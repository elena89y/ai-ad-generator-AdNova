"""범용 env-토글 씬 before/after 러너 — dessert(DESSERT_REPLATE)·PAL(PAL_ADAPTIVE) 공용.

REAL-001(finish)은 param 토글이라 real001_finish_ab.py 가 담당. dessert 재플레이팅·PAL
적응형 팔레트는 런타임 env 토글이라 이 러너로 before(off)/after(on)를 같은 입력·시드·스타일로
생성한다. 단일변수: 지정 env 만 off/on, 나머지 고정. style_gen.generate_scene 직접 호출.

원장: RunLogger(phase=--phase) → runs.jsonl (arm=before|after, env_key/env_val 기록).

사용:
  # dessert: 재플레이팅 off/on (editorial, 디저트 입력)
  python scripts/scene_env_ab.py run --phase DESSERT-AB --env-key DESSERT_REPLATE \
      --off 0 --on 1 --style editorial --manifest experiments/dessert_inputs.yaml \
      --inputs-dir ~/Desktop/AdNova/HOLDOUT_inputs
  # PAL: 고정/적응형 (pop, food 입력)
  python scripts/scene_env_ab.py run --phase PAL-AB --env-key PAL_ADAPTIVE \
      --off 0 --on 1 --style pop --manifest experiments/pal_inputs.yaml
  python scripts/scene_env_ab.py summary --phase DESSERT-AB
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.harness.run_logger import RunLogger  # noqa: E402
from app.services.reference_style_plans import normalize_domain  # noqa: E402

logger = logging.getLogger("scene_env_ab")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

BACKEND = Path(__file__).resolve().parents[1]
RUNS_REAL = BACKEND / "experiments" / "runs.jsonl"
RUNS_DRY = BACKEND / "results" / "ai" / "scene_env_dryrun_runs.jsonl"
OUT_ROOT = BACKEND / "results" / "ai" / "scene_env_ab"


def _load_manifest(path: Path) -> dict:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    assert len(data["items"]) >= 1, f"매니페스트 항목 없음: {path}"
    return data


def _run_one(image_path: Path, item: dict, style_key: str, seed: int, env_key: str,
             arm: str, env_val: str, phase: str, out_dir: Path, runs_path: Path, dry: bool) -> None:
    mode = item.get("expected_mode", "dish")
    domain = normalize_domain(mode)
    subject_en = item.get("subject_en") or item.get("name") or "product"
    with RunLogger(phase=phase, mode=mode, engine="local",
                   input=item["file"], seed=seed,
                   params={"arm": arm, "env_key": env_key, "env_val": env_val,
                           "style": style_key, "dry_run": dry},
                   runs_path=runs_path) as run:
        prev = os.environ.get(env_key)
        os.environ[env_key] = env_val
        try:
            if dry:
                run.note(f"[dry] {env_key}={env_val} arm={arm} (신생성=Kontext 필요, VM)")
                out = out_dir / f"dry_{arm}_{item['file']}"
                shutil.copy(image_path, out)
                time.sleep(0.02)
                run.set_output(str(out))
                run.set_verdict("dry")
                return
            from app.services import style_gen
            # arm별 하위폴더 — kontext 출력이 입력 stem으로만 이름지어져 before/after가
            #   같은 파일에 덮어쓰는 충돌 방지(BUGFIX).
            arm_dir = Path(out_dir) / arm
            arm_dir.mkdir(parents=True, exist_ok=True)
            out_path = style_gen.generate_scene(
                str(image_path), style_key, subject_en,
                output_dir=str(arm_dir), seed=seed, domain=domain)
            run.set_output(out_path)
        finally:
            if prev is None:
                os.environ.pop(env_key, None)
            else:
                os.environ[env_key] = prev


def cmd_run(args: argparse.Namespace) -> None:
    data = _load_manifest(Path(args.manifest).expanduser())
    seed = int(data.get("seed", 42))
    items = data["items"][:args.sample] if args.sample else data["items"]
    inputs_dir = Path(args.inputs_dir).expanduser() if args.inputs_dir else None
    runs_path = RUNS_DRY if args.dry_run else RUNS_REAL
    out_dir = OUT_ROOT / args.phase.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    arms = (("before", args.off), ("after", args.on))
    n = 0
    for item in items:
        img = (inputs_dir / item["file"]) if inputs_dir else Path(item["file"])
        if not img.exists():
            logger.warning("입력 없음, 건너뜀: %s", img); continue
        for arm, env_val in arms:
            _run_one(img, item, args.style, seed, args.env_key, arm, str(env_val),
                     args.phase, out_dir, runs_path, args.dry_run)
            n += 1
            logger.info("[%s] %s / %s=%s(%s)", args.phase, item["file"], args.env_key, env_val, arm)
    logger.info("%s %s %d건 (dry=%s)", args.phase, "배선검증" if args.dry_run else "실측", n, args.dry_run)


def cmd_summary(args: argparse.Namespace) -> None:
    runs_path = RUNS_DRY if args.dry_run else RUNS_REAL
    rows = [json.loads(l) for l in runs_path.read_text().splitlines()
            if l.strip() and f'"{args.phase}"' in l]
    pairs: dict = {}
    for r in rows:
        p = r.get("params", {})
        pairs.setdefault(r.get("input"), {})[p.get("arm")] = r.get("output")
    lines = [f"# {args.phase} before/after — 육안 비교 목록\n",
             "| 입력 | before(off) | after(on) |", "|---|---|---|"]
    for inp, a in sorted(pairs.items()):
        lines.append(f"| {inp} | {a.get('before','—')} | {a.get('after','—')} |")
    print("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser(description="범용 env-토글 씬 A/B 러너")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--phase", required=True, help="원장 phase (예: DESSERT-AB, PAL-AB)")
    r.add_argument("--env-key", required=True, help="토글 env 이름 (DESSERT_REPLATE/PAL_ADAPTIVE)")
    r.add_argument("--off", default="0", help="before 값")
    r.add_argument("--on", default="1", help="after 값")
    r.add_argument("--style", default="editorial")
    r.add_argument("--manifest", required=True)
    r.add_argument("--inputs-dir", default=None)
    r.add_argument("--sample", type=int, default=0)
    r.add_argument("--dry-run", action="store_true")
    r.set_defaults(func=cmd_run)
    s = sub.add_parser("summary")
    s.add_argument("--phase", required=True)
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_summary)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
