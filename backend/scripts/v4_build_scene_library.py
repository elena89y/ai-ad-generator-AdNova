"""v4 P4-2 — 장면 배경 라이브러리 빌더 (오프라인, 유지보수 창 전용) — 담당: 한의정.

⚠️ 반드시 GPU 워커(adnova-generation.service) 정지 상태에서 실행할 것 (결정 D-1):
   SDXL(≈7GB) + 상주 Kontext(≈14GB) 동시 상주 = L4 22GB OOM.
   본 스크립트는 시작 시 free VRAM < 16GB 면 스스로 중단한다.

사용법 (VM, 레포 backend/ 에서):
  # P4B 파일럿 24장(2스타일 × 2도메인 × 2아키타입 × 시드3, 소품 없음)
  ../.venv/bin/python scripts/v4_build_scene_library.py build --pilot \
      --outdir /opt/adnova/models/scene_library
  # 1) 후보 생성 (플랜 24종 × 소품변형 × 후보 N) + 갤러리
  ../.venv/bin/python scripts/v4_build_scene_library.py build \
      --outdir /opt/adnova/models/scene_library --candidates 4
  # 필터 예: --plans "pop/drink/*" 만 먼저
  # 2) 갤러리(gallery.html)를 보고 채택 파일명을 picks.txt 에 한 줄씩 기록 (사람 큐레이션)
  #    한 줄 형식: "파일명.png" 또는 "파일명.png surface_y=0.73" (Tier2/sdxl 판은 실측 필수)
  # 3) 확정 — 매니페스트(sha256·version·surface_y 오버라이드) 작성
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
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services import scene_plans  # noqa: E402

SDXL_REPO = "stabilityai/stable-diffusion-xl-base-1.0"
SDXL_REQUIRED_FILES = (
    "model_index.json",
    "scheduler/scheduler_config.json",
    "text_encoder/config.json",
    "text_encoder/model.fp16.safetensors",
    "text_encoder_2/config.json",
    "text_encoder_2/model.fp16.safetensors",
    "tokenizer/merges.txt",
    "tokenizer/special_tokens_map.json",
    "tokenizer/tokenizer_config.json",
    "tokenizer/vocab.json",
    "tokenizer_2/merges.txt",
    "tokenizer_2/special_tokens_map.json",
    "tokenizer_2/tokenizer_config.json",
    "tokenizer_2/vocab.json",
    "unet/config.json",
    "unet/diffusion_pytorch_model.fp16.safetensors",
    "vae/config.json",
    "vae/diffusion_pytorch_model.fp16.safetensors",
)
SEEDS = [11, 23, 37, 49, 61, 73]
PILOT_STYLES = ("pop", "warm_vintage")
PILOT_DOMAINS = ("drink", "object")
PILOT_SEEDS = (11, 23, 37)
PILOT_PLAN_KEYS = (
    "pop/drink/diagonal_splash",
    "pop/drink/color_block_duo",
    "pop/object/color_block",
    "pop/object/concept_stage",
    "warm_vintage/drink/linen_organic",
    "warm_vintage/drink/wood_morning",
    "warm_vintage/object/linen_organic",
    "warm_vintage/object/craft_paper",
)
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


def _resolve_local_sdxl_snapshot() -> Path:
    """허브의 전체 저장소 검사를 피하고 실행에 필요한 FP16 스냅샷만 검증한다."""
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    hub_cache = Path(os.environ.get("HF_HUB_CACHE", hf_home / "hub"))
    repo_cache = hub_cache / f"models--{SDXL_REPO.replace('/', '--')}"
    main_ref = repo_cache / "refs" / "main"
    if not main_ref.is_file():
        raise FileNotFoundError(f"SDXL main ref 없음: {main_ref}")

    revision = main_ref.read_text(encoding="utf-8").strip()
    if not revision:
        raise FileNotFoundError(f"SDXL main ref가 비어 있음: {main_ref}")
    snapshot = repo_cache / "snapshots" / revision
    missing = [name for name in SDXL_REQUIRED_FILES if not (snapshot / name).is_file()]
    if missing:
        preview = ", ".join(missing[:5])
        suffix = f" 외 {len(missing) - 5}개" if len(missing) > 5 else ""
        raise FileNotFoundError(f"SDXL FP16 필수 파일 누락: {preview}{suffix}")
    return snapshot


def _load_sdxl_pipeline(torch_module):  # noqa: ANN001, ANN202
    """공용 캐시의 FP16 가중치만 선택해 FP32 모델의 추가 다운로드·메모리 사용을 막는다."""
    from diffusers import StableDiffusionXLPipeline

    snapshot = _resolve_local_sdxl_snapshot()
    return StableDiffusionXLPipeline.from_pretrained(
        str(snapshot),
        torch_dtype=torch_module.float16,
        use_safetensors=True,
        variant="fp16",
        local_files_only=True,
    ).to("cuda")


def _variants(plan) -> list[tuple]:
    """소품 변형: 항상 무소품 판 + (소품 있으면) 슬롯 전체를 넣은 판 1개."""
    out: list[tuple] = [()]
    if plan.prop_slots:
        out.append(tuple(plan.prop_slots))
    return out


def _build_jobs(plans_pattern: str, candidates: int,
                pilot: bool = False) -> tuple[list[tuple], tuple[int, ...]]:
    """빌드 작업 계약. 파일럿은 P4B의 24장 구성을 옵션과 무관하게 고정한다."""
    if pilot:
        by_key = {p.key: p for p in scene_plans.PLANS}
        missing = [key for key in PILOT_PLAN_KEYS if key not in by_key]
        if missing:
            raise ValueError(f"P4B 파일럿 플랜 누락: {missing}")
        plans = [by_key[key] for key in PILOT_PLAN_KEYS]
        return [(p, ()) for p in plans], PILOT_SEEDS

    plans = [p for p in scene_plans.PLANS if fnmatch.fnmatch(p.key, plans_pattern)]
    if not plans:
        raise ValueError(f"플랜 필터 매치 없음: {plans_pattern}")
    return [(p, v) for p in plans for v in _variants(p)], tuple(SEEDS[:candidates])


def _generate_with_retry(render):
    """이미지 1장을 생성하고 실패하면 정확히 한 번 더 시도한다."""
    last_error = None
    for retry_count in range(2):
        try:
            return render(), retry_count, None
        except Exception as exc:  # 생성기 예외는 장별로 격리해 전체 빌드를 계속한다.
            last_error = exc
    return None, 1, str(last_error)


def _candidate_name(plan, props: tuple, seed: int) -> str:  # noqa: ANN001
    return f"{plan.key.replace('/', '_')}__{'-'.join(props) or 'none'}__s{seed}.png"


def _existing_pilot_candidates(cand_dir: Path, jobs: list[tuple],
                               seeds: tuple[int, ...]) -> list[str]:
    """파일럿 측정 오염을 막기 위해 같은 계약의 기존 후보를 찾는다."""
    existing = []
    for plan, props in jobs:
        for seed in seeds:
            name = _candidate_name(plan, props, seed)
            if (cand_dir / name).is_file():
                existing.append(name)
    return existing


def _plan_key_from_candidate(name: str) -> str:
    """후보 파일명의 접두사를 등록된 plan key와 정확히 대조한다."""
    prefix = name.split("__", 1)[0]
    for plan in scene_plans.PLANS:
        if prefix == plan.key.replace("/", "_"):
            return plan.key
    raise ValueError(f"등록되지 않은 plan key 접두사: {prefix}")


def _load_manifest_entries() -> list[dict]:
    """기존 매니페스트를 읽는다. 손상 파일은 덮어쓰지 않고 finalize를 중단한다."""
    if not MANIFEST.is_file():
        return []
    entries = []
    for line_no, line in enumerate(MANIFEST.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"매니페스트 JSON 손상({line_no}행): {exc}") from exc
        if not isinstance(entry, dict) or not all(key in entry for key in ("plan", "file", "sha256")):
            raise ValueError(f"매니페스트 항목 형식 오류({line_no}행)")
        entries.append(entry)
    return entries


def _manifest_plan_indices(entries: list[dict]) -> dict[str, int]:
    """기존 확정 파일의 plan별 최대 연번을 복원한다."""
    indices: dict[str, int] = {}
    for entry in entries:
        plan_key = str(entry["plan"])
        prefix = f"{plan_key.replace('/', '_')}__"
        filename = str(entry["file"])
        suffix = filename.removeprefix(prefix).removesuffix(".png")
        if filename.startswith(prefix) and suffix.isdigit():
            indices[plan_key] = max(indices.get(plan_key, 0), int(suffix))
    return indices


def _write_manifest_entries(entries: list[dict]) -> None:
    """병합된 매니페스트를 원자 교체한다."""
    pending = MANIFEST.with_suffix(".jsonl.tmp")
    pending.write_text(
        "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in entries),
        encoding="utf-8",
    )
    pending.replace(MANIFEST)


def _write_timing_report(outdir: Path, pilot: bool, load_s: float,
                         image_timings: list[dict], expected_images: int,
                         generated: int, skipped: int, retries: int,
                         failures: list[dict]) -> Path:
    image_times = [item["elapsed_s"] for item in image_timings]
    per_image = {
        "count": len(image_times),
        "mean_s": round(sum(image_times) / len(image_times), 3) if image_times else None,
        "min_s": round(min(image_times), 3) if image_times else None,
        "max_s": round(max(image_times), 3) if image_times else None,
    }
    report = {
        "mode": "pilot" if pilot else "build",
        "contract": {
            "styles": list(PILOT_STYLES),
            "domains": list(PILOT_DOMAINS),
            "archetypes_per_style_domain": 2,
            "seeds": list(PILOT_SEEDS),
            "props": [],
        } if pilot else None,
        "expected_images": expected_images,
        "generated": generated,
        "skipped": skipped,
        "failed": len(failures),
        "retries": retries,
        "load_s": round(load_s, 3),
        "per_image": per_image,
        "images": image_timings,
        "failures": failures,
    }
    report_path = outdir / ("pilot_timing.json" if pilot else "build_timing.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"시간 리포트: load={report['load_s']}s · "
        f"image_mean={per_image['mean_s']}s · generated={generated} · "
        f"skipped={skipped} · retries={retries} · failed={len(failures)}"
    )
    print(f"JSON → {report_path}")
    return report_path


def cmd_build(args) -> None:
    _guard_vram()

    outdir = Path(args.outdir)
    cand_dir = outdir / "candidates"
    cand_dir.mkdir(parents=True, exist_ok=True)

    try:
        jobs, seeds = _build_jobs(args.plans, args.candidates, args.pilot)
    except ValueError as exc:
        sys.exit(str(exc))
    plan_count = len({p.key for p, _ in jobs})
    n_img = len(jobs) * len(seeds)
    if args.pilot:
        existing = _existing_pilot_candidates(cand_dir, jobs, seeds)
        if existing:
            sys.exit(
                f"P4B 파일럿 기존 후보 {len(existing)}장 발견 — 타이밍·프롬프트 검증 오염 방지를 "
                "위해 비어 있는 새 --outdir를 사용하세요"
            )
    mode = "P4B pilot" if args.pilot else "full build"
    print(f"[{mode}] 플랜 {plan_count} · 프롬프트셋 {len(jobs)} · 이미지 {n_img}장 "
          f"(예상 {n_img * 16 / 60:.0f}분 @16s/장)")

    import torch

    load_started = time.perf_counter()
    pipe = _load_sdxl_pipeline(torch)
    load_s = time.perf_counter() - load_started

    rows = []
    image_timings: list[dict] = []
    failures: list[dict] = []
    generated = 0
    skipped = 0
    retries = 0
    for i, (plan, props) in enumerate(jobs, 1):
        prompt = scene_plans.build_bg_prompt(plan, props)
        assert len(prompt.split()) <= 60, f"프롬프트 60단어 초과(77토큰 함정): {plan.key}"
        for seed in seeds:
            name = _candidate_name(plan, props, seed)
            fp = cand_dir / name
            if fp.exists():
                skipped += 1
                print(f"[{i}/{len(jobs)}] skip {name}")
                rows.append((plan, props, name))
                continue

            def render():
                generator = torch.Generator("cuda").manual_seed(seed)
                return pipe(
                    prompt=prompt, negative_prompt=scene_plans.NEGATIVE_PROMPT,
                    num_inference_steps=args.steps, width=1024, height=1024,
                    generator=generator,
                ).images[0]

            image_started = time.perf_counter()
            img, retry_count, error = _generate_with_retry(render)
            elapsed = time.perf_counter() - image_started
            retries += retry_count
            if error:
                failures.append({"file": name, "error": error, "elapsed_s": round(elapsed, 3)})
                print(f"[{i}/{len(jobs)}] failed after retry {name}: {error}")
                continue
            img.save(fp)
            generated += 1
            image_timings.append({
                "file": name,
                "elapsed_s": round(elapsed, 3),
                "retries": retry_count,
            })
            rows.append((plan, props, name))
            retry_note = " (retry 1)" if retry_count else ""
            print(f"[{i}/{len(jobs)}] {name} · {elapsed:.2f}s{retry_note}")

    # 갤러리 — 사람 큐레이션용
    cells = "\n".join(
        f'<div class="c"><img src="candidates/{n}"><p>{n}</p></div>'
        for _, _, n in rows)
    (outdir / "gallery.html").write_text(
        '<meta charset="utf-8"><style>body{font-family:sans-serif;background:#111;color:#eee}'
        ".c{display:inline-block;width:31%;margin:1%}.c img{width:100%}p{font-size:11px}</style>"
        f"<h2>scene library candidates — 채택할 파일명을 picks.txt 에 기록</h2>{cells}",
        encoding="utf-8")
    _write_timing_report(
        outdir, args.pilot, load_s, image_timings, n_img,
        generated, skipped, retries, failures,
    )
    print(f"완료 → {outdir}/gallery.html 를 열어 큐레이션 후 finalize 실행")


def _parse_picks_line(line: str) -> tuple[str, float | None]:
    """`파일명.png [surface_y=0.73]` 형식. surface_y 생략 시 플랜 기본값 사용."""
    parts = line.split()
    name = parts[0]
    surface_y = None
    for tok in parts[1:]:
        if tok.startswith("surface_y="):
            surface_y = float(tok.removeprefix("surface_y="))
    if surface_y is not None and not (0.0 <= surface_y <= 1.0):
        sys.exit(f"surface_y 범위 오류(0~1): {line}")
    return name, surface_y


def cmd_finalize(args) -> None:
    outdir = Path(args.outdir)
    cand_dir = outdir / "candidates"
    picks = [_parse_picks_line(line.strip())
             for line in Path(args.picks).read_text().splitlines()
             if line.strip() and not line.startswith("#")]
    if not picks:
        sys.exit("picks 비어있음")
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    by_key = {p.key: p for p in scene_plans.PLANS}
    validated = []
    for name, surface_y in picks:
        src = cand_dir / name
        if not src.exists():
            sys.exit(f"후보 없음: {name}")
        try:
            plan_key = _plan_key_from_candidate(name)
        except ValueError as exc:
            sys.exit(str(exc))
        plan = by_key[plan_key]
        if surface_y is None and plan.render_mode != "code" and not plan.requires_recompose:
            sys.exit(
                f"surface_y 누락(Tier2 이미지는 실측 오버라이드 필수, SSOT S-0#4): {name}"
            )
        props = [] if "__none__" in name else name.split("__")[1].split("-")
        validated.append((name, src, plan_key, props, surface_y, _sha256(src)))

    try:
        entries = _load_manifest_entries()
    except ValueError as exc:
        sys.exit(str(exc))
    seen = _manifest_plan_indices(entries)
    for name, src, plan_key, props, surface_y, source_hash in validated:
        duplicate = next(
            (
                entry for entry in entries
                if entry["plan"] == plan_key and entry["sha256"] == source_hash
                and (outdir / str(entry["file"])).is_file()
                and _sha256(outdir / str(entry["file"])) == source_hash
            ),
            None,
        )
        if duplicate is not None:
            print(f"이미 채택됨 {plan_key} ← {name}")
            continue
        seen[plan_key] = seen.get(plan_key, 0) + 1
        dst = outdir / f"{plan_key.replace('/', '_')}__{seen[plan_key]}.png"
        shutil.copy(src, dst)
        entry = {
            "plan": plan_key, "file": dst.name, "sha256": _sha256(dst),
            "version": 1, "props": props, "curated_by": args.curated_by,
        }
        if surface_y is not None:
            entry["surface_y"] = round(surface_y, 3)
        entries.append(entry)
        print(f"채택 {plan_key} ← {name}" + (f" (surface_y={surface_y})" if surface_y else ""))
    _write_manifest_entries(entries)
    missing = {p.key for p in scene_plans.PLANS
               if not p.requires_recompose} - {str(entry["plan"]) for entry in entries}
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
    b.add_argument("--pilot", action="store_true", help="P4B 고정 24장 계약으로 빌드")
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
