"""HYB-001 — 하이브리드 3암 A/B 러너 (DIRECTION_v6 T3, 게이트 G3) — 담당: 한의정.

동일 입력 12장 × {local, api, hybrid} 3암 — 입력·knob·seed 고정, **이미지 엔진만 변수**
(클린 단일변수 A/B — Best-of-N 사고 재발 금지). 포스터·문구는 코드 경로(불변)라 비교 제외(poster=False).

**3암 = 서비스 3버전 대응 (발표 서사):**
  ① local  = 로컬 이미지 파이프라인 버전 — process_ad 기존 A/B/C 자동 라우팅 (GPU, VM에서)
  ② api    = 전-LLM 버전 — 이미지 생성까지 전부 API. 지시문 = **enhanced_v2**(APIQ-002 승자):
             6무드 scene_prompt + analyze_photo 파트별 보존등급 + 브랜드·소품 가드.
             CPU만 필요, API_BUDGET_USD 예산가드는 edit_image 내부에서 강제
  ③ hybrid = 상용화 후보 — hyb001_inputs.yaml 의 hybrid_engine 사전 배정
             (정체성 민감=사물 SKU·texture_hero → api / 배경·씬 연출 → local)
  ※ 분석·문구는 3버전 공통으로 GPT(장당 ~$0.002, summary 가 '공통 LLM' 열로 분리 집계).
    문구까지 로컬 모델인 무-OpenAI 버전은 현 코드에 없음(v2 하네스 별도) — 본 실험 범위 외.

모든 실행은 RunLogger(phase="HYB-001")로 원장(runs.jsonl) 1행씩 적재(T0 KPI 자동 파생).
품질축 중 judge/identity 는 본 스크립트가 아니라 기존 도구로 채운다:
  v4_audit_runs.py audit(정체성 DINO/ΔE) · smoke_judge_batch.py(캘리브레이티드 judge).

사용 (backend/ 에서, VM은 ../.venv/bin/python):
  # 로컬 CPU 사전 검증 — 생성 없이 배선·원장·비교표 경로만 (OpenAI 0회, GPU 0회):
  python scripts/hyb001_three_arm_ab.py run --arm all --dry-run \
      --inputs-dir ~/Desktop/AdNova/HYB001_inputs
  python scripts/hyb001_three_arm_ab.py summary --dry-run
  # [선행] APIQ-001 — API 모델×quality 매트릭스(3장×3설정, 보수 추정 ≤$1, CPU 로컬 가능):
  python scripts/hyb001_three_arm_ab.py apiq --inputs-dir ~/Desktop/AdNova/HYB001_inputs
  python scripts/hyb001_three_arm_ab.py summary --apiq
  #   → 육안 승자 확정 후 매니페스트 apiq.chosen 갱신 (HYB-001 api/hybrid 암이 이 설정을 읽음)
  #   [결과 07-21] g2/low 유지, mini 정체성 3/3 실패 탈락, high 는 프리미엄 티어 후보 보관.
  # [선행2] APIQ-002 — 지시문 강화 A/B(draft vs enhanced, 3장×2, ≤$0.15):
  python scripts/hyb001_three_arm_ab.py apiq2 --inputs-dir ~/Desktop/AdNova/HYB001_inputs
  python scripts/hyb001_three_arm_ab.py summary --apiq2
  #   → enhanced 승 시 HYB-001 api 경로를 enhanced 조립으로 승격(별도 커밋) 후 본 실험.
  # VM 실측 (게이트 G3 지출 상한: api 암 전체 ≤ $0.5, high 선택 시 상한 재산정):
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

# 키는 backend/.env 에만 있다(VM) — 호출자 env 의존으로 12행 전멸한 실측 사고(2026-07-20) 재발 방지.
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.harness.run_logger import RunLogger  # noqa: E402

logger = logging.getLogger("hyb001")

BACKEND = Path(__file__).resolve().parents[1]
MANIFEST = BACKEND / "experiments" / "hyb001_inputs.yaml"
RUNS_REAL = BACKEND / "experiments" / "runs.jsonl"
RUNS_DRY = BACKEND / "results" / "ai" / "hyb001_dryrun_runs.jsonl"  # gitignore 영역
SUMMARY_REAL = BACKEND / "experiments" / "hyb001_summary.md"
SUMMARY_DRY = BACKEND / "results" / "ai" / "hyb001_dryrun_summary.md"
SUMMARY_APIQ = BACKEND / "experiments" / "apiq001_summary.md"
SUMMARY_APIQ_DRY = BACKEND / "results" / "ai" / "apiq001_dryrun_summary.md"
SUMMARY_APIQ2 = BACKEND / "experiments" / "apiq002_summary.md"
SUMMARY_APIQ2_DRY = BACKEND / "results" / "ai" / "apiq002_dryrun_summary.md"
OUT_ROOT = BACKEND / "results" / "ai" / "hyb001"

ARMS = ("local", "api", "hybrid")


def _load_manifest() -> dict:
    data = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    assert len(data["items"]) == 12, "HYB-001 입력은 12장 고정 (G3 프로토콜)"
    return data


def _engine_for(arm: str, item: dict) -> str:
    return item["hybrid_engine"] if arm == "hybrid" else arm


def _run_one_local(image_path: Path, item: dict, knob: float, seed: int,
                   arm: str, out_dir: Path, runs_path: Path, dry: bool,
                   model: str = "", quality: str = "", phase: str = "HYB-001") -> None:
    """local 엔진 1건: 기존 process_ad 라우팅 그대로 (단일변수 원칙상 파라미터 손대지 않음).
    model/quality 는 api 엔진 전용 — 시그니처 통일을 위해 받고 무시한다."""
    with RunLogger(phase=phase, mode=item["expected_mode"], engine="local",
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


def _mode_style_hint(mode: str) -> str:
    """모드별 연출 힌트(prompts/api_image.yaml) — local 암의 모드별 경로(A인플레이스/B씬/C스튜디오)에
    대응하는 제품급 연출을 api 암에도 부여한다(②전-LLM 버전 공정성). 키 없으면 기본 힌트."""
    from app.services import prompt_registry

    try:
        return prompt_registry.get("api_image", f"style_hint_{mode}")
    except Exception:  # noqa: BLE001 — 힌트 부재가 실행을 막으면 안 됨
        return ""


def _run_one_api(image_path: Path, item: dict, knob: float, seed: int,
                 arm: str, out_dir: Path, runs_path: Path, dry: bool,
                 model: str = "", quality: str = "", phase: str = "HYB-001") -> None:
    """api 엔진 1건 — 지시문 = enhanced_v2 (APIQ-002 승자, 07-21 승격).

    6무드 scene_prompt(api_style_by_mode 배정) + analyze_photo 파트별 보존등급 + 가드 2종.
    model/quality: 미지정 시 호출부(cmd_run)가 매니페스트 apiq.chosen 을 넣어준다."""
    style_key = (_load_manifest().get("api_style_by_mode") or {}).get(
        item["expected_mode"], "editorial")
    with RunLogger(phase=phase, mode=item["expected_mode"], engine="api",
                   input=item["file"], seed=seed,
                   params={"arm": arm, "knob": knob, "dry_run": dry,
                           "model": model, "quality": quality,
                           "variant": "enhanced_v2", "style": style_key},
                   runs_path=runs_path) as run:
        # GPU 호스트에서 API 경로의 유휴 GPU 시간이 비용으로 오계상되면 3암 비교가 왜곡된다
        run.set_meta(gpu_used=False)
        instr = _build_api_instruction(image_path, item, "enhanced_v2", style_key, dry, run)
        run.note(f"instruction[enhanced_v2/{style_key}]: {instr}")
        if dry:
            # 지시문 조립까지는 실코드 경로를 태워 배선 검증 (OpenAI 호출 없음)
            from app.harness.pricing import image_cost_of
            from app.services.style_specs import get_spec

            frag = get_spec(style_key).scene_prompt.format(subject=item["subject_en"])[:30]
            assert frag in instr, f"scene_prompt 주입 누락: {style_key}"
            assert "styling accessory" in instr and "Final rule" in instr, "v2 가드 누락"
            run.add_llm_usage("gpt-5.4-mini", tok_in=300, tok_out=80)   # 표 산식 검증용 모의값
            run.add_image_api_usage(model, n=1,
                                    cost_usd=image_cost_of(model, quality=quality) or 0.02)
            out = out_dir / f"dry_{item['file']}"
            shutil.copy(image_path, out)
            run.set_output(str(out))
            run.set_verdict("dry")
            return
        from app.services.api_image_service import edit_image

        out = edit_image(str(image_path), instr, out_dir=str(out_dir),
                         model=model, quality=quality, run=run)
        run.set_output(out)


def _chosen_setting(data: dict, args: argparse.Namespace) -> tuple[str, str]:
    """api 엔진 설정 해석: CLI 명시 > 매니페스트 apiq.chosen (APIQ-001 승자 설정)."""
    chosen = (data.get("apiq") or {}).get("chosen") or {}
    model = getattr(args, "model", None) or chosen.get("model", "gpt-image-2")
    quality = getattr(args, "quality", None) or chosen.get("quality", "low")
    return model, quality


def cmd_run(args: argparse.Namespace) -> None:
    data = _load_manifest()
    knob, seed = float(data["knob"]), int(data["seed"])
    inputs_dir = Path(args.inputs_dir).expanduser()
    runs_path = RUNS_DRY if args.dry_run else RUNS_REAL
    arms = ARMS if args.arm == "all" else (args.arm,)
    model, quality = _chosen_setting(data, args)
    if args.dry_run and args.arm == "all" and runs_path.exists():
        runs_path.unlink()  # 드라이런 원장은 매회 새로 (실측 원장은 절대 삭제 금지)

    items = data["items"]
    if getattr(args, "only", None):
        # 부분 재실측(프로토콜 개정분만) — 예: hybrid 암에서 api 배정 5장만 enhanced_v2 재실행.
        # summary 의 last-wins 가 (암, 입력) 최신 행만 집계하므로 원장 정합 유지.
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        items = [i for i in items if i["file"] in wanted]
        missing = wanted - {i["file"] for i in items}
        assert not missing, f"--only 미지 파일: {sorted(missing)} (매니페스트 items 대조)"

    for arm in arms:
        out_dir = OUT_ROOT / arm
        out_dir.mkdir(parents=True, exist_ok=True)
        for item in items:
            image_path = inputs_dir / item["file"]
            if not image_path.exists():
                logger.error("입력 없음, 건너뜀: %s", image_path)
                continue
            engine = _engine_for(arm, item)
            fn = _run_one_local if engine == "local" else _run_one_api
            logger.info("[%s] %s → %s", arm, item["file"], engine)
            try:
                fn(image_path, item, knob, seed, arm, out_dir, runs_path, args.dry_run,
                   model=model, quality=quality)
            except Exception:  # noqa: BLE001 — 1건 실패가 배치를 죽이면 안 됨(원장에 error 행 남음)
                logger.exception("[%s] %s 실패", arm, item["file"])


def cmd_apiq(args: argparse.Namespace) -> None:
    """APIQ-001 — API 모델×quality 매트릭스 미니 실험 (HYB-001 선행).

    모드별 최난이도 3장 × 매니페스트 apiq.matrix 설정. 실측 후 육안(아트디렉터)+judge 로
    승자를 정해 매니페스트 apiq.chosen 을 갱신하면 HYB-001 이 그 설정으로 돈다."""
    data = _load_manifest()
    knob, seed = float(data["knob"]), int(data["seed"])
    inputs_dir = Path(args.inputs_dir).expanduser()
    runs_path = RUNS_DRY if args.dry_run else RUNS_REAL
    apiq = data.get("apiq") or {}
    by_file = {it["file"]: it for it in data["items"]}
    items = [by_file[f] for f in apiq.get("items", []) if f in by_file]
    assert len(items) == 3, "APIQ-001 입력은 모드별 최난이도 3장 (매니페스트 apiq.items 확인)"

    for setting in apiq.get("matrix", []):
        model, quality = setting["model"], setting["quality"]
        out_dir = BACKEND / "results" / "ai" / "apiq001" / f"{model}_{quality}"
        out_dir.mkdir(parents=True, exist_ok=True)
        for item in items:
            image_path = inputs_dir / item["file"]
            if not image_path.exists():
                logger.error("입력 없음, 건너뜀: %s", image_path)
                continue
            logger.info("[apiq %s/%s] %s", model, quality, item["file"])
            try:
                _run_one_api(image_path, item, knob, seed, "apiq", out_dir, runs_path,
                             args.dry_run, model=model, quality=quality, phase="APIQ-001")
            except Exception:  # noqa: BLE001 — 1건 실패가 매트릭스를 죽이면 안 됨
                logger.exception("[apiq %s/%s] %s 실패", model, quality, item["file"])


def _build_api_instruction(image_path: Path, item: dict, variant: str,
                           style_key: str, dry: bool, run) -> str:  # noqa: ANN001
    """API edit 지시문 조립 (APIQ-002 실험 + HYB-001 본실험 공용).

    draft       = APIQ-001 초안(모드별 한 줄 힌트, 이름 기반 subject) — 실험 대조군 보존용.
    enhanced    = 6무드 scene_prompt({subject} 치환, 실측 튜닝 자산) + analyze_photo 파트별
                  보존등급 주입. negative 는 gpt-image edit 에 파라미터가 없어 미적용.
    enhanced_v2 = enhanced + 가드 2종(브랜드·스타일링 소품 보존, 무드발 소품 추가 금지).
                  **APIQ-002 승자(07-21 아트디렉터 확정) — HYB-001 api 암 기본.**
    """
    from app.services.api_image_service import build_edit_instruction

    if variant == "draft":
        return build_edit_instruction(
            item["subject_en"], style_hint=_mode_style_hint(item["expected_mode"]),
            is_object=item["expected_mode"] == "object")

    from app.services.style_specs import get_spec

    spec = get_spec(style_key)
    if dry:
        subject = item["subject_en"]
        identity, flexible = ["(dry) label"], ["(dry) container"]  # fmt 경로 배선 검증용
    else:
        from app.services import gpt_service

        analysis = gpt_service.analyze_photo(str(image_path), item["name"])  # Vision 1회
        subject = (getattr(analysis, "subject_en", "") or item["subject_en"]) if analysis \
            else item["subject_en"]
        identity = list(analysis.identity_parts) if analysis else None
        flexible = list(analysis.flexible_parts) if analysis else None
        if analysis is None:
            run.note("analyze_photo 실패 → 파트 주입 없이 진행(폴백)")
    hint = spec.scene_prompt.format(subject=subject) if spec.scene_prompt else spec.mood
    # 레지스트리 원문은 불변(스냅샷 게이트) — MJ 관용구(--ar 4:5 등 플래그+값)만 gpt-image 전달 전 제거
    import re

    hint = re.sub(r",?\s*--\w+(\s+\S+)?", "", hint).strip().rstrip(",")
    instr = build_edit_instruction(subject, style_hint=hint,
                                   identity_parts=identity, flexible_parts=flexible,
                                   is_object=item["expected_mode"] == "object")
    if variant == "enhanced_v2":
        # APIQ-002 보강 가드: 브랜드·스타일링 소품 보존 + 무드발(發) 소품 추가 금지 최종 규칙
        from app.services import prompt_registry

        instr += " " + prompt_registry.get("api_image", "brand_style_lock")
        instr += " " + prompt_registry.get("api_image", "props_guard_final")
    return instr


def cmd_apiq2(args: argparse.Namespace) -> None:
    """APIQ-002 — 지시문 강화 A/B (draft vs enhanced). 모델·quality 는 chosen 고정.

    APIQ-001 발견("초안 지시문이 병목 의심")의 검증 — 승자 확정 시 HYB-001 api 경로 승격."""
    data = _load_manifest()
    knob, seed = float(data["knob"]), int(data["seed"])
    inputs_dir = Path(args.inputs_dir).expanduser()
    runs_path = RUNS_DRY if args.dry_run else RUNS_REAL
    model, quality = _chosen_setting(data, args)
    apiq2 = data.get("apiq2") or {}
    style_map: dict = apiq2.get("style_map") or {}
    by_file = {it["file"]: it for it in data["items"]}
    items = [by_file[f] for f in (data.get("apiq") or {}).get("items", []) if f in by_file]
    assert len(items) == 3 and set(style_map) == {i["file"] for i in items}, \
        "APIQ-002: apiq.items 3장과 apiq2.style_map 키가 일치해야 함"
    if args.only:  # 부분 재검증(예: 가드 보강 후 에이드만)
        items = [i for i in items if i["file"] == args.only]
        assert items, f"--only {args.only}: apiq.items 에 없음"

    for variant in (args.variants or apiq2.get("variants", ["draft", "enhanced"])):
        out_dir = BACKEND / "results" / "ai" / "apiq002" / variant
        out_dir.mkdir(parents=True, exist_ok=True)
        for item in items:
            image_path = inputs_dir / item["file"]
            if not image_path.exists():
                logger.error("입력 없음, 건너뜀: %s", image_path)
                continue
            style_key = style_map[item["file"]]
            logger.info("[apiq2 %s] %s (style=%s)", variant, item["file"], style_key)
            try:
                with RunLogger(phase="APIQ-002", mode=item["expected_mode"], engine="api",
                               input=item["file"], seed=seed,
                               params={"arm": "apiq2", "variant": variant, "style": style_key,
                                       "model": model, "quality": quality, "knob": knob,
                                       "dry_run": args.dry_run},
                               runs_path=runs_path) as run:
                    run.set_meta(gpu_used=False)
                    instr = _build_api_instruction(image_path, item, variant, style_key,
                                                   args.dry_run, run)
                    run.note(f"instruction[{variant}]: {instr}")
                    if args.dry_run:
                        if variant.startswith("enhanced"):
                            from app.services.style_specs import get_spec
                            frag = get_spec(style_key).scene_prompt.format(
                                subject=item["subject_en"])[:30]
                            assert frag and frag in instr, \
                                f"scene_prompt 주입 누락: {style_key}"
                            assert "(dry) label" in instr, "identity_parts 주입 누락"
                        if variant == "enhanced_v2":
                            assert "styling accessory" in instr and "Final rule" in instr, \
                                "v2 보강 가드 누락 (prompts/api_image.yaml 확인)"
                        from app.harness.pricing import image_cost_of
                        run.add_llm_usage("gpt-5.4-mini", tok_in=300, tok_out=80)
                        run.add_image_api_usage(model, n=1,
                                                cost_usd=image_cost_of(model, quality=quality) or 0.02)
                        out = out_dir / f"dry_{item['file']}"
                        shutil.copy(image_path, out)
                        run.set_output(str(out))
                        run.set_verdict("dry")
                        continue
                    from app.services.api_image_service import edit_image

                    out = edit_image(str(image_path), instr, out_dir=str(out_dir),
                                     model=model, quality=quality, run=run)
                    run.set_output(out)
            except Exception:  # noqa: BLE001 — 1건 실패가 A/B 를 죽이면 안 됨
                logger.exception("[apiq2 %s] %s 실패", variant, item["file"])


def _p50(vals: list[float]) -> float | None:
    return round(statistics.median(vals), 2) if vals else None


def _summary_apiq(runs_path: Path, summary_path: Path) -> None:
    """APIQ-001 매트릭스 요약 — (model, quality) 그룹별 비용·시간. 품질 판정은 육안 정본
    (JDG-002 메타 교훈: 자동지표는 스크리닝용) — 표 옆에 산출 디렉터리를 병기해 육안 대조를 돕는다."""
    groups: dict[tuple[str, str], list[dict]] = {}
    fails: dict[tuple[str, str], int] = {}
    for line in runs_path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("phase") != "APIQ-001" or not rec.get("kpi"):
            continue
        p = rec.get("params", {})
        key = (p.get("model", "?"), p.get("quality", "?"))
        if rec.get("error"):
            fails[key] = fails.get(key, 0) + 1
            continue
        groups.setdefault(key, []).append(rec)

    lines = ["# APIQ-001 — API 모델×quality 매트릭스 (자동 생성)", "",
             "품질 승자 판정은 육안(아트디렉터) 정본 — 산출: results/ai/apiq001/{model}_{quality}/.",
             "승자 확정 후 experiments/hyb001_inputs.yaml 의 apiq.chosen 갱신 → HYB-001 이 그 설정으로 실행.", "",
             "| model | quality | n | 실패 | 장당 비용 $ (mean) | p50 시간 s |",
             "|---|---|---|---|---|---|"]
    for (model, quality), recs in sorted(groups.items()):
        kpis = [r["kpi"] for r in recs]
        costs = [k["cost"]["total_usd"] for k in kpis if k["cost"].get("total_usd") is not None]
        times = [k["time"]["total_s"] for k in kpis if k["time"].get("total_s") is not None]
        lines.append("| {} | {} | {} | {} | {} | {} |".format(
            model, quality, len(recs), fails.get((model, quality), 0),
            round(sum(costs) / len(costs), 4) if costs else "—",
            _p50(times) if times else "—"))
    lines += ["", f"원장: {runs_path}"]
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n→ 저장: {summary_path}")


def _summary_apiq2(runs_path: Path, summary_path: Path) -> None:
    """APIQ-002 요약 — variant(draft|enhanced) 그룹 비용·시간. 품질은 육안 2단계 정본."""
    groups: dict[str, list[dict]] = {}
    fails: dict[str, int] = {}
    for line in runs_path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("phase") != "APIQ-002" or not rec.get("kpi"):
            continue
        variant = rec.get("params", {}).get("variant", "?")
        if rec.get("error"):
            fails[variant] = fails.get(variant, 0) + 1
            continue
        groups.setdefault(variant, []).append(rec)

    lines = ["# APIQ-002 — 지시문 강화 A/B (자동 생성)", "",
             "단일변수 = 지시문(draft=초안 힌트 / enhanced=6무드 scene_prompt+파트별 보존등급).",
             "품질 승자는 육안 2단계 정본 — 산출: results/ai/apiq002/{variant}/. 지시문 전문은 원장 notes.", "",
             "| variant | n | 실패 | 장당 비용 $ (mean) | p50 시간 s |",
             "|---|---|---|---|---|"]
    for variant, recs in sorted(groups.items()):
        kpis = [r["kpi"] for r in recs]
        costs = [k["cost"]["total_usd"] for k in kpis if k["cost"].get("total_usd") is not None]
        times = [k["time"]["total_s"] for k in kpis if k["time"].get("total_s") is not None]
        lines.append("| {} | {} | {} | {} | {} |".format(
            variant, len(recs), fails.get(variant, 0),
            round(sum(costs) / len(costs), 4) if costs else "—",
            _p50(times) if times else "—"))
    lines += ["", f"원장: {runs_path}"]
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n→ 저장: {summary_path}")


def cmd_summary(args: argparse.Namespace) -> None:
    runs_path = RUNS_DRY if args.dry_run else RUNS_REAL
    if getattr(args, "apiq2", False):
        _summary_apiq2(runs_path, SUMMARY_APIQ2_DRY if args.dry_run else SUMMARY_APIQ2)
        return
    if getattr(args, "apiq", False):
        _summary_apiq(runs_path, SUMMARY_APIQ_DRY if args.dry_run else SUMMARY_APIQ)
        return
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

    # 원장은 append-only — 재실측(프로토콜 개정)이 있으면 같은 (암, 입력)의 **최신 행만** 채택.
    #   (2026-07-20: api 암이 .env 사고·모드힌트 개정으로 2회 재실측 → last-wins 필요)
    for arm in ARMS:
        latest: dict[str, dict] = {}
        for rec in rows[arm]:                     # 원장 순서 = 시간 순서
            latest[rec.get("input", "")] = rec
        rows[arm] = list(latest.values())

    # error 행은 KPI 평균에서 제외(0비용·0시간이 평균을 왜곡) — 실패 수는 표에 별도 보고.
    failures = {a: sum(1 for r in rows[a] if r.get("error")) for a in ARMS}
    rows = {a: [r for r in rows[a] if not r.get("error")] for a in ARMS}

    lines = ["# HYB-001 — 3암 KPI 비교 (자동 생성: hyb001_three_arm_ab.py summary)", "",
             "3암 = 서비스 3버전: ①local=로컬 파이프라인 ②api=전-LLM ③hybrid=상용화 후보.",
             "비용은 '이미지 엔진'(GPU환산+이미지API, 버전 간 변수)과 '공통 LLM'(분석·문구, 3버전 동일)을 분리 집계.", "",
             "| 암 | n | 실패 | 이미지 엔진 $/장 | 공통 LLM $/장 | 총 $/장 | p50 시간 s | gate 통과율 | judge (mean) | identity (mean) |",
             "|---|---|---|---|---|---|---|---|---|---|"]

    def _mean(vals: list, nd: int = 4):  # noqa: ANN202
        return round(sum(vals) / len(vals), nd) if vals else "—"

    for arm in ARMS:
        recs = rows[arm]
        kpis = [r["kpi"] for r in recs]
        engine_costs = [(k["cost"].get("gpu_usd_est") or 0) + (k["cost"].get("image_api_usd") or 0)
                        for k in kpis]
        llm_costs = [k["cost"].get("openai_usd") or 0 for k in kpis]
        costs = [k["cost"]["total_usd"] for k in kpis if k["cost"].get("total_usd") is not None]
        times = [k["time"]["total_s"] for k in kpis if k["time"].get("total_s") is not None]
        gates = [k["quality"].get("gate_passed") for k in kpis
                 if k["quality"].get("gate_passed") is not None]
        judges = [k["quality"].get("judge_score") for k in kpis
                  if k["quality"].get("judge_score") is not None]
        idents = [k["quality"].get("identity") for k in kpis
                  if k["quality"].get("identity") is not None]
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            arm, len(recs), failures[arm],
            _mean(engine_costs), _mean(llm_costs), _mean(costs),
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
    pr.add_argument("--model", help="api 엔진 모델 (기본: 매니페스트 apiq.chosen)")
    pr.add_argument("--quality", choices=("low", "medium", "high"),
                    help="api 엔진 quality (기본: 매니페스트 apiq.chosen)")
    pr.add_argument("--only", help="쉼표구분 파일명 — 해당 입력만 부분 재실측 (last-wins 집계)")
    pr.add_argument("--dry-run", action="store_true",
                    help="생성·과금 없이 배선/원장/표 검증 (별도 드라이런 원장 사용)")
    pr.set_defaults(fn=cmd_run)
    pq = sub.add_parser("apiq", help="APIQ-001: API 모델×quality 매트릭스 (3장×3설정, ≤$1)")
    pq.add_argument("--inputs-dir", required=True, help="입력 디렉터리 (HYB001_inputs 재사용)")
    pq.add_argument("--dry-run", action="store_true")
    pq.set_defaults(fn=cmd_apiq)
    p2 = sub.add_parser("apiq2", help="APIQ-002: 지시문 강화 A/B (3장×2변형, g2/low 고정, ≤$0.15)")
    p2.add_argument("--inputs-dir", required=True, help="입력 디렉터리 (HYB001_inputs 재사용)")
    p2.add_argument("--only", help="apiq.items 중 1장만 재검증 (예: drink_ade.png)")
    p2.add_argument("--variants", nargs="+",
                    help="변형 지정 (기본: 매니페스트. 보강 재검증은 enhanced_v2)")
    p2.add_argument("--dry-run", action="store_true")
    p2.set_defaults(fn=cmd_apiq2)
    ps = sub.add_parser("summary", help="KPI 비교표 생성 (기본 HYB-001 3암, --apiq/--apiq2)")
    ps.add_argument("--dry-run", action="store_true")
    ps.add_argument("--apiq", action="store_true", help="APIQ-001 매트릭스 요약")
    ps.add_argument("--apiq2", action="store_true", help="APIQ-002 지시문 A/B 요약")
    ps.set_defaults(fn=cmd_summary)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
