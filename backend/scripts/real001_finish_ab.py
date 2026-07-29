"""REAL-001 finish A/B — 사진적 사실감 finish_profile 절의 효과 실측 (담당: 한의정).

대조(finish=none) vs 처리(finish=photographic)를 **같은 입력·스타일·시드**로 생성한다.
단일변수 원칙: finish_profile 만 토글하고 나머지는 고정. style_gen.generate_scene 를 직접
호출해 Best-of-N·process_ad 라우팅 노이즈를 배제(controlled A/B).

판정(육안판정 프로토콜):
  - 정본 = 아트디렉터 육안, REAL001_rubric_anchors_9.jpg(픽바이트 9앵커) 대비 어느 쪽이 더
    사진적 사실감(자연광·재질·절제색·그라운딩)에 근접한가.
  - 보조 = VLM realism 차원(advisory), DINO 정체성 무붕괴 확인(finish가 형태·색 안 깨야).

원장: RunLogger(phase="REAL-001") → runs.jsonl 1행/생성 (arm=control|treat, finish_profile 기록).

사용:
  # 로컬 CPU 배선검증 (GPU 없이 finish 절 주입 유무만 확인)
  python scripts/real001_finish_ab.py run --dry-run
  # VM 실측 (kontext=GPU)
  python scripts/real001_finish_ab.py run --inputs-dir ~/Desktop/AdNova/HOLDOUT_inputs \
      --manifest experiments/holdout001_inputs.yaml --styles realism
  python scripts/real001_finish_ab.py summary
"""
from __future__ import annotations

import argparse
import logging
import shutil
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.harness.run_logger import RunLogger  # noqa: E402
from app.services.reference_style_plans import (  # noqa: E402
    build_reference_instruction, normalize_domain)

logger = logging.getLogger("real001")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

BACKEND = Path(__file__).resolve().parents[1]
MANIFEST = BACKEND / "experiments" / "hyb001_inputs.yaml"
RUNS_REAL = BACKEND / "experiments" / "runs.jsonl"
RUNS_DRY = BACKEND / "results" / "ai" / "real001_dryrun_runs.jsonl"
SUMMARY = BACKEND / "experiments" / "real001_summary.md"
SUMMARY_DRY = BACKEND / "results" / "ai" / "real001_dryrun_summary.md"
OUT_ROOT = BACKEND / "results" / "ai" / "real001"

# finish A/B 두 팔 — 대조(무주입=현행)와 처리(리얼리즘 절 주입). 같은 시드로 짝.
ARMS = (("control", "none"), ("treat", "photographic"))
# 모드→도메인 매핑은 normalize_domain 이 처리(dish→food, cafe→drink). style 은 CLI/기본.
DEFAULT_STYLE = "realism"  # REAL-001 = 사진적 사실감 → realism 무드에서 우선 검증


def _load_manifest(path: Path) -> dict:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    assert len(data["items"]) >= 3, f"매니페스트 항목 부족(<3): {path}"
    return data


def _run_one(image_path: Path, item: dict, style_key: str, seed: int,
             arm: str, finish: str, out_dir: Path, runs_path: Path, dry: bool) -> None:
    """finish A/B 1건: generate_scene 직접 호출(단일변수). dry면 배선만 검증(GPU 없음)."""
    mode = item.get("expected_mode", "dish")
    domain = normalize_domain(mode)
    subject_en = item.get("subject_en") or item.get("name") or "product"
    with RunLogger(phase="REAL-001", mode=mode, engine="local",
                   input=item["file"], seed=seed,
                   params={"arm": arm, "finish_profile": finish, "style": style_key,
                           "dry_run": dry},
                   runs_path=runs_path) as run:
        if dry:
            # GPU 없이 배선 검증: 지시문에 finish 절이 처리군에만 주입되는지 단언.
            instr = build_reference_instruction(style_key, domain, subject_en,
                                                finish_profile=finish)
            has_clause = bool(instr) and "photographic realism" in instr
            expect = (finish == "photographic")
            assert has_clause == expect, (
                f"finish 배선 오류: arm={arm} finish={finish} "
                f"clause={has_clause} expect={expect} (instr={'None' if not instr else 'ok'})")
            run.note(f"[dry] finish={finish} clause_injected={has_clause} instr_ok={bool(instr)}")
            out = out_dir / f"dry_{arm}_{item['file']}"
            shutil.copy(image_path, out)
            time.sleep(0.02)
            run.set_output(str(out))
            run.set_verdict("dry")
            return
        from app.services import style_gen

        # arm별 하위폴더 — kontext 출력이 입력 stem으로만 이름지어져 control/treat이
        #   같은 파일에 덮어쓰는 충돌 방지(BUGFIX: 첫 배치서 before/after 동일파일화).
        arm_dir = Path(out_dir) / arm
        arm_dir.mkdir(parents=True, exist_ok=True)
        out_path = style_gen.generate_scene(
            str(image_path), style_key, subject_en,
            output_dir=str(arm_dir), seed=seed, domain=domain,
            finish_profile=finish)
        run.set_output(out_path)


def cmd_run(args: argparse.Namespace) -> None:
    manifest_path = Path(getattr(args, "manifest", None) or MANIFEST).expanduser()
    data = _load_manifest(manifest_path)
    seed = int(data.get("seed", 42))
    items = data["items"]
    if args.sample:
        items = items[:args.sample]
    styles = [s.strip() for s in (args.styles or DEFAULT_STYLE).split(",") if s.strip()]
    inputs_dir = Path(args.inputs_dir).expanduser() if args.inputs_dir else None
    runs_path = RUNS_DRY if args.dry_run else RUNS_REAL
    out_base = OUT_ROOT
    out_base.mkdir(parents=True, exist_ok=True)

    n = 0
    for item in items:
        img = (inputs_dir / item["file"]) if inputs_dir else Path(item["file"])
        if not img.exists():
            logger.warning("입력 없음, 건너뜀: %s", img)
            continue
        for style_key in styles:
            out_dir = out_base / style_key
            out_dir.mkdir(parents=True, exist_ok=True)
            for arm, finish in ARMS:
                _run_one(img, item, style_key, seed, arm, finish, out_dir, runs_path, args.dry_run)
                n += 1
                logger.info("[REAL-001] %s / %s / %s(finish=%s) 완료", item["file"], style_key, arm, finish)
    logger.info("REAL-001 %s 생성 %d건 (styles=%s, dry=%s)", "배선검증" if args.dry_run else "실측",
                n, styles, args.dry_run)


def cmd_summary(args: argparse.Namespace) -> None:
    """control/treat 짝을 입력·스타일별로 묶어 육안 비교 목록 출력."""
    runs_path = RUNS_DRY if args.dry_run else RUNS_REAL
    summary = SUMMARY_DRY if args.dry_run else SUMMARY
    import json
    rows = [json.loads(l) for l in runs_path.read_text().splitlines()
            if l.strip() and '"REAL-001"' in l]
    # 입력+스타일 키로 last-wins, arm별 최신 output
    pairs: dict[tuple, dict] = {}
    for r in rows:
        p = r.get("params", {})
        key = (r.get("input"), p.get("style"))
        pairs.setdefault(key, {})[p.get("arm")] = r.get("output")
    lines = ["# REAL-001 finish A/B — 육안 비교 목록 (정본: REAL001_rubric_anchors_9.jpg)\n",
             "| 입력 | 스타일 | control(finish=none) | treat(finish=photographic) |",
             "|---|---|---|---|"]
    for (inp, style), arms in sorted(pairs.items(), key=lambda x: (x[0][0] or "", x[0][1] or "")):
        lines.append(f"| {inp} | {style} | {arms.get('control','—')} | {arms.get('treat','—')} |")
    lines.append(f"\n판정: 9앵커 대비 어느 쪽이 자연광·재질·절제색·그라운딩에 근접한가(육안 정본).")
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n→ 저장: {summary}")


def main() -> None:
    ap = argparse.ArgumentParser(description="REAL-001 finish A/B 러너")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="control/treat 생성")
    r.add_argument("--inputs-dir", default=None, help="입력 이미지 폴더(매니페스트 file 기준)")
    r.add_argument("--manifest", default=None, help="입력 매니페스트 yaml(기본 hyb001_inputs)")
    r.add_argument("--styles", default=None, help="쉼표구분 스타일(기본 realism)")
    r.add_argument("--sample", type=int, default=0, help="앞 N개만(스모크)")
    r.add_argument("--dry-run", action="store_true", help="GPU 없이 배선만 검증")
    r.set_defaults(func=cmd_run)
    s = sub.add_parser("summary", help="control/treat 짝 육안 목록")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_summary)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
