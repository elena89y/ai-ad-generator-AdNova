"""item1 C모드 스튜디오 강화 before/after — 담당: 한의정.

C모드 사물 제품컷의 배경/광택 강화(studio 딥톤·헤일로·바닥반사 + gloss 적응형 니)가
매트/다크 사물의 정체성·완성도를 끌어올렸는지 실측한다.

before = 구 파이프라인 저장 출력(local.png, HOLDOUT-001)  ·  after = 신코드 generate_object_ad
판정: DINO 정체성(원본 대비, after≥before 목표 — 특히 헤드폰/텀블러 0.70→↑, 향수 0.81 무붕괴)
      + 육안(구 vs 신, 형태분리·제품감). rembg 누끼는 GPU(VM) 필요 → 실측은 VM.

원장: RunLogger(phase="ITEM1-C") → runs.jsonl (material, dino_after/before/delta).

사용:
  python scripts/item1_cmode_ab.py run --dry-run          # DINO 배선 + before 재현(로컬)
  python scripts/item1_cmode_ab.py run \
      --inputs-dir ~/Desktop/AdNova/HOLDOUT_inputs \
      --before-dir ~/Desktop/AdNova/HOLDOUT001_육안판정_20260721   # VM 실측
  python scripts/item1_cmode_ab.py summary
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.harness.run_logger import RunLogger  # noqa: E402

logger = logging.getLogger("item1c")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")

BACKEND = Path(__file__).resolve().parents[1]
RUNS_REAL = BACKEND / "experiments" / "runs.jsonl"
RUNS_DRY = BACKEND / "results" / "ai" / "item1c_dryrun_runs.jsonl"
SUMMARY = BACKEND / "experiments" / "item1c_summary.md"
SUMMARY_DRY = BACKEND / "results" / "ai" / "item1c_dryrun_summary.md"
OUT_ROOT = BACKEND / "results" / "ai" / "item1c"

# 홀드아웃 C모드 객체: 파일 stem → (material, subject_en). 매트/다크=열세 재질(baseline 0.70).
OBJECTS = {
    "향수": ("transparent", "perfume bottle"),   # baseline DINO 0.810 (승·투명) — 무붕괴 확인용
    "헤드폰": ("matte", "wireless headphones"),   # 0.698 (매트/다크·열세) — 개선 타깃
    "텀블러": ("matte", "water tumbler"),         # 0.697 (매트/흰·열세) — 개선 타깃
}


def _dino(a: str, b: str) -> float | None:
    try:
        from app.harness.metrics import identity_dino
        return round(float(identity_dino(a, b)), 4)
    except Exception as e:  # noqa: BLE001
        logger.warning("DINO 실패(%s): %s", Path(a).name, str(e)[:80])
        return None


def _run_one(stem: str, material: str, subject_en: str, orig: Path,
             before_png: Path | None, out_dir: Path, runs_path: Path, dry: bool) -> None:
    with RunLogger(phase="ITEM1-C", mode="object", engine="local",
                   input=orig.name, seed=0,
                   params={"material": material, "subject_en": subject_en, "arm": "after",
                           "dry_run": dry},
                   runs_path=runs_path) as run:
        before_dino = _dino(str(before_png), str(orig)) if before_png and before_png.exists() else None
        if dry:
            # GPU 없이: before(구 출력) DINO 재현으로 배선·baseline 검증. 신생성 스킵.
            run.note(f"[dry] material={material} before_dino={before_dino} (신생성=rembg 필요, VM)")
            run.set_output(str(before_png) if before_png else "")
            run.set_verdict("dry")
            run.set_meta(dino_before=before_dino)
            return
        from app.services.object_service import generate_object_ad

        res = generate_object_ad(str(orig), material=material, output_dir=str(out_dir))
        after_dino = _dino(res.output_path, str(orig))
        delta = (round(after_dino - before_dino, 4)
                 if (after_dino is not None and before_dino is not None) else None)
        run.set_output(res.output_path)
        run.set_meta(dino_after=after_dino, dino_before=before_dino, dino_delta=delta,
                     seconds=res.seconds)
        logger.info("[ITEM1-C] %s(%s): before=%s after=%s Δ=%s",
                    stem, material, before_dino, after_dino, delta)


def cmd_run(args: argparse.Namespace) -> None:
    inputs_dir = Path(args.inputs_dir).expanduser() if args.inputs_dir else \
        Path("~/Desktop/AdNova/HOLDOUT_inputs").expanduser()
    before_dir = Path(args.before_dir).expanduser() if args.before_dir else None
    runs_path = RUNS_DRY if args.dry_run else RUNS_REAL
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    n = 0
    for stem, (material, subject_en) in OBJECTS.items():
        orig = inputs_dir / f"{stem}.jpg"
        if not orig.exists():
            logger.warning("원본 없음, 건너뜀: %s", orig); continue
        before_png = (before_dir / stem / "local.png") if before_dir else None
        _run_one(stem, material, subject_en, orig, before_png, OUT_ROOT, runs_path, args.dry_run)
        n += 1
    logger.info("ITEM1-C %s %d건 (dry=%s)", "배선검증" if args.dry_run else "실측", n, args.dry_run)


def cmd_summary(args: argparse.Namespace) -> None:
    runs_path = RUNS_DRY if args.dry_run else RUNS_REAL
    summary = SUMMARY_DRY if args.dry_run else SUMMARY
    rows = [json.loads(l) for l in runs_path.read_text().splitlines()
            if l.strip() and '"ITEM1-C"' in l]
    latest: dict[str, dict] = {}
    for r in rows:
        latest[r.get("input")] = r  # last-wins
    lines = ["# item1 C모드 studio 강화 before/after (DINO 정체성, 원본 대비)\n",
             "| 객체 | 재질 | before(구) | after(신) | Δ |",
             "|---|---|---|---|---|"]
    for inp, r in sorted(latest.items()):
        # set_meta 는 레코드 최상위에 평탄화 저장 → 중첩 아님, r 에서 직접 읽는다.
        p = r.get("params", {})
        lines.append(f"| {inp} | {p.get('material','')} | {r.get('dino_before','—')} "
                     f"| {r.get('dino_after','—')} | {r.get('dino_delta','—')} |")
    lines.append("\n판정: 매트/다크(헤드폰·텀블러) Δ>0 = 강화 성공, 향수 무붕괴. 미감 최종=육안(구 local.png vs 신).")
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines)); print(f"\n→ 저장: {summary}")


def main() -> None:
    ap = argparse.ArgumentParser(description="item1 C모드 studio 강화 A/B 러너")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--inputs-dir", default=None)
    r.add_argument("--before-dir", default=None, help="구 출력(local.png) 폴더 — before DINO용")
    r.add_argument("--dry-run", action="store_true")
    r.set_defaults(func=cmd_run)
    s = sub.add_parser("summary")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_summary)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
