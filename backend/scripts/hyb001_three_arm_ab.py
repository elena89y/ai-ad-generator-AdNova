"""HYB-001 — 하이브리드 3암 A/B 러너 (DIRECTION_v6 T3, 게이트 G3) — 담당: 한의정.

동일 입력 12장 × {local, api, hybrid} 3암 — 입력·knob·seed 고정, **엔진만 변수**
(클린 단일변수 A/B — Best-of-N 사고 재발 금지). 포스터·문구는 코드 경로(불변)라 비교 제외(poster=False).

  - local  : generation_service.process_ad 기존 A/B/C 자동 라우팅 (GPU 필요 — VM에서)
  - api    : analyze_menu → build_edit_instruction → api_image_service.edit_image
             (CPU만, API_BUDGET_USD 예산가드는 edit_image 내부에서 강제)
  - hybrid : experiments/hyb001_inputs.yaml 의 hybrid_engine 사전 배정
             (정체성 민감=사물 SKU·texture_hero → api / 배경·씬 연출 → local)

모든 실행은 RunLogger(phase="HYB-001")로 원장(runs.jsonl) 1행씩 적재(T0 KPI 자동 파생).
품질축 중 judge/identity 는 본 스크립트가 아니라 기존 도구로 채운다:
  v4_audit_runs.py audit(정체성 DINO/ΔE) · smoke_judge_batch.py(캘리브레이티드 judge).

사용 (backend/ 에서, VM은 ../.venv/bin/python):
  # 로컬 CPU 사전 검증 — 생성 없이 배선·원장·비교표 경로만 (OpenAI 0회, GPU 0회):
  python scripts/hyb001_three_arm_ab.py run --arm all --dry-run \
      --inputs-dir ~/Desktop/AdNova/HYB001_inputs
  python scripts/hyb001_three_arm_ab.py summary --dry-run
  # VM 실측 (게이트 G3 지출 상한: api 암 전체 ≤ $0.5):
  python scripts/hyb001_three_arm_ab.py run --arm local  --inputs-dir ~/HYB001_inputs
  python scripts/hyb001_three_arm_ab.py run --arm api    --inputs-dir ~/HYB001_inputs
  python scripts/hyb001_three_arm_ab.py run --arm hybrid --inputs-dir ~/HYB001_inputs
  python scripts/hyb001_three_arm_ab.py summary          # → experiments/hyb001_summary.md
"""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import statistics
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.harness.run_logger import RunLogger  # noqa: E402

logger = logging.getLogger("hyb001")

BACKEND = Path(__file__).resolve().parents[1]
MANIFEST = BACKEND / "experiments" / "hyb001_inputs.yaml"
RUNS_REAL = BACKEND / "experiments" / "runs.jsonl"
RUNS_DRY = BACKEND / "results" / "ai" / "hyb001_dryrun_runs.jsonl"  # gitignore 영역
SUMMARY_REAL = BACKEND / "experiments" / "hyb001_summary.md"
SUMMARY_DRY = BACKEND / "results" / "ai" / "hyb001_dryrun_summary.md"
OUT_ROOT = BACKEND / "results" / "ai" / "hyb001"

ARMS = ("local", "api", "hybrid")


def _load_manifest() -> dict:
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert len(data["items"]) == 12, "HYB-001 입력은 12장 고정 (G3 프로토콜)"
    return data


def _engine_for(arm: str, item: dict) -> str:
    return item["hybrid_engine"] if arm == "hybrid" else arm


def _run_one_local(image_path: Path, item: dict, knob: float, seed: int,
                   arm: str, out_dir: Path, runs_path: Path, dry: bool) -> None:
    """local 엔진 1건: 기존 process_ad 라우팅 그대로 (단일변수 원칙상 파라미터 손대지 않음)."""
    with RunLogger(phase="HYB-001", mode=item["expected_mode"], engine="local",
                   input=item["file"], seed=seed,
                   params={"arm": arm, "knob": knob, "dry_run": dry},
                   runs_path=runs_path) as run:
        if dry:
            out = out_dir / f"dry_{item['file']}"
            shutil.copy(image_path, out)
            time.sleep(0.05)
            run.set_output(str(out))
            run.set_verdict("dry")
            return
        from app.services import generation_service

        result = generation_service.process_ad(
            str(image_path), item["name"], knob=knob, poster=False,
            output_dir=str(out_dir), seed=seed, _run=run)
        run.set_output(result.final_image_path)


def _run_one_api(image_path: Path, item: dict, knob: float, seed: int,
                 arm: str, out_dir: Path, runs_path: Path, dry: bool) -> None:
    """api 엔진 1건. 실측에선 analyze_menu 결과 subject_en 을 쓰고 매니페스트 라벨과 대조 기록."""
    with RunLogger(phase="HYB-001", mode=item["expected_mode"], engine="api",
                   input=item["file"], seed=seed,
                   params={"arm": arm, "knob": knob, "dry_run": dry},
                   runs_path=runs_path) as run:
        # GPU 호스트에서 API 경로의 유휴 GPU 시간이 비용으로 오계상되면 3암 비교가 왜곡된다
        run.set_meta(gpu_used=False)
        if dry:
            # 지시문 조립까지는 실코드 경로를 태워 배선 검증 (OpenAI 호출 없음)
            from app.services.api_image_service import build_edit_instruction

            instr = build_edit_instruction(
                item["subject_en"], is_object=item["expected_mode"] == "object")
            run.note(f"dry instruction: {instr[:120]}")
            run.add_llm_usage("gpt-5.4-mini", tok_in=300, tok_out=80)   # 표 산식 검증용 모의값
            run.add_image_api_usage("gpt-image-2", n=1)
            out = out_dir / f"dry_{item['file']}"
            shutil.copy(image_path, out)
            run.set_output(str(out))
            run.set_verdict("dry")
            return
        from app.services import gpt_service
        from app.services.api_image_service import build_edit_instruction, edit_image

        analysis = gpt_service.analyze_menu(item["name"])
        subject = analysis.subject_en or item["subject_en"]
        if subject != item["subject_en"]:
            run.note(f"subject_en 상이: manifest={item['subject_en']} / analyze={subject}")
        instr = build_edit_instruction(subject, is_object=analysis.domain == "object")
        out = edit_image(str(image_path), instr, out_dir=str(out_dir), run=run)
        run.set_output(out)


def cmd_run(args: argparse.Namespace) -> None:
    data = _load_manifest()
    knob, seed = float(data["knob"]), int(data["seed"])
    inputs_dir = Path(args.inputs_dir).expanduser()
    runs_path = RUNS_DRY if args.dry_run else RUNS_REAL
    arms = ARMS if args.arm == "all" else (args.arm,)
    if args.dry_run and args.arm == "all" and runs_path.exists():
        runs_path.unlink()  # 드라이런 원장은 매회 새로 (실측 원장은 절대 삭제 금지)

    for arm in arms:
        out_dir = OUT_ROOT / arm
        out_dir.mkdir(parents=True, exist_ok=True)
        for item in data["items"]:
            image_path = inputs_dir / item["file"]
            if not image_path.exists():
                logger.error("입력 없음, 건너뜀: %s", image_path)
                continue
            engine = _engine_for(arm, item)
            fn = _run_one_local if engine == "local" else _run_one_api
            logger.info("[%s] %s → %s", arm, item["file"], engine)
            try:
                fn(image_path, item, knob, seed, arm, out_dir, runs_path, args.dry_run)
            except Exception:  # noqa: BLE001 — 1건 실패가 배치를 죽이면 안 됨(원장에 error 행 남음)
                logger.exception("[%s] %s 실패", arm, item["file"])


def _p50(vals: list[float]) -> float | None:
    return round(statistics.median(vals), 2) if vals else None


def cmd_summary(args: argparse.Namespace) -> None:
    runs_path = RUNS_DRY if args.dry_run else RUNS_REAL
    summary_path = SUMMARY_DRY if args.dry_run else SUMMARY_REAL
    rows: dict[str, list[dict]] = {a: [] for a in ARMS}
    for line in runs_path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("phase") != "HYB-001" or not rec.get("kpi"):
            continue
        arm = rec.get("params", {}).get("arm")
        if arm in rows:
            rows[arm].append(rec)

    lines = ["# HYB-001 — 3암 KPI 비교 (자동 생성: hyb001_three_arm_ab.py summary)", "",
             "| 암 | n | 장당 비용 $ (mean) | p50 시간 s | gate 통과율 | judge (mean) | identity (mean) |",
             "|---|---|---|---|---|---|---|"]
    for arm in ARMS:
        recs = rows[arm]
        kpis = [r["kpi"] for r in recs]
        costs = [k["cost"]["total_usd"] for k in kpis if k["cost"].get("total_usd") is not None]
        times = [k["time"]["total_s"] for k in kpis if k["time"].get("total_s") is not None]
        gates = [k["quality"].get("gate_passed") for k in kpis
                 if k["quality"].get("gate_passed") is not None]
        judges = [k["quality"].get("judge_score") for k in kpis
                  if k["quality"].get("judge_score") is not None]
        idents = [k["quality"].get("identity") for k in kpis
                  if k["quality"].get("identity") is not None]
        lines.append("| {} | {} | {} | {} | {} | {} | {} |".format(
            arm, len(recs),
            round(sum(costs) / len(costs), 4) if costs else "—",
            _p50(times) if times else "—",
            f"{sum(1 for g in gates if g)}/{len(gates)}" if gates else "—",
            round(sum(judges) / len(judges), 2) if judges else "null(별도 judge 배치)",
            round(sum(idents) / len(idents), 3) if idents else "null(v4_audit로 채움)"))
    lines += ["", f"원장: {runs_path}", "판정 규약: 절감률·속도 주장은 이 표 수치로만 (실험로그 v4 HYB-001에 전기)."]
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n→ 저장: {summary_path}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(description="HYB-001 하이브리드 3암 A/B")
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("run", help="1개 암(또는 all) 실행")
    pr.add_argument("--arm", choices=(*ARMS, "all"), required=True)
    pr.add_argument("--inputs-dir", required=True, help="입력 12장 디렉터리")
    pr.add_argument("--dry-run", action="store_true",
                    help="생성·과금 없이 배선/원장/표 검증 (별도 드라이런 원장 사용)")
    pr.set_defaults(fn=cmd_run)
    ps = sub.add_parser("summary", help="3암 KPI 비교표 생성")
    ps.add_argument("--dry-run", action="store_true")
    ps.set_defaults(fn=cmd_summary)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
